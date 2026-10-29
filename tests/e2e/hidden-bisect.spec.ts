import { test, expect } from "@playwright/test";
// Seed: `PYTHONPATH=. uv run python scripts/seed_variant_runs.py` -> PP_SEED17 = "TOKEN RUN_HIDDEN_FAIL RUN_CAP".
const BASE = process.env.BASE_URL ?? "http://localhost:8000";
const [token, runHidden, runCap] = (process.env.PP_SEED17 ?? "").split(" ");

test.skip(!runCap, "set PP_SEED17 from scripts/seed_variant_runs.py");
test.beforeEach(async ({ context }) => { await context.addCookies([{ name: "pp_sid", value: token, url: BASE }]); });

test("fix that fails the hidden variant shows Needs attention and the hidden row", async ({ page }) => {
  await page.goto(`${BASE}/runs/${runHidden}`);
  await expect(page.locator(".badge")).toHaveText("Needs attention");
  const extra = page.getByRole("region", { name: "Extra checks" });
  await expect(extra).toContainText("FAILS a hidden variant");
  await expect(extra.locator(".dot-fail")).toHaveCount(1);
  await extra.screenshot({ path: "docs/build-plan/evidence/B17/b17-hidden.png" });
});

test("bisect found: names the first failing commit with a link and the probes", async ({ page }) => {
  await page.goto(`${BASE}/runs/${runHidden}`);
  const extra = page.getByRole("region", { name: "Extra checks" });
  await expect(extra.getByRole("link", { name: /^[0-9a-f]{7}$/ })).toHaveAttribute("href", /github\.com\/pallets\/click\/commit\/[0-9a-f]{40}/);
  await extra.getByText(/Show the 2 test runs/).click();
  await expect(extra.locator("details li")).toHaveCount(2);
  await extra.screenshot({ path: "docs/build-plan/evidence/B17/b17-bisect.png" });
});

test("bisect over the step cap shows Not run with the reason, never a guessed commit", async ({ page }) => {
  await page.goto(`${BASE}/runs/${runCap}`);
  const extra = page.getByRole("region", { name: "Extra checks" });
  await expect(extra).toContainText("Not run: the search needed more test runs than our limit (6). We don't guess a commit.");
  await expect(extra.locator("a[href*='/commit/']")).toHaveCount(0);
  await expect(page.locator(".badge")).toHaveText("Ready for human review");
  await expect(extra).toContainText("also passes a hidden variant");
  await page.screenshot({ path: "docs/build-plan/evidence/B17/b17-cap.png", fullPage: true });
});
