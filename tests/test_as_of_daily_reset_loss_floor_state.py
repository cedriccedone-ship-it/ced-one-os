"""Frozen C10 witnesses; all sources/admissions are explicitly synthetic.

Successful dependencies use real public analyzers and detached validators.
Resealing mutations issues new synthetic admission so hashes do not hide checks.
"""
import ast
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import localcontext
from fractions import Fraction
import hashlib
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import struct
from zoneinfo import ZoneInfo

import pytest

from ced_one.business_divisions.trading import as_of_daily_reset_loss_floor_state as c10
from ced_one.business_divisions.trading import current_intraday_trailing_loss_threshold_state as c8
from ced_one.business_divisions.trading import causal_financial_account_state_snapshot as account
from ced_one.business_divisions.trading import causal_account_rule_regime_assessment as regime

TARGETS = ("ACCOUNT_LIFECYCLE", "DAILY_RULE", "RESET_CALENDAR", "RESET_BALANCE", "INITIAL_CAPITAL", "SOURCE_COMPLETENESS", "SOURCE_REVISIONS")
ROLE_SUPPORT = (("enrollment",), ("daily_rule", "enrollment"), ("calendar_definition", "tzif", "daily_rule"),
                ("reset_balance", "daily_rule"), ("initial_capital", "daily_rule"), ("coverage",), ("coverage",))
FLAGS = ("quantity_selection", "budget_approval", "position_effect_compliance", "margin_capital_approval", "trade_decision", "financial_risk", "execution")
EXCLUSIONS = ("deposits_or_credits", "rewards_or_withdrawals", "capital_change", "phase_change", "reset_or_migration", "anchor_correction", "rule_or_calendar_change", "unresolved_activity")
UNKNOWN = (
    ("C8_MISSING", "/c8"), ("C8_NOT_ESTABLISHED", "/c8"), ("FIRST_PARTIAL_DAY_UNSUPPORTED", "/reset_boundary"),
    ("DAILY_REGIME_MISSING", "/daily_regime"), ("NATIVE_REGIME_UNRESOLVED", "/daily_regime"),
    ("RULE_SELECTOR_MISSING", "/daily_regime/selector"), ("RULE_NOT_SELECTED", "/daily_regime/selector"),
    ("RULE_MODEL_UNSUPPORTED", "/daily_regime/selector"), ("RULE_COVERAGE_INCOMPLETE", "/daily_regime"),
    ("CALENDAR_MISSING", "/calendar"), ("ORIGINAL_ROLE_MISSING", "/roles/enrollment"),
    ("CALENDAR_BOUNDARY_UNRESOLVED", "/calendar"), ("RULE_CALENDAR_UNSUPPORTED", "/daily_regime/selector"),
    ("RULE_SESSION_UNRESOLVED", "/daily_regime"), ("RESET_SEMANTICS_UNRESOLVED", "/reset_meaning"),
    ("COVERAGE_MISSING", "/coverage"), ("SOURCE_COVERAGE_INCOMPLETE", "/coverage/sources"),
    ("COVERAGE_INCOMPLETE", "/coverage"), ("REVISION_UNSUPPORTED", "/coverage/source_revisions"),
    ("EXCLUDED_ACTIVITY_UNRESOLVED", "/coverage/excluded_activity/deposits_or_credits"),
    ("ORIGINAL_AVAILABILITY_UNKNOWN", "/originals/0/source_available_at"),
    ("SOURCE_CUTOFF_UNRESOLVED", "/source_information_cutoff"), ("NATIVE_AVAILABILITY_UNKNOWN", "/daily_regime"),
    ("NATIVE_MAPPING_INCOMPLETE", "/native_mappings"), ("ORIGINAL_UNUSED", "/originals/7"),
    ("SUPPORT_INCOMPLETE", "/support_assertions"), ("ADMISSION_MISSING", ""), ("ADMISSION_NOT_CURRENT", "/available_at"),
    ("RECEIPT_MISSING", "/receipts"), ("RECEIPT_UNRESOLVED", "/receipts/0"),
    ("RECEIPT_MEMBERSHIP_INCOMPLETE", "/receipts/0/originals"))


def fixture_owner():
    spec = importlib.util.spec_from_file_location("c8_fixture", str(Path(__file__).with_name("test_current_intraday_trailing_loss_threshold_state.py")))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def encoded(value):
    return base64.b64encode(canonical(value).encode()).decode()


def decoded(value):
    return json.loads(base64.b64decode(value))


def stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def at(case, hours=0, minutes=0):
    return stamp(datetime.fromisoformat(case[0]["reset_boundary"].replace("Z", "+00:00")) + timedelta(hours=hours, minutes=minutes))


def set_content(row, raw):
    row["content"] = base64.b64encode(raw).decode()
    row["content_sha256"] = hashlib.sha256(raw).hexdigest()


def original(identifier, raw, source, published, observed=None):
    row = dict(evidence_id=identifier, source=deepcopy(source), document=dict(namespace={k: source[k] for k in ("source_id", "source_contract", "source_contract_version")},
        document_id="synthetic-" + identifier, document_revision="1"), media_type="application/json", content="", content_sha256="",
        source_available_at=published, observed_at=observed or published)
    set_content(row, raw)
    return row


def members(q):
    rows = [] if q["c8"] is None else decoded(q["c8"]["request_json"])["originals"]
    return [dict(owner=owner,evidence_id=o["evidence_id"],original_sha256=digest(o))
            for owner, originals in (("C8",rows),("C10",q["originals"])) for o in originals]


def seal(case):
    q, ctx8, ctx = case
    originals = {o["evidence_id"]: o for o in q["originals"]}
    refs = [r for r in q["roles"].values() if r is not None] + [m["original"] for m in q["native_mappings"]]
    for ref in refs:
        if ref["evidence_id"] in originals:
            ref["original_sha256"] = digest(originals[ref["evidence_id"]])
    if ctx is not None:
        ctx["request_sha256"] = digest(q)
        ctx["c8_context_sha256"] = None if ctx8 is None else digest(ctx8)
        assertions = {a["target"]: a for a in q["support_assertions"]}
        ctx["receipts"] = [dict(target=t,request_sha256=digest(q),c8_context_sha256=ctx["c8_context_sha256"],
            assertion_sha256=None if t not in assertions else digest(assertions[t]),originals=members(q),decision="ADMITTED") for t in TARGETS]
    return case


def replace8(case, q8, ctx8):
    f = fixture_owner()
    if q8["history"] is not None and q8["history"]["coverage"] is not None:
        ref = q8["history"]["coverage"]["report"]
        ref["original_sha256"] = digest(next(o for o in q8["originals"] if o["evidence_id"] == ref["evidence_id"]))
    if ctx8 is not None:
        f.admit(q8,ctx8)
    result = c8.evaluate_current_intraday_trailing_loss_threshold_state(q8,trusted_context=ctx8)
    case[0]["c8"] = dict(request_json=encoded(q8),result_json=encoded(result))
    case[1] = ctx8
    return seal(case)


def set_daily(case, native, refresh_selector=True):
    bundle = fixture_owner().replay_regime(native)
    case[0]["daily_regime"].update(bundle)
    selector = case[0]["daily_regime"]["selector"]
    if selector is not None and refresh_selector:
        selector["native_rule_sha256"] = digest(native["manifest"]["packages"][selector["package_index"]]["rules"][selector["rule_index"]])
    return seal(case)


# Reuse the repository's fixed TZif fixture bytes, never a host timezone fallback.
parsed = ast.parse(Path(__file__).with_name("test_xauusd_account_specific_risk_policy_evaluation.py").read_text())
TZIF = base64.b64decode(next(ast.literal_eval(n.value) for n in parsed.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id == "TZIF" for t in n.targets)))


def sample(balances=(), initial="1000", date="2026-01-10"):
    zone = ZoneInfo.from_file(BytesIO(TZIF),key="Europe/Amsterdam")
    local = datetime.fromisoformat(date)
    m = local.replace(tzinfo=zone).astimezone(timezone.utc)
    n = (local+timedelta(days=1)).replace(tzinfo=zone).astimezone(timezone.utc)
    f = fixture_owner()
    f.time = lambda day,hour=0: stamp(m+timedelta(days=day-10,hours=hour))
    f.T, f.R, f.K, f.INCEPTION = stamp(m), stamp(m+timedelta(hours=5)), stamp(m+timedelta(hours=8)), f.time(5)
    q8,ctx8 = f.sample(balances,initial)
    native = decoded(q8["provider_regime"]["input_json"])
    refs = [dict(evidence_id="terms",clause_locator="synthetic daily rule")]
    daily = dict(rule_id="daily",representation="SUPPORTED",effects=["ACCOUNT_ELIGIBILITY"],instrument_scope=dict(kind="ALL_ACCOUNT_INSTRUMENTS"),evidence_refs=deepcopy(refs),
        body=dict(type="DAILY_RESET_FLOOR",measure=dict(kind="EQUITY",currency="USD",definition_refs=deepcopy(refs),cost_treatment=dict(commissions="IN_MEASURE",financing="IN_MEASURE",other_charges="NOT_APPLICABLE")),
        reset_anchor="BALANCE",deduction=dict(kind="INITIAL_REFERENCE_FRACTION",reference="INITIAL_BALANCE",fraction="0.03"),compliant_when="GREATER_THAN_OR_EQUAL",
        adjustment_policy="NO_UNREPRESENTED_CAPITAL_OR_PHASE_ADJUSTMENTS",reset_schedule=dict(source_timezone="Europe/Amsterdam",source_local_reset_time="00:00:00",
            schedule_period=dict(effective_from=stamp(m),effective_until=stamp(n),end_status="KNOWN"),boundaries=[stamp(m),stamp(n)],evidence_refs=deepcopy(refs))))
    native["manifest"]["packages"][0]["rules"].append(daily)
    q8["provider_regime"] = f.replay_regime(native)
    q8["originals"][0]["observed_at"] = stamp(m+timedelta(hours=5,minutes=1))
    term = decoded(q8["originals"][1]["content"])
    term.update(daily_rule=daily["body"], explicit_synthetic_source=True)
    set_content(q8["originals"][1],canonical(term).encode())
    q8["history"]["coverage"]["report"]["original_sha256"] = digest(q8["originals"][0])
    ctx8.update(admitted_at=stamp(m+timedelta(hours=6)),available_at=stamp(m+timedelta(hours=6,minutes=5)))
    f.admit(q8,ctx8)
    result8 = c8.evaluate_current_intraday_trailing_loss_threshold_state(q8,trusted_context=ctx8)
    native_daily = deepcopy(native)
    native_daily["economic_timestamp"] = stamp(m+timedelta(hours=2))
    bundle = f.replay_regime(native_daily)
    scope = deepcopy(q8["scope"])
    provider = f.source
    reset_source = decoded(q8["account_snapshot"]["input_json"])["observation"]["source"]
    final = balances[-1] if balances else initial
    rows = [original("enrollment",canonical(dict(synthetic=True,scope=scope,inception=f.INCEPTION)).encode(),provider("enrollment"),f.time(2)),
        original("calendar_definition",canonical(dict(synthetic=True,timezone="Europe/Amsterdam",reset="00:00:00",session=[stamp(m),stamp(n)])).encode(),provider("calendar"),f.time(2)),
        original("tzif",TZIF,dict(source_id="synthetic-tzdb",source_contract="tzif",source_contract_version="1",source_snapshot_id="fixture"),f.time(2)),
        original("reset_balance",canonical(dict(synthetic=True,balance=final,effective_at=stamp(m),mode="AFTER_ALL_C8_EVENTS_AT_M")).encode(),reset_source,f.R,stamp(m+timedelta(hours=5,minutes=1))),
        original("initial_capital",canonical(dict(synthetic=True,initial_capital=initial,currency="USD",scope=scope)).encode(),provider("capital"),f.time(2)),
        original("coverage",canonical(dict(synthetic=True,complete=True,through=native_daily["economic_timestamp"],cutoff=f.R,revisions=[])).encode(),provider("coverage"),stamp(m+timedelta(hours=5,minutes=30)),stamp(m+timedelta(hours=5,minutes=31)))]
    copied_terms = deepcopy(q8["originals"][1]); copied_terms["evidence_id"] = "daily_rule"; rows.append(copied_terms)
    rows.sort(key=lambda o:o["evidence_id"])
    roles = {role:dict(evidence_id=role,original_sha256=digest(next(o for o in rows if o["evidence_id"]==role))) for role in ("enrollment","daily_rule","calendar_definition","tzif","reset_balance","initial_capital","coverage")}
    q = dict(contract=c10.CONTRACT,rule_version=c10.RULE_VERSION,economic_time=native_daily["economic_timestamp"],knowledge_boundary=f.K,reset_boundary=stamp(m),source_information_cutoff=f.R,scope=scope,
        c8=dict(request_json=encoded(q8),result_json=encoded(result8)),daily_regime=dict(**bundle,selector=dict(assignment_id="assignment",package_index=0,rule_index=1,native_rule_sha256=digest(daily))),
        calendar=dict(timezone_id="Europe/Amsterdam",tzdb_release="synthetic-fixture-release",tzif_sha256=hashlib.sha256(TZIF).hexdigest(),local_date=date,local_reset_time="00:00:00",utc_start=stamp(m),utc_end=stamp(n)),
        reset_meaning=dict(mode="AFTER_ALL_C8_EVENTS_AT_M"),coverage=dict(economic_from=f.INCEPTION,economic_through=native_daily["economic_timestamp"],
            sources=sorted([deepcopy(f.NS),deepcopy(f.ACCOUNT_NS),dict(source_id="synthetic-tzdb",source_contract="tzif",source_contract_version="1")],key=lambda ns:tuple(ns[k] for k in ("source_id","source_contract","source_contract_version"))),
            source_inventory="COMPLETE",reset_activity="COMPLETE",lifecycle="COMPLETE",rule_calendar="COMPLETE",source_revisions="NONE",excluded_activity=dict.fromkeys(EXCLUSIONS,"ABSENT")),
        originals=rows,roles=roles,native_mappings=[dict(native_evidence_id="terms",original=deepcopy(roles["daily_rule"]))],support_assertions=[])
    for target, required in zip(TARGETS,ROLE_SUPPORT):
        q["support_assertions"].append(dict(target=target,citations=[dict(evidence_id=r,start=0,end=len(base64.b64decode(next(o for o in rows if o["evidence_id"]==r)["content"]))) for r in sorted(required)]))
    ctx = dict(contract=c10.ADMISSION_CONTRACT,rule_version=c10.ADMISSION_RULE_VERSION,admission_id="synthetic-c10-admission",authority_namespace=deepcopy(f.NS),authority_id="independent-synthetic-host",
        mandate_id="synthetic-c10-review",mandate_revision=1,request_sha256="",c8_context_sha256="",admitted_at=stamp(m+timedelta(hours=7)),available_at=stamp(m+timedelta(hours=7,minutes=5)),effective_from=f.time(1),effective_until=None,receipts=[])
    return seal([q,ctx8,ctx])


def run(case):
    return c10.evaluate_as_of_daily_reset_loss_floor_state(case[0],trusted_c8_context=case[1],trusted_context=case[2])


def validate(result,case):
    return c10.validate_as_of_daily_reset_loss_floor_state(result,case[0],trusted_c8_context=case[1],trusted_context=case[2])


def invalid(case):
    with pytest.raises(ValueError,match="^INVALID_DAILY_RESET_FLOOR_INPUT$"):
        run(case)


def synthetic_midnight(case,kind):
    m = datetime.fromisoformat(case[0]["reset_boundary"].replace("Z","+00:00"))
    # The ordinary fixture's old offset is +1h. Gap skips midnight; fold repeats it.
    transition = m if kind == "gap" else m+timedelta(hours=1)
    new_offset = 7200 if kind == "gap" else 0
    raw = b"TZif\0"+b"\0"*15+struct.pack(">6l",0,0,0,1,2,8)+struct.pack(">l",int(transition.timestamp()))+b"\1"+struct.pack(">lbb",3600,0,0)+struct.pack(">lbb",new_offset,0,4)+b"OLD\0NEW\0"
    row = next(o for o in case[0]["originals"] if o["evidence_id"]=="tzif")
    set_content(row,raw)
    case[0]["calendar"]["tzif_sha256"] = row["content_sha256"]
    for a in case[0]["support_assertions"]:
        for c in a["citations"]:
            if c["evidence_id"]=="tzif": c["end"]=len(raw)
    return seal(case)


def unknown_case(reason):
    case=sample(); q,ctx8,ctx=case
    if reason == "C8_MISSING": q["c8"],case[1]=None,None
    elif reason == "C8_NOT_ESTABLISHED":
        q8=decoded(q["c8"]["request_json"]); q8["history"]=None; replace8(case,q8,ctx8)
    elif reason == "FIRST_PARTIAL_DAY_UNSUPPORTED":
        q8=decoded(q["c8"]["request_json"]); q8["history"]["inception"]=q["reset_boundary"]; q8["history"]["coverage"]["from"]=q["reset_boundary"]; replace8(case,q8,ctx8)
    elif reason == "DAILY_REGIME_MISSING": q["daily_regime"]=None; q["native_mappings"]=[]
    elif reason == "NATIVE_REGIME_UNRESOLVED":
        native=decoded(q["daily_regime"]["input_json"]); native["approvals"]=[]; set_daily(case,native)
    elif reason == "RULE_SELECTOR_MISSING": q["daily_regime"]["selector"]=None
    elif reason == "RULE_NOT_SELECTED":
        native=decoded(q["daily_regime"]["input_json"])
        other=deepcopy(native["manifest"]["packages"][0]); other["package_id"]="other"; native["manifest"]["packages"].append(other)
        binding=deepcopy(native["manifest"]["assignments"][0]["package_bindings"][0]); binding["package"]["package_id"]="other"; binding["effective_period"]["effective_from"]=at(case,48)
        native["manifest"]["assignments"][0]["package_bindings"].append(binding)
        q["daily_regime"]["selector"]["package_index"]=1; set_daily(case,native)
    elif reason == "RULE_MODEL_UNSUPPORTED":
        native=decoded(q["daily_regime"]["input_json"]); native["manifest"]["packages"][0]["rules"][1]["body"]["deduction"]["fraction"]="0.05"; set_daily(case,native)
    elif reason == "RULE_COVERAGE_INCOMPLETE":
        native=decoded(q["daily_regime"]["input_json"]); native["manifest"]["packages"][0]["coverage"]["completeness"]="LIMITED"; set_daily(case,native)
    elif reason == "CALENDAR_MISSING": q["calendar"]=None
    elif reason == "ORIGINAL_ROLE_MISSING": q["roles"]["enrollment"]=None
    elif reason == "CALENDAR_BOUNDARY_UNRESOLVED": synthetic_midnight(case,"gap")
    elif reason == "RULE_CALENDAR_UNSUPPORTED":
        native=decoded(q["daily_regime"]["input_json"]); schedule=native["manifest"]["packages"][0]["rules"][1]["body"]["reset_schedule"]
        schedule["schedule_period"]["effective_until"]=at(case,48); schedule["boundaries"].append(at(case,48)); set_daily(case,native)
    elif reason == "RULE_SESSION_UNRESOLVED":
        native=decoded(q["daily_regime"]["input_json"]); native["manifest"]["assignments"][0]["package_bindings"][0]["effective_period"]["effective_until"]=at(case,4); set_daily(case,native)
    elif reason == "RESET_SEMANTICS_UNRESOLVED": q["reset_meaning"]={"mode":"UNKNOWN"}
    elif reason == "COVERAGE_MISSING": q["coverage"]=None
    elif reason == "SOURCE_COVERAGE_INCOMPLETE": q["coverage"]["sources"]=[]
    elif reason == "COVERAGE_INCOMPLETE": q["coverage"]["reset_activity"]="UNKNOWN"
    elif reason == "REVISION_UNSUPPORTED": q["coverage"]["source_revisions"]="PRESENT"
    elif reason == "EXCLUDED_ACTIVITY_UNRESOLVED": q["coverage"]["excluded_activity"]["deposits_or_credits"]="PRESENT"
    elif reason == "ORIGINAL_AVAILABILITY_UNKNOWN": q["originals"][0]["source_available_at"]=None
    elif reason == "SOURCE_CUTOFF_UNRESOLVED": q["originals"][0].update(source_available_at=at(case,5,1),observed_at=at(case,5,2))
    elif reason == "NATIVE_AVAILABILITY_UNKNOWN":
        native=decoded(q["daily_regime"]["input_json"]); native["manifest"]["timing"]["source_available_at"]=None; set_daily(case,native)
    elif reason == "NATIVE_MAPPING_INCOMPLETE": q["native_mappings"]=[]
    elif reason == "ORIGINAL_UNUSED":
        extra=deepcopy(q["originals"][0]); extra["evidence_id"]="zz_extra"; extra["source"]["source_snapshot_id"]="extra"; extra["document"]["document_id"]="extra"; q["originals"].append(extra)
    elif reason == "SUPPORT_INCOMPLETE": q["support_assertions"]=[]
    elif reason == "ADMISSION_MISSING": case[2]=None
    elif reason == "ADMISSION_NOT_CURRENT": ctx["available_at"]=at(case,9)
    seal(case)
    if reason == "RECEIPT_MISSING": ctx["receipts"].pop()
    elif reason == "RECEIPT_UNRESOLVED": ctx["receipts"][0]["decision"]="UNRESOLVED"
    elif reason == "RECEIPT_MEMBERSHIP_INCOMPLETE": ctx["receipts"][0]["originals"]=[]
    return case


@pytest.mark.parametrize("balances,floor,reset",[((),"970","1000"),(("1100","1050","1120"),"1090","1120"),(("1100","1050"),"1020","1050")])
def test_positive_public_replay_exact_finance_and_detached(balances,floor,reset):
    case=sample(balances); before=deepcopy(case); result=run(case)
    assert result["outcome"]=="ESTABLISHED"
    assert result["state"]["daily_loss_floor"]==floor
    assert result["state"]["reset_balance"]==reset
    assert result["state"]["daily_loss_allowance"]=="30"
    assert result["state"]["as_of"]==case[0]["economic_time"]
    assert result["state"]["reset_boundary"]==case[0]["reset_boundary"]
    assert result["required_targets"]==list(TARGETS)
    assert validate(result,case)==result
    assert case==before
    assert all(binding["originals"]==members(case[0]) for binding in result["admission_bindings"])


@pytest.mark.parametrize("reason,pointer",UNKNOWN,ids=[r for r,p in UNKNOWN])
def test_all_31_unknown_branches_and_existing_pointers(reason,pointer):
    case=unknown_case(reason); result=run(case)
    assert result["outcome"]=="UNKNOWN" and result["state"] is None
    assert result["reason_codes"]==[reason]
    root="TRUSTED_CONTEXT" if reason in ("ADMISSION_MISSING","ADMISSION_NOT_CURRENT","RECEIPT_MISSING","RECEIPT_UNRESOLVED","RECEIPT_MEMBERSHIP_INCOMPLETE") else "REQUEST"
    assert result["findings"]==[dict(reason_code=reason,subject=dict(root=root,pointer=pointer))]
    subject=case[2] if root=="TRUSTED_CONTEXT" else case[0]
    for token in pointer.split('/')[1:]: subject=subject[int(token)] if isinstance(subject,list) else subject[token]
    assert all(b["originals"]==members(case[0]) for b in result["admission_bindings"])
    assert validate(result,case)==result


@pytest.mark.parametrize("date,hours",[("2026-01-10",24),("2026-03-29",23),("2026-10-25",25)])
def test_calendar_delayed_reconstruction_with_mixed_report(date,hours):
    case=sample(date=date); q,ctx8,ctx=case; result=run(case)
    assert result["outcome"]=="ESTABLISHED"
    assert (datetime.fromisoformat(q["calendar"]["utc_end"])-datetime.fromisoformat(q["reset_boundary"])).total_seconds()==hours*3600
    assert q["reset_boundary"] < q["economic_time"] < q["source_information_cutoff"] < ctx8["available_at"] < ctx["admitted_at"] < ctx["available_at"] < q["knowledge_boundary"] < q["calendar"]["utc_end"]
    q8=decoded(q["c8"]["request_json"])
    assert q8["originals"][0]["source_available_at"]==q["source_information_cutoff"]
    assert q8["originals"][0]["observed_at"]>q["source_information_cutoff"]


@pytest.mark.parametrize("kind",["gap","fold"])
def test_nonexistent_and_ambiguous_midnight_are_unknown(kind):
    result=run(synthetic_midnight(sample(),kind))
    assert result["reason_codes"]==["CALENDAR_BOUNDARY_UNRESOLVED"]


@pytest.mark.parametrize("field",["request_sha256","c8_context_sha256"])
@pytest.mark.parametrize("receipts",[True,False])
@pytest.mark.parametrize("parent",["positive","missing","unknown"])
def test_root_bindings_are_structural_even_before_missing_parent(field,receipts,parent):
    case=sample()
    if parent=="missing": case[0]["c8"],case[1]=None,None
    elif parent=="unknown":
        q8=decoded(case[0]["c8"]["request_json"]); q8["history"]=None; replace8(case,q8,case[1])
    seal(case)
    if not receipts: case[2]["receipts"]=[]
    case[2][field]="0"*64
    invalid(case)


def test_empty_observation_witness_and_native_references():
    case=sample(); q=case[0]
    q.update(c8=None,daily_regime=None,calendar=None,reset_meaning=None,coverage=None,originals=[],roles=dict.fromkeys(q["roles"],None),native_mappings=[],support_assertions=[])
    case[1]=None; seal(case); case[2]["receipts"]=[]
    result=run(case)
    assert result["reason_codes"]==["C8_MISSING"] and result["state"] is None
    assert result["native_references"]==dict(c8=None,reset_snapshot=None,daily_regime=None)
    assert result["admission_bindings"]==[dict(target=t,assertion_sha256=None,receipt_sha256=None,originals=[]) for t in TARGETS]
    case[2]=None
    assert run(case)["reason_codes"]==["C8_MISSING"]


@pytest.mark.parametrize("mode",["missing","empty","subset","unresolved"])
def test_repaired_full_result_membership_independent_of_receipt(mode):
    case=sample(); receipt=case[2]["receipts"][0]; expected=members(case[0]); assertion=case[0]["support_assertions"][0]
    if mode=="missing": case[2]["receipts"].pop(0)
    elif mode=="empty": receipt["originals"]=[]
    elif mode=="subset": receipt["originals"].pop()
    else: receipt["decision"]="UNRESOLVED"
    result=run(case)
    expected_reason={"missing":"RECEIPT_MISSING","empty":"RECEIPT_MEMBERSHIP_INCOMPLETE","subset":"RECEIPT_MEMBERSHIP_INCOMPLETE","unresolved":"RECEIPT_UNRESOLVED"}[mode]
    assert result["reason_codes"]==[expected_reason]
    binding=result["admission_bindings"][0]
    assert binding==dict(target=TARGETS[0],assertion_sha256=digest(assertion),receipt_sha256=None if mode=="missing" else digest(receipt),originals=expected)
    assert validate(result,case)==result


@pytest.mark.parametrize("role,pub,reason",[("coverage",4,"SOURCE_CUTOFF_UNRESOLVED"),("coverage",5,None),("coverage",6,None),
    ("calendar_definition",4,None),("calendar_definition",5,None),("calendar_definition",6,"SOURCE_CUTOFF_UNRESOLVED")])
def test_cutoff_report_only_and_operational_only(role,pub,reason):
    case=sample(); row=next(o for o in case[0]["originals"] if o["evidence_id"]==role)
    row.update(source_available_at=at(case,pub),observed_at=at(case,pub,1)); seal(case)
    result=run(case)
    assert result["reason_codes"]==([reason] if reason else ["DAILY_FLOOR_ESTABLISHED"])


@pytest.mark.parametrize("pub",[4,5,6])
def test_mixed_calendar_report_has_exact_S_cutoff(pub):
    case=sample(); q=case[0]; q["roles"]["coverage"]=deepcopy(q["roles"]["calendar_definition"])
    q["originals"]=[o for o in q["originals"] if o["evidence_id"]!="coverage"]
    for assertion in q["support_assertions"][-2:]: assertion["citations"]=[deepcopy(q["support_assertions"][2]["citations"][0])]
    row=q["originals"][0]; row.update(source_available_at=at(case,pub),observed_at=at(case,pub,1)); seal(case)
    result=run(case)
    assert result["reason_codes"]==(["DAILY_FLOOR_ESTABLISHED"] if pub==5 else ["SOURCE_CUTOFF_UNRESOLVED"])


@pytest.mark.parametrize("pub",[4,5,6])
def test_imported_mixed_C8_report_cutoff(pub):
    case=sample(); q8=decoded(case[0]["c8"]["request_json"])
    q8["originals"][0].update(source_available_at=at(case,pub),observed_at=at(case,pub,1))
    # At p<S native C8 remains valid if its own report cutoff is earlier.
    if pub<5: q8["history"]["coverage"]["source_information_cutoff"]=at(case,pub)
    ctx8=case[1]
    if pub==6: ctx8.update(admitted_at=at(case,6,10),available_at=at(case,6,15))
    replace8(case,q8,ctx8)
    assert decoded(case[0]["c8"]["result_json"])["outcome"]=="ESTABLISHED"
    assert run(case)["reason_codes"]==(["DAILY_FLOOR_ESTABLISHED"] if pub==5 else ["SOURCE_CUTOFF_UNRESOLVED"])


def test_cross_owner_identical_local_ID_is_not_deduplicated():
    case=sample(); q=case[0]
    for row in q["originals"]:
        if row["evidence_id"]=="daily_rule": row["evidence_id"]="terms"
    q["originals"].sort(key=lambda o:o["evidence_id"])
    q["roles"]["daily_rule"]["evidence_id"]="terms"; q["native_mappings"][0]["original"]["evidence_id"]="terms"
    for assertion in q["support_assertions"]:
        for citation in assertion["citations"]:
            if citation["evidence_id"]=="daily_rule": citation["evidence_id"]="terms"
        assertion["citations"].sort(key=lambda c:(c["evidence_id"],c["start"],c["end"]))
    seal(case); result=run(case)
    assert result["outcome"]=="ESTABLISHED"
    assert [(m["owner"],m["evidence_id"]) for m in result["admission_bindings"][0]["originals"] if m["evidence_id"]=="terms"]==[("C8","terms"),("C10","terms")]


@pytest.mark.parametrize("mutation",["content","media","publication"])
def test_cross_owner_capture_conflicts_reject_after_rebinding(mutation):
    case=sample(); row=next(o for o in case[0]["originals"] if o["evidence_id"]=="daily_rule")
    if mutation=="content": set_content(row,b"synthetic different version content")
    elif mutation=="media": row["media_type"]="text/plain"
    else: row["observed_at"]=at(case,1)
    seal(case); invalid(case)


@pytest.mark.parametrize("index",range(7),ids=TARGETS)
def test_each_independent_target_requires_its_own_semantic_support(index):
    case=sample(); case[0]["support_assertions"][index]["citations"]=[]; seal(case)
    assert run(case)["reason_codes"]==["SUPPORT_INCOMPLETE"]


@pytest.mark.parametrize("index",range(7),ids=TARGETS)
def test_each_target_receipt_is_independently_required(index):
    case=sample(); case[2]["receipts"].pop(index)
    assert run(case)["reason_codes"]==["RECEIPT_MISSING"]


@pytest.mark.parametrize("field",["request_sha256","c8_context_sha256","assertion_sha256","target","member_hash","member_owner","member_id"])
def test_receipt_manipulation_is_structural(field):
    case=sample(); receipt=case[2]["receipts"][0]
    if field.endswith("sha256"): receipt[field]="0"*64
    elif field=="target": receipt["target"]="INVENTED"
    elif field=="member_hash": receipt["originals"][0]["original_sha256"]="0"*64
    elif field=="member_owner": receipt["originals"][0]["owner"]="OTHER"
    else: receipt["originals"][0]["evidence_id"]="not-present"
    invalid(case)


@pytest.mark.parametrize("kind",["missing","before","unknown"])
def test_same_timestamp_reset_events_require_explicit_semantics(kind):
    case=sample(("1100","1050")); q8=decoded(case[0]["c8"]["request_json"])
    for event in q8["history"]["events"]: event["occurred_at"]=case[0]["reset_boundary"]
    replace8(case,q8,case[1])
    assert run(case)["state"]["reset_balance"]=="1050"
    case[0]["reset_meaning"]=None if kind=="missing" else dict(mode="BEFORE_SOME_EVENTS_AT_M" if kind=="before" else "UNKNOWN")
    seal(case); assert run(case)["reason_codes"]==["RESET_SEMANTICS_UNRESOLVED"]
    case[0]["reset_meaning"]={"mode":"NO_C8_EVENTS_AT_M"}; seal(case); invalid(case)


def test_zero_event_no_posting_mode_and_T_equal_M():
    case=sample(); q=case[0]; q["reset_meaning"]["mode"]="NO_C8_EVENTS_AT_M"; q["economic_time"]=q["reset_boundary"]; q["coverage"]["economic_through"]=q["economic_time"]
    native=decoded(q["daily_regime"]["input_json"]); native["economic_timestamp"]=q["economic_time"]; set_daily(case,native)
    assert run(case)["outcome"]=="ESTABLISHED"


@pytest.mark.parametrize("which",["M","N","T_at_N","native_clock","native_timezone","bad_tzif","bad_tzif_hash"])
def test_calendar_contradictions_are_structural(which):
    case=sample(); q=case[0]
    if which=="M": q["calendar"]["utc_start"]=at(case,0,1)
    elif which=="N": q["calendar"]["utc_end"]=at(case,23)
    elif which=="T_at_N": q["economic_time"]=q["calendar"]["utc_end"]; q["source_information_cutoff"]=q["economic_time"]; q["knowledge_boundary"]=q["economic_time"]
    elif which.startswith("native_"):
        native=decoded(q["daily_regime"]["input_json"]); schedule=native["manifest"]["packages"][0]["rules"][1]["body"]["reset_schedule"]
        schedule["source_local_reset_time" if which=="native_clock" else "source_timezone"]="01:00:00" if which=="native_clock" else "MT5-server"
        set_daily(case,native)
    elif which=="bad_tzif_hash": q["calendar"]["tzif_sha256"]="0"*64
    else:
        row=next(o for o in q["originals"] if o["evidence_id"]=="tzif"); set_content(row,b"TZif2\0broken"); q["calendar"]["tzif_sha256"]=row["content_sha256"]
    seal(case); invalid(case)


@pytest.mark.parametrize("case_kind",["gap_binding","gap_approval","rejected_before_T","competitor","unknown_period","open_ended","connected_union","end_at_N"])
def test_full_session_native_intervals(case_kind):
    case=sample(); q=case[0]; native=decoded(q["daily_regime"]["input_json"])
    assignment=native["manifest"]["assignments"][0]; binding=assignment["package_bindings"][0]; approval=native["approvals"][0]
    positive=case_kind in ("open_ended","connected_union","end_at_N")
    if case_kind=="gap_binding": binding["effective_period"]["effective_until"]=at(case,4)
    elif case_kind=="gap_approval": approval["effective_period"]["effective_until"]=at(case,4)
    elif case_kind=="rejected_before_T":
        denial=deepcopy(approval); denial["approval_reference"]["source_snapshot_id"]="denial"; denial["decision"]="REJECTED"; denial["effective_period"].update(effective_from=at(case),effective_until=at(case,1)); native["approvals"].append(denial)
    elif case_kind=="competitor":
        competitor=deepcopy(assignment); competitor["assignment_id"]="competitor"; competitor["enrollment_period"]["effective_from"]=at(case,3); native["manifest"]["assignments"].append(competitor)
    elif case_kind=="unknown_period":
        other=deepcopy(binding); other["effective_period"].update(effective_from=at(case,3),effective_until=None,end_status="UNKNOWN"); assignment["package_bindings"].append(other)
    elif case_kind=="open_ended":
        binding["effective_period"].update(effective_until=None,end_status="OPEN_ENDED"); approval["effective_period"].update(effective_until=None,end_status="OPEN_ENDED")
    elif case_kind=="connected_union":
        tail=deepcopy(binding); binding["effective_period"]["effective_until"]=at(case,3); tail["effective_period"]["effective_from"]=at(case,3); assignment["package_bindings"].append(tail)
        tail=deepcopy(approval); approval["effective_period"]["effective_until"]=at(case,3); tail["effective_period"]["effective_from"]=at(case,3); tail["approval_reference"]["source_snapshot_id"]="tail"; native["approvals"].append(tail)
    else:
        binding["effective_period"]["effective_until"]=q["calendar"]["utc_end"]; approval["effective_period"]["effective_until"]=q["calendar"]["utc_end"]
    set_daily(case,native)
    assert run(case)["reason_codes"]==(["DAILY_FLOOR_ESTABLISHED"] if positive else ["RULE_SESSION_UNRESOLVED"])


@pytest.mark.parametrize("which",["snapshot","C8","daily"])
def test_rehashed_native_result_forgery_never_replaces_public_replay(which):
    case=sample(); q=case[0]
    if which=="daily":
        value=decoded(q["daily_regime"]["result_json"]); value["economic_timestamp"]=at(case,1); value.pop("assessment_id"); value["assessment_id"]="account_rule_regime_assessment_"+digest(value)[:24]; q["daily_regime"]["result_json"]=encoded(value)
    elif which=="C8":
        value=decoded(q["c8"]["result_json"]); value["state"]["final_balance"]="9999"; value.pop("assessment_identity"); value["assessment_identity"]=c8.IDENTITY_PREFIX+digest(value); q["c8"]["result_json"]=encoded(value)
    else:
        q8=decoded(q["c8"]["request_json"]); bundle=q8["account_snapshot"]; value=decoded(bundle["result_json"]); value["observation"]["account_measures"]["balance"]="9999"; value.pop("snapshot_id"); value["snapshot_id"]="financial_account_state_snapshot_"+digest(value)[:24]; bundle["result_json"]=encoded(value); q["c8"]["request_json"]=encoded(q8)
    seal(case); invalid(case)


@pytest.mark.parametrize("path",[("state","daily_loss_floor"),("state","reset_balance"),("state","initial_capital"),("temporal_scope",),("reconstruction_evidence","request_sha256"),
    ("admission_bindings",0,"originals"),("native_references","c8","bundle_sha256"),("native_references","reset_snapshot","snapshot_id"),("native_references","daily_regime","assessment_id"),
    ("findings",),("reason_codes",),("limitations",),("assessment_identity",)])
def test_complete_detached_reconstruction_rejects_rehashed_result_mutations(path):
    case=sample(); result=run(case); row=result
    for token in path[:-1]: row=row[token]
    key=path[-1]; previous=row[key]
    row[key]=[] if isinstance(previous,list) else "caller-change"
    if path==("findings",): row[key]=[dict(reason_code="C8_MISSING",subject=dict(root="REQUEST",pointer="/c8"))]
    result.pop("assessment_identity",None); result["assessment_identity"]=c10.IDENTITY_PREFIX+digest(result)
    # For identity itself retain a forged identity rather than repairing it.
    if path==("assessment_identity",): result["assessment_identity"]="forged"
    with pytest.raises(ValueError,match="^DAILY_RESET_FLOOR_RESULT_MISMATCH$"): validate(result,case)


@pytest.mark.parametrize("flag",FLAGS+("TOP",))
@pytest.mark.parametrize("value",[True,0])
def test_exact_false_authority_and_external_profit_lock(flag,value):
    case=sample(); result=run(case)
    assert result["authority"]==dict.fromkeys(FLAGS,False) and all(type(v) is bool for v in result["authority"].values())
    assert result["execution"] is False
    assert "FROZEN_AWAITING_PAYOUT_VETO_EXTERNAL" in result["limitations"]
    assert "NO_CONTINUOUS_COMPLIANCE" in result["limitations"] and "NO_PAYOUT_AUTHORIZATION" in result["limitations"]
    if flag=="TOP": result["execution"]=value
    else: result["authority"][flag]=value
    result.pop("assessment_identity"); result["assessment_identity"]=c10.IDENTITY_PREFIX+digest(result)
    with pytest.raises(ValueError,match="^DAILY_RESET_FLOOR_RESULT_MISMATCH$"): validate(result,case)


@pytest.mark.parametrize("initial",["1000.00000000000000000001","100000000000000000000000000000000000000000000000000000000000000001"])
def test_exact_arithmetic_does_not_use_ambient_decimal_precision(initial):
    case=sample(initial=initial)
    with localcontext() as ctx:
        ctx.prec=2
        result=run(case)
    assert result["outcome"]=="ESTABLISHED"
    assert Fraction(result["state"]["daily_loss_floor"])==Fraction(initial)*Fraction(97,100)


@pytest.mark.parametrize("balances",[("0",),("-10",)])
def test_negative_floor_is_not_promoted_to_eligibility(balances):
    result=run(sample(balances))
    assert result["outcome"]=="ESTABLISHED" and Fraction(result["state"]["daily_loss_floor"])<0
    assert result["execution"] is False and result["authority"]["trade_decision"] is False


def test_all_public_validators_are_called_without_mocked_success(monkeypatch):
    case=sample(); calls={"c8":0,"account":0,"regime":0}
    def wrap(owner,name,label):
        original=getattr(owner,name)
        def real(*args,**kwargs):
            calls[label]+=1
            return original(*args,**kwargs)
        monkeypatch.setattr(owner,name,real)
    wrap(c8,"validate_current_intraday_trailing_loss_threshold_state","c8")
    wrap(account,"validate_causal_financial_account_state_snapshot","account")
    wrap(regime,"validate_causal_account_rule_regime_assessment","regime")
    result=run(case); validate(result,case)
    assert calls["c8"]==2 and calls["account"]==4 and calls["regime"]==4


@pytest.mark.parametrize("reason,pointer",UNKNOWN[:-1],ids=[r for r,p in UNKNOWN[:-1]])
def test_unknown_order_preserves_every_earlier_gate_over_partial_receipt(reason,pointer):
    case=unknown_case(reason)
    if case[2] is not None and case[2]["receipts"]: case[2]["receipts"][0]["originals"]=[]
    assert run(case)["reason_codes"]==[reason]


@pytest.mark.parametrize("reason,pointer",UNKNOWN[:25],ids=[r for r,p in UNKNOWN[:25]])
def test_early_unknown_gates_precede_support_and_admission(reason,pointer):
    case=unknown_case(reason); case[0]["support_assertions"]=[]; case[2]=None; seal(case)
    assert run(case)["reason_codes"]==[reason]


@pytest.mark.parametrize("mutation",["report_hash","original_hash","selector","future_observation","admission_before_observation"])
def test_structural_failures_never_hidden_by_C8_missing(mutation):
    case=sample(); q=case[0]; q["c8"],case[1]=None,None
    if mutation=="report_hash":
        seal(case); q["roles"]["coverage"]["original_sha256"]="0"*64
    elif mutation=="original_hash":
        q["originals"][0]["content_sha256"]="0"*64; seal(case)
    elif mutation=="selector":
        q["daily_regime"]["selector"]["rule_index"]=100; seal(case)
    elif mutation=="future_observation":
        q["originals"][0]["observed_at"]=at(case,9); seal(case)
    else:
        seal(case); case[2]["admitted_at"]=at(case,4)
    invalid(case)


@pytest.mark.parametrize("mutation",["account","currency","lifecycle","C8_M","C8_K","daily_T","daily_R","R_after_S"])
def test_exact_known_owner_joins_reject_even_after_new_admission(mutation):
    case=sample(); q=case[0]
    if mutation in ("account","currency","lifecycle"):
        if mutation=="account": q["scope"]["account"]["account_id"]="other"
        elif mutation=="currency": q["scope"]["account"]["currency"]="EUR"
        else: q["scope"]["lifecycle_id"]="other"
    elif mutation=="C8_M": q["reset_boundary"]=at(case,0,1); q["calendar"]["utc_start"]=q["reset_boundary"]
    elif mutation=="C8_K": q["knowledge_boundary"]=at(case,9)
    else:
        native=decoded(q["daily_regime"]["input_json"])
        if mutation=="daily_T": native["economic_timestamp"]=at(case,1)
        else:
            native["requested_knowledge_boundary"]=at(case,6)
            native["manifest"]["timing"].update(observed_at=at(case,6),source_available_at=at(case,6))
            native["manifest"]["coverage"]["source_information_cutoff"]=at(case,6)
        set_daily(case,native)
    seal(case); invalid(case)


@pytest.mark.parametrize("field,value",[("model","daily equity"),("reset_anchor","EQUITY"),("fraction","0.04"),("reference","INITIAL_EQUITY"),("cost","SUBTRACT_SEPARATELY"),("comparison","GREATER_THAN"),("scope","EXACT")])
def test_supported_native_alternatives_are_unknown_not_silently_reinterpreted(field,value):
    case=sample(); native=decoded(case[0]["daily_regime"]["input_json"]); rule=native["manifest"]["packages"][0]["rules"][1]; body=rule["body"]
    if field=="model":
        rule["representation"]="UNSUPPORTED"; rule["body"]=dict(type="UNSUPPORTED",source_rule_label=value,unsupported_reason="SEMANTICS_NOT_SUPPORTED",description="synthetic alternative")
    elif field=="reset_anchor": body["reset_anchor"]=value
    elif field in ("fraction","reference"): body["deduction"][field]=value
    elif field=="cost": body["measure"]["cost_treatment"]["commissions"]=value
    elif field=="comparison": body["compliant_when"]=value
    else:
        rule["instrument_scope"]=dict(kind="EXACT_INSTRUMENTS",instruments=[dict(source_id="broker",source_contract="symbols",source_contract_version="1",environment="DEMO",instrument_id="XAUUSD")])
    set_daily(case,native)
    assert run(case)["reason_codes"]==["RULE_MODEL_UNSUPPORTED"]


@pytest.mark.parametrize("field",EXCLUSIONS)
@pytest.mark.parametrize("value",["PRESENT","UNKNOWN"])
def test_every_unsupported_post_reset_adjustment_is_unresolved(field,value):
    case=sample(); case[0]["coverage"]["excluded_activity"][field]=value; seal(case)
    result=run(case)
    assert result["reason_codes"]==["EXCLUDED_ACTIVITY_UNRESOLVED"] and result["state"] is None
    assert result["findings"][0]["subject"]["pointer"]=="/coverage/excluded_activity/"+field


@pytest.mark.parametrize("field",["account_snapshot","history","provider_regime"])
def test_genuine_native_unknown_is_preserved_and_references_follow_presence(field):
    case=sample(); q8=decoded(case[0]["c8"]["request_json"]); q8[field]=None; replace8(case,q8,case[1]); result=run(case)
    assert result["reason_codes"]==["C8_NOT_ESTABLISHED"] and result["state"] is None
    assert result["native_references"]["c8"]["outcome"]=="UNKNOWN"
    assert (result["native_references"]["reset_snapshot"] is None)==(field=="account_snapshot")
    assert result["native_references"]["daily_regime"] is not None
    assert all(b["originals"]==members(case[0]) for b in result["admission_bindings"])


def test_missing_C8_context_uses_genuine_C8_unknown_not_a_forged_positive():
    case=sample(); replace8(case,decoded(case[0]["c8"]["request_json"]),None)
    assert run(case)["reason_codes"]==["C8_NOT_ESTABLISHED"]


@pytest.mark.parametrize("mutation",["wrong_doc","unknown_native_id","wrong_source","wrong_hash","wrong_publication"])
def test_original_native_mapping_binding_rejects_resealed_manipulation(mutation):
    case=sample(); q=case[0]; native=decoded(q["daily_regime"]["input_json"])
    if mutation=="unknown_native_id": q["native_mappings"][0]["native_evidence_id"]="missing"
    elif mutation=="wrong_doc": native["manifest"]["evidence"][0]["document_reference"]="other-document"
    elif mutation=="wrong_source": native["manifest"]["evidence"][0]["source"]["source_snapshot_id"]="other-capture"
    elif mutation=="wrong_hash": native["manifest"]["evidence"][0]["document_sha256"]="0"*64
    else: native["manifest"]["evidence"][0]["timing"]["source_available_at"]=at(case,-200)
    if mutation!="unknown_native_id": set_daily(case,native)
    seal(case); invalid(case)


@pytest.mark.parametrize("field",["available_at","effective_from","effective_until"])
def test_stale_context_fields_have_exact_priority_and_pointer(field):
    case=sample()
    case[2][field]=at(case,9) if field!="effective_until" else case[0]["knowledge_boundary"]
    result=run(case)
    assert result["reason_codes"]==["ADMISSION_NOT_CURRENT"]
    assert result["findings"][0]["subject"]==dict(root="TRUSTED_CONTEXT",pointer="/"+field)


SEALED_PATHS=[(0,()),(0,("scope",)),(0,("scope","account")),(0,("scope","provider_namespace")),(0,("roles",)),
    (0,("originals",0)),(0,("originals",0,"source")),(0,("originals",0,"document")),(0,("calendar",)),(0,("coverage",)),
    (0,("coverage","excluded_activity")),(0,("reset_meaning",)),(0,("c8",)),(0,("daily_regime",)),(0,("daily_regime","selector")),
    (0,("native_mappings",0)),(0,("roles","coverage")),(0,("support_assertions",0)),(0,("support_assertions",0,"citations",0)),
    (2,()),(2,("receipts",0)),(2,("receipts",0,"originals",0))]
@pytest.mark.parametrize("root,path",SEALED_PATHS)
def test_every_local_object_is_sealed(root,path):
    case=sample(); row=case[root]
    for token in path: row=row[token]
    row["unexpected"]=None
    if root==0: seal(case)
    invalid(case)


@pytest.mark.parametrize("mutation",["original_order","duplicate_original","source_order","duplicate_source","assertion_order","duplicate_assertion","citation_order","duplicate_citation","receipt_order","duplicate_receipt","member_order","duplicate_member","mapping_duplicate"])
def test_collection_identity_and_order_are_enforced(mutation):
    case=sample(); q,_,ctx=case
    if mutation=="original_order": q["originals"].reverse()
    elif mutation=="duplicate_original": q["originals"].insert(0,deepcopy(q["originals"][0]))
    elif mutation=="source_order": q["coverage"]["sources"].reverse()
    elif mutation=="duplicate_source": q["coverage"]["sources"].insert(0,deepcopy(q["coverage"]["sources"][0]))
    elif mutation=="assertion_order": q["support_assertions"].reverse()
    elif mutation=="duplicate_assertion": q["support_assertions"].insert(0,deepcopy(q["support_assertions"][0]))
    elif mutation=="citation_order": q["support_assertions"][1]["citations"].reverse()
    elif mutation=="duplicate_citation": q["support_assertions"][0]["citations"]*=2
    elif mutation=="mapping_duplicate": q["native_mappings"]*=2
    if mutation in ("receipt_order","duplicate_receipt","member_order","duplicate_member"):
        if mutation=="receipt_order": ctx["receipts"].reverse()
        elif mutation=="duplicate_receipt": ctx["receipts"].insert(0,deepcopy(ctx["receipts"][0]))
        elif mutation=="member_order": ctx["receipts"][0]["originals"].reverse()
        else: ctx["receipts"][0]["originals"].insert(0,deepcopy(ctx["receipts"][0]["originals"][0]))
    else: seal(case)
    invalid(case)


@pytest.mark.parametrize("mutation",["float","bool_index","negative_index","bool_mandate","bad_time","orphan_ref","citation_end","citation_bool","bad_namespace","bad_currency","base64","duplicate_json","float_json"])
def test_exact_primitives_and_native_JSON_decode_reject(mutation):
    case=sample(); q=case[0]
    if mutation=="float": q["extra"]=1.5
    elif mutation=="bool_index": q["daily_regime"]["selector"]["rule_index"]=True
    elif mutation=="negative_index": q["daily_regime"]["selector"]["rule_index"]=-1
    elif mutation=="bool_mandate": case[2]["mandate_revision"]=True
    elif mutation=="bad_time": q["economic_time"]="2026-01-10T01:00:00Z"
    elif mutation=="orphan_ref": q["roles"]["coverage"]["evidence_id"]="missing"
    elif mutation=="citation_end": q["support_assertions"][0]["citations"][0]["end"]=10**9
    elif mutation=="citation_bool": q["support_assertions"][0]["citations"][0]["start"]=False
    elif mutation=="bad_namespace": q["originals"][0]["document"]["namespace"]["source_id"]="other"
    elif mutation=="bad_currency": q["scope"]["account"]["currency"]="usd"
    elif mutation=="base64": q["daily_regime"]["input_json"]="!"
    else:
        raw=b'{"contract":1,"contract":2}' if mutation=="duplicate_json" else b'{"x":1.0}'
        q["daily_regime"]["input_json"]=base64.b64encode(raw).decode()
    seal(case); invalid(case)


@pytest.mark.parametrize("fact",["prior_intraday_equity_breach","FROZEN_AWAITING_PAYOUT"])
def test_original_account_restrictions_never_become_floor_authority(fact):
    case=sample(); row=next(o for o in case[0]["originals"] if o["evidence_id"]=="enrollment")
    body=decoded(row["content"]); body[fact]=True; set_content(row,canonical(body).encode()); seal(case)
    result=run(case)
    assert result["outcome"]=="ESTABLISHED" and result["state"]["daily_loss_floor"]=="970"
    assert result["authority"]==dict.fromkeys(FLAGS,False) and result["execution"] is False
    assert "NO_CURRENT_ELIGIBILITY" in result["limitations"] and "FROZEN_AWAITING_PAYOUT_VETO_EXTERNAL" in result["limitations"]


def test_full_TZif_citation_required_not_merely_some_artifact_bytes():
    case=sample()
    citation=next(c for c in case[0]["support_assertions"][2]["citations"] if c["evidence_id"]=="tzif")
    citation["end"]-=1; seal(case)
    assert run(case)["reason_codes"]==["SUPPORT_INCOMPLETE"]


def test_false_report_completeness_does_not_hide_missing_or_invalid_original():
    case=sample(); case[0]["coverage"]["sources"]=[]
    seal(case)
    assert run(case)["reason_codes"]==["SOURCE_COVERAGE_INCOMPLETE"]
    case[0]["roles"]["coverage"]["original_sha256"]="0"*64
    invalid(case)


@pytest.mark.parametrize("kind",["unknown","two_revisions","same_version_conflict"])
def test_revisions_are_not_selected_by_labels_or_text_order(kind):
    case=sample(); q=case[0]
    if kind=="unknown": q["coverage"]["source_revisions"]="UNKNOWN"
    else:
        other=deepcopy(q["originals"][0]); other["evidence_id"]="zz_revision"; other["source"]["source_snapshot_id"]="revision-capture"
        if kind=="two_revisions": other["document"]["document_revision"]="2"
        else: set_content(other,b"new bytes for the same immutable version")
        q["originals"].append(other)
    seal(case)
    if kind=="same_version_conflict": invalid(case)
    else:
        result=run(case)
        assert result["reason_codes"]==["REVISION_UNSUPPORTED"] and result["state"] is None


def test_caller_original_rehash_cannot_reuse_existing_C8_admission():
    case=sample(); q8=decoded(case[0]["c8"]["request_json"])
    set_content(q8["originals"][0],b"caller modified original financial evidence")
    q8["history"]["coverage"]["report"]["original_sha256"]=digest(q8["originals"][0])
    case[0]["c8"]["request_json"]=encoded(q8); seal(case)
    invalid(case)


def test_huge_independent_mandate_integer_has_no_process_wide_limit_change():
    import sys
    case=sample(); case[2]["mandate_revision"]=10**4500
    before=sys.get_int_max_str_digits()
    result=run(case)
    assert result["outcome"]=="ESTABLISHED"
    assert validate(result,case)==result
    assert sys.get_int_max_str_digits()==before
