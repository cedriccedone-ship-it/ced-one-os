"""Real strategy/#23/#13 owners exercise immutable technical candidate terms."""
from copy import deepcopy

import pytest

from ced_one.business_divisions.trading import xauusd_technical_trade_candidate as owner
from ced_one.business_divisions.trading.causal_snapshot_availability import CAUSAL_SNAPSHOT_AVAILABILITY
from ced_one.business_divisions.trading.causal_trading_policy_strategy_action_formulation import STRATEGY_ACTION_FORMULATION
from tests.test_xauusd_causal_liquidity_reversal import scenario, action_input, candle, ts

ENGINE = owner.XAUUSD_TECHNICAL_TRADE_CANDIDATE


def policy(seconds=120):
    return dict(contract=owner.POLICY_CONTRACT, policy_id="technical-1", policy_version=1,
                configuration=dict(entry_validity_duration_seconds=seconds))


def formulation_input(direction="LONG", seconds=120, entry=None, at=31):
    d,h = scenario(direction)
    if entry is not None:
        h["M1"][33] = (candle(30,entry-10,entry,entry-10,entry) if direction=="LONG"
                        else candle(30,entry+10,entry+10,entry,entry))
    action_request = action_input(d,h,at)
    action = STRATEGY_ACTION_FORMULATION.analyze(action_request).to_dict()
    return dict(candidate_policy_definition=policy(seconds), strategy_assessment=deepcopy(action_request["strategy_assessment"]),
                action_formulation=action, action_formulation_input=action_request), h


@pytest.fixture(scope="module")
def originals():
    return {direction: formulation_input(direction) for direction in ("LONG","SHORT")}


def base(originals, direction="LONG"):
    return deepcopy(originals[direction])


def source(history, at, timeframe="M1", include_future=False):
    return CAUSAL_SNAPSHOT_AVAILABILITY.analyze(dict(symbol="XAUUSD", timeframe=timeframe,
        requested_evaluation_timestamp=ts(at), candle_history=deepcopy(history if include_future else
            [c for c in history if owner.parse_timestamp(c["timestamp"]) <= owner.parse_timestamp(ts(at))]))).to_dict()


def validity_input(p,h,at=31,formulated=None):
    return dict(candidate_formulation=ENGINE.analyze(p).to_dict() if formulated is None else formulated,
                formulation_input=deepcopy(p),evaluation_boundary=ts(at),m1_source=source(h["M1"],at))


def evaluate(p,h,at=31):
    return ENGINE.evaluate_validity(validity_input(p,h,at)).to_dict()


def set_breach(h,direction,minute=31,equality=False):
    row=next(c for c in h["M1"] if c["timestamp"]==ts(minute))
    if direction=="LONG": row["low"]=107.0 if equality else 106.0
    else: row["high"]=193.0 if equality else 194.0


@pytest.mark.parametrize("direction",["LONG","SHORT"])
def test_exact_real_terms_and_no_buffers(originals,direction):
    p,h=base(originals,direction)
    before=deepcopy(p)
    r=ENGINE.analyze(p).to_dict(); c=r["candidate"]
    b=p["strategy_assessment"]["bindings"]
    assert r["formulation_status"]=="FORMULATED"
    assert c["entry_reference"]==dict(kind="TECHNICAL_ENTRY_REFERENCE",value=b["T1"]["candle"]["close"],evidence=b["T1"])
    assert c["stop_reference"]==dict(kind="TECHNICAL_STOP_REFERENCE",value=b["E1"]["candle"]["low" if direction=="LONG" else "high"],evidence=b["E1"])
    assert c["valid_from"]==ts(31) and c["valid_until"]==ts(33)
    assert r["upstream_formulation"]==p["action_formulation"]
    assert p==before
    assert owner.validate_technical_candidate_formulation(r,p)==r


@pytest.mark.parametrize("direction,entry,formed",[("LONG",124,True),("LONG",107,False),("LONG",100,False),
    ("SHORT",176,True),("SHORT",193,False),("SHORT",200,False)])
def test_geometry_is_candidate_only(direction,entry,formed):
    p,h=formulation_input(direction,entry=entry)
    assert p["strategy_assessment"]["status"]=="COMPLETE"
    before=deepcopy(p)
    r=ENGINE.analyze(p).to_dict()
    assert r["formulation_status"]==("FORMULATED" if formed else "NOT_FORMULATED")
    if not formed:
        assert r["candidate"] is None
        assert r["reason"]=="ENTRY_STOP_GEOMETRY_NOT_ADMISSIBLE"
        with pytest.raises(ValueError,match="No admissible candidate"):
            ENGINE.evaluate_validity(validity_input(p,h,formulated=r))
    assert p==before


@pytest.mark.parametrize("field",["contract","rule_version","status","reason","assessment_identity","setup_identity",
    "completion_identity","configuration_fingerprint","evaluation_boundary","knowledge_boundary","authority","execution",
    "bindings","strategy_definition","birth_boundary","status_boundary"])
def test_tampered_assessment_rejected_even_with_matching_input_copy(originals,field):
    p,h=base(originals)
    p["strategy_assessment"][field]="forged"
    p["action_formulation_input"]["strategy_assessment"]=deepcopy(p["strategy_assessment"])
    with pytest.raises(ValueError): ENGINE.analyze(p)


@pytest.mark.parametrize("field",["contract","rule_version","action_policy_definition","strategy_assessment","setup_identity",
    "completion_identity","evaluation_boundary","knowledge_boundary","formulation_status","formulated_action","reason",
    "authority","execution","formulation_identity"])
def test_complete_action_content_is_reconstructed(originals,field):
    p,h=base(originals)
    p["action_formulation"][field]="forged"
    with pytest.raises(ValueError): ENGINE.analyze(p)


@pytest.mark.parametrize("part",["assessment","action","both"])
def test_later_valid_upstream_cannot_replace_only_one_frozen_binding(originals,part):
    p,h=base(originals)
    other,_=formulation_input(at=32)
    if part in ("assessment","both"): p["strategy_assessment"]=other["strategy_assessment"]
    if part in ("action","both"): p["action_formulation"]=other["action_formulation"]
    with pytest.raises(ValueError): ENGINE.analyze(p)


@pytest.mark.parametrize("field,value",[("strategy_id","different"),("strategy_version","0.3"),("instrument","EURUSD"),
    ("direction","SHORT"),("configuration",{})])
def test_strategy_policy_mismatch(originals,field,value):
    p,h=base(originals)
    p["action_formulation_input"]["action_policy_definition"]["strategy_definition"][field]=value
    with pytest.raises(ValueError): ENGINE.analyze(p)


@pytest.mark.parametrize("role,field",[("T1","close"),("T1","timestamp"),("E1","low"),("E1","high")])
def test_bound_evidence_tampering(originals,role,field):
    p,h=base(originals)
    p["strategy_assessment"]["bindings"][role]["candle"][field]=999
    with pytest.raises(ValueError): ENGINE.analyze(p)


@pytest.mark.parametrize("bad",[None,[],{},True,"assessment"])
def test_malformed_upstream(originals,bad):
    p,h=base(originals)
    for field in ("strategy_assessment","action_formulation","action_formulation_input"):
        changed=deepcopy(p); changed[field]=bad
        with pytest.raises(ValueError): ENGINE.analyze(changed)


@pytest.mark.parametrize("seconds",[None,True,False,0,-1,1.5,"60",float("nan"),float("inf"),10**100])
def test_duration_must_be_explicit_positive_representable_seconds(originals,seconds):
    p,h=base(originals)
    p["candidate_policy_definition"]["configuration"]["entry_validity_duration_seconds"]=seconds
    with pytest.raises(ValueError): ENGINE.analyze(p)


@pytest.mark.parametrize("change",["missing_duration","extra_policy","extra_config","contract","bool_version","empty_id"])
def test_policy_schema(originals,change):
    p,h=base(originals); v=p["candidate_policy_definition"]
    if change=="missing_duration": v["configuration"]={}
    if change=="extra_policy": v["quantity"]=1
    if change=="extra_config": v["configuration"]["buffer"]=1
    if change=="contract": v["contract"]="other"
    if change=="bool_version": v["policy_version"]=True
    if change=="empty_id": v["policy_id"]=" "
    with pytest.raises(ValueError): ENGINE.analyze(p)


def test_noncomplete_upstream_is_invalid_input():
    p,h=formulation_input(at=30)
    with pytest.raises(ValueError,match="requires COMPLETE"):
        ENGINE.analyze(p)


@pytest.mark.parametrize("field",["candidate_identity","entry_reference","stop_reference","valid_from","valid_until",
    "entry_validity_duration_seconds","candidate_policy_fingerprint","upstream_formulation_fingerprint","m1_origin_fingerprint",
    "assessment_identity","formulation_identity","strategy_id","strategy_version","instrument","direction","setup_identity",
    "completion_identity","authority","execution","contract","rule_version"])
def test_candidate_terms_cannot_mutate_under_same_identity(originals,field):
    p,h=base(originals); r=ENGINE.analyze(p).to_dict()
    r["candidate"][field]="changed"
    with pytest.raises(ValueError): owner.validate_technical_candidate_formulation(r,p)


def test_forged_recomputed_hash_is_not_owner_validation(originals):
    p,h=base(originals); r=ENGINE.analyze(p).to_dict(); c=r["candidate"]
    c["entry_reference"]["value"]+=1
    c["candidate_identity"]=owner.identity("technical_candidate_",{k:v for k,v in c.items() if k!="candidate_identity"})
    with pytest.raises(ValueError): owner.validate_technical_candidate_formulation(r,p)


def test_deterministic_identity_and_duration_binding(originals):
    p,h=base(originals); r=ENGINE.analyze(p).to_dict()
    reordered={k:p[k] for k in reversed(p)}
    assert ENGINE.analyze(reordered).to_dict()==r
    p["candidate_policy_definition"]["configuration"]["entry_validity_duration_seconds"]=121
    assert ENGINE.analyze(p).to_dict()["candidate"]["candidate_identity"]!=r["candidate"]["candidate_identity"]


@pytest.mark.parametrize("direction",["LONG","SHORT"])
@pytest.mark.parametrize("at,status",[(31,"VALID"),(31.5,"VALID"),(32,"VALID"),(33,"VALID"),(33.01,"EXPIRED"),(34,"EXPIRED")])
def test_inclusive_expiry_and_empty_initial_domain(originals,direction,at,status):
    p,h=base(originals,direction); r=evaluate(p,h,at)
    assert r["status"]==status
    assert r["terminal_boundary"]==(ts(33) if status=="EXPIRED" else None)


@pytest.mark.parametrize("direction",["LONG","SHORT"])
@pytest.mark.parametrize("minute,at,status,boundary",[(31,32,"INVALIDATED",32),(32,33,"INVALIDATED",33),
    (33,34,"EXPIRED",33),(31,31.5,"VALID",None)])
def test_breach_completion_order(originals,direction,minute,at,status,boundary):
    p,h=base(originals,direction); set_breach(h,direction,minute)
    r=evaluate(p,h,at)
    assert r["status"]==status
    assert r["terminal_boundary"]==(None if boundary is None else ts(boundary))


@pytest.mark.parametrize("direction",["LONG","SHORT"])
def test_equality_does_not_breach(originals,direction):
    p,h=base(originals,direction); set_breach(h,direction,equality=True)
    assert evaluate(p,h,32)["status"]=="VALID"


def test_first_breach_wins(originals):
    p,h=base(originals); set_breach(h,"LONG",31); set_breach(h,"LONG",32)
    assert evaluate(p,h,35)["terminal_boundary"]==ts(32)


@pytest.mark.parametrize("at,expected",[(31.5,"VALID"),(31.75,"VALID"),(31.76,"EXPIRED"),(32,"EXPIRED")])
def test_crossing_candle_never_backdates_breach(originals,at,expected):
    p,h=base(originals); p["candidate_policy_definition"]=policy(45)
    set_breach(h,"LONG",31)
    r=evaluate(p,h,at)
    assert r["status"]==expected
    assert r["terminal_boundary"]==(ts(31.75) if expected=="EXPIRED" else None)


@pytest.mark.parametrize("minute,at",[(31,32),(31,34),(32,33),(32,34)])
def test_required_gaps_unknown_even_after_expiry(originals,minute,at):
    p,h=base(originals); h["M1"]=[c for c in h["M1"] if c["timestamp"]!=ts(minute)]
    r=evaluate(p,h,at)
    assert r["status"]=="UNKNOWN" and r["terminal_boundary"] is None


def test_missing_interval_not_required_until_complete(originals):
    p,h=base(originals); h["M1"]=[c for c in h["M1"] if c["timestamp"]!=ts(31)]
    assert evaluate(p,h,31.5)["status"]=="VALID"


@pytest.mark.parametrize("change",["overlap","duplicate","off_grid","conflicting_t1","conflicting_prefix","future","impossible"])
def test_malformed_or_conflicting_continuation_rejects(originals,change):
    p,h=base(originals)
    if change=="overlap": h["M1"][35]["timestamp"]=ts(31.5)
    if change=="duplicate": h["M1"].insert(35,deepcopy(h["M1"][34]))
    if change=="off_grid": h["M1"]=h["M1"][:34]+[candle(31.5,118,119,117,118)]
    if change=="conflicting_t1": h["M1"][33]["high"]=125.0
    if change=="conflicting_prefix": h["M1"][0]["high"]=120.0
    if change=="impossible": h["M1"][34]["high"]=1.0
    v=validity_input(p,h,33)
    if change=="future": v["m1_source"]=source(h["M1"],33,include_future=True)
    with pytest.raises(ValueError): ENGINE.evaluate_validity(v)


def test_missing_anchor_is_unknown(originals):
    p,h=base(originals); h["M1"]=[c for c in h["M1"] if c["timestamp"]!=ts(30)]
    assert evaluate(p,h,32)["reason"]=="MISSING_ORIGINAL_T1_ANCHOR"


@pytest.mark.parametrize("state",["INVALIDATED","EXPIRED"])
def test_unknown_resolves_without_mutating_previous_record(originals,state):
    p,h=base(originals)
    if state=="INVALIDATED": set_breach(h,"LONG",31)
    missing=deepcopy(h); missing["M1"]=[c for c in h["M1"] if c["timestamp"]!=ts(31)]
    old=evaluate(p,missing,34); before=deepcopy(old)
    assert old["status"]=="UNKNOWN"
    assert evaluate(p,h,35)["status"]==state
    assert old==before


@pytest.mark.parametrize("state",["INVALIDATED","EXPIRED"])
def test_later_gaps_and_breaches_do_not_erase_terminal_result(originals,state):
    p,h=base(originals)
    if state=="INVALIDATED": set_breach(h,"LONG",31)
    first=evaluate(p,h,34)
    set_breach(h,"LONG",35)
    h["M1"]=[c for c in h["M1"] if c["timestamp"]!=ts(34)]
    later=evaluate(p,h,40)
    assert (later["status"],later["terminal_boundary"])==(first["status"],first["terminal_boundary"])
    assert p["strategy_assessment"]["status"]=="COMPLETE"


def test_gap_before_observed_breach_prevents_claiming_first_terminal(originals):
    p,h=base(originals); set_breach(h,"LONG",32)
    h["M1"]=[c for c in h["M1"] if c["timestamp"]!=ts(31)]
    assert evaluate(p,h,34)["status"]=="UNKNOWN"


def test_frozen_upstream_and_identity_survive_current_status_changes(originals):
    p,h=base(originals); r=ENGINE.analyze(p).to_dict(); frozen=deepcopy(r)
    at_start=ENGINE.evaluate_validity(validity_input(p,h,31,r)).to_dict()
    set_breach(h,"LONG",31)
    later=ENGINE.evaluate_validity(validity_input(p,h,34,r)).to_dict()
    assert at_start["candidate_identity"]==later["candidate_identity"]==r["candidate"]["candidate_identity"]
    assert at_start["status"]=="VALID" and later["status"]=="INVALIDATED"
    assert r==frozen
    assert r["upstream_formulation"]==p["action_formulation"]


def test_valid_extension_does_not_require_equal_snapshot_ids(originals):
    p,h=base(originals); v=validity_input(p,h,33)
    assert v["m1_source"]["source_snapshot_id"]!=v["candidate_formulation"]["m1_origin_source"]["source_snapshot_id"]
    assert ENGINE.evaluate_validity(v).to_dict()["status"]=="VALID"


def test_post_t1_q1_close_is_not_a_validity_predicate(originals):
    p,h=base(originals)
    p["candidate_policy_definition"]=policy(600)
    # M1 closes below Q1=114 while remaining above E1=107. No post-T1 M5 input.
    for i,c in enumerate(h["M1"]):
        if owner.parse_timestamp(c["timestamp"])>=owner.parse_timestamp(ts(31)):
            h["M1"][i]={**c,"open":112.0,"high":113.0,"low":111.0,"close":112.0}
    h.pop("M5")
    assert evaluate(p,h,36)["status"]=="VALID"


def test_later_price_cannot_mutate_entry(originals):
    p,h=base(originals); r=ENGINE.analyze(p).to_dict()
    h["M1"][34]=candle(31,130,150,129,145)
    v=ENGINE.evaluate_validity(validity_input(p,h,32,r)).to_dict()
    assert v["candidate_identity"]==r["candidate"]["candidate_identity"]
    assert r["candidate"]["entry_reference"]["value"]==124


@pytest.mark.parametrize("field",["candidate_identity","evaluation_boundary","m1_source","status","reason","terminal_boundary",
    "contract","rule_version","authority","execution"])
def test_complete_validity_result_owner_validation(originals,field):
    p,h=base(originals); v=validity_input(p,h,34)
    r=ENGINE.evaluate_validity(v).to_dict()
    assert owner.validate_technical_candidate_validity(r,v)==r
    r[field]="tampered"
    with pytest.raises(ValueError): owner.validate_technical_candidate_validity(r,v)


def test_evidence_change_is_bound_even_if_status_same(originals):
    p,h=base(originals); v=validity_input(p,h,32); old=ENGINE.evaluate_validity(v).to_dict()
    h["M1"][34]["high"]=130.0
    changed=validity_input(p,h,32)
    assert ENGINE.evaluate_validity(changed).to_dict()["status"]==old["status"]
    with pytest.raises(ValueError): owner.validate_technical_candidate_validity(old,changed)


@pytest.mark.parametrize("change",["earlier_k","later_source","wrong_timeframe","tampered_source","empty_source"])
def test_boundary_and_source_binding(originals,change):
    p,h=base(originals); v=validity_input(p,h,32)
    if change=="earlier_k": v["evaluation_boundary"]=ts(30)
    if change=="later_source": v["m1_source"]=source(h["M1"],33)
    if change=="wrong_timeframe": v["m1_source"]=source(h["M1"],32,"M5")
    if change=="tampered_source": v["m1_source"]["source_snapshot_id"]="forged"
    if change=="empty_source":
        v["m1_source"]=source([],32)
        assert ENGINE.evaluate_validity(v).to_dict()["status"]=="UNKNOWN"
    else:
        with pytest.raises(ValueError): ENGINE.evaluate_validity(v)


def test_original_upstream_availability_cannot_be_backdated():
    p,h=formulation_input(at=32)
    with pytest.raises(ValueError,match="frozen upstream availability"):
        evaluate(p,h,31)


def test_no_account_quantity_or_execution_authority(originals):
    p,h=base(originals); r=ENGINE.analyze(p).to_dict(); v=evaluate(p,h)
    forbidden={"account_id","provider","environment","quantity","risk_percentage","balance","equity","margin","order"}
    def inspect(value):
        if isinstance(value,dict):
            assert not forbidden.intersection(value)
            for item in value.values(): inspect(item)
        elif isinstance(value,list):
            for item in value: inspect(item)
    inspect(r); inspect(v)
    for obj in (r,r["candidate"],v):
        assert obj["authority"]==dict(trade_decision=False,financial_risk=False,execution=False)
        assert obj["execution"] is False


def test_results_and_validation_returns_are_detached(originals):
    p,h=base(originals); before=deepcopy(p); r=ENGINE.analyze(p)
    original=r.to_dict(); copy=r.to_dict(); copy["candidate"]["entry_reference"]["value"]=1
    exposed=r.payload; exposed["candidate"]["direction"]="SHORT"
    checked=owner.validate_technical_candidate_formulation(r,p); checked["candidate"]=None
    p["strategy_assessment"]["status"]="changed"
    assert r.to_dict()==original
    assert original["upstream_formulation"]["strategy_assessment"]==before["strategy_assessment"]


def test_canonical_validation_distinguishes_false_from_zero(originals):
    p,h=base(originals); r=ENGINE.analyze(p).to_dict()
    r["candidate"]["authority"]["execution"]=0
    with pytest.raises(ValueError): owner.validate_technical_candidate_formulation(r,p)


@pytest.mark.parametrize("changed",["entry","stop"])
def test_genuinely_changed_owner_valid_terms_change_identity(originals,changed):
    p,h=base(originals); first=ENGINE.analyze(p).to_dict()["candidate"]
    if changed=="entry":
        other,_=formulation_input(entry=125)
    else:
        d,h=scenario(); h["M15"][4]["low"]=106.0
        action_request=action_input(d,h)
        other=dict(candidate_policy_definition=policy(),strategy_assessment=deepcopy(action_request["strategy_assessment"]),
                   action_formulation=STRATEGY_ACTION_FORMULATION.analyze(action_request).to_dict(),
                   action_formulation_input=action_request)
    second=ENGINE.analyze(other).to_dict()["candidate"]
    assert second[changed+"_reference"]["value"]!=first[changed+"_reference"]["value"]
    assert second["candidate_identity"]!=first["candidate_identity"]


def test_consistent_missing_original_post_t1_interval_can_be_supplied_later():
    d,h=scenario()
    h["M1"]=[c for c in h["M1"] if c["timestamp"]!=ts(31)]
    action_request=action_input(d,h,33)  # Strategy completed at 31, before the gap.
    p=dict(candidate_policy_definition=policy(),strategy_assessment=deepcopy(action_request["strategy_assessment"]),
           action_formulation=STRATEGY_ACTION_FORMULATION.analyze(action_request).to_dict(),action_formulation_input=action_request)
    assert evaluate(p,h,34)["status"]=="UNKNOWN"
    h["M1"].append(candle(31,118,119,106,118)); h["M1"].sort(key=lambda c:c["timestamp"])
    assert evaluate(p,h,35)["status"]=="INVALIDATED"


def test_conflicting_original_post_t1_observation_rejects():
    p,h=formulation_input(at=33)
    set_breach(h,"LONG",31)
    with pytest.raises(ValueError,match="Conflicting replacement"):
        evaluate(p,h,34)


def test_short_duration_does_not_demand_an_expiry_crossing_interval(originals):
    p,h=base(originals); p["candidate_policy_definition"]=policy(1)
    h["M1"]=[c for c in h["M1"] if owner.parse_timestamp(c["timestamp"])<owner.parse_timestamp(ts(31))]
    r=evaluate(p,h,32)
    assert r["status"]=="EXPIRED"
    assert r["terminal_boundary"]==ts(31+1/60)


def test_validity_result_is_detached_from_input_and_exposed_copies(originals):
    p,h=base(originals); v=validity_input(p,h,32); before=deepcopy(v)
    result=ENGINE.evaluate_validity(v); initial=result.to_dict()
    assert v==before
    exposed=result.payload; exposed["m1_source"]["approved_candle_history"].clear()
    checked=owner.validate_technical_candidate_validity(result,v); checked["status"]="INVALIDATED"
    v["m1_source"]["approved_candle_history"].clear()
    assert result.to_dict()==initial
