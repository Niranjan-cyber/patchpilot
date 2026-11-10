import { test, expect } from "@playwright/test";
// #101 PR history + feedback badge. Needs a server whose DB has a run with a PR (PP_FB_TOKEN = its session cookie,
// PP_FB_RUN = its run id), e.g. a run pointing at wheelgap/wheelgap#133.
const BASE = process.env.BASE_URL ?? "http://localhost:8000";
const token = process.env.PP_FB_TOKEN ?? "";
const run = process.env.PP_FB_RUN ?? "";
const shots = process.env.PP_FB_SHOTS ?? "docs/evidence";

test.skip(!token || !run, "set PP_FB_TOKEN and PP_FB_RUN");

test.beforeEach(async ({ page }) => {
  await page.context().addCookies([{ name: "pp_sid", value: token, url: BASE }]);
});

test("a failed 'seen' never hides feedback that loaded", async ({ page }) => {
  await page.route("**/feedback/seen", (r) => r.fulfill({ status: 500, body: "{}" }));
  await page.goto(`${BASE}/runs/${run}/pr`);
  await expect(page.getByRole("heading", { name: "Maintainer feedback" })).toBeVisible();
  await expect(page.getByText("Couldn't load feedback")).toHaveCount(0);
  await expect(page.locator(".fb-item").first()).toBeVisible({ timeout: 30_000 });
});

for (const [w, h] of [[1280, 900], [375, 812]] as const) {
  test(`My runs and the PR page at ${w}px: no overflow`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h });
    await page.goto(`${BASE}/my-runs`);
    await expect(page.getByRole("heading", { name: "Your progress" })).toBeVisible({ timeout: 30_000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(w);
    await page.screenshot({ path: `${shots}/history-${w}-myruns.png`, fullPage: true });
    await page.goto(`${BASE}/runs/${run}/pr`);
    await expect(page.getByRole("heading", { name: "Maintainer feedback" })).toBeVisible();
    await expect(page.locator(".fb-item").first()).toBeVisible({ timeout: 30_000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(w);
    await page.screenshot({ path: `${shots}/history-${w}-pr-page.png`, fullPage: true });
  });
}
