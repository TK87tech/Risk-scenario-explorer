import { expect, test, type Page } from "@playwright/test";

const API = process.env.API_URL ?? "http://localhost:8000";
const fmt = (n: number) => new Intl.NumberFormat("en-US").format(n);

async function signIn(page: Page, username: string) {
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(username); // demo realm: password = username
  await page.locator("#kc-login").click();
  await expect(page.getByText(`Signed in as ${username}`)).toBeVisible();
}

test("public users see results that match the API", async ({ page, request }) => {
  const api = await (await request.get(`${API}/api/scenarios/rp100/results`)).json();
  await page.goto("/");
  await expect(page.getByTestId("exposed-total")).toHaveText(fmt(api.summary.exposed_population));
  await expect(page.locator("tbody tr")).toHaveCount(77);
  await expect(page.locator("tbody tr").first().locator("th")).toHaveText(api.provinces[0].province);
});

test("comparing scenarios shows the change from the API", async ({ page, request }) => {
  const cmp = await (await request.get(`${API}/api/compare?base=rp100&target=rp100_2050`)).json();
  await page.goto("/");
  await page.getByLabel("Scenario", { exact: true }).selectOption("rp100_2050");
  await page.getByLabel("Compare with", { exact: true }).selectOption("rp100");
  await expect(page.getByTestId("change-total")).toHaveText(`+${fmt(cmp.change)}`);
});

test("asking and downloading require sign-in", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Ask" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Download CSV" })).toBeDisabled();
});

test("a viewer can ask but not download", async ({ page }) => {
  await page.goto("/");
  await signIn(page, "viewer");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(page.getByTestId("answer")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole("button", { name: "Download CSV" })).toBeDisabled();
});

test("an analyst can download results", async ({ page }) => {
  await page.goto("/");
  await signIn(page, "analyst");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV" }).click();
  expect((await download).suggestedFilename()).toBe("rp100_results.csv");
});
