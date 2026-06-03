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

## Adding A Service

1. Add `[services.<service_name>]` to `config/services.toml`.
2. Set `type` to a capability type such as:
   - `document_parser`
   - `ocr`
   - `embedding`
   - `vector_store`
   - `search`
   - `mcp`
   - another explicit type if needed
3. Set `provider` to the provider implementation key.
4. Store secrets as environment variable names, for example `api_key_env = "BOCHA_API_KEY"`.
5. Implement provider logic under `app/providers/`.
6. Register provider construction in `app/core/router.py`.
7. Add or update tests.

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
