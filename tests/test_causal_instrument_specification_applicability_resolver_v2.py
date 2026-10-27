"""Version-bound applicability reuses lifecycle semantics without upgrading facts."""
from copy import deepcopy
import pytest
from ced_one.business_divisions.trading import causal_instrument_specification_applicability_resolver as owner
from ced_one.business_divisions.trading import causal_financial_instrument_contract_metadata_snapshot as v1
from ced_one.business_divisions.trading import causal_financial_instrument_contract_metadata_snapshot_v2 as v2
from ced_one.business_divisions.trading import causal_instrument_specification_lifecycle_evidence_snapshot as lifecycle
from tests.test_trading_vertical_slice_v28 import sample as old_sample, assertion, statement, correction, edge, evidence, time
from tests.test_causal_financial_instrument_contract_metadata_snapshot_v2 import sample as payoff_sample
from tests.test_trading_vertical_slice_v25 import paths, replace


def refresh(value):
    entry = value['lifecycle_evidence']
    entry['snapshot'] = lifecycle.CAUSAL_INSTRUMENT_SPECIFICATION_LIFECYCLE_EVIDENCE_SNAPSHOT.analyze(entry['snapshot_input']).to_dict()
    for entry in value['specification_revisions']:
        analyzer = v2.CAUSAL_FINANCIAL_INSTRUMENT_CONTRACT_METADATA_SNAPSHOT_V2 if entry['snapshot_input']['contract'] == v2.CONTRACT else v1.CAUSAL_FINANCIAL_INSTRUMENT_CONTRACT_METADATA_SNAPSHOT
        entry['snapshot'] = analyzer.analyze(entry['snapshot_input']).to_dict()
    return value


def sample(rows=None, versions=None):
    value = old_sample(rows)
    value.update(contract=owner.CONTRACT_V2, rule_version=owner.RULE_VERSION_V2)
    for entry in value['specification_revisions']:
        data = entry['snapshot_input']
        if versions is None or data['specification']['source']['source_snapshot_id'] in versions:
            data.update(contract=v2.CONTRACT, rule_version=v2.RULE_VERSION)
            data['specification']['payoff'] = payoff_sample()['specification']['payoff']
    return refresh(value)


def run(value):
    return owner.CAUSAL_INSTRUMENT_SPECIFICATION_APPLICABILITY_RESOLVER_V2.analyze(value).to_dict()


def validate(result, value):
    return owner.validate_causal_instrument_specification_applicability_resolver_v2(result, value)


@pytest.mark.parametrize('versions,contract', [(set(),v1.CONTRACT), ({'A'},v2.CONTRACT)])
def test_dispatch_exact_content(versions, contract):
    value = sample(versions=versions); result = run(value)
    artifact = value['specification_revisions'][0]['snapshot']
    assert result['contract'] == owner.CONTRACT_V2
    assert result['rule_version'] == owner.RULE_VERSION_V2
    assert result['outcome'] == 'UNIQUE_APPLICABLE_REVISION'
    assert result['selected_specification_snapshot_reference'] == owner._artifact_reference(artifact)
    assert result['selected_specification_snapshot_reference']['contract'] == contract
    assert ('payoff' in artifact['specification']) == (contract == v2.CONTRACT)
    assert validate(result,value) == result


@pytest.mark.parametrize('rows,outcome,selected', [
    ([assertion()], 'UNIQUE_APPLICABLE_REVISION','A'),
    ([assertion(),assertion('b',statement('APPLIES','B'))], 'UNRESOLVED',None),
    ([assertion('w',statement('WITHDRAWS'))], 'NO_APPLICABLE_REVISION_ESTABLISHED',None),
    ([assertion(),assertion('b',edge())], 'UNIQUE_APPLICABLE_REVISION','B'),
    ([assertion(),correction(replacement=statement('APPLIES','B'))], 'UNIQUE_APPLICABLE_REVISION','B'),
    ([assertion(),correction()], 'NO_APPLICABLE_REVISION_ESTABLISHED',None),
])
def test_lifecycle(rows, outcome, selected):
    value = sample(rows); result = run(value)
    assert result['outcome'] == outcome
    assert (None if result['selected_revision'] is None else result['selected_revision']['source_snapshot_id']) == selected
    assert validate(result,value) == result


def test_insufficient_coverage():
    value = sample(); evidence(value)['coverage']['completeness'] = 'LIMITED'
    evidence(value)['coverage']['omissions']['history_truncated'] = True
    result = run(refresh(value))
    assert result['outcome'] == 'UNRESOLVED'
    assert result['selected_specification_snapshot_reference'] is None


def test_mixed_transition():
    value = sample([assertion(),assertion('b',edge())], versions={'B'})
    result = run(value)
    assert result['selected_revision']['source_snapshot_id'] == 'B'
    assert result['selected_specification_snapshot_reference']['contract'] == v2.CONTRACT
    assert {r['snapshot_reference']['contract'] for r in result['specification_revision_references']} == {v1.CONTRACT,v2.CONTRACT}


@pytest.mark.parametrize('collision', [False,True])
def test_duplicate_revision(collision):
    value = sample(); extra = deepcopy(value['specification_revisions'][0])
    if collision:
        extra['snapshot_input'].update(contract=v1.CONTRACT,rule_version=v1.RULE_VERSION)
        del extra['snapshot_input']['specification']['payoff']
    value['specification_revisions'].append(extra)
    with pytest.raises(ValueError): run(refresh(value))


@pytest.mark.parametrize('kind', ['unknown','relabel','input','rule','tamper'])
def test_version_and_owner_substitution(kind):
    value = sample(versions=set()) if kind == 'relabel' else sample()
    entry = value['specification_revisions'][0]
    if kind == 'unknown': entry['snapshot']['contract'] = 'unknown'
    elif kind == 'relabel': entry['snapshot'].update(contract=v2.CONTRACT,rule_version=v2.RULE_VERSION)
    elif kind == 'input': entry['snapshot_input']['contract'] = v1.CONTRACT
    elif kind == 'rule': entry['snapshot']['rule_version'] = v1.RULE_VERSION
    else: entry['snapshot']['specification']['payoff']['payoff_units_per_quantity_unit'] = '999'
    with pytest.raises(ValueError): run(value)


@pytest.mark.parametrize('path', list(paths(run(sample()))))
def test_result_tampering(path):
    value = sample(); result = run(value); replace(result,path,'tampered')
    with pytest.raises(ValueError): validate(result,value)


def test_v1_not_broadened():
    value = sample(); value.update(contract=owner.CONTRACT,rule_version=owner.RULE_VERSION)
    with pytest.raises(ValueError): owner.CAUSAL_INSTRUMENT_SPECIFICATION_APPLICABILITY_RESOLVER.analyze(value)
    with pytest.raises(ValueError): run(old_sample())


@pytest.mark.parametrize('kind', ['namespace','future','revision','cutoff'])
def test_binding_and_causality(kind):
    value = sample(); spec = value['specification_revisions'][0]['snapshot_input']['specification']
    if kind == 'namespace': spec['position_namespace']['instrument_id'] = 'other'
    elif kind == 'future':
        spec['timing']['observed_at'] = time(13)
        value['specification_revisions'][0]['snapshot_input']['requested_evaluation_timestamp'] = time(14)
    elif kind == 'revision': spec['source']['source_snapshot_id'] = 'other'
    else: evidence(value)['coverage']['source_information_cutoff'] = time(11)
    if kind == 'cutoff': assert run(refresh(value))['outcome'] == 'UNRESOLVED'
    else:
        with pytest.raises(ValueError): run(refresh(value))


def test_objects_and_mutation_isolation():
    value = sample(); entry = value['specification_revisions'][0]
    entry['snapshot'] = v2.CAUSAL_FINANCIAL_INSTRUMENT_CONTRACT_METADATA_SNAPSHOT_V2.analyze(entry['snapshot_input'])
    result = owner.CAUSAL_INSTRUMENT_SPECIFICATION_APPLICABILITY_RESOLVER_V2.analyze(value)
    expected = result.to_dict()
    result.payload['selected_revision'].clear()
    result.to_dict()['authority']['execution'] = True
    assert validate(result,value) == expected
    value['specification_revisions'].clear()
    assert result.to_dict() == expected
