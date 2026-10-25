import type { Plan, Simulated } from "./types";

export const offline = new URLSearchParams(window.location.search).get("demo") === "offline";
const configuredApiBase = import.meta.env.VITE_API_BASE?.trim();
const API_BASE = configuredApiBase || (import.meta.env.DEV ? "http://localhost:8000" : "");
export const apiConfigured = offline || Boolean(API_BASE);

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE) throw new Error("Live API endpoint is not configured. Set VITE_API_BASE and rebuild the frontend.");
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 15_000);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: init?.signal ?? controller.signal,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw new Error("The API request timed out.");
    throw new Error("The API is unavailable. Check the backend URL and CORS configuration.");
  } finally {
    window.clearTimeout(timeout);
  }
  if (!response.ok) {
    const body = await response.text();
    try {
      const parsed = JSON.parse(body) as { detail?: string };
      throw new Error(parsed.detail || `Request failed (${response.status})`);
    } catch (error) {
      if (error instanceof Error && !error.message.startsWith("Unexpected")) throw error;
      throw new Error(body || `Request failed (${response.status})`);
    }
  }
  return response.json() as Promise<T>;
}

async function offlineFixture(scenarioId: string): Promise<{ simulate: Simulated; plan: Plan }> {
  const fixtureName = scenarioId === "stripe-paymentintents" ? "stripe" : scenarioId;
  const response = await fetch(`/fixtures/${fixtureName}.json`);
  if (!response.ok) throw new Error("Offline fixture is unavailable");
  const raw = await response.json() as {
    id: string;
    before: Record<string, string>;
    after?: Record<string, string>;
    changes: Simulated["changes"];
    sites: Simulated["sites"];
    impacts: Simulated["impacts"];
    graph: Simulated["graph"];
    patch_plan: Plan["plan"];
    verification: Plan["gates"];
  };
  const diffs = Object.entries(raw.before).flatMap(([path, before]) => {
    const after = raw.after?.[path];
    if (after === undefined || after === before) return [];
    return [{ path, before, after }];
  });
  return {
    simulate: { scenario: raw.id, changes: raw.changes, sites: raw.sites, impacts: raw.impacts, graph: raw.graph },
    plan: { scenario: raw.id, plan: raw.patch_plan, diffs, gates: raw.verification },
  };
}

export async function loadSimulation(scenarioId: string): Promise<Simulated> {
  if (offline) return (await offlineFixture(scenarioId)).simulate;
  return request<Simulated>(`/simulate/${scenarioId}`, { method: "POST" });
}

export async function loadPlan(scenarioId: string): Promise<Plan> {
  if (offline) return (await offlineFixture(scenarioId)).plan;
  return request<Plan>("/plan", { method: "POST", body: JSON.stringify({ scenario_id: scenarioId }) });
}

export async function ship(scenarioId: string): Promise<Record<string, unknown>> {
  if (offline) return { dry_run: true, scenario: scenarioId, offline: true };
  return request<Record<string, unknown>>("/ship", {
    method: "POST",
    body: JSON.stringify({ scenario_id: scenarioId, dry_run: true, approved_by: "click" }),
  });
}

export async function health(): Promise<{ ok: boolean }> {
  if (offline) return { ok: true };
  return request<{ ok: boolean }>("/healthz");
}
