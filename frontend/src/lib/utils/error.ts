import { ApiError } from "@/lib/api/client";

export function getFriendlyErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (typeof error.response === "string") return error.response;

    if (
      typeof error.response === "object" &&
      error.response !== null &&
      "error" in error.response &&
      typeof (error.response as { error?: { message?: unknown } }).error?.message === "string"
    ) {
      return String((error.response as { error?: { message?: unknown } }).error?.message);
    }

    if (
      typeof error.response === "object" &&
      error.response !== null &&
      "detail" in error.response &&
      typeof (error.response as { detail?: unknown }).detail === "string"
    ) {
      return String((error.response as { detail?: unknown }).detail);
    }

    if (error.status === 0) {
      return "Network error. Please check your connection and try again.";
    }
  }

  if (error instanceof Error && error.message) return error.message;

  return fallback;
}
