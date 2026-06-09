from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl

from app.schemas.common import CamelModel


class CapabilityEvidence(BaseModel):
    capability_id: str = Field(description="对应标准能力库中的ID，例如 cap_vla_imitation")
    matched_score: int = Field(description="该项能力评分 0-100", ge=0, le=100)
    experience_months: int = Field(description="该能力的实际项目经验月数", ge=0)
    evidence_text: str = Field(description="从简历或GitHub作品中抽取的具体事实依据、项目陈述")


class AINativeFeatures(BaseModel):
    uses_cursor_or_claude_code: bool = Field(description="是否有痕迹表明其高频使用AI原生开发工具")
    has_independent_agent_projects: bool = Field(description="是否独立开发过Agent、RAG、工作流或多模态工具")
    github_active_contributor: bool = Field(description="GitHub是否有高星开源库贡献或高频提交痕迹")
    community_footprints: List[str] = Field(
        default_factory=list,
        description="抓取到的社区痕迹标签，如 [HuggingFace-Spaces, 即刻AI圈, B站技术Up]",
    )


class CandidateProfileEvaluation(BaseModel):
    candidate_raw_id: str
    target_role: str = Field(description="12个具身岗位名称之一")
    is_ai_native_talent: bool = Field(description="综合研判：此候选人是否属于高潜AI原生年轻人")
    capability_match_matrix: List[CapabilityEvidence] = Field(description="抽取的各项机器人底层能力矩阵证明")
    ai_native_attributes: AINativeFeatures = Field(description="AI原生特质硬指标审核结果")
    overall_match_score: int = Field(description="岗位总体匹配得分 0-100", ge=0, le=100)
    risk_alerts: List[str] = Field(default_factory=list, description="红旗信号/硬伤提示")
    custom_interview_prompts: List[str] = Field(default_factory=list, description="技术一面定制追问问题")
    source_url: Optional[HttpUrl] = Field(default=None, description="候选人外部资料链接")
    parsed_capabilities: Optional[Dict[str, CapabilityEvidence]] = Field(
        default=None,
        description="按 capability_id 索引的能力证据，便于写入 candidate_profile.parsed_capabilities",
    )


class CandidateRequest(CamelModel):
    name: str = Field(min_length=1, max_length=128)
    current_company: str | None = Field(default=None, max_length=128)
    city: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=256)


class CandidateCreate(CandidateRequest):
    id: str = Field(min_length=1, max_length=64)


class CandidateResponse(CandidateRequest):
    id: str
    job_candidate_id: int
    job_id: str
    job_title: str
    match_score: int = Field(ge=0, le=100)
    pipeline_status: str
