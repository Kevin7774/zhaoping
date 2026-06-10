import { chromium } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";

const baseUrl = process.env.E2E_BASE_URL || "http://127.0.0.1:5174";
const apiBase = process.env.E2E_API_BASE || "http://127.0.0.1:8011/api";
const projectId = process.env.E2E_PROJECT_ID || "project_2026_ai_team";
const artifactDir = path.resolve(process.cwd(), "..");
const outputPath = path.join(artifactDir, "error-probes-v4.json");

function apiUrl(apiPath) {
  return `${apiBase}${apiPath}`;
}

async function routeJson500(page, apiPath, detail) {
  await page.route(apiUrl(apiPath), async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail }),
    });
  });
}

async function visible(page, text, timeout = 2500) {
  try {
    await page.getByText(text, { exact: false }).first().waitFor({ state: "visible", timeout });
    return true;
  } catch {
    return false;
  }
}

async function openProject(page) {
  await page.goto(`/projects/${projectId}`, { waitUntil: "domcontentloaded" });
}

async function loadHealthyProject(page) {
  await openProject(page);
  await page.getByRole("heading", { name: "2026 AI 团队招聘" }).waitFor({ timeout: 15000 });
}

async function runCase(browser, testCase) {
  const context = await browser.newContext({ baseURL: baseUrl, viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const consoleErrors = [];
  const networkErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("response", (response) => {
    const url = response.url();
    if (url.startsWith(apiBase) && response.status() >= 400) {
      networkErrors.push({ method: response.request().method(), url, status: response.status() });
    }
  });

  const result = {
    name: testCase.name,
    endpoint: testCase.endpoint,
    status: "FAIL",
    consoleErrors,
    networkErrors,
  };
  try {
    await testCase.run(page, result);
    result.status = testCase.expect(result) ? "PASS" : "FAIL";
  } catch (error) {
    result.error = error instanceof Error ? error.message : String(error);
  } finally {
    result.bodyText = (await page.locator("body").innerText().catch(() => "")).slice(0, 1200);
    await context.close();
  }
  return result;
}

async function main() {
  await fs.mkdir(artifactDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const cases = [
    {
      name: "projects 500 shows page error without fake project data",
      endpoint: `GET /projects/${projectId}`,
      run: async (page, result) => {
        await routeJson500(page, `/projects/${projectId}`, "E2E forced projects 500");
        await openProject(page);
        result.errorVisible = await visible(page, "E2E forced projects 500", 10000);
        result.fakeProjectVisible = await visible(page, "2026 AI 团队招聘", 1000);
      },
      expect: (result) => result.errorVisible && !result.fakeProjectVisible,
    },
    {
      name: "jobs 500 shows page error without fake jobs",
      endpoint: `GET /projects/${projectId}/jobs`,
      run: async (page, result) => {
        await routeJson500(page, `/projects/${projectId}/jobs`, "E2E forced jobs 500");
        await openProject(page);
        result.errorVisible = await visible(page, "E2E forced jobs 500", 10000);
        result.fakeJobVisible = await visible(page, "VLA / 具身智能算法工程师", 1000);
      },
      expect: (result) => result.errorVisible && !result.fakeJobVisible,
    },
    {
      name: "candidates 500 shows page error without fake candidates",
      endpoint: `GET /projects/${projectId}/candidates`,
      run: async (page, result) => {
        await page.route(`${apiUrl(`/projects/${projectId}/candidates`)}**`, async (route) => {
          await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "E2E forced candidates 500" }) });
        });
        await openProject(page);
        result.errorVisible = await visible(page, "E2E forced candidates 500", 10000);
        result.fakeCandidateVisible = await visible(page, "Alex Chen", 1000);
      },
      expect: (result) => result.errorVisible && !result.fakeCandidateVisible,
    },
    {
      name: "integrations status 500 gates capabilities",
      endpoint: "GET /integrations/status",
      run: async (page, result) => {
        await routeJson500(page, "/integrations/status", "E2E forced integrations 500");
        await loadHealthyProject(page);
        result.errorVisible = await visible(page, "E2E forced integrations 500", 10000);
        const button = page.getByRole("button", { name: "岗位分析" }).first();
        result.buttonDisabled = await button.isDisabled();
      },
      expect: (result) => result.errorVisible && result.buttonDisabled,
    },
    {
      name: "scenarios run 500 does not fake task success",
      endpoint: "POST /scenarios/run",
      run: async (page, result) => {
        await loadHealthyProject(page);
        await routeJson500(page, "/scenarios/run", "E2E forced scenarios run 500");
        await page.getByRole("button", { name: "岗位分析" }).first().click();
        result.errorVisible = await visible(page, "E2E forced scenarios run 500", 8000);
        result.taskPanelVisible = await visible(page, "任务实时日志", 1000);
      },
      expect: (result) => result.errorVisible && !result.taskPanelVisible,
    },
    {
      name: "segments query 500 does not fake save",
      endpoint: "POST /segments/query",
      run: async (page, result) => {
        await loadHealthyProject(page);
        await routeJson500(page, "/segments/query", "E2E forced segments query 500");
        await page.getByRole("button", { name: "查询目标人群" }).click();
        result.errorVisible = await visible(page, "E2E forced segments query 500", 8000);
        result.fakeSavedVisible = await visible(page, "已保存目标人群", 1000);
      },
      expect: (result) => result.errorVisible && !result.fakeSavedVisible,
    },
    {
      name: "reports latest 500 is surfaced without fake latest report",
      endpoint: `GET /projects/${projectId}/reports/latest`,
      run: async (page, result) => {
        await routeJson500(page, `/projects/${projectId}/reports/latest`, "E2E forced latest report 500");
        await loadHealthyProject(page);
        result.errorVisible = await visible(page, "E2E forced latest report 500", 8000);
      },
      expect: (result) => result.errorVisible,
    },
    {
      name: "jobs match 500 does not show fake match result",
      endpoint: "POST /jobs/match",
      run: async (page, result) => {
        await loadHealthyProject(page);
        await routeJson500(page, "/jobs/match", "E2E forced jobs match 500");
        await page.getByRole("button", { name: "岗位匹配" }).first().click();
        result.errorVisible = await visible(page, "E2E forced jobs match 500", 8000);
        result.fakeResultVisible = await visible(page, "岗位匹配结果", 1000);
      },
      expect: (result) => result.errorVisible && !result.fakeResultVisible,
    },
  ];
  const results = [];
  for (const testCase of cases) {
    results.push(await runCase(browser, testCase));
  }

  const workflowRun500 = await fetch(apiUrl("/workflows/run"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workflow: { id: "bad", inputs: {}, steps: [] }, input: {}, auto_run: true }),
  });
  results.push({
    name: "workflows run invalid request returns error and creates no fake task",
    endpoint: "POST /workflows/run",
    status: workflowRun500.status >= 400 ? "PASS" : "FAIL",
    networkErrors: [{ method: "POST", url: apiUrl("/workflows/run"), status: workflowRun500.status }],
    responseSummary: await workflowRun500.json().catch(() => null),
  });

  await browser.close();
  const output = {
    generatedAt: new Date().toISOString(),
    baseUrl,
    apiBase,
    results,
    summary: {
      pass: results.filter((item) => item.status === "PASS").length,
      fail: results.filter((item) => item.status !== "PASS").length,
      consoleErrorCount: results.reduce((count, item) => count + (item.consoleErrors?.length || 0), 0),
      networkErrorCount: results.reduce((count, item) => count + (item.networkErrors?.length || 0), 0),
    },
  };
  await fs.writeFile(outputPath, `${JSON.stringify(output, null, 2)}\n`, "utf8");
  console.log(JSON.stringify(output.summary, null, 2));
  if (output.summary.fail) process.exitCode = 1;
}

main();
