# AI 招聘助手 E2E v4 报告

## A. 测试环境

- commit: 67b36b85acf0c2948242e6c693c75b0c72f10c77
- branch: main
- startedAt: 2026-06-09T14:29:11.246Z
- finishedAt: 2026-06-09T14:34:00Z
- appUrl: http://127.0.0.1:5174/projects/project_2026_ai_team
- apiBase: frontend /api via Vite preview proxy -> http://127.0.0.1:8011/api
- backendPort: 8011
- frontendPort: 5174
- projectDatabaseUrl: sqlite:///data/projects.sqlite3
- taskDatabaseUrl: sqlite:///data/tasks.sqlite3
- seed: {"candidates": 5, "jobs": 3, "matches": 5, "project_id": "project_2026_ai_team"}
- runId: e2e-v4-20260609-222640
- nodeVersion: v24.16.0
- pnpmVersion: 11.5.0
- pythonVersion: Python 3.12.13
- browserVersion: Google Chrome 147.0.7727.137
- e2eRunner: scripts/e2e_project_detail_clicks.mjs + supplemental probes + Playwright error probes + soak-lite

## B. 入口确认

- 真实入口链路: `frontend/index.html -> frontend/src/main.tsx -> frontend/src/app/App.tsx -> frontend/src/app/router.tsx -> /projects/project_2026_ai_team`
- TS App: PASS
- legacy `frontend/src/App.jsx`: 未被 `main.tsx` 挂载，仅作为历史参考。

## C. OpenAPI / Registry / Frontend Matrix

- openapi_path_count: 50
- openapi_method_endpoint_count: 51
- capabilityRegistry_path_count: 50
- active_ts_endpoint_count: 25
- active_ts_wrapper_endpoint_count: 25
- legacy_endpoint_count: 7
- backend_only_endpoint_count: 22
- registered_but_no_client_wrapper_count: 22
- missing_registry_count: 0
- stale_registry_count: 0
- category_counts: {'active_ts_productized': 25, 'legacy_only': 4, 'registered_only': 22}

| method | path | openapi | registry | TS wrapper | TS page | legacy wrapper | category | risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GET | /health | yes | yes | MainLayout.fetchHealth | MainLayout.fetchHealth | no | active_ts_productized | P2 |
| POST | /integrations/env | yes | yes | no | no | no | registered_only | P1 |
| GET | /integrations/status | yes | yes | getIntegrationsStatus | getIntegrationsStatus | no | active_ts_productized | P2 |
| POST | /jobs/match | yes | yes | runJobMatch | runJobMatch | no | active_ts_productized | P2 |
| POST | /outreach/draft | yes | yes | createOutreachDraft | createOutreachDraft | no | active_ts_productized | P2 |
| PATCH | /outreach/drafts/{draft_id} | yes | yes | updateOutreachDraft | updateOutreachDraft | no | active_ts_productized | P2 |
| GET | /outreach/history | yes | yes | getOutreachHistory | getOutreachHistory | no | active_ts_productized | P2 |
| POST | /outreach/send | yes | yes | sendOutreachDraft | sendOutreachDraft | no | active_ts_productized | P1 |
| GET | /projects/{project_id} | yes | yes | getProject | getProject | no | active_ts_productized | P2 |
| GET | /projects/{project_id}/candidate-search-schedules | yes | yes | getCandidateSearchSchedules | getCandidateSearchSchedules | no | active_ts_productized | P2 |
| GET | /projects/{project_id}/candidates | yes | yes | getProjectCandidatesPage | getProjectCandidatesPage | no | active_ts_productized | P2 |
| GET | /projects/{project_id}/candidates/unique | yes | yes | no | no | no | registered_only | P1 |
| POST | /projects/{project_id}/candidates/{job_candidate_id}/compliance-review | yes | yes | confirmCandidateCompliance | confirmCandidateCompliance | no | active_ts_productized | P2 |
| GET | /projects/{project_id}/jobs | yes | yes | getProjectJobs | getProjectJobs | no | active_ts_productized | P2 |
| PUT | /projects/{project_id}/jobs/{job_id}/candidate-search-schedule | yes | yes | updateCandidateSearchSchedule | updateCandidateSearchSchedule | no | active_ts_productized | P2 |
| POST | /projects/{project_id}/jobs/{job_id}/upload-resumes | yes | yes | uploadProjectResume | uploadProjectResume | no | active_ts_productized | P2 |
| GET | /projects/{project_id}/reports/latest | yes | yes | getLatestWeeklyReport | getLatestWeeklyReport | no | active_ts_productized | P2 |
| POST | /reports/weekly | yes | yes | saveWeeklyReport | saveWeeklyReport | no | active_ts_productized | P2 |
| GET | /reports/{report_id} | yes | yes | no | no | no | registered_only | P1 |
| POST | /resumes/ingest | yes | yes | no | no | no | registered_only | P1 |
| POST | /resumes/local-import | yes | yes | no | no | no | registered_only | P1 |
| GET | /review/feedback | yes | yes | no | no | no | registered_only | P1 |
| POST | /rsi/evaluate | yes | yes | no | no | no | registered_only | P1 |
| GET | /scenarios/meta | yes | yes | getScenariosMeta | getScenariosMeta | no | active_ts_productized | P2 |
| POST | /scenarios/run | yes | yes | runCandidateEvaluation, runProjectScenario, runWeeklyReport | runCandidateEvaluation, runProjectScenario, runWeeklyReport | no | active_ts_productized | P2 |
| POST | /search/archive | yes | yes | no | no | no | registered_only | P1 |
| GET | /search/archive/diff | yes | yes | no | no | no | registered_only | P1 |
| GET | /search/archive/recent | yes | yes | no | no | no | registered_only | P1 |
| POST | /search/brief | yes | yes | no | no | no | registered_only | P1 |
| POST | /search/evidence | yes | yes | no | no | no | registered_only | P1 |
| POST | /search/plan | yes | yes | no | no | no | registered_only | P1 |
| POST | /search/run | yes | yes | no | no | no | registered_only | P1 |
| POST | /search/watchlist/run | yes | yes | no | no | no | registered_only | P1 |
| GET | /segments | yes | yes | no | no | no | registered_only | P1 |
| POST | /segments | yes | yes | createSegment | createSegment | no | active_ts_productized | P2 |
| POST | /segments/query | yes | yes | querySegmentCandidates | querySegmentCandidates | no | active_ts_productized | P2 |
| GET | /segments/{segment_id} | yes | yes | no | no | no | registered_only | P1 |
| GET | /tasks/{task_id} | yes | yes | getTask | getTask | no | active_ts_productized | P2 |
| GET | /tasks/{task_id}/artifacts | yes | yes | no | no | no | registered_only | P2 |
| POST | /tasks/{task_id}/cancel | yes | yes | cancelTask | cancelTask | cancelTask | active_ts_productized | P2 |
| POST | /tasks/{task_id}/confirm | yes | yes | confirmTask | confirmTask | confirmTask | active_ts_productized | P2 |
| POST | /tasks/{task_id}/probe-feedback | yes | yes | no | no | sendProbeFeedback | legacy_only | P1 |
| POST | /tasks/{task_id}/retry | yes | yes | retryTask | retryTask | retryTask | active_ts_productized | P2 |
| GET | /tasks/{task_id}/stream | yes | yes | useTaskStream/taskStreamUrl | useTaskStream/taskStreamUrl | no | active_ts_productized | P2 |
| GET | /workflow/meta | yes | yes | no | no | no | registered_only | P2 |
| POST | /workflow/sessions | yes | yes | no | no | no | registered_only | P1 |
| POST | /workflow/sessions/{task_id}/nodes/{node_id}/retry | yes | yes | no | no | retryWorkflowNode | legacy_only | P1 |
| POST | /workflow/sessions/{task_id}/nodes/{node_id}/run | yes | yes | no | no | runWorkflowNode | legacy_only | P1 |
| POST | /workflow/sessions/{task_id}/nodes/{node_id}/skip | yes | yes | no | no | skipWorkflowNode | legacy_only | P1 |
| POST | /workflows/run | yes | yes | no | no | no | registered_only | P1 |
| POST | /workflows/validate | yes | yes | no | no | no | registered_only | P2 |

## D. 修复记录

### BUG-001-static-contract-hardcoded-count
- root cause: Static contract test asserted a fixed OpenAPI path count instead of comparing OpenAPI and registry sets.
- changed files: tests/test_static_contracts.py
- why safe: Test-only change; now catches both missing and stale registry paths and explicitly checks compliance-review.
- tests after: pytest-static-contracts-final.log: 108 passed
- regression: frontend lint/build/test, compileall, backend pytest all passed.

### BUG-002-e2e-audit-tooling
- root cause: No reusable v4 matrix/probe/report tooling existed for the requested audit.
- changed files: scripts/e2e_v4_contract_audit.py, scripts/e2e_v4_api_probes.py, scripts/e2e_v4_render_report.py, artifacts/e2e_evidence/runner/error-probes-v4.mjs
- why safe: Read/probe/report tooling only; product code and business logic unchanged.
- tests after: compileall-final PASS; probes all 200 except intentionally simulated 4xx/5xx error cases.
- regression: No new unit/build failures.

## E. 当前 TS endpoint E2E 总览

| 功能/接口 | 状态 | 证据 |
| --- | --- | --- |
| 岗位分析：scenario A task/SSE + task control | PASS | task=c7341ed2ff6f; evidence=4 |
| 找候选人：scenario B task/SSE | PASS | task=d590fea40d75; evidence=2 |
| 候选人评估 + 任务 HumanGate 确认 | PASS | task=0bbd2991a6a9; evidence=4 |
| 招聘周报：scenario D task/SSE + HumanGate + 持久化 | PASS | task=2129768b30b6; evidence=4 |
| 人群筛选闭环：后端查询 + 保存能力门控 | LIMITED | task=—; evidence=1 |
| 邮件触达闭环：后端草稿 + 人工确认 + 模拟发送记录 | PASS | task=—; evidence=4 |
| 岗位匹配 UI：真实 /jobs/match 结果 | PASS | task=—; evidence=1 |
| 补充 API probes | PASS | 33 probes, all status 200 |
| 错误态 probes | PASS | 9 pass / 0 fail |

## F. A/B/C/D task 总览

| scenario | task_id | status | notes |
| --- | --- | --- | --- |
| 岗位分析：scenario A task/SSE + task control | c7341ed2ff6f | PASS |  |
| 找候选人：scenario B task/SSE | d590fea40d75 | PASS |  |
| 候选人评估 + 任务 HumanGate 确认 | 0bbd2991a6a9 | PASS |  |
| 招聘周报：scenario D task/SSE + HumanGate + 持久化 | 2129768b30b6 | PASS |  |

## G. 找候选人 B 入库专项

- B task_id: `d590fea40d75`
- 初次点击后状态: awaiting_human，需要 confirm 后才入库。
- confirm 后: `found=8 normalized=8 inserted=0 linked=8 duplicates=0 rejected=0`，项目候选人关联数增加。
- 重复跑 B: `found=6 inserted=0 linked=0 duplicates=6`，X-Total-Count 保持 16。
- 结论: 入库闭环存在；不会重复插入同一批候选人。页面未前端 append 假候选人。

## H. 邮件触达

- draft: 后端 `/outreach/draft` 创建，`backendGenerated=true`。
- send mode: email_delivery missing_key 时 `simulate=true`，history 写入 `deliveryMode=simulated`。
- 结论: 未发现真实发送误导文案。

## I. Segment

- UI: `/segments/query` PASS；保存按钮因 `database_api=disabled` 被正确门控，状态 LIMITED。
- API probe: POST `/segments` 200，segmentId=['segment_767d246a8128']。

## J. JSON Workflow

- validate: valid workflow true；duplicate id / unresolved placeholder / future dependency / duplicate output_key / invalid limit / invalid max_retries / missing field / unsupported step type 均返回 valid=false。
- run: `scenario_id=json_workflow`，human_gate awaiting，confirm 后 done，result 包含 workflow_id/context/artifacts/final_output。
- A/B/C/D regression: E2E 主链路 PASS。

## K. Soak Test Metrics

- startedAt: 2026-06-09T14:39:29Z
- finishedAt: 2026-06-09T14:41:29Z
- durationSeconds: 120.7
- loops: 24
- passLoops: 24
- failedLoops: 0
- averageDurationMs: 29.4
- p95CallDurationMs: 8.0
- networkErrorCount: 0
- timeoutCount: 0
- pollingMax: —
- sseFailures: —
- consoleErrors: —
- eventSourceObservation: not measured in soak-lite
- 说明: 本轮为 120 秒 soak-lite，未跑满 30 分钟，最终状态按 LIMITED 处理。

## L. 风险清单

- P1 P1-B-INGESTION-GATE: Scenario B requires HumanGate confirmation before lead_ingestion; pre-confirm page only shows task/SSE, not new candidates. Evidence: scenario-b-confirm-v4.log: after confirm lead_ingestion found=8 linked=8; repeat run duplicates=6 count unchanged.
- P1 P1-SEGMENT-UI-GATE: Segment save is UI LIMITED because database_api is disabled; backend POST /segments works in API probe. Evidence: UI flow LIMITED with database API 未接入; supplemental POST /segments 200.
- P2 P2-SOAK-DURATION: Soak was 120 seconds / 24 loops, not the requested 30-120 minutes. Evidence: soak-v4.json: passLoops=24, failedLoops=0.

## M. 最终结论

1. 当前 TS 前端真实入口是否确认: PASS
2. 当前 TS 24 endpoint 是否全部通过 E2E: PASS；当前实际 active TS endpoint count=25，包含额外 compliance-review。
3. OpenAPI 和 capabilityRegistry 是否对齐: PASS
4. compliance-review 是否已补 registry: PASS
5. 后端已有但 TS 未接能力: 见 C 表，backend/registered/legacy only 共 26 个 method endpoint。
6. 找候选人是否已完成入库闭环: PASS，需要 HumanGate confirm 后完成。
7. 是否存在假数据: NO
8. 是否存在假成功: NO
9. 是否可用于内部演示: YES
10. 是否可用于内部试用: LIMITED
11. 下一步建议: 跑满 30 分钟 soak；如需 segment UI 保存，接入/启用 database_api；在 B flow UI 上更明确提示 awaiting_human 后才会入库。

整体结论: LIMITED
