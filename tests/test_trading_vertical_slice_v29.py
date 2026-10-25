"""Account rule ownership, causal applicability and non-authoritative boundaries."""
from copy import deepcopy
import json

import pytest

from ced_one.business_divisions.trading import causal_account_rule_regime_assessment as owner

UNIQUE = "UNIQUE_APPLICABLE_APPROVED_REGIME"
ABSENT = "NO_APPLICABLE_APPROVED_REGIME_ESTABLISHED"


def time(day):
    return f"2026-01-{day:02d}T00:00:00Z"


def period(start=1, end=30):
    return dict(effective_from=time(start), effective_until=time(end), end_status="KNOWN")


def reference(identifier):
    return dict(source_id="source", source_contract="contract", source_contract_version="1", source_snapshot_id=identifier)


def refs():
    return [dict(evidence_id="terms", clause_locator="section 1")]


def measure():
    return dict(kind="EQUITY", currency="USD", definition_refs=refs(), cost_treatment=dict(commissions="IN_MEASURE", financing="SUBTRACT_SEPARATELY", other_charges="NOT_APPLICABLE"))


def rule(kind="ACCOUNT_STATE_REQUIREMENT"):
    bodies = {
        "ACCOUNT_STATE_REQUIREMENT": dict(required_facts=["ACCOUNT_ACTIVE", "NO_PRIOR_DISQUALIFYING_BREACH"]),
        "INSTRUMENT_ACTION_PERMISSION": dict(actions=["ENTRY_LONG", "HOLD"], permission="PERMITTED"),
        "POSITION_LIMIT": dict(limit_kind="CONCURRENT_POSITION_COUNT", maximum=1),
        "STATIC_FLOOR": dict(measure=measure(), threshold=dict(kind="INITIAL_REFERENCE_FRACTION", reference="INITIAL_BALANCE", fraction="0.900"), compliant_when="GREATER_THAN"),
        "DAILY_RESET_FLOOR": dict(measure=measure(), reset_anchor="BALANCE", deduction=dict(kind="INITIAL_REFERENCE_FRACTION", reference="INITIAL_BALANCE", fraction="0.050"), compliant_when="GREATER_THAN_OR_EQUAL", reset_schedule=dict(source_timezone="Europe/Amsterdam", source_local_reset_time="00:00:00", schedule_period=period(1, 4), boundaries=[time(i) for i in range(1, 5)], evidence_refs=refs()), adjustment_policy="NO_UNREPRESENTED_CAPITAL_OR_PHASE_ADJUSTMENTS"),
        "ACTION_WINDOW": dict(actions=["ENTRY_LONG", "HOLD"], mode="PERMITTED_ONLY_WITHIN", source_timezone="UTC", schedule_period=period(), intervals=[period(1, 10), period(12, 20)], evidence_refs=refs()),
        "AUTOMATION_PERMISSION": dict(operation_mode="AUTOMATED", permission="PERMITTED"),
        "UNSUPPORTED": dict(source_rule_label="trailing floor", unsupported_reason="SEMANTICS_NOT_SUPPORTED", description="Trailing watermark formula."),
    }
    return dict(rule_id=kind, representation="UNSUPPORTED" if kind == "UNSUPPORTED" else "SUPPORTED", effects=["ENTRY"], instrument_scope=dict(kind="ALL_ACCOUNT_INSTRUMENTS"), evidence_refs=refs(), body=dict(type=kind, **bodies[kind]))


def sample():
    account = dict(source_id="broker", source_contract="accounts", source_contract_version="1", account_id="exact-account", environment="DEMO")
    package = dict(package_id="rules", package_revision="z", provider_id="provider", program_id="program", account_type_id="type", phase_id="phase", effective_period=period(), evidence_refs=refs(), interpretation=dict(interpretation_id="interpretation", interpretation_version="1", interpreted_at=time(3), interpreter_ref="review-process", limitations=[]), coverage=dict(completeness="COMPLETE", scope="ACCOUNT_TRADING_AND_ELIGIBILITY", evidence_refs=refs(), limitations=[]), rules=[rule()])
    assignment = dict(assignment_id="assignment", account=deepcopy(account), provider_id="provider", program_id="program", account_type_id="type", phase_id="phase", agreement=dict(status="IDENTIFIED", agreement_id="agreement"), enrollment_period=period(), phase_period=period(), package_bindings=[dict(package=dict(package_id="rules", package_revision="z"), effective_period=period(), evidence_refs=refs())], evidence_refs=refs())
    evidence = dict(evidence_id="terms", source=reference("document"), acquisition="MANUAL_TRANSCRIPTION", document_reference="archive:official-terms", document_revision=None, document_date=None, document_sha256=None, timing=dict(observed_at=time(2), source_available_at=None), captured_by="capture-process", limitations=[])
    value = dict(contract=owner.CONTRACT, rule_version=owner.RULE_VERSION, requested_knowledge_boundary=time(10), economic_timestamp=time(10), account=account, manifest=dict(source=reference("manifest"), timing=dict(observed_at=time(10), source_available_at=None), coverage=dict(completeness="COMPLETE", economic_period=period(), source_information_cutoff=time(10), limitations=[]), evidence=[evidence], assignments=[assignment], packages=[package]), approvals=[])
    value["approvals"] = [dict(approval_reference=reference("approval"), authority_role="mission_control", policy_id="policy", policy_version=1, context_fingerprint="external-context", assignment_id="assignment", assignment_content_fingerprint="pending", package=dict(package_id="rules", package_revision="z"), package_content_fingerprint="pending", decision="APPROVED", decided_at=time(4), observed_at=time(4), effective_period=period())]
    return refresh(value)


def refresh(value):
    temporary = deepcopy(value)
    temporary["approvals"] = []
    normalized = owner._normalize_input(temporary)
    for approval in value["approvals"]:
        assignment = next(a for a in normalized["manifest"]["assignments"] if a["assignment_id"] == approval["assignment_id"])
        package = next(p for p in normalized["manifest"]["packages"] if (p["package_id"], p["package_revision"]) == (approval["package"]["package_id"], approval["package"]["package_revision"]))
        approval["assignment_content_fingerprint"] = owner._hash_id("account_rule_assignment_", assignment)
        approval["package_content_fingerprint"] = owner._hash_id("account_rule_package_", package)
    return value


def run(value):
    return owner.CAUSAL_ACCOUNT_RULE_REGIME_ASSESSMENT.analyze(value).to_dict()


def package(value):
    return value["manifest"]["packages"][0]


def assignment(value):
    return value["manifest"]["assignments"][0]


def add_package(value, start=1, end=30):
    second = deepcopy(package(value))
    second.update(package_revision="a", effective_period=period(start, end))
    value["manifest"]["packages"].append(second)
    assignment(value)["package_bindings"].append(dict(package=dict(package_id="rules", package_revision="a"), effective_period=period(start, end), evidence_refs=refs()))
    return second


def test_unique_and_boundaries():
    value = sample()
    result = run(value)
    assert result["outcome"] == UNIQUE
    assert result["interpretation_support"] == "ALL_DECLARED_RULES_SUPPORTED"
    assert result["authority"] == dict(trade_decision=False, financial_risk=False, execution=False)
    assert result["limitations"] == list(owner.LIMITATIONS)
    assert result["source_authentication"] == "NOT_VERIFIED_BY_THIS_CAPABILITY"
    assert owner.validate_causal_account_rule_regime_assessment(result, value) == result
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    assert set(result) == set("contract rule_version identity_scope assessment_id requested_knowledge_boundary economic_timestamp account manifest_reference manifest_content_fingerprint manifest_coverage outcome selected_regime interpretation_support reason_codes source_authentication limitations authority".split())


@pytest.mark.parametrize("field", ["source_id", "source_contract", "source_contract_version", "account_id", "environment"])
def test_exact_account(field):
    value = sample()
    value["account"][field] = "LIVE" if field == "environment" else "other"
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("field", owner.SCOPE_FIELDS)
def test_scope_mismatch(field):
    value = sample()
    package(value)[field] = "other"
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("field", owner.SCOPE_FIELDS)
def test_unknown_scope(field):
    value = sample()
    assignment(value)[field] = None
    result = run(refresh(value))
    assert result["outcome"] == "UNRESOLVED"
    assert "ACCOUNT_ASSIGNMENT_IDENTITY_UNKNOWN" in result["reason_codes"]


def test_empty_manifest_and_no_binding():
    value = sample()
    value["manifest"].update(assignments=[], packages=[], evidence=[])
    value["approvals"] = []
    assert run(value)["outcome"] == ABSENT
    value = sample()
    assignment(value)["package_bindings"] = []
    value["manifest"]["packages"] = []
    value["approvals"] = []
    assert run(value)["reason_codes"] == ["NO_APPLICABLE_PACKAGE"]


def test_unapproved_competitor_and_revision_order():
    value = sample()
    add_package(value)
    result = run(refresh(value))
    assert result["outcome"] == "UNRESOLVED"
    assert result["reason_codes"] == ["MULTIPLE_APPLICABLE_PACKAGES"]
    value["manifest"]["packages"].reverse()
    assignment(value)["package_bindings"].reverse()
    assert run(value) == result


@pytest.mark.parametrize("day,revision", [(9, "z"), (10, "a"), (11, "a")])
def test_historical_explicit_replacement(day, revision):
    value = sample()
    package(value)["effective_period"] = period(1, 10)
    assignment(value)["package_bindings"][0]["effective_period"] = period(1, 10)
    add_package(value, 10)
    approval = deepcopy(value["approvals"][0])
    approval["approval_reference"] = reference("approval2")
    approval["package"]["package_revision"] = "a"
    value["approvals"].append(approval)
    value["economic_timestamp"] = time(day)
    result = run(refresh(value))
    assert result["outcome"] == UNIQUE
    assert result["selected_regime"]["package"]["package_revision"] == revision


def test_future_known_change_not_yet_effective():
    value = sample()
    add_package(value, 20)
    assert run(refresh(value))["outcome"] == UNIQUE


@pytest.mark.parametrize("day,phase", [(9, "phase"), (10, "phase2")])
def test_phase_transition(day, phase):
    value = sample()
    second_package = add_package(value, 10)
    second_package["phase_id"] = "phase2"
    second_assignment = deepcopy(assignment(value))
    second_assignment.update(assignment_id="assignment2", phase_id="phase2", phase_period=period(10))
    second_assignment["package_bindings"] = [assignment(value)["package_bindings"].pop()]
    assignment(value)["phase_period"] = period(1, 10)
    value["manifest"]["assignments"].append(second_assignment)
    approval = deepcopy(value["approvals"][0])
    approval.update(approval_reference=reference("approval2"), assignment_id="assignment2", package=dict(package_id="rules", package_revision="a"))
    value["approvals"].append(approval)
    value["economic_timestamp"] = time(day)
    result = run(refresh(value))
    assert result["selected_regime"]["assignment"]["phase_id"] == phase


@pytest.mark.parametrize("target", ["manifest", "evidence", "interpretation", "approval", "publication"])
def test_no_lookahead(target):
    value = sample()
    if target == "manifest": value["manifest"]["timing"]["observed_at"] = time(11)
    if target == "evidence": value["manifest"]["evidence"][0]["timing"]["observed_at"] = time(11)
    if target == "interpretation": package(value)["interpretation"]["interpreted_at"] = time(11)
    if target == "approval": value["approvals"][0]["observed_at"] = time(11)
    if target == "publication": value["manifest"]["evidence"][0]["timing"]["source_available_at"] = time(11)
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("case,reason", [("missing", "APPROVAL_NOT_ESTABLISHED"), ("rejected", "APPROVAL_REJECTED"), ("expired", "APPROVAL_NOT_EFFECTIVE_AT_T"), ("future", "APPROVAL_NOT_EFFECTIVE_AT_T"), ("conflict", "APPROVAL_CONFLICT")])
def test_approval_outcomes(case, reason):
    value = sample()
    if case == "missing": value["approvals"] = []
    if case == "rejected": value["approvals"][0]["decision"] = "REJECTED"
    if case == "expired": value["approvals"][0]["effective_period"] = period(1, 10)
    if case == "future": value["approvals"][0]["effective_period"] = period(11)
    if case == "conflict":
        second = deepcopy(value["approvals"][0])
        second.update(approval_reference=reference("second"), decision="REJECTED")
        value["approvals"].append(second)
    result = run(value)
    assert result["reason_codes"] == [reason]
    assert result["outcome"] == ("UNRESOLVED" if case == "conflict" else ABSENT)


@pytest.mark.parametrize("field", ["assignment_content_fingerprint", "package_content_fingerprint"])
def test_approval_content_binding(field):
    value = sample()
    value["approvals"][0][field] = "tampered"
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("completeness", ["COMPLETE", "LIMITED", "UNKNOWN"])
def test_manifest_coverage(completeness):
    value = sample()
    value["manifest"]["coverage"]["completeness"] = completeness
    if completeness == "UNKNOWN": value["manifest"]["coverage"]["source_information_cutoff"] = None
    result = run(value)
    assert result["outcome"] == (UNIQUE if completeness == "COMPLETE" else "UNRESOLVED")


@pytest.mark.parametrize("completeness", ["COMPLETE", "LIMITED", "UNKNOWN"])
@pytest.mark.parametrize("unsupported", [False, True])
def test_rule_coverage_support_and_scoped_absence(completeness, unsupported):
    value = sample()
    package(value)["coverage"]["completeness"] = completeness
    package(value)["rules"] = [rule("UNSUPPORTED")] if unsupported else []
    result = run(refresh(value))
    assert result["outcome"] == UNIQUE
    assert result["selected_regime"]["package"]["coverage"]["completeness"] == completeness
    assert result["interpretation_support"] == ("UNSUPPORTED_RULES_PRESENT" if unsupported else "ALL_DECLARED_RULES_SUPPORTED")
    assert len(result["selected_regime"]["package"]["rules"]) == int(unsupported)
    assert ("RULE_COVERAGE_" + completeness in result["reason_codes"]) == (completeness != "COMPLETE")


@pytest.mark.parametrize("kind", ["ACCOUNT_STATE_REQUIREMENT", "INSTRUMENT_ACTION_PERMISSION", "POSITION_LIMIT", "STATIC_FLOOR", "DAILY_RESET_FLOOR", "ACTION_WINDOW", "AUTOMATION_PERMISSION", "UNSUPPORTED"])
def test_typed_rules_preserved(kind):
    value = sample()
    package(value)["rules"] = [rule(kind)]
    result = run(refresh(value))
    body = result["selected_regime"]["package"]["rules"][0]["body"]
    assert body["type"] == kind
    if kind == "STATIC_FLOOR":
        assert body["threshold"]["fraction"] == "0.9"
        assert body["compliant_when"] == "GREATER_THAN"
    if kind == "DAILY_RESET_FLOOR":
        assert body["deduction"]["fraction"] == "0.05"
        assert body["reset_anchor"] == "BALANCE"
        assert body["compliant_when"] == "GREATER_THAN_OR_EQUAL"
    assert result["outcome"] == UNIQUE  # Does not evaluate expired rule calendar or financial state.


def test_quantity_and_decimal_exactness():
    value = sample()
    row = rule("POSITION_LIMIT")
    row["instrument_scope"] = dict(kind="EXACT_INSTRUMENTS", instruments=[dict(source_id="broker", source_contract="instruments", source_contract_version="1", environment="DEMO", instrument_id="XAUUSD")])
    row["body"] = dict(type="POSITION_LIMIT", limit_kind="PER_POSITION_QUANTITY", quantity_unit="lot", maximum="0.10000000000000000000000000000100")
    package(value)["rules"] = [row]
    result = run(refresh(value))
    assert result["selected_regime"]["package"]["rules"][0]["body"]["maximum"] == "0.100000000000000000000000000001"
    row["instrument_scope"] = dict(kind="ALL_ACCOUNT_INSTRUMENTS")
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "1e-2", 0.9, True, "1.1", "-0.1"])
def test_invalid_fraction(bad):
    value = sample()
    row = rule("STATIC_FLOOR")
    row["body"]["threshold"]["fraction"] = bad
    package(value)["rules"] = [row]
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("kind", ["ACTION_WINDOW", "DAILY_RESET_FLOOR"])
def test_invalid_calendars(kind):
    value = sample()
    row = rule(kind)
    package(value)["rules"] = [row]
    if kind == "ACTION_WINDOW": row["body"]["intervals"].append(period(5, 15))
    else: row["body"]["reset_schedule"]["boundaries"].pop()
    with pytest.raises(ValueError): run(value)


def test_ordering_normalization_and_no_clock():
    value = sample()
    package(value)["rules"] = [rule("STATIC_FLOOR"), rule("ACTION_WINDOW"), rule("ACCOUNT_STATE_REQUIREMENT")]
    result = run(refresh(value))
    package(value)["rules"].reverse()
    value["economic_timestamp"] = "2026-01-10T01:00:00+01:00"
    assert run(value) == result
    assert run(value) == result


@pytest.mark.parametrize("bad", ["2026-01-10", "2026-02-30T00:00:00Z", "2026-01-10T00:00:00", "2026-01-10T00:00:60Z", "2026-01-10T00:00:00+25:00", None, 123])
def test_bad_timestamps(bad):
    value = sample()
    value["economic_timestamp"] = bad
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("collection", ["packages", "assignments", "evidence", "approvals", "rules", "bindings"])
def test_duplicate_rejection(collection):
    value = sample()
    rows = value["approvals"] if collection == "approvals" else package(value)["rules"] if collection == "rules" else assignment(value)["package_bindings"] if collection == "bindings" else value["manifest"][collection]
    rows.append(deepcopy(rows[0]))
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize("case", ["package", "evidence", "extra_evidence", "extra_package", "approval"])
def test_dangling_and_unrelated(case):
    value = sample()
    if case == "package": assignment(value)["package_bindings"][0]["package"]["package_revision"] = "missing"
    if case == "evidence": package(value)["evidence_refs"][0]["evidence_id"] = "missing"
    if case == "extra_evidence":
        second = deepcopy(value["manifest"]["evidence"][0]); second["evidence_id"] = "extra"
        value["manifest"]["evidence"].append(second)
    if case == "extra_package":
        second = deepcopy(package(value)); second["package_revision"] = "extra"
        value["manifest"]["packages"].append(second)
    if case == "approval": value["approvals"][0]["assignment_id"] = "missing"
    with pytest.raises(ValueError): run(value)


def paths(value, prefix=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from paths(item, prefix + (key,))
    elif isinstance(value, list):
        for key, item in enumerate(value):
            yield from paths(item, prefix + (key,))
    else:
        yield prefix


@pytest.mark.parametrize("path", list(paths(run(sample()))))
def test_every_output_leaf_is_reconstructed(path):
    value = sample()
    result = run(value)
    target = result
    for part in path[:-1]: target = target[part]
    target[path[-1]] = "tampered"
    with pytest.raises(ValueError): owner.validate_causal_account_rule_regime_assessment(result, value)


@pytest.mark.parametrize("path", [p for p in paths(sample()) if isinstance(p[-1], str)])
def test_exact_nested_schema_rejects_extra_fields(path):
    value = sample()
    target = value
    for part in path[:-1]: target = target[part]
    target["unexpected"] = None
    with pytest.raises(ValueError): run(value)


def test_mutation_isolation_and_reconstruction_detachment():
    value = sample()
    original = deepcopy(value)
    artifact = owner.CAUSAL_ACCOUNT_RULE_REGIME_ASSESSMENT.analyze(value)
    expected = artifact.to_dict()
    package(value)["rules"].clear()
    artifact.payload["account"]["account_id"] = "changed"
    artifact.to_dict()["selected_regime"]["package"]["rules"].clear()
    validated = owner.validate_causal_account_rule_regime_assessment(artifact, original)
    validated["selected_regime"]["package"]["rules"].clear()
    assert artifact.to_dict() == expected
    with pytest.raises(ValueError): owner.validate_causal_account_rule_regime_assessment(artifact, value)


def test_unknown_period_and_stale_coverage():
    value = sample()
    assignment(value)["phase_period"].update(effective_from=None)
    assert run(refresh(value))["reason_codes"] == ["APPLICABILITY_TIMING_UNKNOWN"]
    value = sample()
    value["manifest"]["coverage"]["source_information_cutoff"] = time(9)
    assert run(value)["reason_codes"] == ["MANIFEST_CUTOFF_BEFORE_K"]


def test_agreement_unknown_vs_evidenced_not_applicable():
    value = sample()
    assignment(value)["agreement"] = dict(status="UNKNOWN", agreement_id=None)
    assert run(refresh(value))["outcome"] == "UNRESOLVED"
    assignment(value)["agreement"]["status"] = "NOT_APPLICABLE"
    assert run(refresh(value))["outcome"] == UNIQUE


def test_no_materiality_override():
    value = sample()
    package(value)["rules"] = [rule("UNSUPPORTED")]
    package(value)["rules"][0]["material"] = False
    with pytest.raises(ValueError): run(value)


def test_open_ended_period_and_approval_union():
    value = sample()
    first = value["approvals"][0]
    first["effective_period"] = period(1, 12)
    second = deepcopy(first)
    second.update(approval_reference=reference("second"), effective_period=period(12, 25))
    value["approvals"].append(second)
    result = run(value)
    assert result["selected_regime"]["applicable_period"]["effective_until"] == owner._timestamp(time(25))
    assert len(result["selected_regime"]["approval_references"]) == 2


def test_no_source_authentication_or_financial_calculations():
    value = sample()
    package(value)["rules"] = [rule("STATIC_FLOOR"), rule("DAILY_RESET_FLOOR"), rule("UNSUPPORTED")]
    result = run(refresh(value))
    forbidden = {"candidate_compliance", "headroom", "pnl", "margin", "trade_decision_result", "authorization", "BUY", "SELL", "NO_TRADE"}
    assert not forbidden.intersection(part for path in paths(result) for part in path if isinstance(part, str))
    assert result["outcome"] == UNIQUE
    assert result["interpretation_support"] == "UNSUPPORTED_RULES_PRESENT"


def test_same_package_overlapping_bindings_are_not_competing_packages():
    value = sample()
    binding = deepcopy(assignment(value)["package_bindings"][0])
    binding["effective_period"] = period(5, 20)
    assignment(value)["package_bindings"].append(binding)
    assert run(refresh(value))["outcome"] == UNIQUE


def test_competing_account_assignments():
    value = sample()
    second = deepcopy(assignment(value))
    second["assignment_id"] = "second"
    value["manifest"]["assignments"].append(second)
    assert run(refresh(value))["reason_codes"] == ["MULTIPLE_ACCOUNT_ASSIGNMENTS"]


@pytest.mark.parametrize("field", ["effective_from", "end_status"])
def test_unknown_binding_period_does_not_disappear(field):
    value = sample()
    binding = assignment(value)["package_bindings"][0]
    if field == "effective_from": binding["effective_period"][field] = None
    else: binding["effective_period"].update(end_status="UNKNOWN", effective_until=None)
    assert run(refresh(value))["reason_codes"] == ["APPLICABILITY_TIMING_UNKNOWN"]


def test_explicit_open_ended_validity():
    value = sample()
    for p in (assignment(value)["enrollment_period"], assignment(value)["phase_period"], assignment(value)["package_bindings"][0]["effective_period"], package(value)["effective_period"], value["approvals"][0]["effective_period"]):
        p.update(end_status="OPEN_ENDED", effective_until=None)
    result = run(refresh(value))
    assert result["outcome"] == UNIQUE
    assert result["selected_regime"]["applicable_period"]["end_status"] == "OPEN_ENDED"


@pytest.mark.parametrize("kind", ["STATIC_FLOOR", "DAILY_RESET_FLOOR"])
@pytest.mark.parametrize("comparison", ["GREATER_THAN", "GREATER_THAN_OR_EQUAL"])
def test_absolute_floor_and_comparator_are_preserved_without_calculation(kind, comparison):
    value = sample()
    row = rule(kind)
    field = "threshold" if kind == "STATIC_FLOOR" else "deduction"
    row["body"][field] = dict(kind="ABSOLUTE", amount="1000.000")
    row["body"]["compliant_when"] = comparison
    package(value)["rules"] = [row]
    body = run(refresh(value))["selected_regime"]["package"]["rules"][0]["body"]
    assert body[field]["amount"] == "1000"
    assert body["compliant_when"] == comparison
    assert "calculated_threshold" not in body


@pytest.mark.parametrize("mode", ["PERMITTED_ONLY_WITHIN", "PROHIBITED_WITHIN"])
def test_empty_window_preserves_mode(mode):
    value = sample()
    row = rule("ACTION_WINDOW")
    row["body"].update(mode=mode, intervals=[])
    package(value)["rules"] = [row]
    body = run(refresh(value))["selected_regime"]["package"]["rules"][0]["body"]
    assert body["intervals"] == []
    assert body["mode"] == mode


@pytest.mark.parametrize("case", ["cutoff_future", "complete_omission", "rule_complete_omission", "interpretation_before_source", "approval_before_interpretation", "duplicate_reset", "bad_local_time", "unknown_cost", "mixed_unknown_effects", "count_bool", "policy_bool", "bad_document_date", "bad_hash"])
def test_additional_invalid_contract_cases(case):
    value = sample()
    if case == "cutoff_future": value["manifest"]["coverage"]["source_information_cutoff"] = time(11)
    if case == "complete_omission": value["manifest"]["coverage"]["limitations"] = ["missing enrollment"]
    if case == "rule_complete_omission": package(value)["coverage"]["limitations"] = ["missing clauses"]
    if case == "interpretation_before_source": package(value)["interpretation"]["interpreted_at"] = time(1)
    if case == "approval_before_interpretation": value["approvals"][0]["decided_at"] = time(2)
    if case in ("duplicate_reset", "bad_local_time"):
        row = rule("DAILY_RESET_FLOOR"); package(value)["rules"] = [row]
        if case == "duplicate_reset": row["body"]["reset_schedule"]["boundaries"].append(time(2))
        else: row["body"]["reset_schedule"]["source_local_reset_time"] = "24:00:00"
    if case == "unknown_cost":
        row = rule("STATIC_FLOOR"); package(value)["rules"] = [row]
        row["body"]["measure"]["cost_treatment"]["financing"] = "UNKNOWN"
    if case == "mixed_unknown_effects": package(value)["rules"][0]["effects"] = ["ENTRY", "UNKNOWN"]
    if case == "count_bool":
        row = rule("POSITION_LIMIT"); package(value)["rules"] = [row]; row["body"]["maximum"] = True
    if case == "policy_bool": value["approvals"][0]["policy_version"] = True
    if case == "bad_document_date": value["manifest"]["evidence"][0]["document_date"] = "2026-02-30"
    if case == "bad_hash": value["manifest"]["evidence"][0]["document_sha256"] = "not-a-hash"
    with pytest.raises(ValueError): run(value)


def test_source_and_content_changes_change_identity():
    value = sample()
    original = run(value)
    value["manifest"]["source"]["source_snapshot_id"] = "corrected-manifest"
    assert run(value)["assessment_id"] != original["assessment_id"]
    value = sample()
    package(value)["rules"] = [rule("UNSUPPORTED")]
    changed = run(refresh(value))
    assert changed["assessment_id"] != original["assessment_id"]
    assert changed["selected_regime"]["regime_id"] != original["selected_regime"]["regime_id"]


def test_timestamp_and_decimal_normalization_preserve_identity():
    value = sample()
    package(value)["rules"] = [rule("STATIC_FLOOR")]
    original = run(refresh(value))
    package(value)["rules"][0]["body"]["threshold"]["fraction"] = "0.900000"
    package(value)["effective_period"]["effective_from"] = "2026-01-01T01:00:00+01:00"
    assert run(value) == original


def test_assessment_boundary_outside_manifest():
    value = sample()
    value["economic_timestamp"] = time(30)
    assert run(value)["reason_codes"] == ["T_OUTSIDE_MANIFEST_COVERAGE"]


def test_unknown_publication_and_known_document_metadata():
    value = sample()
    evidence = value["manifest"]["evidence"][0]
    evidence.update(document_revision="official-v1", document_date="2026-01-01", document_sha256="a" * 64)
    result = run(value)
    assert result["outcome"] == UNIQUE
    assert result["selected_regime"]["evidence"][0]["timing"]["source_available_at"] is None
