"""Account facts: strict source contract, causal availability, and no authority."""
from copy import deepcopy
from decimal import localcontext
import ast
import inspect

import pytest

from ced_one.business_divisions.trading import causal_financial_account_state_snapshot as owner


def sample():
    return dict(contract=owner.CONTRACT, rule_version=owner.RULE_VERSION,
        requested_evaluation_timestamp="2026-10-24T12:00:00Z", observation=dict(
            account=dict(account_id=" account-1 ", environment="DEMO", currency="USD", position_mode="HEDGING"),
            source=dict(source_id=" source ", source_contract="account-report", source_contract_version="1", source_snapshot_id="revision-1"),
            timing=dict(effective_at="2026-10-24T10:00:00Z", observed_at="2026-10-24T11:00:00Z", source_available_at="2026-10-24T10:30:00Z"),
            account_measures=dict(completeness="COMPLETE", balance="1000.00", equity="-20.50", used_margin="0.00", free_margin="-30"),
            positions=dict(completeness="COMPLETE", items=[
                dict(position_id="b", instrument_id=" source:XAU ", direction="SHORT", quantity="2.00", quantity_unit=" lot "),
                dict(position_id="a", instrument_id=" source:XAU ", direction="LONG", quantity="1.5000", quantity_unit=" lot ")]),
            pending_obligations=dict(scope="NOT_IN_SCOPE")))


def run(value):
    return owner.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT.analyze(value).to_dict()


def at(value, path):
    for key in path:
        value = value[key]
    return value


def replace(value, path, replacement):
    at(value, path[:-1])[path[-1]] = replacement


def reversed_maps(value):
    if type(value) is dict:
        return {key: reversed_maps(item) for key, item in reversed(list(value.items()))}
    if type(value) is list:
        return [reversed_maps(item) for item in value]
    return value


OBJECT_PATHS = [(), ("observation",)] + [("observation", key) for key in
    ("account", "source", "timing", "account_measures", "positions", "pending_obligations")] + [("observation", "positions", "items", 0)]


@pytest.mark.parametrize("path", OBJECT_PATHS)
def test_exact_schema_at_every_object(path):
    original = sample()
    for key in at(original, path):
        changed = deepcopy(original)
        del at(changed, path)[key]
        with pytest.raises(ValueError): run(changed)
    changed = deepcopy(original); at(changed, path)["extra"] = True
    with pytest.raises(ValueError): run(changed)
    for bad in (None, [], "object", True):
        if not path:
            with pytest.raises(ValueError): run(bad)
        else:
            changed = deepcopy(original); replace(changed, path, bad)
            with pytest.raises(ValueError): run(changed)


@pytest.mark.parametrize("path", [("contract",), ("rule_version",),
    ("observation", "account", "environment"), ("observation", "account", "position_mode"),
    ("observation", "account_measures", "completeness"), ("observation", "positions", "completeness"),
    ("observation", "positions", "items", 0, "direction"), ("observation", "pending_obligations", "scope")])
@pytest.mark.parametrize("bad", ["unsupported", "", None, True, 1, []])
def test_constants_and_vocabularies(path, bad):
    value = sample(); replace(value, path, bad)
    with pytest.raises(ValueError): run(value)


OPAQUE_PATHS = [("observation", "account", "account_id")] + [
    ("observation", "source", key) for key in ("source_id", "source_contract", "source_contract_version", "source_snapshot_id")] + [
    ("observation", "positions", "items", 0, key) for key in ("position_id", "instrument_id", "quantity_unit")]


@pytest.mark.parametrize("path", OPAQUE_PATHS)
def test_opaque_strings(path):
    value = sample(); replace(value, path, " exact opaque ")
    result = run(value)
    if "items" not in path:
        assert at(result, path) == " exact opaque "
    else:
        assert any(row[path[-1]] == " exact opaque " for row in result["observation"]["positions"]["items"])
    for bad in ("", " \t\n", None, True, 1):
        replace(value, path, bad)
        with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("bad", ["usd", "US", "USDD", " USD", "US1", "ÜSD", None, 123])
def test_currency(bad):
    value = sample(); value["observation"]["account"]["currency"] = bad
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("bad", [0, 1, 1.5, True, False, float("nan"), float("inf"), "NaN", "Infinity", "1e2", "+1", "01", "-01", "1,000", " 1", "1 ", "1\n", ".5", "1.", "", "١"])
def test_decimal_grammar(bad):
    for path in (("observation", "account_measures", "balance"), ("observation", "positions", "items", 0, "quantity")):
        value = sample(); replace(value, path, bad)
        with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("raw,canonical", [("120.5000", "120.5"), ("0.00", "0"), ("-0.000", "0"),
    ("-125.300", "-125.3"), ("1000", "1000"), ("0.0000000000000000000010", "0.000000000000000000001")])
def test_decimal_normalization_without_precision_dependency(raw, canonical):
    value = sample(); value["observation"]["account_measures"]["balance"] = raw
    with localcontext() as context:
        context.prec = 1
        result = run(value)
    assert result["observation"]["account_measures"]["balance"] == canonical
    value["observation"]["account_measures"]["balance"] = canonical
    assert run(value) == result


def test_signs_and_no_accounting_equations():
    value = sample()
    for key in ("balance", "equity", "free_margin"):
        value["observation"]["account_measures"][key] = "-5000"
    value["observation"]["account_measures"]["used_margin"] = "-0.000"
    assert run(value)["observation"]["account_measures"]["used_margin"] == "0"
    value["observation"]["account_measures"]["used_margin"] = "-0.1"
    with pytest.raises(ValueError): run(value)
    for quantity in ("0", "0.00", "-0.00", "-0.1"):
        value = sample(); value["observation"]["positions"]["items"][0]["quantity"] = quantity
        with pytest.raises(ValueError): run(value)


TIME_PATHS = [("requested_evaluation_timestamp",)] + [("observation", "timing", key) for key in
    ("effective_at", "observed_at", "source_available_at")]


@pytest.mark.parametrize("bad", ["2026-10-24", "2026-10-24T12:00Z", "2026-10-24T12:00:00", "2026-10-24 12:00:00Z",
    "2026-10-24T12:00:60Z", "2026-02-30T12:00:00Z", "2026-10-24T12:00:00.1234567Z",
    "2026-10-24T12:00:00+24:00", "2026-10-24T12:00:00+01:60", "2026-10-24T12:00:00+0100",
    "2026-10-24T12:00:00z", "2026-10-24T24:00:00Z", "0000-01-01T00:00:00Z", "0001-01-01T00:00:00+01:00", True, 1])
def test_timestamp_grammar(bad):
    for path in TIME_PATHS:
        value = sample(); replace(value, path, bad)
        with pytest.raises(ValueError): run(value)


def test_equivalent_timezones_and_equal_boundaries():
    value = sample(); expected = run(value)
    for path in TIME_PATHS:
        raw = at(value, path)
        hour = int(raw[11:13]) + 2
        replace(value, path, raw[:11] + f"{hour:02d}" + raw[13:-1] + ".000000+02:00")
    assert run(value) == expected
    for path in TIME_PATHS: replace(value, path, "2000-01-01T00:00:00.000001Z")
    assert run(value)["requested_evaluation_timestamp"] == "2000-01-01T00:00:00.000001Z"
    value["observation"]["timing"]["source_available_at"] = None
    assert run(value)["observation"]["timing"]["source_available_at"] is None
    for key in ("effective_at", "observed_at"):
        bad = deepcopy(value); bad["observation"]["timing"][key] = None
        with pytest.raises(ValueError): run(bad)


@pytest.mark.parametrize("key,time", [("effective_at", "11:30:00"), ("observed_at", "12:00:01"),
    ("observed_at", "09:00:00"), ("source_available_at", "09:59:59"), ("source_available_at", "11:00:01")])
def test_temporal_inequalities(key, time):
    value = sample(); value["observation"]["timing"][key] = f"2026-10-24T{time}Z"
    with pytest.raises(ValueError): run(value)


def test_revision_history_is_explicit():
    earlier = sample(); original = run(earlier)
    revision = deepcopy(earlier)
    revision["observation"]["source"]["source_snapshot_id"] = "revision-2"
    revision["observation"]["timing"]["observed_at"] = "2026-10-25T12:00:00Z"
    with pytest.raises(ValueError): run(revision)
    revision["requested_evaluation_timestamp"] = "2026-10-25T12:00:00Z"
    assert run(revision)["snapshot_id"] != original["snapshot_id"]
    assert run(earlier) == original


@pytest.mark.parametrize("count", range(5))
@pytest.mark.parametrize("status", ["COMPLETE", "PARTIAL", "UNAVAILABLE"])
def test_measures_completeness(count, status):
    value = sample(); measures = value["observation"]["account_measures"]
    for index, key in enumerate(owner.MEASURES): measures[key] = "0" if index < count else None
    measures["completeness"] = status
    expected = "COMPLETE" if count == 4 else "UNAVAILABLE" if count == 0 else "PARTIAL"
    if status == expected:
        assert run(value)["observation"]["account_measures"] == measures
    else:
        with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("status", ["COMPLETE", "PARTIAL", "UNAVAILABLE"])
@pytest.mark.parametrize("empty", [False, True])
def test_position_completeness(status, empty):
    value = sample(); positions = value["observation"]["positions"]
    positions["completeness"] = status
    if empty: positions["items"] = []
    if status == "UNAVAILABLE" and not empty:
        with pytest.raises(ValueError): run(value)
    else:
        result = run(value)["observation"]["positions"]
        assert result["completeness"] == status
        assert bool(result["items"]) == (not empty)


@pytest.mark.parametrize("mode", ["NETTING", "HEDGING", "UNKNOWN"])
def test_position_modes(mode):
    value = sample(); value["observation"]["account"]["position_mode"] = mode
    if mode == "NETTING":
        with pytest.raises(ValueError): run(value)
        value["observation"]["positions"]["items"][0]["instrument_id"] = "other"
    assert len(run(value)["observation"]["positions"]["items"]) == 2


def test_invalid_inventory_and_partial_rows():
    for items in (None, (), {}, "positions"):
        value = sample(); value["observation"]["positions"]["items"] = items
        with pytest.raises(ValueError): run(value)
    for different in (False, True):
        value = sample(); rows = value["observation"]["positions"]["items"]
        rows[1] = deepcopy(rows[0])
        if different: rows[1]["quantity"] = "999"
        with pytest.raises(ValueError): run(value)
    value = sample(); value["observation"]["positions"]["completeness"] = "PARTIAL"
    del value["observation"]["positions"]["items"][0]["quantity"]
    with pytest.raises(ValueError): run(value)


def test_output_identity_and_authority():
    value = sample(); before = deepcopy(value); result = run(value)
    assert set(result) == {"contract", "rule_version", "identity_scope", "snapshot_id", "requested_evaluation_timestamp",
        "observation", "source_authentication", "limitations", "authority"}
    assert result["source_authentication"] == "NOT_VERIFIED_BY_THIS_CAPABILITY"
    assert result["authority"] == dict(trade_decision=False, financial_risk=False, execution=False)
    assert result["limitations"] == ["PENDING_OBLIGATIONS_NOT_IN_SCOPE", "FINANCIAL_EXPOSURE_NOT_CALCULATED", "FRESHNESS_NOT_EVALUATED"]
    assert result["observation"]["pending_obligations"] == {"scope": "NOT_IN_SCOPE"}
    assert result["identity_scope"] == "snapshot_deterministic"
    assert result["snapshot_id"] == owner._hash_id("financial_account_state_snapshot_", {key: val for key, val in result.items() if key != "snapshot_id"})
    assert run(reversed_maps(value)) == result == run(value)
    value["observation"]["positions"]["items"].reverse()
    assert run(value) == result
    assert [row["position_id"] for row in result["observation"]["positions"]["items"]] == ["a", "b"]
    assert before == sample()


CHANGES = [(("requested_evaluation_timestamp",), "2026-10-24T13:00:00Z")]
CHANGES += [(("observation", "account", key), val) for key, val in
    [("account_id", "other"), ("environment", "LIVE"), ("currency", "EUR"), ("position_mode", "UNKNOWN")]]
CHANGES += [(("observation", "source", key), "changed") for key in sample()["observation"]["source"]]
CHANGES += [(("observation", "timing", key), val) for key, val in
    [("effective_at", "2026-10-24T09:00:00Z"), ("observed_at", "2026-10-24T11:30:00Z"), ("source_available_at", None)]]
CHANGES += [(("observation", "account_measures", key), "20") for key in owner.MEASURES]
CHANGES += [(("observation", "positions", "items", 0, key), val) for key, val in
    [("position_id", "c"), ("instrument_id", "other"), ("direction", "LONG"), ("quantity", "20"), ("quantity_unit", "contracts")]]
CHANGES += [(("observation", "positions", "completeness"), "PARTIAL")]


@pytest.mark.parametrize("path,replacement", CHANGES)
def test_material_identity_sensitivity(path, replacement):
    value = sample(); original = run(value)
    replace(value, path, replacement)
    assert run(value)["snapshot_id"] != original["snapshot_id"]
    with pytest.raises(ValueError): owner.validate_causal_financial_account_state_snapshot(original, value)


def all_paths(value, prefix=()):
    if type(value) is dict:
        for key, item in value.items():
            yield prefix + (key,)
            yield from all_paths(item, prefix + (key,))
    elif type(value) is list:
        for index, item in enumerate(value):
            yield from all_paths(item, prefix + (index,))


def test_owner_rejects_missing_changed_and_extra_content_at_every_depth():
    value = sample(); result = run(value)
    for path in all_paths(result):
        for remove in (True, False):
            tampered = deepcopy(result)
            if remove: del at(tampered, path[:-1])[path[-1]]
            else: replace(tampered, path, "tampered")
            with pytest.raises(ValueError): owner.validate_causal_financial_account_state_snapshot(tampered, value)
    for path in [()] + [path for path in all_paths(result) if type(at(result, path)) is dict]:
        tampered = deepcopy(result); at(tampered, path)["extra"] = True
        with pytest.raises(ValueError): owner.validate_causal_financial_account_state_snapshot(tampered, value)


@pytest.mark.parametrize("change", ["decimal", "timestamp", "order", "bool_number", "number_bool", "nan", "infinity", "limitations"])
def test_noncanonical_serialized_result(change):
    value = sample(); result = run(value)
    if change == "decimal": result["observation"]["account_measures"]["balance"] = "1000.00"
    elif change == "timestamp": result["requested_evaluation_timestamp"] = value["requested_evaluation_timestamp"]
    elif change == "order": result["observation"]["positions"]["items"].reverse()
    elif change == "bool_number": result["authority"]["execution"] = 0
    elif change == "number_bool": result["observation"]["account_measures"]["balance"] = True
    elif change == "limitations": result["limitations"].reverse()
    else: result["observation"]["account_measures"]["balance"] = float("nan" if change == "nan" else "inf")
    with pytest.raises(ValueError): owner.validate_causal_financial_account_state_snapshot(result, value)


def test_mutation_isolation_and_roundtrip():
    value = sample(); before = deepcopy(value)
    obj = owner.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT.analyze(value)
    result = obj.to_dict()
    assert value == before
    validated = owner.validate_causal_financial_account_state_snapshot(obj, value)
    assert validated == result
    value["observation"]["positions"]["items"].clear()
    assert obj.to_dict() == result
    validated["observation"]["positions"]["items"][0]["quantity"] = "999"
    assert obj.to_dict() == result
    second = owner.validate_causal_financial_account_state_snapshot(result, before)
    result["observation"]["account"]["account_id"] = "mutation"
    assert second == obj.to_dict()


def test_measures_partial_identity_and_fixed_exclusions():
    value = sample(); original = run(value)
    value["observation"]["account_measures"].update(completeness="PARTIAL", balance=None)
    assert run(value)["snapshot_id"] != original["snapshot_id"]
    for key, replacement in [("scope", "COMPLETE"), ("items", [])]:
        value = sample(); value["observation"]["pending_obligations"][key] = replacement
        with pytest.raises(ValueError): run(value)


def test_independent_library_only():
    tree = ast.parse(inspect.getsource(owner))
    modules = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert [name for name in modules if name and name.startswith("ced_one")] == [
        "ced_one.business_divisions.trading.causal_factual_intelligence_envelope"]
    # No wall-clock calls or external activity: datetime is used only for parsing.
    calls = [ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(name.endswith((".now", ".utcnow", ".time", ".execute", ".dispatch")) for name in calls)
