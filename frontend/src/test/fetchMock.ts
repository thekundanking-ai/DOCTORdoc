import { vi } from "vitest";

type Route = { path: string; method?: string; status?: number; body?: unknown };
type FakeResponse = { ok: boolean; status: number; json: () => Promise<unknown> };

function jsonResponse(body: unknown, status: number): FakeResponse {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

export function installFetchMock(routes: Route[]) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const full = String(input);
    const url = full.split("?")[0].replace(/^\/api/, "");
    const method = init?.method ?? "GET";
    const candidates = routes.filter((r) => url === r.path || url.startsWith(`${r.path}/`));
    const route = candidates
      .map((r) => ({ r, methodMatch: r.method ? (r.method === method ? 2 : 0) : 1, length: r.path.length }))
      .sort((a, b) => b.methodMatch - a.methodMatch || b.length - a.length)[0]?.r;
    if (!route) return jsonResponse({ detail: "not found" }, 404);
    let body = route.body;
    if (Array.isArray(body)) {
      body = body.length > 1 ? body.shift() : body[0];
    }
    return jsonResponse(body ?? {}, route.status ?? 200);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function testUser() {
  return { id: 1, email: "owner@example.com", full_name: "Owner", role: "clinic_owner", clinic_id: 1 };
}

export function testPatient(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    clinic_id: 1,
    full_name: "Alice Smith",
    mobile: "+15551234567",
    is_active: true,
    created_by: 1,
    created_at: "2026-11-06T00:00:00Z",
    updated_at: "2026-11-06T00:00:00Z",
    ...overrides,
  };
}
