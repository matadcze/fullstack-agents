import { API_BASE_URL, REQUEST_TIMEOUT_MS } from "@/config/constants";
import type {
  AuditEventListResponse,
  ChangePasswordRequest,
  ErrorResponse,
  HealthResponse,
  LoginRequest,
  ReadinessResponse,
  RefreshTokenRequest,
  RegisterRequest,
  TokenResponse,
  UpdateProfileRequest,
  UserResponse,
  AgentRunRequest,
  AgentRunResponse,
} from "@/lib/types/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    public response: ErrorResponse | string,
    public correlationId: string | null = null,
    message?: string,
  ) {
    super(message || String(response));
    this.name = "ApiError";
  }
}

class ApiClient {
  private baseUrl: string;
  private timeout: number;
  private accessToken: string | null = null;

  constructor(baseUrl: string = API_BASE_URL, timeout: number = REQUEST_TIMEOUT_MS) {
    this.baseUrl = baseUrl;
    this.timeout = timeout;
    // Load token from localStorage if available
    if (typeof window !== "undefined") {
      this.accessToken = localStorage.getItem("access_token");
    }
  }

  setAccessToken(token: string | null) {
    this.accessToken = token;
    if (typeof window !== "undefined") {
      if (token) {
        localStorage.setItem("access_token", token);
      } else {
        localStorage.removeItem("access_token");
      }
    }
  }

  getAccessToken(): string | null {
    return this.accessToken;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit & { method?: string; isFormData?: boolean } = {},
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };

    if (!options.isFormData && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    if (this.accessToken) {
      headers["Authorization"] = `Bearer ${this.accessToken}`;
    }

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers,
      });

      const correlationIdHeader = response.headers.get("x-correlation-id");

      if (response.status === 204) {
        return undefined as T;
      }

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const correlationId =
          correlationIdHeader ||
          ((data as ErrorResponse | null)?.error?.correlation_id
            ? String((data as ErrorResponse).error.correlation_id)
            : null);
        throw new ApiError(
          response.status,
          data || response.statusText,
          correlationId,
          `API error: ${response.status}`,
        );
      }

      return data as T;
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }

      if (error instanceof Error) {
        if (error.name === "AbortError") {
          throw new ApiError(0, "Request timed out. Please try again.", null, error.message);
        }
        throw new ApiError(0, error.message, null, error.message);
      }

      throw new ApiError(0, "Network error. Please try again.", null, "Network error");
    } finally {
      clearTimeout(timeoutId);
    }
  }

  private async get<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: "GET" });
  }

  private async post<T>(endpoint: string, body: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  private async put<T>(endpoint: string, body: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  }

  private async delete<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: "DELETE" });
  }

  // Health check endpoints
  async health(): Promise<HealthResponse> {
    return this.get<HealthResponse>("/api/v1/health");
  }

  async readiness(): Promise<ReadinessResponse> {
    return this.get<ReadinessResponse>("/api/v1/readiness");
  }

  // Authentication endpoints
  readonly auth = {
    register: (data: RegisterRequest): Promise<UserResponse> =>
      this.post<UserResponse>("/api/v1/auth/register", data),

    login: async (data: LoginRequest): Promise<TokenResponse> => {
      const response = await this.post<TokenResponse>("/api/v1/auth/login", data);
      this.setAccessToken(response.access_token);
      if (typeof window !== "undefined") {
        localStorage.setItem("refresh_token", response.refresh_token);
      }
      return response;
    },

    logout: () => {
      this.setAccessToken(null);
      if (typeof window !== "undefined") {
        localStorage.removeItem("refresh_token");
      }
    },

    refreshToken: async (data: RefreshTokenRequest): Promise<TokenResponse> => {
      const response = await this.post<TokenResponse>("/api/v1/auth/refresh", data);
      this.setAccessToken(response.access_token);
      if (typeof window !== "undefined") {
        localStorage.setItem("refresh_token", response.refresh_token);
      }
      return response;
    },

    changePassword: (data: ChangePasswordRequest): Promise<void> =>
      this.post<void>("/api/v1/auth/change-password", data),

    updateProfile: (data: UpdateProfileRequest): Promise<UserResponse> =>
      this.put<UserResponse>("/api/v1/auth/profile", data),

    me: (): Promise<UserResponse> => this.get<UserResponse>("/api/v1/auth/me"),

    deleteAccount: (): Promise<void> => this.delete<void>("/api/v1/auth/me"),
  };

  // Audit endpoints
  readonly audit = {
    list: (params?: {
      page?: number;
      page_size?: number;
      event_type?: string;
      resource_id?: string;
      start_date?: string;
      end_date?: string;
    }): Promise<AuditEventListResponse> => {
      const queryParams = new URLSearchParams();
      if (params) {
        Object.entries(params).forEach(([key, value]) => {
          if (value !== undefined && value !== null) {
            queryParams.append(key, String(value));
          }
        });
      }
      const query = queryParams.toString();
      return this.get<AuditEventListResponse>(`/api/v1/audit${query ? `?${query}` : ""}`);
    },
  };

  // Agent endpoints
  readonly agents = {
    run: (data: AgentRunRequest): Promise<AgentRunResponse> =>
      this.post<AgentRunResponse>("/api/v1/agents/run", data),
  };
}

export const apiClient = new ApiClient();
export { ApiClient };
