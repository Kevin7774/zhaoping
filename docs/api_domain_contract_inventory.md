# API 与领域契约资料清单

本文档汇总当前 `zhaoping` 仓库中可用于前后端对齐的核心 API 契约、领域实体、旧前端 API 封装、架构说明、DDL、鉴权、文件导入和状态流转资料。

生成时间：2026-06-09  
仓库路径：`/home/lison/Desktop/zhaoping`

## 1. 结论

当前仓库的契约资料是“部分完整”的：

- 后端 API 契约存在，但不是静态 `openapi.json` / `swagger.yaml` 文件，而是 FastAPI 运行时生成。
- 核心领域实体覆盖 `Job`、`Candidate`、`Task`、`AgentEvent`、`Feedback`。
- 邮件 / 触达链路有 provider 和配置，但没有独立的 `Email` / `Communication` 数据实体表。
- 周报有业务函数 `generate_weekly_report()`，但没有独立的 `Report` 数据实体表。
- 旧前端没有 React Router / Vue Router 路由配置；它是 React 单页工作台，通过状态和模块切换驱动。
- DDL、README 架构说明和能力集成文档存在。
- 当前没有看到应用级 JWT / OAuth2 登录鉴权代码；只有外部服务 token / API key 配置。
- 当前文件导入接口是 `file_path` 字符串，不是 multipart upload。

## 2. 后端核心 API 契约

### 2.1 FastAPI 入口

核心文件：

- `app/api/main.py`

关键位置：

- `app = FastAPI(title="Robot Talent Agent MVP")`
- 请求模型：`IngestRequest`、`MatchRequest`、`SearchRequest`、`RunRequest`、`WorkflowSessionRequest`、`ConfirmRequest` 等。
- API 路由集中定义在 `app/api/main.py`。

### 2.2 运行时 OpenAPI

FastAPI 会自动生成：

- Swagger UI：`/docs`
- OpenAPI JSON：`/openapi.json`

前端也有对应读取函数：

- `frontend/src/api.js`
- `fetchOpenApi()`

```js
export function fetchOpenApi() {
  return request('/openapi.json')
}
```

### 2.3 导出 OpenAPI JSON

建议用项目虚拟环境导出，因为 `pyproject.toml` 要求 Python `>=3.11`。

```bash
.venv/bin/python - <<'PY' > openapi.json
from app.api.main import app
import json

print(json.dumps(app.openapi(), ensure_ascii=False, indent=2))
PY
```

已验证该方式可生成 OpenAPI，版本为：

```text
3.1.0
```

API info：

```json
{
  "title": "Robot Talent Agent MVP",
  "version": "0.1.0"
}
```

### 2.4 当前主要 API 路径

从 FastAPI app 运行时生成的路径摘要：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查 |
| `GET` | `/scenarios/meta` | 场景与 Agent 元信息 |
| `GET` | `/workflow/meta` | 原子 workflow 元信息 |
| `GET` | `/integrations/status` | 集成状态，不返回密钥值 |
| `POST` | `/integrations/env` | 本地保存 allowlisted 环境变量 |
| `POST` | `/rsi/evaluate` | RSI 自评估 |
| `POST` | `/search/plan` | 搜索计划 |
| `POST` | `/search/run` | 执行搜索 |
| `POST` | `/search/evidence` | 生成证据记录 |
| `POST` | `/search/brief` | 生成情报 brief |
| `POST` | `/search/archive` | 归档搜索结果 |
| `GET` | `/search/archive/recent` | 最近归档 |
| `GET` | `/search/archive/diff` | 归档差异 |
| `POST` | `/search/watchlist/run` | 执行 watchlist |
| `POST` | `/scenarios/run` | 启动 A/B/C/D 场景任务 |
| `POST` | `/workflow/sessions` | 创建原子 workflow session |
| `POST` | `/workflow/sessions/{task_id}/nodes/{node_id}/run` | 运行 workflow 节点 |
| `POST` | `/workflow/sessions/{task_id}/nodes/{node_id}/retry` | 重试 workflow 节点 |
| `POST` | `/workflow/sessions/{task_id}/nodes/{node_id}/skip` | 跳过 workflow 节点 |
| `GET` | `/tasks/{task_id}` | 获取任务快照 |
| `GET` | `/tasks/{task_id}/stream` | SSE 任务事件流 |
| `POST` | `/tasks/{task_id}/cancel` | 取消任务 |
| `POST` | `/tasks/{task_id}/retry` | 重试任务 |
| `POST` | `/tasks/{task_id}/confirm` | 人工确认 |
| `POST` | `/tasks/{task_id}/probe-feedback` | 面试追问反馈回写 |
| `POST` | `/resumes/ingest` | 简历导入和向量化 |
| `POST` | `/jobs/match` | 岗位匹配检索 |
| `GET` | `/review/feedback` | Review feedback 占位接口 |

### 2.5 OpenAPI Components Schema

运行时 OpenAPI 中的主要 schema：

```text
AtomicNodeRunRequest
AtomicNodeSkipRequest
ConfirmRequest
EnvSaveRequest
HTTPValidationError
IngestRequest
MatchRequest
ProbeFeedbackRequest
RSIEvaluateRequest
RunRequest
SearchArchiveRequest
SearchEvidenceRequest
SearchRequest
SearchWatchlistRequest
ValidationError
WatchlistItem
WorkflowSessionRequest
```

## 3. 后端核心领域实体

### 3.1 Job 相关实体

文件：

- `app/db/schema.py`
- `app/db/create_schema.sql`
- `app/skills/tech_space.py`
- `app/skills/recruiting_scenarios.py`

数据库表：

- `job_capability_standard`
- `job_profile`

`job_capability_standard` 字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `capability_id` | `VARCHAR(64)` | 能力 ID，主键 |
| `tech_layer` | `VARCHAR(32)` | 技术层 |
| `capability_name_zh` | `VARCHAR(128)` | 中文能力名 |
| `capability_name_en` | `VARCHAR(128)` | 英文能力名 |
| `keywords` | `TEXT[]` | 关键词 |
| `evaluation_nodes` | `TEXT[]` | 评估节点 |
| `standard_interview_questions` | `TEXT[]` | 标准面试问题 |

`job_profile` 字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `job_profile_id` | `VARCHAR(64)` | 岗位画像 ID，主键 |
| `role_name` | `VARCHAR(128)` | 岗位名称 |
| `priority_level` | `VARCHAR(16)` | 优先级 |
| `is_ai_native_friendly` | `BOOLEAN` | 是否适合 AI 原生人才 |
| `essential_capabilities` | `JSONB` | 必备能力 |
| `preferred_capabilities` | `JSONB` | 加分能力 |
| `exclusion_tags` | `TEXT[]` | 排除标签 |
| `target_company_types` | `TEXT[]` | 目标公司类型 |
| `target_schools_labs` | `TEXT[]` | 目标学校 / 实验室 |
| `salary_range_min` | `INT` | 最低薪资 |
| `salary_range_max` | `INT` | 最高薪资 |

相关业务函数：

- `generate_job_profile_and_jd(requirement: str)`
- `build_talent_map(target: str)`
- `build_search_keywords(role_key: str)`

### 3.2 Candidate 相关实体

文件：

- `app/db/schema.py`
- `app/db/create_schema.sql`
- `app/schemas/candidate.py`
- `app/skills/recruiting_scenarios.py`

数据库表：

- `candidate_profile`

`candidate_profile` 字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `candidate_id` | `VARCHAR(64)` | 候选人 ID，主键 |
| `source_platform` | `VARCHAR(32)` | 来源平台 |
| `source_url` | `VARCHAR(512)` | 来源 URL |
| `is_ai_native_talent` | `BOOLEAN` | 是否 AI 原生人才 |
| `technical_layer_tags` | `TEXT[]` | 技术层标签 |
| `parsed_capabilities` | `JSONB` | 解析出的能力 |
| `github_metrics` | `JSONB` | GitHub 指标 |
| `huggingface_metrics` | `JSONB` | Hugging Face 指标 |
| `paper_metrics` | `JSONB` | 论文指标 |
| `raw_text_vector_id` | `VARCHAR(64)` | 原始文本向量 ID |

Pydantic schema：

- `CapabilityEvidence`
- `AINativeFeatures`
- `CandidateProfileEvaluation`

相关业务函数：

- `evaluate_candidate(candidate_material, target, team_constraint, aperture_weight)`

### 3.3 Feedback 相关实体

文件：

- `app/db/schema.py`
- `app/db/create_schema.sql`

数据库表：

- `agent_evaluation_feedback`

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `feedback_id` | `BIGSERIAL` | 反馈 ID，主键 |
| `candidate_id` | `VARCHAR(64)` | 候选人 ID |
| `target_job_profile_id` | `VARCHAR(64)` | 目标岗位画像 ID |
| `agent_score` | `INT` | Agent 评分，0-100 |
| `agent_match_reason` | `TEXT` | 匹配原因 |
| `reviewer_risk_alerts` | `TEXT[]` | reviewer 风险提示 |
| `human_status` | `VARCHAR(32)` | 人工状态 |
| `human_notes` | `TEXT` | 人工备注 |
| `created_at` | `TIMESTAMP` | 创建时间 |

允许的 `human_status`：

```text
pending
approved
rejected_overruled
modified
```

### 3.4 Task / AgentEvent 运行时实体

文件：

- `app/db/task_models.py`
- `app/schemas/tasks.py`
- `app/db/create_schema.sql`

数据库表：

- `tasks`
- `agent_events`

`tasks` 关键字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `task_id` | `VARCHAR(64)` | 任务 ID，主键 |
| `scenario_id` | `VARCHAR(32)` | 场景 ID |
| `input` | `TEXT` | 用户输入 |
| `status` | `VARCHAR(32)` | 任务状态 |
| `team_constraint` | `VARCHAR(256)` | 团队约束 |
| `aperture_weight` | `DOUBLE PRECISION` | 视角权重 |
| `frontend_state` | `JSONB` | 前端状态 |
| `current_agent` | `VARCHAR(64)` | 当前 Agent |
| `current_step` | `INT` | 当前步骤 |
| `total_steps` | `INT` | 总步骤数 |
| `awaiting` | `JSONB` | 等待人工输入的数据 |
| `result` | `JSONB` | 最终结果 |
| `error` | `TEXT` | 错误信息 |
| `steps_done` | `JSONB` | 已完成步骤 |
| `human_decision` | `JSONB` | 人工决策 |

允许的任务状态：

```text
processing
awaiting_human
done
error
cancelled
```

`agent_events` 关键字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `BIGSERIAL` | 事件 ID |
| `task_id` | `VARCHAR(64)` | 任务 ID |
| `type` | `VARCHAR(32)` | 事件类型 |
| `agent_id` | `VARCHAR(64)` | Agent ID |
| `step_index` | `INT` | 步骤序号 |
| `step_label` | `VARCHAR(128)` | 步骤标签 |
| `message` | `TEXT` | 事件消息 |
| `data` | `JSONB` | 事件数据 |
| `status` | `VARCHAR(32)` | 状态 |
| `created_at` | `TIMESTAMP` | 创建时间 |

允许的事件类型：

```text
step_start
tool_call
evidence
summary
human_gate
error
cancelled
```

### 3.5 Email / Communication

当前没有独立的邮件或通信数据实体表。

已有的是触达能力 provider 和配置：

- `app/providers/outreach.py`
- `config/services.toml`
- `.env.example`

provider：

- `HunterEmailFinderProvider`
- `ZeroBounceEmailValidationProvider`
- `NeverBounceEmailValidationProvider`
- `CompliantEmailDeliveryProvider`
- `PostmarkCompliantEmailProvider`
- `SendGridCompliantEmailProvider`

配置服务：

- `hunter_email_finder`
- `zerobounce_email_validation`
- `neverbounce_email_validation`
- `postmark_compliant_email`
- `sendgrid_compliant_email`

邮件发送安全约束：

- 默认要求人工审批：`manual_approval_required = true`
- 每日发送上限：`daily_send_limit = 50`
- suppression list：`data/outreach/suppression_list.jsonl`
- audit log：`data/outreach/email_audit.jsonl`
- 必须有退订链接：`UNSUBSCRIBE_BASE_URL`
- 发件人来自环境变量：`RECRUITING_CONTACT_EMAIL`

结论：这是触达 provider 层，不是领域实体层。如果前后端要做 Communication 页面，需要补表或统一事件模型。

### 3.6 Report

当前没有独立 `report` 表或 `Report` ORM。

已有的是场景 D 周报业务函数：

- `generate_weekly_report(weekly_data: str, focus_roles: List[str] | None = None)`

文件：

- `app/skills/recruiting_scenarios.py`

输出字段：

- `本周招聘结论`
- `关键岗位进展`
- `Top 候选人`
- `市场人才信号`
- `招聘风险`
- `下周行动建议`

结论：周报现在是业务函数输出，并通过任务 `result` 保存，不是独立 Report 实体。

## 4. 旧前端路由配置与 API 封装

### 4.1 前端技术栈

文件：

- `frontend/package.json`

当前依赖：

```json
{
  "dependencies": {
    "react": "^19.2.6",
    "react-dom": "^19.2.6"
  }
}
```

没有发现：

- `react-router`
- `vue-router`
- `RouterProvider`
- `BrowserRouter`
- `Routes`
- `Route`
- `createBrowserRouter`
- `useRoutes`

验证命令：

```bash
rg -n "react-router|vue-router|RouterProvider|BrowserRouter|Routes|Route|createBrowserRouter|useRoutes" \
  frontend/src frontend/package.json \
  -g '!frontend/node_modules/**' \
  -g '!frontend/dist/**'
```

该命令无匹配结果。

### 4.2 前端入口

文件：

- `frontend/src/main.jsx`

入口逻辑：

```jsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

### 4.3 主应用

文件：

- `frontend/src/App.jsx`

特征：

- 单页 Agent 工作台。
- 通过 hooks 管理当前场景、任务、模块、状态和报告。
- 没有 URL 路由配置。

相关 hooks：

- `frontend/src/hooks/useAgentWorkspace.js`
- `frontend/src/hooks/useAgentOrchestrator.js`

### 4.4 API 请求封装层

文件：

- `frontend/src/api.js`

基础配置：

```js
const BASE = import.meta.env.VITE_API_BASE ?? '/api'
export const API_DOCS_URL = BASE ? `${BASE}/docs` : '/docs'
```

核心封装：

```js
function request(path, options = {}) {
  const { body, query, ...fetchOptions } = options
  const init = { ...fetchOptions }
  if (body !== undefined) {
    init.method = init.method || 'POST'
    init.headers = { 'Content-Type': 'application/json', ...(init.headers || {}) }
    init.body = JSON.stringify(body)
  }
  return fetch(`${BASE}${path}${queryString(query)}`, init).then(handle)
}
```

前端 API 函数：

| 函数 | 后端接口 |
| --- | --- |
| `fetchHealth()` | `GET /health` |
| `fetchMeta()` | `GET /scenarios/meta` |
| `fetchWorkflowMeta()` | `GET /workflow/meta` |
| `fetchOpenApi()` | `GET /openapi.json` |
| `fetchIntegrationStatus()` | `GET /integrations/status` |
| `saveIntegrationEnv(values)` | `POST /integrations/env` |
| `createSearchPlan(payload)` | `POST /search/plan` |
| `runSearch(payload)` | `POST /search/run` |
| `createSearchEvidence(payload)` | `POST /search/evidence` |
| `createSearchBrief(payload)` | `POST /search/brief` |
| `archiveSearchArtifact(payload)` | `POST /search/archive` |
| `fetchRecentArchives(params)` | `GET /search/archive/recent` |
| `fetchArchiveDiff(params)` | `GET /search/archive/diff` |
| `runSearchWatchlist(payload)` | `POST /search/watchlist/run` |
| `ingestResume(payload)` | `POST /resumes/ingest` |
| `matchJobs(payload)` | `POST /jobs/match` |
| `evaluateRsi(payload)` | `POST /rsi/evaluate` |
| `fetchReviewFeedback()` | `GET /review/feedback` |
| `runScenario(...)` | `POST /scenarios/run` |
| `createWorkflowSession(...)` | `POST /workflow/sessions` |
| `runWorkflowNode(...)` | `POST /workflow/sessions/{task_id}/nodes/{node_id}/run` |
| `retryWorkflowNode(...)` | `POST /workflow/sessions/{task_id}/nodes/{node_id}/retry` |
| `skipWorkflowNode(...)` | `POST /workflow/sessions/{task_id}/nodes/{node_id}/skip` |
| `fetchTask(taskId)` | `GET /tasks/{task_id}` |
| `taskStreamUrl(taskId)` | `GET /tasks/{task_id}/stream` |
| `cancelTask(taskId)` | `POST /tasks/{task_id}/cancel` |
| `retryTask(taskId)` | `POST /tasks/{task_id}/retry` |
| `confirmTask(...)` | `POST /tasks/{task_id}/confirm` |
| `sendProbeFeedback(...)` | `POST /tasks/{task_id}/probe-feedback` |

## 5. 架构设计文档与数据库 DDL

### 5.1 架构说明

文件：

- `README.md`

覆盖内容：

- 项目能力概览
- AI 原生招聘行研 Agent 全链路
- 功能图
- 团队画像图
- 数据 Pipeline
- 关键目录
- API 示例
- 场景 A/B/C/D 工作流
- 能力标准治理与溯源
- 外部服务 provider 说明

### 5.2 能力集成规范

文件：

- `docs/capability_integration.md`

覆盖内容：

- 新增 capability 的集成规则
- 配置、provider、router、metadata、测试要求
- task status 和 audit event 约束
- 禁止硬编码 API key、token、私有 endpoint

### 5.3 Watchlist 调度说明

文件：

- `docs/watchlist_scheduling.md`

覆盖内容：

- watchlist 一次性运行
- cron / systemd timer
- 验证方式
- 合规约束

### 5.4 DDL

文件：

- `app/db/create_schema.sql`

包含表：

- `job_capability_standard`
- `job_profile`
- `candidate_profile`
- `agent_evaluation_feedback`
- `tasks`
- `agent_events`

## 6. 鉴权、文件上传、状态流转

### 6.1 鉴权

当前没有看到应用级 JWT / OAuth2 登录鉴权代码。

已存在的是外部 provider 的 token / API key 配置，例如：

- `GITHUB_TOKEN`
- `HF_TOKEN`
- `X_BEARER_TOKEN`
- `OPENROUTER_API_KEY`
- `POSTMARK_SERVER_TOKEN`
- `SENDGRID_API_KEY`
- `HUNTER_API_KEY`
- `ZEROBOUNCE_API_KEY`

`/integrations/status` 会返回安全的服务状态，不返回 secret。

`/integrations/env` 只允许本地请求保存 allowlisted 环境变量：

- `127.0.0.1`
- `::1`
- `localhost`
- `testclient`

除非设置：

```bash
ALLOW_REMOTE_ENV_SAVE=true
```

### 6.2 文件导入

当前简历导入接口：

```http
POST /resumes/ingest
```

请求体：

```json
{
  "file_path": "test_readme.md",
  "candidate_id": "cand_ai_native_002",
  "write_database": false
}
```

实现位置：

- `app/api/main.py`
- `ingest_resume(request: IngestRequest)`

注意：

- 当前不是 multipart upload。
- 后端检查 `Path(request.file_path).exists()`。
- 实际解析和向量化由 `process_and_vectorize_resume()` 完成。

### 6.3 状态流转

任务状态：

```text
processing
awaiting_human
done
error
cancelled
```

核心接口：

- `POST /scenarios/run`
- `POST /workflow/sessions`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/stream`
- `POST /tasks/{task_id}/confirm`
- `POST /tasks/{task_id}/cancel`
- `POST /tasks/{task_id}/retry`

状态变化来源：

- `app/core/orchestrator.py`
- `app/db/task_models.py`
- `app/schemas/tasks.py`

事件类型：

```text
step_start
tool_call
evidence
summary
human_gate
error
cancelled
```

前端通过 SSE 监听：

```js
export function taskStreamUrl(taskId) {
  return `${BASE}/tasks/${taskId}/stream`
}
```

## 7. 当前缺口

### 7.1 缺少静态 API 契约文件

当前没有仓库内静态文件：

- `openapi.json`
- `openapi.yaml`
- `swagger.json`
- `swagger.yaml`
- Postman Collection
- Protobuf 文件

建议：

- 增加 `docs/openapi.json` 或 `docs/openapi.yaml`
- 在 CI 中校验 OpenAPI 是否能生成

### 7.2 缺少 Communication 实体

当前触达链路是 provider 级实现，缺少统一业务实体。

建议补充表：

- `communication_threads`
- `communication_messages`
- `communication_events`
- `email_suppression_entries`

或者复用 `agent_events`，但需要明确事件语义和查询方式。

### 7.3 缺少 Report 实体

当前周报通过 `generate_weekly_report()` 输出，并存到 task result。

建议补充表：

- `reports`
- `report_sections`
- `report_citations`

最低限度也可以增加：

- `report_id`
- `scenario_id`
- `task_id`
- `report_type`
- `title`
- `content_json`
- `created_at`
- `updated_at`

### 7.4 缺少应用级登录鉴权

当前没有 JWT / OAuth2 用户登录鉴权。

如果要进入多人或外部访问场景，需要补：

- 用户表
- session 或 JWT 机制
- 权限模型
- API dependency guard
- 前端登录态处理
- secret / env 管理策略

### 7.5 文件上传不是浏览器上传模式

当前 `/resumes/ingest` 使用本地路径。

如果要支持网页上传，需要新增：

- `UploadFile`
- multipart form
- 文件大小限制
- 文件类型白名单
- 存储目录隔离
- 病毒 / 内容安全检查
- 文件清理策略

## 8. 验证命令

### 8.1 定位文件

```bash
rg --files \
  -g 'README*' \
  -g 'package.json' \
  -g 'pyproject.toml' \
  -g '*.sql' \
  -g '*openapi*' \
  -g '*swagger*' \
  -g '*.proto'
```

### 8.2 生成 OpenAPI 路径摘要

```bash
.venv/bin/python - <<'PY'
from app.api.main import app

spec = app.openapi()
print(spec.get("openapi"))
print(spec.get("info", {}))
for path, methods in sorted(spec.get("paths", {}).items()):
    print(path, ",".join(sorted(m.upper() for m in methods)))
PY
```

### 8.3 查看 OpenAPI schema 列表

```bash
.venv/bin/python - <<'PY'
from app.api.main import app

spec = app.openapi()
for name in sorted((spec.get("components") or {}).get("schemas", {})):
    print(name)
PY
```

### 8.4 搜索前端路由依赖

```bash
rg -n "react-router|vue-router|RouterProvider|BrowserRouter|Routes|Route|createBrowserRouter|useRoutes" \
  frontend/src frontend/package.json \
  -g '!frontend/node_modules/**' \
  -g '!frontend/dist/**'
```

### 8.5 搜索邮件 / 触达相关代码

```bash
rg -n "email|Email|Communication|communication|outreach|触达|postmark|sendgrid|hunter|zerobounce" \
  app config README.md .env.example docs \
  -g '!frontend/node_modules/**' \
  -g '!frontend/dist/**'
```

## 9. 建议下一步

优先级建议：

1. 导出并提交 `docs/openapi.json`，让前端和后端有稳定契约文件。
2. 决定是否要补 `Communication` 和 `Report` 独立实体。
3. 如果要支持浏览器上传，改造 `/resumes/ingest` 为 multipart upload，同时保留本地路径模式作为 CLI / 运维入口。
4. 如果要外部访问或多人协作，先补应用级鉴权和权限边界。
5. 为 API 契约增加静态测试，至少验证 OpenAPI 可生成、关键路径存在、前端 API 封装路径不漂移。

