# projects.py API hardening plan

## Context checked

- Router: `app/api/routers/projects.py`
- Schemas: `app/schemas/job.py`, `app/schemas/candidate.py`, `app/schemas/project.py`
- Models: `app/models/job.py`, `app/models/candidate.py`, `app/models/project.py`
- Existing tests: `tests/test_projects_api.py`
- API mount: `app/api/main.py`

## Decisions

- Keep `GET /projects/{project_id}/candidates` as a job-candidate association list because the current response model includes `job_candidate_id`, `job_id`, and `job_title`, and existing tests already assert joined match rows.
- Add `GET /projects/{project_id}/candidates/unique` for de-duplicated candidates instead of changing the existing endpoint in place.
- Fix `GET /projects/{project_id}/jobs` N+1 by replacing per-job statistic queries with portable grouped SQL for counts/averages plus one candidate-status query that is grouped in Python. This avoids PostgreSQL-only functions such as `array_agg` and keeps SQLite tests valid.
- Treat `JobResponse.pipeline_status` as aggregated candidate pipeline state, not a duplicate of `Job.status`. Use a deterministic priority: `awaiting_human` > `processing` > `pending_outreach` > `sourced` > `done` > fallback first non-null status > `job.status` when a job has no candidates.
- Add `skip` / `limit` query parameters to job and candidate list endpoints with conservative bounds.
- Do not implement auth, Redis cache, or materialized views in this task because the repo currently has no user/member model or auth dependency, and caching/stat materialization would introduce new infrastructure outside this narrow route fix.

## Task checklist

- [x] Write failing tests in `tests/test_projects_api.py` for `/jobs` pagination and aggregate statistics without per-job stats queries.
- [x] Write failing tests that prove `pipelineStatus` is derived from `JobCandidate.pipeline_status` priority instead of `Job.status`.
- [x] Write failing tests for `/projects/{project_id}/candidates` pagination while preserving association-list semantics.
- [x] Write failing tests for `/projects/{project_id}/candidates/unique` returning one row per candidate when the same candidate is linked to multiple jobs.
- [x] Write failing tests for empty jobs and empty candidates responses.
- [x] Write failing tests for naive and timezone-aware `created_at` values normalizing to UTC in `GET /projects/{project_id}`.
- [x] Implement a portable job-stat query helper in `app/api/routers/projects.py` using grouped counts/averages and Python-side status aggregation.
- [x] Add `skip` / `limit` parameters with FastAPI `Query` validation to `/jobs`, `/candidates`, and `/candidates/unique`.
- [x] Add a unique-candidate response schema or reuse the smallest compatible schema if an existing one fits.
- [x] Update `JobResponse.pipeline_status` construction to use aggregated candidate status.
- [x] Keep `_project_stats()` behavior unchanged except for typing clarity if needed.
- [x] Run focused tests: `pytest tests/test_projects_api.py -q`.
- [x] Run broader regression relevant to this API: `pytest tests/test_projects_api.py tests/test_seed_db.py tests/test_candidate_evaluation_task.py -q`.
- [x] Add a review section below with final diff summary, test evidence, and deferred risks.

## Risks and boundaries

- Changing `/candidates` to de-duplicate would break current frontend/test contract, so this plan avoids that breaking change.
- `pipeline_status` aggregation is a business rule. The priority list above is explicit and testable, but product owners may later want a different status ordering.
- Query-count assertions can be brittle across SQLAlchemy versions. Prefer checking behavior and helper usage unless a stable SQL-count fixture is straightforward.
- Avoid PostgreSQL-only aggregate functions in this route because the existing tests run against SQLite.
- Auth must be designed separately around a real user identity source and project membership table.
- Redis/materialized views should only be added after measuring route latency and data size under realistic load.

## Review

- Status: implemented.
- Diff summary:
  - `app/api/routers/projects.py`: added pagination to jobs/candidates, added `/candidates/unique`, replaced per-job stats queries with portable grouped rollups plus Python status aggregation, and changed job `pipeline_status` to derive from candidate pipeline state.
  - `app/schemas/candidate.py`: added `UniqueCandidateResponse`.
  - `tests/test_projects_api.py`: added red/green coverage for pagination, bounded query count, status aggregation, unique candidates, empty lists, and UTC datetime behavior.
  - `frontend/src/capabilities/capabilityRegistry.js` and `tests/test_static_contracts.py`: productized the new OpenAPI path.
  - `tasks/lessons.md`: recorded the SQLite/PostgreSQL aggregate portability lesson.
- Test evidence:
  - RED check: `.venv/bin/python -m pytest tests/test_projects_api.py -q` failed with 7 expected failures before implementation.
  - Focused API: `.venv/bin/python -m pytest tests/test_projects_api.py -q` passed with 12 tests.
  - API regression: `.venv/bin/python -m pytest tests/test_projects_api.py tests/test_seed_db.py tests/test_candidate_evaluation_task.py -q` passed with 15 tests.
  - API import: `.venv/bin/python -c "from app.api.main import app; print(app.title)"` printed `Robot Talent Agent MVP`.
  - Compile: `.venv/bin/python -m compileall app tests` passed.
  - Full backend/contracts: `.venv/bin/python -m pytest -q` passed with 123 tests.
  - Frontend unit tests: `pnpm test` passed with 20 tests after aligning `frontend/src/features/projects/state.test.ts` with the current `FilterCriteria` shape.
- Known unrelated blocker:
  - `pnpm build` fails because `frontend/src/app/router.tsx` imports `../pages/ProjectDetailPage`, while `frontend/src/pages/ProjectDetailPage.tsx` is currently deleted in the working tree. This appears unrelated to the projects API route change and was not restored or rerouted in this task.
- Deferred risks:
  - Project authorization still needs a real user/member model and dependency.
  - Redis/materialized-view caching should wait for measured route latency and data volume.
  - Product may later want a different `pipeline_status` priority order.

---

# candidate pagination UI plan

## Goal

Use the backend `skip` / `limit` support from `GET /projects/{project_id}/candidates` in the frontend so large candidate lists can be loaded incrementally.

## Task checklist

- [x] Add a failing API client test proving `getProjectCandidates(projectId, { skip, limit })` sends query parameters.
- [x] Add a failing CandidateTable test proving the table renders a `加载更多` control and calls `onLoadMore`.
- [x] Update `frontend/src/features/projects/api.ts` so `getProjectCandidates` accepts optional pagination params.
- [x] Update `frontend/src/features/candidates/components/CandidateTable.tsx` with `hasMore`, `isLoadingMore`, and `onLoadMore` props.
- [x] Update `frontend/src/pages/ProjectDetailPage.tsx` to load the first candidate page, append later pages, and re-apply local filters.
- [x] Run `pnpm test` and `pnpm build` in `frontend/`.
- [x] Run `.venv/bin/python -m pytest -q`.

## Review

- Status: implemented.
- Test evidence:
  - RED API client: `pnpm vitest run src/features/projects/api.test.ts` failed before implementation because query params were not present.
  - RED table: `pnpm vitest run src/features/candidates/components/CandidateTable.test.tsx` failed before implementation because `加载更多` / `加载中...` controls were missing.
  - Focused API client: `pnpm vitest run src/features/projects/api.test.ts` passed with 6 tests.
  - Focused table: `pnpm vitest run src/features/candidates/components/CandidateTable.test.tsx` passed with 4 tests.
  - Frontend full: `pnpm test` passed with 23 tests.
  - Frontend build: `pnpm build` passed.
  - Backend/contracts: `.venv/bin/python -m pytest -q` passed with 123 tests.
