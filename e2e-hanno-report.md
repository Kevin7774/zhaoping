# Hanno E2E Report

Final status: **LIMITED**

Generated: 2026-06-09T15:21:45.884074+00:00

## Environment
- Runtime used: `.venv/bin/python` 3.12.13; system `python` is 3.10.12.
- Backend: FastAPI on real server during test.
- Database: isolated Docker PostgreSQL, not SQLite for E2E.
- Frontend: TS entry `frontend/src/main.tsx`; legacy `App.jsx` was not the product entry.
- Mailtrap: SMTP credentials missing, so real sandbox delivery was blocked.

## Results
- BP init: generated **16** real jobs from `data/input/projects/bp_ai_hardware.md`, with full matrix fields.
- Resume import: 2 PDF resumes imported through Docling, candidates visible after refresh: 张载德, 代宁.
- Parser metadata: `parser=docling`, `provider=docling`, `parser_confidence=0.9`, `degraded_reason=None`.
- Outreach: draft generated, manually patched, persisted, and simulated history written.
- Real email: `simulate=false` returned 503 because email delivery is not active; no real candidate email was sent.
- Frontend: project detail page rendered project, job matrix, and candidates from real API; screenshot at `artifacts/e2e_hanno/screenshots/project-detail.png`.

## Verification
- `.venv/bin/python -m pytest -q` => **205 passed, 6 warnings**.
- `.venv/bin/python -m compileall app scripts tests` => pass.
- `pnpm --dir frontend lint` => pass.
- `pnpm --dir frontend build` => pass.
- `pnpm --dir frontend test` => 9 files / 68 tests passed.

## Bugs Fixed
- BUG-HANNO-001 (P0): No BP initialization API / no job matrix persistence / v2 prompts absent Fix: Added initialize-from-bp route, job matrix columns, v2 prompts, frontend registry/types/table projection
- BUG-HANNO-002 (P0): LLM JSON malformed and only single parse attempt Fix: Added schema-safe retry_prompt loop up to 3 attempts, compact JSON repair prompt, minimumRoleCount gate
- BUG-HANNO-003 (P1): Parser metadata not persisted; generic headings used as names Fix: Parser last_metadata, raw_payload parser/provider/parser_confidence/degraded_reason, filename/name-label heuristics, LLM+heuristic merge
- BUG-HANNO-004 (P0): Public web emails were not automatically pending compliance review Fix: Public/open web/source scrape email sources now require compliance review; resume_file/manual/referral exempt
- BUG-HANNO-005 (P1): LLM draft could omit candidate full name or strategy tag while still accepted Fix: Reject LLM draft unless candidate.name and strategy_tag are present; deterministic fallback preserves contract

## Limitations
- System python is 3.10.12; all project commands used .venv Python 3.12.13.
- Mailtrap SMTP credentials are unset, so no real Mailtrap sandbox delivery was attempted.
- No productized frontend public-site extraction flow exists for live open-web email ingestion; backend compliance contract is covered by tests.
- Project detail page does not display outreach history automatically after refresh.
- Weekly report endpoint returned 404 because no weekly report was generated in this run.

## Next Actions
- P0: Configure MAILTRAP_SMTP_HOST/PORT/USERNAME/PASSWORD/FROM for sandbox-only real send, then rerun /outreach/send simulate=false.
- P0: Add productized public-site email extraction flow that writes extraction_method/source_url/evidence/compliance_status and exposes it in TS page.
- P1: Persist manual edit intent separately from draft body.
- P1: Expose outreach history on project detail refresh.
- P1: Add observability events for BP LLM repair attempts without logging secrets.
- P2: Improve resume LLM structured extraction for 张载德 confidence/name without relying on filename fallback.
- P2: Add a weekly report generation step to remove expected latest-report 404.
