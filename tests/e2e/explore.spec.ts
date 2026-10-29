import { test, expect } from "@playwright/test";
// Live GitHub reads: set EXPLORE_REPO to the team upstream repo once it exists (defaults to pallets/click).
const BASE = process.env.BASE_URL ?? "http://localhost:8000";
const REPO = process.env.EXPLORE_REPO ?? "https://github.com/pallets/click";

test("a Python repo shows 3-5 suggestions with reasons, effort labelled Estimate, and repo checks", async ({ page }) => {
  await page.goto(`${BASE}/explore`);
  await page.getByLabel("GitHub repository link").fill(REPO);
  await page.getByRole("button", { name: "Find issues" }).click();
  const items = page.locator(".shortlist > li");
  await expect(items.first()).toBeVisible({ timeout: 30_000 });
  expect(await items.count()).toBeGreaterThanOrEqual(1);
  expect(await items.count()).toBeLessThanOrEqual(5);
  await expect(items.first().locator(".why li").first()).toBeVisible();
  await expect(items.first()).toContainText("Estimate:");
  await expect(page.locator(".repo-signals")).toContainText("Has tests");
  await expect(items.first().getByRole("link", { name: "Check this issue" })).toHaveAttribute("href", /\/check\?url=/);
  await page.screenshot({ path: "docs/build-plan/evidence/B18/b18-shortlist.png", fullPage: true });
});

test("a JavaScript repo shows the unsupported message, not an empty or failed list", async ({ page }) => {
  await page.goto(`${BASE}/explore?url=${encodeURIComponent("https://github.com/expressjs/express")}`);
  await expect(page.getByText("PatchPilot can only run Python projects today")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".shortlist")).toHaveCount(0);
  await page.screenshot({ path: "docs/build-plan/evidence/B18/b18-unsupported.png", fullPage: true });
});

test("a non-GitHub link fails with a specific message", async ({ page }) => {
  await page.goto(`${BASE}/explore?url=${encodeURIComponent("https://gitlab.com/a/b")}`);
  await expect(page.getByRole("heading", { name: "Couldn't check this repository" })).toBeVisible();
  await expect(page.getByText("Paste a link to a GitHub repository")).toBeVisible();
});
