"""The single provider-independent local Mission Control execution pipeline."""
from __future__ import annotations

from dataclasses import asdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from ced_one.mission_control.classifier import RequestClassifier
from ced_one.mission_control.execution import ExecutionPlanStep, MissionExecutionPlan
from ced_one.mission_control.governance import AuthorizationSnapshot, ExecutionGovernanceGate, PolicyEvaluationContext
from ced_one.mission_control.guards import MissionGuard
from ced_one.mission_control.policy import ExecutionPolicy, PolicyDecision, RiskImpactClassification, validate_context_data
from ced_one.mission_control.request import MissionRequestBuilder
from ced_one.mission_control.resolver import RequestResolver
from ced_one.mission_control.runtime import LocalExecutionRuntime, MissionExecutionDispatcher, ExecutionOutcome
from ced_one.mission_control.tasks import MissionTask, MissionTaskGraph, TaskLifecycleState as S
from ced_one.mission_control.types import ApprovalState, MissionResult, RequestStatus


class ArchivedContextError(ValueError):
    """Fixed public selection failures; never include archived payload values."""


_SELECTION_FIELDS = {"mission_id", "record_sha256", "division", "capability", "contract_id",
                     "rule_version", "evaluation_time", "created_not_after"}
_PROJECTION_FIELDS = {"schema_version", "source_mission_id", "record_sha256", "division", "capability",
                      "contract_id", "rule_version", "evaluation_time", "source_request_created_at",
                      "created_not_after", "selected_at", "payload_sha256", "temporal_scope"}


def _context_time(value):
    try:
        if type(value) is not str:
            raise ValueError()
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ArchivedContextError("INVALID_CONTEXT_TIME") from None


def _time_text(value):
    return value.isoformat().replace("+00:00", "Z")


def _digest(value):
    if validate_context_data(value):
        raise ArchivedContextError("INVALID_PROJECTION")
    try:
        encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    except (ValueError, TypeError, RecursionError):
        raise ArchivedContextError("INVALID_PROJECTION") from None


def _sha256(value):
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def validate_archived_context_projection(value):
    """Check the isolated data contract; this does not authenticate or authorize it."""
    if type(value) is not dict or set(value) != {"selection", "original_payload"}:
        raise ArchivedContextError("INVALID_PROJECTION")
    ref = value["selection"]
    if (type(ref) is not dict or set(ref) != _PROJECTION_FIELDS or
            any(type(v) is not str or not v.strip() for v in ref.values()) or
            ref["schema_version"] != "mission_control.archived_context.v1" or
            ref["temporal_scope"] != "HISTORICAL_RECORD_ONLY" or
            not _sha256(ref["record_sha256"]) or not _sha256(ref["payload_sha256"]) or
            type(value["original_payload"]) is not dict):
        raise ArchivedContextError("INVALID_PROJECTION")
    times = [_context_time(ref[k]) for k in (
        "evaluation_time", "source_request_created_at", "created_not_after", "selected_at")]
    if times != sorted(times) or times[-1] > datetime.now(timezone.utc):
        raise ArchivedContextError("SOURCE_TIME_MISMATCH")
    if _digest(value["original_payload"]) != ref["payload_sha256"]:
        raise ArchivedContextError("PROJECTION_CONTENT_MISMATCH")
    return deepcopy(value)


class MissionControlService:
    """Execute explicitly registered capabilities under an explicitly supplied policy."""

    def __init__(self, division_registry: dict[str, Any] | None = None, *, runtime=None, policy: ExecutionPolicy | None = None, archive=None):
        self.division_registry = {} if division_registry is None else division_registry
        self.resolver = RequestResolver(self.division_registry)
        self.runtime = runtime if runtime is not None else LocalExecutionRuntime()
        self.policy = policy if policy is not None else ExecutionPolicy("default_deny", 1)
        self.dispatcher = MissionExecutionDispatcher(self.division_registry, self.runtime)
        self.execution_history: list[MissionResult] = []
        self.archive = archive

    def get_archived_mission(self, mission_id: str):
        """Read historical data only; never restore a task or its authorization."""
        if self.archive is None:
            from ced_one.memory.mission_store import ArchiveNotConfiguredError
            raise ArchiveNotConfiguredError()
        return self.archive.get(mission_id)

    def select_archived_context(self, selection: dict):
        """Explicit read only. Request time is not historical archive availability."""
        if (type(selection) is not dict or set(selection) != _SELECTION_FIELDS or
                any(type(v) is not str or not v.strip() for v in selection.values()) or
                not _sha256(selection["record_sha256"])):
            raise ArchivedContextError("INVALID_SELECTION")
        criteria = deepcopy(selection)
        boundary = _context_time(criteria["evaluation_time"])
        latest = _context_time(criteria["created_not_after"])
        record = self.get_archived_mission(criteria["mission_id"])
        if (record.mission_id != criteria["mission_id"] or record.record_sha256 != criteria["record_sha256"] or
                record.request.request_id != record.mission_id or record.result.request_id != record.mission_id):
            raise ArchivedContextError("SOURCE_IDENTITY_MISMATCH")
        source = record.result
        contract = source.metadata.get("capability_contract", {})
        if (source.status is not RequestStatus.COMPLETED or source.success is not True or
                source.metadata.get("execution_performed") is not True):
            raise ArchivedContextError("SOURCE_NOT_COMPLETED")
        if (record.request.business_division != criteria["division"] or source.division != criteria["division"] or
                source.capability != criteria["capability"] or type(contract) is not dict or
                contract.get("name") != criteria["capability"] or contract.get("division_name") != criteria["division"] or
                contract.get("contract_id") != criteria["contract_id"] or contract.get("permission_scope") != "read_only" or
                type(contract.get("metadata")) is not dict or
                contract.get("metadata", {}).get("rule_version") != criteria["rule_version"]):
            raise ArchivedContextError("SOURCE_ORIGIN_MISMATCH")
        if _context_time(record.request.context.get("requested_evaluation_timestamp")) != boundary:
            raise ArchivedContextError("SOURCE_TIME_MISMATCH")
        selected_at = datetime.now(timezone.utc)
        created_at = record.request.created_at.astimezone(timezone.utc)
        if not boundary <= created_at <= latest <= selected_at:
            raise ArchivedContextError("SOURCE_TIME_MISMATCH")
        projection = {"selection": {
            "schema_version": "mission_control.archived_context.v1", "source_mission_id": record.mission_id,
            "record_sha256": record.record_sha256, "division": criteria["division"], "capability": criteria["capability"],
            "contract_id": criteria["contract_id"], "rule_version": criteria["rule_version"],
            "evaluation_time": _time_text(boundary), "source_request_created_at": _time_text(created_at),
            "created_not_after": _time_text(latest), "selected_at": _time_text(selected_at),
            "payload_sha256": _digest(source.result_payload), "temporal_scope": "HISTORICAL_RECORD_ONLY",
        }, "original_payload": deepcopy(source.result_payload)}
        return validate_archived_context_projection(projection)

    def handle_request(self, user_goal: str, *, business_division: str | None = None,
                       request_type: str = "general", priority: str = "normal", source: str = "user",
                       context: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None,
                       constraints: list[str] | None = None, archive_selection: dict | None = None) -> MissionResult:
        request = MissionRequestBuilder.from_user_goal(user_goal, business_division=business_division,
            request_type=request_type, priority=priority, source=source, context=deepcopy(context),
            metadata=deepcopy(metadata), constraints=deepcopy(constraints))
        if archive_selection is not None and context is None:
            request.context = {"archive_selection": deepcopy(archive_selection)}
        details = {"execution_performed": False}
        graph = MissionTaskGraph(request.request_id, f"plan_{request.request_id}")
        graph.audit_log.record("REQUEST_RECEIVED", mission_id=request.request_id)
        division_name = specialist_name = capability_name = None
        plan = None

        def finish(status, summary, *, errors=None, payload=None, approval=ApprovalState.NOT_REQUIRED):
            graph.audit_log.record("MISSION_RESULT", mission_id=request.request_id, status=status.value, execution_performed=details["execution_performed"])
            if plan is not None:
                details["execution_plan"] = plan.as_dict()
                details["execution_trace"] = [step.as_dict() for step in plan.steps]
            details["task_graph"] = graph.as_dict()
            details["audit_reference"] = request.request_id
            result = MissionResult(request_id=request.request_id, status=status, division=division_name,
                specialist=specialist_name, capability=capability_name, summary=summary,
                errors=errors or [], result_payload=payload or {}, approval_state=approval,
                success=status == RequestStatus.COMPLETED and details["execution_performed"], metadata=details)
            if self.archive is not None:
                from ced_one.memory.mission_store import ArchiveError
                details["archive"] = {"status": "stored"}
                try:
                    self.archive.save(request, result, {
                        "policy_id": self.policy.policy_id,
                        "policy_version": self.policy.policy_version,
                        "default_decision": self.policy.default_decision,
                    })
                except ArchiveError as exc:
                    details["archive"] = {"status": "failed", "error_code": exc.code}
                except Exception:
                    # An optional store must never turn a finished execution into
                    # another attempt, or recursively enter finish() on failure.
                    details["archive"] = {"status": "failed", "error_code": "ARCHIVE_ERROR"}
            self.execution_history.append(result)
            return result

        try:
            if not isinstance(user_goal, str) or not user_goal.strip():
                return finish(RequestStatus.FAILED, "Request goal is required.", errors=["Invalid user_goal."])
            authority = MissionGuard.validate_authority(request.metadata)
            if not authority.valid:
                return finish(RequestStatus.FAILED, "Authority validation failed.", errors=authority.violations)
            classification = RequestClassifier.classify(request)
            details["classification"] = classification
            resolution = self.resolver.resolve(request, classification)
            details["division_resolution"] = resolution
            details["route_decision"] = asdict(resolution)
            if not resolution.is_supported or not resolution.is_routeable or not resolution.division_name:
                return finish(RequestStatus.UNROUTEABLE, resolution.rationale, errors=[resolution.rationale])
            division_name = resolution.division_name
            division = self.division_registry[division_name]
            resolve_specialist = getattr(division, "resolve_specialist", None) or getattr(division, "identify_specialist", None)
            resolve_capability = getattr(division, "resolve_capability", None) or getattr(division, "identify_capability", None)
            specialist = resolve_specialist(request) if resolve_specialist else {}
            capability = resolve_capability(request) if resolve_capability else {}
            errors = []
            for label, binding in (("specialist", specialist), ("capability", capability)):
                if not isinstance(binding, dict) or not binding.get("name"):
                    errors.append(f"Invalid {label} assignment.")
                elif binding.get("division_name") != division_name:
                    errors.append(f"Invalid {label} division binding.")
            if errors:
                return finish(RequestStatus.FAILED, "Invalid specialist or capability assignment.", errors=errors)
            specialist_name, capability_name = specialist["name"], capability["name"]
            if resolution.specialist_name not in (None, specialist_name) or resolution.capability_name not in (None, capability_name):
                return finish(RequestStatus.FAILED, "Inconsistent resolution bindings.", errors=["Resolution binding mismatch."])
            permission = specialist.get("permission_scope")
            if not permission or capability.get("permission_scope", permission) != permission:
                return finish(RequestStatus.FAILED, "Permission scope mismatch.", errors=["Permission scope mismatch."])
            plan = MissionExecutionPlan(graph.plan_id, request.request_id, division_name, specialist_name, capability_name,
                steps=[ExecutionPlanStep(name, name.replace("_", " "), order, division=division_name, specialist=specialist_name, capability=capability_name)
                       for order, name in enumerate(("validate_authority", "resolve_division", "resolve_specialist", "resolve_capability", "validate_scope", "execute_plan"), 1)])
            for step in plan.steps[:-1]:
                step.status = "completed"
            approval = MissionGuard.evaluate_approval(request.metadata)
            if approval.required:
                plan.steps[-1].approval_required = True
                plan.steps[-1].status = "blocked"
                details["approval_requirement"] = approval
                return finish(RequestStatus.AWAITING_APPROVAL, "Explicit approval is required.", approval=ApprovalState.PENDING)
            selection = self.runtime.get_registration(division_name, capability_name) if callable(getattr(self.runtime, "get_registration", None)) and callable(getattr(self.runtime, "reserve_registration", None)) else None
            contract = selection.contract if selection else None
            if contract is None:
                return finish(RequestStatus.UNSUPPORTED, "No capability executor is registered.", errors=["Missing capability executor."])
            if (contract.name, contract.division_name, contract.permission_scope, contract.contract_id) != (capability_name, division_name, permission, capability.get("contract")):
                return finish(RequestStatus.FAILED, "Registered contract does not match assignment.", errors=["Capability contract binding mismatch."])
            if type(contract.metadata) is dict and contract.metadata.get("requires_archived_context") is True:
                if archive_selection is None or context is not None:
                    return finish(RequestStatus.FAILED, "Explicit archive selection is required.", errors=["INVALID_SELECTION_INPUT"])
                payload = validate_archived_context_projection(self.select_archived_context(archive_selection))
                request.context = deepcopy(payload)
                details["archived_context_selection"] = deepcopy(payload["selection"])
                graph.audit_log.record("ARCHIVED_CONTEXT_SELECTED", mission_id=request.request_id, **payload["selection"])
            else:
                if archive_selection is not None:
                    return finish(RequestStatus.FAILED, "Capability does not accept archived context.", errors=["UNSUPPORTED_ARCHIVE_INPUT"])
                payload = deepcopy(request.context)
            errors = contract.validate_input(payload)
            if errors:
                return finish(RequestStatus.FAILED, "Invalid capability input.", errors=errors)
            task = MissionTask(f"task_{request.request_id}", request.request_id, plan.plan_id, "execute_capability", user_goal,
                division_name=division_name, specialist_name=specialist_name, capability_name=capability_name,
                permission_scope=permission, retryable=contract.retryable, metadata={"input_payload": payload})
            graph.tasks[task.task_id] = task
            # Classification is owned by the registered contract, never by caller metadata.
            classification_metadata = contract.metadata if isinstance(contract.metadata, dict) else {}
            risk = RiskImpactClassification("capability_contract", contract.contract_id, request.created_at,
                classification_metadata.get("risk_level"), classification_metadata.get("impact_level"),
                {"contract_id": contract.contract_id, "permission_scope": permission})
            def evaluation_context():
                return PolicyEvaluationContext(task.task_id, request.request_id, task.task_state, task.approval_state,
                    division_name, specialist_name, capability_name, "local", permission_scope=permission,
                    adapter_type="local", risk_impact_classification=risk,
                    policy_id=self.policy.policy_id, policy_version=self.policy.policy_version,
                    task_context={"input_payload": payload, "capability_contract": contract.to_dict(),
                                  "registration_id": selection.registration_id, "execution_context": {}})
            decision = ExecutionGovernanceGate().evaluate(evaluation_context(), policy=self.policy)
            details["policy_decision"] = asdict(decision)
            graph.audit_log.record("POLICY_EVALUATED", task_id=task.task_id, mission_id=request.request_id, **asdict(decision))
            if decision.decision in {PolicyDecision.REQUIRE_APPROVAL, PolicyDecision.ESCALATE}:
                state = ApprovalState.PENDING if decision.decision == PolicyDecision.REQUIRE_APPROVAL else ApprovalState.ESCALATED
                graph.transition_task(task.task_id, S.BLOCKED, approval_state=state)
                plan.steps[-1].status = "blocked"
                return finish(RequestStatus.AWAITING_APPROVAL, decision.reason, approval=state)
            if not decision.is_allowed:
                graph.transition_task(task.task_id, S.REJECTED, reason=decision.reason)
                plan.steps[-1].status = "rejected"
                return finish(RequestStatus.REJECTED, decision.reason, errors=[decision.reason])
            if "archived_context_selection" in details:
                try:
                    validate_archived_context_projection(payload)
                    if payload["selection"] != details["archived_context_selection"]:
                        raise ArchivedContextError("STALE_ARCHIVED_CONTEXT")
                except ArchivedContextError:
                    graph.transition_task(task.task_id, S.REJECTED, reason="STALE_ARCHIVED_CONTEXT")
                    plan.steps[-1].status = "rejected"
                    return finish(RequestStatus.REJECTED, "Archived context changed after selection.",
                                  errors=["STALE_ARCHIVED_CONTEXT"])
            graph.transition_task(task.task_id, S.READY)
            graph.transition_task(task.task_id, S.ASSIGNED)
            current = evaluation_context()
            authorization = AuthorizationSnapshot.from_context(current)
            plan.approved = True
            result = self.dispatcher.dispatch(task=task, assignment={**specialist, "capability_name": capability_name},
                capability_contract=contract, input_payload=payload, policy=self.policy,
                authorization_context=current, authorization_snapshot=authorization, audit_log=graph.audit_log)
            details["execution_performed"] = result.runtime_metadata.get("execution_performed", False)
            if details["execution_performed"] and "archived_context_selection" in details:
                graph.audit_log.record("ARCHIVED_CONTEXT_USED", task_id=task.task_id, mission_id=request.request_id,
                                       **details["archived_context_selection"])
            details["execution_result"] = result.to_dict()
            details["capability_contract"] = contract.to_dict()
            graph.audit_log.record("EXECUTION_RESULT", task_id=task.task_id, mission_id=request.request_id, execution_result=result.to_dict())
            if not details["execution_performed"]:
                graph.transition_task(task.task_id, S.REJECTED, reason=result.failure_reason)
                plan.steps[-1].status = "rejected"
                return finish(RequestStatus.REJECTED, result.failure_reason, errors=result.validation_errors)
            if result.outcome == ExecutionOutcome.SUCCEEDED:
                graph.mark_task_result(task.task_id, result_payload=result.result_payload)
                plan.steps[-1].status = "completed"
                return finish(RequestStatus.COMPLETED, "Capability executed and output validated.", payload=result.result_payload)
            if result.outcome == ExecutionOutcome.CANCELLED:
                graph.transition_task(task.task_id, S.CANCELLED, reason=result.failure_reason)
                plan.steps[-1].status = "cancelled"
                return finish(RequestStatus.CANCELLED, result.failure_reason or "Execution cancelled.")
            graph.mark_task_result(task.task_id, validation_errors=result.validation_errors or [result.failure_reason or result.outcome.value])
            plan.steps[-1].status = "failed"
            return finish(RequestStatus.FAILED, result.failure_reason or "Execution failed.", errors=result.validation_errors or [result.outcome.value])
        except Exception as exc:
            return finish(RequestStatus.FAILED, "Mission processing failed.", errors=[f"{type(exc).__name__}: {exc}"])
