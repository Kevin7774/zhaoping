import { chromium } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";

const baseUrl = process.env.E2E_BASE_URL || "http://127.0.0.1:5176";
const projectId = process.env.E2E_PROJECT_ID || "project_2026_ai_team";
const artifactDir = path.resolve(process.cwd(), "..");
const outputPath = path.join(artifactDir, "small-screen-smoke-pgv6.json");

async function main() {
  const browser = await chromium.launch({ headless: true });
  const results = [];
  const routes = [
    `/projects/${projectId}`,
    `/projects/project_hanno_ai_hardware`,
    "/dashboard",
  ];
  for (const route of routes) {
    const context = await browser.newContext({ baseURL: baseUrl, viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    const consoleErrors = [];
    page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
    const entry = { route, status: "FAIL", consoleErrors };
    try {
      await page.goto(route, { waitUntil: "networkidle", timeout: 30000 });
      const body = await page.locator("body").innerText();
      entry.hasContent = body.length > 200;
      entry.hasErrorState = /加载失败|出错|Error/i.test(body.slice(0, 4000)) && !body.includes("API 在线");
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
      entry.horizontalOverflowPx = Math.max(0, scrollWidth - clientWidth);
      const shot = path.join(artifactDir, "screenshots", `small-screen-${route.replaceAll("/", "_")}.png`);
      await fs.mkdir(path.dirname(shot), { recursive: true });
      await page.screenshot({ path: shot, fullPage: false });
      entry.screenshot = shot;
      entry.status = entry.hasContent && consoleErrors.length === 0 ? "PASS" : "FAIL";
    } catch (error) {
      entry.error = String(error);
    } finally {
      await context.close();
    }
    results.push(entry);
  }
  await browser.close();
  const summary = { generatedAt: new Date().toISOString(), viewport: "390x844", results };
  await fs.writeFile(outputPath, JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary.results.map((r) => ({ route: r.route, status: r.status, overflowPx: r.horizontalOverflowPx, consoleErrors: r.consoleErrors.length })), null, 2));
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
