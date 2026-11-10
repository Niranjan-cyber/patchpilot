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
    // the page fitting isn't enough: the PR cell itself must be fully readable inside its card
    const clipped = await page.$$eval(".pr-cell", (cells) => cells.filter((td) => {
      const box = td.closest(".table-wrap")!.getBoundingClientRect(), r = td.getBoundingClientRect();
      return td.scrollWidth > td.clientWidth + 1 || r.right > box.right + 1 || r.left < box.left - 1;
    }).length);
    expect(clipped).toBe(0);
    await page.screenshot({ path: `${shots}/history-${w}-myruns.png`, fullPage: true });
    await page.goto(`${BASE}/runs/${run}/pr`);
    await expect(page.getByRole("heading", { name: "Maintainer feedback" })).toBeVisible();
    await expect(page.locator(".fb-item").first()).toBeVisible({ timeout: 30_000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(w);
    await page.screenshot({ path: `${shots}/history-${w}-pr-page.png`, fullPage: true });
  });
}

test("#103: Revise from feedback uses the saved plan and goes to the run", async ({ page }) => {
  let posted = false;
  await page.route("**/revise-from-feedback", (r) => { posted = true; return r.fulfill({ status: 200, contentType: "application/json", body: "{}" }); });
  // the fixture PR (wheelgap#133) is merged, so show it as open to reach the button
  await page.route("**/feedback/assist", async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), pr_state: "open" } }); });
  await page.goto(`${BASE}/runs/${run}/pr`);
  await expect(page.locator(".fb-item").first()).toBeVisible({ timeout: 30_000 });
  const pick = page.getByLabel("Include in the revision plan").first();
  await pick.check();
  await page.getByRole("button", { name: /^Save plan/ }).click();
  const revise = page.getByRole("button", { name: /^Revise from feedback \(\d+\)$/ });
  await expect(revise).toBeEnabled();
  await page.screenshot({ path: `${shots}/revise-from-feedback.png`, fullPage: true });
  await revise.click();
  await expect(page).toHaveURL(new RegExp(`/runs/${run}$`));
  expect(posted).toBe(true);
});

test("#103: no Revise on a merged or closed pull request", async ({ page }) => {
  await page.route("**/feedback/assist", async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), pr_state: "merged" } }); });
  await page.goto(`${BASE}/runs/${run}/pr`);
  await expect(page.locator(".fb-item").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: /^Revise from feedback/ })).toHaveCount(0);
  await expect(page.getByText("This pull request is merged, so Revise isn't offered.")).toBeVisible();
});
