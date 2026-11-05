"""C8 synthetic originals/admissions; successful native results are never mocked."""
import base64
import ast
from copy import deepcopy
from decimal import localcontext
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import pytest

from ced_one.business_divisions.trading import current_intraday_trailing_loss_threshold_state as c8
from ced_one.business_divisions.trading import causal_account_rule_regime_assessment as regime
from ced_one.business_divisions.trading import causal_financial_account_state_snapshot as account


def time(day, hour=0):
    return f"2026-01-{day:02d}T{hour:02d}:00:00.000000Z"


T, R, K, INCEPTION = time(10), time(11), time(12), time(5)
NS = dict(source_id="synthetic", source_contract="ledger", source_contract_version="1")
ACCOUNT_NS = dict(source_id="broker", source_contract="accounts", source_contract_version="1")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def encoded(value):
    return base64.b64encode(canonical(value).encode()).decode()


def decoded(value):
    return json.loads(base64.b64decode(value))


def source(identifier="batch"):
    return dict(**NS, source_snapshot_id=identifier)


def period(start=1, end=30):
    return dict(effective_from=time(start), effective_until=None if end is None else time(end),
                end_status="OPEN_ENDED" if end is None else "KNOWN")


def citations():
    return [dict(evidence_id="report", locator="complete synthetic account history"),
            dict(evidence_id="terms", locator="synthetic rule and identity")]


def bundle(payload, native_owner):
    artifact = native_owner.analyze(payload).to_dict()
    return dict(input_json=encoded(payload), result_json=encoded(artifact))


def replay_regime(payload):
    """Prepare synthetic approval IDs as existing native fixtures do; replay is public.

    Private normalization is used only to issue the test's input fingerprints,
    never as a replacement for successful public analysis or validation.
    """
    temporary = deepcopy(payload)
    temporary["approvals"] = []
    normalized = regime._normalize_input(temporary)
    assignments = {a["assignment_id"]: a for a in normalized["manifest"]["assignments"]}
    packages = {(p["package_id"], p["package_revision"]): p for p in normalized["manifest"]["packages"]}
    for approval in payload["approvals"]:
        approval["assignment_content_fingerprint"] = "account_rule_assignment_" + digest(assignments[approval["assignment_id"]])[:24]
        key = (approval["package"]["package_id"], approval["package"]["package_revision"])
        approval["package_content_fingerprint"] = "account_rule_package_" + digest(packages[key])[:24]
    return bundle(payload, regime.CAUSAL_ACCOUNT_RULE_REGIME_ASSESSMENT)


def native_regime():
    refs = [dict(evidence_id="terms", clause_locator="synthetic rule")]
    native_account = dict(**ACCOUNT_NS, account_id="account", environment="DEMO")
    rule = dict(rule_id="trailing", representation="UNSUPPORTED", effects=["ACCOUNT_ELIGIBILITY"],
                instrument_scope=dict(kind="ALL_ACCOUNT_INSTRUMENTS"), evidence_refs=deepcopy(refs),
                body=dict(type="UNSUPPORTED", source_rule_label="synthetic intraday trailing loss",
                          unsupported_reason="SEMANTICS_NOT_SUPPORTED", description="Synthetic watermark, not provider terms."))
    package = dict(package_id="rules", package_revision="1", provider_id="synthetic-provider", program_id="synthetic-program",
                   account_type_id="synthetic-type", phase_id="synthetic-phase", effective_period=period(), evidence_refs=deepcopy(refs),
                   interpretation=dict(interpretation_id="interpretation", interpretation_version="1", interpreted_at=time(3),
                                       interpreter_ref="synthetic-review", limitations=[]),
                   coverage=dict(completeness="COMPLETE", scope="ACCOUNT_TRADING_AND_ELIGIBILITY", evidence_refs=deepcopy(refs), limitations=[]), rules=[rule])
    assignment = dict(assignment_id="assignment", account=deepcopy(native_account),
                      **{k: package[k] for k in ("provider_id", "program_id", "account_type_id", "phase_id")},
                      agreement=dict(status="IDENTIFIED", agreement_id="synthetic-agreement"), enrollment_period=period(), phase_period=period(),
                      package_bindings=[dict(package=dict(package_id="rules", package_revision="1"), effective_period=period(), evidence_refs=deepcopy(refs))],
                      evidence_refs=deepcopy(refs))
    evidence = dict(evidence_id="terms", source=source(), acquisition="SOURCE_OBSERVED", document_reference="synthetic-terms",
                    document_revision="1", document_date=None, document_sha256=None,
                    timing=dict(observed_at=time(2), source_available_at=time(2)), captured_by="synthetic-fixture", limitations=[])
    approval = dict(approval_reference=source("approval"), authority_role="governance", policy_id="synthetic-policy", policy_version=1,
                    context_fingerprint="synthetic-native-host", assignment_id="assignment", assignment_content_fingerprint="pending",
                    package=dict(package_id="rules", package_revision="1"), package_content_fingerprint="pending", decision="APPROVED",
                    decided_at=time(4), observed_at=time(4), effective_period=period())
    return dict(contract=regime.CONTRACT, rule_version=regime.RULE_VERSION, requested_knowledge_boundary=R, economic_timestamp=T,
                account=native_account, manifest=dict(source=source("manifest"), timing=dict(observed_at=R, source_available_at=R),
                coverage=dict(completeness="COMPLETE", economic_period=period(), source_information_cutoff=R, limitations=[]),
                evidence=[evidence], assignments=[assignment], packages=[package]), approvals=[approval])


def native_account(balance):
    return dict(contract=account.CONTRACT, rule_version=account.RULE_VERSION, requested_evaluation_timestamp=K,
                observation=dict(account=dict(account_id="account", environment="DEMO", currency="USD", position_mode="HEDGING"),
                    source=dict(**ACCOUNT_NS, source_snapshot_id="snapshot"),
                    timing=dict(effective_at=T, observed_at=R, source_available_at=R),
                    account_measures=dict(completeness="COMPLETE", balance=balance, equity=balance, used_margin="0", free_margin=balance),
                    positions=dict(completeness="COMPLETE", items=[]), pending_obligations=dict(scope="NOT_IN_SCOPE")))


def original(identifier, content, published):
    raw = canonical(content).encode()
    return dict(evidence_id=identifier, source=source(),
                document=dict(namespace=deepcopy(NS), document_id="synthetic-" + identifier, document_revision="1"),
                media_type="application/json", content=base64.b64encode(raw).decode(), content_sha256=hashlib.sha256(raw).hexdigest(),
                source_available_at=published, observed_at=published)


def number(value):
    # Independent long division for finite fixture fractions, without floats.
    sign = "-" if value < 0 else ""
    whole, remainder = divmod(abs(value.numerator), value.denominator)
    digits = []
    while remainder:
        digit, remainder = divmod(remainder * 10, value.denominator)
        digits.append(str(digit))
    return sign + str(whole) + (("." + "".join(digits)) if digits else "")


def targets(q):
    result = [dict(kind=kind, event_id=None) for kind in c8.TARGET_KINDS[:-1]]
    if q["history"] is not None:
        result.extend(dict(kind="EVENT_CLASSIFICATION", event_id=row["event_id"])
                      for row in sorted(q["history"]["events"], key=lambda r: r["event_id"]))
    return result


def admit(q, context):
    """Issue test receipts from independent normative hashes, not C8 approval."""
    if context is None:
        return q, context
    context["request_sha256"] = digest(q)
    assertions = {(r["target"]["kind"], r["target"]["event_id"]): r for r in q["support_assertions"]}
    context["receipts"] = []
    for target in targets(q):
        assertion = assertions.get((target["kind"], target["event_id"]))
        context["receipts"].append(dict(target=deepcopy(target), request_sha256=digest(q),
            assertion_sha256=None if assertion is None else digest(assertion),
            original_ids=[r["evidence_id"] for r in q["originals"]], decision="ADMITTED"))
    return q, context


def seal(q, context):
    if q["history"] is not None and q["history"]["coverage"] is not None:
        report = next((r for r in q["originals"] if r["evidence_id"] == "report"), None)
        if report is not None:
            q["history"]["coverage"]["report"]["original_sha256"] = digest(report)
    return admit(q, context)


def sample(balances=(), initial="1000"):
    rp = native_regime()
    events = []
    previous = Fraction(initial)
    for i, balance in enumerate(balances, 1):
        current = Fraction(balance)
        delta = current - previous
        events.append(dict(event_id=f"close-{i}", origin=source(), original_record_id=f"original-close-{i}", occurred_at=time(5 + i),
            sequence=i, currency="USD", kind="ATOMIC_FULL_CLOSE", citations=citations(),
            close=dict(position_id=f"position-{i}", instrument=dict(namespace=deepcopy(NS), instrument_id="XAUUSD" if i % 2 else "EURUSD"),
                balance_before=number(previous), gross_realized_pnl=number(delta), commission_delta="0", financing_delta="0",
                other_cost_delta="0", net_balance_delta=number(delta), balance_after=balance)))
        previous = current
    final = balances[-1] if balances else initial
    originals = [original("report", dict(synthetic=True, account="account", initial_capital=initial, inception=INCEPTION,
                    through=T, information_cutoff=R, events=events, complete_topics=list(c8.TOPICS),
                    exclusions=dict.fromkeys(c8.EXCLUSIONS, "ABSENT"), revisions=[]), R),
                 original("terms", dict(synthetic=True, account="account", provider="synthetic-provider", initial_capital=initial,
                    formula="max(initial, atomic full-close balances) - initial/10", lifecycle_from=INCEPTION), time(2))]
    coverage = dict(report=dict(evidence_id="report", original_sha256=digest(originals[0])), **{"from": INCEPTION}, through=T,
                    source_information_cutoff=R, account_wide="COMPLETE", inception="COMPLETE", source_inventory="COMPLETE",
                    events="COMPLETE", revisions="COMPLETE", ordering="AUTHORITATIVE_TOTAL_ORDER", expected_event_count=len(events),
                    exclusions=dict.fromkeys(c8.EXCLUSIONS, "ABSENT"), citations=citations())
    h = dict(inception=INCEPTION, initial_capital=dict(amount=initial, currency="USD", citations=citations()),
             rule=dict(assignment_id="assignment", package_index=0, rule_index=0, native_rule_sha256=digest(rp["manifest"]["packages"][0]["rules"][0]),
                       effective_from=INCEPTION, effective_until=None, model="CLOSED_POSITION_BALANCE_HIGH_WATERMARK",
                       deduction="ONE_TENTH_INITIAL_CAPITAL", lower_bound="INITIAL_CAPITAL", update="EACH_ATOMIC_FULL_POSITION_CLOSE", citations=citations()),
             sources=[dict(namespace=deepcopy(NS), topics=list(c8.TOPICS), citations=citations())], coverage=coverage, events=events, revisions=[])
    q = dict(contract=c8.CONTRACT, rule_version=c8.RULE_VERSION, economic_time=T, knowledge_boundary=K,
             scope=dict(account=dict(namespace=deepcopy(ACCOUNT_NS), account_id="account", environment="DEMO", currency="USD"),
                        provider_namespace=deepcopy(NS), provider_id="synthetic-provider", program_id="synthetic-program",
                        account_type_id="synthetic-type", phase_id="synthetic-phase", lifecycle_id="lifecycle"),
             account_snapshot=bundle(native_account(final), account.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT),
             provider_regime=replay_regime(rp), originals=originals, history=h, support_assertions=[])
    q["support_assertions"] = [dict(target=deepcopy(t), citations=citations()) for t in targets(q)]
    context = dict(contract=c8.ADMISSION_CONTRACT, rule_version=c8.ADMISSION_RULE_VERSION, admission_id="synthetic-admission",
                   authority_namespace=deepcopy(NS), authority_id="independent-test-host", mandate_id="synthetic-mandate", mandate_revision=1,
                   request_sha256=digest(q), admitted_at=time(11, 12), available_at=time(11, 13), effective_from=time(1),
                   effective_until=time(30), receipts=[])
    return admit(q, context)


def run(case):
    return c8.evaluate_current_intraday_trailing_loss_threshold_state(case[0], trusted_context=case[1])


def assert_unknown(case, reason, pointer=None, root="REQUEST"):
    result = run(case)
    assert result["outcome"] == "UNKNOWN"
    assert result["state"] is None
    assert result["reason_codes"] == [reason]
    assert len(result["findings"]) == 1
    if pointer is not None:
        assert result["findings"] == [dict(reason_code=reason, subject=dict(root=root, pointer=pointer))]
    assert len(result["admission_bindings"]) == len(result["required_targets"])
    return result


def assert_invalid(case):
    with pytest.raises(ValueError, match="^INVALID_TRAILING_LOSS_INPUT$"):
        run(case)


def test_complete_zero_history_and_full_detached_reconstruction():
    case = sample()
    before = deepcopy(case)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["state"] == dict(inception=INCEPTION, as_of=T, currency="USD", initial_capital="1000", final_balance="1000",
                                  high_watermark="1000", threshold="900", steps=[])
    assert result["temporal_scope"] == "AS_OF_T_USING_EVIDENCE_BY_K"
    assert len(result["required_targets"]) == len(result["admission_bindings"]) == 9
    assert result["reason_codes"] == ["THRESHOLD_ESTABLISHED"] and result["findings"] == []
    assert set(result) == set("contract rule_version temporal_scope economic_time knowledge_boundary scope outcome reason_codes findings state native_references required_targets admission_bindings reconstruction_evidence source_authentication authority execution assessment_identity".split())
    assert result["assessment_identity"] == c8.IDENTITY_PREFIX + digest({k: v for k, v in result.items() if k != "assessment_identity"})
    assert case == before
    assert c8.validate_current_intraday_trailing_loss_threshold_state(result, case[0], trusted_context=case[1]) == result


@pytest.mark.parametrize("balances,high,threshold", [(("1100", "1050", "1120"), "1120", "1020"),
    (("1200", "900"), "1200", "1100"), (("800", "950"), "1000", "900"), (("-1", "-2"), "1000", "900")])
def test_accountwide_running_maximum(balances, high, threshold):
    case = sample(balances)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED"
    assert result["state"]["high_watermark"] == high
    assert result["state"]["threshold"] == threshold
    assert len(result["state"]["steps"]) == len(balances)
    assert len(result["required_targets"]) == 9 + len(balances)
    assert result["state"]["final_balance"] == balances[-1]
    assert [r["event_id"] for r in result["state"]["steps"]] == [r["event_id"] for r in case[0]["history"]["events"]]


def test_exact_deduction_and_no_ambient_decimal_precision():
    for initial, threshold in [("1000.01", "900.009"), ("0.000000000000000000000001", "0.0000000000000000000000009")]:
        case = sample(initial=initial)
        with localcontext() as ctx:
            ctx.prec = 2
            assert run(case)["state"]["threshold"] == threshold


def test_public_validator_calls_are_genuine(monkeypatch):
    case = sample(("1100", "1050", "1120"))
    calls = []
    original_a = account.validate_causal_financial_account_state_snapshot
    original_r = regime.validate_causal_account_rule_regime_assessment
    def check_a(value, payload):
        calls.append("account")
        return original_a(value, payload)
    def check_r(value, payload):
        calls.append("regime")
        return original_r(value, payload)
    monkeypatch.setattr(account, "validate_causal_financial_account_state_snapshot", check_a)
    monkeypatch.setattr(regime, "validate_causal_account_rule_regime_assessment", check_r)
    result = run(case)
    c8.validate_current_intraday_trailing_loss_threshold_state(result, case[0], trusted_context=case[1])
    assert calls == ["account", "regime", "account", "regime"]


@pytest.mark.parametrize("field,reason", [("account_snapshot", "ACCOUNT_SNAPSHOT_MISSING"),
    ("provider_regime", "PROVIDER_REGIME_MISSING"), ("history", "HISTORY_MISSING")])
def test_missing_owners_keep_other_native_reference_and_targets(field, reason):
    q, context = sample()
    q[field] = None
    result = assert_unknown(admit(q, context), reason, "/" + field)
    assert len(result["required_targets"]) == 9
    for name in ("account_snapshot", "provider_regime"):
        assert (result["native_references"][name] is None) == (q[name] is None)


@pytest.mark.parametrize("field,reason", [("inception", "INCEPTION_MISSING"), ("initial_capital", "INITIAL_CAPITAL_MISSING"),
    ("rule", "RULE_MISSING"), ("coverage", "COVERAGE_MISSING")])
def test_missing_history_ancestors(field, reason):
    q, context = sample()
    q["history"][field] = None
    assert_unknown(admit(q, context), reason, "/history/" + field)


def test_delayed_evidence_native_boundaries_and_report_binding():
    q, context = sample()
    result = run((q, context))
    assert T < R < context["admitted_at"] <= context["available_at"] < K
    assert result["economic_time"] == result["state"]["as_of"] == T
    assert result["knowledge_boundary"] == K
    native = decoded(q["provider_regime"]["input_json"])
    assert native["economic_timestamp"] == T and native["requested_knowledge_boundary"] == R
    assert q["history"]["coverage"]["source_information_cutoff"] == R


def test_equal_boundary_and_equal_inception_zero_event_history():
    q, context = sample()
    q["economic_time"] = K
    q["history"]["inception"] = K
    q["history"]["coverage"].update({"from": K, "through": K, "source_information_cutoff": K})
    q["history"]["rule"]["effective_from"] = K
    for original in q["originals"]:
        if original["evidence_id"] == "report":
            original.update(source_available_at=K, observed_at=K)
    np = decoded(q["account_snapshot"]["input_json"])
    np["observation"]["timing"] = dict(effective_at=K, observed_at=K, source_available_at=K)
    q["account_snapshot"] = bundle(np, account.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT)
    rp = decoded(q["provider_regime"]["input_json"])
    rp.update(economic_timestamp=K, requested_knowledge_boundary=K)
    rp["manifest"]["timing"].update(observed_at=K, source_available_at=K)
    rp["manifest"]["coverage"]["source_information_cutoff"] = K
    q["provider_regime"] = replay_regime(rp)
    context.update(admitted_at=K, available_at=K)
    assert run(seal(q, context))["state"]["threshold"] == "900"


@pytest.mark.parametrize("mutation", ["future-inception", "reversed-coverage", "T-after-K", "future-original",
    "publication-after-observation", "report-before-cutoff", "admission-before-observation", "admission-backwards", "admission-reversed-period"])
def test_contradictory_chronology_rejects(mutation):
    q, context = sample()
    if mutation == "future-inception": q["history"]["inception"] = time(13)
    elif mutation == "reversed-coverage": q["history"]["coverage"]["from"] = time(20)
    elif mutation == "T-after-K": q["economic_time"] = time(13)
    elif mutation == "future-original": q["originals"][0]["observed_at"] = time(13)
    elif mutation == "publication-after-observation": q["originals"][0]["source_available_at"] = time(12)
    elif mutation == "report-before-cutoff": q["originals"][0].update(source_available_at=time(9), observed_at=time(9))
    elif mutation == "admission-before-observation": context["admitted_at"] = T
    elif mutation == "admission-backwards": context["available_at"] = time(11, 11)
    else: context["effective_until"] = context["effective_from"]
    assert_invalid(seal(q, context))


@pytest.mark.parametrize("mutation", ["account", "currency", "namespace", "provider"])
def test_known_native_identity_contradictions(mutation):
    q, context = sample()
    if mutation == "account": q["scope"]["account"]["account_id"] = "other"
    elif mutation == "currency": q["scope"]["account"]["currency"] = "EUR"
    elif mutation == "namespace": q["scope"]["account"]["namespace"]["source_id"] = "other"
    else: q["scope"]["provider_id"] = "other"
    assert_invalid(admit(q, context))


@pytest.mark.parametrize("mutation", ["bad-original-hash", "same-document-conflict", "duplicate-evidence", "duplicate-capture", "bad-report-id", "bad-report-hash"])
def test_original_identity_and_report_integrity(mutation):
    q, context = sample()
    if mutation == "bad-original-hash": q["originals"][0]["content_sha256"] = "0" * 64
    elif mutation in ("same-document-conflict", "duplicate-capture", "duplicate-evidence"):
        row = deepcopy(q["originals"][0])
        if mutation != "duplicate-evidence": row["evidence_id"] = "report-copy"
        if mutation == "same-document-conflict":
            row["source"]["source_snapshot_id"] = "other"
            row["content"] = base64.b64encode(b"different").decode()
            row["content_sha256"] = hashlib.sha256(b"different").hexdigest()
        q["originals"].append(row); q["originals"].sort(key=lambda r: r["evidence_id"])
    elif mutation == "bad-report-id": q["history"]["coverage"]["report"]["evidence_id"] = "nonexistent"
    else: q["history"]["coverage"]["report"]["original_sha256"] = "0" * 64
    assert_invalid(admit(q, context))


def test_multiple_documents_same_snapshot_and_same_version_different_capture():
    q, context = sample()
    assert q["originals"][0]["source"] == q["originals"][1]["source"]
    extra = deepcopy(q["originals"][1]); extra["evidence_id"] = "terms-copy"; extra["source"]["source_snapshot_id"] = "another-capture"
    q["originals"].append(extra)
    assert run(admit(q, context))["outcome"] == "ESTABLISHED"


def test_named_revision_versions_are_not_silently_selected():
    q, context = sample()
    extra = deepcopy(q["originals"][1]); extra["evidence_id"] = "terms-v2"; extra["document"]["document_revision"] = "2"
    q["originals"].append(extra)
    assert_unknown(admit(q, context), "REVISION_UNSUPPORTED", "/originals/1")


@pytest.mark.parametrize("roster", ["empty", "topic", "wrong-namespace", "empty-bad-report"])
def test_source_roster_unknown_does_not_hide_invalid_report(roster):
    q, context = sample()
    if roster.startswith("empty"): q["history"]["sources"] = []
    elif roster == "topic": q["history"]["sources"][0]["topics"].pop()
    else: q["history"]["sources"][0]["namespace"]["source_id"] = "wrong"
    if roster == "empty-bad-report": q["history"]["coverage"]["report"]["evidence_id"] = "missing"
    if roster in ("wrong-namespace", "empty-bad-report"):
        assert_invalid(admit(q, context))
    else:
        assert_unknown(admit(q, context), "SOURCE_COVERAGE_INCOMPLETE", "/history/sources")


@pytest.mark.parametrize("field,value", [("events", "UNKNOWN"), ("expected_event_count", 1), ("source_information_cutoff", None),
    ("source_information_cutoff", time(9)), ("through", time(9)), ("from", time(4))])
def test_incomplete_coverage(field, value):
    q, context = sample(); q["history"]["coverage"][field] = value
    assert_unknown(admit(q, context), "HISTORY_COVERAGE_INCOMPLETE", "/history/coverage")


def test_dropped_renumbered_event_cannot_bypass_declared_count():
    q, context = sample(("1100", "1050", "1120"))
    q["history"]["events"].pop(1)
    q["history"]["events"][1]["sequence"] = 2
    q["support_assertions"] = [r for r in q["support_assertions"] if r["target"]["event_id"] != "close-2"]
    assert_unknown(admit(q, context), "HISTORY_COVERAGE_INCOMPLETE")


@pytest.mark.parametrize("field", c8.EXCLUSIONS)
def test_every_excluded_or_unresolved_lifecycle_activity(field):
    q, context = sample(); q["history"]["coverage"]["exclusions"][field] = "UNKNOWN"
    assert_unknown(admit(q, context), "EXCLUDED_ACTIVITY_UNRESOLVED", "/history/coverage/exclusions/" + field)


def test_correction_inventory_precedes_exclusion_findings():
    q, context = sample()
    q["history"]["revisions"] = [dict(notice_id="correction", origin=source(), original_record_id="correction", effective_at=T,
                                        kind="CORRECTION", citations=citations())]
    q["history"]["coverage"]["exclusions"]["historical_correction"] = "PRESENT"
    assert_unknown(admit(q, context), "REVISION_UNSUPPORTED", "/history/revisions/0")


@pytest.mark.parametrize("ordering", ["gap", "null", "backward-time", "coverage-unknown"])
def test_ambiguous_ordering(ordering):
    q, context = sample(("1100", "1050"))
    if ordering == "gap": q["history"]["events"][1]["sequence"] = 3
    elif ordering == "null": q["history"]["events"][1]["sequence"] = None
    elif ordering == "backward-time": q["history"]["events"][0]["occurred_at"] = time(8)
    else: q["history"]["coverage"]["ordering"] = "UNKNOWN"
    assert_unknown(admit(q, context), "ORDER_UNRESOLVED", "/history/events")


def test_same_timestamp_has_explicit_authoritative_sequence():
    q, context = sample(("1100", "1050")); q["history"]["events"][1]["occurred_at"] = q["history"]["events"][0]["occurred_at"]
    assert run(admit(q, context))["state"]["high_watermark"] == "1100"


@pytest.mark.parametrize("mutation", ["duplicate-sequence", "duplicate-id", "duplicate-position", "event-currency", "bad-close-arithmetic"])
def test_structural_event_contradictions(mutation):
    q, context = sample(("1100", "1050")); events = q["history"]["events"]
    if mutation == "duplicate-sequence": events[1]["sequence"] = 1
    elif mutation == "duplicate-id": events[1]["event_id"] = events[0]["event_id"]
    elif mutation == "duplicate-position": events[1]["close"]["position_id"] = events[0]["close"]["position_id"]
    elif mutation == "event-currency": events[0]["currency"] = "EUR"
    else: events[0]["close"]["balance_after"] = "1111"
    assert_invalid(admit(q, context))


def test_supported_embedded_costs_and_broken_balance_chain():
    q, context = sample(("1100",))
    close = q["history"]["events"][0]["close"]
    close.update(gross_realized_pnl="105", commission_delta="-2", financing_delta="-1", other_cost_delta="-2")
    assert run(admit(q, context))["state"]["threshold"] == "1000"
    close.update(balance_before="1001", balance_after="1101")
    assert_unknown(admit(q, context), "BALANCE_CHAIN_UNRECONCILED", "/history/events/0/close/balance_before")


def test_unsupported_event_never_succeeds_and_absence_contradiction_rejects():
    q, context = sample(("1100",)); event = q["history"]["events"][0]
    event.update(kind="DEPOSIT_OR_CREDIT", close=None, sequence=None)
    assert_invalid(admit(q, context))
    q["history"]["coverage"]["exclusions"]["deposits_or_credits"] = "PRESENT"
    assert_unknown(admit(q, context), "EXCLUDED_ACTIVITY_UNRESOLVED")


@pytest.mark.parametrize("field,value,reason", [("balance", None, "SNAPSHOT_BALANCE_MISSING"),
    ("balance", "1001", "SNAPSHOT_UNRECONCILED"), ("effective_at", time(9), "SNAPSHOT_NOT_AT_ASSESSMENT_TIME")])
def test_snapshot_missing_stale_or_unreconciled(field, value, reason):
    q, context = sample(); payload = decoded(q["account_snapshot"]["input_json"])
    if field == "balance":
        payload["observation"]["account_measures"][field] = value
        if value is None: payload["observation"]["account_measures"]["completeness"] = "PARTIAL"
    else: payload["observation"]["timing"][field] = value
    q["account_snapshot"] = bundle(payload, account.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT)
    assert_unknown(admit(q, context), reason, "/account_snapshot")


@pytest.mark.parametrize("which", ["account-boundary", "regime-economic", "regime-R-before-T", "regime-R-after-K"])
def test_wrong_native_temporal_bindings(which):
    q, context = sample()
    if which == "account-boundary":
        p = decoded(q["account_snapshot"]["input_json"]); p["requested_evaluation_timestamp"] = time(13)
        q["account_snapshot"] = bundle(p, account.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT)
    else:
        p = decoded(q["provider_regime"]["input_json"])
        if which == "regime-economic": p["economic_timestamp"] = time(9)
        else:
            boundary = time(9) if which == "regime-R-before-T" else time(13)
            p["requested_knowledge_boundary"] = boundary; p["manifest"]["timing"].update(observed_at=boundary, source_available_at=boundary)
            p["manifest"]["coverage"]["source_information_cutoff"] = boundary
        q["provider_regime"] = replay_regime(p)
    assert_invalid(admit(q, context))


@pytest.mark.parametrize("which", ["original", "account", "manifest", "native-evidence"])
def test_unknown_availability_is_never_promoted(which):
    q, context = sample()
    if which == "original":
        q["originals"][0]["source_available_at"] = None
        assert_unknown(seal(q, context), "ORIGINAL_AVAILABILITY_UNKNOWN", "/originals/0/source_available_at")
    elif which == "account":
        p = decoded(q["account_snapshot"]["input_json"]); p["observation"]["timing"]["source_available_at"] = None
        q["account_snapshot"] = bundle(p, account.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT)
        assert_unknown(admit(q, context), "NATIVE_AVAILABILITY_UNKNOWN", "/account_snapshot")
    else:
        p = decoded(q["provider_regime"]["input_json"])
        timing = p["manifest"]["timing"] if which == "manifest" else p["manifest"]["evidence"][0]["timing"]
        timing["source_available_at"] = None; q["provider_regime"] = replay_regime(p)
        assert_unknown(admit(q, context), "NATIVE_AVAILABILITY_UNKNOWN", "/provider_regime")


def test_native_unknown_is_retained_and_never_faked_positive():
    q, context = sample(); p = decoded(q["provider_regime"]["input_json"]); p["approvals"] = []
    q["provider_regime"] = replay_regime(p)
    result = assert_unknown(admit(q, context), "NATIVE_REGIME_UNRESOLVED", "/provider_regime")
    retained = decoded(result["reconstruction_evidence"]["request"]["provider_regime"]["result_json"])
    assert retained["outcome"] == "NO_APPLICABLE_APPROVED_REGIME_ESTABLISHED"
    assert result["native_references"]["provider_regime"]["assessment_id"] == retained["assessment_id"]


@pytest.mark.parametrize("which", ["enrollment", "phase", "package", "binding-gap", "rule-expired"])
def test_historical_economic_applicability(which):
    q, context = sample(); p = decoded(q["provider_regime"]["input_json"]); assignment = p["manifest"]["assignments"][0]
    if which == "rule-expired":
        q["history"]["rule"]["effective_until"] = T
        assert_unknown(admit(q, context), "RULE_NOT_SUPPORTED")
        return
    if which == "enrollment": assignment["enrollment_period"]["effective_from"] = time(6)
    elif which == "phase": assignment["phase_period"]["effective_from"] = time(6)
    elif which == "package": p["manifest"]["packages"][0]["effective_period"]["effective_from"] = time(6)
    else: assignment["package_bindings"][0]["effective_period"]["effective_from"] = time(6)
    q["provider_regime"] = replay_regime(p)
    assert_unknown(admit(q, context), "NATIVE_HISTORICAL_APPLICABILITY_UNRESOLVED", "/provider_regime")


def test_multiple_binding_union_and_current_approval_do_not_invent_past_authority():
    q, context = sample(); p = decoded(q["provider_regime"]["input_json"]); assignment = p["manifest"]["assignments"][0]
    first = assignment["package_bindings"][0]; first["effective_period"] = period(1, 8)
    second = deepcopy(first); second["effective_period"] = period(8, None); assignment["package_bindings"].append(second)
    p["manifest"]["packages"][0]["effective_period"] = period(1, None)
    p["approvals"][0]["effective_period"] = period(9, 12)
    extra = deepcopy(p["approvals"][0]); extra["approval_reference"]["source_snapshot_id"] = "later-approval"; extra["effective_period"] = period(12, 30)
    p["approvals"].append(extra)
    q["provider_regime"] = replay_regime(p)
    assert run(admit(q, context))["outcome"] == "ESTABLISHED"


def test_original_selector_indexes_do_not_follow_sorted_native_results():
    q, context = sample(); p = decoded(q["provider_regime"]["input_json"])
    second = dict(rule_id="aaa", representation="SUPPORTED", effects=["ENTRY"], instrument_scope=dict(kind="ALL_ACCOUNT_INSTRUMENTS"),
                  evidence_refs=[dict(evidence_id="terms", clause_locator="synthetic rule")], body=dict(type="ACCOUNT_STATE_REQUIREMENT", required_facts=["ACCOUNT_ACTIVE"]))
    p["manifest"]["packages"][0]["rules"].append(second)
    q["provider_regime"] = replay_regime(p)
    assert decoded(q["provider_regime"]["result_json"])["selected_regime"]["package"]["rules"][0]["rule_id"] == "aaa"
    assert run(admit(q, context))["outcome"] == "ESTABLISHED"


@pytest.mark.parametrize("selector", ["missing-owner", "invalid-existing", "malformed-missing"])
def test_selector_ancestor_rules(selector):
    q, context = sample()
    if selector != "invalid-existing": q["provider_regime"] = None
    q["history"]["rule"]["rule_index"] = -1 if selector == "malformed-missing" else 100
    if selector == "missing-owner": assert_unknown(admit(q, context), "PROVIDER_REGIME_MISSING")
    else: assert_invalid(admit(q, context))


@pytest.mark.parametrize("which", ["assertion-missing", "assertion-empty", "coverage-citation", "context-missing", "receipt-missing", "unresolved", "membership"])
def test_independent_admission_failures_and_binding_cardinality(which):
    q, context = sample()
    if which == "assertion-missing": q["support_assertions"].pop(0)
    elif which == "assertion-empty": q["support_assertions"][0]["citations"] = []
    elif which == "coverage-citation": q["history"]["coverage"]["citations"] = [citations()[1]]
    q, context = admit(q, context)
    if which in ("assertion-missing", "assertion-empty", "coverage-citation"):
        result = assert_unknown((q, context), "SUPPORT_INCOMPLETE", "/support_assertions")
        if which == "assertion-missing": assert result["admission_bindings"][0]["assertion_sha256"] is None
    elif which == "context-missing":
        result = assert_unknown((q, None), "ADMISSION_MISSING", "", "TRUSTED_CONTEXT")
        assert all(b["receipt_sha256"] is None for b in result["admission_bindings"])
    else:
        if which == "receipt-missing": context["receipts"].pop(0)
        elif which == "unresolved": context["receipts"][0]["decision"] = "UNRESOLVED"
        else: context["receipts"][0]["original_ids"].pop()
        code = {"receipt-missing": "RECEIPT_MISSING", "unresolved": "RECEIPT_UNRESOLVED", "membership": "RECEIPT_MEMBERSHIP_INCOMPLETE"}[which]
        pointer = {"receipt-missing": "/receipts", "unresolved": "/receipts/0", "membership": "/receipts/0/original_ids"}[which]
        assert_unknown((q, context), code, pointer, "TRUSTED_CONTEXT")


@pytest.mark.parametrize("which", ["request-hash", "receipt-request-hash", "assertion-hash", "unknown-target", "unknown-original", "duplicate-receipt"])
def test_forged_or_cross_bound_context_rejects(which):
    q, context = sample()
    if which == "request-hash": context["request_sha256"] = "0" * 64
    elif which == "receipt-request-hash": context["receipts"][0]["request_sha256"] = "0" * 64
    elif which == "assertion-hash": context["receipts"][0]["assertion_sha256"] = "0" * 64
    elif which == "unknown-target": context["receipts"][0]["target"] = dict(kind="EVENT_CLASSIFICATION", event_id="missing")
    elif which == "unknown-original": context["receipts"][0]["original_ids"] = ["nonexistent"]
    else: context["receipts"].insert(0, deepcopy(context["receipts"][0]))
    assert_invalid((q, context))


@pytest.mark.parametrize("field,value", [("available_at", time(13)), ("effective_from", time(13)), ("effective_until", K)])
def test_admission_temporal_pointers(field, value):
    q, context = sample(); context[field] = value
    assert_unknown((q, context), "ADMISSION_NOT_CURRENT", "/" + field, "TRUSTED_CONTEXT")


def test_rehashed_original_tampering_cannot_reuse_admission():
    q, context = sample(); q["originals"][1]["content"] = base64.b64encode(b"altered").decode()
    q["originals"][1]["content_sha256"] = hashlib.sha256(b"altered").hexdigest()
    assert_invalid((q, context))


@pytest.mark.parametrize("mutation", ["threshold", "authority", "execution", "temporal-scope", "binding", "reference", "reason", "extra"])
def test_detached_result_mutation_even_after_rehash(mutation):
    q, context = sample(); result = run((q, context))
    if mutation == "threshold": result["state"]["threshold"] = "901"
    elif mutation == "authority": result["authority"]["execution"] = 0
    elif mutation == "execution": result["execution"] = 0
    elif mutation == "temporal-scope": result["temporal_scope"] = "CURRENT"
    elif mutation == "binding": result["admission_bindings"][0]["receipt_sha256"] = "0" * 64
    elif mutation == "reference": result["native_references"]["account_snapshot"]["bundle_sha256"] = "0" * 64
    elif mutation == "reason": result["reason_codes"] = ["UNKNOWN"]
    else: result["extra"] = False
    result["assessment_identity"] = c8.IDENTITY_PREFIX + digest({k: v for k, v in result.items() if k != "assessment_identity"})
    with pytest.raises(ValueError, match="^TRAILING_LOSS_RESULT_MISMATCH$"):
        c8.validate_current_intraday_trailing_loss_threshold_state(result, q, trusted_context=context)


def test_embedded_result_context_cannot_replace_independent_admission():
    q, context = sample(); result = run((q, context))
    with pytest.raises(ValueError, match="^TRAILING_LOSS_RESULT_MISMATCH$"):
        c8.validate_current_intraday_trailing_loss_threshold_state(result, q)


def test_native_result_rehash_cannot_override_native_reconstruction():
    q, context = sample(); native = decoded(q["account_snapshot"]["result_json"])
    native["observation"]["account_measures"]["balance"] = "9999"
    native["snapshot_id"] = "financial_account_state_snapshot_" + digest({k: v for k, v in native.items() if k != "snapshot_id"})[:24]
    q["account_snapshot"]["result_json"] = encoded(native)
    assert_invalid(admit(q, context))


def test_native_json_duplicates_and_noncanonical_base64_reject():
    q, context = sample(); raw = b'{"contract":"first","contract":"second"}'
    q["account_snapshot"]["input_json"] = base64.b64encode(raw).decode()
    assert_invalid(admit(q, context))
    q, context = sample(); q["account_snapshot"]["input_json"] += "\n"
    assert_invalid(admit(q, context))


def test_authority_profit_lock_boundary_and_detached_copies():
    q, context = sample(); artifact = c8.CURRENT_INTRADAY_TRAILING_LOSS_THRESHOLD_STATE.analyze(q, context)
    result = artifact.to_dict()
    expected_flags = {"quantity_selection", "budget_approval", "position_effect_compliance", "margin_capital_approval", "trade_decision", "financial_risk", "execution"}
    assert set(result["authority"]) == expected_flags
    assert all(type(v) is bool and v is False for v in result["authority"].values())
    assert result["execution"] is False and result["source_authentication"] == "NOT_VERIFIED_BY_THIS_CAPABILITY"
    # This module cannot alter the separate lock: it has no runtime/risk-policy
    # dependency or registration. No integration test of that external gate is
    # implied by the local authority test.
    tree = ast.parse(Path(c8.__file__).read_text())
    imported = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert all("runtime" not in name and "risk_policy" not in name for name in imported)
    assert not {"authorization", "payout_eligibility", "equity_compliance", "margin_approval"}.intersection(result)
    result["state"]["threshold"] = "0"
    assert artifact.to_dict()["state"]["threshold"] == "900"
    validated = c8.validate_current_intraday_trailing_loss_threshold_state(artifact.to_dict(), q, trusted_context=context)
    validated["reconstruction_evidence"]["request"]["originals"].clear()
    assert len(q["originals"]) == 2


def test_every_returned_pointer_resolves_in_its_declared_root():
    cases = []
    for field in ("account_snapshot", "provider_regime", "history"):
        q, ctx = sample(); q[field] = None; cases.append(admit(q, ctx))
    cases.append((sample()[0], None))
    q, ctx = sample(); ctx["effective_until"] = K; cases.append((q, ctx))
    for q, context in cases:
        finding = run((q, context))["findings"][0]
        subject = finding["subject"]
        value = q if subject["root"] == "REQUEST" else context
        for segment in subject["pointer"].split("/")[1:]:
            segment = segment.replace("~1", "/").replace("~0", "~")
            value = value[int(segment)] if type(value) is list else value[segment]


def test_structural_failure_precedes_missing_owner():
    q, context = sample(); q["account_snapshot"] = None; q["originals"][0]["content_sha256"] = "0" * 64
    assert_invalid(admit(q, context))


def at(value, path):
    for key in path:
        value = value[key]
    return value


REQUEST_OBJECTS = [(), ("scope",), ("scope", "account"), ("scope", "account", "namespace"),
    ("scope", "provider_namespace"), ("account_snapshot",), ("provider_regime",),
    ("originals", 0), ("originals", 0, "source"), ("originals", 0, "document"),
    ("originals", 0, "document", "namespace"), ("history",), ("history", "initial_capital"),
    ("history", "rule"), ("history", "sources", 0), ("history", "sources", 0, "namespace"),
    ("history", "coverage"), ("history", "coverage", "report"), ("history", "coverage", "exclusions"),
    ("history", "events", 0), ("history", "events", 0, "origin"), ("history", "events", 0, "close"),
    ("history", "events", 0, "close", "instrument"), ("history", "events", 0, "close", "instrument", "namespace"),
    ("history", "events", 0, "citations", 0), ("support_assertions", 0), ("support_assertions", 0, "target")]
CONTEXT_OBJECTS = [(), ("authority_namespace",), ("receipts", 0), ("receipts", 0, "target")]


@pytest.mark.parametrize("path", REQUEST_OBJECTS)
@pytest.mark.parametrize("change", ["missing", "extra"])
def test_every_local_request_object_is_sealed(path, change):
    q, context = sample(("1100",))
    row = at(q, path)
    if change == "extra": row["unexpected"] = None
    else: del row[next(iter(row))]
    assert_invalid((q, context))


@pytest.mark.parametrize("path", CONTEXT_OBJECTS)
@pytest.mark.parametrize("change", ["missing", "extra"])
def test_every_context_object_is_sealed(path, change):
    q, context = sample()
    row = at(context, path)
    if change == "extra": row["unexpected"] = None
    else: del row[next(iter(row))]
    assert_invalid((q, context))


@pytest.mark.parametrize("value", [True, 1000, 1000.0, "-0", "1000.0", "01", "+1", "1e3", "1.", "NaN", "Infinity", " 1"])
def test_money_requires_exact_canonical_decimal_strings(value):
    q, context = sample(); q["history"]["initial_capital"]["amount"] = value
    assert_invalid(admit(q, context))


@pytest.mark.parametrize("value", [True, -1, 0.0, "0", None])
def test_selector_requires_exact_nonnegative_integer(value):
    q, context = sample(); q["provider_regime"] = None; q["history"]["rule"]["package_index"] = value
    assert_invalid(admit(q, context))


@pytest.mark.parametrize("value", ["2026-01-10T00:00:00Z", "2026-01-10T01:00:00.000000+01:00", "2026-02-30T00:00:00.000000Z", "0000-01-01T00:00:00.000000Z"])
def test_local_times_are_canonical_and_valid(value):
    q, context = sample(); q["economic_time"] = value
    assert_invalid(admit(q, context))


@pytest.mark.parametrize("collection", ["originals", "assertions", "receipts", "citations", "topics"])
def test_local_array_order_is_never_silently_normalized(collection):
    q, context = sample()
    if collection == "originals": q["originals"].reverse()
    elif collection == "assertions": q["support_assertions"].reverse()
    elif collection == "receipts": context["receipts"].reverse()
    elif collection == "citations": q["history"]["rule"]["citations"].reverse()
    else: q["history"]["sources"][0]["topics"].reverse()
    assert_invalid((q, context))


def test_empty_roster_with_events_defers_all_membership_checks():
    q, context = sample(("1100", "1050", "1120")); q["history"]["sources"] = []
    assert_unknown(admit(q, context), "SOURCE_COVERAGE_INCOMPLETE", "/history/sources")


def test_newer_snapshot_cannot_substitute_for_asof_state():
    q, context = sample(); p = decoded(q["account_snapshot"]["input_json"])
    p["observation"]["timing"] = dict(effective_at=K, source_available_at=K, observed_at=K)
    p["observation"]["account_measures"]["balance"] = "1200"
    q["account_snapshot"] = bundle(p, account.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT)
    context.update(admitted_at=K, available_at=K)
    assert_unknown(admit(q, context), "SNAPSHOT_NOT_AT_ASSESSMENT_TIME")


def test_rule_applicable_at_K_but_not_T_cannot_be_applied_retrospectively():
    q, context = sample(); p = decoded(q["provider_regime"]["input_json"])
    p["manifest"]["packages"][0]["effective_period"]["effective_from"] = R
    q["provider_regime"] = replay_regime(p)
    assert_unknown(admit(q, context), "NATIVE_REGIME_UNRESOLVED")


def test_snapshot_and_native_approval_observations_constrain_admission():
    q, context = sample(); p = decoded(q["provider_regime"]["input_json"])
    new_r = time(11, 16)
    p["requested_knowledge_boundary"] = new_r
    p["manifest"]["timing"].update(observed_at=new_r, source_available_at=new_r)
    p["manifest"]["coverage"]["source_information_cutoff"] = new_r
    p["approvals"][0]["observed_at"] = new_r
    q["provider_regime"] = replay_regime(p)
    assert_invalid(admit(q, context))


def test_late_original_observation_is_not_backdated_from_publication():
    q, context = sample(); q["originals"][1]["observed_at"] = K
    assert_invalid(seal(q, context))


def test_scoped_native_instrument_rule_is_not_accountwide_trailing_proof():
    q, context = sample(); p = decoded(q["provider_regime"]["input_json"])
    rule = p["manifest"]["packages"][0]["rules"][0]
    rule["instrument_scope"] = dict(kind="EXACT_INSTRUMENTS", instruments=[dict(**NS, environment="DEMO", instrument_id="XAUUSD")])
    q["history"]["rule"]["native_rule_sha256"] = digest(rule)
    q["provider_regime"] = replay_regime(p)
    assert_unknown(admit(q, context), "RULE_NOT_SUPPORTED")


def test_receipt_success_cannot_remove_required_event_target():
    q, context = sample(("1100",))
    context["receipts"].pop()
    result = assert_unknown((q, context), "RECEIPT_MISSING")
    assert len(result["required_targets"]) == len(result["admission_bindings"]) == 10
    assert result["admission_bindings"][-1]["receipt_sha256"] is None


def test_unrelated_unknown_activity_precedes_order_and_missing_admission():
    q, context = sample(("1100",))
    q["history"]["events"][0]["sequence"] = None
    q["history"]["coverage"]["exclusions"]["unknown_transaction"] = "UNKNOWN"
    assert_unknown((q, None), "EXCLUDED_ACTIVITY_UNRESOLVED", "/history/coverage/exclusions/unknown_transaction")


def test_overlapping_past_assignment_does_not_disappear_at_current_selection():
    q, context = sample(); p = decoded(q["provider_regime"]["input_json"])
    past = deepcopy(p["manifest"]["assignments"][0])
    past.update(assignment_id="past-assignment", enrollment_period=period(5, 8), phase_period=period(5, 8))
    p["manifest"]["assignments"].append(past)
    q["provider_regime"] = replay_regime(p)
    assert decoded(q["provider_regime"]["result_json"])["outcome"] == "UNIQUE_APPLICABLE_APPROVED_REGIME"
    assert_unknown(admit(q, context), "NATIVE_HISTORICAL_APPLICABILITY_UNRESOLVED")


def test_other_package_in_past_lifecycle_is_not_invented_continuity():
    q, context = sample(); p = decoded(q["provider_regime"]["input_json"])
    past = deepcopy(p["manifest"]["packages"][0]); past.update(package_revision="0", effective_period=period(5, 8))
    p["manifest"]["packages"].append(past)
    binding = deepcopy(p["manifest"]["assignments"][0]["package_bindings"][0])
    binding.update(package=dict(package_id="rules", package_revision="0"), effective_period=period(5, 8))
    p["manifest"]["assignments"][0]["package_bindings"].append(binding)
    q["provider_regime"] = replay_regime(p)
    # Raw package index zero remains the selected revision 1; owner output sorts.
    assert decoded(q["provider_regime"]["result_json"])["outcome"] == "UNIQUE_APPLICABLE_APPROVED_REGIME"
    assert_unknown(admit(q, context), "NATIVE_HISTORICAL_APPLICABILITY_UNRESOLVED")


def test_arbitrary_precision_does_not_change_process_integer_limits():
    q, context = sample()
    initial = "9" * 5000
    q["history"]["initial_capital"]["amount"] = initial
    p = native_account(initial)
    q["account_snapshot"] = bundle(p, account.CAUSAL_FINANCIAL_ACCOUNT_STATE_SNAPSHOT)
    result = run(admit(q, context))
    assert result["state"]["threshold"] == "8" + "9" * 4999 + ".1"


@pytest.mark.parametrize("which", ["initial-currency", "document-namespace", "event-after-T", "rule-hash", "assertion-duplicate"])
def test_additional_cross_object_contradictions(which):
    q, context = sample(("1100",))
    if which == "initial-currency": q["history"]["initial_capital"]["currency"] = "EUR"
    elif which == "document-namespace": q["originals"][0]["document"]["namespace"]["source_id"] = "other"
    elif which == "event-after-T": q["history"]["events"][0]["occurred_at"] = R
    elif which == "rule-hash": q["history"]["rule"]["native_rule_sha256"] = "0" * 64
    else: q["support_assertions"].insert(0, deepcopy(q["support_assertions"][0]))
    assert_invalid(admit(q, context))
