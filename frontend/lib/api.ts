import type { Action, Alert, AgentName, CaseSummary, GeoStory, Pending2FA, Stats, StoryActions, StoryAgents, StoryAmount, StoryCase, StoryHourly, StoryMetrics, StoryOverview } from "@/lib/types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { ...init, cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
  return response.json() as Promise<T>;
}

export const api = {
  overview: () => request<StoryOverview>("/story/overview"),
  hourly: () => request<StoryHourly[]>("/story/hourly"),
  amounts: () => request<StoryAmount[]>("/story/amounts"),
  actions: () => request<StoryActions>("/story/actions"),
  agents: () => request<StoryAgents>("/story/agents"),
  cases: (limit = 20) => request<CaseSummary[]>(`/story/cases?limit=${limit}`),
  caseFile: (txnId: number) => request<StoryCase>(`/story/case/${txnId}`),
  muleGraph: (accountId: string) => request<{ nodes: { id: string }[]; edges: { source: string; target: string; amount: number }[] }>(`/story/mule-graph/${encodeURIComponent(accountId)}`),
  geo: (accountId: string) => request<GeoStory>(`/story/geo/${encodeURIComponent(accountId)}`),
  metrics: () => request<StoryMetrics>("/story/metrics"),
  stats: () => request<Stats>("/stats"),
  alerts: (limit = 50) => request<Alert[]>(`/alerts?limit=${limit}`),
  pending2FA: () => request<Pending2FA[]>("/pending-2fa"),
  reviewQueue: () => request<Alert[]>("/review-queue"),
  verify2FA: (txnId: number, otp: string) => request<{ status: string }>("/2fa/verify", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ txn_id: txnId, otp }) }),
  review: (txnId: number, decision: "APPROVE" | "BLOCK", analyst: string) => request<{ status: string }>(`/review/${txnId}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, analyst }) }),
  devOtp: (txnId: number) => request<{ otp: string }>(`/dev/otp/${txnId}`),
  demo: (name: "mule" | "night" | "travel") => request<{ scenario: string; published: number; txn_ids: number[] }>(`/demo/scenario/${name}`, { method: "POST" }),
};

export type { Action, AgentName };
