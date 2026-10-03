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
    public authenticationChallenge: string | null = null,
  ) {
    super(message || String(response));
    this.name = "ApiError";
  }
}

type RequestOptions = RequestInit & { isFormData?: boolean; skipAuth?: boolean };

class ApiClient {
  private baseUrl: string;
  private timeout: number;
  private accessToken: string | null = null;
  private sessionGeneration = 0;
  private refreshRequest: {
    generation: number;
    token: string;
    promise: Promise<TokenResponse>;
  } | null = null;
  private sessionInvalidationListeners = new Set<() => void>();

  constructor(baseUrl: string = API_BASE_URL, timeout: number = REQUEST_TIMEOUT_MS) {
    this.baseUrl = baseUrl;
    this.timeout = timeout;
    // Load token from localStorage if available
    if (typeof window !== "undefined") {
      this.accessToken = localStorage.getItem("access_token");
    }
  }

  setAccessToken(token: string | null) {
    this.sessionGeneration++;
    this.storeAccessToken(token);
  }

  private storeAccessToken(token: string | null) {
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

  onSessionInvalidated(listener: () => void): () => void {
    this.sessionInvalidationListeners.add(listener);
    return () => {
      this.sessionInvalidationListeners.delete(listener);
    };
  }

  private async request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const token = options.skipAuth ? null : this.accessToken;
    const generation = this.sessionGeneration;

    try {
      const result = await this.sendRequest<T>(endpoint, options, token);
      if (token && generation !== this.sessionGeneration) throw this.sessionChangedError();
      return result;
    } catch (error) {
      if (token && generation !== this.sessionGeneration) {
        throw this.sessionChangedError();
      }
      if (!this.isSessionUnauthorized(error, endpoint) || !token) throw error;

      // A late 401 may refer to the old token after another request already refreshed it.
      if (token === this.accessToken) {
        const refreshToken =
          typeof window !== "undefined" ? localStorage.getItem("refresh_token") : null;
        if (!refreshToken) {
          this.auth.logout();
          throw error;
        }
        try {
          await this.auth.refreshToken({ refresh_token: refreshToken });
        } catch (refreshError) {
          if (this.accessToken && generation !== this.sessionGeneration) {
            throw this.sessionChangedError();
          }
          throw refreshError;
        }
      }

      if (generation !== this.sessionGeneration || !this.accessToken) {
        throw this.sessionChangedError();
      }
      const retryToken = this.accessToken;
      try {
        const result = await this.sendRequest<T>(endpoint, options, retryToken);
        if (generation !== this.sessionGeneration) throw this.sessionChangedError();
        return result;
      } catch (retryError) {
        if (
          generation !== this.sessionGeneration ||
          (retryError instanceof ApiError &&
            retryError.status === 401 &&
            retryToken !== this.accessToken)
        ) {
          throw this.sessionChangedError();
        }
        if (this.isSessionUnauthorized(retryError, endpoint)) this.auth.logout();
        throw retryError;
      }
    }
  }

  private sessionChangedError(): ApiError {
    return new ApiError(0, "The session changed. Please try again.");
  }

  private isSessionUnauthorized(error: unknown, endpoint: string): error is ApiError {
    return (
      error instanceof ApiError &&
      error.status === 401 &&
      // Wrong current passwords also return 401, but token failures include this challenge.
      (endpoint !== "/api/v1/auth/change-password" || error.authenticationChallenge !== null)
    );
  }

  private refreshSession(data: RefreshTokenRequest): Promise<TokenResponse> {
    const generation = this.sessionGeneration;
    if (
      this.refreshRequest?.generation === generation &&
      this.refreshRequest.token === data.refresh_token
    ) {
      return this.refreshRequest.promise;
    }

    const promise = this.performRefresh(data, generation).finally(() => {
      if (this.refreshRequest?.promise === promise) this.refreshRequest = null;
    });
    this.refreshRequest = { generation, token: data.refresh_token, promise };
    return promise;
  }

  private async performRefresh(
    data: RefreshTokenRequest,
    generation: number,
  ): Promise<TokenResponse> {
    try {
      const response = await this.post<TokenResponse>("/api/v1/auth/refresh", data, true);
      if (generation !== this.sessionGeneration) throw this.sessionChangedError();
      this.storeAccessToken(response.access_token);
      if (typeof window !== "undefined") {
        localStorage.setItem("refresh_token", response.refresh_token);
      }
      return response;
    } catch (error) {
      if (generation !== this.sessionGeneration) throw this.sessionChangedError();
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        this.auth.logout();
      }
      throw error;
    }
  }

  private async sendRequest<T>(
    endpoint: string,
    options: RequestOptions,
    token: string | null,
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    const { isFormData, skipAuth, ...fetchOptions } = options;
    const headers = new Headers(fetchOptions.headers);

    if (!isFormData && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    if (token && !skipAuth) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    try {
      const response = await fetch(url, {
        ...fetchOptions,
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
          response.headers.get("www-authenticate"),
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

  private async post<T>(endpoint: string, body: unknown, skipAuth = false): Promise<T> {
    return this.request<T>(endpoint, {
      method: "POST",
      body: JSON.stringify(body),
      skipAuth,
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
      this.post<UserResponse>("/api/v1/auth/register", data, true),

    login: async (data: LoginRequest): Promise<TokenResponse> => {
      const response = await this.post<TokenResponse>("/api/v1/auth/login", data, true);
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
      for (const listener of this.sessionInvalidationListeners) listener();
    },

    refreshToken: (data: RefreshTokenRequest): Promise<TokenResponse> => this.refreshSession(data),

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
