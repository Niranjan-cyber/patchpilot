import { test, expect } from "@playwright/test";
const BASE = process.env.BASE_URL ?? "http://localhost:8000";
for (const id of ["verified_fix", "env_failed", "paused_quota_unknown_reset", "stopped_during_setup", "blocked"]) {
  test(`fixture ${id}`, async ({ page }) => {
    await page.goto(`${BASE}/runs/${id}`);
    await expect(page.locator("h1")).toBeVisible();
    await page.screenshot({ path: `tests/e2e/screenshots/b02-${id}.png`, fullPage: true });
  });
}
test("shell", async ({ page }) => {
  await page.goto(BASE);
  await expect(page.getByText("Turn a GitHub issue into a tested fix.")).toBeVisible();
  await page.screenshot({ path: "tests/e2e/screenshots/b01-shell.png", fullPage: true });
});
