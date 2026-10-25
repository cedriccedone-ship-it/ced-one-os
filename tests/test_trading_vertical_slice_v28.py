"""Source-relative through-K resolution, strict binding and conservative conflicts."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from itertools import permutations
import ast
import inspect

import pytest

from ced_one.business_divisions.trading import causal_instrument_specification_applicability_resolver as owner
from ced_one.business_divisions.trading import causal_financial_instrument_contract_metadata_snapshot as metadata
from ced_one.business_divisions.trading import causal_instrument_specification_lifecycle_evidence_snapshot as lifecycle
from tests.test_trading_vertical_slice_v25 import sample as metadata_sample
from tests.test_trading_vertical_slice_v27 import sample as lifecycle_sample, assertion, correction, statement, revision, time, timing

UNIQUE = "UNIQUE_APPLICABLE_REVISION"
ABSENT = "NO_APPLICABLE_REVISION_ESTABLISHED"
UNKNOWN = "UNRESOLVED"


def edge(before="A", after="B"):
    result = statement("SUPERSEDES")
    result.update(predecessor_revision=revision(before), successor_revision=revision(after))
    return result


def sample(rows=None):
    source = lifecycle_sample()
    source["evidence"]["coverage"].update(timing=timing(12), source_information_cutoff=time(12))
    source["evidence"]["assertions"] = [assertion()] if rows is None else rows
    refs = {}
    for row in source["evidence"]["assertions"]:
        prop = row["statement"]
        if prop["kind"] == "CORRECTS": prop = prop["replacement_statement"]
        if prop is None: continue
        for field in ("revision", "predecessor_revision", "successor_revision"):
            if field in prop:
                ref = prop[field]
                refs[tuple(ref[k] for k in ("source_id", "source_contract", "source_contract_version", "source_snapshot_id"))] = ref
    entries = []
    for ref in refs.values():
        spec = metadata_sample()
        spec["specification"].update(source=deepcopy(ref), position_namespace=deepcopy(source["evidence"]["target_namespace"]))
        spec["specification"]["timing"]["effective_at"] = time(9)
        entries.append(dict(snapshot=None, snapshot_input=spec))
    value = dict(contract=owner.CONTRACT, rule_version=owner.RULE_VERSION,
                 requested_knowledge_boundary=time(12), economic_timestamp=time(10),
                 lifecycle_evidence=dict(snapshot=None, snapshot_input=source), specification_revisions=entries)
    return refresh(value)


def refresh(value, objects=False):
    entry = value["lifecycle_evidence"]
    result = lifecycle.CAUSAL_INSTRUMENT_SPECIFICATION_LIFECYCLE_EVIDENCE_SNAPSHOT.analyze(entry["snapshot_input"])
    entry["snapshot"] = result if objects else result.to_dict()
    for entry in value["specification_revisions"]:
        result = metadata.CAUSAL_FINANCIAL_INSTRUMENT_CONTRACT_METADATA_SNAPSHOT.analyze(entry["snapshot_input"])
        entry["snapshot"] = result if objects else result.to_dict()
    return value


def evidence(value):
    return value["lifecycle_evidence"]["snapshot_input"]["evidence"]


def spec(value, name="A"):
    return next(entry["snapshot_input"]["specification"] for entry in value["specification_revisions"]
                if entry["snapshot_input"]["specification"]["source"]["source_snapshot_id"] == name)


def run(value):
    return owner.CAUSAL_INSTRUMENT_SPECIFICATION_APPLICABILITY_RESOLVER.analyze(value).to_dict()


def validate(result, value):
    return owner.validate_causal_instrument_specification_applicability_resolver(result, value)


def check(value, outcome, reasons, selected=None):
    result = run(value)
    assert result["outcome"] == outcome
    assert result["reason_codes"] == reasons
    if selected is None:
        assert result["selected_revision"] is None
        assert result["selected_specification_snapshot_reference"] is None
    else:
        assert result["selected_revision"] == revision(selected)
        assert {"revision": result["selected_revision"], "snapshot_reference": result["selected_specification_snapshot_reference"]} in result["specification_revision_references"]
    assert validate(result, value) == result
    return result


def at(value, path):
    for key in path: value = value[key]
    return value


def paths(value, prefix=()):
    if type(value) is dict: items = value.items()
    elif type(value) is list: items = enumerate(value)
    else: return
    for key, child in items:
        yield prefix + (key,)
        yield from paths(child, prefix + (key,))


@pytest.mark.parametrize("path", [(), ("lifecycle_evidence",), ("specification_revisions", 0)])
def test_exact_resolver_objects(path):
    original = sample()
    for key in at(original, path):
        value = deepcopy(original); del at(value, path)[key]
        with pytest.raises(ValueError): run(value)
    value = deepcopy(original); at(value, path)["extra"] = True
    with pytest.raises(ValueError): run(value)
    for bad in (None, [], (), "object", True, 1):
        value = deepcopy(original)
        if path: at(value, path[:-1])[path[-1]] = bad
        else: value = bad
        with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("field", ["contract", "rule_version"])
@pytest.mark.parametrize("bad", [None, True, 1, [], {}, "", "unknown"])
def test_constants(field, bad):
    value = sample(); value[field] = bad
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("bad", [None, {}, (), "revisions", True, 1])
def test_collection_type(bad):
    value = sample(); value["specification_revisions"] = bad
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("field", ["economic_timestamp", "requested_knowledge_boundary"])
@pytest.mark.parametrize("bad", [None, True, 1, [], "2026-10-24", "2026-10-24T10:00Z", "2026-10-24T10:00:00",
    "2026-02-30T10:00:00Z", "2026-10-24T10:00:60Z", "2026-10-24T10:00:00.1234567Z",
    "2026-10-24T10:00:00+24:00", "2026-10-24T10:00:00+01:60", "0001-01-01T00:00:00+01:00"])
def test_timestamp_grammar(field, bad):
    value = sample(); value[field] = bad
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("location", ["lifecycle", "metadata"])
def test_every_owner_artifact_field_is_reconstructed(location):
    original = sample()
    basepath = ("lifecycle_evidence",) if location == "lifecycle" else ("specification_revisions", 0)
    artifact = at(original, basepath)["snapshot"]
    for path in paths(artifact):
        for remove in (False, True):
            value = deepcopy(original); target = at(value, basepath)["snapshot"]
            if remove: del at(target, path[:-1])[path[-1]]
            else: at(target, path[:-1])[path[-1]] = "tampered"
            with pytest.raises(ValueError): run(value)
    for path in [()] + [p for p in paths(artifact) if type(at(artifact, p)) is dict]:
        value = deepcopy(original); at(at(value, basepath)["snapshot"], path)["extra"] = True
        with pytest.raises(ValueError): run(value)
    value = deepcopy(original); at(value, basepath)["snapshot_input"]["requested_evaluation_timestamp"] = time(13)
    with pytest.raises(ValueError): run(value)


def test_object_wrappers_and_mutated_public_metadata_payload():
    value = refresh(sample(), objects=True)
    assert run(value) == run(sample())
    value["specification_revisions"][0]["snapshot"].payload["specification"]["economics"]["reference_unit"] = "changed"
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("prop", [statement(), statement("WITHDRAWS"), edge(),
                                  statement("APPLIES", "B"), statement("WITHDRAWS", "B"), edge("B", "C")])
@pytest.mark.parametrize("replacement", [False, True])
def test_every_reference_required_even_if_inactive_or_retracted(prop, replacement):
    prop = deepcopy(prop); prop["economic_scope"]["effective_from"] = time(15)
    rows = [assertion("a", prop)] if not replacement else [assertion(), correction(replacement=prop)]
    value = sample(rows)
    run(value)
    for index in range(len(value["specification_revisions"])):
        changed = deepcopy(value); changed["specification_revisions"].pop(index)
        with pytest.raises(ValueError): run(changed)
    retracted = sample([assertion(), correction()]); retracted["specification_revisions"] = []
    with pytest.raises(ValueError): run(retracted)


@pytest.mark.parametrize("variant", ["extra", "duplicate", "economics", "effective", "boundary", "namespace"])
def test_extra_and_duplicate_representations(variant):
    value = sample(); extra = deepcopy(value["specification_revisions"][0]); value["specification_revisions"].append(extra)
    owned = extra["snapshot_input"]["specification"]
    if variant == "extra": owned["source"]["source_snapshot_id"] = "unused"
    if variant == "economics": owned["economics"]["reference_units_per_quantity_unit"] = "999"
    if variant == "effective": owned["timing"]["effective_at"] = time(8)
    if variant == "boundary": extra["snapshot_input"]["requested_evaluation_timestamp"] = time(13)
    if variant == "namespace": owned["position_namespace"]["instrument_id"] = "other"
    refresh(value)
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("field", ["source_id", "source_contract", "source_contract_version", "environment", "instrument_id", "quantity_unit"])
def test_full_namespace_binding(field):
    value = sample(); ns = spec(value)["position_namespace"]
    ns[field] = "LIVE" if field == "environment" else ns[field] + " "
    refresh(value)
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("field", ["source_id", "source_contract", "source_contract_version", "source_snapshot_id"])
def test_full_revision_binding(field):
    value = sample(); spec(value)["source"][field] += " "
    refresh(value)
    with pytest.raises(ValueError): run(value)


def test_reporting_source_independence_and_no_snapshot_id_confusion():
    value = sample(); result = run(value)
    assert result["reporting_source"]["source_id"] != result["selected_revision"]["source_id"]
    assert result["selected_revision"]["source_snapshot_id"] != result["selected_specification_snapshot_reference"]["snapshot_id"]
    evidence(value)["source"]["source_id"] = "totally independent reporter"
    assert run(refresh(value))["outcome"] == UNIQUE


@pytest.mark.parametrize("boundary", [11, 12, 13])
def test_metadata_owner_boundaries(boundary):
    value = sample(); value["specification_revisions"][0]["snapshot_input"]["requested_evaluation_timestamp"] = time(boundary)
    assert run(refresh(value))["outcome"] == UNIQUE


@pytest.mark.parametrize("boundary", [11, 12, 13])
def test_lifecycle_owner_boundaries(boundary):
    value = sample(); source = value["lifecycle_evidence"]["snapshot_input"]
    source["requested_evaluation_timestamp"] = time(boundary)
    if boundary == 11:
        source["evidence"]["timing"] = timing(11)
        source["evidence"]["coverage"].update(timing=timing(11), source_information_cutoff=time(11))
    result = run(refresh(value))
    assert result["outcome"] == (UNKNOWN if boundary == 11 else UNIQUE)


@pytest.mark.parametrize("component", ["report", "coverage", "assertion", "metadata", "cutoff"])
def test_owner_valid_future_evidence_rejects_at_k(component):
    value = sample(); source = value["lifecycle_evidence"]["snapshot_input"]
    source["requested_evaluation_timestamp"] = time(14)
    evidence(value)["timing"] = timing(14)
    if component != "report": evidence(value)["timing"] = dict(observed_at=time(14), source_available_at=None)
    if component == "coverage": evidence(value)["coverage"]["timing"] = timing(13)
    if component == "assertion": evidence(value)["assertions"][0]["timing"]["observed_at"] = time(13)
    if component == "cutoff": evidence(value)["coverage"].update(timing=timing(13), source_information_cutoff=time(13))
    if component == "metadata":
        evidence(value)["timing"] = timing(12)
        value["specification_revisions"][0]["snapshot_input"]["requested_evaluation_timestamp"] = time(14)
        spec(value)["timing"]["observed_at"] = time(13)
    refresh(value)
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("status,reason", [("COMPLETE", "COVERAGE_CUTOFF_BEFORE_KNOWLEDGE_BOUNDARY"),
                                           ("LIMITED", "COVERAGE_LIMITED"), ("UNKNOWN", "COVERAGE_UNKNOWN")])
def test_coverage_gates_and_structural_errors_first(status, reason):
    value = sample([assertion(), correction(), correction("d", "c")])
    cov = evidence(value)["coverage"]; cov["completeness"] = status
    if status == "COMPLETE": cov["source_information_cutoff"] = time(11)
    elif status == "LIMITED": cov["omissions"]["history_truncated"] = True
    else:
        cov.update(starting_basis="UNKNOWN", source_information_cutoff=None,
                   omissions=dict(assertions_omitted=None, history_truncated=None))
        cov["timing"]["source_available_at"] = None
        for row in evidence(value)["assertions"]: row["timing"]["source_available_at"] = None
    refresh(value)
    check(value, UNKNOWN, [reason])
    value["specification_revisions"] = []
    with pytest.raises(ValueError): run(value)


def test_empty_complete_and_withdrawal_only():
    check(sample([]), ABSENT, ["NO_APPLICABLE_CANDIDATE_ESTABLISHED"])
    check(sample([assertion(proposition=statement("WITHDRAWS"))]), ABSENT, ["NO_APPLICABLE_CANDIDATE_ESTABLISHED"])


@pytest.mark.parametrize("replacement,expected,selected", [
    (None, ABSENT, None), (statement("APPLIES", "B"), UNIQUE, "B"),
    (edge(), UNIQUE, "B"), (statement("WITHDRAWS"), ABSENT, None)])
def test_simple_correction(replacement, expected, selected):
    value = sample([assertion(), correction(replacement=replacement)])
    reason = "UNIQUE_APPLICABLE_REVISION_ESTABLISHED" if selected else "NO_APPLICABLE_CANDIDATE_ESTABLISHED"
    check(value, expected, [reason], selected)


def test_replacement_outside_t_displaces_whole_original():
    replacement = statement("APPLIES", "B"); replacement["economic_scope"]["effective_from"] = time(13)
    check(sample([assertion(), correction(replacement=replacement)]), ABSENT, ["NO_APPLICABLE_CANDIDATE_ESTABLISHED"])


@pytest.mark.parametrize("rows,reasons", [
    ([assertion(), correction(), correction("d", "c")], ["CORRECTION_OF_CORRECTION"]),
    ([assertion(), correction(), correction("d")], ["MULTIPLE_CORRECTIONS_FOR_ASSERTION"]),
    ([assertion(), correction(replacement=statement()), correction("d", replacement=statement())], ["MULTIPLE_CORRECTIONS_FOR_ASSERTION"]),
    ([assertion(), correction(), correction("d", "c"), correction("e", "c")], ["CORRECTION_OF_CORRECTION", "MULTIPLE_CORRECTIONS_FOR_ASSERTION"]),
])
def test_correction_ambiguity(rows, reasons):
    for row in rows:
        if row["statement"]["kind"] != "CORRECTS": row["statement"]["economic_scope"]["effective_from"] = time(15)
    check(sample(rows), UNKNOWN, reasons)


def test_deep_correction_structure():
    rows = [assertion()]
    for index in range(1100): rows.append(correction(f"c{index}", "a" if index == 0 else f"c{index - 1}"))
    check(sample(rows), UNKNOWN, ["CORRECTION_OF_CORRECTION"])


@pytest.mark.parametrize("hour,expected", [(8, ABSENT), (9, UNIQUE), (10, UNIQUE), (11, ABSENT), (13, ABSENT)])
def test_half_open_scope(hour, expected):
    prop = statement(); prop["economic_scope"]["effective_until"] = time(11)
    value = sample([assertion(proposition=prop)]); value["economic_timestamp"] = time(hour)
    result = run(value); assert result["outcome"] == expected


def test_future_economics_and_open_end():
    prop = statement(); prop["economic_scope"]["effective_from"] = time(13)
    value = sample([assertion(proposition=prop)]); spec(value)["timing"]["effective_at"] = time(13)
    refresh(value)
    assert run(value)["outcome"] == ABSENT
    value["economic_timestamp"] = time(14)
    assert run(value)["outcome"] == UNIQUE
    assert value["specification_revisions"][0]["snapshot"]["effective_start_status"] == "FUTURE_EFFECTIVE"


@pytest.mark.parametrize("props,outcome,selected", [
    ([statement()], UNIQUE, "A"), ([edge()], UNIQUE, "B"),
    ([statement(), edge()], UNIQUE, "B"),
    ([edge(), edge("B", "C")], UNIQUE, "C"),
    ([edge(), edge("A", "C")], UNKNOWN, None),
    ([edge(), edge("A", "C"), edge("B", "C")], UNIQUE, "C"),
    ([edge(), statement("APPLIES", "C")], UNKNOWN, None),
    ([statement(), statement("APPLIES", "B")], UNKNOWN, None),
    ([edge(), edge()], UNIQUE, "B"),
    ([statement(), statement()], UNIQUE, "A"),
])
def test_lifecycle_graph(props, outcome, selected):
    value = sample([assertion(str(i), prop) for i, prop in enumerate(props)])
    reason = "MULTIPLE_APPLICABLE_CANDIDATES" if outcome == UNKNOWN else "UNIQUE_APPLICABLE_REVISION_ESTABLISHED"
    check(value, outcome, [reason], selected)


def test_bounded_supersession_and_inactive_cycle():
    forward = edge(); forward["economic_scope"]["effective_until"] = time(11)
    reverse = edge("B", "A"); reverse["economic_scope"]["effective_from"] = time(13)
    value = sample([assertion(), assertion("b", forward), assertion("c", reverse)])
    assert run(value)["selected_revision"] == revision("B")
    value["economic_timestamp"] = time(11)
    assert run(value)["selected_revision"] == revision("A")
    reverse["economic_scope"]["effective_from"] = time(9)
    check(sample([assertion("b", forward), assertion("c", reverse)]), UNKNOWN, ["ACTIVE_SUPERSESSION_CYCLE"])


@pytest.mark.parametrize("props", [
    [statement(), statement("WITHDRAWS")],
    [edge(), statement("WITHDRAWS", "B")],
    [statement(), edge(), statement("WITHDRAWS")],
    [edge(), edge("B", "C"), statement("WITHDRAWS", "B")],
])
def test_withdrawal_conflict_before_displacement_no_reinstatement(props):
    check(sample([assertion(str(i), prop) for i, prop in enumerate(props)]), UNKNOWN,
          ["POSITIVE_APPLICABILITY_WITHDRAWAL_CONFLICT"])


@pytest.mark.parametrize("kind", ["applies", "successor", "displaced", "replacement"])
def test_effective_start_conflict(kind):
    rows = {"applies": [assertion()], "successor": [assertion(proposition=edge())],
            "displaced": [assertion(), assertion("b", edge())],
            "replacement": [assertion(), correction(replacement=statement("APPLIES", "B"))]}[kind]
    value = sample(rows); name = "B" if kind in {"successor", "replacement"} else "A"
    spec(value, name)["timing"]["effective_at"] = time(11)
    check(refresh(value), UNKNOWN, ["SPECIFICATION_EFFECTIVE_START_CONFLICT"])
    spec(value, name)["timing"]["effective_at"] = time(10)
    assert run(refresh(value))["outcome"] == UNIQUE


def test_predecessor_only_and_withdrawn_only_future_start_not_positive():
    value = sample([assertion(proposition=edge())]); spec(value)["timing"]["effective_at"] = time(13)
    assert run(refresh(value))["outcome"] == UNIQUE
    value = sample([assertion(proposition=statement("WITHDRAWS"))]); spec(value)["timing"]["effective_at"] = time(13)
    assert run(refresh(value))["outcome"] == ABSENT


def test_all_conflict_reasons_and_stage_stopping():
    rows = [assertion(), assertion("b", edge()), assertion("c", edge("B", "A")), assertion("w", statement("WITHDRAWS"))]
    value = sample(rows); spec(value)["timing"]["effective_at"] = time(11)
    reasons = ["ACTIVE_SUPERSESSION_CYCLE", "POSITIVE_APPLICABILITY_WITHDRAWAL_CONFLICT", "SPECIFICATION_EFFECTIVE_START_CONFLICT"]
    check(refresh(value), UNKNOWN, reasons)
    evidence(value)["assertions"] += [correction("x"), correction("y")]
    check(refresh(value), UNKNOWN, ["MULTIPLE_CORRECTIONS_FOR_ASSERTION"])


@pytest.mark.parametrize("model,complete", [(metadata.MODEL, "PARTIAL"), (metadata.MODEL, "UNAVAILABLE"), ("other", "UNAVAILABLE"), (None, "UNAVAILABLE")])
def test_measurement_readiness_not_required(model, complete):
    value = sample(); owned = spec(value); owned.update(economic_model=model, completeness=complete)
    if complete == "PARTIAL": owned["economics"]["reference_unit"] = None
    else: owned["economics"] = {key: None for key in owned["economics"]}
    check(refresh(value), UNIQUE, ["UNIQUE_APPLICABLE_REVISION_ESTABLISHED"], "A")


def test_exact_output_and_hashes():
    value = sample(); result = run(value)
    assert list(result) == ["contract", "rule_version", "identity_scope", "resolution_id", "requested_knowledge_boundary",
        "economic_timestamp", "target_namespace", "reporting_source", "coverage", "lifecycle_evidence_reference",
        "specification_revision_references", "outcome", "selected_revision", "selected_specification_snapshot_reference",
        "reason_codes", "source_authentication", "limitations", "authority"]
    assert result["contract"] == "trading.causal_instrument_specification_applicability_resolver.v1"
    assert result["rule_version"] == "causal_instrument_specification_applicability_resolver_v1"
    assert result["identity_scope"] == "snapshot_deterministic"
    assert result["authority"] == dict(trade_decision=False, financial_risk=False, execution=False)
    assert result["source_authentication"] == "NOT_VERIFIED_BY_THIS_CAPABILITY"
    assert result["limitations"] == ["COVERAGE_CLAIMS_NOT_INDEPENDENTLY_VERIFIED", "GLOBAL_GOVERNING_SELECTION_NOT_PERFORMED",
        "CROSS_SOURCE_PRECEDENCE_NOT_EVALUATED", "FINANCIAL_MEASUREMENT_NOT_PERFORMED", "VALUATION_NOT_PERFORMED",
        "PRICE_SELECTION_NOT_PERFORMED", "PRICE_SUITABILITY_NOT_EVALUATED", "FRESHNESS_NOT_EVALUATED",
        "FINANCIAL_EXPOSURE_NOT_CALCULATED", "POSITION_SIZING_NOT_PERFORMED"]
    assert result["resolution_id"] == owner._hash_id("instrument_specification_applicability_resolution_", {k: v for k, v in result.items() if k != "resolution_id"})
    for ref, artifact in [(result["lifecycle_evidence_reference"], value["lifecycle_evidence"]["snapshot"]),
                          (result["selected_specification_snapshot_reference"], value["specification_revisions"][0]["snapshot"])]:
        assert set(ref) == {"contract", "rule_version", "snapshot_id", "content_fingerprint"}
        assert ref["content_fingerprint"] == owner._hash_id("validated_owner_content_", artifact)
    assert "economics" not in str(result)


def test_permutation_invariance_and_normalization():
    rows = [assertion(), assertion("b", edge()), assertion("c", edge("B", "C"))]
    original = sample(rows); expected = run(original)
    for order in permutations(rows):
        value = deepcopy(original); evidence(value)["assertions"] = list(order)
        for revisions in permutations(value["specification_revisions"]):
            changed = deepcopy(value); changed["specification_revisions"] = list(revisions)
            assert run(refresh(changed)) == expected
    value = deepcopy(original)
    # Normalize caller timestamps and owner reconstruction inputs, then regenerate artifacts.
    for path in list(paths(value)):
        raw = at(value, path)
        if type(raw) is str and raw.startswith("2026-"):
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            at(value, path[:-1])[path[-1]] = parsed.astimezone(timezone(timedelta(hours=2))).isoformat(timespec="microseconds")
    for entry in value["specification_revisions"]: entry["snapshot_input"]["specification"]["economics"]["reference_units_per_quantity_unit"] = "100.00000"
    assert run(refresh(value)) == expected
    def reversed_maps(obj):
        if type(obj) is dict: return {k: reversed_maps(v) for k, v in reversed(list(obj.items()))}
        if type(obj) is list: return [reversed_maps(v) for v in obj]
        return obj
    assert run(reversed_maps(original)) == expected
    assert validate(reversed_maps(expected), original) == expected


@pytest.mark.parametrize("change", ["T", "K", "coverage", "reporter", "assertion", "nonselected", "retracted", "owner_boundary"])
def test_identity_binds_all_consumed_content(change):
    value = sample([assertion(), assertion("b", edge()), assertion("c", statement("APPLIES", "C")), correction("d", "c")])
    original = run(value)
    if change == "T": value["economic_timestamp"] = time(11)
    elif change == "K": value["requested_knowledge_boundary"] = time(13)
    elif change == "coverage": evidence(value)["coverage"]["declaration_id"] += " "
    elif change == "reporter": evidence(value)["source"]["source_id"] += " "
    elif change == "assertion": evidence(value)["assertions"][0]["assertion_id"] = "other"
    elif change in {"nonselected", "retracted"}: spec(value, "A" if change == "nonselected" else "C")["economics"]["reference_units_per_quantity_unit"] = "999"
    else: value["specification_revisions"][0]["snapshot_input"]["requested_evaluation_timestamp"] = time(13)
    refresh(value)
    assert run(value)["resolution_id"] != original["resolution_id"]
    with pytest.raises(ValueError): validate(original, value)


def test_full_result_reconstruction_and_mutation_isolation():
    value = sample(); before = deepcopy(value)
    obj = owner.CAUSAL_INSTRUMENT_SPECIFICATION_APPLICABILITY_RESOLVER.analyze(value)
    result = obj.to_dict()
    assert validate(obj, value) == result
    for path in paths(result):
        for remove in (False, True):
            changed = deepcopy(result)
            if remove: del at(changed, path[:-1])[path[-1]]
            else: at(changed, path[:-1])[path[-1]] = "tampered"
            with pytest.raises(ValueError): validate(changed, value)
    for path in [()] + [p for p in paths(result) if type(at(result, p)) is dict]:
        changed = deepcopy(result); at(changed, path)["extra"] = True
        with pytest.raises(ValueError): validate(changed, value)
    value["specification_revisions"].clear()
    obj.payload["specification_revision_references"].clear()
    detached = validate(obj, before); detached["limitations"].clear()
    assert obj.to_dict() == result
    result["selected_revision"]["source_id"] = "changed"
    assert obj.to_dict() == run(before)
    with pytest.raises(FrozenInstanceError): obj.resolution_id = "changed"


@pytest.mark.parametrize("change", ["timestamp", "order", "limits", "bool", "nan", "infinity", "reasons"])
def test_noncanonical_output_rejected(change):
    value = sample([assertion(), assertion("b", edge())]); result = run(value)
    if change == "timestamp": result["economic_timestamp"] = time(10)
    elif change == "order": result["specification_revision_references"].reverse()
    elif change == "limits": result["limitations"].reverse()
    elif change == "bool": result["authority"]["execution"] = 0
    elif change == "reasons": result["reason_codes"].append(result["reason_codes"][0])
    else: result["coverage"]["source_information_cutoff"] = float("nan" if change == "nan" else "inf")
    with pytest.raises(ValueError): validate(result, value)


def test_independent_library_only():
    tree = ast.parse(inspect.getsource(owner))
    modules = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert [name for name in modules if name and name.startswith("ced_one")] == [
        "ced_one.business_divisions.trading", "ced_one.business_divisions.trading",
        "ced_one.business_divisions.trading.causal_factual_intelligence_envelope"]
    imports = [alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names]
    assert "causal_financial_instrument_contract_metadata_snapshot" in imports
    assert "causal_instrument_specification_lifecycle_evidence_snapshot" in imports
    assert not any("price_observation" in name or "account_state" in name for name in imports)
    calls = [ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(name.endswith((".now", ".utcnow", ".time", ".execute", ".dispatch")) for name in calls)
