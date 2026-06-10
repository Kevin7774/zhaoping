# Capability Integration Guide

This document is the source of truth for adding new capabilities to this repository.

Current architecture: config-driven service routing with typed Pydantic config validation.

## Current Files

- `config/services.toml`: service and skill registry.
- `app/core/config.py`: loads and validates service/skill configuration.
- `app/providers/`: provider implementations grouped by capability type.
- `app/core/router.py`: resolves service type/name to provider instances.
- `app/core/skill_registry.py`: loads static Python skill dictionaries.
- `app/core/mcp_registry.py`: lists configured MCP services.
- `app/api/main.py`: FastAPI application entrypoint.
- `app/db/task_models.py`: SQLAlchemy task orchestration tables for `tasks` and `agent_events`.
- `app/schemas/tasks.py`: Pydantic task status and audit event schemas.
- `app/core/orchestrator.py`: lightweight AgentRunner plus persistent DBTaskStore.
- `scripts/smoke_external_services.py`: live smoke checks for configured paid/external services.
- `tests/test_static_contracts.py`: low-cost contract tests for config and routing.

If this architecture changes, update this document first. Automation and skills should follow this document over stale assumptions.

## Integration Contract

Business modules should depend on capability interfaces through `ServiceRouter`, not concrete providers.

Allowed business usage pattern:

```python
from app.core.router import get_router

router = get_router()
results = router.search("some_search_service").search("query")
```

Avoid this in business modules:

```python
from some_vendor import SearchClient
```

## Task Orchestration Contract

Agent runs are persisted in `tasks` and `agent_events`.

- Default task database: `TASK_DATABASE_URL`, falling back to `sqlite:///data/tasks.sqlite3`.
- Allowed task statuses: `processing`, `awaiting_human`, `done`, `error`, `cancelled`.
- Allowed audit event types: `step_start`, `tool_call`, `evidence`, `summary`, `human_gate`, `error`, `cancelled`.
- The frontend should prefer `GET /tasks/{task_id}/stream` with native `EventSource`.
- `GET /tasks/{task_id}` remains the 600ms polling fallback.
- `POST /tasks/{task_id}/cancel` records a `cancelled` event and releases any checkpointed human gate.
- `POST /tasks/{task_id}/retry` starts a new task from the original persisted input.
- `POST /tasks/{task_id}/confirm` writes the human decision and resumes checkpointed human-gate tasks. Fixed legacy scenarios and project candidate-evaluation tasks must not keep a runner thread blocked while waiting for HR approval.
- Do not emit raw LLM thought chains. Audit events may include stage summaries, tool calls, evidence, citations, result summaries, and error reasons only.

## Atomic Workflow Control Contract

The four A/B/C/D recruiting scenarios can also be controlled as atomic nodes without replacing the legacy full-run task API.

- `GET /workflow/meta` exposes scenarios and individually controllable nodes derived from `SCENARIO_PLANS`.
- `POST /workflow/sessions` creates a persisted task session with `frontend_state.workflow.mode = "atomic"`.
- `POST /workflow/sessions/{task_id}/nodes/{node_id}/run` executes one node, for example `A.0`.
- `POST /workflow/sessions/{task_id}/nodes/{node_id}/skip` marks one node as skipped without executing its handler.
- `POST /workflow/sessions/{task_id}/nodes/{node_id}/retry` reruns one node and increments its node-level `run_count`.
- Atomic node state is stored in `TaskModel.frontend_state.workflow`; no schema migration is required.
- Atomic execution still emits normal `agent_events` using existing event types, with `data.atomic_node_id` for traceability.
- Node outputs are summarized into workflow `artifacts` so the frontend can pass outputs between A/B/C/D at field level.
- Human-in-the-loop atomic nodes should be run once to create an awaiting draft, then run again with `decision` and optional `edits`.

## JSON Workflow Context And Artifact Contract

JSON workflow `context` is the hot state bag for prompt variables and business flow
state. It should stay small. Do not use it as a long-text document store.

For large step outputs such as raw search results, extracted page text, uploaded
resume text, or generated long drafts, opt into file-backed artifact storage:

```json
{
  "id": "raw_search",
  "type": "search",
  "input": "{{ query }}",
  "output_type": "artifact",
  "output_key": "search_results",
  "metadata": {
    "business_meaning": "raw web search results"
  }
}
```

When `output_type = "artifact"`:

- The normalized raw output is written to
  `WORKFLOW_ARTIFACT_DIR/{task_id}/{artifact_key}.json`.
- `WORKFLOW_ARTIFACT_DIR` defaults to `data/workflow_artifacts`.
- `state.context[output_key]` contains only an `artifact_ref` with key, storage
  type, size, MIME type, and preview.
- `state.artifacts[artifact_key]` contains local file metadata including the
  path, producing step, output key, size, and preview.
- Step audit output uses the same lightweight `artifact_ref`, so task snapshots,
  events, and final results do not persist the raw long payload in the task DB.
- Frontend clients must read full artifact content through
  `GET /tasks/{task_id}/artifacts?path=...`. The API only serves paths that are
  inside `WORKFLOW_ARTIFACT_DIR` and registered on that task snapshot; clients
  must not read backend local filesystem paths directly.

Downstream LLM prompts should normally reference a summary variable such as
`{{ search_summary }}`. If a later step needs raw artifact content, add an
explicit artifact-reading step instead of relying on `{{ search_results }}` to
inline the original long text.

DSL validation enforces this contract before execution. Search steps must declare
`output_type = "artifact"`, while normal short outputs such as LLM summaries,
structured extraction results, and human decisions default to
`output_type = "context"`. The older `metadata.output_storage` flag is still
accepted as a compatibility alias, but new workflow JSON should use
`output_type`.

`structured_extract.schema` is also validated at DSL load time. Supported schema
types are `object`, `array`, `string`, `number`, `integer`, and `boolean`.
Object `required` fields must be declared in `properties`, and nested
`properties`/`items` schemas are checked recursively before the workflow is
accepted.

## Adding A Service

1. Add `[services.<service_name>]` to `config/services.toml`.
2. Set `type` to a capability type such as:
   - `document_parser`
   - `ocr`
   - `embedding`
   - `evaluation`
   - `vector_store`
   - `search`
   - `llm`
   - `structured_output`
   - `mcp`
   - another explicit type if needed
3. Set `provider` to the provider implementation key.
4. Store secrets as environment variable names, for example `api_key_env = "BOCHA_API_KEY"`.
5. Implement provider logic under `app/providers/`.
6. Register provider construction in `app/core/router.py`.
7. Add or update tests.

Evaluation providers should expose deterministic local checks by default. Live LLM
or external judge calls must remain opt-in and must not run from unit tests.

## Current Search And Scraping Integrations

The search stack now includes executable or routable providers for recruiting, academic, social, school/competition, and web snapshot workflows:

- `agent_reach_social_search` (`search` / `agent_reach_social`): executable fan-out provider. Weibo uses `mcporter` direct Weibo search. Bilibili, V2EX, Zhihu, Juejin, CSDN, and SegmentFault use `mcporter` Exa site search. Runtime requirements are `agent-reach`, `mcporter`, and `opencli`.
- `openalex_works_search`, `openalex_authors_search`, `openalex_institutions_search`: OpenAlex providers for papers, authors, institutions, schools, labs, citations, and topics.
- `semantic_scholar_papers_search`, `semantic_scholar_authors_search`: Semantic Scholar Graph API providers for papers, authors, venues, h-index, and citation evidence.
- `education_competition_monitor`: curated monitoring target provider for school/lab pages and competitions such as Tianchi, DataFountain, CCF, ICPC/CCPC, Lanqiao, and Kaggle.
- `opencli_crawl_scrape`: local OpenCLI web reader using `opencli web read --url {url} -f json`. The CLI can be installed while Browser Bridge remains disconnected; live browser-backed reads require the Chrome/Chromium extension.
- `public_web_snapshot_monitor`: writes timestamped snapshot manifests under `data/snapshots/public_web/` using `firecrawl_scrape` as the primary scrape provider and optional `browserbase_session` metadata.

Scenario B candidate sourcing exposes a top-down research trace in the HumanGate
lead preview. The backend groups live sources into market map, technical
evidence, people network, social signal, and school/competition layers. The
trace includes query, services attempted, result counts, missing credentials,
timeouts, and layer-level coverage without exposing secret values or raw
provider payloads. Runtime calls are bounded by a live-provider budget; skipped
sources must be reported as `missing_credentials`, `missing_tool`,
`manual_setup`, or `deferred_by_live_budget` instead of failing silently.

Keep planned/source-catalog entries in `app/skills/search_sources.py` aligned with concrete services in `config/services.toml`.

## Adding A Static Skill

Use `[skills.<skill_name>]` in `config/services.toml` when the capability is static Python data or a local workflow dictionary.

```toml
[skills.robot_capability_standards]
module = "app.skills.tech_space"
entrypoint = "CAPABILITY_STANDARDS"
description = "Canonical capability IDs, keywords, and evaluation nodes."
```

Access it through:

```python
router.skills["robot_capability_standards"]
```

## Verification

Run:

```bash
conda run -n robot_agent python -m compileall app scripts tests
conda run -n robot_agent python -m pytest -q
```

If the ingest path changes, also run:

```bash
conda run -n robot_agent python -m app.rag.ingest_worker --file test_readme.md --candidate-id cand_ai_native_002
```

If the API layer changes, also verify importability:

```bash
conda run -n robot_agent python -c "from app.api.main import app; print(app.title)"
```

If external API credentials are configured and the user explicitly allows live calls, run:

```bash
conda run -n robot_agent python scripts/smoke_external_services.py
```

## Safety Rules

- Do not hard-code API keys, tokens, or private endpoints.
- Do not make paid or live external calls in tests unless explicitly requested.
- Keep candidate data local by default.
- Do not change default providers unless the user requests it.
- Treat `qdrant_mvp_store/`, `__pycache__/`, `.pytest_cache/`, and local test inputs as runtime artifacts.
