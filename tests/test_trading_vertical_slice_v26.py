"""Point-price facts, causal revision availability and no financial authority."""
from copy import deepcopy
from decimal import localcontext
import ast
import inspect

import pytest

from ced_one.business_divisions.trading import causal_financial_price_observation_snapshot as owner


def sample():
    return dict(contract=owner.CONTRACT, rule_version=owner.RULE_VERSION,
        requested_evaluation_timestamp="2026-10-24T12:00:00Z", observation=dict(
            source=dict(source_id=" price supplier ", source_contract="price-report", source_contract_version="1", source_snapshot_id="price-1"),
            target_namespace=dict(source_id="account-provider", source_contract="account-report", source_contract_version="2",
                                  environment="DEMO", instrument_id="source:XAU"),
            denomination=dict(specification_source=dict(source_id="metadata-provider", source_contract="specification",
                              source_contract_version="3", source_snapshot_id="spec-1"),
                              reference_asset_id=" gold ", reference_unit="troy ounce", price_currency="USD"),
            timing=dict(price_time="2026-10-24T10:00:00Z", observed_at="2026-10-24T11:00:00Z", source_available_at="2026-10-24T10:30:00Z"),
            price_type="MARK", availability="AVAILABLE", price="120.5000"))


def run(value):
    return owner.CAUSAL_FINANCIAL_PRICE_OBSERVATION_SNAPSHOT.analyze(value).to_dict()


def validate(value, source):
    return owner.validate_causal_financial_price_observation_snapshot(value, source)


def at(value, path):
    for key in path:
        value = value[key]
    return value


def replace(value, path, replacement):
    at(value, path[:-1])[path[-1]] = replacement


def paths(value, prefix=()):
    if type(value) is dict:
        for key, child in value.items():
            yield prefix + (key,)
            yield from paths(child, prefix + (key,))


def reversed_maps(value):
    if type(value) is dict:
        return {key: reversed_maps(child) for key, child in reversed(list(value.items()))}
    if type(value) is list:
        return [reversed_maps(child) for child in value]
    return value


OBJECTS = [()] + [path for path in paths(sample()) if type(at(sample(), path)) is dict]
OPAQUES = [("observation", "source", key) for key in sample()["observation"]["source"]]
OPAQUES += [("observation", "target_namespace", key) for key in sample()["observation"]["target_namespace"] if key != "environment"]
OPAQUES += [("observation", "denomination", "specification_source", key) for key in sample()["observation"]["denomination"]["specification_source"]]
OPAQUES += [("observation", "denomination", key) for key in ("reference_asset_id", "reference_unit")]
TIME_PATHS = [("requested_evaluation_timestamp",)] + [("observation", "timing", key) for key in sample()["observation"]["timing"]]


@pytest.mark.parametrize("path", OBJECTS)
@pytest.mark.parametrize("unavailable", [False, True])
def test_exact_schemas(path, unavailable):
    original = sample()
    if unavailable:
        original["observation"].update(availability="UNAVAILABLE", price=None)
    for key in at(original, path):
        value = deepcopy(original)
        del at(value, path)[key]
        with pytest.raises(ValueError): run(value)
    value = deepcopy(original)
    at(value, path)["extra"] = True
    with pytest.raises(ValueError): run(value)
    for bad in (None, [], "object", True, 1):
        value = deepcopy(original)
        if path: replace(value, path, bad)
        else: value = bad
        with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("path", [("contract",), ("rule_version",), ("observation", "price_type"),
    ("observation", "availability"), ("observation", "target_namespace", "environment")])
@pytest.mark.parametrize("bad", [None, True, 1, [], "", "unknown", " demo ", "CANDLE_CLOSE", "mark", "PARTIAL"])
def test_closed_values(path, bad):
    value = sample(); replace(value, path, bad)
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("path", OPAQUES)
def test_opaque_preservation_and_types(path):
    value = sample(); replace(value, path, " exact ID ")
    assert at(run(value), path) == " exact ID "
    for bad in (None, "", " \n\t", 1, True, [], {}):
        replace(value, path, bad)
        with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("bad", [None, "usd", "US", "USDD", " USD", "US1", "ÜSD", True, 123, []])
def test_currency(bad):
    value = sample(); value["observation"]["denomination"]["price_currency"] = bad
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("price_type", ["BID", "ASK", "MID", "MARK", "LAST"])
@pytest.mark.parametrize("availability,price", [("AVAILABLE", "-12.30"), ("AVAILABLE", "0"), ("UNAVAILABLE", None)])
def test_price_types_availability_and_no_derivation(price_type, availability, price):
    value = sample(); value["observation"].update(price_type=price_type, availability=availability, price=price)
    result = run(value)
    assert result["observation"]["price"] == ("-12.3" if price == "-12.30" else price)
    assert result["observation"]["price_type"] == price_type
    assert result["observation"]["availability"] == availability
    assert validate(result, value) == result


@pytest.mark.parametrize("bad", [None, 0, 1, 1.5, True, False, float("nan"), float("inf"), "NaN", "Infinity", "1e2", "+1", "01", "-01", "1,000", " 1", "1 ", "1\n", ".5", "1.", "", "١"])
def test_invalid_available_decimal(bad):
    value = sample(); value["observation"]["price"] = bad
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("bad", ["0", "-1", "NaN", 0, False, [], {}])
def test_unavailable_requires_null(bad):
    value = sample(); value["observation"].update(availability="UNAVAILABLE", price=bad)
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("raw,canonical", [("120.5000", "120.5"), ("1000", "1000"), ("-0.000", "0"), ("-0", "0"), ("0.000", "0"),
    ("-12345678901234567890.12345678900", "-12345678901234567890.123456789"), ("0.00000000000000000100", "0.000000000000000001")])
def test_decimal_precision_and_equivalence(raw, canonical):
    value = sample(); value["observation"]["price"] = raw
    with localcontext() as ctx:
        ctx.prec = 1
        result = run(value)
    assert result["observation"]["price"] == canonical
    value["observation"]["price"] = canonical
    assert run(value) == result


@pytest.mark.parametrize("bad", ["2026-10-24", "2026-10-24T12:00Z", "2026-10-24T12:00:00", "2026-10-24 12:00:00Z",
    "2026-10-24T12:00:60Z", "2026-02-30T12:00:00Z", "2026-10-24T12:00:00.1234567Z",
    "2026-10-24T12:00:00+24:00", "2026-10-24T12:00:00+01:60", "2026-10-24T12:00:00+0100",
    "2026-10-24T12:00:00z", "0000-01-01T00:00:00Z", "0001-01-01T00:00:00+01:00", True, 1, []])
def test_timestamp_grammar(bad):
    for path in TIME_PATHS:
        value = sample(); replace(value, path, bad)
        with pytest.raises(ValueError): run(value)


def test_correction_causal_boundary_and_replay():
    value = sample(); original = run(value)
    correction = deepcopy(value)
    correction["observation"]["source"]["source_snapshot_id"] = "correction-2"
    correction["observation"]["timing"].update(observed_at="2026-10-24T12:05:00Z", source_available_at="2026-10-24T12:04:00Z")
    correction["observation"]["price"] = "121"
    with pytest.raises(ValueError): run(correction)
    correction["requested_evaluation_timestamp"] = "2026-10-24T12:05:00Z"
    revised = run(correction)
    assert revised["observation"]["timing"]["price_time"] == original["observation"]["timing"]["price_time"]
    assert revised["snapshot_id"] != original["snapshot_id"]
    assert run(value) == original
    with pytest.raises(ValueError): validate(original, correction)


@pytest.mark.parametrize("key,time", [("price_time", "2026-10-24T12:01:00Z"), ("price_time", "2026-10-24T11:01:00Z"),
    ("observed_at", "2026-10-24T12:01:00Z"), ("observed_at", "2026-10-24T09:59:00Z"),
    ("source_available_at", "2026-10-24T09:59:00Z"), ("source_available_at", "2026-10-24T11:01:00Z")])
def test_temporal_inversions(key, time):
    value = sample(); value["observation"]["timing"][key] = time
    with pytest.raises(ValueError): run(value)


def test_time_equivalence_null_publication_and_equal_boundaries():
    value = sample(); original = run(value)
    for path in TIME_PATHS:
        raw = at(value, path); hour = int(raw[11:13]) + 2
        replace(value, path, raw[:11] + f"{hour:02d}" + raw[13:-1] + ".000000+02:00")
    assert run(value) == original
    for available in (None, "2026-10-24T10:00:00Z", "2026-10-24T11:00:00Z"):
        value = sample(); value["observation"]["timing"]["source_available_at"] = available
        assert validate(run(value), value) == run(value)
    for path in TIME_PATHS[:-1]:
        value = sample(); replace(value, path, None)
        with pytest.raises(ValueError): run(value)
    value = sample()
    for key in value["observation"]["timing"]:
        value["observation"]["timing"][key] = value["requested_evaluation_timestamp"]
    assert run(value)["observation"]["timing"]["price_time"] == "2026-10-24T12:00:00.000000Z"


def test_exact_result_identity_and_namespace_separation():
    value = sample(); before = deepcopy(value); result = run(value)
    assert set(result) == {"contract", "rule_version", "identity_scope", "snapshot_id", "requested_evaluation_timestamp",
        "observation", "source_authentication", "limitations", "authority"}
    assert result["contract"] == "trading.causal_financial_price_observation_snapshot.v1"
    assert result["rule_version"] == "causal_financial_price_observation_snapshot_v1"
    assert result["identity_scope"] == "snapshot_deterministic"
    assert result["source_authentication"] == "NOT_VERIFIED_BY_THIS_CAPABILITY"
    assert result["authority"] == dict(trade_decision=False, financial_risk=False, execution=False)
    assert result["limitations"] == ["PRICE_SELECTION_NOT_PERFORMED", "FRESHNESS_NOT_EVALUATED", "PRICE_SUITABILITY_NOT_EVALUATED",
        "SPECIFICATION_COMPATIBILITY_NOT_VALIDATED", "VALUATION_NOT_PERFORMED", "FINANCIAL_EXPOSURE_NOT_CALCULATED"]
    obs = result["observation"]
    assert len({obs["source"]["source_id"], obs["target_namespace"]["source_id"], obs["denomination"]["specification_source"]["source_id"]}) == 3
    assert result["snapshot_id"] == owner._hash_id("financial_price_observation_snapshot_", {key: val for key, val in result.items() if key != "snapshot_id"})
    assert run(reversed_maps(value)) == result == run(value)
    assert validate(reversed_maps(result), value) == result
    assert value == before


CHANGES = [(path, at(sample(), path) + " ") for path in OPAQUES]
CHANGES += [(("requested_evaluation_timestamp",), "2026-10-24T13:00:00Z"),
    (("observation", "target_namespace", "environment"), "LIVE"), (("observation", "denomination", "price_currency"), "EUR"),
    (("observation", "price_type"), "BID"), (("observation", "price"), "121")]
CHANGES += [(("observation", "timing", key), val) for key, val in [("price_time", "2026-10-24T09:00:00Z"),
    ("observed_at", "2026-10-24T11:30:00Z"), ("source_available_at", None)]]


@pytest.mark.parametrize("path,replacement", CHANGES)
def test_material_identity(path, replacement):
    value = sample(); original = run(value); replace(value, path, replacement)
    assert run(value)["snapshot_id"] != original["snapshot_id"]
    with pytest.raises(ValueError): validate(original, value)


def test_availability_identity():
    value = sample(); original = run(value)
    value["observation"].update(availability="UNAVAILABLE", price=None)
    assert run(value)["snapshot_id"] != original["snapshot_id"]
    with pytest.raises(ValueError): validate(original, value)


def test_owner_tamper_all_fields():
    value = sample(); result = run(value)
    for path in paths(result):
        for remove in (False, True):
            changed = deepcopy(result)
            if remove: del at(changed, path[:-1])[path[-1]]
            else: replace(changed, path, "tampered")
            with pytest.raises(ValueError): validate(changed, value)
    for path in [()] + [path for path in paths(result) if type(at(result, path)) is dict]:
        changed = deepcopy(result); at(changed, path)["extra"] = True
        with pytest.raises(ValueError): validate(changed, value)


@pytest.mark.parametrize("change", ["decimal", "timestamp", "bool_number", "number_bool", "nan", "infinity", "limitations", "authority"])
def test_noncanonical_serialization(change):
    value = sample(); result = run(value)
    if change == "decimal": result["observation"]["price"] = "120.5000"
    elif change == "timestamp": result["requested_evaluation_timestamp"] = value["requested_evaluation_timestamp"]
    elif change == "bool_number": result["authority"]["execution"] = 0
    elif change == "number_bool": result["observation"]["price"] = True
    elif change == "limitations": result["limitations"].reverse()
    elif change == "authority": result["authority"]["financial_risk"] = True
    else: result["observation"]["price"] = float("nan" if change == "nan" else "inf")
    with pytest.raises(ValueError): validate(result, value)


def test_mutation_isolation():
    value = sample(); before = deepcopy(value)
    obj = owner.CAUSAL_FINANCIAL_PRICE_OBSERVATION_SNAPSHOT.analyze(value)
    result = obj.to_dict(); validated = validate(obj, value)
    assert result == validated and value == before
    value["observation"]["source"]["source_id"] = "caller mutation"
    assert obj.to_dict() == result
    validated["observation"]["denomination"]["specification_source"]["source_id"] = "mutation"
    assert obj.to_dict() == result
    second = validate(result, before)
    result["observation"]["target_namespace"]["environment"] = "LIVE"
    result["limitations"].clear()
    assert second == obj.to_dict()


def test_independent_library_only():
    tree = ast.parse(inspect.getsource(owner))
    modules = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert [name for name in modules if name and name.startswith("ced_one")] == [
        "ced_one.business_divisions.trading.causal_factual_intelligence_envelope"]
    calls = [ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(name.endswith((".now", ".utcnow", ".time", ".execute", ".dispatch")) for name in calls)
