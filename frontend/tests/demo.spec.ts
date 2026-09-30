import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// The demo path (docs/DEMO_SCRIPT.md), end to end against the committed snapshot.

test.beforeEach(async ({ page }) => {
  // No request may leave the machine: the demo must work offline.
  await page.route(/^https?:\/\/(?!127\.0\.0\.1|localhost)/, (route) => route.abort());
});

test("home opens with the anchor case and computed numbers @mobile", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("198,000");
  await expect(page.getByText("Snapshot", { exact: true })).toBeVisible();
  await expect(page.getByText("No issues detected during validation")).toBeVisible();
  await expect(page.getByRole("img", { name: /Order-of-magnitude ruler/ })).toBeVisible();
  const findings = await (await page.request.get("/api/overview")).json();
  await expect(page.getByText(`See all ${findings.summary.findings_total} findings`)).toBeVisible();
});

test("finding detail shows evidence, lineage and the impact trace", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Open the evidence for this record" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Water temperature");
  await expect(page.getByRole("heading", { name: "Evidence" })).toBeVisible();
  await expect(page.getByText("Observation.component[4].valueQuantity")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Where these values first appear" })).toBeVisible();
  await expect(page.getByText(/this record feeds 1 library, 1 profile, 2 series, \d+ comparisons?, \d+ claims/)).toBeVisible();
  await expect(page.locator("p", { hasText: "Root cause:" })).toContainText("unknown");
});

test("findings can be filtered by severity", async ({ page }) => {
  await page.goto("/findings");
  await page.getByRole("button", { name: /^Critical/ }).click();
  await expect(page).toHaveURL(/severity=CRITICAL/);
  const tags = page.locator("tbody tr td:first-child");
  await expect(tags.first()).toContainText("Critical");
  expect(await tags.filter({ hasNotText: "Critical" }).count()).toBe(0);
});

test("compare returns NOT for non-overlapping age bands, with computed alternatives", async ({ page }) => {
  await page.goto("/compare?id=cmp-obesity-benevento-vs-oslo-18-29");
  await expect(page.getByText("Not comparable").first()).toBeVisible();
  await expect(page.getByText(/Age bands do not overlap/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "What you can compare instead" })).toBeVisible();
});

test("claim guardrail blocks a trend built on broken records", async ({ page }) => {
  await page.goto("/claims");
  await page.getByLabel("Your claim").fill("Water temperature at Almyros increased from 2013 to 2020");
  await page.getByRole("button", { name: "Check this claim", exact: true }).click();
  await expect(page.getByRole("heading", { name: "How Data Doctor read your claim" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Blocked" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Steps the guardrail took" })).toBeVisible();
});

test("claim guardrail supports a clean threshold exceedance", async ({ page }) => {
  await page.goto("/claims");
  await page.getByRole("button", { name: "PM10 at Benevento site 04 exceeded the WHO guideline in 2018" }).click();
  await expect(page.getByRole("heading", { name: "Supported" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "What you can safely say" })).toBeVisible();
});

test("report offers every export", async ({ page }) => {
  await page.goto("/report");
  for (const name of ["Open researcher report (html)", "Download researcher report", "Download fhir operationoutcome bundle", "Download findings"]) {
    await expect(page.getByRole(name.startsWith("Open") ? "link" : "button", { name })).toBeVisible();
  }
  const oo = await page.request.get("/api/reports/operation-outcome.json");
  expect((await oo.json()).resourceType).toBe("Bundle");
});

for (const path of ["/", "/findings", "/compare?id=cmp-obesity-benevento-vs-oslo-18-29", "/claims", "/report", "/sources"]) {
  test(`no serious accessibility violations on ${path}`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${v.id}: ${v.nodes.length} node(s) e.g. ${v.nodes[0]?.target}`)).toEqual([]);
  });
}

test("finding detail is accessible in dark mode", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  const ov = await (await page.request.get("/api/overview")).json();
  await page.goto(`/findings/${encodeURIComponent(ov.hero_finding.id)}`);
  await page.waitForLoadState("networkidle");
  const results = await new AxeBuilder({ page }).withTags(["wcag2aa"]).analyze();
  expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
});

test("keyboard users can skip to content", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
});
