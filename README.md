# Ced-One OS

A provider-independent Python foundation for governed capability execution, with a deterministic XAUUSD analysis library.

The current implementation provides one local Mission Control pipeline, explicit policies and executors, task lifecycle validation, in-memory audit records, and factual trading analysis. Core, memory, communication, and generic integration packages remain placeholders. There are no live data feeds, broker connections, external AI calls, or trading execution.

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

## Execution contract

`MissionControlService` is the official entrypoint. `MissionControlFlow` and `MissionControlOrchestrator` are compatibility wrappers around the same service. Their `handle_request(...)` signature is retained; constructors accept optional `runtime` and `policy` dependencies.

Register executors with `LocalExecutionRuntime.register(contract, executor)`. Each executor receives a `SpecialistExecutionContract` and returns a dictionary validated against its capability contract. The request's `context` supplies that input dictionary. Runtime implementations do not determine task completion.

- No registered executor: `UNSUPPORTED`, with `execution_performed=False`.
- No matching allow policy: denied by default.
- Approval required or escalated: blocked without execution. Caller metadata cannot grant approval.
- `COMPLETED` and `success=True`: execution occurred and the output passed validation.
- Runtime exceptions and invalid output: structured failure results.

Mocks must be registered explicitly. Historical routing examples no longer report successful execution merely because a plan exists. Approval resumption, automatic retry scheduling, persistent audit storage and hard interruption of synchronous Python code are not implemented.

## Trading analysis

The library includes market structure, candle morphology, volatility, liquidity, liquidity events, FVGs, displacement, order blocks, structural ranges, premium/discount geometry and factual multi-timeframe composition/chronology.

Direct detector calls analyze supplied history. For causal observations, use the snapshot boundary: timestamps are candle opening times, and only candles whose timeframe duration has elapsed are approved. All OHLC values must be positive and finite; timestamps must include a timezone and be strictly increasing.

Market structure rule `market_structure_v2` uses strictly two-sided pivots. Break detection uses anchors confirmed before the current candle. This intentionally changes older results that counted boundary candles as confirmed pivots; dependent provenance now names v2. Capability wire contracts retain their v1 shape.

## Layout and architecture

`Mission Control → Business Division → Specialist / Capability → registered local executor`

- `src/ced_one/mission_control/`: generic orchestration, contracts, policy and task lifecycle.
- `src/ced_one/business_divisions/trading/`: domain routing, factual analyzers and explicit candle execution composition.
- `tests/`: boundary, regression and producer-to-consumer integration tests.
- `scripts/`: runnable local example.
- `docs/`: governing documents and architecture decisions.

See [system architecture](docs/system_architecture.md), [capability architecture](docs/capability_architecture.md), and [constitution](docs/constitution.md). CI runs the suite and example on Python 3.11–3.13.
