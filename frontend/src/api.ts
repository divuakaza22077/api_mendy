import type { Plan, Simulated } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
export const offline = new URLSearchParams(window.location.search).get("demo") === "offline";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    throw new Error((await response.text()) || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function offlineFixture(): Promise<{ simulate: Simulated; plan: Plan }> {
  const response = await fetch("/fixtures/stripe.json");
  if (!response.ok) throw new Error("Offline fixture is unavailable");
  return response.json() as Promise<{ simulate: Simulated; plan: Plan }>;
}

export async function loadSimulation(scenarioId: string): Promise<Simulated> {
  if (offline) return (await offlineFixture()).simulate;
  return request<Simulated>(`/simulate/${scenarioId}`, { method: "POST" });
}

export async function loadPlan(scenarioId: string): Promise<Plan> {
  if (offline) return (await offlineFixture()).plan;
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
