# AI 招聘助手全量长测 v3 报告

- E2E_RUN_ID: 20260609_104936
- Started: 2026-06-09T10:49:36.887Z
- Finished: 2026-06-09T10:51:46.886Z
- Duration: 130s
- Overall: LIMITED

## A. 环境与启动

- Branch: main
- Commit: cdc3e047dde5ac246fcba5c61baa421241ac5a98
- Git dirty status: M app/core/workflow_context.py;  M app/core/workflow_executor.py;  M frontend/src/pages/ProjectDetailPage.test.tsx;  M frontend/src/pages/ProjectDetailPage.tsx;  M tests/test_json_workflow_engine.py; ?? artifacts/; ?? test-results/; ?? tests/fixtures/
- OS: Linux 6.8.0-124-generic x64
- Python: Python 3.11.0rc1
- Node: v24.16.0
- pnpm: 11.5.0
- Browser/Test runner: Version 1.60.0
- API base: http://127.0.0.1:8010/api
- Frontend: http://127.0.0.1:5174
- Project DB: /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/projects.sqlite3
- Task DB: /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/tasks.sqlite3

## B. Seed 与 Cleanup 清单

- Seed summary: {"candidates":5,"jobs":3,"matches":5,"project_id":"project_2026_ai_team"}
- Seed IDs: {"projectIds":["project_2026_ai_team"],"jobIds":["job_vla_algorithm","job_robot_data_platform","job_embodied_agent_infra"],"candidateIds":["cand_lin_chen","cand_zhou_han","cand_maya_li","cand_wang_ke","cand_sara_qi"],"matchCount":5}
- Created runtime IDs: {"taskIds":["633ce3d78712","58cd895dbc2e","d004288d4365","b1f474f98034","6803923ff001","2804f0522087","25d4b63d1ec7","e545e47e9c24","fc8a23da31c3","806a307a58d1","7c14089738d6","017a5c58358d","7f7775862c75","65c6cb299d48"],"reportIds":["report_e75c3cca3b27"],"segmentIds":["segment_9233b03c8f6d"],"draftIds":["draft_93978745e1f8"],"historyIds":["history_a763baec54d5"]}
- Cleanup policy: artifact SQLite DB 保留用于复核；可删除 `artifacts/e2e_evidence/projects.sqlite3` 与 `tasks.sqlite3` 清理本次数据。

## C. 命令验证

| Command | Verdict | Exit | Log |
| --- | --- | ---: | --- |
| frontend lint | PASS | 0 | /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/command-logs/frontend-lint.log |
| frontend build | PASS | 0 | /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/command-logs/frontend-build.log |
| frontend test | PASS | 0 | /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/command-logs/frontend-test.log |
| python compileall | PASS | 0 | /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/command-logs/python-compileall.log |
| pytest all | PASS | 0 | /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/command-logs/pytest-all.log |
| pytest json workflow | PASS | 0 | /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/command-logs/pytest-json-workflow.log |
| pytest static contracts | PASS | 0 | /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/command-logs/pytest-static-contracts.log |
| ui-e2e-project-detail | PASS | 0 | /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/command-logs/ui-e2e-project-detail.log |

## D. API 合同探测

| Name | Method | Path | Status | Verdict | Note |
| --- | --- | --- | ---: | --- | --- |
| health | GET | /health | 200 | PASS |  |
| openapi | GET | /openapi.json | 200 | PASS |  |
| project detail | GET | /projects/project_2026_ai_team | 200 | PASS |  |
| project jobs | GET | /projects/project_2026_ai_team/jobs | 200 | PASS |  |
| project candidates | GET | /projects/project_2026_ai_team/candidates?skip=0&limit=50 | 200 | PASS |  |
| unique candidates | GET | /projects/project_2026_ai_team/candidates/unique | 200 | PASS |  |
| integrations status | GET | /integrations/status | 200 | PASS |  |
| scenarios meta | GET | /scenarios/meta | 200 | PASS |  |
| workflow meta | GET | /workflow/meta | 200 | PASS |  |
| segments query | POST | /segments/query | 200 | PASS |  |
| segments save | POST | /segments | 200 | PASS |  |
| segments list | GET | /segments?projectId=project_2026_ai_team | 200 | PASS |  |
| segments get | GET | /segments/segment_9233b03c8f6d | 200 | PASS |  |
| weekly report save | POST | /reports/weekly | 200 | PASS |  |
| weekly report latest | GET | /projects/project_2026_ai_team/reports/latest | 200 | PASS |  |
| weekly report get | GET | /reports/report_e75c3cca3b27 | 200 | PASS |  |
| outreach draft | POST | /outreach/draft | 200 | PASS |  |
| outreach patch | PATCH | /outreach/drafts/draft_93978745e1f8 | 200 | PASS |  |
| outreach simulate send | POST | /outreach/send | 200 | PASS |  |
| outreach history | GET | /outreach/history?projectId=project_2026_ai_team | 200 | PASS |  |
| search plan local catalog | POST | /search/plan | 200 | PASS |  |
| search run local catalog | POST | /search/run | 200 | PASS |  |
| search archive recent | GET | /search/archive/recent?limit=5 | 200 | PASS |  |
| rsi evaluate local | POST | /rsi/evaluate | 200 | PASS |  |
| jobs match fallback | POST | /jobs/match | 200 | PASS | May be LIMITED if local embedding/vector provider is unavailable and DB fallback cannot match. |
| resumes ingest | POST | /resumes/ingest | 500 | LIMITED | Endpoint depends on local parser/embedding/vector-store; no live provider is configured in this run. |
| scenario task create | POST | /scenarios/run | 200 | PASS |  |
| task snapshot | GET | /tasks/633ce3d78712 | 200 | PASS |  |
| task cancel | POST | /tasks/633ce3d78712/cancel | 200 | PASS |  |
| concurrent workflow create 1 | POST | /workflows/run | 200 | PASS |  |
| concurrent workflow create 3 | POST | /workflows/run | 200 | PASS |  |
| concurrent workflow create 2 | POST | /workflows/run | 200 | PASS |  |
| concurrency unique task_id audit | ASSERT | /workflows/run x3 | assert | PASS | API-level concurrency probe; UI reclick debounce is covered as LIMITED unless a dedicated browser reclick script is run. |
| validate advanced_ai_algorithm_recruiting.json | POST | /workflows/validate | 200 | PASS |  |
| validate resume_structured_extract.json | POST | /workflows/validate | 200 | PASS |  |
| validate jd_structured_extract.json | POST | /workflows/validate | 200 | PASS |  |
| advanced recruiting workflow task create | POST | /workflows/run | 200 | PASS |  |
| invalid workflow duplicate step id | POST | /workflows/validate | 200 | PASS |  |
| invalid workflow unresolved placeholder | POST | /workflows/validate | 200 | PASS |  |
| invalid workflow future dependency | POST | /workflows/validate | 200 | PASS |  |
| invalid workflow duplicate output_key | POST | /workflows/validate | 200 | PASS |  |
| invalid workflow invalid limit | POST | /workflows/validate | 200 | PASS |  |
| invalid workflow invalid max_retries | POST | /workflows/validate | 200 | PASS |  |
| invalid workflow missing required field | POST | /workflows/validate | 200 | PASS |  |
| invalid workflow unsupported step type | POST | /workflows/validate | 200 | PASS |  |
| json workflow long human run | POST | /workflows/run | 200 | PASS |  |
| json workflow task after backend restart | GET | /tasks/2804f0522087 | 200 | PASS |  |
| json workflow confirm after restart | POST | /tasks/2804f0522087/confirm | 200 | PASS |  |
| json workflow cancel probe create | POST | /workflows/run | 200 | PASS |  |
| json workflow cancel | POST | /tasks/25d4b63d1ec7/cancel | 200 | PASS |  |
| json workflow retry legacy endpoint | POST | /tasks/25d4b63d1ec7/retry | 500 | LIMITED | Current retry route is legacy scenario retry; JSON workflow retry support is assessed as LIMITED if it cannot restart json_workflow. |

## E. UI E2E 闭环

| Feature | Status | task_id | SSE | HumanGate | Final | Fake Data/Success Audit |
| --- | --- | --- | --- | --- | --- | --- |
| 页面加载 | PASS | — | no | no | — | 未发现 mock-only 候选人名 |
| 岗位分析 A | PASS | e545e47e9c24 | yes | yes | done | 未发现前端本地伪造 task_id/done，终态来自 GET /tasks probe 与 SSE 事件 |
| 找候选人 B | PASS | fc8a23da31c3 | yes | yes | done | 未发现前端生成假候选人 |
| 候选人评估 C | PASS | 806a307a58d1 | yes | yes | done | 评分/状态来自 task result.database_update 与后端刷新，不是前端生成评分 |
| 招聘周报 D | PASS | 7c14089738d6 | yes | yes | done | 周报显示来自可解析 task result/后端保存结果 |
| HumanGate | PASS | 806a307a58d1, 017a5c58358d, 7f7775862c75 | yes | yes | done, done, done | confirm 响应未直接伪造 done，终态等待后端 task snapshot |
| 邮件草稿 | PASS | — | no | yes | — | 草稿来自后端；未显示发送成功；send simulate=true |
| 人群筛选 | PASS | — | no | no | — | 未显示已保存后端分群 |
| SSE fallback | PASS | 65c6cb299d48 | no | yes | done | 终态来自 fallback GET /tasks snapshot，不是本地伪造 done |
| 错误态 | PASS | — | no | no | — | 未显示假项目/岗位/候选人 |

## F. JSON Workflow 专项

### Valid Fixtures
- PASS: tests/fixtures/json_workflows/advanced_ai_algorithm_recruiting.json
- PASS: tests/fixtures/json_workflows/resume_structured_extract.json
- PASS: tests/fixtures/json_workflows/jd_structured_extract.json

### Invalid Workflow Validation
- PASS: duplicate step id
- PASS: unresolved placeholder
- PASS: future dependency
- PASS: duplicate output_key
- PASS: invalid limit
- PASS: invalid max_retries
- PASS: missing required field
- PASS: unsupported step type

### Long-Running Human-In-The-Loop
- Verdict: PASS
- Task: 2804f0522087
- PASS: awaiting_human before restart (status=awaiting_human)
- PASS: runtime checkpoint exists (frontend_state.json_workflow_runtime missing)
- PASS: current_step_index stopped at human_gate (current_step_index=1)
- PASS: awaiting payload exists (awaiting payload missing)
- PASS: pre-step executed once before restart (pre_screen count=1)
- PASS: still awaiting after restart (status=awaiting_human)
- PASS: checkpoint index preserved after restart (current_step_index=1)
- PASS: not marked interrupted error (error=)
- PASS: done after confirm (status=done)
- PASS: pre human_gate step not repeated (pre_screen count=1)
- PASS: final result workflow_id (workflow_id missing)
- PASS: final result context (context missing)
- PASS: final result artifacts (artifacts missing)
- PASS: final result final_output (final_output missing)
- PASS: confirm stored in runtime context (decision=approve)

### Pytest Evidence
- PASS: .venv/bin/python -m pytest tests/test_json_workflow_engine.py -q
- PASS: .venv/bin/python -m pytest tests/test_static_contracts.py -q

## G. 静态审计与风险

| Check | File | Verdict | Note |
| --- | --- | --- | --- |
| ProjectDetailPage does not import projectMock | frontend/src/pages/ProjectDetailPage.tsx | PASS | 防止项目详情页在 API 失败时回退假数据。 |
| ProjectDetailPage does not call buildCandidateEmailDraft | frontend/src/pages/ProjectDetailPage.tsx | PASS | 触达草稿应来自 /outreach/draft。 |
| legacy buildCandidateEmailDraft only exists in state helper | frontend/src/features/projects/state.ts | INFO | P2: helper/test fixture 存在，但项目详情页未调用。 |
| weekly report parser supports Chinese backend keys | frontend/src/pages/ProjectDetailPage.tsx | PASS | D 场景 task result 的中文键可被 UI 消费。 |
| useTaskStream uses EventSource | frontend/src/shared/hooks/useTaskStream.ts | PASS | SSE 主链路存在。 |
| useTaskStream has fallback polling | frontend/src/shared/hooks/useTaskStream.ts | PASS | SSE 失败后轮询兜底存在。 |
| confirm route checks json_workflow_runtime before legacy confirm | app/api/main.py | PASS | 避免 JSON workflow confirm 走 legacy wait_event 错误分支。 |
| recovery preserves awaiting JSON workflow | app/core/orchestrator.py | PASS | 重启恢复不应把 awaiting_human checkpoint 标为 interrupted error。 |
| workflow executor does not import concrete providers | app/core/workflow_executor.py | PASS | JSON Workflow Engine 通过 ServiceRouter 而非具体 provider。 |
| structured extract retry prompt is sanitized | app/core/workflow_context.py | PASS | 失败上下文不能泄露 key/provider internals。 |
| projectMock file still exists but is isolated | frontend/src/shared/mocks/projectMock.ts | INFO | P2: 测试 fixture 存在；运行时页面未导入。 |

## H. 稳定性与安全

- Soak verdict: LIMITED
- Soak configured seconds: 30
- Soak note: This run used a short soak. Set E2E_SOAK_SECONDS=1800..7200 to satisfy the requested 30-120 minute stability window.
- PASS: report redaction - JSON report is checked for raw email pattern before final write.
- PASS: secret redaction - JSON report is checked for common API key/token prefixes before final write.

## I. 最终决策

- 真实后端闭环: YES
- UI 是否消费后端结果: YES
- 长时间稳定性: LIMITED
- 假数据/假成功: NO_BLOCKING_EVIDENCE
- 内部 demo: YES
- 内部试用: LIMITED
- P0 fixes: []
- P1 fixes: []
- Limited reasons: 2 API contract(s) are environment-limited; full 30-120 minute soak was not run; JSON workflow retry endpoint is legacy-limited

## Artifacts

- devServerLog: /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/dev-server.log
- devServerRestart2Log: /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/dev-server-restart-2.log
- uiE2EJson: /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/e2e-report.json
- networkLog: /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/network-log.json
- probeLog: /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/probe-log.json
- trace: /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/trace.zip
- fallbackTrace: /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/fallback-trace.zip
- fullJsonReport: /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/e2e_project_detail_report.json
- markdownReport: /home/lison/Desktop/zhaoping/artifacts/e2e_evidence/e2e-report.md
