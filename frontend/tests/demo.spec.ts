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
  // The opening contrast, in words: FHIR conformance passes, scientific consistency is critical.
  const verdicts = page.getByRole("group", { name: /^Two verdicts/ }).first();
  await expect(verdicts.getByText("Pass", { exact: true })).toBeVisible();
  await expect(verdicts.getByText("Critical", { exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: /Order-of-magnitude ruler/ })).toBeVisible();
  const findings = await (await page.request.get("/api/overview")).json();
  await expect(page.getByText(`See all ${findings.summary.findings_total} findings`)).toBeVisible();
});

test("finding detail shows evidence, lineage and the impact trace", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Open the evidence for this record" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Water temperature");
  await expect(page.getByRole("heading", { name: "Evidence", exact: true })).toBeVisible();
  await expect(page.getByText("Observation.component[4].valueQuantity")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Where these values first appear" })).toBeVisible();
  await expect(page.getByText(/this record feeds 1 library, 1 profile, 2 series, \d+ comparisons?, \d+ claims/)).toBeVisible();
  await expect(page.getByRole("region", { name: "What is wrong and why" }).getByText(/Root cause:\s*unknown/i)).toBeVisible();
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
  await expect(page.getByRole("heading", { name: "What you can do instead" })).toBeVisible();
  await expect(page.getByText("A direct comparison of these two values.")).toBeVisible();
  // Each dimension opens to show what A and B published for it.
  // The kind of each problem comes from the engine's semantics: a population mismatch is a hard blocker, a related
  // measure is a caveat.
  const population = page.locator("summary", { hasText: "Population" });
  await expect(population.getByText("hard blocker")).toBeVisible();
  await expect(page.locator("summary", { hasText: "Measure" }).getByText("contextual")).toBeVisible();
  await page.getByText("Population", { exact: true }).click();
  await expect(page.locator("details[open]").getByText(/^A: Obesity prevalence/)).toBeVisible();
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

test("the report separates observed, derived, inferred and unknown statements", async ({ page }) => {
  const list = await (await page.request.get("/api/findings?resource=Observation/Obs-Almyros-TemperatureWater-2013&rule=SEM-SCALE-001")).json();
  const calc = (await (await page.request.get(`/api/findings/${encodeURIComponent(list.items[0].id)}`)).json()).calculation;
  await page.goto("/report");
  const exec = page.locator('dl[aria-label="Most important record"]');
  for (const kind of ["observed", "derived", "inferred", "unknown"]) await expect(exec.getByText(kind, { exact: true })).toBeVisible();
  await expect(exec.getByText(`${calc.steps[0].expression} = ${calc.steps[0].result};`)).toBeVisible(); // the backend's own calculation
  await expect(exec.getByText(/Root cause: which published value is wrong, and why, is not established/)).toBeVisible();
});

test("report offers every export", async ({ page }) => {
  await page.goto("/report");
  for (const name of ["Open researcher report (html)", "Download researcher report", "Download fhir operationoutcome bundle", "Download findings"]) {
    await expect(page.getByRole(name.startsWith("Open") ? "link" : "button", { name })).toBeVisible();
  }
  const oo = await page.request.get("/api/reports/operation-outcome.json");
  expect((await oo.json()).resourceType).toBe("Bundle");
});

test("the what-if lab: change the numbers and the rules react; the FHIR server is asked about the same numbers", async ({ page }) => {
  // The server call is answered here (tests never reach the sandbox); the rules run for real on the API.
  let asked: { values?: Record<string, number> } | null = null;
  await page.route("**/api/lab/observation/validate", async (route) => {
    asked = route.request().postDataJSON();
    await route.fulfill({ json: { outcome: { issue: [{ severity: "information", code: "informational", diagnostics: "No issues detected during validation" }] },
      http_status: 200, server: "test", checked_at: "2026-10-01T00:00:00Z", note: "Validated against base FHIR R4." } });
  });
  await page.goto("/");
  const lab = page.getByRole("region", { name: "Change the numbers yourself" });
  await expect(lab.getByText("4 rules fail", { exact: true })).toBeVisible(); // the published record
  await lab.getByRole("button", { name: /Test an idea/ }).click();
  await expect(lab.getByText("1 rule fails", { exact: true })).toBeVisible(); // only the series check still fails
  await expect(lab.getByRole("list", { name: "Rules checked on these numbers" }).getByText("SEM-TEMP-001")).toBeVisible();
  await lab.getByRole("textbox", { name: "Mean", exact: true }).fill("999999999");
  await expect(lab.getByText(/rules fail/).first()).toBeVisible();
  await lab.getByRole("button", { name: "Ask the real FHIR server" }).click();
  await expect(lab.getByText("No issues detected during validation")).toBeVisible();
  expect(asked!.values!.average).toBe(999999999);
  await lab.getByRole("button", { name: "Back to the published numbers" }).click();
  await expect(lab.getByText("4 rules fail", { exact: true })).toBeVisible();
  await expect(lab.getByText("The numbers changed since you asked.")).toBeVisible();
});

test("check your own data: a real record and a clean one, as a Bundle", async ({ page }) => {
  await page.goto("/check");
  await page.getByRole("button", { name: "Both, as a Bundle" }).click();
  await expect(page.getByLabel("FHIR JSON or NDJSON")).toHaveValue(/"resourceType": "Bundle"/);
  await page.getByRole("button", { name: "Check this data" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "1 of 2 records has problems" })).toBeVisible();
  await expect(page.getByText("identical to the published record").first()).toBeVisible();
  await page.getByLabel("FHIR JSON or NDJSON").fill("not json");
  await page.getByRole("button", { name: "Check this data" }).click();
  await expect(page.getByRole("alert")).toContainText("not valid JSON");
});

test("claims are read live while typing, by keyword rules", async ({ page }) => {
  await page.goto("/claims");
  await page.locator("#claim-text").pressSequentially("PM10 at Benevento site 04 exceeded the WHO guideline in 2018", { delay: 5 });
  await expect(page.getByText("✓ ready to check")).toBeVisible();
  await expect(page.getByText("kind: a value exceeds a limit or guideline")).toBeVisible();
});

test("the published data: where it comes from, a series over time, every record as published", async ({ page }) => {
  const obs = await (await page.request.get("/api/observations")).json();
  const flagged = obs.items.filter((o: { blocking: boolean }) => o.blocking).length;
  await page.goto("/data");
  await expect(page.getByRole("heading", { level: 1, name: "The published data" })).toBeVisible();
  await expect(page.getByRole("link", { name: "https://sandbox.hl7europe.eu/oneaquahealth/fhir" })).toBeVisible();
  // The default series is the anchor record's: annual mean water temperature at Almyros, 198,000 in 2013.
  await expect(page.getByRole("combobox", { name: "Measure and place" })).toHaveValue(/water-temperature\|Loc-Almyros\|\|summary/);
  const chart = page.getByRole("img", { name: /Mean of Water temperature, Almyros/ });
  await expect(chart).toBeVisible();
  await expect(chart.getByText("198,000", { exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "Statistic" }).selectOption("median");
  await expect(page.getByRole("img", { name: /Median of Water temperature, Almyros/ }).getByText("19.8", { exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "Status" }).selectOption("problems");
  await expect(page.getByText(new RegExp(`of ${flagged} records \\(filtered from ${obs.total}\\)`))).toBeVisible();
  await expect(page.getByRole("link", { name: /Open Observation\/.+ on the FHIR server/ }).first()).toHaveAttribute("href", /^https:\/\/sandbox\.hl7europe\.eu\/oneaquahealth\/fhir\/Observation\//);
});

for (const path of ["/", "/data", "/findings", "/compare?id=cmp-obesity-benevento-vs-oslo-18-29", "/claims", "/check", "/report", "/sources"]) {
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

test("finding detail: what is wrong, why, root cause unknown, and the raw record with the flagged fields highlighted", async ({ page }) => {
  const ov = await (await page.request.get("/api/overview")).json();
  await page.goto(`/findings/${encodeURIComponent(ov.hero_finding.id)}`);
  const hero = page.getByRole("region", { name: "What is wrong and why" });
  await expect(hero.getByRole("list", { name: "Evidence chain" }).getByRole("heading")).toHaveText(
    ["1 Observed", "2 Calculation", "3 Result", "4 Rule broken", "5 Conclusion", "6 Root cause"],
  );
  await expect(hero.getByText(/Root cause:\s*unknown/i)).toBeVisible();
  await page.getByRole("button", { name: "View raw resource" }).click();
  const drawer = page.getByRole("dialog");
  await expect(drawer).toBeVisible();
  expect(await drawer.locator("[data-hit=true]").count()).toBeGreaterThan(0);
  await expect(drawer.locator("[data-hit=true]").first()).toBeInViewport();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
});

test("the claim ladder shows how far the evidence reaches", async ({ page }) => {
  await page.goto("/claims?id=clm-obesity-benevento-higher-than-oslo");
  await expect(page.getByRole("heading", { name: "How far the evidence reaches" })).toBeVisible();
  await expect(page.getByText("The evidence reaches Description; your claim needs Comparison.")).toBeVisible();
  await expect(page.getByRole("list", { name: "Evidence ladder" }).getByText("your claim")).toBeVisible();
  await page.goto("/claims?id=clm-benevento04-pm10-exceeds-who-2018");
  await expect(page.getByText("The evidence reaches Comparison.")).toBeVisible();
});

test("Ctrl+K searches what the audit found and opens it", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Control+k");
  const box = page.getByRole("combobox", { name: /Search findings/ });
  await expect(box).toBeFocused();
  await box.fill("SEM-STAT-001 Almyros 2013 temperature");
  await expect(page.getByRole("listbox", { name: "Results" }).getByRole("option").first()).toContainText("SEM-STAT-001");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/findings\/F-SEM-STAT-001-/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Water temperature");
});

test("the impact trace: selecting a node shows what it depends on and what uses it", async ({ page }) => {
  const ov = await (await page.request.get("/api/overview")).json();
  await page.goto(`/findings/${encodeURIComponent(ov.hero_finding.id)}`);
  const claim = page.getByRole("button", { name: /Claim .*median water temperature/ });
  await claim.click();
  await expect(claim).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("Depends on")).toBeVisible();
  await expect(page.getByRole("link", { name: "See this claim and its evidence" })).toBeVisible();
});

test("keyboard users can skip to content", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
});

test("no page scrolls sideways on a phone @mobile", async ({ page }) => {
  const ov = await (await page.request.get("/api/overview")).json();
  for (const path of ["/", "/data", "/findings", `/findings/${encodeURIComponent(ov.hero_finding.id)}`, "/compare?id=cmp-obesity-benevento-vs-oslo-female",
    "/claims?id=clm-benevento-pm25-exceeds-who", "/check", "/report", "/sources"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal overflow on ${path}`).toBeLessThanOrEqual(1);
  }
});

test("the theme is an icon-only control with Dark, Light and System, remembered across visits", async ({ page }) => {
  await page.goto("/");
  const html = page.locator("html");
  await expect(html).toHaveAttribute("data-theme", "dark"); // dark by default
  const button = page.getByRole("button", { name: "Change theme" });
  await expect(button).toHaveAttribute("title", "Change theme");
  await button.click();
  const menu = page.getByRole("menu", { name: "Theme" });
  await expect(menu.getByRole("menuitemradio")).toHaveText(["Dark", "Light", "System"]);
  await expect(menu.getByRole("menuitemradio", { name: "Dark" })).toHaveAttribute("aria-checked", "true");
  await menu.getByRole("menuitemradio", { name: "Light" }).click();
  await expect(html).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(html).toHaveAttribute("data-theme", "light");
  await button.click();
  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
  await expect(button).toBeFocused();
});

test("the sidebar groups pages under strong section labels", async ({ page }) => {
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Main" });
  await expect(nav.getByRole("list", { name: "Investigate" }).getByRole("link")).toHaveText(["Data health", "Findings", "Compare", "Check a claim", "Report"]);
  await expect(nav.getByRole("list", { name: "Data" }).getByRole("link")).toHaveText(["The data", "Check your data", "Sources & rules"]);
  const size = (sel: string) => page.locator(sel).first().evaluate((e) => parseFloat(getComputedStyle(e).fontSize));
  const weight = (sel: string) => page.locator(sel).first().evaluate((e) => Number(getComputedStyle(e).fontWeight));
  expect(await size("#nav-Investigate")).toBeGreaterThanOrEqual(12);
  expect(await weight("#nav-Investigate")).toBeGreaterThanOrEqual(650);
  expect(await weight("#nav-Investigate")).toBeGreaterThan(await weight('nav[aria-label="Main"] a:not([aria-current])'));
});

test("findings filter by category and by place, from what the audit read", async ({ page }) => {
  const all = await (await page.request.get("/api/findings?limit=1")).json();
  await page.goto("/findings");
  await page.getByLabel("Category", { exact: true }).selectOption("SEMANTIC");
  await expect(page.getByText(`${all.facets.category.SEMANTIC} findings of ${all.total}`)).toBeVisible();
  await page.getByLabel("Category", { exact: true }).selectOption("");
  await page.getByLabel("Place", { exact: true }).selectOption("Almyros monitoring reach");
  const rows = page.locator("tbody tr");
  await expect(rows.first()).toBeVisible();
  for (const place of await page.locator("tbody tr td:nth-child(4)").allTextContents()) expect(place).toBe("Almyros monitoring reach");
});

test("on a phone the navigation opens as a drawer @mobile", async ({ page, isMobile }) => {
  test.skip(!isMobile, "the drawer is the phone layout");
  await page.goto("/");
  await page.getByRole("button", { name: "Open the menu" }).click();
  const drawer = page.getByRole("dialog", { name: "Menu" });
  await expect(drawer.getByRole("button", { name: "Change theme" })).toBeVisible();
  await drawer.getByRole("link", { name: "Sources & rules" }).click();
  await expect(page).toHaveURL(/\/sources$/);
  await expect(drawer).toBeHidden();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Sources & rules");
});

test("every finding proves itself: the calculation on screen is the backend's own evidence", async ({ page }) => {
  const list = await (await page.request.get("/api/findings?resource=Observation/Obs-Almyros-TemperatureWater-2013&rule=SEM-SCALE-001")).json();
  const id = list.items[0].id;
  const detail = await (await page.request.get(`/api/findings/${encodeURIComponent(id)}`)).json();
  const step = detail.calculation.steps[0];
  expect(step.expression).toBe("average / median = 198,000 / 19.8");
  expect(step.value).toBe(detail.finding.evidence.measures.mean_median_ratio);
  await page.goto(`/findings/${encodeURIComponent(id)}`);
  const chain = page.getByRole("list", { name: "Evidence chain" });
  await expect(chain.getByText(`${step.expression} = ${step.result}`, { exact: true })).toBeVisible();
  await expect(chain.getByText(detail.calculation.result, { exact: true })).toBeVisible(); // "... exactly 10⁴."
  await expect(chain.getByText(detail.calculation.check.evaluated, { exact: true })).toBeVisible();
  await expect(chain.getByText("does not hold")).toBeVisible();
  await expect(chain.getByText(/Root cause:\s*unknown/i)).toBeVisible();
  // Never a corrected value: the page states no "correct" temperature.
  await expect(page.getByText(/correct(ed)? (value|temperature)|actual temperature/i)).toHaveCount(0);
});
