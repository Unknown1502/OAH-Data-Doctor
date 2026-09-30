import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// The demo path (docs/DEMO_SCRIPT.md), end to end against the committed snapshot.

// Comparisons and claims run by these tests are persisted by the app (they feed the impact trace). Remove them afterwards
// so a demo started after the tests shows only the catalog analyses.
test.afterAll(async ({ playwright }, testInfo) => {
  const ctx = await playwright.request.newContext({ baseURL: testInfo.project.use.baseURL });
  await ctx.post("/api/analyses/reset");
  await ctx.dispose();
});

test.beforeEach(async ({ page }) => {
  // No request may leave the machine: the demo must work offline.
  await page.route(/^https?:\/\/(?!127\.0\.0\.1|localhost)/, (route) => route.abort());
});

test("home opens with the anchor case and computed numbers @mobile", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("198,000");
  // The badge must state the true source of the current run: live (with fetch time) or snapshot.
  const status = await (await page.request.get("/api/status")).json();
  await expect(page.getByText(status.source.kind === "live" ? "Live" : "Snapshot", { exact: true })).toBeVisible();
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

test("a user can bring their own model key; it stays in the tab and goes only to this server", async ({ page }) => {
  const key = "gsk_e2e_not_a_real_key";
  // No provider is called in tests: answer the model list, the connection check and the rephrasing here, and record
  // what the page sends.
  await page.route("**/api/llm/models", (route) =>
    route.fulfill({ json: { models: ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "qwen/qwen3-32b"], error: null } }),
  );
  await page.route("**/api/llm/test", (route) =>
    route.fulfill({ json: { ok: true, name: "groq:llama-3.3-70b-versatile", latency_ms: 321, reply: "OK", models: [] } }),
  );
  let sent: { llm?: Record<string, string> } | null = null;
  await page.route("**/api/findings/*/explain", async (route) => {
    sent = route.request().postDataJSON();
    await route.fulfill({ json: { text: "The median lies below the minimum, so these values cannot all be right.", method: "llm:groq:llama-3.3-70b-versatile", fallback_reason: null } });
  });
  const ov = await (await page.request.get("/api/overview")).json();
  await page.goto(`/findings/${encodeURIComponent(ov.hero_finding.id)}`);

  await page.getByRole("button", { name: "Language model: off" }).click();
  const dialog = page.getByRole("dialog", { name: "Connect a language model" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("Provider")).toHaveValue("groq"); // a free provider is preselected
  await expect(dialog.getByRole("button", { name: "Connect" })).toBeDisabled(); // until a key is entered
  await expect(dialog.getByRole("link", { name: "Create a Groq API key" })).toHaveAttribute("href", "https://console.groq.com/keys");
  await expect(dialog.getByPlaceholder("Enter your Groq API key")).toBeVisible();
  await dialog.getByLabel("API key").fill(key);
  await expect(dialog.getByText("3 models are available with your key.")).toBeVisible();
  await dialog.getByLabel("Model", { exact: true }).selectOption("llama-3.3-70b-versatile");
  const a11y = await new AxeBuilder({ page }).include("dialog").withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(a11y.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
  await dialog.getByRole("button", { name: "Connect" }).click();
  await expect(dialog).toBeHidden();

  // The top bar now always says which model is in use and whose key pays for it.
  const modelButton = page.getByRole("button", { name: /^Language model: Groq llama-3.3-70b-versatile/ });
  await expect(modelButton).toBeVisible();
  await expect(modelButton).toContainText("your key");
  // Tab-only by default: sessionStorage, not localStorage.
  expect(await page.evaluate(() => [sessionStorage.getItem("dd-llm") !== null, localStorage.getItem("dd-llm")])).toEqual([true, null]);
  await page.getByRole("button", { name: "Rephrase with Groq llama-3.3-70b-versatile" }).click();
  const credit = page.locator("p", { hasText: "Rephrased by" });
  await expect(credit).toContainText("Groq");
  await expect(credit).toContainText("llama-3.3-70b-versatile");
  expect(sent).toEqual({ llm: { provider: "groq", model: "llama-3.3-70b-versatile", api_key: key } });

  await modelButton.click();
  await dialog.getByRole("button", { name: "Disconnect" }).click();
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(page.getByRole("button", { name: "Language model: off" })).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem("dd-llm"))).toBeNull();
});

test("keyboard users can skip to content", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
});

test("no page scrolls sideways on a phone @mobile", async ({ page }) => {
  const ov = await (await page.request.get("/api/overview")).json();
  for (const path of ["/", "/findings", `/findings/${encodeURIComponent(ov.hero_finding.id)}`, "/compare?id=cmp-obesity-benevento-vs-oslo-female",
    "/claims?id=clm-benevento-pm25-exceeds-who", "/report", "/sources"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal overflow on ${path}`).toBeLessThanOrEqual(1);
  }
});
