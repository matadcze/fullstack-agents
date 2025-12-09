import { ApiError } from "@/lib/api/client";

export function getFriendlyErrorMessage(error: unknown, fallback: string): string {
  const withCorrelation = (message: string, correlationId: string | null): string => {
    return correlationId ? `${message} (Ref: ${correlationId})` : message;
  };

  if (error instanceof ApiError) {
    if (typeof error.response === "string") return error.response;

    if (
      typeof error.response === "object" &&
      error.response !== null &&
      "error" in error.response &&
      typeof (error.response as { error?: { message?: unknown } }).error?.message === "string"
    ) {
      const message = String((error.response as { error?: { message?: unknown } }).error?.message);
      return withCorrelation(message, error.correlationId);
    }

    if (
      typeof error.response === "object" &&
      error.response !== null &&
      "detail" in error.response &&
      typeof (error.response as { detail?: unknown }).detail === "string"
    ) {
      const message = String((error.response as { detail?: unknown }).detail);
      return withCorrelation(message, error.correlationId);
    }

    if (error.status === 0) {
      return withCorrelation(
        "Network error. Please check your connection and try again.",
        error.correlationId,
      );
    }

    if (error.correlationId) {
      return withCorrelation(fallback, error.correlationId);
    }
  }

  if (error instanceof Error && error.message) return error.message;

  return fallback;
}
