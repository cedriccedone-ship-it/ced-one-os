"""Strict instrument facts, independent availability and no financial authority."""
from copy import deepcopy
from decimal import localcontext
import ast
import inspect
from itertools import product

import pytest

from ced_one.business_divisions.trading import causal_financial_instrument_contract_metadata_snapshot as owner


def sample():
    return dict(contract=owner.CONTRACT, rule_version=owner.RULE_VERSION,
        requested_evaluation_timestamp="2026-10-24T12:00:00Z", specification=dict(
            source=dict(source_id=" metadata supplier ", source_contract="instrument-report", source_contract_version="1", source_snapshot_id="revision-1"),
            position_namespace=dict(source_id="account-provider", source_contract="account-report", source_contract_version="2",
                                    environment="DEMO", instrument_id="source:XAU", quantity_unit=" lot "),
            timing=dict(effective_at="2026-10-26T00:00:00Z", observed_at="2026-10-24T11:00:00Z", source_available_at="2026-10-24T10:30:00Z"),
            economic_model=owner.MODEL, completeness="COMPLETE",
            economics=dict(reference_asset_id="gold", reference_unit="troy ounce", reference_units_per_quantity_unit="100.000", price_currency="USD")))


def run(value):
    return owner.CAUSAL_FINANCIAL_INSTRUMENT_CONTRACT_METADATA_SNAPSHOT.analyze(value).to_dict()


def validate(value, source):
    return owner.validate_causal_financial_instrument_contract_metadata_snapshot(value, source)


def at(value, path):
    for key in path: value = value[key]
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
    if type(value) is list: return [reversed_maps(child) for child in value]
    return value


OBJECTS = [()] + [path for path in paths(sample()) if type(at(sample(), path)) is dict]


@pytest.mark.parametrize("path", OBJECTS)
def test_exact_schemas(path):
    original = sample()
    for key in at(original, path):
        value = deepcopy(original); del at(value, path)[key]
        with pytest.raises(ValueError): run(value)
    value = deepcopy(original); at(value, path)["extra"] = True
    with pytest.raises(ValueError): run(value)
    for bad in (None, [], "object", True, 1):
        value = sample()
        if path: replace(value, path, bad)
        else: value = bad
        with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("path", [("contract",), ("rule_version",), ("specification", "completeness"),
    ("specification", "position_namespace", "environment")])
@pytest.mark.parametrize("bad", [None, True, 1, [], "", "unknown", " demo "])
def test_closed_values(path, bad):
    value = sample(); replace(value, path, bad)
    with pytest.raises(ValueError): run(value)


OPAQUES = [("specification", "source", key) for key in sample()["specification"]["source"]]
OPAQUES += [("specification", "position_namespace", key) for key in sample()["specification"]["position_namespace"] if key != "environment"]
OPAQUES += [("specification", "economics", key) for key in ("reference_asset_id", "reference_unit")]


@pytest.mark.parametrize("path", OPAQUES)
def test_opaque_preservation_and_types(path):
    value = sample(); replace(value, path, " exact ID ")
    assert at(run(value), path) == " exact ID "
    for bad in ("", " \n\t", 1, True, []):
        replace(value, path, bad)
        with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("model", [owner.MODEL, "other-model", None])
@pytest.mark.parametrize("mask", list(product([False, True], repeat=4)))
@pytest.mark.parametrize("status", ["COMPLETE", "PARTIAL", "UNAVAILABLE"])
def test_total_support_completeness_matrix(model, mask, status):
    value = sample(); spec = value["specification"]
    spec.update(economic_model=model, completeness=status)
    for key, present in zip(spec["economics"], mask):
        if not present: spec["economics"][key] = None
    count = sum(mask)
    expected = "COMPLETE" if count == 4 else "PARTIAL" if count else "UNAVAILABLE"
    valid = status == expected and (model == owner.MODEL or count == 0)
    if not valid:
        with pytest.raises(ValueError): run(value)
    else:
        result = run(value)
        assert result["model_support"] == ("SUPPORTED" if model == owner.MODEL else "UNAVAILABLE" if model is None else "UNSUPPORTED")
        assert result["specification"]["completeness"] == status
        assert validate(result, value) == result


@pytest.mark.parametrize("model", ["", " \t", True, 1, [], {}])
def test_invalid_model(model):
    value = sample(); value["specification"]["economic_model"] = model
    with pytest.raises(ValueError): run(value)


def test_model_no_aliases_or_inference():
    for model in (" LINEAR_REFERENCE_NOTIONAL ", "linear_reference_notional", "inverse"):
        value = sample(); spec = value["specification"]
        spec.update(economic_model=model, completeness="UNAVAILABLE", economics={key: None for key in owner.ECONOMICS})
        result = run(value)
        assert result["model_support"] == "UNSUPPORTED"
        assert result["specification"]["economic_model"] == model
    value = sample(); spec = value["specification"]
    spec["economics"]["reference_unit"] = None; spec["completeness"] = "PARTIAL"
    assert run(value)["specification"]["economics"]["reference_unit"] is None


@pytest.mark.parametrize("bad", [0, 1, 1.5, True, False, float("nan"), float("inf"), "NaN", "Infinity", "1e2", "+1", "01", "-01", "1,000", " 1", "1 ", "1\n", ".5", "1.", "", "١", "0", "-0.000", "-1"])
def test_multiplier_invalid_even_when_partial(bad):
    value = sample(); spec = value["specification"]
    spec["economics"]["reference_units_per_quantity_unit"] = bad
    spec["economics"]["reference_unit"] = None; spec["completeness"] = "PARTIAL"
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("bad", ["usd", "US", "USDD", " USD", "US1", "ÜSD", True, 123, []])
def test_currency(bad):
    value = sample(); value["specification"]["economics"]["price_currency"] = bad
    with pytest.raises(ValueError): run(value)


def test_decimal_precision_and_equivalence():
    value = sample()
    for raw, canonical in [("120.5000", "120.5"), ("1000", "1000"), ("0.00000000000000000100", "0.000000000000000001")]:
        value["specification"]["economics"]["reference_units_per_quantity_unit"] = raw
        with localcontext() as ctx:
            ctx.prec = 1
            result = run(value)
        assert result["specification"]["economics"]["reference_units_per_quantity_unit"] == canonical
        value["specification"]["economics"]["reference_units_per_quantity_unit"] = canonical
        assert run(value) == result


TIME_PATHS = [("requested_evaluation_timestamp",)] + [("specification", "timing", key) for key in sample()["specification"]["timing"]]


@pytest.mark.parametrize("bad", ["2026-10-24", "2026-10-24T12:00Z", "2026-10-24T12:00:00", "2026-10-24 12:00:00Z",
    "2026-10-24T12:00:60Z", "2026-02-30T12:00:00Z", "2026-10-24T12:00:00.1234567Z",
    "2026-10-24T12:00:00+24:00", "2026-10-24T12:00:00+01:60", "2026-10-24T12:00:00+0100",
    "2026-10-24T12:00:00z", "0000-01-01T00:00:00Z", "0001-01-01T00:00:00+01:00", True, 1])
def test_timestamp_grammar(bad):
    for path in TIME_PATHS:
        value = sample(); replace(value, path, bad)
        with pytest.raises(ValueError): run(value)


def test_temporal_semantics_and_replay():
    value = sample(); original = run(value)
    assert original["effective_start_status"] == "FUTURE_EFFECTIVE"
    for effective in ("2026-10-24T09:00:00Z", value["requested_evaluation_timestamp"]):
        changed = deepcopy(value); changed["specification"]["timing"]["effective_at"] = effective
        assert run(changed)["effective_start_status"] == "EFFECTIVE_FROM_REACHED"
    later = deepcopy(value); later["requested_evaluation_timestamp"] = value["specification"]["timing"]["effective_at"]
    assert run(later)["effective_start_status"] == "EFFECTIVE_FROM_REACHED"
    assert run(later)["snapshot_id"] != original["snapshot_id"]
    assert run(value) == original
    correction = deepcopy(value)
    correction["specification"]["source"]["source_snapshot_id"] = "revision-2"
    correction["specification"]["timing"].update(effective_at="2026-10-20T00:00:00Z", observed_at="2026-10-25T00:00:00Z")
    with pytest.raises(ValueError): run(correction)
    correction["requested_evaluation_timestamp"] = "2026-10-25T00:00:00Z"
    assert run(correction)["effective_start_status"] == "EFFECTIVE_FROM_REACHED"
    with pytest.raises(ValueError): validate(original, correction)


def test_publication_order_and_timezone_equivalence():
    value = sample(); original = run(value)
    for path in TIME_PATHS:
        raw = at(value, path); hour = int(raw[11:13]) + 2
        replace(value, path, raw[:11] + f"{hour:02d}" + raw[13:-1] + ".000000+02:00")
    assert run(value) == original
    for available in (None, "2026-10-24T11:00:00Z"):
        value = sample(); value["specification"]["timing"]["source_available_at"] = available
        assert run(value)["model_support"] == "SUPPORTED"
    value["specification"]["timing"]["source_available_at"] = "2026-10-24T11:00:01Z"
    with pytest.raises(ValueError): run(value)
    for path in (TIME_PATHS[0], ("specification", "timing", "effective_at"), ("specification", "timing", "observed_at")):
        value = sample(); replace(value, path, None)
        with pytest.raises(ValueError): run(value)


def test_exact_result_identity_and_namespace_separation():
    value = sample(); before = deepcopy(value); result = run(value)
    assert set(result) == {"contract", "rule_version", "identity_scope", "snapshot_id", "requested_evaluation_timestamp",
        "specification", "model_support", "effective_start_status", "source_authentication", "limitations", "authority"}
    assert result["identity_scope"] == "snapshot_deterministic"
    assert result["source_authentication"] == "NOT_VERIFIED_BY_THIS_CAPABILITY"
    assert result["authority"] == dict(trade_decision=False, financial_risk=False, execution=False)
    assert result["limitations"] == ["REVISION_SELECTION_NOT_PERFORMED", "FRESHNESS_NOT_EVALUATED", "VALUATION_NOT_PERFORMED", "FINANCIAL_EXPOSURE_NOT_CALCULATED"]
    assert result["specification"]["source"]["source_id"] != result["specification"]["position_namespace"]["source_id"]
    assert result["snapshot_id"] == owner._hash_id("financial_instrument_contract_metadata_snapshot_", {key: val for key, val in result.items() if key != "snapshot_id"})
    assert run(reversed_maps(value)) == result == run(value)
    assert value == before


CHANGES = [(("requested_evaluation_timestamp",), "2026-10-24T13:00:00Z")]
CHANGES += [(("specification", "source", key), "changed") for key in sample()["specification"]["source"]]
CHANGES += [(("specification", "position_namespace", key), "LIVE" if key == "environment" else "changed") for key in sample()["specification"]["position_namespace"]]
CHANGES += [(("specification", "timing", key), val) for key, val in [("effective_at", "2026-10-24T12:00:00Z"), ("observed_at", "2026-10-24T11:30:00Z"), ("source_available_at", None)]]
CHANGES += [(("specification", "economics", key), val) for key, val in [("reference_asset_id", "other"), ("reference_unit", "gram"), ("reference_units_per_quantity_unit", "20"), ("price_currency", "EUR")]]


@pytest.mark.parametrize("path,replacement", CHANGES)
def test_material_identity(path, replacement):
    value = sample(); original = run(value); replace(value, path, replacement)
    assert run(value)["snapshot_id"] != original["snapshot_id"]
    with pytest.raises(ValueError): validate(original, value)


def test_model_completeness_and_whitespace_identity():
    value = sample(); ids = [run(value)["snapshot_id"]]
    value["specification"]["economics"]["reference_unit"] = None
    value["specification"]["completeness"] = "PARTIAL"
    ids.append(run(value)["snapshot_id"])
    value["specification"]["economics"] = {key: None for key in owner.ECONOMICS}
    value["specification"]["completeness"] = "UNAVAILABLE"
    for model in (owner.MODEL, "other", " other ", None):
        value["specification"]["economic_model"] = model
        ids.append(run(value)["snapshot_id"])
    assert len(set(ids)) == len(ids)


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


@pytest.mark.parametrize("change", ["decimal", "timestamp", "bool_number", "number_bool", "nan", "infinity", "limitations"])
def test_noncanonical_serialization(change):
    value = sample(); result = run(value)
    if change == "decimal": result["specification"]["economics"]["reference_units_per_quantity_unit"] = "100.000"
    elif change == "timestamp": result["requested_evaluation_timestamp"] = value["requested_evaluation_timestamp"]
    elif change == "bool_number": result["authority"]["execution"] = 0
    elif change == "number_bool": result["specification"]["economics"]["reference_units_per_quantity_unit"] = True
    elif change == "limitations": result["limitations"].reverse()
    else: result["specification"]["economics"]["reference_units_per_quantity_unit"] = float("nan" if change == "nan" else "inf")
    with pytest.raises(ValueError): validate(result, value)


def test_mutation_isolation():
    value = sample(); before = deepcopy(value)
    obj = owner.CAUSAL_FINANCIAL_INSTRUMENT_CONTRACT_METADATA_SNAPSHOT.analyze(value)
    result = obj.to_dict(); validated = validate(obj, value)
    assert result == validated and value == before
    value["specification"]["source"]["source_id"] = "caller mutation"
    assert obj.to_dict() == result
    validated["specification"]["economics"]["reference_unit"] = "mutation"
    assert obj.to_dict() == result
    second = validate(result, before)
    result["specification"]["position_namespace"]["environment"] = "LIVE"
    assert second == obj.to_dict()


def test_independent_library_only():
    tree = ast.parse(inspect.getsource(owner))
    modules = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert [name for name in modules if name and name.startswith("ced_one")] == [
        "ced_one.business_divisions.trading.causal_factual_intelligence_envelope"]
    calls = [ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(name.endswith((".now", ".utcnow", ".time", ".execute", ".dispatch")) for name in calls)
