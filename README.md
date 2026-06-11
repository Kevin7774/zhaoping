# 机器人招聘 Agent MVP

面向机器人与 AI 原生团队招聘的工程化 Agent MVP。系统把项目/BP 材料、岗位画像、候选人材料、搜索情报、人工确认、触达和周报统一到 FastAPI 后端、React 控制台、配置化 provider 路由、任务运行时和本地证据归档中。

当前 README 只记录已经接入或代码中真实存在的能力。能力集成规范见 `docs/capability_integration.md`，服务注册表以 `config/services.toml` 为准。

## 当前能力

| 能力域 | 已实现内容 | 主要入口 |
| --- | --- | --- |
| 项目招聘工作台 | 项目创建、BP/项目提示词导入、岗位矩阵预览/初始化、项目岗位、候选人、候选人去重、合规确认、周报读取。 | `frontend/src/pages/ProjectDetailPage.tsx`、`app/api/routers/projects.py` |
| BP 岗位生成 | 五阶段 pipeline：claims、capability graph、gap analysis、role design、critic gate；输出岗位、能力缺口、研究 trace 和被拒岗位。 | `app/core/bp_pipeline.py` |
| A/B/C/D 招聘场景 | A 岗位画像与 JD，B 人才地图，C 候选人评估，D 招聘周报；支持完整任务和原子节点 `run/retry/skip`。 | `app/core/orchestrator.py`、`app/skills/recruiting_scenarios.py` |
| 任务运行时 | `tasks` / `agent_events` 持久化，SSE 事件流、polling fallback、取消、重试、人工确认、artifact 读取。 | `app/db/task_models.py`、`GET /tasks/{task_id}/stream` |
| JSON Workflow | 支持 `search`、`llm_prompt`、`structured_extract`、`save_artifact`、`human_gate`；长 search 输出写入 artifact。 | `app/core/workflow_dsl.py`、`app/core/workflow_runner.py` |
| 搜索情报 | `plan -> run -> evidence -> brief -> archive`，支持 watchlist、recent/diff、Evidence Ledger。 | `app/providers/search.py`、`app/core/intelligence_archive.py` |
| 候选人数据 | 简历解析、项目岗位简历上传、本地简历导入、向量入库、项目库/向量库匹配、候选人线索入库。 | `app/api/routers/resumes.py`、`app/rag/ingest_worker.py` |
| 分群与触达 | Segment 查询/保存/读取；邮件草稿、人工编辑、模拟或真实发送保护、触达历史。 | `app/api/routers/segments.py`、`app/api/routers/outreach.py` |
| 评估闭环 | Self-RSI local/full 评估，输出能力 trace、反馈缺口、测试结果和迭代计划。 | `app/providers/evaluation.py` |
| 集成状态 | 动态读取 `config/services.toml`，返回 provider 状态、中文名、代码路径、缺密钥/缺工具状态，不返回密钥值。 | `GET /integrations/status` |
| 前端控制台 | Workflow、Search Intel、Archive Watch、Candidate、Evaluation、Ops 工作区和能力注册表。 | `frontend/src/capabilities/capabilityRegistry.js` |

## 最新搜索能力

搜索能力分为本地目录规划、可控 live provider、浏览器授权平台搜索和网页正文读取。搜索型项目任务使用结构化 `frontend_state`。

```json
{
  "search_profile": "candidate_sourcing",
  "execution_policy": "bounded_live",
  "source_layers": ["academic", "code_model", "social", "news_funding"],
  "search_budget": {
    "max_providers": 14,
    "per_provider_limit": 3,
    "timeout_seconds": 10,
    "max_crawl_pages": 0
  }
}
```

`talent_source_catalog` 是来源规划目录，不直接抓取网页。它会根据 query
返回推荐信源、风险提示、建议 query，以及 `executable_services` /
`frontend_layers` 路由提示。场景 B 会把这些推荐映射到真实 provider，先按
catalog 推荐排序，再受 `source_layers` 和 `search_budget` 约束执行 live
search。

`execution_policy` 当前有效值：

| 值 | 行为 |
| --- | --- |
| `bounded_live` | 默认标准联网，受 provider 数、每 provider 数量和 timeout 控制。默认 provider 上限为 14，不自动触发浏览器平台搜索。 |
| `deep_live` | 深度联网，默认 provider 上限为 36；只有 `search_budget.max_crawl_pages > 0` 时才启用 crawler snapshot。 |

### Live Search Provider

| 分组 | Services | 说明 |
| --- | --- | --- |
| 默认联邦入口 | `due_diligence_federated_search` | 默认 search service；组合本地来源目录、开放网页和 live provider，输出覆盖矩阵、计划、brief 和证据线索。 |
| 开放网页 | `brave_web_search` | Brave Web Search API；需要 `BRAVE_SEARCH_API_KEY`。 |
| GitHub / 模型生态 | `github_candidates`、`github_repositories`、`github_code`、`github_topics`、`github_users`、`huggingface_models` | GitHub 候选人、用户、仓库、代码、topic 和 Hugging Face 模型信号；GitHub token 走 `GITHUB_TOKEN`，HF token 可选 `HF_TOKEN`。 |
| 学术 | `openalex_works_search`、`openalex_authors_search`、`openalex_institutions_search`、`semantic_scholar_papers_search` | 论文、作者、机构、引用、venue 和开放访问链接。 |
| 社媒/社区 | `agent_reach_social_search` | 微博、B站、V2EX、知乎、掘金、CSDN、SegmentFault 等公开搜索线索。 |
| 授权平台 | `opencli_platform_search` | OpenCLI 浏览器授权平台搜索；覆盖 B站、知乎、小红书、LinkedIn、YouTube、X/Twitter、Reddit、微信公众号，前端默认关闭，需要显式开启 `platform_search`。 |
| 网页正文 | `opencli_web_read_search`、`opencli_crawl_scrape` | OpenCLI `web read`，用于已发现 URL 的 Markdown/HTML/metadata 读取。 |
| 学校/竞赛 | `education_competition_monitor` | 高校官网、实验室页、天池、DataFountain、CCF、ICPC/CCPC、蓝桥杯、Kaggle 目标。 |
| 新闻/融资 | `gnews_funding_news` | GNews 融资新闻需要 `GNEWS_API_KEY`。 |
| 监管/尽调 | `sec_edgar_company_filings`、`sec_company_facts`、`sec_insider_transactions`、`sec_ownership_activism`、`sec_investment_adviser_reports`、`fdic_bankfind_institutions`、`federal_register_documents`、`cpsc_recalls`、`fda_enforcement_recalls`、`fda_device_510k`、`fda_device_events`、`fda_device_classification`、`fda_device_registration_listing`、`cfpb_consumer_complaints`、`nhtsa_recalls`、`epa_echo_facilities`、`clinicaltrials_studies`、`sec_enforcement_search`、`usaspending_awards`、`grants_gov_opportunities` | 公司披露、财务事实、内部人交易、控制权、投顾/ERA、银行机构、监管文件、召回、FDA、CFPB、NHTSA、EPA、临床试验、SEC enforcement、政府合同/拨款和非稀释资金。 |

### OpenCLI / Agent-Reach 状态

`opencli_platform_search` 已接入这些命令，并通过 `platform_search` 前端层显式开启；服务配置限制单次最多跑 4 个平台，避免普通候选人搜索触发长时间浏览器 fan-out：

```text
opencli bilibili search ...
opencli zhihu search ...
opencli xiaohongshu search ...
opencli linkedin people-search ...
opencli youtube search ...
opencli twitter search ...
opencli reddit search ...
opencli weixin search ...
```

运行时要求：

- `opencli` 命令存在。
- OpenCLI Browser Bridge 已连接。
- 需要登录态的平台必须先在 Chrome/Chromium 登录。例如 X/Twitter 缺 `ct0` cookie 时会返回 `AUTH_REQUIRED`。
- Reddit 和微信公众号搜索可通过 OpenCLI 只读 smoke 验证；平台结果仍只能作为线索，关键结论必须回看原文。

外部工具只使用公开页面、官方站点行为、用户授权登录态或用户提供材料；不绕过登录、付费墙、robots.txt、访问控制或平台条款。

## API 能力总览

以 `/openapi.json`、`app/api/main.py`、`app/api/routers/` 和 `frontend/src/capabilities/capabilityRegistry.js` 为准。

| 能力域 | 主要路径 | 状态 | 用途 |
| --- | --- | --- | --- |
| 系统状态与集成 | `GET /health`、`GET /integrations/status`、`POST /integrations/env` | system | 健康检查、provider 状态、安全保存 allowlist 环境变量。 |
| 项目工作台 | `GET/POST /projects`、`GET /projects/{project_id}`、`GET /projects/{project_id}/jobs`、`GET /projects/{project_id}/candidates`、`GET /projects/{project_id}/candidates/unique` | productized | 项目、岗位、候选人和统计。 |
| BP 岗位生成 | `POST /projects/{project_id}/materials/upload`、`POST /projects/{project_id}/preview-from-bp`、`POST /projects/{project_id}/initialize-from-bp` | productized | 上传材料、预览岗位矩阵、写入岗位。 |
| 候选人入库与匹配 | `POST /resumes/ingest`、`POST /resumes/local-import`、`POST /projects/{project_id}/jobs/{job_id}/upload-resumes`、`POST /jobs/match` | productized | 简历解析、向量入库、岗位匹配。 |
| 候选人搜索计划 | `GET /projects/{project_id}/candidate-search-schedules`、`PUT /projects/{project_id}/jobs/{job_id}/candidate-search-schedule` | productized | 保存岗位级自动搜候选人计划，调度器触发场景 B。 |
| 搜索情报 | `POST /search/plan`、`POST /search/run`、`POST /search/evidence`、`POST /search/brief`、`POST /search/archive`、`GET /search/archive/recent`、`GET /search/archive/diff`、`POST /search/watchlist/run` | productized | 计划、执行、证据、简报、归档和 watchlist。 |
| 场景任务 | `GET /scenarios/meta`、`POST /scenarios/run` | productized | 启动 A/B/C/D 招聘场景任务。 |
| 任务运行时 | `GET /tasks/{task_id}`、`GET /tasks/{task_id}/stream`、`POST /tasks/{task_id}/confirm`、`POST /tasks/{task_id}/cancel`、`POST /tasks/{task_id}/retry`、`GET /tasks/{task_id}/artifacts`、`POST /tasks/{task_id}/probe-feedback` | system | 快照、SSE、确认、取消、重试、artifact 和追问反馈。 |
| 原子工作流 | `GET /workflow/meta`、`POST /workflow/sessions`、`POST /workflow/sessions/{task_id}/nodes/{node_id}/run`、`POST /workflow/sessions/{task_id}/nodes/{node_id}/retry`、`POST /workflow/sessions/{task_id}/nodes/{node_id}/skip` | system | 节点级控制 A/B/C/D。 |
| JSON Workflow | `POST /workflows/validate`、`POST /workflows/run` | productized/system | 校验并运行自定义 search、LLM、结构化抽取、artifact 和 human gate 流程。 |
| RSI 评估 | `POST /rsi/evaluate` | productized | 运行 local/full 评估。 |
| 分群与触达 | `POST /segments/query`、`POST/GET /segments`、`GET /segments/{segment_id}`、`POST /outreach/draft`、`PATCH /outreach/drafts/{draft_id}`、`POST /outreach/send`、`GET /outreach/history` | productized | Segment、邮件草稿、人工编辑、发送和历史。 |
| 周报 | `POST /reports/weekly`、`GET /projects/{project_id}/reports/latest`、`GET /reports/{report_id}` | productized | 周报写入与读取。 |
| 认证与开发监控 | `POST /auth/login`、`GET /auth/me`、`POST /monitor/start`、`GET /monitor/status` | productized/system | 登录态和开发监控。 |

任务状态固定为 `processing`、`awaiting_human`、`done`、`error`、`cancelled`。前端优先使用 `GET /tasks/{task_id}/stream`，连接失败时回退到 `GET /tasks/{task_id}`。

## 关键目录

| 路径 | 作用 |
| --- | --- |
| `app/api/main.py` | FastAPI 入口，挂载前端静态资源和 API 路由。 |
| `app/api/routers/projects.py` | 项目、BP、岗位、候选人、合规确认和自动搜索计划。 |
| `app/api/routers/resumes.py` | 简历上传、本地简历导入和项目岗位简历任务。 |
| `app/api/routers/outreach.py` | 邮件触达闭环。 |
| `app/api/routers/segments.py` | 候选人 segment。 |
| `app/api/routers/reports.py` | 周报持久化。 |
| `app/core/orchestrator.py` | A/B/C/D 场景、任务运行时、搜索分层控制和 live provider 预算。 |
| `app/core/workflow_dsl.py` | JSON workflow DSL 校验。 |
| `app/core/workflow_runner.py` | JSON workflow 执行和 artifact 存储。 |
| `app/core/integration_status.py` | 集成状态聚合。 |
| `app/core/router.py` | `ServiceRouter`，按 `config/services.toml` 构造 provider。 |
| `app/core/config.py` | 服务配置加载与校验。 |
| `app/providers/` | document、OCR、embedding、vector、search、scraping、LLM、email、database、MCP、evaluation、structured output provider。 |
| `app/skills/tech_space.py` | 12 个机器人岗位、能力标准和团队画像。 |
| `app/skills/search_sources.py` | 搜索来源目录。 |
| `app/db/schema.py` / `app/models/` | 项目库 schema/model。 |
| `app/db/task_models.py` | 任务库 schema/model。 |
| `frontend/src/pages/ProjectDetailPage.tsx` | 项目详情主工作台。 |
| `frontend/src/capabilities/capabilityRegistry.js` | 前端能力、路径产品化状态和风险元数据。 |
| `frontend/src/shared/hooks/useTaskStream.ts` | SSE + polling task stream hook。 |
| `scripts/smoke_search_sources.py` | live search / external tool smoke。 |
| `scripts/run_watchlist.py` | 不启动 API 的 watchlist CLI。 |
| `docs/watchlist_scheduling.md` | watchlist 定时运行说明。 |
| `docs/capability_integration.md` | 新能力接入规范。 |

## 环境安装

优先使用仓库内 `.venv`。当前代码按 Python 3.12 运行；不要直接用系统 Python 3.10 跑测试。

```bash
.venv/bin/python --version
.venv/bin/python -m pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu121
pnpm --dir frontend install
```

`.env` 只保存在本机，不提交。常用变量：

```bash
PROJECT_DATABASE_URL=postgresql+psycopg://...
TASK_DATABASE_URL=postgresql+psycopg://...
OPENROUTER_API_KEY=...
BRAVE_SEARCH_API_KEY=...
GITHUB_TOKEN=...
HF_TOKEN=...
GNEWS_API_KEY=...
RESEND_API_KEY=...
HUNTER_API_KEY=...
ZEROBOUNCE_API_KEY=...
ALIBABA_CLOUD_ACCESS_KEY_ID=...
ALIBABA_CLOUD_ACCESS_KEY_SECRET=...
```

## 数据库

本地长期开发推荐 PostgreSQL：

```bash
docker volume create zhaoping_pg_data

docker run -d \
  --name zhaoping-postgres \
  --restart unless-stopped \
  -e POSTGRES_USER=zhaoping \
  -e POSTGRES_PASSWORD='换成你的本机密码' \
  -e POSTGRES_DB=zhaoping \
  -p 127.0.0.1:55432:5432 \
  -v zhaoping_pg_data:/var/lib/postgresql/data \
  postgres:16-alpine
```

建表：

```bash
psql "$DATABASE_URL" -f app/db/create_schema.sql
# 或
.venv/bin/python scripts/create_db.py
```

如果不配置数据库，项目仍可使用本地默认 SQLite task DB 和 disabled project DB 路由，但项目持久化能力会受限。

## 启动

生产式本地访问，前端先 build 后由 FastAPI 同域托管：

```bash
./scripts/start_phone.sh
```

默认地址：

- 本机：`http://127.0.0.1:8020`
- 手机：脚本会打印局域网地址，例如 `http://192.168.x.x:8020`
- 健康检查：`http://127.0.0.1:8020/health`

开发模式：

```bash
./start.sh
```

默认地址：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`
- 健康检查：`http://127.0.0.1:8000/health`

常用覆盖：

```bash
BACKEND_PORT=8010 FRONTEND_PORT=5174 ./start.sh
PUBLIC_HOST=你的电脑局域网IP ./scripts/start_dev.sh
KILL_OLD_DEV=0 ./start.sh
LOAD_ENV_FILE=0 ./start.sh
```

只启动 API：

```bash
set -a
source .env
set +a

.venv/bin/python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

临时公网演示：

```bash
./scripts/start_public_cloudflare.sh
setsid -f ./scripts/watch_public_cloudflare.sh >/dev/null 2>&1
```

运行状态文件：

- `data/runtime/cloudflare_url.txt`
- `data/runtime/phone_server.log`
- `data/runtime/cloudflared.log`
- `data/runtime/public_watch.log`

## 常用调用

简历入库：

```bash
curl -X POST http://localhost:8000/resumes/ingest \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"test_readme.md","candidate_id":"cand_ai_native_002"}'
```

岗位匹配：

```bash
curl -X POST http://localhost:8000/jobs/match \
  -H 'Content-Type: application/json' \
  -d '{"query":"Diffusion Policy 和遥操作数据清洗经验","top_k":5}'
```

搜索 brief：

```bash
curl -X POST http://localhost:8000/search/brief \
  -H 'Content-Type: application/json' \
  -d '{"query":"robotics foundation model hiring signal","limit":5}'
```

场景任务：

```bash
curl -X POST http://localhost:8000/scenarios/run \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"B","input":"找家庭机器人 VLA/SLAM 候选人","frontend_state":{"execution_policy":"bounded_live"}}'
```

RSI 评估：

```bash
curl -X POST http://localhost:8000/rsi/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"suite":"candidate_evaluation_core","threshold":0.8}'
```

## 本地 RAG 入库

```bash
.venv/bin/python -m app.rag.ingest_worker --file test_readme.md --candidate-id cand_ai_native_002
```

PDF、DOCX、图片走 Docling；Markdown/TXT 直接读取。默认 embedding 是 `bge_m3_local`，向量库是 `qdrant_local`，路径为 `./qdrant_mvp_store`。

可选写入候选人元数据到项目库：

```bash
.venv/bin/python -m app.rag.ingest_worker \
  --file test_readme.md \
  --candidate-id cand_ai_native_002 \
  --write-db
```

## Watchlist

一次性运行：

```bash
.venv/bin/python scripts/run_watchlist.py --config config/watchlist.example.toml
```

API 运行：

```bash
curl -X POST http://localhost:8000/search/watchlist/run \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"name":"机器人融资","query":"robotics funding"}],"limit":3,"archive":true}'
```

最近归档和 diff：

```bash
curl 'http://localhost:8000/search/archive/recent?limit=5'
curl 'http://localhost:8000/search/archive/diff?artifact_type=brief&watchlist_name=机器人融资'
```

定时运行、systemd timer 和安全边界见 `docs/watchlist_scheduling.md`。

## 外部工具 Smoke

全量 live search / external tool smoke：

```bash
.venv/bin/python scripts/smoke_search_sources.py \
  --academic-query "robot foundation model" \
  --github-query "robotics foundation model" \
  --hf-query "robotics" \
  --social-query "robotics VLA demo" \
  --opencli-platform-query "robotics VLA demo" \
  --opencli-url "https://example.com" \
  --limit 3
```

只验证外部工具入口：

```bash
.venv/bin/python scripts/smoke_search_sources.py \
  --external-only \
  --social-query "robotics VLA demo" \
  --opencli-platform-query "robotics VLA demo" \
  --opencli-url "https://example.com" \
  --limit 1
```

OpenCLI 单平台只读 smoke：

```bash
opencli reddit search "robotics diffusion policy" --limit 1 -f json
opencli weixin search "具身智能 机器人" --limit 1 -f json
opencli twitter search "robotics diffusion policy" --limit 1 -f json
```

如果 X/Twitter 返回 `AUTH_REQUIRED`，在 Chrome/Chromium 登录 `https://x.com` 后重试。

## 统一配置和路由

所有外部能力先在 `config/services.toml` 注册，再通过 `ServiceRouter` 调用。业务代码不要直接硬编码 OCR、搜索、Embedding、Qdrant、MCP、LLM、邮件或 scraping 实现。

当前默认服务：

```toml
[defaults]
email_delivery = "resend_email_delivery"
email_discovery = "hunter_email_discovery"
email_verification = "zerobounce_email_verification"
document_parser = "auto_document_parser"
embedding = "bge_m3_local"
evaluation = "self_rsi_evaluator"
vector_store = "qdrant_local"
ocr = "aliyun_ocr"
search = "due_diligence_federated_search"
mcp = "disabled_mcp"
structured_output = "outlines_structured_output"
database = "disabled_database"
llm = "openrouter_auto_reasoning"
scraping = "opencli_crawl_scrape"
```

Python 调用：

```python
from app.core.router import get_router

router = get_router()
results = router.search("opencli_platform_search").search("robotics VLA demo", limit=3)
for item in results:
    print(item["source_key"], item["title"], item.get("url"))
```

## 验证

后端：

```bash
.venv/bin/python -m compileall app scripts tests
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q
.venv/bin/python -c "from app.api.main import app; print(app.title)"
```

前端：

```bash
pnpm --dir frontend test
pnpm --dir frontend lint
pnpm --dir frontend build
```

如果只改 README，至少运行：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests/test_static_contracts.py::test_search_smoke_script_and_readme_document_live_sources -q
git diff --check
```
