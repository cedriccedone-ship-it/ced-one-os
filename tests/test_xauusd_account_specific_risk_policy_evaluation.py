"""Pre-quantity policy checks using real reconstructed upstream owner artifacts."""
import base64
from copy import deepcopy
from decimal import localcontext
from hashlib import sha256
import inspect
import json

import pytest

from ced_one.business_divisions.trading import xauusd_account_specific_risk_policy_evaluation as owner
from tests import test_trading_vertical_slice_v24 as accounts
from tests import test_trading_vertical_slice_v29 as regimes
from tests import test_xauusd_candidate_gross_reference_financial_measurement as measurements

T = '2026-01-10T00:00:00.000000Z'
EARLY = '2026-01-01T00:00:00.000000Z'
END = '2027-01-01T00:00:00.000000Z'
# Fixed Amsterdam TZif artifact; no runtime host database dependency.
TZIF = 'VFppZjIAAAAAAAAAAAAAAAAAAAAAAAALAAAACwAAAAAAAAC4AAAACwAAABaAAAAAmERJgJsMJXCb1drwnNmukJ2ktZCeuZCQn4SXkJ/O+DCgYKXwoX67cKIuEvCjekzwpDWB8KVeI3CmJTXwpyeb8KgqAfCpB33wqe40cKrnX/Cr11DwrMdB8K3Jp/CupyPwr6BPcLCHBfCxiWvwsnBMoLNysqC0UC6gtUlaILYwEKC3MnaguA/yoLj/46C579SgutaLILvY8SC8yOIgvbjTIL6fiaC/mLUgwJsbIMF4lyDCaIggw1h5IMQ/L6DFOFsgxjrBIMdY1qDH2gmgyEoZIMznSxDNqReQzqJDEM+SNBDQbl6Q0XIWENJOQJDTkUAQ1EsjkA2kY5AOixoQD4RFkBB0NpARZCeQElQYkBNNRBAUM/qQFSPrkBYT3JAXA82QF/O+kBjjr5AZ06CQGsORkBu8vRAcrK4QHZyfEB6MkBAffIEQIGxyECFcYxAiTFQQIzxFECQsNhAlHCcQJgwYECcFQ5An9TSQKOUlkCnVFpAqxQeQK7T4kCyk6ZAtlNqQLoTLkC90vJAwZK2QMV3ZEDJytBAzPbsQNFKWEDUdnRA2MngQNv1/EDgblJA43WEQOft2kDq9QxA721iQPKZfkD27OpA+hkGQP5sckEBmI5BBhDkQQkYFkENkGxBEJeeQRUP9EEYFyZBHI98QR+7mEEkDwRBJzsgQSuOjEEuuqhBMzL+QTY6MEE6soZBPbm4QUIyDkFFXipBSbGWQUzdskFRMR5BVF06QViwpkFb3MJBYFUYQWNcSkFn1KBBatvSQW9UKEFygERBdtOwQXn/zEF+UzhBgX9UQYX3qkGI/txBjXcyQZB+ZEGU9rpBmCLWQZx2QkGfol5Bo/XKQach5kGrdVJBrqFuQbMZxEG2IPZBuplMQb2gfkHCGNRBxUTwQcmYXEHMxHhB0RfkQdREAEHYvFZB28OIQeA73kHjQxBB57tmQerCmEHvOu5B8mcKQfa6dkH55pJB/jn+QAQIFAgMEAwQIBgcGBwYHBgcGBwYHBgcGBwYHBgcGBwYHBgcGBwYHBgcGBwYHBgcGBwYHBgMEAwQDBAMEAwQJCgkKCQoJCgkKCQoJCgkKCQoJCgkKCQoJCgkKCQoJCgkKCQoJCgkKCQoJCgkKCQoJCgkKCQoJCgkKCQoJCgkKCQoJCgkKCQoJCgkKCQoJCgkKCQoJCgkKCQoJCgkKCQoJCgkKCQoJCgkKCQoJCgkKCQoJCgkKCQoJCgAABBoAAAAAAAAABAAADhAACAAAHCABDAAADhAACAAAHCABDAAADhABEQAAAAAABAAAAAAABAAAHCABDAAADhAACExNVABXRVQAQ0VUAENFU1QAV0VTVAAAAAABAQABAQEBAQAAAAAAAAAAAQEBVFppZjIAAAAAAAAAAAAAAAAAAAAAAAAMAAAADAAAAAAAAAC5AAAADAAAABr/////Vrbf5v////9t6MgA/////5hESYD/////mwwlcP////+b1drw/////5zZrpD/////naS1kP////+euZCQ/////5+El5D/////n874MP////+gYKXw/////6F+u3D/////oi4S8P////+jekzw/////6Q1gfD/////pV4jcP////+mJTXw/////6cnm/D/////qCoB8P////+pB33w/////6nuNHD/////qudf8P////+r11Dw/////6zHQfD/////rcmn8P////+upyPw/////6+gT3D/////sIcF8P////+xiWvw/////7JwTKD/////s3KyoP////+0UC6g/////7VJWiD/////tjAQoP////+3Mnag/////7gP8qD/////uP/joP////+579Sg/////7rWiyD/////u9jxIP////+8yOIg/////7240yD/////vp+JoP////+/mLUg/////8CbGyD/////wXiXIP/////CaIgg/////8NYeSD/////xD8voP/////FOFsg/////8Y6wSD/////x1jWoP/////H2gmg/////8hKGSD/////zOdLEP/////NqReQ/////86iQxD/////z5I0EP/////Qbl6Q/////9FyFhD/////0k5AkP/////TkUAQ/////9RLI5AAAAAADaRjkAAAAAAOixoQAAAAAA+ERZAAAAAAEHQ2kAAAAAARZCeQAAAAABJUGJAAAAAAE01EEAAAAAAUM/qQAAAAABUj65AAAAAAFhPckAAAAAAXA82QAAAAABfzvpAAAAAAGOOvkAAAAAAZ06CQAAAAABrDkZAAAAAAG7y9EAAAAAAcrK4QAAAAAB2cnxAAAAAAHoyQEAAAAAAffIEQAAAAACBschAAAAAAIVxjEAAAAAAiTFQQAAAAACM8RRAAAAAAJCw2EAAAAAAlHCcQAAAAACYMGBAAAAAAJwVDkAAAAAAn9TSQAAAAACjlJZAAAAAAKdUWkAAAAAAqxQeQAAAAACu0+JAAAAAALKTpkAAAAAAtlNqQAAAAAC6Ey5AAAAAAL3S8kAAAAAAwZK2QAAAAADFd2RAAAAAAMnK0EAAAAAAzPbsQAAAAADRSlhAAAAAANR2dEAAAAAA2MngQAAAAADb9fxAAAAAAOBuUkAAAAAA43WEQAAAAADn7dpAAAAAAOr1DEAAAAAA721iQAAAAADymX5AAAAAAPbs6kAAAAAA+hkGQAAAAAD+bHJAAAAAAQGYjkAAAAABBhDkQAAAAAEJGBZAAAAAAQ2QbEAAAAABEJeeQAAAAAEVD/RAAAAAARgXJkAAAAABHI98QAAAAAEfu5hAAAAAASQPBEAAAAABJzsgQAAAAAErjoxAAAAAAS66qEAAAAABMzL+QAAAAAE2OjBAAAAAATqyhkAAAAABPbm4QAAAAAFCMg5AAAAAAUVeKkAAAAABSbGWQAAAAAFM3bJAAAAAAVExHkAAAAABVF06QAAAAAFYsKZAAAAAAVvcwkAAAAABYFUYQAAAAAFjXEpAAAAAAWfUoEAAAAABatvSQAAAAAFvVChAAAAAAXKAREAAAAABdtOwQAAAAAF5/8xAAAAAAX5TOEAAAAABgX9UQAAAAAGF96pAAAAAAYj+3EAAAAABjXcyQAAAAAGQfmRAAAAAAZT2ukAAAAABmCLWQAAAAAGcdkJAAAAAAZ+iXkAAAAABo/XKQAAAAAGnIeZAAAAAAat1UkAAAAABrqFuQAAAAAGzGcRAAAAAAbYg9kAAAAABuplMQAAAAAG9oH5AAAAAAcIY1EAAAAABxUTwQAAAAAHJmFxAAAAAAczEeEAAAAAB0RfkQAAAAAHURABAAAAAAdi8VkAAAAAB28OIQAAAAAHgO95AAAAAAeNDEEAAAAAB57tmQAAAAAHqwphAAAAAAe867kAAAAAB8mcKQAAAAAH2unZAAAAAAfnmkkAAAAAB/jn+QAQIDBgMEBQQFCQcIBwgHCAcIBwgHCAcIBwgHCAcIBwgHCAcIBwgHCAcIBwgHCAcIBwgHCAcEBQQFBAUEBQQFCgsKCwoLCgsKCwoLCgsKCwoLCgsKCwoLCgsKCwoLCgsKCwoLCgsKCwoLCgsKCwoLCgsKCwoLCgsKCwoLCgsKCwoLCgsKCwoLCgsKCwoLCgsKCwoLCgsKCwoLCgsKCwoLCgsKCwoLCgsKCwoLCgsKCwoLCgsKCwoLCgsAAAQaAAAAAAQaAAQAAAAAAAgAAA4QAAwAABwgARAAAA4QAAwAABwgARAAAA4QARUAAAAAAAgAAAAAAAgAABwgARAAAA4QAAxMTVQAQk1UAFdFVABDRVQAQ0VTVABXRVNUAAAAAAABAQABAQEBAQAAAAAAAAAAAAEBAQpDRVQtMUNFU1QsTTMuNS4wLE0xMC41LjAvMwo='
SOURCE = dict(source_id='broker', source_contract='accounts', source_contract_version='1', source_snapshot_id='local-evidence')


def provenance():
    return dict(source=deepcopy(SOURCE), record_id='record')


def artifact(value):
    return dict(contract=value['contract'], rule_version=value['rule_version'], full_content_sha256=digest(value))


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def compatibility(q):
    s = q['account_state']['snapshot']; c = q['candidate']['formulation']; m = q['financial_measurement']['assessment']
    q['financial_compatibility'] = [dict(contract=owner.COMPATIBILITY_CONTRACT, rule_version=owner.COMPATIBILITY_RULE,
        assertion_id='compatible', assertion_revision=1, source=deepcopy(SOURCE), available_at=q['knowledge_boundary'],
        assessment_economic_time=q['assessment_economic_time'], knowledge_boundary=q['knowledge_boundary'],
        intended_use='PRE_QUANTITY_FROZEN_REFERENCE_RISK_CALCULATION', subjects=dict(account_snapshot=artifact(s),
        candidate=artifact(c), measurement=artifact(m), specification=artifact(m['selected_specification']),
        quantity_unit=m['quantity_unit'], measurement_pnl_currency=m['pnl_currency'], account_equity_currency=s['observation']['account']['currency']))]


def refresh_account(q):
    q['account_state']['snapshot'] = accounts.run(q['account_state']['snapshot_input'])
    compatibility(q)


def selected(q):
    return q['account_rule_regime']['assessment']['selected_regime']['package']['rules'][0]


def set_rule(q, kind, edit=None):
    value = q['account_rule_regime']['assessment_input']
    rule = regimes.rule(kind)
    if edit: edit(rule)
    regimes.package(value)['rules'] = [rule]
    q['account_rule_regime']['assessment'] = regimes.run(regimes.refresh(value))
    q['provider_operands'] = []
    return selected(q)


def support(content, identifier, at=T):
    return dict(evidence_id=identifier, source=deepcopy(SOURCE), available_at=at, content=deepcopy(content))


def evidence_ref(e):
    return dict(evidence_id=e['evidence_id'], full_content_sha256=digest(e))


def operand(q, tag, body):
    r = selected(q)
    row = dict(tag=tag, rule_reference=dict(rule_id=r['rule_id'], full_content_sha256=digest(r)),
        account_binding=deepcopy(q['own_policy']['account_binding']), effective_from=EARLY, effective_until=END,
        source=deepcopy(SOURCE), available_at=q['knowledge_boundary'], supporting_evidence=[], body=deepcopy(body))
    content = dict(kind='PROVIDER_OPERAND', **{k: row[k] for k in ('tag','rule_reference','account_binding','effective_from','effective_until','body')})
    row['supporting_evidence'] = [support(content, tag + str(len(q['provider_operands'])), q['knowledge_boundary'])]
    q['provider_operands'].append(row)
    return row


def trade(q, name='a', mechanism='INITIAL_PROTECTIVE_STOP', amount='-10', status='FINAL_COMPLETE', structure='SUPPORTED', close='2026-01-09T23:30:00.000000Z', revision=1, predecessor=None, at=None, fills=1):
    at = at or q['knowledge_boundary']
    evidence = []
    def proof(content, label):
        e = support(content, label, at); evidence.append(e); return evidence_ref(e)
    def group(role):
        g = dict(group_id=name+role, role=role, grouping_interpretation='explicit-source-group-v1',
            member_execution_references=[dict(source_id='executions', execution_id=name+role+str(i), full_content_sha256=sha256((name+role+str(i)).encode()).hexdigest()) for i in range(fills)])
        g['evidence_reference'] = proof(dict(kind='EXECUTION_GROUP', trade_identity=name, **g), role)
        return g
    ep = dict(model=owner._UNIT, structure=structure, completed=True, actual_terminal_close_time=close,
              instrument='XAUUSD', entry_group=None, terminal_group=None, structure_evidence=None)
    if structure == 'SUPPORTED':
        ep['entry_group'], ep['terminal_group'] = group('ENTRY'), group('TERMINAL')
        ep['structure_evidence'] = proof(dict(kind='EPISODE_STRUCTURE', trade_identity=name, model=owner._UNIT,
            entry_group_sha256=digest(ep['entry_group']), terminal_group_sha256=digest(ep['terminal_group']),
            scale_in=False, partial_exit=False, mixed_exit=False, completed=True), 'structure')
    else:
        mechanism, status, amount = 'UNRESOLVED', 'UNAVAILABLE', None
        ep['structure_evidence'] = proof(dict(kind='UNSUPPORTED_EPISODE', trade_identity=name, structure=structure), 'structure')
    instruction = dict(instruction_id=name+'initial', instruction_revision=1, full_content_sha256='a'*64) if mechanism == 'INITIAL_PROTECTIVE_STOP' else None
    attr = dict(mechanism=mechanism, original_instruction=instruction, evidence_reference=None)
    terminal = digest(ep['terminal_group']) if ep['terminal_group'] else None
    if mechanism != 'UNRESOLVED':
        attr['evidence_reference'] = proof(dict(kind='TERMINAL_CAUSATION', trade_identity=name, terminal_group_sha256=terminal, mechanism=mechanism, original_instruction=instruction), 'causation')
    net = dict(interpretation_id=owner._NET, interpretation_version='1', status=status, amount=amount,
        currency='USD' if amount is not None else None, episode_reference=name, terminal_execution_group_reference=terminal,
        provenance=provenance(), available_at=at, interpretation_evidence=None)
    if status == 'FINAL_COMPLETE':
        net['interpretation_evidence'] = proof(dict(kind='NET_ECONOMICS', trade_identity=name, terminal_group_sha256=terminal,
            interpretation_id=owner._NET, interpretation_version='1', all_required_components_incorporated=True,
            amount=amount, currency='USD'), 'net')
    return dict(contract=owner.TRADE_CONTRACT, rule_version=owner.TRADE_RULE, account_binding=deepcopy(q['own_policy']['account_binding']),
        trade_identity=name, evidence_revision=revision, source=deepcopy(SOURCE), available_at=at,
        predecessor_reference=predecessor, episode=ep, terminal_attribution=attr, realized_net_result=net,
        supporting_evidence=sorted(evidence,key=lambda e:e['evidence_id']))


def trade_ref(row):
    return dict(trade_identity=row['trade_identity'], evidence_revision=row['evidence_revision'], full_content_sha256=digest(row))


def coverage(q, effective=None, complete=True):
    day = owner._day(deepcopy(q['timezone_evidence']), q['own_policy'], owner._time(q['assessment_economic_time']), owner._time(q['knowledge_boundary']))
    effective = q['actual_trade_evidence'] if effective is None else effective
    interval = dict(start=day['utc_start'], end=q['assessment_economic_time'], start_inclusive=True, end_inclusive=True)
    q['trade_coverage'] = [dict(contract=owner.COVERAGE_CONTRACT, rule_version=owner.COVERAGE_RULE, coverage_id='coverage', coverage_revision=1,
        account_binding=deepcopy(q['own_policy']['account_binding']), source=deepcopy(SOURCE), available_at=q['knowledge_boundary'],
        trade_unit_model=owner._UNIT, day_binding=day, requested_close_interval=interval, covered_close_interval=deepcopy(interval),
        inventory_completeness='COMPLETE' if complete else 'PARTIAL', effective_population_references=sorted([trade_ref(r) for r in effective if owner._relevant(r,day,owner._time(q['assessment_economic_time']))],key=lambda r:(r['trade_identity'],r['evidence_revision'])),
        unresolved_population='NONE', correction_knowledge_cutoff=q['knowledge_boundary'])]


@pytest.fixture(scope='module')
def baseline():
    original = {'LONG': measurements.formulation_input('LONG')}
    m = measurements.sample(original)
    a = accounts.sample()
    a['requested_evaluation_timestamp'] = T
    a['observation']['account']['account_id'] = 'exact-account'
    a['observation']['source'] = deepcopy(SOURCE)
    a['observation']['timing'] = dict(effective_at=T, observed_at=T, source_available_at=T)
    a['observation']['account_measures'].update(balance='10000',equity='10000',free_margin='10000')
    a['observation']['positions']['items'] = []
    r = regimes.sample()
    s = accounts.run(a)
    binding = {k:v for k,v in SOURCE.items() if k != 'source_snapshot_id'} | dict(account_id='exact-account',environment='DEMO')
    tz_binding = dict(timezone_id='Europe/Amsterdam', tzdb_release='2026e-rearguard',tzif_sha256=sha256(base64.b64decode(TZIF)).hexdigest())
    q = dict(contract=owner.CONTRACT,rule_version=owner.RULE_VERSION,assessment_economic_time=T,knowledge_boundary=T,operation_mode='AUTOMATED',
        account_state=dict(snapshot=s,snapshot_input=a), candidate=dict(formulation=m['candidate_formulation'],formulation_input=m['formulation_input']),
        financial_measurement=dict(assessment=measurements.run(m),measurement_input=m), account_rule_regime=dict(assessment=regimes.run(r),assessment_input=r),
        own_policy=dict(contract=owner.POLICY_CONTRACT,rule_version=owner.POLICY_RULE,policy_id='own',policy_revision=1,account_binding=binding,
            effective_from=EARLY,effective_until=END,available_at=EARLY,provenance=provenance(),
            equity_admissibility=dict(mode='EXACT_TIME',account_measure_source_binding=deepcopy(SOURCE)),timezone_binding=tz_binding),
        timezone_evidence=dict(**tz_binding,tzif_base64=TZIF,provenance=provenance(),available_at=EARLY),
        actual_trade_evidence=[],trade_coverage=[],financial_compatibility=[],provider_operands=[])
    compatibility(q); coverage(q)
    for fact in selected(q)['body']['required_facts']: operand(q,'ACCOUNT_FACT',dict(fact=fact,value=True))
    return q


@pytest.fixture
def q(baseline):
    return deepcopy(baseline)


def run(q):
    return owner.evaluate_account_specific_risk_policy(q)


def daily(q):
    return run(q)['own_policy']['daily_loss_gate']


def test_satisfied_reconstruction_and_authority(q):
    before = deepcopy(q); result = run(q)
    assert result['overall_outcome'] == 'SATISFIED'
    assert result['own_policy']['target_monetary_risk'] == '100'
    assert result['authority'] == dict(trade_decision=False,financial_risk=False,execution=False)
    assert result['execution'] is False
    assert owner.validate_account_specific_risk_policy(result,q) == result
    assert q == before
    ident = result.pop('assessment_identity')
    assert ident == 'account_specific_risk_policy_' + digest(result)


def test_tamper_and_altered_input(q):
    result = run(q); result['own_policy']['target_monetary_risk'] = '101'
    with pytest.raises(ValueError): owner.validate_account_specific_risk_policy(result,q)
    result = run(q); q['own_policy']['provenance']['record_id'] = 'other'
    with pytest.raises(ValueError): owner.validate_account_specific_risk_policy(result,q)
    assert run(q)['assessment_identity'] != result['assessment_identity']


@pytest.mark.parametrize('part,field',[('account_state','snapshot'),('candidate','formulation'),('financial_measurement','assessment'),('account_rule_regime','assessment')])
def test_reconstruct_each_owner(q,part,field):
    q[part][field]['authority']['execution'] = True
    with pytest.raises(ValueError): run(q)


@pytest.mark.parametrize('amount,outcome,budget',[('0','NOT_SATISFIED',None),('-1','NOT_SATISFIED',None),(None,'UNKNOWN',None),('0.000000000001','SATISFIED','0.00000000000001'),('12345678901234567890.123456789','SATISFIED','123456789012345678.90123456789')])
def test_equity_exact_and_no_balance_fallback(q,amount,outcome,budget):
    q['account_state']['snapshot_input']['observation']['account_measures'].update(equity=amount,completeness='PARTIAL' if amount is None else 'COMPLETE')
    refresh_account(q)
    with localcontext() as ctx:
        ctx.prec=3; result=run(q)
    assert result['own_policy']['equity_gate']['outcome'] == outcome
    assert result['own_policy']['target_monetary_risk'] == budget


@pytest.mark.parametrize('mode,age,limit,expected',[('EXACT_TIME',1,None,'UNKNOWN'),('MAX_AGE',1,1,'SATISFIED'),('MAX_AGE',2,1,'UNKNOWN'),('MAX_AGE',0,0,'SATISFIED')])
def test_freshness(q,mode,age,limit,expected):
    from datetime import timedelta
    timing=q['account_state']['snapshot_input']['observation']['timing']
    timing['effective_at']=owner._stamp(owner._time(T)-timedelta(microseconds=age))
    p=q['own_policy']['equity_admissibility']; p['mode']=mode
    if limit is not None: p['maximum_age_microseconds']=limit
    refresh_account(q)
    assert run(q)['own_policy']['equity_gate']['outcome']==expected


@pytest.mark.parametrize('bad',[True,-1,1.0,'1',None])
def test_age_type(q,bad):
    q['own_policy']['equity_admissibility'].update(mode='MAX_AGE',maximum_age_microseconds=bad)
    with pytest.raises(ValueError): run(q)


@pytest.mark.parametrize('instant,start,end',[
    (T,'2026-01-09T23:00:00.000000Z','2026-01-10T23:00:00.000000Z'),
    ('2026-03-29T12:00:00Z','2026-03-28T23:00:00.000000Z','2026-03-29T22:00:00.000000Z'),
    ('2026-10-25T12:00:00Z','2026-10-24T22:00:00.000000Z','2026-10-25T23:00:00.000000Z'),
    ('2026-01-09T23:00:00Z','2026-01-09T23:00:00.000000Z','2026-01-10T23:00:00.000000Z')])
def test_bound_timezone_days(q,instant,start,end):
    day=owner._day(q['timezone_evidence'],q['own_policy'],owner._time(instant),owner._time(END))
    assert (day['utc_start'],day['utc_end_exclusive'])==(start,end)
    assert 'ZoneInfo("Europe/Amsterdam")' not in inspect.getsource(owner)


@pytest.mark.parametrize('case',['digest','release','zone','base64','malformed','post_k'])
def test_timezone_rejections(q,case):
    e=q['timezone_evidence']
    if case=='digest': e['tzif_sha256']='0'*64
    if case=='release': e['tzdb_release']='other'
    if case=='zone': e['timezone_id']='UTC'
    if case=='base64': e['tzif_base64']='!'
    if case=='post_k': e['available_at']=END
    if case=='malformed':
        raw=b'TZif2'+b'\0'*4; e['tzif_base64']=base64.b64encode(raw).decode(); e['tzif_sha256']=sha256(raw).hexdigest(); q['own_policy']['timezone_binding']['tzif_sha256']=e['tzif_sha256']
    with pytest.raises(ValueError): run(q)


@pytest.mark.parametrize('mechanism,amount,status,count',[
    ('INITIAL_PROTECTIVE_STOP','-1','FINAL_COMPLETE',1),('INITIAL_PROTECTIVE_STOP','0','FINAL_COMPLETE',0),
    ('INITIAL_PROTECTIVE_STOP','1','FINAL_COMPLETE',0),('INITIAL_PROTECTIVE_STOP','-1','PROVISIONAL',0),
    ('INITIAL_PROTECTIVE_STOP',None,'UNAVAILABLE',0),('BREAK_EVEN_STOP','-1','FINAL_COMPLETE',0),
    ('PROTECTED_PROFIT_STOP','-1','FINAL_COMPLETE',0),('AMENDED_STOP','-1','FINAL_COMPLETE',0),
    ('TARGET','-1','FINAL_COMPLETE',0),('MANUAL','-1','FINAL_COMPLETE',0),('OTHER','-1','FINAL_COMPLETE',0),
    ('UNRESOLVED','-1','FINAL_COMPLETE',0)])
def test_classification(q,mechanism,amount,status,count):
    q['actual_trade_evidence']=[trade(q,mechanism=mechanism,amount=amount,status=status)]; coverage(q)
    assert daily(q)['established_qualifying_count']==count


@pytest.mark.parametrize('structure',['SCALE_IN','PARTIAL_EXIT','MIXED_EXIT','INSEPARABLE_NETTING','INSEPARABLE_REVERSAL','UNRESOLVED'])
def test_unsupported_visible(q,structure):
    q['actual_trade_evidence']=[trade(q,structure=structure)]; coverage(q)
    assert daily(q)['outcome']=='UNKNOWN'
    q['trade_coverage'][0]['effective_population_references']=[]
    with pytest.raises(ValueError): run(q)


@pytest.mark.parametrize('count,complete,possible,expected',[(0,True,False,'SATISFIED'),(0,False,False,'UNKNOWN'),(1,True,False,'SATISFIED'),(1,False,False,'UNKNOWN'),(1,True,True,'UNKNOWN'),(2,False,True,'NOT_SATISFIED')])
def test_daily_coverage_threshold(q,count,complete,possible,expected):
    q['actual_trade_evidence']=[trade(q,str(i)) for i in range(count)]
    if possible:q['actual_trade_evidence'].append(trade(q,'unresolved',status='PROVISIONAL'))
    coverage(q,complete=complete)
    assert daily(q)['outcome']==expected


@pytest.mark.parametrize('close,count',[('2026-01-09T22:59:59.999999Z',0),('2026-01-09T23:00:00.000000Z',1),(T,1)])
def test_close_boundaries(q,close,count):
    q['actual_trade_evidence']=[trade(q,close=close)]; coverage(q)
    assert daily(q)['established_qualifying_count']==count


def test_multifill_permutation_duplicate_and_wins_do_not_reset(q):
    q['actual_trade_evidence']=[trade(q,'a',fills=3),trade(q,'b',amount='1'),trade(q,'c')]; coverage(q)
    expected=run(q); assert expected['own_policy']['daily_loss_gate']['established_qualifying_count']==2
    q['actual_trade_evidence'].reverse(); q['actual_trade_evidence'].append(deepcopy(q['actual_trade_evidence'][0]))
    for r in q['actual_trade_evidence']:
        r['supporting_evidence'].reverse()
        r['episode']['entry_group']['member_execution_references'].reverse()
    q['provider_operands'].reverse();q['trade_coverage'][0]['effective_population_references'].reverse()
    assert run(q)==expected


@pytest.mark.parametrize('case',['no_group_proof','no_causation','wrong_instruction','net_episode','net_terminal','incomplete_net','same_revision','missing_predecessor','cross_trade','post_k'])
def test_trade_invalid(q,case):
    r=trade(q); q['actual_trade_evidence']=[r]; coverage(q)
    if case=='no_group_proof':r['episode']['entry_group']['evidence_reference']=None
    if case=='no_causation':r['terminal_attribution']['evidence_reference']=None
    if case=='wrong_instruction':r['terminal_attribution']['original_instruction']['instruction_revision']=2
    if case=='net_episode':r['realized_net_result']['episode_reference']='other'
    if case=='net_terminal':r['realized_net_result']['terminal_execution_group_reference']='0'*64
    if case=='incomplete_net':r['realized_net_result']['amount']=None
    if case=='same_revision':
        other=deepcopy(r);other['source']['source_snapshot_id']='other';q['actual_trade_evidence'].append(other)
    if case=='missing_predecessor':r['predecessor_reference']=dict(trade_identity='a',evidence_revision=99,full_content_sha256='0'*64)
    if case=='cross_trade':r['predecessor_reference']=dict(trade_identity='other',evidence_revision=1,full_content_sha256='0'*64)
    if case=='post_k':r['available_at']=END
    with pytest.raises(ValueError):run(q)


def test_correction_linear_and_day_move(q):
    a=trade(q,revision=9); b=trade(q,revision=2,predecessor=trade_ref(a),amount='1')
    q['actual_trade_evidence']=[b,a];coverage(q,effective=[b])
    assert daily(q)['established_qualifying_count']==0
    c=trade(q,revision=1,predecessor=trade_ref(b),close='2026-01-09T22:00:00.000000Z')
    q['actual_trade_evidence'].append(c);coverage(q,effective=[c]);assert daily(q)['established_qualifying_count']==0


def test_correction_branch(q):
    a=trade(q);b=trade(q,revision=2,predecessor=trade_ref(a));c=trade(q,revision=3,predecessor=trade_ref(a))
    q['actual_trade_evidence']=[a,b,c]
    with pytest.raises(ValueError):run(q)


@pytest.mark.parametrize('field',['end_inclusive','start_inclusive','correction_knowledge_cutoff'])
def test_coverage_insufficient(q,field):
    if field=='correction_knowledge_cutoff':q['trade_coverage'][0][field]=EARLY
    else:q['trade_coverage'][0]['covered_close_interval'][field]=False
    assert daily(q)['outcome']=='UNKNOWN'


@pytest.mark.parametrize('field',['candidate','account_snapshot','quantity_unit','specification','measurement'])
def test_compatibility_wrong_subject(q,field):
    q['financial_compatibility'][0]['subjects'][field]='wrong'
    with pytest.raises(ValueError):run(q)


def test_missing_compatibility_and_currency_scope(q):
    q['financial_compatibility']=[];assert run(q)['financial_compatibility']['outcome']=='UNKNOWN'
    q['account_state']['snapshot_input']['observation']['account']['currency']='EUR';refresh_account(q)
    result=run(q);assert result['financial_compatibility']['outcome']=='UNKNOWN'
    assert result['financial_compatibility']['historical_economic_time']==q['financial_measurement']['assessment']['economic_timestamp']
    assert result['financial_compatibility']['establishes_current_executable_risk'] is False


def test_failure_does_not_hide_unknown_or_invalid(q):
    q['actual_trade_evidence']=[trade(q,'a'),trade(q,'b')];coverage(q);q['financial_compatibility']=[]
    result=run(q);assert result['overall_outcome']=='NOT_SATISFIED';assert result['financial_compatibility']['outcome']=='UNKNOWN'
    q['provider_operands'][0]['body']['value']='invalid'
    with pytest.raises(ValueError):run(q)


@pytest.mark.parametrize('kind',['AUTOMATION_PERMISSION','INSTRUMENT_ACTION_PERMISSION','ACCOUNT_STATE_REQUIREMENT','STATIC_FLOOR','DAILY_RESET_FLOOR','POSITION_LIMIT','ACTION_WINDOW','UNSUPPORTED'])
def test_provider_basics(q,kind):
    set_rule(q,kind);result=run(q)['provider_policy']['rule_results'][0]
    expected='SATISFIED' if kind in ('AUTOMATION_PERMISSION','INSTRUMENT_ACTION_PERMISSION') else 'NOT_SATISFIED' if kind=='ACTION_WINDOW' else 'UNKNOWN'
    assert result['outcome']==expected


@pytest.mark.parametrize('kind',['AUTOMATION_PERMISSION','INSTRUMENT_ACTION_PERMISSION'])
def test_explicit_prohibition(q,kind):
    set_rule(q,kind,lambda r:r['body'].update(permission='PROHIBITED'))
    assert run(q)['overall_outcome']=='NOT_SATISFIED'


@pytest.mark.parametrize('value,expected',[(True,'SATISFIED'),(False,'NOT_SATISFIED'),(None,'UNKNOWN')])
def test_account_fact(q,value,expected):
    q['provider_operands']=[]
    for fact in selected(q)['body']['required_facts']:operand(q,'ACCOUNT_FACT',dict(fact=fact,value=value))
    assert run(q)['provider_policy']['rule_results'][0]['outcome']==expected


def floor_operands(q,initial='10000',financing='0',anchor=None):
    m=selected(q)['body']['measure']
    operand(q,'MEASURE_BINDING',dict(account_snapshot=artifact(q['account_state']['snapshot']),measure_kind=m['kind'],**{f:m[f] for f in ('currency','definition_refs','cost_treatment')}))
    operand(q,'INITIAL_REFERENCE',dict(reference='INITIAL_BALANCE',amount=initial,currency='USD'))
    operand(q,'COST_ADJUSTMENTS',dict(currency='USD',commissions=None,financing=financing,other_charges=None))
    if anchor is not None:operand(q,'RESET_ANCHOR',dict(reset_boundary=T,measure_kind='BALANCE',amount=anchor,currency='USD',unrepresented_adjustments=False))


@pytest.mark.parametrize('comparator,financing,expected',[('GREATER_THAN','1000','NOT_SATISFIED'),('GREATER_THAN_OR_EQUAL','1000','SATISFIED'),('GREATER_THAN','999','SATISFIED'),('GREATER_THAN_OR_EQUAL','1001','NOT_SATISFIED'),('GREATER_THAN',None,'UNKNOWN')])
def test_floor_comparators_and_costs(q,comparator,financing,expected):
    set_rule(q,'STATIC_FLOOR',lambda r:r['body'].update(compliant_when=comparator));floor_operands(q,financing=financing)
    result=run(q)['provider_policy']['rule_results'][0];assert result['outcome']==expected
    if expected!='UNKNOWN':assert result['establishes_post_entry_headroom'] is False


@pytest.mark.parametrize('anchor,expected',[('10500','SATISFIED'),('10501','NOT_SATISFIED'),(None,'UNKNOWN')])
def test_provider_reset_boundary(q,anchor,expected):
    def edit(r):
        r['body']['reset_schedule'].update(schedule_period=regimes.period(1,30),boundaries=[regimes.time(i) for i in range(1,31)])
    set_rule(q,'DAILY_RESET_FLOOR',edit);floor_operands(q,anchor=anchor)
    result=run(q);assert result['provider_policy']['rule_results'][0]['outcome']==expected
    assert result['derived_day']['utc_start']!=T


@pytest.mark.parametrize('committed,effect,complete,expected',[(0,'NEW_SEPARATE_POSITION',True,'SATISFIED'),(1,'NEW_SEPARATE_POSITION',True,'NOT_SATISFIED'),(1,'NO_COUNT_CHANGE',True,'SATISFIED'),(0,'UNKNOWN',True,'UNKNOWN'),(0,'QUANTITY_DEPENDENT',True,'SATISFIED'),(0,'QUANTITY_DEPENDENT',False,'UNKNOWN')])
def test_position_count(q,committed,effect,complete,expected):
    set_rule(q,'POSITION_LIMIT')
    operand(q,'POSITION_COUNT_CONTEXT',dict(account_snapshot=artifact(q['account_state']['snapshot']),inventory_complete=complete,commitments_complete=complete,committed_additional_positions=committed,count_effect=effect))
    result=run(q);assert result['provider_policy']['rule_results'][0]['outcome']==expected
    if effect=='QUANTITY_DEPENDENT' and complete:assert any(o['kind']=='QUANTITY_DEPENDENTENT_POSITION_COUNT'.replace('DEPENDENTENT','DEPENDENT') for o in result['outstanding_obligations'])


def test_conflicting_operands(q):
    operand(q,'ACCOUNT_FACT',dict(fact='ACCOUNT_ACTIVE',value=False))
    with pytest.raises(ValueError):run(q)


@pytest.mark.parametrize('field',['assessment_economic_time','knowledge_boundary'])
def test_inconsistent_temporal_context(q,field):
    q[field]=END if field=='assessment_economic_time' else EARLY
    with pytest.raises(ValueError):run(q)


@pytest.mark.parametrize('field',list('contract rule_version assessment_economic_time knowledge_boundary operation_mode account_state candidate financial_measurement account_rule_regime own_policy timezone_evidence actual_trade_evidence trade_coverage financial_compatibility provider_operands'.split()))
def test_top_level_exact_schema(q,field):
    del q[field]
    with pytest.raises(ValueError):run(q)


def retime(q, t=T, k=T):
    q.update(assessment_economic_time=t,knowledge_boundary=k)
    a=q['account_state']['snapshot_input'];a['requested_evaluation_timestamp']=k
    a['observation']['timing']=dict(effective_at=t,observed_at=k,source_available_at=k)
    refresh_account(q)
    r=q['account_rule_regime']['assessment_input'];r.update(economic_timestamp=t,requested_knowledge_boundary=k)
    r['manifest']['timing']['observed_at']=k;r['manifest']['coverage']['source_information_cutoff']=k
    q['account_rule_regime']['assessment']=regimes.run(regimes.refresh(r))
    q['provider_operands']=[]
    for fact in selected(q)['body'].get('required_facts',[]):operand(q,'ACCOUNT_FACT',dict(fact=fact,value=True))
    coverage(q)


def test_retrospective_correction_does_not_rewrite_earlier(q):
    first=trade(q,'a');second=trade(q,'b');q['actual_trade_evidence']=[first,second];coverage(q)
    original=run(q);assert original['overall_outcome']=='NOT_SATISFIED'
    later=deepcopy(q);k='2026-01-11T00:00:00.000000Z';retime(later,k=k)
    correction=trade(later,'a',revision=2,predecessor=trade_ref(first),amount='1')
    later['actual_trade_evidence'].append(correction);coverage(later,effective=[correction,second])
    result=run(later);assert result['overall_outcome']=='SATISFIED'
    assert result['assessment_economic_time']==T and result['knowledge_boundary']==k
    assert run(q)==original
    q['actual_trade_evidence'].append(correction)
    with pytest.raises(ValueError):run(q)


def test_successor_availability_before_parent(q):
    a=trade(q);b=trade(q,revision=2,predecessor=trade_ref(a),at='2026-01-09T23:45:00.000000Z')
    q['actual_trade_evidence']=[a,b]
    with pytest.raises(ValueError,match='predates predecessor'):run(q)


def test_cyclic_correction_claim(q):
    a=trade(q);b=trade(q,revision=2,predecessor=trade_ref(a));a['predecessor_reference']=trade_ref(b)
    q['actual_trade_evidence']=[a,b]
    with pytest.raises(ValueError):run(q)


def test_final_economics_cannot_predate_close(q):
    r=trade(q);r['realized_net_result']['available_at']=EARLY;q['actual_trade_evidence']=[r]
    with pytest.raises(ValueError,match='predates terminal close'):run(q)


def test_execution_reuse_rejected_after_proofs_rebound(q):
    a=trade(q,'a');b=trade(q,'b')
    # Rebind all source proofs coherently: only underlying execution reuse is invalid.
    old=b['episode']['entry_group'];old['member_execution_references']=deepcopy(a['episode']['entry_group']['member_execution_references'])
    group_support=next(e for e in b['supporting_evidence'] if e['evidence_id']=='ENTRY')
    group_support['content']['member_execution_references']=deepcopy(old['member_execution_references'])
    old['evidence_reference']=evidence_ref(group_support)
    structure=next(e for e in b['supporting_evidence'] if e['evidence_id']=='structure')
    structure['content']['entry_group_sha256']=digest(old);b['episode']['structure_evidence']=evidence_ref(structure)
    q['actual_trade_evidence']=[a,b];coverage(q)
    with pytest.raises(ValueError,match='reused'):run(q)


def test_gap_execution_is_not_price_based(q):
    r=trade(q);q['actual_trade_evidence']=[r];coverage(q)
    assert daily(q)['established_qualifying_count']==1
    # No exit price exists in this local contract: causation is bound source evidence.
    assert 'exit_price' not in r['terminal_attribution']
    r['terminal_attribution']=dict(mechanism='UNRESOLVED',original_instruction=None,evidence_reference=None)
    coverage(q);assert daily(q)['established_qualifying_count']==0


def test_future_account_rejected(q):
    later='2026-01-11T00:00:00.000000Z';retime(q,k=later)
    q['account_state']['snapshot_input']['observation']['timing']['effective_at']=later;refresh_account(q)
    with pytest.raises(ValueError,match='Future effective'):run(q)


@pytest.mark.parametrize('where',['own_policy','timezone_evidence','trade_coverage','financial_compatibility','provider_operands'])
def test_all_local_evidence_must_be_available(q,where):
    obj=q[where] if isinstance(q[where],dict) else q[where][0];obj['available_at']=END
    with pytest.raises(ValueError):run(q)


@pytest.mark.parametrize('field',['equity_gate','daily_loss_gate'])
def test_ineffective_policy_is_unresolved(q,field):
    q['own_policy']['effective_until']=T
    assert run(q)['own_policy'][field]['outcome']=='UNKNOWN'


def test_exact_time_forbids_max_age(q):
    q['own_policy']['equity_admissibility']['maximum_age_microseconds']=0
    with pytest.raises(ValueError):run(q)


def test_no_coverage_proves_nothing(q):
    q['trade_coverage']=[]
    assert daily(q)['outcome']=='UNKNOWN'


def test_incomplete_classification_is_bounded_by_inventory(q):
    q['actual_trade_evidence']=[trade(q,status='PROVISIONAL')];coverage(q)
    result=daily(q);assert result['inventory_coverage_adequate'] is True
    assert result['possible_qualifying_upper_bound']==1 and result['outcome']=='SATISFIED'


def test_compatibility_conflict_and_duplicate(q):
    expected=run(q);q['financial_compatibility']*=2;assert run(q)==expected
    q['financial_compatibility'][1]=deepcopy(q['financial_compatibility'][1]);q['financial_compatibility'][1]['source']['source_snapshot_id']='other'
    with pytest.raises(ValueError):run(q)


INSTRUMENT=dict(source_id='broker',source_contract='accounts',source_contract_version='1',environment='DEMO',instrument_id='XAUUSD')


def instrument_scope(r):
    r['instrument_scope']=dict(kind='EXACT_INSTRUMENTS',instruments=[deepcopy(INSTRUMENT)])


def bind_instrument(q, instrument=None):
    operand(q,'INSTRUMENT_BINDING',dict(candidate=artifact(q['candidate']['formulation']),provider_instrument=deepcopy(instrument or INSTRUMENT)))


def test_quantity_limit_remains_obligation(q):
    def edit(r):
        instrument_scope(r);r['body']=dict(type='POSITION_LIMIT',limit_kind='PER_POSITION_QUANTITY',quantity_unit='lot',maximum='2')
    set_rule(q,'POSITION_LIMIT',edit)
    assert run(q)['provider_policy']['rule_results'][0]['outcome']=='UNKNOWN'
    bind_instrument(q);result=run(q)
    assert result['overall_outcome']=='SATISFIED'
    obligation=next(o for o in result['outstanding_obligations'] if o['kind']=='QUANTITY_LIMIT')
    assert obligation['rule']==selected(q)
    assert not any(k in result for k in ('quantity','authorization','decision_time'))


def test_instrument_binding_required_and_scope(q):
    set_rule(q,'INSTRUMENT_ACTION_PERMISSION',instrument_scope)
    assert run(q)['provider_policy']['rule_results'][0]['outcome']=='UNKNOWN'
    bind_instrument(q);assert run(q)['provider_policy']['rule_results'][0]['outcome']=='SATISFIED'
    q['provider_operands']=[];bind_instrument(q,dict(INSTRUMENT,instrument_id='OTHER'))
    assert run(q)['provider_policy']['rule_results'][0]['reasons']==['RULE_OUTSIDE_BOUND_INSTRUMENT_SCOPE']


@pytest.mark.parametrize('mode,intervals,expected',[('PERMITTED_ONLY_WITHIN',[(1,20)],'SATISFIED'),('PROHIBITED_WITHIN',[(1,20)],'NOT_SATISFIED'),('PROHIBITED_WITHIN',[(1,10)],'SATISFIED')])
def test_action_window_semantics(q,mode,intervals,expected):
    set_rule(q,'ACTION_WINDOW',lambda r:r['body'].update(mode=mode,intervals=[regimes.period(a,b) for a,b in intervals]))
    assert run(q)['provider_policy']['rule_results'][0]['outcome']==expected


def test_action_window_missing_schedule_coverage(q):
    set_rule(q,'ACTION_WINDOW',lambda r:r['body'].update(schedule_period=regimes.period(1,10),intervals=[regimes.period(1,10)]))
    assert run(q)['provider_policy']['rule_results'][0]['outcome']=='UNKNOWN'


def test_absolute_floor(q):
    set_rule(q,'STATIC_FLOOR',lambda r:r['body'].update(threshold=dict(kind='ABSOLUTE',amount='10000'),compliant_when='GREATER_THAN_OR_EQUAL'))
    floor_operands(q);q['provider_operands']=[o for o in q['provider_operands'] if o['tag']!='INITIAL_REFERENCE']
    assert run(q)['provider_policy']['rule_results'][0]['outcome']=='SATISFIED'


@pytest.mark.parametrize('remove',['MEASURE_BINDING','INITIAL_REFERENCE','COST_ADJUSTMENTS'])
def test_floor_missing_required_operands(q,remove):
    set_rule(q,'STATIC_FLOOR');floor_operands(q);q['provider_operands']=[o for o in q['provider_operands'] if o['tag']!=remove]
    assert run(q)['provider_policy']['rule_results'][0]['outcome']=='UNKNOWN'


def test_position_inventory_incomplete(q):
    q['account_state']['snapshot_input']['observation']['positions']['completeness']='PARTIAL';refresh_account(q)
    set_rule(q,'POSITION_LIMIT')
    operand(q,'POSITION_COUNT_CONTEXT',dict(account_snapshot=artifact(q['account_state']['snapshot']),inventory_complete=False,commitments_complete=True,committed_additional_positions=0,count_effect='NEW_SEPARATE_POSITION'))
    assert run(q)['provider_policy']['rule_results'][0]['outcome']=='UNKNOWN'


def test_exact_position_scope_filters_other_instruments(q):
    q['account_state']['snapshot_input']['observation']['positions']['items']=[dict(position_id=str(i),instrument_id='OTHER',direction='LONG',quantity='1',quantity_unit='lot') for i in range(3)]
    refresh_account(q);set_rule(q,'POSITION_LIMIT',instrument_scope);bind_instrument(q)
    operand(q,'POSITION_COUNT_CONTEXT',dict(account_snapshot=artifact(q['account_state']['snapshot']),inventory_complete=True,commitments_complete=True,committed_additional_positions=0,count_effect='NEW_SEPARATE_POSITION'))
    assert run(q)['provider_policy']['rule_results'][0]['projected_count']==1


def test_unknown_effects_are_not_silently_omitted(q):
    set_rule(q,'AUTOMATION_PERMISSION',lambda r:r.update(effects=['UNKNOWN']))
    assert run(q)['provider_policy']['rule_results'][0]['outcome']=='UNKNOWN'


def test_lifetime_obligations(q):
    set_rule(q,'AUTOMATION_PERMISSION',lambda r:r.update(effects=['HOLDING']))
    assert any(o['kind']=='LATER_RULE_APPLICABILITY' for o in run(q)['outstanding_obligations'])


def test_absent_approved_regime(q):
    r=q['account_rule_regime']['assessment_input'];r['approvals']=[]
    q['account_rule_regime']['assessment']=regimes.run(r);q['provider_operands']=[]
    assert run(q)['provider_policy']['regime_gate']['outcome']=='UNKNOWN'


@pytest.mark.parametrize('field',['account_binding','rule_reference','supporting_evidence'])
def test_operand_wrong_bindings(q,field):
    q['provider_operands'][0][field]={} if field!='supporting_evidence' else []
    with pytest.raises(ValueError):run(q)


@pytest.mark.parametrize('bad',['NaN','Infinity','1e3',1.0,True])
def test_local_financial_plain_decimal_only(q,bad):
    r=trade(q);r['realized_net_result']['amount']=bad;q['actual_trade_evidence']=[r]
    with pytest.raises(ValueError):run(q)
