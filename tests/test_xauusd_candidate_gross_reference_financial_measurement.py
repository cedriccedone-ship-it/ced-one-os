"""Historical measurement with real candidate, metadata and lifecycle owners."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import localcontext
from itertools import permutations
import ast
import inspect
import pytest

from ced_one.business_divisions.trading import xauusd_candidate_gross_reference_financial_measurement as owner
from ced_one.business_divisions.trading import xauusd_causal_liquidity_reversal as strategy
from ced_one.business_divisions.trading import causal_trading_policy_strategy_action_formulation as actions
from ced_one.business_divisions.trading.causal_snapshot_availability import snapshot_identity
from tests.test_xauusd_technical_trade_candidate import formulation_input, ENGINE, evaluate, set_breach, ts
from tests.test_causal_instrument_specification_applicability_resolver_v2 import sample as financial_sample, refresh
from tests.test_trading_vertical_slice_v27 import assertion, statement, correction
from tests.test_trading_vertical_slice_v28 import edge
from tests.test_trading_vertical_slice_v25 import paths, replace


def shift(value):
    if type(value) is dict: return {k: shift(v) for k,v in value.items()}
    if type(value) is list: return [shift(v) for v in value]
    if type(value) is str and value.startswith('2026-10-'):
        moment = datetime.fromisoformat(value.replace('Z','+00:00'))
        moment += datetime(2026,1,2,tzinfo=timezone.utc) - datetime(2026,10,24,9,tzinfo=timezone.utc)
        return moment.isoformat().replace('+00:00','Z')
    return value


@pytest.fixture(scope='module')
def originals():
    return {d: formulation_input(d) for d in ('LONG','SHORT')}


def refresh_measurement(value, bridge=True):
    request = value['applicability_input']
    refresh(request)
    resolved = owner.applicability.CAUSAL_INSTRUMENT_SPECIFICATION_APPLICABILITY_RESOLVER_V2.analyze(request).to_dict()
    value['applicability'] = resolved
    selected = next((row['snapshot'] for row in request['specification_revisions']
                     if row['snapshot']['specification']['source'] == resolved['selected_revision']), None)
    if bridge and selected is not None:
        value['bridge_assertions'] = [dict(contract=owner.ASSERTION_CONTRACT, assertion_revision_id='binding-1',
            source=dict(source_id='domain-declaration',source_contract='price-domain',source_contract_version='1'),
            available_at=ts(120), candidate_formulation=deepcopy(value['candidate_formulation']),
            selected_specification=deepcopy(selected), relationship=owner.RELATIONSHIP, verdict='COMPATIBLE')]
    else: value['bridge_assertions'] = []
    return value


def sample(originals, direction='LONG', rows=None, versions=None, bridge=True):
    p,_ = deepcopy(originals[direction])
    financial = shift(financial_sample(rows, versions))
    financial['economic_timestamp'] = ts(31)
    return refresh_measurement(dict(contract=owner.CONTRACT,rule_version=owner.RULE_VERSION,
        knowledge_boundary=ts(180), candidate_formulation=ENGINE.analyze(p).to_dict(), formulation_input=p,
        applicability=None, applicability_input=financial, bridge_assertions=[]), bridge)


def run(value):
    return owner.XAUUSD_CANDIDATE_GROSS_REFERENCE_FINANCIAL_MEASUREMENT.analyze(value).to_dict()


def terms(value):
    return value['applicability_input']['specification_revisions'][0]['snapshot_input']['specification']


def check(value, outcome):
    result = run(value)
    assert result['outcome'] == outcome
    assert (result['gross_reference_loss_per_quantity_unit'] is None) == (outcome != 'MEASURED')
    return result


@pytest.mark.parametrize('direction', ['LONG','SHORT'])
def test_exact_real_measurement(originals,direction):
    value = sample(originals,direction); result = check(value,'MEASURED')
    assert result['reference_price_distance'] == '17'
    assert result['gross_reference_loss_per_quantity_unit'] == '425'
    assert result['pnl_currency'] == 'USD'
    assert result['economic_timestamp'] == owner.metadata._timestamp(ts(31))
    assert result['candidate_formulation']['candidate']['entry_reference']['evidence']['candle']['timestamp'] == ts(30)
    assert not any(result['authority'].values())
    assert owner.validate_candidate_gross_reference_financial_measurement(result,value) == result


@pytest.mark.parametrize('kind,bridge,expected', [
    ('v1',False,'NOT_MEASURABLE'), ('partial',False,'UNKNOWN'), ('nonuniform',False,'NOT_MEASURABLE'),
    ('complete',False,'UNKNOWN'), ('complete',True,'MEASURED'), ('incompatible',True,'NOT_MEASURABLE'),
    ('unknown_model',False,'NOT_MEASURABLE'), ('missing_model',True,'UNKNOWN'), ('unknown_scope',True,'UNKNOWN'),
    ('partial_incompatible',True,'NOT_MEASURABLE'), ('nonuniform_partial',False,'NOT_MEASURABLE'),
])
def test_blocker_precedence(originals,kind,bridge,expected):
    value = sample(originals,versions=set() if kind == 'v1' else None,bridge=bridge)
    if kind != 'v1':
        p = terms(value)['payoff']
        if 'partial' in kind: p['payoff_units_per_quantity_unit'] = None
        if 'nonuniform' in kind: p['uniformity'] = 'NONUNIFORM'
        if kind == 'unknown_scope': p['uniformity'] = 'UNKNOWN'
        if kind in ('unknown_model','missing_model'):
            p.update(model='inverse' if kind=='unknown_model' else None,payoff_units_per_quantity_unit=None,pnl_currency=None)
        refresh_measurement(value,bridge)
    if 'incompatible' in kind: value['bridge_assertions'][0]['verdict'] = 'INCOMPATIBLE'
    check(value,expected)


@pytest.mark.parametrize('v1', [False,True])
@pytest.mark.parametrize('kind', ['malformed','future','conflict','revision_conflict'])
def test_integrity_not_hidden(originals,v1,kind):
    value = sample(originals,versions=set() if v1 else None)
    row = value['bridge_assertions'][0]
    if kind == 'malformed': row['source']['extra'] = True
    elif kind == 'future': row['available_at'] = ts(181)
    else:
        other = deepcopy(row); other['verdict'] = 'INCOMPATIBLE'
        if kind == 'conflict': other['assertion_revision_id'] = 'binding-2'
        value['bridge_assertions'].append(other)
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize('verdict,expected',[('COMPATIBLE','MEASURED'),('INCOMPATIBLE','NOT_MEASURABLE')])
def test_collection_identity(originals,verdict,expected):
    value = sample(originals); row = value['bridge_assertions'][0]; row['verdict'] = verdict
    baseline = check(value,expected)
    value['bridge_assertions'].append(deepcopy(row))
    assert run(value) == baseline
    other = deepcopy(row); other['source']['source_id'] = 'second-source'; other['assertion_revision_id'] = 'second'
    value['bridge_assertions'].append(other)
    result = check(value,expected)
    assert len(result['bridge_assertions']) == 2
    assert result['assessment_identity'] != baseline['assessment_identity']
    for order in permutations(value['bridge_assertions']):
        changed = deepcopy(value); changed['bridge_assertions'] = list(order)
        assert run(changed) == result


@pytest.mark.parametrize('kind', ['unresolved','absent'])
def test_missing_selection(originals,kind):
    rows = [assertion(),assertion('b',statement('APPLIES','B'))] if kind=='unresolved' else [assertion('w',statement('WITHDRAWS'))]
    value = sample(originals,rows=rows,bridge=False)
    result = check(value,'UNKNOWN')
    assert result['selected_specification'] is None
    value['bridge_assertions'] = sample(originals)['bridge_assertions']
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize('path', [
    ('candidate_formulation','candidate','entry_reference','evidence','candle','close'),
    ('candidate_formulation','candidate','stop_reference','evidence','candle','low'),
    ('candidate_formulation','m1_origin_source','metadata','rule_version'),
    ('selected_specification','specification','source','source_snapshot_id'),
    ('selected_specification','specification','position_namespace','instrument_id'),
])
def test_bridge_substitution(originals,path):
    value = sample(originals); replace(value['bridge_assertions'][0],path,'substituted')
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize('kind',['input_t','input_k','early_k','future_candidate'])
def test_causal_boundaries(originals,kind):
    value = sample(originals)
    if kind=='input_t': value['applicability_input']['economic_timestamp'] = ts(30)
    elif kind=='input_k': value['knowledge_boundary'] = ts(181)
    elif kind=='early_k': value['knowledge_boundary'] = ts(30)
    else: value['knowledge_boundary'] = ts(-1)
    if kind=='input_t': refresh_measurement(value)
    with pytest.raises(ValueError): run(value)


def test_later_validity_irrelevant(originals):
    value = sample(originals); before = run(value)
    p,h = deepcopy(originals['LONG'])
    assert evaluate(p,h,34)['status'] == 'EXPIRED'
    set_breach(h,'LONG',31)
    assert evaluate(p,h,34)['status'] == 'INVALIDATED'
    assert run(value) == before
    value['current_validity'] = 'VALID'
    with pytest.raises(ValueError): run(value)


def test_reference_multiplier_independent(originals):
    value = sample(originals); spec = terms(value)
    spec['economics']['reference_units_per_quantity_unit'] = None; spec['completeness'] = 'PARTIAL'
    assert check(refresh_measurement(value),'MEASURED')['gross_reference_loss_per_quantity_unit'] == '425'
    spec['economics']['reference_units_per_quantity_unit'] = '25'; spec['completeness'] = 'COMPLETE'
    assert check(refresh_measurement(value),'MEASURED')['gross_reference_loss_per_quantity_unit'] == '425'


@pytest.mark.parametrize('value,expected',[(1,'1'),(10**30+1,'1000000000000000000000000000001'),(0.1,'0.1'),(1e20,'100000000000000000000'),(1e-7,'0.0000001'),(5e-324,'0.'+'0'*323+'5'),(-0.0,'0')])
def test_numeric_interpretation(value,expected):
    with localcontext() as context:
        context.prec = 1
        assert owner._plain(owner._price(value)) == expected


@pytest.mark.parametrize('value',[True,False,float('nan'),float('inf'),-float('inf')])
def test_bad_numeric(value):
    with pytest.raises(ValueError): owner._price(value)


def test_exact_distance_and_collapse():
    assert owner._plain(owner._distance(owner._price(0.3),owner._price(0.1),'LONG')) == '0.2'
    entry,stop = 1.0000000000000001e18,1000000000000000100
    assert entry > stop
    with pytest.raises(ValueError,match='INTERPRETED_GEOMETRY_INCONSISTENCY'):
        owner._distance(owner._price(entry),owner._price(stop),'LONG')
    for entry,stop in [(1,1),(1,2)]:
        with pytest.raises(ValueError,match='INTERPRETED_GEOMETRY_INCONSISTENCY'):
            owner._distance(owner._price(entry),owner._price(stop),'LONG')


def test_ambient_precision(originals):
    value = sample(originals); terms(value)['payoff']['payoff_units_per_quantity_unit'] = '12345678901234567890.123456789'
    refresh_measurement(value)
    with localcontext() as context:
        context.prec = 1; low = run(value)
        context.prec = 80; high = run(value)
    assert low == high
    assert low['gross_reference_loss_per_quantity_unit'] == '209876541320987654132.098765413'


class NumericInt(int):
    """JSON-serializable owner-valid value outside the new exact built-in domain."""


def rebuild_numeric_candidate(value, conversion):
    p = value['formulation_input']; action_input = p['action_formulation_input']
    request = action_input['assessment_input']
    for source in request['sources'].values():
        for candle in source['approved_candle_history']:
            for key in ('open','high','low','close'): candle[key] = conversion(candle[key])
        source['source_snapshot_id'] = snapshot_identity(source)
        source['evidence']['source_snapshot_id'] = source['source_snapshot_id']
    assessment = strategy.XAUUSD_CAUSAL_LIQUIDITY_REVERSAL.analyze(request).to_dict()
    action_input['strategy_assessment'] = assessment
    p['strategy_assessment'] = deepcopy(assessment)
    p['action_formulation'] = actions.STRATEGY_ACTION_FORMULATION.analyze(action_input).to_dict()
    value['candidate_formulation'] = ENGINE.analyze(p).to_dict()
    return refresh_measurement(value)


@pytest.mark.parametrize('conversion,expected',[(int,'MEASURED'),(NumericInt,'NOT_MEASURABLE')])
def test_owner_valid_numeric_domain(originals,conversion,expected):
    value = rebuild_numeric_candidate(sample(originals),conversion)
    if conversion is NumericInt: value['bridge_assertions'] = []
    check(value,expected)


def test_timing_revisions(originals):
    for boundary,selected in [(ts(30.5),'B'),(ts(32),'A')]:
        value = sample(originals,rows=[assertion(),assertion('b',edge())])
        evidence = value['applicability_input']['lifecycle_evidence']['snapshot_input']['evidence']
        evidence['assertions'][1]['statement']['economic_scope']['effective_from'] = boundary
        for entry in value['applicability_input']['specification_revisions']:
            if entry['snapshot_input']['specification']['source']['source_snapshot_id']=='B':
                entry['snapshot_input']['specification']['timing']['effective_at'] = boundary
        result = check(refresh_measurement(value),'MEASURED')
        assert result['selected_specification']['specification']['source']['source_snapshot_id'] == selected
    value = sample(originals,rows=[assertion(),correction(replacement=statement('APPLIES','B'))])
    assert check(value,'MEASURED')['selected_specification']['specification']['source']['source_snapshot_id']=='B'


@pytest.mark.parametrize('field',['contract','rule_version','knowledge_boundary'])
def test_wrong_contract_or_boundary(originals,field):
    value = sample(originals); value[field] = 'invalid'
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize('field',['current_validity','account','quantity','price','compliance','execution'])
def test_excluded_inputs(originals,field):
    value = sample(originals); value[field] = {}
    with pytest.raises(ValueError): run(value)


def test_mutation_and_full_validation(originals):
    value = sample(originals); result = owner.XAUUSD_CANDIDATE_GROSS_REFERENCE_FINANCIAL_MEASUREMENT.analyze(value)
    expected = result.to_dict()
    result.payload['bridge_assertions'].clear(); result.to_dict()['authority']['execution'] = True
    validated = owner.validate_candidate_gross_reference_financial_measurement(result,value)
    validated['candidate_formulation'].clear()
    assert result.to_dict() == expected
    for field in expected:
        changed = deepcopy(expected); changed[field] = None
        with pytest.raises(ValueError): owner.validate_candidate_gross_reference_financial_measurement(changed,value)
    value['bridge_assertions'].clear()
    assert result.to_dict() == expected


def test_reason_order_and_identity(originals):
    value = sample(originals); p = terms(value)['payoff']; p.update(model='inverse',payoff_units_per_quantity_unit=None,pnl_currency=None,uniformity='NONUNIFORM')
    refresh_measurement(value); value['bridge_assertions'][0]['verdict']='INCOMPATIBLE'
    result = check(value,'NOT_MEASURABLE')
    assert result['reasons']==['UNSUPPORTED_PAYOFF_MODEL','NONUNIFORM_PAYOFF','DIRECT_PRICE_DOMAIN_INCOMPATIBLE']
    changed = deepcopy(value); changed['bridge_assertions'][0]['source']['source_id']='other'
    assert run(changed)['assessment_identity'] != result['assessment_identity']


def test_dependencies():
    tree = ast.parse(inspect.getsource(owner))
    imports = [a.name for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom)) for a in n.names]
    assert not any(any(word in name for word in ('account_state','price_observation','rule_regime','execution')) for name in imports)
    calls = [ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call)]
    assert not any('validity' in call for call in calls)
    assert 'abs' not in calls


@pytest.mark.parametrize('field',['reference_asset_id','reference_unit','price_currency'])
def test_missing_reference_dimensions(originals,field):
    value = sample(originals); spec = terms(value)
    spec['economics'][field] = None; spec['completeness'] = 'PARTIAL'
    check(refresh_measurement(value),'UNKNOWN')


@pytest.mark.parametrize('field',['payoff_units_per_quantity_unit','pnl_currency'])
def test_missing_payoff_fields(originals,field):
    value = sample(originals); terms(value)['payoff'][field] = None
    check(refresh_measurement(value),'UNKNOWN')


@pytest.mark.parametrize('bad',[True,float('nan'),float('inf')])
def test_malformed_candidate_not_hidden_by_v1(originals,bad):
    value = sample(originals,versions=set(),bridge=False)
    value['candidate_formulation']['candidate']['entry_reference']['value'] = bad
    with pytest.raises(ValueError): run(value)


def test_exact_input_schemas(originals):
    original = sample(originals)
    for path in [(),('bridge_assertions',0),('bridge_assertions',0,'source')]:
        target = original
        for key in path: target = target[key]
        for missing in target:
            value = deepcopy(original); current = value
            for key in path: current = current[key]
            del current[missing]
            with pytest.raises(ValueError): run(value)


def test_t_equals_k(originals):
    value = sample(originals); boundary = ts(31)
    def cap(item):
        if type(item) is dict: return {key:cap(child) for key,child in item.items()}
        if type(item) is list: return [cap(child) for child in item]
        if type(item) is str and item.startswith('2026-01-02T') and owner.metadata._timestamp(item)>owner.metadata._timestamp(boundary):
            return boundary
        return item
    value['applicability_input'] = cap(value['applicability_input'])
    value['knowledge_boundary'] = boundary
    refresh_measurement(value)
    value['bridge_assertions'][0]['available_at'] = boundary
    result = check(value,'MEASURED')
    assert result['economic_timestamp'] == result['knowledge_boundary']


def test_max_finite_float_exact():
    value = owner._price(float.fromhex('0x1.fffffffffffffp+1023'))
    assert owner._plain(value) == '17976931348623157' + '0'*292


def test_nested_output_tampering(originals):
    value = sample(originals); result = run(value)
    for path in [
        ('candidate_formulation','candidate','stop_reference','value'),
        ('selected_specification','specification','payoff','payoff_units_per_quantity_unit'),
        ('applicability','selected_specification_snapshot_reference','content_fingerprint'),
        ('bridge_assertions',0,'source','source_id'),
        ('authority','financial_risk'),
    ]:
        changed = deepcopy(result); replace(changed,path,'altered')
        with pytest.raises(ValueError): owner.validate_candidate_gross_reference_financial_measurement(changed,value)
