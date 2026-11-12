// Screenshot every main screen (light / dark / mobile) + frames for the demo GIF.
// Needs the backend (kavra serve, demo data) on :8000 and the web app on :3000.
// Usage: node scripts/capture.mjs [--only today,study] [--frames]
import { chromium } from "playwright-core";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const OUT = join(ROOT, "docs", "screenshots");
const FRAMES = join(ROOT, "docs", "frames");
const BASE = process.env.WEB_URL ?? "http://localhost:3000";
const args = process.argv.slice(2);
const only = args.includes("--only") ? args[args.indexOf("--only") + 1].split(",") : null;
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ channel: "msedge" });

async function page(theme, mobile) {
  const ctx = await browser.newContext({
    viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    deviceScaleFactor: mobile ? 3 : 2,
    isMobile: mobile,
    hasTouch: mobile,
    colorScheme: theme,
    reducedMotion: "no-preference",
  });
  await ctx.addInitScript((t) => {
    localStorage.setItem("kavra.theme", t);
    localStorage.setItem("kavra.locale", "tr");
  }, theme);
  return ctx.newPage();
}

const settle = (p, ms = 900) => p.waitForLoadState("networkidle").then(() => p.waitForTimeout(ms));

const SCREENS = {
  today: async (p) => {
    await p.goto(`${BASE}/`);
    await settle(p, 1400);
  },
  library: async (p) => {
    await p.goto(`${BASE}/library`);
    await settle(p);
  },
  document: async (p) => {
    await p.goto(`${BASE}/library/1`);
    await settle(p);
  },
  study: async (p) => {
    await p.goto(`${BASE}/study?doc=1`);
    await settle(p);
  },
  "study-feedback": async (p) => {
    await p.goto(`${BASE}/study?doc=1`);
    await settle(p);
    await answerFirst(p, true);
    await p.waitForTimeout(1300);
  },
  "study-wrong": async (p) => {
    await p.goto(`${BASE}/study`);
    await settle(p);
    await answerFirst(p, false);
    await p.waitForTimeout(1300);
  },
  exam: async (p) => {
    await p.goto(`${BASE}/exam`);
    await settle(p);
  },
  insights: async (p) => {
    await p.goto(`${BASE}/insights`);
    await settle(p, 1200);
  },
};

/** Answer the current card: pick an option (correct or not) via the API's view of the card. */
async function answerFirst(p, correct, index = 0) {
  const doc = new URL(p.url()).searchParams.get("doc");
  const queue = await (await p.request.get(`http://127.0.0.1:8000/api/study/queue${doc ? `?document_id=${doc}` : ""}`)).json();
  const q = await (await p.request.get(`http://127.0.0.1:8000/api/questions/${queue.items[index].id}`)).json();
  const card = p.locator("main section").first();
  if (q.type === "mcq") {
    await card.getByRole("radio").nth(correct ? q.correct_index : (q.correct_index + 1) % 4).click();
  } else if (q.type === "tf") {
    await card.getByRole("radio").nth((q.answer === "true") === correct ? 0 : 1).click();
  } else if (q.type === "cloze") {
    await card.locator("input").fill(correct ? q.answer : "osmoz");
  } else {
    await card.locator("textarea").fill(correct ? q.key_points.join(". ") : q.key_points[0]);
  }
  await p.waitForTimeout(250);
  await p.getByRole("button", { name: /Kontrol et|Check/ }).click();
}

const variants = [
  { name: "light", theme: "light", mobile: false },
  { name: "dark", theme: "dark", mobile: false },
  { name: "mobile", theme: "light", mobile: true },
  { name: "mobile-dark", theme: "dark", mobile: true },
];

if (!args.includes("--frames")) {
  for (const v of variants) {
    for (const [name, go] of Object.entries(SCREENS)) {
      if (only && !only.includes(name)) continue;
      if (v.mobile && ["document", "insights"].includes(name) && v.theme === "dark") continue;
      const p = await page(v.theme, v.mobile);
      await go(p);
      await p.screenshot({ path: join(OUT, `${name}-${v.name}.png`), fullPage: !v.mobile && ["today", "document", "insights"].includes(name) });
      await p.context().close();
      console.log("✓", name, v.name);
    }
  }
}

// ---- GIF frames: study flow on desktop light ----
if (args.includes("--frames")) {
  mkdirSync(FRAMES, { recursive: true });
  const p = await page("light", false);
  await p.setViewportSize({ width: 1200, height: 760 });
  let i = 0;
  const shot = async (n = 1) => {
    for (let k = 0; k < n; k++) await p.screenshot({ path: join(FRAMES, `f${String(i++).padStart(4, "0")}.png`) });
  };
  const burst = async (ms) => {
    const end = Date.now() + ms;
    while (Date.now() < end) await shot();
  };
  await p.goto(`${BASE}/`);
  await settle(p, 1500);
  await shot(12);
  await p.goto(`${BASE}/study`);
  await settle(p);
  await shot(10);
  await answerFirst(p, true);
  await burst(1500);
  await shot(18);
  await p.keyboard.press("Enter");
  await settle(p, 400);
  await shot(10);
  await answerFirst(p, false);
  await burst(1500);
  await shot(14);
  await p.keyboard.press("s");
  await burst(700);
  await shot(18);
  console.log("frames:", i);
}

await browser.close();
