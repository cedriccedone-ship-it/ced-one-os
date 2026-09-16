"""Shared candle validation; causal completion is owned by the snapshot layer."""
from datetime import datetime, timezone
import math
from typing import Any

TIMEFRAMES = {"D1", "H4", "H1", "M30", "M15", "M5", "M1"}


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an ISO-8601 string.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must include an explicit timezone.")
    return parsed.astimezone(timezone.utc)


def validate_prices(candle: dict[str, Any], names=("open", "high", "low", "close")) -> list[str]:
    errors = []
    values = {}
    for name in names:
        try:
            value = candle[name]
            number = float(value)
            if isinstance(value, bool) or not math.isfinite(number) or number <= 0:
                raise ValueError()
            values[name] = number
        except (KeyError, TypeError, ValueError, OverflowError):
            errors.append(f"Invalid numeric {name}: must be finite and greater than 0.")
    if all(name in values for name in ("open", "high", "low", "close")):
        if values["high"] < max(values["open"], values["close"]) or values["low"] > min(values["open"], values["close"]):
            errors.append("Impossible OHLC: inconsistent high/low boundaries.")
    return errors


def validate_history(history: Any, *, allow_empty=False) -> list[str]:
    if not isinstance(history, list):
        return ["Missing required field: candle_history"]
    if not history and not allow_empty:
        return ["Candle history cannot be empty."]
    errors = []
    previous = None
    seen = set()
    for index, candle in enumerate(history):
        if not isinstance(candle, dict):
            errors.append(f"Candle at index {index} must be a dictionary.")
            continue
        errors.extend(f"Candle {index}: {error}" for error in validate_prices(candle))
        try:
            timestamp = parse_timestamp(candle.get("timestamp"))
            if timestamp in seen:
                errors.append(f"Duplicate timestamp at index {index}.")
            if previous is not None and timestamp <= previous:
                errors.append("Timestamps must be strictly increasing.")
            seen.add(timestamp)
            previous = timestamp
        except ValueError as exc:
            errors.append(f"Invalid timestamp at index {index}: {exc}")
    return errors


def validate_detector_input(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["Input payload must be a dictionary."]
    errors = []
    if str(payload.get("symbol", "")).upper() != "XAUUSD":
        errors.append("Unsupported symbol: only XAUUSD is accepted in this slice.")
    if str(payload.get("timeframe", "")).upper() not in TIMEFRAMES:
        errors.append("Unsupported timeframe.")
    try:
        parse_timestamp(payload.get("evaluation_time"))
    except ValueError as exc:
        errors.append(f"Invalid evaluation_time: {exc}")
    return errors + validate_history(payload.get("candle_history"))
