import { test, expect } from "@playwright/test";
// Needs seeded runs: `PYTHONPATH=. uv run python scripts/seed_diagnose_run.py` prints "TOKEN RUN_OK RUN_TRIAGE" -> PP_SEED.
const BASE = process.env.BASE_URL ?? "http://localhost:8000";
const [token, runOk, runTriage] = (process.env.PP_SEED ?? "").split(" ");

test.skip(!token, "set PP_SEED from scripts/seed_diagnose_run.py");

test.beforeEach(async ({ context }) => {
  await context.addCookies([{ name: "pp_sid", value: token, url: BASE }]);
});

test("diagnosis cites file:line at the pinned commit, tour and evidence; rejected attempt in Show details", async ({ page, request }) => {
  await page.goto(`${BASE}/runs/${runOk}`);
  const card = page.locator(".diagnosis");
  await expect(card.getByRole("heading", { name: /Likely cause/ })).toBeVisible();
  const loc = card.locator(".locs a").first();
  await expect(loc).toHaveText("src/click/types.py:454");
  await expect(loc).toHaveAttribute("href", /github\.com\/pallets\/click\/blob\/[0-9a-f]{40}\/src\/click\/types\.py#L454$/);
  await expect(card.locator(".tour li")).toHaveCount(3);
  await page.screenshot({ path: "docs/build-plan/evidence/B07/b07-diagnosis.png", fullPage: true });
  await card.locator(".tour").scrollIntoViewIfNeeded();
  await card.screenshot({ path: "docs/build-plan/evidence/B07/b07-tour.png" });

  const href = await card.locator(".hint a").first().getAttribute("href");
  const r = await page.request.get(`${BASE}${href}`);
  expect(r.status()).toBe(200);                                   // evidence opens for the owner
  expect((await request.get(`${BASE}${href}`)).status()).toBe(404); // and not for anyone else

  await page.getByText(/Show details \(1 rejected attempt\)/).click();
  await expect(page.locator(".attempts li")).toContainText("Fixer attempt 1 of 4");
  await expect(page.locator(".attempts li")).toContainText("changed a test file");
  await page.locator(".attempts").screenshot({ path: "docs/build-plan/evidence/B07/b07-policy-reject.png" });
});

test("invalid diagnosis twice: TRIAGE_ONLY, diagnosis unavailable, never a green step", async ({ page }) => {
  await page.goto(`${BASE}/runs/${runTriage}`);
  await expect(page.getByText(/Diagnosis unavailable/)).toBeVisible();
  await expect(page.locator(".badge")).toHaveText("Unable to verify a fix");
  await expect(page.locator(".step-failed")).toContainText("Diagnose");
  await page.getByText(/Show details \(2 rejected attempts\)/).click();
  await expect(page.locator(".attempts li").first()).toContainText("cited evidence that doesn't exist");
  await page.screenshot({ path: "docs/build-plan/evidence/B07/b07-triage.png", fullPage: true });
});
