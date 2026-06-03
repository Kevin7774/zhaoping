# 机器人招聘 Agent MVP

面向家庭场景全栈整机机器人公司的 AI 原生招聘行研 Agent MVP。项目当前重点是把业务招聘请求、多模态多源数据、岗位能力标准、候选人材料和人工反馈接入统一的 RAG、Memory、Evaluation 与数据飞轮底座，便于后续扩展 OCR、搜索、MCP、Workflow、Skills、结构化抽取和人工复核流程。

## 当前能力

- PostgreSQL 四张核心表：能力标准、岗位画像、候选人画像、评审反馈。
- 12 个具身机器人岗位元数据与能力标签字典。
- 6 个跨学科团队画像：系统架构、AI 多模态、机器人控制、机电结构、嵌入式实时、产品交付。
- 场景 A/B/C/D 本地招聘工作流：岗位画像与 JD、人才地图、候选人评估、招聘周报。
- 候选人简历/作品抽取的 Pydantic 结构化输出 schema。
- 本地 4090 文档解析、Embedding、Qdrant 入库脚本。
- FastAPI 预留简历入库、岗位匹配、反馈查询接口。
- 配置驱动的服务路由：文档解析、OCR、Embedding、向量库、LLM、DB、MCP、Skill 都通过 `config/services.toml` 注册。
- Search 数据源目录：网页、招聘站、LinkedIn、公司官网、GitHub、Hugging Face、ModelScope、论文、专利、AI 社区、活动、视频、工商、新闻、年报、高校实验室、会议论文名单。

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
        C["C：候选人评估\n匹配评分 / 风险点 / 面试追问 / 推荐结论 / 证据链"]
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
| `docs/capability_integration.md` | 新增能力时的集成规范。 |
| `tests/test_static_contracts.py` | 配置、路由、静态能力字典和基础 RAG 工具函数的契约测试。 |

## 环境安装

项目要求 Python 3.11 或更高版本；不要使用系统默认 Python 3.10 运行本项目。推荐固定使用 `robot_agent` conda 环境，当前已验证环境为 Python 3.11。

```bash
conda create -n robot_agent python=3.11 -y
conda activate robot_agent
python --version
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu121
```

如果本机已经存在 `robot_agent` 环境，直接激活并补齐依赖：

```bash
conda activate robot_agent
python --version
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu121
```

`python --version` 必须显示 `Python 3.11.x`。如果显示 `Python 3.10.x`，说明没有进入正确环境。

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

```bash
conda run -n robot_agent uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

当前接口：

| 方法 | 路径 | 输入 | 输出 |
| --- | --- | --- | --- |
| `GET` | `/health` | 无 | `{"status": "ok"}` |
| `POST` | `/resumes/ingest` | `file_path`、`candidate_id`、`write_database` | 候选人 ID 与 Markdown 预览 |
| `POST` | `/jobs/match` | `query`、`top_k` | Qdrant 检索结果 |
| `GET` | `/review/feedback` | 无 | 当前为占位状态 |

示例：

```bash
curl -X POST http://localhost:8000/resumes/ingest \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"test_readme.md","candidate_id":"cand_ai_native_002"}'

curl -X POST http://localhost:8000/jobs/match \
  -H 'Content-Type: application/json' \
  -d '{"query":"Diffusion Policy 和遥操作数据清洗经验","top_k":5}'
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
evaluation = evaluate_candidate("候选人材料...", target="家庭机器人 VLA 算法工程师")
weekly_report = generate_weekly_report("本周招聘进展、候选人状态、面试反馈和市场信号...")
```

也可以通过 `ServiceRouter` 读取注册后的 Skill：

```python
from app.core.router import get_router

scenarios = get_router().skills["home_robot_recruiting_scenarios"]
job = scenarios["functions"]["generate_job_profile_and_jd"]("我们想招一个家庭机器人 VLA 算法工程师")
weekly_report = scenarios["functions"]["generate_weekly_report"]("本周招聘周报数据...")
```

## Search 数据源接入

当前 `search` 默认服务是本地数据源目录 provider：`talent_source_catalog`。它不会直接抓取网页或调用付费接口，而是返回应该查询哪些数据源、用途、人才信号、建议 query 和合规接入方式。真实联网采集应逐个接入官方 API、授权账号、MCP 或人工导出流程。

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
search = "talent_source_catalog"
mcp = "disabled_mcp"
structured_output = "outlines_structured_output"
database = "disabled_database"
llm = "token_plan_anthropic"
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
