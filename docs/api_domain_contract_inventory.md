# API 与领域契约资料清单

生成时间：2026-06-10
仓库路径：`/home/lison/Desktop/zhaoping`

## 结论

当前仓库以 FastAPI 运行时 OpenAPI 为后端契约源，以 TypeScript Router 前端为唯一有效入口：

- 后端入口：`app/api/main.py`
- 前端入口：`frontend/index.html -> frontend/src/main.tsx -> frontend/src/app/App.tsx -> frontend/src/app/router.tsx`
- 前端 API client：`frontend/src/shared/api/client.ts`
- 项目工作区 API wrapper：`frontend/src/features/projects/api.ts`
- Auth API wrapper：`frontend/src/features/auth/api.ts`
- capability registry：`frontend/src/capabilities/capabilityRegistry.js`

旧 JSX workbench 已删除，不能再作为产品化入口或契约依据。

## 后端契约

FastAPI 自动生成：

- Swagger UI：`/docs`
- OpenAPI JSON：`/openapi.json`

导出命令：

```bash
.venv/bin/python - <<'PY' > openapi.json
from app.api.main import app
import json

print(json.dumps(app.openapi(), ensure_ascii=False, indent=2))
PY
```

核心路由分组：

- 项目：`/projects/*`
- 候选人、岗位、周报、触达：`/projects/{project_id}/...`、`/jobs/match`、`/reports/*`、`/outreach/*`
- 任务流：`/tasks/{task_id}`、`/tasks/{task_id}/stream`、`/tasks/{task_id}/confirm`
- JSON workflow：`/workflows/validate`、`/workflows/run`
- Atomic workflow 后端控制：`/workflow/meta`、`/workflow/sessions/*`
- 搜索与归档：`/search/*`
- 集成状态：`/integrations/status`
- 鉴权：`/auth/login`、`/auth/me`

## 前端契约

当前前端使用 React Router：

- `frontend/src/app/router.tsx` 定义页面路由。
- `frontend/src/app/MainLayout.tsx` 管理项目切换、健康状态和本地登录状态。
- `frontend/src/pages/ProjectDetailPage.tsx` 是项目主工作台，负责 BP 初始化、场景任务、候选人搜索、HumanGate、周报、触达和任务实时日志。
- `frontend/src/shared/hooks/useTaskStream.ts` 负责 SSE、快照刷新和 fallback polling。

API 封装分层：

- `frontend/src/shared/api/client.ts`：统一 fetch、query、JWT token provider、错误处理。
- `frontend/src/features/projects/api.ts`：项目工作区业务 API。
- `frontend/src/features/auth/api.ts`：本地 JWT 登录、持久化和退出。

## 数据实体

主要 SQLAlchemy model：

- `app/models/project.py`
- `app/models/job.py`
- `app/models/candidate.py`
- `app/models/outreach.py`
- `app/models/report.py`
- `app/models/auth.py`
- `app/db/task_models.py`

主要 Pydantic schema：

- `app/schemas/project.py`
- `app/schemas/job.py`
- `app/schemas/candidate.py`
- `app/schemas/outreach.py`
- `app/schemas/reports.py`
- `app/schemas/auth.py`
- `app/schemas/tasks.py`
- `app/schemas/workflows.py`

## 能力注册

`frontend/src/capabilities/capabilityRegistry.js` 必须覆盖 OpenAPI paths，并用以下状态表达产品化程度：

- `productized`：当前 TS 页面或 wrapper 有实际用户路径。
- `system`：系统支撑接口，通常由任务流、集成状态或后端控制流程使用。
- `closed`：保留或占位接口，不应展示为用户主路径。

验证测试：

```bash
.venv/bin/python -m pytest tests/test_static_contracts.py::test_frontend_capability_registry_productizes_all_backend_paths -q
```

## 运行产物

运行输出不得进入 git：

- `artifacts/`
- `test-results/`
- `data/ocr_smoke.png`
- `data/runtime/`
- `data/workflow_artifacts/`
- `data/*.sqlite3`

验证测试：

```bash
.venv/bin/python -m pytest tests/test_static_contracts.py::test_generated_runtime_artifacts_are_not_versioned -q
```

## 推荐验证

```bash
.venv/bin/python -m compileall app scripts tests
.venv/bin/python -m pytest -q
pnpm --dir frontend test
pnpm --dir frontend build
```
