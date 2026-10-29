import { test, expect } from "@playwright/test";
const BASE = process.env.BASE_URL ?? "http://localhost:8000";
// Honest-ending path. Real run when PP_TRIAGE_RUN is set (a run id ending TRIAGE_ONLY/CANNOT_REPRODUCE), else the labelled sample.
test("an unverifiable issue ends in an honest triage report with a download", async ({ page }) => {
  const id = process.env.PP_TRIAGE_RUN ?? "triage_only";
  await page.goto(`${BASE}/runs/${id}`);
  await expect(page.getByText(/Unable to verify/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Download report" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Review and approve" })).toHaveCount(0);
  await page.screenshot({ path: "tests/e2e/screenshots/b13-triage.png", fullPage: true });
});
