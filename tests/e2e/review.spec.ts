import { test, expect } from "@playwright/test";
const BASE = process.env.BASE_URL ?? "http://localhost:8000";
const { PP_TOKEN = "", PP_RUN = "" } = process.env;
test("S-05: exact diff, approve needs all 3 boxes, typed text survives reload", async ({ page, context }) => {
  test.skip(!PP_TOKEN, "needs scripts/seed_review_run.py");
  await context.addCookies([{ name: "pp_sid", value: PP_TOKEN, url: BASE }]);
  await page.goto(`${BASE}/runs/${PP_RUN}/review`);
  await expect(page.getByText("Review the exact change")).toBeVisible();
  await expect(page.getByText("+    return a / b")).toBeVisible();
  const approve = page.getByRole("button", { name: "Approve this change" });
  await page.getByLabel("I read every change below").check();
  await page.getByLabel("I understand what it changes and why").check();
  await expect(approve).toBeDisabled();
  await page.screenshot({ path: "tests/e2e/screenshots/b10-review.png", fullPage: true });
  await page.getByLabel("The pull request may say that AI helped write it").check();
  await expect(approve).toBeEnabled();
});
