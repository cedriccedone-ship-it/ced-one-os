"""Bounded local exports; candle closure is a research availability assumption."""
from copy import deepcopy
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import re

from .causal_snapshot_availability import VALID_TIMEFRAME_DURATIONS
from .validation import parse_timestamp, validate_prices

CONTRACT = "trading.historical_market_data.v1"
ORDER = tuple(VALID_TIMEFRAME_DURATIONS)
MAX_BYTES = 16 * 1024 * 1024


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def stamp(at):
    return at.isoformat().replace("+00:00", "Z")


def exact(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError(label + " has invalid fields")


def text(value):
    if type(value) is not str or not value.strip():
        raise ValueError("Expected nonempty text")


def sha(value):
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Invalid SHA256")


def read_bytes(path):
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Local input exceeds 16 MiB")
    return data


def json_text(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("Nonfinite JSON constant")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def validate_manifest(m):
    exact(m, {"contract", "symbol", "source_namespace", "dataset_id", "dataset_revision", "price_basis",
              "csv_sha256", "timeframes", "sessions", "dataset_end"}, "Manifest")
    if m["contract"] != CONTRACT or m["symbol"] != "XAUUSD" or m["price_basis"] not in ("BID", "ASK", "MID", "LAST"):
        raise ValueError("Unsupported export contract, symbol or price basis")
    for k in ("source_namespace", "dataset_id", "dataset_revision"):
        text(m[k])
    sha(m["csv_sha256"])
    specs = m["timeframes"]
    if type(specs) is not dict or not specs or not set(specs) <= set(ORDER):
        raise ValueError("Invalid timeframe manifest")
    for tf, spec in specs.items():
        exact(spec, {"anchor", "coverage_start", "coverage_end"}, "Timeframe")
        a, b, c = (parse_timestamp(spec[k]) for k in ("anchor", "coverage_start", "coverage_end"))
        if b >= c or (b-a) % VALID_TIMEFRAME_DURATIONS[tf] or a.microsecond or a.second:
            raise ValueError("Invalid timeframe coverage/grid")
    if type(m["sessions"]) is not list:
        raise ValueError("Sessions must be a list")
    previous = None
    for interval in m["sessions"]:
        exact(interval, {"open", "close"}, "Session")
        a, b = (parse_timestamp(interval[k]) for k in ("open", "close"))
        if a >= b or (previous is not None and a < previous):
            raise ValueError("Sessions must be ordered, disjoint half-open intervals")
        previous = b
    if m["dataset_end"] is not None:
        end = parse_timestamp(m["dataset_end"])
        if "M1" not in specs or end < parse_timestamp(specs["M1"]["coverage_start"]):
            raise ValueError("Invalid M1 dataset endpoint")
    return m


def validate_binding(binding, payload):
    exact(binding, {"contract", "dataset_sha256", "manifest_sha256", "manifest_json", "imported_at", "input_sha256"}, "Import binding")
    if binding["contract"] != CONTRACT:
        raise ValueError("Unsupported import binding")
    for k in ("dataset_sha256", "manifest_sha256", "input_sha256"):
        sha(binding[k])
    if type(binding["manifest_json"]) is not str:
        raise ValueError("Invalid manifest text")
    manifest = validate_manifest(json_text(binding["manifest_json"]))
    if (hashlib.sha256(binding["manifest_json"].encode()).hexdigest() != binding["manifest_sha256"] or
            manifest["csv_sha256"] != binding["dataset_sha256"] or digest(payload) != binding["input_sha256"]):
        raise ValueError("Import identity/input mismatch")
    if parse_timestamp(binding["imported_at"]) > datetime.now(timezone.utc):
        raise ValueError("Future import time")
    return deepcopy(binding)


@dataclass(frozen=True)
class HistoricalDataset:
    manifest_json: str
    dataset_sha256: str
    imported_at: str
    _histories_json: str

    @property
    def manifest(self):
        return json_text(self.manifest_json)

    @property
    def histories(self):
        return json_text(self._histories_json)

    def binding(self, payload):
        return validate_binding(dict(contract=CONTRACT, dataset_sha256=self.dataset_sha256,
            manifest_sha256=hashlib.sha256(self.manifest_json.encode()).hexdigest(), manifest_json=self.manifest_json,
            imported_at=self.imported_at, input_sha256=digest(payload)), payload)

    def factual_input(self, at, definition):
        at = parse_timestamp(at)
        original = self.histories
        histories = {}
        for tf in ORDER:
            # Explicit strategy evidence domains; other slots retain export coverage.
            spec = self.manifest["timeframes"].get(tf)
            left = definition["configuration"]["history_starts"].get(tf, spec["coverage_start"] if spec else stamp(at))
            histories[tf] = [deepcopy(c) for c in original[tf]
                             if parse_timestamp(left) <= parse_timestamp(c["timestamp"]) and
                             parse_timestamp(c["timestamp"]) + VALID_TIMEFRAME_DURATIONS[tf] <= at]
        return dict(symbol="XAUUSD", requested_evaluation_timestamp=stamp(at), timeframe_histories=histories)

    def observation_rows(self, at):
        at = parse_timestamp(at)
        return [deepcopy(c) for c in self.histories["M1"]
                if at-timedelta(minutes=1) <= parse_timestamp(c["timestamp"]) < at+timedelta(hours=24)]


def load_dataset(csv_path, manifest_path):
    raw, manifest_raw = read_bytes(csv_path), read_bytes(manifest_path)
    manifest_text = manifest_raw.decode("utf-8")
    m = validate_manifest(json_text(manifest_text))
    identity = hashlib.sha256(raw).hexdigest()
    if identity != m["csv_sha256"]:
        raise ValueError("CSV SHA256 mismatch")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""), strict=True)
    try:
        fields = reader.fieldnames
    except csv.Error:
        raise ValueError("Malformed CSV header") from None
    if fields != ["timeframe", "timestamp", "open", "high", "low", "close"]:
        raise ValueError("Invalid CSV header")
    def rows():
        try:
            yield from reader
        except csv.Error:
            raise ValueError("Malformed CSV row") from None
    histories = {tf: [] for tf in ORDER}
    sessions = [(parse_timestamp(s["open"]), parse_timestamp(s["close"])) for s in m["sessions"]]
    last_order = -1
    for row in rows():
        if set(row) != set(reader.fieldnames) or any(v is None for v in row.values()):
            raise ValueError("Malformed CSV row")
        tf = row["timeframe"]
        if tf not in m["timeframes"] or ORDER.index(tf) < last_order:
            raise ValueError("Undeclared or unordered timeframe")
        last_order = ORDER.index(tf)
        at = parse_timestamp(row["timestamp"])
        spec, duration = m["timeframes"][tf], VALID_TIMEFRAME_DURATIONS[tf]
        if ((at-parse_timestamp(spec["anchor"])) % duration or at < parse_timestamp(spec["coverage_start"]) or
                at+duration > parse_timestamp(spec["coverage_end"])):
            raise ValueError("Candle outside declared grid/coverage")
        if histories[tf] and at <= parse_timestamp(histories[tf][-1]["timestamp"]):
            raise ValueError("Duplicate or unordered candle")
        if tf == "M1":
            if not any(a <= at and at+duration <= b for a, b in sessions):
                raise ValueError("M1 candle outside declared sessions")
            if m["dataset_end"] is not None and at+duration > parse_timestamp(m["dataset_end"]):
                raise ValueError("M1 candle after dataset endpoint")
        candle = {"timestamp": stamp(at)}
        try:
            for k in ("open", "high", "low", "close"):
                if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", row[k]):
                    raise ValueError("Invalid export price")
                n = Decimal(row[k])
                if not n.is_finite() or n <= 0:
                    raise ValueError("Invalid export price")
                candle[k] = float(n)
        except InvalidOperation:
            raise ValueError("Invalid export price") from None
        if validate_prices(candle):
            raise ValueError("Invalid export OHLC")
        histories[tf].append(candle)
    return HistoricalDataset(manifest_text, identity, stamp(datetime.now(timezone.utc)), json.dumps(histories, allow_nan=False))
