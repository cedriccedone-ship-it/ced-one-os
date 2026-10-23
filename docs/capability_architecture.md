# Capability Architecture

Mission Control coordinates generic contracts. Business divisions own domain resolution and explicitly register local capability implementations. Providers remain replaceable behind execution contracts.

## Public interfaces

`CapabilityExecutionContract.to_dict()` serializes the registration contract. Input and output schemas currently specify required dictionary fields. Domain executors perform deeper semantic validation; these schemas are not full JSON Schema implementations.

`LocalExecutionRuntime.register(contract, executor)` registers one executor for a division/capability pair. The executor accepts a `SpecialistExecutionContract` and returns a dictionary. Registration is not authorization: the caller must also configure an applicable execution policy. Mocks have no implicit default registration.

The first officially integrated trading executor is candle intelligence. Other analyzers remain callable library capabilities and are not automatically wired to Mission Control.

## Trading rules and provenance

Shared validation checks finite positive OHLC values, possible candle boundaries, explicit timezones and increasing timestamps. Direct detectors analyze supplied history; the causal snapshot boundary owns completion based on opening timestamps plus timeframe duration.

Market structure rule `market_structure_v2` excludes both boundary candles from confirmed pivots. Structure uses all confirmed pivots; break detection uses the structure and anchors available before the current candle. Liquidity and dealing ranges consume the same pivot source. Existing capability contracts retain their serialized v1 shape, while dependent rule references identify v2.

Causal envelopes preserve analyzer output and source/configuration identities. Chronology consumes five real event families through their existing producer schemas; FVG rule branches are read from `evidence.rule_branch`. Absent, unavailable, invalid and not-evaluated remain distinct outcomes.

## H1–H5 hardening contracts

These rules extend completed slices; they add no strategy, confirmation/disqualification, lifecycle or Mission Control authority behavior.

| Owner | Contract / rule |
| --- | --- |
| #6 Liquidity Intelligence | Wire contract v1; `liquidity_intelligence_v2` |
| #9 Liquidity Events | Wire contract v1; `liquidity_events_v2` |
| #10 Order Block Intelligence | Wire contract v1; `order_block_intelligence_v2` |
| #13 Source Snapshot | Existing v1 contract, rule and snapshot identity recipe |
| #14 Source Context | Existing v1 contract, rule and context identity recipe |
| #15 Factual Envelope | Wire contract v1; `causal_factual_intelligence_envelope_v3` |
| #16 Factual Context | Wire contract v1; `causal_factual_multi_timeframe_context_v3` |
| #18 Composition | Existing v1 contract and rule |
| #19 Chronology | `trading.causal_available_factual_event_chronology.v2`; rule and manifest v2 |

**Order Block origins (H3).** For displacement index `i` and origin lookback `L`, search backward over exactly `max(0, i-L)..i-1`. An absent preceding opposite candle produces no block. Gaps between candles remain valid. The local block identity recipe is unchanged for valid inputs.

**Historical liquidity (H2).** Slice #6 exposes `historical_interactions` independently of current `liquidity_levels`. To classify candle `i`, it builds boundaries from pivots at indices `max(0, i-L)..i-1` whose confirmation indices are strictly less than `i`. Confirmation or establishment on candle `i` cannot classify that candle. Every interaction binds geometry, causal members, confirmation/completion evidence, effective lookback, rule and configuration fingerprint in a content-addressed `causal_boundary`. Later members can change the current cluster, but cannot rewrite or delete earlier interactions. Current ordinal level IDs remain local presentation identifiers. Current level interaction lists refer to their exact current boundary descriptor; historical equivalence uses the causal descriptor, never final ordinal equality.

Slice #6 reports over all supplied candles and introduces no interaction retention limit. Its evidence separates the full historical reporting domain from the current candidate scan count. Slice #9 maps that historical stream without redetection, preserves boundary evidence, and owns touch filtering and maximum-event retention. Its state keys and source references use causal boundary IDs, including untouched current boundaries. A boundary ID is deterministic evidence, not a durable cluster-version subsystem.

**Availability chronology (H1).** The v2 contract orders groups and `BEFORE` edges by `causal_availability_timestamp`, while retaining `event_timestamp` as the producer's original label. `causal_availability_basis` preserves required candle labels, completion instants and liquidity boundary references. Slice #13 owns candle completion: opening timestamp plus timeframe duration. FVG creation uses the third candle; interactions use the established object and interaction candle; displacement uses its qualifying candle with prior baseline; Order Blocks use displacement and preceding origin; ranges use both confirmed pivots; liquidity uses the event-local boundary and interaction candle. Availability must not exceed the source cutoff or requested evaluation time. Equal availability groups explicitly declare `ORDER_UNPROVEN`; serialization tie order establishes no factual precedence. Creation annotations are `snapshot_current_state`, separate from historical interaction state. No detector is invoked by chronology. Old label-time v1 `BEFORE` semantics are not silently reinterpreted.

**Coverage (H5).** Each family has a coverage state and `coverage_scope`: supplied source bounds, evaluation/cutoff, candidate/lookback domain, interaction domain, output filters, retention limits, effective configuration and rule/fingerprint. `FULLY_COVERED` applies only to that explicit configured domain. Filtered absence does not claim that no historical event occurred. Filtered FVG object counts remain object counts; their omitted event count stays unknown. Retention counts preserve the dd16ccd fix: Order Block omitted creations plus omitted interactions, without summing generic truncation diagnostics or affected-block counts. Source/lookback bounds, filters and retention remain separate. Unknown required coverage dominates aggregate coverage. Earliest/latest retained label and availability timestamps are separate fields and never stand in for evaluation bounds.

**Serialized consistency (H4).** Owners validate serialized inputs at the consuming boundaries. Slice #13 recomputes its original snapshot hash, validates approved OHLC and completion/cutoff, and checks metadata/count/evidence consistency separately. It does not replay approved-only history and lose `INCOMPLETE` evidence. Slice #14 validates sources through #13 and recomputes its own unchanged context identity and derived fields.

Slice #15 retains the existing full authoritative-result hash and configuration fingerprint algorithm. Its v3 envelope identity binds serialized content, including normalized effective configuration; ignored raw request keys do not affect identity. Every exposed validated terminal result is hash-checked, including a retained result after classification failure. Failed executions retain null success IDs and bounded partial-execution/dependency provenance. Dependency references without full payloads receive reference-level validation only.

Slice #16 delegates envelope validation to #15. Its v3 identity includes full validated references and each envelope's content fingerprint, binding degraded terminal configuration, retained result and progress even when the successful envelope ID is null. This fingerprint is a content reference, not a manufactured success identity. The evidence descriptor is `full_validated_references_v3`. Slices #18 and #19 invoke the #16 owner validator; #19 also checks every supplied envelope against its authoritative context reference. Unsupported legacy envelope/context rules are rejected; no persistent migration mechanism is introduced.

These hashes establish deterministic content consistency, not signatures or hostile-process authenticity. Historical retention remains bounded only by supplied approved history and existing producer filters/retention owners. Direct detectors still rely on the caller to supply appropriate history; causal composition obtains that history through Slice #13.

## Slice #20 causal market state synthesis

`CausalMarketStateSynthesisAnalyzer.analyze()` in `causal_market_state_synthesis.py` accepts exactly `factual_context`, `factual_envelopes`, `composition`, `chronology`, and `configuration`. Context/envelopes must use hardened rules v3; the envelope matrix contains all seven timeframes and ten capabilities. Chronology uses `trading.causal_available_factual_event_chronology.v2`. Configuration accepts only `schema_version`, normalized to `causal_market_state_synthesis_configuration_v1`; `{}` selects this version. Raw candles, detached detector results, independent evaluation boundaries and additional input keys are rejected.

The #18 and #19 owners expose `validate_factual_composition` and `validate_factual_chronology`. Each reconstructs its own descriptive result from validated upstream inputs and compares all serialized content, including diagnostics, metadata, coverage and identities. This runs composition/event normalization only, with no factual detector invocation. Composition identity uses canonical timeframe order, preserving canonical producer identities across dictionary serialization order. Existing chronology results without an optional composition reference remain valid; a supplied reference must match the fully validated composition. Synthesis always binds both results independently.

Output contract `trading.causal_market_state_synthesis.v1`, rule `causal_market_state_synthesis_v1`, contains a vector for D1, H4, H1, M30, M15, M5 and M1. Each timeframe retains its source snapshot, cutoff and factual context state. There is no dominant regime or aggregation score.

| Dimension | Preserved authoritative fields |
| --- | --- |
| Market Structure | `structure_state`, latest high/low relationships, continuation/reversal break candidate/confirmed flags |
| Volatility / Range | `volatility_state`, `range_state`, `volatility_trend`, `abnormal_range`, `gap_state` |
| Liquidity | `liquidity_levels` and #19 retained liquidity events |
| Imbalance / FVG | Independent `fair_value_gaps` objects and #19 FVG events |
| Displacement | `displacement_events`, `displacement_sequences` and #19 displacement events |
| Structural Dealing Range | Exact selected `current_range` |
| Premium / Discount | Exact producer `observation` |
| Order Blocks | Independent `order_blocks` objects and #19 block events |
| Adjacent Timeframe Availability | #18 relationships, stored once under the parent timeframe; M1 has no child |

Each claim exposes `source_field`, `support_state`, `value`, `temporal_scope` and `provenance`. Support precedence is `EVIDENCED`, then `ABSENT_IN_SCOPE`, then `UNKNOWN`. A semantically usable positive object survives broader filtered/truncated coverage. Retained payloads with failed classification do not become evidence; current owners provide no narrower semantic-authority exception. Unknown and scoped-absence claims carry a null value and retain coverage/degradation provenance. A producer boolean `false` remains an evidenced producer value when its result is usable.

Current-object absence uses owner-specific evaluation evidence and absence classifications. Filters or truncation that could hide qualifying evidence prevent absence. Unsupported negative claims remain unknown. #19 coverage is used only for historical event families in its manifest, never for current structure, volatility, selected range, premium/discount or current object absence. Adjacent relationships retain both endpoints and #18's exact relationship in provenance; unusable endpoints produce unknown support without inventing semantic agreement.

Snapshot-current observations describe the authoritative cutoff and do not imply historical creation state. Historical claims preserve #19 causal availability and its availability basis; equal-time groups retain `ORDER_UNPROVEN`. Historical synthesis requires a bundle produced for that boundary, never a filtered later chronology. Local object/event IDs are qualified by capability contract/rule, authoritative result, envelope content fingerprint, context, snapshot, timeframe, cutoff and locator. Claims also retain effective configuration, coverage and degradation. The synthesis identity binds normalized configuration and all material bound inputs under `snapshot_deterministic`; it is neither persistent entity identity nor a signature.

Slice #20 is callable library infrastructure. It adds no specialist registration, routes, detector adapters, runtime executor, policy or lifecycle authority. Mission Control remains final authority. Tests cover the fixed bundle, owner validation, degraded retained results, mixed objects, scoped absence, filtered/truncated positives, actual future FVG/liquidity/range changes and detector/execution isolation.
