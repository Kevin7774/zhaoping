# 机器人招聘 Agent MVP

面向家庭场景全栈整机机器人公司的 AI 原生招聘行研 Agent MVP。项目当前重点是把业务招聘请求、多模态多源数据、岗位能力标准、候选人材料和人工反馈接入统一的 RAG、Memory、Evaluation 与数据飞轮底座，便于后续扩展 OCR、搜索、MCP、Workflow、Skills、结构化抽取和人工复核流程。

## 当前能力

- PostgreSQL 四张核心表：能力标准、岗位画像、候选人画像、评审反馈。
- 12 个具身机器人岗位元数据与能力标签字典。
- 6 个跨学科团队画像：系统架构、AI 多模态、机器人控制、机电结构、嵌入式实时、产品交付。
- 场景 A/B/C/D 本地招聘工作流：岗位画像与 JD、人才地图、候选人评估、招聘周报。
- 场景 C 候选人评估已升级为 Agent Matrix：工程事实链、信源/RAG 核验、能力平移推演、苏格拉底追问和面试反馈回流。
- 自我 RSI 评估闭环：通过 Evaluation provider 运行评估测试集，输出测试结果、反馈缺口和下一轮回归用例。
- 候选人简历/作品抽取的 Pydantic 结构化输出 schema。
- 本地 4090 文档解析、Embedding、Qdrant 入库脚本。
- FastAPI 预留简历入库、岗位匹配、反馈查询接口。
- 配置驱动的服务路由：文档解析、OCR、Embedding、向量库、LLM、DB、MCP、Skill 都通过 `config/services.toml` 注册。
- Search 数据源目录：网页、招聘站、LinkedIn、公司官网、GitHub、Hugging Face、ModelScope、PDL、X recent posts、Crustdata、邮箱发现/验证、合规触达、抓取基础设施、论文、专利、AI 社区、活动、视频、工商、新闻、年报、高校实验室、会议论文名单。

## 推荐架构：AI 原生招聘行研 Agent 全链路

当前架构按“业务请求输入层 + 多模态多源数据层 + AI 原生基础设施 + 机器人招聘知识资产 + 任务路由规划 + 多 Agent 协作 + A/B/C/D 场景输出 + 数据飞轮”组织。

关键边界：

- 用户输入层只表达为“业务请求输入层”，不绑定具体职能角色。
- 场景固定为 A/B/C/D：A 岗位画像与 JD，B 人才地图，C 候选人评估，D 招聘周报。
- 知识层前置多模态多源信息输入，包括网页、招聘站、AI 社区、论坛、活动、视频、GitHub、论文、专利和模型社区。
- 基础设施层显式承载 MCP Connectors、Workflow Orchestrator、Skills、RAG / Retrieval、Memory、Evaluation 和 Guardrails。
- 输出、人工修改、面试反馈、offer / reject 和入职表现会通过数据飞轮回流到知识库、画像库和评分体系。

```mermaid
flowchart TB
    subgraph Input["多模态多源信息输入层"]
        BusinessRequest["业务请求输入层\n一句招聘需求 / 目标岗位 / 候选人材料 / 周报数据"]
        RecruitingData["招聘数据\nJD / 简历 / 面试反馈 / 招聘漏斗 / 薪酬数据"]
        IndustryData["行业数据\n机器人公司 / 融资新闻 / 产品发布 / 技术报告"]
        TechData["技术数据\n论文 / 专利 / GitHub / Hugging Face / ModelScope"]
        CommunityData["AI 社区\nAI 论坛 / Discord / 微信群 / 知乎 / 即刻 / Reddit"]
        EventData["AI 活动\nHackathon / Meetup / 会议 / 直播 / Workshop"]
        VideoData["视频内容\nB站 / YouTube / 技术演讲 / Demo 视频 / 字幕"]
        InternalData["内部数据\n公司战略 / 团队结构 / 历史 JD / 候选人库"]
    end

    subgraph Infra["AI 原生基础设施层"]
        MCP["MCP Connectors\n外部 API / 内部系统 / 多源工具"]
        Workflow["Workflow Orchestrator\nA/B/C/D 场景编排"]
        Skills["Skills\n岗位画像 / 简历解析 / 人才地图 / 视频解析 / GitHub 分析"]
        RAG["RAG / Retrieval\n行业资料 / 岗位库 / 候选人库 / 公司库"]
        Memory["Memory\n招聘上下文 / 候选人历史 / 岗位偏好 / 反馈记录"]
        Evaluation["Evaluation\n评分卡 / 人工校准 / 输出质量评估"]
        Guardrails["Guardrails\n数据脱敏 / 权限控制 / 合规检查 / 人工审核"]
    end

    subgraph Knowledge["机器人招聘知识资产层"]
        TechRoute["家庭机器人技术路线库"]
        CapabilityMatrix["全栈岗位能力矩阵库"]
        CompanyTeam["目标公司与团队库"]
        NativeTalent["AI 原生人才画像库"]
        CandidateProfile["候选人画像库"]
        Scorecard["面试题与评分卡库"]
        MarketComp["招聘市场与薪酬数据库"]
        FeedbackAsset["历史反馈与成功画像库"]
    end

    subgraph Routing["任务路由与规划层"]
        Intent["Intent Router\n识别 A/B/C/D 场景"]
        Planner["Planner Agent\n拆解任务步骤"]
        ToolPlanner["Tool Planner\n选择工具 / 数据源 / Skill"]
        ContextBuilder["Context Builder\n组装岗位 / 候选人 / 行业 / 公司上下文"]
    end

    subgraph Agents["多 Agent 协作层"]
        IndustryAgent["行业研究 Agent"]
        TechAgent["技术路线 Agent"]
        JobAgent["岗位画像 Agent"]
        MapAgent["人才地图 Agent"]
        RadarAgent["AI 原生人才雷达 Agent"]
        EvalAgent["候选人评估 Agent"]
        StrategyAgent["招聘策略 Agent"]
        WeeklyAgent["招聘周报 Agent"]
        ReviewAgent["Reflection / Reviewer Agent"]
    end

    subgraph Output["A/B/C/D 场景输出层"]
        A["A：岗位画像与 JD\n岗位定位 / 能力矩阵 / JD / 面试问题 / 候选人来源"]
        B["B：人才地图\n目标公司 / 目标团队 / 候选人来源 / 搜索关键词 / 触达策略"]
        C["C：候选人评估\n工程事实链 / 能力频谱 / 增量价值 / 追问反馈 / 证据链"]
        D["D：招聘周报\n本周招聘结论 / 关键岗位进展 / Top 候选人 / 市场人才信号 / 招聘风险 / 下周行动建议"]
    end

    subgraph Flywheel["数据飞轮与持续优化层"]
        OutputResult["输出结果"]
        HumanEdit["人工修改"]
        InterviewFeedback["面试反馈"]
        OfferReject["offer / reject 结果"]
        OnboardPerformance["入职表现"]
        ProfileFix["岗位画像修正"]
        ScoreCalibration["候选人评分校准"]
        MapUpdate["人才地图更新"]
        KnowledgeEvolution["知识库持续进化"]
    end

    Input --> Infra --> Knowledge --> Routing --> Agents --> Output --> Flywheel
    Flywheel -.回流.-> Knowledge
    Flywheel -.校准.-> Evaluation
    Flywheel -.更新.-> Memory
```

## 功能图

```mermaid
mindmap
  root((机器人招聘 Agent MVP))
    多模态多源输入
      业务请求输入层
      招聘站与薪酬
      行业新闻与产品发布
      GitHub/论文/专利/模型社区
      AI 社区/活动/视频
      内部候选人库与历史 JD
    AI 原生基础设施
      MCP Connectors
      Workflow Orchestrator
      Skills
      RAG/Retrieval
      Memory
      Evaluation
      Guardrails
    知识资产
      家庭机器人技术路线库
      全栈岗位能力矩阵库
      目标公司与团队库
      AI 原生人才画像库
      候选人画像库
      面试题与评分卡库
    A/B/C/D 场景
      A 岗位画像与 JD
      B 人才地图
      C 候选人评估
      D 招聘周报
    数据飞轮
      输出结果
      人工修改
      面试反馈
      offer/reject 与入职表现
      回流知识库/画像库/评分体系
```

## 团队画像图

世界模型与具身智能是高度交叉学科。优秀团队不能只靠单点算法能力，需要同时覆盖 AI、机器人控制、硬件工程、数据系统和商业交付能力。

```mermaid
flowchart LR
    Team[具身智能商业化团队] --> Architect[系统级总架构师]
    Team --> AI[AI 与多模态算法科学家]
    Team --> Control[机器人控制科学家]
    Team --> Mech[机电与结构专家]
    Team --> Embedded[嵌入式与实时系统工程师]
    Team --> Delivery[产品和行业交付团队]

    Architect --> A1[大脑/小脑/硬件/数据/OS/场景解耦]
    AI --> AI1[视觉/语言/动作/触觉/空间/世界预测]
    Control --> C1[WBC/MPC/轨迹优化/状态估计/阻抗控制]
    Mech --> M1[关节/传动/灵巧手/散热/线束/可制造性]
    Embedded --> E1[驱动板/总线/RTOS/同步/边缘推理]
    Delivery --> D1[可复制场景/客户付费/交付运维]

    Architect -.协同边界.-> AI
    Architect -.安全落地.-> Control
    Control -.实机约束.-> Mech
    Embedded -.实时链路.-> Control
    AI -.数据闭环.-> Embedded
    Delivery -.现场反馈.-> Architect
```

| 团队画像 | 核心职责 | 理想背景 | 关联岗位画像 |
| --- | --- | --- | --- |
| 系统级总架构师 | 解耦大脑、小脑、硬件、数据、操作系统和客户场景。 | 机器人实验室、自动驾驶、工业机器人、大模型公司、复杂硬件系统公司。 | `robot_system_architect` |
| AI 与多模态算法科学家 | 负责视觉、语言、动作、触觉、空间重建和世界预测模型。 | 大模型、多模态模型、具身智能实验室、自动驾驶感知/预测团队。 | `vla_embodied_expert`、`world_model_simulation`、`multimodal_perception`、`vision_3d_algorithm` |
| 机器人控制科学家 | 负责 WBC、MPC、轨迹优化、状态估计、阻抗控制、强化学习控制和稳定性验证。 | 足式机器人、工业机器人、机器人控制实验室、自动驾驶控制团队。 | `motion_control_mpc_wbc`、`manipulation_grasping`、`dexterous_hand_control`、`slam_navigation_expert` |
| 机电与结构专家 | 负责关节、传动、灵巧手、散热、线束、结构强度和可制造性。 | 消费硬件、工业机器人、电机/执行器、汽车零部件公司。 | `embedded_foc_engineer`、`dexterous_hand_control`、`qa_reliability_engineer` |
| 嵌入式与实时系统工程师 | 负责驱动板、通信总线、RTOS、实时调度、传感器同步和边缘推理。 | 机器人嵌入式、汽车电子、运动控制、边缘计算硬件团队。 | `embedded_foc_engineer`、`robot_data_infrastructure`、`robot_system_architect` |
| 产品和行业交付团队 | 找到可复制场景，将 demo 转化为客户付费。 | 机器人解决方案、智能硬件交付、工业自动化集成商、ToB 产品团队。 | `qa_reliability_engineer`、`robot_system_architect`、`robot_data_infrastructure` |

## 数据 Pipeline

```mermaid
sequenceDiagram
    autonumber
    participant Input as 简历/作品文件
    participant API as API 或 CLI
    participant Router as ServiceRouter
    participant Parser as Document Parser
    participant Chunker as chunk_markdown
    participant Embed as bge-m3 Embedding
    participant Qdrant as Qdrant Local
    participant PG as PostgreSQL
    participant Search as 岗位匹配查询

    Input->>API: file_path + candidate_id
    API->>Router: resolve(document_parser)
    Router->>Parser: parse(file_path)
    Parser-->>API: clean_text / markdown
    API->>Chunker: 按空行切块，过滤短文本
    Chunker-->>API: chunks
    API->>Router: resolve(embedding)
    Router->>Embed: embed_texts(chunks)
    Embed-->>API: embeddings
    API->>Router: resolve(vector_store)
    Router->>Qdrant: upsert_chunks(candidate_id, chunks, embeddings)
    opt --write-db
        API->>Router: resolve(database)
        Router->>PG: upsert candidate_profile
    end
    Search->>Router: resolve(embedding + vector_store)
    Search->>Embed: embed_texts([query])
    Search->>Qdrant: search(query_vector, top_k)
    Qdrant-->>Search: 候选人相关 chunks
```

## 关键目录

| 路径 | 作用 |
| --- | --- |
| `app/api/main.py` | FastAPI 入口，暴露健康检查、简历入库、岗位匹配、反馈占位接口。 |
| `app/rag/ingest_worker.py` | 本地文档解析、切块、Embedding、Qdrant 入库主流程。 |
| `app/core/router.py` | 服务路由器，把业务调用分发到配置中的 provider。 |
| `app/core/config.py` | 加载并校验 `config/services.toml`。 |
| `app/providers/` | 文档解析、OCR、Embedding、向量库、LLM、DB、搜索等 provider 实现。 |
| `app/skills/tech_space.py` | 12 个机器人岗位、6 个团队画像与能力标准静态字典。 |
| `app/skills/recruiting_scenarios.py` | 场景 A/B/C/D：岗位画像与 JD、人才地图、候选人评估、招聘周报的工作流和本地生成函数。 |
| `app/skills/search_sources.py` | 网页、招聘、候选人、公司、开源、模型社区、学术、专利、AI 社区、活动、视频、融资和会议等搜索数据源目录。 |
| `app/db/schema.py` | PostgreSQL 四张核心表的 SQLAlchemy schema。 |
| `config/services.toml` | 默认服务、外部能力、Skill、MCP 的注册表。 |
| `config/watchlist.example.toml` | 尽调级情报 watchlist 示例配置，用于定期追踪融资、人才、技术和竞争信号。 |
| `scripts/run_watchlist.py` | 不启动 API 的 watchlist CLI，生成 brief、写入 JSONL archive，并输出 Markdown 报告。 |
| `scripts/smoke_search_sources.py` | 手动验证 OpenAlex、SEC EDGAR 和可选 Brave live search provider 的连通性。 |
| `docs/capability_integration.md` | 新增能力时的集成规范。 |
| `docs/watchlist_scheduling.md` | watchlist 的一次性运行、cron、systemd timer 和验证说明。 |
| `tests/test_static_contracts.py` | 配置、路由、静态能力字典和基础 RAG 工具函数的契约测试。 |

## 环境安装

项目开发环境优先使用仓库内 `.venv`。当前已验证运行时为 Python 3.12.13；不要使用系统默认 Python 3.10 运行本项目。

```bash
python --version
.venv/bin/python --version
.venv/bin/python -m pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu121
pnpm --dir frontend install
```

验收标准：

- `.venv/bin/python --version` 应显示 `Python 3.12.13`，或至少是项目约定的 Python 3.12 运行时。
- `pnpm --dir frontend install` 成功后，前端开发服务由 `scripts/start_dev.sh` 或根目录 `./start.sh` 启动。
- `.env` 不要提交到 Git；只在本机保存数据库、LLM、邮件等私密配置。

如果你仍然使用 conda，可以保留 `robot_agent` 环境，但要显式确认 Python 版本符合当前项目要求：

```bash
conda activate robot_agent
python --version
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu121
```

## 持久 PostgreSQL

本地长期开发推荐用 Docker volume 持久化 PostgreSQL 数据。下面命令只绑定到 `127.0.0.1`，不会把数据库暴露到局域网或公网：

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

如果容器已经创建过，后续只需要：

```bash
docker start zhaoping-postgres
```

`.env` 中配置后端项目库和任务库：

```bash
PROJECT_DATABASE_URL=postgresql+psycopg://zhaoping:换成你的本机密码@127.0.0.1:55432/zhaoping
TASK_DATABASE_URL=postgresql+psycopg://zhaoping:换成你的本机密码@127.0.0.1:55432/zhaoping
```

验证 PostgreSQL 状态：

```bash
docker exec zhaoping-postgres pg_isready -U zhaoping -d zhaoping

set -a
source .env
set +a

.venv/bin/python - <<'PY'
from app.db.session import project_database_url
from app.db.task_models import task_database_url

print(project_database_url())
print(task_database_url())
PY
```

如果密码中包含 `@`、`:`、`/`、`#` 等特殊字符，需要在 URL 中做百分号编码。

备份示例：

```bash
docker exec zhaoping-postgres pg_dump -U zhaoping zhaoping > backup.sql
```

## 建表

方式一：直接执行 SQL。

```bash
psql "$DATABASE_URL" -f app/db/create_schema.sql
```

方式二：使用 SQLAlchemy schema。

```bash
export DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/robot_agent"
conda run -n robot_agent python scripts/create_db.py
```

## 本地 RAG 入库

```bash
conda run -n robot_agent python -m app.rag.ingest_worker --file test_readme.md --candidate-id cand_ai_native_002
```

PDF、DOCX、图片会走 Docling；Markdown/TXT 会直接读取。向量库默认写入 `./qdrant_mvp_store`。

可选写入候选人元数据到 PostgreSQL：

```bash
conda run -n robot_agent python -m app.rag.ingest_worker \
  --file test_readme.md \
  --candidate-id cand_ai_native_002 \
  --write-db
```

## API 服务

手机访问推荐使用生产模式，前端会先打包成静态资源，再由 FastAPI 直接托管页面和 API：

```bash
./scripts/start_phone.sh
```

默认地址：

- 本机网站：`http://127.0.0.1:8020`
- 手机网站：启动脚本会自动打印，例如 `http://192.168.x.x:8020`
- 后端接口同域访问，例如 `http://127.0.0.1:8020/health`

公网临时访问可使用 Cloudflare quick tunnel：

```bash
./scripts/start_public_cloudflare.sh
setsid -f ./scripts/watch_public_cloudflare.sh >/dev/null 2>&1
```

如需由系统自动守护并在登录后自动拉起：

```bash
systemctl --user link "$PWD/deploy/zhaoping-public.service"
systemctl --user enable --now zhaoping-public.service
systemctl --user status zhaoping-public.service --no-pager
```

运行状态和日志：

- 公网 URL：`data/runtime/cloudflare_url.txt`
- 后端日志：`data/runtime/phone_server.log`
- Tunnel 日志：`data/runtime/cloudflared.log`
- 守护日志：`data/runtime/public_watch.log`

说明：quick tunnel 的 `trycloudflare.com` 地址适合临时演示，不保证永久固定。如果需要“一直同一个网址可访问”，应使用 Cloudflare Named Tunnel 绑定自己的域名，或部署到云平台；同时电脑不能关机或睡眠。

开发模式可用根目录一键脚本启动后端 API 与 Vite 前端控制台：

```bash
./start.sh
```

`./start.sh` 会做三件事：

- 自动加载仓库根目录 `.env`，让后端读取 `PROJECT_DATABASE_URL` 和 `TASK_DATABASE_URL`。
- 默认启用 `KILL_OLD_DEV=1`，启动前清理占用开发端口的旧本项目后端/Vite 进程。
- 委托执行 `scripts/start_dev.sh`，并把 `VITE_API_TARGET` 指到当前后端地址。

保守模式可以直接运行底层脚本。它默认不杀旧进程，端口被占用时会报错退出：

```bash
./scripts/start_dev.sh
```

开发模式默认地址：

- 本机前端控制台：`http://127.0.0.1:5173`
- 手机前端控制台：启动脚本会自动打印，例如 `http://192.168.x.x:5173`
- 后端健康检查：`http://127.0.0.1:8000/health`

手机访问要求：

- 手机和电脑在同一个 Wi-Fi / 局域网。
- 在手机浏览器打开启动脚本打印的 `frontend phone` 地址。
- 如果脚本识别的 IP 不对，可以手动指定：

```bash
PUBLIC_HOST=你的电脑局域网IP ./scripts/start_dev.sh
```

可用环境变量覆盖端口或环境：

```bash
BACKEND_PORT=8010 FRONTEND_PORT=5174 ./start.sh
```

如果 `pnpm` 或 `npm` 不在非交互式 shell 的 `PATH` 中，可以显式指定：

```bash
PNPM_BIN=/path/to/pnpm ./start.sh
# 或
NPM_BIN=/path/to/npm ./start.sh
```

如果要保留旧进程，不自动清理端口：

```bash
KILL_OLD_DEV=0 ./start.sh
```

如果不想自动加载 `.env`，例如你已经在 shell 中手动注入环境变量：

```bash
LOAD_ENV_FILE=0 ./start.sh
```

只启动 API：

```bash
set -a
source .env
set +a

.venv/bin/python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

如果看到 `address already in use`，说明端口已有进程占用。推荐直接使用：

```bash
./start.sh
```

它只会清理识别为本项目旧开发服务的进程；如果端口被未知进程占用，脚本会拒绝误杀并打印占用信息。

也可以手动查看占用：

```bash
ss -ltnp 'sport = :8000'
ss -ltnp 'sport = :5173'
```

当前接口：

| 方法 | 路径 | 输入 | 输出 |
| --- | --- | --- | --- |
| `GET` | `/health` | 无 | `{"status": "ok"}` |
| `POST` | `/resumes/ingest` | `file_path`、`candidate_id`、`write_database` | 候选人 ID 与 Markdown 预览 |
| `POST` | `/jobs/match` | `query`、`top_k` | Qdrant 检索结果 |
| `POST` | `/scenarios/run` | `scenario`、`input`、`team_constraint`、`aperture_weight` | 启动 A/B/C/D Agent 任务 |
| `POST` | `/rsi/evaluate` | `suite`、`threshold`、`cases` | 运行自我 RSI 评估，返回测试结果、反馈缺口和迭代计划 |
| `POST` | `/tasks/{task_id}/probe-feedback` | `probe_id`、`answered`、`note` | 面试追问反馈回写到当前任务画像 |
| `GET` | `/review/feedback` | 无 | 当前为占位状态 |

示例：

```bash
curl -X POST http://localhost:8000/resumes/ingest \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"test_readme.md","candidate_id":"cand_ai_native_002"}'

curl -X POST http://localhost:8000/jobs/match \
  -H 'Content-Type: application/json' \
  -d '{"query":"Diffusion Policy 和遥操作数据清洗经验","top_k":5}'

curl -X POST http://localhost:8000/rsi/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"suite":"candidate_evaluation_core","threshold":0.8}'

# 全能力演示模式：会尝试 live search、LLM judge、本地 RAG/向量库和集成状态。
# 缺少密钥、模型或索引时不会中断，会在 capability_trace / full_mode_artifacts 中返回原因。
curl -X POST http://localhost:8000/rsi/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"mode":"full","allow_live":true,"max_live_results":1,"threshold":0.8}'
```

## 场景 A/B/C/D 本地工作流

```python
from app.skills.recruiting_scenarios import (
    build_talent_map,
    evaluate_candidate,
    generate_job_profile_and_jd,
    generate_weekly_report,
)

job = generate_job_profile_and_jd("我们想招一个家庭机器人 VLA 算法工程师")
talent_map = build_talent_map("家庭机器人 SLAM 工程师")
evaluation = evaluate_candidate(
    "候选人材料...",
    target="家庭机器人 VLA 算法工程师",
    team_constraint="真机泛化",
)
weekly_report = generate_weekly_report("本周招聘进展、候选人状态、面试反馈和市场信号...")
```

也可以通过 `ServiceRouter` 读取注册后的 Skill：

```python
from app.core.router import get_router

scenarios = get_router().skills["home_robot_recruiting_scenarios"]
job = scenarios["functions"]["generate_job_profile_and_jd"]("我们想招一个家庭机器人 VLA 算法工程师")
weekly_report = scenarios["functions"]["generate_weekly_report"]("本周招聘周报数据...")
```

## 能力标准治理与溯源

岗位能力库现在按四层管理：

| 层 | 内容 | 更新方式 |
| --- | --- | --- |
| 静态基座 | 技术层、岗位大类、能力 ID、基础输出 Schema、合规规则 | 人工版本化更新 |
| 动态证据层 | 论文、会议、JD、公司官网、GitHub、专利、新闻、候选人材料 | 搜索 / API / RAG / 人工导入后写入证据链 |
| 推理校准层 | 能力是否必备、重要性排序、技术路线覆盖、目标来源迁移价值 | 多源证据交叉验证 + 人工确认 |
| 长期记忆层 | 人工修订、面试反馈、offer / reject、入职表现、失败案例 | 回流 Memory，反向修正能力标准 |

对应的静态 skill：

| Skill | 入口 | 用途 |
| --- | --- | --- |
| `robot_capability_governance` | `STATIC_DYNAMIC_DECISION_TABLE` | 标记哪些信息静态、动态、需要搜索验证或长期记忆。 |
| `robot_capability_traceability` | `CAPABILITY_TRACEABILITY_OVERRIDES` | 记录能力的技术路线细分、证据要求、待验证假设和记忆信号。 |
| `evidence_record_schema` | `EVIDENCE_RECORD_SCHEMA` | 约束每条证据必须包含来源类型、URL/引用、发布时间、摘录、置信度和验证状态。 |

以 `SLAM / 导航算法工程师` 为例，原来的三项必备能力仍保留为兼容字段，但会额外输出 `能力画像`、`能力细分` 和 `证据链与验证`：

- `激光/视觉/IMU多传感器融合建图`：拆分为传感器标定与时间同步、状态估计与后端优化、地图表示与更新接口、工程部署与可观测性。
- `高动态环境实时局部避障与重规划`：拆分为局部规划器、动态障碍代价地图、失败恢复与重规划策略、家庭场景安全边界。
- `长期地图动态更新与高精重定位`：拆分为长期地图生命周期、高精重定位与失效恢复、语义空间记忆、设备数据回流与评测闭环。

当前状态仍是 `unverified_static_baseline`：系统会明确标记这是静态基线，后续需要通过学术、产业、开源、候选人反馈和人工修订升级为 `cross_validated` 或 `human_approved`。

## Search 数据源接入

当前 `search` 默认服务是联邦情报搜索 provider：`due_diligence_federated_search`。默认执行仍以本地数据源目录 `talent_source_catalog` 的来源规划为主，不会自动抓取网页、调用付费接口、接管浏览器或使用登录态。真实联网采集应逐个接入官方 API、授权账号、MCP、外部工具 adapter 或人工导出流程，并显式开启对应服务。

已注册的联网搜索 provider：

| Service | Provider | 默认启用 | 密钥环境变量 | 用途 |
| --- | --- | --- | --- | --- |
| `agent_reach_social_search` | `agent_reach_social` | 否 | 无 | Agent-Reach/OpenCLI 可执行社媒搜索入口，支持微博、B站、V2EX、知乎、掘金、CSDN、SegmentFault，并保留 X/Twitter、Reddit、YouTube、小红书、抖音、公众号等渠道规划。 |
| `scrapling_adaptive_scrape` | `external_search_tool` | 否 | 无 | Scrapling 外部工具入口，规划公开或已授权网页的自适应抓取、JS 渲染和结构化抽取。 |
| `browser_use_agent_search` | `external_search_tool` | 否 | 无 | Browser-use 外部工具入口，规划 LLM 驱动浏览器操作、登录后授权页面和后台流程。 |
| `claude_chrome_supervised_search` | `external_search_tool` | 否 | 无 | Claude in Chrome 人工监督入口，适合复杂认证和需要盯屏的真实 Chrome 页面。 |
| `web_access_cdp_search` | `external_search_tool` | 否 | 无 | Web-access Skill 入口，规划 WebSearch/WebFetch/curl/Chrome CDP 和本地浏览器书签/历史检索。 |
| `brave_web_search` | `brave_web` | 否 | `BRAVE_SEARCH_API_KEY` | 调用 Brave Web Search API，获取开放网页证据候选。 |
| `github_repositories` | `github_repositories` | 否 | 可选 `GITHUB_TOKEN` | 调用 GitHub repository search，获取开源项目、stars、forks、topic、维护者和语言信号。 |
| `huggingface_models` | `huggingface_models` | 否 | 可选 `HF_TOKEN` | 调用 Hugging Face Hub models API，获取模型、下载量、点赞、标签、作者和任务类型信号。 |
| `pdl_people_search` | `people_data_labs_people` | 否 | `PDL_API_KEY` | 调用 People Data Labs person search，用于候选人身份补全、公司、履历、社交链接和公开联系人字段。 |
| `x_recent_posts_search` | `x_recent_posts` | 否 | `X_BEARER_TOKEN` | 调用 X API v2 recent search，发现 KOL、关键词、社区动态、开源发布和招聘市场讨论。 |
| `crustdata_signal_search` | `crustdata_signals` | 否 | `CRUSTDATA_API_KEY` | 调用 Crustdata live web/news/social search，补 PDL 新鲜度不足，追踪人员、公司、招聘、融资和增长变化信号。 |
| `companies_house_search` | `companies_house` | 否 | `COMPANIES_HOUSE_API_KEY` | 调用 UK Companies House company search，获取公司编号、状态、类型、成立时间和注册地址线索。 |
| `courtlistener_search` | `courtlistener` | 否 | 可选 `COURTLISTENER_TOKEN` | 调用 CourtListener legal search，获取美国判例/案名/法院/案号/引用等诉讼风险线索。 |
| `openalex_works_search` | `openalex_works` | 否 | 无 | 调用 OpenAlex Works API，获取论文、作者、引用和技术主题线索。 |
| `openalex_authors_search` | `openalex_authors` | 否 | 无 | 调用 OpenAlex Authors API，获取作者、机构、作品数、引用数和研究主题。 |
| `openalex_institutions_search` | `openalex_institutions` | 否 | 无 | 调用 OpenAlex Institutions API，获取学校/机构主页、国家、作品数和引用信号。 |
| `semantic_scholar_papers_search` | `semantic_scholar_papers` | 否 | 无 | 调用 Semantic Scholar paper search，获取论文、作者、摘要、venue、引用和开放访问链接。 |
| `semantic_scholar_authors_search` | `semantic_scholar_authors` | 否 | 无 | 调用 Semantic Scholar author search，获取作者、别名、机构、论文数、引用数和 h-index。 |
| `education_competition_monitor` | `education_competition_monitor` | 否 | 无 | 返回高校官网、实验室成员页、天池、DataFountain、CCF、ICPC/CCPC、蓝桥杯、Kaggle 等监控目标。 |
| `sec_edgar_company_filings` | `sec_edgar_company_filings` | 否 | 无 | 调用 SEC EDGAR 公司 ticker/CIK 与 submissions API，获取 10-K、10-Q、8-K 等披露记录。 |
| `sec_company_facts` | `sec_company_facts` | 否 | 无 | 调用 SEC Company Facts XBRL API，获取收入、利润、资产、负债、现金、研发费用和 EPS 等财务事实。 |
| `sec_insider_transactions` | `sec_insider_transactions` | 否 | 无 | 调用 SEC submissions API，筛选 Form 3/4/5，获取高管、董事和大股东持股/交易披露线索。 |
| `sec_ownership_activism` | `sec_ownership_activism` | 否 | 无 | 调用 SEC submissions API，筛选 Schedule 13D/13G、13F 和 Form 144，监控重大持股、控制权和减持披露。 |
| `sec_investment_adviser_reports` | `sec_investment_adviser_reports` | 否 | 无 | 下载 SEC Investment Adviser Information Reports ZIP，解析 Form ADV 子集数据，获取投顾/ERA 的 CRD、SEC#、CIK、状态、地址、网站、ADV 日期和监管身份线索。 |
| `fdic_bankfind_institutions` | `fdic_bankfind_institutions` | 否 | 无 | 调用 FDIC BankFind institutions API，获取银行名称、FDIC certificate、状态、监管机构、资产、存款、利润、ROA/ROE、地点和网站信号。 |
| `federal_register_documents` | `federal_register_documents` | 否 | 无 | 调用 Federal Register documents API，获取规则、拟议规则、公告、机构、引用和监管政策线索。 |
| `cpsc_recalls` | `cpsc_recalls` | 否 | 无 | 调用 CPSC Recall API，获取消费品召回、hazard、remedy、产品和企业角色信号。 |
| `fda_enforcement_recalls` | `fda_enforcement_recalls` | 否 | 无 | 调用 openFDA enforcement endpoints，获取 device/food/drug 召回等级、召回企业、原因、分布和状态信号。 |
| `fda_device_510k` | `fda_device_510k` | 否 | 无 | 调用 openFDA Device 510(k) Clearances API，获取器械申请人、K number、产品代码、decision date、clearance type 和 substantially equivalent 信号。 |
| `fda_device_events` | `fda_device_events` | 否 | 无 | 调用 openFDA Device Adverse Events/MAUDE API，获取器械不良事件、故障、伤害、死亡、产品代码、报告日期和上市后安全信号。 |
| `fda_device_classification` | `fda_device_classification` | 否 | 无 | 调用 openFDA Device Classification API，获取产品代码、器械分类、device class、regulation number、medical specialty、submission type 和 review panel 信号。 |
| `fda_device_registration_listing` | `fda_device_registration_listing` | 否 | 无 | 调用 openFDA Device Registration and Listing API，获取注册号、FEI、owner/operator、设施地点、establishment type、产品代码和列名产品信号。 |
| `cfpb_consumer_complaints` | `cfpb_consumer_complaints` | 否 | 无 | 调用 CFPB Consumer Complaint Database API，获取消费金融投诉、产品、issue、公司响应、及时性和争议信号。 |
| `nhtsa_recalls` | `nhtsa_recalls` | 否 | 无 | 调用 NHTSA recalls API，按 model year/make/model 获取车辆安全召回、组件、后果、补救和制造商信号。 |
| `epa_echo_facilities` | `epa_echo_facilities` | 否 | 无 | 调用 EPA ECHO facility lookup，获取设施身份、项目系统、地点、非合规、正式执法和处罚信号。 |
| `clinicaltrials_studies` | `clinicaltrials_studies` | 否 | 无 | 调用 ClinicalTrials.gov API v2，获取试验登记、状态、阶段、赞助方、干预、终点、入组和地点信号。 |
| `cms_openpayments` | `cms_openpayments` | 否 | 无 | 调用 CMS Open Payments DKAN API，获取药械/医药公司付款、研究付款、权益关系、医生和教学医院商业关系信号。 |
| `census_international_trade` | `census_international_trade` | 否 | `CENSUS_API_KEY` | 调用 U.S. Census International Trade API，获取进出口国家、HS 商品、月度值和年初至今贸易流。 |
| `fred_series_search` | `fred_series_search` | 否 | `FRED_API_KEY` | 调用 FRED series search 和 observations API，获取利率、通胀、失业率、信用利差、金融压力、收益率曲线等宏观序列和最新观测值。 |
| `gdelt_doc_news` | `gdelt_doc_news` | 否 | 无 | 调用 GDELT DOC API，获取全球新闻文章列表、来源国家、语言和发布日期。 |
| `gnews_funding_news` | `gnews_funding_news` | 否 | `GNEWS_API_KEY` | 调用 GNews Search API，聚焦 funding、financing、acquisition、merger、investment、venture 事件。 |
| `sec_enforcement_search` | `sec_enforcement` | 否 | 无 | 调用 SEC 官网搜索，聚焦 enforcement、litigation、settled charges、fraud、penalty 等执法处罚线索。 |
| `usajobs_search` | `usajobs` | 否 | `USAJOBS_API_KEY` + `USAJOBS_USER_AGENT` | 调用 USAJOBS Search API，获取岗位、机构、地点和薪酬区间等招聘薪酬信号。 |
| `usaspending_awards` | `usaspending_awards` | 否 | 无 | 调用 USAspending Advanced Award Search，获取美国联邦合同、拨款、收款方、金额和授予机构。 |
| `sam_gov_opportunities` | `sam_gov_opportunities` | 否 | `SAM_GOV_API_KEY` | 调用 SAM.gov Get Opportunities API，获取 solicitation、pre-solicitation、sources sought、special notice、set-aside、NAICS/PSC、截止日期、联系人和前瞻政府需求信号。 |
| `grants_gov_opportunities` | `grants_gov_opportunities` | 否 | 无 | 调用 Grants.gov search2 API，获取 forecasted/posted 联邦资助机会、agency、opportunity number、ALN/CFDA、open/close date 和非稀释资金管线信号。 |
| `patentsview_patents` | `patentsview_patents` | 否 | 无 | 调用 PatentsView patents query，获取美国专利标题、摘要、授权日、受让人和发明人线索。 |
| `ofac_sanctions_lists` | `ofac_sanctions_lists` | 否 | 无 | 下载 OFAC SDN 与 Consolidated XML 清单，筛查制裁和合规风险。 |

已注册的非 search 增长/触达 provider：

| Service | Provider | 默认服务类型 | 密钥环境变量 | 用途 |
| --- | --- | --- | --- | --- |
| `hunter_email_finder` | `hunter_email_finder` | `email_discovery` | `HUNTER_API_KEY` | 调用 Hunter Email Finder，按姓名和公司域名/公司名发现工作邮箱。 |
| `zerobounce_email_validation` | `zerobounce_email_validation` | `email_verification` | `ZEROBOUNCE_API_KEY` | 调用 ZeroBounce 单邮箱验证，降低退信率和域名信誉损伤。 |
| `neverbounce_email_validation` | `neverbounce_email_validation` | `email_verification` | `NEVERBOUNCE_API_KEY` | 调用 NeverBounce single check，作为邮箱验证备选或二次校验。 |
| `postmark_compliant_email` | `postmark_compliant_email` | `email_delivery` | `POSTMARK_SERVER_TOKEN` + `RECRUITING_CONTACT_EMAIL` + `UNSUBSCRIBE_BASE_URL` | 调用 Postmark Email API，并强制人工审批、退订链接、黑名单、每日限额和审计日志。 |
| `sendgrid_compliant_email` | `sendgrid_compliant_email` | `email_delivery` | `SENDGRID_API_KEY` + `RECRUITING_CONTACT_EMAIL` + `UNSUBSCRIBE_BASE_URL` | 调用 SendGrid v3 Mail Send API，并套用同一套合规发送闭环。 |
| `firecrawl_scrape` | `firecrawl_scrape` | `scraping` | `FIRECRAWL_API_KEY` | 调用 Firecrawl scrape API，把公开或授权网页转为 Markdown/元数据。 |
| `opencli_crawl_scrape` | `opencli_crawl` | `scraping` | 无 | 调用本地 `opencli web read` 命令，把公开或授权 URL 转为 Markdown/HTML/元数据；未安装 `opencli` 时状态显示 `missing_tool`。 |
| `public_web_snapshot_monitor` | `public_web_snapshot_monitor` | `scraping` | 依赖 `firecrawl_scrape` / 可选 `browserbase_session` | 定期抓取并保存公开网页快照、Markdown 和 manifest，用于学校、实验室、竞赛、论坛和招聘页变化监控。 |
| `apify_actor_run` | `apify_actor_run` | `scraping` | `APIFY_API_TOKEN` | 调用 Apify Actor run API，运行合规 Actor 抓取任务。 |
| `brightdata_web_unlocker` | `brightdata_web_unlocker` | `scraping` | `BRIGHTDATA_API_KEY` + `BRIGHTDATA_ZONE` | 调用 Bright Data Web Unlocker API，用于已批准的公开网页访问。 |
| `browserbase_session` | `browserbase_session` | `scraping` | `BROWSERBASE_API_KEY` + `BROWSERBASE_PROJECT_ID` | 调用 Browserbase sessions API，创建托管云浏览器会话。 |

Brave provider 调用官方 Web Search endpoint `https://api.search.brave.com/res/v1/web/search`，请求头使用 `X-Subscription-Token`。配置只保存环境变量名，不保存密钥。

GitHub provider 调用 `https://api.github.com/search/repositories`，使用 repository search 参数 `q`、`per_page`、`sort=stars` 和 `order=desc`。未配置 `GITHUB_TOKEN` 时仍可使用公开限额；配置后只通过环境变量读取 token。Hugging Face provider 调用 `https://huggingface.co/api/models`，使用 `search`、`limit`、`sort=downloads`、`full=true` 检索模型生态。

Agent-Reach 社媒 provider 通过 `router.search("agent_reach_social_search")` fan-out 到本地命令：微博使用 `mcporter call 'weibo.search_content(...)'`，B站、V2EX、知乎、掘金、CSDN、SegmentFault 使用 `mcporter call 'exa.web_search_exa(...)'` 做站内公开搜索。OpenCLI 来自 `https://github.com/jackwener/OpenCLI`，安装后可用 `npm install -g @jackwener/opencli` 与 `opencli doctor` 验证；网页读取路径使用 `opencli web read --url <url> -f json`。

People Data Labs provider 调用 `https://api.peopledatalabs.com/v5/person/search`，使用 `X-api-key` 请求头和 PDL Search API 参数，只从 `PDL_API_KEY` 读取密钥。X recent posts provider 调用 `https://api.x.com/2/tweets/search/recent`，使用 `Authorization: Bearer <X_BEARER_TOKEN>`、`max_results`、`tweet.fields`、`user.fields` 和 `expansions=author_id`。Crustdata signal provider 调用 `https://api.crustdata.com/web/search/live`，使用 `Authorization: Bearer <CRUSTDATA_API_KEY>` 和 `x-api-version=2025-11-01`，默认 sources 为 `web/news/social`。

邮箱发现和触达链路采用分层 provider：Hunter 调用 `https://api.hunter.io/v2/email-finder`；ZeroBounce 调用 `https://api.zerobounce.net/v2/validate`；NeverBounce 调用 `https://api.neverbounce.com/v4.2/single/check`。发送层只允许 `postmark_compliant_email` 或 `sendgrid_compliant_email` 在 `approved=true` 后发送，并写入 `data/outreach/email_audit.jsonl`；退订或拒绝写入 `data/outreach/suppression_list.jsonl`。Postmark endpoint 为 `https://api.postmarkapp.com/email`，SendGrid endpoint 为 `https://api.sendgrid.com/v3/mail/send`。

抓取层默认 provider 是 Firecrawl，调用 `https://api.firecrawl.dev/v2/scrape`。OpenCLI provider 使用本地命令模板 `opencli web read --url {url} -f json`，通过 `router.scraping("opencli_crawl_scrape").scrape(url)` 调用；命令缺失时集成状态为 `missing_tool`。`public_web_snapshot_monitor` 通过 `router.scraping("public_web_snapshot_monitor").snapshot(urls=[...], job_name="...")` 调用，默认 primary scrape service 是 `firecrawl_scrape`，可记录 `browserbase_session` 元数据并写入 `data/snapshots/public_web/.../manifest.json`。Apify Actor run 使用 `https://api.apify.com/v2/acts/{actor_id}/runs`；Bright Data Web Unlocker 使用 `https://api.brightdata.com/request`；Browserbase session 使用 `https://api.browserbase.com/v1/sessions`。这些 provider 只应用于公开或明确授权页面，并需要域名边界、速率限制和数据最小化策略。

Companies House provider 调用 `https://api.company-information.service.gov.uk/search/companies`，使用 `q`、`items_per_page` 和 HTTP Basic Auth。API key 只从 `COMPANIES_HOUSE_API_KEY` 读取。CourtListener provider 调用 `https://www.courtlistener.com/api/rest/v4/search/`，使用 `q`、`type=o` 和 `page_size` 检索公开司法数据；`COURTLISTENER_TOKEN` 为可选环境变量。

OpenAlex provider 调用 `https://api.openalex.org/works`、`https://api.openalex.org/authors` 和 `https://api.openalex.org/institutions`，使用 `search`、`per-page` 与排序参数查询学术作品、作者和机构。Semantic Scholar provider 调用 `https://api.semanticscholar.org/graph/v1/paper/search` 和 `https://api.semanticscholar.org/graph/v1/author/search`，用于论文、作者、学校/机构方向、实验室线索和引用网络交叉验证。学校/竞赛监控 provider 维护高校官网、实验室成员页、天池、DataFountain、CCF、ICPC/CCPC、蓝桥杯和 Kaggle 目标，并建议进入公开网页快照。SEC provider 先从 `https://www.sec.gov/files/company_tickers.json` 匹配 ticker/CIK，再调用 `https://data.sec.gov/submissions/CIK{cik}.json` 读取近期披露元数据。SEC 请求必须带 `User-Agent`，当前配置为项目级研究标识；正式使用应改成你的机构/邮箱标识。

SEC Company Facts provider 调用 `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`，抽取常用 `us-gaap` 指标的最新事实值，用于财务基本面核验。SEC insider transactions provider 复用 `https://data.sec.gov/submissions/CIK{cik}.json`，筛选 Form 3/4/5 与修订表，用于监控内部人交易、持股变动和治理信号。SEC ownership activism provider 同样基于 submissions 数据，筛选 Schedule 13D/13G、13F 和 Form 144，用于监控匹配 filer 的重大持股、控制权、机构持仓和拟减持披露；它不是完整目标公司股东穿透表，关键结论仍需回看原文和补充外部持有人检索。SEC Investment Adviser Reports provider 下载 `https://www.sec.gov/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/ia060126.zip`，解析 SEC Investment Adviser Information Reports 中的 Form ADV 子集，抽取 CRD、SEC#、CIK、Firm Type、SEC status、latest ADV filing date、主办公室、网站、电话、books and records 地点等投顾/ERA 监管身份信号。SEC 说明这些报告来自 Form ADV/IARD，且 SEC 和州监管机构不保证填报内容准确；关键结论仍需回看 IAPD 和最新 Form ADV。FDIC BankFind provider 调用 `https://api.fdic.gov/banks/institutions`，按银行名称、网站或城市检索 FDIC 公开银行机构数据，抽取 FDIC certificate、active 状态、主监管机构、保险监管机构、charter agency、bank class、资产、国内存款、净利润、ROA/ROE、报告日期、成立日期、办公地点和网站。该来源适合银行/存款机构主体核验、金融机构风险和交易对手背景调查；FDIC 网站链接仍需人工确认身份和上下文。Federal Register provider 调用 `https://www.federalregister.gov/api/v1/documents.json`，使用 `conditions[term]`、`per_page`、`order=newest` 和字段筛选检索监管文件。

CPSC recalls provider 调用官方说明的 `https://www.saferproducts.gov/RestWebServices/Recall`，使用 `ProductName` 与 `format=json` 检索 CPSC 公开召回数据，抽取消费品安全 hazard、remedy、产品、企业角色、召回日期和原文链接。该数据用于产品安全/质量风险尽调，不能替代公司公告、监管处罚、诉讼和客户事故原始材料。

FDA enforcement recalls provider 调用 openFDA 的 `https://api.fda.gov/device/enforcement.json`、`https://api.fda.gov/food/enforcement.json` 和 `https://api.fda.gov/drug/enforcement.json`，抽取 Recall Enterprise System enforcement reports 中的 recall classification、recalling firm、product description、reason、distribution、status 和 report date。openFDA 数据用于 FDA 监管产品质量/召回风险线索，不应直接用于医疗判断。

FDA Device 510(k) provider 调用 openFDA 的 `https://api.fda.gov/device/510k.json`，按 device_name、applicant、product_code 和 k_number 检索 510(k) clearances，抽取 K number、申请人、器械名称、产品代码、decision date、decision description、clearance type、advisory committee、openfda device class 和 regulation number。该来源用于 medtech 产品准入、predicate/产品代码、上市路径和竞争产品线索；它不代表实时销售状态、临床疗效或法律意见。

FDA Device Adverse Events provider 调用 openFDA 的 `https://api.fda.gov/device/event.json`，检索 MAUDE medical device reports，抽取 report number、event type、date received/date of event、device brand/generic name、manufacturer、product code、UDI、PMA/PMN、openfda device class 和 regulation number。MAUDE 是被动监测数据，适合发现上市后安全/故障/投诉线索，但不能单独推断发生率、因果关系、产品总体安全性或医疗结论。

FDA Device Classification provider 调用 openFDA 的 `https://api.fda.gov/device/classification.json`，按 product_code、device_name、medical_specialty 和 medical_specialty_description 检索 FDA 产品分类，抽取 product code、device class、regulation number、review panel、submission type、third-party flag、implant/life-sustain support flag、GMP exempt flag 和 summary malfunction reporting eligibility。该来源用于把 510(k)、MAUDE、召回、UDI 和注册数据中的产品代码归一到监管分类维度。

FDA Device Registration and Listing provider 调用 openFDA 的 `https://api.fda.gov/device/registrationlisting.json`，按 products.product_code、products.openfda.device_name、registration.name 和 owner_operator.firm_name 检索注册/列名记录，抽取 registration number、FEI、firm、owner/operator、设施地址、establishment type、产品代码、proprietary names、PMA/K number 和 openfda 分类。该来源用于设施、供应链、注册状态和产品列名交叉验证；注册列名不代表产品批准或实时上市销售状态。

CFPB consumer complaints provider 调用 `https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/`，使用 `search_term`、`size` 和 `sort=created_date_desc` 检索公开消费金融投诉，抽取 company、product、issue、consumer narrative、company response、timely response、dispute、submission channel 和 state。CFPB 明确提示公司级投诉量需要结合公司规模和市场份额解释，不能单独作为消费者伤害程度结论。

NHTSA recalls provider 调用官方 `https://api.nhtsa.gov/recalls/recallsByVehicle`，从 query 中识别 model year、make 和 model，抽取 NHTSA campaign number、manufacturer、component、summary、consequence、remedy 和 report date。该 provider 是车型级 recall 检索，不是 VIN 级 open recall 状态；单车核验仍需 VIN 查询或制造商召回系统。

EPA ECHO facilities provider 调用 ECHO 官方 REST 服务 `https://echodata.epa.gov/echo/echo_rest_services.get_facilities`，先获取 QueryID，再用 `echo_rest_services.get_qid` 拉取设施列表；用设施/公司名查询 ECHO 设施合规和执法历史线索，抽取 EPA Registry ID、地址、经纬度、program system IDs、NAICS/SIC、非合规季度、正式执法和处罚计数。EPA ECHO 适合环境合规筛查，但单个项目结论仍需进入 Detailed Facility Report 和原始 program record 复核。

ClinicalTrials.gov provider 调用官方 `https://clinicaltrials.gov/api/v2/studies`，使用 `query.term`、`pageSize` 和 `format=json` 检索试验登记，抽取 NCT ID、overall status、phase、study type、sponsor、conditions、interventions、primary outcomes、enrollment、日期和地点。该来源用于产品管线/临床验证线索，不代表疗效、安全性或监管批准结论。

CMS Open Payments provider 调用 `https://openpaymentsdata.cms.gov/api/1/metastore/schemas/dataset/items` 发现最新年度 General、Research、Ownership payment datasets，再通过 `https://openpaymentsdata.cms.gov/api/1/datastore/query/{dataset_id}/0` 查询付款记录，抽取 reporting entity、covered recipient、教学医院、金额、付款性质、产品、NPI、地区和 program year。该来源用于药械/医药商业关系、KOL 支付、研究付款和权益关系尽调；付款记录本身不代表违规、背书或医疗结论。

US Census trade provider 调用 `https://api.census.gov/data/timeseries/intltrade/imports/hs` 和 `https://api.census.gov/data/timeseries/intltrade/exports/hs`，API key 只从 `CENSUS_API_KEY` 读取；优先识别 query 中的 HS code，返回国家、商品、月度值和年初至今值。FRED provider 调用 `https://api.stlouisfed.org/fred/series/search` 发现宏观经济序列，再调用 `https://api.stlouisfed.org/fred/series/observations` 获取最新观测值，API key 只从 `FRED_API_KEY` 读取。该来源用于利率、通胀、失业率、GDP、信用利差、收益率曲线、金融压力和宏观周期背景；FRED 序列需确认单位、频率、季调和发布时间，不能直接替代原始发布机构口径。GNews funding provider 调用 `https://gnews.io/api/v4/search`，API key 只从 `GNEWS_API_KEY` 读取，查询会自动叠加融资、并购、投资关键词。

SEC enforcement provider 调用 `https://www.sec.gov/enforcement-litigation/litigation-releases`，解析官方 litigation releases 列表作为执法/诉讼风险线索。USAJOBS provider 调用 `https://data.usajobs.gov/api/Search`，API key 和 user agent 分别只从 `USAJOBS_API_KEY`、`USAJOBS_USER_AGENT` 读取。

GDELT provider 调用 `https://api.gdeltproject.org/api/v2/doc/doc`，使用 `mode=ArtList`、`format=json`、`timespan=7d` 追踪近实时全球新闻。USAspending provider 调用 `https://api.usaspending.gov/api/v2/search/spending_by_award/`，用 `keywords`、`fields`、`limit` 和财政年度时间窗检索合同与拨款。SAM.gov opportunities provider 调用 `https://api.sam.gov/opportunities/v2/search`，API key 只从 `SAM_GOV_API_KEY` 读取，按 title、postedFrom、postedTo、limit 检索合同机会，抽取 notice ID、solicitation number、opportunity type、set-aside、NAICS/PSC、response deadline、agency path、place of performance、award/awardee、联系人、附件和 UI 链接。该来源用于前瞻政府需求、RFP/RFQ、sources sought、sole-source/special notice 和采购管线线索；API 只返回机会最新 active version，历史版本仍需回到 SAM.gov Data Services 复核。Grants.gov opportunities provider 调用 `https://api.grants.gov/v1/api/search2`，默认检索 `forecasted|posted` 机会，抽取 opportunity ID/number、title、agency、open/close date、status、docType 和 ALN/CFDA 列表。该来源用于 SBIR/STTR、政府资助、科研补助和非稀释资金管线发现；机会存在不代表目标公司申请、获奖或资金到账。

PatentsView provider 调用 `https://search.patentsview.org/api/v1/patent/`，使用专利标题、摘要和受让人文本检索技术证据；如果命中 USPTO Open Data Portal 迁移页，则返回 `temporarily_unavailable` 迁移提示。OFAC provider 使用官方 XML 下载地址 `https://www.treasury.gov/ofac/downloads/sdn.xml` 和 `https://www.treasury.gov/ofac/downloads/consolidated/consolidated.xml`，在本地解析匹配名称、别名、类型和制裁项目。

外部工具 provider 使用同一个 `external_search_tool` adapter：`Agent-Reach` 项目地址 `https://github.com/Panniantong/Agent-Reach`，用于社媒和垂直平台搜索/读取规划；`Scrapling` 项目地址 `https://github.com/D4Vinci/Scrapling`，用于公开或授权网页抓取规划；`Browser-use` 项目地址 `https://github.com/browser-use/browser-use`，用于 LLM 浏览器自动化规划；`Claude in Chrome` 官网 `https://claude.ai/chrome`，只能作为用户真实浏览器中的人工监督入口；`Web-access` 项目地址 `https://github.com/eze-is/web-access`，用于 Search/Fetch/curl/CDP 路由规划。这些 adapter 默认 `execute_enabled=false`，不会自动安装工具、登录账号、接管 Chrome 或绕过反爬；`/search/run` 返回的是可执行计划和 runtime/setup 状态。正式启用前需要确认安装、账号授权、域名 allowlist、动作范围、日志保留、robots/平台条款和人工确认策略。

```python
from app.core.router import get_router

results = get_router().search("brave_web_search").search("家庭机器人 SLAM 长期重定位", limit=5)
for result in results:
    print(result["title"], result["url"])
```

手动 smoke 验证 live search：

```bash
conda run -n robot_agent python scripts/smoke_search_sources.py \
  --academic-query "robot foundation model" \
  --sec-query "MSFT annual report" \
  --sec-facts-query "MSFT revenue" \
  --insider-query "MSFT insider transactions" \
  --ownership-query "Berkshire Hathaway 13F" \
  --adviser-query "BlackRock" \
  --fdic-query "Silicon Valley Bank" \
  --regulatory-query "robotics" \
  --recall-query "robot vacuum" \
  --fda-query "robotic surgical system" \
  --fda-510k-query "robotic surgical system" \
  --fda-event-query "robotic surgical system" \
  --fda-classification-query "NAY" \
  --fda-registration-query "NAY" \
  --cfpb-query "fintech lender" \
  --nhtsa-query "2024 Tesla Model Y recall" \
  --epa-query "battery manufacturing" \
  --clinical-query "robotic surgery" \
  --openpayments-query "Medtronic" \
  --trade-query "854231 imports" \
  --fred-query "inflation interest rate" \
  --news-query "robotics funding" \
  --funding-query "robotics funding" \
  --enforcement-query "robotics" \
  --jobs-query "robotics engineer" \
  --spending-query "robotics" \
  --sam-query "robotics" \
  --grants-query "robotics" \
  --patent-query "robot manipulation" \
  --sanctions-query "example" \
  --github-query "robotics foundation model" \
  --hf-query "robotics" \
  --company-query "openai" \
  --court-query "robotics" \
  --social-query "robotics VLA demo" \
  --scrape-query "https://example.com robotics" \
  --browser-query "Find robotics hiring evidence on an authorized site" \
  --chrome-query "Review a complex authorized page under supervision" \
  --web-access-query "robotics hiring search with public web first" \
  --limit 3
```

只验证外部工具入口时可以跳过旧 live API：

```bash
conda run -n robot_agent python scripts/smoke_search_sources.py \
  --external-only \
  --social-query "robotics VLA demo" \
  --scrape-query "https://example.com robotics" \
  --browser-query "Find robotics hiring evidence on an authorized site" \
  --chrome-query "Review a complex authorized page under supervision" \
  --web-access-query "robotics hiring search with public web first" \
  --limit 1
```

Brave、GDELT、GNews、Agent-Reach、Scrapling、Browser-use、Claude in Chrome 和 Web-access 返回结果只能作为开放网页/新闻/社媒/浏览器操作线索；GitHub、Hugging Face、Companies House、CourtListener、OpenAlex、SEC、FDIC、Federal Register、CPSC、FDA、CFPB、NHTSA、EPA、ClinicalTrials.gov、CMS Open Payments、US Census、FRED、USAJOBS、USAspending、SAM.gov、Grants.gov、PatentsView 和 OFAC 虽然更接近权威或结构化来源，仍需要回看原文、日期、主体、字段口径和上下文。能力、投资或交易合规相关结论不得只靠单一来源，应结合公司注册、诉讼、学术、产业、开源代码、模型生态、监管披露、财务事实、投顾/ERA/Form ADV、银行/存款机构身份、宏观利率/通胀/信用利差、内部人交易、重大持股/控制权披露、监管政策、产品召回/安全风险、FDA enforcement recalls、FDA 510(k) clearances、FDA MAUDE adverse events、FDA device classification/product codes、FDA device registration/listing、消费金融投诉、车辆安全召回、环境设施合规、临床试验登记、医疗付款/权益关系、贸易流、融资事件、非稀释资金机会、执法处罚、招聘薪酬、政府合同/拨款、政府采购机会、专利、制裁清单、候选人反馈或人工确认做交叉验证。

`due_diligence_federated_search` 的 plan/brief 会把目录来源和已注册 live provider 同时映射到尽调覆盖矩阵：`primary_disclosure`、`market_and_funding`、`macro_market_context`、`non_dilutive_funding`、`technical_evidence`、`people_and_hiring`、`community_signal`、`regulatory_enforcement`、`product_quality_safety`、`ownership_governance`、`investment_adviser_due_diligence`、`financial_institution_risk`、`environmental_supply_chain`、`clinical_validation`、`healthcare_commercial_relationships`、`government_procurement`。搜索阶段除市场、技术、人员和证据复核外，还显式包含 `compliance_risk`、`operational_risk` 和 `governance_and_contracts`，用于驱动制裁/诉讼/执法、召回/质量/环境/贸易、宏观利率/通胀/信用利差、投顾/ERA/Form ADV、银行/存款机构、非稀释资金、内部人交易/重大持股/政府合同/临床验证/医疗付款关系的后续检索动作。

## OpenRouter 多模型推理

OpenRouter 是当前默认 LLM provider。它用于多模型推理、证据抽取、证据裁判和可选联网研究，不替代 Brave、GitHub、学术 API、数据库或向量库这些真实数据源。历史中转站 `token_plan_anthropic` 仍保留为非默认路由，只有显式调用并配置 `ANTHROPIC_COMPATIBLE_API_KEY` 时才使用。

| Service | Provider | 默认启用 | 密钥环境变量 | 用途 |
| --- | --- | --- | --- | --- |
| `openrouter_auto_reasoning` | `openrouter_chat` | 是 | `OPENROUTER_API_KEY` | 自动路由模型，用于能力校准、证据综合和规划。 |
| `openrouter_online_research` | `openrouter_chat` | 否 | `OPENROUTER_API_KEY` | 带 OpenRouter web search server tool 的探索性研究；可能产生额外搜索成本。 |
| `openrouter_evidence_judge` | `openrouter_chat` | 否 | `OPENROUTER_API_KEY` | 对多源证据做一致性、冲突和置信度判断。 |

调用方式：

```python
from app.core.router import get_router

router = get_router()
answer = router.llm("openrouter_auto_reasoning").text(
    "判断这条家庭机器人 SLAM 能力是否应升级为必备能力。",
    max_tokens=512,
)
models = router.llm("openrouter_auto_reasoning").list_models()
```

OpenRouter Chat Completions 使用 `https://openrouter.ai/api/v1/chat/completions` 和 `Authorization: Bearer <OPENROUTER_API_KEY>`。模型目录可通过 `https://openrouter.ai/api/v1/models` 获取。`openrouter/auto` 会由 OpenRouter 自动选择合适模型；如果需要固定模型或成本上限，应新增单独 service 并显式指定模型。

| 数据源 | 用途 | 接入约束 |
| --- | --- | --- |
| 公开网页 / 搜索引擎 | 公开网页、产品资料、技术博客和公司公开信息 | 官方搜索 API、站内搜索、RSS 或公开网页，遵守 `robots.txt` 和平台条款。 |
| Boss / 猎聘 / 拉勾 / 智联 | 招聘岗位、薪酬、技能要求 | 授权账号、官方商业接口、人工导出或合规第三方服务。 |
| LinkedIn | 候选人履历、人才流动 | 官方/授权产品、人工检索或候选人主动提供资料。 |
| 公司官网 | 产品、团队、技术方向 | 遵守 `robots.txt`，优先公开招聘页、团队页、博客和新闻稿。 |
| GitHub | 工程能力、开源贡献 | 使用 GitHub API 或公开搜索，token 走环境变量。 |
| Hugging Face / ModelScope | 模型、数据集、Demo、Space 和开源影响力 | 官方 API、公开项目页或人工整理，记录 license 和发布日期。 |
| Google Scholar / arXiv | 学术能力、论文方向 | arXiv 用公开 API；Scholar 优先人工检索或合规第三方服务。 |
| 专利数据库 | 技术发明人和公司技术布局 | 公开检索、授权数据库 API 或人工导出。 |
| 企查查 / 天眼查 | 公司工商、融资、股权 | 官方商业接口或人工授权导出。 |
| 新闻媒体 | 融资、产品发布、团队动态 | RSS、新闻搜索 API、站内搜索或授权媒体数据库。 |
| AI 社区 / 论坛 | 年轻高潜人才、技术讨论、项目传播和社区影响力 | 公开页面、官方 API、授权社群整理或人工记录；不采集私域敏感信息。 |
| AI 活动 / 会议 | 活动参与者、演讲嘉宾、获奖项目和新兴团队线索 | 活动官网、公开议程、公开直播页或主办方授权名单。 |
| 视频平台 / 字幕 | Demo 真实性、技术讲解、公开演讲和项目影响力 | 官方 API、公开字幕、公开视频元数据或人工标注，保留 URL 和发布时间。 |
| 招股书 / 年报 | 上市公司业务和人员情况 | 交易所、监管机构和上市公司公开披露文件。 |
| 学校实验室官网 | 高校人才来源 | 公开网页、RSS 或人工整理，只采集公开职业线索。 |
| 会议论文名单 | ICRA、IROS、CoRL、RSS、CVPR、NeurIPS 等人才线索 | 官方 proceedings、OpenReview、Semantic Scholar、DBLP。 |

代码调用：

```python
from app.core.router import get_router

router = get_router()
plan = router.search().plan("VLA 机器人 招聘 薪酬", limit=5)
```

CLI 快速查看：

```bash
conda run -n robot_agent python - <<'PY'
from app.core.router import get_router

for source in get_router().search().search("ICRA humanoid control", limit=5):
    print(source["source_key"], source["name_zh"], source["purpose"])
PY
```

## 统一配置和路由

所有外部能力先在 `config/services.toml` 注册，再通过 `ServiceRouter` 调用。业务代码不要直接硬编码 OCR、搜索、Embedding、Qdrant、MCP 或 Skill 实现。

当前默认路由：

```toml
[defaults]
document_parser = "auto_document_parser"
embedding = "bge_m3_local"
vector_store = "qdrant_local"
ocr = "aliyun_ocr"
search = "due_diligence_federated_search"
mcp = "disabled_mcp"
structured_output = "outlines_structured_output"
database = "disabled_database"
llm = "openrouter_auto_reasoning"
```

命令行可临时覆盖服务：

```bash
conda run -n robot_agent python -m app.rag.ingest_worker \
  --file test_readme.md \
  --candidate-id cand_ai_native_002 \
  --document-parser auto_document_parser \
  --embedding bge_m3_local \
  --vector-store qdrant_local
```

后续接入搜索 API、OCR API、MCP server 或新的模型服务时，优先新增一个 `services.<name>` 配置，再在 `app/providers/` 中实现 provider，并在 `app/core/router.py` 中注册 provider 构造逻辑。当前接入规范以 `docs/capability_integration.md` 为准。

## 外部服务 Smoke Test

`.env` 保存本地密钥，`config/services.toml` 只保存环境变量名。外部服务验证：

```bash
conda run -n robot_agent python scripts/smoke_external_services.py
```

注意：该命令会检查已配置的外部服务凭证和连通性，运行前确认本地环境变量已经设置。

## 验证

固定使用 `robot_agent` 环境验证，避免系统 Python 3.10 缺少 `tomllib` 或系统 pytest 插件版本冲突：

```bash
conda run -n robot_agent python -m compileall app scripts tests
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 conda run -n robot_agent python -m pytest -q
```

如果只验证 README 的 Mermaid 在 GitHub、GitLab 或支持 Mermaid 的 Markdown 查看器中显示，直接打开 `README.md` 即可。若目标平台不支持 Mermaid，需要把三张图导出为 PNG/SVG 后再嵌入文档。
