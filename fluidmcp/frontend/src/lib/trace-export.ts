import type { ExecutionRun } from "../components/inspector/chat-types";

export interface TraceExportOptions {
  serverName?: string;
  serverUrl?: string;
}

function formatTimestamp(ms: number): string {
  return new Date(ms).toISOString();
}

function formatDuration(startMs: number, endMs?: number): string {
  if (!endMs) return "—";
  return `${endMs - startMs}ms`;
}


export function toJSON(runs: ExecutionRun[], opts: TraceExportOptions = {}): string {
  const payload = {
    exported_at: new Date().toISOString(),
    server_name: opts.serverName ?? null,
    server_url: opts.serverUrl ?? null,
    run_count: runs.length,
    runs: runs.map((run) => ({
      run_id: run.runId,
      server_id: run.serverId,
      started_at: formatTimestamp(run.startTime),
      ended_at: run.endTime ? formatTimestamp(run.endTime) : null,
      duration_ms: run.endTime ? run.endTime - run.startTime : null,
      steps: run.steps.map((s) => ({
        type: s.type,
        tool_name: s.toolName ?? null,
        params: s.params ?? null,
        result: s.result ?? null,
        content: s.content ?? null,
        timestamp: formatTimestamp(s.timestamp),
      })),
    })),
  };
  return JSON.stringify(payload, null, 2);
}

export function toMarkdown(runs: ExecutionRun[], opts: TraceExportOptions = {}): string {
  const lines: string[] = [];
  const exportedAt = new Date().toLocaleString();

  lines.push(`# MCP Trace Export`);
  if (opts.serverName) lines.push(`**Server:** ${opts.serverName}`);
  if (opts.serverUrl) lines.push(`**URL:** ${opts.serverUrl}`);
  lines.push(`**Exported:** ${exportedAt}`);
  lines.push(`**Runs:** ${runs.length}`);
  lines.push("");

  runs.forEach((run, i) => {
    const toolCallStep = run.steps.find((s) => s.type === "tool_call");
    const label = toolCallStep?.toolName ?? "chat";
    const duration = formatDuration(run.startTime, run.endTime);

    lines.push(`---`);
    lines.push(`## Run ${i + 1} — \`${label}\` (${duration})`);
    lines.push(`**Started:** ${formatTimestamp(run.startTime)}`);
    if (run.endTime) lines.push(`**Ended:** ${formatTimestamp(run.endTime)}`);
    lines.push("");

    run.steps.forEach((step) => {
      switch (step.type) {
        case "user":
          lines.push(`### User`);
          lines.push(step.content ?? "");
          lines.push("");
          break;
        case "thinking":
          lines.push(`### Thinking`);
          lines.push(`> ${(step.content ?? "").replace(/\n/g, "\n> ")}`);
          lines.push("");
          break;
        case "tool_call":
          lines.push(`### Tool Call — \`${step.toolName}\``);
          lines.push("```json");
          lines.push(JSON.stringify(step.params ?? {}, null, 2));
          lines.push("```");
          lines.push("");
          break;
        case "tool_result":
          lines.push(`### Tool Result`);
          lines.push("```json");
          lines.push(JSON.stringify(step.result ?? {}, null, 2));
          lines.push("```");
          lines.push("");
          break;
        case "assistant":
          lines.push(`### Assistant`);
          lines.push(step.content ?? "");
          lines.push("");
          break;
        case "error":
          lines.push(`### Error`);
          lines.push(`> ${step.content ?? ""}`);
          lines.push("");
          break;
      }
    });
  });

  return lines.join("\n");
}

export function downloadFile(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}
