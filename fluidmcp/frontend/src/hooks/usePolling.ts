import { useRef, useCallback, useState, useEffect } from 'react';

interface PollingOptions {
  interval?: number;          // Polling interval in ms (default: 1000)
  timeout?: number;           // Total timeout in ms (default: 30000)
  onSuccess?: () => void;     // Called when condition is met
  onTimeout?: () => void;     // Called when timeout is reached
  onError?: (error: Error) => void;
}

interface PollingResult {
  startPolling: (
    checkFn: () => Promise<boolean>,  // Returns true when done
    options?: PollingOptions
  ) => Promise<boolean>;
  stopPolling: () => void;
  isPolling: boolean;
}

export function usePolling(): PollingResult {
  const timeoutRef = useRef<number | null>(null);
  const intervalRef = useRef<number | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  const stopPolling = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setIsPolling(false);
  }, []);

  const startPolling = useCallback(
    async (
      checkFn: () => Promise<boolean>,
      options: PollingOptions = {}
    ): Promise<boolean> => {
      const {
        interval = 1000,
        timeout = 30000,
        onSuccess,
        onTimeout,
        onError,
      } = options;

      // Stop any existing polling
      stopPolling();

      return new Promise((resolve) => {
        setIsPolling(true);

        // Track if promise has been resolved to prevent race conditions
        let hasResolved = false;

        const resolveOnce = (value: boolean) => {
          if (!hasResolved) {
            hasResolved = true;
            resolve(value);
          }
        };

        // Timeout handler
        timeoutRef.current = setTimeout(() => {
          stopPolling();
          onTimeout?.();
          resolveOnce(false);
        }, timeout);

        // Polling interval
        const poll = async () => {
          try {
            const isDone = await checkFn();

            if (isDone) {
              stopPolling();
              onSuccess?.();
              resolveOnce(true);
              return;
            }
          } catch (error) {
            stopPolling();
            onError?.(error instanceof Error ? error : new Error(String(error)));
            resolveOnce(false);
          }
        };

        // Initial check
        poll();

        // Set up interval
        intervalRef.current = setInterval(poll, interval);
      });
    },
    [stopPolling]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  return {
    startPolling,
    stopPolling,
    isPolling,
  };
}
