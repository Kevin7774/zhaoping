from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.routers.projects as projects_router
from app.api.main import app
from app.api.routers.projects import _utc_datetime
from app.db.session import get_project_session
from app.models import Candidate, Job, JobCandidate, Project, ProjectBase


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ProjectBase.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

    with session_factory() as session:
        _seed_project(session)

    try:
        yield session_factory
    finally:
        engine.dispose()


@pytest.fixture()
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override_project_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_project_session] = override_project_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_get_project_returns_base_info_and_stats(client: TestClient) -> None:
    response = client.get("/projects/project_2026_ai_team")

    assert response.status_code == 200
    assert response.json() == {
        "id": "project_2026_ai_team",
        "name": "2026 AI 团队招聘",
        "status": "active",
        "createdAt": "2026-06-09T00:00:00Z",
        "openJobs": 2,
        "totalCandidates": 3,
        "awaitingHuman": 1,
        "averageMatchScore": 85,
    }


def test_get_project_jobs_returns_pipeline_status_and_rollups(client: TestClient) -> None:
    response = client.get("/projects/project_2026_ai_team/jobs")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "job_vla_algorithm",
            "projectId": "project_2026_ai_team",
            "title": "VLA / 具身智能算法工程师",
            "headcount": 2,
            "status": "processing",
            "pipelineStatus": "awaiting_human",
            "candidateCount": 2,
            "averageMatchScore": 85,
        },
        {
            "id": "job_robot_data_platform",
            "projectId": "project_2026_ai_team",
            "title": "机器人数据平台工程师",
            "headcount": 1,
            "status": "offer",
            "pipelineStatus": "done",
            "candidateCount": 1,
            "averageMatchScore": 85,
        },
    ]


# Distinct vocabulary per template so the critic gate's boundary-overlap check
# does not reject fake roles as duplicates of each other.
FAKE_ROLE_TEMPLATES = [
    ("vla_algorithm", "VLA 算法研究员", "设计视觉语言动作模型的训练与评测闭环", ["VLA", "imitation learning"]),
    ("edge_inference", "边缘推理优化工程师", "压缩与量化多模态模型并部署到边缘盒子", ["TensorRT", "量化部署"]),
    ("embedded_firmware", "嵌入式固件工程师", "开发传感器接入固件与 OTA 升级通道", ["RTOS", "OTA"]),
    ("hardware_delivery", "智能硬件交付工程师", "负责现场安装联调与备件管理", ["工控机", "现场部署"]),
    ("data_platform", "数据平台工程师", "建设多源采集清洗与质量监控流水线", ["ETL", "数据质量"]),
    ("rag_engineer", "RAG 知识库工程师", "搭建文档解析向量检索与证据链", ["向量数据库", "文档解析"]),
    ("agent_workflow", "Agent 工作流工程师", "编排任务画布与人工确认节点", ["工作流引擎", "SSE"]),
    ("fullstack_product", "全栈产品工程师", "实现客户工作台配置后台与看板", ["React", "FastAPI"]),
    ("devops_private", "私有化部署运维工程师", "搭建离线安装监控告警与升级回滚", ["Docker", "可观测性"]),
    ("qa_evaluation", "测试与模型评估工程师", "建立回归集端到端用例与模型评测指标", ["pytest", "模型评估"]),
    ("security_compliance", "安全合规工程师", "设计权限审计数据留存与隐私护栏", ["权限审计", "隐私合规"]),
    ("solution_lead", "行业解决方案专家", "把行业痛点转译为方案包与验证清单", ["售前方案", "行业研究"]),
    ("delivery_manager", "交付项目经理", "管理里程碑风险验收与跨方协调", ["项目管理", "验收标准"]),
    ("customer_success", "客户成功工程师", "运营上线后反馈培训与续费线索", ["客户成功", "运维支持"]),
    ("ocr_multimodal", "OCR 多模态工程师", "构建票据表单与现场图像结构化识别", ["OCR", "多模态"]),
    ("sales_sea", "东盟区域销售经理", "开拓东盟渠道伙伴与政企客户", ["渠道销售", "海外市场"]),
]

FAKE_EVIDENCE_QUOTE = "边缘计算与 AI 综合解决方案"


def fake_claims_payload(quote: str) -> dict:
    return {
        "business_commitments": [{"id": "C1", "claim": "交付边缘 AI 综合解决方案", "quote": quote}],
        "product_lines": [{"id": "P1", "claim": "智能硬件产品线", "quote": quote}],
        "customer_scenarios": [],
        "delivery_constraints": [],
        "existing_resources": [{"id": "R1", "resource": "已有供应链与厂房", "quote": quote}],
    }


def fake_capability_payload(role_count: int) -> dict:
    return {
        "capabilities": [
            {
                "id": f"CAP{index}",
                "name": f"{FAKE_ROLE_TEMPLATES[index][1]}能力",
                "description": FAKE_ROLE_TEMPLATES[index][2],
                "kind": "tech",
                "supports_commitments": ["C1"],
            }
            for index in range(role_count)
        ]
    }


def fake_gap_payload(role_count: int) -> dict:
    return {
        "gaps": [
            {
                "capability_id": f"CAP{index}",
                "status": "missing",
                "resolution": "hire",
                "rationale": "长期核心能力，外包会失去交付控制。",
                "evidence": ["C1", "R1"],
            }
            for index in range(role_count)
        ]
    }


def fake_role_design_payload(role_count: int, quote: str = FAKE_EVIDENCE_QUOTE) -> dict:
    roles = []
    for index in range(role_count):
        role_id, title, responsibility, skills = FAKE_ROLE_TEMPLATES[index]
        roles.append(
            {
                "role_id": role_id,
                "title": title,
                "seniority": "Senior",
                "headcount": 1,
                "responsibilities": [responsibility],
                "must_have_skills": skills,
                "nice_to_have_skills": ["跨团队协作"],
                "target_companies": ["边缘计算公司", "智能硬件厂商"],
                "exclusion_signals": ["仅做 Demo 无交付经验"],
                "interview_questions": [f"请拆解一次与「{title}」相关的交付故障。"],
                "scoring_rubric": {"domain_fit": 40, "engineering_depth": 35, "delivery": 25},
                "search_strategy": {
                    "community": f'"{skills[0]}" AND production',
                    "academic": f'"{skills[0]}" AND evaluation',
                    "industry": f'"{title}"',
                },
                "why_needed": f"业务承诺 C1 依赖 CAP{index} 能力缺口，必须由「{title}」承接，外部资源无法覆盖。",
                "bp_evidence": [quote],
                "business_commitments": ["C1"],
                "capability_gaps": [f"CAP{index}"],
                "why_hire_not_vendor": "知识需要留在组织内，外包会失去质量控制。",
                "if_not_hired_risk": "对应交付承诺将延期并失去客户验收。",
                "dependencies": [],
                "first_90_day_outcomes": ["完成首个客户场景的可验收交付"],
                "hiring_priority": ["P0", "P1", "P2"][index % 3],
                "confidence": 0.9,
                "business_context": "AI 电商定制平台需要可上线可迭代的交付能力。",
                "job_scope": f"负责{title}的端到端业务闭环。",
                "must_have_signals": ["全栈开发", "AI coding 实战"],
                "bonus_signals": ["开源项目", "电商 SaaS 经验"],
                "risk_signals": ["只会写 prompt", "只会调 API"],
                "sourcing_keywords": [skills[0], "Agentic Builder"],
                "outreach_angle": "用真实业务问题和完整 SDLC 主导权吸引 builder。",
            }
        )
    return {
        "industry_reading": "汉诺云智面向边缘计算与 AI 交付。",
        "technical_assumptions": ["需要覆盖云边协同、硬件交付和 AI 应用工程。"],
        "roles": roles,
        "coverage_gaps": [],
    }


class FakeProjectInitLLM:
    """Stage-aware fake for the five-stage BP pipeline."""

    def __init__(self, role_count: int = 14, evidence_quote: str = FAKE_EVIDENCE_QUOTE) -> None:
        self.prompts: list[str] = []
        self.role_count = role_count
        self.evidence_quote = evidence_quote

    def text(self, prompt: str, max_tokens: int = 1024) -> str:
        self.prompts.append(prompt)
        if "stage_id: bp_claims" in prompt:
            payload: dict = fake_claims_payload(self.evidence_quote)
        elif "stage_id: bp_capability_graph" in prompt:
            payload = fake_capability_payload(self.role_count)
        elif "stage_id: bp_gap_analysis" in prompt:
            payload = fake_gap_payload(self.role_count)
        else:
            payload = fake_role_design_payload(self.role_count, self.evidence_quote)
        return json.dumps(payload, ensure_ascii=False)


class FakeProjectInitRouter:
    def __init__(self, llm: FakeProjectInitLLM) -> None:
        self.llm_provider = llm

    def llm(self, service_name: str | None = None) -> FakeProjectInitLLM:
        return self.llm_provider


class SequenceProjectInitLLM(FakeProjectInitLLM):
    """Injects scripted outputs for chosen stages; other calls delegate to the stage-aware base."""

    def __init__(self, stage_scripts: dict[str, list[str]], role_count: int = 1) -> None:
        super().__init__(role_count=role_count)
        self.stage_scripts = {marker: list(outputs) for marker, outputs in stage_scripts.items()}

    def text(self, prompt: str, max_tokens: int = 1024) -> str:
        for marker, outputs in self.stage_scripts.items():
            if marker in prompt and outputs:
                self.prompts.append(prompt)
                return outputs.pop(0)
        return super().text(prompt, max_tokens=max_tokens)


class MessagesProjectInitLLM(FakeProjectInitLLM):
    def __init__(self, role_count: int = 14, evidence_quote: str = FAKE_EVIDENCE_QUOTE) -> None:
        super().__init__(role_count=role_count, evidence_quote=evidence_quote)
        self.messages_calls: list[dict] = []

    def messages(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0,
        response_format: dict | None = None,
    ) -> dict:
        self.messages_calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": response_format,
            }
        )
        return {"choices": [{"message": {"content": self.text(messages[0]["content"], max_tokens=max_tokens)}}]}


class SlowProjectInitLLM(MessagesProjectInitLLM):
    def messages(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0,
        response_format: dict | None = None,
    ) -> dict:
        self.messages_calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": response_format,
            }
        )
        time.sleep(0.2)
        return {"choices": [{"message": {"content": self.text(messages[0]["content"], max_tokens=max_tokens)}}]}


def test_list_projects_returns_project_stats(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(
            Project(
                id="project_hanno_ai_hardware",
                name="汉诺云智招聘",
                status="active",
                created_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
            )
        )
        session.add(
            Job(
                id="job_hanno_edge",
                project_id="project_hanno_ai_hardware",
                title="边缘 AI 架构师",
                headcount=1,
                status="sourcing",
            )
        )
        session.commit()

    response = client.get("/projects")

    assert response.status_code == 200
    payload = response.json()
    assert [project["id"] for project in payload] == ["project_hanno_ai_hardware", "project_2026_ai_team"]
    assert payload[0]["openJobs"] == 1
    assert payload[0]["totalCandidates"] == 0
    assert payload[1]["openJobs"] == 2


def test_create_project_creates_empty_isolated_project(client: TestClient) -> None:
    response = client.post(
        "/projects",
        json={"id": "project_new_market", "name": "新市场招聘项目", "status": "active"},
    )

    assert response.status_code == 201
    assert response.json()["id"] == "project_new_market"
    assert response.json()["openJobs"] == 0
    assert client.get("/projects/project_new_market/jobs").json() == []
    assert client.get("/projects/project_new_market/candidates").json() == []


def test_create_project_rejects_duplicate_project_id(client: TestClient) -> None:
    response = client.post(
        "/projects",
        json={"id": "project_2026_ai_team", "name": "重复项目", "status": "active"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Project already exists: project_2026_ai_team"


def test_update_project_persists_name_and_status(client: TestClient) -> None:
    response = client.patch(
        "/projects/project_2026_ai_team",
        json={"name": "2026 AI 团队招聘更新版", "status": "paused"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "2026 AI 团队招聘更新版"
    assert response.json()["status"] == "paused"
    reloaded = client.get("/projects/project_2026_ai_team")
    assert reloaded.json()["name"] == "2026 AI 团队招聘更新版"
    assert reloaded.json()["status"] == "paused"


def test_update_project_rejects_unknown_project(client: TestClient) -> None:
    response = client.patch("/projects/missing", json={"name": "不存在", "status": "active"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found: missing"


def test_delete_project_removes_project_owned_records(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    response = client.delete("/projects/project_2026_ai_team")

    assert response.status_code == 204
    assert client.get("/projects/project_2026_ai_team").status_code == 404
    assert client.get("/projects/project_2026_ai_team/jobs").status_code == 404
    with session_factory() as session:
        assert session.get(Project, "project_2026_ai_team") is None
        assert session.scalar(select(func.count(Job.id))) == 0
        assert session.scalar(select(func.count(JobCandidate.id))) == 0
        assert session.scalar(select(func.count(Candidate.id))) == 3


def test_delete_project_rejects_unknown_project(client: TestClient) -> None:
    response = client.delete("/projects/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found: missing"


def test_upload_project_material_saves_file_for_bp_generation(
    client: TestClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    parsed_content = "汉诺云智边缘计算与 AI 综合解决方案。"

    class FakeMaterialParser:
        last_metadata = {
            "parser": "fake_docling",
            "provider": "test",
            "confidence": 0.91,
            "degraded_reason": None,
        }

        def parse(self, file_path: str) -> str:
            assert file_path.endswith("uploaded-bp.pdf")
            return parsed_content

    class FakeMaterialRouter:
        def document_parser(self, service_name: str | None = None) -> FakeMaterialParser:
            return FakeMaterialParser()

    monkeypatch.setattr(projects_router, "get_router", lambda: FakeMaterialRouter(), raising=False)

    response = client.post(
        "/projects/project_2026_ai_team/materials/upload",
        files={"file": ("uploaded-bp.pdf", b"%PDF fake content", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "fileName": "uploaded-bp.pdf",
        "bpFilePath": "data/input/projects/uploaded-bp.md",
        "sourceFilePath": "data/input/projects/uploaded-bp.pdf",
        "sizeBytes": len(b"%PDF fake content"),
        "parser": "fake_docling",
        "confidence": 0.91,
        "degradedReason": None,
    }
    source_path = tmp_path / "data" / "input" / "projects" / "uploaded-bp.pdf"
    parsed_path = tmp_path / "data" / "input" / "projects" / "uploaded-bp.md"
    assert source_path.read_bytes() == b"%PDF fake content"
    assert parsed_path.read_text(encoding="utf-8") == parsed_content


def test_upload_project_material_falls_back_to_ocr_when_document_parser_is_empty(
    client: TestClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    class EmptyMaterialParser:
        last_metadata = {"parser": "fake_docling", "confidence": 0.2}

        def parse(self, file_path: str) -> str:
            return ""

    class FakeOCRProvider:
        def extract_text(self, file_path: str | None = None, url: str | None = None) -> str:
            assert file_path and file_path.endswith("scanned-bp.pdf")
            return "OCR 识别出的项目材料正文"

    class FakeMaterialRouter:
        def document_parser(self, service_name: str | None = None) -> EmptyMaterialParser:
            return EmptyMaterialParser()

        def ocr(self, service_name: str | None = None) -> FakeOCRProvider:
            return FakeOCRProvider()

    monkeypatch.setattr(projects_router, "get_router", lambda: FakeMaterialRouter(), raising=False)

    response = client.post(
        "/projects/project_2026_ai_team/materials/upload",
        files={"file": ("scanned-bp.pdf", b"%PDF scanned content", "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["bpFilePath"] == "data/input/projects/scanned-bp.md"
    assert payload["parser"] == "ocr"
    assert payload["confidence"] == 0.65
    assert "document parser returned empty text" in payload["degradedReason"]
    assert (tmp_path / "data" / "input" / "projects" / "scanned-bp.md").read_text(encoding="utf-8") == "OCR 识别出的项目材料正文"


def test_preview_project_from_bp_uses_json_mode_and_does_not_persist_jobs(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    bp_path = tmp_path / "bp_ai_hardware.md"
    bp_path.write_text("汉诺云智边缘计算与 AI 综合解决方案，需要智能硬件交付团队。", encoding="utf-8")
    llm = MessagesProjectInitLLM(role_count=14)
    monkeypatch.setattr(projects_router, "get_router", lambda: FakeProjectInitRouter(llm), raising=False)

    response = client.post(
        "/projects/project_hanno_ai_hardware/preview-from-bp",
        json={
            "projectName": "汉诺云智边缘计算与 AI 综合解决方案招聘项目",
            "bpFilePath": str(bp_path),
        },
    )

    assert response.status_code == 200
    assert response.json()["jobCount"] == 14
    assert response.json()["jobs"][0]["title"] == "VLA 算法研究员"
    assert llm.messages_calls[0]["response_format"] == {"type": "json_object"}
    with session_factory() as session:
        assert session.get(Project, "project_hanno_ai_hardware") is None
        assert session.scalar(select(func.count(Job.id)).where(Job.project_id == "project_hanno_ai_hardware")) == 0


def test_preview_project_roles_from_prompt_without_bp_file(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = MessagesProjectInitLLM(role_count=4, evidence_quote="面向工业质检的边缘 AI 招聘项目")
    monkeypatch.setattr(projects_router, "get_router", lambda: FakeProjectInitRouter(llm), raising=False)

    response = client.post(
        "/projects/project_prompt_generated/preview-from-bp",
        json={
            "projectName": "提示词生成项目",
            "generationMode": "prompt",
            "projectPrompt": "我要搭建一个面向工业质检的边缘 AI 招聘项目，需要算法、硬件、交付和行业研究岗位。",
            "industryResearchPrompt": "重点拆解工业质检、边缘盒子、现场交付和数据闭环。",
            "minimumRoleCount": 4,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jobCount"] == 4
    assert payload["generationMode"] == "prompt"
    assert payload["researchTrace"][0]["stage"] == "业务承诺抽取"
    assert any(item["stage"] == "Critic Gate" for item in payload["researchTrace"])
    assert "project_prompt:" in llm.prompts[0]
    assert "industry_research_prompt:" in llm.prompts[0]
    assert "bp_markdown:" not in llm.prompts[0]
    with session_factory() as session:
        assert session.get(Project, "project_prompt_generated") is None
        assert session.scalar(select(func.count(Job.id)).where(Job.project_id == "project_prompt_generated")) == 0


def test_preview_project_from_bp_falls_back_when_llm_times_out(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    bp_path = tmp_path / "bp_ai_hardware.md"
    bp_path.write_text("汉诺云智边缘计算与 AI 综合解决方案，需要智能硬件、边缘计算、RAG 和私有化交付团队。", encoding="utf-8")
    llm = SlowProjectInitLLM(role_count=14)
    monkeypatch.setattr(projects_router, "get_router", lambda: FakeProjectInitRouter(llm), raising=False)
    monkeypatch.setattr(projects_router, "BP_PIPELINE_CALL_TIMEOUT_SECONDS", 0.01, raising=False)

    response = client.post(
        "/projects/project_hanno_ai_hardware/preview-from-bp",
        json={
            "projectName": "汉诺云智边缘计算与 AI 综合解决方案招聘项目",
            "bpFilePath": str(bp_path),
            "minimumRoleCount": 14,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jobCount"] == 14
    assert payload["jobs"][0]["title"] == "行业研究与解决方案负责人"
    assert payload["generationDegraded"] is True
    assert any("timed out" in item or "LLM" in item for item in payload["coverageGaps"])
    with session_factory() as session:
        assert session.scalar(select(func.count(Job.id)).where(Job.project_id == "project_hanno_ai_hardware")) == 0


def test_initialize_project_from_bp_falls_back_and_persists_when_llm_times_out(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    bp_path = tmp_path / "bp_ai_hardware.md"
    bp_path.write_text("汉诺云智边缘计算与 AI 综合解决方案，需要智能硬件、边缘计算、RAG 和私有化交付团队。", encoding="utf-8")
    llm = SlowProjectInitLLM(role_count=14)
    monkeypatch.setattr(projects_router, "get_router", lambda: FakeProjectInitRouter(llm), raising=False)
    monkeypatch.setattr(projects_router, "project_session_factory", lambda: session_factory, raising=False)
    monkeypatch.setattr(projects_router, "BP_PIPELINE_CALL_TIMEOUT_SECONDS", 0.01, raising=False)

    response = client.post(
        "/projects/project_hanno_ai_hardware/initialize-from-bp",
        json={
            "projectName": "汉诺云智边缘计算与 AI 综合解决方案招聘项目",
            "bpFilePath": str(bp_path),
            "minimumRoleCount": 14,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jobCount"] == 14
    assert payload["jobs"][0]["title"] == "行业研究与解决方案负责人"
    with session_factory() as session:
        assert session.get(Project, "project_hanno_ai_hardware") is not None
        assert session.scalar(select(func.count(Job.id)).where(Job.project_id == "project_hanno_ai_hardware")) == 14


def test_initialize_project_from_bp_retries_once_when_llm_json_is_malformed(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    bp_path = tmp_path / "bp_ai_hardware.md"
    bp_path.write_text("汉诺云智边缘计算与 AI 综合解决方案，需要智能硬件交付团队。", encoding="utf-8")
    llm = SequenceProjectInitLLM(
        {"stage_id: bp_claims": ['{"business_commitments":[{"id":"C1"']},
        role_count=1,
    )
    monkeypatch.setattr(projects_router, "get_router", lambda: FakeProjectInitRouter(llm), raising=False)
    monkeypatch.setattr(projects_router, "project_session_factory", lambda: session_factory, raising=False)

    response = client.post(
        "/projects/project_hanno_ai_hardware/initialize-from-bp",
        json={
            "projectName": "汉诺云智边缘计算与 AI 综合解决方案招聘项目",
            "bpFilePath": str(bp_path),
            "minimumRoleCount": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()["jobCount"] == 1
    repair_prompts = [prompt for prompt in llm.prompts if "上一次输出不合法" in prompt]
    assert len(repair_prompts) == 1
    assert "stage_id: bp_claims" in repair_prompts[0]


def test_initialize_project_from_bp_allows_second_json_repair_retry(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    bp_path = tmp_path / "bp_ai_hardware.md"
    bp_path.write_text("汉诺云智边缘计算与 AI 综合解决方案，需要智能硬件交付团队。", encoding="utf-8")
    llm = SequenceProjectInitLLM(
        {
            "stage_id: bp_claims": [
                '{"business_commitments":[{"id":"C1"',
                '{"business_commitments":[],"existing_resources":[]}',
            ]
        },
        role_count=1,
    )
    monkeypatch.setattr(projects_router, "get_router", lambda: FakeProjectInitRouter(llm), raising=False)
    monkeypatch.setattr(projects_router, "project_session_factory", lambda: session_factory, raising=False)

    response = client.post(
        "/projects/project_hanno_ai_hardware/initialize-from-bp",
        json={
            "projectName": "汉诺云智边缘计算与 AI 综合解决方案招聘项目",
            "bpFilePath": str(bp_path),
            "minimumRoleCount": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()["jobCount"] == 1
    repair_prompts = [prompt for prompt in llm.prompts if "上一次输出不合法" in prompt]
    assert len(repair_prompts) == 2


def test_initialize_project_from_bp_retries_when_role_count_is_below_minimum(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    bp_path = tmp_path / "bp_ai_hardware.md"
    bp_path.write_text("汉诺云智边缘计算与 AI 综合解决方案，需要智能硬件交付团队。", encoding="utf-8")
    llm = SequenceProjectInitLLM(
        {"stage_id: bp_role_design": [json.dumps(fake_role_design_payload(7), ensure_ascii=False)]},
        role_count=14,
    )
    monkeypatch.setattr(projects_router, "get_router", lambda: FakeProjectInitRouter(llm), raising=False)
    monkeypatch.setattr(projects_router, "project_session_factory", lambda: session_factory, raising=False)

    response = client.post(
        "/projects/project_hanno_ai_hardware/initialize-from-bp",
        json={
            "projectName": "汉诺云智边缘计算与 AI 综合解决方案招聘项目",
            "bpFilePath": str(bp_path),
            "minimumRoleCount": 14,
        },
    )

    assert response.status_code == 200
    assert response.json()["jobCount"] == 14
    redesign_prompts = [prompt for prompt in llm.prompts if "少于要求的 14" in prompt]
    assert len(redesign_prompts) == 1


def test_preview_project_from_bp_keeps_accepted_roles_when_still_below_minimum(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    bp_path = tmp_path / "bp_single_role.md"
    bp_path.write_text("汉诺云智边缘计算与 AI 综合解决方案，需要智能硬件交付团队。", encoding="utf-8")
    llm = FakeProjectInitLLM(role_count=1)
    monkeypatch.setattr(projects_router, "get_router", lambda: FakeProjectInitRouter(llm), raising=False)
    monkeypatch.setattr(projects_router, "project_session_factory", lambda: session_factory, raising=False)

    response = client.post(
        "/projects/project_hanno_ai_hardware/preview-from-bp",
        json={
            "projectName": "汉诺云智边缘计算与 AI 综合解决方案招聘项目",
            "bpFilePath": str(bp_path),
            "minimumRoleCount": 14,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jobCount"] == 1
    assert any("低于设置的最少岗位数 14" in item for item in payload["coverageGaps"])


def test_preview_project_from_bp_returns_422_when_no_roles_pass_critic_gate(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    bp_path = tmp_path / "bp_single_role.md"
    bp_path.write_text("汉诺云智边缘计算与 AI 综合解决方案，需要智能硬件交付团队。", encoding="utf-8")
    llm = FakeProjectInitLLM(role_count=1, evidence_quote="材料里完全不存在的引用文本")
    monkeypatch.setattr(projects_router, "get_router", lambda: FakeProjectInitRouter(llm), raising=False)
    monkeypatch.setattr(projects_router, "project_session_factory", lambda: session_factory, raising=False)

    response = client.post(
        "/projects/project_hanno_ai_hardware/preview-from-bp",
        json={
            "projectName": "汉诺云智边缘计算与 AI 综合解决方案招聘项目",
            "bpFilePath": str(bp_path),
            "minimumRoleCount": 1,
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "素材未能解析出任何通过证据审核的岗位" in detail
    assert "找到原文" in detail
    with session_factory() as session:
        assert session.scalar(select(func.count(Job.id)).where(Job.project_id == "project_hanno_ai_hardware")) == 0


def test_initialize_project_from_bp_runs_pipeline_and_persists_full_job_matrix(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    bp_path = tmp_path / "bp_ai_hardware.md"
    bp_path.write_text("汉诺云智边缘计算与 AI 综合解决方案，需要智能硬件交付团队。", encoding="utf-8")
    llm = FakeProjectInitLLM(role_count=14)
    monkeypatch.setattr(projects_router, "get_router", lambda: FakeProjectInitRouter(llm), raising=False)
    monkeypatch.setattr(projects_router, "project_session_factory", lambda: session_factory, raising=False)

    response = client.post(
        "/projects/project_hanno_ai_hardware/initialize-from-bp",
        json={
            "projectName": "汉诺云智边缘计算与 AI 综合解决方案招聘项目",
            "bpFilePath": str(bp_path),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["projectId"] == "project_hanno_ai_hardware"
    assert payload["jobCount"] == 14
    assert payload["promptName"] == "bp_pipeline_v1"
    assert "stage_id: bp_claims" in llm.prompts[0]
    assert "JSON-only" in llm.prompts[0]
    assert any("不可编造" in prompt for prompt in llm.prompts)
    assert any("must_have_skills" in prompt for prompt in llm.prompts)
    assert payload["claims"]["business_commitments"][0]["id"] == "C1"

    jobs_response = client.get("/projects/project_hanno_ai_hardware/jobs")

    assert jobs_response.status_code == 200
    jobs = jobs_response.json()
    assert len(jobs) == 14
    first_job = jobs[0]
    assert first_job["title"] == "VLA 算法研究员"
    assert first_job["seniority"] == "Senior"
    assert first_job["responsibilities"] == ["设计视觉语言动作模型的训练与评测闭环"]
    assert first_job["mustHaveSkills"] == ["VLA", "imitation learning"]
    assert first_job["targetCompanies"] == ["边缘计算公司", "智能硬件厂商"]
    assert first_job["exclusionSignals"] == ["仅做 Demo 无交付经验"]
    rationale = first_job["rationale"]
    assert "C1" in rationale["whyNeeded"]
    assert rationale["bpEvidence"] == [FAKE_EVIDENCE_QUOTE]
    assert rationale["businessCommitments"] == ["C1"]
    assert rationale["capabilityGaps"] == ["CAP0"]
    assert rationale["hiringPriority"] == "P0"
    assert rationale["confidence"] == 0.9
    assert rationale["whyHireNotVendor"]
    assert rationale["ifNotHiredRisk"]
    assert rationale["mustHaveSignals"] == ["全栈开发", "AI coding 实战"]
    assert rationale["riskSignals"] == ["只会写 prompt", "只会调 API"]
    assert rationale["sourcingKeywords"] == ["VLA", "Agentic Builder"]
    assert rationale["outreachAngle"]
    assert rationale["businessContext"]

    with session_factory() as session:
        project = session.get(Project, "project_hanno_ai_hardware")
        stored_jobs = session.query(Job).filter(Job.project_id == "project_hanno_ai_hardware").all()
    assert project is not None
    assert len(stored_jobs) == 14


def test_get_project_jobs_supports_pagination(client: TestClient) -> None:
    response = client.get("/projects/project_2026_ai_team/jobs?skip=1&limit=1")

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "2"
    assert response.headers["x-has-more"] == "false"
    assert response.json() == [
        {
            "id": "job_robot_data_platform",
            "projectId": "project_2026_ai_team",
            "title": "机器人数据平台工程师",
            "headcount": 1,
            "status": "offer",
            "pipelineStatus": "done",
            "candidateCount": 1,
            "averageMatchScore": 85,
        }
    ]


def test_get_project_jobs_uses_bounded_queries(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add_all(
            [
                Job(
                    id=f"job_extra_{index}",
                    project_id="project_2026_ai_team",
                    title=f"Extra role {index}",
                    headcount=1,
                    status="sourcing",
                )
                for index in range(4)
            ]
        )
        session.commit()

    with session_factory() as session:
        bind = session.get_bind()

    select_statements: list[str] = []

    def count_selects(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    event.listen(bind, "before_cursor_execute", count_selects)
    try:
        response = client.get("/projects/project_2026_ai_team/jobs")
    finally:
        event.remove(bind, "before_cursor_execute", count_selects)

    assert response.status_code == 200
    assert len(response.json()) == 6
    assert len(select_statements) <= 5


def test_get_project_candidates_returns_joined_candidate_matches(client: TestClient) -> None:
    response = client.get("/projects/project_2026_ai_team/candidates")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "cand_lin_chen",
            "jobCandidateId": 1,
            "jobId": "job_vla_algorithm",
            "jobTitle": "VLA / 具身智能算法工程师",
            "name": "Alex Chen",
            "currentCompany": "Embodied AI Lab",
            "city": "深圳",
            "email": "alex.chen@example.com",
            "matchScore": 92,
            "pipelineStatus": "processing",
        },
        {
            "id": "cand_zhou_han",
            "jobCandidateId": 2,
            "jobId": "job_vla_algorithm",
            "jobTitle": "VLA / 具身智能算法工程师",
            "name": "Zhou Han",
            "currentCompany": "Robot Foundation Team",
            "city": "上海",
            "email": "zhou.han@example.com",
            "matchScore": 78,
            "pipelineStatus": "awaiting_human",
        },
        {
            "id": "cand_wang_ke",
            "jobCandidateId": 3,
            "jobId": "job_robot_data_platform",
            "jobTitle": "机器人数据平台工程师",
            "name": "Wang Ke",
            "currentCompany": "Autonomous Driving Data",
            "city": "上海",
            "email": "wang.ke@example.com",
            "matchScore": 85,
            "pipelineStatus": "done",
        },
    ]


def test_get_project_candidates_supports_pagination(client: TestClient) -> None:
    response = client.get("/projects/project_2026_ai_team/candidates?skip=1&limit=1")

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "3"
    assert response.headers["x-has-more"] == "true"
    assert response.json() == [
        {
            "id": "cand_zhou_han",
            "jobCandidateId": 2,
            "jobId": "job_vla_algorithm",
            "jobTitle": "VLA / 具身智能算法工程师",
            "name": "Zhou Han",
            "currentCompany": "Robot Foundation Team",
            "city": "上海",
            "email": "zhou.han@example.com",
            "matchScore": 78,
            "pipelineStatus": "awaiting_human",
        }
    ]


def test_get_project_candidates_marks_last_page_in_pagination_headers(client: TestClient) -> None:
    response = client.get("/projects/project_2026_ai_team/candidates?skip=2&limit=1")

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "3"
    assert response.headers["x-has-more"] == "false"
    assert [candidate["id"] for candidate in response.json()] == ["cand_wang_ke"]


def test_get_project_unique_candidates_deduplicates_candidates(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(
            JobCandidate(
                job_id="job_robot_data_platform",
                candidate_id="cand_lin_chen",
                match_score=88,
                pipeline_status="pending_outreach",
            )
        )
        session.commit()

    response = client.get("/projects/project_2026_ai_team/candidates/unique")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "cand_lin_chen",
            "name": "Alex Chen",
            "currentCompany": "Embodied AI Lab",
            "city": "深圳",
            "email": "alex.chen@example.com",
        },
        {
            "id": "cand_wang_ke",
            "name": "Wang Ke",
            "currentCompany": "Autonomous Driving Data",
            "city": "上海",
            "email": "wang.ke@example.com",
        },
        {
            "id": "cand_zhou_han",
            "name": "Zhou Han",
            "currentCompany": "Robot Foundation Team",
            "city": "上海",
            "email": "zhou.han@example.com",
        },
    ]


def test_get_project_unique_candidates_supports_pagination(client: TestClient) -> None:
    response = client.get("/projects/project_2026_ai_team/candidates/unique?skip=1&limit=1")

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "3"
    assert response.headers["x-has-more"] == "true"
    assert response.json() == [
        {
            "id": "cand_wang_ke",
            "name": "Wang Ke",
            "currentCompany": "Autonomous Driving Data",
            "city": "上海",
            "email": "wang.ke@example.com",
        }
    ]


def test_empty_project_lists_return_empty_arrays(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(
            Project(
                id="project_empty",
                name="Empty project",
                status="active",
                created_at=datetime(2026, 6, 9, tzinfo=timezone.utc),
            )
        )
        session.commit()

    assert client.get("/projects/project_empty/jobs").json() == []
    assert client.get("/projects/project_empty/candidates").json() == []
    assert client.get("/projects/project_empty/candidates/unique").json() == []


def test_project_created_at_naive_datetime_is_returned_as_utc(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(
            Project(
                id="project_naive_time",
                name="Naive time project",
                status="active",
                created_at=datetime(2026, 6, 9, 12, 30),
            )
        )
        session.commit()

    response = client.get("/projects/project_naive_time")

    assert response.status_code == 200
    assert response.json()["createdAt"] == "2026-06-09T12:30:00Z"


def test_utc_datetime_converts_aware_datetime_to_utc() -> None:
    value = datetime(2026, 6, 9, 8, 30, tzinfo=timezone(timedelta(hours=8)))

    assert _utc_datetime(value) == datetime(2026, 6, 9, 0, 30, tzinfo=timezone.utc)


def test_unknown_project_returns_404(client: TestClient) -> None:
    response = client.get("/projects/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found: missing"


def _seed_project(session: Session) -> None:
    project = Project(
        id="project_2026_ai_team",
        name="2026 AI 团队招聘",
        status="active",
        created_at=datetime(2026, 6, 9, tzinfo=timezone.utc),
    )
    jobs = [
        Job(
            id="job_vla_algorithm",
            project_id=project.id,
            title="VLA / 具身智能算法工程师",
            headcount=2,
            status="processing",
        ),
        Job(
            id="job_robot_data_platform",
            project_id=project.id,
            title="机器人数据平台工程师",
            headcount=1,
            status="offer",
        ),
    ]
    candidates = [
        Candidate(
            id="cand_lin_chen",
            name="Alex Chen",
            current_company="Embodied AI Lab",
            city="深圳",
            email="alex.chen@example.com",
        ),
        Candidate(
            id="cand_zhou_han",
            name="Zhou Han",
            current_company="Robot Foundation Team",
            city="上海",
            email="zhou.han@example.com",
        ),
        Candidate(
            id="cand_wang_ke",
            name="Wang Ke",
            current_company="Autonomous Driving Data",
            city="上海",
            email="wang.ke@example.com",
        ),
    ]
    matches = [
        JobCandidate(job_id="job_vla_algorithm", candidate_id="cand_lin_chen", match_score=92, pipeline_status="processing"),
        JobCandidate(job_id="job_vla_algorithm", candidate_id="cand_zhou_han", match_score=78, pipeline_status="awaiting_human"),
        JobCandidate(job_id="job_robot_data_platform", candidate_id="cand_wang_ke", match_score=85, pipeline_status="done"),
    ]

    session.add(project)
    session.add_all(jobs)
    session.add_all(candidates)
    session.flush()
    session.add_all(matches)
    session.commit()
