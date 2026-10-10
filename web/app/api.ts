// This unauthenticated client is for a local, loopback-only game server.
export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

/** Central transport: bounded requests, actionable network/HTTP/JSON errors. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: init.signal ?? AbortSignal.timeout(15000),
    });
    const payload = await response.clone().json().catch(() => null) as { error?: string } | null;
    if (!response.ok) throw new Error(payload?.error || `Game engine returned HTTP ${response.status}.`);
    if (!payload || typeof payload !== "object") throw new Error("Game engine returned invalid JSON.");
    return response;
  } catch (error) {
    if (error instanceof TypeError || (error instanceof DOMException && error.name === "TimeoutError")) {
      throw new Error(`Cannot reach the local game engine at ${API_BASE}. Start the Python API and retry.`);
    }
    throw error;
  }
}
