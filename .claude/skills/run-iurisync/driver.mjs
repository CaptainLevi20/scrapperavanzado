#!/usr/bin/env node
// Playwright driver for IURISYNC (backend API + Celery worker + Vite frontend).
// Usage: node driver.mjs <command> [args...]
//
// Commands:
//   flow <apiKey> [sourceName] [fini] [ffin]   Full login -> trigger run -> watch -> documents flow
//   login <apiKey>                              Log in only, screenshot the dashboard
//   screenshot <path> <name>                     Navigate to a frontend path and screenshot it
//
// Screenshots land in .claude/skills/run-iurisync/screenshots/<name>.png
// Requires the frontend dev server (default http://localhost:5173) and the
// backend API (default http://localhost:8000) already running - see SKILL.md.

import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOT_DIR = path.join(__dirname, "screenshots");
mkdirSync(SCREENSHOT_DIR, { recursive: true });

const FRONTEND_URL = process.env.IURISYNC_FRONTEND_URL ?? "http://localhost:5173";

async function shot(page, name) {
  const file = path.join(SCREENSHOT_DIR, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  console.log(`[screenshot] ${file}`);
}

function logConsoleErrors(page) {
  page.on("console", (msg) => {
    if (msg.type() === "error") console.log(`[console error] ${msg.text()}`);
  });
  page.on("pageerror", (err) => console.log(`[page error] ${err.message}`));
}

async function login(page, apiKey) {
  await page.goto(`${FRONTEND_URL}/login`, { waitUntil: "domcontentloaded" });
  await page.fill('input[type="password"]', apiKey);
  await page.click('button[type="submit"]');
  await page.waitForURL(`${FRONTEND_URL}/`, { timeout: 10_000 });
}

async function triggerRun(page, sourceName, fini, ffin) {
  await page.goto(`${FRONTEND_URL}/runs`, { waitUntil: "domcontentloaded" });
  await page.click('button:has-text("Nuevo run")');
  await page.waitForSelector("#run-fini", { timeout: 5_000 });

  // Source picker is a checkbox list (aria-label = source name), not a <select>.
  await page.getByRole("checkbox", { name: sourceName, exact: true }).check();

  await page.fill("#run-fini", fini);
  await page.fill("#run-ffin", ffin);
  await shot(page, "02-new-run-dialog");

  await page.click('button:has-text("Iniciar run")');
  await page.waitForURL(/\/runs\/\d+/, { timeout: 10_000 });

  const runId = page.url().match(/\/runs\/(\d+)/)[1];
  console.log(`[run] created run ${runId}`);
  return runId;
}

async function watchRun(page, runId, { timeoutMs = 60_000, pollMs = 3_000 } = {}) {
  await shot(page, "03-run-detail-initial");
  const deadline = Date.now() + timeoutMs;
  let lastStatus = null;
  while (Date.now() < deadline) {
    const statusText = await page.locator("main").innerText();
    const isCompleted = /completed|completado/i.test(statusText) && !/pending|running/i.test(statusText);
    if (statusText !== lastStatus) {
      console.log(`[run ${runId}] progress tick`);
      lastStatus = statusText;
    }
    if (isCompleted) {
      console.log(`[run ${runId}] reached a terminal state`);
      break;
    }
    await page.waitForTimeout(pollMs);
    await page.reload({ waitUntil: "domcontentloaded" });
  }
  await shot(page, "04-run-detail-final");
}

async function browseDocuments(page) {
  await page.goto(`${FRONTEND_URL}/documents`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("table", { timeout: 10_000 });
  await shot(page, "05-documents-list");

  const downloadButton = page.locator('button:has-text("Descargar")').first();
  const count = await page.locator('button:has-text("Descargar")').count();
  if (count === 0) {
    console.log("[documents] no documents available to download yet");
    return;
  }
  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 15_000 }),
    downloadButton.click(),
  ]);
  const suggested = download.suggestedFilename();
  console.log(`[documents] download started: ${suggested}`);
  await download.saveAs(path.join(SCREENSHOT_DIR, suggested));
  console.log(`[documents] saved to ${path.join(SCREENSHOT_DIR, suggested)}`);
}

async function main() {
  const [command, ...args] = process.argv.slice(2);
  if (!command) {
    console.error("Usage: node driver.mjs <flow|login|screenshot> [args...]");
    process.exit(1);
  }

  const browser = await chromium.launch();
  const context = await browser.newContext({ acceptDownloads: true });
  const page = await context.newPage();
  logConsoleErrors(page);

  try {
    if (command === "login") {
      const [apiKey] = args;
      await login(page, apiKey);
      await shot(page, "01-dashboard-after-login");
    } else if (command === "screenshot") {
      const [urlPath, name] = args;
      await page.goto(`${FRONTEND_URL}${urlPath}`, { waitUntil: "domcontentloaded" });
      await shot(page, name);
    } else if (command === "flow") {
      const [apiKey, sourceName = "Corte Constitucional", fini = "2024-01-01", ffin = "2024-01-31"] = args;
      await login(page, apiKey);
      await shot(page, "01-dashboard-after-login");
      const runId = await triggerRun(page, sourceName, fini, ffin);
      await watchRun(page, runId);
      await browseDocuments(page);
    } else {
      console.error(`Unknown command: ${command}`);
      process.exit(1);
    }
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
