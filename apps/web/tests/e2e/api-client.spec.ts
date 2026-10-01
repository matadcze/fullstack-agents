import { test, expect } from "@playwright/test";
import { mock } from "node:test";
import { ApiClient, ApiError } from "../../src/lib/api/client";
import type { RefreshTokenRequest, TokenResponse } from "../../src/lib/types/api";

const tokens: TokenResponse = {
  access_token: "new-access",
  refresh_token: "new-refresh",
  token_type: "bearer",
  expires_in: 3600,
};

class MemoryStorage implements Storage {
  private values = new Map<string, string>();

  get length() {
    return this.values.size;
  }
  clear() {
    this.values.clear();
  }
  getItem(key: string) {
    return this.values.get(key) ?? null;
  }
  key(index: number) {
    return [...this.values.keys()][index] ?? null;
  }
  removeItem(key: string) {
    this.values.delete(key);
  }
  setItem(key: string, value: string) {
    this.values.set(key, value);
  }
}

const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((fulfill) => {
    resolve = fulfill;
  });
  return { promise, resolve };
}

test.beforeEach(() => {
  Object.defineProperty(globalThis, "window", { value: {}, configurable: true });
  Object.defineProperty(globalThis, "localStorage", {
    value: new MemoryStorage(),
    configurable: true,
  });
  localStorage.setItem("access_token", "old-access");
  localStorage.setItem("refresh_token", "old-refresh");
});

test.afterEach(() => {
  mock.restoreAll();
  for (const [key, descriptor] of [
    ["window", originalWindow],
    ["localStorage", originalStorage],
  ] as const) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else Reflect.deleteProperty(globalThis, key);
  }
});

test("refreshes an expired access token and retries the original request once", async () => {
  const client = new ApiClient("http://api.test");
  const requests: { url: string; options?: RequestInit }[] = [];
  mock.method(globalThis, "fetch", async (url: string, options?: RequestInit) => {
    requests.push({ url, options });
    if (url.endsWith("/refresh")) return Response.json(tokens);
    if (new Headers(options?.headers).get("Authorization") === "Bearer old-access") {
      return Response.json({ detail: "Expired token" }, { status: 401 });
    }
    return Response.json({ id: "user", email: "user@example.com" });
  });

  await expect(client.auth.me()).resolves.toMatchObject({ id: "user" });
  expect(requests.map(({ url }) => url)).toEqual([
    "http://api.test/api/v1/auth/me",
    "http://api.test/api/v1/auth/refresh",
    "http://api.test/api/v1/auth/me",
  ]);
  expect(JSON.parse(String(requests[1].options?.body))).toEqual({ refresh_token: "old-refresh" });
  expect(client.getAccessToken()).toBe(tokens.access_token);
  expect(localStorage.getItem("refresh_token")).toBe(tokens.refresh_token);
});

test("coordinates concurrent unauthorized requests with one refresh", async () => {
  const client = new ApiClient("http://api.test");
  let refreshCount = 0;
  let originalCount = 0;
  let retryCount = 0;
  mock.method(globalThis, "fetch", async (url: string, options?: RequestInit) => {
    if (url.endsWith("/refresh")) {
      refreshCount++;
      return Response.json(tokens);
    }
    if (new Headers(options?.headers).get("Authorization") === "Bearer old-access") {
      originalCount++;
      return Response.json({ detail: "Expired token" }, { status: 401 });
    }
    retryCount++;
    return Response.json({ id: "user" });
  });

  const results = await Promise.allSettled([
    client.auth.me(),
    client.audit.list(),
    client.agents.run({ prompt: "hello" }),
  ]);
  expect(results.map(({ status }) => status)).toEqual(["fulfilled", "fulfilled", "fulfilled"]);
  expect({ refreshCount, originalCount, retryCount }).toEqual({
    refreshCount: 1,
    originalCount: 3,
    retryCount: 3,
  });
});

test("keeps credentials on network failures without refreshing", async () => {
  const client = new ApiClient("http://api.test");
  const fetchMock = mock.method(globalThis, "fetch", async () => {
    throw new TypeError("Failed to fetch");
  });
  await expect(client.auth.me()).rejects.toMatchObject({ status: 0 });
  expect(client.getAccessToken()).toBe("old-access");
  expect(localStorage.getItem("refresh_token")).toBe("old-refresh");
  expect(fetchMock.mock.calls).toHaveLength(1);
});

test("never retries a request more than once", async () => {
  const client = new ApiClient("http://api.test");
  const fetchMock = mock.method(globalThis, "fetch", async (url: string) => {
    if (url.endsWith("/refresh")) return Response.json(tokens);
    return Response.json({ detail: "Invalid session" }, { status: 401 });
  });
  await expect(client.auth.me()).rejects.toBeInstanceOf(ApiError);
  expect(fetchMock.mock.calls).toHaveLength(3);
  expect(client.getAccessToken()).toBeNull();
  expect(localStorage.getItem("access_token")).toBeNull();
  expect(localStorage.getItem("refresh_token")).toBeNull();
});

for (const status of [400, 403, 422, 429, 500, 503]) {
  test(`does not refresh on a non-401 response (${status})`, async () => {
    const client = new ApiClient("http://api.test");
    const fetchMock = mock.method(globalThis, "fetch", async () =>
      Response.json({ detail: "Request failed" }, { status }),
    );
    await expect(client.audit.list()).rejects.toMatchObject({ status });
    expect(fetchMock.mock.calls).toHaveLength(1);
    expect(client.getAccessToken()).toBe("old-access");
    expect(localStorage.getItem("refresh_token")).toBe("old-refresh");
  });
}

for (const status of [429, 500, 503]) {
  test(`preserves credentials and propagates transient refresh failure (${status})`, async () => {
    const client = new ApiClient("http://api.test");
    const fetchMock = mock.method(globalThis, "fetch", async (url: string) =>
      Response.json(
        { detail: "Request failed" },
        { status: url.endsWith("/refresh") ? status : 401 },
      ),
    );
    await expect(client.auth.me()).rejects.toMatchObject({ status });
    expect(fetchMock.mock.calls).toHaveLength(2);
    expect(client.getAccessToken()).toBe("old-access");
    expect(localStorage.getItem("refresh_token")).toBe("old-refresh");
  });
}

for (const status of [401, 403]) {
  test(`clears both tokens after a rejected refresh (${status}) without recursion`, async () => {
    const client = new ApiClient("http://api.test");
    const fetchMock = mock.method(globalThis, "fetch", async (url: string) =>
      Response.json(
        { detail: "Invalid session" },
        { status: url.endsWith("/refresh") ? status : 401 },
      ),
    );
    await expect(client.auth.me()).rejects.toMatchObject({ status });
    expect(fetchMock.mock.calls).toHaveLength(2);
    expect(client.getAccessToken()).toBeNull();
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
  });
}

test("does not refresh rejected login or registration requests", async () => {
  const client = new ApiClient("http://api.test");
  const fetchMock = mock.method(globalThis, "fetch", async () =>
    Response.json({ detail: "Invalid credentials" }, { status: 401 }),
  );
  await expect(
    client.auth.login({ email: "user@example.com", password: "incorrect" }),
  ).rejects.toMatchObject({ status: 401 });
  await expect(
    client.auth.register({ email: "user@example.com", password: "incorrect" }),
  ).rejects.toMatchObject({ status: 401 });
  expect(fetchMock.mock.calls).toHaveLength(2);
  for (const { arguments: args } of fetchMock.mock.calls) {
    expect(new Headers(args[1]?.headers).has("Authorization")).toBe(false);
  }
  expect(client.getAccessToken()).toBe("old-access");
  expect(localStorage.getItem("refresh_token")).toBe("old-refresh");
});

test("rejects a missing refresh token without retrying", async () => {
  localStorage.removeItem("refresh_token");
  const client = new ApiClient("http://api.test");
  const fetchMock = mock.method(globalThis, "fetch", async () =>
    Response.json({ detail: "Invalid session" }, { status: 401 }),
  );
  await expect(client.auth.me()).rejects.toMatchObject({ status: 401 });
  expect(fetchMock.mock.calls).toHaveLength(1);
  expect(client.getAccessToken()).toBeNull();
  expect(localStorage.getItem("access_token")).toBeNull();
});

test("does not refresh unauthenticated requests", async () => {
  localStorage.removeItem("access_token");
  const client = new ApiClient("http://api.test");
  const fetchMock = mock.method(globalThis, "fetch", async () =>
    Response.json({ detail: "Missing credentials" }, { status: 401 }),
  );
  await expect(client.auth.me()).rejects.toMatchObject({ status: 401 });
  expect(fetchMock.mock.calls).toHaveLength(1);
});

test("preserves credentials after a request timeout", async () => {
  const client = new ApiClient("http://api.test", 5);
  const fetchMock = mock.method(
    globalThis,
    "fetch",
    (_url: string, options?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        options?.signal?.addEventListener("abort", () =>
          reject(new DOMException("Aborted", "AbortError")),
        );
      }),
  );
  await expect(client.auth.me()).rejects.toMatchObject({
    status: 0,
    response: "Request timed out. Please try again.",
  });
  expect(fetchMock.mock.calls).toHaveLength(1);
  expect(client.getAccessToken()).toBe("old-access");
  expect(localStorage.getItem("refresh_token")).toBe("old-refresh");
});

test("shares a network refresh failure and permits recovery on a later request", async () => {
  const client = new ApiClient("http://api.test");
  let failRefresh = true;
  let refreshCount = 0;
  mock.method(globalThis, "fetch", async (url: string, options?: RequestInit) => {
    if (url.endsWith("/refresh")) {
      refreshCount++;
      if (failRefresh) throw new TypeError("Failed to fetch");
      return Response.json(tokens);
    }
    if (new Headers(options?.headers).get("Authorization") === "Bearer old-access") {
      return Response.json({ detail: "Expired token" }, { status: 401 });
    }
    return Response.json({ id: "user" });
  });
  const results = await Promise.allSettled([client.auth.me(), client.audit.list()]);
  expect(results).toEqual([
    { status: "rejected", reason: expect.objectContaining({ status: 0 }) },
    { status: "rejected", reason: expect.objectContaining({ status: 0 }) },
  ]);
  expect(refreshCount).toBe(1);
  expect(client.getAccessToken()).toBe("old-access");
  expect(localStorage.getItem("refresh_token")).toBe("old-refresh");

  failRefresh = false;
  await expect(client.auth.me()).resolves.toMatchObject({ id: "user" });
  expect(refreshCount).toBe(2);
});

test("reuses rotated credentials when an old request returns a late 401", async () => {
  const client = new ApiClient("http://api.test");
  const lateResponse = deferred<Response>();
  let refreshCount = 0;
  let meCount = 0;
  mock.method(globalThis, "fetch", async (url: string, options?: RequestInit) => {
    if (url.endsWith("/refresh")) {
      refreshCount++;
      return Response.json(tokens);
    }
    const token = new Headers(options?.headers).get("Authorization");
    if (url.endsWith("/audit") && token === "Bearer old-access") return lateResponse.promise;
    if (url.endsWith("/me")) meCount++;
    if (token === "Bearer old-access") {
      return Response.json({ detail: "Expired token" }, { status: 401 });
    }
    return Response.json({ id: "user" });
  });
  const lateRequest = client.audit.list();
  await client.auth.me();
  lateResponse.resolve(Response.json({ detail: "Expired token" }, { status: 401 }));
  await expect(lateRequest).resolves.toMatchObject({ id: "user" });
  expect(refreshCount).toBe(1);
  expect(meCount).toBe(2);
});

test("coordinates explicit refresh calls with automatic refresh", async () => {
  const client = new ApiClient("http://api.test");
  const refreshResponse = deferred<Response>();
  const automaticRefreshStarted = deferred<void>();
  const refresh = client.auth.refreshToken;
  let refreshCalls = 0;
  mock.method(client.auth, "refreshToken", (data: RefreshTokenRequest) => {
    refreshCalls++;
    if (refreshCalls === 3) automaticRefreshStarted.resolve();
    return refresh(data);
  });
  let refreshCount = 0;
  mock.method(globalThis, "fetch", async (url: string, options?: RequestInit) => {
    if (url.endsWith("/refresh")) {
      refreshCount++;
      return refreshResponse.promise;
    }
    if (new Headers(options?.headers).get("Authorization") === "Bearer old-access") {
      return Response.json({ detail: "Expired token" }, { status: 401 });
    }
    return Response.json({ id: "user" });
  });
  const explicit = client.auth.refreshToken({ refresh_token: "old-refresh" });
  expect(client.auth.refreshToken({ refresh_token: "old-refresh" })).toBe(explicit);
  const automatic = client.auth.me();
  await automaticRefreshStarted.promise;
  refreshResponse.resolve(Response.json(tokens));
  await expect(explicit).resolves.toEqual(tokens);
  await expect(automatic).resolves.toMatchObject({ id: "user" });
  expect(refreshCount).toBe(1);
});

for (const sessionChange of ["logout", "login"] as const) {
  test(`does not restore an old session after ${sessionChange} during refresh`, async () => {
    const client = new ApiClient("http://api.test");
    const refreshStarted = deferred<void>();
    const refreshResponse = deferred<Response>();
    const fetchMock = mock.method(globalThis, "fetch", async (url: string) => {
      if (url.endsWith("/refresh")) {
        refreshStarted.resolve();
        return refreshResponse.promise;
      }
      if (url.endsWith("/login")) {
        return Response.json({
          ...tokens,
          access_token: "other-access",
          refresh_token: "other-refresh",
        });
      }
      return Response.json({ detail: "Expired token" }, { status: 401 });
    });
    const result = expect(client.auth.me()).rejects.toMatchObject({ status: 0 });
    await refreshStarted.promise;
    if (sessionChange === "logout") client.auth.logout();
    else await client.auth.login({ email: "other@example.com", password: "password" });
    refreshResponse.resolve(Response.json(tokens));
    await result;
    expect(fetchMock.mock.calls).toHaveLength(sessionChange === "logout" ? 2 : 3);
    expect(client.getAccessToken()).toBe(sessionChange === "logout" ? null : "other-access");
    expect(localStorage.getItem("refresh_token")).toBe(
      sessionChange === "logout" ? null : "other-refresh",
    );
  });
}

test("replays the method and body and preserves errors from a failed retry", async () => {
  const client = new ApiClient("http://api.test");
  const requests: RequestInit[] = [];
  mock.method(globalThis, "fetch", async (url: string, options: RequestInit) => {
    if (url.endsWith("/refresh")) return Response.json(tokens);
    requests.push(options);
    return Response.json(
      { error: { code: "FAILED", message: "Unavailable", details: {} } },
      {
        status:
          new Headers(options.headers).get("Authorization") === "Bearer old-access" ? 401 : 503,
        headers: { "x-correlation-id": "retry-ref" },
      },
    );
  });
  await expect(client.agents.run({ prompt: "hello" })).rejects.toMatchObject({
    status: 503,
    correlationId: "retry-ref",
    response: { error: { message: "Unavailable" } },
  });
  expect(requests).toHaveLength(2);
  expect(requests.map(({ method, body }) => ({ method, body }))).toEqual([
    { method: "POST", body: '{"prompt":"hello"}' },
    { method: "POST", body: '{"prompt":"hello"}' },
  ]);
  expect(client.getAccessToken()).toBe("new-access");
  expect(localStorage.getItem("refresh_token")).toBe("new-refresh");
});

test("does not invalidate the session for an incorrect current password", async () => {
  const client = new ApiClient("http://api.test");
  const fetchMock = mock.method(globalThis, "fetch", async (url: string) => {
    if (url.endsWith("/refresh")) return Response.json(tokens);
    return Response.json({ detail: "Incorrect current password" }, { status: 401 });
  });
  await expect(
    client.auth.changePassword({ current_password: "incorrect", new_password: "new-password" }),
  ).rejects.toMatchObject({ status: 401 });
  expect(fetchMock.mock.calls).toHaveLength(1);
  expect(client.getAccessToken()).toBe("old-access");
  expect(localStorage.getItem("refresh_token")).toBe("old-refresh");
});

test("refreshes password-change requests only for an authentication challenge", async () => {
  const client = new ApiClient("http://api.test");
  const fetchMock = mock.method(globalThis, "fetch", async (url: string, options?: RequestInit) => {
    if (url.endsWith("/refresh")) return Response.json(tokens);
    if (new Headers(options?.headers).get("Authorization") === "Bearer old-access") {
      return Response.json(
        { detail: "Expired token" },
        { status: 401, headers: { "www-authenticate": "Bearer" } },
      );
    }
    return Response.json({ detail: "Incorrect current password" }, { status: 401 });
  });
  await expect(
    client.auth.changePassword({ current_password: "incorrect", new_password: "new-password" }),
  ).rejects.toMatchObject({ status: 401 });
  expect(fetchMock.mock.calls).toHaveLength(3);
  expect(client.getAccessToken()).toBe("new-access");
  expect(localStorage.getItem("refresh_token")).toBe("new-refresh");
});

for (const status of [200, 401, 403]) {
  test(`discards a late /me response (${status}) after a newer login`, async () => {
    const client = new ApiClient("http://api.test");
    const meResponse = deferred<Response>();
    mock.method(globalThis, "fetch", async (url: string) => {
      if (url.endsWith("/me")) return meResponse.promise;
      return Response.json({
        ...tokens,
        access_token: "other-access",
        refresh_token: "other-refresh",
      });
    });
    const result = expect(client.auth.me()).rejects.toMatchObject({ status: 0 });
    await client.auth.login({ email: "other@example.com", password: "password" });
    meResponse.resolve(Response.json({ id: "old-user" }, { status }));
    await result;
    expect(client.getAccessToken()).toBe("other-access");
    expect(localStorage.getItem("refresh_token")).toBe("other-refresh");
  });
}

test("notifies session invalidation listeners and supports unsubscribing", async () => {
  const client = new ApiClient("http://api.test");
  const listener = mock.fn();
  const unsubscribe = client.onSessionInvalidated(listener);
  mock.method(globalThis, "fetch", async () =>
    Response.json({ detail: "Invalid session" }, { status: 401 }),
  );
  await expect(client.auth.me()).rejects.toMatchObject({ status: 401 });
  expect(listener.mock.calls).toHaveLength(1);
  unsubscribe();
  client.auth.logout();
  expect(listener.mock.calls).toHaveLength(1);
});
