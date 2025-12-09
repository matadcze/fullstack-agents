/**
 * Application configuration constants
 */

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const API_ENDPOINTS = {
  health: "/api/v1/health",
  auth: {
    register: "/api/v1/auth/register",
    login: "/api/v1/auth/login",
    refresh: "/api/v1/auth/refresh",
    me: "/api/v1/auth/me",
    changePassword: "/api/v1/auth/change-password",
    profile: "/api/v1/auth/profile",
  },
  audit: "/api/v1/audit",
  agentRun: "/api/v1/agents/run",
} as const;

export const REQUEST_TIMEOUT_MS = 30000;
export const POLLING_INTERVAL_MS = 2000;

export const APP_NAME = "{{PROJECT_NAME}}";
export const APP_VERSION = "0.1.0";
