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

These are in-process application guarantees for trusted registered code, not a sandbox for arbitrary Python. Live audit records are held in memory. The optional mission archive below durably stores finished request handling; neither audit representation is tamper-proof.

## Task lifecycle

One transition table governs task and graph operations. Normal execution is pending → ready → assigned → in progress → completed. Dependencies and approval gate readiness and execution. Completed, cancelled and rejected tasks are terminal. Mutation is validated before state is changed.

Failure precedes retry pending. A retry requires `retryable=True` and a remaining budget; entering retry pending consumes one retry. The graph propagates dependency failure transitively. Recoverable dependency blocks may clear once the predecessor completes. The service performs one attempt per request; a scheduler and automatic retries are outside the current implementation.

Only Mission Control records final task outcomes after output validation. Planning alone never implies successful execution. `metadata.execution_performed` distinguishes dispatch rejection from an execution attempt.

## Local candle reference implementation

The trading executor creates a source snapshot, rejects invalid/unavailable sources, and passes only approved closed candles to the real candle analyzer. The final payload adds source identity, cutoff, completion state, contract and rule version. Policy results, runtime result, task graph and audit reference accompany the mission result.

No live providers, broker operations or automatic approval continuation are part of this pipeline. Timeouts declared on contracts remain descriptive for synchronous local executors; they do not forcibly interrupt Python functions.

## Durable Mission Archive v1

The host may inject `SQLiteMissionArchive(path)` into `MissionControlService(archive=...)`.
Without it, execution behavior is unchanged. Each finished request, including rejected,
blocked and failed requests, attempts one save. `get_archived_mission(mission_id)` reads
an `ArchivedMission`: `mission_id`, `request`, `result`, `policy`, `record_sha256`, and
the constant `temporal_scope=HISTORICAL_RECORD_ONLY`. Reading neither dispatches nor
populates live execution history. A missing ID raises `MissionNotFoundError`.

The v1 SQLite database has application ID `0x43454431`, user version 1, and one table
`missions(mission_id TEXT PRIMARY KEY NOT NULL, version INTEGER NOT NULL,
record_json TEXT NOT NULL, record_sha256 TEXT NOT NULL)`. A save uses one transaction
and never replaces a record. Identical content for the same ID is idempotent;
different content raises `MissionConflictError`. New database files use mode 0600;
the host supplies an existing, trusted parent directory on a local filesystem
supporting atomic hard links and directory fsync. Initialization builds, commits,
closes and fsyncs a private temporary database in that directory. A hard link
publishes the complete database without replacing an existing path; the parent
directory is then fsynced. Concurrent initializers validate whichever complete
database won publication. No active SQLite connection uses the temporary name
after publication. An abrupt initialization crash may leave private `.init-*`
files, which are not adopted or automatically deleted. A leftover after publication
can be a hard-link alias of the archive, not an independent snapshot. Hosts must
use only the selected archive path for SQLite access. A published database can be
valid but empty if the process died before its first mission commit.

Existing empty files (including remnants from the earlier initialization method),
foreign databases and unknown versions are refused, never initialized or replaced.
An empty file cannot prove archive ownership; the host must inspect and relocate
it explicitly before choosing a missing archive path. Reads never create files.
They first use SQLite read-only mode. Only `SQLITE_READONLY_ROLLBACK` permits a
second connection to the existing database in `mode=rw`, with SQL `query_only=ON`,
so SQLite can recover its rollbackjournal. Schema checks, SQLite `quick_check`,
record hashes, types and identities must pass before returning recovered evidence.
Recovery restores database consistency only; it never resumes mission execution.
Other storage failures, lock timeouts (five seconds), schema mismatches, corrupt
records and unsupported versions have explicit errors. No migrations or mission
retries are automatic.

`record_json` is compact, ASCII JSON with sorted object keys and no NaN/Infinity.
Its exact keys are `version`, `mission_id`, `request`, `result`, `policy`.
Version is the exact integer 1. Mission ID is a nonempty string equal to both
request/result IDs. Request/result are tagged `MissionRequest`/`MissionResult`.
Policy is a tagged dictionary containing exactly `policy_id` (string),
`policy_version` (integer), `default_decision` (`PolicyDecision`). Evaluated
decisions, bindings and fingerprints remain in the original result/audit.
The complete input, native evidence, economic boundaries and result are retained
without domain reinterpretation. SHA-256 binds the exact UTF-8 record bytes.

Every value uses a tagged JSON array: `["null"]`, `["bool",boolean]`,
`["str",string]`, `["int",canonical lowercase signed hexadecimal string]`,
`["float",finite float.hex() string]`, `["list",nodes]`,
`["dict",[[string,node],...]]` (unique keys in original insertion order),
`["enum",type_name,member_name]`, `["datetime",ISO-microseconds,fold,zone_name]`,
or `["dataclass",type_name,[[field_name,node],...]]` (all declared fields in
declaration order). List and dictionary insertion order are preserved: native
source hashes depend on original OHLC key order. Encoding is deterministic for
that complete ordered value; reordering a dictionary changes archived content.
Shared object aliases are not preserved. Supported datetimes are aware built-in `datetime` values
with fixed-offset `datetime.timezone`, retaining offset, name and fold. Naive or
named-zone datetimes, cycles and unsupported Python types fail explicitly.
Nesting beyond 100 levels and records exceeding 64 MiB also fail explicitly.

The closed type allowlist is `MissionRequest`, `MissionResult`,
`RequestClassification`, `DivisionResolutionResult`, `ApprovalRequirement`,
`AuthorityValidationResult`; enums are `RequestStatus`, `ApprovalState`,
`PolicyDecision`. Dataclass fields must match their declared types exactly.
No pickle, dynamic imports, caller type registration, authorization snapshots,
executor objects or executable policies are deserialized. Decode must re-encode
to the same bytes, preserving booleans versus integers and enum/dataclass types.

Known credential-key names, including password, token, API key, API secret,
secret access key, AWS credential fields, bearer/session/ID tokens, authorization
and credentials, refuse the entire save (`SENSITIVE_DATA`), including nested
dictionaries inside lists. Matching ignores case and non-alphanumeric separators;
nothing is redacted into an apparently original record. This is an explicit
field-name denylist, not a complete secretscanner: unlisted field names and opaque
strings may contain secrets. Hosts must keep credentials out of mission inputs,
outputs and errors. Archive
errors expose fixed codes, never database exception text or payload values.
Successful saves add `metadata.archive.status=stored`; failures instead add
`status=failed` and a fixed `error_code` (unexpected store exceptions use
`ARCHIVE_ERROR`). Original execution status, success and
errors remain unchanged. Storage failure never reruns analysis. Disabled archives
add no metadata. An interrupted, uncommitted mission is not retained or rerun;
SQLite journal recovery preserves previously committed records.

This is historical task memory, not source authentication, a signature, current
market evidence or renewed authorization. Checksums detect inconsistency, not a
hostile writer who can replace content and checksum. Retrieval preserves native
artifacts without executing their producers or granting cached approval. A new
mission always requires current policy and registration. Financial owners,
UNKNOWN/unavailable semantics and the separate payout veto remain unchanged.
