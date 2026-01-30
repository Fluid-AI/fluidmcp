import { usePolling } from './usePolling';
import apiClient from '../services/api';

interface ServerPollingOptions {
  expectedState?: 'running' | 'stopped';
  checkTools?: boolean;          // Also verify tools are available
  onSuccess?: () => void;
  onTimeout?: () => void;
  onError?: (error: Error) => void;
}

export function useServerPolling(serverId: string) {
  const { startPolling, stopPolling, isPolling } = usePolling();

  const pollForServerState = async (options: ServerPollingOptions = {}) => {
    const { expectedState, checkTools, onSuccess, onTimeout, onError } = options;

    return startPolling(
      async () => {
        try {
          // Fetch server status
          const server = await apiClient.getServerDetails(serverId);

          // Check state if specified
          if (expectedState && server.status?.state !== expectedState) {
            return false;
          }

          // Check tools if requested
          if (checkTools) {
            const toolsResponse = await apiClient.getServerTools(serverId);
            if (!toolsResponse.tools || toolsResponse.tools.length === 0) {
              return false;
            }
          }

          return true; // All conditions met
        } catch (error: any) {
          // Distinguish between expected errors (server not ready) and unexpected errors
          const status = error?.response?.status;

          // Expected errors - server is starting up or not ready yet
          if (status === 404 || status === 503 || status === 502) {
            return false; // Keep polling
          }

          // Unexpected errors - network failures, auth failures, server crashes
          // These should not be silently swallowed
          throw error;
        }
      },
      {
        interval: 1000,      // Check every 1 second
        timeout: 30000,      // Give up after 30 seconds
        onSuccess,
        onTimeout,
        onError,
      }
    );
  };

  return {
    pollForServerState,
    stopPolling,
    isPolling,
  };
}
