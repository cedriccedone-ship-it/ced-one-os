"""Strict export parsing and economic boundary isolation, without native replay."""
from copy import deepcopy
import hashlib
import json

import pytest

from scripts.local_historical_replay import write_demo_dataset
from ced_one.business_divisions.trading.historical_market_data import load_dataset, digest, validate_binding


@pytest.fixture
def export(tmp_path):
    return write_demo_dataset(tmp_path)


def change_csv(paths, transform):
    csv, manifest, _, _ = paths
    csv.write_text(transform(csv.read_text()), encoding="utf-8")
    m = json.loads(manifest.read_text())
    m["csv_sha256"] = hashlib.sha256(csv.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(m), encoding="utf-8")


def test_closed_candles_and_distinct_anchor_observations(export):
    csv, manifest, config, _ = export
    dataset = load_dataset(csv, manifest)
    run = json.loads(config.read_text())
    factual = dataset.factual_input(run["T"], run["strategy_definition"])
    assert factual["timeframe_histories"]["M1"][-1]["timestamp"] < run["T"]
    assert dataset.observation_rows(run["T"])[0] == factual["timeframe_histories"]["M1"][-1]
    assert dataset.observation_rows(run["T"])[1]["timestamp"] == run["T"]
    assert factual["timeframe_histories"]["D1"] == factual["timeframe_histories"]["M30"] == []
    binding = dataset.binding(factual)
    assert binding["dataset_sha256"] == hashlib.sha256(csv.read_bytes()).hexdigest()
    assert binding["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    changed = deepcopy(factual)
    changed["symbol"] = "other"
    with pytest.raises(ValueError, match="mismatch"):
        validate_binding(binding, changed)


@pytest.mark.parametrize("change", ["hash", "header", "duplicate", "timezone_duplicate", "unordered", "naive", "offgrid",
    "nan", "infinity", "zero", "negative", "underscore", "whitespace", "ohlc", "extra_column", "missing_column", "timeframe", "quote"])
def test_invalid_csv_is_rejected(export, change):
    csv, manifest, _, _ = export
    if change == "hash":
        csv.write_bytes(csv.read_bytes()+b"\n")
    else:
        def edit(value):
            if change == "quote": return value.splitlines()[0]+'\nM1,"unterminated\n'
            rows = value.splitlines()
            first = rows[1].split(",")
            if change == "header": rows[0] += ",extra"
            elif change in ("duplicate", "timezone_duplicate"):
                repeated = rows[1].replace("Z,", "+00:00,") if change == "timezone_duplicate" else rows[1]
                rows.insert(2, repeated)
            elif change == "unordered": rows[1], rows[2] = rows[2], rows[1]
            elif change == "naive": first[1] = first[1].replace("Z", "")
            elif change == "offgrid": first[1] = first[1].replace(":00Z", ":01Z")
            elif change in ("nan", "infinity", "zero", "negative"):
                first[2] = {"nan":"NaN", "infinity":"Infinity", "zero":"0", "negative":"-1"}[change]
            elif change == "underscore": first[2] = "1_000"
            elif change == "whitespace": first[2] = " 100"
            elif change == "ohlc": first[3] = "1"
            elif change == "extra_column": first.append("unexpected")
            elif change == "missing_column": first.pop()
            elif change == "timeframe": first[0] = "M2"
            if change not in ("duplicate", "timezone_duplicate", "unordered"): rows[1] = ",".join(first)
            return "\n".join(rows)+"\n"
        change_csv(export, edit)
    with pytest.raises((ValueError, TypeError)):
        load_dataset(csv, manifest)


@pytest.mark.parametrize("change", ["symbol", "version", "session", "overlap", "coverage", "endpoint", "extra"])
def test_invalid_manifest_or_session_is_rejected(export, change):
    csv, manifest, _, _ = export
    m = json.loads(manifest.read_text())
    if change == "symbol": m["symbol"] = "GOLD"
    elif change == "version": m["contract"] = "unknown"
    elif change == "session": m["sessions"] = []
    elif change == "overlap": m["sessions"] *= 2
    elif change == "coverage": m["timeframes"]["M1"]["coverage_end"] = m["timeframes"]["M1"]["coverage_start"]
    elif change == "endpoint": m["dataset_end"] = m["timeframes"]["M1"]["coverage_start"]
    else: m["api_secret"] = "must-not-be-stored"
    manifest.write_text(json.dumps(m))
    with pytest.raises(ValueError): load_dataset(csv, manifest)


def test_duplicate_json_and_nonfinite_json_are_rejected(export):
    csv, manifest, _, _ = export
    original = manifest.read_text()
    for invalid in ('{"contract":"x",'+original[1:], original.replace('"dataset_end": null', '"dataset_end": NaN')):
        manifest.write_text(invalid)
        with pytest.raises(ValueError): load_dataset(csv, manifest)


def test_missing_candles_are_preserved_and_sessions_do_not_fill(export):
    csv, manifest, config, _ = export
    run = json.loads(config.read_text())
    before = load_dataset(csv, manifest)
    removed = before.histories["M1"][2]["timestamp"]
    change_csv(export, lambda s: "\n".join(row for row in s.splitlines() if ","+removed+"," not in row)+"\n")
    after = load_dataset(csv, manifest)
    assert len(after.histories["M1"]) == len(before.histories["M1"])-1
    assert digest(after.factual_input(run["T"], run["strategy_definition"])) != digest(before.factual_input(run["T"], run["strategy_definition"]))


def test_post_t_data_do_not_enter_native_candidate_input(tmp_path):
    a = write_demo_dataset(tmp_path/"target")
    b = write_demo_dataset(tmp_path/"stop", case="stop")
    first, second = load_dataset(*a[:2]), load_dataset(*b[:2])
    run = json.loads(a[2].read_text())
    assert first.dataset_sha256 != second.dataset_sha256
    assert first.factual_input(run["T"], run["strategy_definition"]) == second.factual_input(run["T"], run["strategy_definition"])
    assert first.observation_rows(run["T"]) != second.observation_rows(run["T"])


def test_loaded_data_and_binding_are_isolated(export):
    dataset = load_dataset(*export[:2])
    before = dataset.histories
    mutated = dataset.histories
    mutated["M1"][0]["high"] += 100
    changed_manifest = dataset.manifest
    changed_manifest["dataset_revision"] = "changed"
    assert dataset.histories == before
    assert dataset.manifest["dataset_revision"] == "v1"


def test_explicit_non_utc_offset_normalizes_to_same_economic_time(export):
    from datetime import timedelta
    from ced_one.business_divisions.trading.validation import parse_timestamp
    dataset = load_dataset(*export[:2])
    def offset_csv(value):
        lines = value.splitlines()
        for i in range(1, len(lines)):
            fields = lines[i].split(",")
            fields[1] = parse_timestamp(fields[1]).astimezone(__import__('datetime').timezone(timedelta(hours=2))).isoformat()
            lines[i] = ",".join(fields)
        return "\n".join(lines)+"\n"
    change_csv(export, offset_csv)
    assert load_dataset(*export[:2]).histories == dataset.histories
