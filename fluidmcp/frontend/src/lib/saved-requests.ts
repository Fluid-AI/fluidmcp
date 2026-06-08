export interface SavedRequest {
  id: string;
  title: string;
  toolName: string;
  params: Record<string, unknown>;
  createdAt: number;
  serverUrl: string;
}

const storageKey = (serverUrl: string) =>
  `fmcp_saved_${serverUrl.replace(/[^a-zA-Z0-9]/g, "_")}`;

export function loadSavedRequests(serverUrl: string): SavedRequest[] {
  try {
    return JSON.parse(localStorage.getItem(storageKey(serverUrl)) || "[]");
  } catch {
    return [];
  }
}

export function saveRequest(serverUrl: string, req: SavedRequest): void {
  const all = loadSavedRequests(serverUrl);
  localStorage.setItem(storageKey(serverUrl), JSON.stringify([req, ...all]));
}

export function deleteSavedRequest(serverUrl: string, id: string): void {
  const all = loadSavedRequests(serverUrl).filter(r => r.id !== id);
  localStorage.setItem(storageKey(serverUrl), JSON.stringify(all));
}

export function renameSavedRequest(serverUrl: string, id: string, newTitle: string): void {
  const all = loadSavedRequests(serverUrl).map(r =>
    r.id === id ? { ...r, title: newTitle } : r
  );
  localStorage.setItem(storageKey(serverUrl), JSON.stringify(all));
}
