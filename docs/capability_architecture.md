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

## Slice #21 causal factual condition evaluation

`CausalFactualConditionEvaluationAnalyzer.analyze()` accepts exactly `synthesis`, `upstream_bundle`, and `condition`. The first two are the complete Slice #20 result and its exact five-field input bundle. `validate_market_state_synthesis()` belongs to #20 and reconstructs and compares the entire serialized result, including metadata, support, provenance and identity, without factual detector execution. Valid degraded synthesis remains valid. The #21 evaluator receives only that validated synthesis and normalized condition; it never interprets the upstream bundle or diagnostic/provenance text.

The evaluator contract is `trading.causal_factual_condition_evaluation.v1`, rule `causal_factual_condition_evaluation_v1`. Every condition requires `contract: "trading.causal_factual_condition_definition.v1"`, a nonempty string `condition_id`, one canonical `timeframe`, and `predicate_type`. The remaining fields depend strictly on the family:

| Predicate type | Additional required fields |
| --- | --- |
| `SCALAR_COMPARISON` | `target`, `operator` (`EQ` or `NE`), `expected_value` of the target's exact type |
| `CLAIM_EXISTS` | `target` |
| `OBJECT_EXISTS` | `target`, `filters`: a list of `{field, operator, expected_value}`; operators are `EQ`/`NE`, values are strings |
| `ALL_OF` | `constituents`: 1–32 complete atomic condition definitions, with unique IDs and the same timeframe |

Unknown and family-forbidden keys, nesting, null expected values and incompatible types are rejected. Strings compare exactly, with no trimming or case folding. Boolean targets accept only booleans, never integers. Object filters are conjunctive, permit at most one occurrence of each allowed field, and require an explicit list (`[]` means unfiltered existence). Filter and constituent list order is preserved. Dictionary insertion order is non-semantic; no semantic defaulting is performed.

For example, this condition asks about an existing producer field, without assigning trading significance:

```json
{
  "contract": "trading.causal_factual_condition_definition.v1",
  "condition_id": "structure-observation",
  "timeframe": "H1",
  "predicate_type": "SCALAR_COMPARISON",
  "target": "structure_state",
  "operator": "EQ",
  "expected_value": "bullish_structure"
}
```

### Fixed v1 target surface

The owner-controlled accessor selects records in `synthesis.timeframes[T].dimensions[D]` with the exact `source_field` below and `temporal_scope == "snapshot_current"`. Target identifiers are fixed; callers cannot provide paths. Singular accessors require exactly one record before support filtering, including an absent/unknown placeholder. In this table, SC means scalar comparison (`EQ`/`NE`); CE means claim existence (no operator); OE means object existence with exact string filters (`EQ`/`NE`).

| Target | Dimension | Source field / fixed value projection | Type / cardinality | Families / filters |
| --- | --- | --- | --- | --- |
| `structure_state` | `market_structure` | `structure_state.value` | String, singular | SC, CE |
| `latest_high_relationship` | `market_structure` | `latest_high_relationship.value` | String, singular | SC, CE |
| `latest_low_relationship` | `market_structure` | `latest_low_relationship.value` | String, singular | SC, CE |
| `continuation_break_candidate` | `market_structure` | `continuation_break_candidate.value` | Boolean, singular | SC, CE |
| `continuation_break_confirmed` | `market_structure` | `continuation_break_confirmed.value` | Boolean, singular | SC, CE |
| `reversal_break_candidate` | `market_structure` | `reversal_break_candidate.value` | Boolean, singular | SC, CE |
| `reversal_break_confirmed` | `market_structure` | `reversal_break_confirmed.value` | Boolean, singular | SC, CE |
| `volatility_state` | `volatility_range` | `volatility_state.value` | String, singular | SC, CE |
| `range_state` | `volatility_range` | `range_state.value` | String, singular | SC, CE |
| `volatility_trend` | `volatility_range` | `volatility_trend.value` | String, singular | SC, CE |
| `abnormal_range` | `volatility_range` | `abnormal_range.value` | Boolean, singular | SC, CE |
| `gap_state` | `volatility_range` | `gap_state.value` | String, singular | SC, CE |
| `current_structural_range` | `structural_dealing_range_intelligence` | `current_range.value` | Object, singular | CE |
| `current_range_order` | `structural_dealing_range_intelligence` | `current_range.value.chronological_order` | String, singular parent | SC |
| `premium_discount_observation` | `premium_discount_intelligence` | `observation.value` | Object, singular | CE |
| `premium_discount_classification` | `premium_discount_intelligence` | `observation.value.classification` | String, singular parent | SC |
| `liquidity_levels` | `liquidity` | `liquidity_levels.value` | Objects, 0..N | OE: `side`, `level_type`, `current_status` |
| `fair_value_gaps` | `fvg_imbalance_intelligence` | `fair_value_gaps.value` | Objects, 0..N | OE: `side`, `current_status` |
| `displacement_events` | `displacement_intelligence` | `displacement_events.value` | Objects, 0..N | OE: `direction` |
| `displacement_sequences` | `displacement_intelligence` | `displacement_sequences.value` | Objects, 0..N | OE: `direction` |
| `order_blocks` | `order_block_intelligence` | `order_blocks.value` | Objects, 0..N | OE: `direction`, `current_state` |

Historical claims, adjacent-timeframe relationships, ordering groups, numeric geometry, timestamps, identifiers as filters, nested interactions, diagnostics, provenance operands and all unlisted fields are excluded. Producer displacement object records retain #20's snapshot-current reporting semantics; they do not imply an ongoing displacement regime.

### Truth, scope and authority

A usable scalar evaluates to `SATISFIED` or `NOT_SATISFIED`. Evidenced `false` is a known boolean. Undefined scalar operands yield `UNKNOWN` for both EQ and NE, including when the parent has `ABSENT_IN_SCOPE`. CE tests authoritative usable presence, not dictionary presence or truthiness. A wrong type inside an evidenced selected field fails closed.

OE is satisfied by any authoritative matching object, even under broader incomplete coverage. All matching references remain available in source order. Negative existence requires a matching explicit #20 `ABSENT_IN_SCOPE` placeholder for the exact declared domain; a nonempty but nonmatching collection remains unknown. No completeness is inferred from diagnostics. #20 currently permits such absence for FVGs, displacement events, Order Blocks and the selected current structural range, using their respective owner-specific evaluated/configured domains. Structure, volatility, premium/discount, current liquidity levels and displacement sequences have no additional negative inference. Empty sequences have no placeholder and remain unknown. Collection absence does not extend beyond its declared domain.

ALL_OF evaluates every constituent: any `NOT_SATISFIED` yields `NOT_SATISFIED`; otherwise any `UNKNOWN` yields `UNKNOWN`; otherwise the result is `SATISFIED`. Unknown constituents remain in output even when another is false. Duplicate singular records fail closed even when their values agree. Mixed object states remain distinct.

Results contain the normalized condition and condition identity, evaluator contract/rule, evaluation identity, supplied requested timestamp and timeframe cutoff, synthesis ID, outcome/reasons, evidence and constituent results. Evidence includes inherited support, selected observed values and synthesis-local locators (synthesis ID, timeframe, dimension, claim index, source field and existing source/object locator). Object predicates expose only allowlisted field values; object CE needs no copied geometry. Locators are not persistent entity IDs. Identities use existing snapshot-deterministic hashing; hashes are not authenticity guarantees.

Mismatched synthesis/upstream boundaries are rejected. A fully consistent later bundle remains a valid, explicitly identified later evaluation; no unstated intended historical time is inferred. There is no wall-clock input, detector recomputation or external mutable state dependency.

Slice #21 remains callable library infrastructure with no registration, routing, execution, lifecycle or Mission Control policy changes. Its outcomes describe factual predicate truth only. Faithfully attributed owner values such as `bullish_structure` are permitted; new trading conclusions, recommendations, opportunities, action parameters, scores and execution instructions are not produced. Mission Control remains final authority. The layer assigns no trading significance and implements no future decision or risk-authorization capability.

## Slice #22 causal trading policy prerequisite assessment

`CausalTradingPolicyPrerequisiteAssessmentAnalyzer.analyze()` in `causal_trading_policy_prerequisite_assessment.py` accepts exactly `policy_definition`, `condition_evaluation`, `synthesis`, `upstream_bundle`, and `condition`. The last three are the exact Slice #21 input bundle. The assessment contract is `trading.causal_trading_policy_prerequisite_assessment.v1`, with rule `causal_trading_policy_prerequisite_assessment_v1` and identity scope `snapshot_deterministic`.

Slice #21 now owns `validate_causal_factual_condition_evaluation(value, synthesis, upstream_bundle, condition)`. It reconstructs through existing #21 logic (and #20 owner validation), compares every serialized field, and returns detached validated content. Missing, extra or changed fields, including nested evidence, observed values, reasons and constituent identities, reject with `ValueError`. No factual detectors run. The owner helper `condition_identity()` uses the unchanged normalized-condition identity recipe, also used by #21 output generation.

### Policy definition and binding

Caller-supplied policy definitions contain exactly seven fields:

| Field | Constraint |
| --- | --- |
| `policy_definition_contract` | `trading.causal_trading_policy_prerequisite_definition.v1` |
| `policy_definition_rule_version` | `causal_trading_policy_prerequisite_definition_v1` |
| `policy_id` | Nonempty string preserved exactly |
| `policy_version` | Positive integer; booleans rejected |
| `instrument` | Uppercase identifier `[A-Z][A-Z0-9_]*`; no whitespace or alias normalization |
| `timeframe` | One canonical timeframe |
| `required_condition` | Complete condition normalized only by #21 |

The normalized owned snapshot adds `required_condition_identity`, derived by #21, and `complete_definition_fingerprint`, hashing every normalized definition field except the fingerprint itself. Caller-supplied derived fields and all unknown keys are rejected. Dictionary ordering is non-semantic; constituent ordering and condition strings remain unchanged. Definition normalization supplies no activation, approval, selection or profitability semantics.

The assessment validates the serialized #21 evaluation, compares its complete normalized condition against the policy requirement, and requires policy/required-condition/evaluation timeframe equality. Shortening an ALL_OF, changing a condition under the same identifier, substitution and timeframe mismatch reject. #22 never evaluates predicates or recomputes conjunction truth.

Instrument identity is read only from the exact #20 owner-validated synthesis. The evaluation must bind that synthesis ID, requested timestamp and selected timeframe cutoff. #22 reads no synthesis factual claims or upstream diagnostics. Existing factual support remains XAUUSD-only; a policy can declare a different instrument scope without creating support for that market. Only after all validation succeeds does an instrument mismatch yield non-applicability.

### Assessment semantics and result

| Instrument scope | Validated #21 root outcome | Applicability | Prerequisite assessment |
| --- | --- | --- | --- |
| Matches | `SATISFIED` | `APPLICABLE` | `PREREQUISITE_ESTABLISHED` |
| Matches | `NOT_SATISFIED` | `APPLICABLE` | `PREREQUISITE_NOT_ESTABLISHED` |
| Matches | `UNKNOWN` | `APPLICABLE` | `PREREQUISITE_UNKNOWN` |
| Differs | Any valid outcome | `NOT_APPLICABLE` | `null` |

Invalid inputs raise `ValueError`, never a semantic assessment. Instrument mismatch cannot hide prior validation failure. Unknown never becomes false. The complete validated #21 result is embedded unchanged, including unknown constituents beneath a false aggregate. Valid degraded null cutoffs remain null; missing or inconsistent serialized cutoff fields reject. Seven upstream timeframe cutoffs need not be equal. Historical and later coherent bundles retain their supplied boundaries, without freshness heuristics or historical policy-existence/approval claims.

The exact top-level result fields are `contract`, `rule_version`, `identity_scope`, `assessment_id`, `policy_definition`, `evaluated_instrument`, `condition_evaluation`, `applicability`, `prerequisite_assessment`, `reason_codes`, and `authority`. #21-owned identities, timestamps, evidence and reasons remain inside `condition_evaluation`, not duplicated at the top level. #22 reason codes are exactly `["POLICY_SCOPE_MATCH"]` or `["INSTRUMENT_SCOPE_MISMATCH"]`. Authority is exactly `{"trade_decision": false, "financial_risk": false, "execution": false}`. The assessment identity hashes the complete result excluding only `assessment_id`; there is no random or wall-clock input. Hashes establish consistency, not authenticity or policy approval.

Slice #22 establishes only whether the exact declared factual prerequisite of a supplied policy holds within its declared scope. It generates no directional action, candidate, opportunity, financial-risk conclusion or execution permission. Faithfully embedded upstream evidence is not a new trading conclusion. Legacy bias/scoring, generic Mission Control ALLOW/DENY semantics and execution-plan approval are not used. The capability remains callable library infrastructure with no routing, registration, lifecycle, account, broker or runtime changes. Mission Control remains final operational authority.

## Slice #23 causal trading policy action formulation

`CausalTradingPolicyActionFormulationAnalyzer.analyze()` in `causal_trading_policy_action_formulation.py` accepts exactly `action_policy_definition`, `prerequisite_assessment`, and `assessment_input`. The last field is the exact five-field #22 analyzer input (`policy_definition`, `condition_evaluation`, `synthesis`, `upstream_bundle`, `condition`), passed only to #22 owner validation. The formulation contract is `trading.causal_trading_policy_action_formulation.v1`, rule `causal_trading_policy_action_formulation_v1`, identity scope `snapshot_deterministic`.

The additive #22 helper `validate_causal_trading_policy_prerequisite_assessment(value, assessment_input)` reconstructs through the existing analyzer and compares complete sorted-key JSON with non-finite values rejected. Missing, extra, changed, type-substituted and nested content rejects with `ValueError`; list order is preserved and serialized booleans differ from numbers. It returns detached reconstructed content. Existing #22 schemas and semantics remain unchanged. Reconstruction delegates to upstream owners without factual detector execution and establishes consistency, not authenticity.

### Action-policy definition

Caller definitions contain exactly six fields:

| Field | Constraint |
| --- | --- |
| `action_policy_contract` | `trading.causal_trading_policy_action_definition.v1` |
| `action_policy_rule_version` | `causal_trading_policy_action_definition_v1` |
| `action_policy_id` | Nonempty exact string; no trimming or case normalization |
| `action_policy_version` | Positive integer; booleans rejected |
| `prerequisite_definition` | Exactly the seven caller-level #22 definition fields |
| `declared_action` | Exactly `action_type: "DIRECTIONAL_ENTRY_INTENT"` and `direction: "LONG"` or `"SHORT"` |

Unknown/missing keys, unsupported values and caller-supplied derived fields reject. No coercion or semantic defaults apply. #22 alone normalizes the nested prerequisite into its nine-field owned definition. The normalized action policy adds only `complete_action_policy_fingerprint`, using `_hash_id("action_policy_definition_", normalized_definition_without_fingerprint)`. No separate action identity or duplicate prerequisite fingerprint is introduced. Dictionary insertion order is non-semantic; existing list order remains significant. Caller input is not mutated.

Validation order is action-policy normalization, complete #22 owner validation, exact complete normalized prerequisite equality, then semantic branching. IDs and fingerprints alone never establish binding. Invalid inputs reject even if the assessment would otherwise be blocked.

### Formulation and authority

| Validated applicability | Validated prerequisite | Status | Formulated action | Singleton reason |
| --- | --- | --- | --- | --- |
| `APPLICABLE` | `PREREQUISITE_ESTABLISHED` | `FORMULATED` | Detached exact declaration | `ACTION_FORMULATED` |
| `APPLICABLE` | `PREREQUISITE_NOT_ESTABLISHED` | `NOT_FORMULATED` | `null` | `PREREQUISITE_NOT_ESTABLISHED` |
| `APPLICABLE` | `PREREQUISITE_UNKNOWN` | `NOT_FORMULATED` | `null` | `PREREQUISITE_UNKNOWN` |
| `NOT_APPLICABLE` | `null` | `NOT_FORMULATED` | `null` | `POLICY_NOT_APPLICABLE` |

Other combinations reject. The result has exactly `contract`, `rule_version`, `identity_scope`, `formulation_id`, `action_policy_definition`, `prerequisite_assessment`, `formulation_status`, `formulated_action`, `reason_codes`, and `authority`. Policy and assessment snapshots are complete and detached. Authority is exactly `{"trade_decision": false, "financial_risk": false, "execution": false}`. No proposal flag or lifecycle exists.

The declaration remains visible in blocked policy provenance; only status and `formulated_action` establish instantiation. `NOT_FORMULATED` is neither HOLD nor a trade rejection or opposite-direction recommendation. LONG/SHORT originate exclusively from the declaration and express intended directional exposure, without account/position assumptions or broker BUY/SELL translation. They establish no selection, recommendation, confidence, profitability, sizing, leverage, price, stop, target, order parameter or authorization.

`formulation_id` uses `_hash_id("policy_action_formulation_", complete_result_without_formulation_id)`. Action changes alter both action-policy and formulation identities even when blocked, while leaving the assessment unchanged. No wall clock or randomness enters identity. Instrument, timeframe, requested timestamp, cutoff and upstream identities remain transitively bound through the assessment without top-level copies. Legitimate null cutoffs remain null; upstream timeframe cutoffs need not match. Coherent historical/later bundles are accepted and inconsistent substitutions reject. Historical mapping proves no historical policy existence, activation, proposal, selection, approval or execution.

#23 remains callable library infrastructure. It reads no factual evidence to infer direction, duplicates no prerequisite truth logic, consumes no financial-account state and uses no legacy bias/alignment scoring. It adds no runtime registration, routing, execution plan, dispatcher invocation, broker integration or Mission Control changes. Mission Control remains final operational authority.

## Slice #24 causal financial account state snapshot

`CausalFinancialAccountStateSnapshotAnalyzer.analyze()` in `causal_financial_account_state_snapshot.py` owns the factual representation of one supplied account observation. This independent branch does not consume #23. The contract is `trading.causal_financial_account_state_snapshot.v1`, rule `causal_financial_account_state_snapshot_v1`, identity scope `snapshot_deterministic`.

### Exact caller schema

Every object requires exactly its declared string keys; missing/extra fields reject. No coercion or semantic defaults apply.

| Object | Exact fields / values |
| --- | --- |
| Input | `contract`, `rule_version`, `requested_evaluation_timestamp`, `observation` |
| Observation | `account`, `source`, `timing`, `account_measures`, `positions`, `pending_obligations` |
| Account | `account_id`, `environment` (`DEMO`/`LIVE`), `currency` (three uppercase ASCII letters), `position_mode` (`NETTING`/`HEDGING`/`UNKNOWN`) |
| Source | `source_id`, `source_contract`, `source_contract_version`, `source_snapshot_id` |
| Timing | `effective_at`, `observed_at`, `source_available_at` |
| Account measures | `completeness`, `balance`, `equity`, `used_margin`, `free_margin` |
| Positions | `completeness`, `items` (list) |
| Position item | `position_id`, `instrument_id`, `direction` (`LONG`/`SHORT`), `quantity`, `quantity_unit` |
| Pending obligations | `scope: "NOT_IN_SCOPE"` |

Contract/rule values must equal the constants above. Opaque account/source/position/instrument/unit identifiers are strings containing at least one non-whitespace character, preserved exactly. Account identity is scoped by source identity and environment. Currency syntax does not certify registry membership. Environment is a supplied fact, not proof of authentication.

### Decimal values and inventory

Monetary values and quantities must be strings matching `-?(0|[1-9][0-9]*)(\.[0-9]+)?`. Numbers, booleans, exponents, non-finite values, commas, leading plus signs, invalid leading zeros and whitespace reject. Normalization strips trailing fractional zeros and an unnecessary decimal point, mapping signed zero to `"0"`, without rounding or decimal-context dependence. All amounts are source-reported in account currency. Balance, equity and free margin may be negative; used margin must be nonnegative. No accounting equation is imposed and no financial amount is derived.

The four measure slots are structurally mandatory but allow null. Completeness is independently declared for measures and positions:

| Domain | COMPLETE | PARTIAL | UNAVAILABLE |
| --- | --- | --- | --- |
| Four account measures | All four non-null | One to three non-null | All four null |
| Positions | Valid exhaustive list, possibly empty | Valid known rows, possibly empty; omissions possible | Empty list; no inventory established |

Contradictory combinations reject. Partial coverage never permits malformed rows. Completeness is a source assertion structurally validated by this owner, not externally verified coverage. Missing facts never become zero or proof of absence.

Positions describe existing source-reported facts, not #23 entry intent. Quantities are strictly positive in explicit source units. IDs are unique, even for otherwise identical rows. NETTING permits at most one position per exact instrument ID; HEDGING permits multiple unique position IDs per instrument; UNKNOWN retains rows without inferring mechanics. Position items normalize into lexicographic order by exact position ID. No symbol normalization, unit conversion or exposure aggregation occurs. Entry price, open timestamp, per-position PnL, stops, targets and strategy metadata are deferred, as are margin level and account realized/unrealized PnL.

Pending orders and reserved commitments remain explicitly outside scope. Complete positions never establish complete financial commitments, complete exposure or available capacity.

### Causal availability

Timestamps require valid calendar dates, seconds, `Z` or an explicit `±HH:MM` offset, and at most six fractional digits. Timezone-free values and leap seconds reject. Normalize to UTC with exactly six fractional digits and `Z`.

`effective_at` is when the source says the state applies. `observed_at` is when this exact observation/revision first became available to the consuming system. `source_available_at` is source publication/availability time or null. Require `effective_at <= observed_at <= requested_evaluation_timestamp`; when source availability is supplied, also require `effective_at <= source_available_at <= observed_at`. No clock-skew repair or wall-clock comparison occurs. One timing set covers the complete coherent observation; no histories, source merging or revision selection are accepted.

A later revision with a later observed time cannot pass an earlier boundary. Historical replay supplies that exact revision and its original availability evidence. This stateless contract cannot authenticate backdated assertions or detect source ID reuse across invocations. Timing does not imply operational freshness; future policy owns freshness thresholds.

### Result, identity and validation

The output has exactly `contract`, `rule_version`, `identity_scope`, `snapshot_id`, `requested_evaluation_timestamp`, `observation`, `source_authentication`, `limitations`, and `authority`. Observation content is normalized and detached. No overall usability/status field is added.

`source_authentication` is exactly `NOT_VERIFIED_BY_THIS_CAPABILITY`. `limitations` is exactly the ordered list `["PENDING_OBLIGATIONS_NOT_IN_SCOPE", "FINANCIAL_EXPOSURE_NOT_CALCULATED", "FRESHNESS_NOT_EVALUATED"]`. `authority` is exactly `{"trade_decision": false, "financial_risk": false, "execution": false}`.

The ID uses `_hash_id("financial_account_state_snapshot_", complete_normalized_result_without_snapshot_id)`. Every semantic output field is bound. Dictionary insertion order and caller position order are non-semantic; equivalent decimal spellings and timezone representations yield the same identity. There is no random, wall-clock or mutable external input.

`validate_causal_financial_account_state_snapshot(value, snapshot_input)` reconstructs through this owner and compares the entire sorted-key serialized result, rejecting non-finite values. Missing, extra, changed or type-substituted nested content rejects with `ValueError`, including booleans substituted for numbers. Serialized output must already contain canonical decimals, UTC timestamps and position order. Validation returns detached reconstructed content; it does not authenticate source truth. Inputs, stored results, serialization returns and validator returns do not share mutable structures that let caller mutation rewrite a snapshot.

This callable library capability adds no routing, registry, broker integration or Mission Control changes. It performs no trade selection, risk-limit evaluation, financial-risk authorization, sizing, exposure/drawdown calculation, capacity reservation, order generation, reconciliation or account mutation. Future authenticated connectors may bind their own authentication evidence to the source identity without changing this owner's meaning.

## Slice #25 causal financial instrument contract metadata snapshot

`CausalFinancialInstrumentContractMetadataSnapshotAnalyzer.analyze()` in `causal_financial_instrument_contract_metadata_snapshot.py` represents exactly one supplied instrument specification/revision. This independent instrument-fact branch consumes neither #23 nor #24. Contract: `trading.causal_financial_instrument_contract_metadata_snapshot.v1`; rule: `causal_financial_instrument_contract_metadata_snapshot_v1`; identity scope: `snapshot_deterministic`.

### Exact caller schema and dimensional semantics

| Object | Exact fields |
| --- | --- |
| Input | `contract`, `rule_version`, `requested_evaluation_timestamp`, `specification` |
| Specification | `source`, `position_namespace`, `timing`, `economic_model`, `completeness`, `economics` |
| Source | `source_id`, `source_contract`, `source_contract_version`, `source_snapshot_id` |
| Position namespace | `source_id`, `source_contract`, `source_contract_version`, `environment`, `instrument_id`, `quantity_unit` |
| Timing | `effective_at`, `observed_at`, `source_available_at` |
| Economics | `reference_asset_id`, `reference_unit`, `reference_units_per_quantity_unit`, `price_currency` |

All schemas are exact, with no defaults or coercion. Contract/rule constants must match. Opaque identifiers require exact strings containing at least one non-whitespace character and are preserved, including surrounding whitespace. Environment is exactly DEMO or LIVE. Metadata-source provenance and the target account-position namespace are separate assertions; their providers and source schemas may differ. V1 assumes uniform specification scope within the full target namespace; indistinguishable account-specific variants are outside scope.

The sole interpreted model is `LINEAR_REFERENCE_NOTIONAL`: one declared quantity unit represents `reference_units_per_quantity_unit` reference units of `reference_asset_id`; a compatible price is denominated in `price_currency` per exactly one `reference_unit` of that asset. Reference asset and measurement unit are separate; no meaning is inferred from GOLD, XAUUSD, lot or contract labels. This describes dimensions only, not a valuation, monetary exposure, PnL or margin calculation.

Non-null reference asset/unit fields are opaque identifiers. Price currency is three uppercase ASCII letters without registry lookup. The multiplier is a strictly positive decimal string matching `-?(0|[1-9][0-9]*)(\.[0-9]+)?`. Integers, floats, booleans, exponents, non-finite values, whitespace, leading plus and invalid leading zeros reject. Trailing fractional zeros and an unnecessary decimal point are removed without rounding or ambient decimal-context dependence. Signed zero normalizes to `"0"`, then fails positivity. All four economics slots are structurally required and may be null under the coverage rules.

| Model | Derived support | Economics / completeness |
| --- | --- | --- |
| Exact `LINEAR_REFERENCE_NOTIONAL` | `SUPPORTED` | Four non-null: COMPLETE; one to three: PARTIAL; zero: UNAVAILABLE |
| Other nonempty opaque identifier | `UNSUPPORTED` | All economics null and completeness UNAVAILABLE |
| Null | `UNAVAILABLE` | All economics null and completeness UNAVAILABLE |

Unknown model identifiers are preserved without aliases or interpretation. Completeness concerns only the four supported economics slots, not every field in an arbitrary provider specification. Contradictory coverage or malformed non-null values reject even under PARTIAL. Unsupported models cannot carry arbitrary provider blobs or interpreted economics.

### Availability versus effective start

Timestamps follow #24-compatible grammar and canonical UTC representation: valid calendar datetime with seconds, explicit Z or ±HH:MM, at most six fractional digits, no leap seconds or timezone-free values; output uses six fractional digits and Z. `observed_at` is when the exact revision first became available to the consuming system. Require `observed_at <= requested_evaluation_timestamp`; non-null publication time must satisfy `source_available_at <= observed_at`.

Unlike #24 account observations, there is no ordering constraint between `effective_at` and publication/observation time. Announcements before their effective start are valid. `effective_start_status` is `EFFECTIVE_FROM_REACHED` when the start is at or before the evaluation boundary, otherwise `FUTURE_EFFECTIVE`. Reaching the start establishes neither governing/current revision nor freshness or absence of supersession. A later correction is unavailable at an earlier knowledge boundary even if its effective start is historical. Re-evaluating a known revision at a later boundary may change its status and snapshot ID. No history, revision selection or effective-end interval is represented.

### Output, identity and owner validation

Exactly eleven output fields: `contract`, `rule_version`, `identity_scope`, `snapshot_id`, `requested_evaluation_timestamp`, `specification`, `model_support`, `effective_start_status`, `source_authentication`, `limitations`, `authority`. Specification content is normalized and detached. Source authentication is exactly `NOT_VERIFIED_BY_THIS_CAPABILITY`. Limitations are exactly the ordered list `["REVISION_SELECTION_NOT_PERFORMED", "FRESHNESS_NOT_EVALUATED", "VALUATION_NOT_PERFORMED", "FINANCIAL_EXPOSURE_NOT_CALCULATED"]`. Authority is exactly `{"trade_decision": false, "financial_risk": false, "execution": false}`; no general usability flag is added.

Identity uses `_hash_id("financial_instrument_contract_metadata_snapshot_", complete_normalized_result_without_snapshot_id)`. Dictionary insertion order is non-semantic; equivalent accepted decimals/timestamps normalize identically. Opaque string changes remain significant. No clock, randomness, external registry or mutable external state enters identity.

`validate_causal_financial_instrument_contract_metadata_snapshot(value, snapshot_input)` reconstructs through the owner and compares the complete sorted-key serialized result with non-finite values rejected. Missing/extra/changed nested content, type substitutions, noncanonical decimal/timestamp output and altered support/status/limitations/authority reject with `ValueError`. Return detached reconstructed content. Caller mutation and mutation of serialization/validator returns cannot rewrite prior snapshots. Validation establishes supplied-evidence consistency, not source authenticity or governing applicability.

### Future #24 binding (not implemented)

A future consumer must owner-validate both artifacts and compare exactly:

| #24 | #25 |
| --- | --- |
| `observation.source.source_id` | `specification.position_namespace.source_id` |
| `observation.source.source_contract` | `specification.position_namespace.source_contract` |
| `observation.source.source_contract_version` | `specification.position_namespace.source_contract_version` |
| `observation.account.environment` | `specification.position_namespace.environment` |
| Selected position `instrument_id` | `specification.position_namespace.instrument_id` |
| Selected position `quantity_unit` | `specification.position_namespace.quantity_unit` |

Do not compare #24 source fields to #25 metadata provenance, or compare their source snapshot IDs. Account currency need not equal price currency; a difference exposes a later conversion requirement. Namespace equality alone does not authorize calculation. Consumers still need supported/complete economics as required, compatible knowledge boundaries, applicability to the measurement time, governing-revision selection, valuation evidence and any necessary conversion evidence.

Tick size/value, point value, quantity increments/minima, settlement/profit/margin currencies, rates, leverage, fees, financing, account-specific conditions and expiry are deferred. #25 performs no price selection, valuation, conversion, exposure, margin, risk, sizing, proposal/decision, capacity reservation, broker mutation or execution. No runtime, routing, registry or Mission Control changes are introduced.

## Slice #26 causal financial price observation snapshot

`CausalFinancialPriceObservationSnapshotAnalyzer.analyze()` in `causal_financial_price_observation_snapshot.py` owns exactly one supplied point-price observation/revision or explicit unavailable-price report. This is an independent factual library capability consuming neither #23, #24 nor #25. Contract: `trading.causal_financial_price_observation_snapshot.v1`; rule: `causal_financial_price_observation_snapshot_v1`; identity scope: `snapshot_deterministic`.

### Exact schemas and provenance

| Object | Exact fields |
| --- | --- |
| Input | `contract`, `rule_version`, `requested_evaluation_timestamp`, `observation` |
| Observation | `source`, `target_namespace`, `denomination`, `timing`, `price_type`, `availability`, `price` |
| Source | `source_id`, `source_contract`, `source_contract_version`, `source_snapshot_id` |
| Target namespace | `source_id`, `source_contract`, `source_contract_version`, `environment`, `instrument_id` |
| Denomination | `specification_source`, `reference_asset_id`, `reference_unit`, `price_currency` |
| Specification source | `source_id`, `source_contract`, `source_contract_version`, `source_snapshot_id` |
| Timing | `price_time`, `observed_at`, `source_available_at` |

Objects require exactly their declared fields and types, without defaults or coercion. Environment is DEMO or LIVE. Opaque identifiers are strings containing at least one non-whitespace character and are preserved exactly, including surrounding whitespace. Price currency is exactly three uppercase ASCII letters, without registry authentication.

`source` identifies the price supplier and exact supplied observation/revision. `target_namespace` identifies the account/instrument namespace; its provider may differ from the price supplier. `denomination.specification_source` is an opaque supplied reference to the specification revision whose dimensional vocabulary is asserted. It is not a consumed or validated #25 artifact. No external authentication, source lookup, symbol parsing or dimensional inference occurs.

Price means `price_currency` per exactly one `reference_unit` of `reference_asset_id` under that referenced vocabulary. No quantity unit, multiplier or conversion belongs in this observation.

### Price types, values and availability

The closed price-type vocabulary is BID, ASK, MID, MARK and LAST. These are source-declared types: bid, ask, midpoint-type, marking/reference and last-traded price respectively. No executable-size guarantee, midpoint calculation, marking-method verification or suitability determination is supplied. Unknown/null types, aliases and case variants reject.

AVAILABLE requires a decimal string matching `-?(0|[1-9][0-9]*)(\.[0-9]+)?`. Negative, zero and positive prices are accepted; acceptance does not establish economic suitability. Integers, floats, booleans, exponent notation, non-finite values, commas, leading plus, whitespace and invalid leading zeros reject. Normalization removes trailing fractional zeros and an unnecessary decimal point, and maps signed zero to `"0"`, without rounding or ambient decimal-context dependence.

UNAVAILABLE requires `price: null`. Zero remains a real available value. No PARTIAL state exists. All provenance, target, denomination, type and timing fields remain required for unavailable reports. Such a report establishes no claim that no quote or trade existed in the market.

### Point time and causal corrections

`price_time` is the market time represented by the observation, or the market time to which an unavailable report pertains. `observed_at` is when this exact observation/revision first became available to the consuming system. `source_available_at` is publication/availability time or null. Require `price_time <= observed_at <= requested_evaluation_timestamp`; when publication is supplied, also require `price_time <= source_available_at <= observed_at`.

Timestamps require valid calendar datetimes with seconds, explicit Z or ±HH:MM, at most six fractional digits, no leap seconds and no timezone-free values. Canonical output uses UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`. There is no future-effective price exception.

A correction retains its represented market time and supplies its own revision identity and causal availability times. A revision first available at 10:05 rejects at a 10:02 knowledge boundary even when its market time is earlier. This owner does not compare histories, select a governing correction or authenticate backdated assertions. One point observation establishes no validity interval, valid-until-superseded behavior, freshness or latest-observation status.

CANDLE_CLOSE and interval-derived types are excluded. No candle adapter or OHLC conversion exists, and copying a numeric close cannot relabel it as LAST or MARK. A future consumer may explicitly consume owner-validated completed candle-close evidence under an appropriate contract preserving interval/completion semantics.

### Output, identity and validation

Exactly nine output fields: `contract`, `rule_version`, `identity_scope`, `snapshot_id`, `requested_evaluation_timestamp`, `observation`, `source_authentication`, `limitations`, `authority`. Observation contains the complete normalized supplied content. Source authentication is exactly `NOT_VERIFIED_BY_THIS_CAPABILITY`. Limitations are exactly this ordered list: `["PRICE_SELECTION_NOT_PERFORMED", "FRESHNESS_NOT_EVALUATED", "PRICE_SUITABILITY_NOT_EVALUATED", "SPECIFICATION_COMPATIBILITY_NOT_VALIDATED", "VALUATION_NOT_PERFORMED", "FINANCIAL_EXPOSURE_NOT_CALCULATED"]`. Authority is exactly `{"trade_decision": false, "financial_risk": false, "execution": false}`. No support, usability, freshness or valuation status is added.

Identity uses `_hash_id("financial_price_observation_snapshot_", complete_normalized_result_without_snapshot_id)`. All normalized output content is bound. Equivalent accepted decimals/timestamps and dictionary insertion orders produce the same identity; opaque identifier and correction provenance/content changes remain significant. No clock, randomness or mutable external state enters identity.

`validate_causal_financial_price_observation_snapshot(value, snapshot_input)` reconstructs through the #26 owner from the complete exact input and compares the entire sorted-key JSON serialization with non-finite values rejected. Missing, extra, changed, type-substituted or noncanonical content at every depth rejects with `ValueError`, including identity, provenance, dimensions, timing, limitations and authority. Validation returns detached reconstructed content. Mutation of caller input, serialization results or validator returns cannot rewrite prior snapshots. Validation establishes consistency of supplied evidence, not authenticity.

### Future compatibility and measurement path (not implemented)

A future consumer must owner-validate both #26 and #25 artifacts and compare exactly:

| #26 | #25 |
| --- | --- |
| `observation.target_namespace` fields `source_id`, `source_contract`, `source_contract_version`, `environment`, `instrument_id` | Same five fields in `specification.position_namespace` |
| `observation.denomination.specification_source` (all four fields) | `specification.source` |
| `observation.denomination.reference_asset_id` | `specification.economics.reference_asset_id` |
| `observation.denomination.reference_unit` | `specification.economics.reference_unit` |
| `observation.denomination.price_currency` | `specification.economics.price_currency` |

Do not compare #26 `observation.source` to #25 `specification.source`: price and specification suppliers are separate concepts. Quantity units and reference-units-per-quantity-unit remain on the specification side. These comparisons establish consistency of assertions, not authenticity, governing applicability, freshness, price suitability or financial-use authorization. #26 performs none of these comparisons at runtime.

The future position measurement path is #24 position → #25 quantity/instrument semantics → #26 price denomination/evidence. No separate direct #24 binding owner is introduced. Direct target-namespace comparison may check consistency but cannot replace #25 quantity semantics. Account currency may differ from price currency, exposing a future conversion requirement.

Remaining blockers to financial measurement include governing/applicable specification selection, supported and sufficiently complete economics, compatible knowledge boundaries, price selection and suitability, and any required conversion evidence. No valuation or exposure capability is established by #26. Risk limits, financial-risk authorization, sizing, action quantity, pending commitments and capacity reservation remain separate future responsibilities as required by their eventual consumers.

#26 performs no governing revision or price selection, freshness assessment, price suitability determination, compatibility validation, valuation, reference notional, market value, exposure, currency conversion, PnL, margin, financial-risk evaluation/authorization, position sizing, trade selection/decision, capacity reservation, broker mutation, execution or Mission Control authorization. No registries, routing, existing public contracts or execution systems change.

## Slice #27 causal instrument specification lifecycle evidence snapshot

`CausalInstrumentSpecificationLifecycleEvidenceSnapshotAnalyzer.analyze()` in `causal_instrument_specification_lifecycle_evidence_snapshot.py` owns one source-relative, namespace-scoped collection of immutable lifecycle assertions and its declared coverage. Contract: `trading.causal_instrument_specification_lifecycle_evidence_snapshot.v1`; rule: `causal_instrument_specification_lifecycle_evidence_snapshot_v1`; identity scope: `snapshot_deterministic`. It represents factual propositions and validates structure and causal availability; it does not resolve applicability or select a governing revision.

### Exact caller schemas and provenance

| Object | Exact fields |
| --- | --- |
| Input | `contract`, `rule_version`, `requested_evaluation_timestamp`, `evidence` |
| Evidence | `source`, `target_namespace`, `timing`, `coverage`, `assertions` |
| Source / specification revision reference | `source_id`, `source_contract`, `source_contract_version`, `source_snapshot_id` |
| Target namespace | `source_id`, `source_contract`, `source_contract_version`, `environment`, `instrument_id`, `quantity_unit` |
| Assertion | `assertion_id`, `timing`, `statement` |
| Timing (report, assertion, coverage) | `observed_at`, `source_available_at` |
| Economic scope | `effective_from`, `effective_until` |
| Coverage | `declaration_id`, `timing`, `completeness`, `assertion_kinds`, `economic_domain`, `source_information_cutoff`, `starting_basis`, `omissions` |
| Omissions | `assertions_omitted`, `history_truncated` |

Schemas reject missing/extra fields, incompatible types, coercion and defaults. Identifiers are exact strings containing at least one non-whitespace character; surrounding whitespace and case are preserved. Environment is DEMO or LIVE. Arrays are lists; omission booleans cannot be numbers. Malformed or structurally contradictory input raises `ValueError`.

The evidence source identifies the reporting source/schema and exact report revision. It need not equal the target namespace source. The six-field namespace includes quantity unit because the specification governs quantity-unit economics. Revision references identify #25 `specification.source`, including its source revision ID, not the derived #25 top-level snapshot ID. No economics are embedded or validated. Assertion IDs and coverage declaration IDs are scoped to the reporting-source schema and full namespace; they imply neither precedence nor authentication. This stateless owner cannot detect identity reuse across invocations. Coverage from an independently identified reporter is outside v1.

### Immutable statement vocabulary

| Kind | Exact statement fields | Supplied proposition |
| --- | --- | --- |
| APPLIES | `kind`, `revision`, `economic_scope` | The revision applies to the target namespace over the stated scope. |
| SUPERSEDES | `kind`, `predecessor_revision`, `successor_revision`, `economic_scope` | The distinct successor replaces the predecessor for applicability within the stated scope. |
| WITHDRAWS | `kind`, `revision`, `economic_scope` | The revision is withdrawn from applicability within the stated scope. |
| CORRECTS | `kind`, `target_assertion_id`, `replacement_statement` | The identified assertion's whole proposition is erroneous and is replaced, or retracted without replacement. |

SUPERSEDES asserts the successor applies in place of the named predecessor within scope; it establishes no precedence over unrelated revisions, complete history or absence of revision C. WITHDRAWS targets a revision and never automatically reinstates a predecessor. Neither changes #25 artifacts.

A correction targets another assertion in the same collection, possibly an earlier correction. Its replacement is a complete APPLIES, SUPERSEDES or WITHDRAWS statement, or null for whole-proposition retraction. Embedded CORRECTS and field patches are forbidden. Embedded replacement content is identified through the correction and inherits its availability. Direct correction of #25 economics is outside scope. Correcting a correction preserves an explicit challenge; this owner does not determine which propositions become operative.

### Economic scope and causal availability

Primitive propositions have half-open intervals `[effective_from, effective_until)`. Start is required; a non-null end must be strictly later. Null explicitly asserts no scheduled economic end, not permanent validity or valid-until-superseded semantics. Point-only and zero-length intervals are unsupported. Future-effective assertions and retroactive corrections are valid; economic time has no ordering requirement against publication or observation. Corrections have no additional interval: replacement content supplies its own scope, while null retracts the whole target proposition.

Every timing object requires observation at or before the requested knowledge boundary; non-null source publication must be at or before observation. Assertion and coverage observations must be at or before report observation. Correction targets must be observed no later than their corrections; when both publication times exist, target publication must also be no later. Equality is allowed. No separate event timestamp is introduced.

Timestamps use #24–#26 grammar: valid calendar timestamps with seconds, explicit Z or ±HH:MM, at most six fractional digits, no leap seconds, canonical UTC with six fractional digits and trailing Z. No causal filtering occurs: any unavailable assertion, correction, coverage declaration or report rejects the entire input. A later correction or completeness claim cannot be used at an earlier knowledge boundary. Later snapshots do not rewrite historical snapshots.

### Coverage universe and starting basis

`assertion_kinds` is exactly the ordered list `["APPLIES", "SUPERSEDES", "WITHDRAWS", "CORRECTS"]`; `economic_domain` is exactly `ALL_ECONOMIC_TIMES`. Coverage inherits the report source/schema and full target namespace. It never claims cross-source completeness.

| Completeness | Cutoff | Starting basis | Omission flags |
| --- | --- | --- | --- |
| COMPLETE | Required timestamp | FROM_INCEPTION | Both false |
| LIMITED | Required timestamp | FROM_INCEPTION | Both booleans, at least one true |
| UNKNOWN | Null | UNKNOWN | Both null |

COMPLETE is the source's declaration that every lifecycle assertion in the four families, for this full namespace, from the inception of its assertion history through the source-information cutoff inclusive, is included across all economic times. This includes original, corrected, withdrawn, conflicting and future-effective propositions published by that cutoff. Completeness is not independently verified and does not imply consistency or unique applicability.

`assertions_omitted` declares known exclusions such as filtering or selective reporting; `history_truncated` declares loss of earlier history through retention or availability. No omission count is inferred. LIMITED acknowledges incompleteness of the defined universe. UNKNOWN makes no usable cutoff/history claim; known omissions belong in LIMITED. Complete history cannot be inferred from record counts, empty arrays or retained timestamp bounds.

Known coverage requires publication times for every assertion and the coverage declaration: assertion publication <= cutoff <= coverage publication <= coverage observation. UNKNOWN permits null publication times, but validates all supplied times normally. A coverage cutoff before the requested knowledge boundary cannot establish absence of intervening updates.

An empty COMPLETE collection is valid and means only that the source declares no assertions in the defined universe through the cutoff. It does not establish no specification exists/applies, no other source has evidence, or trading prohibition. V1 supports only from-inception known coverage; economically filtered domains, explicit starting-state snapshots and compressed/current-applicable anchors are excluded.

### Structural rejection versus preserved conflicts

Duplicate assertion IDs reject even if identical; no deduplication occurs. Missing correction targets, self-corrections and correction-reference cycles reject. LIMITED collections must still be closed under correction references. Identical supersession endpoints, invalid intervals, malformed references and contradictory coverage declarations reject.

Overlapping APPLIES for distinct revisions, overlapping APPLIES/WITHDRAWS, competing corrections and revision-level supersession cycles remain evidence. They are substantive conflicts for a later resolver. Only correction-reference cycles are structural errors. COMPLETE coverage may contain all such substantive conflicts.

### Output, identity and owner validation

Exactly nine output fields: `contract`, `rule_version`, `identity_scope`, `snapshot_id`, `requested_evaluation_timestamp`, `evidence`, `source_authentication`, `limitations`, `authority`. Evidence is complete normalized content; no selected revision, resolved applicability or conflict-resolution result appears. Authentication is exactly `NOT_VERIFIED_BY_THIS_CAPABILITY`. Limitations are exactly `["GOVERNING_SELECTION_NOT_PERFORMED", "APPLICABILITY_RESOLUTION_NOT_PERFORMED", "CROSS_SOURCE_PRECEDENCE_NOT_EVALUATED", "COVERAGE_CLAIMS_NOT_INDEPENDENTLY_VERIFIED", "SPECIFICATION_REFERENCES_NOT_VALIDATED", "FINANCIAL_MEASUREMENT_NOT_PERFORMED"]`. Authority is exactly `{"trade_decision": false, "financial_risk": false, "execution": false}`.

Assertions sort by exact assertion ID string for serialization only, never chronology or precedence. Dictionary insertion order is non-semantic. Equivalent timestamps and reordered input assertion lists normalize identically; opaque identifier differences remain significant. Identity is `_hash_id("instrument_specification_lifecycle_evidence_snapshot_", complete_normalized_result_without_snapshot_id)`, binding all facts, coverage, references, economic and knowledge times, limitations and authority without clocks, randomness or external state.

`validate_causal_instrument_specification_lifecycle_evidence_snapshot(value, snapshot_input)` reconstructs through the owner from exact caller input, compares full sorted-key JSON with non-finite values rejected, and returns detached reconstructed content. Missing/extra/changed/type-substituted/noncanonical content rejects with `ValueError`. Caller inputs, exposed payload copies, serialization results and validator returns cannot mutate prior snapshots. Hashing establishes consistency, not authentication.

### Future resolver and downstream chain

#27 has no runtime dependency on #23/#24/#25/#26. A future resolver must owner-validate #27 and consumed #25 artifacts against their exact inputs; compare the full #27 namespace with #25 `specification.position_namespace`; and compare revision references with all four fields of #25 `specification.source`. It must reject inconsistent binding, including different economics supplied under one revision reference when jointly consumed. Matching strings alone neither validates an artifact nor authenticates evidence. Referenced metadata must be causally available within the intended knowledge boundary.

The resolver must define measurement versus knowledge time, adequate coverage, relationship interpretation, competing corrections, substantive conflicts, accepted source scope, and unresolved/absent/uniquely established applicability. It must not infer precedence from timestamps or sorting, authority from labels, completeness from records, or applicability from #25 effective-start status alone.

The downstream chain is #25 + #27 → future applicability resolver → #24 + applicable #25 → reference quantity. #27 makes the necessary evidence representable; incomplete/conflicting collections need not resolve. Reference notional using #26 still requires owner-validated AVAILABLE price evidence; exact namespace/specification/denomination compatibility; price-purpose suitability and selection; temporal alignment/freshness rules; and financial arithmetic/output semantics. Account-currency amounts may additionally require conversion evidence.

No governing selection, applicability resolution, cross-source precedence, authentication, reference quantity calculation, price consumption, valuation, exposure, FX, financial-risk evaluation, sizing, trade authorization or execution occurs here. Existing contracts, registries, routing and Mission Control remain unchanged.

## Slice #28 causal instrument specification applicability resolver

`CausalInstrumentSpecificationApplicabilityResolverAnalyzer.analyze()` in `causal_instrument_specification_applicability_resolver.py` consumes exactly one owner-validated #27 snapshot and exactly the required collection of owner-validated #25 revisions. It answers whether this reporter's supplied lifecycle history, complete through knowledge boundary K, uniquely establishes a supplied revision as applicable at economic timestamp T. It has no global governing or operational authority.

Contract: `trading.causal_instrument_specification_applicability_resolver.v1`; rule: `causal_instrument_specification_applicability_resolver_v1`; identity scope: `snapshot_deterministic`. The callable singleton is `CAUSAL_INSTRUMENT_SPECIFICATION_APPLICABILITY_RESOLVER`. No registration, routing, package export, runtime or Mission Control changes are introduced.

### Exact caller input and owner reconstruction

| Object | Exact fields |
| --- | --- |
| Input | `contract`, `rule_version`, `requested_knowledge_boundary`, `economic_timestamp`, `lifecycle_evidence`, `specification_revisions` |
| Lifecycle evidence | `snapshot`, `snapshot_input` |
| Each specification revision entry | `snapshot`, `snapshot_input` |

`specification_revisions` is a list, possibly empty. Each snapshot is an owner result object or serialized artifact accepted by its owner validator. Each `snapshot_input` is the complete exact original owner reconstruction input. The resolver invokes the #27 validator and every supplied #25 validator and uses their detached reconstructed returns; object wrappers, matching labels and hashes alone never establish validation. Resolver objects require exact fields/types, with no defaults, aliases or coercion. Constants must match.

T and K use the #25/#27 timestamp grammar: valid calendar timestamp with seconds, explicit Z or ±HH:MM, at most six fractional digits, no leap seconds or timezone-free values. Output is canonical UTC with six fractional digits and trailing Z. Opaque strings retain whitespace and case.

### Required revision collection and binding

Before corrections or economic filtering, extract every distinct four-field revision reference from every APPLIES, WITHDRAWS and SUPERSEDES statement, including both supersession endpoints and all non-null correction replacements. Require exactly one #25 artifact per reference. Missing, extra/unreferenced and duplicate representations reject with `ValueError`. Duplicates reject even when identical, or when only their owner evaluation boundaries differ. Incompatible economics, timing, namespace or model facts under one jointly consumed reference cannot be selected between. Corrected-away and economically inactive references remain required. An empty reference universe requires an empty metadata list.

For each artifact, compare the full #27 `evidence.target_namespace` with #25 `specification.position_namespace`: `source_id`, `source_contract`, `source_contract_version`, `environment`, `instrument_id`, `quantity_unit`. Compare lifecycle revision references with all four #25 `specification.source` fields: `source_id`, `source_contract`, `source_contract_version`, `source_snapshot_id`. The reporting source is independent of the metadata supplier. A source revision ID is not the derived #25 snapshot ID.

Canonical metadata order is lexicographic on the exact tuple `(source_id, source_contract, source_contract_version, source_snapshot_id)`. Ordering determines serialization only. The collection covers the references in this evidence, not every specification revision that exists globally.

### Temporal and through-K coverage semantics

T is economic time; K is the consuming-system knowledge boundary; E is #27's owner evaluation boundary; C is the coverage source-information cutoff. Each #25 artifact also retains its own evaluation boundary. Owner boundaries may precede, equal or follow K, but artifacts must validate against their unchanged original reconstruction inputs, then pass explicit availability checks against K.

Require report, coverage, every assertion and every consumed specification `observed_at <= K`, and every non-null `source_available_at <= K`. Owner constraints additionally require publication at or before observation and their existing report/correction relationships. Owner-valid-at-E does not establish availability at K when E > K. Unavailable evidence rejects the entire input; no filtering or artifact rewriting occurs. T has no ordering constraint against K: future economic scopes are supplied assertions, not guaranteed future reality.

| Coverage | Through-K behavior |
| --- | --- |
| COMPLETE, C = K | Eligible for resolution |
| COMPLETE, C < K | UNRESOLVED: `COVERAGE_CUTOFF_BEFORE_KNOWLEDGE_BOUNDARY` |
| LIMITED | UNRESOLVED: `COVERAGE_LIMITED` |
| UNKNOWN | UNRESOLVED: `COVERAGE_UNKNOWN` |
| C > K | Invalid causal input; reject |

The theoretical condition C >= K reduces to C = K because known coverage requires `C <= coverage.source_available_at <= coverage.observed_at <= K`. Successful through-K coverage consequently has publication, coverage observation and report observation equal to K. This strict boundary is intentional; no lag tolerance or freshness window is inferred. Earlier #27 evaluation boundaries cannot establish COMPLETE coverage through a later K.

COMPLETE remains source-declared and unauthenticated. Empty COMPLETE at C = K establishes only no applicable candidate in the declared evidence universe. It does not establish that no specification exists/applies globally, that trading is prohibited, or that another source lacks information.

### Conservative correction calculus

Analyze the entire assertion collection before filtering by T. Map assertion IDs to assertions and target IDs to incoming corrections. Any correction targeting an original CORRECTS assertion yields `CORRECTION_OF_CORRECTION`. Any target with more than one incoming correction yields `MULTIPLE_CORRECTIONS_FOR_ASSERTION`. Emit both when applicable, in that order, and stop interpretation. These rules apply even to identical/null replacements and apparently irrelevant economic scopes. There is no branch pruning, latest-wins, lexical/list precedence or automatic reinstatement.

Otherwise retain primitives without corrections. A primitive with one correction is wholly displaced: substitute its complete non-null primitive replacement, or nothing for null. Replacement availability is the correction's availability; all timing has already passed validation. Replacement scope alone determines activity. A replacement outside T still displaces the original whole proposition. Correction-reference cycles, self-corrections and missing targets remain #27 structural failures.

### Lifecycle resolution algorithm and outcomes

Stages are fixed: validate all inputs/bindings/availability; coverage gate; correction gate; economic activity; substantive conflicts; candidate count. A failed semantic gate emits only its stage's applicable reasons; later stages are not evaluated. Validation failures always remain `ValueError`, even when evidence would otherwise be unresolved.

A primitive is active exactly when `effective_from <= T` and its end is null or `T < effective_until`. Construct sets P (APPLIES revisions plus SUPERSEDES successors), D (SUPERSEDES predecessors), W (WITHDRAWS revisions), and directed graph G of active predecessor → successor edges. Repeated evidence contributes the same set member/edge without creating an additional candidate.

Before displacement, detect all of: a directed cycle in G; nonempty P intersect W; any revision in P whose validated #25 `specification.timing.effective_at > T`. Emit all applicable reasons in canonical order and return UNRESOLVED. Cycle detection is iterative. Contradictions cannot be hidden by subsequent displacement.

The effective-start comparison uses T directly, never #25 `effective_start_status`, which is relative to that owner's boundary. A lifecycle-positive claim before the factual start is substantive conflicting evidence: unresolved, not invalid binding, clipped scope or ordinary absence. This also applies to a positive revision later displaced by another edge. A predecessor-only or withdrawal-only reference is not positive evidence.

With no conflicts, candidates are P minus D:

| Outcome | Necessary and sufficient conditions after successful validation |
| --- | --- |
| `UNIQUE_APPLICABLE_REVISION` | COMPLETE C = K, supported correction calculus, no substantive conflict, exactly one candidate |
| `NO_APPLICABLE_REVISION_ESTABLISHED` | Same gates, zero candidates |
| `UNRESOLVED` | Insufficient coverage, unsupported correction structure, substantive conflict, or multiple candidates |

APPLIES(A) plus A → B selects B. A → B → C selects C absent other conflicts. A → B and A → C leave two candidates; adding B → C explicitly displaces B and leaves C. Unrelated positive revisions remain candidates. Withdrawals add no positive evidence and never reinstate predecessors; withdrawal of a positive successor is a conflict. Bounded relationships have no effect outside their half-open scopes. Null ends assert no scheduled end, not permanence.

NO_APPLICABLE_REVISION_ESTABLISHED means only that complete, interpretable source-relative evidence through K establishes no candidate at T. Only UNIQUE carries selected references. Unsupported economic models or partial/unavailable economics alone do not prevent selection: applicability is not measurement readiness.

### Exact reason vocabulary and stage emission

The closed canonical order is:

1. `COVERAGE_LIMITED`
2. `COVERAGE_UNKNOWN`
3. `COVERAGE_CUTOFF_BEFORE_KNOWLEDGE_BOUNDARY`
4. `CORRECTION_OF_CORRECTION`
5. `MULTIPLE_CORRECTIONS_FOR_ASSERTION`
6. `ACTIVE_SUPERSESSION_CYCLE`
7. `POSITIVE_APPLICABILITY_WITHDRAWAL_CONFLICT`
8. `SPECIFICATION_EFFECTIVE_START_CONFLICT`
9. `MULTIPLE_APPLICABLE_CANDIDATES`
10. `UNIQUE_APPLICABLE_REVISION_ESTABLISHED`
11. `NO_APPLICABLE_CANDIDATE_ESTABLISHED`

Reasons are a nonempty list without duplicates. Coverage failure emits exactly one coverage reason. Correction failure emits all applicable correction reasons. Substantive failure emits all applicable substantive reasons. Otherwise emit exactly the candidate-count reason corresponding to multiple, one or zero candidates. Reasons describe the stopping stage, not an exhaustive diagnosis. No free-text reasoning enters output or identity.

### Exact output, identity and validation

Exactly eighteen top-level fields, in serialization order: `contract`, `rule_version`, `identity_scope`, `resolution_id`, `requested_knowledge_boundary`, `economic_timestamp`, `target_namespace`, `reporting_source`, `coverage`, `lifecycle_evidence_reference`, `specification_revision_references`, `outcome`, `selected_revision`, `selected_specification_snapshot_reference`, `reason_codes`, `source_authentication`, `limitations`, `authority`.

| Object | Exact fields |
| --- | --- |
| Coverage | `completeness`, `source_information_cutoff` |
| Owner artifact reference | `contract`, `rule_version`, `snapshot_id`, `content_fingerprint` |
| Each canonical specification revision reference | `revision`, `snapshot_reference` |

Target namespace is the six-field #27 namespace; reporting source is its four-field evidence source. Coverage preserves the validated completeness and cutoff (null for UNKNOWN). The lifecycle reference identifies the one #27 artifact. Each metadata entry contains its four-field source revision and an owner artifact reference. `selected_revision` and `selected_specification_snapshot_reference` are both null unless UNIQUE; when unique they exactly match one consumed entry. No economics, full owner artifacts, candidate arrays or free-text explanations are embedded.

Each owner reference fingerprints its entire reconstructed serialized result, including its snapshot ID, using `_hash_id("validated_owner_content_", validated_owner_result)`. These are content-consistency references, not authentication and not substitutes for owner validation.

Identity is `_hash_id("instrument_specification_applicability_resolution_", complete_normalized_output_without_resolution_id)`, using existing canonical JSON and truncated SHA-256 conventions. It binds every consumed owner's full content through fingerprints, including nonselected/corrected-away metadata, all boundaries and coverage, outcome/reasons/selection, namespace/source, limitations and authority. Equivalent accepted collection permutations, map ordering and normalized timestamps/decimals produce identical output/identity. Opaque strings and owner evaluation boundary changes remain significant. No clocks, randomness or external state enter the result.

`validate_causal_instrument_specification_applicability_resolver(value, resolver_input)` reconstructs through this owner from the exact caller input and compares the entire output using sorted-key JSON with `allow_nan=False`. Missing/extra/changed/type-substituted/noncanonical/nonfinite content rejects. Supplied output is not normalized into acceptance. The validator returns detached reconstructed content. Caller inputs, exposed payload copies, serialization results and validator returns cannot mutate previous results; payload access follows #27's defensive-copy pattern.

### Limitations, authority and downstream boundary

`source_authentication` is exactly `NOT_VERIFIED_BY_THIS_CAPABILITY`. Ordered limitations are exactly:

`["COVERAGE_CLAIMS_NOT_INDEPENDENTLY_VERIFIED", "GLOBAL_GOVERNING_SELECTION_NOT_PERFORMED", "CROSS_SOURCE_PRECEDENCE_NOT_EVALUATED", "FINANCIAL_MEASUREMENT_NOT_PERFORMED", "VALUATION_NOT_PERFORMED", "PRICE_SELECTION_NOT_PERFORMED", "PRICE_SUITABILITY_NOT_EVALUATED", "FRESHNESS_NOT_EVALUATED", "FINANCIAL_EXPOSURE_NOT_CALCULATED", "POSITION_SIZING_NOT_PERFORMED"]`.

Authority is exactly `{"trade_decision": false, "financial_risk": false, "execution": false}`. Source authentication and authorization exclusions use those established fields rather than redundant limitation strings.

A UNIQUE result may unlock a later #24 position + selected owner-valid #25 revision → reference quantity capability. A downstream consumer must validate #28 and bind the consumed #25 artifact to the selected reference, then separately establish economics support/completeness, dimensional compatibility and arithmetic semantics. #28 consumes neither #24 nor #26 and performs no financial calculation, price selection/suitability/freshness assessment, valuation, exposure, sizing, risk authorization, trade decision or execution. Reference notional remains dependent on future suitable #26 selection, temporal alignment, exact dimensions and arithmetic/conversion rules.

## Slice #29 causal account rule regime assessment

`CausalAccountRuleRegimeAssessmentAnalyzer.analyze()` in
`causal_account_rule_regime_assessment.py` assesses one exact account at economic
T using evidence available by K. It consumes one replacement manifest and explicit
approval provenance. It selects no market direction, constructs no candidate,
calculates no financial measurement and issues no authorization. The singleton is
`CAUSAL_ACCOUNT_RULE_REGIME_ASSESSMENT`; the owner validator is
`validate_causal_account_rule_regime_assessment(value, assessment_input)`.

Contract: `trading.causal_account_rule_regime_assessment.v1`; rule version:
`causal_account_rule_regime_assessment_v1`; identity scope:
`snapshot_deterministic`.

### Exact input and common records

All objects require exactly their declared fields, without aliases, coercion,
extra metadata or implicit defaults. All collections below are lists. Identifiers
are opaque, case-sensitive strings containing at least one non-whitespace
character; they are not stripped or inferred from display names. Timestamps follow
#24–#28's explicit-offset grammar and normalize to six-fractional-digit UTC `Z`.
Financial values are plain decimal strings, normalized without floating point or
arithmetic rounding. NaN, infinity and exponent notation are rejected.

| Record | Exact fields |
| --- | --- |
| Input | `contract`, `rule_version`, `requested_knowledge_boundary`, `economic_timestamp`, `account`, `manifest`, `approvals` |
| Account | `source_id`, `source_contract`, `source_contract_version`, `account_id`, `environment` |
| Artifact reference | `source_id`, `source_contract`, `source_contract_version`, `source_snapshot_id` |
| Package key | `package_id`, `package_revision` |
| Period | `effective_from`, `effective_until`, `end_status` |
| Timing | `observed_at`, `source_available_at` |
| Clause reference | `evidence_id`, `clause_locator` |
| Manifest | `source`, `timing`, `coverage`, `evidence`, `assignments`, `packages` |
| Manifest coverage | `completeness`, `economic_period`, `source_information_cutoff`, `limitations` |

Account environment is `DEMO` or `LIVE`. A simulated funded account may use
`DEMO`; provider/program/type/phase are separately evidenced. Manifest source is
an artifact reference. A period is half-open. `end_status=KNOWN` requires a known
end; `OPEN_ENDED` and `UNKNOWN` require a null end. A null start means unknown.
Known start must precede known end. Open-ended is an explicit validity assertion,
not an inference from missing source information. Manifest and calendar coverage
periods must have known finite endpoints.

Manifest completeness is `COMPLETE`, `LIMITED` or `UNKNOWN`. A non-null cutoff
cannot exceed report observation; only UNKNOWN permits a null cutoff. COMPLETE
requires an empty limitations list. Limitations are unique sorted opaque strings.
This inventory covers account assignments, package bindings, changes and approval
history over its economic period. It does not establish completeness of rules
within a package.

### Evidence, assignment, interpretation and approval

| Record | Exact fields |
| --- | --- |
| Evidence | `evidence_id`, `source`, `acquisition`, `document_reference`, `document_revision`, `document_date`, `document_sha256`, `timing`, `captured_by`, `limitations` |
| Assignment | `assignment_id`, `account`, `provider_id`, `program_id`, `account_type_id`, `phase_id`, `agreement`, `enrollment_period`, `phase_period`, `package_bindings`, `evidence_refs` |
| Agreement | `status`, `agreement_id` |
| Package binding | `package`, `effective_period`, `evidence_refs` |
| Package | `package_id`, `package_revision`, `provider_id`, `program_id`, `account_type_id`, `phase_id`, `effective_period`, `evidence_refs`, `interpretation`, `coverage`, `rules` |
| Interpretation | `interpretation_id`, `interpretation_version`, `interpreted_at`, `interpreter_ref`, `limitations` |
| Rule coverage | `completeness`, `scope`, `evidence_refs`, `limitations` |
| Approval | `approval_reference`, `authority_role`, `policy_id`, `policy_version`, `context_fingerprint`, `assignment_id`, `assignment_content_fingerprint`, `package`, `package_content_fingerprint`, `decision`, `decided_at`, `observed_at`, `effective_period` |

Evidence acquisition is `SOURCE_OBSERVED` or `MANUAL_TRANSCRIPTION`. Document
reference and capture process/actor are opaque required references; evaluation
never fetches a URL. Document revision, calendar date and lowercase 64-hex SHA256
may be null. A document date is not automatically its publication timestamp.
Unknown source publication remains null; observation by K can still establish
availability. Structural validation authenticates neither the source nor the
transcription.

Every assignment binds the exact requested account. Its four provider/program/
type/phase identifiers may be null, making a potentially active assignment
unresolved. Packages require all four identifiers. A known assignment identifier
must exactly match its bound package. Agreement status is `IDENTIFIED`,
`NOT_APPLICABLE` or `UNKNOWN`; only IDENTIFIED has a non-null ID. Nonapplicability
is an evidenced assertion, not a missing-value default. Clause lists are nonempty
and reference supplied evidence. All supplied evidence and packages must be used;
dangling references and unrelated extras reject.

Packages are immutable interpretations with one exact phase. Changing content,
provenance, coverage or effectiveness requires a new opaque revision; revision
ordering conveys no precedence. Rule-specific effectiveness is represented by a
replacement package, not a second lifecycle mechanism.

Approval roles are `mission_control` or `governance`, preserving existing role
vocabulary without introducing a human identity directory. Policy version is a
positive integer. Decisions are `APPROVED` or `REJECTED`. Approval binds the exact
normalized assignment and package fingerprints; a generic APPROVED state is
insufficient. Approval cannot fabricate enrollment or phase. Authority and context
fingerprints are preserved claims, not independently authenticated policy results.
An approval cannot predate the package interpretation. Explicit retrospective
approval is interpretation approval as known at K, not historical trade authority.

### Typed rule inventory

Every rule has exactly `rule_id`, `representation`, `effects`, `instrument_scope`,
`evidence_refs`, `body`. Rule IDs are unique within a package. Representation is
`SUPPORTED` or `UNSUPPORTED`. Effects are a nonempty subset, in canonical order,
of `ENTRY`, `HOLDING`, `EXIT`, `ACCOUNT_ELIGIBILITY`, `PHASE_TRANSITION`, `PAYOUT`,
`UNKNOWN`; UNKNOWN must stand alone.

Instrument scope is `{kind: ALL_ACCOUNT_INSTRUMENTS}` or
`{kind: EXACT_INSTRUMENTS, instruments: [...]}`. An exact list is nonempty; each
instrument has `source_id`, `source_contract`, `source_contract_version`,
`environment`, `instrument_id`. Quantity limits require exactly one instrument.

Supported bodies are strict tagged unions:

| Type | Other exact body fields | Semantics |
| --- | --- | --- |
| `ACCOUNT_STATE_REQUIREMENT` | `required_facts` | Nonempty subset of ACCOUNT_ACTIVE, PHASE_OPEN_FOR_TRADING, NO_PRIOR_DISQUALIFYING_BREACH |
| `INSTRUMENT_ACTION_PERMISSION` | `actions`, `permission` | Actions ENTRY_LONG, ENTRY_SHORT, HOLD, EXIT; PERMITTED or PROHIBITED |
| `POSITION_LIMIT` / PER_POSITION_QUANTITY | `limit_kind`, `quantity_unit`, `maximum` | Positive decimal maximum for one position in one exact instrument |
| `POSITION_LIMIT` / CONCURRENT_POSITION_COUNT | `limit_kind`, `maximum` | Nonnegative integer open-position count in scope |
| `STATIC_FLOOR` | `measure`, `threshold`, `compliant_when` | Absolute floor or retained fraction of an initial reference |
| `DAILY_RESET_FLOOR` | `measure`, `reset_anchor`, `deduction`, `compliant_when`, `reset_schedule`, `adjustment_policy` | Reset-anchor amount minus specified deduction |
| `ACTION_WINDOW` | `actions`, `mode`, `source_timezone`, `schedule_period`, `intervals`, `evidence_refs` | Explicit finite UTC action schedule |
| `AUTOMATION_PERMISSION` | `operation_mode`, `permission` | MANUAL/AUTOMATED and PERMITTED/PROHIBITED only |

All bodies also contain `type`. Permissions never override other applicable
constraints or grant execution authority. The position-count model does not
silently include orders, netting equivalence or other accounts. Automation
permission does not classify prohibited strategy behavior.

Floor measure has exactly `kind`, `currency`, `definition_refs`, `cost_treatment`.
Kind is BALANCE/EQUITY; currency is three uppercase ASCII letters. Cost treatment
has exactly `commissions`, `financing`, `other_charges`, each IN_MEASURE,
SUBTRACT_SEPARATELY or NOT_APPLICABLE. These assert source-defined accounting
semantics; a later assessor must establish compatible measures and avoid double
subtraction. Unknown/conditional semantics require an unsupported rule.

Threshold/deduction is `{kind: ABSOLUTE, amount}` or
`{kind: INITIAL_REFERENCE_FRACTION, reference, fraction}`. Reference is
INITIAL_BALANCE/INITIAL_EQUITY; fraction is in [0,1]. Absolute static amounts may
be signed; deductions must be nonnegative. Static fraction is the retained floor
fraction, whereas daily fraction is the amount deducted from the reset anchor.
Comparator is GREATER_THAN or GREATER_THAN_OR_EQUAL. Reset anchor is BALANCE or
EQUITY. Adjustment policy is exactly
NO_UNREPRESENTED_CAPITAL_OR_PHASE_ADJUSTMENTS. No threshold, loss, headroom or
margin is calculated here.

Reset schedule has exactly `source_timezone`, `source_local_reset_time`,
`schedule_period`, `boundaries`, `evidence_refs`. Local time is HH:MM:SS. Boundaries
are unique explicit UTC instants sorted chronologically and include the schedule's
finite endpoints. Adjacent boundaries define reset periods. Source calendar and
DST translation are approved interpretation claims, not runtime calculations.

Action-window actions are ENTRY_LONG, ENTRY_SHORT or HOLD. Mode is
PERMITTED_ONLY_WITHIN or PROHIBITED_WITHIN. Intervals are finite half-open Period
objects, sorted, nonoverlapping and contained in schedule_period. Empty lists
respectively permit nothing or declare no prohibition within coverage. Outside
coverage, downstream evaluability is not established. No timezone database,
recurrence engine, holiday lookup or schedule extrapolation is used.

An unsupported body has exactly `type: UNSUPPORTED`, `source_rule_label`,
`unsupported_reason`, `description`. Reason is SEMANTICS_NOT_SUPPORTED,
SEMANTICS_AMBIGUOUS, REQUIRED_TIMING_UNKNOWN or REQUIRED_PARAMETERS_UNKNOWN.
Scope, effects and clauses remain visible. There is no material=false or ignore
escape hatch. Trailing drawdown, arbitrary strategy/consistency formulas and
cross-account rules are preserved this way when outside supported semantics.

### Coverage, causal selection and replacement lifecycle

Package coverage scope is ACCOUNT_TRADING_AND_ELIGIBILITY. COMPLETE declares all
rules capable of affecting entry, holding, exit or continued account eligibility
have been inventoried for the exact package scope, including unsupported rules.
It requires an empty coverage-limitations list. LIMITED declares omissions or
unresolved inventory; UNKNOWN establishes no completeness claim. Complete scoped
absence can support only an inventory-relative absence statement. Incomplete
absence cannot. Neither complete coverage nor approval proves provider agreement.

All consumed evidence must be observed by K; known publication cannot follow
observation. Evidence must be available by report observation and package source
clauses by interpretation time. Interpretation must be available by report time.
Approval decision must be no later than its observation, which must be by K.
Unavailable evidence rejects the whole input, including economically inactive
records; no filtering or later-artifact rewriting is permitted.

T and K have no ordering restriction. Selection requires complete manifest
coverage containing T with cutoff equal to K. Earlier cutoff, incomplete coverage
or potentially active unknown identity/effectiveness returns UNRESOLVED. Known
inactive periods do not create ambiguity. Active enrollment and phase identify
one assignment; package bindings and package effectiveness then identify one
package. Competing packages are checked before approval, including unapproved
competitors. No revision ordering or lexical tie-breaker is used.

No eligible assignment/package/approval yields
NO_APPLICABLE_APPROVED_REGIME_ESTABLISHED. Conflicting active APPROVED/REJECTED
claims yield UNRESOLVED. Exact active approval yields
UNIQUE_APPLICABLE_APPROVED_REGIME. Multiple consistent approval records support
one regime. Applicability remains separate from package coverage and
interpretation support: ALL_DECLARED_RULES_SUPPORTED, UNSUPPORTED_RULES_PRESENT,
or NOT_ASSESSED when nothing is selected.

One replacement manifest expresses explicit predecessor closure and successor
start, phase changes and approval validity. Corrections require new source
manifest revisions and changed package content requires new package revisions.
Earlier-K assessments use artifacts available at that K; later corrections cannot
rewrite historical knowledge. Unresolved overlapping correction claims remain
conflicting assignments/bindings. There is no generic lifecycle graph or
multi-source precedence mechanism.

Reason codes use this exact order, emitting only findings whose prerequisites
have been assessed:

```text
MANIFEST_COVERAGE_LIMITED
MANIFEST_COVERAGE_UNKNOWN
MANIFEST_CUTOFF_BEFORE_K
T_OUTSIDE_MANIFEST_COVERAGE
ACCOUNT_ASSIGNMENT_NOT_ESTABLISHED
ACCOUNT_ASSIGNMENT_IDENTITY_UNKNOWN
APPLICABILITY_TIMING_UNKNOWN
MULTIPLE_ACCOUNT_ASSIGNMENTS
MULTIPLE_APPLICABLE_PACKAGES
NO_APPLICABLE_PACKAGE
APPROVAL_NOT_ESTABLISHED
APPROVAL_NOT_EFFECTIVE_AT_T
APPROVAL_REJECTED
APPROVAL_CONFLICT
UNIQUE_APPLICABLE_APPROVED_REGIME_ESTABLISHED
RULE_COVERAGE_LIMITED
RULE_COVERAGE_UNKNOWN
UNSUPPORTED_RULES_PRESENT
```

Malformed schemas, invalid times/decimals, duplicate identities, unavailable
information, dangling/extra references, known scope mismatch and approval-content
mismatch raise ValueError. Coherent competing evidence, missing approval,
expired approval, unknown phase and incomplete inventories are deterministic
non-affirmative results. A unique package with limited rule coverage or unsupported
rules stays uniquely applicable and exposes the separate downstream blockers.

### Output, fingerprints and reconstruction

Exact output fields: `contract`, `rule_version`, `identity_scope`, `assessment_id`,
`requested_knowledge_boundary`, `economic_timestamp`, `account`,
`manifest_reference`, `manifest_content_fingerprint`, `manifest_coverage`,
`outcome`, `selected_regime`, `interpretation_support`, `reason_codes`,
`source_authentication`, `limitations`, `authority`.

Selected regime is null unless uniquely established and approved. Otherwise it
has exactly `regime_id`, `assignment`, `assignment_content_fingerprint`, `package`,
`package_content_fingerprint`, `approval_references`, `applicable_period`,
`evidence`. Assignment and package are complete normalized records. Evidence is
exactly their referenced source inventory. Approval references carry complete
supporting approval records, including connected approved validity intervals.
Applicable period intersects enrollment, phase, binding, package and the connected
union of supporting approval periods containing T. Calendar horizons remain
explicit in rules and are not extended by this period. Point selection at T does
not establish candidate-lifetime compliance or future approval consistency.

Fingerprint prefixes are `account_rule_assignment_`, `account_rule_package_`,
`account_rule_manifest_`; regime prefix is `account_rule_regime_`, binding account,
assignment and package. Assessment prefix is `account_rule_regime_assessment_`.
Hashes use existing `_hash_id` canonical content conventions. Package and
assignment fingerprints contain normalized content without derived fingerprints;
approvals reference these without cycles. Assessment identity hashes the complete
normalized output excluding itself. Hash equality is not authentication.

Evidence, assignments, packages and rules sort by their respective exact identity;
approvals sort by the four-field reference tuple. Bindings sort by package key
and canonical period. Clauses sort by evidence ID and locator. Enumerated sets use
fixed enum order; opaque string sets sort lexically. Duplicates reject. Dates,
decimal spellings and set-like list ordering normalize before hashing.

The owner reconstructs from original input and compares the complete canonical
output with allow_nan=False. Altered identifiers, provenance, rules, authority or
limitations cannot be excused by matching selected fields. Validator returns,
result payload access and serialization are detached copies. Analysis has no
clock, randomness, external fetching, mutation or runtime registration.

Source authentication is NOT_VERIFIED_BY_THIS_CAPABILITY. Authority is exactly
`{trade_decision: false, financial_risk: false, execution: false}`. Fixed ordered
limitations are:

```text
SOURCE_CLAIMS_NOT_INDEPENDENTLY_AUTHENTICATED
OPERATIONAL_APPROVAL_CLAIMS_NOT_INDEPENDENTLY_AUTHENTICATED
PROVIDER_AGREEMENT_WITH_INTERPRETATION_NOT_ESTABLISHED
COVERAGE_CLAIMS_NOT_INDEPENDENTLY_VERIFIED
RULE_COMPLETENESS_RELATIVE_TO_DECLARED_SCOPE
CROSS_SOURCE_PRECEDENCE_NOT_EVALUATED
SOURCE_CALENDAR_TRANSLATION_NOT_INDEPENDENTLY_VERIFIED
CANDIDATE_COMPLIANCE_NOT_EVALUATED
FINANCIAL_RISK_NOT_EVALUATED
ACCOUNT_STATE_AND_HEADROOM_NOT_EVALUATED
TRADE_AUTHORIZATION_NOT_PERFORMED
EXECUTION_NOT_PERFORMED
```

### Downstream obligations and deliberate exclusions

A combined assessor must owner-validate, bind the exact account and candidate,
require unique approved applicability and complete scoped rule coverage, evaluate
all supported constraints and reject unresolved candidate-relevant unsupported
rules. Irrelevance requires candidate-lifetime evidence, not a caller flag. It
must establish source-compatible measures, prior-breach status, initial and reset
anchors, commitments, payoff, prices and costs as needed, then combine provider
constraints with strategy policy. It cannot equate a #24 measure label with the
provider's measure definition. Point applicability does not authorize crossing a
phase, rule, approval or calendar boundary. New K requires sufficiently current
input; an old result cannot be relabeled.

Mission Control remains responsible for current trust, approval, revocation,
expiry, atomic commitments and bounded authorization. This slice neither issues
those artifacts nor changes #23–#28 or governance contracts. Every result belongs
to one exact account; accounts sharing capital or provider are not interchangeable.
Cross-account constraints remain visible rather than assuming independence.

## Strategy #1 — XAUUSD Causal Liquidity Reversal v0.2, Revision 2.1

The additive `xauusd_causal_liquidity_reversal` module owns the strategy's
prerequisite assessment and reconstruction. Its contract is
`trading.xauusd_causal_liquidity_reversal.assessment.v0.2`; its definition contract
is `trading.xauusd_causal_liquidity_reversal.definition.v0.2`. The supported ID is
`xauusd_causal_liquidity_reversal`, version `0.2`, rule `revision_2.1`, instrument
`XAUUSD`, with an explicit `LONG` or `SHORT` direction.

`XAUUSD_CAUSAL_LIQUIDITY_REVERSAL.analyze(input).to_dict()` accepts exactly:

- `strategy_definition`: contract, strategy ID/version, rule version, instrument,
  direction and configuration.
- `as_of`: one timezone-aware boundary. The result's evaluation and knowledge
  boundaries both equal this boundary.
- `sources`: H4, H1, M15, M5 and M1 snapshots serialized by #13, each evaluated at
  the same `as_of`. The assessor validates these through the #13 source owner.
- `setup_ordinal`: zero-based selection among successive, causally founded
  distinct tuples in the declared domain. Zero selects the first setup. Births
  are independent: a distinct tuple can become provable while an earlier setup
  remains active. Required prior history is replayed, never discarded. The
  ordinal is a request selector, not economic identity.

Configuration explicitly supplies `history_starts` for all five timeframes,
`founding_start`, `founding_end`, `windows_seconds` for E1/R1/K1/RT1/T1, and
`order_block`, `liquidity`, `displacement`, `fvg` configuration dictionaries.
Factual configuration defaults are normalized by their existing owners. Nested
order-block displacement lookback remains controlled by #10. Domain boundaries
and durations have no trading defaults: the caller chooses these research
parameters. The history starts define a fixed bounded source domain, including
pivot and displacement context; founding start/end delimit admissible births.
They must remain unchanged when evaluating the same setup later. A different
domain is a different effective definition, not a continuation of the old one.

Each source must cover every expected completed interval from its declared start
through the boundary being replayed. Exact interval adjacency is required;
missing intervals fail closed without calendar inference. Extra leading candles
outside the declared domain are ignored after source validation. Losing required
leading or internal history produces UNKNOWN. Later missing intervals do not
rewrite an already established terminal outcome. Malformed OHLC, contradictory
snapshots, overlapping intervals and unsupported definitions raise `ValueError`.
Valid but unavailable snapshots produce UNKNOWN.

The replay invokes the existing #3, #6, #7, #8, #10 and liquidity-event owners on
completed prefixes. It does not add a detector, generic strategy language,
persistent registry, strategy-aware #22 or execution component. Producer rule
versions are recorded in the assessment and founding identity. Owner validation
establishes content consistency, not external data authenticity.

Founding requires exact aligned H4 structure; latest causally confirmed H1 CA1;
latest eligible direction-compatible native **unvisited** H1 P1; and exactly one
eligible M15 single-swing L1 inside P1's inclusive full range. Native P1 visitation
uses the producer's body-based rules; strategy geometry uses its full range.
CA1 availability is confirmation-candle completion. H1 directional agreement is
not required. L1 prior touches are allowed; prior sweeps/closes are not. A cluster
cannot replace a single level, and lost single-object continuity is UNKNOWN.
Canonical SB1 is the first covered boundary where all birth predicates hold,
including availability exactly equal to SB1.

CA1/P1/L1 bindings are immutable. The first exact L1 sweep establishes E1; a
close beyond L1 before it invalidates. B1 is the latest opposite-type M5 pivot
whose confirmation completion strictly precedes E1's occurrence start. Proven
absence invalidates at E1 completion. R1 is the first directional M5 displacement
starting no earlier than E1 completion. K1 is the first directional completed M5
close beyond B1, allowing joint R1/K1. Required M5 evidence is contiguous.

Q1 uses the exact A–R1–C FVG formation, with R1 as its middle candle and C as the
immediate successor. No qualifying Q1 at C completion invalidates; unfinished C
waits and missing C is UNKNOWN. Q1 eligibility is the later of formation and K1
availability. Pre-eligibility touch/partial fill cannot be RT1; pre-eligibility
full fill invalidates. RT1 is the first subsequent M5 range overlap with Q1,
excluding creation and pre-eligibility candles. Producer fill labels do not
replace geometric overlap. T1 is the first directional M1 displacement starting
no earlier than RT1's M5 completion.

Completed closes through CA1, P1 or Q1 and opposite H4 structure invalidate before
completion. Unresolved H4 context is UNKNOWN. Wick-only penetration does not
establish close invalidation. Materially competing completion/invalidation, or
RT1/invalidation without provable order, is UNKNOWN. No intrabar ordering is
invented from finer data.

Stage deadlines use configured elapsed seconds from SB1, E1 completion, R1
completion, Q1 eligibility and RT1 completion respectively. Endpoints are
inclusive. Missing observations never move deadlines; required missing evidence
is UNKNOWN. An unfinished candle at the deadline cannot qualify later. Adequate
negative coverage at a deadline produces EXPIRED. Before a deadline, proven
prerequisites with the next event absent produce WAITING. COMPLETE records the
first canonical completion and survives subsequent adverse evidence.

The replay remembers exhausted founding tuples locally while reconstructing the
requested setup. INVALIDATED, EXPIRED and COMPLETE exhaust the exact
strategy/version/config/instrument/direction/CA1/P1/L1 tuple. A later setup needs a
distinct CA1, P1 or L1 and complete birth proof. No runtime state is persisted.
Setup identity is available at birth, completion identity binds that setup to its
first T1, and assessment identity binds the complete evaluation-specific result.
Descriptors include immutable source candles, confirmation boundaries, geometry,
membership and rule/configuration provenance; producer indices, ordinal event
IDs, recency counters and current lifecycle states are excluded from economic
identity. `validate_strategy_assessment(assessment, assessment_input)` rebuilds
the complete expected result and compares its full canonical content.

### Additive StrategyAssessment consumption in #23

`causal_trading_policy_strategy_action_formulation` exposes
`STRATEGY_ACTION_FORMULATION.analyze(input).to_dict()`, under
`trading.causal_trading_policy_action_formulation.strategy.v1`. Existing #21,
#22 and #23 v1 modules and contracts are unchanged.

The input contains `action_policy_definition`, `strategy_assessment` and exact
`assessment_input` reconstruction material. The policy definition uses contract
`trading.causal_trading_policy_action_definition.strategy.v1`, a nonempty
`policy_id`, positive integer `policy_version`, the complete `strategy_definition`,
its `configuration_fingerprint`, and `declared_action` containing
`action_type: DIRECTIONAL_ENTRY_INTENT` and the same direction as the strategy.

This path delegates full reconstruction to the strategy owner, then checks exact
definition/configuration/fingerprint/direction agreement. Only owner-valid
COMPLETE assessments produce FORMULATED; all other lifecycle states produce
NOT_FORMULATED with no action. The formulation carries the assessment's setup,
completion and evaluation/knowledge bindings. It declares the policy's intent
without evaluating strategy semantics itself. Every assessment and formulation
retains false trade-decision, financial-risk and execution authority, and an
explicit false execution flag. There is no account, sizing, risk or order logic.

Real producer integration and adversarial contract tests are in
`tests/test_xauusd_causal_liquidity_reversal.py`.

## XAUUSD technical trade candidate v1

`xauusd_technical_trade_candidate.py` implements one strategy-specific owner for
unsized, account-independent technical candidate formulation and current validity
reconstruction. It does not modify Strategy #1 or the strategy-aware #23 contract.
It supplies technical references only: no financial approval, authorization,
executable fill, quantity, order or execution semantics.

The singleton is `XAUUSD_TECHNICAL_TRADE_CANDIDATE`. Its `analyze()` method accepts
exactly `candidate_policy_definition`, `strategy_assessment`, `action_formulation`
and `action_formulation_input`. The last field is the original #23 reconstruction
input, including original strategy reconstruction material. The #23 analyzer
delegates strategy reconstruction to its existing owner. This owner compares the
complete reconstructed #23 artifact and requires its embedded assessment to equal
the supplied COMPLETE assessment. It does not implement strategy detection again.

The policy has exactly `contract`, `policy_id`, `policy_version`, `configuration`.
Its contract is `trading.xauusd_technical_trade_candidate.policy.v1`; ID is a
nonempty string, version a positive integer, and configuration contains exactly
`entry_validity_duration_seconds`, an explicit positive integer elapsed duration.
There is no default trading duration, price buffer or tick-size normalization.

Formulation contract: `trading.xauusd_technical_trade_candidate.formulation.v1`.
Candidate contract: `trading.xauusd_technical_trade_candidate.v1`.
Validity contract: `trading.xauusd_technical_trade_candidate.validity.v1`.
All use rule version `xauusd_technical_trade_candidate_v1`.

The formulation result contains `contract`, `rule_version`,
`candidate_policy_definition`, `upstream_formulation`, `m1_origin_source`,
`formulation_status`, `candidate`, `reason`, `authority`, and `execution`.
The original #23 artifact (including its StrategyAssessment) and original #13 M1
snapshot are frozen provenance. A candidate contains their content fingerprints,
the policy fingerprint, original assessment/formulation identities, reconstructed
strategy ID/version, instrument/direction and setup/completion identities.
`entry_reference` and `stop_reference` each contain `kind`, `value`, and the exact
bound event `evidence`. Entry is `TECHNICAL_ENTRY_REFERENCE`: T1's completed close.
Stop is `TECHNICAL_STOP_REFERENCE`: E1's low for LONG or high for SHORT. These
numeric values are preserved from the owner-valid evidence without financial
denomination conversion or executable-order interpretation.

LONG requires entry strictly above stop; SHORT requires entry strictly below stop.
Failure returns `NOT_FORMULATED`, null candidate and
`ENTRY_STOP_GEOMETRY_NOT_ADMISSIBLE`. It does not create an INVALIDATED candidate
or change historical COMPLETE. Successful formulation returns `FORMULATED` and
`CANDIDATE_FORMULATED`. Non-COMPLETE upstream input or inconsistent, forged or
malformed artifacts reject with `ValueError`.

The candidate also carries `entry_validity_duration_seconds`, `valid_from`
(T1 availability), derived `valid_until`, authority/execution fields and
`candidate_identity`. Identity hashes the complete candidate without its own ID,
including full-content policy/upstream/origin fingerprints. Exposed aliases are
reconstructed, never separately editable inputs. Current evaluation time and
status are excluded from this immutable identity.

`evaluate_validity()` accepts exactly `candidate_formulation`, `formulation_input`,
`evaluation_boundary`, and `m1_source`. It reconstructs the frozen formulation
from its original inputs. K cannot predate the original upstream knowledge
boundary or T1 availability. The current #13 source must be XAUUSD M1 at K.
Its snapshot ID may differ from the original: legitimate extension changes IDs.
All supplied completed candles must follow the original one-minute grid, and
timestamp/OHLC content must agree wherever current and original histories overlap.
The current source must retain the exact T1 anchor; missing anchor is UNKNOWN,
conflicting content rejects. The frozen original reconstruction material supplies
the strategy context; the continuation need not repeat unrelated earlier candles.

Required post-T1 intervals start at `valid_from` and complete no later than
`min(K, valid_until)`. They must be exactly adjacent. A missing required completed
interval is UNKNOWN; an unfinished interval is excluded. No calendar assumptions
or gap bridging occur. LONG low strictly below stop, or SHORT high strictly above
stop, establishes a breach at that M1 completion. Equality does not breach.
The first breach wins, including completion exactly at expiry. A candle completing
after expiry cannot backdate its extreme even if it opened before expiry.

Without a breach and with sufficient evidence, status is VALID for K at or before
`valid_until`; it is EXPIRED only for K strictly after that threshold. EXPIRED
reports `terminal_boundary = valid_until`; this is the expiry threshold, not a
claim that EXPIRED applied at the inclusive endpoint. INVALIDATED reports the
first breach completion. VALID and UNKNOWN have null terminal boundaries. Gaps
after a proven terminal event do not erase it; later breaches cannot replace
EXPIRED. Consistent missing evidence can resolve UNKNOWN in a new evaluation.
There is no independent post-T1 Q1 predicate or post-T1 M5 input requirement.

Validity output contains exactly `contract`, `rule_version`, `candidate_identity`,
`evaluation_boundary`, the complete supplied validated `m1_source`, `status`,
`reason`, `terminal_boundary`, `authority`, and `execution`. No separate evaluation
identifier or persistent state is introduced. The validators
`validate_technical_candidate_formulation(value, formulation_input)` and
`validate_technical_candidate_validity(value, validity_input)` reconstruct and
compare complete canonical content, including evidence and types. Outputs and
validator returns are detached copies. Source consistency is not feed
authentication; this stateless owner cannot detect an unsupplied earlier revision
or independently authenticate when a source correction was learned.

Every result retains false trade-decision, financial-risk and execution authority,
plus `execution: false`. Technical VALID is not financial or account admissibility.
No account/provider/environment, quantity, risk percentage, margin, funded-account
result, TP or trade management is added. Later account-bound consumers must bind
the immutable candidate and current owner-valid validity result independently.

## Payoff-bearing instrument metadata v2

`causal_financial_instrument_contract_metadata_snapshot_v2.py` owns contract
`trading.causal_financial_instrument_contract_metadata_snapshot.v2`, rule
`causal_financial_instrument_contract_metadata_snapshot_v2`. The v1 owner and
public contract remain unchanged. V2 is one complete source revision, not a v1
artifact relabeled or accompanied by a separately selected payoff attachment.

The exact input retains `contract`, `rule_version`,
`requested_evaluation_timestamp`, and `specification`. Specification retains all
v1 fields and adds exactly `payoff`: `model`, `payoff_units_per_quantity_unit`,
`pnl_currency`, `uniformity`. Model, coefficient and P&L currency may be null;
uniformity is required and exactly UNIFORM, NONUNIFORM or UNKNOWN. Source,
six-field position namespace, reference economics and timing are reused.

The sole supported model is `LINEAR_SAME_CURRENCY_PAYOFF_V1`. For future
consumers, LONG signed change is exit minus entry; SHORT is entry minus exit.
Gross reference P&L is signed change times the constant positive payoff
coefficient times positive quantity magnitude. Prices have dimensions C/R,
coefficient R/Q, quantity Q, result C. Reference asset/unit and price currency
come from reference economics; Q is the namespace quantity unit. Explicit
`pnl_currency` must equal known `price_currency`; mismatch rejects, never converts.
P&L currency does not establish settlement currency. The model is symmetric,
entry-level-independent and linear in finite-decimal fractional quantities,
without an executability claim. Reciprocal, nonlinear, asymmetric, tiered,
cross-currency and undocumented transformed payoffs are unsupported.

`reference_units_per_quantity_unit` and `payoff_units_per_quantity_unit` are
independent assertions. Neither is derived from the other, even when equal.
Reference `model_support`/`completeness` retain their existing meaning.
Payoff completeness does not depend on the reference-notional multiplier.

UNIFORM explicitly asserts economics uniform across the entire six-field
namespace. NONUNIFORM declares material variation that namespace cannot
represent; UNKNOWN does not establish uniformity. No account ID is added.
Missing account ID never proves uniformity. The source revision identifies the
whole declaration; owner validation checks supplied consistency, not external
truth. Source authentication remains `NOT_VERIFIED_BY_THIS_CAPABILITY`.

V2 adds derived output `payoff_model_support` and `payoff_completeness`:

| Declaration | Support | Completeness |
| --- | --- | --- |
| Recognized, UNIFORM, required values/dimensions present | SUPPORTED | COMPLETE |
| Recognized, UNIFORM, required evidence missing | SUPPORTED | PARTIAL |
| Recognized, UNKNOWN uniformity | SUPPORTED | PARTIAL |
| Recognized, NONUNIFORM | UNSUPPORTED | COMPLETE or PARTIAL by supplied evidence |
| Unknown nonempty model | UNSUPPORTED | UNAVAILABLE |
| Null model | UNAVAILABLE | UNAVAILABLE |

Unknown/null models require null coefficient and P&L currency. Recognized
models require coefficient, P&L currency, reference asset, reference unit and
price currency for completeness. Malformed supplied values reject even for
unsupported scope. A usable interpretation requires SUPPORTED plus COMPLETE
plus separate applicability; no state implies freshness, authenticity,
executability, compliance or authorization. Missing economics never becomes zero.

Financial numbers use canonical plain decimal strings: no exponents, floats,
bools, whitespace, leading plus or nonfinite values. Trailing fractional zeros
and signed zero normalize; zero/negative payoff coefficients reject. No rounding
or candidate arithmetic occurs. Future arithmetic must preserve exact finite
Decimal results independently of ambient precision; candidate-number conversion
and any later explicit tick/currency rounding rules are outside this owner.

Identity binds the complete normalized v2 result, including all source,
namespace, timing, reference/payoff content, uniformity, derived statuses,
requested evidence boundary, limitations and false authority. Equivalent
normalized inputs agree; changes in economic meaning change identity. Owner
validation reconstructs and compares complete content, rejects substitutions,
and returns detached content. Candidate identity, quantity and a particular
applicability T/K result are absent.

### Versioned applicability under the existing owner

The existing applicability module adds `CONTRACT_V2`, `RULE_VERSION_V2`,
`CAUSAL_INSTRUMENT_SPECIFICATION_APPLICABILITY_RESOLVER_V2` and
`validate_causal_instrument_specification_applicability_resolver_v2`.
Contract/rule are `trading.causal_instrument_specification_applicability_resolver.v2`
and `causal_instrument_specification_applicability_resolver_v2`.
Input/output fields and lifecycle algorithm retain their existing meanings.
V1 behavior is unchanged and does not accept v2 metadata.

The v2 entry point dispatches v1/v2 metadata to the exact owner validator and
retains each owner's contract, rule, snapshot identity and complete-content
fingerprint. Mixed lifecycle collections may transition from v1 to v2. Selecting
v1 does not provide payoff semantics. Unknown versions, relabeling, tampering,
input disagreement and duplicate source revision representations (including
v1/v2 collisions) reject. Applicability does not itself test payoff completeness.

Lifecycle evidence v1 is unchanged: its references identify whole economic
revisions. Payoff changes require a distinct source revision. A stateless owner
cannot detect undisclosed historical revision reuse. Resolution remains
source-relative, without global governing precedence. The fact exposes timing;
the future consumer chooses economic T for its claim, and the resolver applies
supplied T/K. No candidate economic time is chosen here.

### Deferred bridge and exclusions

A later financial measurement must establish evidence-backed compatibility of
technical symbol and source/data-contract domain with the financial namespace,
selected payoff-bearing revision, price denomination, provenance and temporal
scope. Matching XAUUSD strings is insufficient. No bridge, registry or symbol
resolver is implemented here.

No candidate P&L/loss, sizing, account state, current market price, account risk
percentage, permitted loss, FX, spread, commission, fees, financing, slippage,
margin, compliance, authorization or execution is performed. Costs are excluded,
not zero-filled. Authority remains exactly trade_decision=false,
financial_risk=false, execution=false.

## Candidate gross reference financial measurement v1

`xauusd_candidate_gross_reference_financial_measurement.py` provides
`XAUUSD_CANDIDATE_GROSS_REFERENCE_FINANCIAL_MEASUREMENT.analyze()` and
`validate_candidate_gross_reference_financial_measurement()`.
Contract: `trading.xauusd_candidate_gross_reference_financial_measurement.v1`;
rule: `xauusd_candidate_gross_reference_financial_measurement_v1`.

This deterministic, stateless assessment measures the hypothetical frozen
entry-to-stop reference move under the instrument economics applicable at T1
candle completion, using evidence available through K. Scenario identifier:
`T1_COMPLETION_FROZEN_REFERENCE_V1`. Economic T is reconstructed candidate
`valid_from`, checked against the opening-labelled T1 candle plus M1 duration.
It is not actual entry, fill, receipt or order time. Point applicability suffices
for this frozen-terms scenario; no holding-interval economics are asserted.
Current candidate validity is neither consumed nor identity-bound. Later
INVALIDATED/EXPIRED/UNKNOWN validity does not erase historical geometry.
MEASURED never implies current actionability.

### Exact input and local assertion

Input fields are exactly `contract`, `rule_version`, `knowledge_boundary`,
`candidate_formulation`, `formulation_input`, `applicability`,
`applicability_input`, `bridge_assertions`. The frozen candidate formulation is
reconstructed by its owner. Applicability must reconstruct through #28 v2 with
its economic timestamp equal T and knowledge boundary equal K. All nested
lifecycle and specification artifacts are owner-validated. Selected metadata is
obtained from that reconstruction input and matched to the resolver's exact
selected owner reference, never accepted as an independent substitute.

Each bridge assertion has exactly:

| Field | Meaning |
| --- | --- |
| `contract` | `CANDIDATE_FINANCIAL_PRICE_DOMAIN_BINDING_ASSERTION_V1` |
| `assertion_revision_id` | Nonblank assertion revision identifier |
| `source` | Exactly nonblank `source_id`, `source_contract`, `source_contract_version` |
| `available_at` | Explicit timestamp, normalized to UTC, admitted by K |
| `candidate_formulation` | Complete exact reconstructed frozen formulation |
| `selected_specification` | Complete exact selected owner artifact, v1 or v2 |
| `relationship` | `DIRECT_PRICE_DENOMINATION_COMPATIBILITY` |
| `verdict` | `COMPATIBLE` or `INCOMPATIBLE` |

Full formulation binding covers candidate identity, technical symbol, both exact
T1/E1 references, original M1 source and upstream strategy/action provenance.
It introduces no external feed identity. Full financial binding covers source
revision, namespace, owner version, identity and dimensions. The assertion
expressly covers both frozen references under the versioned numeric rule and
selected price domain. No scaling, reciprocal transformation, unit conversion
or hidden FX is supported. A known need for such transformation is expressed
as INCOMPATIBLE, not as another supported relationship type.

No bridge effective interval, registry, service or persistent lifecycle exists.
Assertions refer to this exact candidate/specification subject. A bridge cannot
claim a selected subject when the resolver selected none. Source assertions
remain unauthenticated: `NOT_VERIFIED_BY_THIS_CAPABILITY`.

Every supplied assertion is admitted evidence: `available_at > K` rejects,
never filters. Empty collection means missing proof. Normalize timestamps,
collapse only complete normalized duplicates, and sort by canonical complete
content. Distinct provenance stays identity-significant. Same assertion revision
identifier with differing normalized content rejects across the collection.
COMPATIBLE and INCOMPATIBLE assertions together reject. Multiple compatible or
multiple incompatible assertions retain their distinct provenance. There is no
claim that supplied evidence exhausts all external sources.

### Numeric interpretation and monetary meaning

`CANDIDATE_PRICE_DECIMAL_INTERPRETATION_V1` interprets built-in integers exactly
without float conversion; built-in finite floats through exact parsing of
Python `repr`. Scientific notation is allowed only during parsing. Booleans and
nonfinite numbers reject. Other owner-valid representations are unsupported,
never coerced. The result is exact relative to this rule, not recovered original
feed decimal precision.

Arithmetic uses signed integer coefficients and decimal scales. Scale alignment,
subtraction and multiplication are exact and independent of ambient Decimal
precision. Canonical values are plain decimal strings, with unnecessary trailing
fractional zeros removed and signed zero normalized. No rounding occurs.
LONG distance is entry minus stop; SHORT distance is stop minus entry. No
absolute-value repair is performed. Nonpositive interpreted distance rejects
with `INTERPRETED_GEOMETRY_INCONSISTENCY`, which is not automatically an
accusation of upstream tampering: mixed integer/float interpretation can collapse
previously strict geometry.

For MEASURED, exact selected metadata v2 must establish supported complete
UNIFORM `LINEAR_SAME_CURRENCY_PAYOFF_V1` economics. Native P&L currency must equal
price currency. Reference asset/unit and quantity unit must be established.
Gross reference loss per quantity unit equals distance times the independent
positive payoff coefficient. The reference-notional multiplier is not used or
required. Output is a positive magnitude in P&L currency per quantity unit,
not signed/realized P&L, executable loss, an account risk or a quantity-one trade.

### Failure precedence and output

Validate every supplied schema, owner artifact, subject binding and contradiction;
validate causal admissibility; evaluate decisive blockers; otherwise evaluate
missing proof; calculate only when all requirements pass. A blocker never hides
malformed supplied evidence. T and the frozen upstream knowledge boundary must
not exceed K.

| Outcome | Meaning |
| --- | --- |
| `NOT_MEASURABLE` | Selected v1, explicit unsupported payoff model, NONUNIFORM scope, direct incompatibility, or owner-valid unsupported price representation |
| `UNKNOWN` | No decisive blocker and missing bridge/payoff proof, PARTIAL economics, UNRESOLVED or NO_APPLICABLE_REVISION_ESTABLISHED |
| `MEASURED` | Complete supported applicable compatible evidence and positive interpreted geometry |

REJECT is a ValueError input/contract failure, not an outcome. In particular,
selected v1 plus absent bridge is NOT_MEASURABLE; selected v1 plus malformed or
post-K bridge rejects. No-applicable-revision remains source-relative, not a
claim of universal absence. Unselected metadata cannot establish a selected
payoff blocker.

Output includes contract/rule/scenario/numeric interpretation, reconstructed
candidate formulation, canonical assertions, reconstructed applicability,
selected specification or null, T/K, interpreted entry/stop or null, distance
or null, usable payoff coefficient or null, established P&L currency/quantity
unit or null, outcome, ordered reasons, monetary result, source-authentication
limitation, authority, exclusions and `assessment_identity`. Monetary result is
null for every non-MEASURED outcome, never zero-filled.

Decisive reasons are ordered: unsupported price representation, selected v1,
unsupported payoff model, nonuniform payoff, direct incompatibility. If no
blocker applies, missing reasons are ordered: unresolved/absent applicability or
incomplete payoff, then missing bridge. Successful reason is
`GROSS_REFERENCE_LOSS_MEASURED`.

Identity hashes complete normalized output before adding its identity field.
It binds actual selected content (including v1), explicit absence, evidence
provenance and availability, scenario, interpretation, boundaries, outcomes and
exclusions. Assertion permutations/exact duplicates normalize identically.
Validation reconstructs complete output and rejects altered content even with a
matching-looking identity. Results and validation returns provide detached copies.

Authority remains `{trade_decision: false, financial_risk: false, execution: false}`.
Excluded: current actionability, supplied-quantity loss, sizing, account binding,
balance/equity, account risk, permitted loss/headroom, FX, spread, slippage,
commission, swap, margin, executable bid/ask, tick/order rounding, quantity
minima/maxima/steps, candidate compliance, trade authorization and execution.
Costs are excluded rather than represented as zero. No existing production
contract is modified.

## Current executable entry-to-stop risk basis v1

`xauusd_current_entry_to_stop_risk_basis.py` exposes
`evaluate_current_entry_to_stop_risk_basis(request, *, trusted_planning_context=None)`
and `validate_current_entry_to_stop_risk_basis(assessment, request, *,
trusted_planning_context=None)`. Contract:
`trading.xauusd_current_entry_to_stop_risk_basis.v1`; rule:
`xauusd_current_entry_to_stop_risk_basis_v1`. The capability is a point-in-time,
deterministic, read-only financial measurement. It can establish a typed monetary
loss function for a prospective immediate market entry and the original
technical stop, conditional on an explicitly admitted planning scenario. It
does not choose a quantity or authorize an order. Historical T1 measurement
continues to describe the frozen historical reference, not current execution.

The exact request fields are `contract`, `rule_version`,
`assessment_economic_time`, `knowledge_boundary`, `candidate`, `validity`,
`applicability`, `price_observations`, `scenario_evidence`, `planning_evidence`
and `account_state`. Candidate, validity, #28 v2 applicability, each #26 price,
selected payoff metadata v2 and optional #24 account evidence are reconstructed
through their public owners with full input/artifact pairs. #28's selected
revision is a source reference: the selected specification body is recovered
from the validated resolver revisions. Historical policy source specifications
are carried inside the local planning evidence, never added to #28's exact
current-revision inventory. Candidate validity has no native assessment ID, so
the local binding references its complete reconstructed content.

Current economic time, validity evaluation time and knowledge boundary are the
same instant K. Compare parsed UTC instants because technical candidate stamps
and financial snapshot stamps have different fractional-second formatting.
Financial owners preserve their own content and identifiers. Quote age uses the
actual `price_time` and exact integer microseconds, with equality at the
approved maximum admitted. An old receipt cannot refresh an old quote. #28
must establish current applicability through K. Post-K admitted evidence
rejects. The result is not a reusable authorization lease.

For an established result, two owner-valid #26 observations provide one
explicitly source-declared coherent BID/ASK event. Matching timestamps alone
do not prove coherence. Both observations must match the selected financial
namespace and denomination, have compatible supplier provenance, positive
prices and `BID <= ASK`. The only supported entry mechanism is
`IMMEDIATE_MARKET_ENTRY_SCENARIO_V1`, with output
`order_entry_constraint=NONE`. The prospective LONG entry reference is ASK;
SHORT is BID. No liquidity or fill guarantee follows from an observed quote.

The frozen candidate stop S is interpreted under directly compatible financial
price terms. A prospective LONG stop triggers on BID <= S; a SHORT stop on
ASK >= S. These touch semantics differ from the candidate owner's completed-M1
strict-breach validity rule. The current quote must be on the safe side of S.
The original stop must lie exactly on the declared grid `(S-origin)/tick`, and
the declared minimum trigger distance must be met without rounding or widening.
No actual trigger or fill is inferred.

Only complete, supported, uniform
`LINEAR_SAME_CURRENCY_PAYOFF_V1` metadata v2 can establish the monetary
expression. The payoff coefficient is `payoff_units_per_quantity_unit`, not
the reference-notional multiplier. Quantity and P&L dimensions must match
charges and any bound account. No FX conversion is performed. Built-in integer
candidate prices are exact; finite built-in float candidate prices use their
decimal Python `repr` interpretation. All subsequent arithmetic is exact.

With approved adverse-entry allowance `a_e`, adverse-stop allowance `a_s`,
payoff coefficient `p` and supported positive quantity `0 < q <= Q`:

| Direction | Assessed entry E | Assessed stop fill X | Distance d |
| --- | --- | --- | --- |
| LONG | ASK + a_e | S - a_s | E - X |
| SHORT | BID - a_e | S + a_s | X - E |

The typed model `POSITIVE_QUANTITY_LINEAR_PLUS_MINIMUM_AFFINE_CHARGES_V1`
represents `R(q) = p*d*q + Σ max(minimum_i, fixed_i + per_unit_i*q)` for that
positive domain. Its separate `R(0)=0` branch is mathematical no-trade. Every
opening, closing, other-charge and financing category needs explicit INCLUDED,
NOT_APPLICABLE, UNKNOWN or UNSUPPORTED coverage. INCLUDED needs supported
aggregate terms; no missing cost becomes zero. Financing must cover the whole
entry-to-terminal-stop scenario or be explicitly inapplicable. Candidate expiry
is not a holding deadline. Spread is already represented by the appropriate
quote sides and is not charged again.

The local scenario declaration contract is
`trading.xauusd_current_entry_to_stop_risk_basis.scenario_evidence.v1`.
Declarations bind full candidate, validity, applicability, selected
specification, current BID/ASK and optional account references. They carry
status, effective interval, exact terms and typed supporting evidence.
`SOURCE_DECLARED_TERM`, `PLANNING_ASSUMPTION` and `BROKER_CONSTRAINT` remain
distinct; a label or prose alone cannot establish a term. A coherent event is
dynamic evidence. The local planning inventory contract is
`trading.xauusd_current_entry_to_stop_risk_basis.planning_evidence.v1` with
rule `APPROVED_CONDITIONAL_PLANNING_SCENARIO_V1`. It carries a complete
approval/rejection/revocation history and source-relative coverage through K.
An explicit full-content predecessor reference is required for replacement.
Conflicting revisions, missing predecessors, cycles, branches, retrospective
approval and altered content reject. A currently effective rejection or
revocation prevents admission; a future-effective one does not apply early.
Expiration does not revive a predecessor. No highest-version selection occurs.

The planning inventory is admissible only when an independently supplied host
`trusted_planning_context` pins its complete canonical digest, issuer,
planning-only mandate, scope and K. The keyword parameter represents a
host-assigned trust assumption, not external authentication or protection
against hostile in-process Python. Without it, planning admission remains
UNKNOWN; a detached validator also needs it to reproduce an established
assessment. Approval binds static candidate/specification/scope and scenario
terms. Current quotes, quote event, validity and #28 resolution remain dynamic.
Planning approval permits an exact conditional analytical assumption; it is
not a broker guarantee, prudence judgment, financial-risk authorization or
trade decision.

The outcomes are ESTABLISHED, NOT_SUITABLE and UNKNOWN. Every supplied owner
artifact and local declaration is checked before outcomes; malformed,
contradictory or post-K admitted content raises ValueError. Decisive
incompatibility outranks uncertainty, while retaining all justified reasons.
`risk_function` is null for every non-established assessment. Detached
validation reconstructs and compares the entire result, including a full
canonical content identity. All authority flags and top-level execution remain
false. Excluded: quantity selection, equity and daily-loss budget comparison,
provider compliance, FX, margin, actual fills, realized P&L, stop management,
BUY/SELL authorization and execution. Mission Control remains the final
decision authority.

## Current entry quantity-domain assessment v1

`xauusd_current_entry_quantity_domain.py` exposes
`evaluate_current_entry_quantity_domain(request, *, trusted_quantity_context=None)`
and `validate_current_entry_quantity_domain(assessment, request, *,
trusted_quantity_context=None)`. Contract:
`trading.xauusd_current_entry_quantity_domain.v1`; rule:
`xauusd_current_entry_quantity_domain_v1`.

This read-only derived assessment establishes only the independently admitted,
current entry-order grid and bounds for one exact source/account/instrument
scope. It has no candidate, account-state, instrument-metadata, #28, #29 or
risk-policy dependency. A later consumer must reconstruct those owners and prove
their joins. Entry-order volume bounds are distinct from a resulting-position
maximum and a risk scenario's maximum supported quantity. No existing contract,
registry, Mission Control route, executor or connector changes.

### Exact request and source evidence

All listed keys are required; extra keys are rejected. Explicit unknowns use
null, declared gaps or unknown tagged values. IDs are nonblank strings preserved
without trimming, case folding or Unicode normalization. Times require seconds,
an explicit timezone and at most microsecond precision; normalization uses UTC
with six fractional digits. Intervals include their start and exclude their end;
a null end explicitly means open-ended. Hashes are lowercase SHA-256 hex.

The request keys are `contract`, `rule_version`, `assessment_economic_time`,
`knowledge_boundary`, `scope`, `quantity_inventory`. Current assessment requires
`T = K`. Missing inventory is null. Scope keys are `provider_id`, `venue_id`,
`environment` (DEMO/LIVE), `account_id`, `instrument_id`, `quantity_unit`,
`entry_direction` (LONG/SHORT), `entry_mechanism`
(`IMMEDIATE_MARKET_ENTRY_SCENARIO_V1`). Identities belong to that exact namespace;
no aliases or quantity-unit conversions are inferred.

Source references contain `source_id`, `source_contract`,
`source_contract_version`, `source_snapshot_id`. Original evidence items contain
`evidence_id`, `source`, `media_type`, `content_base64`, `source_available_at`,
`observed_at`. Base64 is canonical padded RFC 4648, encoding nonempty original
bytes. Evidence references contain `evidence_id`, `content_sha256`; they bind the
whole normalized evidence item, including bytes, provenance and timing.

Inventory contract is
`trading.xauusd_current_entry_quantity_domain.inventory.v1`; rule is
`xauusd_current_entry_quantity_domain_inventory_v1`. Its keys are `contract`,
`rule_version`, `model`, `source`, `scope`, `source_available_at`, `observed_at`,
`evidence`, `coverage`, `records`, `unsupported_lifecycle_evidence`. Its only model
is `WHOLE_ENTRY_DOMAIN_REPLACEMENT_STREAM_V1`. Scope must exactly match the
request. Unsupported lifecycle events are preserved as evidence references;
they produce UNKNOWN rather than being discarded. The owner preserves original
documents but does not parse arbitrary documents or authenticate providers.

### Stream records and coverage

Declaration keys are `record_id`, `kind` (DECLARE), `predecessor`,
`effective_from`, `effective_until`, `source_available_at`, `observed_at`,
`evidence_refs`, `domain`. A null domain honestly reports unavailable terms.
Withdrawal keys are `record_id`, `kind` (WITHDRAW), `predecessor`,
`effective_from`, `source_available_at`, `observed_at`, `evidence_refs`. A
withdrawal has no expiry or domain and cannot be a root.

Predecessors are exactly `{kind: ROOT}`, `{kind: UNKNOWN}`, or
`{kind: RECORD, record: {record_id, content_sha256}}`. Record references bind the
whole normalized immutable record. Source records retain their immutable
identity within the issuer namespace and scope across inventory snapshots.

Coverage keys are `declaration_id`, `source_available_at`, `observed_at`,
`economic_from`, `economic_until`, `source_information_cutoff`,
`quantity_rule_completeness`, `revision_completeness`, `starting_basis`,
`root_records`, `missing_record_ids`, `records_omitted`, `history_truncated`,
`evidence_refs`. Completeness is COMPLETE/LIMITED/UNKNOWN; starting basis is
FROM_INCEPTION/INCOMPLETE_OR_UNKNOWN. Omission flags are booleans or null.
Root records are exact record references; known missing IDs identify absent
record bodies. Every supplied root must be declared; declared roots must resolve
to roots or explicitly missing records. Multiple valid roots remain evidence
of unresolved uniqueness, not permission to select one.

Complete quantity coverage requires every supplied declaration body to be
present and supported, including historical bodies. Complete revision coverage
requires inception coverage, known predecessors, no missing records and both
omission flags false. LIMITED revision coverage requires a concrete declared
limitation. UNKNOWN may preserve known partial facts. Explicit contradictions
with COMPLETE coverage are rejected.

An explicitly declared absent predecessor yields UNKNOWN. An undeclared dangling
reference, mismatching body hash, conflicting immutable identity, self-reference
or cycle is rejected. Missing evidence references are malformed; unavailable
support is represented by an empty reference list and yields UNKNOWN. Duplicate
IDs and references are rejected, including exact duplicates.

Positive resolution requires one complete, acyclic, nonbranching chain from one
root, with nondecreasing effective starts. Precedence follows exact predecessor
links, never revision labels, input order or observation times. Branches and
multiple roots produce UNKNOWN even when their domains agree. Conservatively,
known future branches also prevent a supported whole-stream proof. Decreasing
effective starts and explicitly unsupported events produce UNKNOWN.

The last chain record effective by T governs; equal effective starts follow
chain order. A known future successor does not replace the current record early.
An effective withdrawal or expired successor yields UNKNOWN without reviving a
predecessor. A new complete declaration explicitly following a withdrawal can
govern; an opaque correction or reinstatement instruction remains unsupported.

### Independent host admission and time

Admission contract is
`trading.xauusd_current_entry_quantity_domain.admission.v1`; rule is
`xauusd_current_entry_quantity_domain_admission_v1`. Keys are `contract`,
`rule_version`, `admission_id`, `authority_id`, `mandate_id`, `mandate_revision`
(positive integer), `purpose` (ENTRY_QUANTITY_FACT_ADMISSION_ONLY),
`admission_basis` (PROVIDER_ORIGIN_VERIFIED_EXTERNALLY or
PROVIDER_DOCUMENTS_REVIEWED_EXTERNALLY), `inventory_source`,
`inventory_content_sha256`, `scope`, `knowledge_boundary`, `admitted_at`,
`available_at`, `effective_from`, `effective_until`, `assurances`.

Assurances have exactly `source_authority`, `quantity_rule_semantics`,
`revision_coverage`, `evidence_availability`. Each contains `status`
(ADMITTED/UNRESOLVED) and `evidence_refs`; ADMITTED requires nonempty, resolvable
support. All four must be independently admitted. They cover exact source
authority, whole-domain semantics, inventory/revision coverage fidelity and
availability of original evidence by K. A host context cannot override actual
source gaps, unsupported lifecycle semantics or invalid grid terms.

The host independently injects this context. Source identifiers, provenance,
hashes and caller approval assertions do not authenticate a provider. A
keyword-only parameter is not a security boundary against hostile Python inside
the trusted host. No real provider connector, admission integration or verified
live volume rules are supplied by this capability. Synthetic tests simulate the
boundary and do not establish provider facts. Source authentication always
remains NOT_VERIFIED_BY_THIS_CAPABILITY.

Context source, scope, normalized inventory pin and K must match exactly;
mismatches are rejected. A context with null inventory is rejected because its
pin has no target. Admission validity must contain T; an otherwise valid expired
or future admission produces UNKNOWN.

Every observation must be at or before K. Known source availability must be at
or before observation; unknown availability yields UNKNOWN. The inventory cannot
precede contained observations. Known coverage cutoff must not exceed K or its
known publication time; establishment requires cutoff exactly K and economic
coverage containing T. All material observations must precede admission, with
`admitted_at <= available_at <= K`. Post-K evidence or admission is rejected.
Future effective starts are permitted independently of availability. The strict
complete-through-K requirement may force publication, observation and admission
to meet at K; delayed feeds must remain unresolved rather than be backdated.

### Exact grid and canonical identity

Grid keys are `model` (REGULAR_GRID_CLOSED_BOUNDS_V1), `origin`, `increment`,
`minimum`, `maximum`. Maximum is exactly `{kind: FINITE, value}` or
`{kind: UNBOUNDED}`. Terms are signed finite decimal strings; increment must be
positive. Finite bounds must satisfy minimum <= maximum. An unknown maximum is
not unbounded. Unsupported models, binary floats, booleans, exponents,
nonfinite values, leading plus signs and whitespace are rejected.

Decimal syntax is `-?[0-9]+(?:\.[0-9]+)?`. Normalize leading integer zeroes,
trailing fractional zeroes and negative zero. Arbitrary-precision integer and
rational arithmetic avoids a fixed Decimal context and Python's configurable
integer-to-decimal digit conversion limit.

For `q = o + n*d`, integer n, `d > 0`, `q > 0`, and inclusive bounds m and M,
normalize `r = o - floor(o/d)*d`, so `0 <= r < d`. Derive
`first = max(ceil((m-r)/d), floor(-r/d)+1)` and, for finite M,
`last = floor((M-r)/d)`. The positive domain is empty exactly when last < first.
The original index may be negative, and canonical first may be zero when r > 0.
Zero/negative minimums do not admit nonpositive quantities. An explicitly
unbounded maximum has no last index. No domain enumeration or quantity selection
occurs.

Descriptor is `{kind: EMPTY}` or
`{kind: REGULAR_GRID, origin, increment, first_index, last_index}`. Indices are
canonical nonnegative integer strings; null last means explicitly unbounded.
Domain identity hashes quantity unit and descriptor. It identifies a normalized
descriptor, not all alternative representations of the same finite set.

Canonical JSON sorts keys, uses compact separators and UTF-8 without Unicode
escaping, and rejects nonfinite values and surrogate code points. Typed times
and decimals normalize; IDs and source bytes remain exact. Set-like collections
sort by canonical content. Equivalent decimal spellings preserve normalized
record/inventory identities; changing source bytes changes evidence identity.
Origin shifts by whole increments preserve domain identity while changing
declaration/assessment identity. The complete normalized inventory is pinned;
hashes establish consistency, not authenticity.

### Outcomes, reconstruction and authority

All supplied material is validated before outcomes. Malformed schema, numeric
terms, contradictory completeness, invalid references, pins, intervals or causal
timing raises ValueError, even if another gate would yield UNKNOWN. Honest
missing evidence, unresolved assurance, incomplete coverage, unsupported or
competing histories, withdrawal and expiry produce UNKNOWN. No unadmitted or
otherwise unresolved declaration can establish an empty effective domain.

Only fully admitted, complete, uniquely current evidence permits ESTABLISHED
for a nonempty positive grid, or NOT_SUITABLE for a mathematically empty grid.
Reasons are deduplicated and lexicographically sorted; findings requiring absent
inputs are not invented. The module's closed `REASON_CODES` vocabulary contains
the frozen uncertainty reasons and the two success/empty-domain reasons.

Output keys are `contract`, `rule_version`, `assessment_economic_time`,
`knowledge_boundary`, `scope`, `outcome`, `reason_codes`, `resolved_record`,
`domain`, `domain_identity`, `reconstruction_evidence`, `source_authentication`,
`downstream_obligations`, `authority`, `execution`, `assessment_identity`.
UNKNOWN has null domain and domain identity; a fully admitted resolved withdrawal
or expired successor may retain its record reference. Reconstruction evidence
contains the normalized `request` and `trusted_context_content_sha256` or null.
The validator requires the independently supplied context again, rebuilds the
entire assessment and compares complete canonical content. Serialized outputs
require exact JSON container types. Results and validation returns are detached.

Assessment identity is `current_entry_quantity_domain_` plus the SHA-256 of the
complete result before adding that identity. Domain identity is
`entry_quantity_domain_` plus the hash of `{quantity_unit, domain}`.

Fixed sorted downstream obligations are BUDGET_AND_DAILY_LOSS_ELIGIBILITY,
CANDIDATE_VALIDITY, INSTRUMENT_AND_UNIT_COMPATIBILITY,
MARGIN_AND_CAPITAL_FEASIBILITY, MARKET_AND_ORDER_EXECUTION_FEASIBILITY,
MISSION_CONTROL_AUTHORIZATION, POSITION_EFFECT_AND_OTHER_PROVIDER_COMPLIANCE,
RISK_CONSTRAINED_QUANTITY_SELECTION. These are unresolved requirements, not
findings that other owners passed or failed.

All authority flags are false: `quantity_selection`, `budget_approval`,
`position_effect_compliance`, `margin_capital_approval`, `trade_decision`,
`financial_risk`, `execution`. Top-level execution is false. There is no selected
quantity, risk-budget calculation, position-effect proof, margin/capital
approval, trade authorization, broker mutation or execution.

## Current risk-budget quantity feasibility v1

`xauusd_current_risk_budget_quantity_feasibility.py` exposes
`evaluate_current_risk_budget_quantity_feasibility(request, *,
trusted_planning_context=None, trusted_quantity_context=None,
trusted_feasibility_context=None)` and
`validate_current_risk_budget_quantity_feasibility(assessment, request, *,
trusted_planning_context=None, trusted_quantity_context=None,
trusted_feasibility_context=None)`. Contract:
`trading.xauusd_current_risk_budget_quantity_feasibility.v1`; rule:
`xauusd_current_risk_budget_quantity_feasibility_v1`.

The sole calculation is the complete supported set
`F = {q in D: 0 < q <= Q and R(q) <= B}`. D is the independently admitted
entry-order domain, Q the established risk scenario's finite support, R its
charge-bearing conditional loss and B the eligible own-policy maximum budget.
No quantity is selected. No connector, registry, route, policy engine, Mission
Control change or execution integration is introduced.

### Request, reconstruction and source joins

All specified fields are required and extra fields reject. The request fields
are `contract`, `rule_version`, `assessment_economic_time`, `knowledge_boundary`,
`risk_policy`, `risk_basis`, `quantity_domain`, `binding_evidence`. Each owner
field is null or exactly `{assessment, request}` containing the complete native
serialized output and original input. Null declares unavailable evidence.
The three public native validators reconstruct every supplied artifact;
planning and quantity contexts are supplied independently to their owners.
An orphaned native context rejects. Native structures and identifiers remain
unchanged. Finite native JSON numbers remain in provenance, never in the new
quantity arithmetic. Non-JSON containers, nonfinite values and surrogate text
reject.

Current outer assessment times must all equal T=K. Compare parsed UTC instants,
not native timestamp spellings. Candidate formulation and original input must
match across policy and risk. Risk validity must bind that candidate at K.
Supplied risk/policy account input/artifact pairs must match completely.
Quantity direction and established risk mechanism must match the common entry.
These are structural co-references; violations reject before any outcome.
Historical measurement inside the policy retains its historical economic time
and specification revision.
Equivalent active scenario declarations retain the native risk owner's
established semantics: its validator already proves identical status, terms
and subjects, so distinct declaration IDs create no additional selection gate.

A positive composition requires the risk owner's account-bound path: account
pair, active scenario account scope and independent planning account scope must
all exist and match environment, account ID and currency. A valid account-free
risk result remains usable in its own contract but is unresolved here.
Relevant active #29 instrument bindings must match the current financial
source-qualified namespace on common fields; no namespace alias is inferred.

The binding contract is
`trading.xauusd_current_risk_budget_quantity_feasibility.binding.v1`, rule
`xauusd_current_risk_budget_quantity_feasibility_binding_v1`. Its exact fields:
`contract`, `rule_version`, `binding_id`, `source`, `assessment_economic_time`,
`knowledge_boundary`, `effective_from`, `effective_until`,
`source_available_at`, `observed_at`, `subjects`, `claims`, `evidence`.
Source is exactly `{source_id, source_contract, source_contract_version,
source_snapshot_id}`. Subjects has exactly `risk_policy_bundle_sha256`,
`risk_basis_bundle_sha256`, `quantity_domain_bundle_sha256`; each is the hash
of its complete owner envelope, or null exactly for an absent envelope.

Claims has exactly four keys, each `{status, evidence_refs}` with status
COMPATIBLE/INCOMPATIBLE/UNKNOWN:

| Claim | Literal conditions and independent semantic obligation |
| --- | --- |
| account_provider_venue | Risk account ID/environment equal quantity scope, planning venue equals quantity venue; independently admit the source-qualified account, provider and financial/quote venue relationship. |
| instrument_namespace | Candidate, current selected specification and quantity instrument/environment agree; independently admit actual provider instrument identity. |
| quantity_denomination | Financial, entry-grid and active charge units agree literally; independently admit equal economic meaning without scaling. |
| monetary_denomination | Policy/account, current payoff and active charge currencies agree; independently admit equal monetary denomination without FX. |

The first three claims address risk/domain envelopes; monetary denomination
addresses risk/policy. A non-UNKNOWN assertion with absent addressed envelopes
rejects. A COMPATIBLE assertion contradicting known literal subjects rejects.
Missing comparands remain unresolved. Matching provider/source labels do not
establish trust or source equivalence.

### Original evidence, time and independent admission

Binding and feasibility context have separate evidence catalogs. Evidence has
exactly `evidence_id`, `source`, `media_type`, `content_base64`,
`source_available_at`, `observed_at`. Original bytes must be nonempty canonical
padded base64. References are exactly `{evidence_id, content_sha256}`, hashing
the whole normalized evidence item. References resolve within their catalog;
duplicate IDs/references and mismatched or missing references reject. Empty
source support lists and null source availability are explicit unresolved
facts, not incompatibility. No document parser or provider authentication is
implemented.

The feasibility admission contract is
`trading.xauusd_current_risk_budget_quantity_feasibility.admission.v1`, rule
`xauusd_current_risk_budget_quantity_feasibility_admission_v1`. Exact fields:
`contract`, `rule_version`, `admission_id`, `authority_id`, `mandate_id`,
`mandate_revision` (positive integer, excluding booleans), `purpose`
(`FEASIBILITY_FACT_AND_BINDING_ADMISSION_ONLY`), `knowledge_boundary`,
`effective_from`, `effective_until`, `admitted_at`, `available_at`, `evidence`,
`admissions`.

Each admission is exactly `{target, subject_content_sha256, assurances}`.
Assurances has exactly `source_authority`, `fact_and_policy_semantics`,
`coverage_for_proposition`, `causal_availability`, each exactly
`{status, evidence_refs}` with ADMITTED/UNRESOLVED status. ADMITTED requires
nonempty original evidence references with known source availability and
observation no later than admission. A target is trusted only when all four
assurances are admitted and the context is current.

Permissible targets and projections are frozen:

| Target | Exact hashed projection |
| --- | --- |
| `{kind: POLICY_GATE, gate: EQUITY/DAILY_LOSS/FINANCIAL_COMPATIBILITY/REGIME}` | `{target, owner_bundle: risk_policy}` |
| `{kind: PROVIDER_RULE, rule_reference: {rule_id, full_content_sha256}}` | `{target, owner_bundle: risk_policy}` |
| `{kind: RISK_FUNCTION_INPUTS}` | `{target, owner_bundle: risk_basis, trusted_planning_context_sha256}` |
| `{kind: RISK_NEGATIVE, reason_code}` | `{target, owner_bundle: risk_basis, trusted_planning_context_sha256}` |
| `{kind: BINDING, claim}` | `{target, binding_evidence}` |

Policy targets identify `own_policy.equity_gate`, `own_policy.daily_loss_gate`,
`financial_compatibility`, `provider_policy.regime_gate`, or the unique native
rule result with that exact reference. Risk-negative selectors must belong to
the module's frozen `NATIVE_RISK_NEGATIVES` set and occur in the reconstructed
NOT_SUITABLE result's reasons excluding uncertainties. Nonexistent targets,
duplicate targets, forged pins and arbitrary/wildcard targets reject.

Policy gate admission independently establishes its necessary source facts,
governing policy, semantics and coverage. The daily block can be admitted from
two definite qualifying losses without complete population coverage; a passing
daily gate still requires the native sufficient coverage. Risk-function input
admission covers underlying candidate/history, current specification, quotes,
source terms, charges and finite support, without granting planning permission.
Risk-negative admission covers the particular native predicate's necessary
facts and applicability. Binding admission establishes the exact asserted
relationship for its pinned subjects. One receipt never admits another target.
Native UNKNOWN cannot become SATISFIED through a receipt.

Planning-dependent negative selectors (`PLANNING_*`, `APPROVED_*`, `TRUSTED_*`
and QUOTE_VENUE_MISMATCH) also need the separate native-valid planning context;
except mandate expiry itself, it must contain K. This deliberately fails
closed when the context is absent/inactive. A scoped risk negative establishes
unusability of the submitted basis; stale quotes do not establish a current
market stop trigger.

Local time requires seconds, timezone and at most microseconds, normalized to
UTC with six fractional digits. Intervals include their start and exclude their
end; null end means open-ended. Require observed_at <= K and known source
availability <= observation; context admitted_at <= available_at <= K and exact
K. An expired/future-effective context or binding remains unresolved. Supplied
post-K material, contradictory timing or admission before its supporting
evidence rejects. Native revision selection, withdrawals, histories and
availability retain their owners' semantics; a future known revision cannot
govern early and a predecessor is never silently revived.

Trusted hosts must independently supply contexts and actually verify facts,
authority, semantics, coverage and causal availability. Hashes, issuer strings
and caller approval flags cannot authenticate their supplier. Native planning
permission, quantity-fact admission and feasibility admission remain separate.
No live provider connector or production admission integration is established.

### Exact domains and deterministic outcomes

Canonical D is `q = r + k*increment`, with 0 <= r < increment, positive
represented q, integer first/last indices and an optional unbounded last index.
Index zero is valid for positive residue. For Q, compute
`N = floor((Q-r)/increment)`, supported last `min(U,N)` (N when U unbounded),
and tail first `max(L,N+1)`. Empty intervals are `{kind: EMPTY}`. Otherwise
the native descriptor shape is retained with canonical integer strings.

Positive risk is `c*q + sum(max(minimum_i, fixed_i + per_unit_i*q))` with c>0
and nonnegative charges, so it is strictly increasing. R(0)=0 is the no-position
alternative; positive fixed/minimum charges may create a jump at zero. Evaluate
the full first-point risk exactly. If it exceeds B, the supported feasible set
is empty. Otherwise integer upper-midpoint binary search derives the last
feasible index, including equality. It is a set boundary, never a selection.
Arithmetic uses arbitrary-precision rationals/integers, including chunked
decimal integer conversion; no floats, rounding or provider-grid enumeration.

Entry domain is available independently from native quantity admission. Risk
support requires established native risk and admitted inputs. Budget requires
all native policy gates SATISFIED and their independent admission, consuming
`maximum_monetary_risk`, never target-risk optimization. Supported domain/tail
need admitted risk support, account-bound evidence and the first three binding
claims; no budget is needed. Feasible domain additionally needs eligible B,
monetary compatibility and remaining joins. Null means unestablished; EMPTY
means proven empty. Provider quantities above Q remain explicitly unassessed.

Structural rejection always precedes outcomes. Independently admitted scoped
negatives yield NOT_SUITABLE; otherwise unresolved mandatory proof yields
UNKNOWN; otherwise a complete nonempty feasible set yields ESTABLISHED.
Candidate/policy failure never manufactures an empty mathematical set. Native
negative and unknown findings remain intact in reconstruction. Independent
unresolved diagnostics survive a decisive negative.

Output fields are `contract`, `rule_version`, `assessment_economic_time`,
`knowledge_boundary`, `outcome`, `reason_codes`, `negative_proofs`,
`unresolved_findings`, `budget`, `risk_support`, `entry_domain`,
`supported_entry_domain`, `feasible_domain`, `outside_risk_support`,
`reconstruction_evidence`, `downstream_obligations`, `source_authentication`,
`authority`, `execution`, `assessment_identity`. Budget is null or
`{amount, currency}`; support null or `{maximum_quantity, quantity_unit}`;
domain fields null or `{quantity_unit, domain}`. Proofs are exactly
`{reason_code, target, scope}`; unresolved findings `{reason_code, target}`.
Proof scopes are CANDIDATE_AT_K, POLICY_GATE_AT_K, RISK_INPUT_BUNDLE,
BINDING_RELATION, ENTRY_DOMAIN or SUPPORTED_DOMAIN. Diagnostic targets also
allow OWNER with RISK_POLICY/RISK_BASIS/QUANTITY_DOMAIN, COMPOSITION,
ENTRY_DOMAIN, SUPPORTED_DOMAIN and FEASIBLE_DOMAIN; these cannot be receipts.

The closed local reason vocabulary is `SUPPORTED_FEASIBLE_DOMAIN_ESTABLISHED`,
`CANDIDATE_NOT_CURRENTLY_VALID`, `PRE_QUANTITY_POLICY_BLOCKED`,
`RISK_BASIS_UNUSABLE`, `BINDING_INCOMPATIBLE`, `ENTRY_DOMAIN_EMPTY`,
`NO_SUPPORTED_POSITIVE_QUANTITY`, `BUDGET_BELOW_FIRST_SUPPORTED_QUANTITY_RISK`,
`OWNER_MISSING`, `OWNER_UNKNOWN`, `ADMISSION_MISSING`, `ADMISSION_UNRESOLVED`,
`ADMISSION_NOT_CURRENT`, `NEGATIVE_NOT_ADMITTED`, `BINDING_MISSING`,
`BINDING_SUPPORT_MISSING`, `BINDING_NOT_CURRENT`, `BINDING_UNRESOLVED`,
`ACCOUNT_APPLICABILITY_UNRESOLVED`, `POLICY_INSTRUMENT_NAMESPACE_UNRESOLVED`.
Native reasons stay native. Reasons/obligations are unique sorted strings;
proofs/findings sort by canonical content. OWNER_UNKNOWN also records native
risk uncertainties accompanying NOT_SUITABLE; it does not relabel that outcome.

Reconstruction is exactly `{request, trusted_planning_context_sha256,
trusted_quantity_context_sha256, trusted_feasibility_context_sha256}`. Missing
contexts have null hashes. Canonical encoding is compact sorted-key JSON with
ensure_ascii=False, allow_nan=False, encoded UTF-8. Normalize local records and
collections; preserve native owner requests and native context representations.
Local evidence sorts by ID, references by ID/hash, admissions by canonical
target. Composition assessment identity is
`current_risk_budget_quantity_feasibility_` plus the complete output hash before
adding its identity. Equivalent native presentations may retain different
composition provenance identities. The validator independently rebuilds every
field and context dependency, not merely a supplied ID. All returns detach.

All authority flags are false: quantity_selection, budget_approval,
position_effect_compliance, margin_capital_approval, trade_decision,
financial_risk, execution. Top-level execution is false and source authentication
is NOT_VERIFIED_BY_THIS_CAPABILITY. Fixed downstream obligations are
MARGIN_AND_AVAILABLE_CAPITAL_FEASIBILITY, MARKET_ORDER_AND_FILL_FEASIBILITY,
MISSION_CONTROL_CURRENT_AUTHORIZATION, POSITION_EFFECT_AND_ACCOUNT_RULE_COMPLIANCE,
POST_ENTRY_FLOOR_AND_PROVIDER_HEADROOM, QUANTITY_SELECTION_POLICY_AND_SELECTION.
Native detailed obligations remain in provenance. Equity budget is not
provider-safe headroom; entry volume is not resulting-position compliance;
conditional loss is not a guaranteed realized-loss ceiling.

## RESEARCH-ONLY — XAUUSD reference trade management experiment v0.1

`xauusd_reference_trade_management_experiment.py` is an additive, deterministic
research evaluator. It is not part of the authoritative production BUY/SELL
chain. It does not change Strategy #1, Technical Trade Candidate, current
candidate validity, financial measurement, #24–#29, Mission Control or execution.
It asks when a frozen candidate's protective reference stop should advance.
There is no account sizing, quantity, daily-loss gate, partial close, financial
P&L, optimizer, persistent replay, or broker order/fill model.

The public functions are `evaluate_reference_scenario(request)`,
`validate_reference_scenario(assessment, request)`,
`aggregate_reference_experiment(request)` and
`validate_reference_experiment(assessment, request)`. Detached validators fully
reconstruct their result; supplied identities never replace validation.
Contracts use `trading.xauusd_reference_trade_management_experiment` followed by
`.policy.v1`, `.scenario.v1`, `.aggregate.v1`, or `.dataset_relationship.v1`.
The experiment rule is `xauusd_reference_trade_management_experiment_v1`; the
relationship rule is `xauusd_reference_trade_management_dataset_relationship_v1`.
Policy values are frozen constants, not an optimization configuration surface.

### Frozen experiment and causal observation

All variants use the same owner-reconstructed candidate and original directional
R: entry minus initial stop for LONG, initial stop minus entry for SHORT. The
exact interpreted distance must be positive. BE and +1R/+2R/+3R remain anchored
to that immutable distance. A keeps its initial stop. B advances to BE after
+1R. C advances to BE after +1R and to +1R after +2R. D and E use C's stages but
require an eligible M1 or M5 directional pivot gate respectively. The target is
always +3R; it is not an optimal-target claim.

T is candidate `valid_from`, the frozen T1 completion. H is T plus exactly
1440 elapsed minutes. Eligible M1 intervals open at T or later and complete no
later than H. The T1-producing candle and the interval opening at H are excluded.
Entry eligibility expiry is not an open-position timeout. Missing candles do not
pause or extend H. This is a predeclared research observation duration only.

M1 owns all stop, milestone, target and gap observations. Equality is a touch.
Each completed interval first evaluates the previously active stop and target.
An opening already terminal uses the opening as its reference simulation mark;
otherwise an intrabar terminal touch uses the exact terminal level. Neither is
a fill claim. Opening-derived milestones are established at completion, only if
the interval survives. All reached milestones latch, the highest permitted stop
stage is selected, and activation begins with the next M1 interval. A newly
selected stop already beyond the close is evaluated at the next opening.

D/E use the strict three-consecutive-candle pivot predicate: LONG center low
below both neighbors; SHORT center high above both neighbors. Comparisons use
exact interpreted prices locally, without changing MarketStructureAnalyzer.
The center must open at or after T; its following candle must complete strictly
after first +1R establishment. Equal-boundary confirmation is permanently
ineligible. M5 contributes only E's gate. On gate opening, previously latched
+2R permits immediate completion-time catch-up to the +1R stop. No pivot or
management protection is backdated.

### Exact inputs and research relationship assumptions

A scenario request has exactly `contract`, `rule_version`, `variant`,
`candidate_formulation`, `formulation_input`, `research_boundary` and `evidence`.
Evidence contains `m1`, `m5` (null except where supplied for E), and `declarations`.
Source artifacts follow the existing causal snapshot contract; bounded histories
include the frozen T1 anchor and required pivot warm-up. The research boundary
must be at least H. Every supplied artifact is validated before replay, including
content that would follow an early terminal event. Overlapping original M1
history cannot replace the frozen source content.

Prices accept only built-in integers and finite built-in floats interpreted
through decimal `repr`. Bool, numeric subclasses, strings and Decimal inputs are
rejected. Exact rational arithmetic is equivalent to integer coefficient/scale
arithmetic for these finite-decimal prices and derived levels. Exact OHLC
validation supplements existing source validation. Ratios serialize as reduced
`numerator`/`denominator`, positive denominator, numerator sign, and zero `0/1`.
Undefined metrics are null. Decimal context and display rounding cannot affect
branching, results or identities.

Relationship declarations are explicit, non-authenticated research assumptions.
They do not prove external feed identity. Exactly two types are supported:
`CANDIDATE_ORIGIN_TO_M1_SAME_RESEARCH_PRICE_DOMAIN` and
`M1_TO_M5_COMMON_RESEARCH_DATASET`. The latter asserts a common research price
domain, dataset lineage and compatible declared grids; it does not assert that
M5 was aggregated from M1. Symbol/value/timestamp coincidences are insufficient.

Each declaration has exact fields: `contract`, `rule_version`, `declaration_id`,
`declaration_revision`, `relationship_type`, `source_namespace`,
`dataset_revision`, `price_domain`, `available_at`, `subject_bindings`,
`timeframe_grid_bindings`, `coverage_declarations`, `declaration_provenance`,
`authority`. Provenance contains `declarant_namespace` and `record_id`.
Revision is a positive built-in integer. The candidate-origin binding includes
complete formulation SHA256, reconstruction-input SHA256, candidate identity,
original M1 source reference, and explicitly both entry/stop reference fields.
Observation bindings include contract/rule, symbol/timeframe, snapshot identity
and full-artifact SHA256. All bindings are recomputed against supplied evidence.

Grid bindings contain timeframe, anchor opening and fixed duration (60 or 300
seconds). Equivalent anchor phases normalize against the UTC epoch. An M5
anchor must lie on the declared M1 grid; UTC modulo-five alignment is not
assumed. Per-timeframe coverage contains `requested_start`, `requested_end`,
`declared_coverage_start`, `declared_coverage_end`, and nullable `dataset_end`.
Coverage is half-open and requested coverage includes warm-up through H. A
coverage assertion never supplies missing candles. The last supplied candle
never establishes dataset end, and candles beyond a declared endpoint reject.

Declarations support only boundaries at or after `available_at`. Availability
itself is asserted research provenance. Post-research-boundary declarations
reject. Missing candidate-to-M1 compatibility censors at the first required
completed M1 interval. E's relationship/structural evidence censors only when it
could change the next active stop; unbound M5 values cannot prove "no pivot."
An established gate survives later irrelevant gaps. Later declarations cannot
repair earlier consequential absence. All declarations are checked for conflict
before replay: higher revisions do not supersede contradictions. Exact duplicates
collapse; distinct consistent provenance remains significant.

Declaration authority is exactly false for `authenticated_source_truth`,
`trade_decision`, `financial_risk` and `execution`. Scenario/aggregate authority
is false for trade decision, financial risk and execution, with `execution=false`.

### Outcomes, shared paths and excursions

Completion statuses are RESOLVED, AMBIGUOUS, HORIZON_CENSORED,
MISSING_DATA_CENSORED and END_OF_DATA_UNRESOLVED. An internal hole differs from
reaching an explicitly declared dataset endpoint. Missing structural evidence is
consequential only when its unknown predicate could change the next stop. A known
neighbor that already disproves the strict predicate can make another missing
neighbor irrelevant. No structural dependency solely after H prevents horizon
censoring. Established terminals survive subsequent missing data; malformed
supplied data still rejects the entire request.

Mechanisms INITIAL_RISK_STOP, BREAK_EVEN_STOP, PROTECTED_PROFIT_STOP and
FINAL_TARGET are separate from economic sign; censored scenarios use NONE.
A BE opening mark can be negative R. Censoring creates no terminal mark, zero R,
or invented eventual bounds. Same-bar unresolved stop/target order retains
complete terminal alternatives with mark, exact R, occurrence kind, completion
boundary, supporting candle, ordering condition and excursion lower bounds.

Paired comparisons share the same candle evidence and nested adverse barriers.
Compatibility excludes target-before-nearer-stop paired with farther-stop-before-
target, and requires equal stop barriers to agree. This small first-touch ordering
calculation preserves shared paths without a generic path solver.

MAE/MFE start at zero. Completed nonterminal intervals contribute full extremes.
Terminal intervals contribute only their opening and branch-specific terminal
mark. Values are labelled CONSERVATIVE OBSERVED-PREFIX LOWER-BOUND EXCURSIONS;
branch ranges describe uncertainty in these lower bounds, not upper bounds on
actual full-path excursions. Censored scenarios retain their observed prefix.
Retained-MFE is not a primary metric.

### Cohorts, identities, metrics and leakage restrictions

Aggregate requests contain `contract`, `rule_version`, `cohort` (candidate
identities), `scenarios` (assessment/request pairs), and `partitions`. Every
candidate requires exactly one validated A–E scenario. All five share the same
candidate reconstruction, normalized M1 artifact and normalized base declaration
set. E alone may add M5 evidence/declarations. Missing, rejected, duplicate or
inconsistent members do not silently shrink the cohort.

Scenario identity hashes complete normalized assessment content, including
reconstruction input, source artifacts, declarations, frozen policy, exact terms,
transitions, coverage, reasons, alternatives and metrics. Accepted raw numeric
representations remain in provenance. Aggregate identity binds the complete
validated matrix, cohort, partitions, policy, counts and results. Unordered sets
normalize deterministically; candle chronology remains significant. Existing
snapshot IDs and declaration IDs alone are never trusted as full fingerprints.

Per-variant metrics report status counts, resolved coverage, resolved mechanism
counts, resolved-subset mean R and median, excursion summaries with denominators,
and full-cohort terminal mean bounds only when every member has terminal
alternatives. Paired results include compatible alternatives, exact delta bounds,
jointly assessable counts, and definite/possible/indeterminate/no mechanism and
economic loss avoidance. Economic loss avoidance requires A negative and the
comparison nonnegative on compatible paths. Censoring is not treated as avoidance.
Mean and expectancy are one field, not duplicate statistics.

Drawdown is a secondary DESCRIPTIVE RESOLVED-SCENARIO CLOSED-R DRAWDOWN. Resolved
increments sharing a terminal evidence-completion time are summed before the
cumulative update. Coverage is explicit. Overlapping scenarios are independent
references, not an executable shared-account equity curve.

Partitions are named, nonoverlapping half-open UTC entry intervals with optional
selection boundaries. Entry T assigns membership. Selection requires H <= B and
all validated evidence used by the assessment available by B. Later retrospective
outcomes remain descriptive and cannot enter earlier selection statistics. There
is no walk-forward/optimization machinery. Primary policy and 1440-minute horizon
remain frozen; secondary sensitivity analysis cannot redefine the primary result.

## Causal Account-Specific Risk Policy Evaluation v1

`xauusd_account_specific_risk_policy_evaluation.py` adds deterministic,
read-only, causal **pre-quantity policy evaluation** after facts and derived
financial measurements, before authorization/decision and execution. It does
not extend or mutate #23–#29, Strategy #1, candidate formulation, financial
measurement, reference experiments, Mission Control or execution.

Public functions are `evaluate_account_specific_risk_policy(request)` and
`validate_account_specific_risk_policy(assessment, request)`. The assessment
contract is `trading.xauusd_account_specific_risk_policy_evaluation.v1`, with
rule `xauusd_account_specific_risk_policy_evaluation_v1`.

### Inputs and reconstruction

The exact request contains `contract`, `rule_version`,
`assessment_economic_time`, `knowledge_boundary`, `operation_mode`,
`account_state`, `candidate`, `financial_measurement`, `account_rule_regime`,
`own_policy`, `timezone_evidence`, `actual_trade_evidence`, `trade_coverage`,
`financial_compatibility` and `provider_operands`.

The four upstream pairs contain respectively `snapshot`/`snapshot_input`,
`formulation`/`formulation_input`, `assessment`/`measurement_input` and
`assessment`/`assessment_input`. Public owner validators reconstruct every
artifact; detached IDs are insufficient. The measurement must reconstruct the
same candidate and original formulation input. One #24 snapshot binds the
account/source/environment, account currency and current measures. Candidate
direction determines ENTRY_LONG or ENTRY_SHORT; no separate caller action is
accepted. Operation mode is MANUAL or AUTOMATED.

Nested serialized evidence contracts belong only to this evaluator:

| Evidence | Contract | Rule |
| --- | --- | --- |
| Own policy | `trading.xauusd_account_specific_risk_policy_evaluation.policy.v1` | `own_account_risk_policy_v1` |
| Actual trade | `trading.account_actual_trade_outcome_evidence.v1` | `account_actual_trade_outcome_evidence_v1` |
| Coverage | `trading.account_actual_trade_outcome_coverage.v1` | `account_actual_trade_outcome_coverage_v1` |
| Reference compatibility | `trading.xauusd_account_specific_risk_policy_evaluation.reference_compatibility.v1` | `frozen_reference_account_compatibility_v1` |

These are bounded local evidence structures, not standalone ledger, accounting,
calendar, FX or risk services. Source provenance is retained and bound; this
capability does not authenticate external source assertions.

### Fixed own policy and temporal admissibility

`OWN_EQUITY_RISK_POLICY_V1` uses only #24
`observation.account_measures.equity` and `observation.account.currency`.
Target and maximum fractions are both exactly `0.01`; for admissible positive
equity E, both monetary budgets are E/100. Integer-rational arithmetic avoids
floating point and ambient Decimal precision. Financial results serialize as
canonical plain decimals, including zero. Nonpositive admissible equity fails;
missing or stale equity is UNKNOWN, with no balance/free-margin substitution.
The budget is not a claim of provider-safe headroom.

Own policy binds ID/revision, account, effective interval, availability,
provenance, equity admissibility and timezone artifact. EXACT_TIME requires
T_account = T_assessment. MAX_AGE requires an explicit nonnegative built-in
integer `maximum_age_microseconds`, excludes bool, and admits equality at the
limit. There is no default age. A policy outside its effective half-open
interval leaves own-policy gates UNKNOWN.

T_account <= T_assessment <= K. Account evidence and measurement knowledge
boundaries must be no later than K; #29 economic time and K must exactly match
the request. All admitted local evidence must be available by K. T1 and the
financial measurement's historical economic scope remain unchanged. K greater
than T_assessment means an as-known-at-K assessment of that economic instant,
not a reconstruction of knowledge available at T_assessment. A later decision
has a separate semantic role even if its timestamp equals T_assessment.

### Amsterdam day and actual trades

`OWN_POLICY_TRADING_DAY_EUROPE_AMSTERDAM_V1` uses the local civil date of
T_assessment, local midnight inclusive through next local midnight exclusive.
The policy binds Europe/Amsterdam, `tzdb_release` and exact `tzif_sha256`.
Request evidence supplies those fields plus strict `tzif_base64`, provenance
and availability. The evaluator verifies the digest and policy binding and
loads only those bytes with `ZoneInfo.from_file`. No host timezone fallback or
new dependency exists. Independently constructed consecutive local midnights
preserve 23-hour and 25-hour DST days. Tests embed a fixed Amsterdam TZif artifact
inside the authorized test module.

Actual close time assigns each completed episode to the day. Relevant closes
satisfy day_start <= close <= T_assessment, with the day end exclusive. The
`SINGLE_ENTRY_SINGLE_TERMINAL_EXIT_TRADE_UNIT_V1` supports one logical entry and
one complete terminal exit, with no scale-in, partial exit or mixed exit.
Explicit structured source evidence binds group identity, role, interpretation
and execution membership; multiple fills can constitute a single logical group.
No grouping is inferred from price, symbol or proximity. Underlying execution
reuse across independent episodes or roles rejects. Unsupported scale-in,
partial/mixed exits, netting and reversals remain visible unresolved population.

Terminal attribution separately binds the complete terminal group, original
protective instruction revision/content, and supporting causal interpretation.
INITIAL_PROTECTIVE_STOP differs from BREAK_EVEN_STOP, PROTECTED_PROFIT_STOP,
AMENDED_STOP, TARGET, MANUAL and OTHER. UNRESOLVED cannot assert a causal proof.
Price equality or negative economics cannot establish original-stop causation;
a gap execution can qualify through the same explicit causal evidence.

`ACTUAL_REALIZED_NET_PNL_FINAL_V1` binds the episode, terminal group,
interpretation/version, status, amount/currency, provenance and availability.
FINAL_COMPLETE requires source evidence that all required economic components
are incorporated and cannot predate the close. PROVISIONAL and UNAVAILABLE
remain distinct; provisional negative results do not establish qualifying losses.
No broker accounting or commissions ledger is reconstructed here.

### Corrections, coverage and daily threshold

`AS_KNOWN_AT_K_REASSESSABLE_DAILY_GATE_V1` validates every supplied revision
before selecting a unique effective successor. Corrections bind both predecessor
identity and complete predecessor content. Exact duplicates collapse; conflicting
revision identities, missing/cross-trade predecessors, branches, cycles,
backwards availability and post-K evidence reject. Arrival order or a larger
revision number cannot supersede evidence. Later correction can change mechanism,
net economics or close/day assignment without rewriting an earlier assessment.
There is no persistent daily latch.

Coverage binds account/source, ID/revision, availability, trade-unit model, exact
own-policy day, requested and covered close intervals with explicit endpoint
inclusion, inventory completeness, effective population references, unresolved
population and correction cutoff. Adequate coverage includes closes exactly at
T_assessment and establishes correction completeness through K. Complete
inventory must include all supplied relevant effective members, including
unsupported structures; supported-subset completeness is not account-wide
completeness. Inventory completeness does not imply classification completeness.
An empty list without adequate coverage proves nothing.

`OWN_DAILY_INITIAL_RISK_STOP_LOSS_GATE_V1` classifies each effective episode as
qualifying, nonqualifying or potentially qualifying. Only a supported completed
original initial-stop episode with FINAL_COMPLETE negative net economics counts.
Other mechanisms do not count merely because they lose money. Wins never reset
prior qualifying losses. At least two established qualifying losses fail the
gate. Adequate coverage with a possible qualifying upper bound below two
satisfies it; otherwise it is UNKNOWN. Incomplete account coverage or unsupported
inseparable population yields an explicit unbounded upper bound. Two established
losses remain decisive while every other gate and all supplied material are
still validated and reported.

### Frozen-reference compatibility and provider policy

Compatibility assertions bind complete reconstructed account, candidate,
measurement and selected specification content, quantity unit, both currencies,
T_assessment/K, intended use, source, revision and availability. The only supported
use is `PRE_QUANTITY_FROZEN_REFERENCE_RISK_CALCULATION`, in the same currency.
Missing assertions, unsupported measurement or currency conversion needs are
UNKNOWN. Wrong subjects or contradictory supplied assertions reject. This does
not establish current executable prices, spread, slippage, instrument economics,
guaranteed loss or execution permission.

Provider policy is separate from own policy. The selected approved #29 regime
and complete rule coverage are required. Local tagged operands bind exact rule
content, account/context, source, availability, effective interval and structured
support. Tags are MEASURE_BINDING, INITIAL_REFERENCE, RESET_ANCHOR,
COST_ADJUSTMENTS, ACCOUNT_FACT, POSITION_COUNT_CONTEXT and INSTRUMENT_BINDING.
Conflicting values for a required role reject; no precedence resolver or implicit
zero costs exist. Exact instrument scope requires a candidate/provider instrument
binding. Unknown rule effects and relevant unsupported mandatory rules remain
UNKNOWN; later lifetime rules remain obligations.

| #29 type | Pre-quantity handling |
| --- | --- |
| INSTRUMENT_ACTION_PERMISSION | Candidate-derived action and established instrument scope; explicit prohibition fails. |
| AUTOMATION_PERMISSION | Match explicit operation mode; applicable prohibition fails. |
| ACTION_WINDOW | Preserve #29 half-open schedules and permitted-only/prohibited intervals; absent schedule coverage is UNKNOWN. |
| ACCOUNT_STATE_REQUIREMENT | Bound required facts; false fails, missing/unresolved is UNKNOWN. |
| STATIC_FLOOR | Bound current measure, exact absolute/initial-reference threshold, required costs and original strict/non-strict comparator. |
| DAILY_RESET_FLOOR | As above plus exact provider reset interval/anchor and deduction; never substitute the own-policy Amsterdam day. |
| CONCURRENT_POSITION_COUNT | Complete bound inventory and commitments plus established count effect; exact instrument scope filters positions only in a compatible source namespace. |
| PER_POSITION_QUANTITY | Retain exact rule as downstream quantity obligation; final compliance is not evaluated. |
| UNSUPPORTED | Relevant mandatory pre-quantity rule is UNKNOWN. |

Missing non-quantity operands cannot become quantity-dependent obligations.
Known current floor comparisons do not establish post-entry headroom; post-entry
floor compliance remains an obligation. Quantity-dependent count effects defer
only after inventory and commitments are established.

### Results, identity and authority boundary

Results retain account/candidate identity, T/K, complete reconstruction evidence,
derived day, effective trade references, equity/daily gates and monetary budgets,
compatibility, regime/rule results, reasons, supporting references and outstanding
obligations. Gates use exactly SATISFIED, NOT_SATISFIED or UNKNOWN. Malformed,
contradictory and causally inadmissible input instead raises ValueError. All
supplied material is validated before policy evaluation; a conclusive failure
cannot hide malformed material or unrelated unknown gates.

Any conclusive applicable pre-quantity failure makes the overall result
NOT_SATISFIED; otherwise any unresolved required gate makes it UNKNOWN;
otherwise it is SATISFIED. Both failure and uncertainty block progression.
SATISFIED is not authorization. Current candidate validity, current executable
risk/instrument suitability, risk-constrained quantity selection and Mission
Control authorization remain explicit downstream obligations.

Assessment identity hashes complete canonical normalized content, excluding only
its own identity field. Object keys are sorted, JSON is compact and finite,
timestamps are UTC with six fractional digits, local set-like evidence has
stable semantic ordering, and explicit predecessor links preserve correction
relationships. Existing owner reconstruction inputs remain complete provenance.
The detached validator re-evaluates the original request and compares the whole
canonical assessment, never merely its supplied fingerprint.

Authority is exactly false for `trade_decision`, `financial_risk`, and `execution`;
`execution` is also false at the assessment level. No BUY/SELL authorization,
quantity selection, reservation, order placement, research-scenario substitution
for actual trades, generic ledger/FX service or runtime integration is introduced.

## Current Entry Position-Effect Basis v1

`xauusd_current_entry_position_effect_basis.py` establishes a conditional terminal
position mapping, without choosing an order quantity. Given independently
admitted account-wide flatness and absence of outstanding position-affecting
commitments at T=K, explicitly admitted current mechanics map an accepted,
fully filled entry of aggregate quantity q to exactly one terminal position of
quantity q in the same unit and direction. Initial count is 0, terminal count is
1 and terminal count delta is 1. All fills must aggregate into that one position.
Unrelated intervening state changes are excluded by an explicit condition; their
future absence is not established. Peak intermediate count is not evaluated.

Only finite inclusive quantity intervals `0 < minimum <= q <= maximum` are
supported, including singleton intervals. This interval describes support for
the conditional mapping, not entry-order acceptance, grid membership, provider
compliance, margin/capital feasibility, risk eligibility or execution authority.
Both LONG and SHORT and evidenced NETTING/HEDGING modes are supported separately.
A mode label, empty list or successful hash comparison alone proves none of the
required mechanics, coverage or source relationships.

### Constants and public APIs

| Name | Exact value |
| --- | --- |
| Request/assessment contract | `trading.xauusd_current_entry_position_effect_basis.v1` |
| Request/assessment rule | `xauusd_current_entry_position_effect_basis_v1` |
| Inventory contract | `trading.xauusd_current_entry_position_effect_basis.inventory.v1` |
| Inventory rule | `xauusd_current_entry_position_effect_basis_inventory_v1` |
| Admission contract | `trading.xauusd_current_entry_position_effect_basis.admission.v1` |
| Admission rule | `xauusd_current_entry_position_effect_basis_admission_v1` |
| Purpose | `POSITION_EFFECT_FACT_ADMISSION_ONLY` |
| Entry mechanism | `IMMEDIATE_MARKET_ENTRY_SCENARIO_V1` |
| Supported model | `ONE_NEW_SEPARATE_POSITION` |
| Supported aggregation | `ALL_ENTRY_FILLS_TO_ONE_POSITION` |
| Position population | `ALL_ACCOUNT_POSITIONS` |
| Commitment population | `ALL_ACCOUNT_POSITION_AFFECTING_COMMITMENTS` |
| Complete actor coverage | `ALL_ACCOUNT_ACTORS` |
| Source authentication | `NOT_VERIFIED_BY_THIS_CAPABILITY` |
| Identity prefix | `current_entry_position_effect_basis_` |

```python
evaluate_current_entry_position_effect_basis(
    request: dict, *, trusted_position_effect_context=None,
) -> dict

validate_current_entry_position_effect_basis(
    assessment: dict, request: dict, *, trusted_position_effect_context=None,
) -> dict
```

Neither function reads a clock, fetches evidence, authenticates its caller,
reserves capacity or invokes Mission Control. The existing public
`validate_causal_financial_account_state_snapshot` reconstructs the complete
native account pair. No strategy, #29, risk-budget or quantity-grid dependency
is introduced. Those owners remain separate responsibilities of later consumers.

### Closed schemas and primitive types

Every displayed object has exactly its listed required keys. Unknown keys and
omitted keys reject; `?` below permits a null value without permitting omission.
Arrays are serialized lists and may be empty unless a positive-proof condition
requires content. Objects are serialized dictionaries. Integer types exclude
booleans; booleans must be exact booleans. Reject cycles, non-string keys,
nonfinite numbers, non-JSON values and strings that cannot encode as UTF-8.
Finite native JSON numbers retain their native presentation; no local quantity
is represented as a binary floating-point number.

`Text` is a string with at least one non-whitespace character, retained exactly.
No trimming, aliases or case/symbol normalization occur. `Hash` is 64 lowercase
hexadecimal characters. `Completeness` is COMPLETE/LIMITED/UNKNOWN. Environment
is DEMO/LIVE; currency is three uppercase ASCII letters. Mode is
NETTING/HEDGING/UNKNOWN. Local timestamps and decimals are defined below. Native
account structures keep their original owner's schema and representation.

```text
Namespace = {source_id: Text, source_contract: Text, source_contract_version: Text}
Source = {source_id: Text, source_contract: Text, source_contract_version: Text,
          source_snapshot_id: Text}
EvidenceRef = {evidence_id: Text, content_sha256: Hash}
RecordRef = {record_id: Text, content_sha256: Hash}
Evidence = {evidence_id: Text, source: Source, media_type: Text,
            content_base64: string, source_available_at: Timestamp?,
            observed_at: Timestamp}

Request = {contract, rule_version, assessment_economic_time: Timestamp,
           knowledge_boundary: Timestamp, scope: Scope,
           account_state: AccountPair?, effect_inventory: Inventory?}
AccountPair = {snapshot: object, snapshot_input: object}

Scope = {account: AccountIdentity, provider_namespace: Namespace,
         provider_id: Text, venue_id: Text, instrument: InstrumentIdentity,
         entry_direction: LONG|SHORT,
         entry_mechanism: IMMEDIATE_MARKET_ENTRY_SCENARIO_V1,
         quantity_unit: Text}
AccountIdentity = {source_id: Text, source_contract: Text,
                   source_contract_version: Text, account_id: Text,
                   environment: DEMO|LIVE, currency: Currency}
InstrumentIdentity = {source_id: Text, source_contract: Text,
                      source_contract_version: Text, environment: DEMO|LIVE,
                      instrument_id: Text}
```

Request contract/rule equal the constants above. Provider/venue IDs are qualified
by provider_namespace. Original evidence must be nonempty bytes encoded in exact
standard padded base64: decoding and re-encoding must produce the identical
string. Whitespace and alternate encodings reject. Evidence source identity is
provenance, not authentication; arbitrary provider documents are not parsed to
invent fact interpretations.

```text
Inventory = {contract, rule_version, source: Source, scope: Scope,
             source_available_at: Timestamp?, observed_at: Timestamp,
             evidence: [Evidence], coverage: Coverage, records: [Record]}
Coverage = {economic_from: Timestamp, economic_until: Timestamp?,
            source_information_cutoff: Timestamp?,
            declaration_completeness: Completeness,
            revision_completeness: Completeness,
            starting_basis: FROM_INCEPTION|INCOMPLETE_OR_UNKNOWN,
            root_records: [RecordRef], missing_record_ids: [Text],
            records_omitted: boolean?, history_truncated: boolean?,
            source_available_at: Timestamp?, observed_at: Timestamp,
            evidence_refs: [EvidenceRef]}

Declare = {record_id: Text, kind: DECLARE, predecessor: Predecessor,
           effective_from: Timestamp, effective_until: Timestamp?,
           source_available_at: Timestamp?, observed_at: Timestamp,
           evidence_refs: [EvidenceRef], body: DeclarationBody}
Withdraw = {record_id: Text, kind: WITHDRAW, predecessor: Predecessor,
            effective_from: Timestamp, source_available_at: Timestamp?,
            observed_at: Timestamp, evidence_refs: [EvidenceRef]}
Predecessor = {kind: ROOT}
            | {kind: UNKNOWN}
            | {kind: RECORD, record: RecordRef}
```

Inventory contract/rule equal their constants. Inventory scope equals request
scope. Withdrawal has neither body nor effective_until; a root withdrawal
rejects. Null interval ends explicitly mean open-ended; null source availability,
cutoffs and omission flags mean unresolved. A declaration replaces the whole
local basis declaration; it does not merge selected fields or resolve unrelated
source precedence.

```text
DeclarationBody = {account_bundle_sha256: Hash, positions: PositionDeclaration,
                   bindings: Bindings, mechanics: Mechanics,
                   commitments: Commitments}
PositionDeclaration = {state_at: Timestamp, source_information_cutoff: Timestamp?,
                       inventory_completeness: Completeness,
                       revision_completeness: Completeness,
                       population_scope: ALL_ACCOUNT_POSITIONS,
                       evidence_refs: [EvidenceRef]}
Bindings = {account_provider_venue: BindingClaim,
            instrument_namespace: BindingClaim,
            quantity_denomination: BindingClaim,
            direction_and_mechanism: BindingClaim}
BindingClaim = {status: COMPATIBLE|INCOMPATIBLE|UNKNOWN,
                evidence_refs: [EvidenceRef]}
Mechanics = {position_mode: NETTING|HEDGING|UNKNOWN,
             model: ONE_NEW_SEPARATE_POSITION|OTHER|UNKNOWN,
             fill_aggregation: ALL_ENTRY_FILLS_TO_ONE_POSITION|OTHER|UNKNOWN,
             quantity_range: QuantityRange?,
             source_information_cutoff: Timestamp?,
             revision_completeness: Completeness, evidence_refs: [EvidenceRef]}
QuantityRange = {minimum: Decimal, maximum: Decimal}
```

The account bundle hash covers the entire original native pair. Historical
hashes identify historical subjects, whose facts cannot substitute for current
account facts. A supplied range must be finite, positive and ordered, or reject.
A null range is unestablished. There is no unbounded-range representation.
OTHER explicitly represents unsupported semantics, preserved in original bytes.
Bindings address the full scoped relationships, without alternate identities
or conversion instructions.

```text
Commitments = {state_at: Timestamp, source_information_cutoff: Timestamp?,
               population_scope: ALL_ACCOUNT_POSITION_AFFECTING_COMMITMENTS,
               source_universe_completeness: Completeness,
               actor_coverage: ALL_ACCOUNT_ACTORS|UNKNOWN,
               inventory_roster: [RosterMember], reports: [CommitmentReport],
               evidence_refs: [EvidenceRef]}
RosterMember = {inventory_id: Text, source_namespace: Namespace,
                source_account_id: Text,
                role: PROVIDER|SUBMISSION_CHANNEL|RESERVATION_OR_ALLOCATION
                      |OTHER_POSITION_EFFECT_SOURCE,
                binding_evidence_refs: [EvidenceRef]}
CommitmentReport = {inventory_id: Text, source: Source, state_at: Timestamp,
                    source_information_cutoff: Timestamp?,
                    inventory_completeness: Completeness,
                    revision_completeness: Completeness,
                    source_available_at: Timestamp?, observed_at: Timestamp,
                    categories: Categories, evidence_refs: [EvidenceRef]}
CategoryFinding = {status: EMPTY|NONEMPTY|UNKNOWN, evidence_refs: [EvidenceRef]}
```

Categories has exactly seven keys, each a CategoryFinding:
PENDING_SUBMISSIONS, ACCEPTED_UNFILLED_ORDERS, PARTIALLY_FILLED_ORDERS,
CANCELLATIONS_AWAITING_CONFIRMATION, POSITION_RESERVATIONS,
POSITION_ALLOCATIONS and OTHER_PROVIDER_OR_ACCOUNT_PENDING_EFFECTS.

### Commitment population and identity joins

The closure population includes outstanding effects at T that can change the
exact account's positions or allocations, across all instruments and actors:
manual, automated, local, remote and provider-originated activity as relevant.
The hypothetical entry is not an already-submitted order. Positive closure
requires all source-universe and actor coverage independently admitted, a
nonempty roster with at least one PROVIDER member, exactly one current report per
member, complete inventory/revision coverage and supported EMPTY findings for
every category in every report. Source limitations can establish emptiness only
through independently admitted evidence; absent fields are insufficient.

Empty roster/no provider, missing listed reports, limited/unknown coverage,
NONEMPTY or UNKNOWN categories and unsupported empty claims yield UNKNOWN.
Duplicate roster/report identities, unlisted reports and report/roster namespace
contradictions reject. Complete population coverage with unknown classification
is valid unresolved input. A cancellation request remains outstanding until
terminal confirmation. Empty provider orders cannot exclude unacknowledged
local submissions. Roster completeness is independently proven, not inferred
from checking all supplied reports. No quantity aggregation or cross-source
deduplication is required to prove a union empty.

Direct equalities reject on contradiction: request account namespace/ID/
environment/currency versus reconstructed native account; instrument versus
account environment; inventory versus request scope; native evaluation boundary
versus K; uniquely identified current declaration account hash versus current
native pair; declared position state_at versus native effective_at; report
namespace versus roster namespace. A COMPLETE local position-inventory claim
cannot accompany native PARTIAL/UNAVAILABLE positions. Known native and selected
mechanics modes must agree. Missing native evidence yields UNKNOWN, not a
fabricated equality failure. The syntactic current candidate for joins is the
last effective record of one connected fully supplied chain; competing or
incomplete chains do not permit choosing a record for these joins.

Positive native state requires effective_at=T, complete empty positions, known
mode and known source availability. Older native effective time is UNKNOWN;
different native evaluation boundary rejects. No financial measure is derived or
used as a risk gate in this capability.

Independent bindings establish account-to-provider/venue association, instrument
identity/applicability, identity quantity denomination, direction/mechanism
semantics and each roster source-account relationship. There are no implicit
account aliases, symbol mappings, currency or lot conversions. The schema has no
alternate unit field or conversion expression; evidence bytes are not parsed to
invent one. Later consumers must independently reconstruct their relevant owners
and check this exact scope and quantity-range membership.

### Causality and whole-declaration revisions

Local timestamps require calendar-valid YYYY-MM-DDTHH:MM:SS[.fraction](Z|+/-HH:MM),
one to six fractional digits if present, explicit timezone, offset hour 00-23 and
minute 00-59. Leap seconds reject. Normalize to UTC with six fractional digits;
never round excess precision. Require T=K. Every observation is <=K and known
source availability is <=observation. Inventory observation contains coverage,
records, evidence and nested reports; declaration observation contains its
reports. State assertions cannot postdate their containing observation or known
publication. Cited evidence observation cannot postdate its assertion. Body
claims inherit declaration observation; categories inherit report observation.
Known information cutoffs cannot exceed K, observation or known publication.
Future effective information known by K is allowed; post-K observations are not.

Positive current proof requires inventory economic coverage containing T; cutoff
K for inventory coverage and selected positions, mechanics, commitment closure
and reports; state_at=T for positions, commitments and reports; current
declaration and admission intervals containing T. Intervals are half-open.
Earlier/null cutoff is UNKNOWN; future cutoff rejects. The exact-T native timing
constraints force account observation and its admission to fit the same boundary.
No freshness tolerance, delayed-observation continuity model, lookahead or
backdating is introduced. New K requires reconstruction with current evidence.

Record IDs are unique; fingerprints cover complete normalized records, including
predecessors and evidence references. Every supplied root appears in coverage;
root references identify roots. Missing references must be explicitly listed as
missing IDs. Missing-and-supplied IDs, wrong hashes, unexplained dangling
references, self-reference, cycles and duplicate references reject. COMPLETE
revision coverage requires FROM_INCEPTION, no missing IDs/UNKNOWN predecessors,
and both omission flags false; contradictions reject. LIMITED/UNKNOWN coverage
need not enumerate every missing fact and stays unresolved.

Successor effective/observation times and known publication times must be
nondecreasing; backward ordering is UNKNOWN with REVISION_ORDER_UNSUPPORTED.
Usable history needs complete declaration/revision coverage, one supplied root,
one connected chain covering all records, no gaps and supported ordering.
Multiple roots/branches, disconnected/incomplete history and absence of a current
declaration remain UNKNOWN. Otherwise select the last chain record effective by
T. A withdrawal or expired successor remains UNKNOWN without predecessor revival.
A future-effective successor does not replace the current declaration early;
a later effective declaration can replace a withdrawal. Local history alone
never proves complete underlying provider revisions without host admission.

Inactive/historical body facts are structurally validated but are not evaluated
for current flatness, emptiness or supported range. Their record envelopes and
lineage support remain required. Each DECLARE remains a full replacement.

### Independently supplied host admission

```text
TrustedContext = {contract, rule_version, admission_id: Text, authority_id: Text,
                  mandate_id: Text, mandate_revision: positive integer,
                  purpose: POSITION_EFFECT_FACT_ADMISSION_ONLY,
                  request_content_sha256: Hash, knowledge_boundary: Timestamp,
                  effective_from: Timestamp, effective_until: Timestamp?,
                  admitted_at: Timestamp, available_at: Timestamp,
                  assurances: Assurances}
Assurance = {status: ADMITTED|UNRESOLVED, evidence_refs: [EvidenceRef]}
```

Contract/rule equal the admission constants. Assurances has exactly six keys:

| Assurance | Independently admitted proposition |
| --- | --- |
| source_authority | Authority and scope of each relevant supplier |
| original_positions_and_commitments | Original support for the bound account state and reports |
| coverage_and_common_state | Complete source/actor universe and coherent common T/K state |
| mechanics_and_revisions | Mechanics/interpretation and current underlying revision coverage |
| identity_and_quantity_semantics | Full identity joins and identity quantity mapping |
| causal_availability | Evidence and admission genuinely available by K |

References resolve against inventory evidence. Context K equals request K;
request pin hashes complete normalized request with native pair preserved.
Require inventory observation <=admission<=context availability<=K, admission no
earlier than supplied native observation, and nonempty support with known source
availability for every ADMITTED assurance. All references, even UNRESOLVED ones,
resolve with correct digests and observations no later than admission. Non-null
context with null inventory rejects. Wrong contract/purpose/pin/timing rejects.
Absent context, inactive context or any unresolved assurance yields UNKNOWN.
Admission cannot override native incompleteness, missing reports, outstanding
commitments or unsupported mechanics.

The trusted host must actually control context supply and independently verify
originals, authority, coverage, semantics, bindings and causality. Hashes/issuer
strings cannot authenticate their own supplier. A caller controlling both request
and trusted argument can fabricate both; this pure library does not detect that
trust-boundary failure. Provider authentication, live ingestion and production
admission integration remain external and unestablished.

### Outcomes, reasons and precise diagnostics

Outcomes are exactly ESTABLISHED and UNKNOWN. Structural violations raise
ValueError before semantic results. Non-flat state, outstanding commitments and
unsupported transitions never become NOT_SUITABLE or a trading prohibition.
Validate every supplied object, including inactive records/context, reconstruct
the native owner, check references/joins/causality, resolve history, then evaluate
all independent current proof requirements. Collect independent findings without
manufacturing descendants of absent parents or an unidentified current record.

Findings are exactly `{reason_code, subject}`. Subject is an RFC 6901 JSON Pointer
into `{request: normalized_request, trusted_position_effect_context:
normalized_context_or_null}`, identifying an existing value. Missing reports point
to their roster member; missing owner/context points to its null value. Deduplicate
identical findings; retain all distinct reasons and subjects.

| Closed reason | Trigger |
| --- | --- |
| MISSING_ACCOUNT_STATE | Null account pair |
| MISSING_EFFECT_INVENTORY | Null inventory |
| MISSING_HOST_ADMISSION | Null trusted context |
| ADMISSION_NOT_CURRENT | Valid context interval excludes T |
| ASSURANCE_UNRESOLVED | An assurance is UNRESOLVED |
| SOURCE_AVAILABILITY_UNKNOWN | Required proof envelope/support has null source availability |
| SUPPORTING_EVIDENCE_MISSING | Required support array is empty |
| COVERAGE_INCOMPLETE | Inventory declaration completeness not COMPLETE |
| COVERAGE_NOT_CURRENT | Inventory economic interval excludes T, applicable cutoff not K, or selected state time not T |
| REVISION_HISTORY_INCOMPLETE | Inventory revision coverage/inception/gaps/connectivity unresolved, or selected position/mechanics revision coverage not COMPLETE |
| REVISION_ORDER_UNSUPPORTED | Backward successor effective/observation/known publication ordering |
| COMPETING_REVISION_CHAINS | Multiple roots or branching successor relationships |
| NO_CURRENT_DECLARATION | Resolvable chain has no effective record, or complete empty history has none |
| CURRENT_DECLARATION_WITHDRAWN | Selected current record is WITHDRAW |
| CURRENT_DECLARATION_EXPIRED | Selected declaration end <=T |
| ACCOUNT_STATE_NOT_CURRENT | Native effective_at<T |
| POSITION_INVENTORY_INCOMPLETE | Native completeness or selected position-inventory completeness not COMPLETE |
| ACCOUNT_NOT_FLAT | Native position rows present |
| ACCOUNT_MODE_UNRESOLVED | Native or selected mechanics mode UNKNOWN |
| BINDING_UNRESOLVED | Selected binding UNKNOWN |
| BINDING_INCOMPATIBLE | Selected binding INCOMPATIBLE |
| MECHANICS_UNSUPPORTED_OR_UNKNOWN | Selected model/aggregation differs from supported literals |
| QUANTITY_RANGE_UNESTABLISHED | Selected range null |
| COMMITMENT_REPORT_MISSING | Selected roster member lacks report |
| COMMITMENT_COVERAGE_INCOMPLETE | Empty roster/no provider, incomplete source universe/actor coverage, or report inventory/revision coverage not COMPLETE |
| COMMITMENT_PRESENT | Selected category NONEMPTY |
| COMMITMENT_STATUS_UNKNOWN | Selected category UNKNOWN |
| POSITION_EFFECT_BASIS_ESTABLISHED | Every positive requirement holds with no findings |

Applicable cutoffs are inventory coverage and selected positions, mechanics,
commitments and reports. Required support arrays are coverage, every record's
own lineage support, and every reference array in the selected current body.
Required availability includes inventory, coverage, record envelopes, selected
reports, native account source and evidence cited by required arrays. Unreferenced
catalog evidence is structurally checked and preserved but is not mandatory
proof. Historical body support is not current proof; record support still is.
Reason subjects identify the corresponding failing fields/nodes. UNKNOWN reasons
are the unique sorted finding codes; ESTABLISHED has no findings and only its
success reason. Any finding prevents the symbolic basis from being returned.

### Exact output, authority and downstream obligations

Output has exactly `contract`, `rule_version`, `assessment_economic_time`,
`knowledge_boundary`, `scope`, `outcome`, `reason_codes`, `resolved_record`,
`effect_basis`, `unresolved_findings`, `reconstruction_evidence`,
`downstream_obligations`, `source_authentication`, `authority`, `execution` and
`assessment_identity`. Times/scope are normalized request values. resolved_record
is null or RecordRef, populated only with established history/coverage support
and all current admission requirements; it may identify withdrawal/expiry without
establishing a mapping and does not require flatness or empty commitments.

effect_basis is null for UNKNOWN. For ESTABLISHED it is exactly:

```text
{model: ONE_NEW_SEPARATE_POSITION,
 position_mode: NETTING|HEDGING,
 quantity_unit: scoped unit,
 quantity_range: {minimum: canonical positive decimal,
                  maximum: canonical positive decimal},
 resulting_direction: LONG|SHORT,
 resulting_position_quantity: {kind: IDENTITY_OF_ENTRY_QUANTITY},
 initial_position_count: 0, terminal_position_count: 1,
 terminal_position_count_delta: 1,
 conditions: [ACCEPTED_ENTRY_FULLY_FILLED,
              ALL_ENTRY_FILLS_AGGREGATED_UNDER_ADMITTED_MECHANICS,
              NO_UNRELATED_INTERVENING_STATE_CHANGE,
              ADMITTED_MECHANICS_REMAIN_APPLICABLE]}
```

Conditions use exactly that order. They are explicit assumptions of the terminal
mapping, not proven future events. No selected numeric q is returned. A consumer
must enforce inclusive range membership; arbitrary caller misuse cannot be
prevented by serialization. Admission is not order acceptance or fill feasibility.

Authority has exactly quantity_selection, budget_approval,
position_effect_compliance, margin_capital_approval, trade_decision,
financial_risk and execution, all false. Top-level execution is false. Fixed,
sorted downstream obligations are ATOMIC_COMMITMENT_AND_RESERVATION_CONTROL,
CANDIDATE_VALIDITY, CURRENT_STATE_AND_MECHANICS_REVALIDATION,
ENTRY_QUANTITY_DOMAIN_MEMBERSHIP, MARGIN_AND_AVAILABLE_CAPITAL_FEASIBILITY,
MARKET_ORDER_AND_FILL_FEASIBILITY, MISSION_CONTROL_CURRENT_AUTHORIZATION,
POSITION_EFFECT_AND_ACCOUNT_RULE_COMPLIANCE, POST_ENTRY_FLOOR_AND_PROVIDER_HEADROOM,
QUANTITY_SELECTION_POLICY_AND_SELECTION and RISK_BUDGET_QUANTITY_FEASIBILITY.
Mission Control retains final current authorization and atomic commitment
responsibilities; no broker, registry, runtime or existing-owner behavior changes.

### Canonical identity and detached reconstruction

Canonical J is compact sorted-key JSON, ensure_ascii=False, allow_nan=False,
encoded UTF-8. H is lowercase SHA-256 of J. Integers render exactly without an
interpreter-wide digit-limit change. Local decimal grammar is
`-?(0|[1-9][0-9]*)(\.[0-9]+)?`: reject exponents, plus, whitespace, commas,
nonfinite values and invalid leading zeros. Strip trailing fractional zeros and
an unnecessary point, map signed zero to "0", then enforce range positivity.
Use arbitrary-precision exact coefficients/scales or rationals without floating
point, Decimal context dependence or Python decimal-string digit-limit dependence.

Evidence sorts by evidence_id; records/root references by record_id; evidence
references by evidence_id then digest; missing IDs lexicographically; roster and
reports by inventory_id; findings by complete canonical JSON; reasons/obligations
lexicographically. Record chronology comes solely from lineage. Input identity
and reference arrays reject duplicates including exact duplicates. Derived
findings/reasons deduplicate. Native pair arrays and spellings remain untouched,
so equivalent local presentations share identity while valid different native
presentations may retain different provenance identities.

Evidence references hash complete normalized Evidence, not only raw bytes.
Record references hash complete normalized Record. Account hash covers the
original preserved AccountPair. Admission pins complete normalized Request.
Reconstruction is exactly `{request: normalized_request,
trusted_position_effect_context_sha256: H(normalized_context) or null}`.
Assessment identity is the fixed prefix plus H(complete output excluding only
assessment_identity). The validator accepts a serialized object, independently
re-evaluates originals/context, compares every serialized output field without
normalizing the supplied assessment into acceptance, and returns a detached copy.
Caller-recomputed identities cannot bypass replay. No returned object shares
mutable state with inputs, contexts or other returned assessments.

Acceptance tests use genuine account-owner construction/validation, mirrored
directions and modes, exact/singleton/extreme ranges, all seven commitment
categories, source/actor closure, missing/partial/stale states, unsupported
mechanics, direct identity contradictions, explicit missing/competing revision
histories, withdrawal/expiry/future successors, temporal violations, forged pins,
original-byte and complete output tampering, canonical ordering, mutation
isolation and fixed false authority. Synthetic external evidence and admissions
test contract semantics only; no production provider truth/authentication is
claimed. Correctly shaped attacker-controlled trusted arguments require external
host-boundary controls rather than an invented unit-test authentication guarantee.

## Current Terminal Position-Limit Assessment v1

`xauusd_current_terminal_position_limits.py` establishes a conditional terminal
quantity/count predicate over the independently established finite positive
position-effect interval P. It consumes original owner pairs and host-admitted
original rule material. It neither consumes risk-feasible set F nor intersects a
quantity grid or selects q. An established interval does not establish an
executable order, continuous compliance, margin/capital feasibility or trading
authorization.

### Constants and public APIs

```text
CONTRACT = trading.xauusd_current_terminal_position_limits.v1
RULE_VERSION = xauusd_current_terminal_position_limits_v1
ADMISSION_CONTRACT = trading.xauusd_current_terminal_position_limits.admission.v1
ADMISSION_RULE = xauusd_current_terminal_position_limits_admission_v1
PURPOSE = TERMINAL_POSITION_LIMIT_FACT_ADMISSION_ONLY
MECHANISM = IMMEDIATE_MARKET_ENTRY_SCENARIO_V1
SOURCE_AUTHENTICATION = NOT_VERIFIED_BY_THIS_CAPABILITY
IDENTITY_PREFIX = current_terminal_position_limits_
PREDICATE_KIND = TERMINAL_UPPER_BOUND_CONJUNCTION
```

```python
evaluate_current_terminal_position_limits(
    request: dict, *, trusted_position_effect_context=None,
    trusted_position_limit_context=None,
) -> dict
validate_current_terminal_position_limits(
    assessment: dict, request: dict, *, trusted_position_effect_context=None,
    trusted_position_limit_context=None,
) -> dict
```

### Closed types and request

All listed keys are required and extra keys reject. Null is permitted only where
explicit. Text is UTF-8-encodable, nonempty after a whitespace check, with original
spelling preserved. Hash is 64 lowercase hexadecimal characters. Count is a
built-in integer >= 0 and PositiveInt is >= 1; bool never substitutes for int.
Completeness is COMPLETE, LIMITED or UNKNOWN. Objects must be serialized JSON
trees; cycles, non-string keys, custom objects and floating-point fields reject.

Local Time accepts calendar-valid `YYYY-MM-DDTHH:MM:SS[.fraction](Z|+HH:MM|-HH:MM)`
with 1..6 fractional digits when present, no leap seconds, offset hours <= 23 and
minutes <= 59. Normalize to UTC with six fractional digits and Z; UTC conversion
outside years 0001..9999 rejects. Decimal grammar is
`-?(0|[1-9][0-9]*)(\.[0-9]+)?`; strip trailing fractional zeros and an unnecessary
point, normalize signed zero to "0", and enforce positivity where declared.
No exponent, plus sign, whitespace, nonfinite value or leading-zero variant is
accepted. Native pair representations remain owned by their existing validators.

```text
Request = {contract, rule_version, assessment_economic_time: Time,
 knowledge_boundary: Time, scope: Scope, position_effect: PositionEffectPair|null,
 account_rule_regime: RegimePair|null, rule_support: RuleSupport|null}
PositionEffectPair = {assessment: native object, request: native object}
RegimePair = {assessment: native object, assessment_input: native object}
Namespace = {source_id: Text, source_contract: Text, source_contract_version: Text}
Source = Namespace + {source_snapshot_id: Text}
Account = Namespace + {account_id: Text, environment: DEMO|LIVE, currency: [A-Z]{3}}
Instrument = Namespace + {environment: DEMO|LIVE, instrument_id: Text}
Scope = {account: Account, provider_namespace: Namespace, provider_id: Text,
 venue_id: Text, instrument: Instrument, entry_direction: LONG|SHORT,
 entry_mechanism: MECHANISM, quantity_unit: Text}
```

T equals K after normalization. Instrument/account environments match. Provider,
venue, currency, instrument and unit values have no built-in defaults or implicit
aliases. Qualified identity is an equality constraint, not issuer authentication.

### Native replay and joins

Invoke the public `validate_current_entry_position_effect_basis(assessment,
request, trusted_position_effect_context=...)` and
`validate_causal_account_rule_regime_assessment(assessment, assessment_input)`.
The position owner transitively reconstructs the original financial-account
snapshot. No additional account, position, commitment or revision resolver is
introduced. Preserve complete native pairs, including original strings and array
ordering, in local reconstruction evidence.

Native economic/knowledge times equal outer T=K. Position-effect scope equals
outer scope. Regime account equals outer account's namespace, account ID and
environment (native regime has no currency field). The selected assignment and
package provider IDs equal outer provider ID. Program/account-type/phase/agreement
and native approval/revision selection remain native-owned. Provider namespace,
venue and instrument/denomination meaning need independent SCOPE admission.

Every supplied object, inactive native record, unused original and supplied
context is structurally validated before a semantic return. Malformed material,
contradictory known identities or failed native output replay raises ValueError
even if another prerequisite is missing. Correctly reconstructed native UNKNOWN
propagates uncertainty. A supplied native positive assessment with missing or
changed native context fails native replay. A position-effect context without
its owner pair rejects.

### Original evidence and typed mappings

```text
OriginalEvidence = {evidence_id: Text, source: Source, media_type: Text,
 content_base64: Text, content_sha256: Hash, source_available_at: Time|null,
 observed_at: Time}
EvidenceRef = {evidence_id: Text, envelope_sha256: Hash}
NativeRef = {kind: MANIFEST|ASSIGNMENT|PACKAGE|APPROVAL|EVIDENCE|RULE|CLAUSE,
 pointer: canonical JSON pointer, content_sha256: Hash}
NativeMapping = {native_reference: NativeRef, original_reference: EvidenceRef,
 original_locator: Text, relationship: EXACT_DOCUMENT|CLAUSE_SUPPORT|ASSERTION_SUPPORT}
```

Original bytes are nonempty canonical padded Base64: strict decode/re-encode must
round-trip exactly. content_sha256 hashes decoded bytes without text/newline
conversion. envelope_sha256 hashes the complete normalized OriginalEvidence,
including raw hash, source metadata and times. NativeRef hashes the entire
original object addressed within `account_rule_regime.assessment_input`, before
any native normalization. Only these owner-valid pointers are accepted:

```text
MANIFEST /manifest
ASSIGNMENT /manifest/assignments/i
PACKAGE /manifest/packages/i
APPROVAL /approvals/i
EVIDENCE /manifest/evidence/i
RULE /manifest/packages/i/rules/j
CLAUSE /manifest/assignments/i/evidence_refs/j
CLAUSE /manifest/assignments/i/package_bindings/j/evidence_refs/k
CLAUSE /manifest/packages/i/evidence_refs/j
CLAUSE /manifest/packages/i/coverage/evidence_refs/j
CLAUSE /manifest/packages/i/rules/j/evidence_refs/k
CLAUSE /manifest/packages/i/rules/j/body/measure/definition_refs/k
CLAUSE /manifest/packages/i/rules/j/body/reset_schedule/evidence_refs/k
CLAUSE /manifest/packages/i/rules/j/body/evidence_refs/k
```

The last three apply only to native bodies declaring them. Clause targets must
be actual native `{evidence_id, clause_locator}` objects. RFC 6901 escapes are
only ~0/~1; canonical nonnegative indices have no leading zeros. Invalid kinds,
hashes, targets, URI fragments, wildcards, negative indices, '-' and arbitrary
resolving paths reject.

EVIDENCE requires EXACT_DOCUMENT, CLAUSE requires CLAUSE_SUPPORT and all other
kinds require ASSERTION_SUPPORT. One mapping per native target is allowed.
Clause and corresponding native document mappings must identify the same
original envelope. Missing mappings are unresolved; supplied invalid references
or contradictions reject. EXACT_DOCUMENT requires the native four-part source
identity, equality with any known native document SHA-256, and equal known source
availability times. A null native digest stays null; independent admission must
establish the supplemental relationship. Locators and hashes alone cannot prove
faithful interpretation or provider authority.

All original observations <= packet observation <= K; known publication <=
observation. Mapping originals must have been observed by the corresponding
native assertion: manifest observation for manifest/assignment/assignment clauses;
interpreted_at for package/rule/package clauses; approval observation for approval;
native evidence observation for document mappings. Current exception/override
review may use later originals available by K, without claiming the earlier
interpretation already knew them. Required unknown source availability prevents
proof. Unreferenced unknown availability does not block; post-K supplied evidence
still rejects.

### Supplemental assertions and every-rule disposition

```text
RuleSupport = {observed_at: Time, evidence: OriginalEvidence[],
 native_mappings: NativeMapping[], scope_binding: ScopeBinding, coverage: Coverage,
 rule_bindings: RuleBinding[]}
ScopeBinding = {status: COMPATIBLE|INCOMPATIBLE|UNKNOWN, evidence_refs: EvidenceRef[]}
Coverage = {terminal_limit_inventory: Completeness,
 exceptions_and_overrides: Completeness, source_information_cutoff: Time|null,
 evidence_refs: EvidenceRef[]}
RuleBinding = {rule_reference: NativeRef<RULE>, population: Population,
 quantity_denomination: QuantityMeaning, terminal_projection: TerminalProjection,
 force: RuleForce}
Population = {relation: CONTAINS_ENTRY_INSTRUMENT|DISJOINT|UNKNOWN,
 evidence_refs: EvidenceRef[]}
QuantityMeaning = {relation: IDENTICAL|INCOMPATIBLE|UNKNOWN|NOT_APPLICABLE,
 evidence_refs: EvidenceRef[]}
TerminalProjection = {kind: EXPLICIT_TERMINAL_STATE|CONTINUOUS_NECESSARY_TERMINAL|UNKNOWN,
 evidence_refs: EvidenceRef[]}
RuleForce = {status: MANDATORY_THROUGHOUT_P|UNKNOWN, exception_coverage: Completeness,
 exception_resolution: NONE_APPLICABLE|RESOLVED_WITH_BOUND_UNCHANGED|UNKNOWN,
 source_information_cutoff: Time|null, evidence_refs: EvidenceRef[]}
```

No supplemental ceiling, relevance flag, precedence ranking, selected q or approval
boolean exists. NOT_APPLICABLE is forbidden for per-position quantity rules;
denomination is unused for other bodies. Positive terminal projections are
permitted only for native supported POSITION_LIMIT bodies. Cutoffs cannot exceed
packet observation. Empty support arrays cannot establish a positive assertion.

Every rule in the selected native package receives exactly one derived disposition:

1. Unusable regime/scope admission, exact binding, originals or own RULE receipt:
   UNRESOLVED.
2. Independently established disjoint population: DISJOINT_POPULATION.
3. Unresolved population or UNKNOWN lifecycle effect: UNRESOLVED.
4. Effects exclusively EXIT/PHASE_TRANSITION/PAYOUT, faithfully admitted:
   OTHER_OBLIGATION.
5. Any ENTRY/HOLDING/ACCOUNT_ELIGIBILITY and unsupported representation:
   UNRESOLVED.
6. Relevant supported non-position body: OTHER_OBLIGATION.
7. Relevant supported position limit with P and every numerical proof gate:
   TERMINAL_LIMIT; otherwise UNRESOLVED.

Supported other bodies are ACCOUNT_STATE_REQUIREMENT, INSTRUMENT_ACTION_PERMISSION,
AUTOMATION_PERMISSION, STATIC_FLOOR, DAILY_RESET_FLOOR and ACTION_WINDOW. HOLDING
is potentially terminal-relevant. OTHER_OBLIGATION is retained, never passed.
Unsupported semantics cannot become a numeric bound via free text or a receipt.
An empty selected rule list still requires independently complete coverage.

Account-wide and admitted included-instrument populations have terminal count 1;
proven disjoint populations have count 0. Same-namespace distinct instrument IDs
still need admitted exhaustive population meaning. Different namespaces alone
establish neither identity nor disjointness; cross-namespace reconciliation stays
UNKNOWN. A disjoint claim contradicting account-wide scope or explicit membership,
or a containing claim contradicting exact same-namespace exclusion, rejects.
IDENTICAL quantity meaning requires exact native/outer unit spelling; honest
INCOMPATIBLE means UNKNOWN. No unit, currency or contract-size conversion occurs.

EXPLICIT_TERMINAL_STATE requires original support explicitly applying the bound
to the defined terminal state. CONTINUOUS_NECESSARY_TERMINAL requires a genuine
continuous restriction whose quantified states include that terminal state. The
native CONCURRENT_POSITION_COUNT tag alone does not prove either interpretation.
A passing necessary terminal comparison never discharges intermediate/peak/path
compliance. All outputs carry these conditional assumptions in exactly this order:

```text
ACCEPTED_ENTRY_FULLY_FILLED
ALL_ENTRY_FILLS_AGGREGATED_UNDER_ADMITTED_MECHANICS
NO_UNRELATED_INTERVENING_STATE_CHANGE
ADMITTED_MECHANICS_REMAIN_APPLICABLE
ADMITTED_RULES_REMAIN_APPLICABLE_AT_TERMINAL_STATE
```

### Independent host admission and target support closure

```text
PositionLimitContext = {contract: ADMISSION_CONTRACT, rule_version: ADMISSION_RULE,
 admission_id: Text, authority_namespace: Namespace, authority_id: Text,
 mandate_id: Text, mandate_revision: PositiveInt, purpose: PURPOSE,
 request_content_sha256: Hash, knowledge_boundary: Time, effective_from: Time,
 effective_until: Time|null, admitted_at: Time, available_at: Time,
 applicable_approval_refs: NativeRef<APPROVAL>[], admissions: Receipt[]}
Receipt = {target: AdmissionTarget, status: ADMITTED|UNRESOLVED,
 evidence_refs: EvidenceRef[]}
AdmissionTarget = {kind: REGIME}|{kind: SCOPE}|{kind: COVERAGE}
 | {kind: RULE, rule_reference: NativeRef<RULE>}
```

Context pins H(complete normalized Request), exact K and purpose. Require packet
observation <= admitted_at <= available_at <= K, and no consumed native observation
after admission. Current admission uses the half-open interval
effective_from <= T < effective_until, or no upper end. Expired/future-effective
well-formed admission gives UNKNOWN. Wrong pins, purpose, K, chronology, orphan
context without support, invalid/duplicate targets and references reject.
applicable_approval_refs equals exactly the native selected regime's returned
approval component, mapped to original input pointers, or [] with no selection.
Known future-effective connected approvals are preserved without requiring every
individual interval to contain T.

Each ADMITTED receipt has nonempty references and includes the complete required
original-support closure. Extra valid references cannot replace missing support:

- REGIME admits source authority, faithful assignment/interpretation, approval
  provenance and complete current assignment/package/approval revision inventory.
  Its closure includes manifest, selected assignment/package and all selected
  approval mappings, all selected assignment/binding clauses, selected package's
  own clauses and corresponding document mappings.
- SCOPE admits exact request/native account/provider/venue/instrument/unit
  relationships, with scope_binding evidence.
- COVERAGE admits complete current terminal inventory and exception/override
  review, including material interpretation limitations; its closure includes
  native package coverage clauses/documents and supplemental coverage evidence.
- RULE admits one exact native rule's faithful classification, population and
  each interpretation used. Closure includes its rule mapping, all nested native
  clauses/documents, population evidence and any denomination/projection/force
  evidence used numerically. Unused numerical assertions need not be proved for
  disjoint/other dispositions.

Global receipts cannot replace a RULE receipt. Missing support/receipts means
UNKNOWN; UNRESOLVED receipts cannot establish a claim. Required originals must
have known causal source availability. Numerical force requires mandatory status,
complete rule-specific exceptions, NONE_APPLICABLE or resolved with unchanged
bound, and rule-specific cutoff exactly K.

This module does not authenticate source, provider or host identities. Its trusted
argument must be injected by an independently controlled host that establishes
issuer, mandate, evidence access and review. Correct hashes and an ADMITTED label
cannot authenticate a caller-created dictionary. No trusted provider integration,
source registry or ingestion connector is introduced. Without real evidence and
independently established admission, the honest result remains UNKNOWN.

### Exact predicate, scoped exclusions and outcomes

P=[a,b], 0<a<=b<infinity, comes only from established native position-effect support.
Applicable admitted native quantity ceilings contribute q<=U_i; count maxima
contribute N_j<=M_j. Count is constant across P. Disjoint count 0 is tautological
because native M>=0 and is recorded in disposition without a predicate constraint.
Only unconditional mandatory bounds after exception closure enter the conjunction.

For a complete predicate, any failing count gives EMPTY. Otherwise
u=min({b} union {U_i}); u<a gives EMPTY, else inclusive [a,u]. A proved empty
constraint universe gives P. Comparisons use arbitrary-precision exact arithmetic,
without floating point, rounding, ambient Decimal precision or grid enumeration.
Never extrapolate beyond P or assert grid membership/nonempty executable quantity.

Each independently usable rule can produce:

- U<a: ALL_SUPPORT, QUANTITY_LIMIT_EXCLUDES_ALL_P.
- a<=U<b: UPPER_TAIL (U,b], QUANTITY_LIMIT_EXCLUDES_UPPER_TAIL.
- N>M: ALL_SUPPORT, COUNT_LIMIT_EXCLUDES_ALL_P.
- Otherwise no exclusion.

All exclusions require P, unique current native regime, admitted REGIME/SCOPE/that
RULE, exact population/units, supported projection and independently closed
mandatory force/exceptions through K. An unrelated incomplete global inventory
does not erase a self-contained proof. If missing coverage could conceal an
exception defeating that rule, no such proof exists. Minimum arithmetic is never
an authority or precedence resolver.

```text
NegativeProof = {rule_reference: NativeRef<RULE>, reason_code: negative code,
 excluded_domain: {kind: ALL_SUPPORT}
  | {kind: UPPER_TAIL, lower_exclusive: PositiveDecimal, upper_inclusive: PositiveDecimal},
 admission_targets: AdmissionTarget[], evidence_refs: EvidenceRef[]}
```

Targets are exactly REGIME, SCOPE and that RULE in canonical order. Evidence is
the union of those receipts and their required closures; reconstructed position
evidence/context separately pins P.

Precedence is ValueError for any supplied structural invalidity; NOT_SUITABLE for
an independently sufficient all-P exclusion; otherwise UNKNOWN for any unresolved
complete-predicate gate; otherwise ESTABLISHED with a complete nonempty interval.
NOT_SUITABLE is scoped to P and never a final NO TRADE decision. All unrelated
unknowns and partial exclusions remain visible. UNKNOWN returns null predicate
and domain. A decisive negative returns EMPTY even if unrelated uncertainty
requires the complete predicate to remain null. With complete coverage the full
predicate is returned for either definite outcome.

### Output, reasons, identity and authority

```text
Assessment = {contract, rule_version, assessment_economic_time: Time,
 knowledge_boundary: Time, scope: Scope, outcome: ESTABLISHED|NOT_SUITABLE|UNKNOWN,
 reason_codes: ReasonCode[], position_effect_support: PositionSupport|null,
 rule_dispositions: RuleDisposition[], terminal_limit_predicate: Predicate|null,
 terminal_satisfying_domain: SatisfyingDomain|null, negative_proofs: NegativeProof[],
 unresolved_findings: UnresolvedFinding[], conditions: fixed five strings,
 reconstruction_evidence: ReconstructionEvidence, downstream_obligations: fixed strings,
 source_authentication: SOURCE_AUTHENTICATION, authority: Authority, execution: false,
 assessment_identity: IDENTITY_PREFIX + Hash}
Interval = {minimum: PositiveDecimal, maximum: PositiveDecimal}, minimum<=maximum
PositionSupport = {position_effect_identity: Text, quantity_unit: Text, interval: Interval}
RuleDisposition = {rule_reference: NativeRef<RULE>,
 disposition: TERMINAL_LIMIT|DISJOINT_POPULATION|OTHER_OBLIGATION|UNRESOLVED,
 terminal_count: 0|1|null, reason_codes: ReasonCode[]}
Predicate = {kind: TERMINAL_UPPER_BOUND_CONJUNCTION, support: Interval,
 quantity_unit: Text, constraints: Constraint[]}
Constraint = {kind: PER_POSITION_QUANTITY, rule_reference: NativeRef<RULE>,
 maximum: PositiveDecimal, projection: EXPLICIT_TERMINAL_STATE|CONTINUOUS_NECESSARY_TERMINAL}
 | {kind: TERMINAL_POSITION_COUNT, rule_reference: NativeRef<RULE>, terminal_count: 0|1,
 maximum: Count, projection: EXPLICIT_TERMINAL_STATE|CONTINUOUS_NECESSARY_TERMINAL}
SatisfyingDomain = {kind: EMPTY}
 | {kind: CLOSED_INTERVAL, minimum: PositiveDecimal, maximum: PositiveDecimal}
UnresolvedFinding = {reason_code: unresolved code, subject: canonical JSON pointer}
ReconstructionEvidence = {request: complete normalized Request with native pairs preserved,
 trusted_position_effect_context_sha256: Hash|null,
 trusted_position_limit_context_sha256: Hash|null}
```

PositionSupport is present iff native position-effect reconstruction establishes P.
Disposition terminal_count is non-null only for count rules with admitted population
and established native count; it can survive another failed numerical gate.
Non-count rows always have null. Finding subjects address the conceptual root
{request, trusted_position_effect_context, trusted_position_limit_context}; missing
objects use their existing null field, never an invented dangling descendant.

The closed unresolved vocabulary and emission gates are:

```text
OWNER_MISSING                       null required owner pair
OWNER_NOT_ESTABLISHED               reconstructed position owner is not established
REGIME_NOT_UNIQUE                   native regime selects no unique current regime
RULE_SUPPORT_MISSING               null supplemental packet
ADMISSION_MISSING                  null terminal context
ADMISSION_NOT_CURRENT              context does not cover T
RECEIPT_MISSING                    required target absent
RECEIPT_UNRESOLVED                 target explicitly unresolved
ORIGINAL_SUPPORT_MISSING           required mapping/support/receipt closure absent
SOURCE_AVAILABILITY_UNKNOWN         required original publication unavailable
SCOPE_UNRESOLVED                   scope assertion UNKNOWN
SCOPE_INCOMPATIBLE                 scope assertion INCOMPATIBLE
COVERAGE_INCOMPLETE                required native/supplemental completeness not COMPLETE
COVERAGE_NOT_CURRENT               required supplemental cutoff null or before K
RULE_BINDING_MISSING               selected rule has no binding
POPULATION_UNRESOLVED              supported population relation unestablished
QUANTITY_SEMANTICS_UNRESOLVED        required denomination UNKNOWN
QUANTITY_SEMANTICS_INCOMPATIBLE      required denomination INCOMPATIBLE
RULE_EFFECT_UNKNOWN                relevant native lifecycle UNKNOWN
RULE_UNSUPPORTED                   potentially terminal-relevant unsupported representation
TERMINAL_PROJECTION_UNRESOLVED      required terminal projection UNKNOWN
RULE_FORCE_UNRESOLVED              mandatory force unestablished
EXCEPTIONS_UNRESOLVED              rule exception coverage/resolution/cutoff insufficient
```

Positive disposition codes are TERMINAL_RULE_ESTABLISHED,
DISJOINT_POPULATION_ESTABLISHED and OTHER_OBLIGATION_RETAINED. Their codes stay
in their own rows. UNRESOLVED rows contain applicable shared and local blocking
codes. Top reasons are the union of negative and unresolved codes, with
TERMINAL_DOMAIN_ESTABLISHED exactly for ESTABLISHED. Collect independently
assessable failures, suppressing descendant noise for missing parents. Unused
numerical claims do not create findings for established disjoint/other rows.

J is compact sorted-key JSON, ensure_ascii=False, allow_nan=False, UTF-8; H is
lowercase SHA-256(J). Exact integers render without changing interpreter-wide
conversion limits. Normalize local times/decimals only. Evidence sorts by ID;
mappings/bindings by canonical native reference; evidence refs by ID/hash; native refs and
receipt targets by canonical reference/target; constraints/dispositions/proofs/
findings by complete J; reasons/obligations lexicographically. Conditions retain
fixed order. Input duplicate identities/references reject even if identical;
derived unions/findings/reasons deduplicate. Native arrays/spellings stay original.

Native context digest is copied from the successfully replayed position owner's
reconstruction evidence, not a duplicated private normalizer. Terminal context
digest is H(normalized new context), or null. Assessment identity is the fixed
prefix plus H(entire output excluding only assessment_identity). Validator fully
reevaluates original owners, evidence and contexts, then compares every serialized
field without normalizing a supplied output into acceptance. Rehashed tampering
rejects. All returned data is detached from inputs, contexts and other outputs.

Authority has exactly quantity_selection, budget_approval,
position_effect_compliance, margin_capital_approval, trade_decision, financial_risk
and execution, all false; top execution is false. Fixed sorted obligations are:

```text
ATOMIC_COMMITMENT_AND_RESERVATION_CONTROL
CANDIDATE_VALIDITY
CURRENT_STATE_MECHANICS_AND_RULE_REVALIDATION
ENTRY_QUANTITY_DOMAIN_MEMBERSHIP
EXECUTION_PATH_AND_PEAK_POSITION_LIMIT_COMPLIANCE
MARGIN_AND_AVAILABLE_CAPITAL_FEASIBILITY
MARKET_ORDER_AND_FILL_FEASIBILITY
MISSION_CONTROL_CURRENT_AUTHORIZATION
ORDER_ACCEPTANCE_AND_PENDING_COMMITMENT_RULES
OTHER_PROVIDER_AND_ACCOUNT_RULE_COMPLIANCE
POST_ENTRY_FLOOR_AND_PROVIDER_HEADROOM
QUANTITY_SELECTION_POLICY_AND_SELECTION
RISK_BUDGET_QUANTITY_FEASIBILITY
```

Acceptance tests reconstruct genuine owners across LONG/SHORT and NETTING/HEDGING,
all lifecycle effects/dispositions, terminal/continuous interpretations, exact
inclusive/singleton/extreme bounds, count 0/1, population relationships, conjunctive
limits, complete absence, incomplete/competing/current/future regimes, exception
closure and scoped negatives, native null/non-null hashes, whitelisted mappings,
receipt targets/support, post-K and malformed unrelated evidence, rehashed owner/
output mutations, deterministic native/local presentation and detached results.
Synthetic external admissions do not prove production provider authentication.

### Separate future profit-lock and payout lifecycle

The strategic aim of controlled funded-account growth around 4–5% monthly,
followed by an account-specific halt on new trading while awaiting payout,
belongs to a separate future account-level profit-lock/payout-lifecycle owner.
It must eventually use actual prop-firm terms, reliable net realized performance,
payout-cycle definitions and current account-state authorization. This terminal
slice introduces no performance target, profit trigger, payout eligibility or
provider-rule reinterpretation.

## Current Entry Quantity Constraint Composition v1

`xauusd_current_entry_quantity_constraint_composition.py` reconstructs the
financial-feasibility and terminal-position-limit owners, establishes one exact
qualified current scenario, and derives conditional supported quantity grids.
It does not recalculate risk, fees, policy, position effects or provider limits.
It selects no quantity, constructs no order, and grants no downstream authority.
This section records the frozen final normative contract.

### Constants, public APIs and trust boundary

```text
CONTRACT = trading.xauusd_current_entry_quantity_constraint_composition.v1
RULE_VERSION = xauusd_current_entry_quantity_constraint_composition_v1
IDENTITY_PREFIX = current_entry_quantity_constraint_composition_
MECHANISM = IMMEDIATE_MARKET_ENTRY_SCENARIO_V1
SOURCE_AUTHENTICATION = NOT_VERIFIED_BY_THIS_CAPABILITY
Outcome = ESTABLISHED | NOT_SUITABLE | UNKNOWN
Owner = FINANCIAL | TERMINAL
JoinStatus = PROVEN | UNKNOWN
```

```python
evaluate_current_entry_quantity_constraint_composition(
    request: dict, *, trusted_planning_context=None,
    trusted_quantity_context=None, trusted_feasibility_context=None,
    trusted_position_effect_context=None, trusted_position_limit_context=None,
) -> dict
validate_current_entry_quantity_constraint_composition(
    assessment: dict, request: dict, *, trusted_planning_context=None,
    trusted_quantity_context=None, trusted_feasibility_context=None,
    trusted_position_effect_context=None, trusted_position_limit_context=None,
) -> dict
```

For each nonnull original pair invoke the genuine public validator:

```python
validate_current_risk_budget_quantity_feasibility(
    pair["assessment"], pair["request"],
    trusted_planning_context=trusted_planning_context,
    trusted_quantity_context=trusted_quantity_context,
    trusted_feasibility_context=trusted_feasibility_context,
)
validate_current_terminal_position_limits(
    pair["assessment"], pair["request"],
    trusted_position_effect_context=trusted_position_effect_context,
    trusted_position_limit_context=trusted_position_limit_context,
)
```

Consume the full reconstructed results. Their transitive reconstruction includes
candidate/validity, current risk basis, policy, grid, account state, position
mechanics, commitments and rule regime. No supplied summary or identity replaces
replay. No new admission service, blanket approval or provider integration exists.
Trusted contexts must come from an independently controlled host boundary; the
pure function cannot authenticate a caller-created dictionary. Hashes bind
content, never provider authenticity. Existing scope-specific admissions remain
native-owned. No aliases, currency conversion or quantity conversion are inferred.

All supplied serialized material and contexts are checked before any semantic
return. A malformed owner or context, contradictory known co-reference or failed
replay raises ValueError even alongside a missing prerequisite or decisive
negative. An absent financial pair requires all three financial contexts null;
an absent terminal pair requires both terminal contexts null. Nested orphan
context rules remain native-owned.

### Closed primitives and request

Every object has exactly the listed required keys; extra keys reject. Null is
allowed only where explicit. Text is a built-in UTF-8-encodable string nonempty
after a whitespace check, with actual spelling preserved. Currency matches
`[A-Z]{3}`. Hash is 64 lowercase hexadecimal characters. Nat is a built-in
nonnegative integer excluding bool. Index is a canonical nonnegative integer
string `0|[1-9][0-9]*` with no imposed digit-count limit. Decimal is a canonical
finite plain-decimal string, without exponent, plus, unnecessary leading zeros,
trailing fractional zeros or signed zero. PositiveDecimal is strictly positive.
NativeJSONObject is an ordinary dictionary with string keys and recursively
serialized finite JSON values, additionally governed by its native schema.
Native finite floats remain provenance only. Cycles, non-JSON containers,
nonfinite numbers and invalid Unicode reject.

Local input Timestamp requires calendar-valid
`YYYY-MM-DDTHH:MM:SS[.fraction](Z|+/-HH:MM)`, at most six fractional digits, valid
explicit offset and representable UTC instant. Output is UTC with six fractional
digits and Z. Current outer economic time must equal knowledge boundary T=K.

```text
Request = {contract, rule_version, assessment_economic_time: Timestamp,
 knowledge_boundary: Timestamp, scope: Scope,
 risk_budget_feasibility: OwnerPair|null,
 terminal_position_limits: OwnerPair|null}
OwnerPair = {assessment: NativeJSONObject, request: NativeJSONObject}
Namespace = {source_id: Text, source_contract: Text,
 source_contract_version: Text}
Account = {source_id: Text, source_contract: Text,
 source_contract_version: Text, account_id: Text,
 environment: DEMO|LIVE, currency: Currency}
Instrument = {source_id: Text, source_contract: Text,
 source_contract_version: Text, environment: DEMO|LIVE, instrument_id: Text}
Scope = {account: Account, provider_namespace: Namespace, provider_id: Text,
 venue_id: Text, instrument: Instrument, entry_direction: LONG|SHORT,
 entry_mechanism: IMMEDIATE_MARKET_ENTRY_SCENARIO_V1, quantity_unit: Text}
```

Account/instrument environments agree. Scope declares the subject, not admitted
applicability. An explicit null top-level pair is a missing prerequisite;
omitted keys, partial pairs and null pair members reject. No standalone grid,
approval, selected quantity, order or decision is accepted.

### Original paths and exact shared scenario

FR denotes the original financial pair's request; TR denotes the original
terminal pair's request. FA and TA are their returned reconstructed assessments.
RP=FR.risk_policy, RB=FR.risk_basis, QD=FR.quantity_domain,
PE=TR.position_effect. Nested assessment facts are used only after top-level
native replay. Nullable ancestors make an operand unavailable; present malformed
native structures remain errors.

| Subject | Exact original/replayed paths |
| --- | --- |
| Account pairs | RP.request.account_state; RB.request.account_state; PE.request.account_state |
| Regime pairs | RP.request.account_rule_regime; TR.account_rule_regime |
| Candidate pairs | RP.request.candidate; RB.request.candidate |
| Current validity | RB.request.validity |
| Historical measurement | RP.request.financial_measurement |
| Current qualified financial namespace | RB.assessment.reconstruction_evidence.selected_specification.specification.position_namespace |
| Financial semantic assertions | FR.binding_evidence.claims |
| Grid scope | QD.assessment.scope |
| Position and terminal scope | PE.assessment.scope; TA.scope |
| P | PE.assessment.effect_basis.quantity_range; TA.position_effect_support.interval |
| D intersect R | FA.supported_entry_domain |
| F | FA.feasible_domain |
| H | TA.terminal_satisfying_domain |
| Terminal exclusions | TA.negative_proofs |

Compare all available required operands even when another is absent. A known
contradiction raises ValueError. Unavailable material is not a fabricated
inequality. Complete original-pair equality preserves native strings, arrays,
nulls and numeric representations; object-key order alone is immaterial. No
alternative account or regime original reconciliation is supported.

Exactly eleven join rows occur, sorted lexicographically by requirement:

| JoinRequirement | PROVEN iff |
| --- | --- |
| ACCOUNT_ORIGINALS | All three account original pairs exist and are identical. |
| REGIME_ORIGINALS | Both regime original pairs exist and are identical. |
| ACCOUNT_IDENTITY | All account/regime pairs exist; account namespace, ID, environment and currency equal outer account; native regime accounts equal its projection excluding currency. |
| PROVIDER_AND_VENUE | Financial and position owners are established; both selected regimes exist and originals match; assignment/package and grid provider IDs agree with outer provider; grid/planning/position venues agree; position/terminal provider namespaces equal outer. |
| INSTRUMENT_IDENTITY | Financial and position owners are established; current financial namespace projected to Instrument equals outer instrument; grid instrument/environment and qualified position/terminal instruments agree. |
| DIRECTION_AND_MECHANISM | Financial and position owners are established; candidate, risk scenario, grid, position basis/scope and terminal scope agree with outer direction/mechanism. |
| QUANTITY_DENOMINATION | Financial and position owners are established; current namespace/risk function, financial set fields, grid, position basis/scope and terminal scope use the exact outer unit, with native independently admitted economic meaning. |
| MONETARY_DENOMINATION | Financial and position owners are established; shared account, budget, current risk function and payoff currency equal outer currency, preserving native monetary admission. |
| CURRENT_BOUNDARY | Both top-level owners and nested position owner exist and current boundaries equal outer T=K; descendant native current checks replay. |
| CANDIDATE_AND_HISTORY | Both candidate originals, validity and historical measurement pairs exist; candidate originals agree and native replay binds validity and historical measurement. This does not itself assert current validity. |
| INDEPENDENT_SCOPE_ADMISSION | Financial and nested position-effect owners replay as ESTABLISHED with separately supplied native contexts. |

Every available position/terminal scope equals the complete outer scope; every
available grid scope field equals its corresponding outer field. Account
identities project native observation source/account fields. Check all available
current financial instrument, direction, mechanism, unit, currency, provider and
planning-venue comparands before assigning semantic join outcomes.

Equal labels alone never establish meaning. Financial establishment includes
admitted account/provider/venue, instrument, quantity and monetary bindings;
position establishment includes admitted account/provider/venue, instrument,
quantity and direction/mechanism bindings. There is no invented financial
provider_namespace field. Connect the branches through shared account/regime
originals and qualified instrument/provider/venue facts; never substitute an
evidence publisher's namespace. Missing semantic admission leaves UNKNOWN.

### Conservative gate and exact sets

Gate J holds exactly when financial outcome is ESTABLISHED, nested position
outcome is ESTABLISHED and all eleven join checks are PROVEN. Terminal
ESTABLISHED is not required. If J is false, both main domains and both limitation
fields are null. Retain native negatives/findings. Do not consume intermediate
grids of financial UNKNOWN or NOT_SUITABLE as positive joint operands.

Let D be the admitted positive entry grid, R=(0,Q] the finite risk support,
F the established financial feasible grid, P=[a,b] finite position support,
and H the established terminal satisfying interval or EMPTY:

```text
S = D intersect R intersect P
B = F intersect P
C = F intersect H
```

Obtain D intersect R and F directly from the native financial fields. Obtain P
from replayed position mechanics and compare terminal support. No monetary risk,
fees, position effects or provider limits are recalculated.

For q(n)=r+n*d with d>0, 0<=r<d and inclusive native indices i..j, clipping to
closed [l,u] yields:

```text
first = max(i, ceil((l-r)/d))
last  = min(j, floor((u-r)/d))
EMPTY iff first > last
floor(A/B) = A // B                 (integer B > 0)
ceil(A/B)  = -((-A) // B)
```

Use exact integer coefficient/scale or rational arithmetic, sign-aware chunked
large-integer conversion and serialization, no enumeration, float rounding,
ambient Decimal precision or interpreter-wide settings. Index zero is valid
with positive residue. Signed intermediate bounds are supported; owner-valid
nonempty canonical grids have nonnegative member indices. Negative declared
origins are accepted only through native canonicalization. Main grids are finite.

When J holds, copy the native financial outside-risk-support set. Represent
F outside P by the nonempty segments:

```text
[i_F, min(j_F, ceil((a-r)/d)-1)]
[max(i_F, floor((b-r)/d)+1), j_F]
```

Order segments by numeric first index; there are at most two. An empty list
means none; null means unestablished. Outside R/P quantities remain unassessed,
not prohibited. Only the native outside-risk-support limitation may be unbounded.

### Outcome matrix, emptiness and partial exclusions

After structural validation, N below means native prerequisite NOT_SUITABLE
without automatically manufacturing an EMPTY grid; U means UNKNOWN:

| Financial / Terminal | ESTABLISHED | NOT_SUITABLE | UNKNOWN | null |
| --- | --- | --- | --- | --- |
| ESTABLISHED | Evaluate J/sets | N; bounded EMPTY only with J | Evaluate J/sets | U |
| NOT_SUITABLE | N | N | N | N |
| UNKNOWN | U | N | U | U |
| null | U | N | U | U |

Always preserve missing/unknown owner and native unresolved findings. Known
co-reference contradictions and failed replay override every cell. A native
negative without J preserves only its original scope; both main domains stay
null. No scoped negative is a final NO TRADE.

When J holds, choose at most one derived mathematical-negative classification:

1. S empty: both main domains EMPTY; EMPTY_COMMON_SUPPORT.
2. S nonempty, B empty: common=S, composed EMPTY;
   NO_COMMON_FINANCIALLY_FEASIBLE_QUANTITY.
3. S/B nonempty, terminal ESTABLISHED: compute C from F and H. Empty yields
   EMPTY_TERMINAL_INTERSECTION; nonempty is the exact finite composition.
4. S/B nonempty, terminal UNKNOWN or NOT_SUITABLE: composed EMPTY only if native
   terminal exclusions cover all B; otherwise composed null.

Native terminal EMPTY accompanies NOT_SUITABLE and independently established
ALL_SUPPORT; forged ESTABLISHED/EMPTY fails native replay. For terminal UNKNOWN
retaining an admitted upper tail (U,b] on the same P, all nonempty B is excluded
iff r+first_index(B)*d > U. Equality does not exclude. ALL_SUPPORT covers P.
Consume only replayed native proofs; an upper tail's upper endpoint must equal
P.maximum. Same-P upper-tail unions reduce to the smallest lower endpoint.
Reference all individually sufficient native witnesses, sorted by reference key.
If only some B is excluded, retain the negative reference but never promote the
uncovered remainder to a positive set. B emptiness is classified before terminal
attribution. Native rule evidence, scopes, admission targets and assumptions stay
fully preserved in the replayable original owners.

Aggregate precedence is ValueError, then any native prerequisite or derived
negative => NOT_SUITABLE, then any unresolved finding => UNKNOWN, then a complete
nonempty composed grid => ESTABLISHED. Any other combination is an invariant
failure. Unknowns survive decisive negatives and never become positive proofs.

### Closed output and diagnostic types

```text
Assessment = {contract, rule_version, assessment_economic_time,
 knowledge_boundary, scope: Scope, outcome: Outcome, reason_codes: ReasonCode[],
 owner_references: OwnerReferences, join_checks: JoinCheck[],
 common_supported_domain: QuantitySet|null, composed_domain: QuantitySet|null,
 support_limitations: SupportLimitations,
 native_negative_proof_references: NativeItemReference[],
 negative_proofs: NegativeProof[], unresolved_findings: UnresolvedFinding[],
 conditions: Text[], reconstruction_evidence: ReconstructionEvidence,
 downstream_obligations: Text[], source_authentication, authority: Authority,
 execution: false, assessment_identity: Text}
OwnerReferences = {financial: OwnerReference|null, terminal: OwnerReference|null}
OwnerReference = {assessment_identity: Text, owner_bundle_sha256: Hash}
NativeItemReference = {owner: FINANCIAL|TERMINAL,
 collection: negative_proofs|unresolved_findings, index: Nat,
 content_sha256: Hash}
JoinCheck = {requirement: JoinRequirement, status: PROVEN|UNKNOWN}
Empty = {kind: EMPTY}
FiniteGrid = {kind: REGULAR_GRID, origin: Decimal, increment: PositiveDecimal,
 first_index: Index, last_index: Index}
QuantitySet = {quantity_unit: Text, domain: Empty|FiniteGrid}
NativeGrid = {kind: REGULAR_GRID, origin: Decimal, increment: PositiveDecimal,
 first_index: Index, last_index: Index|null}
NativeQuantitySet = {quantity_unit: Text, domain: Empty|NativeGrid}
SupportLimitations = {outside_risk_support: NativeQuantitySet|null,
 financially_feasible_outside_position_support: FiniteGrid[]|null}
```

OwnerReference is null exactly for an absent top-level owner. Its identity comes
from returned replay; bundle hash covers the complete original pair. Every
NativeItemReference resolves against the replayed owner's actual collection and
hashes the complete item. References are unique by owner/collection/index and
sort by owner, collection, then numeric index. The native-negative-reference
array includes every native negative, even when only partial or nondecisive.
There are no arbitrary pointers or diagnostic extension dictionaries.

Common supported domain is null iff J is false, otherwise exactly S. Composed
domain is null without J or sufficient terminal proof, EMPTY only by the
classification above, or a finite nonempty conditional grid. Nonempty grids
have 0<=origin<increment, positive first quantity, ordered inclusive indices and
canonical strings. Limitation segments inherit the established outer unit.

```text
NegativeProof =
 {kind: NATIVE_PREREQUISITE_NOT_SUITABLE, native_proof: NativeItemReference}
 | {kind: EMPTY_COMMON_SUPPORT}
 | {kind: NO_COMMON_FINANCIALLY_FEASIBLE_QUANTITY}
 | {kind: EMPTY_TERMINAL_INTERSECTION}
 | {kind: TERMINAL_EXCLUSION_COVERS_COMMON_FEASIBLE,
    covered_domain: QuantitySet, native_proofs: NativeItemReference[]}
UnresolvedFinding = {reason_code: OWNER_MISSING|OWNER_UNKNOWN|
 JOIN_UNRESOLVED|NATIVE_UNRESOLVED, subject: Owner|JoinRequirement,
 native_reference: NativeItemReference|null}
```

For financial NOT_SUITABLE emit a native-prerequisite proof per native negative.
For terminal NOT_SUITABLE do so only per ALL_SUPPORT negative, never per partial
tail alone. Derived negatives are common-support scoped; native prerequisites
retain native scope. Coverage's covered_domain is nonempty B and its witnesses
are the nonempty list of all individually sufficient terminal native negatives.

Generate OWNER_MISSING per null owner and OWNER_UNKNOWN per unknown top-level
owner, with subject that owner and null reference. Generate JOIN_UNRESOLVED per
unknown join with subject that requirement and null reference. Generate
NATIVE_UNRESOLVED per native unresolved item with subject that owner and a
matching collection/index/hash reference. The reference is required only for
NATIVE_UNRESOLVED. Preserve nested uncertainty through native reconstruction.

ReasonCode is exactly:

```text
CONDITIONAL_QUANTITY_DOMAIN_ESTABLISHED
NATIVE_PREREQUISITE_NOT_SUITABLE
EMPTY_COMMON_SUPPORT
NO_COMMON_FINANCIALLY_FEASIBLE_QUANTITY
EMPTY_TERMINAL_INTERSECTION
TERMINAL_EXCLUSION_COVERS_COMMON_FEASIBLE
OWNER_MISSING
OWNER_UNKNOWN
JOIN_UNRESOLVED
NATIVE_UNRESOLVED
```

reason_codes is the sorted unique union of local negative kinds and unresolved
codes, plus CONDITIONAL_QUANTITY_DOMAIN_ESTABLISHED exactly for ESTABLISHED.
Native detailed reasons remain native. Proofs/findings deduplicate only identical
derived content and sort by canonical JSON. Never reorder native collections.

### Reconstruction, identity, causality and detached validation

```text
ReconstructionEvidence = {request: Request,
 trusted_planning_context_sha256: Hash|null,
 trusted_quantity_context_sha256: Hash|null,
 trusted_feasibility_context_sha256: Hash|null,
 trusted_position_effect_context_sha256: Hash|null,
 trusted_position_limit_context_sha256: Hash|null}
```

Copy the first three fingerprints from returned financial reconstruction and
the last two from returned terminal reconstruction. Preserve native fingerprint
conventions; absent corresponding owners yield null fingerprints. Normalize only
local outer timestamps, derived decimal/index strings and local collections.
Preserve every native original string, numeric representation, array and null.

Canonical JSON is compact sorted-key UTF-8, ensure_ascii=False and separators
(',', ':'), with nonfinite values rejected and array order preserved. Preserve
finite native float JSON representation, distinguish bool from numbers, and emit
arbitrary integers as ordinary decimal JSON without global digit-limit changes.
For ordinary values match Python standard JSON bytes. H(x) is SHA-256 of these
bytes. Identity is IDENTITY_PREFIX+H(complete result before adding identity),
including reconstruction, diagnostics, flags and context fingerprints.

Current boundaries compare parsed UTC instants. Preserve historical candidate
and measurement times and native no-lookahead checks. Post-K observations or
admissions cannot support a result; known future-effective data remains future.
Expired/future-effective native context outcomes remain native. No wall clock
substitutes for explicit K. Equivalent outer times normalize identically with
otherwise identical originals; changed native presentation may change identity.

The detached validator requires a serialized dictionary, reevaluates the entire
request with all five contexts, compares every supplied field against exact
canonical expected output and returns a detached copy. It never normalizes a
forged output into acceptance. Rehashed tampering, extra/missing fields, altered
ordering and 0 substituted for false reject. No caller input/context or previous
return shares mutable state with new output.

### Fixed assumptions, authority and downstream obligations

Conditions are exactly this ordered list:

```text
ACCEPTED_ENTRY_FULLY_FILLED
ALL_ENTRY_FILLS_AGGREGATED_UNDER_ADMITTED_MECHANICS
NO_UNRELATED_INTERVENING_STATE_CHANGE
ADMITTED_MECHANICS_REMAIN_APPLICABLE
ADMITTED_RULES_REMAIN_APPLICABLE_AT_TERMINAL_STATE
CONDITIONAL_ON_RECONSTRUCTED_RISK_BASIS
```

Authority has exactly quantity_selection, budget_approval,
position_effect_compliance, margin_capital_approval, trade_decision,
financial_risk and execution, all built-in false booleans. Top-level execution
is false; source_authentication is NOT_VERIFIED_BY_THIS_CAPABILITY.

Downstream obligations are exactly the sorted native union:

```text
ATOMIC_COMMITMENT_AND_RESERVATION_CONTROL
CANDIDATE_VALIDITY
CURRENT_STATE_MECHANICS_AND_RULE_REVALIDATION
ENTRY_QUANTITY_DOMAIN_MEMBERSHIP
EXECUTION_PATH_AND_PEAK_POSITION_LIMIT_COMPLIANCE
MARGIN_AND_AVAILABLE_CAPITAL_FEASIBILITY
MARKET_ORDER_AND_FILL_FEASIBILITY
MISSION_CONTROL_CURRENT_AUTHORIZATION
ORDER_ACCEPTANCE_AND_PENDING_COMMITMENT_RULES
OTHER_PROVIDER_AND_ACCOUNT_RULE_COMPLIANCE
POSITION_EFFECT_AND_ACCOUNT_RULE_COMPLIANCE
POST_ENTRY_FLOOR_AND_PROVIDER_HEADROOM
QUANTITY_SELECTION_POLICY_AND_SELECTION
RISK_BUDGET_QUANTITY_FEASIBILITY
```

No obligation is marked discharged. A nonempty conditional grid establishes no
order acceptance, fills/stops, continuous/peak position compliance, full provider
compliance, floor headroom, margin, capital reservation, final trading decision,
financial approval or execution authority.

### Normative acceptance and file boundary

Tests must build shared original account/regime evidence before deriving both
native branches, using genuine public replay and synthetic independent admissions.
Cover LONG/SHORT and NETTING/HEDGING; 0.9 financial endpoint versus 0.2 terminal
cap; inclusive singleton; nonempty H without grid points; distinct S-empty,
B-empty and terminal-intersection-empty cases; all-P count/quantity negatives;
terminal UNKNOWN with full versus partial B exclusion and open-tail equality;
multiple sufficient witnesses; all sixteen owner combinations and financial
rejection without F. Partial-negative fixtures keep the shared native package
complete and make supplemental terminal coverage incomplete, so financial
establishment remains possible.

Also cover original account/input/regime contradictions, qualified namespaces,
missing semantic denomination, explicit null versus malformed/missing keys,
orphaned contexts, malformed material beside missing owners, current/historical
timing, expired/future-effective admissions, known future revisions, post-K
material, pending commitments, positive index zero, negative-origin
canonicalization, 5,001-place increments/huge indices, unbounded limitation tails,
rehashed owner and every new output-leaf tampering, canonical identity, local
presentation equivalence, detached/mutation isolation, exact false authority and
absence of quantity/order/final decision. Synthetic evidence authenticates no
real provider. Existing owners and tests are never weakened for fixture success.

Implementation scope is exactly this new standalone module,
`tests/test_xauusd_current_entry_quantity_constraint_composition.py`, and this
documentation addition. No existing owner, registry, Mission Control, connector,
dependency, execution or export change is part of this capability.

The separate funded-account objective remains controlled approximately 4–5%
monthly performance, not a guarantee, with an account-specific halt after the
defined realized-profit threshold, no new trades during payout waiting, explicit
reset/reactivation, and actual provider/account/cross-account restrictions.
Composition implements no profit-lock, payout or monthly-performance policy.

## Current Entry Provider-Measure Projection Basis v1

This standalone owner establishes only the conditional accounting equality
`B_scenario(q) = B_current - R(q)` for every quantity in the complete independently
established finite Capability 5 composed grid C. It preserves the native risk
expression and selects no quantity. The approved implementation baseline was
`d95eb73` on main; local origin/main equality is distinct from fresh remote
verification. The following is the frozen normative implementation contract.

### Constants and public interfaces

```text
CONTRACT = trading.xauusd_current_entry_provider_measure_projection_basis.v1
RULE_VERSION = xauusd_current_entry_provider_measure_projection_basis_v1
ADMISSION_CONTRACT = trading.xauusd_current_entry_provider_measure_projection_basis.admission.v1
ADMISSION_RULE_VERSION = xauusd_current_entry_provider_measure_projection_basis_admission_v1
ADMISSION_PURPOSE = PROVIDER_MEASURE_PROJECTION_FACT_ADMISSION_ONLY
IDENTITY_PREFIX = current_entry_provider_measure_projection_basis_
DESCRIPTOR_KIND = EXACT_MODELED_SETTLED_BALANCE_V1
ENDPOINT = FULLY_SETTLED_MODELED_STOP
ENTRY_MECHANISM = IMMEDIATE_MARKET_ENTRY_SCENARIO_V1
SOURCE_AUTHENTICATION = NOT_VERIFIED_BY_THIS_CAPABILITY
```

```python
evaluate_current_entry_provider_measure_projection_basis(
    request: dict, *, trusted_planning_context=None,
    trusted_quantity_context=None, trusted_feasibility_context=None,
    trusted_position_effect_context=None, trusted_position_limit_context=None,
    trusted_financial_projection_context=None,
) -> dict

validate_current_entry_provider_measure_projection_basis(
    assessment: dict, request: dict, *, trusted_planning_context=None,
    trusted_quantity_context=None, trusted_feasibility_context=None,
    trusted_position_effect_context=None, trusted_position_limit_context=None,
    trusted_financial_projection_context=None,
) -> dict
```

The sole direct upstream reconstruction call is the genuine public
`validate_current_entry_quantity_constraint_composition`, receiving the first
five contexts unchanged. Every present native owner is fully replayed before
consumption. Identity hashes, cached results, labels and private owner helpers
cannot replace public replay. Upstream contracts remain unchanged.

### Primitive, request and qualified scope schemas

Every object is closed, with exactly the declared required fields. Null is
permitted only where explicitly stated. Text is a valid Unicode nonempty string
containing a non-whitespace character; case and padding remain significant.
Hash is 64 lowercase hexadecimal characters. Timestamp requires a real date,
explicit timezone, seconds and at most six fractional digits; local fields
normalize to UTC with six fractional digits and Z. Nat is a built-in integer
at least zero; PositiveInt is a built-in integer at least one; neither accepts
booleans. Completeness is exactly COMPLETE, LIMITED or UNKNOWN. Identity-bearing
duplicates reject even when identical.

```text
Namespace = {source_id: Text, source_contract: Text, source_contract_version: Text}
Source = {source_id: Text, source_contract: Text, source_contract_version: Text,
          source_snapshot_id: Text}

Request = {
  contract: CONTRACT,
  rule_version: RULE_VERSION,
  assessment_economic_time: Timestamp,
  knowledge_boundary: Timestamp,
  scope: Scope,
  quantity_composition: null | {assessment: native object, request: native object},
  measure_target: null | MeasureTarget,
  scenario: Scenario,
  projection_evidence: null | ProjectionEvidence
}

Scope = {
  account: {source_id: Text, source_contract: Text, source_contract_version: Text,
            account_id: Text, environment: DEMO|LIVE, currency: Currency},
  provider_namespace: Namespace,
  provider_id: Text,
  venue_id: Text,
  instrument: {source_id: Text, source_contract: Text, source_contract_version: Text,
               environment: DEMO|LIVE, instrument_id: Text},
  entry_direction: LONG|SHORT,
  entry_mechanism: IMMEDIATE_MARKET_ENTRY_SCENARIO_V1,
  quantity_unit: Text
}

Currency = three uppercase ASCII letters
Scenario = {endpoint: FULLY_SETTLED_MODELED_STOP, settlement_before: Timestamp}
```

Account/instrument environments match. The complete scope equals the genuine
Capability 5 scope. Source identity relationships are admitted; matching labels
alone do not establish them. T equals K by parsed instants. The finite deadline
H = settlement_before is strictly later than T. No duplicate top-level account,
regime or risk originals are accepted.

### Native owners and bounded reference catalogue

Let CB be the complete original quantity_composition pair. Fixed recovery paths:

```text
FQ = CB.request.risk_budget_feasibility.request
TQ = CB.request.terminal_position_limits.request
PB = FQ.risk_policy
RB = FQ.risk_basis
AB = PB.request.account_state
GB = PB.request.account_rule_regime

PB, RB = {assessment, request}
AB = {snapshot, snapshot_input}
GB = {assessment, assessment_input}
```

Absent owner paths remain absent; no partial original is manufactured. Capability
5 already compares shared account originals across policy/risk/position-effect
branches and shared regime originals across policy/terminal branches.

```text
NativeRef = {
  kind: catalogue kind,
  owner_bundle_sha256: Hash,
  selector: exact selector below,
  content_sha256: Hash
}
```

Bundle owner hashes identify the complete preserved original pair. Bundle target
hashes identify that same complete pair. Other content hashes identify the exact
original node below, except RISK_FUNCTION and RISK_CHARGE, which identify genuine
reconstructed risk output. Native normalization must not replace original array
order or spelling for these hashes/selectors.

| Kind | Owner | Selector | Target |
| --- | --- | --- | --- |
| COMPOSITION_BUNDLE | CB | null | Complete CB |
| ACCOUNT_BUNDLE | AB | null | Complete AB |
| POLICY_BUNDLE | PB | null | Complete PB |
| REGIME_BUNDLE | GB | null | Complete GB |
| RISK_BASIS_BUNDLE | RB | null | Complete RB |
| RISK_FUNCTION | RB | null | Replayed assessment.risk_function |
| RISK_CHARGE | RB | {charge_id: Text} | Unique replayed risk charge |
| REGIME_ASSIGNMENT | GB | {assignment_id: Text} | Original manifest.assignments member |
| REGIME_PACKAGE | GB | {package_id: Text, package_revision: Text} | Original manifest.packages member |
| REGIME_BINDING | GB | {assignment_id: Text, binding_index: Nat} | Original assignment.package_bindings[index] |
| REGIME_RULE | GB | {package_id: Text, package_revision: Text, rule_id: Text} | Original package.rules member |
| REGIME_MEASURE | GB | Same as REGIME_RULE | Original rule.body.measure |
| REGIME_DOCUMENT | GB | {evidence_id: Text} | Original manifest.evidence member |
| REGIME_APPROVAL | GB | {approval_index: Nat} | Original assessment_input.approvals[index] |
| REGIME_CLAUSE | GB | Bounded clause selector below | Original clause-reference object |

All manifest paths are within GB.assessment_input. Array indices refer to raw
original arrays. Measure exists only on STATIC_FLOOR and DAILY_RESET_FLOOR.

```text
MeasureTarget = {
  assignment: REGIME_ASSIGNMENT NativeRef,
  package: REGIME_PACKAGE NativeRef,
  rule: REGIME_RULE NativeRef,
  measure: REGIME_MEASURE NativeRef
}

REGIME_CLAUSE.selector = {
  container: non-clause NativeRef from the table below,
  field: EVIDENCE_REFS|COVERAGE_EVIDENCE_REFS|DEFINITION_REFS,
  clause_index: Nat
}
```

| Container | Field | Relative original path |
| --- | --- | --- |
| REGIME_ASSIGNMENT | EVIDENCE_REFS | evidence_refs[index] |
| REGIME_BINDING | EVIDENCE_REFS | evidence_refs[index] |
| REGIME_PACKAGE | EVIDENCE_REFS | evidence_refs[index] |
| REGIME_PACKAGE | COVERAGE_EVIDENCE_REFS | coverage.evidence_refs[index] |
| REGIME_RULE | EVIDENCE_REFS | evidence_refs[index] |
| REGIME_MEASURE | DEFINITION_REFS | definition_refs[index] |

No other combination, recursive clause container, reset-threshold/action-window
clause or arbitrary JSON path is supported. A native clause is exactly
{evidence_id, clause_locator}. All four measure target references describe one
actual selected assignment/package and its actual rule/measure. No label-based
substitution is allowed. A valid EQUITY target resolves but is semantically
unsupported. A fabricated measure on a non-measure rule rejects.

Wrong selector/kind, missing referenced target/owner, wrong owner/content hash,
duplicate/conflicting native identities and ambiguous lookups raise ValueError.
Omitted prerequisites or missing mappings yield UNKNOWN.

### Original envelopes and mandatory support closure

```text
Original = {
  evidence_id: Text, source: Source, media_type: Text,
  content_base64: Text, content_sha256: Hash,
  source_available_at: Timestamp|null, observed_at: Timestamp
}
OriginalRef = {evidence_id: Text, envelope_sha256: Hash}
NativeMapping = {
  native_reference: NativeRef, original_reference: OriginalRef,
  original_locator: Text,
  relationship: EXACT_DOCUMENT|CLAUSE_SUPPORT|ASSERTION_SUPPORT
}
```

Bytes must be nonempty canonical padded base64, round-tripping identically.
content_sha256 hashes raw decoded bytes. envelope_sha256 hashes the complete
normalized original envelope, including source and chronology. Native document
mappings use EXACT_DOCUMENT, clause mappings CLAUSE_SUPPORT, all others
ASSERTION_SUPPORT. Locators are opaque document locations, never executable paths.

An EXACT_DOCUMENT mapping matches the native complete Source and its known byte
hash/publication time. A clause maps to an original also mapped to its native
document, with independently supported locator meaning. Unknown native metadata
is not invented. Missing mappings yield UNKNOWN; contradictory identities,
hashes or supplied clause/document relationships reject. Multiple originals may
support a node; exact duplicate mappings reject.

Establishment requires original support for:

1. Selected assignment and every active original binding contributing to the
   selected immutable package, including all their clauses.
2. Selected package, direct clauses and coverage clauses.
3. Target rule/direct clauses and target measure/every definition clause.
4. Every native document referenced by those clauses.
5. Every approval in the returned selected approval component, including
   connected approved intervals contributing to that component.
6. Original account bundle and direct balance meaning.
7. Native risk basis, reconstructed function and every native charge.
8. All consumed local lifecycle, coverage, accounting, financial-report and
   settlement assertions.

Composition/policy/regime bundle provenance links cannot replace that closure.
An assertion mapping supports an object's meaning; it does not claim that a
provider document literally contains the generated assessment.

### Interpretation inventory and immutable revision lifecycle

```text
ProjectionEvidence = {
  source: Source, scope: Scope,
  source_available_at: Timestamp|null, observed_at: Timestamp,
  originals: Original[], native_mappings: NativeMapping[],
  coverage: InterpretationCoverage, records: InterpretationRecord[]
}
RecordRef = {record_id: Text, content_sha256: Hash}
InterpretationCoverage = {
  economic_from: Timestamp, economic_until: Timestamp,
  source_information_cutoff: Timestamp|null,
  declaration_completeness: Completeness, revision_completeness: Completeness,
  starting_basis: FROM_INCEPTION|INCOMPLETE_OR_UNKNOWN,
  root_records: RecordRef[], missing_record_ids: Text[],
  records_omitted: bool|null, history_truncated: bool|null,
  source_available_at: Timestamp|null, observed_at: Timestamp,
  evidence_refs: OriginalRef[]
}
Predecessor = {kind: ROOT} | {kind: UNKNOWN} |
              {kind: RECORD, record: RecordRef}
DECLARE = {
  record_id: Text, kind: DECLARE, predecessor: Predecessor,
  effective_from: Timestamp, effective_until: Timestamp|null,
  source_available_at: Timestamp|null, observed_at: Timestamp,
  evidence_refs: OriginalRef[], body: DeclarationBody
}
WITHDRAW = {
  record_id: Text, kind: WITHDRAW, predecessor: Predecessor,
  effective_from: Timestamp,
  source_available_at: Timestamp|null, observed_at: Timestamp,
  evidence_refs: OriginalRef[]
}
```

Economic intervals are finite and nonempty. Declaration nonnull ends exceed
starts; null is explicitly open-ended. A withdrawal cannot be a root. Each
successor replaces the entire declaration with no inherited fields.

Potential establishment requires both completeness fields COMPLETE, coverage of
all [T,H), cutoff K, FROM_INCEPTION, no missing IDs, false omission/truncation,
one complete supported linear chain containing every record, original support
and independent revision admission. Select the last lineage record effective
at T, not the greatest label, timestamp or array position. A selected withdrawal
or expired declaration yields UNKNOWN, without predecessor revival. Explicit
subsequent DECLARE can reestablish the complete body.

Duplicate IDs, forged content references, cycles/self references, unexplained
dangling references, a supplied record also declared missing, a supplied ROOT
omitted from roots, a non-root declared as root, and COMPLETE revision claims
contradicting disclosed gaps raise ValueError. Honestly disclosed unavailable
roots/predecessors, incomplete inception/revisions, competing roots/branches and
unsupported backward effective/observed/known-publication lineage order yield
UNKNOWN. A complete history with no record effective at T yields UNKNOWN.

Every historical body remains structurally validated and retained. Historical
subject pins, old charge IDs and financial timestamps are not compared with
today's owners. Only the governing declaration supplies today's accounting
facts. An expired latest declaration retains its historical pins even when it
is resolved as expired; it cannot supply current accounting facts.
Future-effective declarations are retained and checked without premature
activation. Scalar historical hashes do not admit alternative owner bundles.

### Accounting declaration and exact direct-balance bridge

```text
DeclarationBody = {
  subjects: Subjects,
  baseline_binding: BaselineBinding,
  price_loss_recognition: PriceRecognition,
  charge_recognition: ChargeRecognition[],
  cost_coverage_and_rounding: CostCoverage,
  financial_coverage: FinancialCoverage,
  scenario_compatibility: ScenarioCompatibility
}
Subjects = {
  quantity_composition_bundle_sha256: Hash|null,
  account_bundle_sha256: Hash|null,
  regime_bundle_sha256: Hash|null,
  risk_basis_bundle_sha256: Hash|null,
  measure_target_sha256: Hash|null
}
BaselineBinding = {
  state_at: Timestamp, source_information_cutoff: Timestamp|null,
  relationship: DIRECT_NATIVE_BALANCE|OTHER|UNKNOWN,
  evidence_refs: OriginalRef[]
}
PriceRecognition = {
  recognition: EXACT_ONCE_AFTER_BASELINE|OTHER|UNKNOWN,
  evidence_refs: OriginalRef[]
}
ChargeRecognition = {
  charge_id: Text, charge_content_sha256: Hash,
  recognition: EXACT_ONCE_AFTER_BASELINE|ALREADY_REFLECTED|OTHER|UNKNOWN,
  aggregation: EXACT_NATIVE_AGGREGATE|OTHER|UNKNOWN,
  evidence_refs: OriginalRef[]
}
CostCoverage = {
  completeness: Completeness,
  rounding: EXACT_NATIVE_EXPRESSION_ON_C|OTHER|UNKNOWN,
  financing: EXACT_NATIVE_SCENARIO_THROUGH_DEADLINE|NOT_APPLICABLE|OTHER|UNKNOWN,
  evidence_refs: OriginalRef[]
}
ScenarioCompatibility = {
  endpoint: FULLY_SETTLED_MODELED_STOP, settlement_before: Timestamp,
  economic_from: Timestamp, economic_until: Timestamp,
  source_information_cutoff: Timestamp|null,
  accounting_continuity: SUPPORTED|OTHER|UNKNOWN,
  settlement_meaning: SUPPORTED|OTHER|UNKNOWN,
  evidence_refs: OriginalRef[]
}
```

All five governing subject pins must be nonnull and correct for establishment.
Baseline is the original current snapshot balance, with effective state T,
known causal availability and admitted direct BALANCE mapping at cutoff K.
Snapshot, measure and risk denomination must match literally and semantically.
Balance need not equal equity; no reconciliation equation is assumed.

Price loss and every charge must be recognized exactly once after baseline.
Charge rows are an exact bijection by native ID/hash. A wrong governing pin,
extra nonexistent charge or wrong charge hash rejects; missing pins/rows remain
unresolved. Historical bodies retain the separation above.

Every charge must use native SOURCE_SCHEDULE. Native
SUPPORTED_SCENARIO_ENVELOPE is valid upstream but cannot prove exact debit.
SOURCE_SCHEDULE alone does not prove recognition, baseline inclusion, aggregate
fill semantics, posting precision or financing horizon. Fixed/minimum branches
must remain intact. An already-reflected debit cannot be counted again.

Native measure costs are compatible only as supported IN_MEASURE or documented
NOT_APPLICABLE. SUBTRACT_SEPARATELY and EQUITY yield UNKNOWN. Opening/closing
commission categories use commissions treatment; financing/other charges use
their corresponding treatment. NOT_APPLICABLE must agree with native category
coverage and have originals/admission; zero-valued cost does not imply it.

Cost completeness must be COMPLETE. Provider aggregate posting/rounding must
preserve the native expression for every q in C, including breakpoints. This is
a universally admitted proposition; sample checks cannot prove it. Financing
must cover the entire deadline or be independently supported as not applicable.
No caller monetary adjustment, fee replacement, FX or bound variant is allowed.

### Complete financial source, actor and report coverage

```text
FinancialCoverage = {
  state_at: Timestamp, source_information_cutoff: Timestamp|null,
  economic_from: Timestamp, economic_until: Timestamp,
  source_universe_completeness: Completeness,
  actor_completeness: Completeness,
  actors: Actor[], source_roster: FinancialSource[], reports: FinancialReport[],
  evidence_refs: OriginalRef[]
}
Actor = {
  actor_id: Text, namespace: Namespace,
  role: PROVIDER|ACCOUNT_OWNER|AUTOMATION|OTHER,
  evidence_refs: OriginalRef[]
}
FinancialSource = {
  inventory_id: Text, source_namespace: Namespace,
  role: PROVIDER|ACCOUNT_LEDGER|RESERVATION_LEDGER|OTHER,
  actor_ids: Text[], evidence_refs: OriginalRef[]
}
FinancialReport = {
  inventory_id: Text, source: Source,
  state_at: Timestamp, source_information_cutoff: Timestamp|null,
  economic_from: Timestamp, economic_until: Timestamp,
  source_available_at: Timestamp|null, observed_at: Timestamp,
  inventory_completeness: Completeness, revision_completeness: Completeness,
  categories: FinancialCategories, evidence_refs: OriginalRef[]
}
Category = {status: ABSENT|PRESENT|UNKNOWN, effects: FinancialEffect[],
            evidence_refs: OriginalRef[]}
FinancialEffect = {effect_id: Text, actor_id: Text,
                   known_effective_at: Timestamp|null, evidence_refs: OriginalRef[]}
```

FinancialCategories has exactly seven Category keys:

```text
UNPOSTED_CHARGES
CASH_TRANSFERS_AND_WITHDRAWALS
PAYOUT_ADJUSTMENTS
PHASE_OR_CAPITAL_ADJUSTMENTS
MONETARY_RESERVATIONS
KNOWN_SCHEDULED_FINANCIAL_EVENTS
OTHER_MEASURE_AFFECTING_OBLIGATIONS
```

Positive closure requires state T, cutoff K, exact window [T,H), both universe
completenesses COMPLETE, nonempty supported actor/source rosters, explicit
provider actor/source inclusion, every actor covered by an applicable source
and a provider source covering a provider actor. Labels do not prove authority
or responsibility; namespace/account/provider relationships need admission.

There is exactly one report per roster inventory, with matching namespace,
current state/cutoff/window and COMPLETE inventory/revision coverage. Every
report addresses all seven categories for all its assigned actors. All seven
must be explicitly ABSENT with original support and topic-specific admission.
Coverage includes unsettled effects at T and relevant known scheduled effects.
Candidate debits may be excluded from additional effects only with evidence
they are exactly represented in R.

ABSENT and UNKNOWN have empty effects arrays; PRESENT has at least one effect.
Known presence with incomplete reporting is PRESENT plus separate incomplete
coverage. Actor/inventory/report IDs are unique; effect IDs are unique across
categories within a report. Effects reference actors assigned to that report's
source. Unknown actors, extra/duplicate reports, source mismatches and contradictory
status/effect arrays reject. Missing reports yield UNKNOWN. Empty arrays alone
never prove completeness. PRESENT prevents this zero-additional-effect model;
it produces UNKNOWN, no monetary adjustment and no floor violation. Dates alone
do not prove settlement/relevance. Excluding a known event outside the horizon
requires supported semantics establishing no effect within it.

### Independent sixth context and receipt closure

```text
ProjectionAdmission = {
  contract: ADMISSION_CONTRACT, rule_version: ADMISSION_RULE_VERSION,
  admission_id: Text, authority_namespace: Namespace, authority_id: Text,
  mandate_id: Text, mandate_revision: PositiveInt, purpose: ADMISSION_PURPOSE,
  request_content_sha256: Hash, knowledge_boundary: Timestamp,
  effective_from: Timestamp, effective_until: Timestamp|null,
  admitted_at: Timestamp, available_at: Timestamp, admissions: Receipt[]
}
Receipt = {
  target: ReceiptTarget, subject_content_sha256: Hash,
  status: ADMITTED|UNRESOLVED, evidence_refs: OriginalRef[]
}
```

Fixed ReceiptTarget objects have exactly {kind}, with kind one of:

```text
SCOPE_AND_NATIVE_BINDINGS
MEASURE_DEFINITION_AND_BASELINE
PRICE_LOSS_RECOGNITION
COST_COVERAGE_AND_ROUNDING
FINANCIAL_SOURCE_COVERAGE
INTERPRETATION_REVISION_COVERAGE
SCENARIO_AND_SETTLEMENT_SEMANTICS
```

Each native risk charge additionally requires exactly:

```text
{kind: CHARGE_RECOGNITION, charge_id: Text, charge_content_sha256: Hash}
```

Let HJSON mean the canonical SHA-256 below and Q the normalized local request
preserving the complete original native pair. The context request pin is HJSON(Q).
Each receipt subject hash is:

```text
HJSON({
  request_content_sha256: HJSON(Q),
  native_context_fingerprints: {
    trusted_planning_context_sha256: Hash|null,
    trusted_quantity_context_sha256: Hash|null,
    trusted_feasibility_context_sha256: Hash|null,
    trusted_position_effect_context_sha256: Hash|null,
    trusted_position_limit_context_sha256: Hash|null
  },
  target: exact ReceiptTarget
})
```

All five fingerprints come unchanged from genuine Capability 5 output. They
must not be recomputed using a new native normalization.

Each receipt includes the entire required original support for its topic:

| Topic | Required originals |
| --- | --- |
| Scope/native bindings | Qualified identity joins; assignment, all contributing bindings, package and selected approval mappings |
| Measure/baseline | Target rule/measure/document clauses; account, direct balance and denomination |
| Price recognition | Native risk/scenario support and current price-recognition assertion |
| Each charge | Exact native charge and its recognition/aggregation assertion |
| Cost/rounding | Category completeness, fee aggregation, universal rounding and financing horizon |
| Financial coverage | Universe, actors, responsibilities, reports, revisions and all seven categories |
| Interpretation revisions | Inventory coverage and complete required lineage/record support |
| Scenario/settlement | Native coordinates, endpoint, horizon, continuity and full settlement meaning |

Topic references must be in that receipt, not merely elsewhere in the inventory.
Extra valid references are allowed. A well-formed receipt without full topic
support yields UNKNOWN and cannot replace an empty assertion support list or
missing mapping. Generic approval cannot replace per-charge receipts.

The mandate interval contains T for establishment; null end is explicitly open.
Context knowledge boundary is K. Require admitted_at <= available_at <= K and
all supplied/consumed original/native observations no later than admission.
Wrong pins, invalid chronology, duplicate targets, nonexistent charge targets,
ADMITTED with empty/dangling/wrong-hash/unavailable references reject. Unknown
required publication availability remains unresolved. Missing/UNRESOLVED
admission yields UNKNOWN. An expired/future mandate yields UNKNOWN.

With no composition owner all six contexts must be null. With no projection
evidence the sixth context must be null. Orphaned contexts reject.

The host supplies admission independently of request production. A dictionary
named trusted does not establish independence. This function checks structure,
binding and chronology; it cannot authenticate its caller, host or provider.

### Causality, applicability and modeled settlement horizon

The endpoint assumes native modeled entry/stop coordinates, complete entry and
stop-close settlement, all modeled debits recognized exactly once, and no
remaining related position/unsettled amount. Completion is strictly before H.
It is hypothetical, not a future observation or predicted fill time.

All supplied observations, known publications, cutoffs and admissions must be
causally available by K, including unused originals and historical/future
records. Post-K material rejects. Require known publication <= observation,
known cutoff <= containing observation, supporting original observation <=
assertion/record observation, and nested observation <= inventory observation <= K.

Native original mapping deadlines remain historical: document observation;
manifest observation for assignment/binding; interpreted_at for package/rule/
measure; approval observation; original account observation. New recognition of
native risk facts can be supported at current declaration observation without
altering risk-owner chronology. Do not backdate newly acquired documents.

At T a successor participates in lineage selection. A known future successor
strictly before H or governing declaration expiry before H yields UNKNOWN.
Changes/expiry exactly at H cover the half-open horizon; later changes do not
block it. Expiry at or before T yields UNKNOWN without revival. Known accounting
or charge applicability ending/changing before H prevents establishment.
Threshold-only daily resets do not themselves change balance. Candidate expiry
is not the settlement deadline; terminal-entry assumptions do not prove stop
settlement. Governance approval intervals do not become authorization leases.

Future-effective information already observed by K is allowed without early
activation. Future observations are forbidden. No unforeseen future event is
claimed absent as observed truth: no unrelated event is a conditional assumption.

### Exact mathematical descriptor and support

```text
ProjectionBasis = {
  kind: EXACT_MODELED_SETTLED_BALANCE_V1,
  baseline_amount: canonical signed decimal string,
  currency: Currency,
  risk_function: complete unchanged NativeRiskFunction,
  support: complete unchanged NativeGrid,
  measure_target: MeasureTarget,
  scenario: Scenario
}
NativeGrid = {
  quantity_unit: Text,
  domain: {kind: REGULAR_GRID, origin: native decimal string,
           increment: native positive decimal string,
           first_index: canonical nonnegative integer string,
           last_index: canonical nonnegative integer string}
}
NativeRiskFunction = {
  model: POSITIVE_QUANTITY_LINEAR_PLUS_MINIMUM_AFFINE_CHARGES_V1,
  quantity_unit: Text, pnl_currency: Currency,
  maximum_supported_quantity: native positive decimal string,
  zero_quantity_loss: "0", price_loss_per_quantity_unit: native decimal string,
  charges: NativeCharge[]
}
NativeCharge = {
  charge_id: Text,
  category: opening_commission|closing_commission|other_charges|financing,
  basis: SOURCE_SCHEDULE|SUPPORTED_SCENARIO_ENVELOPE,
  currency: Currency, quantity_unit: Text,
  fixed: native nonnegative decimal string,
  per_unit: native nonnegative decimal string,
  minimum: native nonnegative decimal string
}
```

The copied native type permits envelopes; established local descriptors do not.
Support is exactly Capability 5 composed_domain, finite with inclusive native
indices. First index zero is valid if quantity is positive. No grid translation,
enumeration, selected quantity, point-evaluation API or out-of-support claim is
introduced. For r, d, a, m_i, f_i, p_i from those unchanged owners:

```text
q(n) = r + n*d
R(q) = a*q + sum(max(m_i, f_i + p_i*q))
B_scenario(q) = B_current - R(q)
```

B_current is solely the original snapshot balance. Fixed/minimum branches remain
symbolic. Decimal grammar is -?(0|[1-9][0-9]*)(\.[0-9]+)?. Local canonical output
removes trailing fractional zeros/empty fraction and maps negative zero to 0.
Index grammar is 0|[1-9][0-9]*. No exponents, plus signs or nonfinite values.
Exact integer/rational interpretation and chunked huge-integer conversion avoid
floating money arithmetic, ambient Decimal precision and process-wide setting
changes. This owner needs no monetary point computation to return the exact
symbolic descriptor. Zero/negative modeled balances remain valid factual values.

### Outcomes, deterministic diagnostics and complete result

Outcomes are exactly ESTABLISHED and UNKNOWN; structural failure raises
ValueError. Validate every supplied independent structure and replay present
owners before semantic outcomes. Structural failure takes precedence over
missing prerequisites. Collect independently assessable findings; missing
parents suppress only unassessable descendant noise. Missing context suppresses
individual missing receipts; missing declaration suppresses charge-row noise.
Explicit envelope charges/present effects remain reportable when assessable.

Upstream null/UNKNOWN/NOT_SUITABLE produces local UNKNOWN with exact native
negative/unresolved content preserved. No local NOT_SUITABLE or inferred floor
breach exists. Partial native exclusions outside established C do not invalidate
the projection on C. Establishment requires every local predicate and has only
the positive local reason and no unresolved findings.

Exact reason vocabulary and triggers:

| Reason | Trigger |
| --- | --- |
| CONDITIONAL_BALANCE_PROJECTION_ESTABLISHED | All establishment predicates pass |
| OWNER_MISSING | Null composition pair |
| OWNER_UNKNOWN | Genuine composition UNKNOWN |
| OWNER_NOT_SUITABLE | Genuine composition NOT_SUITABLE |
| NATIVE_UNRESOLVED | Genuine composition retains unresolved findings |
| MEASURE_TARGET_MISSING | Null target |
| PROJECTION_EVIDENCE_MISSING | Null evidence |
| ADMISSION_MISSING | Sixth context absent |
| ADMISSION_NOT_CURRENT | Well-formed mandate does not contain T |
| RECEIPT_MISSING | Required topic/charge receipt absent |
| RECEIPT_UNRESOLVED | Required receipt status UNRESOLVED |
| ORIGINAL_SUPPORT_MISSING | Required mapping, assertion or topic closure absent |
| SOURCE_AVAILABILITY_UNKNOWN | Required consumed publication unavailable |
| CURRENT_BASELINE_UNESTABLISHED | Balance/current state/cutoff not established |
| MEASURE_BINDING_UNRESOLVED | Subject pin or direct selected account/measure relationship unresolved |
| MEASURE_MODEL_UNSUPPORTED | EQUITY, separate adjustment or explicitly non-direct model |
| DENOMINATION_UNRESOLVED | Matching literals lack required semantic admission |
| INTERPRETATION_COVERAGE_UNRESOLVED | Declaration coverage/horizon/cutoff insufficient |
| REVISION_HISTORY_INCOMPLETE | Honestly incomplete inception/roots/predecessors/revisions |
| REVISION_ORDER_UNSUPPORTED | Unsupported backward lineage chronology |
| COMPETING_INTERPRETATIONS | Multiple roots or branches |
| NO_CURRENT_INTERPRETATION | Complete admitted history has no effective record |
| INTERPRETATION_WITHDRAWN | Resolved governing withdrawal |
| INTERPRETATION_EXPIRED | Governing declaration expired at T |
| HORIZON_INTERPRETATION_CHANGE | Known successor/applicability expiry interrupts [T,H) |
| PRICE_RECOGNITION_UNRESOLVED | Not exact once after baseline |
| CHARGE_RECOGNITION_MISSING | No native charge recognition row |
| CHARGE_RECOGNITION_UNRESOLVED | Recognition OTHER/UNKNOWN |
| CHARGE_ALREADY_REFLECTED | Debit already in baseline |
| CHARGE_AGGREGATION_UNRESOLVED | Aggregate native semantics unresolved |
| COST_COVERAGE_UNRESOLVED | Complete exact cost coverage unestablished |
| EXACT_DEBIT_UNESTABLISHED | Native envelope or unsupported exact debit |
| ROUNDING_SEMANTICS_UNRESOLVED | Universal equality-preserving posting unresolved |
| FINANCING_HORIZON_UNRESOLVED | Financing through H/nonapplicability unresolved |
| FINANCIAL_COVERAGE_UNRESOLVED | Actor/source/category/state/revision coverage insufficient |
| FINANCIAL_REPORT_MISSING | Roster source lacks report |
| ADDITIONAL_FINANCIAL_EFFECT_PRESENT | Relevant additional effect present |
| SCENARIO_CONTINUITY_UNRESOLVED | Endpoint/horizon/accounting/settlement unsupported |

Literal currency contradictions, forged pins and malformed references reject
instead of receiving uncertainty codes. Missing admission does not manufacture
every possible accounting uncertainty. Withdrawal/expiry do not become
NO_CURRENT_INTERPRETATION. Reasons sort uniquely; findings sort uniquely by
(reason_code, subject), using evaluator-generated deterministic locations rather
than caller-driven resolvers.

```text
Result = {
  contract, rule_version, assessment_economic_time, knowledge_boundary,
  scope, measure_target, scenario, outcome, reason_codes,
  owner_reference, resolved_record, supported_domain, projection_basis,
  native_diagnostics, unresolved_findings, conditions, limitations,
  reconstruction_evidence, downstream_obligations, source_authentication,
  authority, execution, assessment_identity
}
owner_reference = null | {
  assessment_identity: Text, owner_bundle_sha256: Hash,
  outcome: ESTABLISHED|UNKNOWN|NOT_SUITABLE
}
resolved_record = null | {record_id: Text, kind: DECLARE|WITHDRAW, content_sha256: Hash}
supported_domain = null | NativeGrid
projection_basis = null | ProjectionBasis
native_diagnostics = null | {
  negative_proofs: exact native array,
  native_negative_proof_references: exact native array,
  unresolved_findings: exact native array
}
unresolved_findings = {reason_code: nonpositive local reason, subject: Text}[]
ReconstructionEvidence = {
  request: normalized local Request with preserved complete native pair,
  native_context_fingerprints: {
    trusted_planning_context_sha256: Hash|null,
    trusted_quantity_context_sha256: Hash|null,
    trusted_feasibility_context_sha256: Hash|null,
    trusted_position_effect_context_sha256: Hash|null,
    trusted_position_limit_context_sha256: Hash|null
  },
  projection_evidence_sha256: Hash|null,
  trusted_financial_projection_context_sha256: Hash|null
}
```

Native diagnostic nested schemas/content are inherited unchanged from genuine
Capability 5. Owner reference/diagnostics are null exactly when owner absent.
Resolved record is nonnull only after supported complete lineage and independent
revision admission; it may identify an expired declaration/withdrawal. Supported
domain is nonnull exactly when Capability 5 is ESTABLISHED, even if local UNKNOWN.
Projection basis is nonnull exactly when local ESTABLISHED. Target retains request
nullability. Absent evidence/context fingerprints are null.

### Canonical identity, preservation and detached validation

Use sorted-key compact UTF-8 JSON with ordinary Unicode unescaped, no nonfinite
values/invalid Unicode, and exact bool/int/native numeric distinctions. Finite
native provenance floats retain their original numeric type but never enter
money arithmetic. Preserve all native arrays, decimal/timestamp spellings and
nulls. Normalize only locally owned timestamps/decimals before their hashes.

Local ordering: originals by evidence_id; records by record_id; actors by actor_id;
rosters/reports by inventory_id; category effects by effect_id; charge recognition
by charge_id; roots by record identity; references/mappings by complete canonical
identity; missing/actor IDs by text; admissions by canonical target; findings by
reason_code/subject. Identity-bearing duplicates reject. Native copied arrays
are never sorted by this owner.

assessment_identity is IDENTITY_PREFIX plus SHA-256 of the complete canonical
result before adding assessment_identity. The public validator fully reevaluates
with all six original contexts, compares every supplied field to the expected
canonical result without repairing forged output, and returns a detached copy.
Rehashing altered native/local outputs grants no trust. Inputs, contexts and
all returned nested structures have no mutable aliasing.

### Fixed conditions, limitations, obligations and authority

Exactly eight ordered conditions:

```text
NATIVE_MODELED_ENTRY_AND_STOP_COORDINATES_ASSUMED
COMPLETE_MODELED_ENTRY_AND_STOP_CLOSE
ALL_SCENARIO_AMOUNTS_RECOGNIZED_EXACTLY_ONCE
SETTLEMENT_STRICTLY_BEFORE_DEADLINE
NO_RELATED_UNSETTLED_AMOUNT_OR_POSITION_AT_ENDPOINT
NO_UNRELATED_INTERVENING_FINANCIAL_EVENT
ADMITTED_ACCOUNTING_AND_CHARGE_TERMS_REMAIN_APPLICABLE
NATIVE_RISK_BASIS_CONDITIONS_RETAINED
```

Exactly eleven ordered limitations:

```text
CONDITIONAL_PLANNING_ASSUMPTIONS
REALIZED_LOSS_CEILING_NOT_GUARANTEED
FILL_AND_STOP_EXECUTION_NOT_GUARANTEED
SOURCE_AUTHENTICITY_NOT_VERIFIED
FUTURE_MARKET_AND_SPECIFICATION_CHANGES_NOT_COVERED
NO_AUTHORIZATION_LEASE
MODELED_SETTLEMENT_NOT_OBSERVED
BALANCE_ONLY_EXACT_MODEL
NO_PROJECTION_OUTSIDE_COMPOSED_SUPPORT
PROVIDER_FLOOR_AND_HEADROOM_NOT_ASSESSED
CONTINUOUS_DRAWDOWN_COMPLIANCE_NOT_ASSESSED
```

Exactly seventeen sorted downstream obligations, none marked discharged:

```text
ACCOUNT_PROFIT_LOCK_AND_PAYOUT_ELIGIBILITY
ACTUAL_SETTLEMENT_AND_ACCOUNT_REVALIDATION
ATOMIC_COMMITMENT_AND_RESERVATION_CONTROL
CANDIDATE_VALIDITY
CONTINUOUS_PROVIDER_MEASURE_AND_DRAWDOWN_COMPLIANCE
CURRENT_STATE_MECHANICS_AND_RULE_REVALIDATION
ENTRY_QUANTITY_DOMAIN_MEMBERSHIP
EXECUTION_PATH_AND_PEAK_POSITION_LIMIT_COMPLIANCE
MARGIN_AND_AVAILABLE_CAPITAL_FEASIBILITY
MARKET_ORDER_AND_FILL_FEASIBILITY
MISSION_CONTROL_CURRENT_AUTHORIZATION
ORDER_ACCEPTANCE_AND_PENDING_COMMITMENT_RULES
OTHER_PROVIDER_AND_ACCOUNT_RULE_COMPLIANCE
POSITION_EFFECT_AND_ACCOUNT_RULE_COMPLIANCE
POST_ENTRY_FLOOR_AND_PROVIDER_HEADROOM
QUANTITY_SELECTION_POLICY_AND_SELECTION
RISK_BUDGET_QUANTITY_FEASIBILITY
```

Authority has exactly quantity_selection, budget_approval,
position_effect_compliance, margin_capital_approval, trade_decision,
financial_risk and execution, all built-in false booleans. Numeric zero cannot
impersonate false. Top-level execution is false and source authentication is
NOT_VERIFIED_BY_THIS_CAPABILITY. No selected quantity, BUY/SELL/NO TRADE, floor
headroom judgment, margin/financial authorization, broker order, settlement
guarantee, payout action or authorization lease is returned.

### Acceptance matrix and three-file boundary

Positive tests rebuild genuine shared-original Capability 5 chains and separate
synthetic admissions for LONG/SHORT crossed with NETTING/HEDGING. Cover positive,
zero and negative modeled balances and unequal balance/equity; exact source
schedules; minimum/fixed crossover equality; uncertain fill aggregation;
already-reflected charges; envelopes; EQUITY/separate-adjustment targets;
incomplete actors/sources/reports/revisions; empty lists without complete universe;
all seven present-effect categories; missing target/baseline/measure support;
literal currency rejection versus semantic admission uncertainty; universal
rounding; missing/unresolved/topic-incomplete/per-charge admission; forged pins;
raw-byte/base64/envelope/native-selector attacks; every required mapping;
incomplete roots/predecessors/branches; withdrawal/expiry without revival;
whole replacement; historical old pins; known change before H versus at/after H;
post-K unused material; null/UNKNOWN/NOT_SUITABLE owner with preserved diagnostics;
malformed evidence beside absent owner; huge indices/5,001-place decimals;
zero-index/nonzero/negative-origin grids; no assertion beyond C; rehashed native
and every local output-field tampering; input/context/output isolation; all false
authority and no selection/order/floor/execution. Honest unsupported evidence
yields UNKNOWN; structural contradiction yields ValueError; all predicates
supported yield ESTABLISHED. Tests do not authenticate actual providers.

Implementation scope is exactly:

```text
ADD src/ced_one/business_divisions/trading/xauusd_current_entry_provider_measure_projection_basis.py
ADD tests/test_xauusd_current_entry_provider_measure_projection_basis.py
APPEND ONLY docs/capability_architecture.md
```

No upstream owner/validator/contract, existing test/fixture, runtime, dependency,
registry, export, provider connector, Mission Control or configuration changes.

### External trust and mandatory separate profit lock

Raw-byte/envelope hashing proves content binding; native replay proves
reconstruction; independent host admission accepts bounded source/semantic
propositions. Actual provider authentication remains external. None of those
labels alone authenticates a provider. Uploaded bytes and caller-issued receipts
cannot establish independence. The host must competently admit real source/actor
completeness, document semantics, aggregation and universal posting compatibility;
this pure function does not parse arbitrary documents into those truths. Without
adequate real evidence and independent admission, operational outcome is UNKNOWN.
Even established conditional arithmetic guarantees no actual fill, stop, fees,
settlement or realized loss.

The separate account-authorization capability must preserve configurable
account-specific approximately 4–5% monthly targeting, defined net realized
performance/cycle baseline, durable FROZEN_AWAITING_PAYOUT, no new trades while
locked, safe existing position/order handling, verified payout and explicitly
authorized eligible reactivation, and actual provider/cross-account restrictions.
An established active lock vetoes new-trade authorization regardless of this
projection. This owner implements and bypasses none of that lifecycle.

## Capability 7 — Current Post-Entry Provider Floor & Headroom Assessment v1

### Frozen responsibility, public boundary and authority

This section implements the final normative contract closure (sections A–P).
Capability 7 proves only conditional modeled settled-endpoint native static-floor
predicates over the complete finite C6 quantity domain C. Every supported rule
must govern every q in C and every settlement instant s in [T,H), with invariant
threshold, comparator, measure and mandatory force. The endpoint is exactly
FULLY_SETTLED_MODELED_STOP. T equals K. H is inherited only from genuine C6.
Actual settlement, actual provider compliance, continuous drawdown compliance,
equity projection, authentication, quantity selection, margin/capital approval,
execution and an authorization lease remain outside this owner's responsibility.

The public APIs are:

```python
evaluate_current_post_entry_provider_floor_headroom(
    request, *, trusted_planning_context=None, trusted_quantity_context=None,
    trusted_feasibility_context=None, trusted_position_effect_context=None,
    trusted_position_limit_context=None, trusted_financial_projection_context=None,
    trusted_provider_floor_context=None,
) -> dict

validate_current_post_entry_provider_floor_headroom(
    assessment, request, *, trusted_planning_context=None,
    trusted_quantity_context=None, trusted_feasibility_context=None,
    trusted_position_effect_context=None, trusted_position_limit_context=None,
    trusted_financial_projection_context=None, trusted_provider_floor_context=None,
) -> dict
```

The sole direct upstream pair is provider_measure_projection: {assessment,
request}. Replay it using the public validate_current_entry_provider_measure_
projection_basis validator, forwarding the first six contexts unchanged. No
private upstream validation helper is imported. No replacement native bundle,
balance, risk function, quantity grid, threshold or scenario is accepted.

```text
CONTRACT = trading.xauusd_current_post_entry_provider_floor_headroom.v1
RULE_VERSION = xauusd_current_post_entry_provider_floor_headroom_v1
ADMISSION_CONTRACT = trading.xauusd_current_post_entry_provider_floor_headroom.admission.v1
ADMISSION_RULE_VERSION = xauusd_current_post_entry_provider_floor_headroom_admission_v1
ADMISSION_PURPOSE = PROVIDER_FLOOR_FACT_ADMISSION_ONLY
IDENTITY_PREFIX = current_post_entry_provider_floor_headroom_
```

### Closed primitive, request and original-evidence grammar

Every object below has exactly its listed keys. All keys are required; X? means
X or JSON null, never an omitted key. Arrays are JSON arrays. Text is nonblank
valid Unicode preserved exactly; Hash is 64 lowercase hexadecimal characters;
Nat is a nonnegative JSON integer excluding Boolean; Index matches
0|[1-9][0-9]*; Currency is three uppercase ASCII letters. Decimal is a plain
signed decimal string matching -?(0|[1-9][0-9]*)(\.[0-9]+)?. Normalize owned
insignificant fractional zeros and negative zero. Native JSON and original byte
content retain their original representation.

Time requires an explicit zone, seconds and at most six fractional digits.
Normalize owned times to UTC with six fractional digits and Z. Invalid dates,
leap-second spellings, unknown zones and excess precision reject. Completeness
is COMPLETE|LIMITED|UNKNOWN. Namespace/Source identity labels are claims until
independently admitted; their existence does not authenticate a provider.

```text
Namespace = {source_id: Text, source_contract: Text, source_contract_version: Text}
Source = {source_id: Text, source_contract: Text, source_contract_version: Text,
          source_snapshot_id: Text}
Scope = {
  account: {source_id: Text, source_contract: Text, source_contract_version: Text,
            account_id: Text, environment: DEMO|LIVE, currency: Currency},
  provider_namespace: Namespace, provider_id: Text, venue_id: Text,
  instrument: {source_id: Text, source_contract: Text, source_contract_version: Text,
               environment: DEMO|LIVE, instrument_id: Text},
  entry_direction: LONG|SHORT,
  entry_mechanism: IMMEDIATE_MARKET_ENTRY_SCENARIO_V1, quantity_unit: Text
}
Request = {
  contract: CONTRACT, rule_version: RULE_VERSION,
  assessment_economic_time: Time, knowledge_boundary: Time, scope: Scope,
  provider_measure_projection: {assessment: NativeJSON, request: NativeJSON}?,
  floor_evidence: FloorEvidence?
}
FloorEvidence = {
  source: Source, scope: Scope, source_available_at: Time?, observed_at: Time,
  originals: Original[], native_mappings: NativeMapping[],
  coverage: DeclarationCoverage, records: DeclarationRecord[]
}
Original = {
  evidence_id: Text, source: Source, media_type: Text, content_base64: Text,
  content_sha256: Hash, source_available_at: Time?, observed_at: Time
}
OriginalRef = {evidence_id: Text, envelope_sha256: Hash}
Refs = OriginalRef[]
NativeRef = {kind: NativeKind, owner_bundle_sha256: Hash,
             selector: catalogue-specific object|null, content_sha256: Hash}
NativeMapping = {native_reference: NativeRef, original_reference: OriginalRef,
                 original_locator: Text,
                 relationship: EXACT_DOCUMENT|CLAUSE_SUPPORT|ASSERTION_SUPPORT}
```

Account and instrument environments agree. Evidence scope equals request scope.
When C6 exists, scope and both current times equal its reconstructed output.
When C6 is absent all seven contexts are null. Independent evidence may still be
structurally checked, with empty native mappings and null native subject pins;
it cannot yield a numerical proof. A nonnull seventh context also requires
nonnull floor evidence.

Original content is nonempty canonical padded base64. content_sha256 hashes the
decoded bytes. An OriginalRef hashes the entire normalized Original envelope.
Every original reference resolves, has the correct hash, and was observed by its
containing assertion's observation. Known source publication <= observation <= K.
Child assertions precede their containers. Entries precede reports, which precede
declarations, which precede the floor envelope. Coverage precedes the envelope.
States and cutoffs cannot postdate containing observations. These checks apply
to unused, historical and future-effective material as well. Known post-K
information rejects; unknown publication is structurally allowed but prevents a
proof requiring it. Future economic effect is allowed without early activation.

### Frozen original recovery and bounded native catalogue

```text
P6 = request.provider_measure_projection
CB = P6.request.quantity_composition
FQ = CB.request.risk_budget_feasibility.request
PB = FQ.risk_policy
RB = FQ.risk_basis
AB = PB.request.account_state
GB = PB.request.account_rule_regime
PB,RB = {assessment,request}
AB = {snapshot,snapshot_input}
GB = {assessment,assessment_input}
```

Absent paths remain absent. Owner hashes identify complete preserved original
pairs. Content hashes identify exact original nodes except the genuine replayed
risk function and charges. All array indices address raw original array order.

| Kind | Owner | Exact selector | Target |
| --- | --- | --- | --- |
| COMPOSITION_BUNDLE | CB | null | Complete CB |
| ACCOUNT_BUNDLE | AB | null | Complete AB |
| POLICY_BUNDLE | PB | null | Complete PB |
| REGIME_BUNDLE | GB | null | Complete GB |
| RISK_BASIS_BUNDLE | RB | null | Complete RB |
| RISK_FUNCTION | RB | null | Replayed risk_function |
| RISK_CHARGE | RB | {charge_id: Text} | Replayed charge |
| REGIME_ASSIGNMENT | GB | {assignment_id: Text} | Original manifest assignment |
| REGIME_PACKAGE | GB | {package_id: Text, package_revision: Text} | Original package |
| REGIME_BINDING | GB | {assignment_id: Text, binding_index: Nat} | Original binding |
| REGIME_RULE | GB | {package_id: Text, package_revision: Text, rule_id: Text} | Original rule |
| REGIME_MEASURE | GB | Same as REGIME_RULE | Original body.measure |
| REGIME_DOCUMENT | GB | {evidence_id: Text} | Original manifest evidence |
| REGIME_APPROVAL | GB | {approval_index: Nat} | Original approval |
| REGIME_CLAUSE | GB | See below | Original clause reference |
| POLICY_OPERAND | PB | {operand_index: Nat} | request.provider_operands[index] |
| POLICY_OPERAND_SUPPORT | PB | {operand_index: Nat, evidence_index: Nat} | Operand supporting_evidence[index] |

REGIME_CLAUSE.selector = {container: bounded non-clause NativeRef,
field: EVIDENCE_REFS|COVERAGE_EVIDENCE_REFS|DEFINITION_REFS, clause_index: Nat}.
Allowed combinations are assignment/binding/rule EVIDENCE_REFS; package
EVIDENCE_REFS or COVERAGE_EVIDENCE_REFS; measure DEFINITION_REFS. They address
respectively evidence_refs, coverage.evidence_refs or definition_refs. No other
combination, recursive clause container or arbitrary path exists.

Document mappings use EXACT_DOCUMENT; clauses CLAUSE_SUPPORT; other targets
ASSERTION_SUPPORT. Native document source, known byte hash and known publication
pins match. Clause mappings agree with their document envelope. Missing required
support is UNKNOWN; conflicting known pins reject. Mapping originals precede
the native assertion's deadline: account/manifest observation, package
interpretation, approval observation, or operand/support available_at. A bundle
or function without a native deadline uses envelope observation. Required native
support includes clauses and their documents. Fractional operands include every
original supporting-evidence member. The operand's own embedded native rule
reference remains in the policy owner's hash scheme; it is never replaced by a
C7 hash. Public replay validates its association with the selected native rule.

### Complete provider-source universe

```text
Topic = RULES|EXCEPTIONS_AND_WAIVERS|OVERRIDES_AND_PRECEDENCE|
        REVISIONS_AND_WITHDRAWALS|SCHEDULED_RULE_CHANGES|
        ACCOUNT_PHASE_AND_PACKAGE_CHANGES
RuleUniverse = {
  state_at: Time, source_information_cutoff: Time?,
  economic_from: Time, economic_until: Time,
  source_universe_completeness: Completeness,
  actor_universe_completeness: Completeness,
  actors: Actor[], sources: RuleSource[], reports: SourceReport[],
  entries: SourceEntry[], evidence_refs: Refs
}
Actor = {actor_id: Text, namespace: Namespace,
         role: PROVIDER|ACCOUNT_AUTHORITY|GOVERNANCE|OTHER,
         topics: Topic[], evidence_refs: Refs}
RuleSource = {inventory_id: Text, namespace: Namespace,
              role: RULEBOOK|AGREEMENT|SUPPLEMENTAL|REVISION_LEDGER|OTHER,
              responsibilities: Responsibility[], evidence_refs: Refs}
Responsibility = {actor_id: Text, topics: Topic[]}
ReportKey = {inventory_id: Text, actor_id: Text, topic: Topic}
SourceReport = {
  key: ReportKey, source: Source, state_at: Time, source_information_cutoff: Time?,
  economic_from: Time, economic_until: Time,
  source_available_at: Time?, observed_at: Time,
  inventory_completeness: Completeness, revision_completeness: Completeness,
  starting_basis: FROM_INCEPTION|INCOMPLETE_OR_UNKNOWN,
  entry_ids: Text[], missing_entry_ids: Text[],
  entries_omitted: boolean?, history_truncated: boolean?, evidence_refs: Refs
}
Period = {effective_from: Time?, effective_until: Time?,
          end_status: KNOWN|OPEN_ENDED|UNKNOWN}
SourceEntry = {
  entry_id: Text, report_key: ReportKey, source_record_id: Text, kind: EntryKind,
  effective_period: Period, source_available_at: Time?, observed_at: Time,
  disposition: EntryDisposition, native_rule_refs: NativeRef[],
  related_entry_ids: Text[], evidence_refs: Refs
}
EntryRef = {entry_id: Text, content_sha256: Hash}
EntryDisposition = MAPPED_NATIVE_RULE|SUPPORTING_RULE_EVIDENCE|
                   HISTORICAL_NON_GOVERNING|PROVEN_OUTSIDE_SCOPE|
                   OTHER_OBLIGATION|UNRESOLVED
```

| Topic | Exact allowed EntryKind values |
| --- | --- |
| RULES | RULE |
| EXCEPTIONS_AND_WAIVERS | EXCEPTION, WAIVER |
| OVERRIDES_AND_PRECEDENCE | OVERRIDE, PRECEDENCE |
| REVISIONS_AND_WITHDRAWALS | AMENDMENT, WITHDRAWAL |
| SCHEDULED_RULE_CHANGES | THRESHOLD_CHANGE, COMPARATOR_CHANGE, MEASURE_CHANGE, FORCE_CHANGE |
| ACCOUNT_PHASE_AND_PACKAGE_CHANGES | PACKAGE_CHANGE, PHASE_CHANGE |

Economic coverage intervals are finite and nonempty. Period KNOWN requires a
finite end; other statuses require null end. A known start precedes a known end.
Responsibilities reference actual actors and nonempty subsets of their topics.
Report keys belong to actual responsibilities; report source namespaces match.
Each entry belongs to exactly one report, whose entry_ids equal its supplied
members. source_record_id is unique per report. Entry IDs are globally unique
within a declaration. Missing IDs are disjoint from supplied IDs. Related IDs
exist or are explicitly missing in the referring report; self-relations reject.
EntryRef hashes the whole normalized entry in that declaration.

MAPPED_NATIVE_RULE requires RULE and at least one genuine native rule;
SUPPORTING_RULE_EVIDENCE requires a native rule. Current native references belong
to the selected package. COMPLETE inventory cannot declare missing/omitted
entries. COMPLETE revision history cannot declare gaps, truncation, omissions or
an unknown starting basis. Relations alone do not resolve provider precedence;
the host independently admits source-history interpretation from originals.

Global positive proof requires complete independently admitted source and actor
universes, a provider actor, coverage of all six topics, assignment of every
actor topic to a source, and exactly one current complete report per actual
responsibility/topic. Current state_at and cutoff equal T; reports and coverage
contain [T,H). Native package coverage is COMPLETE. Every native rule has a
mapped source RULE and proved disposition. Every source entry has a proved
source disposition. Unmapped or unsupported relevant requirements remain
unresolved. OTHER_OBLIGATION requires proof that the source requirement is
outside this endpoint-floor proposition and retains its separate obligation.
A caller's declared disposition is never automatically a proved disposition.

### Rule applicability, force, exceptions and exact native operands

```text
Assertion<V> = {status: V, evidence_refs: Refs}
Population = CONTAINS_SCENARIO|DISJOINT|UNKNOWN
Endpoint = EXPLICIT_SETTLED_ENDPOINT|CONTINUOUS_INCLUDES_SETTLED_ENDPOINT|
           OUTSIDE_SETTLED_ENDPOINT|UNKNOWN
Force = MANDATORY_UNCHANGED|NOT_MANDATORY|UNKNOWN
Measure = IDENTICAL|INCOMPATIBLE|UNKNOWN
ExceptionResolution = NONE_APPLICABLE|RESOLVED_WITH_PREDICATE_UNCHANGED|
                      WAIVED_THROUGHOUT|MODIFIES_NATIVE_PREDICATE|UNKNOWN
HorizonStatus = INVARIANT_AS_KNOWN_ON_T_H|KNOWN_RELEVANT_CHANGE_BEFORE_H|UNKNOWN
ThresholdRelationship = NATIVE_COMPATIBLE|INCOMPATIBLE|UNKNOWN
Closure = {
  source_universe_completeness: Completeness, revision_completeness: Completeness,
  source_information_cutoff: Time?, report_keys: ReportKey[],
  entry_refs: EntryRef[], evidence_refs: Refs
}
ExceptionClosure = {
  resolution: ExceptionResolution, closure: Closure, authority_actor_ids: Text[],
  authority_evidence_refs: Refs, precedence_evidence_refs: Refs, evidence_refs: Refs
}
HorizonClosure = {status: HorizonStatus, closure: Closure, evidence_refs: Refs}
ThresholdBinding = {relationship: ThresholdRelationship,
                    initial_reference_operand: NativeRef?, evidence_refs: Refs}
RuleBinding = {
  rule_reference: NativeRef, source_entries: EntryRef[],
  population: Assertion<Population>, endpoint: Assertion<Endpoint>?,
  force: Assertion<Force>?, exceptions: ExceptionClosure?,
  measure: Assertion<Measure>?, threshold: ThresholdBinding?,
  horizon: HorizonClosure?, evidence_refs: Refs
}
```

Bindings name genuine selected-package rules and mapped source RULE entries.
A usable closure has both completeness values COMPLETE, cutoff T, a nonempty
set of complete admitted horizon-covering reports, resolved entry references,
and independently admitted exhaustiveness of every source and actor capable of
defeating that rule proposition. A scoped closure can be complete while an
unrelated part of the global universe remains unknown.

Disposition order is: proved invariant disjoint population ->
DISJOINT_POPULATION; proved invariant endpoint exclusion -> OTHER_OBLIGATION for
supported native ACCOUNT_STATE_REQUIREMENT, INSTRUMENT_ACTION_PERMISSION,
AUTOMATION_PERMISSION, POSITION_LIMIT or ACTION_WINDOW, otherwise
OUTSIDE_SETTLED_ENDPOINT; proved whole-horizon waiver -> WAIVED_THROUGHOUT;
fully supported numerical static floor -> SUPPORTED_STATIC_FLOOR; otherwise
UNRESOLVED. Native effects labels alone establish no endpoint or force fact.

A waiver requires contained population, proved endpoint, NOT_MANDATORY,
WAIVED_THROUGHOUT, complete exception/horizon closures, an actual WAIVER entry,
existing authority actors, nonempty authority/precedence support and independent
whole-domain/whole-horizon admission. Mandatory unchanged force plus a declared
whole-horizon waiver is a structural contradiction. Bare NOT_MANDATORY is unknown.

Numerical support requires native SUPPORTED STATIC_FLOOR, contained population,
a positive endpoint relation, MANDATORY_UNCHANGED, NONE_APPLICABLE or
RESOLVED_WITH_PREDICATE_UNCHANGED exceptions, IDENTICAL measure,
NATIVE_COMPATIBLE threshold, invariant horizon and all receipts/support.
Relevant daily-reset, trailing, EQUITY, conditional, changing and unrepresented
requirements remain unresolved. MODIFIES_NATIVE_PREDICATE supplies no replacement.

IDENTICAL means equality of the complete original measure object: kind,
currency, original ordered definition_refs and cost_treatment. No alias or
currency conversion exists. A false current IDENTICAL claim rejects; honest
incompatibility is UNKNOWN. Only direct BALANCE with supported IN_MEASURE or
NOT_APPLICABLE treatment is supported. SUBTRACT_SEPARATELY is not calculated.
C6 already owns exact accounting recognition and charge coverage.

ABSOLUTE uses the signed original amount and a null initial-reference selector.
INITIAL_REFERENCE_FRACTION uses an original POLICY_OPERAND tagged
INITIAL_REFERENCE for that exact native rule/account/reference/currency, valid
through [T,H), with all original support mapped and admitted. Missing selector
or insufficient interval yields UNKNOWN; wrong selector/binding or falsely
claimed compatible denomination rejects. Preserve signed amount and fraction.
INITIAL_EQUITY is allowed only as a historical threshold operand, never an
EQUITY projection. No amount is supplied by the seventh context.

### Immutable declaration and revision grammar

```text
Subjects = {
  projection_bundle_sha256: Hash?, projection_basis_sha256: Hash?,
  policy_bundle_sha256: Hash?, account_bundle_sha256: Hash?, regime_bundle_sha256: Hash?
}
DeclarationBody = {
  subjects: Subjects, source_information_cutoff: Time?,
  economic_from: Time, economic_until: Time,
  universe: RuleUniverse, rule_bindings: RuleBinding[]
}
RecordRef = {record_id: Text, content_sha256: Hash}
Predecessor = {kind: ROOT}|{kind: UNKNOWN}|{kind: RECORD, record: RecordRef}
DECLARE = {
  record_id: Text, kind: DECLARE, predecessor: Predecessor,
  effective_from: Time, effective_until: Time?,
  source_available_at: Time?, observed_at: Time,
  evidence_refs: Refs, body: DeclarationBody
}
WITHDRAW = {
  record_id: Text, kind: WITHDRAW, predecessor: Predecessor,
  effective_from: Time, source_available_at: Time?, observed_at: Time,
  evidence_refs: Refs
}
DeclarationRecord = DECLARE|WITHDRAW
DeclarationCoverage = {
  economic_from: Time, economic_until: Time, source_information_cutoff: Time?,
  declaration_completeness: Completeness, revision_completeness: Completeness,
  starting_basis: FROM_INCEPTION|INCOMPLETE_OR_UNKNOWN,
  root_records: RecordRef[], missing_record_ids: Text[],
  records_omitted: boolean?, history_truncated: boolean?,
  source_available_at: Time?, observed_at: Time, evidence_refs: Refs
}
```

Each DECLARE replaces the entire preceding interpretation. Nonnull expiry is
strictly after its effective start. WITHDRAW cannot be a root. IDs are unique;
root/parent hashes identify complete normalized records. Every supplied root
appears in coverage. Missing referenced IDs must be explicitly declared missing
and cannot also be supplied. Cycles, self-parenting, false roots, wrong hashes
and unexplained dangling references reject. COMPLETE history contradicting gaps,
unknown predecessors, omissions or truncation rejects. Honest incompleteness,
multiple roots, competing children and backward effective/observation/known
publication ordering are UNKNOWN. A usable chain is connected, complete and
nonbranching from one independently supported root, containing every record.

Select the last lineage record effective at T, with equal effective times ordered
by lineage, never IDs or list order. Coverage must be complete/current at T and
span [T,H). No effective record, a current withdrawal or expired latest declaration
provides a current proof. Never revive a predecessor. A known future successor
or current expiry strictly before H prevents either invariant positive or local
negative proof. A transition exactly at H does not affect [T,H).

Current unexpired native subject pins must match actual owners/basis. Wrong
nonnull pins reject; unavailable subjects have null pins; missing available pins
remain unresolved. Current entry/binding native references resolve against the
selected owner tree. Historical/expired/future body references are checked for
local grammar, hashes, local relationships, originals and causality, but are not
rebound to today's native tree. Historical targets remain inert. Global native
mappings always address today's supplied owners. Required lineage publication
uncertainty remains unresolved.

Provider economic enrollment, phase, package and contributing binding intervals
must support the complete horizon. A relevant native/source transition inside
the horizon prevents the affected proof even if a declaration claims invariance.
A change at T must already be reflected in the current interpretation. Governance
approval expiry is not economic provider-rule expiry. No provider timezone label
is authenticated or converted into an economic boundary by this capability.

### Seventh independent host admission and exact support unions

```text
FloorAdmission = {
  contract: ADMISSION_CONTRACT, rule_version: ADMISSION_RULE_VERSION,
  admission_id: Text, authority_namespace: Namespace, authority_id: Text,
  mandate_id: Text, mandate_revision: positive JSON integer,
  purpose: ADMISSION_PURPOSE, request_content_sha256: Hash,
  knowledge_boundary: Time, effective_from: Time, effective_until: Time?,
  admitted_at: Time, available_at: Time, admissions: Receipt[]
}
Receipt = {
  target: AdmissionTarget, subject_content_sha256: Hash,
  status: ADMITTED|UNRESOLVED, evidence_refs: Refs
}
AdmissionTarget =
  {kind: REGIME_SCOPE}
  |{kind: DECLARATION_REVISION_COVERAGE}
  |{kind: RULE_SOURCE_UNIVERSE}
  |{kind: SOURCE_REPORT, record_id: Text, report_key: ReportKey}
  |{kind: SOURCE_ENTRY_DISPOSITION, record_id: Text, entry_reference: EntryRef}
  |{kind: RuleTopic, record_id: Text, rule_reference: NativeRef}
RuleTopic = RULE_DISPOSITION|RULE_ENDPOINT_FORCE|RULE_EXCEPTIONS|RULE_MEASURE|
            RULE_THRESHOLD|RULE_HORIZON
SixFingerprints = {
  trusted_planning_context_sha256: Hash?, trusted_quantity_context_sha256: Hash?,
  trusted_feasibility_context_sha256: Hash?, trusted_position_effect_context_sha256: Hash?,
  trusted_position_limit_context_sha256: Hash?, trusted_financial_projection_context_sha256: Hash?
}
```

Receipt targets identify genuine supplied subjects; record-specific targets
require DECLARE records. Historical targets cannot support current conclusions.
Targets are unique. Recover the first five fingerprints from genuine C6
reconstruction_evidence.native_context_fingerprints and the sixth from its
trusted_financial_projection_context_sha256. Do not replace these with independently
hashed raw caller contexts. All six are null without an upstream owner.

```text
request_content_sha256 = HJSON(normalized Request)
subject_content_sha256 = HJSON({request_content_sha256,
                               native_context_fingerprints: SixFingerprints,
                               target})
```

All supplied C7 observations precede admission; admitted_at <= available_at <= K.
Knowledge boundary equals K. The mandate interval is nonempty and must contain T
for usable admission; it supplies no lease through H. Missing/stale contexts and
missing/unresolved receipts fail closed. Incorrect request/subject pins, dangling
targets, empty ADMITTED receipts and impossible chronology reject.

For the following table E(node) is its own OriginalRefs in evidence_refs and,
where present, authority_evidence_refs and precedence_evidence_refs. M(native)
is the union of all mappings for the required native nodes, their clauses and
those clauses' native documents. Missing mappings remain unresolved and never
silently shrink a proof. All unions are exact sets of complete OriginalRefs.

| Target | Exact required original support union |
| --- | --- |
| REGIME_SCOPE | Current record E; account bundle, selected assignment/package, every binding contributing at T, their clauses/documents, connected selected approvals |
| DECLARATION_REVISION_COVERAGE | Coverage E and every supplied record's own E |
| RULE_SOURCE_UNIVERSE | Universe/actor/source E and native selected-package coverage clauses/documents |
| SOURCE_REPORT | Report, roster-source and actor E plus E of every supplied member entry |
| SOURCE_ENTRY_DISPOSITION | Entry/report/source/actor E plus its native rule mappings and clauses/documents |
| RULE_DISPOSITION | Binding/population E, bound source-entry support, native rule mapping and clauses/documents |
| RULE_ENDPOINT_FORCE | Rule-disposition support plus endpoint/force E |
| RULE_EXCEPTIONS | Rule-disposition support, exception/authority/precedence E, support of all closure reports/entries |
| RULE_MEASURE | Rule-disposition support, measure E, rule measure/definitions, C6 target measure/definitions, account mapping |
| RULE_THRESHOLD | Rule-disposition support, threshold E, native rule support, original operand and every supporting-evidence mapping for fractional thresholds |
| RULE_HORIZON | Rule-disposition support, horizon/closure E, all closure-report/entry support, selected assignment/package/bindings and clauses/documents |

Support of a referenced report/entry is its table union. An ADMITTED receipt must
have exactly that evidence set; nonempty incomplete or extraneous support yields
RECEIPT_SUPPORT_MISMATCH. Unknown required publication remains unresolved even
with an ADMITTED label. A caller cannot select a smaller support union.

Every proved rule requires REGIME_SCOPE, DECLARATION_REVISION_COVERAGE,
RULE_DISPOSITION and RULE_HORIZON. Endpoint exclusion additionally requires
RULE_ENDPOINT_FORCE; waiver also requires RULE_EXCEPTIONS; numerical floors
require all six rule topics. Bound source entries and closure entries/reports
require their own receipts. An entry also requires its report's receipt. Global
positive establishment additionally requires RULE_SOURCE_UNIVERSE and every
responsibility report and source-entry disposition.

The host independently controls issuer, actual mandate/revision and factual
admission. Local code validates content binding, reconstruction, chronology and
support. External provider authentication remains external. A fully self-consistent
fabricated context cannot be authenticated from its issuer strings or hashes;
untrusted caller contexts must not be promoted into the trusted host argument.
No provider integration, document parser or trusted issuer registry is introduced.
The seventh context cannot repair native UNKNOWN, invent rules/operands, bypass
financial coverage, substitute measures/amounts or authorize a trade.

### Exact finite-grid mathematics and outcome precedence

For established C6 preserve C exactly:

```text
q(n) = origin + n*increment
0 <= L=first_index <= n <= U=last_index < infinity
increment > 0; q(L) > 0
R(q) = a*q + sum(max(m_i, f_i+p_i*q))
B(q) = B0-R(q)
F_r = A_r or I_r*alpha_r
h_r(q) = B0-R(q)-F_r
GREATER_THAN: h_r(q)>0
GREATER_THAN_OR_EQUAL: h_r(q)>=0
```

The native payoff coefficient and adverse distance are positive, so a>0. Native
fixed/minimum/per-unit charges are nonnegative. Every charge is nondecreasing;
R is strictly increasing; each h is strictly decreasing. Negative native origin
and index zero are preserved when q is positive. No index translation occurs.

Failure at L yields empty passing prefix and all-C exclusion; success at U yields
all C passing; otherwise exact logarithmic integer binary search finds the largest
passing J. Passing indices [L,J] and excluded [J+1,U] are inclusive. Intersect
complete predicates by the smallest passing upper index. An empty intersection
of these prefixes implies an individually empty prefix. Never enumerate a large
grid or use float money, epsilon, cents rounding, approximate fee breakpoints or
global numerical-setting mutation. Parse/format huge integer coefficients and
indices in chunks. Exact rational arithmetic preserves signed thresholds,
initial amounts and balances. Negative balance alone is not a rule violation.
Fixed and minimum charges remain in the native risk function exactly once.

Precedence is structural ValueError first, then self-contained NOT_SUITABLE,
then UNKNOWN, then ESTABLISHED. Validate unused material before conclusions.
NOT_SUITABLE requires an independently proved mandatory supported invariant floor
excluding all C, including current declaration/scope, exact original operands,
complete own exceptions/horizon and receipts. Unrelated global unknowns survive
as findings without defeating this proof. No native diagnostic outside C is
promoted into a C7 endpoint breach. Missing/UNKNOWN C6 permits no C7 arithmetic.

ESTABLISHED requires genuine nonempty C, at least one proved mandatory supported
floor, complete two-sided native/source coverage, every relevant rule resolved,
and a nonempty exact conjunction. No supported applicable floor is UNKNOWN.
Partial exclusion with incomplete coverage preserves the suffix witness and
headroom but never approves an aggregate positive complement.

### Closed result, diagnostics, canonical identity and replay

```text
QuantityDomain = {quantity_unit: Text, domain:
  {kind: EMPTY}|{kind: REGULAR_GRID, origin: Decimal, increment: Decimal,
                first_index: Index, last_index: Index}}
Headroom = {
  kind: C6_BALANCE_MINUS_NATIVE_STATIC_FLOOR, projection_basis_sha256: Hash,
  rule_reference: NativeRef, threshold_amount: Decimal, currency: Currency,
  compliant_when: GREATER_THAN|GREATER_THAN_OR_EQUAL,
  initial_reference_operand: NativeRef?
}
RuleDisposition = SUPPORTED_STATIC_FLOOR|DISJOINT_POPULATION|
                  OUTSIDE_SETTLED_ENDPOINT|WAIVED_THROUGHOUT|OTHER_OBLIGATION|UNRESOLVED
RuleResult = {
  rule_reference: NativeRef, disposition: RuleDisposition, reason_codes: ReasonCode[],
  headroom: Headroom?, rule_passing_domain: QuantityDomain?,
  rule_excluded_domain: QuantityDomain?
}
SourceDisposition = {entry_reference: EntryRef, disposition: EntryDisposition,
                     reason_codes: ReasonCode[]}
Conjunction = {kind: STATIC_SETTLED_ENDPOINT_FLOOR_CONJUNCTION,
               support: NativeGrid, rule_references: NativeRef[]}
NegativeProof = {
  kind: ALL_C_EXCLUDED|SUFFIX_EXCLUDED,
  scope: CONDITIONAL_SETTLED_ENDPOINT_ON_C, rule_reference: NativeRef,
  declaration: RecordRef, headroom_sha256: Hash, excluded_domain: QuantityDomain,
  admission_targets: AdmissionTarget[], evidence_refs: Refs
}
Finding = {reason_code: FindingCode,
           subject: {root: REQUEST|TRUSTED_PROVIDER_FLOOR_CONTEXT|UPSTREAM_ASSESSMENT,
                     pointer: JSON-Pointer string}}
OwnerReference = {assessment_identity: Text, owner_bundle_sha256: Hash,
                  outcome: ESTABLISHED|UNKNOWN}
ResolvedRecord = {record_id: Text, kind: DECLARE|WITHDRAW, content_sha256: Hash}
Reconstruction = {request: Request, native_context_fingerprints: SixFingerprints,
                  floor_evidence_sha256: Hash?,
                  trusted_provider_floor_context_sha256: Hash?}
Authority = {quantity_selection: false, budget_approval: false,
             position_effect_compliance: false, margin_capital_approval: false,
             trade_decision: false, financial_risk: false, execution: false}
Result = {
  contract: CONTRACT, rule_version: RULE_VERSION,
  assessment_economic_time: Time, knowledge_boundary: Time, scope: Scope,
  scenario: NativeScenario?, outcome: ESTABLISHED|NOT_SUITABLE|UNKNOWN,
  reason_codes: ReasonCode[], owner_reference: OwnerReference?,
  resolved_record: ResolvedRecord?, supported_domain: NativeGrid?,
  rule_results: RuleResult[], source_dispositions: SourceDisposition[],
  complete_predicate: Conjunction?, passing_domain: QuantityDomain?,
  negative_proofs: NegativeProof[], unresolved_findings: Finding[],
  native_diagnostics: NativeJSON?, native_unresolved_findings: NativeJSON?,
  native_conditions: Text[]?, native_limitations: Text[]?,
  conditions: Text[], limitations: Text[], reconstruction_evidence: Reconstruction,
  downstream_obligations: Text[],
  source_authentication: NOT_VERIFIED_BY_THIS_CAPABILITY,
  authority: Authority, execution: false, assessment_identity: Text
}
```

NativeScenario is complete unchanged C6 {endpoint,settlement_before}; NativeGrid
is its unchanged {quantity_unit,domain:{kind:REGULAR_GRID,origin,increment,
first_index,last_index}}. With no owner, owner/scenario/native fields/support
are null. With an owner, copy scenario and all native diagnostics/conditions/
limitations even for UNKNOWN. native_diagnostics equals C6.native_diagnostics;
native_unresolved_findings equals C6.unresolved_findings. supported_domain exists
only for established C6. Do not rewrite upstream historical ownership.

A locally unique latest record may populate resolved_record even if expired,
withdrawn or not admitted. It is not a proof flag. No unique candidate gives null.
Rule rows cover every selected native rule; missing bindings remain unresolved.
Source rows cover the locally selected unexpired DECLARE's entries; otherwise
empty. Unproved source dispositions output UNRESOLVED. Numerical row fields
are all null unless a supported floor is fully proved. Preserve proved numerical
rows and suffix witnesses despite aggregate UNKNOWN.

complete_predicate exists only for complete global coverage and at least one
supported floor; it may accompany a complete all-C negative. passing_domain is
its exact conjunction. A scoped all-C proof with incomplete global coverage
emits EMPTY passing_domain and null complete_predicate. Other incomplete cases
have null aggregate passing_domain. Empty excluded intervals produce no witness.
Each witness includes exactly its required receipt targets and their support
union; its headroom hash pins the corresponding row's complete descriptor.

The exact closed FindingCode set and trigger classes are:

| Code | Trigger |
| --- | --- |
| OWNER_MISSING | Direct owner absent |
| OWNER_UNKNOWN | Genuine C6 UNKNOWN |
| EVIDENCE_MISSING | Floor evidence absent |
| SOURCE_AVAILABILITY_UNKNOWN | Required publication unknown |
| NATIVE_SUPPORT_MISSING | Required mapping/original/subject support absent |
| ADMISSION_MISSING | Seventh context absent |
| ADMISSION_NOT_CURRENT | Mandate does not contain T |
| RECEIPT_MISSING | Required target absent |
| RECEIPT_UNRESOLVED | Explicit UNRESOLVED receipt |
| RECEIPT_SUPPORT_MISMATCH | Nonempty admitted support differs from exact union |
| DECLARATION_COVERAGE_INCOMPLETE | Declaration coverage incomplete/stale/short |
| REVISION_HISTORY_INCOMPLETE | Honest gaps or incomplete lineage |
| REVISION_ORDER_UNSUPPORTED | Backward lineage chronology |
| COMPETING_DECLARATIONS | Multiple roots/children |
| NO_CURRENT_DECLARATION | No effective current candidate |
| DECLARATION_WITHDRAWN | Latest effective withdrawal |
| DECLARATION_EXPIRED | Latest declaration expired |
| HORIZON_CHANGE | Known relevant transition/expiry before H |
| SOURCE_UNIVERSE_INCOMPLETE | Source/actor/topic/responsibility proof inadequate |
| REPORT_MISSING | Responsibility report absent |
| REPORT_COVERAGE_INCOMPLETE | Report completeness/current/horizon inadequate |
| NATIVE_COVERAGE_INCOMPLETE | Native selected-package inventory incomplete |
| UNMAPPED_SOURCE_ENTRY | Relevant source entry lacks required native mapping |
| SOURCE_ENTRY_UNRESOLVED | Source disposition unproved |
| RULE_BINDING_MISSING | Native rule binding absent |
| RULE_SOURCE_BINDING_MISSING | Mapped source RULE support absent |
| RULE_DISPOSITION_UNRESOLVED | No proved permitted disposition |
| POPULATION_UNRESOLVED | Population proposition unproved |
| ENDPOINT_UNRESOLVED | Endpoint proposition unproved |
| FORCE_UNRESOLVED | Mandatory/waiver force unproved |
| EXCEPTIONS_UNRESOLVED | Exception resolution/closure inadequate |
| RULE_MODEL_UNSUPPORTED | Relevant model outside native static subset |
| MEASURE_UNSUPPORTED | Relevant equity/separate-deduction measure |
| MEASURE_IDENTITY_UNRESOLVED | Exact original identity unproved |
| THRESHOLD_OPERAND_UNRESOLVED | Threshold relationship/operand/interval inadequate |
| HORIZON_UNRESOLVED | Invariant closure unproved |
| NO_SUPPORTED_APPLICABLE_FLOOR | No proved mandatory supported floor |

ReasonCode is precisely FindingCode plus ALL_C_EXCLUDED, SUFFIX_EXCLUDED and
STATIC_ENDPOINT_DOMAIN_ESTABLISHED. Generate semantic failures for existing
subjects; missing parents produce absence findings rather than invented child
subjects. Continue independent branches. Row reasons contain failed shared and
local gates; resolved nonnumeric rows may have empty reasons. Top-level reasons
are the sorted union of local finding codes and proof kinds, plus the positive
code only for ESTABLISHED. Do not import native reason strings into the C7 enum.
Pointers use RFC 6901 escaping and address normalized parent collections/fields
when a child is missing.

Fixed conditions, in order:

```text
C6_SCENARIO_CONDITIONS_RETAINED
SUPPORTED_NATIVE_FLOOR_INTERPRETATIONS_APPLY_AT_ENDPOINT
NO_UNMODELED_RELEVANT_RULE_CHANGE
```

Fixed limitations, in order:

```text
CONDITIONAL_SETTLED_ENDPOINT_ONLY
STATIC_IDENTICAL_BALANCE_FLOORS_ONLY
SOURCE_AUTHENTICITY_NOT_VERIFIED
CONTINUOUS_AND_ACTUAL_PROVIDER_COMPLIANCE_NOT_ESTABLISHED
NO_AUTHORIZATION_LEASE
NO_SELECTION_OR_CAPITAL_APPROVAL
NO_ASSERTION_OUTSIDE_NATIVE_C
NO_VACUOUS_NO_FLOOR_POSITIVE
```

Fixed downstream obligations, lexicographically sorted:

```text
ACCOUNT_PROFIT_LOCK_AND_PAYOUT_ELIGIBILITY
ACTUAL_SETTLEMENT_AND_ACCOUNT_REVALIDATION
ATOMIC_COMMITMENT_AND_RESERVATION_CONTROL
CANDIDATE_VALIDITY
CONTINUOUS_PROVIDER_MEASURE_AND_DRAWDOWN_COMPLIANCE
CURRENT_STATE_MECHANICS_AND_RULE_REVALIDATION
ENTRY_QUANTITY_DOMAIN_MEMBERSHIP
EXECUTION_PATH_AND_PEAK_POSITION_LIMIT_COMPLIANCE
MARGIN_AND_AVAILABLE_CAPITAL_FEASIBILITY
MARKET_ORDER_AND_FILL_FEASIBILITY
MISSION_CONTROL_CURRENT_AUTHORIZATION
ORDER_ACCEPTANCE_AND_PENDING_COMMITMENT_RULES
OTHER_PROVIDER_AND_ACCOUNT_RULE_COMPLIANCE
POSITION_EFFECT_AND_ACCOUNT_RULE_COMPLIANCE
POST_ENTRY_FLOOR_AND_PROVIDER_HEADROOM
QUANTITY_SELECTION_POLICY_AND_SELECTION
RISK_BUDGET_QUANTITY_FEASIBILITY
```

The broader floor/headroom obligation remains because only this conditional
subcase is assessed. Authority's seven fields and result.execution are exact
Boolean false; integer zero cannot substitute.

Preserve native trees, native arrays and original bytes. Normalize only owned
times/decimals/set ordering. Canonical JSON is compact UTF-8, keys sorted by
Unicode order, standard JSON escaping without ASCII escaping. Preserve primitive
types: false, 0 and 0.0 differ. Native finite floats remain provenance only;
reject nonfinite/non-JSON/invalid-Unicode values. Arbitrary integer formatting
uses chunks, with no global digit-limit mutation. Keyed arrays sort by identity:
original/evidence_id; actor/actor_id; source/inventory_id; report/canonical key;
entry/entry_id; record/record_id; binding/canonical native reference;
receipt/canonical target. Other owned sets sort by canonical member. Reject input
duplicate identities/references/mappings/targets; output unions deduplicate exact
members. Findings sort by root,pointer,code; rule rows by native reference; source
rows by entry reference; proofs by rule reference,kind. Fixed arrays retain order.

```text
HJSON(x) = SHA256(canonical UTF-8 JSON(x))
assessment_identity = IDENTITY_PREFIX + HJSON(result without assessment_identity)
```

Raw-byte, normalized-envelope, native-original and embedded owner-native hashes
have distinct subjects/algorithms. The detached validator reruns all seven
contexts and compares every result field with canonical type-preserving equality.
A rehashed forgery is not valid. Both APIs detach every occurrence so neither
input aliases nor repeated output occurrences can mutate another result field.

### Acceptance boundary and separate funded-account profit lock

The dedicated C7 tests reconstruct actual public C6/C5 chains, including the four
LONG/SHORT x NETTING/HEDGING combinations; signed absolute/fractional thresholds
and historical initial equity; strict/inclusive equality; multiple floors;
full/singleton/empty prefixes; fee crossover; extreme precision/huge finite
indices; negative origin/index zero; missing originals and unmapped sources;
unsupported rules; incomplete native/source/actor/report coverage; exceptions,
waivers and scoped negatives; before-H/at-H transitions; historical, expired,
withdrawn and competing declarations; native UNKNOWN and preserved diagnostics;
partial exclusions without optimistic complements; structural defects beside
negative arithmetic; wrong identity/pins; receipt attacks; post-K evidence;
rehashed owner/result tampering; mutation isolation and exact false authority.
Synthetic admissions test local behavior only, never real provider authenticity.

Implementation scope is exactly:

```text
ADD src/ced_one/business_divisions/trading/xauusd_current_post_entry_provider_floor_headroom.py
ADD tests/test_xauusd_current_post_entry_provider_floor_headroom.py
APPEND ONLY docs/capability_architecture.md
```

No existing owner, test, fixture, runtime, dependency, registry, provider connector,
package export or Mission Control change is part of this implementation.

Actual provider authentication and competent independent host admission of real
source/actor completeness, native interpretation, exceptions and universal
horizon applicability remain external. Without adequate evidence and admission,
operational outcome is UNKNOWN. No actual fill, settlement or provider compliance
is guaranteed by a conditional successful calculation.

The mandatory separate funded-account authorization gate retains configurable
account-specific approximately 4–5% monthly targets; net realized profit and
exact payout-cycle baseline; durable FROZEN_AWAITING_PAYOUT; no new entries while
locked; safe existing position/pending-order management; verified payout and
explicitly controlled reactivation; provider/cross-account restrictions. An
established active lock vetoes new trading independently of C7. This capability
implements and bypasses none of that lifecycle and grants no trade authority.

Known entries connected to a native rule through related_entry_ids must have
proved source dispositions before its scoped closure is usable. Relation
components are traversed only to conservatively identify possible relevance;
this does not resolve provider precedence. Unresolved linked waivers, overrides
or changes cannot be omitted from a self-contained negative. Genuinely unrelated
global unknowns remain independent. Findings identify normalized rule/report/
entry objects so equal reason codes on different subjects remain separate.

Owned normalization detaches occurrences before modifying them, so a caller's
alias between a local Period and a native original cannot rewrite preserved
native provenance. REGIME_SCOPE support covers bindings contributing at T;
RULE_HORIZON additionally covers every native binding used across [T,H), including
known future-effective continuations. Missing future binding originals remain
UNKNOWN. Known economic expiry/change reports HORIZON_CHANGE; incomplete
applicability reports HORIZON_UNRESOLVED. Strict JSON validation permits an exact
standard serializer fast path and retains chunk-based arbitrary integer rendering;
no hash or primitive-type semantics change between those paths.

For numerical mandatory force, mapped source RULE intervals must cover the whole
settlement horizon. A rule first effective at H or expired at T cannot establish
current mandatory applicability. Known expiry exactly at H covers the half-open
horizon. These are source-applicability checks in addition to native economic
coverage and independent rule-force/horizon admission.

The current entry-quantity-domain owner canonicalizes provider grid origins to
nonnegative residues before C5/C6. C7 preserves the resulting actual C6 grid,
including genuine index-zero cases; it does not restore provider-declaration
indices. A separate exact-arithmetic test checks negative-origin representation
preservation on the same genuine projected quantities, without forging or mocking
an established native owner. Public positive assessments always use genuine replay.

Known competing native account assignments and different-package bindings are
also checked over [T,H), even when the selected assignment/package remains
open-ended. A proven overlap prevents invariant proof (HORIZON_CHANGE);
potential overlap with unknown applicability remains HORIZON_UNRESOLVED.
Provably historical assertions ending at T and future assertions starting at H
do not overlap this half-open horizon. This checks preserved native information;
it introduces no future-regime selection or replacement floor calculation.

WAIVED_THROUGHOUT also requires the actual admitted WAIVER entries in the
exception closure to cover [T,H). A waiver first effective at H or expired at T
cannot establish current whole-horizon waiver. An actual waiver ending at H
covers this half-open horizon. The independent force, authority, precedence,
exception and horizon receipts remain required; period coverage replaces none
of those gates. Missing waiver applicability stays UNKNOWN.

Only operative SUPPORTING_RULE_EVIDENCE waiver entries can supply that coverage.
A PROVEN_OUTSIDE_SCOPE, HISTORICAL_NON_GOVERNING or OTHER_OBLIGATION source
disposition cannot simultaneously establish a current operative waiver.
Independent unresolved rules retain their own numerical partial exclusions;
the aggregate passing domain remains null while waiver proof is unresolved.

### Observed continuation verification — 2026-11-02

The final focused invocation reconstructed genuine C5/C6 owners and exercised
the complete C7 module after the native-horizon and operative-waiver corrections.
The original native C6 grid is inherited unchanged. The negative-origin helper
check is isolated arithmetic on equivalent proven quantities, never a fabricated
established owner or a replacement for positive public replay.

The following are observed terminal results, all with zero failures and zero
skips. Deselected cases belong only to the targeted invocation.

| Invocation | Observed result | Duration | Exit code |
| --- | --- | --- | --- |
| Final waiver/source-horizon/linked-defeater targets | 14 passed, 309 deselected | 223.70s | 0 |
| Entire final C7 module | 323 passed | 3738.68s | 0 |
| Adjacent C5 quantity-constraint composition module | 126 passed | 740.40s | 0 |
| Adjacent C6 provider-measure projection module | 188 passed | 1712.24s | 0 |
| Seven broader trading modules | 1563 passed | 369.18s | 0 |

The broader invocation covered account-specific risk policy, current entry-to-stop
risk basis, entry quantity domain, risk-budget quantity feasibility, entry
position-effect basis, terminal position limits and trading vertical slice v29.
C5 and C6 were run independently in parallel after the final focused module
passed. The earlier 317-pass C7 invocation preceded the waiver corrections and
does not verify the final source. The earlier combined adjacent invocation was
interrupted at 280 passed (exit 2), and is not a completed regression result.
The preceding unavailable targeted tail remains unverified; no pass is inferred
from its progress output. Full-repository terminal results are reported separately
in the completion report; no full-suite success is asserted by this table.

Verification used PYTHONDONTWRITEBYTECODE=1, PYTHONPATH=src and pytest with its
cache provider disabled. Source and test hashes were checked unchanged across
the final focused run, and the pre-existing architecture prefix remained exactly
318069 bytes. Synthetic admissions establish local contract behavior only;
actual provider authentication, independent host control and the separate funded
account profit-lock gate remain external, mandatory boundaries. All seven
authority fields and result-level execution remain exact Boolean false.

## Capability 8 — As-of Intraday Trailing-Loss Threshold State v1

This append implements the frozen bounded contract, its seven-defect repair,
the dual-boundary/source-roster repair and the final freeze approval. It adds
only the C8 callable library and focused tests. The `current_` spelling in the
module and wire identifiers is a stable identifier, not a live-state claim.

### Owned proposition and public API

For one independently admitted account, currency and unchanged original rule
lifecycle, reconstruct the account-wide balance watermark as of economic T,
using originals and independent admission available by K, with T <= K:

```
B0 = H0 = I
Bj = Bj-1 + all-in admitted atomic full-position-close delta
Hj = max(Hj-1, Bj)
L(T) = Hn - I/10
```

The initial allowance is always I, including an empty positively complete
history or negative closing balances. The snapshot must reconcile to final B.
Every relevant account instrument is included. Calculations use exact rational
arithmetic and canonical finite decimals, without binary floating point,
currency conversion, currency rounding or ambient Decimal precision.

The public entry points in
`current_intraday_trailing_loss_threshold_state.py` are:

```
evaluate_current_intraday_trailing_loss_threshold_state(
    request, *, trusted_context=None) -> dict
validate_current_intraday_trailing_loss_threshold_state(
    value, request, *, trusted_context=None) -> dict
CURRENT_INTRADAY_TRAILING_LOSS_THRESHOLD_STATE.analyze(
    request, trusted_context=None).to_dict() -> dict
```

The host independently chooses the trusted issuer/mandate and passes context as
a separate argument. Issuer labels and serialized receipts do not authenticate
the issuer. No embedded result context or fingerprint substitutes for this
independent argument. Missing admission yields UNKNOWN, subject to earlier
structural errors/findings.

### Closed serialized language

All objects below are sealed; every listed field is required. `X?` means X or
JSON null, never an omitted key. Arrays can be empty unless explicitly required
for establishment. Strict JSON containers and exact primitive types are used;
Boolean never substitutes for an integer. Duplicate native JSON keys, malformed
UTF-8, non-finite numbers, tuple/custom-container coercions and noncanonical
base64 reject.

- Text: nonempty Unicode, no leading/trailing whitespace or surrogate points.
- ID: Text matching `[A-Za-z0-9_.:-]+`.
- Time: valid UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`; no leap seconds.
- Money: exact canonical decimal string, no plus, exponent, leading zeros,
  negative zero, empty fraction or trailing fractional zeros.
- Nat/PosInt: exact JSON integer >=0/>=1; no Boolean.
- Currency: three uppercase ASCII letters.
- Hash: 64 lowercase hexadecimal characters.
- Bytes: canonical padded RFC 4648 base64.
- Pointer: RFC 6901 JSON Pointer, including empty string for the whole root.

HJSON is SHA-256 over UTF-8 of `json.dumps(x, ensure_ascii=True, sort_keys=True,
separators=(",", ":"), allow_nan=False)`. C8's encoder preserves these bytes
for arbitrary-size integers without altering process-wide integer limits.
Object-key order is immaterial; list order is material. Native timestamp
comparisons use their UTC-normalized values, preserving original bundle bytes.

```
Namespace = {source_id: Text, source_contract: Text,
             source_contract_version: Text}
Source = {source_id: Text, source_contract: Text,
          source_contract_version: Text, source_snapshot_id: Text}
Account = {namespace: Namespace, account_id: Text,
           environment: DEMO|LIVE, currency: Currency}
Scope = {account: Account, provider_namespace: Namespace, provider_id: Text,
         program_id: Text, account_type_id: Text, phase_id: Text,
         lifecycle_id: ID}
NativeBundle = {input_json: Bytes, result_json: Bytes}
Request = {contract: "trading.current_intraday_trailing_loss_threshold_state.v1",
           rule_version: "current_intraday_trailing_loss_threshold_state_v1",
           economic_time: Time, knowledge_boundary: Time, scope: Scope,
           account_snapshot: NativeBundle?, provider_regime: NativeBundle?,
           originals: Original[], history: History?,
           support_assertions: SupportAssertion[]}
DocumentIdentity = {namespace: Namespace, document_id: Text,
                    document_revision: Text?}
Original = {evidence_id: ID, source: Source, document: DocumentIdentity,
            media_type: Text, content: Bytes, content_sha256: Hash,
            source_available_at: Time?, observed_at: Time}
OriginalRef = {evidence_id: ID, original_sha256: Hash}
Citation = {evidence_id: ID, locator: Text}
InitialCapital = {amount: Money, currency: Currency, citations: Citation[]}
Rule = {assignment_id: Text, package_index: Nat, rule_index: Nat,
        native_rule_sha256: Hash, effective_from: Time, effective_until: Time?,
        model: CLOSED_POSITION_BALANCE_HIGH_WATERMARK|UNKNOWN,
        deduction: ONE_TENTH_INITIAL_CAPITAL|UNKNOWN,
        lower_bound: INITIAL_CAPITAL|UNKNOWN,
        update: EACH_ATOMIC_FULL_POSITION_CLOSE|UNKNOWN, citations: Citation[]}
SourceMember = {namespace: Namespace, topics: Topic[], citations: Citation[]}
Coverage = {report: OriginalRef, from: Time?, through: Time?,
            source_information_cutoff: Time?, account_wide: COMPLETE|UNKNOWN,
            inception: COMPLETE|UNKNOWN, source_inventory: COMPLETE|UNKNOWN,
            events: COMPLETE|UNKNOWN, revisions: COMPLETE|UNKNOWN,
            ordering: AUTHORITATIVE_TOTAL_ORDER|UNKNOWN,
            expected_event_count: Nat?, exclusions: Exclusions,
            citations: Citation[]}
Exclusions = {rewards_or_withdrawals: ExclusionState,
              deposits_or_credits: ExclusionState,
              reset_or_migration: ExclusionState, capital_change: ExclusionState,
              historical_correction: ExclusionState,
              partial_close_or_deal_posting: ExclusionState,
              unknown_transaction: ExclusionState,
              separate_cost_posting: ExclusionState,
              unresolved_cost: ExclusionState, ambiguous_ordering: ExclusionState,
              rule_change: ExclusionState}
ExclusionState = ABSENT|PRESENT|UNKNOWN
Instrument = {namespace: Namespace, instrument_id: Text}
Close = {position_id: Text, instrument: Instrument, balance_before: Money,
         gross_realized_pnl: Money, commission_delta: Money,
         financing_delta: Money, other_cost_delta: Money,
         net_balance_delta: Money, balance_after: Money}
Event = {event_id: ID, origin: Source, original_record_id: Text,
         occurred_at: Time, sequence: PosInt?, currency: Currency,
         kind: EventKind, close: Close?, citations: Citation[]}
RevisionNotice = {notice_id: ID, origin: Source, original_record_id: Text,
                  effective_at: Time, kind: CORRECTION|REPLACEMENT|WITHDRAWAL|UNKNOWN,
                  citations: Citation[]}
History = {inception: Time?, initial_capital: InitialCapital?, rule: Rule?,
           sources: SourceMember[], coverage: Coverage?, events: Event[],
           revisions: RevisionNotice[]}
```

Topic order is BALANCE_ACTIVITY, POSITION_CLOSURES, ACCOUNT_LIFECYCLE,
RULE_LIFECYCLE, SOURCE_REVISIONS. EventKind is ATOMIC_FULL_CLOSE,
REWARD_OR_WITHDRAWAL, DEPOSIT_OR_CREDIT, RESET_OR_MIGRATION, CAPITAL_CHANGE,
HISTORICAL_CORRECTION, PARTIAL_CLOSE_OR_DEAL_POSTING, UNKNOWN_TRANSACTION,
SEPARATE_COST_POSTING, UNRESOLVED_COST, RULE_CHANGE.

Close is non-null exactly for ATOMIC_FULL_CLOSE. Its signed identities are:
net = gross + commission_delta + financing_delta + other_cost_delta, and
balance_after = balance_before + net. Incorrect arithmetic rejects; unresolved
costs or separate postings do not become zero. Full-close position IDs may not
be reused within the same origin namespace. No prices, leverage, quantities,
partial-close groupings, MT5 deal aggregation or provider transaction semantics
are inferred.

Original document namespace equals its source namespace. Document family key is
(namespace, document_id); version key adds document_revision; capture key adds
the full source reference. Duplicate evidence IDs or capture keys reject. Same
version with different bytes or media type rejects. Different documents in one
snapshot are allowed; same version/bytes across different snapshots is allowed.
More than one revision value in a family, including null alongside named,
returns revision UNKNOWN. Null supplies no revision assurance. There is no v1
revision selection/repair machinery. Content hashes bind decoded bytes; report
original_sha256 binds the entire Original, including identity and timing.
Every citation resolves; semantic relevance is independently admitted.

### Native ownership and dual-boundary chronology

Decode each supplied NativeBundle as strict UTF-8 JSON objects. Call the genuine
public native validators, with (result, input):

- validate_causal_financial_account_state_snapshot
- validate_causal_account_rule_regime_assessment

Each invokes its actual owner analyzer and reconstructs the full native result.
No cached approval replaces replay. The native language is exactly that of the
baseline 55e3693 public owners. Snapshot identity is snapshot_id (no invented
native outcome); regime identity is assessment_id. Raw native arrays remain in
original owner-defined input order, even when native results sort them.

Account ID, environment, currency and observation-source namespace must match
C8 account scope. Regime account namespace/ID/environment must match; known
selected assignment/package provider/program/type/phase mismatches reject.
Namespace correspondence and genuine provider attribution additionally require
independent identity admission; matching labels do not authenticate anything.

Let T=Request.economic_time, K=Request.knowledge_boundary,
R=native regime input.requested_knowledge_boundary, and
S=Coverage.source_information_cutoff. Establishment requires:

```
T <= K
native account requested_evaluation_timestamp = K
native snapshot effective_at = T
T <= snapshot source_available_at <= snapshot observed_at <= K
native regime economic_timestamp = T
T <= R <= K
coverage.from = inception <= T = coverage.through
T <= S <= report source_available_at <= report observed_at <= K
max(all supplied observation times) <= admitted_at <= available_at <= K
context effective_from <= K < context effective_until (or open-ended null)
```

Native regime unique resolution forces its manifest cutoff/observation to R;
R may precede C8 admission/K. No native result is rewritten to a newer boundary.
Observation set includes every C8 original, native account, native manifest,
every native evidence observation and every native approval observation. Source
availability must be known for C8 originals and native account/manifest/evidence
to establish. Native approvals have no publication field; none is invented.
All original observations must be by K. Known publication after observation,
report issuance/observation before its known coverage/cutoff, admission before
observation, reversed intervals or T>K reject. Context availability after K
returns UNKNOWN. A valid snapshot effective at another time returns UNKNOWN.

Known inception>T rejects even with no events. Events require inception <
occurred_at <= T when inception exists, and occurred_at <= T independently.
Inception=T permits a zero-event history. The first close starts at I; an empty
history ends at I. Currency contradictions reject, while chain/snapshot
reconciliation failures return UNKNOWN after admission gates.

The C8 original rule must cover [inception,T], with half-open end >T or null.
Its original native selector is manifest.packages[package_index].rules[rule_index],
with an exact HJSON hash. It must correspond to the selected assignment/package
and an account-wide UNSUPPORTED native rule. Native UNSUPPORTED does not supply
the C8 interpretation: separate original-rule admission does. A missing regime
defers well-formed selector resolution; a malformed selector or invalid selector
against a present regime rejects.

Historical native manifest economic coverage, selected enrollment/phase/package
periods and the known union of same-package bindings must cover [inception,T].
Native periods retain KNOWN/OPEN_ENDED/UNKNOWN and half-open semantics. Touching
same-package intervals may merge; gaps or relevant unknown bounds prevent
establishment. Other assignments or different-package bindings that may overlap
the lifecycle prevent establishment. Current native approval is required at T;
historical trading authorization is not inferred or required by C8.

Economic history is complete through T, not through K. Report cutoff S and
native cutoff R do not waive later-knowledge obligations: trusted ORIGINAL_RULE,
COMPLETE_HISTORY and SOURCE_REVISIONS_AVAILABILITY support must cover relevant
subsequently known evidence through K. Known corrections affecting the supported
history remain unsupported; missing support prevents establishment. An old
report or extended receipt validity is not proof that no newer revision exists.
No evidence observed after T is represented as knowledge available at T, and
no assumption says the balance/watermark/threshold remained unchanged until K.

### Independent admission

```
Target = {kind: TargetKind, event_id: ID?}
SupportAssertion = {target: Target, citations: Citation[]}
Receipt = {target: Target, request_sha256: Hash, assertion_sha256: Hash?,
           original_ids: ID[], decision: ADMITTED|UNRESOLVED}
TrustedContext = {
  contract: "trading.current_intraday_trailing_loss_threshold_state.admission.v1",
  rule_version: "current_intraday_trailing_loss_threshold_state_admission_v1",
  admission_id: ID, authority_namespace: Namespace, authority_id: Text,
  mandate_id: Text, mandate_revision: PosInt, request_sha256: Hash,
  admitted_at: Time, available_at: Time, effective_from: Time,
  effective_until: Time?, receipts: Receipt[]}
```

Always derive these nine targets, in order, with null event_id:

| TargetKind | Independent semantic obligation |
| --- | --- |
| ACCOUNT_PROVIDER_IDENTITY | Original account, namespace, provider/program/type/phase, lifecycle and native correspondence |
| ORIGINAL_RULE | Authoritative original rule, faithful selected-rule interpretation and unchanged lifecycle applicability |
| INITIAL_CAPITAL | Original positive I, currency and inception; not a later balance |
| COMPLETE_HISTORY | Exhaustive source roster/account-wide history, bound report, counts and positive empty-history support |
| HISTORICAL_ORDERING | Original authoritative economic sequence, including same-time ordering |
| BALANCE_RECONSTRUCTION | Exactly-once balance changes, opening I and complete all-in signed costs |
| SNAPSHOT_CONSISTENCY | Same account/currency/lifecycle/as-of time and balance meaning |
| SOURCE_REVISIONS_AVAILABILITY | Original-version identity, exhaustive applicable revisions, causal availability and later knowledge through K |
| EXCLUDED_ACTIVITY_ABSENCE | Positive original coverage of every exclusion, not absence of rows in an unrelated export |

Add EVENT_CLASSIFICATION for every supplied event, ordered by event_id; its
event_id must identify that event. It admits the exact original atomic full
close and all-in balance/cost meaning. No receipt creates/suppresses a target.

Let Q=HJSON(entire request), U=all original evidence IDs in order. Context and
each receipt must bind Q. Receipt assertion_sha256 is HJSON(the corresponding
assertion), or null exactly when no assertion exists. Unknown targets, dangling
citations/IDs, wrong hashes and duplicate identities reject. Establishment
requires one nonempty cited assertion and ADMITTED receipt per required target,
and each receipt.original_ids exactly U. A proper subset returns UNKNOWN;
nonexistent IDs reject. All admitted originals being members does not establish
their target relevance. The external host admits actual authority, semantic
support and completeness; C8 never authenticates provider truth from labels.

### Validation priority, missing parents and diagnostics

Structural order is sealed grammar/order; local identities/hashes/arithmetic/
chronology; public native replay; present-container resolution/native bindings/
conditional source membership; derived target/context/hash/chronology validation.
Any structural failure yields no Result and fixed ValueError text
INVALID_TRAILING_LOSS_INPUT. Such failures precede every UNKNOWN.

An empty source roster defers report/event/revision namespace membership, but
never original/citation/hash validation. A nonempty roster missing a required
namespace rejects. Empty roster or missing Topic returns source-coverage UNKNOWN
at its priority. Missing owners defer only dependent resolution; they never
excuse malformed local grammar or invalid references against present parents.

Semantic gates emit exactly the first finding below; no companions or later
descendants. Pointers address the retained request (default root REQUEST), or
independent TRUSTED_CONTEXT. `i` is the first offending canonical element.

| Priority | Reason | Trigger / pointer |
| --- | --- | --- |
| 1 | ACCOUNT_SNAPSHOT_MISSING | null /account_snapshot |
| 2 | PROVIDER_REGIME_MISSING | null /provider_regime |
| 3 | HISTORY_MISSING | null /history |
| 4 | INCEPTION_MISSING | null /history/inception |
| 5 | INITIAL_CAPITAL_MISSING | null /history/initial_capital |
| 6 | RULE_MISSING | null /history/rule |
| 7 | COVERAGE_MISSING | null /history/coverage |
| 8 | NATIVE_REGIME_UNRESOLVED | not native unique approved /provider_regime |
| 9 | RULE_NOT_SUPPORTED | unknown model literal, non-account-wide/non-UNSUPPORTED rule, wrong selected assignment/package or incomplete C8 rule interval /history/rule |
| 10 | NATIVE_HISTORICAL_APPLICABILITY_UNRESOLVED | historical native coverage/continuity fails /provider_regime |
| 11 | SNAPSHOT_BALANCE_MISSING | native balance exactly null /account_snapshot |
| 12 | SNAPSHOT_NOT_AT_ASSESSMENT_TIME | native effective time differs from T /account_snapshot |
| 13 | SOURCE_COVERAGE_INCOMPLETE | empty roster or missing Topic /history/sources |
| 14 | HISTORY_COVERAGE_INCOMPLETE | endpoints/cutoff/completeness/count fail /history/coverage |
| 15 | REVISION_UNSUPPORTED | nonempty inventory /history/revisions/0, else first conflicting document family /originals/i |
| 16 | EXCLUDED_ACTIVITY_UNRESOLVED | first non-ABSENT exclusion /history/coverage/exclusions/field |
| 17 | EVENT_UNSUPPORTED | first non-atomic-full-close /history/events/i |
| 18 | ORDER_UNRESOLVED | null/gapped sequence, decreasing time or non-authoritative declaration /history/events |
| 19 | ORIGINAL_AVAILABILITY_UNKNOWN | null publication /originals/i/source_available_at |
| 20 | NATIVE_AVAILABILITY_UNKNOWN | account, manifest, then evidence-by-ID null publication /account_snapshot or /provider_regime |
| 21 | SUPPORT_INCOMPLETE | missing assertion/citations/report citation /support_assertions |
| 22 | ADMISSION_MISSING | null context, root TRUSTED_CONTEXT pointer empty string |
| 23 | ADMISSION_NOT_CURRENT | availability>K, else start>K, else end<=K; context /available_at, /effective_from or /effective_until |
| 24 | RECEIPT_MISSING | missing target receipt, context /receipts |
| 25 | RECEIPT_UNRESOLVED | first unresolved, context /receipts/i |
| 26 | RECEIPT_MEMBERSHIP_INCOMPLETE | first original membership !=U, context /receipts/i/original_ids |
| 27 | BALANCE_CHAIN_UNRECONCILED | first before != prior balance /history/events/i/close/balance_before |
| 28 | SNAPSHOT_UNRECONCILED | final B != native balance /account_snapshot |

Exclusion priority follows Exclusions field order above. A known excluded event
contradicting ABSENT rejects structurally; PRESENT/UNKNOWN exclusions precede
EVENT_UNSUPPORTED. No artificial fixture skips these earlier gates to force a
later reason. SNAPSHOT_NOT_CURRENT is superseded and is not an accepted code.

### Complete result, identity and ordering

```
Step = {event_id: ID, sequence: PosInt, balance: Money,
        high_watermark: Money, threshold: Money}
State = {inception: Time, as_of: Time, currency: Currency,
         initial_capital: Money, final_balance: Money,
         high_watermark: Money, threshold: Money, steps: Step[]}
NativeReferences = {
  account_snapshot: {snapshot_id: Text, bundle_sha256: Hash}?,
  provider_regime: {assessment_id: Text, bundle_sha256: Hash}?}
Binding = {target: Target, assertion_sha256: Hash?, receipt_sha256: Hash?,
           original_ids: ID[]}
Finding = {reason_code: Reason,
           subject: {root: REQUEST|TRUSTED_CONTEXT, pointer: Pointer}}
Reconstruction = {request: Request, request_sha256: Hash,
                  trusted_context_sha256: Hash?}
Authority = {quantity_selection: false, budget_approval: false,
             position_effect_compliance: false, margin_capital_approval: false,
             trade_decision: false, financial_risk: false, execution: false}
Result = {
  contract: "trading.current_intraday_trailing_loss_threshold_state.v1",
  rule_version: "current_intraday_trailing_loss_threshold_state_v1",
  temporal_scope: AS_OF_T_USING_EVIDENCE_BY_K,
  economic_time: Time, knowledge_boundary: Time, scope: Scope,
  outcome: ESTABLISHED|UNKNOWN, reason_codes: Reason[], findings: Finding[],
  state: State?, native_references: NativeReferences,
  required_targets: Target[], admission_bindings: Binding[],
  reconstruction_evidence: Reconstruction,
  source_authentication: NOT_VERIFIED_BY_THIS_CAPABILITY,
  authority: Authority, execution: false, assessment_identity: Text}
```

Reason is precisely THRESHOLD_ESTABLISHED plus the table's reason codes.
ESTABLISHED has one success reason, no findings, and State with exactly one step
per event. UNKNOWN has state=null, one reason and one finding, no partial
watermark/threshold and no unconditional positive authenticity/independence
claim. State.as_of and result.economic_time are T; knowledge_boundary is K.

Each native reference is null iff its bundle is absent, even in UNKNOWN;
otherwise it contains the replayed native identity and HJSON(the exact bundle).
There is exactly one binding per derived target in every Result. Missing
assertion/receipt produces a null hash; supplied unresolved/incomplete receipts
remain hashed. Binding.original_ids is always U, never receipt-selected.
Reconstruction retains the exact complete request and independently supplied
context hash (null iff absent), not an embedded substitute trusted context.

assessment_identity is `current_intraday_trailing_loss_threshold_state_` plus
HJSON(the complete result excluding only assessment_identity), including
temporal_scope, every binding, native reference, finding and authority Boolean.
Detached validation repeats native public replay and the complete evaluator
with independent arguments, then compares complete type-sensitive canonical
JSON. Changed hashes or false-to-zero mutations do not pass. A result mismatch
uses fixed ValueError text TRAILING_LOSS_RESULT_MISMATCH; invalid independent
request/context retains INVALID_TRAILING_LOSS_INPUT. Returned data are detached.

| Collection | Identity / required ordering |
| --- | --- |
| Originals | unique evidence ID/capture key, ordered by evidence ID; document conflicts as above |
| Citations | unique (evidence_id,locator), ordered by that tuple |
| Sources | unique namespace triple, ordered by that triple |
| Topics | unique Topic, enumeration order |
| Events | unique event ID, (full origin,original_record_id), known sequence, (origin namespace,position_id); known sequence first ascending, null sequence then event ID |
| Revisions | unique notice ID and (full origin,original_record_id); (effective_at,notice_id) order |
| Targets/assertions/receipts/bindings | unique Target; nine standing kinds then classification by event ID |
| Original-ID membership | unique ID ascending |
| Steps | event/sequence identity, ascending sequence |
| Findings/reasons | singleton by priority, or success reason with no findings |
| Native arrays | original input bytes/order preserved; public owner controls its normalized result |

Text comparisons use Unicode code-point order and exact identity, without case
folding or trimming. Duplicate collections or wrong caller array order reject;
C8 does not silently reorder original data.

### Limits and verification scope

This is a useful delayed factual reconstruction, not current account eligibility.
Consumers retain both T and K, assess intervening changes/freshness separately,
and never present later evidence as information available at T. No equity path,
historical/current breach, daily-loss compliance, margin/capital feasibility,
order acceptance, trading permission or payout eligibility is established.

The seven authority values and top-level execution are exact Boolean false.
The separate funded-account FROZEN_AWAITING_PAYOUT veto remains mandatory.
C8 neither reads nor mutates that gate and adds no runtime registration or
authorization integration. Prior owners, capabilities 1-7 and their public
validators are unchanged. C5-C7 successful outcomes are not dependencies.

Focused tests use synthetic originals and independently supplied test admission,
and genuine public native replay. They cover complete zero-event and multi-
instrument 1100/1050/1120 histories, delayed T<K, exact costs/decimals/negative
balances, missing owners/history/evidence, temporal/identity conflicts, roster
absence, unsupported activity/revisions, ordering, receipt membership and
binding, retained native unresolved artifacts, result rehash/mutation and exact
false authority. No successful native validation is mocked. Synthetic evidence
establishes software behavior only, never actual FTMO applicability or provider
authenticity. Actual source completeness/semantics and competent host trust
remain explicit external obligations. Full regression and Git publication
require separate authorization.

## Capability 9: As-of Account Equity Versus Intraday Trailing-Loss Threshold v1

### Ownership and public interface

This capability establishes one admitted historical comparison: account equity
E minus the genuinely reconstructed C8 trailing-loss threshold L at economic
time T, using evidence available by knowledge boundary K. It does not establish
continuous compliance, present account eligibility, source authenticity or an
authorization. A negative difference is an ESTABLISHED factual result.

Module: `ced_one.business_divisions.trading.as_of_equity_trailing_loss_threshold_comparison`.
Public functions:

```python
evaluate_as_of_equity_trailing_loss_threshold_comparison(
    request, *, trusted_c8_context=None, trusted_equity_context=None
) -> dict
validate_as_of_equity_trailing_loss_threshold_comparison(
    result, request, *, trusted_c8_context=None, trusted_equity_context=None
) -> dict
```

The independently supplied contexts are host trust inputs, never selected from
the request or a caller-supplied result. C8 is replayed with its genuine public
`validate_current_intraday_trailing_loss_threshold_state`; the exact account
snapshot embedded in that C8 request is additionally replayed with the public
`validate_causal_financial_account_state_snapshot`. There is no alternative
snapshot, private-owner shortcut, cached approval or fingerprint-only replay.
C1-C8, native validators, runtime and risk policy remain unchanged.

Constants:

```text
contract = trading.as_of_equity_trailing_loss_threshold_comparison.v1
rule_version = as_of_equity_trailing_loss_threshold_comparison_v1
admission contract = trading.as_of_equity_trailing_loss_threshold_comparison.admission.v1
admission rule_version = as_of_equity_trailing_loss_threshold_comparison_admission_v1
identity prefix = as_of_equity_trailing_loss_threshold_comparison_
temporal_scope = AS_OF_T_USING_EVIDENCE_BY_K
source_authentication = NOT_VERIFIED_BY_THIS_CAPABILITY
```

### Sealed grammar and canonical identities

Every object below has exactly its listed keys, all required. Nullable fields
use explicit null; no omitted-key defaults, extra keys, floats, non-JSON values,
duplicate JSON object keys or Unicode surrogates are accepted. Native nested
JSON is subject to the complete existing public owner schemas at baseline
`1f6a8f0101169c4fe6820316d022cd3eef798fb5`, without a second invented schema.

Primitive definitions:

- Text: nonempty UTF-8 string without leading or trailing whitespace.
- ID: Text matching `[A-Za-z0-9_.:-]+`; Currency: `[A-Z]{3}`.
- Nat and PosInt: exact JSON integers at least zero and one, respectively;
  Boolean values are not integers for these purposes.
- Time: valid UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`, with exactly six fractional digits.
- Money: string matching `-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?`, excluding `-0`.
  There is no precision limit imposed on C9 money or integer fields.
- Bytes: canonical padded RFC 4648 base64 string. Content hashes are SHA-256 of
  decoded bytes. Hash: 64 lowercase hexadecimal characters.
- H(value): SHA-256 of UTF-8 canonical JSON equivalent to `json.dumps(value,
  ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)`.
  Integers retain arbitrary precision without changing process-wide limits.
  Array order and exact Boolean versus integer types are preserved.

```text
Namespace = {source_id:Text, source_contract:Text, source_contract_version:Text}
Source = {source_id:Text, source_contract:Text, source_contract_version:Text,
          source_snapshot_id:Text}
Account = {namespace:Namespace, account_id:Text, environment:DEMO|LIVE,
           currency:Currency}
Scope = {account:Account, provider_namespace:Namespace, provider_id:Text,
         program_id:Text, account_type_id:Text, phase_id:Text, lifecycle_id:ID}
C8Dependency = {request_json:Bytes, result_json:Bytes}
Document = {namespace:Namespace, document_id:Text, document_revision:Text|null}
Original = {evidence_id:ID, source:Source, document:Document, media_type:Text,
            content:Bytes, content_sha256:Hash, source_available_at:Time|null,
            observed_at:Time}
OriginalRef = {evidence_id:ID, original_sha256:Hash}
Roles = {aggregate:OriginalRef|null, definition:OriginalRef|null,
         coverage:OriginalRef|null}
DefinitionPeriod = {effective_from:Time|null, effective_until:Time|null,
                    end_status:KNOWN|OPEN_ENDED|UNKNOWN}
Components = {balance:INCLUDED_ONCE|OMITTED|UNKNOWN,
              floating_pnl:INCLUDED_ONCE|OMITTED|UNKNOWN,
              commissions:INCLUDED_ONCE|NOT_APPLICABLE|OMITTED|UNKNOWN,
              swaps:INCLUDED_ONCE|NOT_APPLICABLE|OMITTED|UNKNOWN,
              other_costs:INCLUDED_ONCE|NOT_APPLICABLE|OMITTED|UNKNOWN}
EquityAssertion = {scope:Scope, economic_time:Time, knowledge_boundary:Time,
                   snapshot_source:Source, snapshot_id:Text,
                   snapshot_bundle_sha256:Hash, amount:Money|null,
                   currency:Currency, originals:Roles,
                   definition_period:DefinitionPeriod,
                   source_information_cutoff:Time|null,
                   account_wide:COMPLETE|UNKNOWN, components:Components,
                   component_integrity:COMPLETE_EXACTLY_ONCE|OMISSION|DUPLICATION|UNKNOWN,
                   source_revisions:NONE|PRESENT|UNKNOWN}
Citation = {evidence_id:ID, start:Nat, end:PosInt}
SupportAssertion = {target:Target, equity_sha256:Hash|null, citations:[Citation]}
Request = {contract:constant, rule_version:constant, economic_time:Time,
           knowledge_boundary:Time, scope:Scope, c8:C8Dependency|null,
           equity:EquityAssertion|null, originals:[Original],
           support_assertions:[SupportAssertion]}
Receipt = {target:Target, request_sha256:Hash, c8_context_sha256:Hash|null,
           assertion_sha256:Hash|null, original_ids:[ID],
           decision:ADMITTED|UNRESOLVED}
EquityTrustedContext = {contract:admission constant, rule_version:admission constant,
                        admission_id:ID, authority_namespace:Namespace,
                        authority_id:Text, mandate_id:Text, mandate_revision:PosInt,
                        request_sha256:Hash, c8_context_sha256:Hash|null,
                        admitted_at:Time, available_at:Time, effective_from:Time,
                        effective_until:Time|null, receipts:[Receipt]}
```

The request and independent equity context are these exact objects. The
independent C8 context is null or the existing sealed C8 trusted context, validated
by its public owner. A nonnull C8 context with absent C8 dependency rejects.
Native JSON bytes must decode to objects with strict JSON types and unique keys;
their original base64 strings remain in the request and dependency hashes.

### Source joins, document versions and equity meaning

T must be no later than K. Equity scope, T, K and currency exactly match the
request. The C8 request scope, T and K also exactly match. C8 preserves its native
snapshot effective time T and account evaluation boundary K, native regime time
T and knowledge boundary R with T <= R <= K, and coverage cutoff S requirements.
C9 does not relax those native or C8 obligations.

When the embedded snapshot exists, the equity assertion binds its full original
source, the public validated result's `snapshot_id`, and H(the exact embedded
native bundle). Both nonnull equity amounts must match the canonical native
value exactly. Missing native equity is never inferred from balance or positions.
The native source namespace must match the request account namespace. Text and
namespace comparisons are exact, without trimming or case folding; C9's Text
restriction also applies to `source_snapshot_id` even where a native owner is
more permissive.

There are at most three local originals. An OriginalRef resolves an existing
local evidence ID and H(the entire envelope), not only its content hash.
Document namespace equals source namespace. Aggregate and coverage originals
belong to the account namespace; definition may belong to account or provider
namespace. Aggregate's full source equals the asserted/native snapshot source.
If aggregate and native publication times are both known, they must match;
their observation times need not match. Every local original must fill a role
for establishment; one original may fill several roles.

Document family is (namespace triple, document_id); version is family plus
document_revision; capture is full Source plus version. Duplicate local captures
reject. The same version with different decoded content or media type rejects
across both C8 and C9. Reusing a capture across owners requires identical entire
envelopes except each owner's local evidence_id. Local IDs are not global IDs.
A null local document revision or multiple versions of a relevant local family
across either owner produces UNKNOWN according to the priority below.

The aggregate is an original account-wide equity statement. The definition
establishes its meaning, currency, effective applicability and component
treatment. Coverage supports complete multi-instrument inclusion and version
review through S9. Balance and floating P/L must each be INCLUDED_ONCE. Costs
must each be INCLUDED_ONCE or independently supported NOT_APPLICABLE. Integrity
must be COMPLETE_EXACTLY_ONCE, account coverage COMPLETE, and source revisions
NONE. These labels alone are not semantic evidence: all required support and
independent admission are mandatory. C9 does not synthesize an equity formula,
sum an incomplete position list, infer provider rules or authenticate the issuer.

Definition KNOWN requires a nonnull end; OPEN_ENDED and UNKNOWN require null end.
Known start/end must satisfy start < end. Establishment requires a known start
at or before T and either OPEN_ENDED or T strictly before the known end.

### Historical chronology and independent admission

S9 is the equity assertion's source_information_cutoff. When known it must
satisfy T <= S9 <= K. Every original observation is at or before K; known source
publication is at or before its observation. Coverage publication, when known,
and observation must be at or after S9. Establishment requires all publication
times known and aggregate/definition publication at or before S9. Publication
after S9 for these two roles yields UNKNOWN, not an invented earlier availability.

Let O contain every supplied local original observation, the normalized native
snapshot observation if present, and the C8 context availability if present.
For a supplied equity context, every o in O must satisfy o <= admitted_at.
The universal condition is true when O is empty; no maximum of an empty set is
evaluated. Missing equity context skips this dependent comparison only. All
independent schema, hash binding and temporal checks still apply.

Admission must precede or equal its availability. A known context end must be
strictly later than its start. Establishment additionally requires availability
by K and both admitted_at and K inside the context's half-open validity period.
The admission context and every receipt bind H(request) and H(C8 trusted context),
the latter null iff that context is absent. Every receipt also binds H(its target's
support assertion), null iff absent. A valid bound context with zero receipts
and no C8/equity/originals/support has a well-defined UNKNOWN / C8_MISSING result.

This is revision review through reported S9, not a latest-known-at-K assertion.
The independent host must not admit evidence it knows was corrected after S9;
it must supply UNRESOLVED or a newly supported request. C9 can detect supplied
conflicts, but cannot detect facts hidden by an untrustworthy host. Later knowledge
is never presented as available at T, and changes between T and K are not assumed
absent.

All five targets always exist, in this order, independently of parent presence,
receipt success or returned outcome:

| Target | Required role citations | Independently admitted obligation |
| --- | --- | --- |
| EQUITY_IDENTITY_BINDING | aggregate, definition | Exact account, currency, lifecycle, snapshot and assessment identity |
| EQUITY_AGGREGATE_MEANING | aggregate, definition | Asserted native amount has the admitted equity meaning |
| EQUITY_ACCOUNT_WIDE_COMPLETENESS | aggregate, coverage | All relevant account instruments and exposures included |
| EQUITY_COST_COMPONENTS | definition, coverage | Required components included exactly once or admitted not applicable |
| EQUITY_SOURCE_VERSION_VALIDITY | aggregate, definition, coverage | Applicable original versions, publication and review through S9 |

Each support assertion binds H(equity), null iff equity is absent. Citations are
nonempty half-open byte ranges satisfying 0 <= start < end <= decoded content
length. A target requires citations covering all its required role IDs; a shared
role ID need only be cited once. Valid byte ranges demonstrate referential support,
not semantic truth. The independently trusted host supplies target-specific
semantic admission. Every admitted receipt must contain the complete sorted
local original ID inventory U. Unknown IDs reject; a proper subset yields UNKNOWN.
C8 originals are bound through the complete C8 dependency and its own admission,
not flattened into C9's local evidence namespace.

### Deterministic rejection, UNKNOWN and results

Structural validation precedes every UNKNOWN gate: exact JSON and request
schema/times/scope; local originals; equity joins/roles/period/cutoff; support
bindings/citations; genuine C8 and embedded native replay; cross-owner document
conflicts; independent equity context/chronology/receipts. Missing parents defer
only comparisons requiring them. They never hide malformed present originals,
invalid byte envelopes, forged replay or misbound contexts/receipts.

Any invalid input raises `ValueError("INVALID_EQUITY_THRESHOLD_INPUT")`. There
is no result for invalid native replay. After structural validation the first
applicable UNKNOWN gate below supplies the sole reason and finding. All later
findings are suppressed. Array index i denotes the first applicable entry in
the required order. Root is REQUEST unless explicitly specified.

| Priority / reason | Exact trigger | Subject pointer |
| --- | --- | --- |
| 1 C8_MISSING | c8 is null | /c8 |
| 2 C8_CONTEXT_MISSING | C8 exists and trusted C8 context is null | C8_TRUSTED_CONTEXT, empty pointer |
| 3 C8_NOT_ESTABLISHED | replayed C8 outcome is not ESTABLISHED | /c8 |
| 4 NATIVE_EQUITY_MISSING | validated native equity is null | /c8 |
| 5 EQUITY_ASSERTION_MISSING | equity is null | /equity |
| 6 EQUITY_AMOUNT_UNDECLARED | equity amount is null | /equity/amount |
| 7 AGGREGATE_ORIGINAL_MISSING | aggregate role is null | /equity/originals/aggregate |
| 8 DEFINITION_ORIGINAL_MISSING | definition role is null | /equity/originals/definition |
| 9 COVERAGE_ORIGINAL_MISSING | coverage role is null | /equity/originals/coverage |
| 10 ORIGINAL_ROLE_COVERAGE_INCOMPLETE | first local original has no role | /originals/i |
| 11 DOCUMENT_REVISION_UNKNOWN | first local revision is null | /originals/i/document/document_revision |
| 12 DOCUMENT_VERSION_CONFLICT | first local family has multiple C8/C9 versions | /originals/i/document |
| 13 SOURCE_REVIEW_CUTOFF_UNKNOWN | S9 is null | /equity/source_information_cutoff |
| 14 ORIGINAL_AVAILABILITY_UNKNOWN | first local publication is null | /originals/i/source_available_at |
| 15 SOURCE_REVIEW_CUTOFF_INSUFFICIENT | aggregate or definition publication exceeds S9 | /equity/source_information_cutoff |
| 16 SOURCE_REVISIONS_UNRESOLVED | source_revisions is not NONE | /equity/source_revisions |
| 17 DEFINITION_NOT_APPLICABLE | unknown start/end status, start after T, or known end at/before T | /equity/definition_period |
| 18 ACCOUNT_WIDE_UNRESOLVED | account_wide is not COMPLETE | /equity/account_wide |
| 19 COMPONENT_TREATMENT_UNSUPPORTED | first component is OMITTED or UNKNOWN | /equity/components/field |
| 20 COMPONENT_INTEGRITY_UNRESOLVED | integrity is not COMPLETE_EXACTLY_ONCE | /equity/component_integrity |
| 21 SUPPORT_INCOMPLETE | target assertion absent or lacks a required role ID citation | /support_assertions |
| 22 EQUITY_ADMISSION_MISSING | trusted equity context is null | EQUITY_TRUSTED_CONTEXT, empty pointer |
| 23 EQUITY_ADMISSION_NOT_CURRENT | availability exceeds K; otherwise admitted_at or K before start; otherwise at/after known end | EQUITY_TRUSTED_CONTEXT, /available_at, /effective_from, or /effective_until in that priority |
| 24 RECEIPT_MISSING | at least one required target lacks a receipt | EQUITY_TRUSTED_CONTEXT, /receipts |
| 25 RECEIPT_UNRESOLVED | first receipt has decision UNRESOLVED | EQUITY_TRUSTED_CONTEXT, /receipts/i |
| 26 RECEIPT_MEMBERSHIP_INCOMPLETE | first receipt's original_ids is a proper subset of U | EQUITY_TRUSTED_CONTEXT, /receipts/i/original_ids |

Missing C8 context is reachable with a genuinely replayable C8 UNKNOWN produced
without that context. A formerly ESTABLISHED C8 result supplied without its
required context fails native detached replay structurally. Missing native
parents are handled by earlier C8 gates rather than invented successful results.
Component order is balance, floating_pnl, commissions, swaps, other_costs.

```text
State = {as_of:Time, currency:Currency, equity:Money, threshold:Money,
         difference:Money, relation:ABOVE|EQUAL|BELOW,
         source_information_cutoff:Time}
C8Reference = {assessment_identity:Text, bundle_sha256:Hash,
               outcome:ESTABLISHED|UNKNOWN}
SnapshotReference = {snapshot_id:Text, bundle_sha256:Hash}
NativeReferences = {c8:C8Reference|null, account_snapshot:SnapshotReference|null}
AdmissionBinding = {target:Target, assertion_sha256:Hash|null,
                    receipt_sha256:Hash|null, original_ids:[ID]}
Subject = {root:REQUEST|C8_TRUSTED_CONTEXT|EQUITY_TRUSTED_CONTEXT,
           pointer:RFC6901 string}
Finding = {reason_code:one UNKNOWN reason above, subject:Subject}
Reconstruction = {request:Request, request_sha256:Hash,
                  c8_trusted_context_sha256:Hash|null,
                  equity_trusted_context_sha256:Hash|null}
Authority = {quantity_selection:false, budget_approval:false,
             position_effect_compliance:false, margin_capital_approval:false,
             trade_decision:false, financial_risk:false, execution:false}
Result = {contract:constant, rule_version:constant, temporal_scope:constant,
          economic_time:Time, knowledge_boundary:Time, scope:Scope,
          outcome:ESTABLISHED|UNKNOWN, reason_codes:[reason], findings:[Finding],
          state:State|null, native_references:NativeReferences,
          required_targets:[Target], admission_bindings:[AdmissionBinding],
          reconstruction_evidence:Reconstruction, source_authentication:constant,
          limitations:[fixed limitation], authority:Authority, execution:false,
          assessment_identity:Text}
```

On establishment, compute D = E - L with exact rational arithmetic and render
canonical finite-decimal Money. Relation is ABOVE for D > 0, EQUAL for D = 0 and
BELOW for D < 0. The sole success reason is COMPARISON_ESTABLISHED, findings are
empty, and state contains T, scope currency, native equity, C8 threshold, D and
S9. UNKNOWN always has state=null and exactly one reason/finding.

C8Reference is null iff request.c8 is null. Otherwise its identity and outcome
come from genuine replay and its bundle hash is H(request.c8), including the
original base64 strings. SnapshotReference is null iff C8 or its embedded
account-snapshot bundle is absent. Otherwise its identity is `snapshot_id` from
the genuine public validated native result, and its hash is H(the exact original
embedded native bundle). Both valid references are retained for UNKNOWN even
when admission fails. Invalid replay never becomes a null reference.

Required targets and admission bindings contain all five entries. Each binding
contains H(the corresponding supplied assertion/receipt), or null if absent,
and always U, irrespective of a receipt's actual membership. Reconstruction
contains the exact detached request and all three input hashes, with null context
hashes iff absent. The fixed limitations, in order, are AS_OF_ONLY,
SOURCE_REVISION_REVIEW_THROUGH_REPORTED_CUTOFF, NO_CONTINUOUS_BREACH_PROOF,
NO_DAILY_LOSS_MARGIN_OR_AUTHORIZATION, NO_SOURCE_AUTHENTICATION.

Assessment identity is the identity prefix plus H(the complete result excluding
assessment_identity), including temporal_scope, references, bindings, limitations
and authority. Detached validation reconstructs from request and independently
supplied contexts, invoking both genuine public owners again, then compares the
entire result with type-sensitive canonical equality. Rehashing an altered
result, changing false to integer zero, or substituting matching labels cannot
bypass reconstruction. Invalid input retains INVALID_EQUITY_THRESHOLD_INPUT;
an altered result raises `ValueError("EQUITY_THRESHOLD_RESULT_MISMATCH")`.
Inputs and returned nested data are detached; no caller mutation is required.

| Collection | Identity and required ordering |
| --- | --- |
| Local originals | unique evidence_id and capture; ascending evidence_id; maximum three |
| Native original arrays | original bytes/order retained; native public owner remains authoritative |
| Support assertions and receipts | unique Target; fixed five-target order; subsets may be supplied |
| Citations | unique (evidence_id,start,end); ascending tuple order |
| Receipt/binding original IDs | unique ID; ascending ID order; bindings always full U |
| Required targets and bindings | exactly all five, fixed target order |
| Findings and reason codes | singleton UNKNOWN or singleton success reason with empty findings |
| Limitations | exactly the five constants in the specified order |

Duplicate or incorrectly ordered input collections reject rather than being
silently normalized. Text ordering is Unicode code-point order.

### Security boundary and focused verification

All seven authority fields and top-level execution are exact Boolean false.
The separate FROZEN_AWAITING_PAYOUT veto remains mandatory and untouched. This
capability grants no trading, execution, margin/capital, daily-loss compliance,
continuous or current equity-compliance, reward or payout permission. A BELOW
result is a historical comparison, not a reconstructed breach history.

Focused tests use synthetic originals and independently supplied synthetic
admission with genuine public C8 and native snapshot replay; successful native
validation is never mocked. They cover BELOW/EQUAL/ABOVE, zero-event and
multi-event C8 dependencies, all 26 UNKNOWN branches, both repaired cases,
delayed evidence and cutoff boundaries, account/currency/lifecycle joins,
document/capture/revision conflicts across owners, missing and tampered evidence,
byte-range and receipt membership, unknown native equity, exact money beyond
Python's default integer conversion limit, rehashed result mutation and
Boolean/integer distinctions. This verifies software behavior, not real FTMO
applicability, authenticated source semantics or an honest external trust host.
Full regression and Git publication require separate authorization.
