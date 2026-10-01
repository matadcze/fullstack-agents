import { test, expect } from "@playwright/test";

const user = {
  id: "user",
  email: "user@example.com",
  full_name: "Test User",
  created_at: "2026-01-01T00:00:00Z",
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("access_token", "old-access");
    localStorage.setItem("refresh_token", "old-refresh");
  });
});

test("retains stored credentials when the initial /me request fails temporarily", async ({
  page,
}) => {
  await page.route("**/api/v1/auth/me", (route) => route.abort("failed"));
  await page.goto("/profile");
  await expect(page).toHaveURL(/login/);
  await expect(page.getByRole("button", { name: /Sign in/i })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("access_token"))).toBe("old-access");
  expect(await page.evaluate(() => localStorage.getItem("refresh_token"))).toBe("old-refresh");
});

test("preserves the loaded user and reports a temporary /me failure on profile refresh", async ({
  page,
}) => {
  let failMe = false;
  await page.route("**/api/v1/auth/me", async (route) => {
    if (!failMe) await route.fulfill({ json: user });
    else await route.fulfill({ status: 503, json: { detail: "Service unavailable" } });
  });
  await page.route("**/api/v1/auth/profile", (route) => {
    failMe = true;
    return route.fulfill({ json: { ...user, full_name: "Updated User" } });
  });
  await page.goto("/profile");
  await expect(page.getByText(user.email)).toBeVisible();
  await page.getByPlaceholder("Your name").fill("Updated User");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Service unavailable")).toBeVisible();
  await expect(page.getByText(user.email)).toBeVisible();
  await expect(page).toHaveURL(/profile/);
  expect(await page.evaluate(() => localStorage.getItem("access_token"))).toBe("old-access");
});

for (const status of [401, 403]) {
  test(`clears the user and both tokens when /me confirms an invalid session (${status})`, async ({
    page,
  }) => {
    await page.route("**/api/v1/auth/me", (route) =>
      route.fulfill({ status, json: { detail: "Invalid session" } }),
    );
    await page.route("**/api/v1/auth/refresh", (route) =>
      route.fulfill({ status: 401, json: { detail: "Invalid refresh token" } }),
    );
    await page.goto("/profile");
    await expect(page).toHaveURL(/login/);
    expect(await page.evaluate(() => localStorage.getItem("access_token"))).toBeNull();
    expect(await page.evaluate(() => localStorage.getItem("refresh_token"))).toBeNull();
  });
}

test("loads the user after automatically refreshing an expired access token", async ({ page }) => {
  let refreshCount = 0;
  await page.route("**/api/v1/auth/me", (route) => {
    if (route.request().headers()["authorization"] === "Bearer old-access") {
      return route.fulfill({ status: 401, json: { detail: "Expired token" } });
    }
    return route.fulfill({ json: user });
  });
  await page.route("**/api/v1/auth/refresh", (route) => {
    refreshCount++;
    expect(route.request().postDataJSON()).toEqual({ refresh_token: "old-refresh" });
    return route.fulfill({
      json: {
        access_token: "new-access",
        refresh_token: "new-refresh",
        token_type: "bearer",
        expires_in: 3600,
      },
    });
  });
  await page.goto("/profile");
  await expect(page.getByText(user.email)).toBeVisible();
  await expect(page).toHaveURL(/profile/);
  expect(refreshCount).toBe(1);
  expect(await page.evaluate(() => localStorage.getItem("access_token"))).toBe("new-access");
  expect(await page.evaluate(() => localStorage.getItem("refresh_token"))).toBe("new-refresh");
});

test("updates AuthContext when another endpoint invalidates the session", async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: user }));
  await page.route("**/api/v1/auth/profile", (route) =>
    route.fulfill({ status: 401, json: { detail: "Expired token" } }),
  );
  await page.route("**/api/v1/auth/refresh", (route) =>
    route.fulfill({ status: 401, json: { detail: "Invalid refresh token" } }),
  );
  await page.goto("/profile");
  await expect(page.getByText(user.email)).toBeVisible();
  await page.getByPlaceholder("Your name").fill("Updated User");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page).toHaveURL(/login/);
  expect(await page.evaluate(() => localStorage.getItem("access_token"))).toBeNull();
  expect(await page.evaluate(() => localStorage.getItem("refresh_token"))).toBeNull();
});
