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
