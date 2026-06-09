import { chromium } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const artifactDir = path.resolve(__dirname, "..");
const baseUrl = process.env.E2E_BASE_URL || "http://127.0.0.1:5178";
const projectId = process.env.E2E_PROJECT_ID || "project_2026_ai_team";
const terminalStatuses = new Set(["done", "error", "cancelled"]);

const report = {
  run: {
    startedAt: new Date().toISOString(),
    baseUrl,
    projectId,
    seed: {
      projectId,
      jobs: 3,
      candidates: 5,
      matches: 5,
      source: "scripts/seed_db.py",
    },
  },
  networkLog: [],
  probeLog: [],
  eventSourceLog: [],
  features: [],
  artifacts: {},
};

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function apiUrl(apiPath) {
  return `${baseUrl}/api${apiPath}`;
}

function pathWithQuery(url) {
  const parsed = new URL(url);
  return `${parsed.pathname}${parsed.search}`;
}

function stripApi(pathnameWithQuery) {
  return pathnameWithQuery.startsWith("/api")
    ? pathnameWithQuery.slice(4) || "/"
    : pathnameWithQuery;
}

function redact(value) {
  if (value === null || value === undefined) return value ?? null;
  if (typeof value === "string") {
    if (value.includes("@")) return value.replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[email redacted]");
    return value.length > 240 ? `${value.slice(0, 240)}...` : value;
  }
  if (typeof value === "number" || typeof value === "boolean") return value;
  if (Array.isArray(value)) return { type: "array", length: value.length, sample: value.slice(0, 2).map(redact) };
  if (typeof value === "object") {
    const output = {};
    for (const [key, item] of Object.entries(value).slice(0, 18)) {
      if (/key|token|secret|password|credential/i.test(key)) output[key] = "[redacted]";
      else if (/email/i.test(key) && typeof item === "string") output[key] = "[email redacted]";
      else output[key] = redact(item);
    }
    return output;
  }
  return String(value);
}

function parseBody(raw) {
  if (!raw) return null;
  try {
    return redact(JSON.parse(raw));
  } catch {
    return redact(raw);
  }
}

async function summarizeResponse(response) {
  const contentType = response.headers()["content-type"] || "";
  if (contentType.includes("text/event-stream")) return "text/event-stream";
  try {
    if (contentType.includes("application/json")) return redact(await response.json());
    const text = await response.text();
    return redact(text);
  } catch (error) {
    return `response body unavailable: ${error instanceof Error ? error.message : String(error)}`;
  }
}

function attachNetwork(page, label) {
  const requestEntries = new WeakMap();
  page.on("request", (request) => {
    const url = request.url();
    if (!url.startsWith(`${baseUrl}/api`)) return;
    const fullPath = pathWithQuery(url);
    const entry = {
      source: label,
      timestamp: new Date().toISOString(),
      method: request.method(),
      url,
      fullPath,
      path: stripApi(fullPath),
      requestBodySummary: parseBody(request.postData()),
      status: null,
      responseSummary: null,
    };
    report.networkLog.push(entry);
    requestEntries.set(request, entry);
  });
  page.on("response", async (response) => {
    const entry = requestEntries.get(response.request());
    if (!entry) return;
    entry.status = response.status();
    entry.responseSummary = await summarizeResponse(response);
  });
  page.on("requestfailed", (request) => {
    const entry = requestEntries.get(request);
    if (!entry) return;
    entry.status = "failed";
    entry.failure = request.failure()?.errorText || "request failed";
  });
}

async function probe(method, apiPath, body = undefined) {
  const startedAt = new Date().toISOString();
  const response = await fetch(apiUrl(apiPath), {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const contentType = response.headers.get("content-type") || "";
  let payload;
  if (contentType.includes("application/json")) payload = await response.json();
  else payload = await response.text();
  const entry = {
    source: "test_probe",
    timestamp: startedAt,
    method,
    path: apiPath,
    status: response.status,
    requestBodySummary: redact(body ?? null),
    responseSummary: redact(payload),
  };
  report.probeLog.push(entry);
  if (!response.ok) throw new Error(`${method} ${apiPath} failed: ${response.status}`);
  return payload;
}

async function waitFor(predicate, timeoutMs, label, intervalMs = 100) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const value = await predicate();
      if (value) return value;
    } catch (error) {
      lastError = error;
    }
    await sleep(intervalMs);
  }
  throw new Error(`Timed out waiting for ${label}${lastError ? `: ${lastError.message}` : ""}`);
}

async function waitForNetworkCall(startIndex, predicate, timeoutMs, label) {
  return waitFor(
    () => report.networkLog.slice(startIndex).find((entry) => predicate(entry)),
    timeoutMs,
    label,
  );
}

async function waitForTaskStatus(taskId, predicate, timeoutMs, label) {
  return waitFor(
    async () => {
      const snapshot = await probe("GET", `/tasks/${taskId}`);
      return predicate(snapshot) ? snapshot : null;
    },
    timeoutMs,
    label,
    300,
  );
}

async function visibleText(page, text, timeout = 1200) {
  try {
    await page.getByText(text, { exact: false }).first().waitFor({ state: "visible", timeout });
    return true;
  } catch {
    return false;
  }
}

async function clickHumanDecision(page, decision, editText = "") {
  const dialog = page.getByRole("dialog", { name: "人工确认" });
  await dialog.waitFor({ state: "visible", timeout: 10000 });
  if (decision === "edit") {
    const textarea = dialog.locator("textarea").first();
    await textarea.fill(editText || "E2E 编辑后通过：保留后端 task 继续执行。");
    await dialog.getByRole("button", { name: "编辑后通过" }).click();
    return;
  }
  if (decision === "reject") {
    await dialog.getByRole("button", { name: "拒绝" }).click();
    return;
  }
  await dialog.getByRole("button", { name: "通过", exact: true }).click();
}

function featureResult(base, checks) {
  const failures = checks.filter((check) => !check.ok);
  return {
    ...base,
    checks,
    status: failures.length ? "FAIL" : "PASS",
    failureReason: failures.map((check) => check.message).join("; ") || "",
    suggestedFix: failures.map((check) => check.fix).filter(Boolean).join(" | ") || "",
  };
}

function callsFor(startIndex, paths) {
  const pathSet = new Set(paths);
  return report.networkLog
    .slice(startIndex)
    .filter((entry) => pathSet.has(entry.path) || pathSet.has(entry.fullPath))
    .map((entry) => ({
      method: entry.method,
      path: entry.path,
      status: entry.status,
      requestBodySummary: entry.requestBodySummary,
      responseSummary: entry.responseSummary,
    }));
}

function isSseConnected(entry) {
  return Boolean(entry && (entry.status === 200 || entry.responseSummary === "text/event-stream"));
}

async function runScenarioTask(page, options) {
  const startIndex = report.networkLog.length;
  await options.button().click();

  const runCall = await waitForNetworkCall(
    startIndex,
    (entry) =>
      entry.method === "POST" &&
      entry.path === "/scenarios/run" &&
      entry.responseSummary?.task_id &&
      entry.requestBodySummary?.scenario === options.scenario,
    20000,
    `${options.featureName} /scenarios/run`,
  );
  const taskId = runCall.responseSummary.task_id;

  const streamCall = await waitForNetworkCall(
    startIndex,
    (entry) => entry.method === "GET" && entry.path === `/tasks/${taskId}/stream`,
    20000,
    `${options.featureName} SSE stream`,
  ).catch(() => null);

  const taskPanelShowsId = await visibleText(page, `task_id: ${taskId}`, 5000);
  const firstTerminalOrAwaiting = await waitForTaskStatus(
    taskId,
    (snapshot) => snapshot.status === "awaiting_human" || terminalStatuses.has(snapshot.status),
    options.awaitTimeoutMs || 90000,
    `${options.featureName} awaiting_human or terminal`,
  );

  let humanGateTriggered = firstTerminalOrAwaiting.status === "awaiting_human";
  let humanModalVisible = false;
  let confirmCall = null;
  let confirmResponseStatus = null;
  let finalSnapshot = firstTerminalOrAwaiting;

  if (humanGateTriggered && options.confirm !== false) {
    humanModalVisible = await visibleText(page, "Human Gate", 10000);
    if (humanModalVisible) {
      const confirmStart = report.networkLog.length;
      await clickHumanDecision(page, options.decision || "approve", options.editText);
      confirmCall = await waitForNetworkCall(
        confirmStart,
        (entry) => entry.method === "POST" && entry.path === `/tasks/${taskId}/confirm`,
        15000,
        `${options.featureName} /confirm`,
      );
    } else if (options.fallbackProbeConfirm !== false) {
      const body = {
        decision: options.decision || "approve",
        edits: options.decision === "edit" ? options.editText || "E2E probe edit" : undefined,
        data: {
          draft: options.editText || "E2E probe confirm because the UI HumanGate modal was not visible.",
        },
      };
      const response = await probe("POST", `/tasks/${taskId}/confirm`, body);
      confirmCall = {
        source: "test_probe",
        method: "POST",
        path: `/tasks/${taskId}/confirm`,
        status: 200,
        requestBodySummary: redact(body),
        responseSummary: redact(response),
      };
    }
    confirmResponseStatus = confirmCall.responseSummary?.status;
    finalSnapshot = await waitForTaskStatus(
      taskId,
      (snapshot) => terminalStatuses.has(snapshot.status),
      options.finalTimeoutMs || 90000,
      `${options.featureName} terminal task status`,
    );
  }

  const featureCalls = callsFor(startIndex, [
    "/scenarios/run",
    `/tasks/${taskId}/stream`,
    `/tasks/${taskId}/confirm`,
  ]);
  if (confirmCall?.source === "test_probe") {
    featureCalls.push({
      method: confirmCall.method,
      path: confirmCall.path,
      status: confirmCall.status,
      requestBodySummary: confirmCall.requestBodySummary,
      responseSummary: confirmCall.responseSummary,
      source: confirmCall.source,
    });
  }

  return {
    startIndex,
    runCall,
    streamCall,
    confirmCall,
    taskId,
    taskPanelShowsId,
    humanGateTriggered,
    humanModalVisible,
    confirmResponseStatus,
    finalSnapshot,
    featureCalls,
    eventCount: finalSnapshot.audit_events?.length ?? 0,
  };
}

function jobRow(page, jobTitle = "VLA / 具身智能算法工程师") {
  return page
    .getByRole("heading", { name: "岗位进展" })
    .locator("..")
    .locator("..")
    .locator("tr", { hasText: jobTitle })
    .first();
}

function candidateRow(page, candidateName = "Alex Chen") {
  return page
    .getByRole("heading", { name: "候选人名单" })
    .locator("..")
    .locator("..")
    .locator("tr", { hasText: candidateName })
    .first();
}

async function collectPageNames(page, names) {
  const results = {};
  for (const name of names) results[name] = await visibleText(page, name, 500);
  return results;
}

async function main() {
  await fs.mkdir(path.join(artifactDir, "screenshots"), { recursive: true });
  await fs.mkdir(path.join(artifactDir, "videos"), { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    baseURL: baseUrl,
    viewport: { width: 1440, height: 1100 },
    recordVideo: { dir: path.join(artifactDir, "videos"), size: { width: 1440, height: 1100 } },
  });
  await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
  const page = await context.newPage();
  attachNetwork(page, "main");

  try {
    const loadStart = report.networkLog.length;
    await page.goto(`/projects/${projectId}`, { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "2026 AI 团队招聘" }).waitFor({ timeout: 20000 });
    const projectCall = await waitForNetworkCall(loadStart, (e) => e.method === "GET" && e.path === `/projects/${projectId}` && e.status, 10000, "project load");
    const jobsCall = await waitForNetworkCall(loadStart, (e) => e.method === "GET" && e.path === `/projects/${projectId}/jobs` && e.status, 10000, "jobs load");
    const candidatesCall = await waitForNetworkCall(loadStart, (e) => e.method === "GET" && e.path.startsWith(`/projects/${projectId}/candidates`) && e.status, 10000, "candidates load");
    const integrationsCall = await waitForNetworkCall(loadStart, (e) => e.method === "GET" && e.path === "/integrations/status" && e.status, 10000, "integrations load");
    const backendCandidateNames = (candidatesCall.responseSummary?.sample || []).map((item) => item.name).filter(Boolean);
    const visibleNames = await collectPageNames(page, ["Alex Chen", "Zhou Han", "Maya Li", "Wang Ke", "Sara Qi", "Lin Chen"]);
    report.features.push(
      featureResult(
        {
          featureName: "页面加载",
          userEntry: `/projects/${projectId}`,
          clickAction: "打开项目详情页",
          expectedApi: [
            `GET /api/projects/${projectId}`,
            `GET /api/projects/${projectId}/jobs`,
            `GET /api/projects/${projectId}/candidates`,
            "GET /api/integrations/status",
          ],
          actualApis: callsFor(loadStart, [
            `/projects/${projectId}`,
            `/projects/${projectId}/jobs`,
            `/projects/${projectId}/candidates?skip=0&limit=50`,
            "/integrations/status",
          ]),
          task_id: null,
          sseConnected: false,
          eventCount: 0,
          finalTaskStatus: null,
          humanGateTriggered: false,
          pageFinalState: "项目、岗位、候选人列表已渲染",
          fakeDataOrSuccess: visibleNames["Lin Chen"] ? "页面出现非 seed 的 Lin Chen" : "未发现 mock-only 候选人名",
        },
        [
          { ok: projectCall.status === 200, message: `项目接口状态 ${projectCall.status}`, fix: "检查 /projects/{id} API 或前端 projectId。" },
          { ok: jobsCall.status === 200, message: `岗位接口状态 ${jobsCall.status}`, fix: "检查 /projects/{id}/jobs API。" },
          { ok: candidatesCall.status === 200, message: `候选人接口状态 ${candidatesCall.status}`, fix: "检查 /projects/{id}/candidates API。" },
          { ok: integrationsCall.status === 200, message: `能力接口状态 ${integrationsCall.status}`, fix: "检查 /integrations/status API。" },
          { ok: visibleNames["Alex Chen"] && visibleNames["Zhou Han"] && visibleNames["Maya Li"], message: "页面未展示 seed 候选人", fix: "确认 CandidateTable 使用后端响应而不是空态/假数据。" },
          { ok: !visibleNames["Lin Chen"], message: "页面展示了 mock-only 候选人 Lin Chen", fix: "移除 projectMock 在项目详情页的数据回退。" },
          { ok: backendCandidateNames.includes("Alex Chen"), message: "候选人响应摘要未包含真实 seed 候选人", fix: "检查后端 seed 或响应映射。" },
        ],
      ),
    );

    const a = await runScenarioTask(page, {
      featureName: "岗位分析 A",
      scenario: "A",
      button: () => jobRow(page).getByRole("button", { name: "岗位分析" }),
      decision: "approve",
    });
    report.features.push(
      featureResult(
        {
          featureName: "岗位分析 A",
          userEntry: "岗位进展表 / VLA 岗位 / 岗位分析",
          clickAction: "点击“岗位分析”并在 HumanGate 点击“通过”",
          expectedApi: ["POST /api/scenarios/run scenario=A", `GET /api/tasks/{taskId}/stream`, "POST /api/tasks/{taskId}/confirm"],
          actualApis: a.featureCalls,
          requestBodySummary: a.runCall.requestBodySummary,
          responseSummary: a.runCall.responseSummary,
          task_id: a.taskId,
          sseConnected: isSseConnected(a.streamCall),
          eventCount: a.eventCount,
          finalTaskStatus: a.finalSnapshot.status,
          humanGateTriggered: a.humanGateTriggered,
          pageFinalState: `任务面板 task_id 可见=${a.taskPanelShowsId}; final=${a.finalSnapshot.status}`,
          fakeDataOrSuccess: "未发现前端本地伪造 task_id/done，终态来自 GET /tasks probe 与 SSE 事件",
        },
        [
          { ok: a.runCall.requestBodySummary?.scenario === "A", message: "scenario 不是 A", fix: "检查 runProjectScenario 的 scenarioForAction 映射。" },
          { ok: Boolean(a.taskId), message: "未返回 task_id", fix: "检查 /scenarios/run 返回结构。" },
          { ok: isSseConnected(a.streamCall), message: "未连接 SSE stream", fix: "检查 useTaskStream(activeTaskId) 和 taskStreamUrl。" },
          { ok: a.taskPanelShowsId, message: "任务面板未显示真实 task_id", fix: "LiveTaskSummary 需要渲染后端 task_id。" },
          { ok: a.humanGateTriggered && a.humanModalVisible, message: "未触发或未显示 HumanGate", fix: "检查后端 hitl step 和 humanGateRequestFromEvent。" },
          { ok: a.confirmCall?.status === 200, message: "HumanGate confirm 未成功", fix: "检查 POST /tasks/{taskId}/confirm。" },
          { ok: a.finalSnapshot.status === "done", message: `最终状态 ${a.finalSnapshot.status}`, fix: "检查 A 场景 runner 或外部检索错误。" },
        ],
      ),
    );

    const b = await runScenarioTask(page, {
      featureName: "找候选人 B",
      scenario: "B",
      button: () => jobRow(page).getByRole("button", { name: "找候选人" }),
      decision: "approve",
    });
    const postBNames = await collectPageNames(page, ["Alex Chen", "Zhou Han", "Maya Li", "Wang Ke", "Sara Qi", "Generated Candidate"]);
    report.features.push(
      featureResult(
        {
          featureName: "找候选人 B",
          userEntry: "岗位进展表 / VLA 岗位 / 找候选人",
          clickAction: "点击“找候选人”并在 HumanGate 点击“通过”",
          expectedApi: ["POST /api/scenarios/run scenario=B", `GET /api/tasks/{taskId}/stream`, "POST /api/tasks/{taskId}/confirm"],
          actualApis: b.featureCalls,
          requestBodySummary: b.runCall.requestBodySummary,
          responseSummary: b.runCall.responseSummary,
          task_id: b.taskId,
          sseConnected: isSseConnected(b.streamCall),
          eventCount: b.eventCount,
          finalTaskStatus: b.finalSnapshot.status,
          humanGateTriggered: b.humanGateTriggered,
          pageFinalState: `候选人列表仍显示 seed 候选人；final=${b.finalSnapshot.status}`,
          fakeDataOrSuccess: postBNames["Generated Candidate"] ? "出现 Generated Candidate" : "未发现前端生成假候选人",
        },
        [
          { ok: b.runCall.requestBodySummary?.scenario === "B", message: "scenario 不是 B", fix: "检查 find_candidates action 映射。" },
          { ok: Boolean(b.taskId), message: "未返回 task_id", fix: "检查 /scenarios/run 返回结构。" },
          { ok: isSseConnected(b.streamCall), message: "未连接 SSE stream", fix: "检查 useTaskStream。" },
          { ok: b.finalSnapshot.status === "done", message: `最终状态 ${b.finalSnapshot.status}`, fix: "检查 B 场景 runner。" },
          { ok: !postBNames["Generated Candidate"], message: "候选人列表出现非后端 seed 名称", fix: "禁止前端用本地 mock 追加候选人。" },
        ],
      ),
    );

    const c = await runScenarioTask(page, {
      featureName: "候选人评估 C",
      scenario: "C",
      button: () => candidateRow(page, "Alex Chen").getByRole("button", { name: "候选人评估" }),
      decision: "approve",
      finalTimeoutMs: 30000,
    });
    const candidateIds = (candidatesCall.responseSummary?.sample || []).map((item) => item.id);
    const cCandidateId = c.runCall.requestBodySummary?.frontend_state?.candidate_id;
    report.features.push(
      featureResult(
        {
          featureName: "候选人评估 C",
          userEntry: "候选人名单 / Alex Chen / 候选人评估",
          clickAction: "点击“候选人评估”并在 HumanGate 点击“通过”",
          expectedApi: ["POST /api/scenarios/run scenario=C with backend candidate_id", `GET /api/tasks/{taskId}/stream`, "POST /api/tasks/{taskId}/confirm"],
          actualApis: c.featureCalls,
          requestBodySummary: c.runCall.requestBodySummary,
          responseSummary: c.runCall.responseSummary,
          task_id: c.taskId,
          sseConnected: isSseConnected(c.streamCall),
          eventCount: c.eventCount,
          finalTaskStatus: c.finalSnapshot.status,
          humanGateTriggered: c.humanGateTriggered,
          pageFinalState: `final=${c.finalSnapshot.status}; database_update=${JSON.stringify(c.finalSnapshot.result?.database_update || null)}`,
          fakeDataOrSuccess: "评分/状态来自 task result.database_update 与后端刷新，不是前端生成评分",
        },
        [
          { ok: c.runCall.requestBodySummary?.scenario === "C", message: "scenario 不是 C", fix: "检查 runCandidateEvaluation。" },
          { ok: candidateIds.includes(cCandidateId), message: `candidate_id ${cCandidateId} 不在后端候选人响应中`, fix: "候选人评估必须使用后端 candidate_id。" },
          { ok: isSseConnected(c.streamCall), message: "未连接 SSE stream", fix: "检查 useTaskStream。" },
          { ok: c.humanGateTriggered && c.humanModalVisible, message: "C 未触发 HumanGate", fix: "检查 ProjectCandidateEvaluationRunner.set_awaiting。" },
          { ok: c.finalSnapshot.result?.database_update?.candidate_id === cCandidateId, message: "最终结果未包含同一 candidate_id 的 database_update", fix: "后端评估结果必须回写并暴露真实更新。" },
          { ok: c.finalSnapshot.status === "done", message: `最终状态 ${c.finalSnapshot.status}`, fix: "检查 C 场景 confirm 后续执行。" },
        ],
      ),
    );

    const d = await runScenarioTask(page, {
      featureName: "招聘周报 D",
      scenario: "D",
      button: () => page.getByRole("button", { name: "生成周报" }).first(),
      decision: "approve",
    });
    const weeklyEmptyVisible = await visibleText(page, "暂无周报，运行招聘周报后生成", 2000);
    const weeklyResultHasChineseReport = Boolean(d.finalSnapshot.result?.["本周招聘结论"]);
    const englishConclusion = d.finalSnapshot.result?.conclusion;
    const weeklyEnglishDisplayed = englishConclusion ? await visibleText(page, String(englishConclusion), 500) : false;
    report.features.push(
      featureResult(
        {
          featureName: "招聘周报 D",
          userEntry: "项目详情页顶部 / 生成周报",
          clickAction: "点击“生成周报”并在 HumanGate 点击“通过”",
          expectedApi: ["POST /api/scenarios/run scenario=D", `GET /api/tasks/{taskId}/stream`, "POST /api/tasks/{taskId}/confirm", "POST /api/reports/weekly only when task result is parseable"],
          actualApis: d.featureCalls.concat(callsFor(d.startIndex, ["/reports/weekly"])),
          requestBodySummary: d.runCall.requestBodySummary,
          responseSummary: d.runCall.responseSummary,
          task_id: d.taskId,
          sseConnected: isSseConnected(d.streamCall),
          eventCount: d.eventCount,
          finalTaskStatus: d.finalSnapshot.status,
          humanGateTriggered: d.humanGateTriggered,
          pageFinalState: weeklyEmptyVisible ? "周报卡片仍为空态" : "周报卡片显示内容",
          fakeDataOrSuccess: weeklyEmptyVisible ? "未显示假周报；但未消费中文 task result" : "周报显示来自可解析 task result/后端保存结果",
        },
        [
          { ok: d.runCall.requestBodySummary?.scenario === "D", message: "scenario 不是 D", fix: "检查 runWeeklyReport。" },
          { ok: isSseConnected(d.streamCall), message: "未连接 SSE stream", fix: "检查 useTaskStream。" },
          { ok: d.finalSnapshot.status === "done", message: `最终状态 ${d.finalSnapshot.status}`, fix: "检查 D 场景 runner。" },
          {
            ok: !weeklyResultHasChineseReport || !weeklyEmptyVisible || weeklyEnglishDisplayed,
            message: "task result 有周报内容但 UI 仍显示空态",
            fix: "weeklyReportFromTaskResult 需要支持后端中文键：本周招聘结论/关键岗位进展/Top 候选人/招聘风险/下周行动建议，或后端返回英文 report schema。",
          },
        ],
      ),
    );

    const humanGateStart = report.networkLog.length;
    const editTask = await runScenarioTask(page, {
      featureName: "HumanGate edit",
      scenario: "C",
      button: () => candidateRow(page, "Zhou Han").getByRole("button", { name: "候选人评估" }),
      decision: "edit",
      editText: "E2E 编辑意见：补充人工校准，但等待后端继续。",
      finalTimeoutMs: 30000,
    });
    const rejectTask = await runScenarioTask(page, {
      featureName: "HumanGate reject",
      scenario: "C",
      button: () => candidateRow(page, "Maya Li").getByRole("button", { name: "候选人评估" }),
      decision: "reject",
      finalTimeoutMs: 30000,
    });
    const humanConfirmCalls = report.networkLog
      .slice(humanGateStart)
      .filter((entry) => entry.method === "POST" && entry.path.endsWith("/confirm"));
    const humanDecisions = new Set([c.confirmCall, editTask.confirmCall, rejectTask.confirmCall].map((entry) => entry?.requestBodySummary?.decision));
    report.features.push(
      featureResult(
        {
          featureName: "HumanGate",
          userEntry: "候选人评估任务的人工确认弹窗",
          clickAction: "分别点击“通过 / 编辑后通过 / 拒绝”",
          expectedApi: ["POST /api/tasks/{taskId}/confirm decision=approve|edit|reject"],
          actualApis: [c.confirmCall, editTask.confirmCall, rejectTask.confirmCall].filter(Boolean).map((entry) => ({
            method: entry.method,
            path: entry.path,
            status: entry.status,
            requestBodySummary: entry.requestBodySummary,
            responseSummary: entry.responseSummary,
          })),
          task_id: [c.taskId, editTask.taskId, rejectTask.taskId].join(", "),
          sseConnected: isSseConnected(c.streamCall) && isSseConnected(editTask.streamCall) && isSseConnected(rejectTask.streamCall),
          eventCount: c.eventCount + editTask.eventCount + rejectTask.eventCount,
          finalTaskStatus: [c.finalSnapshot.status, editTask.finalSnapshot.status, rejectTask.finalSnapshot.status].join(", "),
          humanGateTriggered: c.humanGateTriggered && editTask.humanGateTriggered && rejectTask.humanGateTriggered,
          pageFinalState: "三种人工决策均通过弹窗提交到后端 confirm",
          fakeDataOrSuccess: [c.confirmResponseStatus, editTask.confirmResponseStatus, rejectTask.confirmResponseStatus].every((status) => status !== "done")
            ? "confirm 响应未直接伪造 done，终态等待后端 task snapshot"
            : "confirm 响应已是 done，需核查是否本地伪造终态",
        },
        [
          { ok: humanDecisions.has("approve"), message: "未捕获 approve confirm", fix: "检查 HumanConfirmModal 通过按钮。" },
          { ok: humanDecisions.has("edit"), message: "未捕获 edit confirm", fix: "检查 HumanConfirmModal 编辑后通过按钮。" },
          { ok: humanDecisions.has("reject"), message: "未捕获 reject confirm", fix: "检查 HumanConfirmModal 拒绝按钮。" },
          { ok: humanConfirmCalls.length >= 2, message: "HumanGate 专项 confirm 调用数量不足", fix: "确认每个决策都调用 /tasks/{taskId}/confirm。" },
          { ok: [c.confirmResponseStatus, editTask.confirmResponseStatus, rejectTask.confirmResponseStatus].every((status) => status !== "done"), message: "confirm 后立即显示 done", fix: "confirm 只应提交决策，终态应由后端 runner/SSE 决定。" },
        ],
      ),
    );

    const emailStart = report.networkLog.length;
    await candidateRow(page, "Alex Chen").getByRole("button", { name: "生成草稿" }).click();
    const draftCall = await waitForNetworkCall(emailStart, (e) => e.method === "POST" && e.path === "/outreach/draft" && e.status, 10000, "outreach draft");
    const backendGeneratedText = await visibleText(page, "后端生成", 5000);
    const frontendAssistedText = await visibleText(page, "前端辅助生成", 1000);
    await page.getByRole("button", { name: "确认草稿" }).click();
    await clickHumanDecision(page, "approve");
    const patchCall = await waitForNetworkCall(emailStart, (e) => e.method === "PATCH" && e.path.startsWith("/outreach/drafts/") && e.status, 10000, "outreach draft patch");
    const sendCall = await waitForNetworkCall(emailStart, (e) => e.method === "POST" && e.path === "/outreach/send" && e.status, 10000, "outreach simulated send");
    const confirmedUnsentText = await visibleText(page, "草稿已确认，未发送", 3000);
    const simulatedText = await visibleText(page, "已记录模拟触达", 3000);
    const sendSuccessText = await visibleText(page, "发送成功", 800);
    const noEmailButtonDisabled = await candidateRow(page, "Maya Li").getByRole("button", { name: "生成草稿" }).isDisabled();
    report.features.push(
      featureResult(
        {
          featureName: "邮件草稿",
          userEntry: "候选人名单 / 有邮箱候选人 / 生成草稿",
          clickAction: "点击“生成草稿” -> “确认草稿” -> HumanGate “通过”；检查无邮箱候选人按钮",
          expectedApi: ["POST /api/outreach/draft", "PATCH /api/outreach/drafts/{draftId}", "POST /api/outreach/send simulate=true"],
          actualApis: callsFor(emailStart, ["/outreach/draft", patchCall.path, "/outreach/send", "/outreach/history?projectId=project_2026_ai_team&candidateId=cand_lin_chen"]),
          requestBodySummary: draftCall.requestBodySummary,
          responseSummary: draftCall.responseSummary,
          task_id: null,
          sseConnected: false,
          eventCount: 0,
          finalTaskStatus: null,
          humanGateTriggered: true,
          pageFinalState: `badge=${backendGeneratedText ? "后端生成" : "未知"}; toast=${simulatedText ? "已记录模拟发送，未真实发送" : "未捕获"}`,
          fakeDataOrSuccess: frontendAssistedText
            ? "出现前端辅助生成文案，需核查是否仍有本地草稿回退"
            : "草稿来自后端；未显示发送成功；send simulate=true",
        },
        [
          { ok: draftCall.status === 200 && draftCall.responseSummary?.backendGenerated === true, message: "草稿不是后端生成", fix: "检查 /outreach/draft 返回 backendGenerated。" },
          { ok: !frontendAssistedText, message: "仍显示“前端辅助生成”", fix: "当前验收要求草稿由后端生成，前端不应声明本地辅助生成。" },
          { ok: patchCall.status === 200, message: "确认前 PATCH 草稿失败", fix: "检查 updateOutreachDraft。" },
          { ok: sendCall.status === 200 && sendCall.requestBodySummary?.simulate === true, message: "确认后未以 simulate=true 写入触达历史", fix: "真实发送未接入时只能模拟记录。" },
          { ok: confirmedUnsentText, message: "未显示“草稿已确认，未发送”", fix: "确认成功 toast/历史文案应避免“模拟发送”被误解为发送闭环。" },
          { ok: !sendSuccessText, message: "页面显示发送成功", fix: "真实邮件 provider 未接入时禁止发送成功文案。" },
          { ok: noEmailButtonDisabled, message: "无邮箱候选人的生成草稿按钮未 disabled", fix: "CandidateTable 应根据 candidate.email 禁用按钮。" },
        ],
      ),
    );

    const segmentStart = report.networkLog.length;
    await page.locator("label", { hasText: "匹配分" }).locator("select").selectOption("90");
    await page.getByRole("button", { name: "查询目标人群" }).click();
    const segmentQueryCall = await waitForNetworkCall(segmentStart, (e) => e.method === "POST" && e.path === "/segments/query" && e.status, 10000, "segments query");
    const segmentTotal = segmentQueryCall.responseSummary?.total;
    const segmentCandidateSummary = segmentQueryCall.responseSummary?.candidates;
    const segmentCandidateSamples = segmentCandidateSummary?.sample || [];
    const seedCandidateIds = new Set(["cand_lin_chen", "cand_zhou_han", "cand_maya_li", "cand_wang_ke", "cand_sara_qi"]);
    const segmentHitText = await visibleText(page, `后端筛选命中 ${segmentTotal} 人`, 5000);
    const savedBackendGroupText = await visibleText(page, "已保存后端分群", 800);
    report.features.push(
      featureResult(
        {
          featureName: "人群筛选",
          userEntry: "筛选条件面板",
          clickAction: "设置匹配分 90 分以上，点击“查询目标人群”",
          expectedApi: ["POST /api/segments/query with criteria"],
          actualApis: callsFor(segmentStart, ["/segments/query"]),
          requestBodySummary: segmentQueryCall.requestBodySummary,
          responseSummary: segmentQueryCall.responseSummary,
          task_id: null,
          sseConnected: false,
          eventCount: 0,
          finalTaskStatus: null,
          humanGateTriggered: false,
          pageFinalState: segmentHitText ? `后端筛选命中 ${segmentTotal} 人，尚未保存` : "未捕获筛选命中文案",
          fakeDataOrSuccess: savedBackendGroupText ? "出现已保存后端分群" : "未显示已保存后端分群",
        },
        [
          { ok: segmentQueryCall.status === 200, message: `segments/query 状态 ${segmentQueryCall.status}`, fix: "检查 /segments/query。" },
          { ok: typeof segmentTotal === "number" && segmentTotal === segmentCandidateSummary?.length, message: `筛选结果 total=${segmentTotal}, candidates.length=${segmentCandidateSummary?.length}`, fix: "确认 SegmentQueryResponse total 与 candidates 数量一致。" },
          { ok: segmentCandidateSamples.every((candidate) => seedCandidateIds.has(candidate.id)), message: "筛选结果包含非 seed 后端候选人", fix: "检查 SegmentCriteria 映射和 CandidateResponse map，禁止前端追加假候选人。" },
          { ok: !savedBackendGroupText, message: "预览后显示了已保存后端分群", fix: "预览动作不应声明保存成功。" },
        ],
      ),
    );

    const fallbackFeature = await runFallbackScenario(browser);
    report.features.push(fallbackFeature);

    const errorFeature = await runErrorStateScenario(browser);
    report.features.push(errorFeature);
  } catch (error) {
    const screenshotPath = path.join(artifactDir, "screenshots", "runner-exception.png");
    await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => null);
    report.features.push(
      featureResult(
        {
          featureName: "Runner exception",
          userEntry: "E2E runner",
          clickAction: "N/A",
          expectedApi: [],
          actualApis: [],
          task_id: null,
          sseConnected: false,
          eventCount: 0,
          finalTaskStatus: null,
          humanGateTriggered: false,
          pageFinalState: "脚本异常终止",
          fakeDataOrSuccess: "未完成",
        },
        [{ ok: false, message: error instanceof Error ? error.stack || error.message : String(error), fix: "先修复 runner 捕获的阻断问题后重跑。" }],
      ),
    );
  } finally {
    const tracePath = path.join(artifactDir, "trace.zip");
    await context.tracing.stop({ path: tracePath }).catch(() => null);
    report.artifacts.trace = tracePath;
    const videoPath = await page.video()?.path().catch(() => null);
    if (videoPath) report.artifacts.video = videoPath;
    await page.screenshot({ path: path.join(artifactDir, "screenshots", "final-main.png"), fullPage: true }).catch(() => null);
    await context.close().catch(() => null);
    await browser.close().catch(() => null);
  }

  report.run.finishedAt = new Date().toISOString();
  report.summary = report.features.map((feature) => ({
    feature: feature.featureName,
    status: feature.status,
    api: (feature.actualApis || []).map((api) => `${api.method} ${api.path} ${api.status}`).join("; "),
    task: feature.task_id || "—",
    sse: feature.sseConnected ? "yes" : "no",
    humanGate: feature.humanGateTriggered ? "yes" : "no",
    conclusion: feature.status === "PASS" ? "PASS" : feature.failureReason,
  }));

  await fs.writeFile(path.join(artifactDir, "network-log.json"), JSON.stringify(report.networkLog, null, 2));
  await fs.writeFile(path.join(artifactDir, "probe-log.json"), JSON.stringify(report.probeLog, null, 2));
  await fs.writeFile(path.join(artifactDir, "e2e-report.json"), JSON.stringify(report, null, 2));
  await fs.writeFile(path.join(artifactDir, "e2e-report.md"), renderMarkdown(report));

  const failCount = report.features.filter((feature) => feature.status !== "PASS").length;
  console.log(`E2E evidence report written to ${path.join(artifactDir, "e2e-report.md")}`);
  console.log(`PASS=${report.features.length - failCount} FAIL=${failCount}`);
  if (failCount) process.exitCode = 1;
}

async function runFallbackScenario(browser) {
  const context = await browser.newContext({
    baseURL: baseUrl,
    viewport: { width: 1280, height: 900 },
    recordVideo: { dir: path.join(artifactDir, "videos"), size: { width: 1280, height: 900 } },
  });
  await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
  await context.addInitScript(() => {
    window.__e2eEventSourceUrls = [];
    const realSetTimeout = window.setTimeout.bind(window);
    window.setTimeout = (callback, delay, ...args) => realSetTimeout(callback, Math.min(Number(delay) || 0, 20), ...args);
    class FailingEventSource {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;
      constructor(url) {
        this.url = url;
        this.readyState = FailingEventSource.CONNECTING;
        this.listeners = new Map();
        window.__e2eEventSourceUrls.push(url);
        realSetTimeout(() => {
          if (this.readyState === FailingEventSource.CLOSED) return;
          this.onerror?.(new Event("error"));
        }, 0);
      }
      addEventListener(type, listener) {
        this.listeners.set(type, listener);
      }
      close() {
        this.readyState = FailingEventSource.CLOSED;
      }
    }
    window.EventSource = FailingEventSource;
  });
  const page = await context.newPage();
  attachNetwork(page, "fallback");
  let result;
  try {
    const startIndex = report.networkLog.length;
    await page.goto(`/projects/${projectId}`, { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "2026 AI 团队招聘" }).waitFor({ timeout: 20000 });
    const task = await runScenarioTask(page, {
      featureName: "SSE fallback",
      scenario: "C",
      button: () => candidateRow(page, "Alex Chen").getByRole("button", { name: "候选人评估" }),
      decision: "approve",
      finalTimeoutMs: 30000,
    });
    const constructedUrls = await page.evaluate(() => window.__e2eEventSourceUrls || []);
    report.eventSourceLog.push(...constructedUrls.map((url) => ({ source: "fallback", url })));
    const taskGetCallsBeforeDone = report.networkLog
      .slice(startIndex)
      .filter((entry) => entry.method === "GET" && entry.path === `/tasks/${task.taskId}`);
    await page.getByText("fallback polling: yes").waitFor({ state: "visible", timeout: 10000 }).catch(() => null);
    const countAtDone = report.networkLog.filter((entry) => entry.method === "GET" && entry.path === `/tasks/${task.taskId}`).length;
    await sleep(800);
    const countAfterWait = report.networkLog.filter((entry) => entry.method === "GET" && entry.path === `/tasks/${task.taskId}`).length;
    result = featureResult(
      {
        featureName: "SSE fallback",
        userEntry: "候选人评估任务，init script 模拟 EventSource 失败",
        clickAction: "点击“候选人评估”，EventSource 连续失败后通过轮询完成任务",
        expectedApi: ["EventSource /api/tasks/{taskId}/stream fails/retries", "fallback GET /api/tasks/{taskId}", "terminal 后停止轮询"],
        actualApis: task.featureCalls.concat(
          report.networkLog
            .slice(startIndex)
            .filter((entry) => entry.path === `/tasks/${task.taskId}`)
            .map((entry) => ({ method: entry.method, path: entry.path, status: entry.status, requestBodySummary: entry.requestBodySummary, responseSummary: entry.responseSummary })),
        ),
        task_id: task.taskId,
        sseConnected: false,
        eventCount: task.eventCount,
        finalTaskStatus: task.finalSnapshot.status,
        humanGateTriggered: task.humanGateTriggered,
        pageFinalState: `constructed EventSource=${constructedUrls.length}; GET polls=${taskGetCallsBeforeDone.length}; countAtDone=${countAtDone}; countAfterWait=${countAfterWait}`,
        fakeDataOrSuccess: "终态来自 fallback GET /tasks snapshot，不是本地伪造 done",
      },
      [
        { ok: constructedUrls.some((url) => String(url).includes(`/api/tasks/${task.taskId}/stream`)), message: "未构造 EventSource stream URL", fix: "检查 taskStreamUrl/useTaskStream。" },
        { ok: taskGetCallsBeforeDone.length >= 2, message: "未观察到 fallback 轮询 GET /tasks/{taskId}", fix: "降低重试等待或检查 useTaskStream fallback polling。" },
        { ok: task.finalSnapshot.status === "done", message: `fallback 后最终状态 ${task.finalSnapshot.status}`, fix: "fallback polling 需持续到终态。" },
        { ok: countAfterWait === countAtDone, message: "终态后仍在轮询", fix: "useTaskStream stopForTerminal 后必须 clearPollingTimer。" },
      ],
    );
  } catch (error) {
    await page.screenshot({ path: path.join(artifactDir, "screenshots", "fallback-failure.png"), fullPage: true }).catch(() => null);
    result = featureResult(
      {
        featureName: "SSE fallback",
        userEntry: "候选人评估任务，init script 模拟 EventSource 失败",
        clickAction: "点击“候选人评估”",
        expectedApi: ["fallback GET /api/tasks/{taskId}"],
        actualApis: [],
        task_id: null,
        sseConnected: false,
        eventCount: 0,
        finalTaskStatus: null,
        humanGateTriggered: false,
        pageFinalState: "fallback 场景异常",
        fakeDataOrSuccess: "未完成",
      },
      [{ ok: false, message: error instanceof Error ? error.message : String(error), fix: "检查 fallback 场景或 useTaskStream。" }],
    );
  } finally {
    const tracePath = path.join(artifactDir, "fallback-trace.zip");
    await context.tracing.stop({ path: tracePath }).catch(() => null);
    const videoPath = await page.video()?.path().catch(() => null);
    if (videoPath) report.artifacts.fallbackVideo = videoPath;
    report.artifacts.fallbackTrace = tracePath;
    await context.close().catch(() => null);
  }
  return result;
}

async function runErrorStateScenario(browser) {
  const context = await browser.newContext({ baseURL: baseUrl, viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  attachNetwork(page, "error-state");
  let result;
  try {
    const startIndex = report.networkLog.length;
    await page.route("**/api/projects/**", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "E2E bad API simulation" }),
      });
    });
    await page.goto(`/projects/${projectId}`, { waitUntil: "domcontentloaded" });
    await page.getByText("E2E bad API simulation").waitFor({ timeout: 15000 });
    const noProject = !(await visibleText(page, "2026 AI 团队招聘", 1000));
    const noCandidates = !(await visibleText(page, "Alex Chen", 1000));
    result = featureResult(
      {
        featureName: "错误态",
        userEntry: `/projects/${projectId} with bad API route`,
        clickAction: "刷新项目页，拦截 /api/projects/** 返回 503",
        expectedApi: [`GET /api/projects/${projectId} 503`, "页面错误态", "不显示假项目/岗位/候选人"],
        actualApis: report.networkLog
          .slice(startIndex)
          .filter((entry) => entry.path.startsWith(`/projects/${projectId}`))
          .map((entry) => ({ method: entry.method, path: entry.path, status: entry.status, requestBodySummary: entry.requestBodySummary, responseSummary: entry.responseSummary })),
        task_id: null,
        sseConnected: false,
        eventCount: 0,
        finalTaskStatus: null,
        humanGateTriggered: false,
        pageFinalState: "显示后端错误态",
        fakeDataOrSuccess: noProject && noCandidates ? "未显示假项目/岗位/候选人" : "错误态下仍有项目或候选人内容",
      },
      [
        { ok: noProject, message: "错误态仍显示项目名称", fix: "加载失败时不要回退 projectMock。" },
        { ok: noCandidates, message: "错误态仍显示候选人", fix: "加载失败时不要回退 mock candidates。" },
        { ok: await visibleText(page, "E2E bad API simulation", 1000), message: "未显示后端错误信息", fix: "ProjectDetailPage 应显示 loadError。" },
      ],
    );
  } catch (error) {
    await page.screenshot({ path: path.join(artifactDir, "screenshots", "error-state-failure.png"), fullPage: true }).catch(() => null);
    result = featureResult(
      {
        featureName: "错误态",
        userEntry: `/projects/${projectId}`,
        clickAction: "拦截坏 API",
        expectedApi: ["错误态"],
        actualApis: [],
        task_id: null,
        sseConnected: false,
        eventCount: 0,
        finalTaskStatus: null,
        humanGateTriggered: false,
        pageFinalState: "错误态场景异常",
        fakeDataOrSuccess: "未完成",
      },
      [{ ok: false, message: error instanceof Error ? error.message : String(error), fix: "检查错误态测试或页面错误处理。" }],
    );
  } finally {
    await context.close().catch(() => null);
  }
  return result;
}

function renderMarkdown(data) {
  const lines = [];
  lines.push("# Zhaoping E2E API Evidence Report");
  lines.push("");
  lines.push(`- Started: ${data.run.startedAt}`);
  lines.push(`- Finished: ${data.run.finishedAt}`);
  lines.push(`- Base URL: ${data.run.baseUrl}`);
  lines.push(`- Project: ${data.run.projectId}`);
  lines.push(`- Seed: ${data.run.seed.jobs} jobs / ${data.run.seed.candidates} candidates / ${data.run.seed.matches} matches`);
  lines.push("");
  lines.push("## Summary");
  lines.push("");
  lines.push("| 功能 | 状态 | 接口 | task | SSE | HumanGate | 结论 |");
  lines.push("| --- | --- | --- | --- | --- | --- | --- |");
  for (const item of data.summary) {
    lines.push(
      `| ${item.feature} | ${item.status} | ${String(item.api || "—").replaceAll("|", "\\|")} | ${String(item.task).replaceAll("|", "\\|")} | ${item.sse} | ${item.humanGate} | ${String(item.conclusion || "—").replaceAll("|", "\\|")} |`,
    );
  }
  lines.push("");
  lines.push("## Feature Details");
  for (const feature of data.features) {
    lines.push("");
    lines.push(`### ${feature.featureName} - ${feature.status}`);
    lines.push("");
    lines.push(`- 用户入口: ${feature.userEntry}`);
    lines.push(`- 点击动作: ${feature.clickAction}`);
    lines.push(`- 期望 API: ${(feature.expectedApi || []).join("; ") || "—"}`);
    lines.push(`- 实际 API: ${(feature.actualApis || []).map((api) => `${api.method} ${api.path} ${api.status}`).join("; ") || "—"}`);
    lines.push(`- request body 摘要: ${JSON.stringify(feature.requestBodySummary ?? null)}`);
    lines.push(`- response 摘要: ${JSON.stringify(feature.responseSummary ?? null)}`);
    lines.push(`- task_id: ${feature.task_id ?? "—"}`);
    lines.push(`- SSE 是否连接: ${feature.sseConnected ? "yes" : "no"}`);
    lines.push(`- event count: ${feature.eventCount}`);
    lines.push(`- final task status: ${feature.finalTaskStatus ?? "—"}`);
    lines.push(`- 是否触发 HumanGate: ${feature.humanGateTriggered ? "yes" : "no"}`);
    lines.push(`- 页面最终状态: ${feature.pageFinalState}`);
    lines.push(`- 是否存在假数据/假成功: ${feature.fakeDataOrSuccess}`);
    lines.push(`- 失败原因: ${feature.failureReason || "—"}`);
    lines.push(`- 建议修复点: ${feature.suggestedFix || "—"}`);
  }
  lines.push("");
  lines.push("## Artifacts");
  lines.push("");
  for (const [key, value] of Object.entries(data.artifacts)) lines.push(`- ${key}: ${value}`);
  lines.push(`- network log: ${path.join(artifactDir, "network-log.json")}`);
  lines.push(`- probe log: ${path.join(artifactDir, "probe-log.json")}`);
  return `${lines.join("\n")}\n`;
}

main();
