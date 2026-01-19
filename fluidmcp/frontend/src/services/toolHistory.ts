export interface ToolExecution {
  id: string;
  serverId: string;
  serverName: string;
  toolName: string;
  arguments: Record<string, any>;
  result: any;
  timestamp: string;
  success: boolean;
  error?: string;
  executionTime?: number;
}

const STORAGE_KEY = 'fluidmcp_tool_history';
// Global cap: 250 executions across all tools
// Per-tool cap: 25 executions per specific tool
const MAX_EXECUTIONS_PER_TOOL = 25;

/**
 * Generate a unique ID using crypto.randomUUID() with fallback
 */
function generateId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback for environments without crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
}

class ToolHistoryService {
  /**
   * Save a tool execution to localStorage
   */
  saveExecution(execution: Omit<ToolExecution, 'id' | 'timestamp'>): ToolExecution {
    const newExecution: ToolExecution = {
      ...execution,
      id: generateId(),
      timestamp: new Date().toISOString(),
    };

    const history = this.getAllHistory();
    history.unshift(newExecution);

    // Limit total history size (keep last 250 executions across all tools)
    const trimmedHistory = history.slice(0, 250);

    this._saveToStorage(trimmedHistory);
    return newExecution;
  }

  /**
   * Get execution history for a specific tool
   */
  getHistory(serverId: string, toolName: string): ToolExecution[] {
    const allHistory = this.getAllHistory();
    return allHistory
      .filter(
        (exec) => exec.serverId === serverId && exec.toolName === toolName
      )
      .slice(0, MAX_EXECUTIONS_PER_TOOL);
  }

  /**
   * Get all execution history
   */
  getAllHistory(): ToolExecution[] {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (!stored) return [];
      return JSON.parse(stored) as ToolExecution[];
    } catch (error) {
      console.error('Failed to load tool history:', error);
      return [];
    }
  }

  /**
   * Clear history (optionally filter by server and/or tool)
   */
  clearHistory(serverId?: string, toolName?: string): void {
    if (!serverId && !toolName) {
      // Clear all history
      localStorage.removeItem(STORAGE_KEY);
      return;
    }

    const allHistory = this.getAllHistory();
    const filtered = allHistory.filter((exec) => {
      if (serverId && toolName) {
        return exec.serverId !== serverId || exec.toolName !== toolName;
      }
      if (serverId) {
        return exec.serverId !== serverId;
      }
      if (toolName) {
        return exec.toolName !== toolName;
      }
      return true;
    });

    this._saveToStorage(filtered);
  }

  /**
   * Get recent arguments used for a specific tool (last N executions)
   */
  getRecentArguments(
    serverId: string,
    toolName: string,
    limit: number = 10
  ): Record<string, any>[] {
    const history = this.getHistory(serverId, toolName);
    return history
      .filter((exec) => exec.success)
      .slice(0, limit)
      .map((exec) => exec.arguments);
  }

  /**
   * Get a specific execution by ID
   */
  getExecutionById(executionId: string): ToolExecution | null {
    const allHistory = this.getAllHistory();
    return allHistory.find((exec) => exec.id === executionId) || null;
  }

  /**
   * Export history as JSON string
   */
  exportHistory(): string {
    const history = this.getAllHistory();
    return JSON.stringify(history, null, 2);
  }

  /**
   * Import history from JSON string
   */
  importHistory(jsonString: string): void {
    try {
      const imported = JSON.parse(jsonString) as ToolExecution[];
      const existing = this.getAllHistory();

      // Merge and deduplicate by ID
      const merged = [...imported, ...existing];
      const uniqueMap = new Map(merged.map((exec) => [exec.id, exec]));
      const unique = Array.from(uniqueMap.values());

      // Sort by timestamp (newest first)
      unique.sort(
        (a, b) =>
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      );

      this._saveToStorage(unique.slice(0, 250));
    } catch (error) {
      console.error('Failed to import tool history:', error);
      throw new Error('Invalid history format');
    }
  }

  /**
   * Private helper to save history to localStorage
   */
  private _saveToStorage(history: ToolExecution[]): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
    } catch (error) {
      console.error('Failed to save tool history:', error);
    }
  }
}

// Export singleton instance
export const toolHistoryService = new ToolHistoryService();
