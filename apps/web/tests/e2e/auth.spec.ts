import { test, expect, type Page, type Route } from "@playwright/test";

const CORS_HEADERS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,PUT,DELETE,OPTIONS",
  "access-control-allow-headers": "authorization,content-type",
  "access-control-expose-headers": "x-correlation-id",
};

type StoredUser = { id: string; email: string; password: string; full_name: string | null };
type RecordedRequest = { method: string; path: string; body: unknown };

/** In-memory stand-in for the FastAPI auth endpoints, installed with page.route. */
class FakeApi {
  users = new Map<string, StoredUser>();
  requests: RecordedRequest[] = [];
  activeTokens = new Map<string, string>();
  nextResponse: { status: number; body: unknown; headers?: Record<string, string> } | null = null;

  addUser(email: string, password: string, fullName: string | null = "Existing User") {
    this.users.set(email, { id: crypto.randomUUID(), email, password, full_name: fullName });
  }

  calls(method: string, path: string) {
    return this.requests.filter((r) => r.method === method && r.path === path);
  }

  async install(page: Page) {
    await page.route(/\/api\/v1\//, (route) => this.handle(route));
  }

  private async reply(route: Route, status: number, body?: unknown, headers = {}) {
    await route.fulfill({
      status,
      headers: { ...CORS_HEADERS, "content-type": "application/json", ...headers },
      body: body === undefined ? "" : JSON.stringify(body),
    });
  }

  private publicUser(user: StoredUser) {
    return {
      id: user.id,
      email: user.email,
      full_name: user.full_name,
      created_at: "2026-01-01T00:00:00",
    };
  }

  private async handle(route: Route) {
    const request = route.request();
    const method = request.method();
    if (method === "OPTIONS") return this.reply(route, 204);

    const path = new URL(request.url()).pathname;
    const body = request.postData() ? request.postDataJSON() : undefined;
    this.requests.push({ method, path, body });

    if (this.nextResponse) {
      const { status, body: responseBody, headers } = this.nextResponse;
      this.nextResponse = null;
      return this.reply(route, status, responseBody, headers);
    }

    const token = request.headers()["authorization"]?.replace(/^Bearer /, "");
    const caller = token ? this.users.get(this.activeTokens.get(token) ?? "") : undefined;

    if (method === "POST" && path === "/api/v1/auth/register") {
      if (this.users.has(body.email)) {
        return this.reply(route, 400, { detail: "Email already registered" });
      }
      this.addUser(body.email, body.password, body.full_name ?? null);
      return this.reply(route, 201, this.publicUser(this.users.get(body.email)!));
    }

    if (method === "POST" && path === "/api/v1/auth/login") {
      const user = this.users.get(body.email);
      if (!user || user.password !== body.password) {
        return this.reply(route, 401, { detail: "Invalid email or password" });
      }
      const accessToken = `access-${crypto.randomUUID()}`;
      this.activeTokens.set(accessToken, user.email);
      return this.reply(route, 200, {
        access_token: accessToken,
        refresh_token: `refresh-${crypto.randomUUID()}`,
        token_type: "Bearer",
        expires_in: 900,
      });
    }

    if (path === "/api/v1/auth/me") {
      if (!caller) return this.reply(route, 401, { detail: "User not found" });
      if (method === "GET") return this.reply(route, 200, this.publicUser(caller));
      if (method === "DELETE") {
        this.users.delete(caller.email);
        return this.reply(route, 204);
      }
    }

    return this.reply(route, 404, { detail: `Unmocked ${method} ${path}` });
  }
}

let api: FakeApi;

test.beforeEach(async ({ page }) => {
  api = new FakeApi();
  await api.install(page);
});

async function storedTokens(page: Page) {
  return page.evaluate(() => ({
    access: localStorage.getItem("access_token"),
    refresh: localStorage.getItem("refresh_token"),
  }));
}

async function fillLogin(page: Page, email: string, password: string) {
  await page.getByPlaceholder("Email address").fill(email);
  await page.getByPlaceholder("Password").fill(password);
  await page.getByRole("button", { name: /Sign in/i }).click();
}

async function fillRegister(
  page: Page,
  { email, password, confirm = password, fullName = "" }: Record<string, string>,
) {
  if (fullName) await page.getByPlaceholder("Full Name").fill(fullName);
  await page.getByPlaceholder("Email address").fill(email);
  await page.getByPlaceholder("Password (min 8 characters)").fill(password);
  await page.getByPlaceholder("Confirm password").fill(confirm);
  await page.getByRole("button", { name: /Sign up/i }).click();
}

test.describe("registration", () => {
  test("creates the account, signs in and lands on the dashboard", async ({ page }) => {
    await page.goto("/register");
    await fillRegister(page, {
      email: "new@example.com",
      password: "CorrectHorse1!",
      fullName: "Ada Lovelace",
    });

    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByText("Welcome, Ada Lovelace")).toBeVisible();
    expect(api.calls("POST", "/api/v1/auth/register")[0].body).toEqual({
      email: "new@example.com",
      password: "CorrectHorse1!",
      full_name: "Ada Lovelace",
    });
    expect((await storedTokens(page)).refresh).toMatch(/^refresh-/);
  });

  test("full name is optional", async ({ page }) => {
    await page.goto("/register");
    await fillRegister(page, { email: "anon@example.com", password: "CorrectHorse1!" });

    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByText("Welcome, anon@example.com")).toBeVisible();
    expect(api.calls("POST", "/api/v1/auth/register")[0].body).not.toHaveProperty("full_name");
  });

  test("shows the API error for an already registered email", async ({ page }) => {
    api.addUser("taken@example.com", "CorrectHorse1!");
    await page.goto("/register");
    await fillRegister(page, { email: "taken@example.com", password: "AnotherPass1!" });

    await expect(page.getByText("Email already registered")).toBeVisible();
    await expect(page).toHaveURL(/\/register$/);
    expect(api.calls("POST", "/api/v1/auth/login")).toHaveLength(0);
    expect((await storedTokens(page)).access).toBeNull();
  });

  test("validates the form before calling the API", async ({ page }) => {
    await page.goto("/register");
    await fillRegister(page, {
      email: "mismatch@example.com",
      password: "CorrectHorse1!",
      confirm: "Different1!",
    });
    await expect(page.getByText("Passwords do not match")).toBeVisible();

    await page.getByPlaceholder("Password (min 8 characters)").fill("short");
    await page.getByPlaceholder("Confirm password").fill("short");
    await page.getByRole("button", { name: /Sign up/i }).click();
    await expect(page.getByText("Password must be at least 8 characters")).toBeVisible();

    expect(api.requests).toHaveLength(0);
  });
});

test.describe("login", () => {
  test("rejects wrong credentials without storing tokens", async ({ page }) => {
    api.addUser("user@example.com", "CorrectHorse1!");
    await page.goto("/login");
    await fillLogin(page, "user@example.com", "WrongPass123");

    await expect(page.getByText("Invalid email or password")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("button", { name: /Sign in/i })).toBeEnabled();
    expect(await storedTokens(page)).toEqual({ access: null, refresh: null });
  });

  test("surfaces server error messages with the correlation id", async ({ page }) => {
    api.nextResponse = {
      status: 500,
      body: {
        error: {
          code: "InternalServerError",
          message: "An unexpected error occurred",
          details: {},
          correlation_id: "corr-123",
        },
      },
      headers: { "x-correlation-id": "corr-123" },
    };
    await page.goto("/login");
    await fillLogin(page, "user@example.com", "CorrectHorse1!");

    await expect(page.getByText("An unexpected error occurred (Ref: corr-123)")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("validates the form before calling the API", async ({ page }) => {
    await page.goto("/login");
    // Passes the browser's type=email check but not the app's stricter validator.
    await fillLogin(page, "user@localhost", "short");

    await expect(page.getByText("Enter a valid email address")).toBeVisible();
    await expect(page.getByText("Password must be at least 8 characters")).toBeVisible();
    expect(api.requests).toHaveLength(0);
  });

  test("valid credentials reach the dashboard", async ({ page }) => {
    api.addUser("user@example.com", "CorrectHorse1!", "Grace");
    await page.goto("/login");
    await fillLogin(page, "user@example.com", "CorrectHorse1!");

    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByText("Welcome, Grace")).toBeVisible();
  });
});

test.describe("authorization", () => {
  for (const path of ["/dashboard", "/profile"]) {
    test(`${path} redirects anonymous visitors to login`, async ({ page }) => {
      await page.goto(path);
      await expect(page).toHaveURL(/\/login$/);
    });
  }

  test("a rejected stored token is cleared and the user is sent to login", async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("access_token", "stale-token"));
    await page.goto("/dashboard");

    await expect(page).toHaveURL(/\/login$/);
    expect(api.calls("GET", "/api/v1/auth/me").length).toBeGreaterThan(0);
    expect((await storedTokens(page)).access).toBeNull();
  });
});

test.describe("account deletion", () => {
  async function signInAndOpenProfile(page: Page) {
    api.addUser("leaving@example.com", "CorrectHorse1!", "Leaving");
    await page.goto("/login");
    await fillLogin(page, "leaving@example.com", "CorrectHorse1!");
    await expect(page).toHaveURL(/\/dashboard$/);
    await page.getByRole("link", { name: "Profile", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Delete account" })).toBeVisible();
  }

  test("deletes once after confirmation, signs out and clears tokens", async ({ page }) => {
    await signInAndOpenProfile(page);
    const dialogs: string[] = [];
    page.on("dialog", (dialog) => {
      dialogs.push(dialog.message());
      void dialog.accept();
    });

    await page.getByRole("button", { name: "Delete account" }).click();

    await expect(page).toHaveURL(/\/login$/);
    expect(dialogs).toHaveLength(1);
    expect(api.calls("DELETE", "/api/v1/auth/me")).toHaveLength(1);
    expect(await storedTokens(page)).toEqual({ access: null, refresh: null });
    expect(api.users.has("leaving@example.com")).toBe(false);
  });

  test("cancelling the confirmation keeps the account", async ({ page }) => {
    await signInAndOpenProfile(page);
    page.on("dialog", (dialog) => void dialog.dismiss());

    await page.getByRole("button", { name: "Delete account" }).click();

    await expect(page.getByRole("heading", { name: "Account settings" })).toBeVisible();
    expect(api.calls("DELETE", "/api/v1/auth/me")).toHaveLength(0);
    expect((await storedTokens(page)).access).not.toBeNull();
  });
});
