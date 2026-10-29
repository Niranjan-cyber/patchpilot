import { test, expect } from "@playwright/test";
const BASE = process.env.BASE_URL ?? "http://localhost:8000";

test("eval page matches /api/eval and never shows numbers without results", async ({ page, request }) => {
  const api = await request.get(`${BASE}/api/eval`);
  await page.goto(`${BASE}/eval`);
  if (api.status() === 404) {
    await expect(page.getByRole("heading", { name: "No eval results yet" })).toBeVisible();
    await expect(page.locator(".stat")).toHaveCount(0);
  } else {
    const s = await api.json();
    await expect(page.getByRole("heading", { name: "How often is PatchPilot right?" })).toBeVisible();
    await expect(page.locator(".evaltable tbody tr")).toHaveCount(s.rows.length);
    const fv = page.locator(".stat", { hasText: "false verified claims" }).locator("strong");
    await expect(fv).toHaveText(String(s.counts.false_verified));
    if (s.counts.false_verified) await expect(page.locator(".evaltable tbody tr").first()).toHaveClass(/row-bad/);
    // unknown official results read "Unknown", never "Pass"
    const unknown = s.rows.filter((r: { official: string | null }) => r.official === null).length;
    await expect(page.locator(".evaltable tbody td", { hasText: /^Unknown$/ })).toHaveCount(unknown);
  }
  await page.screenshot({ path: "docs/build-plan/evidence/B14/b14-eval.png", fullPage: true });
});
