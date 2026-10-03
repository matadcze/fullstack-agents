import { test as base, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { createHmac } from "node:crypto";
import { once } from "node:events";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import path from "node:path";
import ts from "typescript";
import type { ApiError } from "../../src/lib/api/client";

const repoRoot = path.resolve(__dirname, "../../../..");
const jwtSecret = "cross-origin-browser-test-secret-only";
const password = "CorrectHorse1!";

const test = base.extend<{ origins: { web: string; api: string } }>({
  origins: async ({}, provide) => {
    const modules = new Map<string, string>();
    for (const [url, file] of [
      ["/client.js", "lib/api/client.ts"],
      ["/constants.js", "config/constants.ts"],
    ]) {
      const source = await readFile(path.join(repoRoot, "apps/web/src", file), "utf8");
      modules.set(
        url,
        ts
          .transpileModule(source, {
            compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
          })
          .outputText.replaceAll("@/config/constants", "/constants.js"),
      );
    }
    const web = createServer((request, response) => {
      const compiledSource = modules.get(request.url ?? "");
      response.setHeader("Content-Type", compiledSource ? "text/javascript" : "text/html");
      response.end(compiledSource ?? "<script>globalThis.process = { env: {} };</script>");
    });
    web.listen(0, "127.0.0.1");
    await once(web, "listening");
    const address = web.address();
    if (!address || typeof address === "string") throw new Error("No web listener");
    const webOrigin = `http://127.0.0.1:${address.port}`;
    const api = spawn(
      process.env.PLAYWRIGHT_API_PYTHON ??
        path.join(
          repoRoot,
          process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python",
        ),
      ["-u", "-m", "tests.browser_server"],
      {
        cwd: path.join(repoRoot, "apps/api"),
        env: {
          ...process.env,
          DATABASE_URL: "sqlite+aiosqlite:///:memory:",
          JWT_SECRET_KEY: jwtSecret,
          CORS_ORIGINS: JSON.stringify([webOrigin]),
        },
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    let output = "";
    let startupError: Error | undefined;
    api.on("error", (error) => (startupError = error));
    api.stdout.on("data", (data) => (output += data.toString()));
    api.stderr.on("data", (data) => (output += data.toString()));
    try {
      await expect
        .poll(
          () => {
            if (startupError) throw startupError;
            if (api.exitCode !== null || api.signalCode !== null)
              throw new Error(`API server exited: ${output}`);
            return output.match(/CORS_TEST_API_URL=(http:\/\/127\.0\.0\.1:\d+)/)?.[1];
          },
          { timeout: 15_000 },
        )
        .toBeTruthy();
      const apiOrigin = output.match(/CORS_TEST_API_URL=(http:\/\/127\.0\.0\.1:\d+)/)![1];
      await expect
        .poll(
          async () => {
            try {
              return (await fetch(`${apiOrigin}/api/v1/health`)).status;
            } catch {
              return 0;
            }
          },
          { timeout: 15_000 },
        )
        .toBe(200);
      await provide({ web: webOrigin, api: apiOrigin });
    } finally {
      if (api.pid !== undefined && api.exitCode === null && api.signalCode === null) {
        const stopped = once(api, "exit");
        api.kill("SIGTERM");
        await stopped;
      }
      await new Promise<void>((resolve, reject) =>
        web.close((error) => (error ? reject(error) : resolve())),
      );
    }
  },
});

test("browser fetch can read the real API's cross-origin Bearer challenge", async ({
  page,
  origins,
}) => {
  await page.goto(origins.web);
  expect(new URL(origins.api).origin).not.toBe(new URL(page.url()).origin);
  const response = await page.evaluate(async (api) => {
    const response = await fetch(`${api}/api/v1/auth/change-password`, {
      method: "POST",
      headers: { Authorization: "Bearer invalid", "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: "WrongPassword1!", new_password: "NewPassword1!" }),
    });
    return {
      type: response.type,
      status: response.status,
      challenge: response.headers.get("WWW-Authenticate"),
    };
  }, origins.api);
  expect(response).toEqual({ type: "cors", status: 401, challenge: "Bearer" });
});

test("cross-origin password changes refresh expired tokens but not incorrect passwords", async ({
  page,
  origins,
}) => {
  await page.goto(origins.web);
  const setup = await page.evaluate(
    async ({ api, password }) => {
      const { ApiClient } = (await import(
        "/client.js" as string
      )) as typeof import("../../src/lib/api/client");
      const client = new ApiClient(api);
      const user = await client.auth.register({ email: "cors@example.com", password });
      const tokens = await client.auth.login({ email: user.email, password });
      return { user, tokens };
    },
    { api: origins.api, password },
  );
  const requests: { path: string; status: number }[] = [];
  page.on("response", (response) => {
    if (response.request().method() === "POST" && response.url().startsWith(origins.api)) {
      requests.push({ path: new URL(response.url()).pathname, status: response.status() });
    }
  });

  const wrongPassword = await page.evaluate(async (api) => {
    const { ApiClient } = (await import(
      "/client.js" as string
    )) as typeof import("../../src/lib/api/client");
    const client = new ApiClient(api);
    try {
      await client.auth.changePassword({
        current_password: "WrongPassword1!",
        new_password: "NewPassword1!",
      });
      return null;
    } catch (error) {
      const apiError = error as ApiError;
      return {
        status: apiError.status,
        challenge: apiError.authenticationChallenge,
        access: client.getAccessToken(),
        refresh: localStorage.getItem("refresh_token"),
      };
    }
  }, origins.api);
  expect(wrongPassword).toEqual({
    status: 401,
    challenge: null,
    access: setup.tokens.access_token,
    refresh: setup.tokens.refresh_token,
  });
  expect(requests).toEqual([{ path: "/api/v1/auth/change-password", status: 401 }]);
  requests.length = 0;

  const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url");
  const payload = Buffer.from(
    JSON.stringify({ sub: setup.user.id, type: "access", exp: 1 }),
  ).toString("base64url");
  const signature = createHmac("sha256", jwtSecret)
    .update(`${header}.${payload}`)
    .digest("base64url");
  const result = await page.evaluate(
    async ({ api, expiredToken, password }) => {
      const { ApiClient } = (await import(
        "/client.js" as string
      )) as typeof import("../../src/lib/api/client");
      const client = new ApiClient(api);
      client.setAccessToken(expiredToken);
      try {
        await client.auth.changePassword({
          current_password: password,
          new_password: "NewPassword1!",
        });
        return {
          ok: true,
          access: client.getAccessToken(),
          refresh: localStorage.getItem("refresh_token"),
        };
      } catch (error) {
        const apiError = error as ApiError;
        return { ok: false, status: apiError.status, challenge: apiError.authenticationChallenge };
      }
    },
    { api: origins.api, expiredToken: `${header}.${payload}.${signature}`, password },
  );
  expect(result.ok, JSON.stringify(result)).toBe(true);
  expect(result.access).not.toBe(`${header}.${payload}.${signature}`);
  expect(result.refresh).not.toBe(setup.tokens.refresh_token);
  expect(requests).toEqual([
    { path: "/api/v1/auth/change-password", status: 401 },
    { path: "/api/v1/auth/refresh", status: 200 },
    { path: "/api/v1/auth/change-password", status: 204 },
  ]);
  const login = await page.request.post(`${origins.api}/api/v1/auth/login`, {
    data: { email: setup.user.email, password: "NewPassword1!" },
  });
  expect(login.status()).toBe(200);
});
