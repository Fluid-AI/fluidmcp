export type ChatMessage = {
  id: string
  runId?: string
  type: "user" | "thinking" | "tool_call" | "tool_result" | "assistant" | "error"
  content?: string
  toolName?: string
  params?: any
  result?: any
  resourceUri?: string
  timestamp: number
  perfMark?: number
}

export type ExecutionRun = {
  runId: string
  serverId: string
  startTime: number
  endTime?: number
  steps: ChatMessage[]
}

export type DisplayGroup =
  | { kind: "standalone"; msg: ChatMessage }
  | { kind: "run"; runId: string; steps: ChatMessage[]; run?: ExecutionRun }

export function groupMessages(messages: ChatMessage[], execHistory: ExecutionRun[]): DisplayGroup[] {
  const runMap = new Map(execHistory.map(r => [r.runId, r]));
  const seen = new Set<string>();
  return messages.reduce<DisplayGroup[]>((acc, msg) => {
    if (!msg.runId) {
      acc.push({ kind: "standalone", msg });
    } else if (!seen.has(msg.runId)) {
      seen.add(msg.runId);
      acc.push({
        kind: "run",
        runId: msg.runId,
        steps: messages.filter(m => m.runId === msg.runId),
        run: runMap.get(msg.runId),
      });
    }
    return acc;
  }, []);
}
