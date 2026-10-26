"""Real completed-source/producer replay; no mocked strategy or factual owners."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from ced_one.business_divisions.trading import xauusd_causal_liquidity_reversal as strategy
from ced_one.business_divisions.trading import causal_trading_policy_strategy_action_formulation as actions
from ced_one.business_divisions.trading.causal_snapshot_availability import CAUSAL_SNAPSHOT_AVAILABILITY

BASE = datetime(2026, 1, 2, tzinfo=timezone.utc)


def ts(minutes):
    return strategy.stamp(BASE + timedelta(minutes=minutes))


def candle(minutes, o, h, l, c):
    return dict(timestamp=ts(minutes), open=float(o), high=float(h), low=float(l), close=float(c))


def scenario(direction="LONG"):
    h4 = [candle(-1920 + i * 240, (h+l)/2, h, l, (h+l)/2) for i, (h, l) in enumerate(
        [(110,104), (115,106), (112,102), (118,108), (114,105), (120,110), (116,108), (119,112)])]
    h1 = [candle(-480+i*60, o,h,l,c) for i,(o,h,l,c) in enumerate([
        (112,114,110,112), (112,115,111,113), (110,113,105,110), (112,115,110,112),
        (113,116,111,113), (112,114,110,112), (112,114,104,110), (110,126,110,125)])]
    m15 = [candle(t,o,h,l,c) for t,o,h,l,c in [
        (-60,114,116,112,114), (-45,113,115,108,113), (-30,114,117,112,114),
        (-15,115,118,113,115), (0,112,114,107,112), (15,118,122,112,120),
        (30,119,121,117,119), (45,119,121,117,119)]]
    m5 = [candle(t,113,114,112,113) for t in range(-30, 65, 5)]
    m5[2] = candle(-20,113,116,112,113)
    for t, values in {15:(112,122,112,121),20:(120,122,117,120),25:(118,120,115,118)}.items():
        m5[(t+30)//5] = candle(t,*values)
    m1 = [candle(t,118,119,117,118) for t in range(-3, 65)]
    m1[33] = candle(30,118,124,118,124)
    histories = dict(H4=h4,H1=h1,M15=m15,M5=m5,M1=m1)
    if direction == "SHORT":
        for history in histories.values():
            for c in history:
                c.update(open=300-c["open"], high=300-c["low"], low=300-c["high"], close=300-c["close"])
    definition = dict(contract=strategy.DEFINITION_CONTRACT, strategy_id=strategy.STRATEGY_ID,
        strategy_version="0.2", rule_version="revision_2.1", instrument="XAUUSD", direction=direction,
        configuration=dict(history_starts={tf: h[0]["timestamp"] for tf,h in histories.items()},
            founding_start=ts(0), founding_end=ts(60),
            windows_seconds=dict(E1=1800,R1=900,K1=900,RT1=900,T1=300),
            order_block=dict(displacement_config=dict(baseline_window=2)),
            liquidity=dict(equal_level_tolerance=0.1), displacement=dict(baseline_window=2), fvg={}))
    return definition, histories


def request(definition, histories, at=31, ordinal=0):
    sources = {tf: CAUSAL_SNAPSHOT_AVAILABILITY.analyze(dict(symbol="XAUUSD",timeframe=tf,
        requested_evaluation_timestamp=ts(at),candle_history=[c for c in h if strategy.parse_timestamp(c["timestamp"]) <= BASE+timedelta(minutes=at)])).to_dict()
        for tf,h in histories.items()}
    return dict(strategy_definition=definition, sources=sources, as_of=ts(at), setup_ordinal=ordinal)


def run(definition, histories, at=31, ordinal=0):
    return strategy.XAUUSD_CAUSAL_LIQUIDITY_REVERSAL.analyze(request(definition,histories,at,ordinal)).to_dict()


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_real_mirrored_complete_chain(direction):
    d,h = scenario(direction)
    r = run(d,h)
    assert r["status"] == "COMPLETE", r
    assert r["birth_boundary"] == ts(0)
    assert set(r["bindings"]) == {"C1","CA1","P1","L1","E1","R1","B1","K1","Q1","RT1","T1"}
    assert r["bindings"]["R1"] == r["bindings"]["K1"]
    assert r["bindings"]["Q1"]["formation"]["b"] == r["bindings"]["R1"]["candle"]
    assert r["bindings"]["T1"]["available_at"] == ts(31)
    assert r["authority"] == strategy.AUTHORITY
    assert r["execution"] is False


@pytest.mark.parametrize("at,stage", [(0,"L1"),(14,"L1"),(15,"B1"),(19,"B1"),(20,"K1"),(24,"K1"),(25,"Q1"),(30,"RT1")])
def test_waiting_and_incomplete_formation(at,stage):
    d,h=scenario()
    r=run(d,h,at)
    assert r["status"] == "WAITING"
    assert list(r["bindings"])[-1] == stage


def test_birth_latest_ca1_equality_and_polling_independence():
    d,h=scenario()
    results=[run(d,h,t) for t in (0,7,20,31,40)]
    assert len({r["setup_identity"] for r in results}) == 1
    assert len({r["birth_boundary"] for r in results}) == 1
    assert len({r["assessment_identity"] for r in results}) == len(results)
    ca=results[0]["bindings"]["CA1"]
    assert ca["candle"]["timestamp"] == ts(-120)
    assert ca["available_at"] == ts(0)
    assert results[0]["bindings"]["P1"]["available_at"] == ts(0)


def test_h1_bearish_correction_is_allowed():
    d,h=scenario()
    h["H1"][1]["high"]=118.0
    owner=strategy._Replay(request(d,h))
    assert owner.facts("structure","H1",BASE)["structure_state"] == "bearish_structure"
    assert run(d,h)["status"] == "COMPLETE"


@pytest.mark.parametrize("tf,missing", [("H4",0),("H1",0),("M15",0),("M5",0),("M1",0),("M5",9),("M5",10),("M1",33)])
def test_missing_required_coverage_is_unknown(tf,missing):
    d,h=scenario()
    del h[tf][missing]
    assert run(d,h)["status"] == "UNKNOWN"


def test_shifted_extra_prefix_does_not_change_economic_identity():
    d,h=scenario()
    before=run(d,h)
    for tf,history in h.items():
        extra=deepcopy(history[0])
        extra["timestamp"]=strategy.stamp(strategy.parse_timestamp(extra["timestamp"])-strategy.VALID_TIMEFRAME_DURATIONS[tf])
        history.insert(0,extra)
    assert run(d,h) == before


def test_absent_b1_is_terminal_and_later_pivot_cannot_repair():
    d,h=scenario()
    h["M5"][2]["high"]=114.0
    r=run(d,h)
    assert (r["status"],r["reason"],r["status_boundary"]) == ("INVALIDATED","ABSENT_PRE_E1_B1",ts(15))


def test_b1_confirmation_equal_e1_occurrence_is_excluded():
    d,h=scenario()
    h["M5"][2]["high"]=114.0
    h["M5"][4]["high"]=116.0  # -10 pivot, -5 confirming candle completes at 0.
    assert run(d,h)["reason"] == "ABSENT_PRE_E1_B1"


@pytest.mark.parametrize("direction",["LONG","SHORT"])
def test_absent_fixed_q1_is_terminal(direction):
    d,h=scenario(direction)
    c=h["M5"][10]
    c["low" if direction=="LONG" else "high"]=113.0 if direction=="LONG" else 187.0
    r=run(d,h)
    assert (r["status"],r["reason"],r["status_boundary"]) == ("INVALIDATED","ABSENT_FIXED_Q1",ts(25))


def test_touch_is_not_e1_and_close_beyond_is_terminal():
    d,h=scenario()
    h["M15"][4]["low"]=108.0
    assert "E1" not in run(d,h,15)["bindings"]
    h["M15"][4].update(low=106.0,close=107.0)
    assert run(d,h)["reason"] == "L1_CLOSE_BEFORE_SWEEP"


def test_overlapping_reaction_cannot_qualify():
    d,h=scenario()
    h["M5"][8]=candle(10,112,122,112,121)  # completes with E1, starts before it.
    h["M5"][9]=candle(15,119,121,118,119)
    r=run(d,h,20)
    assert "R1" not in r["bindings"]


@pytest.mark.parametrize("stage,seconds,status",[("E1",900,"COMPLETE"),("E1",899,"EXPIRED"),
    ("R1",300,"COMPLETE"),("R1",299,"EXPIRED"),("RT1",300,"COMPLETE"),
    ("RT1",299,"EXPIRED"),("T1",60,"COMPLETE"),("T1",59,"EXPIRED")])
def test_inclusive_fixed_deadlines_and_unfinished_deadline_candles(stage,seconds,status):
    d,h=scenario()
    d["configuration"]["windows_seconds"][stage]=seconds
    assert run(d,h)["status"] == status


def test_gap_does_not_extend_deadline_or_prove_expiration():
    d,h=scenario()
    d["configuration"]["windows_seconds"]["R1"]=300
    del h["M5"][9]
    assert run(d,h)["status"] == "UNKNOWN"


def test_first_reaction_is_fixed_even_when_later_reaction_has_fvg():
    d,h=scenario()
    h["M5"][10]=candle(20,113,130,113,129)
    h["M5"][11]=candle(25,126,130,125,128)
    r=run(d,h)
    assert r["reason"] == "ABSENT_FIXED_Q1"
    assert r["bindings"]["R1"]["candle"]["timestamp"] == ts(15)


def delayed_k1():
    d,h=scenario()
    h["M5"][2]["high"]=125.0
    h["M5"][12]=candle(30,118,128,117,127)
    return d,h


def test_preeligibility_partial_fill_cannot_be_rt1():
    d,h=delayed_k1()
    r=run(d,h,35)
    assert r["bindings"]["Q1"]["eligible_at"] == ts(35)
    assert "RT1" not in r["bindings"]


def test_preeligibility_full_fill_invalidates():
    d,h=delayed_k1()
    h["M5"][11]["low"]=114.0
    assert run(d,h)["reason"] == "PRE_ELIGIBILITY_FULL_FILL"


def test_posteligibility_wick_full_fill_is_overlap_not_invalidation():
    d,h=scenario()
    h["M5"][11]["low"]=113.0
    r=run(d,h)
    assert r["status"] == "COMPLETE"
    assert r["bindings"]["RT1"]["candle"]["timestamp"] == ts(25)


def test_rt1_and_invalidation_without_order_is_unknown():
    d,h=scenario()
    h["M5"][11]=candle(25,118,120,112,113)
    assert run(d,h)["reason"] == "RT1_INVALIDATION_ORDER_UNPROVEN"


def test_whole_candle_below_q1_does_not_falsely_count_as_overlap():
    d,h=scenario()
    h["M5"][11]=candle(25,110,112,109,110)
    r=run(d,h)
    assert r["reason"] == "Q1_CLOSE_THROUGH"
    assert "RT1" not in r["bindings"]


def test_pre_rt1_trigger_is_not_reused_and_first_trigger_wins():
    d,h=scenario()
    h["M1"][32]=candle(29,118,130,118,130)
    h["M1"][33]=candle(30,118,119,117,118)
    assert run(d,h)["status"] == "WAITING"
    h["M1"][35]=candle(32,118,138,118,138)
    r=run(d,h,34)
    assert r["bindings"]["T1"]["candle"]["timestamp"] == ts(32)


def test_historical_completion_survives_later_invalidations_and_missing_bars():
    d,h=scenario()
    first=run(d,h)
    h["M5"][12]=candle(30,110,112,100,101)
    del h["M1"][40:]
    later=run(d,h,64)
    assert later["status"] == "COMPLETE"
    assert later["completion_identity"] == first["completion_identity"]
    assert later["status_boundary"] == ts(31)


def hold_after_rt1():
    d,h=scenario()
    h["M1"][33]=candle(30,118,119,117,118)
    for i,c in enumerate(h["M5"]):
        if strategy.parse_timestamp(c["timestamp"]) >= BASE+timedelta(minutes=30):
            h["M5"][i]={**c,"open":120.0,"high":121.0,"low":118.0,"close":120.0}
    d["configuration"]["windows_seconds"]["T1"]=2400
    return d,h


@pytest.mark.parametrize("direction",["LONG","SHORT"])
def test_ca1_close_invalidation(direction):
    d,h=hold_after_rt1()
    h["H1"].append(candle(0,120,122,100,103))
    if direction=="SHORT":
        d["direction"]="SHORT"
        for history in h.values():
            for c in history:
                c.update(open=300-c["open"],high=300-c["low"],low=300-c["high"],close=300-c["close"])
    r=run(d,h,60)
    assert (r["status"],r["reason"]) == ("INVALIDATED","CA1_CLOSE_THROUGH")


@pytest.mark.parametrize("last_low,reason",[(103,"OPPOSITE_H4"),(106,"UNRESOLVED_H4")])
def test_h4_lifetime(last_low,reason):
    d,h=scenario()
    for i,c in enumerate(h["H4"]):
        c["timestamp"]=ts(-2140+i*240)
    h["H4"][-1].update(high=117.0,low=float(last_low))
    h["H4"].append(candle(-220,112,116,108,112))
    d["configuration"]["history_starts"]["H4"]=ts(-2140)
    r=run(d,h)
    assert r["reason"] == reason
    assert r["status"] == ("INVALIDATED" if reason=="OPPOSITE_H4" else "UNKNOWN")


def test_terminal_tuple_is_never_reborn():
    d,h=scenario()
    d["configuration"]["windows_seconds"]["E1"]=60
    first=run(d,h,2)
    assert first["status"] == "EXPIRED"
    next_result=run(d,h,14,ordinal=1)
    assert next_result["setup_identity"] is None
    assert next_result["prior_exhausted_setups"][0]["setup_identity"] == first["setup_identity"]
    assert next_result["reason"] == "NO_NEW_FOUNDING_TUPLE"


def action_input(d,h,at=31):
    req=request(d,h,at)
    assessed=strategy.XAUUSD_CAUSAL_LIQUIDITY_REVERSAL.analyze(req).to_dict()
    policy=dict(contract=actions.DEFINITION_CONTRACT,policy_id="strategy-1",policy_version=1,
        strategy_definition=d,configuration_fingerprint=assessed["configuration_fingerprint"],
        declared_action=dict(action_type="DIRECTIONAL_ENTRY_INTENT",direction=d["direction"]))
    return dict(action_policy_definition=policy,strategy_assessment=assessed,assessment_input=req)


@pytest.mark.parametrize("at,expected",[(0,"NOT_FORMULATED"),(31,"FORMULATED")])
@pytest.mark.parametrize("direction",["LONG","SHORT"])
def test_versioned_action_is_declaration_only(at,expected,direction):
    d,h=scenario(direction)
    payload=action_input(d,h,at)
    result=actions.STRATEGY_ACTION_FORMULATION.analyze(payload).to_dict()
    assert result["formulation_status"] == expected
    assert result["formulated_action"] == (payload["action_policy_definition"]["declared_action"] if at==31 else None)
    assert result["authority"] == strategy.AUTHORITY
    assert result["execution"] is False
    assert result["completion_identity"] == payload["strategy_assessment"]["completion_identity"]


@pytest.mark.parametrize("field",["status","reason","status_boundary","birth_boundary","setup_identity",
    "completion_identity","assessment_identity","configuration_fingerprint","bindings","authority","execution",
    "evaluation_boundary","knowledge_boundary","prior_exhausted_setups","contract","rule_version","setup_ordinal","strategy_definition","factual_rules"])
def test_full_owner_reconstruction_rejects_each_tampered_field(field):
    d,h=scenario()
    payload=action_input(d,h)
    payload["strategy_assessment"][field]="forged"
    with pytest.raises(ValueError,match="reconstruction"):
        actions.STRATEGY_ACTION_FORMULATION.analyze(payload)


def test_forged_hash_and_true_equal_one_are_not_owner_proof():
    d,h=scenario()
    payload=action_input(d,h)
    r=payload["strategy_assessment"]
    r["authority"]["execution"]=0
    r["assessment_identity"]=strategy.identity("assessment_",{k:v for k,v in r.items() if k!="assessment_identity"})
    with pytest.raises(ValueError):
        actions.STRATEGY_ACTION_FORMULATION.analyze(payload)


@pytest.mark.parametrize("change",["id","version","instrument","direction","config","fingerprint","action_direction"])
def test_policy_exact_binding(change):
    d,h=scenario()
    p=action_input(d,h)
    policy=p["action_policy_definition"]
    if change in ("id","version","instrument","direction"):
        key={"id":"strategy_id","version":"strategy_version"}.get(change,change)
        policy["strategy_definition"][key]="SHORT" if change=="direction" else "different"
    elif change=="config": policy["strategy_definition"]["configuration"]["windows_seconds"]["T1"]=61
    elif change=="fingerprint": policy["configuration_fingerprint"]="forged"
    else: policy["declared_action"]["direction"]="SHORT"
    with pytest.raises(ValueError): actions.STRATEGY_ACTION_FORMULATION.analyze(p)


@pytest.mark.parametrize("change",["extra","ordinal_bool","asof","future","source_tamper","impossible","overlap","zero_window"])
def test_malformed_input_rejected(change):
    d,h=scenario()
    if change=="impossible": h["M5"][9]["high"]=1
    if change=="overlap": h["M5"][9]["timestamp"]=ts(14)
    p=request(d,h)
    if change=="extra": p["extra"]=True
    if change=="ordinal_bool": p["setup_ordinal"]=True
    if change=="asof": p["as_of"]=ts(32)
    if change=="future": p["sources"]["M1"]["approved_candle_history"][-1]["timestamp"]=ts(100)
    if change=="source_tamper": p["sources"]["M1"]["source_snapshot_id"]="bad"
    if change=="zero_window": p["strategy_definition"]["configuration"]["windows_seconds"]["T1"]=0
    with pytest.raises(ValueError): strategy.XAUUSD_CAUSAL_LIQUIDITY_REVERSAL.analyze(p)


def test_reconstruction_deterministic_and_does_not_mutate_input():
    d,h=scenario()
    p=request(d,h)
    before=deepcopy(p)
    result=strategy.XAUUSD_CAUSAL_LIQUIDITY_REVERSAL.analyze(p).to_dict()
    assert strategy.validate_strategy_assessment(result,p) == result
    assert strategy.XAUUSD_CAUSAL_LIQUIDITY_REVERSAL.analyze(p).to_dict() == result
    assert p == before


def test_new_l1_binding_can_found_distinct_setup_after_terminal():
    d,h=scenario()
    d["configuration"]["windows_seconds"]["E1"]=60
    old=run(d,h,2)
    new=run(d,h,30,ordinal=1)
    assert new["birth_boundary"] == ts(30)
    assert new["setup_identity"] != old["setup_identity"]
    assert new["bindings"]["CA1"] == old["bindings"]["CA1"]
    assert new["bindings"]["P1"] == old["bindings"]["P1"]
    assert new["bindings"]["L1"] != old["bindings"]["L1"]


def test_new_ca1_binding_can_found_distinct_setup_with_same_p1_l1():
    d,h=scenario()
    d["configuration"]["founding_end"]=ts(180)
    d["configuration"]["windows_seconds"]["E1"]=60
    h["H1"] += [candle(0,120,126,118,120),candle(60,120,125,115,120),candle(120,120,125,118,120)]
    h["M15"]=h["M15"][:4]+[candle(t,115,118,113,115) for t in range(0,180,15)]
    h["M5"]=h["M5"][:6]+[candle(t,115,118,113,115) for t in range(0,180,5)]
    h["M1"]=h["M1"][:3]+[candle(t,115,118,113,115) for t in range(0,180)]
    old=run(d,h,2)
    new=run(d,h,180,ordinal=1)
    assert new["birth_boundary"] == ts(180),new
    assert new["bindings"]["CA1"] != old["bindings"]["CA1"]
    assert new["bindings"]["P1"] == old["bindings"]["P1"]
    assert new["bindings"]["L1"] == old["bindings"]["L1"]


def test_multiple_live_single_l1_candidates_are_unknown():
    d,h=scenario()
    h["M15"]=[candle(t,114,118,low,114) for t,low in [(-120,112),(-105,108),(-90,112),(-75,113),(-60,112),(-45,109),(-30,112),(-15,113)]]+h["M15"][4:]
    d["configuration"]["history_starts"]["M15"]=ts(-120)
    assert run(d,h)["reason"] == "AMBIGUOUS_L1"


def test_l1_cluster_cannot_substitute_for_single_bound_object():
    d,h=scenario()
    h["M15"][4]["low"]=108.0  # second equal pivot forms cluster at 30.
    assert run(d,h)["reason"] == "L1_CONTINUITY_UNPROVEN"


def test_p1_and_ca1_are_not_reselected_after_birth():
    d,h=hold_after_rt1()
    before=run(d,h,0)
    h["H1"].append(candle(0,120,122,110,118))
    later=run(d,h,60)
    assert later["status"] == "WAITING"
    assert later["bindings"]["P1"] == before["bindings"]["P1"]
    assert later["bindings"]["CA1"] == before["bindings"]["CA1"]


def test_b1_immutable_and_k1_may_follow_r1():
    d,h=delayed_k1()
    r=run(d,h,35)
    assert r["bindings"]["B1"]["price"] == 125
    assert r["bindings"]["R1"]["available_at"] == ts(20)
    assert r["bindings"]["K1"]["available_at"] == ts(35)


def test_first_rt1_and_trigger_remain_fixed_under_later_events():
    d,h=scenario()
    h["M5"][12]=candle(30,118,119,114,118)
    h["M1"][34]=candle(31,118,150,118,150)
    r=run(d,h,40)
    assert r["bindings"]["RT1"]["candle"]["timestamp"] == ts(25)
    assert r["bindings"]["T1"]["candle"]["timestamp"] == ts(30)


def test_empty_owner_source_is_unknown_not_malformed():
    d,h=scenario()
    h["H1"]=[]
    assert run(d,h)["status"] == "UNKNOWN"


def test_latest_causally_available_p1_among_two_native_unvisited_blocks():
    d,h=scenario()
    h["H1"][2]=candle(-360,102,113,100,101)
    h["H1"][3]=candle(-300,101,121,101,120)
    factual=strategy._Replay(request(d,h)).facts("order_block","H1",BASE)
    assert sum(b["current_state"]=="unvisited" for b in factual["order_blocks"]) == 2
    r=run(d,h)
    assert r["status"] == "COMPLETE"
    assert r["bindings"]["P1"]["confirmation"]["timestamp"] == ts(-60)


@pytest.mark.parametrize("seconds,status",[(900,"WAITING"),(899,"EXPIRED")])
def test_delayed_k1_endpoint(seconds,status):
    d,h=delayed_k1()
    d["configuration"]["windows_seconds"]["K1"]=seconds
    assert run(d,h,35)["status"] == status


def test_exhausted_history_cannot_be_lost_to_recreate_next_setup():
    d,h=scenario()
    d["configuration"]["windows_seconds"]["E1"]=60
    del h["M1"][3]
    r=run(d,h,30,ordinal=1)
    assert r["status"] == "UNKNOWN"
    assert r["setup_identity"] is None


def test_definition_defaults_normalize_to_same_owner_result():
    d,h=scenario()
    canonical=strategy.normalize_strategy_definition(d)
    assert run(d,h) == run(canonical,h)


@pytest.mark.parametrize("value",[True,float("nan"),float("inf")])
def test_invalid_numeric_configuration(value):
    d,h=scenario()
    d["configuration"]["displacement"]["minimum_range_expansion_ratio"]=value
    with pytest.raises(ValueError): run(d,h)


def test_source_ohlc_is_in_immutable_l1_provenance():
    d,h=scenario()
    before=run(d,h,0)
    h["M15"][1]["open"]=114.0
    after=run(d,h,0)
    assert before["setup_identity"] != after["setup_identity"]


def test_completion_and_context_invalidation_same_boundary_is_unknown():
    d,h=hold_after_rt1()
    h["H1"].append(candle(0,120,122,100,103))
    h["M1"][62]=candle(59,118,130,118,130)
    assert run(d,h,60)["reason"] == "COMPLETION_INVALIDATION_ORDER_UNPROVEN"


def test_wick_through_ca1_and_p1_is_not_close_invalidation():
    d,h=hold_after_rt1()
    h["H1"].append(candle(0,120,122,100,118))
    assert run(d,h,60)["status"] == "WAITING"


def test_q1_invalidates_after_rt1_before_trigger():
    d,h=hold_after_rt1()
    h["M5"][12]=candle(30,118,119,112,113)
    r=run(d,h,35)
    assert r["reason"] == "Q1_CLOSE_THROUGH"
    assert "RT1" in r["bindings"]


def test_prior_l1_touch_is_eligible():
    d,h=scenario()
    h["M15"][3]["low"]=108.0
    assert run(d,h)["status"] == "COMPLETE"


def test_l1_confirmation_can_establish_exact_birth_boundary():
    d,h=scenario()
    h["M15"][1]["low"]=113.0
    h["M15"][3]["low"]=108.0
    h["M15"][4]["low"]=109.0
    r=run(d,h,15)
    assert r["birth_boundary"] == ts(15)
    assert r["bindings"]["L1"]["available_at"] == ts(15)


@pytest.mark.parametrize("state",["UNKNOWN","INVALIDATED","EXPIRED"])
def test_other_lifecycle_states_cannot_formulate(state):
    d,h=scenario()
    if state=="UNKNOWN": del h["M5"][9]
    if state=="INVALIDATED": h["M5"][2]["high"]=114.0
    if state=="EXPIRED": d["configuration"]["windows_seconds"]["T1"]=59
    p=action_input(d,h)
    assert p["strategy_assessment"]["status"] == state
    r=actions.STRATEGY_ACTION_FORMULATION.analyze(p).to_dict()
    assert r["formulation_status"] == "NOT_FORMULATED"
    assert r["formulated_action"] is None


def test_distinct_tuple_birth_is_not_delayed_by_an_earlier_active_setup():
    d,h=scenario()
    first=run(d,h,30)
    second=run(d,h,30,ordinal=1)
    assert first["status"] == "WAITING"
    assert second["birth_boundary"] == ts(30)
    assert second["bindings"]["L1"]["available_at"] == ts(30)
    assert second["setup_identity"] != first["setup_identity"]
    assert run(d,h,31,ordinal=1)["setup_identity"] == second["setup_identity"]


def test_policy_fingerprint_must_describe_its_own_canonical_configuration():
    d,h=scenario()
    p=action_input(d,h)
    p["action_policy_definition"]["strategy_definition"]["configuration"]["displacement"]["minimum_range_expansion_ratio"]=2
    # Reconstruct a matching numerical config, but forge a differently encoded
    # policy configuration while retaining the assessment's fingerprint.
    p["assessment_input"]["strategy_definition"]=deepcopy(p["action_policy_definition"]["strategy_definition"])
    p["strategy_assessment"]=strategy.XAUUSD_CAUSAL_LIQUIDITY_REVERSAL.analyze(p["assessment_input"]).to_dict()
    p["action_policy_definition"]["configuration_fingerprint"]=p["strategy_assessment"]["configuration_fingerprint"]
    p["action_policy_definition"]["strategy_definition"]["configuration"]["displacement"]["minimum_range_expansion_ratio"]=2.0
    with pytest.raises(ValueError,match="own effective configuration"):
        actions.STRATEGY_ACTION_FORMULATION.analyze(p)
