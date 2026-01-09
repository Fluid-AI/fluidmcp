interface Tool {
  name: string;
  description: string;
}

interface ServerDetails {
  id: string;
  name: string;
  description: string;
  status: string;
  tools: Tool[];
}

export const mockServerDetails: ServerDetails = {
  id: "time",
  name: "Time MCP Server",
  description:
    "Provides current time and timezone conversion capabilities using IANA timezone names.",
  status: "running",
  tools: [
    {
      name: "get_current_time",
      description: "Get current time in a specific timezone",
    },
    {
      name: "convert_time",
      description: "Convert time between different timezones",
    },
  ],
};
