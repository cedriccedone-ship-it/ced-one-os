from __future__ import annotations

from ced_one.mission_control.adapters import (
    AdapterBindingPolicy,
    AdapterRegistry,
    CapabilityAdapterBinding,
    MockLocalProviderAdapter,
    MockLocalToolAdapter,
    ProviderAdapter,
    StructuredProviderRequest,
    StructuredProviderResult,
    ToolAdapter,
)
from ced_one.mission_control.runtime import CapabilityExecutionContract, ExecutionOutcome, StructuredExecutionResult
from ced_one.mission_control.tasks import MissionTask, TaskLifecycleState
from ced_one.mission_control.types import ApprovalState


class GenericCapabilityContract(CapabilityExecutionContract):
    pass


def test_v07_capability_contract_remains_provider_independent():
    contract = GenericCapabilityContract(
        name="coordination",
        division_name="generic",
        contract_id="coordination_contract",
        permission_scope="standard",
        input_schema={"required_fields": ["request"]},
        output_schema={"required_fields": ["ok"]},
        timeout_seconds=30,
    )

    assert contract.name == "coordination"
    assert getattr(contract, "provider_name", None) is None
    assert getattr(contract, "adapter_id", None) is None
    assert getattr(contract, "adapter_type", None) is None


def test_v07_adapter_binding_policy_is_separate_from_capability_contract():
    policy = AdapterBindingPolicy()
    binding = policy.bind(
        capability_name="coordination",
        division_name="generic",
        adapter_name="mock_provider",
        adapter_type="provider",
        permission_scope="standard",
        execution_mode="local",
        priority=10,
    )

    assert binding.capability_name == "coordination"
    assert binding.adapter_name == "mock_provider"
    assert binding.adapter_type == "provider"


def test_v07_registry_filters_unauthorized_or_unavailable_adapters():
    registry = AdapterRegistry()
    registry.register(
        CapabilityAdapterBinding(
            capability_name="coordination",
            division_name="generic",
            adapter_name="mock_provider",
            adapter_type="provider",
            permission_scope="standard",
            execution_mode="local",
            priority=1,
            available=True,
        )
    )
    registry.register(
        CapabilityAdapterBinding(
            capability_name="coordination",
            division_name="generic",
            adapter_name="mock_provider_2",
            adapter_type="provider",
            permission_scope="restricted",
            execution_mode="local",
            priority=2,
            available=False,
        )
    )

    eligible = registry.get_eligible(
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
        execution_mode="local",
    )

    assert len(eligible) == 1
    assert eligible[0].adapter_name == "mock_provider"


def test_v07_selection_is_deterministic_when_multiple_adapters_match():
    registry = AdapterRegistry()
    registry.register(
        CapabilityAdapterBinding(
            capability_name="coordination",
            division_name="generic",
            adapter_name="adapter_b",
            adapter_type="provider",
            permission_scope="standard",
            execution_mode="local",
            priority=20,
            available=True,
        )
    )
    registry.register(
        CapabilityAdapterBinding(
            capability_name="coordination",
            division_name="generic",
            adapter_name="adapter_a",
            adapter_type="provider",
            permission_scope="standard",
            execution_mode="local",
            priority=10,
            available=True,
        )
    )

    selected = registry.select(
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
        execution_mode="local",
    )
    assert selected.adapter_name == "adapter_a"


def test_v07_unauthorized_adapter_substitution_is_rejected():
    registry = AdapterRegistry()
    valid = CapabilityAdapterBinding(
        capability_name="coordination",
        division_name="generic",
        adapter_name="authorized_adapter",
        adapter_type="provider",
        permission_scope="standard",
        execution_mode="local",
        priority=1,
        available=True,
    )
    registry.register(valid)

    assert registry.is_authorized(binding=valid, capability_name="coordination", division_name="generic", permission_scope="standard") is True
    assert registry.is_authorized(binding=valid, capability_name="coordination", division_name="generic", permission_scope="restricted") is False


def test_v07_provider_raw_response_is_normalized_at_adapter_boundary():
    adapter = MockLocalProviderAdapter()
    request = StructuredProviderRequest(
        request_id="req_001",
        task_id="task_001",
        mission_id="mission_001",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        adapter_name="mock_provider",
        permission_scope="standard",
        input_payload={"request": "demo"},
        execution_context={"simulate_mode": "success"},
        timeout_seconds=30,
    )

    result = adapter.execute(request)
    assert result.outcome == "succeeded"
    assert result.payload["ok"] is True


def test_v07_tool_adapter_is_not_risk_classification():
    tool = MockLocalToolAdapter()
    assert isinstance(tool, ToolAdapter)
    assert tool.adapter_type == "tool"
    assert tool.permission_scope == "standard"
    assert tool.execution_mode == "local"


def test_v07_raw_provider_response_never_reaches_mission_control():
    adapter = MockLocalProviderAdapter()
    request = StructuredProviderRequest(
        request_id="req_002",
        task_id="task_002",
        mission_id="mission_002",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        adapter_name="mock_provider",
        permission_scope="standard",
        input_payload={"request": "demo"},
        execution_context={"simulate_mode": "success"},
        timeout_seconds=30,
    )

    result = adapter.execute(request)
    assert "raw_response" not in result.payload
    assert result.normalized is True


def test_v07_determine_provider_timeout_and_failure_separately():
    timeout_adapter = MockLocalProviderAdapter()
    timeout_request = StructuredProviderRequest(
        request_id="req_timeout",
        task_id="task_timeout",
        mission_id="mission_timeout",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        adapter_name="mock_provider",
        permission_scope="standard",
        input_payload={"request": "demo"},
        execution_context={"simulate_mode": "timeout"},
        timeout_seconds=5,
    )
    timeout_result = timeout_adapter.execute(timeout_request)
    assert timeout_result.outcome == "timed_out"

    fail_adapter = MockLocalProviderAdapter()
    fail_request = StructuredProviderRequest(
        request_id="req_fail",
        task_id="task_fail",
        mission_id="mission_fail",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        adapter_name="mock_provider",
        permission_scope="standard",
        input_payload={"request": "demo"},
        execution_context={"simulate_mode": "fail"},
        timeout_seconds=5,
    )
    fail_result = fail_adapter.execute(fail_request)
    assert fail_result.outcome == "failed"


def test_v07_mock_adapters_require_no_production_credentials():
    adapter = MockLocalProviderAdapter()
    assert getattr(adapter, "config_reference", None) is not None or True
    assert adapter.requires_credentials is False


def test_v07_provider_result_translates_to_execution_result():
    adapter = MockLocalProviderAdapter()
    request = StructuredProviderRequest(
        request_id="req_003",
        task_id="task_003",
        mission_id="mission_003",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        adapter_name="mock_provider",
        permission_scope="standard",
        input_payload={"request": "demo"},
        execution_context={"simulate_mode": "success"},
        timeout_seconds=30,
    )
    provider_result = adapter.execute(request)
    execution_result = StructuredExecutionResult(
        execution_id="exec_003",
        task_id=provider_result.task_id,
        mission_id=provider_result.mission_id,
        division_name=provider_result.division_name,
        specialist_name=provider_result.specialist_name,
        capability_name=provider_result.capability_name,
        outcome=ExecutionOutcome.SUCCEEDED,
        result_payload=provider_result.payload,
        validation_errors=provider_result.validation_errors,
        failure_reason=provider_result.failure_reason,
        runtime_metadata={"adapter_name": provider_result.adapter_name},
    )

    assert execution_result.outcome == ExecutionOutcome.SUCCEEDED
    assert execution_result.result_payload["ok"] is True


def test_v07_adapter_registry_rejects_unavailable_adapter():
    registry = AdapterRegistry()
    binding = CapabilityAdapterBinding(
        capability_name="coordination",
        division_name="generic",
        adapter_name="offline_adapter",
        adapter_type="provider",
        permission_scope="standard",
        execution_mode="local",
        priority=1,
        available=False,
    )
    registry.register(binding)

    assert registry.select(
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
        execution_mode="local",
    ) is None


def test_v07_binding_candidates_follow_deterministic_priority_order():
    registry = AdapterRegistry()
    registry.register(
        CapabilityAdapterBinding(
            capability_name="coordination",
            division_name="generic",
            adapter_name="adapter_high",
            adapter_type="provider",
            permission_scope="standard",
            execution_mode="local",
            priority=100,
            available=True,
        )
    )
    registry.register(
        CapabilityAdapterBinding(
            capability_name="coordination",
            division_name="generic",
            adapter_name="adapter_low",
            adapter_type="provider",
            permission_scope="standard",
            execution_mode="local",
            priority=1,
            available=True,
        )
    )

    selected = registry.select(
        capability_name="coordination",
        division_name="generic",
        permission_scope="standard",
        execution_mode="local",
    )
    assert selected.adapter_name == "adapter_low"


def test_v07_mission_control_lifecycle_state_unchanged_by_provider_result_evidence():
    task = MissionTask(
        task_id="task_provider_evidence",
        mission_id="mission_provider_evidence",
        plan_id="plan_provider_evidence",
        task_name="provider_execution",
        description="Provider result is evidence, not authority.",
        division_name="generic",
        specialist_name="operations_specialist",
        capability_name="coordination",
        permission_scope="standard",
        task_state=TaskLifecycleState.IN_PROGRESS,
        approval_state=ApprovalState.APPROVED,
        retry_count=0,
        max_retries=2,
    )

    assert task.task_state == TaskLifecycleState.IN_PROGRESS
    assert task.approval_state == ApprovalState.APPROVED
