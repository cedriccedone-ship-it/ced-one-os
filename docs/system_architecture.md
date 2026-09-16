# System Architecture

Status: local execution foundation; no external execution integrations.

## One execution pipeline

`MissionControlService` owns intake, resolution, binding validation, policy evaluation, task state, dispatch, output validation and audit. The earlier Flow and Orchestrator names delegate to this implementation. The compatibility dispatcher also uses the service.

Requests resolve against explicitly registered business divisions. A division supplies specialist/capability bindings; the local runtime holds executors and contracts indexed by `(division_name, capability_name)`. Mission Control never imports trading detectors. Trading composition registers its own implementations.

Input comes from `MissionRequest.context`. An explicit dispatcher input, including `{}`, takes precedence over stored task input. Prior output cannot satisfy an input contract. The selected contract must agree with division, capability, permission scope and the division's contract identifier. A missing executor is unsupported, not completed.

## Authority and policy

Default policy denies. Missing required context denies even under an allow-default policy. Constrained rules require present, equal bindings. Valid matching rules retain the priority, severity, version, effective-time and rule-id precedence.

Risk/impact classification in the official service comes from the registered capability contract, not caller metadata. Caller approval/impact metadata can impose a gate but cannot grant approval. No approval-resumption API is provided in this release.

Authorization uses SHA-256 over canonical context: task/mission identity, state, bindings, permissions, mode, policy identity/version, adapter type, connector identity/version, input, capability contract and risk classification. Evaluation time is excluded from identity. Immediately before execution, the dispatcher rebuilds context, checks its snapshot and evaluates the current policy again. Input or binding changes invalidate earlier authorization.

These are in-process application guarantees for trusted registered code, not a sandbox for arbitrary Python. Audit records are held in memory and are not tamper-proof or durable.

## Task lifecycle

One transition table governs task and graph operations. Normal execution is pending → ready → assigned → in progress → completed. Dependencies and approval gate readiness and execution. Completed, cancelled and rejected tasks are terminal. Mutation is validated before state is changed.

Failure precedes retry pending. A retry requires `retryable=True` and a remaining budget; entering retry pending consumes one retry. The graph propagates dependency failure transitively. Recoverable dependency blocks may clear once the predecessor completes. The service performs one attempt per request; a scheduler and automatic retries are outside the current implementation.

Only Mission Control records final task outcomes after output validation. Planning alone never implies successful execution. `metadata.execution_performed` distinguishes dispatch rejection from an execution attempt.

## Local candle reference implementation

The trading executor creates a source snapshot, rejects invalid/unavailable sources, and passes only approved closed candles to the real candle analyzer. The final payload adds source identity, cutoff, completion state, contract and rule version. Policy results, runtime result, task graph and audit reference accompany the mission result.

No live providers, broker operations, persistence or automatic approval continuation are part of this pipeline. Timeouts declared on contracts remain descriptive for synchronous local executors; they do not forcibly interrupt Python functions.
