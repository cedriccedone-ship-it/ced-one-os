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

## Explicit archived context and governed synthesis v1

`MissionControlService.select_archived_context(selection)` reads exactly one ID;
it never executes, searches, falls back or restores live history. The sealed
selection has eight required nonempty string fields: `mission_id`, `record_sha256`
(64 lowercase hexadecimal characters), `division`, `capability`, `contract_id`,
`rule_version`, `evaluation_time`, and `created_not_after`. Times are aware
ISO-8601 strings, compared as instants and returned in UTC. The source request,
result and registered source contract must agree on origin; the source must be a
successfully completed read-only calculation. Completion is source eligibility,
never permission for a new execution. Its native factual availability may be
UNAVAILABLE. The requested source contract/rule must equal the archived descriptor.

The source input must contain `requested_evaluation_timestamp` equal to T.
Require T <= source request.created_at <= created_not_after <= selected_at (host
UTC time after reading). These are request-time and current selection constraints:
neither request.created_at nor selected_at proves when the record was committed
or available historically. This API makes no as-of-knowledge or live-state claim.

The isolated projection has exactly `selection` and `original_payload` (a detached
copy of the source result_payload, with no historical policies or approvals).
`selection` has exactly `schema_version=mission_control.archived_context.v1`,
`source_mission_id`, `record_sha256`, `division`, `capability`, `contract_id`,
`rule_version`, `evaluation_time`, `source_request_created_at`, `created_not_after`,
`selected_at`, `payload_sha256`, and `temporal_scope=HISTORICAL_RECORD_ONLY`.
All are strings. The payload digest is SHA-256 of compact ASCII JSON, preserving
dictionary insertion order and disallowing NaN/Infinity. Only exact built-in JSON
types accepted by the existing authorization-data validator may occur in this
projection; enum/dataclass payloads are not coerced to JSON values. It is a consistency
binding, not a signature. Unsupported projections fail with a fixed
`ArchivedContextError` code. No archive schema or migration is introduced.

A new request supplies `archive_selection=selection`, with no `context` argument.
The registered contract must require archived context; caller-supplied projected
evidence cannot substitute for this path. Core selects from its own archive before
policy evaluation, archives the actual projected input, and fingerprints all of it
under the existing governance/dispatcher checks. After an allow decision, it
rechecks payload integrity and the independently captured selection reference
before creating authorization. Policy-time changes, including a recomputed
payload digest or a replaced source-record hash, reject as STALE_ARCHIVED_CONTEXT.
Subsequent mutations remain subject to the existing dispatcher snapshot checks.
Selection errors fail the new
mission without executing. `ARCHIVED_CONTEXT_SELECTED` records the source reference;
`ARCHIVED_CONTEXT_USED` is recorded only when the new executor actually ran. Both
events carry the new mission ID. Old decisions and execution status are never
copied into current authorization. Mutating a standalone projection cannot alter
the archive or a later selection.

The single `archived_market_state_synthesis` executor uses the existing factual
market context specialist, contract `trading.archived_market_state_synthesis.v1`,
rule `archived_market_state_synthesis_v1`, read_only, retryable=false. Only original
`trading.factual_market_context_composition.v1` / rule
`factual_market_context_composition_v1` evidence is accepted. Its exact composition
and evidence bundle is validated through public source, envelope, context and
composition owners, including all seven source slots and the 70-envelope profile.
Null native source identities remain null when their owner reports unavailability.
All native boundaries must equal T; cutoffs must not exceed T. Nothing is retimed.

After validation it constructs native chronology v2, then synthesis v1 with the
fixed native configuration `{}`. Public detached validators check both complete
results. The newly created chronology's Python tuple-valued event-source manifest
is represented as JSON arrays, as accepted by its public serialized validator;
original archived source artifacts and native identities are unchanged.
Output contains exactly `synthesis`, `upstream_bundle` (the native five
fields), `source_evidence` (sources and source_context), `provenance`, and
`metadata`. Provenance retains the selection, seven source IDs, source/factual
context, composition, chronology and synthesis IDs. Metadata retains the wrapper
contract/rule and exact observation_only/read_only boundaries with advisory,
strategy and execution outputs false. UNKNOWN, scoped absence, truncation,
UNAVAILABLE and ORDER_UNPROVEN remain owned by the native analyzers. No source
mission or candle detector is rerun; native proof reconstruction is allowed.
The new mission and its result are independently archived by existing handling.
Analysis completion grants no trading, margin, financial-risk or payout authority.

The existing complete execution-result, task and audit representations are
retained. Larger records still fail explicitly at the unchanged 64 MiB archive
boundary; evidence is never truncated or rerun to make storage succeed.

## Governed Strategy Candidate Replay v1

`governed_strategy_candidate_replay` is a read-only Trading route through the
existing factual market context specialist and MissionControlService. Its contract
is `trading.governed_strategy_candidate_replay.v1`, rule
`governed_strategy_candidate_replay_v1`. The host explicitly registers a normalized
Strategy #1 definition, nonnegative integer setup ordinal and positive integer
candidate entry-validity duration. No strategy/domain/duration defaults are added.
The complete profile, SHA-256 and native version manifest belong to the registered
capability metadata and therefore the current authorization fingerprint. Changing
registration or execution data invalidates existing dispatch authorization.

Input is exactly the existing archive projection (`selection`, `original_payload`),
selected by Core from one explicitly pinned factual-composition mission. The
original seven-source/70-envelope bundle is validated through the same public
owners used by archived synthesis. Its T and source identities are preserved;
no later snapshot is filtered back to T. Strategy #1 uses exactly H4/H1/M15/M5/M1.
Unavailable D1/M30 evidence alone does not preclude that strategy. The pinned native
profile includes Strategy v0.2/revision_2.1 and its factual rules, source/context/
envelope/composition versions, strategy-action v1 and technical-candidate v1.

The executor constructs and publicly reconstructs the strategy assessment, runs
the existing public strategy-action analyzer, and, only for COMPLETE, constructs
and publicly validates the technical candidate formulation. Candidate policy and
directional intent are generated from the registered profile; callers supply no
artifacts, approval, alternate executors or native configuration. Native failures
fail the mission. Missing evidence is not fabricated or converted to a signal.

Output keys are `outcome`, `strategy_assessment`, `action_formulation`,
`candidate_formulation`, `candidate`, `reconstruction`, `provenance`, `metadata`,
`authority`, `execution`. Reconstruction contains `assessment_input`,
`action_input`, `candidate_input` (null unless strategy COMPLETE). The two
formulation/candidate fields are null for non-COMPLETE strategy states. Outcome
is UNAVAILABLE if any required source is unavailable; otherwise it preserves
WAITING/UNKNOWN/INVALIDATED/EXPIRED. COMPLETE yields CANDIDATE_FORMULATED or
NOT_FORMULATED according to the native candidate geometry. Entry/stop/direction,
valid_from/valid_until and native identities are preserved exactly. A candidate
is a frozen historical formulation, not an assertion of validity at T or now.
Current candidate validity remains the separate existing native owner.

Provenance binds the complete source selection, new mission ID, original seven
source IDs, five strategy source IDs, economic T, profile/hash and native version
manifest. The wrapper's seven authority fields (quantity_selection,
budget_approval, position_effect_compliance, margin_capital_approval,
trade_decision, financial_risk, execution) and top-level execution are exact false.
Native false flags are retained. No fill, size, financial P&L, provider compliance
or permission is implied; FROZEN_AWAITING_PAYOUT remains a separate mandatory veto.
Existing selection/audit/archive behavior is reused without schema or runtime
changes. Archive availability is not backdated and reading never re-executes.

## Governed Reference Backtest v1

`governed_reference_backtest` is one read-only Mission Control capability using
`factual_market_context_analyst`. Contract `trading.governed_reference_backtest.v1`,
rule `governed_reference_backtest_v1`. It runs only the existing native reference
scenario variant A: initial reference stop, fixed +3R target, 1440 elapsed minutes.
It supplies no fills, quantity, monetary P&L, current eligibility or trading rights.

The host explicitly calls `register_governed_reference_backtest_executor(runtime,
observation_profile=profile)`. Profile input has exactly `research_boundary`, `m1`
(the complete native observation source) and `declarations` (the original native
research relationships). Registration isolates this JSON data and adds the native
version manifest. The complete registered profile, its SHA256, variant A and
registration identity enter the existing authorization snapshot. SHA256 uses UTF-8
JSON with sorted keys, compact separators and `allow_nan=False`; array order is
preserved. Another profile requires another registration and fresh authorization.
No analyzer runs at registration; native replay follows current governance.

Call `MissionControlService.handle_request("Governed reference backtest",
business_division="trading", archive_selection=selection)`. The existing eight
selection fields pin exactly one `governed_strategy_candidate_replay` source with
contract `trading.governed_strategy_candidate_replay.v1` and rule
`governed_strategy_candidate_replay_v1`. Direct payloads/extra context are rejected.
Only this exact source contract may obtain its economic T from the validated
archived input projection. Raw factual source selection retains its old rules.
Source creation/selection times do not prove historical archive availability.

The source must contain CANDIDATE_FORMULATED and complete native reconstruction
inputs; otherwise the mission fails explicitly with NO_CANDIDATE. The executor
reconstructs the original assessment and candidate, compares the original action,
profile, setup ordinal, duration, false authority, identities and economic boundary.
The five native strategy source identities are checked against both original
identity maps. All seven archived source references remain parent provenance;
this wrapper does not independently rerun the original 70 factual envelopes or
claim external feed authentication. The original record hash binds the selected
parent result; hashes do not authenticate its provider.

V1 requires C = candidate.valid_from = original assessment T. H = C + 1440
minutes; H <= K = research_boundary <= current UTC time. Observation M1 has exactly
K as its requested boundary. No observation data enters the candidate replay.
The native scenario excludes the T1-producing interval and scans openings C <= t
< H, requiring the T1 anchor and unchanged overlapping original M1 candles. Entry
validity duration never extends or truncates the reference observation horizon.
Missing intervals are not filled, skipped or repaired with later observations.

Declarations are explicit, unauthenticated research assumptions, including their
available_at, dataset identity/revision, price domain, grids and coverage. They
bind the full original candidate/formulation input and observation artifact.
They are never generated or backdated by the executor. A relationship available
after the first required interval causes native MISSING_DATA_CENSORED, even if
later data exist. An early timestamp in a synthetic fixture is an assumption,
not proof that its completed future dataset was available then. Actual historical
source availability and provider identity remain outside this research result.

Output has exactly `outcome`, `scenario`, `reconstruction`, `provenance`,
`metadata`, `authority`, `execution`. The scenario and reconstruction are native;
`validate_reference_scenario` completely replays them before return. Outcome is
native completion_status: RESOLVED, AMBIGUOUS, HORIZON_CENSORED,
MISSING_DATA_CENSORED or END_OF_DATA_UNRESOLVED. Exact reduced rational result
bounds and nulls are retained. Opening gaps use native reference marks; intrabar
stop/target ambiguity retains both alternatives. Neither becomes a fill claim.
Provenance includes both missions, selected hash, candidate identity, original
candidate provenance, T/C/H/K, observation profile hash and native versions.
Metadata scope is RETROSPECTIVE_REFERENCE_RESEARCH, source_authentication is
NOT_VERIFIED. The seven existing authority flags and top-level execution are
exact false. Historical policies grant no new authorization. The independent
FROZEN_AWAITING_PAYOUT veto remains mandatory.

Existing audit, snapshot mutation checks, default-deny and archive failure behavior
are reused. A storage failure stays visible as archive.status=failed after a
completed calculation and causes no automatic retry. Recovery reads historical
data without execution. No SQLite schema, runtime or native owner is changed.

## Local historical XAUUSD import and causal replay v1

`scripts/local_historical_replay.py` feeds three existing independently governed
missions: factual composition, strategy candidate replay, reference backtest A.
There is no new capability. Each consumer explicitly selects its predecessor's
archived mission ID and record SHA256. A failed archive or absent candidate stops
the chain, without retry. Completed research may still be ambiguous or censored.

The bounded input contract is `trading.historical_market_data.v1`. The UTF-8 CSV
has exactly `timeframe,timestamp,open,high,low,close`, in that column order.
Groups use D1,H4,H1,M30,M15,M5,M1 order; timestamps within each are strictly
increasing. Timestamps label openings and require explicit UTC offsets, normalized
to UTC. Every duplicate UTC opening rejects the export, including equal prices.
Prices are positive finite decimal text, converted to native binary floats and
validated by existing OHLC rules. Original bytes remain hash-bound; arbitrary
decimal precision and source authenticity are not claimed. No sorting, filling,
resampling, symbol mapping or broker-timezone inference takes place.

The JSON manifest has exactly: `contract`, `symbol` (XAUUSD), `source_namespace`,
`dataset_id`, `dataset_revision`, `price_basis` (BID/ASK/MID/LAST), `csv_sha256`
(lowercase SHA256), `timeframes`, `sessions`, `dataset_end`. Nonempty identifiers
are strings. `timeframes` maps supplied native timeframe names to exactly `anchor`,
`coverage_start`, `coverage_end` (offset-aware times). Native fixed durations and
the supplied grid anchor govern each row. Coverage is half-open and contains each
whole supplied candle; it does not assert missing rows exist. Missing timeframe
slots stay empty. The strategy needs H4/H1/M15/M5/M1; D1 and M30 can be unavailable.
`sessions` is an ordered disjoint array of exact `{open,close}` UTC intervals.
Every M1 interval must lie inside one session. Higher-timeframe bars keep their
fixed durations and may span session closures. `dataset_end` is null or an
explicit M1 completion endpoint. Duplicate JSON keys and extra keys are rejected.
Each local file is limited to 16 MiB; archive records retain their existing limit.

Session declarations are research input, not a market-calendar authority. Neither
closures nor data gaps waive the native contiguous-history requirement. Thus a
real weekend or daily maintenance break may cause UNKNOWN or censoring. No
shortened D1 candle, DST adjustment or compressed time is introduced.

The JSON run has exactly `contract`, `T`, `K`, `strategy_definition`,
`setup_ordinal`, `entry_validity_duration_seconds`, `relationship_available_at`.
The strategy profile uses the existing native schema/version. T/H/K are explicit:
C=T, H=T+24 hours, H<=K<=now. Candidate histories start at their configured native
history domains and contain only candles whose opening plus duration is <=T.
Other supplied timeframe domains start at their declared coverage start.
Observation M1 contains the [T-1 minute,T) anchor and rows opening in [T,H).
Later candles never enter candidate replay. No automatic search for a favorable
T or change of strategy configuration occurs.

Native dataset relationship bindings are computed from the actual validated
candidate/formulation and observation artifacts. `relationship_available_at` is
copied from run input, never inferred from T or the import time. Availability
after the first required completion causes native censoring; after K rejects.
Early synthetic timestamps remain explicit research assumptions. Candle closure
does not prove historical receipt or publication, and importing now does not
establish archive availability at T.

Import provenance contains complete CSV and manifest-byte hashes, original
manifest JSON and actual import time. Factual and observation input hashes are
stored in registered capability metadata, bound by current authorization and
checked before native analysis. The candidate mission binds its complete selected
projection and strategy profile through existing governance; its source record
links to the import provenance. Native sealed output schemas are unchanged.
Post-T export changes can change archive hashes and R outcomes while native
candidate identity, input, entry and stop remain identical. All native false
authority fields, current default-deny, approval and post-policy mutation checks
remain mandatory. Recovery is historical data retrieval without execution.

Normal local command (paths explicitly supplied by the user):
`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/local_historical_replay.py --dataset /tmp/xauusd/candles.csv --manifest /tmp/xauusd/manifest.json --run /tmp/xauusd/replay.json --archive /tmp/xauusd/missions.sqlite3`.
`--demo DIRECTORY` instead generates labelled synthetic existing producerfixtures
outside the repository and executes LONG/SHORT target/stop runs. Only demo mode
imports test fixtures. It asserts identical candidates under changed post-T data.
Real use requires a licensed export with known price basis, native grids, session
boundaries and sufficient warm-up/observation data. An M1-only feed requires a
separate resampling contract; this importer does not synthesize other timeframes.

## Historical batch replay v1

The existing local historical CLI accepts `--prepare-batch PLAN` with `--dataset`,
`--manifest` and the original `--run replay.json`. Preparation executes no mission.
It publishes a closed `trading.historical_batch_replay.v1` plan, plus its canonical
SHA256, before execution. Raw profile text and its byte SHA256, full dataset and
manifest hashes, native versions and every ordered point are included. The fixed
first plan uses 16, 17 and 24 September 2026, 13:00 through 13:04 UTC, LONG then
SHORT, ordinal zero and 120-second validity. Founding is 12:00 through 13:04 per
day. Starts are fixed per session: 12 H4, 12 H1, 8 M30, 32 M15, 30 M5 and 60 M1
periods before founding; D1 is explicitly absent. The original profile's other
strategy settings, K and relationship availability remain unchanged. Selection
uses explicit dates, timestamps, session declarations and coverage, never setups
or outcomes. Missing coverage is reported, never repaired by selecting other data.

`--batch PLAN --dataset CSV --manifest JSON --archive DB --report REPORT` validates
the complete plan and source hashes before creating an exclusive external report.
That report durably contains every planned point before the first mission. The
runner sequentially invokes the existing three independently governed missions;
there is no new capability or scheduler. The actual bounded inputs and strategy
profiles retain existing current authorization binding. Plan/report hashes provide
research traceability, not new authorization or independent preregistration proof.
Each consumer selects its exact archived predecessor ID/hash. Native sources,
envelopes, composition, assessment, action, candidate and reference scenario keep
their existing public validation. Native authorities and execution remain false.

All seven factual windows have explicit starts (null means intentionally absent
for a non-strategy timeframe). Candles must close by T. Original M1 observations
retain the [T-1 minute,T) anchor and [T,T+24 hours) openings. No source history is
sorted, filled, compressed or resampled. Closures remain gaps under native rules.
CA1 requires a confirmed H1 pivot and a closed right-hand neighbour; more candles
do not guarantee confirmation, H4 structure or a setup. Replay may stop UNKNOWN
at its first founding boundary. This slice does not reinterpret that outcome.

Each row retains assessment reason, identities, candidate, reference status/R or
uncertainty, mission IDs, record hashes and actual serialized record byte sizes.
Reports checkpoint after each mission and point. A completed candidate with C!=T
is retained with `SKIPPED_C_NE_T`; it never enters reference execution. WAITING,
UNKNOWN and UNAVAILABLE remain observations. Unique setups/completions are counted
by native identities; observation multiplicities remain visible, and repeated
completions do not inflate unique-backtest counts. Technical errors are explicit;
an archive or IO failure aborts without retry, marking remaining points
`NOT_RUN_ABORTED`. If external report storage itself fails, the command fails and
the last published report remains evidence; automatic resume is unsupported.

The archive's exact 67,108,864-byte record limit is unchanged. Bounded candle
windows reduce duplication, but no candle-count estimate guarantees record size;
the existing serializer remains authoritative. Oversize storage aborts the batch,
without shrinking windows, discarding evidence or rerunning an executor. Each
input file retains its existing 16-MiB limit. Existing reports/plans are never
silently overwritten; reruns require a new report path and fresh governance.

Dataset declaration availability is never inferred from T or rewritten. Late
availability may produce `MISSING_DATA_CENSORED` at the first required observation;
K does not retroactively make a declaration available. Real source authentication
is not established by CSV hashes or provider labels. The standalone
`--demo-batch NEW_DIRECTORY` uses one labelled synthetic native producer fixture
and verifies all three archived missions with the +3R reference outcome. It does
not execute the 30-point real-data plan. No broker, financial P&L or trading
permission is introduced.

### Explicit batch schedules

`--prepare-batch PLAN --schedule JSON` optionally replaces the fixed first plan's
dates with explicit founding-start/evaluation pairs. The schedule has exactly
`{"contract":"trading.historical_batch_schedule.v1","sessions":[{"founding_start":"2026-09-16T12:00:00Z","T":"2026-09-16T12:30:00Z"}]}`.
It requires 1..500 sessions, distinct increasing starts, timezone-aware timestamps
normalized to UTC, whole minutes and start <= T. Existing source-grid, native
definition and T/H/K checks still apply. Each pair generates LONG then SHORT,
ordinal zero, 120-second candidate validity, founding_end=T and the same fixed
warmup counts described above; the normalized founding timestamp is session_id.
The original profile text/hash, K and declaration availability are retained.
Expanded ordered points are included in the existing plan hash and validated
before exclusive atomic publication; schedule input is protected from overwrite.
Without `--schedule`, the original 30-point generator and output are unchanged.
The option is accepted only during preparation, executes no missions and changes
neither the batch engine nor Mission Control/native ownership or trading authority.

## Local historical candidate scan v1

`scripts/local_historical_candidate_scan.py --prepare PLAN --dataset CSV
--manifest JSON --run replay.json` seals a `trading.historical_candidate_scan.v1`
plan without analysis or execution. It wraps the existing batch plan (original
profile bytes/hash, CSV/manifest hashes, native versions and exact point inputs),
the diagnostic contract and explicit control point IDs in one canonical SHA256.
The first scan fixes 18 September 12:00, 23 September 16:00 and 25 September 20:00
UTC, each through +30 minutes inclusive, LONG then SHORT: 186 independent points.
Founding end is fixed at +30 for every point in a block; the existing fixed
warmup counts, ordinal zero, 120-second validity, K and declaration availability
are preserved. Start, midpoint and endpoint for both directions are the 18
controls, chosen before calculation. Validation requires those controls for each
block/direction; their label never asserts that they will actually be negative.

`--scan PLAN --dataset CSV --manifest JSON --report REPORT --archive DB` validates
the complete sealed input, exclusively publishes every planned report row, then
constructs and publicly validates the same seven causal sources without factual
envelopes. Each T has its own native replay and detached strategy validation;
only candles closed by T are supplied. No cross-point state, lookahead or retry
is introduced. Native UNKNOWN, WAITING, terminal states, source UNAVAILABLE and
technical errors remain separate. Reports retain full assessments and traces,
input hashes and all seven source IDs/hashes; original datasets are required for
reconstruction. Transition summaries identify changes per block/direction, while
the complete native trace retains intermediate boundaries and early termination.

`analyze_with_diagnostics()` is an optional public strategy method. Its separate
`trading.xauusd_causal_liquidity_reversal.diagnostics.v1` trace observes the same
founding/progression/terminal control flow and evidence. It changes no assessment
field, identity, rule version or strategy condition. Trace reasons are diagnostic
labels, not additional native strategy outcomes or authority. Simultaneously open
progression prerequisites are reported as absent bindings, not an invented order.

Every COMPLETE with T1 available exactly at T is a possible completion, not a
candidate approval. Every possible completion and every control is independently
reconstructed again, then sent through the existing fresh-governed factual,
archived candidate-replay and, where applicable, variant-A reference missions.
Full assessment/input hash, seven sources, setup/completion/T1, predecessor
identity/hash and exact false authority are compared against archived results.
Reports retain plan/point hashes, comparisons and original mission IDs/record
hashes. Denial/approval pending is not a match. Mismatch, storage failure or
verification failure stops further verifications without retry, preserving all
scan rows and marking required remaining verifications NOT_RUN_ABORTED. Failed
report publication raises an error; there is no automatic resume or reexecution.

`--demo NEW_DIRECTORY` uses genuine existing LONG/SHORT producer fixtures at the
completion minute and both neighboring minutes, verifying all six points through
Mission Control and archiving results outside the repository. Scan reports grant
no authority: all seven flags and execution are false. Archive schema, exact
64-MiB per-record limit and native reference semantics remain unchanged. In
particular late declarations and missing M1 still censor R; no broker execution,
financial return claim, source authentication or retrospective time rewrite is
introduced. Real 186-point execution and full regression are separate operations.

### Explicit scan preparation schedule

`--prepare PLAN --schedule JSON` accepts the sealed-input preparation contract
`trading.historical_candidate_scan_schedule.v1`. The JSON has exactly `contract`
and `blocks`. Each of 1..16 chronologically ordered, unique, disjoint blocks has
exactly `founding_start`, `founding_end`, `measurement_step_seconds: 60`,
`directions: ["LONG", "SHORT"]` and `control_offsets_minutes: [0, N//2, N]`.
Timestamps use canonical UTC `YYYY-MM-DDTHH:MM:00Z`; starts align to the export's
H4 anchor, and N is the integer block duration, 2..30 minutes. Every minute from
start through end is expanded LONG then SHORT. The fixed warmup, ordinal zero,
120-second validity, original profile, K and declaration availability are retained.
The existing batch/scan validators, source/profile/version hashes and exclusive
atomic publication produce the same scan-plan grammar. The schedule's executable
meaning is fully represented by the expanded points and control IDs; no separate
schedule hash or archive schema is introduced. Identical inputs give identical
plan hashes, independently of import time. At most 992 points are generated.

Explicit preparation checks every expected closed candidate candle from each
fixed warmup start through the block end. All measurement boundaries must lie
inside one declared half-open session. Gaps, including session breaks inside
native evidence windows, are never filled or skipped. Coverage errors return JSON
with the block, timeframe and exact missing UTC opening times; no plan is
published. Successful CLI output includes the coverage findings. Observation M1
coverage is reported separately as the union `[block start - 1 minute,
block end + 24 hours)` for all T in that block, including exact missing openings.
Those gaps do not block candidate preparation and do not prove usable R evidence.
Late declarations and observation gaps retain native reference censorship.

`--schedule` is rejected with scan/demo execution and is protected from output
overwrite, as are CSV, manifest and profile. Existing output plans cannot be
overwritten. Preparation invokes no analyzers, executors or archive operations.
Without `--schedule`, the original 186-point/18-control generator and hash remain
unchanged, including its existing handling of incomplete research evidence. The
scan control validator uses the lower middle point for even-length point arrays;
its selection for the existing odd-length/default arrays is unchanged. Native
strategy, scan execution, current governance, authority flags, 64-MiB record limit
and reference semantics are unchanged.
