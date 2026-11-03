"""Genuine native replay; synthetic admissions prove local behavior, not authenticity."""
import base64
from copy import deepcopy
from datetime import datetime, timezone
from decimal import localcontext
from fractions import Fraction
from functools import lru_cache
import hashlib
import inspect
import json
import sys

import pytest

from ced_one.business_divisions.trading import xauusd_current_post_entry_provider_floor_headroom as owner
from tests import test_xauusd_current_entry_provider_measure_projection_basis as pf

T, EARLY, H, END, FUTURE = pf.T, pf.EARLY, pf.H, pf.END, pf.FUTURE
CONTEXTS = (*pf.CONTEXTS, "trusted_provider_floor_context")
TIMES = pf.TIMES


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def norm(value, key=None):
    if key == "provider_measure_projection":
        return deepcopy(value)
    if type(value) is dict:
        return {k: norm(v, k) for k, v in value.items()}
    if type(value) is list:
        rows = [norm(v) for v in value]
        field = {"originals": "evidence_id", "actors": "actor_id", "sources": "inventory_id",
                 "entries": "entry_id", "records": "record_id", "root_records": "record_id",
                 "entry_refs": "entry_id", "source_entries": "entry_id", "responsibilities": "actor_id"}.get(key)
        if field:
            return sorted(rows, key=lambda row: row[field])
        field = {"reports": "key", "rule_bindings": "rule_reference", "admissions": "target"}.get(key)
        if field:
            return sorted(rows, key=lambda row: canonical(row[field]))
        return sorted(rows, key=canonical)
    if value is not None and key in TIMES:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(
            timespec="microseconds").replace("+00:00", "Z")
    return value


def eref(original):
    return dict(evidence_id=original["evidence_id"], envelope_sha256=digest(norm(original)))


def entryref(entry):
    return dict(entry_id=entry["entry_id"], content_sha256=digest(norm(entry)))


def recordref(record):
    return dict(record_id=record["record_id"], content_sha256=digest(norm(record)))


def bundle(case):
    return case[0]["provider_measure_projection"]


def evidence(case):
    return case[0]["floor_evidence"]


def body(case):
    return evidence(case)["records"][0]["body"]


def floor(case, rule_id="settlement-balance"):
    return next(b for b in body(case)["rule_bindings"] if b["rule_reference"]["selector"]["rule_id"] == rule_id)


def native_pairs(case):
    return pf.pairs((bundle(case)["request"]["quantity_composition"]["request"],))


@lru_cache(maxsize=48)
def native(direction="LONG", mode="NETTING", amount="9000", comparator="GREATER_THAN_OR_EQUAL", reference=None,
           initial="10000", second=False, model="STATIC_FLOOR", balance=None, grid=None, charge=None, period_spelling=False, future_binding=False, native_change=None):
    up = deepcopy(pf.upstream(direction, mode, balance))
    p = pf.cf.financial(up)[0]["risk_policy"]["request"]
    g = p["account_rule_regime"]
    if native_change is not None:
        kind, start, stop = native_change
        manifest = g["assessment_input"]["manifest"]
        period = dict(effective_from=start, effective_until=None if stop == "UNKNOWN" else stop,
                      end_status="UNKNOWN" if stop == "UNKNOWN" else "OPEN_ENDED" if stop is None else "KNOWN")
        assignment = manifest["assignments"][0]
        if kind == "PACKAGE":
            package = deepcopy(manifest["packages"][0])
            package["package_id"] = "zz-future-package"
            package["effective_period"] = deepcopy(period)
            manifest["packages"].append(package)
            binding = deepcopy(assignment["package_bindings"][0])
            binding["package"] = {k: package[k] for k in ("package_id", "package_revision")}
            binding["effective_period"] = deepcopy(period)
            assignment["package_bindings"].append(binding)
        else:
            assignment = deepcopy(assignment)
            assignment["assignment_id"] = "zz-future-assignment"
            assignment["enrollment_period"] = deepcopy(period)
            assignment["phase_period"] = deepcopy(period)
            manifest["assignments"].append(assignment)
    if future_binding:
        bindings = g["assessment_input"]["manifest"]["assignments"][0]["package_bindings"]
        continuation = deepcopy(bindings[0])
        bindings[0]["effective_period"].update(effective_until=FUTURE, end_status="KNOWN")
        continuation["effective_period"]["effective_from"] = FUTURE
        bindings.append(continuation)
    if period_spelling:
        period = g["assessment_input"]["manifest"]["packages"][0]["effective_period"]
        period["effective_from"] = datetime.fromisoformat(period["effective_from"].replace("Z", "+00:00")).isoformat()
    rule = next(r for r in g["assessment_input"]["manifest"]["packages"][0]["rules"] if r["rule_id"] == "settlement-balance")
    rule["body"]["threshold"] = dict(kind="ABSOLUTE", amount=amount) if reference is None else dict(
        kind="INITIAL_REFERENCE_FRACTION", reference=reference, fraction=amount)
    rule["body"]["compliant_when"] = comparator
    if second:
        other = deepcopy(rule)
        other["rule_id"] = "second-floor"
        other["body"]["threshold"] = dict(kind="ABSOLUTE", amount="9997")
        g["assessment_input"]["manifest"]["packages"][0]["rules"].append(other)
    if model == "UNSUPPORTED":
        other = pf.rf.rule("UNSUPPORTED")
        other["rule_id"] = "unrepresented-floor"
        other["effects"] = ["PAYOUT"]
        g["assessment_input"]["manifest"]["packages"][0]["rules"].append(other)
    elif model in ("DAILY_RESET_FLOOR", "EQUITY"):
        other = pf.rf.rule("DAILY_RESET_FLOOR" if model == "DAILY_RESET_FLOOR" else "STATIC_FLOOR")
        other["rule_id"] = "unrepresented-floor"
        other["effects"] = ["PAYOUT"]
        if model == "EQUITY":
            other["body"]["measure"]["kind"] = "EQUITY"
        g["assessment_input"]["manifest"]["packages"][0]["rules"].append(other)
    g["assessment"] = pf.rf.run(pf.rf.refresh(g["assessment_input"]))
    if reference is not None:
        selected = next(r for r in g["assessment"]["selected_regime"]["package"]["rules"] if r["rule_id"] == rule["rule_id"])
        rr = dict(rule_id=rule["rule_id"], full_content_sha256=hashlib.sha256(
            json.dumps(selected, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest())
        account = deepcopy(g["assessment"]["account"])
        obody = dict(reference=reference, amount=initial, currency="USD")
        assertion = dict(kind="PROVIDER_OPERAND", tag="INITIAL_REFERENCE", rule_reference=rr,
                         account_binding=account, effective_from=EARLY, effective_until=END, body=obody)
        source = deepcopy(p["provider_operands"][0]["source"])
        p["provider_operands"].append(dict(tag="INITIAL_REFERENCE", rule_reference=rr, account_binding=account,
            effective_from=EARLY, effective_until=END, source=source, available_at=T,
            supporting_evidence=[dict(evidence_id="original-initial", source=source, available_at=T, content=assertion)], body=obody))
    pf.cf.limits(up)[0]["account_rule_regime"] = deepcopy(g)
    if charge is not None:
        risk = pf.cf.financial(up)[0]["risk_basis"]["request"]
        risk["scenario_evidence"][0]["terms"]["charges"][0].update(zip(("fixed", "per_unit", "minimum"), charge))
        pf.cf.ff.rfixtures.align_policy(risk, up[1])
    pf.cf.rebuild_financial(up)
    up = pf.cf.rebuild_terminal(up)
    if grid is not None:
        up = pf.cf.change_grid(up, **dict(grid))
    case = pf.sample(native=up)
    assert pf.run(case)["outcome"] == "ESTABLISHED"
    return case


def _sample(**kwargs):
    up = deepcopy(native(**kwargs))
    projection = dict(assessment=pf.run(up), request=up[0])
    q = dict(contract=owner.CONTRACT, rule_version=owner.RULE_VERSION, assessment_economic_time=T,
        knowledge_boundary=T, scope=deepcopy(up[0]["scope"]), provider_measure_projection=projection, floor_evidence=None)
    p, r, a, g = pf.pairs((up[0]["quantity_composition"]["request"],))
    old = up[0]["projection_evidence"]
    originals, mappings = deepcopy(old["originals"]), deepcopy(old["native_mappings"])
    source = deepcopy(old["source"])
    originals.append(pf.original("floors", source, dict(synthetic=True, meaning="Complete native/source rule universe; endpoint force, exact measure, invariant thresholds, exceptions and authority"), T))
    refs = [eref(originals[-1])]
    for i, operand in enumerate(p["request"]["provider_operands"]):
        pairs = [("POLICY_OPERAND", dict(operand_index=i), operand)] + [(
            "POLICY_OPERAND_SUPPORT", dict(operand_index=i, evidence_index=j), row) for j, row in enumerate(operand["supporting_evidence"])]
        for kind, selector, node in pairs:
            original = pf.original("operand:" + kind + ":" + canonical(selector), node["source"], node, node["available_at"])
            originals.append(original)
            mappings.append(dict(native_reference=pf.nref(kind, p, node, selector), original_reference=eref(original),
                                 original_locator="complete original operand/support", relationship="ASSERTION_SUPPORT"))
    topics = sorted(owner.TOPIC_KINDS)
    ns = {k: source[k] for k in ("source_id", "source_contract", "source_contract_version")}
    keys = [dict(inventory_id="rulebook", actor_id="provider", topic=t) for t in topics]
    selected_package = g["assessment"]["selected_regime"]["package"]
    native_rules = [m["native_reference"] for m in mappings if m["native_reference"]["kind"] == "REGIME_RULE" and
                    all(m["native_reference"]["selector"][k] == selected_package[k] for k in ("package_id", "package_revision"))]
    entries = [dict(entry_id=ref["selector"]["rule_id"], report_key=next(k for k in keys if k["topic"] == "RULES"),
        source_record_id=ref["selector"]["rule_id"], kind="RULE", effective_period=dict(effective_from=EARLY, effective_until=None, end_status="OPEN_ENDED"),
        source_available_at=T, observed_at=T, disposition="MAPPED_NATIVE_RULE", native_rule_refs=[deepcopy(ref)], related_entry_ids=[], evidence_refs=deepcopy(refs)) for ref in native_rules]
    reports = [dict(key=key, source=deepcopy(source), state_at=T, source_information_cutoff=T, economic_from=T, economic_until=H,
        source_available_at=T, observed_at=T, inventory_completeness="COMPLETE", revision_completeness="COMPLETE",
        starting_basis="FROM_INCEPTION", entry_ids=sorted(e["entry_id"] for e in entries if e["report_key"] == key),
        missing_entry_ids=[], entries_omitted=False, history_truncated=False, evidence_refs=deepcopy(refs)) for key in keys]
    universe = dict(state_at=T, source_information_cutoff=T, economic_from=T, economic_until=H,
        source_universe_completeness="COMPLETE", actor_universe_completeness="COMPLETE",
        actors=[dict(actor_id="provider", namespace=ns, role="PROVIDER", topics=topics, evidence_refs=deepcopy(refs))],
        sources=[dict(inventory_id="rulebook", namespace=ns, role="RULEBOOK", responsibilities=[dict(actor_id="provider", topics=topics)], evidence_refs=deepcopy(refs))],
        reports=reports, entries=entries, evidence_refs=deepcopy(refs))

    def assertion(status):
        return dict(status=status, evidence_refs=deepcopy(refs))

    def closure():
        return dict(source_universe_completeness="COMPLETE", revision_completeness="COMPLETE", source_information_cutoff=T,
                    report_keys=deepcopy(keys), entry_refs=[], evidence_refs=deepcopy(refs))

    bindings = []
    for ref in native_rules:
        rid = ref["selector"]["rule_id"]
        is_floor = rid != "POSITION_LIMIT"
        operand = next((m["native_reference"] for m in mappings if m["native_reference"]["kind"] == "POLICY_OPERAND" and
                        p["request"]["provider_operands"][m["native_reference"]["selector"]["operand_index"]]["tag"] == "INITIAL_REFERENCE"), None) if rid == "settlement-balance" else None
        bindings.append(dict(rule_reference=deepcopy(ref), source_entries=[entryref(next(e for e in entries if e["entry_id"] == rid))],
            population=assertion("CONTAINS_SCENARIO"), endpoint=assertion("EXPLICIT_SETTLED_ENDPOINT" if is_floor else "OUTSIDE_SETTLED_ENDPOINT"),
            force=assertion("MANDATORY_UNCHANGED") if is_floor else None,
            exceptions=dict(resolution="NONE_APPLICABLE", closure=closure(), authority_actor_ids=[], authority_evidence_refs=[], precedence_evidence_refs=[], evidence_refs=deepcopy(refs)) if is_floor else None,
            measure=assertion("IDENTICAL") if rid != "unrepresented-floor" and is_floor else assertion("UNKNOWN") if is_floor else None,
            threshold=dict(relationship="NATIVE_COMPATIBLE", initial_reference_operand=operand, evidence_refs=deepcopy(refs)) if is_floor else None,
            horizon=dict(status="INVARIANT_AS_KNOWN_ON_T_H", closure=closure(), evidence_refs=deepcopy(refs)), evidence_refs=deepcopy(refs)))
    record = dict(record_id="floor-1", kind="DECLARE", predecessor=dict(kind="ROOT"), effective_from=T,
        effective_until=None, source_available_at=T, observed_at=T, evidence_refs=deepcopy(refs), body=dict(
            subjects=dict(projection_bundle_sha256=digest(projection), projection_basis_sha256=digest(projection["assessment"]["projection_basis"]),
                policy_bundle_sha256=digest(p), account_bundle_sha256=digest(a), regime_bundle_sha256=digest(g)),
            source_information_cutoff=T, economic_from=T, economic_until=H, universe=universe, rule_bindings=bindings))
    q["floor_evidence"] = dict(source=source, scope=deepcopy(q["scope"]), source_available_at=T, observed_at=T,
        originals=originals, native_mappings=mappings, records=[record], coverage=dict(economic_from=T, economic_until=H,
            source_information_cutoff=T, declaration_completeness="COMPLETE", revision_completeness="COMPLETE", starting_basis="FROM_INCEPTION",
            root_records=[recordref(record)], missing_record_ids=[], records_omitted=False, history_truncated=False,
            source_available_at=T, observed_at=T, evidence_refs=deepcopy(refs)))
    context = dict(contract=owner.ADMISSION_CONTRACT, rule_version=owner.ADMISSION_RULE_VERSION, admission_id="synthetic-floor-admission",
        authority_namespace=ns, authority_id="independent-fixture-issuer", mandate_id="floor-facts-only", mandate_revision=1,
        purpose=owner.ADMISSION_PURPOSE, request_content_sha256="0" * 64, knowledge_boundary=T, effective_from=EARLY,
        effective_until=END, admitted_at=T, available_at=T, admissions=[])
    return seal((q, *up[1:], context))


def support_for(q, target):
    """Independent fixture issuer implementing the frozen support-union table."""
    ev = q["floor_evidence"]
    current = next((r for r in ev["records"] if r["record_id"] == target.get("record_id")), None)
    if current is None:
        candidates = [r for r in ev["records"] if r["effective_from"] <= T and r["kind"] == "DECLARE"]
        current = candidates[-1] if candidates else ev["records"][0]
    b = current.get("body")
    u = None if b is None else b["universe"]
    mappings = ev["native_mappings"]
    allrefs = [m["native_reference"] for m in mappings]

    def union(rows):
        return sorted({canonical(x): x for x in rows}.values(), key=canonical)

    def e(node):
        return [] if node is None else union([r for k in ("evidence_refs", "authority_evidence_refs", "precedence_evidence_refs") for r in node.get(k, [])])

    def mapped(refs):
        refs = [r for r in refs if r is not None]
        clauses = [r for r in allrefs if r["kind"] == "REGIME_CLAUSE" and r["selector"]["container"] in refs]
        refs += clauses
        docs = [r for r in allrefs if r["kind"] == "REGIME_DOCUMENT"]
        # Fixture native clauses all refer to their genuine original terms document.
        if any(r["kind"] == "REGIME_CLAUSE" for r in refs):
            refs += docs
        return union([m["original_reference"] for m in mappings if m["native_reference"] in refs])

    def scope_refs(horizon=False):
        target = q["provider_measure_projection"]["assessment"]["measure_target"]
        refs = [r for r in allrefs if r["kind"] in ("ACCOUNT_BUNDLE", "REGIME_APPROVAL") or
                r in (target["assignment"], target["package"])]
        g = q["provider_measure_projection"]["request"]["quantity_composition"]["request"]["risk_budget_feasibility"]["request"]["risk_policy"]["request"]["account_rule_regime"]
        for ref in allrefs:
            if ref["kind"] == "REGIME_BINDING":
                if ref["selector"]["assignment_id"] != target["assignment"]["selector"]["assignment_id"]:
                    continue
                assignment = next(a for a in g["assessment_input"]["manifest"]["assignments"] if a["assignment_id"] == ref["selector"]["assignment_id"])
                binding = assignment["package_bindings"][ref["selector"]["binding_index"]]
                if binding["package"] != target["package"]["selector"]:
                    continue
                period = binding["effective_period"]
                start = norm(period["effective_from"], "effective_from")
                stop = norm(period["effective_until"], "effective_until")
                if (start < H if horizon else start <= T) and (stop is None or stop > T):
                    refs.append(ref)
        return refs

    def report_rows(key):
        report = next(r for r in u["reports"] if r["key"] == key)
        source = next(s for s in u["sources"] if s["inventory_id"] == key["inventory_id"])
        actor = next(a for a in u["actors"] if a["actor_id"] == key["actor_id"])
        return report, source, actor

    def report_e(key):
        return union([r for node in report_rows(key) for r in e(node)] + [r for entry in u["entries"] if entry["report_key"] == key for r in e(entry)])

    def entry_e(entry):
        return union(e(entry) + [r for node in report_rows(entry["report_key"]) for r in e(node)] + mapped(entry["native_rule_refs"]))

    kind = target["kind"]
    if kind == "DECLARATION_REVISION_COVERAGE":
        return union(e(ev["coverage"]) + [ref for row in ev["records"] for ref in e(row)])
    if kind == "REGIME_SCOPE":
        return union(e(current) + mapped(scope_refs()))
    if kind == "RULE_SOURCE_UNIVERSE":
        clauses = [r for r in allrefs if r["kind"] == "REGIME_CLAUSE" and r["selector"]["field"] == "COVERAGE_EVIDENCE_REFS"]
        return union(e(u) + [r for row in u["actors"] + u["sources"] for r in e(row)] + mapped(clauses))
    if kind == "SOURCE_REPORT":
        return report_e(target["report_key"])
    if kind == "SOURCE_ENTRY_DISPOSITION":
        return entry_e(next(e for e in u["entries"] if e["entry_id"] == target["entry_reference"]["entry_id"]))
    binding = next(row for row in b["rule_bindings"] if row["rule_reference"] == target["rule_reference"])
    refs = e(binding) + e(binding["population"]) + [r for er in binding["source_entries"] for r in entry_e(next(e for e in u["entries"] if e["entry_id"] == er["entry_id"]))]
    nr = [binding["rule_reference"]]
    if kind == "RULE_ENDPOINT_FORCE":
        refs += e(binding["endpoint"]) + e(binding["force"])
    elif kind in ("RULE_EXCEPTIONS", "RULE_HORIZON"):
        node = binding["exceptions" if kind == "RULE_EXCEPTIONS" else "horizon"]
        refs += e(node)
        if node is not None:
            refs += e(node["closure"])
            refs += [r for key in node["closure"]["report_keys"] for r in report_e(key)]
            refs += [r for er in node["closure"]["entry_refs"] for r in entry_e(next(e for e in u["entries"] if e["entry_id"] == er["entry_id"]))]
        if kind == "RULE_HORIZON":
            nr += scope_refs(horizon=True)
    elif kind == "RULE_MEASURE":
        refs += e(binding["measure"])
        nr += [r for r in allrefs if r["kind"] == "ACCOUNT_BUNDLE" or r["kind"] == "REGIME_MEASURE" and (
            r["selector"] == binding["rule_reference"]["selector"] or r["selector"]["rule_id"] == "settlement-balance")]
    elif kind == "RULE_THRESHOLD":
        refs += e(binding["threshold"])
        operand = None if binding["threshold"] is None else binding["threshold"]["initial_reference_operand"]
        if operand is not None:
            nr += [operand] + [r for r in allrefs if r["kind"] == "POLICY_OPERAND_SUPPORT" and r["selector"]["operand_index"] == operand["selector"]["operand_index"]]
    return union(refs + mapped(nr))


def seal(case, *, issue=True):
    q, *contexts = case
    ev = q["floor_evidence"]
    originals = {} if ev is None else {r["evidence_id"]: r for r in ev["originals"]}

    def refresh(node):
        if type(node) is dict:
            if set(node) == {"evidence_id", "envelope_sha256"} and node["evidence_id"] in originals:
                node.update(eref(originals[node["evidence_id"]]))
            else:
                for k, value in node.items():
                    if k != "provider_measure_projection":
                        refresh(value)
        elif type(node) is list:
            for value in node:
                refresh(value)
    refresh(q)
    context = contexts[-1]
    if ev is not None:
        for record in ev["records"]:
            if record["kind"] == "DECLARE":
                entries = {e["entry_id"]: e for e in record["body"]["universe"]["entries"]}

                def entrypins(node):
                    if type(node) is dict:
                        if set(node) == {"entry_id", "content_sha256"} and node["entry_id"] in entries:
                            node.update(entryref(entries[node["entry_id"]]))
                        else:
                            for value in node.values():
                                entrypins(value)
                    elif type(node) is list:
                        for value in node:
                            entrypins(value)
                entrypins(record["body"])
        done, pending = {}, list(ev["records"])
        while pending:
            ready = [r for r in pending if r["predecessor"]["kind"] != "RECORD" or r["predecessor"]["record"]["record_id"] in done or
                     r["predecessor"]["record"]["record_id"] not in {x["record_id"] for x in pending}]
            if not ready:
                break
            for record in ready:
                pred = record["predecessor"]
                if pred["kind"] == "RECORD" and pred["record"]["record_id"] in done:
                    pred["record"].update(recordref(done[pred["record"]["record_id"]]))
                done[record["record_id"]] = record
                pending.remove(record)
        for ref in ev["coverage"]["root_records"]:
            if ref["record_id"] in done:
                ref.update(recordref(done[ref["record_id"]]))
    if context is not None:
        if issue and ev is not None:
            candidates = [r for r in ev["records"] if r["effective_from"] <= T and r["kind"] == "DECLARE"]
            current = candidates[-1] if candidates else None
            targets = [dict(kind=k) for k in ("REGIME_SCOPE", "DECLARATION_REVISION_COVERAGE", "RULE_SOURCE_UNIVERSE")]
            if current is not None:
                rid = current["record_id"]
                targets += [dict(kind="SOURCE_REPORT", record_id=rid, report_key=r["key"]) for r in current["body"]["universe"]["reports"]]
                targets += [dict(kind="SOURCE_ENTRY_DISPOSITION", record_id=rid, entry_reference=entryref(e)) for e in current["body"]["universe"]["entries"]]
                targets += [dict(kind=k, record_id=rid, rule_reference=b["rule_reference"]) for b in current["body"]["rule_bindings"] for k in owner.RULE_TOPICS]
            context["admissions"] = [dict(target=t, status="ADMITTED", subject_content_sha256="0" * 64,
                                          evidence_refs=support_for(q, t)) for t in targets]
        context["request_content_sha256"] = digest(norm(q))
        projection = q["provider_measure_projection"]["assessment"]
        pins = deepcopy(projection["reconstruction_evidence"]["native_context_fingerprints"])
        pins["trusted_financial_projection_context_sha256"] = projection["reconstruction_evidence"]["trusted_financial_projection_context_sha256"]
        for receipt in context["admissions"]:
            receipt["subject_content_sha256"] = digest(dict(request_content_sha256=context["request_content_sha256"], native_context_fingerprints=pins, target=receipt["target"]))
    return case


@lru_cache(maxsize=48)
def cached_sample(key):
    return _sample(**dict(key))


def sample(**kwargs):
    return deepcopy(cached_sample(tuple(sorted(kwargs.items()))))


def run(case):
    return owner.evaluate_current_post_entry_provider_floor_headroom(case[0], **dict(zip(CONTEXTS, case[1:])))


def validate(result, case):
    return owner.validate_current_post_entry_provider_floor_headroom(result, case[0], **dict(zip(CONTEXTS, case[1:])))


@lru_cache(maxsize=1)
def genuine_result():
    """Reuse an actual computed positive as tampering input, never an owner mock."""
    return run(sample())


def independent_future_packet(case):
    """Structural-only cases need no native proof; historical refs stay inert."""
    case[0]["provider_measure_projection"] = None
    ev = evidence(case)
    ev["native_mappings"] = []
    for record in ev["records"]:
        record["effective_from"] = FUTURE
        if record["kind"] == "DECLARE":
            record["body"]["subjects"] = {k: None for k in record["body"]["subjects"]}
    return (case[0], *([None] * 7))


@pytest.fixture
def case():
    return sample()























def test_independent_no_owner_packet_is_well_formed(case):
    case = independent_future_packet(case)
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert result["owner_reference"] is None
    assert result["rule_results"] == []
    assert result["source_dispositions"] == []
    assert result["complete_predicate"] is None
    assert result["passing_domain"] is None


def test_missing_floor_packet_findings_address_existing_nullable_parent(case):
    case[0]["floor_evidence"] = None
    case = (*case[:-1], None)
    result = run(case)
    assert result["outcome"] == "UNKNOWN"
    assert "EVIDENCE_MISSING" in result["reason_codes"]
    for finding in result["unresolved_findings"]:
        if finding["subject"]["root"] == "REQUEST":
            pointer = finding["subject"]["pointer"]
            value = result["reconstruction_evidence"]["request"]
            for token in pointer.split("/")[1:]:
                token = token.replace("~1", "/").replace("~0", "~")
                value = value[int(token)] if type(value) is list else value[token]


def test_owned_normalization_cannot_mutate_aliased_native_original():
    case = sample(period_spelling=True)
    g = native_pairs(case)[3]
    period = g["assessment_input"]["manifest"]["packages"][0]["effective_period"]
    assert period["effective_from"].endswith("+00:00")
    next(e for e in body(case)["universe"]["entries"] if e["entry_id"] == "settlement-balance")["effective_period"] = period
    seal(case)
    original = deepcopy(bundle(case))
    result = run(case)
    assert result["outcome"] == "ESTABLISHED", result["unresolved_findings"]
    assert result["reconstruction_evidence"]["request"]["provider_measure_projection"] == original
    assert bundle(case) == original


@pytest.mark.parametrize("omit", [False, True])
def test_horizon_requires_original_support_for_future_contributing_binding(omit):
    case = sample(future_binding=True)
    if omit:
        mappings = evidence(case)["native_mappings"]
        mappings.remove(next(m for m in mappings if m["native_reference"]["kind"] == "REGIME_BINDING" and m["native_reference"]["selector"]["binding_index"] == 1))
    result = run(seal(case))
    assert result["outcome"] == ("UNKNOWN" if omit else "ESTABLISHED"), result["unresolved_findings"]
    if omit:
        assert "NATIVE_SUPPORT_MISSING" in result["reason_codes"]


@pytest.mark.parametrize("indirect", [False, True])
def test_known_unresolved_defeater_suppresses_scoped_negative(indirect):
    case = sample(amount="10000")
    bridge = add_entry(case, "unresolved-waiver", "WAIVER", disposition="UNRESOLVED")
    if indirect:
        bridge["native_rule_refs"] = []
        bridge["related_entry_ids"] = ["settlement-balance"]
        change = add_entry(case, "indirect-change", "THRESHOLD_CHANGE", effective=FUTURE, disposition="UNRESOLVED")
        change["native_rule_refs"] = []
        change["related_entry_ids"] = [bridge["entry_id"]]
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert result["negative_proofs"] == []
    assert row(result)["headroom"] is None
    assert "SOURCE_ENTRY_UNRESOLVED" in result["reason_codes"]


def test_distinct_rule_findings_preserve_independent_obligations():
    case = sample(second=True)
    floor(case)["force"]["status"] = "UNKNOWN"
    floor(case, "second-floor")["force"]["status"] = "UNKNOWN"
    result = run(seal(case))
    failures = [f for f in result["unresolved_findings"] if f["reason_code"] == "FORCE_UNRESOLVED"]
    assert len(failures) == 2
    assert len({f["subject"]["pointer"] for f in failures}) == 2
    assert result["outcome"] == "UNKNOWN"


def test_explicit_declare_after_withdrawal(case):
    first = evidence(case)["records"][0]
    first["effective_from"] = EARLY
    withdrawal = successor(case, kind="WITHDRAW", effective=T)
    replacement = deepcopy(first)
    replacement.update(record_id="floor-3", effective_from=T, predecessor=dict(kind="RECORD", record=recordref(withdrawal)))
    evidence(case)["records"].append(replacement)
    result = run(seal(case))
    assert result["outcome"] == "ESTABLISHED", result["unresolved_findings"]
    assert result["resolved_record"]["record_id"] == "floor-3"


def test_unknown_native_diagnostics_are_owned_and_preserved():
    case = sample()
    p6 = bundle(case)
    upstream = (p6["request"], *case[1:7])
    upstream = (*upstream[:-1], None)
    p6["assessment"] = pf.run(upstream)
    case = (case[0], *case[1:6], None, case[-1])
    body(case)["subjects"]["projection_bundle_sha256"] = digest(p6)
    body(case)["subjects"]["projection_basis_sha256"] = None
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert result["supported_domain"] is None
    assert result["negative_proofs"] == []
    for target, original in (("native_diagnostics", "native_diagnostics"), ("native_unresolved_findings", "unresolved_findings"),
        ("native_conditions", "conditions"), ("native_limitations", "limitations")):
        assert result[target] == p6["assessment"][original]


@pytest.mark.parametrize("comparator,last", [("GREATER_THAN_OR_EQUAL", "15"), ("GREATER_THAN", "14")])
def test_fixed_minimum_fee_crossover(comparator, last):
    result = run(sample(amount="9996.5", comparator=comparator, charge=("0.5", "10", "2"), grid=(("step", "0.01"),)))
    assert result["outcome"] == "ESTABLISHED", result["unresolved_findings"]
    assert result["passing_domain"]["domain"]["last_index"] == last
    assert row(result)["headroom"]["threshold_amount"] == "9996.5"


@pytest.mark.parametrize("reference", ["INITIAL_BALANCE", "INITIAL_EQUITY"])
@pytest.mark.parametrize("initial,amount,last", [("10000", "0.9997", "1"), ("-10000", "1", "2"), ("10000", "0", "2")])
def test_original_fractional_operands(reference, initial, amount, last):
    case = sample(reference=reference, initial=initial, amount=amount)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED", result["unresolved_findings"]
    assert result["passing_domain"]["domain"]["last_index"] == last
    descriptor = row(result)["headroom"]
    assert Fraction(descriptor["threshold_amount"]) == Fraction(initial) * Fraction(amount)
    assert descriptor["initial_reference_operand"] == floor(case)["threshold"]["initial_reference_operand"]


@pytest.mark.parametrize("kind", ["DECLARE", "WITHDRAW"])
@pytest.mark.parametrize("effective,expected", [(FUTURE, "UNKNOWN"), (H, "ESTABLISHED"), (T, "CURRENT")])
def test_whole_declaration_successors(case, kind, effective, expected):
    successor(case, kind=kind, effective=effective)
    result = run(seal(case))
    wanted = "UNKNOWN" if expected == "CURRENT" and kind == "WITHDRAW" else "ESTABLISHED" if expected == "CURRENT" else expected
    assert result["outcome"] == wanted, result["unresolved_findings"]
    if effective == T:
        assert result["resolved_record"]["record_id"] == "floor-2"



@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
@pytest.mark.parametrize("mode", ["NETTING", "HEDGING"])
def test_genuine_positive(direction, mode):
    case = sample(direction=direction, mode=mode)
    before = deepcopy(case)
    result = run(case)
    assert result["outcome"] == "ESTABLISHED", result["unresolved_findings"]
    assert result["passing_domain"] == result["supported_domain"]
    assert row(result, "POSITION_LIMIT")["disposition"] == "OTHER_OBLIGATION"
    if direction == "LONG" and mode == "NETTING":
        assert validate(result, case) == result
    assert case == before


def row(result, rid="settlement-balance"):
    return next(r for r in result["rule_results"] if r["rule_reference"]["selector"]["rule_id"] == rid)


@pytest.mark.parametrize("amount,comparator,outcome,last", [
    ("-10", "GREATER_THAN", "ESTABLISHED", "2"),
    ("0", "GREATER_THAN_OR_EQUAL", "ESTABLISHED", "2"),
    ("9996", "GREATER_THAN_OR_EQUAL", "ESTABLISHED", "2"),
    ("9996", "GREATER_THAN", "ESTABLISHED", "1"),
    ("9997", "GREATER_THAN_OR_EQUAL", "ESTABLISHED", "1"),
    ("9997", "GREATER_THAN", "NOT_SUITABLE", None),
    ("10000", "GREATER_THAN_OR_EQUAL", "NOT_SUITABLE", None),
])
def test_exact_prefixes(amount, comparator, outcome, last):
    result = run(sample(amount=amount, comparator=comparator))
    assert result["outcome"] == outcome, result["unresolved_findings"]
    rr = row(result)
    assert rr["headroom"]["threshold_amount"] == amount
    if last is None:
        assert result["passing_domain"]["domain"] == {"kind": "EMPTY"}
        assert result["negative_proofs"][0]["kind"] == "ALL_C_EXCLUDED"
        assert rr["rule_excluded_domain"] == result["supported_domain"]
    else:
        assert result["passing_domain"]["domain"]["last_index"] == last
        assert rr["rule_passing_domain"] == result["passing_domain"]
        assert bool(result["negative_proofs"]) == (last == "1")




def test_multiple_simultaneous_floors():
    result = run(sample(second=True))
    assert result["outcome"] == "ESTABLISHED", result["unresolved_findings"]
    assert len(result["complete_predicate"]["rule_references"]) == 2
    assert result["passing_domain"]["domain"]["last_index"] == "1"
    assert row(result, "second-floor")["headroom"]["threshold_amount"] == "9997"


@pytest.mark.parametrize("model", ["UNSUPPORTED", "DAILY_RESET_FLOOR", "EQUITY"])
def test_relevant_unsupported_requirement(model):
    result = run(sample(model=model))
    assert result["outcome"] == "UNKNOWN"
    assert result["passing_domain"] is None
    assert row(result, "unrepresented-floor")["disposition"] == "UNRESOLVED"
    assert "RULE_MODEL_UNSUPPORTED" in result["reason_codes"] or "MEASURE_UNSUPPORTED" in result["reason_codes"]


@pytest.mark.parametrize("amount,expected,kind", [("10000", "NOT_SUITABLE", "ALL_C_EXCLUDED"), ("9997", "UNKNOWN", "SUFFIX_EXCLUDED")])
def test_negative_with_unrelated_unknown(amount, expected, kind):
    case = sample(amount=amount)
    body(case)["universe"]["source_universe_completeness"] = "LIMITED"
    result = run(seal(case))
    assert result["outcome"] == expected, result["unresolved_findings"]
    assert result["complete_predicate"] is None
    assert result["negative_proofs"][0]["kind"] == kind
    assert row(result)["headroom"] is not None
    assert (result["passing_domain"] is None) == (expected == "UNKNOWN")
    assert "SOURCE_UNIVERSE_INCOMPLETE" in result["reason_codes"]


def test_partial_negative_with_unrepresented_rule():
    result = run(sample(amount="9997", model="UNSUPPORTED"))
    assert result["outcome"] == "UNKNOWN"
    assert result["passing_domain"] is None
    assert result["negative_proofs"][0]["kind"] == "SUFFIX_EXCLUDED"
    assert row(result)["rule_passing_domain"]["domain"]["last_index"] == "1"


@pytest.mark.parametrize("section,field,value,code", [
    ("population", "status", "UNKNOWN", "POPULATION_UNRESOLVED"),
    ("endpoint", "status", "UNKNOWN", "ENDPOINT_UNRESOLVED"),
    ("force", "status", "NOT_MANDATORY", "FORCE_UNRESOLVED"),
    ("exceptions", "resolution", "UNKNOWN", "EXCEPTIONS_UNRESOLVED"),
    ("exceptions", "resolution", "MODIFIES_NATIVE_PREDICATE", "EXCEPTIONS_UNRESOLVED"),
    ("measure", "status", "UNKNOWN", "MEASURE_IDENTITY_UNRESOLVED"),
    ("measure", "status", "INCOMPATIBLE", "MEASURE_IDENTITY_UNRESOLVED"),
    ("threshold", "relationship", "UNKNOWN", "THRESHOLD_OPERAND_UNRESOLVED"),
    ("threshold", "relationship", "INCOMPATIBLE", "THRESHOLD_OPERAND_UNRESOLVED"),
    ("horizon", "status", "UNKNOWN", "HORIZON_UNRESOLVED"),
    ("horizon", "status", "KNOWN_RELEVANT_CHANGE_BEFORE_H", "HORIZON_CHANGE"),
])
def test_rule_semantic_unknowns(case, section, field, value, code):
    floor(case)[section][field] = value
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert code in result["reason_codes"]
    assert row(result)["headroom"] is None
    assert not result["negative_proofs"]


@pytest.mark.parametrize("section", ["endpoint", "force", "exceptions", "measure", "threshold", "horizon"])
def test_nullable_rule_evidence(case, section):
    floor(case)[section] = None
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert row(result)["disposition"] == "UNRESOLVED"


@pytest.mark.parametrize("disposition", ["DISJOINT_POPULATION", "OUTSIDE_SETTLED_ENDPOINT"])
def test_no_floor_vacuity(case, disposition):
    if disposition == "DISJOINT_POPULATION":
        floor(case)["population"]["status"] = "DISJOINT"
    else:
        floor(case)["endpoint"]["status"] = "OUTSIDE_SETTLED_ENDPOINT"
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert row(result)["disposition"] == disposition
    assert "NO_SUPPORTED_APPLICABLE_FLOOR" in result["reason_codes"]
    assert result["complete_predicate"] is None


def add_entry(case, identifier, kind, *, effective=EARLY, disposition="SUPPORTING_RULE_EVIDENCE", rule_id="settlement-balance"):
    u = body(case)["universe"]
    topic = next(t for t, kinds in owner.TOPIC_KINDS.items() if kind in kinds)
    report = next(r for r in u["reports"] if r["key"]["topic"] == topic)
    entry = dict(entry_id=identifier, report_key=deepcopy(report["key"]), source_record_id=identifier, kind=kind,
        effective_period=dict(effective_from=effective, effective_until=None, end_status="OPEN_ENDED"),
        source_available_at=T, observed_at=T, disposition=disposition, native_rule_refs=[deepcopy(floor(case, rule_id)["rule_reference"])],
        related_entry_ids=[], evidence_refs=deepcopy(u["evidence_refs"]))
    u["entries"].append(entry)
    report["entry_ids"].append(identifier)
    return entry


def test_supported_whole_horizon_waiver(case):
    waiver = add_entry(case, "waiver", "WAIVER")
    b = floor(case)
    b["force"]["status"] = "NOT_MANDATORY"
    b["exceptions"].update(resolution="WAIVED_THROUGHOUT", authority_actor_ids=["provider"],
        authority_evidence_refs=deepcopy(b["evidence_refs"]), precedence_evidence_refs=deepcopy(b["evidence_refs"]))
    b["exceptions"]["closure"]["entry_refs"] = [entryref(waiver)]
    result = run(seal(case))
    assert row(result)["disposition"] == "WAIVED_THROUGHOUT", result["unresolved_findings"]
    assert result["outcome"] == "UNKNOWN"
    assert result["passing_domain"] is None
    assert "NO_SUPPORTED_APPLICABLE_FLOOR" in result["reason_codes"]


@pytest.mark.parametrize("where", ["exceptions", "horizon"])
def test_incomplete_own_closure_suppresses_negative(where):
    case = sample(amount="10000")
    floor(case)[where]["closure"]["source_universe_completeness"] = "UNKNOWN"
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert result["negative_proofs"] == []


@pytest.mark.parametrize("effective,expected", [(FUTURE, "UNKNOWN"), (H, "ESTABLISHED"), (END, "ESTABLISHED")])
def test_known_rule_change(effective, expected, case):
    add_entry(case, "threshold-change", "THRESHOLD_CHANGE", effective=effective)
    result = run(seal(case))
    assert result["outcome"] == expected, result["unresolved_findings"]
    assert ("HORIZON_CHANGE" in result["reason_codes"]) == (expected == "UNKNOWN")


@pytest.mark.parametrize("kind", ["REGIME_SCOPE", "DECLARATION_REVISION_COVERAGE", "RULE_SOURCE_UNIVERSE", "RULE_DISPOSITION",
    "RULE_ENDPOINT_FORCE", "RULE_EXCEPTIONS", "RULE_MEASURE", "RULE_THRESHOLD", "RULE_HORIZON", "SOURCE_REPORT", "SOURCE_ENTRY_DISPOSITION"])
@pytest.mark.parametrize("status", ["MISSING", "UNRESOLVED", "INCOMPLETE"])
def test_required_receipts(case, kind, status):
    context = case[-1]
    candidates = [r for r in context["admissions"] if r["target"]["kind"] == kind]
    target = next((r for r in candidates if r["target"].get("rule_reference", {}).get("selector", {}).get("rule_id") == "settlement-balance"), candidates[0])
    if status == "MISSING":
        context["admissions"].remove(target)
    elif status == "UNRESOLVED":
        target["status"] = "UNRESOLVED"
    else:
        if len(target["evidence_refs"]) > 1:
            target["evidence_refs"].pop()
        else:
            extra = next(o for o in evidence(case)["originals"] if o["evidence_id"] == "accounting")
            target["evidence_refs"].append(eref(extra))
    result = run(seal(case, issue=False))
    assert result["outcome"] == "UNKNOWN"
    code = {"MISSING": "RECEIPT_MISSING", "UNRESOLVED": "RECEIPT_UNRESOLVED", "INCOMPLETE": "RECEIPT_SUPPORT_MISMATCH"}[status]
    assert code in result["reason_codes"]


@pytest.mark.parametrize("field", ["source_universe_completeness", "actor_universe_completeness"])
@pytest.mark.parametrize("state", ["LIMITED", "UNKNOWN"])
def test_global_universe_unknown(case, field, state):
    body(case)["universe"][field] = state
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert row(result)["headroom"] is not None
    assert result["passing_domain"] is None


@pytest.mark.parametrize("field", ["inventory_completeness", "revision_completeness", "source_information_cutoff", "source_available_at", "economic_until"])
def test_report_unknown(case, field):
    report = body(case)["universe"]["reports"][0]
    report[field] = "LIMITED" if "completeness" in field else EARLY if field == "source_information_cutoff" else FUTURE if field == "economic_until" else None
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert not result["negative_proofs"]


def test_missing_report(case):
    b = body(case)
    missing = b["universe"]["reports"].pop(0)
    for binding in b["rule_bindings"]:
        for key in ("exceptions", "horizon"):
            if binding[key] is not None:
                binding[key]["closure"]["report_keys"].remove(missing["key"])
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert "REPORT_MISSING" in result["reason_codes"]


@pytest.mark.parametrize("kind", ["REGIME_RULE", "REGIME_CLAUSE", "REGIME_DOCUMENT", "ACCOUNT_BUNDLE", "REGIME_APPROVAL", "REGIME_BINDING"])
def test_missing_native_mapping(case, kind):
    mappings = evidence(case)["native_mappings"]
    mappings.remove(next(m for m in mappings if m["native_reference"]["kind"] == kind))
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert "NATIVE_SUPPORT_MISSING" in result["reason_codes"]


@pytest.mark.parametrize("where", ["original", "record", "report", "entry", "coverage", "envelope", "admission"])
def test_unused_post_k_material_rejects(case, where):
    ev = evidence(case)
    if where == "admission":
        case[-1]["available_at"] = FUTURE
    else:
        node = {"original": ev["originals"][0], "record": ev["records"][0], "report": body(case)["universe"]["reports"][0],
            "entry": body(case)["universe"]["entries"][0], "coverage": ev["coverage"], "envelope": ev}[where]
        node["observed_at"] = FUTURE
    with pytest.raises(ValueError):
        run(seal(case))


@pytest.mark.parametrize("field,value", [("purpose", "TRADE_APPROVAL"), ("mandate_revision", True), ("request_content_sha256", "f" * 64),
    ("knowledge_boundary", EARLY), ("contract", "other"), ("effective_until", EARLY)])
def test_forged_admission_rejects(case, field, value):
    case[-1][field] = value
    with pytest.raises(ValueError):
        run(case)


@pytest.mark.parametrize("field", ["subject_content_sha256", "evidence_refs", "target"])
def test_malformed_receipt_rejects(case, field):
    receipt = case[-1]["admissions"][0]
    receipt[field] = "f" * 64 if field == "subject_content_sha256" else [] if field == "evidence_refs" else {"kind": "AUTHORIZE"}
    with pytest.raises(ValueError):
        run(case)


def test_missing_and_stale_admission(case):
    result = run((*case[:-1], None))
    assert result["outcome"] == "UNKNOWN"
    assert "ADMISSION_MISSING" in result["reason_codes"]
    case[-1]["effective_until"] = T
    result = run(seal(case, issue=False))
    assert result["outcome"] == "UNKNOWN"
    assert "ADMISSION_NOT_CURRENT" in result["reason_codes"]


def successor(case, *, kind="DECLARE", effective=FUTURE):
    first = evidence(case)["records"][0]
    record = dict(record_id="floor-2", kind=kind, predecessor=dict(kind="RECORD", record=recordref(first)),
        effective_from=effective, source_available_at=T, observed_at=T, evidence_refs=deepcopy(first["evidence_refs"]))
    if kind == "DECLARE":
        record.update(effective_until=None, body=deepcopy(first["body"]))
    evidence(case)["records"].append(record)
    return record




def test_no_predecessor_revival(case):
    successor(case, kind="WITHDRAW", effective=T)
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert "DECLARATION_WITHDRAWN" in result["reason_codes"]
    assert row(result)["headroom"] is None


@pytest.mark.parametrize("expiry,expected", [(T, "UNKNOWN"), (FUTURE, "UNKNOWN"), (H, "ESTABLISHED")])
def test_declaration_expiry(case, expiry, expected):
    evidence(case)["records"][0]["effective_from"] = EARLY
    evidence(case)["records"][0]["effective_until"] = expiry
    result = run(seal(case))
    assert result["outcome"] == expected, result["unresolved_findings"]


def test_historical_pins_are_inert(case):
    old = evidence(case)["records"][0]
    old["effective_from"] = EARLY
    new = successor(case, effective=T)
    old["body"]["subjects"] = {k: "f" * 64 for k in old["body"]["subjects"]}
    for b in old["body"]["rule_bindings"]:
        b["rule_reference"]["owner_bundle_sha256"] = "f" * 64
    assert new["body"]["subjects"] != old["body"]["subjects"]
    result = run(seal(case))
    assert result["outcome"] == "ESTABLISHED", result["unresolved_findings"]
    assert result["resolved_record"]["record_id"] == "floor-2"


def test_competing_current_declarations(case):
    other = deepcopy(evidence(case)["records"][0])
    other["record_id"] = "other-root"
    evidence(case)["records"].append(other)
    evidence(case)["coverage"]["root_records"].append(recordref(other))
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert "COMPETING_DECLARATIONS" in result["reason_codes"]


@pytest.mark.parametrize("defect", ["cycle", "false-root", "unknown-parent", "wrong-hash", "complete-gap", "duplicate"])
def test_malformed_history_rejects(case, defect):
    ev = evidence(case)
    root = ev["records"][0]
    if defect in ("cycle", "unknown-parent"):
        root["predecessor"] = dict(kind="RECORD", record=dict(record_id=root["record_id"] if defect == "cycle" else "absent", content_sha256="0" * 64))
    elif defect == "false-root":
        root["predecessor"] = dict(kind="UNKNOWN")
    elif defect == "wrong-hash":
        ev["coverage"]["root_records"][0]["content_sha256"] = "f" * 64
    elif defect == "complete-gap":
        ev["coverage"]["missing_record_ids"] = ["missing"]
    else:
        ev["records"].append(deepcopy(root))
    if defect != "wrong-hash":
        seal(case)
    with pytest.raises(ValueError):
        run(case)


def test_honest_history_gap(case):
    ev = evidence(case)
    ev["coverage"].update(revision_completeness="LIMITED", missing_record_ids=["missing"], history_truncated=True)
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert "REVISION_HISTORY_INCOMPLETE" in result["reason_codes"]


def test_structural_defect_beats_all_c_negative():
    case = sample(amount="10000")
    evidence(case)["originals"][0]["content_sha256"] = "f" * 64
    with pytest.raises(ValueError):
        run(seal(case))


@pytest.mark.parametrize("origin,step,minimum,maximum,native_origin,first,last", [
    ("0.1", "0.2", "0.1", "0.1", "0.1", "0", "0"),
    ("-0.1", "0.1", "0.1", "0.2", "0", "1", "2"),
])
def test_native_index_identity(origin, step, minimum, maximum, native_origin, first, last):
    grid = tuple(sorted(dict(origin=origin, step=step, minimum=minimum, maximum=maximum).items()))
    case = sample(grid=grid)
    native_support = bundle(case)["assessment"]["projection_basis"]["support"]
    expected = dict(kind="REGULAR_GRID", origin=native_origin, increment=step, first_index=first, last_index=last)
    assert native_support["domain"] == expected
    result = run(case)
    assert result["outcome"] == "ESTABLISHED", result["unresolved_findings"]
    assert result["supported_domain"] == native_support
    assert result["passing_domain"]["domain"] == expected


def test_extreme_precision_and_huge_grid_without_global_changes():
    step = "0." + "0" * 5000 + "1"
    grid = tuple(sorted(dict(step=step).items()))
    case = sample(grid=grid, amount="9996.5")
    previous = sys.get_int_max_str_digits()
    with localcontext() as context:
        context.prec = 2
        result = run(case)
    assert result["outcome"] == "ESTABLISHED", result["unresolved_findings"]
    d = result["passing_domain"]["domain"]
    assert d["first_index"] == "1" + "0" * 5000
    assert d["last_index"] == "15" + "0" * 4999
    assert sys.get_int_max_str_digits() == previous




def test_missing_owner_and_evidence(case):
    case[0]["provider_measure_projection"] = None
    case[0]["floor_evidence"] = None
    result = run((case[0], *([None] * 7)))
    assert result["outcome"] == "UNKNOWN"
    assert result["owner_reference"] is None
    assert result["supported_domain"] is None
    assert {"OWNER_MISSING", "EVIDENCE_MISSING", "ADMISSION_MISSING"} <= set(result["reason_codes"])


@pytest.mark.parametrize("kind", ["REGIME_RULE", "REGIME_DOCUMENT", "ACCOUNT_BUNDLE", "POLICY_BUNDLE"])
def test_false_native_owner_or_content_pin(case, kind):
    mapping = next(m for m in evidence(case)["native_mappings"] if m["native_reference"]["kind"] == kind)
    mapping["native_reference"]["owner_bundle_sha256"] = "f" * 64
    with pytest.raises(ValueError):
        run(seal(case))


@pytest.mark.parametrize("field", ["projection_bundle_sha256", "projection_basis_sha256", "policy_bundle_sha256", "account_bundle_sha256", "regime_bundle_sha256"])
def test_wrong_current_subject_pin(case, field):
    body(case)["subjects"][field] = "f" * 64
    with pytest.raises(ValueError):
        run(seal(case))


def test_unknown_publication_cannot_be_admitted(case):
    next(o for o in evidence(case)["originals"] if o["evidence_id"] == "floors")["source_available_at"] = None
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert "SOURCE_AVAILABILITY_UNKNOWN" in result["reason_codes"]


def test_rehashed_upstream_tampering(case):
    assessment = bundle(case)["assessment"]
    assessment["projection_basis"]["baseline_amount"] = "999999"
    assessment.pop("assessment_identity")
    assessment["assessment_identity"] = pf.owner.IDENTITY_PREFIX + digest(assessment)
    with pytest.raises(ValueError):
        run(seal(case))


RESULT_FIELDS = ("contract rule_version assessment_economic_time knowledge_boundary scope scenario outcome reason_codes owner_reference resolved_record supported_domain rule_results source_dispositions complete_predicate passing_domain negative_proofs unresolved_findings native_diagnostics native_unresolved_findings native_conditions native_limitations conditions limitations reconstruction_evidence downstream_obligations source_authentication authority execution").split()


@pytest.mark.parametrize("field", RESULT_FIELDS)
def test_every_result_field_reconstructed(case, field):
    result = deepcopy(genuine_result())
    result[field] = None if result[field] is not None else "tampered"
    result.pop("assessment_identity")
    result["assessment_identity"] = owner.IDENTITY_PREFIX + digest(result)
    with pytest.raises(ValueError):
        validate(result, case)


def test_exact_authority_and_mutation_isolation(case):
    before = deepcopy(case)
    result = run(case)
    for key in ("quantity_selection", "budget_approval", "position_effect_compliance", "margin_capital_approval", "trade_decision", "financial_risk", "execution"):
        assert result["authority"][key] is False
    assert result["execution"] is False
    assert "ACCOUNT_PROFIT_LOCK_AND_PAYOUT_ELIGIBILITY" in result["downstream_obligations"]
    assert case == before
    result["supported_domain"]["domain"]["origin"] = "mutated"
    assert result["complete_predicate"]["support"]["domain"]["origin"] == "0"
    result["reconstruction_evidence"]["request"]["floor_evidence"]["originals"].clear()
    assert case == before


def test_type_preserving_false_comparison(case):
    result = run(case)
    result["execution"] = 0
    result.pop("assessment_identity")
    result["assessment_identity"] = owner.IDENTITY_PREFIX + digest(result)
    with pytest.raises(ValueError):
        validate(result, case)


def test_presentation_order_and_time_equivalence(case):
    before = run(case)
    q = case[0]
    q["assessment_economic_time"] = datetime.fromisoformat(T.replace("Z", "+00:00")).isoformat()
    ev = evidence(case)
    for key in ("originals", "native_mappings", "records"):
        ev[key].reverse()
    u = body(case)["universe"]
    u["reports"].reverse()
    u["entries"].reverse()
    body(case)["rule_bindings"].reverse()
    case[-1]["admissions"].reverse()
    assert run(seal(case)) == before


def test_only_public_owner_replay_and_no_numerical_global_changes():
    source = inspect.getsource(owner)
    assert "validate_current_entry_provider_measure_projection_basis(" in source
    assert "set_int_max_str_digits" not in source
    assert "getcontext(" not in source
    assert "localcontext(" not in source
    assert "float(" not in source
    assert set(inspect.signature(owner.evaluate_current_post_entry_provider_floor_headroom).parameters) == {"request", *CONTEXTS}




@pytest.mark.parametrize("balance,amount,outcome", [("0", "-10", "ESTABLISHED"), ("-1", "-10", "ESTABLISHED"), ("0", "0", "NOT_SUITABLE")])
def test_signed_projected_balances(balance, amount, outcome):
    result = run(sample(balance=balance, amount=amount))
    assert result["outcome"] == outcome, result["unresolved_findings"]
    assert row(result)["headroom"]["threshold_amount"] == amount


def test_missing_original_fraction_operand():
    case = sample(reference="INITIAL_EQUITY", amount="0.9")
    floor(case)["threshold"]["initial_reference_operand"] = None
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert "THRESHOLD_OPERAND_UNRESOLVED" in result["reason_codes"]
    assert row(result)["headroom"] is None


def test_wrong_original_operand_selector():
    case = sample(reference="INITIAL_EQUITY", amount="0.9")
    ref = next(m["native_reference"] for m in evidence(case)["native_mappings"] if m["native_reference"]["kind"] == "POLICY_OPERAND" and m["native_reference"]["selector"]["operand_index"] == 0)
    floor(case)["threshold"]["initial_reference_operand"] = ref
    with pytest.raises(ValueError):
        run(seal(case))


def test_claimed_identical_equity_measure_rejects():
    case = sample(model="EQUITY")
    floor(case, "unrepresented-floor")["measure"]["status"] = "IDENTICAL"
    with pytest.raises(ValueError):
        run(seal(case))


def test_unmapped_source_entry_is_not_other_obligation(case):
    entry = add_entry(case, "unmapped-floor", "RULE", disposition="UNRESOLVED")
    entry["native_rule_refs"] = []
    result = run(seal(case))
    assert result["outcome"] == "UNKNOWN"
    assert "UNMAPPED_SOURCE_ENTRY" in result["reason_codes"]
    assert any(r["entry_reference"]["entry_id"] == entry["entry_id"] and r["disposition"] == "UNRESOLVED" for r in result["source_dispositions"])


OWNED_PATHS = [(), ("scope",), ("scope", "account"), ("scope", "instrument"), ("scope", "provider_namespace"),
    ("floor_evidence",), ("floor_evidence", "source"), ("floor_evidence", "originals", 0),
    ("floor_evidence", "native_mappings", 0), ("floor_evidence", "native_mappings", 0, "native_reference"),
    ("floor_evidence", "coverage"), ("floor_evidence", "records", 0), ("floor_evidence", "records", 0, "predecessor"),
    ("floor_evidence", "records", 0, "body"), ("floor_evidence", "records", 0, "body", "subjects"),
    ("floor_evidence", "records", 0, "body", "universe"), ("floor_evidence", "records", 0, "body", "universe", "actors", 0),
    ("floor_evidence", "records", 0, "body", "universe", "sources", 0),
    ("floor_evidence", "records", 0, "body", "universe", "sources", 0, "responsibilities", 0),
    ("floor_evidence", "records", 0, "body", "universe", "reports", 0),
    ("floor_evidence", "records", 0, "body", "universe", "entries", 0)]


def at_path(root, path):
    for key in path:
        root = root[key]
    return root


@pytest.mark.parametrize("path", OWNED_PATHS)
def test_closed_owned_objects(case, path):
    if "native_mappings" not in path:
        case = independent_future_packet(case)
    at_path(case[0], path)["unexpected"] = True
    with pytest.raises(ValueError):
        run(seal(case))


@pytest.mark.parametrize("section", ["population", "endpoint", "force", "exceptions", "measure", "threshold", "horizon"])
def test_closed_rule_objects(case, section):
    case = independent_future_packet(case)
    floor(case)[section]["unexpected"] = True
    with pytest.raises(ValueError):
        run(seal(case))


@pytest.mark.parametrize("section,field", [("population", "status"), ("endpoint", "status"), ("force", "status"),
    ("exceptions", "resolution"), ("measure", "status"), ("threshold", "relationship"), ("horizon", "status")])
def test_unknown_enum_spelling_rejects(case, section, field):
    case = independent_future_packet(case)
    floor(case)[section][field] = "UNRECOGNIZED"
    with pytest.raises(ValueError):
        run(seal(case))


@pytest.mark.parametrize("path", [("floor_evidence", "originals"), ("floor_evidence", "native_mappings"),
    ("floor_evidence", "records"), ("floor_evidence", "coverage", "root_records"),
    ("floor_evidence", "records", 0, "body", "rule_bindings"),
    ("floor_evidence", "records", 0, "body", "universe", "actors"),
    ("floor_evidence", "records", 0, "body", "universe", "sources"),
    ("floor_evidence", "records", 0, "body", "universe", "reports"),
    ("floor_evidence", "records", 0, "body", "universe", "entries")])
def test_duplicate_owned_identities_reject(case, path):
    if "native_mappings" not in path:
        case = independent_future_packet(case)
    rows = at_path(case[0], path)
    rows.append(deepcopy(rows[0]))
    with pytest.raises(ValueError):
        run(seal(case))


@pytest.mark.parametrize("bad", ["2026-01-02T00:32:00", "2026-01-02T00:32:00.0000001Z", "2026-02-30T00:00:00Z", True, 0])
def test_malformed_owned_time(case, bad):
    case[0]["knowledge_boundary"] = bad
    with pytest.raises(ValueError):
        run(case)


def test_duplicate_receipt_target_rejects(case):
    case[-1]["admissions"].append(deepcopy(case[-1]["admissions"][0]))
    with pytest.raises(ValueError):
        run(case)


def test_whole_horizon_waiver_cannot_keep_mandatory_force(case):
    floor(case)["exceptions"]["resolution"] = "WAIVED_THROUGHOUT"
    with pytest.raises(ValueError):
        run(seal(case))


@pytest.mark.parametrize("role", ["PROVIDER", "ACCOUNT_AUTHORITY", "GOVERNANCE", "OTHER"])
def test_closed_actor_role_vocabulary(case, role):
    case = independent_future_packet(case)
    body(case)["universe"]["actors"][0]["role"] = role
    assert run(seal(case))["outcome"] == "UNKNOWN"


@pytest.mark.parametrize("role", ["RULEBOOK", "AGREEMENT", "SUPPLEMENTAL", "REVISION_LEDGER", "OTHER"])
def test_closed_source_role_vocabulary(case, role):
    case = independent_future_packet(case)
    body(case)["universe"]["sources"][0]["role"] = role
    assert run(seal(case))["outcome"] == "UNKNOWN"


@pytest.mark.parametrize("kind", [kind for kinds in owner.TOPIC_KINDS.values() for kind in kinds])
def test_closed_entry_kind_vocabulary(case, kind):
    case = independent_future_packet(case)
    u = body(case)["universe"]
    entry = u["entries"][0]
    old_report = next(r for r in u["reports"] if r["key"] == entry["report_key"])
    old_report["entry_ids"].remove(entry["entry_id"])
    topic = next(t for t, kinds in owner.TOPIC_KINDS.items() if kind in kinds)
    report = next(r for r in u["reports"] if r["key"]["topic"] == topic)
    report["entry_ids"].append(entry["entry_id"])
    entry.update(kind=kind, report_key=deepcopy(report["key"]), disposition="SUPPORTING_RULE_EVIDENCE")
    assert run(seal(case))["outcome"] == "UNKNOWN"


@pytest.mark.parametrize("disposition", owner.ENTRY_DISPOSITIONS)
def test_closed_entry_disposition_vocabulary(case, disposition):
    case = independent_future_packet(case)
    body(case)["universe"]["entries"][0]["disposition"] = disposition
    assert run(seal(case))["outcome"] == "UNKNOWN"


@pytest.mark.parametrize("status,end", [("KNOWN", END), ("OPEN_ENDED", None), ("UNKNOWN", None)])
@pytest.mark.parametrize("start", [EARLY, None])
def test_nullable_source_period_vocabulary(case, status, end, start):
    case = independent_future_packet(case)
    body(case)["universe"]["entries"][0]["effective_period"].update(effective_from=start, effective_until=end, end_status=status)
    assert run(seal(case))["outcome"] == "UNKNOWN"


@pytest.mark.parametrize("value", ["LIMITED", "UNKNOWN"])
@pytest.mark.parametrize("field", ["inventory_completeness", "revision_completeness"])
def test_closed_report_completeness_vocabulary(case, value, field):
    case = independent_future_packet(case)
    body(case)["universe"]["reports"][0][field] = value
    assert run(seal(case))["outcome"] == "UNKNOWN"


@pytest.mark.parametrize("field,value", [("entries_omitted", True), ("entries_omitted", None),
    ("history_truncated", True), ("history_truncated", None), ("starting_basis", "INCOMPLETE_OR_UNKNOWN")])
def test_honest_report_gaps_are_structurally_admissible(case, field, value):
    case = independent_future_packet(case)
    report = body(case)["universe"]["reports"][0]
    report.update(inventory_completeness="LIMITED", revision_completeness="LIMITED")
    report[field] = value
    assert run(seal(case))["outcome"] == "UNKNOWN"


@pytest.mark.parametrize("nullable", ["source_information_cutoff", "source_available_at"])
def test_nullable_unneeded_evidence(case, nullable):
    case = independent_future_packet(case)
    evidence(case)["coverage"][nullable] = None
    assert run(seal(case))["outcome"] == "UNKNOWN"




def test_unused_unknown_publication_does_not_create_a_failure(case):
    evidence(case)["originals"].append(pf.original("unused", evidence(case)["source"], {"unused": True}, T))
    evidence(case)["originals"][-1]["source_available_at"] = None
    result = run(seal(case))
    assert result["outcome"] == "ESTABLISHED", result["unresolved_findings"]












@pytest.mark.parametrize("path", [("account", "account_id"), ("provider_id",), ("instrument", "instrument_id"),
    ("account", "currency"), ("provider_namespace", "source_id")])
def test_scope_cannot_substitute_native_identity(case, path):
    parent = at_path(case[0]["scope"], path[:-1])
    parent[path[-1]] = "EUR" if path[-1] == "currency" else "substituted"
    evidence(case)["scope"] = deepcopy(case[0]["scope"])
    with pytest.raises(ValueError):
        run(seal(case))


def test_native_document_source_pin_cannot_be_reissued(case):
    mapping = next(m for m in evidence(case)["native_mappings"] if m["native_reference"]["kind"] == "REGIME_DOCUMENT")
    original = next(o for o in evidence(case)["originals"] if o["evidence_id"] == mapping["original_reference"]["evidence_id"])
    original["source"]["source_id"] = "reissued-from-another-source"
    with pytest.raises(ValueError):
        run(seal(case))




def test_native_unknown_does_not_hide_false_known_measure_identity():
    case = sample(model="EQUITY")
    p6 = bundle(case)
    p6["assessment"] = pf.run((p6["request"], *case[1:6], None))
    assert p6["assessment"]["outcome"] == "UNKNOWN"
    case = (case[0], *case[1:6], None, case[-1])
    body(case)["subjects"]["projection_bundle_sha256"] = digest(p6)
    body(case)["subjects"]["projection_basis_sha256"] = None
    floor(case, "unrepresented-floor")["measure"]["status"] = "IDENTICAL"
    with pytest.raises(ValueError, match="Claimed exact native measure"):
        run(seal(case))


@pytest.mark.parametrize("start,stop,expected", [(H, None, "UNKNOWN"), (EARLY, T, "UNKNOWN"), (EARLY, H, "ESTABLISHED")])
def test_source_rule_support_must_cover_entire_horizon(case, start, stop, expected):
    entry = next(e for e in body(case)["universe"]["entries"] if e["entry_id"] == "settlement-balance")
    entry["effective_period"].update(effective_from=start, effective_until=stop, end_status="OPEN_ENDED" if stop is None else "KNOWN")
    result = run(seal(case))
    assert result["outcome"] == expected, result["unresolved_findings"]
    if expected == "UNKNOWN":
        assert "HORIZON_UNRESOLVED" in result["reason_codes"]
        assert row(result)["headroom"] is None


def test_exact_math_preserves_negative_origin_representation_without_owner_mock():
    case = sample()
    assert run(case)["outcome"] == "ESTABLISHED"
    basis = deepcopy(bundle(case)["assessment"]["projection_basis"])
    # The current quantity-domain owner canonicalizes to a nonnegative residue.
    # This isolated arithmetic check uses the same proven quantities {0.1,0.2}
    # in a negative-origin representation, without fabricating a native owner.
    basis["support"]["domain"] = dict(kind="REGULAR_GRID", origin="-0.1", increment="0.1", first_index="2", last_index="3")
    before = deepcopy(basis)
    passing, excluded = owner._prefix(basis, Fraction("9997"), "GREATER_THAN_OR_EQUAL")
    assert passing["domain"] == dict(kind="REGULAR_GRID", origin="-0.1", increment="0.1", first_index="2", last_index="2")
    assert excluded["domain"] == dict(kind="REGULAR_GRID", origin="-0.1", increment="0.1", first_index="3", last_index="3")
    assert basis == before


@pytest.mark.parametrize("kind", ["PACKAGE", "ASSIGNMENT"])
@pytest.mark.parametrize("start,stop,expected", [(FUTURE, None, "UNKNOWN"), (H, None, "NOT_SUITABLE"),
                                               (EARLY, T, "NOT_SUITABLE"), (FUTURE, "UNKNOWN", "UNKNOWN")])
def test_native_competitor_cannot_hide_behind_open_selected_package(kind, start, stop, expected):
    case = sample(amount="10000", native_change=(kind, start, stop))
    assert bundle(case)["assessment"]["outcome"] == "ESTABLISHED"
    result = run(case)
    assert result["outcome"] == expected, result["unresolved_findings"]
    if expected == "UNKNOWN":
        assert ("HORIZON_UNRESOLVED" if stop == "UNKNOWN" else "HORIZON_CHANGE") in result["reason_codes"]
        assert result["negative_proofs"] == []
        assert row(result)["headroom"] is None
    else:
        assert result["negative_proofs"][0]["kind"] == "ALL_C_EXCLUDED"


def whole_waiver_case(start=EARLY, stop=H, disposition="SUPPORTING_RULE_EVIDENCE"):
    case = sample(amount="10000", second=True)
    waiver = add_entry(case, "waiver", "WAIVER", effective=start, disposition=disposition)
    waiver["effective_period"].update(effective_until=stop, end_status="OPEN_ENDED" if stop is None else "KNOWN")
    binding = floor(case)
    binding["force"]["status"] = "NOT_MANDATORY"
    binding["exceptions"].update(resolution="WAIVED_THROUGHOUT", authority_actor_ids=["provider"],
        authority_evidence_refs=deepcopy(binding["evidence_refs"]), precedence_evidence_refs=deepcopy(binding["evidence_refs"]))
    binding["exceptions"]["closure"]["entry_refs"] = [entryref(waiver)]
    return seal(case)


@pytest.mark.parametrize("start,stop,expected", [(H, None, "UNKNOWN"), (EARLY, T, "UNKNOWN"),
                                               (EARLY, H, "ESTABLISHED")])
def test_waiver_source_must_cover_whole_horizon(start, stop, expected):
    case = whole_waiver_case(start, stop)
    result = run(case)
    assert bundle(case)["assessment"]["outcome"] == "ESTABLISHED"
    assert result["outcome"] == expected, result["unresolved_findings"]
    if expected == "UNKNOWN":
        assert row(result)["disposition"] == "UNRESOLVED"
        assert "HORIZON_UNRESOLVED" in row(result)["reason_codes"]
        assert result["passing_domain"] is None
    else:
        assert row(result)["disposition"] == "WAIVED_THROUGHOUT"
        assert result["passing_domain"]["domain"]["last_index"] == "1"


@pytest.mark.parametrize("disposition", ["PROVEN_OUTSIDE_SCOPE", "HISTORICAL_NON_GOVERNING", "OTHER_OBLIGATION"])
def test_nongoverning_entry_cannot_establish_current_waiver(disposition):
    case = whole_waiver_case(disposition=disposition)
    result = run(case)
    assert bundle(case)["assessment"]["outcome"] == "ESTABLISHED"
    assert result["outcome"] == "UNKNOWN", result["unresolved_findings"]
    assert row(result)["disposition"] == "UNRESOLVED"
    assert "EXCEPTIONS_UNRESOLVED" in row(result)["reason_codes"]
    assert row(result, "second-floor")["disposition"] == "SUPPORTED_STATIC_FLOOR"
    assert result["passing_domain"] is None
