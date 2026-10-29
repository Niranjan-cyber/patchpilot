import { test, expect } from "@playwright/test";
const BASE = process.env.BASE_URL ?? "http://localhost:8000";
const shot = (n: string) => `tests/e2e/screenshots/b03-${n}.png`;

test("paste a real issue → green checklist", async ({ page }) => {
  await page.goto(BASE);
  await page.getByLabel("GitHub issue link").fill("https://github.com/pallets/click/issues/3888");
  await page.getByRole("button", { name: "Check issue" }).click();
  await expect(page.getByRole("button", { name: "Start run" })).toBeEnabled({ timeout: 20000 });
  await expect(page.getByText("It's a Python project")).toBeVisible();
  await page.screenshot({ path: shot("success"), fullPage: true });
});

test("closed issue → warning, Start run needs consent", async ({ page }) => {
  await page.goto(`${BASE}/check?url=${encodeURIComponent("https://github.com/pallets/click/issues/3895")}`);
  await expect(page.getByText("This issue is closed")).toBeVisible({ timeout: 20000 });
  await expect(page.getByRole("button", { name: "Start run" })).toBeDisabled();
  await page.screenshot({ path: shot("warning"), fullPage: true });
});

test("pull request link → specific message", async ({ page }) => {
  await page.goto(`${BASE}/check?url=${encodeURIComponent("https://github.com/pallets/click/pull/2")}`);
  await expect(page.getByText("That's a pull request link")).toBeVisible({ timeout: 20000 });
  await page.screenshot({ path: shot("invalid"), fullPage: true });
});

test("non-Python repo → unsupported, no Start run", async ({ page }) => {
  await page.goto(`${BASE}/check?url=${encodeURIComponent("https://github.com/expressjs/express/issues/1")}`);
  await expect(page.getByText("only run Python projects")).toBeVisible({ timeout: 20000 });
  await expect(page.getByRole("button", { name: "Start run" })).toHaveCount(0);
  await page.screenshot({ path: shot("unsupported"), fullPage: true });
});
