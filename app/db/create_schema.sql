CREATE TABLE IF NOT EXISTS job_capability_standard (
    capability_id VARCHAR(64) PRIMARY KEY,
    tech_layer VARCHAR(32) NOT NULL,
    capability_name_zh VARCHAR(128) NOT NULL,
    capability_name_en VARCHAR(128) NOT NULL,
    keywords TEXT[] NOT NULL,
    evaluation_nodes TEXT[] NOT NULL,
    standard_interview_questions TEXT[],
    CONSTRAINT ck_job_capability_standard_tech_layer CHECK (
        tech_layer IN (
            'brain','brain_learning','brain_simulator','cerebellum','cerebellum_control',
            'cerebellum_action','perception','perception_vlm','perception_spatial','spatial',
            'spatial_navigation','actuation','actuation_tactile','embedded','embedded_hardware',
            'data_tool','data_infrastructure','teleoperation','QA','QA_reliability',
            'hardware_test','system_architecture','hardware_software_co_design','dynamics',
            'foundation_model','data_generation','manipulation'
        )
    )
);

CREATE TABLE IF NOT EXISTS job_profile (
    job_profile_id VARCHAR(64) PRIMARY KEY,
    role_name VARCHAR(128) NOT NULL,
    priority_level VARCHAR(16) NOT NULL DEFAULT 'medium',
    is_ai_native_friendly BOOLEAN NOT NULL DEFAULT FALSE,
    essential_capabilities JSONB NOT NULL,
    preferred_capabilities JSONB,
    exclusion_tags TEXT[],
    target_company_types TEXT[],
    target_schools_labs TEXT[],
    salary_range_min INT,
    salary_range_max INT,
    CONSTRAINT ck_job_profile_priority_level CHECK (priority_level IN ('critical','high','medium','low')),
    CONSTRAINT ck_job_profile_salary_range CHECK (
        salary_range_min IS NULL OR salary_range_max IS NULL OR salary_range_min <= salary_range_max
    )
);

CREATE TABLE IF NOT EXISTS candidate_profile (
    candidate_id VARCHAR(64) PRIMARY KEY,
    source_platform VARCHAR(32) NOT NULL,
    source_url VARCHAR(512),
    is_ai_native_talent BOOLEAN NOT NULL DEFAULT FALSE,
    technical_layer_tags TEXT[],
    parsed_capabilities JSONB,
    github_metrics JSONB,
    huggingface_metrics JSONB,
    paper_metrics JSONB,
    raw_text_vector_id VARCHAR(64),
    CONSTRAINT ck_candidate_profile_source_platform CHECK (
        source_platform IN ('boss','liepin','github','huggingface','bgbg','paper','internal')
    )
);

CREATE TABLE IF NOT EXISTS agent_evaluation_feedback (
    feedback_id BIGSERIAL PRIMARY KEY,
    candidate_id VARCHAR(64) NOT NULL,
    target_job_profile_id VARCHAR(64) NOT NULL,
    agent_score INT NOT NULL,
    agent_match_reason TEXT NOT NULL,
    reviewer_risk_alerts TEXT[] NOT NULL,
    human_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    human_notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_agent_score_range CHECK (agent_score >= 0 AND agent_score <= 100),
    CONSTRAINT ck_agent_evaluation_feedback_human_status CHECK (
        human_status IN ('pending','approved','rejected_overruled','modified')
    )
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id VARCHAR(64) PRIMARY KEY,
    scenario_id VARCHAR(32) NOT NULL,
    input TEXT NOT NULL,
    status VARCHAR(32) NOT NULL,
    team_constraint VARCHAR(256) NOT NULL DEFAULT '真机泛化',
    aperture_weight DOUBLE PRECISION NOT NULL DEFAULT 0.7,
    frontend_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    current_agent VARCHAR(64),
    current_step INT NOT NULL DEFAULT -1,
    total_steps INT NOT NULL DEFAULT 0,
    awaiting JSONB,
    result JSONB,
    error TEXT,
    steps_done JSONB NOT NULL DEFAULT '[]'::jsonb,
    human_decision JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_tasks_status CHECK (
        status IN ('processing','awaiting_human','done','error','cancelled')
    )
);

CREATE INDEX IF NOT EXISTS ix_tasks_scenario_id ON tasks (scenario_id);
CREATE INDEX IF NOT EXISTS ix_tasks_status ON tasks (status);

CREATE TABLE IF NOT EXISTS agent_events (
    id BIGSERIAL PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    type VARCHAR(32) NOT NULL,
    agent_id VARCHAR(64),
    step_index INT,
    step_label VARCHAR(128),
    message TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(32),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_agent_events_type CHECK (
        type IN ('step_start','tool_call','evidence','summary','human_gate','error','cancelled')
    )
);

CREATE INDEX IF NOT EXISTS ix_agent_events_task_id ON agent_events (task_id);
CREATE INDEX IF NOT EXISTS ix_agent_events_type ON agent_events (type);
CREATE INDEX IF NOT EXISTS ix_agent_events_task_id_id ON agent_events (task_id, id);
