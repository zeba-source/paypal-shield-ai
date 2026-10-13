export type Action = "ALLOW" | "REQUEST_2FA" | "HOLD_FOR_REVIEW" | "BLOCK";
export type AgentName = "frequency" | "time" | "geo";

export interface StoryOverview {
  total: number;
  counts_by_type: { type: string; count: number; amount: number }[];
  amount_total: number;
  amount_average: number;
  time_range: { start: string | null; end: string | null };
  accounts: number;
  flagged_count: number;
  flagged_share: number;
  data_note: string;
}

export interface StoryHourly { hour: number; normal: number; flagged: number }
export interface StoryAmount { amount: number }
export interface StoryActions {
  actions: { action: Action; count: number; amount: number }[];
  funnel: { total: number; flagged: number; two_fa_requested: number; two_fa_passed: number; two_fa_failed: number; final_approved: number; final_held: number; final_blocked: number };
}
export interface AgentAnalytics { score_distribution: { bucket: number; count: number }[]; top_reasons: { reason: string; count: number }[] }
export type StoryAgents = Record<AgentName, AgentAnalytics>;
export interface CaseSummary { id: number; txn_id: number; account_id: string; final_score: number; action: Action; type: string; amount: number; event_time: string; reasons: string[] }
export interface TxnEvent { id: number; txn_id: number; stage: string; detail: Record<string, unknown>; created_at: string; seconds_since_previous?: number | null }
export interface StoryCase { transaction: Record<string, unknown>; profile: Record<string, unknown> | null; agents: Record<string, unknown>; policy: Record<string, unknown>; alert: CaseSummary | null; events: TxnEvent[]; outcome: string; previous_transactions: Record<string, unknown>[] }
export interface GeoStory { locations: Record<string, unknown>[]; impossible_travel: Record<string, unknown>[] }
export interface Alert extends CaseSummary { frequency_score: number; time_score: number; geo_score: number; reasons: string[] }
export interface Pending2FA { id: number; txn_id: number; account_id: string; status: string; attempts: number; expires_at: string }
export interface Stats { counts_by_action: Partial<Record<Action, number>>; average_final_score: number | null; two_fa_pass_rate: number; pending_2fa_count: number; average_decision_latency_ms: number; p95_decision_latency_ms: number }
export interface LiveLocation { txn_id: number; action: Action; lat: number; lon: number; city: string; country: string; event_time: string }
export interface LiveFeedRow extends CaseSummary { frequency_score: number; time_score: number; geo_score: number; received_at?: string; pulse?: boolean }
export interface DemoResult { scenario: string; published: number; txn_ids: number[] }
export interface StoryMetrics { count: number; precision: number; recall: number; f1: number; false_positive_rate: number; average_latency_ms: number; confusion_matrix: { true_positive: number; false_positive: number; false_negative: number; true_negative: number } }
export type StreamEvent = TxnEvent;
