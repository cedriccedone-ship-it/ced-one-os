"""Strict lifecycle evidence, scoped coverage and preserved substantive conflicts."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import ast
import inspect
from itertools import product

import pytest

from ced_one.business_divisions.trading import causal_instrument_specification_lifecycle_evidence_snapshot as owner


def time(hour=10, minute=0):
    return f"2026-10-24T{hour:02d}:{minute:02d}:00Z"


def timing(hour=10, minute=0):
    return dict(observed_at=time(hour, minute), source_available_at=time(hour, minute))


def revision(name="A"):
    return dict(source_id=" metadata source ", source_contract="spec", source_contract_version="1", source_snapshot_id=name)


def statement(kind="APPLIES", name="A"):
    scope = dict(effective_from=time(9), effective_until=None)
    if kind == "SUPERSEDES":
        return dict(kind=kind, predecessor_revision=revision("A"), successor_revision=revision("B"), economic_scope=scope)
    return dict(kind=kind, revision=revision(name), economic_scope=scope)


def assertion(identifier="a", proposition=None):
    return dict(assertion_id=identifier, timing=timing(), statement=statement() if proposition is None else proposition)


def correction(identifier="c", target="a", replacement=None):
    return assertion(identifier, dict(kind="CORRECTS", target_assertion_id=target, replacement_statement=replacement))


def sample():
    return dict(contract=owner.CONTRACT, rule_version=owner.RULE_VERSION, requested_evaluation_timestamp=time(12),
        evidence=dict(source=dict(source_id=" lifecycle reporter ", source_contract="lifecycle", source_contract_version="2", source_snapshot_id="report-1"),
            target_namespace=dict(source_id="account-provider", source_contract="account", source_contract_version="3",
                                  environment="DEMO", instrument_id="XAU", quantity_unit=" lot "),
            timing=timing(12), coverage=dict(declaration_id="coverage-1", timing=timing(11), completeness="COMPLETE",
                assertion_kinds=["APPLIES", "SUPERSEDES", "WITHDRAWS", "CORRECTS"], economic_domain="ALL_ECONOMIC_TIMES",
                source_information_cutoff=time(11), starting_basis="FROM_INCEPTION",
                omissions=dict(assertions_omitted=False, history_truncated=False)),
            assertions=[assertion(), assertion("b", statement("SUPERSEDES")), assertion("w", statement("WITHDRAWS")),
                        correction(replacement=statement("APPLIES", "B"))]))


def analyze(value):
    return owner.CAUSAL_INSTRUMENT_SPECIFICATION_LIFECYCLE_EVIDENCE_SNAPSHOT.analyze(value)


def run(value):
    return analyze(value).to_dict()


def validate(value, source):
    return owner.validate_causal_instrument_specification_lifecycle_evidence_snapshot(value, source)


def at(value, path):
    for key in path:
        value = value[key]
    return value


def replace(value, path, replacement):
    at(value, path[:-1])[path[-1]] = replacement


def paths(value, prefix=()):
    if type(value) is dict:
        items = value.items()
    elif type(value) is list:
        items = enumerate(value)
    else:
        return
    for key, child in items:
        yield prefix + (key,)
        yield from paths(child, prefix + (key,))


OBJECTS = [()] + [p for p in paths(sample()) if type(at(sample(), p)) is dict]
TIMES = [p for p in paths(sample()) if type(at(sample(), p)) is str and at(sample(), p).startswith("2026-")]
OPAQUES = [p for p in paths(sample()) if p[-1] in {"source_id", "source_contract", "source_contract_version", "source_snapshot_id",
    "instrument_id", "quantity_unit", "declaration_id"}]


@pytest.mark.parametrize("path", OBJECTS)
def test_exact_object_schemas(path):
    for key in at(sample(), path):
        value = sample(); del at(value, path)[key]
        with pytest.raises(ValueError): run(value)
    value = sample(); at(value, path)["extra"] = True
    with pytest.raises(ValueError): run(value)
    for bad in (None, [], "", True, 1):
        if bad is None and path and path[-1] == "replacement_statement":
            continue  # Null is the explicit whole-proposition retraction.
        value = sample()
        if path: replace(value, path, bad)
        else: value = bad
        with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("path", OPAQUES)
def test_opaque_strings(path):
    for bad in (None, "", " \t\n", 1, True, [], {}):
        value = sample(); replace(value, path, bad)
        with pytest.raises(ValueError): run(value)
    value = sample(); replace(value, path, " distinct ID ")
    result = run(value)
    # Assertion order is canonicalized; input and output paths need not coincide.
    assert " distinct ID " in str(result)
    assert result["snapshot_id"] != run(sample())["snapshot_id"]


@pytest.mark.parametrize("field", ["contract", "rule_version"])
@pytest.mark.parametrize("bad", [None, True, 1, [], "", "unknown"])
def test_constants(field, bad):
    value = sample(); value[field] = bad
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("bad", [None, True, 1, [], "demo", "LIVE "])
def test_environment(bad):
    value = sample(); value["evidence"]["target_namespace"]["environment"] = bad
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("bad", [None, {}, (), "assertions", True])
def test_assertion_list_type(bad):
    value = sample(); value["evidence"]["assertions"] = bad
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("bad", [None, "", " \n", 1, True, [], {}])
def test_assertion_and_target_identifiers(bad):
    for path in [("evidence", "assertions", 0, "assertion_id"), ("evidence", "assertions", 3, "statement", "target_assertion_id")]:
        value = sample(); replace(value, path, bad)
        with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("bad", [None, True, 1, [], "UNKNOWN", "applies", "REPLACES"])
def test_tagged_union(bad):
    value = sample(); value["evidence"]["assertions"][0]["statement"]["kind"] = bad
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("replacement", [None, statement(), statement("SUPERSEDES"), statement("WITHDRAWS")])
def test_replacement_and_retraction(replacement):
    value = sample(); value["evidence"]["assertions"] = [assertion(), correction(replacement=replacement), correction("d", "c")]
    result = run(value)
    assert len(result["evidence"]["assertions"]) == 3
    assert validate(result, value) == result
    bad = sample(); bad["evidence"]["assertions"][3]["statement"]["replacement_statement"] = correction()["statement"]
    with pytest.raises(ValueError): run(bad)


@pytest.mark.parametrize("kind", ["APPLIES", "SUPERSEDES", "WITHDRAWS"])
def test_intervals_and_future_economics(kind):
    for start, end in [(time(9), time(10)), (time(13), None), (time(13), time(14))]:
        value = sample(); prop = statement(kind); prop["economic_scope"] = dict(effective_from=start, effective_until=end)
        value["evidence"]["assertions"] = [assertion(proposition=prop)]
        assert len(run(value)["evidence"]["assertions"]) == 1
    for end in (time(9), time(8), "bad", False):
        value = sample(); value["evidence"]["assertions"][0]["statement"]["economic_scope"]["effective_until"] = end
        with pytest.raises(ValueError): run(value)


def test_reference_duplicates_and_graph_failures():
    value = sample(); prop = value["evidence"]["assertions"][1]["statement"]
    prop["successor_revision"] = deepcopy(prop["predecessor_revision"])
    with pytest.raises(ValueError): run(value)
    for changed in (False, True):
        value = sample(); duplicate = deepcopy(value["evidence"]["assertions"][0])
        if changed: duplicate["statement"] = statement("WITHDRAWS")
        value["evidence"]["assertions"].append(duplicate)
        with pytest.raises(ValueError): run(value)
    for records in ([correction(target="absent")], [correction(target="c")],
                    [correction("c", "d"), correction("d", "c")],
                    [correction("c", "d"), correction("d", "e"), correction("e", "c")]):
        value = sample(); value["evidence"]["assertions"] = records
        with pytest.raises(ValueError): run(value)


def test_substantive_conflicts_preserved():
    value = sample(); inverse = statement("SUPERSEDES")
    inverse["predecessor_revision"], inverse["successor_revision"] = inverse["successor_revision"], inverse["predecessor_revision"]
    value["evidence"]["assertions"] += [assertion("other", statement("APPLIES", "B")), assertion("inverse", inverse), correction("competing", replacement=statement("WITHDRAWS"))]
    result = run(value)
    assert len(result["evidence"]["assertions"]) == len(value["evidence"]["assertions"])
    assert result["evidence"]["coverage"]["completeness"] == "COMPLETE"
    assert validate(result, value) == result


@pytest.mark.parametrize("status", ["COMPLETE", "LIMITED", "UNKNOWN"])
@pytest.mark.parametrize("flags", list(product([False, True, None, 0], repeat=2)))
def test_coverage_matrix(status, flags):
    value = sample(); cov = value["evidence"]["coverage"]; cov["completeness"] = status
    cov["omissions"] = dict(zip(["assertions_omitted", "history_truncated"], flags))
    if status == "UNKNOWN":
        cov.update(source_information_cutoff=None, starting_basis="UNKNOWN")
        valid = all(flag is None for flag in flags)
    else:
        valid = all(type(flag) is bool for flag in flags) and any(flags) == (status == "LIMITED")
    if valid:
        assert validate(run(value), value) == run(value)
    else:
        with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("field,bad", [("completeness", "PARTIAL"), ("completeness", None), ("starting_basis", "EXPLICIT_STARTING_STATE"),
    ("starting_basis", None), ("economic_domain", "BOUNDED"), ("economic_domain", None),
    ("source_information_cutoff", None), ("assertion_kinds", tuple(owner.KINDS)), ("assertion_kinds", list(reversed(owner.KINDS))),
    ("assertion_kinds", list(owner.KINDS[:-1]))])
def test_invalid_coverage_fields(field, bad):
    value = sample(); value["evidence"]["coverage"][field] = bad
    with pytest.raises(ValueError): run(value)


def test_unknown_coverage_and_empty_complete():
    value = sample(); value["evidence"]["assertions"] = []
    assert run(value)["evidence"]["coverage"]["completeness"] == "COMPLETE"
    value = sample(); cov = value["evidence"]["coverage"]
    cov.update(completeness="UNKNOWN", starting_basis="UNKNOWN", source_information_cutoff=None,
               omissions=dict(assertions_omitted=None, history_truncated=None))
    for item in value["evidence"]["assertions"]: item["timing"]["source_available_at"] = None
    cov["timing"]["source_available_at"] = None
    value["evidence"]["timing"]["source_available_at"] = None
    assert validate(run(value), value) == run(value)
    for field, bad in [("source_information_cutoff", time()), ("starting_basis", "FROM_INCEPTION")]:
        changed = deepcopy(value); changed["evidence"]["coverage"][field] = bad
        with pytest.raises(ValueError): run(changed)


@pytest.mark.parametrize("path", TIMES)
def test_timestamp_grammar(path):
    for bad in [None, True, 1, [], "2026-10-24", "2026-10-24T10:00Z", "2026-10-24T10:00:00", "2026-02-30T10:00:00Z",
        "2026-10-24T10:00:60Z", "2026-10-24T10:00:00.1234567Z", "2026-10-24T10:00:00+24:00",
        "2026-10-24T10:00:00+01:60", "0001-01-01T00:00:00+01:00", "2026-10-24 10:00:00Z"]:
        # Null publication is valid for the report only under this COMPLETE fixture.
        if bad is None and path == ("evidence", "timing", "source_available_at"): continue
        value = sample(); replace(value, path, bad)
        with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("path,new", [
    (("evidence", "timing", "observed_at"), time(13)),
    (("evidence", "timing", "source_available_at"), time(13)),
    (("evidence", "coverage", "timing", "observed_at"), time(13)),
    (("evidence", "coverage", "timing", "source_available_at"), time(12)),
    (("evidence", "coverage", "timing", "source_available_at"), None),
    (("evidence", "coverage", "source_information_cutoff"), time(12)),
    (("evidence", "coverage", "source_information_cutoff"), time(9)),
    (("evidence", "assertions", 0, "timing", "observed_at"), time(13)),
    (("evidence", "assertions", 0, "timing", "source_available_at"), None),
    (("evidence", "assertions", 3, "timing", "observed_at"), time(9)),
    (("evidence", "assertions", 3, "timing", "source_available_at"), time(9)),
])
def test_causal_rejections(path, new):
    value = sample(); replace(value, path, new)
    with pytest.raises(ValueError): run(value)


def test_report_observation_bounds_and_cutoff():
    value = sample(); value["requested_evaluation_timestamp"] = time(14)
    value["evidence"]["coverage"]["timing"] = timing(13)
    with pytest.raises(ValueError): run(value)
    value = sample(); value["requested_evaluation_timestamp"] = time(14)
    value["evidence"]["assertions"][0]["timing"]["observed_at"] = time(13)
    with pytest.raises(ValueError): run(value)
    value = sample(); value["evidence"]["coverage"]["source_information_cutoff"] = time(10)
    value["evidence"]["assertions"][1]["timing"] = timing(10, 1)
    with pytest.raises(ValueError): run(value)


def test_historical_correction_without_lookahead():
    value = sample(); value["requested_evaluation_timestamp"] = time(10, 2)
    value["evidence"]["timing"] = timing(10, 2)
    cov = value["evidence"]["coverage"]; cov["timing"] = timing(10, 2); cov["source_information_cutoff"] = time(10, 2)
    value["evidence"]["assertions"] = [assertion()]
    original = run(value)
    corrected = deepcopy(value); row = correction(replacement=statement("APPLIES", "B")); row["timing"] = timing(10, 5)
    corrected["evidence"]["assertions"].append(row)
    with pytest.raises(ValueError): run(corrected)
    corrected["requested_evaluation_timestamp"] = time(10, 6)
    corrected["evidence"]["timing"] = timing(10, 6)
    corrected["evidence"]["coverage"].update(timing=timing(10, 6), source_information_cutoff=time(10, 6))
    result = run(corrected)
    assert len(result["evidence"]["assertions"]) == 2
    assert result["evidence"]["assertions"][1]["statement"]["replacement_statement"]["economic_scope"]["effective_from"] == "2026-10-24T09:00:00.000000Z"
    assert run(value) == original
    with pytest.raises(ValueError): validate(original, corrected)


def test_identity_normalization_and_exact_output():
    value = sample(); result = run(value)
    for path in TIMES:
        parsed = datetime.fromisoformat(at(value, path).replace("Z", "+00:00"))
        replace(value, path, parsed.astimezone(timezone(timedelta(hours=2))).isoformat(timespec="microseconds"))
    value["evidence"]["assertions"].reverse()
    assert run(value) == result
    assert list(result) == ["contract", "rule_version", "identity_scope", "snapshot_id", "requested_evaluation_timestamp", "evidence",
        "source_authentication", "limitations", "authority"]
    assert result["contract"] == "trading.causal_instrument_specification_lifecycle_evidence_snapshot.v1"
    assert result["rule_version"] == "causal_instrument_specification_lifecycle_evidence_snapshot_v1"
    assert result["identity_scope"] == "snapshot_deterministic"
    assert result["source_authentication"] == "NOT_VERIFIED_BY_THIS_CAPABILITY"
    assert result["limitations"] == ["GOVERNING_SELECTION_NOT_PERFORMED", "APPLICABILITY_RESOLUTION_NOT_PERFORMED",
        "CROSS_SOURCE_PRECEDENCE_NOT_EVALUATED", "COVERAGE_CLAIMS_NOT_INDEPENDENTLY_VERIFIED",
        "SPECIFICATION_REFERENCES_NOT_VALIDATED", "FINANCIAL_MEASUREMENT_NOT_PERFORMED"]
    assert result["authority"] == dict(trade_decision=False, financial_risk=False, execution=False)
    assert result["snapshot_id"] == owner._hash_id("instrument_specification_lifecycle_evidence_snapshot_", {k: v for k, v in result.items() if k != "snapshot_id"})
    assert result["evidence"]["source"]["source_id"] != result["evidence"]["target_namespace"]["source_id"]
    assert [x["assertion_id"] for x in result["evidence"]["assertions"]] == ["a", "b", "c", "w"]


@pytest.mark.parametrize("path", OPAQUES)
def test_reference_and_namespace_identity(path):
    value = sample(); original = run(value); replace(value, path, at(value, path) + " ")
    assert run(value)["snapshot_id"] != original["snapshot_id"]
    with pytest.raises(ValueError): validate(original, value)


def test_identity_other_semantics():
    base = sample(); original = run(base)
    variants = []
    for path, new in [(("requested_evaluation_timestamp",), time(13)), (("evidence", "timing", "source_available_at"), None),
        (("evidence", "target_namespace", "environment"), "LIVE"), (("evidence", "assertions", 1, "assertion_id"), " b "),
        (("evidence", "assertions", 3, "statement", "target_assertion_id"), "b"),
        (("evidence", "assertions", 3, "statement", "replacement_statement"), None),
        (("evidence", "assertions", 0, "statement", "kind"), "WITHDRAWS"),
        (("evidence", "assertions", 0, "statement", "economic_scope", "effective_from"), time(8)),
        (("evidence", "assertions", 0, "statement", "economic_scope", "effective_until"), time(14)),
        (("evidence", "coverage", "source_information_cutoff"), time(10, 30)),
        (("evidence", "coverage", "timing", "observed_at"), time(11, 30)),
        (("evidence", "assertions", 1, "timing", "observed_at"), time(10, 30))]:
        value = deepcopy(base); replace(value, path, new); variants.append(value)
    value = sample(); value["evidence"]["coverage"]["completeness"] = "LIMITED"
    value["evidence"]["coverage"]["omissions"]["assertions_omitted"] = True; variants.append(value)
    for value in variants:
        assert run(value)["snapshot_id"] != original["snapshot_id"]
        with pytest.raises(ValueError): validate(original, value)


def test_full_serialized_reconstruction():
    value = sample(); result = run(value)
    assert validate(analyze(value), value) == result
    for path in paths(result):
        changed = deepcopy(result); replace(changed, path, "tampered")
        with pytest.raises(ValueError): validate(changed, value)
        changed = deepcopy(result); del at(changed, path[:-1])[path[-1]]
        with pytest.raises(ValueError): validate(changed, value)
    for path in [()] + [p for p in paths(result) if type(at(result, p)) is dict]:
        changed = deepcopy(result); at(changed, path)["extra"] = True
        with pytest.raises(ValueError): validate(changed, value)


@pytest.mark.parametrize("change", ["timestamp", "order", "limits", "authority", "bool_number", "nan", "infinity"])
def test_noncanonical_serialization(change):
    value = sample(); result = run(value)
    if change == "timestamp": result["requested_evaluation_timestamp"] = time(12)
    elif change == "order": result["evidence"]["assertions"].reverse()
    elif change == "limits": result["limitations"].reverse()
    elif change == "authority": result["authority"]["execution"] = True
    elif change == "bool_number": result["evidence"]["coverage"]["omissions"]["assertions_omitted"] = 0
    else: result["evidence"]["coverage"]["source_information_cutoff"] = float("nan" if change == "nan" else "inf")
    with pytest.raises(ValueError): validate(result, value)


def test_mutation_isolation():
    value = sample(); before = deepcopy(value); obj = analyze(value); result = obj.to_dict()
    validated = validate(obj, value)
    value["evidence"]["assertions"].clear()
    obj.payload["evidence"]["assertions"].clear()
    validated["evidence"]["coverage"]["omissions"]["assertions_omitted"] = True
    assert obj.to_dict() == result
    result["evidence"]["assertions"][0]["statement"]["revision"]["source_id"] = "mutated"
    assert obj.to_dict() == run(before)
    with pytest.raises(FrozenInstanceError): obj.snapshot_id = "changed"


def test_independent_library_only():
    tree = ast.parse(inspect.getsource(owner))
    modules = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert [name for name in modules if name and name.startswith("ced_one")] == ["ced_one.business_divisions.trading.causal_factual_intelligence_envelope"]
    calls = [ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(name.endswith((".now", ".utcnow", ".time", ".execute", ".dispatch")) for name in calls)


def test_dictionary_order_is_nonsemantic():
    def reverse_maps(value):
        if type(value) is dict:
            return {key: reverse_maps(child) for key, child in reversed(list(value.items()))}
        if type(value) is list:
            return [reverse_maps(child) for child in value]
        return value
    value = sample(); result = run(value)
    assert run(reverse_maps(value)) == result
    assert validate(reverse_maps(result), value) == result


def test_correction_order_equal_times_and_unknown_publications():
    value = sample(); value["evidence"]["assertions"] = [assertion(), correction(), correction("d", "c")]
    assert validate(run(value), value) == run(value)
    cov = value["evidence"]["coverage"]
    cov.update(completeness="UNKNOWN", source_information_cutoff=None, starting_basis="UNKNOWN",
               omissions=dict(assertions_omitted=None, history_truncated=None))
    for missing in (0, 1):
        changed = deepcopy(value)
        changed["evidence"]["assertions"][missing]["timing"]["source_available_at"] = None
        assert validate(run(changed), changed) == run(changed)


def test_deep_correction_chain_is_not_recursive():
    value = sample(); rows = [assertion()]
    for index in range(1100):
        rows.append(correction(f"c{index}", "a" if index == 0 else f"c{index - 1}"))
    value["evidence"]["assertions"] = rows
    assert len(run(value)["evidence"]["assertions"]) == 1101
