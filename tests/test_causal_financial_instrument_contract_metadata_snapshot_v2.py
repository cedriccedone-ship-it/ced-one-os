"""Payoff facts stay dimensional, explicit, immutable and non-authoritative."""
from copy import deepcopy
from decimal import localcontext
import pytest
from ced_one.business_divisions.trading import causal_financial_instrument_contract_metadata_snapshot_v2 as owner
from tests.test_trading_vertical_slice_v25 import sample as reference_sample, paths, at, replace


def sample():
    value = reference_sample()
    value.update(contract=owner.CONTRACT, rule_version=owner.RULE_VERSION)
    value['specification']['payoff'] = dict(model=owner.MODEL, payoff_units_per_quantity_unit='25.000', pnl_currency='USD', uniformity='UNIFORM')
    return value


def run(value):
    return owner.CAUSAL_FINANCIAL_INSTRUMENT_CONTRACT_METADATA_SNAPSHOT_V2.analyze(value).to_dict()


def validate(value, source):
    return owner.validate_causal_financial_instrument_contract_metadata_snapshot_v2(value, source)


def test_complete_and_no_calculation():
    value = sample(); result = run(value)
    assert (result['payoff_model_support'], result['payoff_completeness']) == ('SUPPORTED', 'COMPLETE')
    assert result['specification']['payoff']['payoff_units_per_quantity_unit'] == '25'
    assert result['specification']['economics']['reference_units_per_quantity_unit'] == '100'
    assert not any(result['authority'].values())
    assert result['source_authentication'] == 'NOT_VERIFIED_BY_THIS_CAPABILITY'
    assert set(result) == {'snapshot_id', 'contract', 'rule_version', 'identity_scope', 'requested_evaluation_timestamp', 'specification', 'model_support', 'effective_start_status', 'source_authentication', 'limitations', 'authority', 'payoff_model_support', 'payoff_completeness'}
    assert validate(result, value) == result


@pytest.mark.parametrize('bad', ['0', '-0.00', '-1', '1e2', 1.5, True, False, 'NaN', 'Infinity', ' 1', '+1', '01', '', [], {}])
def test_bad_coefficient(bad):
    value = sample(); value['specification']['payoff']['payoff_units_per_quantity_unit'] = bad
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize('uniformity,support,complete', [('UNIFORM','SUPPORTED','COMPLETE'), ('UNKNOWN','SUPPORTED','PARTIAL'), ('NONUNIFORM','UNSUPPORTED','COMPLETE')])
@pytest.mark.parametrize('missing', [False, True])
def test_scope(uniformity, support, complete, missing):
    value = sample(); payoff = value['specification']['payoff']; payoff['uniformity'] = uniformity
    if missing: payoff['pnl_currency'] = None
    result = run(value)
    assert (result['payoff_model_support'], result['payoff_completeness']) == (support, 'PARTIAL' if missing else complete)


@pytest.mark.parametrize('model,support', [(None,'UNAVAILABLE'), ('inverse','UNSUPPORTED')])
def test_unrecognized(model, support):
    value = sample(); payoff = value['specification']['payoff']; payoff.update(model=model, payoff_units_per_quantity_unit=None, pnl_currency=None)
    result = run(value)
    assert (result['payoff_model_support'], result['payoff_completeness']) == (support, 'UNAVAILABLE')
    for field, data in [('payoff_units_per_quantity_unit','1'), ('pnl_currency','USD')]:
        changed = deepcopy(value); changed['specification']['payoff'][field] = data
        with pytest.raises(ValueError): run(changed)


@pytest.mark.parametrize('field', ['reference_asset_id', 'reference_unit', 'price_currency', 'reference_units_per_quantity_unit'])
def test_reference_dependencies(field):
    value = sample(); value['specification']['economics'][field] = None; value['specification']['completeness'] = 'PARTIAL'
    result = run(value)
    assert result['payoff_completeness'] == ('COMPLETE' if field == 'reference_units_per_quantity_unit' else 'PARTIAL')


@pytest.mark.parametrize('field', ['payoff_units_per_quantity_unit', 'pnl_currency'])
def test_missing_payoff(field):
    value = sample(); value['specification']['payoff'][field] = None
    assert run(value)['payoff_completeness'] == 'PARTIAL'


@pytest.mark.parametrize('uniformity', ['UNIFORM', 'NONUNIFORM', 'UNKNOWN'])
def test_currency_contradiction_even_when_unusable(uniformity):
    value = sample(); value['specification']['payoff'].update(pnl_currency='EUR', uniformity=uniformity)
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize('path', [p for p in paths(sample()) if isinstance(at(sample(), p), dict)] + [()])
def test_exact_objects(path):
    original = sample()
    for key in at(original, path):
        value = deepcopy(original); del at(value, path)[key]
        with pytest.raises(ValueError): run(value)
    value = deepcopy(original); at(value, path)['extra'] = True
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize('field,bad', [('uniformity','uniform'), ('model',''), ('pnl_currency','usd'), ('pnl_currency',True)])
def test_bad_declarations(field, bad):
    value = sample(); value['specification']['payoff'][field] = bad
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize('path', list(paths(sample())))
def test_identity_and_input_substitution(path):
    value = sample(); result = run(value)
    changed = deepcopy(value); replace(changed, path, None)
    with pytest.raises(ValueError): validate(result, changed)


@pytest.mark.parametrize('path', list(paths(run(sample()))))
def test_full_content_tampering(path):
    value = sample(); result = run(value); replace(result, path, 'tampered')
    with pytest.raises(ValueError): validate(result, value)


def test_normalization_precision_and_independence():
    value = sample(); canonical = deepcopy(value)
    canonical['specification']['payoff']['payoff_units_per_quantity_unit'] = '25'
    canonical['specification']['timing']['observed_at'] = '2026-10-24T13:00:00+02:00'
    with localcontext() as context:
        context.prec = 1
        assert run(value) == run(canonical)
    changed = deepcopy(value); changed['specification']['payoff']['payoff_units_per_quantity_unit'] = '100'
    assert run(changed)['snapshot_id'] != run(value)['snapshot_id']
    changed['specification']['payoff']['payoff_units_per_quantity_unit'] = None
    assert run(changed)['payoff_completeness'] == 'PARTIAL'


@pytest.mark.parametrize('path,data', [(('specification','payoff','uniformity'),'UNKNOWN'), (('specification','source','source_snapshot_id'),'new'), (('specification','payoff','payoff_units_per_quantity_unit'),'26')])
def test_economic_identity(path, data):
    value = sample(); changed = deepcopy(value); replace(changed,path,data)
    assert run(value)['snapshot_id'] != run(changed)['snapshot_id']


def test_mutation_isolation():
    value = sample(); result = owner.CAUSAL_FINANCIAL_INSTRUMENT_CONTRACT_METADATA_SNAPSHOT_V2.analyze(value); expected = result.to_dict()
    value['specification']['payoff']['pnl_currency'] = 'EUR'
    result.payload['specification']['payoff']['pnl_currency'] = 'EUR'
    result.to_dict()['authority']['execution'] = True
    assert result.to_dict() == expected
    validated = validate(result, sample()); validated['specification'].clear()
    assert result.to_dict() == expected


def test_timing():
    value = sample(); assert run(value)['effective_start_status'] == 'FUTURE_EFFECTIVE'
    assert run(value)['specification']['timing']['observed_at'].endswith('.000000Z')
    value['specification']['timing']['observed_at'] = '2026-10-25T00:00:00Z'
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize('field', ['contract','rule_version'])
def test_wrong_version(field):
    value = sample(); value[field] = 'v1'
    with pytest.raises(ValueError): run(value)
