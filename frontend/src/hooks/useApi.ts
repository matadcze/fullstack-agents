import { useCallback, useEffect, useState } from "react";

export interface UseApiState<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
}

export interface UseApiOptions {
  autoExecute?: boolean;
  onSuccess?: <T>(data: T) => void;
  onError?: (error: Error) => void;
}

/**
 * Hook for executing async API calls with state management.
 */
export function useApi<T>(
  fn: () => Promise<T>,
  options: UseApiOptions = {},
): UseApiState<T> & { execute: () => Promise<void> } {
  const { autoExecute = true, onSuccess, onError } = options;

  const [state, setState] = useState<UseApiState<T>>({
    data: null,
    loading: false,
    error: null,
  });

  const execute = useCallback(async () => {
    setState({ data: null, loading: true, error: null });

    try {
      const result = await fn();
      setState({ data: result, loading: false, error: null });
      onSuccess?.(result);
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      setState({ data: null, loading: false, error });
      onError?.(error);
    }
  }, [fn, onSuccess, onError]);

  useEffect(() => {
    if (autoExecute) {
      // Intended: kick off the initial fetch when opted in.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      execute();
    }
  }, [autoExecute, execute]);

  return { ...state, execute };
}

/**
 * Hook for polling an async function until a condition is met.
 */
export function useApiPolling<T>(
  fn: () => Promise<T>,
  shouldStop: (data: T | null) => boolean,
  interval: number = 2000,
  options: Omit<UseApiOptions, "autoExecute"> = {},
): UseApiState<T> & { stop: () => void } {
  const [state, setState] = useState<UseApiState<T>>({
    data: null,
    loading: false,
    error: null,
  });

  const [isPolling, setIsPolling] = useState(true);
  const { onSuccess, onError } = options;

  const poll = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true }));

    try {
      const result = await fn();
      setState({ data: result, loading: false, error: null });

      if (shouldStop(result)) {
        setIsPolling(false);
        onSuccess?.(result);
      }
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      setState((prev) => ({ ...prev, loading: false, error }));
      setIsPolling(false);
      onError?.(error);
    }
  }, [fn, shouldStop, onSuccess, onError]);

  useEffect(() => {
    if (!isPolling) return;

    // Intended: start polling on mount or when restarted.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    poll();
    const pollInterval = setInterval(poll, interval);

    return () => clearInterval(pollInterval);
  }, [isPolling, interval, poll]);

  const stop = useCallback(() => {
    setIsPolling(false);
  }, []);

  return { ...state, stop };
}
