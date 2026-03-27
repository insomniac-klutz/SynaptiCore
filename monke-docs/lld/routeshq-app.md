# LLD: routeshq_app

> Container: C3 (synapticore-apps) | Application: RoutesHQ
> HLD Reference: S3 C3.2
> Status: stub (rewrite -- not yet implemented)

## Responsibility

RoutesHQ intent classification POC. Classifies user input into first-query, follow-up, or salutation intents using a single Augmented LLM call per classification. Traditional (not agentic) -- 1 dynamic decision point, below the 3-point threshold for CoALA treatment. Deterministic routing: check salutation first, then branch on `is_first_query` flag.

## Public API

### Classification Function

| Function | Signature | Returns | Notes |
|----------|-----------|---------|-------|
| `classify_intent` | `(request: IntentRequest) -> IntentResponse` | `IntentResponse` | Async. Single entry point. Deterministic routing: salutation check first, then first-query vs. follow-up. Each branch makes exactly 1 LLM call via `llm_provider`. |

### Request / Response Models

| Class | Fields | Notes |
|-------|--------|-------|
| `IntentRequest` | `query: str`, `is_first_query: bool = True`, `context: dict[str, Any] \| None = None` | Input to `classify_intent`. `query` is the raw user text. `is_first_query` controls the classification branch. `context` carries previous SQL, chart config, and intent history for follow-up queries. |
| `IntentResponse` | `intent: FirstQueryIntent \| FollowupQueryIntent \| SalutationIntent`, `raw_llm_output: str`, `model_slug: str` | Output from `classify_intent`. `intent` is the parsed domain object. `raw_llm_output` is the raw LLM string for debugging. `model_slug` is the model that performed classification (for audit/logging). |

### Intent Types (from existing `schema.py`)

These types already exist in `SynaptiCore/Apps/RoutesHQ/intent_classifier/schema.py` and are reused in the rewrite.

| Class | Fields | Notes |
|-------|--------|-------|
| `FirstQueryIntentType` | `str, Enum`: `SQL_ONLY`, `SQL_AND_CHART` | First query subtypes. `SQL_ONLY` is the default on ambiguity. |
| `FollowupQueryIntentType` | `str, Enum`: `MODIFY_SQL_AND_CHART`, `MODIFY_CHART_ONLY` | Follow-up subtypes. `MODIFY_SQL_AND_CHART` is the default on ambiguity. |
| `SalutationType` | `str, Enum`: `GREETING`, `GOODBYE`, `THANKS`, `OTHER` | Salutation subtypes. |
| `Intent` | `raw_query: str` | Base class for all intents. |
| `FirstQueryIntent` | `intent_type: FirstQueryIntentType`, `is_first_query: Literal[True] = True` | Extends `Intent`. |
| `FollowupQueryIntent` | `intent_type: FollowupQueryIntentType`, `is_first_query: Literal[False] = False`, `context: dict[str, Any] \| None` | Extends `Intent`. |
| `SalutationIntent` | `intent_type: SalutationType`, `is_salutation: Literal[True] = True` | Extends `Intent`. |

### Prompt Templates

| Prompt | Used By | Variables | Notes |
|--------|---------|-----------|-------|
| `SALUTATION_SYSTEM_PROMPT` | salutation check | -- | Instructs LLM to classify as `GREETING`, `GOODBYE`, `THANKS`, `OTHER`, or `NOT_SALUTATION` |
| `SALUTATION_HUMAN_PROMPT` | salutation check | `{message}` | User message to classify |
| `FIRST_QUERY_SYSTEM_PROMPT` | first-query classification | -- | Instructs LLM to classify as `SQL_ONLY` or `SQL_AND_CHART` |
| `FIRST_QUERY_HUMAN_PROMPT` | first-query classification | `{query}` | User query to classify |
| `FOLLOWUP_QUERY_SYSTEM_PROMPT` | follow-up classification | -- | Instructs LLM to classify as `MODIFY_SQL_AND_CHART` or `MODIFY_CHART_ONLY` |
| `FOLLOWUP_QUERY_HUMAN_PROMPT` | follow-up classification | `{query}`, `{context}` | User query + conversation context |

Prompt content is carried over from existing `classifier.py` / `classifier_langchain.py`. Guardrails in each prompt constrain LLM output to a single enum value.

## Internal Design

### Key Design Decisions

1. **Single LLM call per classification** -- The salutation check is always the first call. If it returns `NOT_SALUTATION`, a second call classifies the query type. Maximum 2 LLM calls per `classify_intent` invocation, but only 1 per branch (salutation detected = 1 call, query classified = 2 calls total). This is a pipeline, not a loop -- no agentic behavior.
2. **Deterministic routing, not LLM-driven routing** -- The `is_first_query` flag and the salutation-vs-query branch are hard-coded `if/else`. The LLM classifies within a branch, it does not choose the branch. This is intentional: RoutesHQ has exactly 1 dynamic decision point per branch (the enum classification), well below the agentic threshold.
3. **`llm_provider` replaces direct Bedrock calls** -- The existing code uses `ChatBedrock` directly. The rewrite routes through `llm_provider` (C1.2.1) via `LlmConfig`. Provider switching (Bedrock to Gemini to local) becomes a config change.
4. **No LangGraph, no LangChain** -- The existing code has two implementations: a LangChain chain (`classifier_langchain.py`) and a LangGraph graph (`classifier.py`). Both are overengineered for a 2-call pipeline. The rewrite uses plain Python with `llm_provider` calls. No framework dependency.
5. **Intent types reused from `schema.py`** -- The existing Pydantic intent models (`FirstQueryIntent`, `FollowupQueryIntent`, `SalutationIntent`, enum types) are well-designed and reused as-is in the rewrite. They move to `synapticore/apps/routeshq/types.py`.
6. **`IntentResponse` wraps the intent** -- Unlike the existing code that returns bare intent objects, the rewrite wraps in `IntentResponse` to include `raw_llm_output` and `model_slug` for debugging and audit.
7. **Default-on-failure strategy** -- If LLM output cannot be parsed to a valid enum value, each branch falls back to a default: `SQL_ONLY` for first queries, `MODIFY_SQL_AND_CHART` for follow-ups, `SalutationType.OTHER` for salutations. This matches the existing behavior.
8. **Context formatting** -- The `context_to_string` utility (from existing `utils.py`) converts the context dict to a human-readable string for the follow-up prompt. Reused in the rewrite.

### Module structure

```
synapticore/apps/routeshq/
    __init__.py           # Exports classify_intent, IntentRequest, IntentResponse
    types.py              # IntentRequest, IntentResponse + re-exports of intent enums/models from schema
    prompts.py            # All 6 prompt templates (system + human x 3 branches)
    classifier.py         # classify_intent function, internal helpers
    utils.py              # context_to_string, format_context
```

### Classification flow

```
classify_intent(request: IntentRequest)
    1. Build salutation messages:
       system = SALUTATION_SYSTEM_PROMPT
       human  = SALUTATION_HUMAN_PROMPT.format(message=request.query)
    2. Call llm_provider(llm_config, messages) → salutation_raw
    3. Parse salutation_raw:
       - If NOT_SALUTATION → go to step 4
       - Else → parse SalutationType enum (default: OTHER)
              → return IntentResponse(intent=SalutationIntent(...), ...)
    4. Branch on request.is_first_query:
       - True  → build first-query messages, call llm_provider
                → parse FirstQueryIntentType enum (default: SQL_ONLY)
                → return IntentResponse(intent=FirstQueryIntent(...), ...)
       - False → build follow-up messages with context_to_string(request.context)
                → call llm_provider
                → parse FollowupQueryIntentType enum (default: MODIFY_SQL_AND_CHART)
                → return IntentResponse(intent=FollowupQueryIntent(...), ...)
```

## Dependencies

### Internal
- `C1.2.1 tools/llm_provider` -- All LLM calls (`LlmConfig` + messages → response)
- `C1.1.4 types/common_types` -- `LlmConfig`, `ConversationMessage`, `ConversationRole`, `ProviderError`, `ConfigurationError`

### External
- `pydantic` (BaseModel, Field, Literal) -- Model validation
- `enum` (Enum) -- Intent type enums

### Not depended on (removed in rewrite)
- `langchain-aws` (`ChatBedrock`) -- replaced by `llm_provider`
- `langchain-core` (`ChatPromptTemplate`, `StrOutputParser`) -- replaced by plain string formatting + `llm_provider`
- `langgraph` (`StateGraph`, `MemorySaver`) -- removed, not needed for a 2-call pipeline

## Error Contracts

### Raised by this module
- `ConfigurationError` -- Invalid `LlmConfig` passed in (missing `model_slug`, etc.)

### Propagated from dependencies
- `ProviderError` -- From `llm_provider` if the LLM call fails (rate limit, auth error, timeout)
- `pydantic.ValidationError` -- From `IntentRequest` construction with invalid fields

### Handled internally
- Unparseable LLM output -- If the LLM returns a string that does not match any enum value, the module catches `ValueError` from enum construction and falls back to the default intent type for that branch. No error is raised to the caller.

## Test Plan

### Unit tests (`tests/unit/apps/test_routeshq_app.py`)

**IntentRequest validation:**
- Constructs with `query` only (defaults: `is_first_query=True`, `context=None`)
- Constructs with all fields specified
- Empty `query` string is valid (LLM will classify it)

**IntentResponse:**
- Contains `intent`, `raw_llm_output`, `model_slug`
- `intent` accepts all three intent union members

**classify_intent -- salutation branch:**
- Input "Hello" with mock LLM returning "GREETING" → `SalutationIntent(intent_type=GREETING)`
- Input "Bye" with mock LLM returning "GOODBYE" → `SalutationIntent(intent_type=GOODBYE)`
- Input "Thanks" with mock LLM returning "THANKS" → `SalutationIntent(intent_type=THANKS)`
- Input "Cheers" with mock LLM returning "OTHER" → `SalutationIntent(intent_type=OTHER)`
- Salutation check returns `NOT_SALUTATION` → proceeds to query classification

**classify_intent -- first-query branch:**
- `is_first_query=True`, mock LLM returns "SQL_ONLY" → `FirstQueryIntent(intent_type=SQL_ONLY)`
- `is_first_query=True`, mock LLM returns "SQL_AND_CHART" → `FirstQueryIntent(intent_type=SQL_AND_CHART)`
- `is_first_query=True`, mock LLM returns garbage → fallback `FirstQueryIntent(intent_type=SQL_ONLY)`

**classify_intent -- follow-up branch:**
- `is_first_query=False`, mock LLM returns "MODIFY_SQL_AND_CHART" → `FollowupQueryIntent(intent_type=MODIFY_SQL_AND_CHART)`
- `is_first_query=False`, mock LLM returns "MODIFY_CHART_ONLY" → `FollowupQueryIntent(intent_type=MODIFY_CHART_ONLY)`
- `is_first_query=False`, mock LLM returns garbage → fallback `FollowupQueryIntent(intent_type=MODIFY_SQL_AND_CHART)`
- Context dict is formatted into the prompt via `context_to_string`

**classify_intent -- LLM interaction:**
- Exactly 1 LLM call when salutation is detected
- Exactly 2 LLM calls when salutation check returns `NOT_SALUTATION`
- `LlmConfig` from caller is passed through to `llm_provider` (mock verify)
- `raw_llm_output` in response matches the mock LLM return value
- `model_slug` in response matches `llm_config.model_slug`

**context_to_string:**
- Empty context returns "No previous context available."
- Context with `previous_sql` includes SQL in output
- Context with `previous_chart_config` includes JSON-formatted chart config
- Context with `previous_intents` includes formatted intent history
- Context with all fields includes all sections

**Edge cases:**
- LLM returns enum value with extra whitespace/casing ("  Sql_Only  ") → normalized and parsed
- LLM returns multiline response → first line stripped and parsed
- `context=None` on follow-up query → "No previous context available." in prompt
- `ProviderError` from `llm_provider` propagates to caller

## ADR References

- None pending. RoutesHQ uses `llm_provider` only -- no framework choices required.

## Maturity

All functions: `stub` (rewrite target)
