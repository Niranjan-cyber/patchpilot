import { test, expect } from "@playwright/test";
const BASE = process.env.BASE_URL ?? "http://localhost:8000";
test("My runs empty state invites a first run", async ({ page }) => {
  await page.goto(`${BASE}/my-runs`);
  await expect(page.getByText("No runs yet. Paste an issue to start.")).toBeVisible();
  await page.screenshot({ path: "tests/e2e/screenshots/b12-myruns-empty.png", fullPage: true });
});
test("someone else's run shows sign-in, never the run", async ({ page }) => {
  await page.goto(`${BASE}/runs/${process.env.PP_FOREIGN_RUN ?? "00000000-0000-4000-8000-000000000000"}`);
  await expect(page.getByText("Sign in with the GitHub account that owns it")).toBeVisible();
  await expect(page.getByText("pallets/itsdangerous")).toHaveCount(0);
  await page.screenshot({ path: "tests/e2e/screenshots/b12-not-yours.png", fullPage: true });
});
