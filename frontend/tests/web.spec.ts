import { test, expect, chromium, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
async function login(page: Page, code: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Smart-ID", exact: true }).click();
  await page.getByLabel("Personal ID code").fill(code);
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByRole("heading", { name: /^Hi, / })).toBeVisible();
}
async function accessible(page: Page) {
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
}
test("keyboard login, protected navigation, history, external hand-off and logout", async ({
  page,
}) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("button", { name: "Smart-ID", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await page.getByLabel("Personal ID code").focus();
  await page.keyboard.type("00000000000");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("alert")).toContainText("AUTH_INVALID");
  await accessible(page);
  await login(page, "00000000002");
  await accessible(page);
  await page.getByRole("link", { name: "Licence", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Medical certificate" }),
  ).toBeVisible();
  await accessible(page);
  const licenceCard = page.locator("section.card").filter({
    has: page.getByRole("heading", { name: "Driving licence", exact: true }),
  });
  const medicalCard = page.locator("section.card").filter({
    has: page.getByRole("heading", {
      name: "Medical certificate",
      exact: true,
    }),
  });
  await expect(
    medicalCard.getByRole("button", { name: "See how to renew" }),
  ).toHaveCount(0);
  await licenceCard.getByRole("button", { name: "See how to renew" }).click();
  await expect(
    page.getByRole("heading", { name: "Renew your driving licence" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Open the official e-service" })
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "Transport Administration",
  );
  // Exercise the actual popup without sending a test browser to the official service.
  await page.context().route(/^https:\/\//, (route) =>
    route.fulfill({
      contentType: "text/html",
      body: "<title>Official destination</title>",
    }),
  );
  const opened = page.waitForEvent("popup");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  const popup = await opened;
  await expect(popup).toHaveTitle("Official destination");
  const destination = popup.url();
  await popup.close();
  await page
    .getByRole("button", { name: "Open the official e-service" })
    .click();
  await page.evaluate(() => {
    window.open = () => null;
  });
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  const fallback = page.getByRole("dialog", {
    name: "Couldn’t open the e-service",
  });
  await expect(fallback).toContainText("DLR-EXT-001");
  await expect(fallback.getByRole("link")).toHaveAttribute("href", destination);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("link", { name: "History", exact: true }).click();
  await page.getByRole("button", { name: "Status checks" }).click();
  await expect(
    page.getByText("latest successful", { exact: false }).first(),
  ).toBeVisible();
  await expect(
    page.locator("article").filter({ hasText: "latest successful" }),
  ).toContainText("Estonian Transport Administration via X-Road");
  await accessible(page);
  await page
    .getByRole("link", { name: "Driving Licence Reminder" })
    .press("Enter");
  await expect(page).toHaveURL(/#overview$/);
  await expect(page.getByRole("heading", { name: /^Hi, / })).toBeVisible();
  await page.getByRole("button", { name: "Log out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "You’re logged out" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Log in again" }).click();
  await expect(page.getByRole("heading", { name: "Log in" })).toBeVisible();
});
test("medical fixture, reminder controls, narrow layout and menu", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, "00000000007");
  const refreshed = page.waitForResponse(
    (r) =>
      r.url().endsWith("/me/driving-data/refresh") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Refresh data" }).click();
  await refreshed;
  await expect(
    page.getByRole("status").filter({ hasText: "Data refreshed." }),
  ).toContainText("At risk");
  await expect(
    page.getByRole("heading", { name: "Renew your medical certificate" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Licence", exact: true }).click();
  await expect(
    page
      .locator("section")
      .filter({
        has: page.getByRole("heading", { name: "Medical certificate" }),
      })
      .locator("dt")
      .filter({ hasText: /^Required$/ })
      .locator("+ dd"),
  ).toHaveText("Yes");
  await expect(
    page
      .locator("section.card")
      .filter({
        has: page.getByRole("heading", {
          name: "Driving licence",
          exact: true,
        }),
      })
      .getByRole("button", { name: "See how to renew" }),
  ).toHaveCount(0);
  await page
    .locator("section.card")
    .filter({
      has: page.getByRole("heading", {
        name: "Medical certificate",
        exact: true,
      }),
    })
    .getByRole("button", { name: "See how to renew" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Renew your medical certificate" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Driving Licence Reminder" }).click();
  await expect(page.getByRole("heading", { name: /^Hi, / })).toBeVisible();
  await expect(page.getByRole("navigation")).toBeVisible();
  await page.getByRole("link", { name: "Reminders", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Reminders" }).first(),
  ).toBeVisible();
  await accessible(page);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  const turnOff = page.getByRole("button", { name: "Turn off reminders" });
  if (await turnOff.isVisible()) {
    await turnOff.click();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(turnOff).toBeVisible();
  } else {
    await page.getByRole("button", { name: "Turn on reminders" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
  }
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("button", { name: "Log out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "You’re logged out" }),
  ).toBeVisible();
});
test("unavailable registry exposes an actionable English error", async ({
  page,
}) => {
  await login(page, "00000000005");
  await page.getByRole("button", { name: "Refresh data" }).click();
  await expect(page.getByRole("alert")).toContainText("XR_UNAVAILABLE");
  await expect(page.getByText(/Data refreshed\./)).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Refresh data" }),
  ).toBeEnabled();
});
test("browser displays a delivered push with the page closed", async ({
  baseURL,
}) => {
  // Chrome's temporary off-the-record contexts suppress desktop notifications.
  const context = await chromium.launchPersistentContext("", {
    channel: process.env.PLAYWRIGHT_CHANNEL,
    permissions: ["notifications"],
  });
  try {
    const page = await context.newPage();
    await page.goto(baseURL!);
    await page.evaluate(async () => {
      await navigator.serviceWorker.register("/sw.js");
      await navigator.serviceWorker.ready;
    });
    const background = await context.newPage();
    const cdp = await context.newCDPSession(background);
    const version = new Promise<string>((resolve) =>
      cdp.on("ServiceWorker.workerRegistrationUpdated", (x) => {
        const reg = x.registrations.find(
          (r) => r.scopeURL === new URL("/", baseURL).href,
        );
        if (reg) resolve(reg.registrationId);
      }),
    );
    await cdp.send("ServiceWorker.enable");
    const registrationId = await version;
    await page.close();
    await cdp.send("ServiceWorker.deliverPushMessage", {
      origin: new URL(baseURL!).origin,
      registrationId,
      data: JSON.stringify({
        title: "Driving Licence Reminder",
        body: "Medical certificate deadline: synthetic test",
        tag: "test-reminder",
      }),
    });
    await background.goto(baseURL!);
    await expect
      .poll(() =>
        background.evaluate(async () =>
          (await (await navigator.serviceWorker.ready).getNotifications()).map(
            (n) => n.tag,
          ),
        ),
      )
      .toContain("test-reminder");
  } finally {
    await context.close();
  }
});

test("denied browser permission keeps reminder choices recoverable", async ({
  page,
  context,
  baseURL,
}) => {
  const code = "00000000006";
  const auth = await context.request.post(baseURL + "/api/v1/auth/demo-login", {
    data: { personalCode: code },
  });
  const headers = {
    Authorization: "Bearer " + (await auth.json()).accessToken,
  };
  const endpoint = baseURL + "/api/v1/me/reminder-preferences";
  const old = await (await context.request.get(endpoint, { headers })).json();
  try {
    await context.request.put(endpoint, {
      headers,
      data: { enabled: false, intervals: [30] },
    });
    await login(page, code);
    const cdp = await context.newCDPSession(page);
    await cdp.send("Browser.setPermission", {
      permission: { name: "notifications" },
      setting: "denied",
      origin: new URL(baseURL!).origin,
    });
    await page.getByRole("link", { name: "Reminders", exact: true }).click();
    await page.getByRole("button", { name: "Turn on reminders" }).click();
    await page.getByRole("button", { name: "Allow", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("PUSH_PERMISSION");
    await expect(
      page.getByRole("checkbox", { name: /30 days before/ }),
    ).toBeDisabled();
    expect(
      (await (await context.request.get(endpoint, { headers })).json())
        .intervals,
    ).toEqual([30]);
    expect(
      (await (await context.request.get(endpoint, { headers })).json()).enabled,
    ).toBe(false);
  } finally {
    await context.request.put(endpoint, {
      headers,
      data: { enabled: old.enabled, intervals: old.intervals },
    });
    await context.request.post(baseURL + "/api/v1/auth/logout", { headers });
  }
});

test("all sign-in choices lead to the same demo accounts", async ({ page }) => {
  await page.goto("/");
  for (const method of ["Smart-ID", "Mobile-ID", "ID-card"]) {
    await page.getByRole("button", { name: method, exact: true }).click();
    await expect(page.getByRole("heading", { name: method })).toBeVisible();
    await page.getByText("Demo accounts", { exact: true }).click();
    await page
      .getByRole("button", { name: /Expiring medical certificate/ })
      .click();
    await expect(page.getByLabel("Personal ID code")).toHaveValue(
      "00000000007",
    );
    await page.getByRole("button", { name: /Other methods/ }).click();
  }
});
test("small-screen switch opens a bottom sheet; cancel preserves and confirm disables", async ({
  page,
  context,
  baseURL,
}) => {
  const code = "00000000003";
  const s = await context.request.post(baseURL + "/api/v1/auth/demo-login", {
    data: { personalCode: code },
  });
  const headers = { Authorization: "Bearer " + (await s.json()).accessToken };
  const endpoint = baseURL + "/api/v1/me/reminder-preferences";
  const old = await (await context.request.get(endpoint, { headers })).json();
  try {
    await context.request.put(endpoint, {
      headers,
      data: { enabled: true, intervals: [7] },
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page, code);
    await page.getByRole("button", { name: "Account menu" }).click();
    const menu = page.getByRole("dialog", { name: "Account menu" });
    await expect(menu.getByRole("link")).toHaveCount(4);
    await menu.getByRole("link", { name: "Reminders" }).click();
    await page.getByRole("checkbox", { name: /90 days before/ }).check();
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByText("Saved", { exact: true })).toBeVisible();
    expect(
      (await (await context.request.get(endpoint, { headers })).json())
        .intervals,
    ).toEqual([90, 7]);
    await page.getByRole("switch", { name: "Reminders" }).click();
    const sheet = page.getByRole("dialog", { name: "Turn off reminders?" });
    const box = await sheet.boundingBox();
    expect(box!.width).toBe(390);
    expect(Math.round(box!.y + box!.height)).toBe(844);
    await accessible(page);
    await sheet.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByRole("switch")).toBeChecked();
    await page
      .getByRole("button", { name: "Turn off reminders", exact: true })
      .click();
    await sheet.getByRole("button", { name: "Turn off", exact: true }).click();
    await expect(page.getByRole("switch")).not.toBeChecked();
    expect(
      (await (await context.request.get(endpoint, { headers })).json()).enabled,
    ).toBe(false);
  } finally {
    await context.request.put(endpoint, {
      headers,
      data: { enabled: old.enabled, intervals: old.intervals },
    });
    await context.request.post(baseURL + "/api/v1/auth/logout", { headers });
  }
});

test("slow refresh announces progress and completion on Licence", async ({
  page,
}) => {
  await login(page, "00000000006");
  await page.getByRole("link", { name: "Licence", exact: true }).click();
  await page.getByRole("button", { name: "Refresh data" }).click();
  await expect(
    page.getByRole("button", { name: "Refreshing…" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("status").filter({ hasText: "Checking your licence" }),
  ).toBeVisible();
  await expect(
    page.getByRole("status").filter({ hasText: "Data refreshed." }),
  ).toContainText("Valid");
});

test("local dev server starts when its preferred port is occupied", async () => {
  const { createServer } = await import("vite");
  const preferred = await createServer({
    server: { host: "127.0.0.1", port: 0 },
    logLevel: "silent",
  });
  try {
    await preferred.listen();
    const address = preferred.httpServer!.address();
    if (!address || typeof address === "string")
      throw new Error("Expected a TCP address");
    const second = await createServer({
      server: { host: "127.0.0.1", port: address.port },
      logLevel: "silent",
    });
    try {
      await second.listen();
      const url = second.resolvedUrls!.local[0];
      expect(Number(new URL(url).port)).toBeGreaterThan(address.port);
      expect((await fetch(url)).ok).toBe(true);
    } finally {
      await second.close();
    }
  } finally {
    await preferred.close();
  }
});
