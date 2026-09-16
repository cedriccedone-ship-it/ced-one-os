"""Explicit executors and policies for historical orchestration scenarios."""
from ced_one.mission_control.runtime import CapabilityExecutionContract, LocalExecutionRuntime
from ced_one.mission_control.policy import ExecutionPolicy, PolicyDecision, PolicyRule
from ced_one.mission_control.types import MissionRequest


def configured_control(cls, divisions):
    runtime = LocalExecutionRuntime()
    rules = []
    for name, division in divisions.items():
        request = MissionRequest("market coordination", business_division=name)
        specialist_fn = getattr(division, "resolve_specialist", None) or getattr(division, "identify_specialist", None)
        capability_fn = getattr(division, "resolve_capability", None) or getattr(division, "identify_capability", None)
        if not specialist_fn or not capability_fn:
            continue
        specialist, capability = specialist_fn(request), capability_fn(request)
        if not specialist or not capability or not specialist.get("name") or not capability.get("name"):
            continue
        # Fixture-owned constant result: no external operations or lasting effects.
        runtime.register(CapabilityExecutionContract(capability["name"], name, capability["contract"], permission_scope=specialist["permission_scope"], output_schema={"required_fields": ["ok"]}, metadata={"risk_level": "low", "impact_level": "limited"}), lambda request: {"ok": True})
        rules.append(PolicyRule("allow_" + name, 1, 1, PolicyDecision.ALLOW, division_name=name, capability_name=capability["name"], permission_scope=specialist["permission_scope"], execution_mode="local"))
    return cls(division_registry=divisions, runtime=runtime, policy=ExecutionPolicy("test", 1, rules=rules))
