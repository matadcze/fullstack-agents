import { test, expect } from "@playwright/test";

const APP_NAME = "{{PROJECT_NAME}}";

test("login page renders", async ({ page }) => {
  await page.goto("/login");

  await expect(page.getByRole("heading", { name: APP_NAME })).toBeVisible();
  await expect(page.getByPlaceholder("Email address")).toBeVisible();
  await expect(page.getByPlaceholder("Password")).toBeVisible();
  await expect(page.getByRole("button", { name: /Sign in/i })).toBeVisible();
});

test("register page renders and links back to login", async ({ page }) => {
  await page.goto("/register");

  await expect(page.getByRole("heading", { name: APP_NAME })).toBeVisible();
  await expect(page.getByPlaceholder("Email address")).toBeVisible();
  await expect(page.getByPlaceholder("Password (min 8 characters)")).toBeVisible();
  await expect(page.getByPlaceholder("Confirm password")).toBeVisible();

  await page.getByRole("link", { name: /Already have an account/i }).click();
  await expect(page).toHaveURL(/login/);
});
