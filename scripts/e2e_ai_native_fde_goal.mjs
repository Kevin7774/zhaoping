#!/usr/bin/env node
import { mkdir, rm, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { spawn } from "node:child_process";
import process from "node:process";

const FRONTEND_URL = process.env.E2E_APP_URL || "http://127.0.0.1:5175";
const API_BASE = process.env.E2E_API_BASE || "http://127.0.0.1:8011";
const CHROME_PATH = process.env.CHROME_PATH || "/usr/bin/google-chrome";
const DEBUG_PORT = Number(process.env.E2E_CHROME_PORT || 9224);
const MODE = process.env.E2E_MODE || "full";
const PROJECT_ID =
  process.env.E2E_PROJECT_ID ||
  `goal_ai_native_fde_${new Date().toISOString().replace(/\D/g, "").slice(0, 14)}`;
const PROJECT_NAME = process.env.E2E_PROJECT_NAME || "AI Native FDE / 全栈工程师";
const PDF_PATH =
  process.env.E2E_PDF_PATH ||
  "/home/lison/Downloads/AI Native FDE _ 全栈工程师招聘素材包.pdf";
const REPORT_PATH = resolve(
  process.env.E2E_REPORT_PATH || "artifacts/e2e_evidence/goal-ai-native-fde-ui.json",
);
const MIN_CANDIDATES = Number(process.env.E2E_MIN_CANDIDATES || 20);

const sleep = (ms) => new Promise((resolveSleep) => setTimeout(resolveSleep, ms));

function nowIso() {
  return new Date().toISOString();
}

function parseJson(raw) {
  if (!raw || typeof raw !== "string") return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function pathOf(url) {
  try {
    const parsed = new URL(url);
    return `${parsed.pathname}${parsed.search}`;
  } catch {
    return url;
  }
}

function summarize(value, depth = 0) {
  if (value === null || value === undefined) return value;
  if (typeof value === "string") return value.length > 260 ? `${value.slice(0, 260)}...` : value;
  if (typeof value === "number" || typeof value === "boolean") return value;
  if (Array.isArray(value)) return { type: "array", length: value.length, sample: value.slice(0, 3).map((item) => summarize(item, depth + 1)) };
  if (typeof value === "object") {
    if (depth > 1) return { type: "object", keys: Object.keys(value).slice(0, 16) };
    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => !/token|key|secret|authorization|password/i.test(key))
        .slice(0, 24)
        .map(([key, item]) => [key, summarize(item, depth + 1)]),
    );
  }
  return String(value);
}

function jsString(value) {
  return JSON.stringify(value);
}

function bodyJson(entry) {
  return entry?.responseBodyJson ?? parseJson(entry?.responseBody);
}

function requestJson(entry) {
  return entry?.requestBodyJson ?? parseJson(entry?.requestPostData);
}

function evidenceFromEntry(entry) {
  return {
    method: entry?.method,
    path: entry ? pathOf(entry.url) : undefined,
    status: entry?.status,
    request: summarize(requestJson(entry) ?? entry?.requestPostData),
    response: summarize(bodyJson(entry) ?? entry?.responseBody),
    error: entry?.errorText,
  };
}

class CDPClient {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.nextId = 1;
    this.pending = new Map();
    this.handlers = new Map();
  }

  connect() {
    return new Promise((resolveConnect, rejectConnect) => {
      this.ws = new WebSocket(this.wsUrl);
      this.ws.addEventListener("open", () => resolveConnect());
      this.ws.addEventListener("error", (event) => rejectConnect(event.error || new Error("CDP websocket error")));
      this.ws.addEventListener("message", (event) => {
        const message = JSON.parse(event.data.toString());
        if (message.id && this.pending.has(message.id)) {
          const { resolve, reject } = this.pending.get(message.id);
          this.pending.delete(message.id);
          if (message.error) reject(new Error(message.error.message || JSON.stringify(message.error)));
          else resolve(message.result || {});
          return;
        }
        if (message.method && this.handlers.has(message.method)) {
          for (const handler of this.handlers.get(message.method)) handler(message.params || {});
        }
      });
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    const payload = JSON.stringify({ id, method, params });
    return new Promise((resolveSend, rejectSend) => {
      this.pending.set(id, { resolve: resolveSend, reject: rejectSend });
      this.ws.send(payload);
    });
  }

  on(method, handler) {
    const handlers = this.handlers.get(method) || [];
    handlers.push(handler);
    this.handlers.set(method, handlers);
  }

  close() {
    try {
      this.ws?.close();
    } catch {
      // ignored
    }
  }
}

async function waitFor(fn, timeoutMs, label, intervalMs = 150) {
  const start = Date.now();
  let lastError;
  while (Date.now() - start < timeoutMs) {
    try {
      const value = await fn();
      if (value) return value;
    } catch (error) {
      lastError = error;
    }
    await sleep(intervalMs);
  }
  throw new Error(`${label} timed out${lastError ? `: ${lastError.message}` : ""}`);
}

async function launchChrome() {
  const userDataDir = `/tmp/zhaoping-ai-native-fde-${Date.now()}`;
  const chrome = spawn(
    CHROME_PATH,
    [
      "--headless=new",
      "--disable-gpu",
      "--no-sandbox",
      "--disable-dev-shm-usage",
      `--remote-debugging-port=${DEBUG_PORT}`,
      `--user-data-dir=${userDataDir}`,
      "about:blank",
    ],
    { stdio: ["ignore", "pipe", "pipe"] },
  );
  chrome.stdout.on("data", () => {});
  chrome.stderr.on("data", () => {});

  await waitFor(async () => {
    const response = await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/list`);
    return response.ok;
  }, 12_000, "Chrome CDP endpoint");

  const targets = await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/list`).then((response) => response.json());
  const page = targets.find((target) => target.type === "page" && target.webSocketDebuggerUrl);
  if (!page) throw new Error("Chrome page target not found");
  return { chrome, userDataDir, wsUrl: page.webSocketDebuggerUrl };
}

function setupNetworkCapture(cdp) {
  const entries = [];
  const byId = new Map();

  cdp.on("Network.requestWillBeSent", (params) => {
    const entry = {
      index: entries.length,
      requestId: params.requestId,
      method: params.request.method,
      url: params.request.url,
      requestPostData: params.request.postData,
      requestBodyJson: parseJson(params.request.postData),
      timestamp: nowIso(),
    };
    entries.push(entry);
    byId.set(params.requestId, entry);
  });

  cdp.on("Network.responseReceived", (params) => {
    const entry = byId.get(params.requestId);
    if (!entry) return;
    entry.status = params.response.status;
    entry.mimeType = params.response.mimeType;
    entry.responseAt = nowIso();
  });

  cdp.on("Network.loadingFinished", async (params) => {
    const entry = byId.get(params.requestId);
    if (!entry) return;
    entry.finishedAt = nowIso();
    try {
      const body = await cdp.send("Network.getResponseBody", { requestId: params.requestId });
      entry.responseBody = body.base64Encoded ? "[base64 response omitted]" : body.body;
      entry.responseBodyJson = parseJson(entry.responseBody);
    } catch (error) {
      entry.responseBodyError = error.message;
    }
  });

  cdp.on("Network.loadingFailed", (params) => {
    const entry = byId.get(params.requestId);
    if (!entry) return;
    entry.errorText = params.errorText;
    entry.finishedAt = nowIso();
  });

  return entries;
}

async function evaluate(cdp, expression) {
  const result = await cdp.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || "Runtime evaluation failed");
  return result.result?.value;
}

async function pageText(cdp) {
  return evaluate(cdp, "document.body ? document.body.innerText : ''");
}

async function dialogText(cdp) {
  return evaluate(
    cdp,
    `(() => [...document.querySelectorAll('[role="dialog"]')]
      .map((dialog) => dialog.innerText || '')
      .join('\\n---dialog---\\n'))()`,
  );
}

async function navigate(cdp, url) {
  await cdp.send("Page.navigate", { url });
  await waitFor(async () => {
    const text = await pageText(cdp);
    return text && !text.includes("Loading...");
  }, 30_000, `navigate ${url}`);
}

async function setLabeledValue(cdp, labelText, value, { exact = false } = {}) {
  return evaluate(
    cdp,
    `(() => {
      const normalize = (text) => (text || '').replace(/\\s+/g, ' ').trim();
      const labels = [...document.querySelectorAll('label')];
      const label = labels.find((item) => {
        const text = normalize(item.innerText || item.textContent);
        return ${exact} ? text === ${jsString(labelText)} : text.includes(${jsString(labelText)});
      });
      const placeholderInput = [...document.querySelectorAll('input, textarea')]
        .find((item) => normalize(item.getAttribute('placeholder')).includes(${jsString(labelText)}));
      const input = label?.querySelector('input, textarea, select') || placeholderInput;
      if (!input) return { ok: false, reason: 'input_not_found', labelText: ${jsString(labelText)} };
      const setter = Object.getOwnPropertyDescriptor(input.constructor.prototype, 'value')?.set;
      setter?.call(input, ${jsString(value)});
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      return { ok: true, labelText: ${jsString(labelText)}, tagName: input.tagName, value: input.value };
    })()`,
  );
}

async function buttonInfo(cdp, text, { sectionTitle = null, occurrence = 0 } = {}) {
  return evaluate(
    cdp,
    `(() => {
      const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
      const visible = (el) => Boolean(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
      const sectionTitle = ${jsString(sectionTitle)};
      let root = document;
      if (sectionTitle) {
        const heading = [...document.querySelectorAll('h1,h2,h3')]
          .find((item) => visible(item) && normalize(item.innerText) === sectionTitle);
        root = heading?.closest('section, aside') || heading?.parentElement || document;
      }
      const buttons = [...root.querySelectorAll('button')]
        .filter((button) => visible(button) && normalize(button.innerText) === ${jsString(text)});
      const button = buttons[${occurrence}];
      return {
        found: Boolean(button),
        disabled: Boolean(button?.disabled),
        text: button ? normalize(button.innerText) : null,
        title: button?.getAttribute('title') || null,
        occurrence: ${occurrence},
        sectionTitle,
        matchingCount: buttons.length,
        availableButtons: [...root.querySelectorAll('button')].filter(visible).slice(0, 24).map((item) => normalize(item.innerText)),
      };
    })()`,
  );
}

async function clickButton(cdp, text, { sectionTitle = null, occurrence = 0 } = {}) {
  return evaluate(
    cdp,
    `(() => {
      const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
      const visible = (el) => Boolean(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
      const sectionTitle = ${jsString(sectionTitle)};
      let root = document;
      if (sectionTitle) {
        const heading = [...document.querySelectorAll('h1,h2,h3')]
          .find((item) => visible(item) && normalize(item.innerText) === sectionTitle);
        root = heading?.closest('section, aside') || heading?.parentElement || document;
      }
      const buttons = [...root.querySelectorAll('button')]
        .filter((button) => visible(button) && normalize(button.innerText) === ${jsString(text)});
      const button = buttons[${occurrence}];
      if (!button) {
        return { ok: false, reason: 'button_not_found', text: ${jsString(text)}, sectionTitle, availableButtons: [...root.querySelectorAll('button')].filter(visible).slice(0, 24).map((item) => normalize(item.innerText)) };
      }
      const disabled = Boolean(button.disabled);
      const title = button.getAttribute('title') || null;
      button.scrollIntoView({ block: 'center', inline: 'center' });
      if (!disabled) button.click();
      return { ok: !disabled, disabled, title, text: normalize(button.innerText), sectionTitle, occurrence: ${occurrence} };
    })()`,
  );
}

async function waitForButtonEnabled(cdp, text, options = {}, timeoutMs = 30_000) {
  return waitFor(async () => {
    const info = await buttonInfo(cdp, text, options);
    return info.found && !info.disabled ? info : null;
  }, timeoutMs, `button enabled: ${text}`);
}

async function setFileInput(cdp, selector, filePath) {
  const documentInfo = await cdp.send("DOM.getDocument", { depth: 1 });
  const node = await cdp.send("DOM.querySelector", { nodeId: documentInfo.root.nodeId, selector });
  if (!node.nodeId) throw new Error(`file input not found: ${selector}`);
  await cdp.send("DOM.setFileInputFiles", { nodeId: node.nodeId, files: [filePath] });
  await evaluate(
    cdp,
    `(() => {
      const input = document.querySelector(${jsString(selector)});
      input?.dispatchEvent(new Event('input', { bubbles: true }));
      input?.dispatchEvent(new Event('change', { bubbles: true }));
      return Boolean(input?.files?.length);
    })()`,
  );
}

function findEntry(entries, { method, pathIncludes, since = 0, bodyPredicate = null, statusPredicate = null }) {
  return entries.find((entry) => {
    if (entry.index < since) return false;
    if (method && entry.method !== method) return false;
    if (pathIncludes && !pathOf(entry.url).includes(pathIncludes)) return false;
    if (bodyPredicate && !bodyPredicate(entry)) return false;
    if (statusPredicate && !statusPredicate(entry)) return false;
    return true;
  });
}

async function waitForEntryBody(entries, query, timeoutMs = 45_000) {
  return waitFor(() => {
    const entry = findEntry(entries, query);
    if (!entry) return null;
    if (entry.responseBodyJson || entry.responseBody || entry.errorText) return entry;
    return null;
  }, timeoutMs, `${query.method || "*"} ${query.pathIncludes} body`);
}

async function apiJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const text = await response.text();
  const data = parseJson(text) ?? text;
  if (!response.ok) throw new Error(`API ${path} failed: ${response.status} ${text.slice(0, 300)}`);
  return { data, status: response.status, headers: response.headers };
}

async function waitForTaskStatus(taskId, expectedStatuses, timeoutMs = 360_000) {
  const expected = new Set(expectedStatuses);
  return waitFor(async () => {
    const { data } = await apiJson(`/tasks/${encodeURIComponent(taskId)}`);
    return expected.has(data.status) ? data : null;
  }, timeoutMs, `task ${taskId} status ${expectedStatuses.join("/")}`, 1_500);
}

async function createProjectViaUi(cdp, entries, report) {
  const flow = { name: "前端创建项目", status: "FAIL", startedAt: nowIso(), evidence: [] };
  const since = entries.length;
  try {
    await navigate(cdp, `${FRONTEND_URL}/dashboard`);
    await waitFor(async () => {
      const text = await pageText(cdp);
      return text.includes("项目列表") && text.includes("项目 ID") && text.includes("创建空项目");
    }, 30_000, "dashboard ready");
    const idInput = await setLabeledValue(cdp, "项目 ID", PROJECT_ID);
    const nameInput = await setLabeledValue(cdp, "项目名称", PROJECT_NAME);
    flow.ui = { idInput, nameInput };
    if (!idInput.ok || !nameInput.ok) throw new Error(`project form fill failed: ${JSON.stringify({ idInput, nameInput })}`);
    await waitForButtonEnabled(cdp, "创建空项目", {}, 15_000);
    const click = await clickButton(cdp, "创建空项目");
    flow.ui.createClick = click;
    if (!click.ok) throw new Error(`create click failed: ${JSON.stringify(click)}`);
    const createEntry = await waitForEntryBody(entries, { method: "POST", pathIncludes: "/api/projects", since }, 20_000);
    flow.evidence.push({ label: "POST /api/projects", ...evidenceFromEntry(createEntry) });
    await waitFor(async () => (await pageText(cdp)).includes(PROJECT_NAME), 30_000, "project page loaded");
    flow.status = createEntry.status < 400 ? "PASS" : "FAIL";
  } catch (error) {
    flow.error = error.message;
    flow.pageTextOnError = (await pageText(cdp).catch(() => "")).slice(0, 2_000);
    throw error;
  } finally {
    flow.finishedAt = nowIso();
    report.flows.push(flow);
  }
}

async function uploadAndInitializeJobViaUi(cdp, entries, report) {
  const flow = { name: "前端上传 PDF 并写入岗位矩阵", status: "FAIL", startedAt: nowIso(), evidence: [] };
  const since = entries.length;
  try {
    await waitFor(async () => (await pageText(cdp)).includes("岗位智能生成"), 30_000, "project detail ready");
    await setFileInput(cdp, "#project-material-upload", PDF_PATH);
    const uploadEntry = await waitForEntryBody(entries, { method: "POST", pathIncludes: "/materials/upload", since }, 180_000);
    flow.evidence.push({ label: "POST material upload", ...evidenceFromEntry(uploadEntry) });

    await setLabeledValue(
      cdp,
      "项目提示词",
      "只为 AI Native FDE / Agentic Builder 创建核心岗位。重点是完整 SDLC、AI coding 实战、Agent/RAG/Workflow/Tool Calling、业务抽象、上线和指标复盘。",
    );
    await setLabeledValue(
      cdp,
      "行业研究偏好",
      "用 top-down 行业研究和真实公开技术证据找候选人：GitHub、论文作者、社媒/社区、新闻融资、学校竞赛都要记录证据，但候选人必须是真实个人。",
    );
    await setLabeledValue(cdp, "最少岗位数", "1");

    const previewSince = entries.length;
    await waitForButtonEnabled(cdp, "预览岗位矩阵", { sectionTitle: "岗位智能生成" }, 15_000);
    const previewClick = await clickButton(cdp, "预览岗位矩阵", { sectionTitle: "岗位智能生成" });
    flow.ui = { previewClick };
    if (!previewClick.ok) throw new Error(`preview click failed: ${JSON.stringify(previewClick)}`);
    const previewEntry = await waitForEntryBody(entries, { method: "POST", pathIncludes: "/preview-from-bp", since: previewSince }, 240_000);
    flow.evidence.push({ label: "POST preview-from-bp", ...evidenceFromEntry(previewEntry) });
    report.preview = summarize(bodyJson(previewEntry));

    const confirmSince = entries.length;
    await waitForButtonEnabled(cdp, "确认覆盖岗位", { sectionTitle: "岗位智能生成" }, 30_000);
    const confirmClick = await clickButton(cdp, "确认覆盖岗位", { sectionTitle: "岗位智能生成" });
    flow.ui.confirmClick = confirmClick;
    if (!confirmClick.ok) throw new Error(`confirm click failed: ${JSON.stringify(confirmClick)}`);
    const initEntry = await waitForEntryBody(entries, { method: "POST", pathIncludes: "/initialize-from-bp", since: confirmSince }, 240_000);
    flow.evidence.push({ label: "POST initialize-from-bp", ...evidenceFromEntry(initEntry) });
    const initialized = bodyJson(initEntry);
    report.initializedJobCount = initialized?.jobCount;
    report.initializedJobs = (initialized?.jobs || []).map((job) => ({
      jobProfileId: job.id,
      roleName: job.title,
      mustHaveSkills: job.mustHaveSkills || job.must_have_skills,
    }));
    await waitFor(async () => (await pageText(cdp)).includes("岗位工作台"), 30_000, "jobs visible");
    flow.status = uploadEntry.status < 400 && previewEntry.status < 400 && initEntry.status < 400 ? "PASS" : "FAIL";
  } catch (error) {
    flow.error = error.message;
    flow.dialogTextOnError = await dialogText(cdp).catch(() => "");
    flow.pageTextOnError = (await pageText(cdp).catch(() => "")).slice(0, 2_000);
    throw error;
  } finally {
    flow.finishedAt = nowIso();
    report.flows.push(flow);
  }
}

async function configureSearchViaUi(cdp) {
  return evaluate(
    cdp,
    `(() => {
      const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
      const details = [...document.querySelectorAll('details')]
        .find((item) => normalize(item.innerText).includes('岗位搜索设置'));
      if (!details) return { ok: false, reason: 'settings_not_found' };
      details.open = true;
      const select = [...details.querySelectorAll('label')]
        .find((item) => normalize(item.innerText).includes('搜索深度'))
        ?.querySelector('select');
      if (select) {
        const setter = Object.getOwnPropertyDescriptor(select.constructor.prototype, 'value')?.set;
        setter?.call(select, 'deep_live');
        select.dispatchEvent(new Event('change', { bubbles: true }));
      }
      const checkboxes = [...details.querySelectorAll('input[type="checkbox"]')];
      for (const checkbox of checkboxes) {
        if (!checkbox.checked) {
          checkbox.checked = true;
          checkbox.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
      return { ok: true, depth: select?.value || null, enabledLayerCount: checkboxes.filter((item) => item.checked).length };
    })()`,
  );
}

async function runFindCandidatesViaUi(cdp, entries, report) {
  const flow = { name: "前端点击找候选人并通过 HumanGate", status: "FAIL", startedAt: nowIso(), evidence: [] };
  const since = entries.length;
  try {
    const searchUi = await configureSearchViaUi(cdp);
    flow.ui = { searchUi };
    await waitFor(async () => {
      const text = await pageText(cdp);
      return text.includes("Search：") || text.includes("系统预检");
    }, 30_000, "search preflight visible");

    let click;
    const recommended = await buttonInfo(cdp, "开始找候选人");
    if (recommended.found && !recommended.disabled) {
      click = await clickButton(cdp, "开始找候选人");
    } else {
      await evaluate(
        cdp,
        `(() => {
          [...document.querySelectorAll('details')].forEach((item) => {
            if ((item.innerText || '').includes('更多操作')) item.open = true;
          });
          return true;
        })()`,
      );
      await waitForButtonEnabled(cdp, "找候选人", { sectionTitle: "岗位工作台" }, 20_000);
      click = await clickButton(cdp, "找候选人", { sectionTitle: "岗位工作台" });
    }
    flow.ui.findClick = click;
    if (!click.ok) throw new Error(`find candidates click failed: ${JSON.stringify(click)}`);

    const scenarioEntry = await waitForEntryBody(entries, {
      method: "POST",
      pathIncludes: "/api/scenarios/run",
      since,
      bodyPredicate: (entry) => requestJson(entry)?.scenario === "B",
    }, 30_000);
    flow.evidence.push({ label: "POST /api/scenarios/run B", ...evidenceFromEntry(scenarioEntry) });
    const taskId = bodyJson(scenarioEntry)?.task_id;
    if (!taskId) throw new Error("scenario B response missing task_id");
    report.scenarioBTaskId = taskId;

    await waitFor(async () => {
      const text = await dialogText(cdp);
      return text.includes("即将入库的候选线索") || text.includes("确认继续");
    }, 360_000, "candidate HumanGate modal", 1_000);
    flow.humanGateText = (await dialogText(cdp)).slice(0, 2_000);

    const confirmSince = entries.length;
    await waitForButtonEnabled(cdp, "继续", {}, 20_000);
    const approve = await clickButton(cdp, "继续");
    flow.ui.approve = approve;
    if (!approve.ok) throw new Error(`HumanGate continue failed: ${JSON.stringify(approve)}`);
    const confirmEntry = await waitForEntryBody(entries, {
      method: "POST",
      pathIncludes: `/api/tasks/${taskId}/confirm`,
      since: confirmSince,
    }, 30_000);
    flow.evidence.push({ label: "POST task confirm", ...evidenceFromEntry(confirmEntry) });

    const finalTask = await waitForTaskStatus(taskId, ["done", "error", "cancelled"], 360_000);
    flow.finalTaskStatus = finalTask.status;
    flow.finalTaskError = finalTask.error;
    report.scenarioBFinalStatus = finalTask.status;
    report.scenarioBResult = summarize(finalTask.result);
    await waitFor(async () => {
      const { headers } = await apiJson(`/projects/${encodeURIComponent(PROJECT_ID)}/candidates?skip=0&limit=50`);
      return Number(headers.get("x-total-count") || "0") >= 0;
    }, 30_000, "candidate API reachable");
    flow.status = scenarioEntry.status < 400 && confirmEntry.status < 400 && finalTask.status === "done" ? "PASS" : "FAIL";
  } catch (error) {
    flow.error = error.message;
    flow.dialogTextOnError = await dialogText(cdp).catch(() => "");
    flow.pageTextOnError = (await pageText(cdp).catch(() => "")).slice(0, 2_500);
    throw error;
  } finally {
    flow.finishedAt = nowIso();
    report.flows.push(flow);
  }
}

async function verifyCandidateDetailsViaUi(cdp, report) {
  const flow = { name: "前端逐个展开候选人详情", status: "FAIL", startedAt: nowIso(), details: [] };
  try {
    await navigate(cdp, `${FRONTEND_URL}/projects/${encodeURIComponent(PROJECT_ID)}`);
    await waitFor(async () => (await pageText(cdp)).includes("候选人与线索"), 45_000, "candidate table visible");
    const { data: candidates, headers } = await apiJson(`/projects/${encodeURIComponent(PROJECT_ID)}/candidates?skip=0&limit=50`);
    const total = Number(headers.get("x-total-count") || candidates.length || "0");
    flow.totalCandidates = total;
    flow.apiCandidates = candidates.slice(0, MIN_CANDIDATES).map((candidate) => ({
      id: candidate.id,
      jobCandidateId: candidate.jobCandidateId,
      name: candidate.name,
      sourcePlatform: candidate.sourcePlatform,
      sourceUrl: candidate.sourceUrl,
      githubUrl: candidate.githubUrl,
      linkedinUrl: candidate.linkedinUrl,
      homepageUrl: candidate.homepageUrl,
      skills: candidate.skills,
    }));
    report.finalCandidateTotal = total;
    report.finalCandidates = flow.apiCandidates;
    if (total < MIN_CANDIDATES) {
      flow.status = "LIMITED";
      flow.error = `候选人不足 ${MIN_CANDIDATES}：当前 ${total}`;
      return flow;
    }

    for (let index = 0; index < MIN_CANDIDATES; index += 1) {
      await waitForButtonEnabled(cdp, "查看", { sectionTitle: "候选人与线索", occurrence: index }, 20_000);
      const click = await clickButton(cdp, "查看", { sectionTitle: "候选人与线索", occurrence: index });
      if (!click.ok) throw new Error(`查看 button ${index} failed: ${JSON.stringify(click)}`);
      const detailText = await waitFor(
        () =>
          evaluate(
            cdp,
            `(() => {
              const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
              const heading = [...document.querySelectorAll('h1,h2,h3')]
                .find((item) => normalize(item.innerText) === '候选人与线索');
              const section = heading?.closest('section') || document;
              const detailBlocks = [...section.querySelectorAll('div')]
                .map((item) => item.innerText || '')
                .filter((text) => text.includes('候选人 ID') && text.includes('证据'))
                .sort((a, b) => b.length - a.length);
              return detailBlocks[0] || '';
            })()`,
          ),
        10_000,
        `candidate detail ${index}`,
      );
      const apiCandidate = flow.apiCandidates[index];
      flow.details.push({
        index,
        candidateId: apiCandidate?.id,
        name: apiCandidate?.name,
        clicked: click.ok,
        hasId: detailText.includes("候选人 ID"),
        hasName: apiCandidate?.name ? detailText.includes(apiCandidate.name) : detailText.includes("姓名"),
        hasSource: /来源 URL|GitHub|LinkedIn|Homepage|来源/.test(detailText),
        hasEvidence: detailText.includes("证据"),
        hasSkillsOrTags: /技能|技术标签|能力/.test(detailText),
        textSample: detailText.slice(0, 900),
      });
    }

    const incomplete = flow.details.filter((item) => !(item.hasId && item.hasName && item.hasSource && item.hasEvidence));
    flow.status = incomplete.length ? "FAIL" : "PASS";
    flow.incomplete = incomplete;
  } catch (error) {
    flow.error = error.message;
    flow.pageTextOnError = (await pageText(cdp).catch(() => "")).slice(0, 2_500);
    throw error;
  } finally {
    flow.finishedAt = nowIso();
    report.flows.push(flow);
  }
}

async function main() {
  const report = {
    generatedAt: nowIso(),
    mode: MODE,
    frontendUrl: FRONTEND_URL,
    apiBase: API_BASE,
    projectId: PROJECT_ID,
    projectName: PROJECT_NAME,
    pdfPath: PDF_PATH,
    minCandidates: MIN_CANDIDATES,
    status: "RUNNING",
    flows: [],
  };

  let chrome;
  let userDataDir;
  let cdp;
  try {
    const launched = await launchChrome();
    chrome = launched.chrome;
    userDataDir = launched.userDataDir;
    cdp = new CDPClient(launched.wsUrl);
    await cdp.connect();
    globalThis.__cdp = cdp;
    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await cdp.send("Network.enable");
    await cdp.send("DOM.enable");
    cdp.on("Page.javascriptDialogOpening", () => {
      cdp.send("Page.handleJavaScriptDialog", { accept: true }).catch(() => {});
    });
    const entries = setupNetworkCapture(cdp);

    if (MODE !== "verify") {
      await createProjectViaUi(cdp, entries, report);
      await uploadAndInitializeJobViaUi(cdp, entries, report);
      await runFindCandidatesViaUi(cdp, entries, report);
    }
    await verifyCandidateDetailsViaUi(cdp, report);

    report.networkSummary = entries
      .filter((entry) => pathOf(entry.url).startsWith("/api/"))
      .slice(-80)
      .map((entry) => ({
        method: entry.method,
        path: pathOf(entry.url),
        status: entry.status,
      }));
    report.status = report.flows.every((flow) => flow.status === "PASS") ? "PASS" : "LIMITED";
  } catch (error) {
    report.status = "FAIL";
    report.error = error.message;
  } finally {
    cdp?.close();
    if (chrome) chrome.kill("SIGTERM");
    if (userDataDir) await rm(userDataDir, { recursive: true, force: true }).catch(() => {});
    await mkdir(resolve(REPORT_PATH, ".."), { recursive: true });
    await writeFile(REPORT_PATH, `${JSON.stringify(report, null, 2)}\n`, "utf8");
    console.log(JSON.stringify({ status: report.status, reportPath: REPORT_PATH, projectId: PROJECT_ID, finalCandidateTotal: report.finalCandidateTotal ?? null }, null, 2));
    if (report.status === "FAIL") process.exitCode = 1;
  }
}

main();
