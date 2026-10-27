// MCP Apps: a tool advertises its UI via _meta on the tool definition or on the result.
// Inspector results arrive wrapped as {success, result}; managed-server results are bare.
export function getWidgetResourceUri(toolDef: any, result: any): string | undefined {
  const raw = result?.result ?? result;
  return (
    toolDef?._meta?.["ui/resourceUri"] ||
    toolDef?._meta?.ui?.resourceUri ||
    raw?._meta?.["ui/resourceUri"] ||
    raw?._meta?.ui?.resourceUri ||
    undefined
  );
}
