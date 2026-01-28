export type ServerStatus = "running" | "starting" | "stopped";

export interface Server {
  id: string;
  name: string;
  description: string;
  status: ServerStatus;
}

export const mockServers: Server[] = [
  {
    id: "airbnb",
    name: "Airbnb Search",
    description: "Search Airbnb listings using MCP",
    status: "running",
  },
  {
    id: "github",
    name: "GitHub MCP",
    description: "Interact with GitHub repositories",
    status: "starting",
  },
  {
    id: "filesystem",
    name: "Filesystem",
    description: "Read and write local files",
    status: "stopped",
  },
  {
    id: "brave-search",
    name: "Brave Search",
    description: "Search the web using Brave Search API",
    status: "running",
  },
  {
    id: "memory",
    name: "Memory",
    description: "Persistent key-value storage for context",
    status: "stopped",
  },
];
