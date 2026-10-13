"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, ArrowUpRight, BellRing, Database, Radio, ShieldCheck } from "lucide-react";
import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { useEventStream } from "@/hooks/useEventStream";
import { usePolling } from "@/hooks/usePolling";
import { ActionBadge, AgentScoreBar, Card, ConnectionPill, DataNote, EmptyState, KpiTile, Narrative, SectionTitle, Skeleton } from "@/components/ui";
import { HourlyChart } from "@/components/Charts";
import type { CaseSummary, StoryCase } from "@/lib/types";

export default function DashboardShell({ mode = "story" }: { mode?: "story" | "live" | "demo" }) {
  const pathname = usePathname();
  const stream = useEventStream();
  const overviewLoader = useCallback(() => api.overview(), []);
  const hourlyLoader = useCallback(() => api.hourly(), []);
  const actionsLoader = useCallback(() => api.actions(), []);
  const casesLoader = useCallback(() => api.cases(20), []);
  const statsLoader = useCallback(() => api.stats(), []);
  const { data: overview, error: overviewError } = usePolling(overviewLoader);
  const { data: hourly } = usePolling(hourlyLoader);
  const { data: actions } = usePolling(actionsLoader);
  const { data: cases } = usePolling(casesLoader);
  const { data: stats } = usePolling(statsLoader);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedCase, setSelectedCase] = useState<StoryCase | null>(null);
  const [demoBusy, setDemoBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const selectCase = async (alert: CaseSummary) => { setSelectedId(alert.txn_id); try { setSelectedCase(await api.caseFile(alert.txn_id)); } catch { setNotice("Could not load that case file."); } };
  const runDemo = async (name: "mule" | "night" | "travel") => { setDemoBusy(name); try { const result = await api.demo(name); setNotice(`${name} scenario published: ${result.txn_ids.join(", ") || "processing"}`); } catch (error) { setNotice(error instanceof Error ? error.message : "Demo failed"); } finally { setDemoBusy(null); } };
  if (overviewError) return <main className="shell"><EmptyState title="API offline" detail={overviewError} /></main>;
  return <main className="shell">
    <header className="topbar"><Link href="/story" className="brand"><span className="brand-mark"><ShieldCheck size={19} /></span><span>FinSight <small>risk intelligence</small></span></Link><nav><Link className={pathname === "/story" ? "active" : ""} href="/story">Story</Link><Link className={pathname === "/live" ? "active" : ""} href="/live">Live</Link><Link className={pathname === "/demo" ? "active" : ""} href="/demo">Demo</Link></nav><ConnectionPill apiUp={Boolean(overview)} streamConnected={stream.connected} /></header>
    {mode === "demo" && <Card className="demo-strip"><div><span className="eyebrow">SCENARIO LAB</span><h1>Make the invisible visible.</h1><p>Inject a crafted pattern and follow its decision trail in real time.</p></div><div className="demo-actions">{(["mule", "night", "travel"] as const).map(name => <button key={name} onClick={() => runDemo(name)} disabled={Boolean(demoBusy)} className="button secondary">{demoBusy === name ? "Publishing…" : name}<ArrowUpRight size={14} /></button>)}</div></Card>}
    <section className="hero"><div><span className="eyebrow">{mode === "live" ? "LIVE OPERATIONS" : "DECISION NARRATIVE"}</span><h1>{mode === "live" ? "Watch risk move." : "Every transaction leaves a trail."}</h1><Narrative>{mode === "live" ? "The stream is the pulse of the system. New receipts, scores, policy choices, and outcomes arrive here as they happen." : "FinSight turns a raw transaction into a human-readable story: what changed, which signal noticed it, and what the policy decided next."}</Narrative></div><div className="hero-orbit"><Activity size={30} /><span>EVENT<br />LEDGER</span></div></section>
    {notice && <div className="toast">{notice}</div>}
    {overview ? <><div className="kpi-grid"><KpiTile label="Processed" value={overview.total} icon={<Database size={17} />} /><KpiTile label="Flagged" value={overview.flagged_count} suffix={` · ${(overview.flagged_share * 100).toFixed(1)}%`} icon={<BellRing size={17} />} /><KpiTile label="Accounts" value={overview.accounts} icon={<Activity size={17} />} /><KpiTile label="Pending 2FA" value={stats?.pending_2fa_count ?? 0} icon={<Radio size={17} />} /></div><DataNote>{overview.data_note}</DataNote></> : <div className="kpi-grid"><Skeleton /><Skeleton /><Skeleton /><Skeleton /></div>}
    <div className="content-grid"><Card><SectionTitle eyebrow="SIGNAL RHYTHM" title="Activity by hour" detail="normal / flagged" />{hourly ? <HourlyChart data={hourly} /> : <Skeleton className="chart-skeleton" />}</Card><Card><SectionTitle eyebrow="OUTCOMES" title="Decision funnel" /><div className="funnel">{actions && ["total", "flagged", "two_fa_requested", "two_fa_passed", "final_held", "final_blocked"].map(key => <div key={key}><strong>{actions.funnel[key as keyof typeof actions.funnel]}</strong><span>{key.replaceAll("_", " ")}</span></div>)}</div></Card></div>
    <div className="content-grid case-grid"><Card><SectionTitle eyebrow="CASES" title="Most interesting" detail="ranked by final score" />{cases?.length ? <div className="case-list">{cases.map(alert => <button className={`case-row ${selectedId === alert.txn_id ? "selected" : ""}`} key={alert.txn_id} onClick={() => selectCase(alert)}><span className="case-score">{Math.round(alert.final_score)}</span><span><strong>{alert.account_id}</strong><small>txn {alert.txn_id} · {alert.type} · {Number(alert.amount).toLocaleString()}</small></span><ActionBadge action={alert.action} /></button>)}</div> : <EmptyState title="No cases yet" detail="Alerts will appear as the event ledger fills." />}</Card><Card>{selectedCase ? <CaseDetail data={selectedCase} /> : <EmptyState title="Select a case" detail="Choose a case to open its full narrative." />}</Card></div>
    <footer><span>FinSight / real-time risk intelligence</span><span>API {overview ? "reachable" : "waiting"} · stream {stream.connected ? "live" : "reconnecting"}</span></footer>
  </main>;
}

function CaseDetail({ data }: { data: StoryCase }) { const transaction = data.transaction; const scores = (data.agents.scores ?? {}) as Record<string, number>; return <><SectionTitle eyebrow="CASE FILE" title={`Transaction ${transaction.txn_id}`} detail={data.outcome} /><div className="case-head"><ActionBadge action={data.alert?.action ?? data.outcome} /><span>{transaction.nameOrig as string}</span><strong>{Number(transaction.amount).toLocaleString()}</strong></div><AgentScoreBar agent="frequency" score={Number(scores.frequency ?? 0)} /><AgentScoreBar agent="time" score={Number(scores.time ?? 0)} /><AgentScoreBar agent="geo" score={Number(scores.geo ?? 0)} /><div className="timeline">{data.events.map(event => <div className="timeline-item" key={event.id}><span className="timeline-dot" /><div><strong>{event.stage.replaceAll("_", " ")}</strong><small>{new Date(event.created_at).toLocaleTimeString()} {event.seconds_since_previous != null ? `· +${event.seconds_since_previous.toFixed(1)}s` : ""}</small></div></div>)}</div></>; }
