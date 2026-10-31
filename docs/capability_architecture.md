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
