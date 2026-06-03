"""Lightweight in-memory agent orchestrator.

The orchestration logic (which agents run, in what order, where humans intervene)
lives here in the backend, not in the frontend. The frontend only listens to task
state via polling and renders whatever the backend reports.

Real capabilities come from ``app.skills.recruiting_scenarios``; this module wraps
those deterministic functions into a step-by-step, trackable, human-interruptible
task so the UI behaves like an agent runtime dashboard instead of a video player.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from app.skills.recruiting_scenarios import (
    HOME_ROBOT_TALENT_SOURCE_MAP,
    build_talent_map,
    evaluate_candidate,
    generate_job_profile_and_jd,
    generate_weekly_report,
    infer_role_key,
)
from app.skills.tech_space import ROBOT_ROLES_METADATA, get_capabilities_for_role


# --------------------------------------------------------------------------- #
# Agent registry: persona / icon / output format for fully dynamic UI render  #
# --------------------------------------------------------------------------- #

AGENT_REGISTRY: Dict[str, Dict[str, str]] = {
    "orchestrator": {
        "name_zh": "任务编排 Agent",
        "persona": "把一句模糊的招聘需求拆解成可执行的子任务，并决定调用哪些下游 Agent。",
        "icon": "🧭",
        "output_format": "任务拆解与岗位识别",
    },
    "industry": {
        "name_zh": "行业研究 Agent",
        "persona": "扫描机器人赛道的目标公司、实验室与人才流动信号。",
        "icon": "🔭",
        "output_format": "目标公司 / 实验室列表",
    },
    "tech_route": {
        "name_zh": "技术路线 Agent",
        "persona": "把岗位拆成家庭机器人技术栈上的核心能力矩阵。",
        "icon": "🧬",
        "output_format": "能力矩阵",
    },
    "job_model": {
        "name_zh": "岗位建模 Agent",
        "persona": "产出岗位画像、JD 与面试问题。",
        "icon": "📋",
        "output_format": "岗位画像 / JD",
    },
    "talent_map": {
        "name_zh": "人才地图 Agent",
        "persona": "绘制候选人来源层级、搜索关键词与触达策略。",
        "icon": "🗺️",
        "output_format": "人才地图",
    },
    "candidate_eval": {
        "name_zh": "候选人评估 Agent",
        "persona": "对候选人材料做匹配评分、风险识别与证据链梳理。",
        "icon": "🎯",
        "output_format": "评分卡 / 风险点",
    },
    "resume_design": {
        "name_zh": "履历设计 Agent",
        "persona": "围绕候选人短板设计面试追问与考察话题。",
        "icon": "✍️",
        "output_format": "面试追问策略",
    },
    "strategy": {
        "name_zh": "招聘策略 Agent",
        "persona": "综合信息制定招聘优先级、节奏与触达计划。",
        "icon": "♟️",
        "output_format": "招聘策略",
    },
    "reflection": {
        "name_zh": "反思审核 Agent",
        "persona": "对中间结论做自检，标记排除项、能力缺口和风险。",
        "icon": "🔍",
        "output_format": "反思结论",
    },
    "report": {
        "name_zh": "报告生成 Agent",
        "persona": "把所有中间结论汇总成结构化最终报告。",
        "icon": "📊",
        "output_format": "结构化报告",
    },
    "human_expert": {
        "name_zh": "人类专家 (Human-in-the-loop)",
        "persona": "在关键节点暂停流程，由人工确认、修改或拒绝后再继续。",
        "icon": "🧑‍⚖️",
        "output_format": "人工决策",
    },
}


# --------------------------------------------------------------------------- #
# Step + scenario plan definitions (the orchestration logic, in the backend)  #
# --------------------------------------------------------------------------- #


@dataclass
class Step:
    agent_id: str
    label: str
    message: str
    kind: str  # compute | reflect | hitl | finalize
    handler: Optional[Callable[[Dict[str, Any]], Any]] = None


# ---- Scenario A: job profile & JD ----------------------------------------- #


def _a_plan(ctx: Dict[str, Any]) -> Any:
    role_key = infer_role_key(ctx["input"])
    ctx["role_key"] = role_key
    role = ROBOT_ROLES_METADATA[role_key]
    ctx["log"] = f"已拆解招聘需求，目标岗位识别为「{role['name_zh']}」"
    return {"role_key": role_key, "岗位": role["name_zh"], "技术层": role["tech_layer"]}


def _a_industry(ctx: Dict[str, Any]) -> Any:
    role_key = ctx["role_key"]
    sources = HOME_ROBOT_TALENT_SOURCE_MAP.get(role_key, {})
    companies = sources.get("priority_sources", ROBOT_ROLES_METADATA[role_key]["target_targets"])
    labs = sources.get("labs", [])
    ctx["log"] = f"检索到 {len(companies)} 家优先目标公司、{len(labs)} 个高校实验室"
    return {"目标公司": companies, "高校实验室": labs}


def _a_tech(ctx: Dict[str, Any]) -> Any:
    caps = get_capabilities_for_role(ctx["role_key"])
    names = [c["capability_name_zh"] for c in caps]
    ctx["log"] = f"拆解出 {len(names)} 项核心能力要求"
    return {"能力矩阵": names}


def _a_job_model(ctx: Dict[str, Any]) -> Any:
    result = generate_job_profile_and_jd(ctx["input"])
    ctx["data"]["job_profile"] = result
    ctx["log"] = "已生成岗位画像、JD 与面试问题草稿"
    return {"岗位定位": result["岗位定位"], "JD职责": result["JD"]["职责"]}


def _a_reflect(ctx: Dict[str, Any]) -> Any:
    result = ctx["data"]["job_profile"]
    exclusions = result["能力矩阵"]["排除项"]
    notes = [f"面试中需规避：{x}" for x in exclusions]
    ctx["data"]["reflection"] = notes
    ctx["log"] = f"反思完成，标记 {len(notes)} 条排除项风险"
    return {"反思结论": notes}


def _a_hitl(ctx: Dict[str, Any]) -> Any:
    result = ctx["data"]["job_profile"]
    return {
        "prompt": "请确认岗位定位与面试问题，可直接通过，或填写修改意见后继续。",
        "draft": {
            "岗位定位": result["岗位定位"],
            "面试问题": result["面试问题"],
        },
    }


def _a_finalize(ctx: Dict[str, Any]) -> Any:
    result = dict(ctx["data"]["job_profile"])
    result["反思结论"] = ctx["data"].get("reflection", [])
    _apply_human_edits(ctx, result)
    ctx["log"] = "已汇总生成最终岗位画像报告"
    return result


# ---- Scenario B: talent map ----------------------------------------------- #


def _b_plan(ctx: Dict[str, Any]) -> Any:
    role_key = infer_role_key(ctx["input"])
    ctx["role_key"] = role_key
    role = ROBOT_ROLES_METADATA[role_key]
    ctx["log"] = f"已识别目标方向「{role['name_zh']}」，准备绘制人才地图"
    return {"role_key": role_key, "岗位": role["name_zh"]}


def _b_map(ctx: Dict[str, Any]) -> Any:
    result = build_talent_map(ctx["input"])
    ctx["data"]["talent_map"] = result
    ctx["log"] = f"已绘制人才地图，覆盖 {len(result['目标公司'])} 家目标公司"
    return {"目标公司": result["目标公司"], "搜索关键词": result["搜索关键词"][:8]}


def _b_strategy(ctx: Dict[str, Any]) -> Any:
    result = ctx["data"]["talent_map"]
    strategy = {
        "优先来源": result["候选人来源"]["优先来源公司"],
        "次优来源": result["候选人来源"]["次优来源公司"],
        "触达话术": result["触达策略"],
    }
    ctx["data"]["strategy"] = strategy
    ctx["log"] = "已制定分层触达策略"
    return strategy


def _b_hitl(ctx: Dict[str, Any]) -> Any:
    return {
        "prompt": "请确认目标公司与触达策略，可通过或填写调整意见。",
        "draft": ctx["data"]["strategy"],
    }


def _b_finalize(ctx: Dict[str, Any]) -> Any:
    result = dict(ctx["data"]["talent_map"])
    result["招聘策略"] = ctx["data"].get("strategy", {})
    _apply_human_edits(ctx, result)
    ctx["log"] = "已汇总生成最终人才地图报告"
    return result


# ---- Scenario C: candidate evaluation ------------------------------------- #


def _c_plan(ctx: Dict[str, Any]) -> Any:
    role_key = infer_role_key(ctx["input"])
    ctx["role_key"] = role_key
    role = ROBOT_ROLES_METADATA[role_key]
    ctx["log"] = f"已解析候选人材料，对标岗位「{role['name_zh']}」"
    return {"对标岗位": role["name_zh"]}


def _c_eval(ctx: Dict[str, Any]) -> Any:
    result = evaluate_candidate(ctx["input"])
    ctx["data"]["evaluation"] = result
    ctx["log"] = f"匹配评分 {result['匹配评分']}，推荐等级「{result['推荐等级']}」"
    return {
        "匹配评分": result["匹配评分"],
        "推荐等级": result["推荐等级"],
        "技术强项": result["技术强项"],
    }


def _c_resume(ctx: Dict[str, Any]) -> Any:
    result = ctx["data"]["evaluation"]
    questions = result["面试追问"]
    ctx["log"] = f"围绕短板设计了 {len(questions)} 条面试追问"
    return {"面试追问": questions}


def _c_reflect(ctx: Dict[str, Any]) -> Any:
    result = ctx["data"]["evaluation"]
    ctx["log"] = f"反思完成，识别 {len(result['风险点'])} 个风险点"
    return {"风险点": result["风险点"], "证据链": result["证据链"]}


def _c_hitl(ctx: Dict[str, Any]) -> Any:
    result = ctx["data"]["evaluation"]
    return {
        "prompt": "请确认推荐结论，可通过或填写人工评价后继续。",
        "draft": {
            "匹配评分": result["匹配评分"],
            "推荐等级": result["推荐等级"],
            "推荐结论": result["推荐结论"],
        },
    }


def _c_finalize(ctx: Dict[str, Any]) -> Any:
    result = dict(ctx["data"]["evaluation"])
    _apply_human_edits(ctx, result)
    ctx["log"] = "已汇总生成最终候选人评估报告"
    return result


# ---- Scenario D: weekly report -------------------------------------------- #


def _d_plan(ctx: Dict[str, Any]) -> Any:
    ctx["data"]["weekly"] = generate_weekly_report(ctx["input"])
    ctx["log"] = "已解析本周招聘数据，识别关注岗位"
    return {"本周招聘结论": ctx["data"]["weekly"]["本周招聘结论"]}


def _d_signals(ctx: Dict[str, Any]) -> Any:
    weekly = ctx["data"]["weekly"]
    ctx["log"] = f"归纳出 {len(weekly['市场人才信号'])} 条市场人才信号"
    return {"市场人才信号": weekly["市场人才信号"], "关键岗位进展": weekly["关键岗位进展"]}


def _d_reflect(ctx: Dict[str, Any]) -> Any:
    weekly = ctx["data"]["weekly"]
    ctx["log"] = f"反思完成，识别 {len(weekly['招聘风险'])} 项招聘风险"
    return {"招聘风险": weekly["招聘风险"]}


def _d_hitl(ctx: Dict[str, Any]) -> Any:
    weekly = ctx["data"]["weekly"]
    return {
        "prompt": "请确认下周行动建议，可通过或填写人工补充后继续。",
        "draft": {"下周行动建议": weekly["下周行动建议"]},
    }


def _d_finalize(ctx: Dict[str, Any]) -> Any:
    result = dict(ctx["data"]["weekly"])
    _apply_human_edits(ctx, result)
    ctx["log"] = "已汇总生成最终招聘周报"
    return result


def _apply_human_edits(ctx: Dict[str, Any], result: Dict[str, Any]) -> None:
    human = ctx.get("human") or {}
    edits = human.get("edits")
    if edits:
        result["人工修订意见"] = edits
    if human.get("decision"):
        result["人工决策"] = human["decision"]


SCENARIO_PLANS: Dict[str, Dict[str, Any]] = {
    "A": {
        "name_zh": "场景 A：岗位画像与 JD",
        "input_hint": "用一句话描述招聘需求，例如：我们想招一个家庭机器人 VLA 算法工程师。",
        "example": "我们想招一个家庭机器人 VLA 算法工程师，要有 Diffusion Policy 和真实机器人部署经验。",
        "steps": [
            Step("orchestrator", "拆解需求", "识别岗位与技术层", "compute", _a_plan),
            Step("industry", "行业研究", "检索目标公司与实验室", "compute", _a_industry),
            Step("tech_route", "技术路线", "拆解能力矩阵", "compute", _a_tech),
            Step("job_model", "岗位建模", "生成岗位画像与 JD", "compute", _a_job_model),
            Step("reflection", "反思审核", "校验排除项与风险", "reflect", _a_reflect),
            Step("human_expert", "人工确认", "等待人类专家确认岗位定位", "hitl", _a_hitl),
            Step("report", "报告生成", "汇总最终岗位画像报告", "finalize", _a_finalize),
        ],
    },
    "B": {
        "name_zh": "场景 B：人才地图",
        "input_hint": "描述目标岗位或技术方向，例如：灵巧手控制负责人。",
        "example": "帮我画一张家庭机器人 SLAM 导航工程师的人才地图。",
        "steps": [
            Step("orchestrator", "拆解需求", "识别目标方向", "compute", _b_plan),
            Step("talent_map", "人才地图", "绘制候选人来源层级", "compute", _b_map),
            Step("strategy", "招聘策略", "制定分层触达策略", "compute", _b_strategy),
            Step("human_expert", "人工确认", "等待人类专家确认触达策略", "hitl", _b_hitl),
            Step("report", "报告生成", "汇总最终人才地图报告", "finalize", _b_finalize),
        ],
    },
    "C": {
        "name_zh": "场景 C：候选人评估",
        "input_hint": "粘贴候选人简历 / 作品 / 项目经历文本。",
        "example": "候选人在 Isaac Sim 搭建家庭厨房洗碗仿真，复现 Diffusion Policy，做过遥操作数据清洗与多摄像头时间戳对齐。",
        "steps": [
            Step("orchestrator", "解析材料", "对标目标岗位", "compute", _c_plan),
            Step("candidate_eval", "候选人评估", "匹配评分与强项识别", "compute", _c_eval),
            Step("resume_design", "履历设计", "设计面试追问", "compute", _c_resume),
            Step("reflection", "反思审核", "识别风险与证据链", "reflect", _c_reflect),
            Step("human_expert", "人工确认", "等待人类专家确认推荐结论", "hitl", _c_hitl),
            Step("report", "报告生成", "汇总最终候选人评估报告", "finalize", _c_finalize),
        ],
    },
    "D": {
        "name_zh": "场景 D：招聘周报",
        "input_hint": "粘贴本周招聘进展、候选人状态、面试反馈、市场信号。",
        "example": "本周推进 VLA 算法工程师招聘，3 人进入终面，1 人 offer，市场有新融资和产品发布。",
        "steps": [
            Step("orchestrator", "解析数据", "识别本周关注岗位", "compute", _d_plan),
            Step("industry", "市场信号", "归纳市场人才信号", "compute", _d_signals),
            Step("reflection", "反思审核", "识别招聘风险", "reflect", _d_reflect),
            Step("human_expert", "人工确认", "等待人类专家确认下周计划", "hitl", _d_hitl),
            Step("report", "报告生成", "汇总最终招聘周报", "finalize", _d_finalize),
        ],
    },
}


# --------------------------------------------------------------------------- #
# Task store + runner                                                         #
# --------------------------------------------------------------------------- #


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskState:
    task_id: str
    scenario: str
    input: str
    status: str = "processing"  # processing | awaiting_human | done | error
    current_agent: Optional[str] = None
    current_step: int = -1
    total_steps: int = 0
    logs: List[Dict[str, str]] = field(default_factory=list)
    steps_done: List[Dict[str, Any]] = field(default_factory=list)
    awaiting: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "scenario": self.scenario,
            "input": self.input,
            "status": self.status,
            "current_agent": self.current_agent,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "logs": self.logs,
            "steps_done": self.steps_done,
            "awaiting": self.awaiting,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
        }


class TaskStore:
    """Thread-safe in-memory task registry."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: Dict[str, TaskState] = {}
        self._events: Dict[str, threading.Event] = {}
        self._decisions: Dict[str, Dict[str, Any]] = {}

    def create(self, scenario: str, user_input: str) -> TaskState:
        task_id = uuid.uuid4().hex[:12]
        task = TaskState(
            task_id=task_id,
            scenario=scenario,
            input=user_input,
            total_steps=len(SCENARIO_PLANS[scenario]["steps"]),
        )
        with self._lock:
            self._tasks[task_id] = task
            self._events[task_id] = threading.Event()
        return task

    def get(self, task_id: str) -> Optional[TaskState]:
        with self._lock:
            return self._tasks.get(task_id)

    def snapshot(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self._tasks.get(task_id)
            return task.to_dict() if task else None

    def append_log(self, task_id: str, agent: str, message: str, level: str = "info") -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.logs.append({"ts": _now(), "agent": agent, "message": message, "level": level})

    def update(self, task_id: str, **fields: Any) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            for key, value in fields.items():
                setattr(task, key, value)

    def add_step_done(self, task_id: str, entry: Dict[str, Any]) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.steps_done.append(entry)

    def confirm(self, task_id: str, decision: str, edits: Optional[str]) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            event = self._events.get(task_id)
            if not task or not event or task.status != "awaiting_human":
                return False
            self._decisions[task_id] = {"decision": decision, "edits": edits}
            event.set()
            return True

    def _wait_for_human(self, task_id: str) -> Dict[str, Any]:
        event = self._events[task_id]
        event.wait()
        event.clear()
        with self._lock:
            return self._decisions.pop(task_id, {"decision": "approve", "edits": None})


# Module-level singleton store.
task_store = TaskStore()


class AgentRunner(threading.Thread):
    """Runs one scenario plan step-by-step, updating the shared TaskStore."""

    STEP_DELAY_SECONDS = 0.6

    def __init__(self, store: TaskStore, task: TaskState) -> None:
        super().__init__(daemon=True)
        self._store = store
        self._task = task

    def run(self) -> None:
        task_id = self._task.task_id
        scenario = self._task.scenario
        plan = SCENARIO_PLANS[scenario]
        ctx: Dict[str, Any] = {
            "input": self._task.input,
            "scenario": scenario,
            "data": {},
            "human": None,
        }

        try:
            for idx, step in enumerate(plan["steps"]):
                agent = AGENT_REGISTRY[step.agent_id]["name_zh"]
                self._store.update(
                    task_id,
                    status="processing",
                    current_step=idx,
                    current_agent=step.agent_id,
                )
                self._store.append_log(task_id, step.agent_id, f"「{agent}」开始：{step.message}")
                time.sleep(self.STEP_DELAY_SECONDS)

                if step.kind == "hitl":
                    payload = step.handler(ctx) if step.handler else {"prompt": "请确认", "draft": {}}
                    self._store.update(
                        task_id,
                        status="awaiting_human",
                        awaiting={
                            "agent": step.agent_id,
                            "prompt": payload.get("prompt", "请确认"),
                            "draft": payload.get("draft", {}),
                        },
                    )
                    self._store.append_log(
                        task_id, step.agent_id, f"流程暂停，等待人类专家：{payload.get('prompt', '')}", "hitl"
                    )

                    decision = self._store._wait_for_human(task_id)
                    if decision.get("decision") == "reject":
                        self._store.update(task_id, status="error", awaiting=None, current_agent=None, error="人工拒绝，流程终止")
                        self._store.append_log(task_id, step.agent_id, "人类专家选择拒绝，流程终止。", "error")
                        return
                    ctx["human"] = decision
                    self._store.update(task_id, awaiting=None)
                    self._store.add_step_done(
                        task_id,
                        {"agent_id": step.agent_id, "label": step.label, "output": {"人工决策": decision.get("decision"), "修改意见": decision.get("edits")}},
                    )
                    self._store.append_log(
                        task_id, step.agent_id, f"人类专家已{decision.get('decision')}，继续执行。", "info"
                    )
                    continue

                output = step.handler(ctx) if step.handler else None
                log_message = ctx.pop("log", None) or f"「{agent}」完成：{step.label}"
                self._store.add_step_done(
                    task_id,
                    {"agent_id": step.agent_id, "label": step.label, "output": output},
                )
                self._store.append_log(task_id, step.agent_id, log_message)

                if step.kind == "finalize":
                    self._store.update(task_id, result=output)

            self._store.update(task_id, status="done", current_agent=None)
            self._store.append_log(task_id, "report", "全部流程完成。", "done")
        except Exception as exc:  # noqa: BLE001 - surface any handler failure to the UI
            self._store.update(task_id, status="error", current_agent=None, error=str(exc))
            self._store.append_log(task_id, self._task.current_agent or "orchestrator", f"执行异常：{exc}", "error")


def start_task(scenario: str, user_input: str) -> TaskState:
    if scenario not in SCENARIO_PLANS:
        raise KeyError(scenario)
    task = task_store.create(scenario, user_input)
    AgentRunner(task_store, task).start()
    return task


def get_meta() -> Dict[str, Any]:
    """Serialize the orchestration protocol for fully dynamic frontend rendering."""

    scenarios = []
    for scenario_id, plan in SCENARIO_PLANS.items():
        scenarios.append(
            {
                "id": scenario_id,
                "name_zh": plan["name_zh"],
                "input_hint": plan["input_hint"],
                "example": plan.get("example", ""),
                "steps": [
                    {
                        "agent_id": step.agent_id,
                        "label": step.label,
                        "message": step.message,
                        "kind": step.kind,
                    }
                    for step in plan["steps"]
                ],
            }
        )
    return {"agents": AGENT_REGISTRY, "scenarios": scenarios}
