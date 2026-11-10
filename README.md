# Ced-One OS

CED-ONE is a provider-independent AI Operating System foundation. Trading is Proof #1,
governed through Mission Control; Core and Trading evolve together.

The current implementation provides one local Mission Control pipeline, explicit policies and executors, task lifecycle validation, optional durable mission archives, and factual trading analysis. Memory currently stores historical missions only; general context retrieval is not implemented. Core, communication, and generic integration packages remain placeholders. There are no live data feeds, broker connections, external AI calls, or trading execution.

## Run locally

Use Python 3.11 or newer:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/local_candle_analysis.py
```

The example registers a read-only candle executor and a bounded allow policy. It analyzes two completed H1 candles; the third candle is still open at the evaluation time and is excluded. Output includes source identity, causal cutoff, rule version, policy decision and audit reference. Input is synthetic, but the analysis uses the real implementation.

Run a governed multi-analysis mission:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/local_factual_market_context.py
```

This explicitly registers the existing `factual_market_context_composition` route
under a narrow read-only policy. One Mission Control task runs the fixed seven-timeframe,
ten-analysis profile, producing 70 factual envelopes and 60 adjacent relationships.
The demonstration aggregates an invented minute-price path into historical OHLC;
open candles are excluded by the real causal source owner. Output shows routing,
source identities, separate composition state, validation and Mission Control audit.

The execution input contains exactly `symbol="XAUUSD"`, one timezone-aware historical
`requested_evaluation_timestamp`, and `timeframe_histories` with D1/H4/H1/M30/M15/M5/M1
raw OHLC arrays. Configurations and analyzers are fixed by registration. The result
contains `composition` and `evidence` (full sources, source context, factual envelopes
and factual context); native artifacts retain their existing contracts and identities.
Public native validators run before return. Invalid sources or failed analysis validation
fail the task; valid unavailable evidence remains unavailable even when calculation completes.
The host supplies authorization before execution; internal analyses are dependencies of
one approved composite task, without separate Mission Control approvals.

Policy permission and `COMPLETED` concern local analysis execution only. They grant
no trading, margin, payout or financial-risk approval. C1–C12 retain their authority
boundaries and deterministic risk gates remain binding. Live audit is in-memory;
an optional archive retains the finished mission and its complete audit.

Save and recover a mission across separate Python processes:

```sh
archive_dir="$(mktemp -d "${TMPDIR:-/tmp}/ced-one-missions.XXXXXX")"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/local_factual_market_context.py --archive "$archive_dir/missions.sqlite3"
# Use the mission_id printed above:
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/local_factual_market_context.py --archive "$archive_dir/missions.sqlite3" --read YOUR_MISSION_ID
```

Hosts opt in with `MissionControlService(archive=SQLiteMissionArchive(path))` and
read with `get_archived_mission(mission_id)`. Reads return an `ArchivedMission`
marked `HISTORICAL_RECORD_ONLY`, retaining typed request/result, source identities,
original evaluation boundary, policy evidence and audit. No executor is registered
for the example's read mode. Historical success and `UNAVAILABLE` retain their
original meaning; reading grants no new authorization and performs no analysis.

Storage is atomic, versioned and checksummed. First publication never replaces an
existing file. Recovery can repair SQLite rollbackjournals without rerunning a
mission; existing empty or unknown files are refused. Known credential keys,
including API secrets and secret access keys, refuse saving. This field-name
filter is not a complete secretscanner; keep secrets out of inputs and text.
`metadata.archive.status` reports
`stored` or `failed` with a fixed error code. A storage failure preserves the
execution outcome and never retries analysis. Checksums provide content integrity,
not protection against a writer who can also replace the checksum. Archive paths
are host-selected; use a private directory outside the repository. See the
[v1 storage contract](docs/system_architecture.md#durable-mission-archive-v1).

Reuse one archived composition in a new governed synthesis mission. First run the
archive command above and let that process exit. Copy its printed mission ID and
record hash into a second command:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/local_factual_market_context.py \
  --archive "$archive_dir/missions.sqlite3" \
  --synthesize SOURCE_MISSION_ID --record-sha256 SOURCE_RECORD_SHA256 \
  --evaluation-time 2026-09-01T00:00:00Z \
  --created-not-after "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

This selects exactly that record, checks its origin/version/time bindings, and
starts a fresh Mission Control request under current policy. The existing factual
specialist validates the original seven-source/70-envelope evidence, builds native
chronology v2 and synthesis v1, and validates both complete results. The original
mission is not rerun. Both missions remain separately archived; output reports
their IDs, hashes, economic boundary, source identities and native validation.
`--read NEW_MISSION_ID` retrieves the synthesis without execution.

Core callers use `select_archived_context(selection)` for data only, or
`handle_request(..., archive_selection=selection)` for a newly governed request.
No caller-supplied `context` may accompany that selection. The explicit reference
pins mission ID, record SHA-256, division, capability, contract/rule versions, T
and the source request's `created_not_after` limit. That limit is not proof of
historical archive availability. Selection never restores historical approval.
UNAVAILABLE, UNKNOWN, scoped absence and unproven event ordering remain native
facts; successful analysis grants no trading or financial authority.

Replay Strategy #1 against exactly one archived composition with the read-only
`governed_strategy_candidate_replay` capability. The host registers
`register_governed_strategy_candidate_replay_executor(runtime,
strategy_definition=definition, setup_ordinal=0,
entry_validity_duration_seconds=120)` from the Trading execution module.
`definition` is an explicit native XAUUSD Causal Liquidity Reversal v0.2 /
revision_2.1 definition, including its historical domain and configuration; the
example ordinal and duration are host choices, not trading defaults. The complete
normalized profile and native versions are bound into current authorization.

With a matching read-only policy and archive configured, call
`service.handle_request("Governed strategy candidate replay",
business_division="trading", archive_selection=selection)` using the same explicit
composition selection described above. The five original H4/H1/M15/M5/M1 sources
must share T; all seven source slots and the original composition are validated.
The executor reconstructs strategy, directional intent and a technical candidate.
WAITING/UNKNOWN/UNAVAILABLE return no candidate. A returned entry/stop is a frozen
historical technical reference, never a fill or a claim of present validity or
trading permission. Results include native reconstruction inputs, source IDs,
profile hash, audit and a separately archived mission. Reading remains data-only.
See the [execution contract](docs/system_architecture.md#governed-strategy-candidate-replay-v1).

## Execution contract

`MissionControlService` is the official entrypoint. `MissionControlFlow` and `MissionControlOrchestrator` are compatibility wrappers around the same service. Their `handle_request(...)` signature is retained; constructors accept optional `runtime` and `policy` dependencies.

Register executors with `LocalExecutionRuntime.register(contract, executor)`. Each executor receives a `SpecialistExecutionContract` and returns a dictionary validated against its capability contract. The request's `context` supplies that input dictionary. Runtime implementations do not determine task completion.

- No registered executor: `UNSUPPORTED`, with `execution_performed=False`.
- No matching allow policy: denied by default.
- Approval required or escalated: blocked without execution. Caller metadata cannot grant approval.
- `COMPLETED` and `success=True`: execution occurred and the output passed validation.
- Runtime exceptions and invalid output: structured failure results.

Mocks must be registered explicitly. Historical routing examples no longer report successful execution merely because a plan exists. Approval resumption, automatic retry scheduling, in-flight crash recovery and hard interruption of synchronous Python code are not implemented.

## Trading analysis

The library includes market structure, candle morphology, volatility, liquidity, liquidity events, FVGs, displacement, order blocks, structural ranges, premium/discount geometry and factual multi-timeframe composition/chronology.

Direct detector calls analyze supplied history. For causal observations, use the snapshot boundary: timestamps are candle opening times, and only candles whose timeframe duration has elapsed are approved. All OHLC values must be positive and finite; timestamps must include a timezone and be strictly increasing.

Market structure rule `market_structure_v2` uses strictly two-sided pivots. Break detection uses anchors confirmed before the current candle. This intentionally changes older results that counted boundary candles as confirmed pivots; dependent provenance now names v2. Capability wire contracts retain their v1 shape.

## Layout and architecture

`Mission Control → Business Division → Specialist / Capability → registered local executor`

- `src/ced_one/mission_control/`: generic orchestration, contracts, policy and task lifecycle.
- `src/ced_one/business_divisions/trading/`: domain routing, factual analyzers and explicit local execution compositions.
- `tests/`: boundary, regression and producer-to-consumer integration tests.
- `scripts/`: runnable local example.
- `docs/`: governing documents and architecture decisions.

See [system architecture](docs/system_architecture.md), [capability architecture](docs/capability_architecture.md), and [constitution](docs/constitution.md). CI runs the suite and example on Python 3.11–3.13.
