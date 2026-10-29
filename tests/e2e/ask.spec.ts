import { test, expect } from "@playwright/test";
// Seed: `PYTHONPATH=. uv run python scripts/seed_diagnose_run.py` -> PP_SEED = "TOKEN RUN_OK RUN_TRIAGE RUN_PAUSED".
const BASE = process.env.BASE_URL ?? "http://localhost:8000";
const [token, runOk, , runPaused] = (process.env.PP_SEED ?? "").split(" ");

test.skip(!runPaused, "set PP_SEED from scripts/seed_diagnose_run.py");
test.beforeEach(async ({ context }) => { await context.addCookies([{ name: "pp_sid", value: token, url: BASE }]); });

test("Explainer unavailable: the panel says so with Try again and never shows an answer", async ({ page }) => {
  // Real server path: with no AI key (or quota hit) the API refuses rather than inventing an answer.
  await page.route("**/api/runs/*/ask", (r) => r.fulfill({ status: 503, contentType: "application/json",
    body: JSON.stringify({ code: "EXPLAINER_UNAVAILABLE", message: "The explainer isn't available right now, so we won't guess an answer. Try again in a minute.", retry_after: 60 }) }));
  await page.goto(`${BASE}/runs/${runOk}`);
  await page.getByRole("button", { name: "Why does the test fail?" }).click();
  await expect(page.getByRole("alert")).toContainText("won't guess an answer");
  await expect(page.getByRole("alert").getByRole("button", { name: "Try again" })).toBeVisible();
  await expect(page.locator(".answer")).toHaveCount(0);
});

test("a cited answer shows its evidence, and each citation opens the source", async ({ page }) => {
  const run = await (await page.request.get(`${BASE}/api/runs/${runOk}`)).json();
  const cite = run.diagnosis.evidence_ids[0];
  // UI rendering check: the answer text is stubbed, the citation is a REAL evidence ID of this run.
  await page.route("**/api/runs/*/ask", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
    question: "Why does PatchPilot point at src/click/types.py?",
    answer: "The failing test calls Choice.convert, and the failure output shows the error message names the normalized value. That message is built in src/click/types.py, so that's where the fix belongs.",
    evidence_ids: [cite] }) }));
  await page.goto(`${BASE}/runs/${runOk}`);
  await page.getByRole("button", { name: "Why src/click/types.py?" }).click();
  const a = page.locator(".answer");
  await expect(a).toContainText("Choice.convert");
  const href = await a.getByRole("link", { name: "evidence 1" }).getAttribute("href");
  expect((await page.request.get(`${BASE}${href}`)).status()).toBe(200);
  await page.locator(".ask").screenshot({ path: "docs/build-plan/evidence/B15/b15-answer.png" });
});

test("guided pause after reproduction shows Continue / Stop", async ({ page }) => {
  await page.goto(`${BASE}/runs/${runPaused}`);
  await expect(page.getByText("Paused so you can look.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue" })).toBeVisible();
  await expect(page.getByLabel("after the failing test is written")).toBeChecked();
  await page.screenshot({ path: "docs/build-plan/evidence/B15/b15-paused.png", fullPage: true });
  const r = await page.request.post(`${BASE}/api/runs/${runPaused}/continue`);
  expect(r.status()).toBe(200);
});
