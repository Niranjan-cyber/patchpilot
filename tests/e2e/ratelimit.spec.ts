import { test, expect } from "@playwright/test";
const BASE = process.env.BASE_URL ?? "http://localhost:8000";
test("rate-limited GitHub shows Failed with retry time, not an empty card", async ({ page }) => {
  test.skip(!process.env.PP_EXPECT_RATELIMIT, "only when the anonymous GitHub limit is exhausted");
  await page.goto(`${BASE}/check?url=${encodeURIComponent("https://github.com/pallets/click/issues/3888")}`);
  await expect(page.getByText("GitHub didn't answer")).toBeVisible({ timeout: 20000 });
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  await page.screenshot({ path: "tests/e2e/screenshots/b03-ratelimited.png", fullPage: true });
});
