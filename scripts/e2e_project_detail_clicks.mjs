#!/usr/bin/env node
import { mkdir, rm, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { spawn } from "node:child_process";
import process from "node:process";

const APP_URL = process.env.E2E_APP_URL || "http://127.0.0.1:5175/projects/project_2026_ai_team";
const API_BASE = process.env.E2E_API_BASE || "http://127.0.0.1:8011";
const CHROME_PATH = process.env.CHROME_PATH || "/usr/bin/google-chrome";
const DEBUG_PORT = Number(process.env.E2E_CHROME_PORT || 9223);
const REPORT_PATH = resolve(process.env.E2E_REPORT_PATH || "data/runtime/e2e_project_detail_report.json");
const PROJECT_ID = process.env.E2E_PROJECT_ID || "project_2026_ai_team";
const PROJECT_TITLE = process.env.E2E_PROJECT_TITLE || "2026 AI 团队招聘";

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

function summarize(value, depth = 0) {
  if (value === null || value === undefined) return value;
  if (typeof value === "string") return value.length > 240 ? `${value.slice(0, 240)}...` : value;
  if (typeof value === "number" || typeof value === "boolean") return value;
  if (Array.isArray(value)) {
    return {
      type: "array",
      length: value.length,
      sample: value.slice(0, 2).map((item) => summarize(item, depth + 1)),
    };
  }
  if (typeof value === "object") {
    if (depth > 1) return { type: "object", keys: Object.keys(value).slice(0, 12) };
    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => !/token|key|secret|authorization|password/i.test(key))
        .slice(0, 18)
        .map(([key, item]) => [key, summarize(item, depth + 1)]),
    );
  }
  return String(value);
}

function pathOf(url) {
  try {
    const parsed = new URL(url);
    return `${parsed.pathname}${parsed.search}`;
  } catch {
    return url;
  }
}

function bodyJson(entry) {
  return entry?.responseBodyJson ?? parseJson(entry?.responseBody);
}

function requestJson(entry) {
  return entry?.requestBodyJson ?? parseJson(entry?.requestPostData);
}

function scenarioBodyPredicate(scenario) {
  return (entry) => requestJson(entry)?.scenario === scenario;
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

async function waitFor(fn, timeoutMs, label, intervalMs = 100) {
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
  const userDataDir = `/tmp/zhaoping-e2e-chrome-${Date.now()}`;
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

  await waitFor(
    async () => {
      const response = await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/list`);
      return response.ok;
    },
    10_000,
    "Chrome CDP endpoint",
  );
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
    entry.responseHeaders = params.response.headers;
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
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.text || "Runtime evaluation failed");
  }
  return result.result?.value;
}

function jsString(value) {
  return JSON.stringify(value);
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
        availableButtons: buttons.slice(0, 8).map((item) => normalize(item.innerText)),
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
        return {
          ok: false,
          reason: 'button_not_found',
          text: ${jsString(text)},
          sectionTitle,
          availableButtons: [...root.querySelectorAll('button')].filter(visible).slice(0, 16).map((item) => normalize(item.innerText)),
        };
      }
      const disabled = Boolean(button.disabled);
      const title = button.getAttribute('title') || null;
      button.scrollIntoView({ block: 'center', inline: 'center' });
      if (!disabled) button.click();
      return { ok: !disabled, disabled, title, text: normalize(button.innerText), sectionTitle };
    })()`,
  );
}

async function setFirstTextInput(cdp, labelText, value) {
  return evaluate(
    cdp,
    `(() => {
      const normalize = (text) => (text || '').replace(/\\s+/g, ' ').trim();
      const labels = [...document.querySelectorAll('label')];
      const label = labels.find((item) => normalize(item.innerText).includes(${jsString(labelText)}));
      const input = label?.querySelector('input, textarea');
      if (!input) return { ok: false, reason: 'input_not_found', labelText: ${jsString(labelText)} };
      const setter = Object.getOwnPropertyDescriptor(input.constructor.prototype, 'value')?.set;
      setter?.call(input, ${jsString(value)});
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      return { ok: true, labelText: ${jsString(labelText)} };
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

async function waitForEntry(entries, query, timeoutMs = 20_000) {
  return waitFor(
    () => findEntry(entries, query),
    timeoutMs,
    `${query.method || "*"} ${query.pathIncludes}`,
  );
}

async function waitForEntryBody(entries, query, timeoutMs = 20_000) {
  return waitFor(
    () => {
      const entry = findEntry(entries, query);
      if (!entry) return null;
      if (entry.responseBodyJson || entry.responseBody || entry.errorText) return entry;
      if (entry.status && pathOf(entry.url).includes("/stream")) return entry;
      return null;
    },
    timeoutMs,
    `${query.method || "*"} ${query.pathIncludes} body`,
  );
}

async function waitForButtonEnabled(cdp, text, options, timeoutMs = 15_000) {
  return waitFor(
    async () => {
      const info = await buttonInfo(cdp, text, options);
      return info.found && !info.disabled ? info : null;
    },
    timeoutMs,
    `button enabled: ${text}`,
  );
}

async function waitForButtonSettled(cdp, text, options, timeoutMs = 10_000) {
  return waitFor(
    async () => {
      const info = await buttonInfo(cdp, text, options);
      if (!info.found) return null;
      return info.title?.includes("加载中") ? null : info;
    },
    timeoutMs,
    `button settled: ${text}`,
  ).catch(() => null);
}

async function waitForCapabilitiesReady(cdp) {
  return waitFor(
    async () => {
      const text = await pageText(cdp);
      return text.includes("后端能力状态") && text.includes("Search：") && text.includes("LLM：");
    },
    12_000,
    "capability status UI",
  );
}

async function closeTaskPanel(cdp) {
  const info = await buttonInfo(cdp, "×");
  if (info.found && !info.disabled) await clickButton(cdp, "×");
}

async function recordScenarioFlow({ cdp, entries, report, name, scenario, button, sectionTitle, occurrence = 0, verifyTaskControls = false }) {
  const flow = {
    name,
    status: "FAIL",
    startedAt: nowIso(),
    ui: { button, sectionTitle, occurrence },
    evidence: [],
    notes: [],
  };
  const since = entries.length;
  try {
    await waitForButtonSettled(cdp, button, { sectionTitle, occurrence });
    const click = await clickButton(cdp, button, { sectionTitle, occurrence });
    flow.ui.click = click;
    if (!click.ok) {
      flow.status = click.disabled ? "LIMITED" : "FAIL";
      flow.notes.push(click.disabled ? `按钮被禁用：${click.title || "无 title"}` : `未找到按钮：${JSON.stringify(click.availableButtons || [])}`);
      return flow;
    }
    const scenarioEntry = await waitForEntryBody(entries, {
      method: "POST",
      pathIncludes: "/api/scenarios/run",
      since,
      bodyPredicate: scenarioBodyPredicate(scenario),
    });
    flow.evidence.push({ label: `POST /api/scenarios/run scenario ${scenario}`, ...evidenceFromEntry(scenarioEntry) });
    const response = bodyJson(scenarioEntry);
    if (!response?.task_id) throw new Error(`scenario ${scenario} response missing task_id`);
    flow.taskId = response.task_id;
    report.createdTaskIds.push(response.task_id);
    const streamEntry = await waitForEntry(entries, {
      method: "GET",
      pathIncludes: `/api/tasks/${response.task_id}/stream`,
      since,
    }, 10_000);
    flow.evidence.push({ label: "GET task stream", ...evidenceFromEntry(streamEntry) });

    if (verifyTaskControls) {
      const control = await verifyTaskControlButtons(cdp, entries, response.task_id);
      flow.taskControls = control;
      flow.evidence.push(...control.evidence);
      if (control.createdRetryTaskId) report.createdTaskIds.push(control.createdRetryTaskId);
    }

    flow.status = flow.evidence.every((item) => !item.status || item.status < 400) ? "PASS" : "FAIL";
  } catch (error) {
    flow.error = error.message;
    flow.dialogTextOnError = await dialogText(cdp).catch(() => "");
    flow.pageTextOnError = (await pageText(cdp).catch(() => "")).slice(0, 2_000);
  } finally {
    flow.finishedAt = nowIso();
    await closeTaskPanel(cdp);
    report.flows.push(flow);
  }
  return flow;
}

async function verifyTaskControlButtons(cdp, entries, taskId) {
  const result = { status: "LIMITED", evidence: [], notes: [] };
  try {
    const cancelInfo = await buttonInfo(cdp, "取消任务");
    if (cancelInfo.found && !cancelInfo.disabled) {
      const sinceCancel = entries.length;
      await clickButton(cdp, "取消任务");
      const cancelEntry = await waitForEntryBody(entries, {
        method: "POST",
        pathIncludes: `/api/tasks/${taskId}/cancel`,
        since: sinceCancel,
      }, 10_000);
      result.evidence.push({ label: "POST task cancel", ...evidenceFromEntry(cancelEntry) });
      result.status = cancelEntry.status < 400 ? "PASS" : "FAIL";
      await sleep(350);
    } else {
      result.notes.push(cancelInfo.found ? "取消任务按钮当前不可用，任务可能已进入终态" : "未找到取消任务按钮");
    }

    const retryInfo = await buttonInfo(cdp, "重试任务");
    if (retryInfo.found && !retryInfo.disabled) {
      const sinceRetry = entries.length;
      await clickButton(cdp, "重试任务");
      const retryEntry = await waitForEntryBody(entries, {
        method: "POST",
        pathIncludes: `/api/tasks/${taskId}/retry`,
        since: sinceRetry,
      }, 10_000);
      result.evidence.push({ label: "POST task retry", ...evidenceFromEntry(retryEntry) });
      result.createdRetryTaskId = bodyJson(retryEntry)?.task_id;
      result.status = retryEntry.status < 400 ? "PASS" : "FAIL";
    } else {
      result.notes.push(retryInfo.found ? "重试任务按钮当前不可用，任务尚未进入终态" : "未找到重试任务按钮");
    }
  } catch (error) {
    result.status = "FAIL";
    result.error = error.message;
  }
  return result;
}

async function verifyCandidateHumanGate(cdp, entries, report) {
  const flow = {
    name: "候选人评估 + 任务 HumanGate 确认",
    status: "FAIL",
    startedAt: nowIso(),
    evidence: [],
    notes: [],
  };
  const since = entries.length;
  try {
    const initialCandidatesEntry = findEntry(entries, {
      method: "GET",
      pathIncludes: `/api/projects/${PROJECT_ID}/candidates`,
    });
    const firstCandidate = bodyJson(initialCandidatesEntry)?.[0];
    if (firstCandidate) {
      report.cleanup.candidateLinks.push({
        candidateId: firstCandidate.id,
        jobId: firstCandidate.jobId,
        matchScore: firstCandidate.matchScore,
        pipelineStatus: firstCandidate.pipelineStatus,
      });
    }

    await waitForButtonSettled(cdp, "候选人评估", { sectionTitle: "候选人名单", occurrence: 0 });
    const click = await clickButton(cdp, "候选人评估", { sectionTitle: "候选人名单", occurrence: 0 });
    flow.ui = { click };
    if (!click.ok) {
      flow.status = click.disabled ? "LIMITED" : "FAIL";
      flow.notes.push(click.disabled ? `按钮被禁用：${click.title || "无 title"}` : "候选人评估按钮不存在");
      return flow;
    }

    const scenarioEntry = await waitForEntryBody(entries, {
      method: "POST",
      pathIncludes: "/api/scenarios/run",
      since,
      bodyPredicate: scenarioBodyPredicate("C"),
    });
    flow.evidence.push({ label: "POST /api/scenarios/run scenario C candidate", ...evidenceFromEntry(scenarioEntry) });
    const taskId = bodyJson(scenarioEntry)?.task_id;
    if (!taskId) throw new Error("candidate evaluation response missing task_id");
    flow.taskId = taskId;
    report.createdTaskIds.push(taskId);

    const streamEntry = await waitForEntry(entries, {
      method: "GET",
      pathIncludes: `/api/tasks/${taskId}/stream`,
      since,
    }, 10_000);
    flow.evidence.push({ label: "GET task stream", ...evidenceFromEntry(streamEntry) });

    await waitFor(
      async () => {
        const text = await dialogText(cdp);
        return text.includes("人工确认");
      },
      12_000,
      "HumanGate modal",
    );
    flow.humanGateModal = "opened";

    const sinceConfirm = entries.length;
    const approve = await clickButton(cdp, "通过");
    flow.ui.approve = approve;
    if (!approve.ok) throw new Error(`HumanGate approve click failed: ${approve.reason || approve.title || "unknown"}`);
    const confirmEntry = await waitForEntryBody(entries, {
      method: "POST",
      pathIncludes: `/api/tasks/${taskId}/confirm`,
      since: sinceConfirm,
    }, 12_000);
    flow.evidence.push({ label: "POST task confirm", ...evidenceFromEntry(confirmEntry) });

    const finalSnapshot = await waitForEntryBody(entries, {
      method: "GET",
      pathIncludes: `/api/tasks/${taskId}`,
      since,
    }, 12_000).catch(() => null);
    if (finalSnapshot) flow.evidence.push({ label: "GET task snapshot", ...evidenceFromEntry(finalSnapshot) });
    flow.status = confirmEntry.status < 400 ? "PASS" : "FAIL";
  } catch (error) {
    flow.error = error.message;
    flow.dialogTextOnError = await dialogText(cdp).catch(() => "");
    flow.pageTextOnError = (await pageText(cdp).catch(() => "")).slice(0, 2_000);
  } finally {
    flow.finishedAt = nowIso();
    await closeTaskPanel(cdp);
    report.flows.push(flow);
  }
  return flow;
}

async function verifyOutreach(cdp, entries, report) {
  const flow = {
    name: "邮件触达闭环：后端草稿 + 人工确认 + 模拟发送记录",
    status: "FAIL",
    startedAt: nowIso(),
    evidence: [],
    notes: [],
  };
  const since = entries.length;
  try {
    await waitForButtonSettled(cdp, "生成草稿", { sectionTitle: "候选人名单", occurrence: 0 });
    const click = await clickButton(cdp, "生成草稿", { sectionTitle: "候选人名单", occurrence: 0 });
    flow.ui = { click };
    if (!click.ok) {
      flow.status = click.disabled ? "LIMITED" : "FAIL";
      flow.notes.push(click.disabled ? `按钮被禁用：${click.title || "无 title"}` : "生成草稿按钮不存在");
      return flow;
    }

    const draftEntry = await waitForEntryBody(entries, {
      method: "POST",
      pathIncludes: "/api/outreach/draft",
      since,
    }, 12_000);
    flow.evidence.push({ label: "POST outreach draft", ...evidenceFromEntry(draftEntry) });
    const draft = bodyJson(draftEntry);
    if (!draft?.draftId) throw new Error("outreach draft response missing draftId");
    report.cleanup.outreachDraftIds.push(draft.draftId);

    const historyGet = await waitForEntryBody(entries, {
      method: "GET",
      pathIncludes: "/api/outreach/history",
      since,
    }, 12_000).catch(() => null);
    if (historyGet) flow.evidence.push({ label: "GET outreach history", ...evidenceFromEntry(historyGet) });

    await waitForButtonEnabled(cdp, "确认草稿", { sectionTitle: "邮件草稿" }, 12_000);
    await setFirstTextInput(cdp, "主题", `E2E 自动验证主题 ${Date.now()}`);
    const openConfirm = await clickButton(cdp, "确认草稿", { sectionTitle: "邮件草稿" });
    flow.ui.openConfirm = openConfirm;

    await waitFor(
      async () => {
        const text = await dialogText(cdp);
        return text.includes("人工确认");
      },
      8_000,
      "outreach HumanGate modal",
    );

    const sinceApprove = entries.length;
    const approve = await clickButton(cdp, "通过");
    flow.ui.approve = approve;
    const patchEntry = await waitForEntryBody(entries, {
      method: "PATCH",
      pathIncludes: `/api/outreach/drafts/${draft.draftId}`,
      since: sinceApprove,
    }, 12_000);
    flow.evidence.push({ label: "PATCH outreach draft", ...evidenceFromEntry(patchEntry) });
    const sendEntry = await waitForEntryBody(entries, {
      method: "POST",
      pathIncludes: "/api/outreach/send",
      since: sinceApprove,
    }, 12_000);
    flow.evidence.push({ label: "POST outreach send", ...evidenceFromEntry(sendEntry) });
    const send = bodyJson(sendEntry);
    if (send?.historyId) report.cleanup.outreachHistoryIds.push(send.historyId);
    const body = await pageText(cdp);
    if (body.includes("已发送成功")) {
      throw new Error("UI displayed forbidden real-send success text");
    }
    flow.status = draftEntry.status < 400 && patchEntry.status < 400 && sendEntry.status < 400 ? "PASS" : "FAIL";
    flow.deliveryMode = send?.deliveryMode;
  } catch (error) {
    flow.error = error.message;
    flow.dialogTextOnError = await dialogText(cdp).catch(() => "");
    flow.pageTextOnError = (await pageText(cdp).catch(() => "")).slice(0, 2_000);
  } finally {
    flow.finishedAt = nowIso();
    report.flows.push(flow);
  }
  return flow;
}

async function verifySegments(cdp, entries, report) {
  const flow = {
    name: "人群筛选闭环：后端查询 + 保存能力门控",
    status: "FAIL",
    startedAt: nowIso(),
    evidence: [],
    notes: [],
  };
  const since = entries.length;
  try {
    const click = await clickButton(cdp, "查询目标人群", { sectionTitle: "筛选条件" });
    flow.ui = { query: click };
    if (!click.ok) throw new Error(`query segment click failed: ${click.reason || click.title || "unknown"}`);
    const queryEntry = await waitForEntryBody(entries, {
      method: "POST",
      pathIncludes: "/api/segments/query",
      since,
    }, 12_000);
    flow.evidence.push({ label: "POST segments query", ...evidenceFromEntry(queryEntry) });

    const saveInfo = await buttonInfo(cdp, "保存目标人群", { sectionTitle: "筛选条件" });
    flow.ui.saveButton = saveInfo;
    if (saveInfo.found && !saveInfo.disabled) {
      const sinceSave = entries.length;
      await clickButton(cdp, "保存目标人群", { sectionTitle: "筛选条件" });
      const saveEntry = await waitForEntryBody(entries, {
        method: "POST",
        pathIncludes: "/api/segments",
        since: sinceSave,
      }, 12_000);
      flow.evidence.push({ label: "POST segments save", ...evidenceFromEntry(saveEntry) });
      const segment = bodyJson(saveEntry);
      if (segment?.segmentId) report.cleanup.segmentIds.push(segment.segmentId);
      flow.status = queryEntry.status < 400 && saveEntry.status < 400 ? "PASS" : "FAIL";
    } else {
      flow.status = queryEntry.status < 400 ? "LIMITED" : "FAIL";
      flow.notes.push(saveInfo.found ? `保存目标人群被能力门控禁用：${saveInfo.title || "无 title"}` : "未找到保存目标人群按钮");
    }
  } catch (error) {
    flow.error = error.message;
    flow.dialogTextOnError = await dialogText(cdp).catch(() => "");
    flow.pageTextOnError = (await pageText(cdp).catch(() => "")).slice(0, 2_000);
  } finally {
    flow.finishedAt = nowIso();
    report.flows.push(flow);
  }
  return flow;
}

async function verifyWeeklyReport(cdp, entries, report) {
  const flow = {
    name: "招聘周报：scenario D task/SSE + HumanGate + 持久化",
    status: "FAIL",
    startedAt: nowIso(),
    evidence: [],
    notes: [],
  };
  const since = entries.length;
  try {
    await waitForButtonSettled(cdp, "生成周报", { occurrence: 0 });
    const click = await clickButton(cdp, "生成周报", { occurrence: 0 });
    flow.ui = { click };
    if (!click.ok) {
      flow.status = click.disabled ? "LIMITED" : "FAIL";
      flow.notes.push(click.disabled ? `按钮被禁用：${click.title || "无 title"}` : "生成周报按钮不存在");
      return flow;
    }
    const scenarioEntry = await waitForEntryBody(entries, {
      method: "POST",
      pathIncludes: "/api/scenarios/run",
      since,
      bodyPredicate: scenarioBodyPredicate("D"),
    });
    flow.evidence.push({ label: "POST /api/scenarios/run scenario D", ...evidenceFromEntry(scenarioEntry) });
    const taskId = bodyJson(scenarioEntry)?.task_id;
    if (!taskId) throw new Error("weekly report response missing task_id");
    flow.taskId = taskId;
    report.createdTaskIds.push(taskId);
    const streamEntry = await waitForEntry(entries, {
      method: "GET",
      pathIncludes: `/api/tasks/${taskId}/stream`,
      since,
    }, 10_000);
    flow.evidence.push({ label: "GET task stream", ...evidenceFromEntry(streamEntry) });

    await waitFor(
      async () => {
        const text = await dialogText(cdp);
        return text.includes("人工确认");
      },
      20_000,
      "weekly HumanGate modal",
    );
    const sinceConfirm = entries.length;
    const approve = await clickButton(cdp, "通过");
    flow.ui.approve = approve;
    const confirmEntry = await waitForEntryBody(entries, {
      method: "POST",
      pathIncludes: `/api/tasks/${taskId}/confirm`,
      since: sinceConfirm,
    }, 12_000);
    flow.evidence.push({ label: "POST task confirm", ...evidenceFromEntry(confirmEntry) });

    const saveEntry = await waitForEntryBody(entries, {
      method: "POST",
      pathIncludes: "/api/reports/weekly",
      since: sinceConfirm,
    }, 20_000).catch(() => null);
    if (saveEntry) {
      flow.evidence.push({ label: "POST reports weekly", ...evidenceFromEntry(saveEntry) });
      const saved = bodyJson(saveEntry);
      if (saved?.reportId) report.cleanup.reportIds.push(saved.reportId);
    } else {
      throw new Error("未观察到 /api/reports/weekly，周报持久化未闭环");
    }
    flow.status = scenarioEntry.status < 400 && confirmEntry.status < 400 && saveEntry.status < 400 ? "PASS" : "FAIL";
  } catch (error) {
    flow.error = error.message;
    flow.dialogTextOnError = await dialogText(cdp).catch(() => "");
    flow.pageTextOnError = (await pageText(cdp).catch(() => "")).slice(0, 2_000);
  } finally {
    flow.finishedAt = nowIso();
    await closeTaskPanel(cdp);
    report.flows.push(flow);
  }
  return flow;
}

async function verifyJobMatch(cdp, entries, report) {
  const flow = {
    name: "岗位匹配 UI：真实 /jobs/match 结果",
    status: "FAIL",
    startedAt: nowIso(),
    evidence: [],
    notes: [],
  };
  const since = entries.length;
  try {
    await waitForButtonSettled(cdp, "岗位匹配", { sectionTitle: "岗位进展", occurrence: 0 });
    const click = await clickButton(cdp, "岗位匹配", { sectionTitle: "岗位进展", occurrence: 0 });
    flow.ui = { click };
    if (!click.ok) {
      flow.status = click.disabled ? "LIMITED" : "FAIL";
      flow.notes.push(click.disabled ? `按钮被禁用：${click.title || "无 title"}` : "岗位匹配按钮不存在");
      return flow;
    }
    const matchEntry = await waitForEntryBody(entries, {
      method: "POST",
      pathIncludes: "/api/jobs/match",
      since,
    }, 20_000);
    flow.evidence.push({ label: "POST jobs match", ...evidenceFromEntry(matchEntry) });
    const response = bodyJson(matchEntry);
    flow.status = matchEntry.status < 400 && Array.isArray(response?.results) ? "PASS" : "FAIL";
    flow.resultCount = Array.isArray(response?.results) ? response.results.length : null;
  } catch (error) {
    flow.error = error.message;
    flow.dialogTextOnError = await dialogText(cdp).catch(() => "");
    flow.pageTextOnError = (await pageText(cdp).catch(() => "")).slice(0, 2_000);
  } finally {
    flow.finishedAt = nowIso();
    report.flows.push(flow);
  }
  return flow;
}

async function collectInitialData(entries, report) {
  const projectEntry = await waitForEntryBody(entries, {
    method: "GET",
    pathIncludes: `/api/projects/${PROJECT_ID}`,
  });
  const jobsEntry = await waitForEntryBody(entries, {
    method: "GET",
    pathIncludes: `/api/projects/${PROJECT_ID}/jobs`,
  });
  const candidatesEntry = await waitForEntryBody(entries, {
    method: "GET",
    pathIncludes: `/api/projects/${PROJECT_ID}/candidates`,
  });
  const integrationsEntry = await waitForEntryBody(entries, {
    method: "GET",
    pathIncludes: "/api/integrations/status",
  });
  const reportEntry = await waitForEntryBody(entries, {
    method: "GET",
    pathIncludes: `/api/projects/${PROJECT_ID}/reports/latest`,
  }).catch(() => null);

  report.initialData = {
    project: evidenceFromEntry(projectEntry),
    jobs: evidenceFromEntry(jobsEntry),
    candidates: evidenceFromEntry(candidatesEntry),
    integrations: evidenceFromEntry(integrationsEntry),
    latestReport: reportEntry ? evidenceFromEntry(reportEntry) : null,
    projectNameVisible: (await pageText(globalThis.__cdp)).includes("2026 AI 团队招聘"),
  };

  const integrations = bodyJson(integrationsEntry);
  report.capabilities = Object.fromEntries(
    (integrations?.capabilities || []).map((item) => [item.service_type, { id: item.id, status: item.status, connected: item.connected }]),
  );
}

async function main() {
  const report = {
    generatedAt: nowIso(),
    appUrl: APP_URL,
    apiBase: API_BASE,
    projectId: PROJECT_ID,
    projectTitle: PROJECT_TITLE,
    status: "RUNNING",
    flows: [],
    createdTaskIds: [],
    cleanup: {
      outreachDraftIds: [],
      outreachHistoryIds: [],
      segmentIds: [],
      reportIds: [],
      candidateLinks: [],
    },
  };

  let chrome;
  let userDataDir;
  let cdp;

  try {
    const launched = await launchChrome();
    chrome = launched.chrome;
    userDataDir = launched.userDataDir;
    cdp = new CDPClient(launched.wsUrl);
    globalThis.__cdp = cdp;
    await cdp.connect();
    const entries = setupNetworkCapture(cdp);
    await cdp.send("Network.enable");
    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");

    await cdp.send("Page.navigate", { url: APP_URL });
    await waitFor(
      async () => {
        const text = await pageText(cdp);
        return text.includes(PROJECT_TITLE) && text.includes("岗位进展") && text.includes("候选人名单");
      },
      20_000,
      "project detail page",
    );

    await collectInitialData(entries, report);
    await waitForCapabilitiesReady(cdp);

    await recordScenarioFlow({
      cdp,
      entries,
      report,
      name: "岗位分析：scenario A task/SSE + task control",
      scenario: "A",
      button: "岗位分析",
      sectionTitle: "岗位进展",
      occurrence: 0,
      verifyTaskControls: true,
    });

    await recordScenarioFlow({
      cdp,
      entries,
      report,
      name: "找候选人：scenario B task/SSE",
      scenario: "B",
      button: "找候选人",
      sectionTitle: "岗位进展",
      occurrence: 0,
    });

    await verifyCandidateHumanGate(cdp, entries, report);
    await verifyWeeklyReport(cdp, entries, report);
    await verifySegments(cdp, entries, report);
    await verifyOutreach(cdp, entries, report);
    await verifyJobMatch(cdp, entries, report);

    report.status = report.flows.some((flow) => flow.status === "FAIL") ? "HAS_FAILURES" : "PASS";
    report.finishedAt = nowIso();
  } catch (error) {
    report.status = "FAILED_TO_RUN";
    report.error = error.message;
    report.finishedAt = nowIso();
  } finally {
    cdp?.close();
    if (chrome) {
      chrome.kill("SIGTERM");
      await sleep(500);
      if (!chrome.killed) chrome.kill("SIGKILL");
    }
    if (userDataDir) await rm(userDataDir, { recursive: true, force: true }).catch(() => null);
    await mkdir(dirname(REPORT_PATH), { recursive: true });
    await writeFile(REPORT_PATH, `${JSON.stringify(report, null, 2)}\n`, "utf8");
    console.log(JSON.stringify({ reportPath: REPORT_PATH, status: report.status, flows: report.flows.map((flow) => ({ name: flow.name, status: flow.status })) }, null, 2));
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
