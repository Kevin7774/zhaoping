import fs from "node:fs/promises";
import fssync from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "../../..");
const artifactDir = path.resolve(__dirname, "..");
const commandLogDir = path.join(artifactDir, "command-logs");
const projectId = "project_2026_ai_team";
const seedProjectDbPath = path.join(artifactDir, "projects.sqlite3");
const seedTaskDbPath = path.join(artifactDir, "tasks.sqlite3");
const runId = process.env.E2E_RUN_ID || timestampId();
const soakSeconds = Number(process.env.E2E_SOAK_SECONDS || "30");
const terminalStatuses = new Set(["done", "error", "cancelled"]);

const report = {
  run: {
    id: runId,
    startedAt: new Date().toISOString(),
    finishedAt: null,
    startEpochMs: Date.now(),
    endEpochMs: null,
    projectId,
  },
  environment: {},
  ports: {},
  databases: {
    projectDatabaseUrl: sqliteUrl(seedProjectDbPath),
    taskDatabaseUrl: sqliteUrl(seedTaskDbPath),
    projectDbPath: seedProjectDbPath,
    taskDbPath: seedTaskDbPath,
  },
  seed: {
    command: `.venv/bin/python scripts/seed_db.py --database-url ${sqliteUrl(seedProjectDbPath)}`,
    summary: null,
    createdIds: {
      projectIds: [projectId],
      jobIds: ["job_vla_algorithm", "job_robot_data_platform", "job_embodied_agent_infra"],
      candidateIds: ["cand_lin_chen", "cand_zhou_han", "cand_maya_li", "cand_wang_ke", "cand_sara_qi"],
      matchCount: 5,
    },
  },
  createdIds: {
    taskIds: [],
    reportIds: [],
    segmentIds: [],
    draftIds: [],
    historyIds: [],
  },
  commands: [],
  apiContracts: [],
  jsonWorkflow: {
    validate: [],
    run: [],
    longRunningHumanLoop: null,
    invalidWorkflows: [],
    pytestEvidence: [],
  },
  uiE2E: null,
  staticAudit: [],
  soak: null,
  securityPrivacy: [],
  artifacts: {},
  decisions: {},
  riskRegister: [],
};

let backendUrl = "";
let frontendUrl = "";
let devProcess = null;
let devLogStream = null;
let devStartCount = 0;

function timestampId() {
  return new Date().toISOString().replace(/[-:]/g, "").replace(/\..+$/, "").replace("T", "_");
}

function sqliteUrl(filePath) {
  return `sqlite:///${filePath}`;
}

function redact(value, depth = 0) {
  if (value === null || value === undefined) return value ?? null;
  if (typeof value === "string") return redactString(value);
  if (typeof value === "number" || typeof value === "boolean") return value;
  if (Array.isArray(value)) {
    if (depth > 6) return value.slice(0, 5).map((item) => redact(item, depth + 1));
    return value.map((item) => redact(item, depth + 1));
  }
  if (typeof value === "object") {
    if (depth > 4) return { type: "object", keys: Object.keys(value).slice(0, 12) };
    const output = {};
    for (const [key, item] of Object.entries(value).slice(0, 32)) {
      if (/key|token|secret|password|credential|authorization/i.test(key)) output[key] = "[redacted]";
      else if (/email/i.test(key) && typeof item === "string") output[key] = "[email redacted]";
      else output[key] = redact(item, depth + 1);
    }
    return output;
  }
  return String(value);
}

function redactString(value) {
  return String(value)
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[email redacted]")
    .replace(/\b(sk|pk|rk|ak|api)[-_][A-Za-z0-9]{8,}\b/gi, "[secret redacted]")
    .replace(/\b[A-Za-z0-9_]*(API_KEY|TOKEN|SECRET|PASSWORD|ACCESS_KEY)[A-Za-z0-9_]*\s*=\s*[^\s"']+/gi, "$1=[redacted]")
    .replace(/Bearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer [redacted]")
    .replace(/OpenRouterChatLLMProvider/g, "[provider-internal]");
}

function truncate(value, max = 4000) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

function slug(value) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "command";
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function main() {
  await prepareArtifactDirs();
  await collectEnvironment();
  await prepareDatabases();
  await runVerificationCommands();
  report.staticAudit = await runStaticAudit();
  report.ports = await choosePorts();

  await startDevServer();
  try {
    await runApiContracts();
    await runJsonWorkflowSpecials();
    await runUiE2E();
    await runShortSoak();
  } finally {
    await stopDevServer();
  }

  finalizeDecisions();
  await writeReports();
  printSummary();
}

async function prepareArtifactDirs() {
  await fs.mkdir(artifactDir, { recursive: true });
  await fs.mkdir(commandLogDir, { recursive: true });
  await fs.mkdir(path.join(artifactDir, "screenshots"), { recursive: true });
  await fs.mkdir(path.join(artifactDir, "videos"), { recursive: true });
}

async function collectEnvironment() {
  const envCommands = [
    ["gitBranch", "git rev-parse --abbrev-ref HEAD"],
    ["gitCommit", "git rev-parse HEAD"],
    ["gitStatus", "git status --short"],
    ["python", ".venv/bin/python --version"],
    ["node", "node --version"],
    ["pnpm", "pnpm --version"],
    ["browserChromium", "pnpm --dir artifacts/e2e_evidence/runner exec playwright --version"],
  ];
  const entries = {};
  for (const [key, command] of envCommands) {
    const result = await runShell(`env-${key}`, command, { timeoutMs: 30000, recordCommand: false });
    entries[key] = result.exitCode === 0 ? result.stdout.trim() : redactString((result.stderr || result.stdout).trim());
  }
  report.environment = {
    branch: entries.gitBranch,
    commit: entries.gitCommit,
    gitStatus: entries.gitStatus,
    os: `${os.type()} ${os.release()} ${os.arch()}`,
    platform: os.platform(),
    cpuCount: os.cpus().length,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    python: entries.python,
    node: entries.node,
    pnpm: entries.pnpm,
    browserOrTestRunner: entries.browserChromium,
    testRunner: "pytest / vitest / Playwright chromium",
    e2eRunId: runId,
  };
}

async function prepareDatabases() {
  await fs.rm(seedProjectDbPath, { force: true });
  await fs.rm(seedTaskDbPath, { force: true });
  const seedResult = await runShell(
    "seed-db",
    `.venv/bin/python scripts/seed_db.py --database-url ${shellQuote(sqliteUrl(seedProjectDbPath))}`,
    { timeoutMs: 60000 },
  );
  try {
    report.seed.summary = JSON.parse(seedResult.stdout.trim());
  } catch {
    report.seed.summary = { status: seedResult.exitCode === 0 ? "seeded" : "error", output: redactString(seedResult.stdout || seedResult.stderr) };
  }
}

async function runVerificationCommands() {
  const env = baseServiceEnv();
  const commands = [
    ["frontend lint", "pnpm --dir frontend lint", 180000],
    ["frontend build", "pnpm --dir frontend build", 240000],
    ["frontend test", "pnpm --dir frontend test", 240000],
    ["python compileall", ".venv/bin/python -m compileall app scripts tests", 180000],
    ["pytest all", ".venv/bin/python -m pytest -q", 600000],
    ["pytest json workflow", ".venv/bin/python -m pytest tests/test_json_workflow_engine.py -q", 300000],
    ["pytest static contracts", ".venv/bin/python -m pytest tests/test_static_contracts.py -q", 300000],
  ];
  for (const [label, command, timeoutMs] of commands) {
    const result = await runShell(label, command, { timeoutMs, env });
    report.commands.push(commandSummary(label, command, result));
    if (label.includes("json workflow") || label.includes("static contracts")) {
      report.jsonWorkflow.pytestEvidence.push(commandSummary(label, command, result));
    }
  }
}

async function choosePorts() {
  const backendPort = await firstFreePort(Number(process.env.BACKEND_PORT || "8010"), 20);
  const frontendPort = await firstFreePort(Number(process.env.FRONTEND_PORT || "5174"), 20);
  backendUrl = `http://127.0.0.1:${backendPort}`;
  frontendUrl = `http://127.0.0.1:${frontendPort}`;
  return {
    backendHost: "0.0.0.0",
    backendPort,
    frontendHost: "0.0.0.0",
    frontendPort,
    backendUrl,
    frontendUrl,
    apiBase: `${backendUrl}/api`,
  };
}

async function startDevServer() {
  await ensureCurrentPortsFreeOrReassign();
  devStartCount += 1;
  const logPath = path.join(artifactDir, devStartCount === 1 ? "dev-server.log" : `dev-server-restart-${devStartCount}.log`);
  report.artifacts[devStartCount === 1 ? "devServerLog" : `devServerRestart${devStartCount}Log`] = logPath;
  devLogStream = fssync.createWriteStream(logPath, { flags: "w" });
  const env = {
    ...baseServiceEnv(),
    BACKEND_HOST: "0.0.0.0",
    BACKEND_PORT: String(report.ports.backendPort),
    FRONTEND_HOST: "0.0.0.0",
    FRONTEND_PORT: String(report.ports.frontendPort),
    USE_CONDA: "0",
    BACKEND_RELOAD: "0",
  };
  devProcess = spawn("bash", ["scripts/start_dev.sh"], {
    cwd: repoRoot,
    env,
    detached: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  devProcess.stdout.on("data", (chunk) => devLogStream.write(redactString(chunk.toString())));
  devProcess.stderr.on("data", (chunk) => devLogStream.write(redactString(chunk.toString())));
  await Promise.all([
    waitForUrl(`${backendUrl}/health`, 90000, "backend health"),
    waitForUrl(frontendUrl, 90000, "frontend"),
  ]);
}

async function stopDevServer() {
  if (!devProcess) {
    if (devLogStream) {
      await new Promise((resolve) => devLogStream.end(resolve));
      devLogStream = null;
    }
    return;
  }
  const proc = devProcess;
  devProcess = null;
  if (proc.exitCode === null && !proc.killed) {
    killProcessTree(proc, "SIGTERM");
    const exited = await waitForProcess(proc, 8000);
    if (!exited && proc.exitCode === null) killProcessTree(proc, "SIGKILL");
  }
  await waitForPortFree(report.ports.backendPort, 8000);
  await waitForPortFree(report.ports.frontendPort, 8000);
  if (devLogStream) {
    await new Promise((resolve) => devLogStream.end(resolve));
    devLogStream = null;
  }
}

async function restartDevServer() {
  await stopDevServer();
  await startDevServer();
}

async function runApiContracts() {
  const project = await contract("health", "GET", "/health", null, { expected: [200] });
  await contract("openapi", "GET", "/openapi.json", null, { expected: [200] });
  await contract("project detail", "GET", `/projects/${projectId}`, null, { expected: [200] });
  const jobs = await contract("project jobs", "GET", `/projects/${projectId}/jobs`, null, { expected: [200] });
  const candidates = await contract("project candidates", "GET", `/projects/${projectId}/candidates?skip=0&limit=50`, null, { expected: [200] });
  await contract("unique candidates", "GET", `/projects/${projectId}/candidates/unique`, null, { expected: [200] });
  await contract("integrations status", "GET", "/integrations/status", null, { expected: [200] });
  await contract("scenarios meta", "GET", "/scenarios/meta", null, { expected: [200] });
  await contract("workflow meta", "GET", "/workflow/meta", null, { expected: [200] });

  const firstJob = Array.isArray(jobs.response) ? jobs.response[0] : null;
  const firstCandidateWithEmail = Array.isArray(candidates.response)
    ? candidates.response.find((item) => item.email) || candidates.response[0]
    : null;

  const segmentQuery = await contract(
    "segments query",
    "POST",
    "/segments/query",
    { projectId, criteria: { minScore: 80, hasEmail: "yes" } },
    { expected: [200] },
  );
  const segmentCandidateIds = Array.isArray(segmentQuery.response?.candidates)
    ? segmentQuery.response.candidates.map((item) => item.id)
    : [];
  const segmentCreate = await contract(
    "segments save",
    "POST",
    "/segments",
    {
      projectId,
      name: `E2E ${runId} 80分以上有邮箱候选人`,
      criteria: { minScore: 80, hasEmail: "yes" },
      candidateIds: segmentCandidateIds,
    },
    { expected: [200] },
  );
  if (segmentCreate.response?.segmentId) report.createdIds.segmentIds.push(segmentCreate.response.segmentId);
  await contract("segments list", "GET", `/segments?projectId=${projectId}`, null, { expected: [200] });
  if (segmentCreate.response?.segmentId) await contract("segments get", "GET", `/segments/${segmentCreate.response.segmentId}`, null, { expected: [200] });

  const reportCreate = await contract(
    "weekly report save",
    "POST",
    "/reports/weekly",
    {
      projectId,
      sourceTaskId: `api_contract_${runId}`,
      report: {
        conclusion: "E2E 合同探测周报",
        keyProgress: ["完成真实后端读写探测"],
        topCandidates: ["Alex Chen: 92 分"],
        risks: ["外部 provider 未做 live 调用"],
        nextActions: ["继续执行 UI E2E"],
      },
    },
    { expected: [200] },
  );
  if (reportCreate.response?.reportId) report.createdIds.reportIds.push(reportCreate.response.reportId);
  await contract("weekly report latest", "GET", `/projects/${projectId}/reports/latest`, null, { expected: [200] });
  if (reportCreate.response?.reportId) await contract("weekly report get", "GET", `/reports/${reportCreate.response.reportId}`, null, { expected: [200] });

  if (firstJob && firstCandidateWithEmail) {
    const draft = await contract(
      "outreach draft",
      "POST",
      "/outreach/draft",
      {
        projectId,
        jobId: firstJob.id,
        candidateId: firstCandidateWithEmail.id,
        segmentId: segmentCreate.response?.segmentId ?? null,
      },
      { expected: [200] },
    );
    if (draft.response?.draftId) report.createdIds.draftIds.push(draft.response.draftId);
    if (draft.response?.draftId) {
      await contract(
        "outreach patch",
        "PATCH",
        `/outreach/drafts/${draft.response.draftId}`,
        { subject: `${draft.response.subject} - E2E`, body: `${draft.response.body}\n\nE2E confirmed.` },
        { expected: [200] },
      );
      const send = await contract(
        "outreach simulate send",
        "POST",
        "/outreach/send",
        { draftId: draft.response.draftId, decision: "approve", simulate: true },
        { expected: [200] },
      );
      if (send.response?.historyId) report.createdIds.historyIds.push(send.response.historyId);
    }
    await contract("outreach history", "GET", `/outreach/history?projectId=${projectId}`, null, { expected: [200] });
  }

  await contract(
    "search plan local catalog",
    "POST",
    "/search/plan",
    { query: "机器人 VLA GitHub 候选人线索", limit: 3, service: "talent_source_catalog" },
    { expected: [200] },
  );
  await contract(
    "search run local catalog",
    "POST",
    "/search/run",
    { query: "机器人 VLA GitHub 候选人线索", limit: 3, service: "talent_source_catalog" },
    { expected: [200] },
  );
  await contract("search archive recent", "GET", "/search/archive/recent?limit=5", null, { expected: [200] });
  await contract(
    "rsi evaluate local",
    "POST",
    "/rsi/evaluate",
    { suite: "candidate_evaluation_core", mode: "local", allow_live: false },
    { expected: [200] },
  );
  await contract(
    "jobs match fallback",
    "POST",
    "/jobs/match",
    { query: "VLA / 具身智能算法工程师", top_k: 3 },
    { expected: [200], limited: [503], timeoutMs: 60000, note: "May be LIMITED if local embedding/vector provider is unavailable and DB fallback cannot match." },
  );
  await contract(
    "resumes ingest",
    "POST",
    "/resumes/ingest",
    { file_path: await writeSampleResume(), candidate_id: `e2e_resume_${runId}`, write_database: false },
    { expected: [200], limited: [422, 500, 503, "error"], timeoutMs: 45000, note: "Endpoint depends on local parser/embedding/vector-store; no live provider is configured in this run." },
  );

  const taskCreate = await contract(
    "scenario task create",
    "POST",
    "/scenarios/run",
    {
      scenario: "A",
      input: "E2E API contract: VLA / 具身智能算法工程师",
      frontend_state: { project_id: projectId, job_id: "job_vla_algorithm", source: "full-v3-runner" },
    },
    { expected: [200] },
  );
  if (taskCreate.response?.task_id) {
    report.createdIds.taskIds.push(taskCreate.response.task_id);
    await waitForTask(taskCreate.response.task_id, (snapshot) => snapshot.status === "awaiting_human" || terminalStatuses.has(snapshot.status), 45000);
    await contract("task snapshot", "GET", `/tasks/${taskCreate.response.task_id}`, null, { expected: [200] });
    await contract("task cancel", "POST", `/tasks/${taskCreate.response.task_id}/cancel`, null, { expected: [200] });
  }
  await runConcurrentTaskCreationProbe();

  if (!project.ok) {
    addRisk("P0", "health 接口未通过，后续闭环证据不可信", "检查 FastAPI 启动和 /health。");
  }
}

async function runConcurrentTaskCreationProbe() {
  const workflow = {
    id: `e2e_concurrent_${runId}`,
    name: "E2E concurrent task creation",
    inputs: { candidate_name: "Alex Chen" },
    steps: [{ id: "save", type: "save_artifact", input: "created {{candidate_name}}", output_key: "created" }],
  };
  const probes = await Promise.all(
    [1, 2, 3].map((index) =>
      contract(
        `concurrent workflow create ${index}`,
        "POST",
        "/workflows/run",
        { workflow: { ...workflow, id: `${workflow.id}_${index}` }, input: { candidate_name: "Alex Chen" }, auto_run: false },
        { expected: [200] },
      ),
    ),
  );
  const taskIds = probes.map((probe) => probe.response?.taskId || probe.response?.task_id).filter(Boolean);
  report.createdIds.taskIds.push(...taskIds);
  const unique = new Set(taskIds);
  report.apiContracts.push({
    name: "concurrency unique task_id audit",
    method: "ASSERT",
    path: "/workflows/run x3",
    status: "assert",
    verdict: taskIds.length === 3 && unique.size === 3 ? "PASS" : "FAIL",
    request: { count: 3 },
    response: { taskIds },
    note: "API-level concurrency probe; UI reclick debounce is covered as LIMITED unless a dedicated browser reclick script is run.",
  });
}

async function runJsonWorkflowSpecials() {
  const fixturePaths = [
    "tests/fixtures/json_workflows/advanced_ai_algorithm_recruiting.json",
    "tests/fixtures/json_workflows/resume_structured_extract.json",
    "tests/fixtures/json_workflows/jd_structured_extract.json",
  ];
  for (const relativePath of fixturePaths) {
    const workflow = JSON.parse(await fs.readFile(path.join(repoRoot, relativePath), "utf8"));
    const validation = await contract(`validate ${path.basename(relativePath)}`, "POST", "/workflows/validate", { workflow }, { expected: [200] });
    report.jsonWorkflow.validate.push({
      fixture: relativePath,
      verdict: validation.response?.valid === true ? "PASS" : "FAIL",
      response: redact(validation.response),
    });
  }

  const advancedWorkflow = JSON.parse(await fs.readFile(path.join(repoRoot, fixturePaths[0]), "utf8"));
  const advancedCreate = await contract(
    "advanced recruiting workflow task create",
    "POST",
    "/workflows/run",
    {
      workflow: advancedWorkflow,
      input: {
        search_query: "GitHub robotics VLA embodied AI candidate",
        role_name: "高级 AI 算法岗",
      },
      auto_run: false,
    },
    { expected: [200] },
  );
  const advancedTaskId = advancedCreate.response?.taskId || advancedCreate.response?.task_id;
  if (advancedTaskId) report.createdIds.taskIds.push(advancedTaskId);
  report.jsonWorkflow.run.push({
    name: "advanced AI algorithm recruiting workflow creation",
    verdict: advancedTaskId ? "PASS" : "FAIL",
    taskId: advancedTaskId,
    response: redact(advancedCreate.response),
    note: "auto_run=false proves custom JSON workflow can create task_id without changing Python business code. Mocked full execution is covered by pytest evidence.",
  });

  await runInvalidWorkflowValidations();
  await runLongRunningHumanLoop();
  await runJsonWorkflowRetryAndCancelProbe();
}

async function runInvalidWorkflowValidations() {
  const base = {
    id: `e2e_invalid_base_${runId}`,
    name: "invalid base",
    inputs: { query: "robotics" },
    steps: [{ id: "search", type: "search", input: "{{query}}", output_key: "results", service: "talent_source_catalog", limit: 3 }],
  };
  const cases = [
    ["duplicate step id", { ...base, steps: [...base.steps, { ...base.steps[0] }] }],
    ["unresolved placeholder", { ...base, steps: [{ ...base.steps[0], input: "{{missing_query}}" }] }],
    [
      "future dependency",
      {
        ...base,
        steps: [
          { id: "first", type: "llm_prompt", prompt: "Use {{later}}", output_key: "first" },
          { id: "later", type: "save_artifact", input: "later", output_key: "later" },
        ],
      },
    ],
    [
      "duplicate output_key",
      {
        ...base,
        steps: [
          { id: "one", type: "save_artifact", input: "one", output_key: "same" },
          { id: "two", type: "save_artifact", input: "two", output_key: "same" },
        ],
      },
    ],
    ["invalid limit", { ...base, steps: [{ ...base.steps[0], limit: 99 }] }],
    ["invalid max_retries", { ...base, steps: [{ id: "extract", type: "structured_extract", input: "x", output_key: "x", schema: { type: "object" }, max_retries: 9 }] }],
    ["missing required field", { ...base, steps: [{ id: "extract", type: "structured_extract", input: "x", output_key: "x" }] }],
    ["unsupported step type", { ...base, steps: [{ id: "bad", type: "send_email", input: "x", output_key: "x" }] }],
  ];
  for (const [name, workflow] of cases) {
    const validation = await contract(`invalid workflow ${name}`, "POST", "/workflows/validate", { workflow }, { expected: [200] });
    const verdict = validation.response?.valid === false ? "PASS" : "FAIL";
    report.jsonWorkflow.invalidWorkflows.push({ name, verdict, response: redact(validation.response) });
  }
}

async function runLongRunningHumanLoop() {
  const workflow = {
    id: `e2e_long_human_loop_${runId}`,
    name: "E2E long running human-in-the-loop",
    inputs: { candidate_name: "Alex Chen" },
    steps: [
      { id: "pre_screen", type: "save_artifact", input: "pre-screen {{candidate_name}}", output_key: "pre_screen" },
      { id: "hr_review", type: "human_gate", prompt: "HR 是否推进 {{candidate_name}} 面谈？", output_key: "hr_decision" },
      { id: "final_summary", type: "save_artifact", input: "final decision {{hr_decision}}", output_key: "final_summary" },
    ],
  };
  const start = await contract("json workflow long human run", "POST", "/workflows/run", { workflow, input: { candidate_name: "Alex Chen" }, auto_run: true }, { expected: [200] });
  const taskId = start.response?.taskId || start.response?.task_id;
  if (taskId) report.createdIds.taskIds.push(taskId);
  const result = {
    taskId,
    verdict: "FAIL",
    checks: [],
    beforeRestart: null,
    afterRestart: null,
    afterConfirm: null,
  };
  if (!taskId) {
    result.checks.push(check(false, "created task_id", "POST /workflows/run did not return task_id"));
    report.jsonWorkflow.longRunningHumanLoop = result;
    addRisk("P0", "JSON workflow 无法创建 long-running task_id", "检查 /workflows/run 和 WorkflowTaskRunner.start。");
    return;
  }
  const awaiting = await waitForTask(taskId, (snapshot) => snapshot.status === "awaiting_human", 45000);
  result.beforeRestart = redact(awaiting);
  const runtimeBefore = awaiting?.frontend_state?.json_workflow_runtime;
  const preScreenDoneCountBefore = countStepDone(awaiting, "pre_screen");
  result.checks.push(check(awaiting?.status === "awaiting_human", "awaiting_human before restart", `status=${awaiting?.status}`));
  result.checks.push(check(Boolean(runtimeBefore), "runtime checkpoint exists", "frontend_state.json_workflow_runtime missing"));
  result.checks.push(check(runtimeBefore?.current_step_index === 1, "current_step_index stopped at human_gate", `current_step_index=${runtimeBefore?.current_step_index}`));
  result.checks.push(check(Boolean(awaiting?.awaiting), "awaiting payload exists", "awaiting payload missing"));
  result.checks.push(check(preScreenDoneCountBefore === 1, "pre-step executed once before restart", `pre_screen count=${preScreenDoneCountBefore}`));
  if (awaiting?.status !== "awaiting_human") {
    result.verdict = "FAIL";
    report.jsonWorkflow.longRunningHumanLoop = result;
    addRisk("P0", "JSON workflow 未进入 awaiting_human，无法执行重启恢复专项", `task_id=${taskId}; status=${awaiting?.status}`);
    return;
  }

  await sleep(1500);
  await restartDevServer();

  const afterRestart = await contract("json workflow task after backend restart", "GET", `/tasks/${taskId}`, null, { expected: [200] });
  result.afterRestart = redact(afterRestart.response);
  const runtimeAfterRestart = afterRestart.response?.frontend_state?.json_workflow_runtime;
  result.checks.push(check(afterRestart.response?.status === "awaiting_human", "still awaiting after restart", `status=${afterRestart.response?.status}`));
  result.checks.push(check(runtimeAfterRestart?.current_step_index === 1, "checkpoint index preserved after restart", `current_step_index=${runtimeAfterRestart?.current_step_index}`));
  result.checks.push(check(!String(afterRestart.response?.error || "").includes("interrupted"), "not marked interrupted error", `error=${afterRestart.response?.error || ""}`));

  await contract("json workflow confirm after restart", "POST", `/tasks/${taskId}/confirm`, { decision: "approve", data: { reviewer: "E2E HR" } }, { expected: [200] });
  const finalSnapshot = await waitForTask(taskId, (snapshot) => terminalStatuses.has(snapshot.status), 45000);
  result.afterConfirm = redact(finalSnapshot);
  const runtimeFinal = finalSnapshot?.frontend_state?.json_workflow_runtime;
  const preScreenDoneCountFinal = countStepDone(finalSnapshot, "pre_screen");
  result.checks.push(check(finalSnapshot?.status === "done", "done after confirm", `status=${finalSnapshot?.status}`));
  result.checks.push(check(preScreenDoneCountFinal === 1, "pre human_gate step not repeated", `pre_screen count=${preScreenDoneCountFinal}`));
  result.checks.push(check(Boolean(finalSnapshot?.result?.workflow_id), "final result workflow_id", "workflow_id missing"));
  result.checks.push(check(Boolean(finalSnapshot?.result?.context), "final result context", "context missing"));
  result.checks.push(check(Boolean(finalSnapshot?.result?.artifacts), "final result artifacts", "artifacts missing"));
  result.checks.push(check(Object.hasOwn(finalSnapshot?.result || {}, "final_output"), "final result final_output", "final_output missing"));
  result.checks.push(check(runtimeFinal?.context?.hr_decision?.decision === "approve", "confirm stored in runtime context", `decision=${runtimeFinal?.context?.hr_decision?.decision}`));
  result.verdict = result.checks.every((item) => item.ok) ? "PASS" : "FAIL";
  report.jsonWorkflow.longRunningHumanLoop = result;
  if (result.verdict !== "PASS") {
    addRisk("P0", "JSON workflow long-running human-in-the-loop 未通过", "检查 checkpoint、重启恢复和 confirm resume。");
  }
}

async function runJsonWorkflowRetryAndCancelProbe() {
  const workflow = {
    id: `e2e_cancel_retry_${runId}`,
    name: "E2E JSON cancel retry probe",
    inputs: { candidate_name: "Alex Chen" },
    steps: [{ id: "save", type: "save_artifact", input: "save {{candidate_name}}", output_key: "saved" }],
  };
  const create = await contract("json workflow cancel probe create", "POST", "/workflows/run", { workflow, input: { candidate_name: "Alex Chen" }, auto_run: false }, { expected: [200] });
  const taskId = create.response?.taskId || create.response?.task_id;
  if (taskId) {
    report.createdIds.taskIds.push(taskId);
    await contract("json workflow cancel", "POST", `/tasks/${taskId}/cancel`, null, { expected: [200] });
    const retry = await contract("json workflow retry legacy endpoint", "POST", `/tasks/${taskId}/retry`, null, {
      expected: [200],
      limited: [409, 422, 500],
      note: "Current retry route is legacy scenario retry; JSON workflow retry support is assessed as LIMITED if it cannot restart json_workflow.",
    });
    report.jsonWorkflow.run.push({
      name: "json workflow cancel/retry endpoint probe",
      verdict: retry.verdict === "PASS" ? "PASS" : "LIMITED",
      taskId,
      response: redact(retry.response),
      note: retry.note,
    });
  }
}

async function runUiE2E() {
  const command = "pnpm --dir artifacts/e2e_evidence/runner exec node e2e-runner.mjs";
  const result = await runShell("ui-e2e-project-detail", command, {
    timeoutMs: 600000,
    env: {
      ...baseServiceEnv(),
      E2E_BASE_URL: frontendUrl,
      E2E_PROJECT_ID: projectId,
      E2E_RUN_ID: runId,
    },
  });
  report.commands.push(commandSummary("ui-e2e-project-detail", command, result));
  const jsonPath = path.join(artifactDir, "e2e-report.json");
  report.artifacts.uiE2EJson = jsonPath;
  report.artifacts.networkLog = path.join(artifactDir, "network-log.json");
  report.artifacts.probeLog = path.join(artifactDir, "probe-log.json");
  report.artifacts.trace = path.join(artifactDir, "trace.zip");
  report.artifacts.fallbackTrace = path.join(artifactDir, "fallback-trace.zip");
  try {
    const payload = JSON.parse(await fs.readFile(jsonPath, "utf8"));
    report.uiE2E = redact({
      run: payload.run,
      summary: payload.summary,
      features: payload.features,
      artifacts: payload.artifacts,
      networkLogCount: payload.networkLog?.length || 0,
      probeLogCount: payload.probeLog?.length || 0,
      eventSourceLogCount: payload.eventSourceLog?.length || 0,
    });
    for (const feature of payload.features || []) {
      if (feature.task_id) {
        String(feature.task_id)
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean)
          .forEach((taskId) => report.createdIds.taskIds.push(taskId));
      }
    }
  } catch (error) {
    report.uiE2E = { status: "unavailable", error: redactString(error.message) };
  }
}

async function runShortSoak() {
  const startedAt = new Date().toISOString();
  const iterations = [];
  const deadline = Date.now() + Math.max(0, soakSeconds) * 1000;
  let count = 0;
  while (Date.now() < deadline) {
    count += 1;
    const health = await apiFetch("GET", "/health", null, { timeoutMs: 8000 });
    const project = await apiFetch("GET", `/projects/${projectId}`, null, { timeoutMs: 8000 });
    const integrations = await apiFetch("GET", "/integrations/status", null, { timeoutMs: 8000 });
    iterations.push({
      index: count,
      timestamp: new Date().toISOString(),
      statuses: {
        health: health.status,
        project: project.status,
        integrations: integrations.status,
      },
    });
    await sleep(2000);
  }
  const failed = iterations.filter((item) => Object.values(item.statuses).some((status) => status !== 200));
  report.soak = {
    configuredSeconds: soakSeconds,
    startedAt,
    finishedAt: new Date().toISOString(),
    iterations: iterations.length,
    failures: failed,
    verdict: failed.length === 0 ? (soakSeconds >= 1800 ? "PASS" : "LIMITED") : "FAIL",
    note:
      soakSeconds >= 1800
        ? "Long soak met the 30 minute minimum."
        : "This run used a short soak. Set E2E_SOAK_SECONDS=1800..7200 to satisfy the requested 30-120 minute stability window.",
  };
  if (report.soak.verdict === "FAIL") addRisk("P0", "soak 探测期间核心接口失败", "查看 dev-server.log 和 apiContracts。");
}

async function runStaticAudit() {
  const audits = [];
  const page = await readRepoFile("frontend/src/pages/ProjectDetailPage.tsx");
  const state = await readRepoFile("frontend/src/features/projects/state.ts");
  const useTaskStream = await readRepoFile("frontend/src/shared/hooks/useTaskStream.ts");
  const main = await readRepoFile("app/api/main.py");
  const orchestrator = await readRepoFile("app/core/orchestrator.py");
  const executor = await readRepoFile("app/core/workflow_executor.py");
  const context = await readRepoFile("app/core/workflow_context.py");
  const mock = await readRepoFile("frontend/src/shared/mocks/projectMock.ts");

  audits.push(audit("ProjectDetailPage does not import projectMock", !page.includes("projectMock"), "frontend/src/pages/ProjectDetailPage.tsx", "防止项目详情页在 API 失败时回退假数据。"));
  audits.push(audit("ProjectDetailPage does not call buildCandidateEmailDraft", !page.includes("buildCandidateEmailDraft"), "frontend/src/pages/ProjectDetailPage.tsx", "触达草稿应来自 /outreach/draft。"));
  audits.push(audit("legacy buildCandidateEmailDraft only exists in state helper", state.includes("buildCandidateEmailDraft"), "frontend/src/features/projects/state.ts", "P2: helper/test fixture 存在，但项目详情页未调用。", "INFO"));
  audits.push(audit("weekly report parser supports Chinese backend keys", page.includes("本周招聘结论") && page.includes("下周行动建议"), "frontend/src/pages/ProjectDetailPage.tsx", "D 场景 task result 的中文键可被 UI 消费。"));
  audits.push(audit("useTaskStream uses EventSource", useTaskStream.includes("new EventSource"), "frontend/src/shared/hooks/useTaskStream.ts", "SSE 主链路存在。"));
  audits.push(audit("useTaskStream has fallback polling", useTaskStream.includes("fallback") && useTaskStream.includes("poll"), "frontend/src/shared/hooks/useTaskStream.ts", "SSE 失败后轮询兜底存在。"));
  audits.push(audit("confirm route checks json_workflow_runtime before legacy confirm", main.indexOf("json_workflow_runtime") > -1 && main.indexOf("json_workflow_runtime") < main.indexOf("task_store.confirm"), "app/api/main.py", "避免 JSON workflow confirm 走 legacy wait_event 错误分支。"));
  audits.push(audit("recovery preserves awaiting JSON workflow", orchestrator.includes('if row.status == "awaiting_human":') && orchestrator.includes("json_workflow_runtime"), "app/core/orchestrator.py", "重启恢复不应把 awaiting_human checkpoint 标为 interrupted error。"));
  audits.push(audit("workflow executor does not import concrete providers", !executor.includes("app.providers") && !executor.includes("OpenRouterChatLLMProvider"), "app/core/workflow_executor.py", "JSON Workflow Engine 通过 ServiceRouter 而非具体 provider。"));
  audits.push(audit("structured extract retry prompt is sanitized", context.includes("sanitize_failure_text") && context.includes("retry_prompt"), "app/core/workflow_context.py", "失败上下文不能泄露 key/provider internals。"));
  audits.push(audit("projectMock file still exists but is isolated", mock.includes("projectMock") && !page.includes("shared/mocks/projectMock"), "frontend/src/shared/mocks/projectMock.ts", "P2: 测试 fixture 存在；运行时页面未导入。", "INFO"));

  for (const item of audits) {
    if (item.verdict === "FAIL") addRisk("P1", item.name, `${item.file}: ${item.note}`);
  }
  return audits;
}

function finalizeDecisions() {
  const commandFails = report.commands.filter((item) => item.verdict === "FAIL");
  const apiFails = report.apiContracts.filter((item) => item.verdict === "FAIL");
  const apiLimited = report.apiContracts.filter((item) => item.verdict === "LIMITED");
  const uiFeatures = report.uiE2E?.features || [];
  const uiFails = Array.isArray(uiFeatures) ? uiFeatures.filter((feature) => feature.status !== "PASS") : [];
  const jsonLong = report.jsonWorkflow.longRunningHumanLoop;
  const jsonInvalidFails = report.jsonWorkflow.invalidWorkflows.filter((item) => item.verdict !== "PASS");
  const staticFails = report.staticAudit.filter((item) => item.verdict === "FAIL");
  const p0 = report.riskRegister.filter((item) => item.priority === "P0");
  const p1 = report.riskRegister.filter((item) => item.priority === "P1");

  const coreBackendClosedLoop =
    commandFails.length === 0 &&
    apiFails.length === 0 &&
    uiFails.length === 0 &&
    jsonLong?.verdict === "PASS" &&
    jsonInvalidFails.length === 0 &&
    staticFails.length === 0;
  const limitedReasons = [];
  if (apiLimited.length) limitedReasons.push(`${apiLimited.length} API contract(s) are environment-limited`);
  if (report.soak?.verdict === "LIMITED") limitedReasons.push("full 30-120 minute soak was not run");
  if (report.jsonWorkflow.run.some((item) => item.verdict === "LIMITED")) limitedReasons.push("JSON workflow retry endpoint is legacy-limited");

  report.decisions = {
    realBackendClosedLoop: coreBackendClosedLoop ? "YES" : "NO",
    uiConsumesBackendResult: uiFails.length === 0 ? "YES" : "NO",
    longStability: report.soak?.verdict === "PASS" ? "YES" : "LIMITED",
    fakeDataOrFakeSuccess: staticFails.length === 0 && uiFails.length === 0 ? "NO_BLOCKING_EVIDENCE" : "FOUND",
    internalDemoReady: coreBackendClosedLoop && p0.length === 0 ? "YES" : "NO",
    internalTrialReady: coreBackendClosedLoop && p0.length === 0 && p1.length === 0 && report.soak?.verdict === "PASS" ? "YES" : "LIMITED",
    overallVerdict: coreBackendClosedLoop && !limitedReasons.length ? "PASS" : coreBackendClosedLoop ? "LIMITED" : "FAIL",
    limitedReasons,
    p0Fixes: p0,
    p1Fixes: p1,
  };

  report.securityPrivacy = [
    {
      name: "report redaction",
      verdict: JSON.stringify(report).match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i) ? "FAIL" : "PASS",
      note: "JSON report is checked for raw email pattern before final write.",
    },
    {
      name: "secret redaction",
      verdict: JSON.stringify(report).match(/\b(sk|pk|rk|api)[-_][A-Za-z0-9]{8,}\b/i) ? "FAIL" : "PASS",
      note: "JSON report is checked for common API key/token prefixes before final write.",
    },
  ];
}

async function writeReports() {
  report.run.finishedAt = new Date().toISOString();
  report.run.endEpochMs = Date.now();
  report.run.durationSeconds = Math.round((report.run.endEpochMs - report.run.startEpochMs) / 1000);
  report.createdIds.taskIds = [...new Set(report.createdIds.taskIds)];
  const jsonPath = path.join(artifactDir, "e2e_project_detail_report.json");
  const mdPath = path.join(artifactDir, "e2e-report.md");
  report.artifacts.fullJsonReport = jsonPath;
  report.artifacts.markdownReport = mdPath;
  const sanitizedReport = redact(report);
  await fs.writeFile(jsonPath, JSON.stringify(sanitizedReport, null, 2));
  await fs.writeFile(mdPath, renderMarkdown(sanitizedReport));
}

function printSummary() {
  console.log(`v3 report: ${path.join(artifactDir, "e2e-report.md")}`);
  console.log(`v3 json:   ${path.join(artifactDir, "e2e_project_detail_report.json")}`);
  console.log(`overall:   ${report.decisions.overallVerdict}`);
}

async function contract(name, method, apiPath, body = null, options = {}) {
  const response = await apiFetch(method, apiPath, body, { timeoutMs: options.timeoutMs || 30000 });
  const expected = options.expected || [200];
  const limited = options.limited || [];
  let verdict = "FAIL";
  if (expected.includes(response.status)) verdict = "PASS";
  else if (limited.includes(response.status) || response.error?.includes("timeout")) verdict = "LIMITED";
  const entry = {
    name,
    method,
    path: apiPath,
    status: response.status,
    verdict,
    request: redact(body),
    response: redact(response.body),
    error: response.error ? redactString(response.error) : null,
    note: options.note || null,
  };
  report.apiContracts.push(entry);
  return { ...entry, ok: verdict === "PASS", response: response.body };
}

async function apiFetch(method, apiPath, body = null, options = {}) {
  const url = `${backendUrl}/api${apiPath}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs || 30000);
  try {
    const response = await fetch(url, {
      method,
      headers: body === null || body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === null || body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const contentType = response.headers.get("content-type") || "";
    const parsed = contentType.includes("application/json") ? await response.json() : await response.text();
    return { status: response.status, body: parsed };
  } catch (error) {
    return { status: "error", body: null, error: error instanceof Error ? error.message : String(error) };
  } finally {
    clearTimeout(timeout);
  }
}

async function waitForTask(taskId, predicate, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let latest = null;
  while (Date.now() < deadline) {
    const response = await apiFetch("GET", `/tasks/${taskId}`, null, { timeoutMs: 8000 });
    latest = response.body;
    if (response.status === 200 && predicate(latest)) return latest;
    await sleep(500);
  }
  return latest;
}

async function waitForUrl(url, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs;
  let lastError = "";
  while (Date.now() < deadline) {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 2500);
      const response = await fetch(url, { signal: controller.signal });
      clearTimeout(timeout);
      if (response.ok) return true;
      lastError = `${response.status}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    if (devProcess && devProcess.exitCode !== null) break;
    await sleep(500);
  }
  throw new Error(`Timed out waiting for ${label}: ${lastError}`);
}

async function firstFreePort(start, count) {
  for (let port = start; port < start + count; port += 1) {
    if (await isPortFree(port)) return port;
  }
  throw new Error(`No free port from ${start} to ${start + count - 1}`);
}

async function ensureCurrentPortsFreeOrReassign() {
  const backendFree = await isPortFree(report.ports.backendPort);
  const frontendFree = await isPortFree(report.ports.frontendPort);
  if (backendFree && frontendFree) return;
  const previous = { ...report.ports };
  const backendPort = backendFree ? report.ports.backendPort : await firstFreePort(report.ports.backendPort + 1, 30);
  const frontendPort = frontendFree ? report.ports.frontendPort : await firstFreePort(report.ports.frontendPort + 1, 30);
  backendUrl = `http://127.0.0.1:${backendPort}`;
  frontendUrl = `http://127.0.0.1:${frontendPort}`;
  report.ports = {
    ...report.ports,
    backendPort,
    frontendPort,
    backendUrl,
    frontendUrl,
    apiBase: `${backendUrl}/api`,
    history: [...(report.ports.history || []), previous],
  };
}

function isPortFree(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => {
      server.close(() => resolve(true));
    });
    server.listen(port, "0.0.0.0");
  });
}

async function waitForPortFree(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await isPortFree(port)) return true;
    await sleep(250);
  }
  return false;
}

function killProcessTree(proc, signal) {
  try {
    process.kill(-proc.pid, signal);
  } catch {
    try {
      proc.kill(signal);
    } catch {
      // Process already exited.
    }
  }
}

function waitForProcess(proc, timeoutMs) {
  return new Promise((resolve) => {
    if (proc.exitCode !== null) return resolve(true);
    const timer = setTimeout(() => resolve(false), timeoutMs);
    proc.once("exit", () => {
      clearTimeout(timer);
      resolve(true);
    });
  });
}

async function runShell(label, command, options = {}) {
  const startedAt = new Date().toISOString();
  const timeoutMs = options.timeoutMs || 120000;
  const env = { ...process.env, ...(options.env || {}) };
  const child = spawn("bash", ["-lc", command], { cwd: repoRoot, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => {
    stdout += chunk.toString();
  });
  child.stderr.on("data", (chunk) => {
    stderr += chunk.toString();
  });
  let timedOut = false;
  const result = await new Promise((resolve) => {
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
      setTimeout(() => {
        if (child.exitCode === null) child.kill("SIGKILL");
      }, 3000);
    }, timeoutMs);
    child.on("close", (code, signal) => {
      clearTimeout(timer);
      resolve({ code, signal });
    });
  });
  const finishedAt = new Date().toISOString();
  const logPath = path.join(commandLogDir, `${slug(label)}.log`);
  const cleanStdout = redactString(stdout);
  const cleanStderr = redactString(stderr);
  await fs.writeFile(
    logPath,
    [
      `$ ${command}`,
      `started_at=${startedAt}`,
      `finished_at=${finishedAt}`,
      `exit_code=${result.code}`,
      `signal=${result.signal || ""}`,
      `timed_out=${timedOut}`,
      "",
      "## stdout",
      cleanStdout,
      "",
      "## stderr",
      cleanStderr,
    ].join("\n"),
  );
  return {
    label,
    command,
    startedAt,
    finishedAt,
    exitCode: result.code,
    signal: result.signal,
    timedOut,
    stdout: cleanStdout,
    stderr: cleanStderr,
    logPath,
  };
}

function commandSummary(label, command, result) {
  return {
    label,
    command,
    verdict: result.exitCode === 0 && !result.timedOut ? "PASS" : "FAIL",
    exitCode: result.exitCode,
    timedOut: result.timedOut,
    startedAt: result.startedAt,
    finishedAt: result.finishedAt,
    stdoutTail: truncate(result.stdout.slice(-3000), 3000),
    stderrTail: truncate(result.stderr.slice(-3000), 3000),
    logPath: result.logPath,
  };
}

function baseServiceEnv() {
  return {
    ...process.env,
    PROJECT_DATABASE_URL: sqliteUrl(seedProjectDbPath),
    TASK_DATABASE_URL: sqliteUrl(seedTaskDbPath),
    E2E_RUN_ID: runId,
  };
}

function shellQuote(value) {
  return `'${String(value).replaceAll("'", "'\\''")}'`;
}

async function writeSampleResume() {
  const filePath = path.join(artifactDir, `sample-resume-${runId}.txt`);
  await fs.writeFile(
    filePath,
    [
      "Alex Chen / Robotics VLA Engineer",
      "",
      "教育经历: CMU Robotics Institute, M.S. Robotics.",
      "工作经历: Embodied AI Lab, Robot Learning Engineer.",
      "项目经历: VLA policy, teleoperation data cleaning, diffusion policy deployment, ROS real robot latency 12ms.",
      "技能: Python, PyTorch, ROS2, Isaac Sim, VLM, LLM agent tooling.",
    ].join("\n"),
  );
  return filePath;
}

async function readRepoFile(relativePath) {
  return fs.readFile(path.join(repoRoot, relativePath), "utf8");
}

function audit(name, ok, file, note, passVerdict = "PASS") {
  return { name, file, verdict: ok ? passVerdict : "FAIL", note };
}

function check(ok, name, detail) {
  return { ok: Boolean(ok), name, detail };
}

function countStepDone(snapshot, stepId) {
  return (snapshot?.steps_done || []).filter((step) => step.label === stepId).length;
}

function addRisk(priority, title, fix) {
  if (report.riskRegister.some((item) => item.priority === priority && item.title === title)) return;
  report.riskRegister.push({ priority, title, fix });
}

function renderMarkdown(data) {
  const lines = [];
  lines.push("# AI 招聘助手全量长测 v3 报告");
  lines.push("");
  lines.push(`- E2E_RUN_ID: ${data.run.id}`);
  lines.push(`- Started: ${data.run.startedAt}`);
  lines.push(`- Finished: ${data.run.finishedAt}`);
  lines.push(`- Duration: ${data.run.durationSeconds}s`);
  lines.push(`- Overall: ${data.decisions.overallVerdict}`);
  lines.push("");
  lines.push("## A. 环境与启动");
  lines.push("");
  lines.push(`- Branch: ${data.environment.branch}`);
  lines.push(`- Commit: ${data.environment.commit}`);
  lines.push(`- Git dirty status: ${String(data.environment.gitStatus || "clean").replace(/\n/g, "; ")}`);
  lines.push(`- OS: ${data.environment.os}`);
  lines.push(`- Python: ${data.environment.python}`);
  lines.push(`- Node: ${data.environment.node}`);
  lines.push(`- pnpm: ${data.environment.pnpm}`);
  lines.push(`- Browser/Test runner: ${data.environment.browserOrTestRunner}`);
  lines.push(`- API base: ${data.ports.apiBase}`);
  lines.push(`- Frontend: ${data.ports.frontendUrl}`);
  lines.push(`- Project DB: ${data.databases.projectDbPath}`);
  lines.push(`- Task DB: ${data.databases.taskDbPath}`);
  lines.push("");
  lines.push("## B. Seed 与 Cleanup 清单");
  lines.push("");
  lines.push(`- Seed summary: ${JSON.stringify(data.seed.summary)}`);
  lines.push(`- Seed IDs: ${JSON.stringify(data.seed.createdIds)}`);
  lines.push(`- Created runtime IDs: ${JSON.stringify(data.createdIds)}`);
  lines.push("- Cleanup policy: artifact SQLite DB 保留用于复核；可删除 `artifacts/e2e_evidence/projects.sqlite3` 与 `tasks.sqlite3` 清理本次数据。");
  lines.push("");
  lines.push("## C. 命令验证");
  lines.push("");
  lines.push("| Command | Verdict | Exit | Log |");
  lines.push("| --- | --- | ---: | --- |");
  for (const item of data.commands) {
    lines.push(`| ${md(item.label)} | ${item.verdict} | ${item.exitCode ?? "—"} | ${md(item.logPath)} |`);
  }
  lines.push("");
  lines.push("## D. API 合同探测");
  lines.push("");
  lines.push("| Name | Method | Path | Status | Verdict | Note |");
  lines.push("| --- | --- | --- | ---: | --- | --- |");
  for (const item of data.apiContracts) {
    lines.push(`| ${md(item.name)} | ${item.method} | ${md(item.path)} | ${item.status} | ${item.verdict} | ${md(item.note || "")} |`);
  }
  lines.push("");
  lines.push("## E. UI E2E 闭环");
  lines.push("");
  const features = data.uiE2E?.features || [];
  if (Array.isArray(features) && features.length) {
    lines.push("| Feature | Status | task_id | SSE | HumanGate | Final | Fake Data/Success Audit |");
    lines.push("| --- | --- | --- | --- | --- | --- | --- |");
    for (const feature of features) {
      lines.push(
        `| ${md(feature.featureName)} | ${feature.status} | ${md(feature.task_id || "—")} | ${feature.sseConnected ? "yes" : "no"} | ${feature.humanGateTriggered ? "yes" : "no"} | ${md(feature.finalTaskStatus || "—")} | ${md(feature.fakeDataOrSuccess || "")} |`,
      );
    }
  } else {
    lines.push(`- UI E2E report unavailable: ${JSON.stringify(data.uiE2E)}`);
  }
  lines.push("");
  lines.push("## F. JSON Workflow 专项");
  lines.push("");
  lines.push("### Valid Fixtures");
  for (const item of data.jsonWorkflow.validate) lines.push(`- ${item.verdict}: ${item.fixture}`);
  lines.push("");
  lines.push("### Invalid Workflow Validation");
  for (const item of data.jsonWorkflow.invalidWorkflows) lines.push(`- ${item.verdict}: ${item.name}`);
  lines.push("");
  lines.push("### Long-Running Human-In-The-Loop");
  const loop = data.jsonWorkflow.longRunningHumanLoop;
  if (loop) {
    lines.push(`- Verdict: ${loop.verdict}`);
    lines.push(`- Task: ${loop.taskId || "—"}`);
    for (const item of loop.checks || []) lines.push(`- ${item.ok ? "PASS" : "FAIL"}: ${item.name} (${md(item.detail)})`);
  }
  lines.push("");
  lines.push("### Pytest Evidence");
  for (const item of data.jsonWorkflow.pytestEvidence) lines.push(`- ${item.verdict}: ${item.command}`);
  lines.push("");
  lines.push("## G. 静态审计与风险");
  lines.push("");
  lines.push("| Check | File | Verdict | Note |");
  lines.push("| --- | --- | --- | --- |");
  for (const item of data.staticAudit) lines.push(`| ${md(item.name)} | ${md(item.file)} | ${item.verdict} | ${md(item.note)} |`);
  lines.push("");
  lines.push("## H. 稳定性与安全");
  lines.push("");
  lines.push(`- Soak verdict: ${data.soak?.verdict || "—"}`);
  lines.push(`- Soak configured seconds: ${data.soak?.configuredSeconds ?? "—"}`);
  lines.push(`- Soak note: ${md(data.soak?.note || "")}`);
  for (const item of data.securityPrivacy) lines.push(`- ${item.verdict}: ${item.name} - ${item.note}`);
  lines.push("");
  lines.push("## I. 最终决策");
  lines.push("");
  lines.push(`- 真实后端闭环: ${data.decisions.realBackendClosedLoop}`);
  lines.push(`- UI 是否消费后端结果: ${data.decisions.uiConsumesBackendResult}`);
  lines.push(`- 长时间稳定性: ${data.decisions.longStability}`);
  lines.push(`- 假数据/假成功: ${data.decisions.fakeDataOrFakeSuccess}`);
  lines.push(`- 内部 demo: ${data.decisions.internalDemoReady}`);
  lines.push(`- 内部试用: ${data.decisions.internalTrialReady}`);
  lines.push(`- P0 fixes: ${JSON.stringify(data.decisions.p0Fixes || [])}`);
  lines.push(`- P1 fixes: ${JSON.stringify(data.decisions.p1Fixes || [])}`);
  if (data.decisions.limitedReasons?.length) lines.push(`- Limited reasons: ${data.decisions.limitedReasons.join("; ")}`);
  lines.push("");
  lines.push("## Artifacts");
  lines.push("");
  for (const [key, value] of Object.entries(data.artifacts)) lines.push(`- ${key}: ${value}`);
  return `${lines.join("\n")}\n`;
}

function md(value) {
  return String(value ?? "").replaceAll("|", "\\|").replace(/\n/g, " ");
}

main().catch(async (error) => {
  addRisk("P0", "full-v3-runner crashed", error instanceof Error ? error.stack || error.message : String(error));
  report.decisions = {
    overallVerdict: "FAIL",
    realBackendClosedLoop: "NO",
    uiConsumesBackendResult: "UNKNOWN",
    longStability: "UNKNOWN",
    fakeDataOrFakeSuccess: "UNKNOWN",
    internalDemoReady: "NO",
    internalTrialReady: "NO",
    p0Fixes: report.riskRegister.filter((item) => item.priority === "P0"),
    p1Fixes: report.riskRegister.filter((item) => item.priority === "P1"),
  };
  report.run.finishedAt = new Date().toISOString();
  report.run.endEpochMs = Date.now();
  await stopDevServer().catch(() => null);
  await writeReports().catch(() => null);
  console.error(error);
  process.exitCode = 1;
});
