/**
 * Shared API types between frontend and backend.
 *
 * These types match the Pydantic schemas defined in the backend.
 * Keep in sync with backend/src/api/schemas.py
 */

// ===== Enums =====

export enum EventType {
  USER_REGISTERED = "USER_REGISTERED",
  USER_LOGGED_IN = "USER_LOGGED_IN",
  USER_LOGGED_OUT = "USER_LOGGED_OUT",
  PASSWORD_CHANGED = "PASSWORD_CHANGED",
  USER_UPDATED = "USER_UPDATED",
  USER_DELETED = "USER_DELETED",
  RESOURCE_CREATED = "RESOURCE_CREATED",
  RESOURCE_UPDATED = "RESOURCE_UPDATED",
  RESOURCE_DELETED = "RESOURCE_DELETED",
}

// ===== Common =====

export interface ErrorDetail {
  code: string;
  message: string;
  details: Record<string, unknown>;
  correlation_id?: string;
}

export interface ErrorResponse {
  error: ErrorDetail;
}

export interface HealthResponse {
  status: string;
}

export interface ReadinessResponse {
  status: string;
  components: Record<string, string>;
}

// ===== Authentication =====

export interface RegisterRequest {
  email: string;
  password: string;
  full_name?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export interface UpdateProfileRequest {
  full_name: string;
}

export interface UserResponse {
  id: string;
  email: string;
  full_name?: string;
  created_at: string;
}

// ===== Audit =====

export interface AuditEventResponse {
  id: string;
  user_id?: string;
  event_type: EventType;
  resource_id?: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface AuditEventListResponse {
  items: AuditEventResponse[];
  page: number;
  page_size: number;
  total: number;
}

// ===== Agent =====

export interface AgentRunRequest {
  prompt: string;
  system?: string;
  tools?: string[];
}

export interface AgentStep {
  step_type: string;
  content: string;
}

export interface AgentRunResponse {
  output: string;
  steps: AgentStep[];
}

// ===== Type Guards =====

export function isErrorResponse(data: unknown): data is ErrorResponse {
  return (
    typeof data === "object" &&
    data !== null &&
    "error" in data &&
    typeof (data as ErrorResponse).error === "object"
  );
}
