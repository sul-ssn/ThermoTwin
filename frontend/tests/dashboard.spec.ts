import { test, expect } from "@playwright/test";
async function mapReady(page: import("@playwright/test").Page) {
  await expect(page.locator(".map-canvas")).toHaveAttribute(
    "data-rendered",
    /^[1-9][0-9]*$/,
    { timeout: 20000 },
  );
  expect(
    (await page.locator(".map-canvas").boundingBox())?.height,
  ).toBeGreaterThan(400);
}
test("light dispatcher design keeps calculations, telemetry and PDF working", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  const networkResponse = page.waitForResponse(
    (r) => r.url().endsWith("/api/v1/network") && r.status() === 200,
  );
  await page.getByRole("button", { name: "Войти в систему" }).click();
  const network = await (await networkResponse).json();
  expect(network.geography.city).toBe("Костанай");
  expect(network.geography.district).toBe("Юбилейный");
  await expect(page.locator(".district")).toContainText("Костанай · Юбилейный");
  await expect(
    page.getByRole("heading", { name: "Карта тепловой сети" }),
  ).toBeVisible();
  await mapReady(page);
  await page.screenshot({ path: "../docs/design-network.png", fullPage: true });
  await page
    .getByRole("button", { name: "Смоделировать аварию", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Шаг 1. Тип аварии" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Продолжить", exact: true }).click();
  await page.getByRole("button", { name: "Продолжить", exact: true }).click();
  await page.getByRole("button", { name: "Рассчитать последствия" }).click();
  await expect(
    page.getByRole("heading", { name: "Результат расчёта" }),
  ).toBeVisible();
  await expect(page.locator(".variant")).toHaveCount(2);
  await page.getByRole("button", { name: "Вариант 2", exact: true }).click();
  await mapReady(page);
  await page.screenshot({
    path: "../docs/design-simulation.png",
    fullPage: true,
  });
  const reportRequest = page.waitForRequest(
    (r) => r.url().includes("/reports/") && r.url().includes("variant_index=1"),
  );
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "PDF-отчёт", exact: true }).click();
  await reportRequest;
  expect((await download).suggestedFilename()).toMatch(/ThermoTwin.*\.pdf/);
  await page.getByRole("button", { name: "Зарегистрировать инцидент" }).click();
  await expect(
    page.getByText("Демонстрационный инцидент зарегистрирован"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Телеметрия", exact: true }).click();
  await mapReady(page);
  await page
    .getByRole("combobox", { name: "Профиль телеметрии" })
    .selectOption("no_connection");
  await expect(
    page.locator(".sensor-panel").getByText("Нет связи", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Профиль телеметрии" })
    .selectOption("normal");
  await expect(
    page.locator(".sensor-panel").getByText("Норма", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/design-telemetry.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Таблица", exact: true }).click();
  await expect(page.locator(".telemetry-main table tbody tr")).toHaveCount(
    network.sensors.length,
  );
  await page.getByRole("button", { name: "График", exact: true }).click();
  await expect(page.locator(".chart-large svg")).toBeVisible();
  await page.getByRole("button", { name: "Отчёты", exact: true }).click();
  await expect(
    page.locator('canvas[aria-label="Предпросмотр PDF-отчёта"]'),
  ).toHaveAttribute("data-ready", "true", { timeout: 20000 });
  await page.screenshot({ path: "../docs/design-reports.png", fullPage: true });
  expect(errors).toEqual([]);
});
test("mobile design offers map and bottom navigation without horizontal overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Войти в систему" }).click();
  await expect(
    page.getByRole("heading", { name: "Карта тепловой сети" }),
  ).toBeVisible();
  await mapReady(page);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: "../docs/design-mobile.png", fullPage: true });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page
    .locator(".mobile-bottom")
    .getByRole("button", { name: "Телеметрия", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Телеметрия", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("button", { name: "Открыть меню" }).click();
  await expect(page.locator(".sidebar.mobile-open")).toBeVisible();
  await page
    .locator(".sidebar.mobile-open")
    .getByRole("button", { name: "Карта сети", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Карта тепловой сети" }),
  ).toBeVisible();
});
