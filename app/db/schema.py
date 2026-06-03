from __future__ import annotations

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

TECH_LAYERS = (
    "brain",
    "brain_learning",
    "brain_simulator",
    "cerebellum",
    "cerebellum_control",
    "cerebellum_action",
    "perception",
    "perception_vlm",
    "perception_spatial",
    "spatial",
    "spatial_navigation",
    "actuation",
    "actuation_tactile",
    "embedded",
    "embedded_hardware",
    "data_tool",
    "data_infrastructure",
    "teleoperation",
    "QA",
    "QA_reliability",
    "hardware_test",
    "system_architecture",
    "hardware_software_co_design",
    "dynamics",
    "foundation_model",
    "data_generation",
    "manipulation",
)

PRIORITY_LEVELS = ("critical", "high", "medium", "low")
SOURCE_PLATFORMS = ("boss", "liepin", "github", "huggingface", "bgbg", "paper", "internal")
HUMAN_STATUSES = ("pending", "approved", "rejected_overruled", "modified")


def _in_constraint(column_name: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    quoted = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column_name} IN ({quoted})", name=name)


job_capability_standard = Table(
    "job_capability_standard",
    metadata,
    Column("capability_id", String(64), primary_key=True),
    Column("tech_layer", String(32), nullable=False),
    Column("capability_name_zh", String(128), nullable=False),
    Column("capability_name_en", String(128), nullable=False),
    Column("keywords", ARRAY(Text), nullable=False),
    Column("evaluation_nodes", ARRAY(Text), nullable=False),
    Column("standard_interview_questions", ARRAY(Text)),
    _in_constraint("tech_layer", TECH_LAYERS, "ck_job_capability_standard_tech_layer"),
)

job_profile = Table(
    "job_profile",
    metadata,
    Column("job_profile_id", String(64), primary_key=True),
    Column("role_name", String(128), nullable=False),
    Column("priority_level", String(16), nullable=False, server_default="medium"),
    Column("is_ai_native_friendly", Boolean, nullable=False, server_default="false"),
    Column("essential_capabilities", JSONB, nullable=False),
    Column("preferred_capabilities", JSONB),
    Column("exclusion_tags", ARRAY(Text)),
    Column("target_company_types", ARRAY(Text)),
    Column("target_schools_labs", ARRAY(Text)),
    Column("salary_range_min", Integer),
    Column("salary_range_max", Integer),
    _in_constraint("priority_level", PRIORITY_LEVELS, "ck_job_profile_priority_level"),
    CheckConstraint(
        "salary_range_min IS NULL OR salary_range_max IS NULL OR salary_range_min <= salary_range_max",
        name="ck_job_profile_salary_range",
    ),
)

candidate_profile = Table(
    "candidate_profile",
    metadata,
    Column("candidate_id", String(64), primary_key=True),
    Column("source_platform", String(32), nullable=False),
    Column("source_url", String(512)),
    Column("is_ai_native_talent", Boolean, nullable=False, server_default="false"),
    Column("technical_layer_tags", ARRAY(Text)),
    Column("parsed_capabilities", JSONB),
    Column("github_metrics", JSONB),
    Column("huggingface_metrics", JSONB),
    Column("paper_metrics", JSONB),
    Column("raw_text_vector_id", String(64)),
    _in_constraint("source_platform", SOURCE_PLATFORMS, "ck_candidate_profile_source_platform"),
)

agent_evaluation_feedback = Table(
    "agent_evaluation_feedback",
    metadata,
    Column("feedback_id", BigInteger, primary_key=True, autoincrement=True),
    Column("candidate_id", String(64), nullable=False),
    Column("target_job_profile_id", String(64), nullable=False),
    Column("agent_score", Integer, nullable=False),
    Column("agent_match_reason", Text, nullable=False),
    Column("reviewer_risk_alerts", ARRAY(Text), nullable=False),
    Column("human_status", String(32), nullable=False, server_default="pending"),
    Column("human_notes", Text),
    Column("created_at", DateTime, nullable=False, server_default=func.current_timestamp()),
    CheckConstraint("agent_score >= 0 AND agent_score <= 100", name="ck_agent_score_range"),
    _in_constraint("human_status", HUMAN_STATUSES, "ck_agent_evaluation_feedback_human_status"),
)


def create_all(engine) -> None:
    """Create all MVP tables on a PostgreSQL SQLAlchemy engine."""
    metadata.create_all(engine)
