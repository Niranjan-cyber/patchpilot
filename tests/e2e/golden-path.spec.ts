import { test, expect } from "@playwright/test";
// B13 prototype exit. Needs: servers up, Gemini key, GITHUB_READ_TOKEN, and PP_DEMO_ISSUE (a planted-bug issue).
const BASE = process.env.BASE_URL ?? "http://localhost:8000";
const ISSUE = process.env.PP_DEMO_ISSUE ?? "";
const shot = (n: string) => `tests/e2e/screenshots/b13-${n}.png`;
test.setTimeout(30 * 60 * 1000);

test("golden path: issue → checks → repro fails 2/2 → fresh-container red→green → approve", async ({ page }) => {
  test.skip(!ISSUE, "set PP_DEMO_ISSUE to a planted-bug issue URL");
  await page.goto(BASE);
  await page.getByLabel("GitHub issue link").fill(ISSUE);
  await page.getByRole("button", { name: "Check issue" }).click();
  await expect(page.getByRole("button", { name: "Start run" })).toBeEnabled({ timeout: 30000 });
  await page.screenshot({ path: shot("01-issue-check"), fullPage: true });
  await page.getByRole("button", { name: "Start run" }).click();
  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]{36}$/);
  await expect(page.getByText("Sample data")).toHaveCount(0);
  await page.screenshot({ path: shot("02-running"), fullPage: true });
  await expect(page.getByText("Ready for human review")).toBeVisible({ timeout: 25 * 60 * 1000 });
  await expect(page.getByText("Run 1: Failed").first()).toBeVisible();
  await expect(page.getByText("Run 2: Passed").first()).toBeVisible();
  await page.screenshot({ path: shot("03-proof"), fullPage: true });
  await page.getByRole("link", { name: "Review and approve" }).click();
  for (const box of ["I read every change below", "I understand what it changes and why", "The pull request may say that AI helped write it"])
    await page.getByLabel(box).check();
  await page.getByRole("button", { name: "Approve this change" }).click();
  await expect(page).toHaveURL(/\/connect\?run=/, { timeout: 60000 });
  await page.screenshot({ path: shot("04-approved-connect"), fullPage: true });
});
