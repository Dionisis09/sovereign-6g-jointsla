import { expect, test } from "@playwright/test";

test("tenant creates a service, runs simulation and inspects decision", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByText("SIMULATION ONLY")).toBeVisible();

  await page.locator(".nav-list").getByRole("button", { name: /Services/ }).click();
  await expect(page.getByRole("heading", { name: "Create service" })).toBeVisible();
  await page.getByLabel("Service name").fill("browser-vision-demo");
  await page.getByRole("button", { name: /Create service/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "Service created" })).toBeVisible();

  const service = page.locator(".record").filter({ hasText: "browser-vision-demo" });
  await expect(service).toBeVisible();
  await service.getByRole("button", { name: /Run simulation/ }).click();
  await expect(page.getByRole("heading", { name: "Run simulation" })).toBeVisible();
  await page.getByRole("button", { name: /Execute in simulator/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "Simulation completed" })).toBeVisible();
  const run = page.locator(".record").filter({ hasText: "browser-vision-demo" });
  await expect(run).toContainText("SIMULATED");
  await run.getByRole("button", { name: /Inspect/ }).click();
  await expect(page.getByRole("heading", { name: "Decision inspector" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Candidates & policy" })).toBeVisible();
  await expect(page.getByText(/SIMULATED SLO (MET|MISSED)/)).toBeVisible();

  await page.locator(".nav-list").getByRole("button", { name: /Telemetry/ }).click();
  await expect(page.getByRole("heading", { name: "Simulated p95 timeline" })).toBeVisible();
  await page.locator(".nav-list").getByRole("button", { name: /Research/ }).click();
  await expect(page.getByRole("heading", { name: /Phase 2/ })).toBeVisible();
});

test("mobile navigation and empty states remain usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await page.locator(".nav-list").getByRole("button", { name: /Services/ }).click();
  await expect(page.getByRole("heading", { name: "Services", exact: true })).toBeVisible();
  await expect(page.getByLabel("Service name")).toBeVisible();
  const horizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  );
  expect(horizontalOverflow).toBe(false);
});
