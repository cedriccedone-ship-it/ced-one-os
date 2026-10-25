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
