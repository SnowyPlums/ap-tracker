declare global {
  interface Window {
    __AP_TRACKER_CONFIG__?: { apiUrl?: string };
  }
}

export function apiBase(): string {
  if (typeof window !== "undefined") {
    return window.__AP_TRACKER_CONFIG__?.apiUrl || process.env.NEXT_PUBLIC_API_URL || "";
  }
  return process.env.NEXT_PUBLIC_API_URL || "";
}

export type User = { id: number; username: string; role: string; created_at: string };
export type Room = {
  id: number; label: string; host: string; port: number; game_status: string;
  room_key: string; invite_code: string; viewer_code: string; players: number;
  checks_done: number; checks_total: number; checks_pct: number; player_names: string[];
};
export type Slot = {
  id: number; slot_name: string; game: string | null; status: string; error_message: string | null;
  checks_done: number; checks_total: number; checks_pct: number; remaining_checks: number;
  hint_points: number; completed: boolean; hints: Array<Record<string, unknown>>;
  locations: Array<{ id: number; name: string; checked: boolean }>;
  auto_deaths: number; manual_deaths: number; total_deaths: number; status_label: string;
};
export type RoomState = Room & {
  sleeping: boolean; totals: { checks_done: number; checks_total: number; checks_pct: number; completed: number; deaths: number };
  slots: Slot[];
};
export type ViewerSlot = {
  id: number; slot_name: string; game: string | null; checks_done: number; checks_total: number;
  checks_pct: number; remaining_checks: number; completed: boolean;
  hints: Array<Record<string, unknown>>; locations: Array<{ id: number; name: string; checked: boolean }>;
  total_deaths: number;
};
export type ViewerState = {
  id: number; label: string; game_status: string; room_key: string; sleeping: boolean;
  totals: { checks_done: number; checks_total: number; checks_pct: number; completed: number; deaths: number };
  slots: ViewerSlot[];
};
export type Event = { id: number; event_type: string | null; text: string; html: string | null; ts: string };
export type Preferences = { order: string[]; visible: string[] };

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(apiBase() + path, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    const message = typeof detail === "string"
      ? detail
      : Array.isArray(detail)
        ? detail.map((item) => item?.msg || String(item)).join(", ")
        : response.statusText || "Request failed";
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export function websocketUrl(roomKey: string): string {
  const url = new URL(apiBase() || window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws/rooms/" + roomKey;
  return url.toString();
}

export function viewerWebsocketUrl(viewerCode: string): string {
  const url = new URL(apiBase() || window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws/view/" + viewerCode;
  return url.toString();
}
