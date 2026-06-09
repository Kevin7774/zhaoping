# Workflow Artifact Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep large workflow outputs out of `state.context` and persisted runtime snapshots by writing explicit artifact outputs to local cold storage and keeping only lightweight references in context.

**Architecture:** Add an opt-in workflow step metadata flag, `metadata.output_storage = "artifact"`. When a step result uses that strategy, `WorkflowTaskRunner` writes the normalized output to `data/workflow_artifacts/{task_id}/{artifact_key}.json`, stores metadata in `state.artifacts`, and stores a small `artifact_ref` object under `state.context[output_key]`.

**Tech Stack:** Python, Pydantic workflow models, existing SQLAlchemy task snapshots, pytest.

---

### Task 1: Red Test For Artifact Output Storage

**Files:**
- Modify: `tests/test_json_workflow_engine.py`

- [ ] **Step 1: Write the failing test**

Add a test that creates a workflow with a search step using `metadata.output_storage = "artifact"`, runs it, and asserts:
- `context["search_results"]` is an `artifact_ref`.
- The long tail text is not present in serialized runtime/result JSON.
- `state.artifacts` contains file metadata.
- The artifact file exists and contains the original long search result.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_json_workflow_engine.py::test_workflow_artifact_output_storage_keeps_large_payload_out_of_context -q
```

Expected: FAIL because the runner currently writes search output directly into `state.context`.

### Task 2: Implement Local Artifact Store

**Files:**
- Modify: `app/core/workflow_runner.py`

- [ ] **Step 1: Add artifact storage helpers**

Add helper functions near the bottom of `workflow_runner.py`:
- `_step_output_storage(step)`
- `_artifact_base_dir()`
- `_artifact_key(step, output_key)`
- `_write_artifact_file(task_id, artifact_key, value)`
- `_artifact_ref(artifact_key, metadata)`

- [ ] **Step 2: Wire runner output handling**

Change `run_until_blocked_or_done` so `metadata.output_storage == "artifact"` writes file-backed artifact metadata and puts only an `artifact_ref` in `state.context`.

- [ ] **Step 3: Keep default behavior compatible**

If metadata is absent or set to `context`, preserve current context write behavior.

### Task 3: Documentation And Verification

**Files:**
- Modify: `docs/capability_integration.md`

- [ ] **Step 1: Document the DSL convention**

Add a short section explaining `metadata.output_storage = "artifact"` and the expected downstream pattern: summarize artifact outputs into small context variables before later LLM prompts.

- [ ] **Step 2: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_json_workflow_engine.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full backend verification**

Run:

```bash
.venv/bin/python -m compileall app scripts tests
.venv/bin/python -m pytest -q
```

Expected: PASS.

