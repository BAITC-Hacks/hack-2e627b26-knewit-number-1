# BE #13 — LLM tools, RAG, and clarification contract

## Runtime boundary

The browser calls only the Django BFF. The OpenAI key is read from the backend
environment and is never accepted in an HTTP request, returned to the browser,
placed in a model prompt, or written to application logs.

The OpenAI integration uses the Responses API with strict JSON-schema function
tools and a strict structured planning response. The model cannot construct an
arbitrary HTTP request. Its complete allowlist is:

- `search_catalog(query, mode, limit)` — local index candidate discovery;
- `get_product(product_id)` — live server-side catalog detail;
- `find_analogs(product_id, limit)` — approved lighting matrix plus a live
  detail check for every returned analog;
- `query_knowledge_base(query, language)` — versioned purchase terms.

Every tool argument is validated again by the server. Unknown tools, unknown
fields, booleans used as integer IDs, invalid IDs, and limits above five are
rejected. Tool/catalog text is passed as `untrusted_data` and the developer
instruction explicitly forbids treating it as a command.

## Source and rendering rules

`search_catalog` deliberately removes `price`, `quantity`, `stores`, and
`availability` from candidates. Current price and availability can enter the
final response only from `get_product`, or from `find_analogs` after that tool
has performed its own live detail checks.

The model returns only a plan: response kind, up to five source-backed product
IDs, at most two clarification questions, and an optional recommendation with
its reason. Django verifies every selected ID against tool results and renders
the factual `facts`, `products`, and `sources` fields itself. Recommendations
remain separate from facts. With no usable source, the server discards any
recommendation and returns a safe refusal.

For purchase terms, only the current knowledge-base version is used.
`conflicted` and `missing` entries preserve the qualification and require a
manager; the model cannot pick one conflicting condition.

## Endpoints

- `POST /api/dialog/messages` returns the completed JSON message.
- `POST /api/dialog/messages/stream` returns Server-Sent Events. It emits
  `state`, then an immediate visible `delta` with `phase=progress`, streams the
  rendered answer through `delta` events with `phase=answer`, and finishes with
  `message` and `done`. Errors use the `error` event. Proxy buffering is disabled with
  `X-Accel-Buffering: no`.

The immediate delta gives the client a bounded time-to-first-visible-token
without exposing the model's internal structured plan. The final factual
payload is still assembled server-side after tool completion. TTFT is recorded
as the `dialog_time_to_first_token` latency metric.

## Bounds and failure behavior

- OpenAI connect/read/overall deadline are independently configurable.
- Safe requests retry at most twice with exponential backoff and jitter.
- HTTP 429 observes `Retry-After`; HTTP 401/403 is a critical event and is not
  retried.
- Output tokens, history characters, tool rounds, calls per round, response
  bytes, product variants, and clarification questions all have server bounds.
- Responses are requested with `store=false`.
- If OpenAI is disabled or unavailable, dialog search and the knowledge base
  continue through the deterministic path and the response is marked degraded
  when an enabled LLM failed.

## Configuration

`backend/.env` is loaded without overriding variables already supplied by the
deployment environment. `manage.py test` intentionally does not load this file,
so tests cannot accidentally spend quota or call a live API. Keep these values
only on the backend:

```dotenv
OPENAI_ENABLED=false
OPENAI_API_KEY=
OPENAI_API_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-6-astra
OPENAI_CONNECT_TIMEOUT_SECONDS=1
OPENAI_READ_TIMEOUT_SECONDS=12
OPENAI_DEADLINE_SECONDS=20
OPENAI_MAX_RETRIES=2
OPENAI_RETRY_JITTER_SECONDS=0.15
OPENAI_MAX_OUTPUT_TOKENS=900
OPENAI_MAX_TOOL_ROUNDS=3
OPENAI_MAX_TOOL_CALLS_PER_ROUND=5
OPENAI_MAX_CONTEXT_CHARS=12000
OPENAI_MAX_TOOL_OUTPUT_CHARS=60000
OPENAI_MAX_RESPONSE_BYTES=1000000
```

Use a newly generated project key, then set `OPENAI_ENABLED=true`. Do not add
any `OPENAI_*` secret to `frontend/.env`: frontend environment variables are
browser-visible by design.

Official protocol references:

- https://developers.openai.com/api/docs/guides/function-calling
- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/docs/guides/streaming-responses
- https://developers.openai.com/api/docs/guides/migrate-to-responses

## Verification

```powershell
cd backend
python manage.py check
python manage.py test dialog.tests -v 2
python manage.py test
```

No live OpenAI request is required by the tests. The Responses API transport,
tool calls, retries, source enforcement, and SSE order are covered with mocks
and the deterministic fixture provider.
