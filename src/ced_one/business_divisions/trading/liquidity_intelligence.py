"""Deterministic XAUUSD liquidity intelligence for Vertical Slice #6.

This module stays read-only, provider-independent, and observational. It maps
confirmed pivot evidence into factual liquidity levels and deterministic
interaction evidence without strategy, execution, or lifecycle semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
import re
from statistics import median
from typing import Any

from ced_one.business_divisions.trading.market_structure import MarketStructureAnalyzer

VALID_TIMEFRAMES = {"D1", "H4", "H1", "M30", "M15", "M5", "M1"}
RULE_VERSION = "liquidity_intelligence_v1"


@dataclass(frozen=True)
class LiquidityIntelligenceConfig:
    lookback_candles: int = 100
    equal_level_tolerance: float = 0.50
    minimum_cluster_members: int = 2
    interaction_tolerance: float = 0.00
    include_single_swing_levels: bool = True

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not isinstance(self.lookback_candles, int):
            errors.append("Invalid config field lookback_candles: must be an integer.")
        elif self.lookback_candles < 3:
            errors.append("Invalid config field lookback_candles: must be at least 3.")

        if not isinstance(self.equal_level_tolerance, (int, float)):
            errors.append("Invalid config field equal_level_tolerance: must be numeric.")
        elif self.equal_level_tolerance <= 0:
            errors.append("Invalid config field equal_level_tolerance: must be greater than 0.")

        if not isinstance(self.minimum_cluster_members, int):
            errors.append("Invalid config field minimum_cluster_members: must be an integer.")
        elif self.minimum_cluster_members < 2:
            errors.append("Invalid config field minimum_cluster_members: must be at least 2.")

        if not isinstance(self.interaction_tolerance, (int, float)):
            errors.append("Invalid config field interaction_tolerance: must be numeric.")
        elif self.interaction_tolerance < 0:
            errors.append("Invalid config field interaction_tolerance: must be greater than or equal to 0.")

        if not isinstance(self.include_single_swing_levels, bool):
            errors.append("Invalid config field include_single_swing_levels: must be a boolean.")
        return errors

    @classmethod
    def from_payload(cls, payload: Any | None) -> "LiquidityIntelligenceConfig":
        if payload is None:
            return cls()
        if isinstance(payload, LiquidityIntelligenceConfig):
            return payload
        if not isinstance(payload, dict):
            raise ValueError("Invalid liquidity intelligence config: config must be a dictionary or LiquidityIntelligenceConfig.")

        valid_keys = {item.name for item in fields(cls)}
        unknown_keys = sorted(set(payload) - valid_keys)
        if unknown_keys:
            raise ValueError(f"Invalid liquidity intelligence config: unknown fields {unknown_keys}.")

        config = cls(**{key: payload.get(key, getattr(cls(), key)) for key in valid_keys})
        errors = config.validate()
        if errors:
            raise ValueError("Invalid liquidity intelligence config: " + "; ".join(errors))
        return config

    def as_dict(self) -> dict[str, Any]:
        return {item.name: getattr(self, item.name) for item in fields(self)}


@dataclass
class LiquidityIntelligenceInput:
    symbol: str
    timeframe: str
    evaluation_time: str
    candle_history: list[dict[str, Any]] = field(default_factory=list)
    config: LiquidityIntelligenceConfig = field(default_factory=LiquidityIntelligenceConfig)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LiquidityIntelligenceInput":
        return cls(
            symbol=str(payload.get("symbol", "XAUUSD")).upper(),
            timeframe=str(payload.get("timeframe", "")).upper(),
            evaluation_time=str(payload.get("evaluation_time", "2026-08-16T10:00:00Z")),
            candle_history=[dict(item) for item in (payload.get("candle_history") or []) if isinstance(item, dict)],
            config=LiquidityIntelligenceConfig.from_payload(payload.get("config")),
        )


@dataclass
class LiquidityIntelligenceResult:
    symbol: str
    timeframe: str
    evaluation_time: str
    timestamp: str
    scanned_candle_count: int
    liquidity_levels: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "evaluation_time": self.evaluation_time,
            "timestamp": self.timestamp,
            "scanned_candle_count": self.scanned_candle_count,
            "liquidity_levels": self.liquidity_levels,
            "summary": self.summary,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }


class LiquidityIntelligenceValidator:
    """Deterministic validation for the liquidity intelligence contract."""

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    @staticmethod
    def validate_input(payload: dict[str, Any], *, evaluation_time: datetime | None = None, max_age_seconds: int = 300) -> list[str]:
        errors: list[str] = []
        if not isinstance(payload, dict):
            return ["Input payload must be a dictionary."]

        symbol = str(payload.get("symbol", "")).upper()
        if symbol != "XAUUSD":
            errors.append("Unsupported symbol: only XAUUSD is accepted in this slice.")

        timeframe = str(payload.get("timeframe", "")).upper()
        if timeframe not in VALID_TIMEFRAMES:
            errors.append(f"Unsupported timeframe: {timeframe or '<missing>'} is not in the allowed deterministic set {sorted(VALID_TIMEFRAMES)}")

        evaluation_time_value = payload.get("evaluation_time")
        if evaluation_time_value is None:
            errors.append("Missing required evaluation_time.")
        else:
            try:
                LiquidityIntelligenceValidator._parse_timestamp(evaluation_time_value)
            except ValueError:
                errors.append("Invalid evaluation_time: must be ISO-8601.")

        candle_history = payload.get("candle_history")
        if not isinstance(candle_history, list):
            return errors + ["Missing required field: candle_history"]
        if not candle_history:
            return errors + ["Candle history cannot be empty."]

        config_value = payload.get("config")
        try:
            LiquidityIntelligenceConfig.from_payload(config_value)
        except ValueError as exc:
            errors.append(str(exc))

        seen_timestamps: set[str] = set()
        last_timestamp: datetime | None = None
        for idx, candle in enumerate(candle_history):
            if not isinstance(candle, dict):
                errors.append(f"Candle at index {idx} must be a dictionary.")
                continue

            required = ["timestamp", "open", "high", "low", "close"]
            for field_name in required:
                if field_name not in candle:
                    errors.append(f"Missing required candle field: {field_name} at index {idx}.")

            if "timestamp" in candle:
                timestamp_value = str(candle["timestamp"])
                if timestamp_value in seen_timestamps:
                    errors.append(f"Duplicate timestamp in candle_history: {timestamp_value}.")
                seen_timestamps.add(timestamp_value)
                try:
                    parsed = LiquidityIntelligenceValidator._parse_timestamp(timestamp_value)
                except ValueError:
                    errors.append(f"Invalid timestamp at index {idx}: must be parseable ISO 8601.")
                    continue
                if last_timestamp is not None and parsed <= last_timestamp:
                    errors.append(f"Timestamps must be strictly increasing; candle at index {idx} is not greater than the previous timestamp.")
                last_timestamp = parsed

            for field_name in ["open", "high", "low", "close"]:
                if field_name not in candle:
                    continue
                try:
                    numeric = float(candle[field_name])
                except (TypeError, ValueError):
                    errors.append(f"Non-numeric value for {field_name} at index {idx}.")
                    continue
                if numeric <= 0:
                    errors.append(f"Invalid numeric value for {field_name} at index {idx}: must be greater than 0.")

            if all(field_name in candle for field_name in ["open", "high", "low", "close"]):
                try:
                    open_value = float(candle["open"])
                    high_value = float(candle["high"])
                    low_value = float(candle["low"])
                    close_value = float(candle["close"])
                except (TypeError, ValueError):
                    continue
                if high_value < max(open_value, close_value):
                    errors.append(f"Impossible OHLC at index {idx}: high must be greater than or equal to max(open, close).")
                if low_value > min(open_value, close_value):
                    errors.append(f"Impossible OHLC at index {idx}: low must be less than or equal to min(open, close).")

        return errors


class LiquidityIntelligenceCapability:
    """Provider-independent deterministic liquidity intelligence capability."""

    def __init__(self):
        self.name = "liquidity_intelligence"
        self.contract = "trading.liquidity_intelligence.v1"
        self.permission_scope = "read_only"
        self.division_name = "trading"
        self.description = "Deterministic factual liquidity intelligence for XAUUSD architecture validation."
        self.metadata = {
            "deterministic_liquidity_intelligence": True,
            "chart_inferred_liquidity": True,
            "observation_only": True,
            "advisory_output": False,
            "strategy_output": False,
            "execution_output": False,
        }

    def validate_input(self, payload: dict[str, Any], *, evaluation_time: datetime | None = None, max_age_seconds: int = 300) -> list[str]:
        validator = LiquidityIntelligenceValidator()
        return validator.validate_input(payload, evaluation_time=evaluation_time, max_age_seconds=max_age_seconds)

    def validate_output(self, payload: dict[str, Any] | None) -> list[str]:
        payload = payload or {}
        errors: list[str] = []
        required = [
            "symbol",
            "timeframe",
            "evaluation_time",
            "timestamp",
            "scanned_candle_count",
            "liquidity_levels",
            "summary",
            "evidence",
            "metadata",
        ]
        for field_name in required:
            if field_name not in payload:
                errors.append(f"Missing required output field: {field_name}")

        forbidden_patterns = {
            "buy": r"\bbuy\b",
            "sell": r"\bsell\b",
            "long": r"\blong\b",
            "short": r"\bshort\b",
            "entry": r"\bentry\b",
            "exit": r"\bexit\b",
            "stop_loss": r"\bstop_loss\b",
            "take_profit": r"\btake_profit\b",
            "risk_reward": r"\brisk_reward\b",
            "setup": r"\bsetup\b",
            "setup_quality": r"\bsetup_quality\b",
            "trade_target": r"\btrade_target\b",
            "profit_target": r"\bprofit_target\b",
            "stop_hunt": r"\bstop_hunt\b",
            "manipulation": r"\bmanipulation\b",
            "smart_money_intent": r"\bsmart_money_intent\b",
            "expected_direction": r"\bexpected_direction\b",
            "probability": r"\bprobability\b",
            "trading_confidence": r"\btrading_confidence\b",
            "trade_recommendation": r"\btrade_recommendation\b",
            "position_size": r"\bposition_size\b",
            "broker_instruction": r"\bbroker_instruction\b",
            "execution_command": r"\bexecution_command\b",
        }
        payload_text = str(payload).lower()
        for forbidden_term, pattern in forbidden_patterns.items():
            if re.search(pattern, payload_text):
                errors.append(f"Forbidden advisory term detected: {forbidden_term}")
        return errors

    def build_result(self, *, payload: dict[str, Any]) -> LiquidityIntelligenceResult:
        return LiquidityIntelligenceAnalyzer().analyze(payload)


class LiquidityIntelligenceSpecialist:
    """Read-only specialist wrapper for deterministic liquidity intelligence."""

    def __init__(self):
        self.name = "liquidity_analyst"
        self.division_name = "trading"
        self.capability_name = "liquidity_intelligence"
        self.permission_scope = "read_only"

    def validate_binding(self, *, division_name: str, specialist_name: str, capability_name: str, permission_scope: str) -> bool:
        return (
            division_name == "trading"
            and specialist_name == "liquidity_analyst"
            and capability_name == "liquidity_intelligence"
            and permission_scope == "read_only"
        )

    def can_mutate_task_lifecycle(self) -> bool:
        return False

    def is_final_authority(self) -> bool:
        return False

    def requires_external_execution(self) -> bool:
        return False

    def requires_live_market_data(self) -> bool:
        return False

    def requires_external_ai(self) -> bool:
        return False

    def analyze_liquidity(self, payload: dict[str, Any], *, evaluation_time: datetime | None = None, max_age_seconds: int = 300) -> LiquidityIntelligenceResult:
        return LiquidityIntelligenceAnalyzer().analyze(payload, evaluation_time=evaluation_time, max_age_seconds=max_age_seconds)


class LiquidityIntelligenceAnalyzer:
    """Deterministic liquidity analyzer for XAUUSD candle history."""

    @staticmethod
    def _normalize_candles(candle_history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for candle in candle_history:
            normalized.append(
                {
                    "timestamp": str(candle["timestamp"]),
                    "open": float(candle["open"]),
                    "high": float(candle["high"]),
                    "low": float(candle["low"]),
                    "close": float(candle["close"]),
                }
            )
        return normalized

    @staticmethod
    def _find_confirmed_pivots(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Reuse Slice #3 pivot evidence, then apply strict two-sided pivot rules.
        swing_highs, swing_lows = MarketStructureAnalyzer._find_confirmed_swings(candles)

        pivots: list[dict[str, Any]] = []
        for swing in swing_highs:
            idx = int(swing["index"])
            if idx <= 0 or idx >= len(candles) - 1:
                continue
            if not (candles[idx]["high"] > candles[idx - 1]["high"] and candles[idx]["high"] > candles[idx + 1]["high"]):
                continue
            pivots.append(
                {
                    "pivot_index": idx,
                    "pivot_timestamp": candles[idx]["timestamp"],
                    "confirmed_at_index": idx + 1,
                    "confirmed_at": candles[idx + 1]["timestamp"],
                    "side": "high",
                    "price": candles[idx]["high"],
                }
            )
        for swing in swing_lows:
            idx = int(swing["index"])
            if idx <= 0 or idx >= len(candles) - 1:
                continue
            if not (candles[idx]["low"] < candles[idx - 1]["low"] and candles[idx]["low"] < candles[idx + 1]["low"]):
                continue
            pivots.append(
                {
                    "pivot_index": idx,
                    "pivot_timestamp": candles[idx]["timestamp"],
                    "confirmed_at_index": idx + 1,
                    "confirmed_at": candles[idx + 1]["timestamp"],
                    "side": "low",
                    "price": candles[idx]["low"],
                }
            )
        return pivots

    @staticmethod
    def _build_clusters(candidates: list[dict[str, Any]], *, side: str, tolerance: float, minimum_members: int) -> list[dict[str, Any]]:
        side_candidates = [item for item in candidates if item["side"] == side]
        side_candidates.sort(key=lambda item: (item["price"], item["pivot_timestamp"]))

        clusters: list[dict[str, Any]] = []
        index = 0
        while index < len(side_candidates):
            group = [side_candidates[index]]
            group_min = side_candidates[index]["price"]
            group_max = side_candidates[index]["price"]
            runner = index + 1
            while runner < len(side_candidates):
                candidate = side_candidates[runner]
                potential_min = min(group_min, candidate["price"])
                potential_max = max(group_max, candidate["price"])
                if (potential_max - potential_min) <= tolerance:
                    group.append(candidate)
                    group_min = potential_min
                    group_max = potential_max
                    runner += 1
                else:
                    break

            if len(group) >= minimum_members:
                clusters.append(
                    {
                        "side": side,
                        "level_type": "equal_high_cluster" if side == "high" else "equal_low_cluster",
                        "members": group,
                    }
                )
                index = runner
            else:
                index += 1

        return clusters

    @staticmethod
    def _event_rank(event_type: str) -> int:
        if event_type == "closed_beyond":
            return 3
        if event_type == "breached":
            return 2
        if event_type == "touched":
            return 1
        return 0

    @staticmethod
    def _status_from_rank(rank: int) -> str:
        if rank >= 3:
            return "closed_beyond"
        if rank == 2:
            return "breached"
        if rank == 1:
            return "touched"
        return "active"

    @staticmethod
    def _interaction_event_for_candle(
        candle: dict[str, Any],
        *,
        side: str,
        lower_boundary: float,
        upper_boundary: float,
    ) -> tuple[str | None, bool]:
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])

        if side == "high":
            if close > upper_boundary:
                return "closed_beyond", False
            if high > upper_boundary:
                return "breached", close <= upper_boundary
            if high >= lower_boundary and high <= upper_boundary:
                return "touched", False
            return None, False

        if close < lower_boundary:
            return "closed_beyond", False
        if low < lower_boundary:
            return "breached", close >= lower_boundary
        if low <= upper_boundary and low >= lower_boundary:
            return "touched", False
        return None, False

    @staticmethod
    def _bars_since(index: int, reference_index: int) -> int:
        if index <= reference_index:
            return 0
        return index - reference_index

    def analyze(self, payload: dict[str, Any], *, evaluation_time: datetime | None = None, max_age_seconds: int = 300) -> LiquidityIntelligenceResult:
        errors = LiquidityIntelligenceValidator.validate_input(payload, evaluation_time=evaluation_time, max_age_seconds=max_age_seconds)
        if errors:
            raise ValueError("Invalid liquidity intelligence input: " + "; ".join(errors))

        input_model = LiquidityIntelligenceInput.from_payload(payload)
        config = input_model.config
        candles = self._normalize_candles(input_model.candle_history)
        last_index = len(candles) - 1
        current_timestamp = candles[-1]["timestamp"]

        confirmed_pivots = self._find_confirmed_pivots(candles)

        candidate_start_index = max(0, len(candles) - config.lookback_candles)
        candidate_pivots = [item for item in confirmed_pivots if item["pivot_index"] >= candidate_start_index]

        high_clusters = self._build_clusters(
            candidate_pivots,
            side="high",
            tolerance=float(config.equal_level_tolerance),
            minimum_members=config.minimum_cluster_members,
        )
        low_clusters = self._build_clusters(
            candidate_pivots,
            side="low",
            tolerance=float(config.equal_level_tolerance),
            minimum_members=config.minimum_cluster_members,
        )
        clusters = high_clusters + low_clusters

        clustered_members: set[tuple[str, str]] = set()
        for cluster in clusters:
            for member in cluster["members"]:
                clustered_members.add((member["side"], member["pivot_timestamp"]))

        single_levels: list[dict[str, Any]] = []
        if config.include_single_swing_levels:
            for pivot in candidate_pivots:
                key = (pivot["side"], pivot["pivot_timestamp"])
                if key in clustered_members:
                    continue
                single_levels.append(
                    {
                        "side": pivot["side"],
                        "level_type": "confirmed_swing_high_level" if pivot["side"] == "high" else "confirmed_swing_low_level",
                        "members": [pivot],
                    }
                )

        level_rows = clusters + single_levels
        levels: list[dict[str, Any]] = []

        for level_index, level in enumerate(level_rows):
            members = sorted(level["members"], key=lambda item: item["pivot_index"])
            member_prices = [float(item["price"]) for item in members]
            member_timestamps = [item["pivot_timestamp"] for item in members]
            member_confirmed_at = [item["confirmed_at"] for item in members]
            member_confirmed_indices = sorted(item["confirmed_at_index"] for item in members)

            representative_price = float(median(member_prices))
            cluster_low = float(min(member_prices)) if "cluster" in level["level_type"] else None
            cluster_high = float(max(member_prices)) if "cluster" in level["level_type"] else None

            if len(members) >= config.minimum_cluster_members and "cluster" in level["level_type"]:
                created_at_index = member_confirmed_indices[config.minimum_cluster_members - 1]
            else:
                created_at_index = int(members[0]["confirmed_at_index"])
            created_at = candles[created_at_index]["timestamp"]

            source_timestamp = min(member_timestamps)
            latest_member_at = max(member_timestamps)

            if cluster_low is None:
                lower_boundary = representative_price - float(config.interaction_tolerance)
                upper_boundary = representative_price + float(config.interaction_tolerance)
            else:
                lower_boundary = cluster_low - float(config.interaction_tolerance)
                upper_boundary = cluster_high + float(config.interaction_tolerance)

            member_indices = {int(item["pivot_index"]) for item in members}
            interaction_records: list[dict[str, Any]] = []
            strongest_rank = 0
            last_interaction_index: int | None = None

            for idx in range(created_at_index + 1, len(candles)):
                if idx in member_indices:
                    continue
                candle = candles[idx]
                event_type, wick_breach_without_close = self._interaction_event_for_candle(
                    candle,
                    side=level["side"],
                    lower_boundary=lower_boundary,
                    upper_boundary=upper_boundary,
                )
                if event_type is None:
                    continue
                event_rank = self._event_rank(event_type)
                strongest_rank = max(strongest_rank, event_rank)
                resulting_status = self._status_from_rank(strongest_rank)
                interaction_records.append(
                    {
                        "candle_timestamp": candle["timestamp"],
                        "event_type": event_type,
                        "observed_high": float(candle["high"]),
                        "observed_low": float(candle["low"]),
                        "observed_close": float(candle["close"]),
                        "applied_boundary": {
                            "lower_boundary": lower_boundary,
                            "upper_boundary": upper_boundary,
                        },
                        "resulting_status": resulting_status,
                        "wick_breach_without_close": wick_breach_without_close,
                    }
                )
                last_interaction_index = idx

            current_status = self._status_from_rank(strongest_rank)
            last_interaction_at = candles[last_interaction_index]["timestamp"] if last_interaction_index is not None else None

            levels.append(
                {
                    "level_id": f"{level['side']}_{level['level_type']}_{level_index + 1}",
                    "side": level["side"],
                    "level_type": level["level_type"],
                    "representative_price": representative_price,
                    "cluster_low": cluster_low,
                    "cluster_high": cluster_high,
                    "member_prices": member_prices,
                    "member_timestamps": member_timestamps,
                    "member_confirmed_at": member_confirmed_at,
                    "member_count": len(members),
                    "source_timestamp": source_timestamp,
                    "created_at": created_at,
                    "latest_member_at": latest_member_at,
                    "bars_since_creation": self._bars_since(last_index, created_at_index),
                    "current_status": current_status,
                    "last_interaction_at": last_interaction_at,
                    "bars_since_last_interaction": (
                        None if last_interaction_index is None else self._bars_since(last_index, last_interaction_index)
                    ),
                    "interaction_count": len(interaction_records),
                    "interactions": interaction_records,
                    "evidence": {
                        "source_pivots": members,
                        "equal_level_tolerance": float(config.equal_level_tolerance),
                        "interaction_tolerance": float(config.interaction_tolerance),
                        "clustering_method": "price_ascending_timestamp_tiebreak_contiguous_max_minus_min",
                        "representative_price_method": "median_member_prices",
                        "status_precedence": ["closed_beyond", "breached", "touched", "active"],
                        "liquidity_rule_version": RULE_VERSION,
                    },
                }
            )

        summary = {
            "active_high_levels": 0,
            "active_low_levels": 0,
            "equal_high_clusters": 0,
            "equal_low_clusters": 0,
            "touched_levels": 0,
            "breached_levels": 0,
            "closed_beyond_levels": 0,
            "wick_breach_without_close_levels": 0,
        }

        for level in levels:
            if level["level_type"] == "equal_high_cluster":
                summary["equal_high_clusters"] += 1
            if level["level_type"] == "equal_low_cluster":
                summary["equal_low_clusters"] += 1
            if level["current_status"] == "active":
                if level["side"] == "high":
                    summary["active_high_levels"] += 1
                else:
                    summary["active_low_levels"] += 1
            if level["current_status"] == "touched":
                summary["touched_levels"] += 1
            if level["current_status"] == "breached":
                summary["breached_levels"] += 1
            if level["current_status"] == "closed_beyond":
                summary["closed_beyond_levels"] += 1
            if any(item["wick_breach_without_close"] for item in level["interactions"]):
                summary["wick_breach_without_close_levels"] += 1

        evidence = {
            "liquidity_rule_version": RULE_VERSION,
            "lookback_candles": config.lookback_candles,
            "candidate_start_index": candidate_start_index,
            "candidate_candle_timestamps": [candle["timestamp"] for candle in candles[candidate_start_index:]],
            "confirmed_pivots_total": len(confirmed_pivots),
            "candidate_pivots_total": len(candidate_pivots),
            "cluster_count": len(clusters),
            "single_level_count": len(single_levels),
        }

        if not levels:
            evidence["reason"] = "insufficient_confirmed_pivots"

        result = LiquidityIntelligenceResult(
            symbol=input_model.symbol,
            timeframe=input_model.timeframe,
            evaluation_time=input_model.evaluation_time,
            timestamp=current_timestamp,
            scanned_candle_count=min(len(candles), config.lookback_candles),
            liquidity_levels=levels,
            summary=summary,
            evidence=evidence,
            metadata={
                "deterministic_liquidity_intelligence": True,
                "chart_inferred_liquidity": True,
                "observation_only": True,
                "advisory_output": False,
                "strategy_output": False,
                "execution_output": False,
                "liquidity_rule_version": RULE_VERSION,
                "authority_scope": "read_only",
                "analysis_scope": "read_only",
            },
        )

        output_errors = LiquidityIntelligenceCapability().validate_output(result.to_dict())
        if output_errors:
            raise ValueError("Invalid liquidity intelligence result: " + "; ".join(output_errors))
        return result


LIQUIDITY_INTELLIGENCE = LiquidityIntelligenceAnalyzer()

__all__ = [
    "LiquidityIntelligenceAnalyzer",
    "LiquidityIntelligenceCapability",
    "LiquidityIntelligenceConfig",
    "LiquidityIntelligenceInput",
    "LiquidityIntelligenceResult",
    "LiquidityIntelligenceSpecialist",
    "LiquidityIntelligenceValidator",
    "LIQUIDITY_INTELLIGENCE",
    "RULE_VERSION",
]
