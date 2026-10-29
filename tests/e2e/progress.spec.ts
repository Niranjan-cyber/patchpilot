import { test, expect } from "@playwright/test";
// Seed: `PYTHONPATH=. uv run python scripts/seed_progress_runs.py` -> PP_SEED16 (session token).
// BASE_URL = normal server; BLOCKED_URL = a server started with HTTPS_PROXY=http://127.0.0.1:9 (GitHub unreachable).
const BASE = process.env.BASE_URL ?? "http://localhost:8000";
const BLOCKED = process.env.BLOCKED_URL;
const token = process.env.PP_SEED16 ?? "";

test.skip(!token, "set PP_SEED16 from scripts/seed_progress_runs.py");

async function open(page, base: string) {
  await page.context().addCookies([{ name: "pp_sid", value: token, url: base }]);
  await page.goto(`${base}/my-runs`);
  await expect(page.getByRole("heading", { name: "Your progress" })).toBeVisible();
}
const stat = (page, label: string) => page.locator(".progress .stat", { hasText: label }).locator("strong");

test("separate counts; PatchPilot and GitHub in separate columns", async ({ page }) => {
  await open(page, BASE);
  await expect(stat(page, "issues analyzed")).toHaveText("3");
  await expect(stat(page, "fixes proposed")).toHaveText("2");
  await expect(stat(page, "pull requests opened")).toHaveText("2");
  await expect(stat(page, "merged on GitHub")).toHaveText("1");
  await expect(page.locator(".progresstable")).toContainText("Merged");
  await expect(page.locator(".progresstable")).toContainText("No pull request");
  await page.screenshot({ path: "docs/build-plan/evidence/B16/b16-progress.png", fullPage: true });
});

test("GitHub blocked: Status unavailable, never open or closed as a guess", async ({ page }) => {
  test.skip(!BLOCKED, "set BLOCKED_URL");
  await open(page, BLOCKED!);
  await expect(stat(page, "merged on GitHub")).toHaveText("0");
  await expect(page.locator(".progresstable td", { hasText: "Status unavailable" })).toHaveCount(2);
  await expect(page.locator(".progresstable")).not.toContainText("Merged");
  await expect(page.getByText(/GitHub didn't tell us the status of 2 pull requests/)).toBeVisible();
  await page.screenshot({ path: "docs/build-plan/evidence/B16/b16-status-unavailable.png", fullPage: true });
});
