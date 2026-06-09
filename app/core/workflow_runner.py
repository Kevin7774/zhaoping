from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import sessionmaker

from app.core.workflow_context import normalize_context_value, truncate_text
from app.core.workflow_dsl import StepDefinition, WorkflowDefinition
from app.core.workflow_executor import (
    HumanGateRequiredException,
    StepExecutor,
    WorkflowFatalException,
    WorkflowRuntimeState,
)
from app.db.task_models import TaskModel, make_task_session_factory
from app.schemas.tasks import AgentEventCreate


JSON_WORKFLOW_SCENARIO_ID = "json_workflow"


class WorkflowTaskRunner:
    def __init__(
        self,
        router: Any | None = None,
        session_factory: sessionmaker | None = None,
    ) -> None:
        self.executor = StepExecutor(router=router)
        self._session_factory = session_factory or make_task_session_factory()

    def start(
        self,
        workflow: WorkflowDefinition,
        initial_context: dict[str, Any],
        auto_run: bool = True,
        conversation_id: str | None = None,
    ) -> str:
        state = WorkflowRuntimeState.from_definition(workflow, initial_context, conversation_id=conversation_id)
        task_id = uuid.uuid4().hex[:12]
        now = _utc_now()
        frontend_state = self._frontend_state(workflow, state)
        row = TaskModel(
            task_id=task_id,
            scenario_id=JSON_WORKFLOW_SCENARIO_ID,
            input=json.dumps(normalize_context_value(initial_context), ensure_ascii=False),
            status="processing",
            team_constraint="json_workflow",
            aperture_weight=0.0,
            frontend_state=frontend_state,
            current_agent=JSON_WORKFLOW_SCENARIO_ID,
            current_step=state.current_step_index,
            total_steps=len(workflow.steps),
            steps_done=[],
            created_at=now,
            updated_at=now,
        )
        with self._session_factory() as session:
            with session.begin():
                session.add(row)
        self._append_event(
            task_id,
            state,
            AgentEventCreate(
                type="summary",
                agent_id=JSON_WORKFLOW_SCENARIO_ID,
                message="JSON workflow task created.",
                data={"total_steps": len(workflow.steps)},
                status="processing",
            ),
        )
        if auto_run:
            self._run_in_background(task_id)
        return task_id

    def snapshot(self, task_id: str) -> dict[str, Any]:
        from app.core.orchestrator import task_store

        snapshot = task_store.snapshot(task_id)
        if snapshot is None:
            raise KeyError(f"Task not found: {task_id}")
        return snapshot

    def resume(
        self,
        task_id: str,
        action: str,
        user_data: dict[str, Any] | None = None,
        auto_run: bool = True,
    ) -> dict[str, Any]:
        workflow, state = self._load_workflow_and_state(task_id)
        if state.current_step_index >= len(workflow.steps):
            raise WorkflowFatalException("Cannot resume completed workflow")
        step = workflow.steps[state.current_step_index]
        decision = normalize_context_value({"decision": action, "data": user_data or {}})
        state.context[step.output_key or step.id] = decision
        state.human_decision = decision
        state.current_step_index += 1
        self._save_checkpoint(
            task_id,
            workflow,
            state,
            status="processing",
            current_agent=JSON_WORKFLOW_SCENARIO_ID,
            current_step=state.current_step_index,
            awaiting=None,
        )
        self._append_event(
            task_id,
            state,
            AgentEventCreate(
                type="human_gate",
                agent_id="human_expert",
                step_index=state.current_step_index - 1,
                step_label=step.id,
                message=f"JSON workflow human decision: {action}",
                data={"decision": decision, "node_status": "done"},
                status="processing",
            ),
        )
        if auto_run:
            self._run_in_background(task_id)
        return self.snapshot(task_id)

    def run_until_blocked_or_done(self, task_id: str) -> dict[str, Any]:
        workflow, state = self._load_workflow_and_state(task_id)
        while state.current_step_index < len(workflow.steps):
            snapshot = self.snapshot(task_id)
            if snapshot["status"] == "cancelled":
                return snapshot
            step = workflow.steps[state.current_step_index]
            self._mark_step_started(task_id, workflow, state, step)
            try:
                result = self.executor.execute_step(step, state)
            except HumanGateRequiredException as exc:
                awaiting = normalize_context_value(
                    {**exc.awaiting, "workflow_id": state.workflow_id, "json_workflow": True}
                )
                self._save_checkpoint(
                    task_id,
                    workflow,
                    state,
                    status="awaiting_human",
                    current_agent=step.type,
                    current_step=state.current_step_index,
                    awaiting=awaiting,
                )
                self._append_event(
                    task_id,
                    state,
                    AgentEventCreate(
                        type="human_gate",
                        agent_id=step.type,
                        step_index=state.current_step_index,
                        step_label=step.id,
                        message=f"JSON workflow suspended: {awaiting.get('prompt', '')}",
                        data={"awaiting": awaiting, "node_status": "awaiting"},
                        status="awaiting_human",
                    ),
                )
                return self.snapshot(task_id)
            except WorkflowFatalException as exc:
                self._mark_error(task_id, workflow, state, step, str(exc), exc.safe_payload)
                return self.snapshot(task_id)
            except Exception as exc:
                self._mark_error(task_id, workflow, state, step, str(exc), {"step_id": step.id})
                return self.snapshot(task_id)

            if result.output_key:
                state.context[result.output_key] = normalize_context_value(result.value)
            state.artifacts.update(normalize_context_value(result.artifacts))
            state.current_step_index += 1
            self._save_checkpoint(
                task_id,
                workflow,
                state,
                status="processing",
                current_agent=step.type,
                current_step=state.current_step_index,
            )
            self._append_step_done(task_id, state, step, result.value)

        self._mark_done(task_id, workflow, state)
        return self.snapshot(task_id)

    def _run_in_background(self, task_id: str) -> None:
        thread = threading.Thread(target=self.run_until_blocked_or_done, args=(task_id,), daemon=True)
        thread.start()

    def _load_workflow_and_state(self, task_id: str) -> tuple[WorkflowDefinition, WorkflowRuntimeState]:
        snapshot = self.snapshot(task_id)
        runtime = (snapshot.get("frontend_state") or {}).get("json_workflow_runtime")
        if not runtime:
            raise KeyError(f"Task is not a JSON workflow: {task_id}")
        state = WorkflowRuntimeState.model_validate(runtime)
        workflow = WorkflowDefinition.model_validate(state.workflow)
        return workflow, state

    def _frontend_state(self, workflow: WorkflowDefinition, state: WorkflowRuntimeState) -> dict[str, Any]:
        workflow_info = {
            "workflow_id": workflow.id,
            "workflow_name": workflow.name,
        }
        return normalize_context_value(
            {
                "json_workflow_runtime": state.model_dump(mode="json"),
                "json_workflow": workflow_info,
            }
        )

    def _save_checkpoint(
        self,
        task_id: str,
        workflow: WorkflowDefinition,
        state: WorkflowRuntimeState,
        status: str | None = None,
        current_agent: str | None = None,
        current_step: int | None = None,
        awaiting: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        state.context = normalize_context_value(state.context)
        state.retry_state = normalize_context_value(state.retry_state)
        state.artifacts = normalize_context_value(state.artifacts)
        frontend_state = self._frontend_state(workflow, state)
        with self._session_factory() as session:
            with session.begin():
                row = session.get(TaskModel, task_id)
                if row is None:
                    return
                row.frontend_state = frontend_state
                row.current_step = state.current_step_index if current_step is None else current_step
                row.current_agent = current_agent
                if status is not None:
                    row.status = status
                if awaiting is not None:
                    row.awaiting = normalize_context_value(awaiting)
                elif status == "processing":
                    row.awaiting = None
                if result is not None:
                    row.result = normalize_context_value(result)
                if error is not None:
                    row.error = error
                row.updated_at = _utc_now()

    def _mark_step_started(
        self,
        task_id: str,
        workflow: WorkflowDefinition,
        state: WorkflowRuntimeState,
        step: StepDefinition,
    ) -> None:
        self._save_checkpoint(
            task_id,
            workflow,
            state,
            status="processing",
            current_agent=step.type,
            current_step=state.current_step_index,
            awaiting=None,
        )
        self._append_event(
            task_id,
            state,
            AgentEventCreate(
                type="step_start",
                agent_id=step.type,
                step_index=state.current_step_index,
                step_label=step.id,
                message=f"JSON workflow step started: {step.id}",
                data={"step_id": step.id, "step_type": step.type, "node_status": "active"},
                status="processing",
            ),
        )
        self._append_event(
            task_id,
            state,
            AgentEventCreate(
                type="tool_call",
                agent_id=step.type,
                step_index=state.current_step_index,
                step_label=step.id,
                message=f"JSON workflow executing step: {step.type}",
                data={"step_id": step.id, "step_type": step.type},
                status="processing",
            ),
        )

    def _append_step_done(self, task_id: str, state: WorkflowRuntimeState, step: StepDefinition, value: Any) -> None:
        output = normalize_context_value(value)
        with self._session_factory() as session:
            with session.begin():
                row = session.get(TaskModel, task_id)
                if row is None:
                    return
                steps_done = list(row.steps_done or [])
                steps_done.append({"agent_id": step.type, "label": step.id, "output": output})
                row.steps_done = normalize_context_value(steps_done)
                row.updated_at = _utc_now()
        self._append_event(
            task_id,
            state,
            AgentEventCreate(
                type="summary",
                agent_id=step.type,
                step_index=state.current_step_index - 1,
                step_label=step.id,
                message=f"JSON workflow step completed: {step.id}",
                data={"step_id": step.id, "output": output, "node_status": "done"},
                status="processing",
            ),
        )

    def _mark_done(self, task_id: str, workflow: WorkflowDefinition, state: WorkflowRuntimeState) -> None:
        last_output_key = next((step.output_key for step in reversed(workflow.steps) if step.output_key), None)
        result = normalize_context_value(
            {
                "workflow_id": state.workflow_id,
                "context": state.context,
                "artifacts": state.artifacts,
                "final_output": state.context.get(last_output_key) if last_output_key else None,
            }
        )
        self._save_checkpoint(
            task_id,
            workflow,
            state,
            status="done",
            current_agent=None,
            current_step=state.current_step_index,
            awaiting=None,
            result=result,
        )
        self._append_event(
            task_id,
            state,
            AgentEventCreate(
                type="summary",
                agent_id=JSON_WORKFLOW_SCENARIO_ID,
                message="JSON workflow completed.",
                data={"status": "done", "result": result},
                status="done",
            ),
        )

    def _mark_error(
        self,
        task_id: str,
        workflow: WorkflowDefinition,
        state: WorkflowRuntimeState,
        step: StepDefinition,
        message: str,
        payload: dict[str, Any] | None,
    ) -> None:
        safe_payload = normalize_context_value(payload or {})
        self._save_checkpoint(
            task_id,
            workflow,
            state,
            status="error",
            current_agent=None,
            current_step=state.current_step_index,
            awaiting=None,
            error=message,
        )
        self._append_event(
            task_id,
            state,
            AgentEventCreate(
                type="error",
                agent_id=step.type,
                step_index=state.current_step_index,
                step_label=step.id,
                message=truncate_text(message, 1200),
                data={
                    **safe_payload,
                    "step_id": step.id,
                    "error": truncate_text(message, 1200),
                    "node_status": "error",
                },
                status="error",
            ),
        )

    def _append_event(self, task_id: str, state: WorkflowRuntimeState, event: AgentEventCreate) -> None:
        from app.core.orchestrator import task_store

        data = normalize_context_value(
            {
                **event.data,
                "workflow_id": state.workflow_id,
                "json_workflow": True,
            }
        )
        task_store.append_event(task_id, event.model_copy(update={"data": data}))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
