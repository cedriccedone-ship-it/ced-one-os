"""Real owner-backed reference research replay and fail-closed contracts."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from ced_one.business_divisions.trading import xauusd_reference_trade_management_experiment as r
from ced_one.business_divisions.trading.causal_snapshot_availability import CAUSAL_SNAPSHOT_AVAILABILITY, snapshot_identity
from tests.test_xauusd_technical_trade_candidate import formulation_input, ENGINE


@pytest.fixture(scope="module")
def owners():
    result = {}
    for direction in ("LONG", "SHORT"):
        request, _ = formulation_input(direction)
        result[direction] = (request, ENGINE.analyze(request).to_dict())
    return result


def source(candles, tf, at):
    return CAUSAL_SNAPSHOT_AVAILABILITY.analyze(dict(symbol="XAUUSD", timeframe=tf,
        requested_evaluation_timestamp=r._stamp(at), candle_history=candles)).to_dict()


def sample(owners, variant="A", bars=None, direction="LONG", m5=None):
    inp, formulation = deepcopy(owners[direction])
    c = formulation["candidate"]
    t = r._time(c["valid_from"])
    e = Fraction(repr(c["entry_reference"]["value"]))
    s = 1 if direction == "LONG" else -1
    risk = abs(e - Fraction(repr(c["stop_reference"]["value"])))
    def candle(minute, values):
        # Input tuples are opening, favorable extreme, adverse extreme, close in R.
        o, f, a, close = [float(e + s * risk * Fraction(str(x))) for x in values]
        return dict(timestamp=r._stamp(t + timedelta(minutes=minute)), open=o, high=max(f, a), low=min(f, a), close=close)
    bars = [(0, .5, -.5, 0)] if bars is None else bars
    rows = [deepcopy(c["entry_reference"]["evidence"]["candle"])]
    rows += [candle(i, values) for i, values in enumerate(bars) if values is not None]
    h = t + timedelta(minutes=1440)
    m5_rows = [] if m5 is None else [candle(i, v) for i, v in m5]
    req = dict(contract=r.SCENARIO_CONTRACT, rule_version=r.RULE_VERSION, variant=variant,
               candidate_formulation=formulation, formulation_input=inp, research_boundary=r._stamp(h),
               evidence=dict(m1=source(rows, "M1", h), m5=source(m5_rows, "M5", h) if variant == "E" and m5 is not None else None, declarations=[]))
    bind(req, m5_anchor=t)
    return req


def bind(req, m5_anchor=None):
    t = r._time(req["candidate_formulation"]["candidate"]["valid_from"])
    h = t + timedelta(minutes=1440)
    def declaration(kind, tfs):
        sources = {tf: req["evidence"][tf.lower()] for tf in tfs}
        bindings = {tf.lower(): r._source_ref(s) for tf, s in sources.items()}
        if kind == r.BASE_RELATIONSHIP:
            bindings["candidate_origin"] = r._origin_ref(req["candidate_formulation"], req["formulation_input"])
        return dict(contract=r.DATASET_RELATIONSHIP_CONTRACT, rule_version=r.RELATIONSHIP_RULE_VERSION,
            declaration_id="base" if kind == r.BASE_RELATIONSHIP else "m5", declaration_revision=1,
            relationship_type=kind, source_namespace="research-fixture", dataset_revision="dataset-1", price_domain="reference-prices",
            available_at=r._stamp(t), subject_bindings=bindings,
            timeframe_grid_bindings={tf: dict(timeframe=tf, anchor_open=r._stamp(m5_anchor or t), duration_seconds=60 if tf == "M1" else 300) for tf in tfs},
            coverage_declarations={tf: dict(requested_start=r._stamp(t-timedelta(minutes=10)), requested_end=r._stamp(h),
                declared_coverage_start=r._stamp(t-timedelta(minutes=10)), declared_coverage_end=r._stamp(h), dataset_end=None) for tf in tfs},
            declaration_provenance=dict(declarant_namespace="fixture", record_id="record-"+kind), authority=deepcopy(r._DECL_AUTHORITY))
    req["evidence"]["declarations"] = [declaration(r.BASE_RELATIONSHIP, ["M1"])]
    if req["evidence"]["m5"] is not None:
        req["evidence"]["declarations"].append(declaration(r.M5_RELATIONSHIP, ["M1", "M5"]))
    return req


def run(req):
    return r.evaluate_reference_scenario(req)


def outcome(req, status, mechanism=None):
    result = run(req)
    assert result["completion_status"] == status
    if mechanism:
        assert mechanism in result["terminal_mechanisms"]
    return result


def refresh_source(req, tf="m1"):
    src = req["evidence"][tf]
    src["source_snapshot_id"] = snapshot_identity(src)
    src["evidence"]["source_snapshot_id"] = src["source_snapshot_id"]
    for d in req["evidence"]["declarations"]:
        if tf in d["subject_bindings"]:
            d["subject_bindings"][tf] = r._source_ref(src)


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
@pytest.mark.parametrize("bars,mechanism,expected", [
    ([(0,.5,-1,0)], "INITIAL_RISK_STOP", -1),
    ([(0,3,-.5,0)], "FINAL_TARGET", 3),
    ([(-1.5,.5,-2,0)], "INITIAL_RISK_STOP", Fraction(-3,2)),
    ([(3.5,4,-2,0)], "FINAL_TARGET", Fraction(7,2)),
])
def test_a_terminals_and_opening_precedence(owners,direction,bars,mechanism,expected):
    out = outcome(sample(owners,bars=bars,direction=direction), "RESOLVED", mechanism)
    assert r._fraction(out["terminal_alternatives"][0]["reference_r"]) == expected
    assert out["terms"]["original_r"] == "17"


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_ambiguity_exact_bounds_and_terminal_excursions(owners,direction):
    out = outcome(sample(owners,bars=[(0,4,-2,0)],direction=direction), "AMBIGUOUS")
    assert len(out["terminal_alternatives"]) == 2
    stop, target = out["terminal_alternatives"]
    assert r._fraction(stop["reference_r"]) == -1
    assert r._fraction(target["reference_r"]) == 3
    assert r._fraction(stop["excursion_lower_bounds"]["mae_r"]) == 1
    assert r._fraction(target["excursion_lower_bounds"]["mfe_r"]) == 3
    assert stop["path_condition"]["candle_sha256"] == target["candle_sha256"]


@pytest.mark.parametrize("variant", ["B","C","D","E"])
def test_old_stop_cannot_be_retroactively_protected(owners,variant):
    out = outcome(sample(owners,variant,bars=[(0,2.5,-1,0)]), "RESOLVED", "INITIAL_RISK_STOP")
    assert not out["transitions"]


@pytest.mark.parametrize("variant,stage", [("B",1),("C",2)])
def test_simultaneous_milestones_highest_stage(owners,variant,stage):
    req=sample(owners,variant,bars=[(0,2.5,-.5,1.5),(1.5,2.5,0,1)])
    out=outcome(req,"RESOLVED", "BREAK_EVEN_STOP" if stage==1 else "PROTECTED_PROFIT_STOP")
    assert out["transitions"][0]["to_stage"]==stage
    assert out["transitions"][0]["active_from_open"]==out["transitions"][0]["established_at"]


@pytest.mark.parametrize("opening", [0,1.5])
def test_b_opening_milestone_established_at_completion_and_adverse_be_gap(owners,opening):
    req=sample(owners,"B",bars=[(opening,2,-.5,1),(-.5,.5,-.75,0)])
    out=outcome(req,"RESOLVED","BREAK_EVEN_STOP")
    assert r._fraction(out["terminal_alternatives"][0]["reference_r"])==Fraction(-1,2)
    assert out["final_state"]["first_1r"]==r._stamp(r._time(out["terms"]["T"])+timedelta(minutes=1))


def test_c_separate_stages_and_final_target(owners):
    out=outcome(sample(owners,"C",bars=[(0,1.5,-.5,1),(1,2.5,.5,2),(2,3,1.5,2)]),"RESOLVED","FINAL_TARGET")
    assert [x["to_stage"] for x in out["transitions"]]==[1,2]


@pytest.mark.parametrize("direction", ["LONG","SHORT"])
def test_d_strict_pivot_and_catchup(owners,direction):
    out=outcome(sample(owners,"D",direction=direction,bars=[(0,2.5,-.25,1),(1,2,-.5,1),(1,2,-.25,1),(1,2,0,1)]),"RESOLVED","PROTECTED_PROFIT_STOP")
    assert out["transitions"][0]["to_stage"]==2
    assert out["gate_evidence"]["center_open"]==r._stamp(r._time(out["terms"]["T"])+timedelta(minutes=1))
    assert out["transitions"][0]["established_at"]==r._stamp(r._time(out["terms"]["T"])+timedelta(minutes=3))


@pytest.mark.parametrize("first", [2,3])
def test_d_before_or_equal_confirmation_is_not_reused(owners,first):
    bars=[(0,.5,-.25,0),(0,.5,-.5,0),(0,.5,-.25,0),(0,.5,-.25,0)]
    bars[first]=(0,1.5,-.25,0)
    out=outcome(sample(owners,"D",bars=bars),"MISSING_DATA_CENSORED")
    assert not out["transitions"] and not out["final_state"]["gate_open"]


def test_d_later_qualifying_pivot(owners):
    bars=[(0,.5,-.25,0),(0,.5,-.5,0),(0,1.5,-.25,0),(0,.5,-.5,0),(0,.5,-.25,0),(0,.5,-.25,0)]
    out=outcome(sample(owners,"D",bars=bars),"RESOLVED","BREAK_EVEN_STOP")
    assert out["transitions"][0]["established_at"]==r._stamp(r._time(out["terms"]["T"])+timedelta(minutes=5))


@pytest.mark.parametrize("relation", [True,False])
def test_e_gate_or_dependency_censor(owners,relation):
    bars=[(0,2.5,-.5,1)]+[(1,2.5,-.5,1)]*14+[(1,2,0,1)]
    m5=[(-5,(0,1,-.25,0)),(0,(0,1,-.25,0)),(5,(0,1,-.5,0)),(10,(0,1,-.25,0))]
    req=sample(owners,"E",bars=bars,m5=m5)
    if not relation: req["evidence"]["declarations"]=req["evidence"]["declarations"][:1]
    out=run(req)
    if relation:
        assert out["completion_status"]=="RESOLVED"
        assert out["terminal_mechanisms"]==["PROTECTED_PROFIT_STOP"]
        assert out["gate_evidence"]["timeframe"]=="M5"
    else:
        assert out["completion_reason"]=="MISSING_CONSEQUENTIAL_M5_GATE_EVIDENCE"
        assert out["completion_boundary"]==r._stamp(r._time(out["terms"]["T"])+timedelta(minutes=10))


def test_e_terminal_before_missing_relationship_matters(owners):
    outcome(sample(owners,"E",bars=[(0,3,-.5,0)]),"RESOLVED","FINAL_TARGET")


def test_missing_base_relationship_and_later_cannot_repair(owners):
    for available in (None,2):
        req=sample(owners,bars=[(0,3,-.5,0)])
        if available is None: req["evidence"]["declarations"]=[]
        else: req["evidence"]["declarations"][0]["available_at"]=r._stamp(r._time(req["candidate_formulation"]["candidate"]["valid_from"])+timedelta(minutes=available))
        out=outcome(req,"MISSING_DATA_CENSORED")
        assert out["reference_result"] is None
        assert out["completion_reason"]=="MISSING_CANDIDATE_M1_RELATIONSHIP"


@pytest.mark.parametrize("offset", [-1,0,1])
def test_base_availability_before_or_at_dependency(owners,offset):
    req=sample(owners,bars=[(0,3,-.5,0)])
    req["evidence"]["declarations"][0]["available_at"]=r._stamp(r._time(req["candidate_formulation"]["candidate"]["valid_from"])+timedelta(minutes=offset))
    outcome(req,"RESOLVED")


def test_missing_interval_not_dataset_end_and_prefix_excursions(owners):
    out=outcome(sample(owners,bars=[(0,.75,-.5,0),None,(0,3,-.5,0)]),"MISSING_DATA_CENSORED")
    assert r._fraction(out["observed_prefix_excursions"]["mfe_r"])==Fraction(3,4)
    assert out["reference_result"] is None


def test_declared_dataset_end(owners):
    req=sample(owners)
    req["evidence"]["declarations"][0]["coverage_declarations"]["M1"]["dataset_end"]=r._stamp(r._time(req["candidate_formulation"]["candidate"]["valid_from"])+timedelta(minutes=1))
    outcome(req,"END_OF_DATA_UNRESOLVED")


@pytest.mark.parametrize("terminal", [False,True])
def test_horizon_and_final_interval(owners,terminal):
    bars=[(0,.5,-.5,0)]*1440
    if terminal: bars[-1]=(0,3,-.5,0)
    # A supplied interval at H is never scanned.
    req=sample(owners,bars=bars)
    out=outcome(req,"RESOLVED" if terminal else "HORIZON_CENSORED")
    assert out["completion_boundary"]==out["terms"]["H"]
    assert bool(out["terminal_alternatives"])==terminal


@pytest.mark.parametrize("value", [True,float("nan"),float("inf"),"124",Decimal("124")])
def test_unsupported_numeric_observation(owners,value):
    req=sample(owners)
    req["evidence"]["m1"]["approved_candle_history"][-1]["close"]=value
    with pytest.raises((ValueError,TypeError)):
        refresh_source(req)
        run(req)


def test_numeric_subclass_rejected():
    class Number(int): pass
    with pytest.raises(ValueError): r._price(Number(1))


@pytest.mark.parametrize("value,expected", [(1,Fraction(1)),(.1,Fraction(1,10)),(1e-8,Fraction(1,100000000)),(10**30,Fraction(10**30))])
def test_exact_numeric_helper_and_context_independence(value,expected):
    with localcontext() as context:
        context.prec=2
        assert r._price(value)==expected
        assert Fraction(r._decimal(expected))==expected
    assert r._ratio(Fraction(2,6))==dict(numerator=1,denominator=3)
    assert r._ratio(0)==dict(numerator=0,denominator=1)
    assert r._ratio(None) is None


def test_int_source_and_exact_ohlc_revalidation(owners):
    req=sample(owners,bars=[(0,3,-1,0)])
    for row in req["evidence"]["m1"]["approved_candle_history"]:
        for field in ("open","high","low","close"): row[field]=int(row[field])
    # Preserve frozen anchor raw representation; mutate only the research candle.
    req["evidence"]["m1"]["approved_candle_history"][0]=deepcopy(req["candidate_formulation"]["candidate"]["entry_reference"]["evidence"]["candle"])
    refresh_source(req)
    outcome(req,"AMBIGUOUS")
    row=req["evidence"]["m1"]["approved_candle_history"][-1]
    row.update(open=10**20+1,close=10**20+1,high=10**20,low=10**20)
    refresh_source(req)
    with pytest.raises(ValueError,match="exact OHLC"): run(req)


@pytest.mark.parametrize("field", ["candidate_identity","full_artifact_sha256","reconstruction_input_sha256","price_references"])
def test_wrong_candidate_binding(owners,field):
    req=sample(owners)
    req["evidence"]["declarations"][0]["subject_bindings"]["candidate_origin"][field]="wrong"
    with pytest.raises(ValueError,match="subject"): run(req)


@pytest.mark.parametrize("field", ["full_artifact_sha256","source_snapshot_id","timeframe","symbol"])
def test_wrong_source_binding(owners,field):
    req=sample(owners)
    req["evidence"]["declarations"][0]["subject_bindings"]["m1"][field]="wrong"
    with pytest.raises(ValueError,match="subject"): run(req)


@pytest.mark.parametrize("field", ["price_domain","dataset_revision","source_namespace"])
def test_conflicting_relationship_descriptor(owners,field):
    req=sample(owners)
    d=deepcopy(req["evidence"]["declarations"][0]);d["declaration_id"]="other";d[field]="other"
    req["evidence"]["declarations"].append(d)
    with pytest.raises(ValueError,match="Conflicting"): run(req)


def test_duplicate_collapse_distinct_provenance_and_order(owners):
    req=sample(owners,bars=[(0,3,-.5,0)])
    baseline=run(req)
    req["evidence"]["declarations"]*=2
    assert run(req)==baseline
    d=deepcopy(req["evidence"]["declarations"][0]);d["declaration_provenance"]["declarant_namespace"]="other"
    req["evidence"]["declarations"].append(d)
    result=run(req)
    assert result["scenario_identity"]!=baseline["scenario_identity"]
    req["evidence"]["declarations"].reverse()
    assert run(req)==result


def test_conflicting_same_revision(owners):
    req=sample(owners)
    d=deepcopy(req["evidence"]["declarations"][0]);d["declaration_provenance"]["record_id"]="other"
    req["evidence"]["declarations"].append(d)
    with pytest.raises(ValueError,match="revision"): run(req)


def test_equivalent_grid_normalization(owners):
    req=sample(owners)
    baseline=run(req)
    g=req["evidence"]["declarations"][0]["timeframe_grid_bindings"]["M1"]
    g["anchor_open"]=r._stamp(r._time(g["anchor_open"])+timedelta(minutes=7))
    assert run(req)==baseline


@pytest.mark.parametrize("mutation", ["post_boundary","authority","endpoint","grid","extra","revision_bool","provenance"])
def test_malformed_declarations_even_after_terminal(owners,mutation):
    req=sample(owners,bars=[(0,3,-.5,0)])
    d=req["evidence"]["declarations"][0]
    if mutation=="post_boundary": d["available_at"]=r._stamp(r._time(req["research_boundary"])+timedelta(seconds=1))
    elif mutation=="authority": d["authority"]["execution"]=True
    elif mutation=="endpoint": d["coverage_declarations"]["M1"]["dataset_end"]=req["candidate_formulation"]["candidate"]["valid_from"]
    elif mutation=="grid": d["timeframe_grid_bindings"]["M1"]["anchor_open"]=r._stamp(r._time(d["available_at"])+timedelta(seconds=1))
    elif mutation=="extra": d["extra"]=1
    elif mutation=="revision_bool": d["declaration_revision"]=True
    else: d["declaration_provenance"]={}
    with pytest.raises(ValueError): run(req)


def aggregate(owners,bars=None):
    requests=[sample(owners,v,bars=bars) for v in r._VARIANTS]
    rows=[dict(request=q,assessment=run(q)) for q in requests]
    return dict(contract=r.AGGREGATE_CONTRACT,rule_version=r.RULE_VERSION,cohort=[rows[0]["assessment"]["candidate_identity"]],scenarios=rows,partitions=[])


def test_complete_matrix_reconstruction_metrics_identity(owners):
    req=aggregate(owners,bars=[(0,3,-.5,0)])
    out=r.aggregate_reference_experiment(req)
    assert r.validate_reference_experiment(out,req)==out
    assert out["metrics"]["A"]["resolved_subset_mean_r"]==r._ratio(3)
    assert out["metrics"]["A"]["resolved_coverage"]==r._ratio(1)
    req["scenarios"].reverse()
    assert r.aggregate_reference_experiment(req)==out
    out["metrics"]["A"]["total_cohort"]=2
    with pytest.raises(ValueError): r.validate_reference_experiment(out,req)


@pytest.mark.parametrize("mutation", ["missing","duplicate","m1","base","tamper"])
def test_matrix_fail_closed(owners,mutation):
    req=aggregate(owners,bars=[(0,3,-.5,0)])
    if mutation=="missing": req["scenarios"].pop()
    elif mutation=="duplicate": req["scenarios"].append(deepcopy(req["scenarios"][0]))
    elif mutation=="tamper": req["scenarios"][0]["assessment"]["completion_reason"]="forged"
    else:
        item=req["scenarios"][1]
        if mutation=="base": item["request"]["evidence"]["declarations"][0]["declaration_provenance"]["record_id"]="other"
        else:
            item["request"]["evidence"]["m1"]["approved_candle_history"][-1]["high"]+=1
            refresh_source(item["request"])
        item["assessment"]=run(item["request"])
    with pytest.raises(ValueError): r.aggregate_reference_experiment(req)


def test_paired_nested_stop_compatibility(owners):
    req=aggregate(owners,bars=[(0,1.5,-.5,1),(1,3,-1,1)])
    out=r.aggregate_reference_experiment(req)
    pairs=out["paired_against_a"]["B"]["comparisons"][0]["compatible_alternative_pairs"]
    assert len(pairs)==3
    assert not any(p["baseline"]["mechanism"]=="INITIAL_RISK_STOP" and p["comparison"]["mechanism"]=="FINAL_TARGET" for p in pairs)
    assert out["metrics"]["A"]["resolved_subset_mean_r"] is None
    assert out["metrics"]["A"]["full_cohort_terminal_mean_bounds"]==dict(lower=r._ratio(-1),upper=r._ratio(3))


def test_equal_stops_require_equal_path(owners):
    out=r.aggregate_reference_experiment(aggregate(owners,bars=[(0,3,-1,0)]))
    pairs=out["paired_against_a"]["B"]["comparisons"][0]["compatible_alternative_pairs"]
    assert len(pairs)==2


def test_censoring_not_zero_or_loss_avoidance(owners):
    out=r.aggregate_reference_experiment(aggregate(owners))
    assert out["metrics"]["A"]["resolved_subset_mean_r"] is None
    assert out["metrics"]["A"]["full_cohort_terminal_mean_bounds"] is None
    assert out["paired_against_a"]["B"]["jointly_assessable_count"]==0
    assert out["paired_against_a"]["B"]["comparisons"][0]["economic_loss_avoided"]=="INDETERMINATE"


@pytest.mark.parametrize("offset,eligible", [(0,True),(-1,False)])
def test_partition_horizon_selection_and_half_open(owners,offset,eligible):
    req=aggregate(owners,bars=[(0,3,-.5,0)])
    terms=req["scenarios"][0]["assessment"]["terms"]
    req["partitions"]=[dict(partition_id="test",entry_start_inclusive=terms["T"],entry_end_exclusive=terms["H"],selection_boundary=r._stamp(r._time(terms["H"])+timedelta(seconds=offset)))]
    out=r.aggregate_reference_experiment(req)
    assert bool(out["partitions"][0]["selection_eligible_cohort"]["A"])==eligible
    req["partitions"][0]["entry_end_exclusive"]=terms["T"]
    with pytest.raises(ValueError): r.aggregate_reference_experiment(req)


def test_tied_drawdown_mean_median_exact():
    def row(value,at):
        return dict(completion_status="RESOLVED",terminal_mechanisms=["INITIAL_RISK_STOP"],terminal_alternatives=[dict(reference_r=r._ratio(value),excursion_lower_bounds=r._excursion_output(Fraction(0),Fraction(0),Fraction(1)))],completion_boundary=at,reference_result=dict(lower_r=r._ratio(value),upper_r=r._ratio(value)))
    at="2026-01-01T00:00:00Z"
    out=r._summary([row(-1,at),row(3,at)])
    assert out["drawdown"]["value_r"]==r._ratio(0)
    assert out["resolved_subset_mean_r"]==r._ratio(1)
    assert out["median_resolved_r"]==r._ratio(1)


def test_candidate_reconstruction_mismatch(owners):
    req=sample(owners)
    req["candidate_formulation"]["candidate"]["stop_reference"]["value"]+=1
    with pytest.raises(ValueError): run(req)


@pytest.mark.parametrize("direction", ["LONG","SHORT"])
def test_strict_pivot_exact_integer_ordering(direction):
    at=r._time("2026-01-01T00:00:00Z")
    n=10**30
    key="low" if direction=="LONG" else "high"
    center=n-1 if direction=="LONG" else n+1
    rows={at+timedelta(minutes=i): {key:Fraction(v)} for i,v in [(-1,n),(0,center),(1,n)]}
    assert r._pivot(rows,at,timedelta(minutes=1),direction=="LONG") is True
    rows[at][key]=Fraction(n)
    assert r._pivot(rows,at,timedelta(minutes=1),direction=="LONG") is False


@pytest.mark.parametrize("missing,center,right,expected", [
    (True,1,2,None),(True,2,1,False),(False,1,2,True),(False,2,2,False),
])
def test_missing_structural_neighbor_only_if_consequential(missing,center,right,expected):
    at=r._time("2026-01-01T00:00:00Z")
    rows={at:{"low":Fraction(center)},at+timedelta(minutes=1):{"low":Fraction(right)}}
    if not missing: rows[at-timedelta(minutes=1)]={"low":Fraction(3)}
    assert r._pivot(rows,at,timedelta(minutes=1),True) is expected


@pytest.mark.parametrize("case", ["missing_possible","missing_irrelevant","complete_no_pivot","gate_open","endpoint"])
def test_e_structural_coverage_cases(owners,case):
    bars=[(0,1.5,-.5,1)]+[(1,1.5,-.5,1)]*15
    m5=[(-5,(0,1,-.25,0)),(0,(0,1,-.5,0)),(5,(0,1,-.25,0))]
    if case=="missing_possible": m5=m5[1:]
    if case=="missing_irrelevant": m5=[(0,(0,1,-.25,0)),(5,(0,1,-.5,0)),(10,(0,1,-.25,0))]
    if case=="complete_no_pivot": m5=[(i,(0,1,-.25,0)) for i in (-5,0,5,10)]
    if case=="gate_open": bars=bars[:10]+[(1,1.5,.5,1)]*10+[(0,1,-.5,0)]
    if case=="endpoint": m5=m5[:2]
    req=sample(owners,"E",bars=bars,m5=m5)
    if case=="endpoint":
        req["evidence"]["declarations"][1]["coverage_declarations"]["M5"]["dataset_end"]=r._stamp(r._time(req["candidate_formulation"]["candidate"]["valid_from"])+timedelta(minutes=5))
    out=run(req)
    if case=="missing_possible":
        assert out["completion_status"]=="MISSING_DATA_CENSORED"
        assert out["completion_reason"]=="MISSING_CONSEQUENTIAL_M5_GATE_EVIDENCE"
    elif case=="endpoint": assert out["completion_status"]=="END_OF_DATA_UNRESOLVED"
    elif case=="complete_no_pivot":
        assert not out["final_state"]["gate_open"]
        assert out["completion_reason"]=="MISSING_REQUIRED_M1_EVIDENCE"
    else:
        assert out["final_state"]["gate_open"]
        assert out["completion_status"]=="RESOLVED"


@pytest.mark.parametrize("delay,opened", [(9,True),(10,True),(11,False)])
def test_e_relationship_availability_at_first_dependency(owners,delay,opened):
    bars=[(0,1.5,-.5,1)]+[(1,1.5,-.5,1)]*10
    m5=[(-5,(0,1,-.25,0)),(0,(0,1,-.5,0)),(5,(0,1,-.25,0))]
    req=sample(owners,"E",bars=bars,m5=m5)
    t=r._time(req["candidate_formulation"]["candidate"]["valid_from"])
    req["evidence"]["declarations"][1]["available_at"]=r._stamp(t+timedelta(minutes=delay))
    out=run(req)
    assert out["final_state"]["gate_open"]==opened
    assert out["completion_status"]==("RESOLVED" if opened else "MISSING_DATA_CENSORED")


@pytest.mark.parametrize("kind", ["m5_binding","shared_m1","lineage","grid"])
def test_e_relationship_contradictions(owners,kind):
    req=sample(owners,"E",m5=[(-5,(0,1,-.25,0)),(0,(0,1,-.5,0)),(5,(0,1,-.25,0))])
    d=req["evidence"]["declarations"][1]
    if kind=="m5_binding": d["subject_bindings"]["m5"]["full_artifact_sha256"]="bad"
    elif kind=="shared_m1": d["subject_bindings"]["m1"]["full_artifact_sha256"]="bad"
    elif kind=="lineage": d["dataset_revision"]="different"
    else: d["timeframe_grid_bindings"]["M5"]["anchor_open"]=r._stamp(r._time(d["available_at"])+timedelta(seconds=30))
    with pytest.raises(ValueError): run(req)


def test_incomplete_m5_not_admitted_and_non_modulo_five_grid(owners):
    req=sample(owners,"E",bars=[(0,1.5,-.5,1)]+[(1,1.5,-.5,1)]*11,
        m5=[(-5,(0,1,-.25,0)),(0,(0,1,-.5,0)),(5,(0,1,-.25,0))])
    t=r._time(req["candidate_formulation"]["candidate"]["valid_from"])
    assert t.minute%5==1
    candles=req["evidence"]["m5"]["approved_candle_history"]
    req["evidence"]["m5"]=source(candles,"M5",t+timedelta(minutes=9))
    bind(req)
    out=run(req)
    assert out["completion_reason"]=="MISSING_CONSEQUENTIAL_M5_GATE_EVIDENCE"
    assert not out["gate_evidence"]


def test_pre_entry_pivot_center_is_ineligible(owners):
    req=sample(owners,"E",bars=[(0,1.5,-.5,1)]+[(1,1.5,-.5,1)]*15,
        m5=[(-10,(0,1,-.25,0)),(-5,(0,1,-.5,0)),(0,(0,1,-.25,0)),(5,(0,1,-.25,0)),(10,(0,1,-.25,0))])
    out=run(req)
    assert not out["final_state"]["gate_open"]


def test_e_equal_confirmation_not_reused_later_pivot_qualifies(owners):
    bars=[(0,.5,-.25,0)]*9+[(0,1.5,-.25,0)]+[(0,.5,-.25,0)]*10+[(0,.5,-.25,0)]
    m5=[(-5,(0,1,-.25,0)),(0,(0,1,-.5,0)),(5,(0,1,-.25,0)),(10,(0,1,-.5,0)),(15,(0,1,-.25,0))]
    out=run(sample(owners,"E",bars=bars,m5=m5))
    t=r._time(out["terms"]["T"])
    assert out["gate_evidence"]["confirmation_completion"]==r._stamp(t+timedelta(minutes=20))
    assert out["completion_status"]=="RESOLVED"


def test_interval_opening_at_h_is_not_evaluated(owners):
    req=sample(owners,bars=[(0,.5,-.5,0)]*1440)
    t=r._time(req["candidate_formulation"]["candidate"]["valid_from"])
    h=t+timedelta(minutes=1440)
    rows=req["evidence"]["m1"]["approved_candle_history"]
    rows.append(dict(timestamp=r._stamp(h),open=1,low=1,high=500,close=124))
    req["research_boundary"]=r._stamp(h+timedelta(minutes=1))
    req["evidence"]["m1"]=source(rows,"M1",h+timedelta(minutes=1))
    bind(req)
    req["evidence"]["declarations"][0]["coverage_declarations"]["M1"]["declared_coverage_end"]=r._stamp(h+timedelta(minutes=1))
    out=outcome(req,"HORIZON_CENSORED")
    assert out["coverage"]["last_processed_completion"]==r._stamp(h)


def test_t1_is_not_post_entry_and_missing_first_candle_not_skipped(owners):
    req=sample(owners,bars=[None,(0,3,-.5,0)])
    out=outcome(req,"MISSING_DATA_CENSORED")
    assert out["coverage"]["last_processed_completion"] is None
    assert out["terminal_mechanisms"]==["NONE"]


@pytest.mark.parametrize("mutation", ["symbol","offgrid","duplicate","ohlc","frozen_anchor"])
def test_bad_sources_reject(owners,mutation):
    req=sample(owners,bars=[(0,3,-.5,0)])
    src=req["evidence"]["m1"]
    if mutation=="symbol": src["symbol"]="EURUSD"
    elif mutation=="offgrid":
        src["approved_candle_history"][-1]["timestamp"]=r._stamp(r._time(src["approved_candle_history"][-1]["timestamp"])+timedelta(seconds=1))
    elif mutation=="duplicate": src["approved_candle_history"].append(deepcopy(src["approved_candle_history"][-1]))
    elif mutation=="ohlc": src["approved_candle_history"][-1]["high"]=1
    else: src["approved_candle_history"][0]["high"]+=1
    refresh_source(req)
    with pytest.raises(ValueError): run(req)


def test_selection_rejects_later_available_evidence_even_when_horizon_mature(owners):
    req=aggregate(owners,bars=[(0,3,-.5,0)])
    terms=req["scenarios"][0]["assessment"]["terms"]
    h=r._time(terms["H"])
    for item in req["scenarios"]:
        q=item["request"]
        q["research_boundary"]=r._stamp(h+timedelta(minutes=1))
        late=deepcopy(q["evidence"]["declarations"][0])
        late["declaration_id"]="late"
        late["available_at"]=r._stamp(h+timedelta(minutes=1))
        q["evidence"]["declarations"].append(late)
        item["assessment"]=run(q)
    req["partitions"]=[dict(partition_id="train",entry_start_inclusive=terms["T"],entry_end_exclusive=terms["H"],selection_boundary=terms["H"])]
    out=r.aggregate_reference_experiment(req)
    assert out["partitions"][0]["descriptive_cohort"]
    assert out["partitions"][0]["selection_eligible_cohort"]["A"]==[]


@pytest.mark.parametrize("field", ["variant","completion_reason","terminal_alternatives","transitions","authority"])
def test_detached_scenario_tampering(owners,field):
    req=sample(owners,bars=[(0,3,-.5,0)])
    out=run(req)
    out[field]="forged"
    with pytest.raises(ValueError): r.validate_reference_scenario(out,req)


def test_request_not_mutated_and_raw_float_provenance_preserved(owners):
    req=sample(owners,bars=[(0,3,-.5,0)])
    before=deepcopy(req)
    out=run(req)
    assert req==before
    assert r.validate_reference_scenario(out,req)==out
    assert type(out["reconstruction"]["evidence"]["m1"]["approved_candle_history"][-1]["open"]) is float
    assert out["terms"]["entry"]=="124"


def test_unbound_m5_still_rejects_impossible_chronology(owners):
    req=sample(owners,"E",m5=[(0,(0,1,-.25,0)),(1,(0,1,-.5,0))])
    req["evidence"]["declarations"]=req["evidence"]["declarations"][:1]
    with pytest.raises(ValueError,match="chronology"): run(req)


def test_identity_changes_for_variant_and_censor_reason(owners):
    req=sample(owners)
    a=run(req)
    req["variant"]="B"
    b=run(req)
    assert a["scenario_identity"]!=b["scenario_identity"]
    req["evidence"]["declarations"]=[]
    c=run(req)
    assert c["completion_reason"]!=b["completion_reason"]
    assert c["scenario_identity"]!=b["scenario_identity"]


@pytest.mark.parametrize("field", ["declaration_id","dataset_revision","source_namespace","price_domain"])
def test_significant_declaration_fields_change_identity(owners,field):
    req=sample(owners)
    baseline=run(req)
    req["evidence"]["declarations"][0][field]+="-other"
    assert run(req)["scenario_identity"]!=baseline["scenario_identity"]
