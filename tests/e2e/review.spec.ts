import { test, expect } from "@playwright/test";
const BASE = process.env.BASE_URL ?? "http://localhost:8000";
const { PP_TOKEN = "", PP_RUN = "" } = process.env;
test("S-05: exact diff, approve needs all 3 boxes, typed text survives reload", async ({ page, context }) => {
  test.skip(!PP_TOKEN, "needs scripts/seed_review_run.py");
  await context.addCookies([{ name: "pp_sid", value: PP_TOKEN, url: BASE }]);
  await page.goto(`${BASE}/runs/${PP_RUN}/review`);
  await expect(page.getByText("Review the exact change")).toBeVisible();
  await expect(page.locator("tr.add", { hasText: "return a / b" })).toBeVisible();   // the added line, shown as added
  const approve = page.getByRole("button", { name: "Approve this change" });
  await page.getByLabel("I read every change below").check();
  await page.getByLabel("I understand what it changes and why").check();
  await expect(approve).toBeDisabled();
  await page.screenshot({ path: "tests/e2e/screenshots/b10-review.png", fullPage: true });
  await page.getByLabel("The pull request may say that AI helped write it").check();
  await expect(approve).toBeDisabled();   // v0.5 §2.3: the three own-words answers are required too
  await page.getByLabel("What was broken?").fill("Dividing by zero returned 0 instead of raising.");
  await page.getByLabel("Why does this change fix it?").fill("It lets a / b raise ZeroDivisionError.");
  await expect(approve).toBeDisabled();
  await page.getByLabel("What does the new test prove?").fill("short");
  await expect(approve).toBeDisabled();   // under 20 characters
  await page.getByLabel("What does the new test prove?").fill("It fails on the old code and passes now.");
  await expect(approve).toBeEnabled();
});

test("#97: the Contribution Explainer is collapsed, each section opens on its own, and unrun checks say so", async ({ page, context }) => {
  test.skip(!PP_TOKEN, "needs scripts/seed_review_run.py");
  await context.addCookies([{ name: "pp_sid", value: PP_TOKEN, url: BASE }]);
  for (const width of [1280, 375]) {
    await page.setViewportSize({ width, height: 860 });
    await page.goto(`${BASE}/runs/${PP_RUN}/review`);
    const explainer = page.locator("details.explainer");
    await expect(explainer).not.toHaveAttribute("open");
    await explainer.locator("> summary").click();
    for (const part of ["Problem", "Root cause", "Fix", "Verification"]) {
      await expect(explainer.locator("details.explainer-part", { hasText: part }).first()).not.toHaveAttribute("open");
    }
    await page.getByText("Verification", { exact: true }).click();
    // the seed records no lint run: it must read "Not run", never a pass
    await expect(page.locator("li", { hasText: "The repository's own checks" }).first()).toContainText("Not run");
    await page.getByText("Root cause", { exact: true }).click();
    await expect(page.getByRole("link", { name: "tinycalc/ops.py:12" })).toHaveAttribute("href", /\/blob\/2247b35e2247b35e.*\/tinycalc\/ops\.py#L12$/);
    await page.getByText(/^Remaining risks/).click();
    await expect(page.getByText("The test doesn't check: dividing by 0.0 (a float)")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);   // no sideways scroll
    await page.getByText("Problem", { exact: true }).click();
    await page.getByText("Fix", { exact: true }).click();
    if (width === 375) {   // a phone screenshot of the whole page is unreadable: show the explainer just under the top bar
      await page.setViewportSize({ width, height: 1600 });
      await explainer.evaluate((el) => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 72));
    } else await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `tests/e2e/screenshots/explainer-${width}.png`, fullPage: width !== 375 });
  }
});

test("#98: each question shows evidence and a labelled suggestion; the answer starts empty and stays the user's", async ({ page, context }) => {
  test.skip(!PP_TOKEN, "needs scripts/seed_review_run.py");
  await context.addCookies([{ name: "pp_sid", value: PP_TOKEN, url: BASE }]);
  for (const width of [1280, 375]) {
    await page.setViewportSize({ width, height: 860 });
    await page.goto(`${BASE}/runs/${PP_RUN}/review`);
    const label = "Suggestion from PatchPilot, based on this run's evidence. Write your own.";
    await expect(page.getByText(label)).toHaveCount(3);
    for (const q of ["What was broken?", "Why does this change fix it?", "What does the new test prove?"]) {
      await expect(page.getByLabel(q)).toHaveValue("");   // never pre-filled
    }
    await expect(page.locator(".question").first()).toContainText("divide(1, 0) raises ZeroDivisionError");   // Q1 evidence
    await expect(page.locator(".question").nth(1)).toContainText("tinycalc/ops.py");                           // Q2: the changed file
    await expect(page.locator(".question").nth(2)).toContainText("fails on the original code (2 of 2 runs)");  // Q3 suggestion
    await expect(page.getByRole("button", { name: /use suggestion|paste/i })).toHaveCount(0);
    for (const box of ["I read every change below", "I understand what it changes and why", "The pull request may say that AI helped write it"])
      await page.getByLabel(box).check();
    const approve = page.getByRole("button", { name: "Approve this change" });
    await page.getByLabel("What was broken?").fill("divide(1, 0) returned 0 instead of raising.");
    await page.getByLabel("Why does this change fix it?").fill("The try/except that swallowed the error is gone.");
    await expect(approve).toBeDisabled();   // one answer still missing
    await page.getByLabel("What does the new test prove?").fill("It fails on the old code and passes with the fix.");
    await expect(approve).toBeEnabled();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.getByLabel("What was broken?").fill("");   // a clean screenshot shows the empty fields
    await page.getByLabel("Why does this change fix it?").fill("");
    await page.getByLabel("What does the new test prove?").fill("");
    await page.locator(".question").first().evaluate((el) => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 80));
    await page.screenshot({ path: `tests/e2e/screenshots/questions-${width}.png` });
  }
});

test("#97: an inconclusive hidden variant says so, never 'not run' or 'reason not recorded'", async ({ page, context }) => {
  test.skip(!PP_TOKEN, "needs scripts/seed_review_run.py");
  await context.addCookies([{ name: "pp_sid", value: PP_TOKEN, url: BASE }]);
  // the real seeded response, with only the variant's recorded status changed (variant.py writes this for an unclear run)
  await page.route("**/api/runs/*/approval", async (route) => {
    const json = await (await route.fetch()).json();
    const row = json.help.explainer.verification.find((c: { id: string }) => c.id === "hidden_variant");
    Object.assign(row, { status: "inconclusive", reason: "variant_run_unclear" });
    await route.fulfill({ json });
  });
  await page.goto(`${BASE}/runs/${PP_RUN}/review`);
  await page.locator("details.explainer > summary").click();
  await page.getByText("Verification", { exact: true }).click();
  const li = page.locator("li", { hasText: "Hidden test variant" }).first();
  await expect(li).toContainText("Inconclusive");
  await expect(li).toContainText("Unclear: the hidden variant's run didn't give a clean pass or fail.");
  await expect(li).not.toContainText("reason wasn't recorded");
});
