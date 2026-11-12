"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Check, Gauge, Play, RotateCcw, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { AgentName, StoryCase, StreamEvent } from "@/lib/types";
import { ActionBadge, AgentScoreBar, Card, ConnectionPill, EmptyState } from "@/components/ui";
import { useEventStream } from "@/hooks/useEventStream";

const scenarios = [
  { name: "mule" as const, title: "Mule account", description: "Many senders funnel money into one account, then it is forwarded almost immediately.", color: "violet" },
  { name: "night" as const, title: "Night-time transaction", description: "A normally daytime account makes a large transfer at 02:30.", color: "cyan" },
  { name: "travel" as const, title: "Impossible travel", description: "The same account appears in Nagpur, then London twenty minutes later.", color: "emerald" },
];
const number = (value: unknown, fallback = 0) => typeof value === "number" ? value : Number(value) || fallback;
const text = (value: unknown, fallback = "") => typeof value === "string" ? value : fallback;
const record = (value: unknown): Record<string, unknown> => value && typeof value === "object" ? value as Record<string, unknown> : {};
const money = (value: number) => `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
const stageLabels = ["Transaction received", "Frequency agent", "Time agent", "Geo agent", "Policy engine", "2FA challenge", "Final status"];

export default function DemoPage() {
  const stream = useEventStream();
  const [scenario, setScenario] = useState<"mule" | "night" | "travel" | null>(null);
  const [txnIds, setTxnIds] = useState<number[]>([]);
  const [selectedTxn, setSelectedTxn] = useState<number | null>(null);
  const [caseFile, setCaseFile] = useState<StoryCase | null>(null);
  const [busy, setBusy] = useState(false);
  const [speed, setSpeed] = useState<"1x" | "0.5x">("1x");
  const [notice, setNotice] = useState("");
  const [otp, setOtp] = useState("");
  const [otpMessage, setOtpMessage] = useState("");

  const journeyEvents = useMemo(() => stream.events.filter(event => txnIds.includes(event.txn_id) && event.txn_id === selectedTxn), [selectedTxn, stream.events, txnIds]);
  const stages = useMemo(() => journeyEvents.map(event => event.stage), [journeyEvents]);
  const policyEvent = journeyEvents.find(event => event.stage === "POLICY_DECISION");
  const policy = record(policyEvent?.detail);
  const finalEvent = journeyEvents.find(event => ["APPROVED", "HELD", "BLOCKED"].includes(event.stage));
  const needs2fa = stages.includes("2FA_SENT") || text(policy.action) === "REQUEST_2FA";
  const activeStep = finalEvent ? 6 : needs2fa ? 5 : policyEvent ? 4 : stages.includes("AGENTS_SCORED") ? 3 : stages.includes("RECEIVED") ? 1 : 0;

  useEffect(() => {
    if (!selectedTxn) return;
    let active = true;
    const load = () => api.caseFile(selectedTxn).then(value => active && setCaseFile(value)).catch(() => undefined);
    load();
    const timer = window.setInterval(load, speed === "1x" ? 700 : 1400);
    return () => { active = false; window.clearInterval(timer); };
  }, [selectedTxn, speed]);

  const play = async (name: "mule" | "night" | "travel") => {
    setBusy(true); setNotice(""); setOtp(""); setOtpMessage("");
    try { const result = await api.demo(name); setScenario(name); setTxnIds(result.txn_ids); setSelectedTxn(result.txn_ids.at(-1) ?? null); setNotice(`${result.published} transactions published. Following the decisive transaction.`); } catch (error) { setNotice(error instanceof Error ? error.message : "Could not start the scenario."); } finally { setBusy(false); }
  };
  const reset = async () => { try { await api.resetDemo(); setScenario(null); setTxnIds([]); setSelectedTxn(null); setCaseFile(null); setNotice("Demo accounts reset."); } catch { setNotice("Could not reset the demo accounts."); } };
  const fetchOtp = async () => {
    if (!selectedTxn) return;
    setOtpMessage("Waiting for the verification request...");
    for (let attempt = 0; attempt < 6; attempt += 1) {
      try {
        const result = await api.devOtp(selectedTxn);
        setOtp(result.otp);
        setOtpMessage("Development OTP loaded. Try it, or enter a wrong code three times.");
        return;
      } catch {
        await new Promise(resolve => window.setTimeout(resolve, 500));
      }
    }
    setOtpMessage("OTP is not ready yet. Confirm the backend and risk consumer are running, then try again.");
  };
  const verify = async () => { if (!selectedTxn || otp.length !== 6) return; try { const result = await api.verify2FA(selectedTxn, otp); setOtpMessage(`Verification status: ${result.status}`); } catch (error) { setOtpMessage(error instanceof Error ? error.message : "Verification failed."); } };

  return <main className="demo-page shell"><header className="topbar"><Link href="/story" className="brand"><span className="brand-mark"><ShieldCheck size={19} /></span><span>FinSight <small>risk intelligence</small></span></Link><nav><Link href="/story">Story</Link><Link href="/live">Live</Link><Link className="active" href="/demo">Demo</Link><Link href="/shop">Shop</Link></nav><ConnectionPill apiUp={stream.connected || Boolean(caseFile)} streamConnected={stream.connected} /></header>
    <section className="demo-hero"><div><span className="eyebrow">SCENARIO LAB</span><h1>Watch a fraud get caught.</h1><p>Choose a crafted pattern, then follow the real event ledger from receipt to outcome. Every caption names the signal that moved the decision.</p></div><div className="speed-control" role="group" aria-label="Demo speed"><span>Explain mode</span><button className={speed === "1x" ? "selected" : ""} onClick={() => setSpeed("1x")}>1x</button><button className={speed === "0.5x" ? "selected" : ""} onClick={() => setSpeed("0.5x")}>0.5x</button></div></section>
    <section className="scenario-grid">{scenarios.map(item => <Card className={`scenario-card ${item.color}`} key={item.name}><span className="eyebrow">{item.name} pattern</span><h2>{item.title}</h2><p>{item.description}</p><button className="play-button" onClick={() => play(item.name)} disabled={busy}><Play size={15} /> {busy && scenario === item.name ? "Publishing" : "Play scenario"}</button></Card>)}</section>
    <div className="demo-toolbar"><button className="button" onClick={reset}><RotateCcw size={14} /> Reset demo</button>{notice && <span className="demo-notice">{notice}</span>}</div>
    {!scenario ? <Card className="demo-empty"><EmptyState title="Pick a scenario to begin" detail="The journey will appear here as the API publishes and evaluates real transactions." /></Card> : <><section className="journey-section"><div className="journey-head"><div><span className="eyebrow">LIVE JOURNEY / {scenario}</span><h2>{scenarios.find(item => item.name === scenario)?.title}</h2></div><div className="txn-picker"><span>Transactions</span>{txnIds.map(id => <button className={id === selectedTxn ? "selected" : ""} key={id} onClick={() => setSelectedTxn(id)}>#{id}</button>)}</div></div><div className="pipeline">{stageLabels.map((label, index) => <PipelineStep key={label} label={label} index={index} active={index <= activeStep} current={index === activeStep} event={eventForStep(index, journeyEvents)} caseFile={caseFile} speed={speed} />)}</div>{needs2fa && <TwoFAChallenge txnId={selectedTxn} otp={otp} setOtp={setOtp} message={otpMessage} onFetch={fetchOtp} onVerify={verify} />}</section><section className="audience-grid"><AudienceCard title="What the user sees" icon={<Sparkles size={17} />}><p>{userSummary(finalEvent, policy)}</p><div className="user-status"><ActionBadge action={text(policy.action, finalEvent?.stage ?? "PROCESSING")} />{finalEvent && <span>{finalEvent.stage === "APPROVED" ? "Payment approved" : finalEvent.stage === "HELD" ? "Payment held for review" : "Payment blocked"}</span>}</div></AudienceCard><AudienceCard title="What the analyst sees" icon={<Gauge size={17} />}><AnalystSummary caseFile={caseFile} policy={policy} events={journeyEvents} /></AudienceCard></section></>}
    <footer><span>FinSight / scenario lab</span><span>{stream.connected ? "stream connected" : "reconnecting"} · speed {speed}</span></footer>
  </main>;
}

function eventForStep(index: number, events: StreamEvent[]) { const stage = ["RECEIVED", "AGENTS_SCORED", "AGENTS_SCORED", "AGENTS_SCORED", "POLICY_DECISION", "2FA_SENT", "APPROVED", "HELD", "BLOCKED"][index]; return events.find(event => event.stage === stage) ?? (index === 6 ? events.find(event => ["APPROVED", "HELD", "BLOCKED"].includes(event.stage)) : undefined); }
function PipelineStep({ label, index, active, current, event, caseFile, speed }: { label: string; index: number; active: boolean; current: boolean; event?: StreamEvent; caseFile: StoryCase | null; speed: string }) { const detail = record(event?.detail); const agent = index > 0 && index < 4 ? (["frequency", "time", "geo"] as AgentName[])[index - 1] : null; const agentData = record(record(caseFile?.agents).agents); const result = agent ? record(agentData[agent]) : {}; const score = number(result.score, number(record(record(caseFile?.agents).scores)[agent ?? ""])); return <motion.div className={`pipeline-step ${active ? "active" : ""} ${current ? "current" : ""}`} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * .06, duration: speed === "1x" ? .35 : .7 }}><div className="step-node">{active ? <Check size={15} /> : <span>{index + 1}</span>}</div><strong>{label}</strong>{agent ? <><div className="journey-score"><span style={{ width: `${Math.min(100, score)}%` }} /></div><small>{score ? `${Math.round(score)} / 100` : "waiting for score"}</small><p>{(Array.isArray(result.reasons) ? result.reasons : []).slice(0, 2).join("; ") || text(detail.reasons, "The detector is listening for a departure from normal.")}</p></> : <p>{captionFor(index, event, caseFile)}</p>}</motion.div>; }
function captionFor(index: number, event?: StreamEvent, data?: StoryCase | null) { const transaction = record(data?.transaction); if (index === 0) return event ? `${text(transaction.type, "Transaction")} for ${money(number(transaction.amount))} received at ${new Date(event.created_at).toLocaleTimeString()}.` : "Waiting for the transaction to enter the ledger."; if (index === 4) return event ? `Final score ${Math.round(number(record(event.detail).final_score))}; deterministic policy selected ${text(record(event.detail).action, "an action")}.` : "Scores combine here. No LLM makes this decision."; if (index === 5) return event ? "A verification challenge was sent. The user has three attempts." : "Only REQUEST_2FA decisions open this challenge."; return event ? `${event.stage.replaceAll("_", " ")} at ${new Date(event.created_at).toLocaleTimeString()}.` : "The final outcome will appear here."; }
function TwoFAChallenge({ txnId, otp, setOtp, message, onFetch, onVerify }: { txnId: number | null; otp: string; setOtp: (value: string) => void; message: string; onFetch: () => void; onVerify: () => void }) { return <motion.div className="otp-challenge" initial={{ opacity: 0, scale: .98 }} animate={{ opacity: 1, scale: 1 }}><div><span className="eyebrow">USER VERIFICATION / TXN {txnId}</span><h3>Confirm it is really you.</h3><p>Enter the six-digit code. Use a wrong code three times to watch the real backend move the transaction to HELD.</p></div><div className="otp-controls"><input value={otp} onChange={event => setOtp(event.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="000000" inputMode="numeric" aria-label="One-time password" /><button className="button" onClick={onFetch}>Fetch dev OTP</button><button className="button" disabled={otp.length !== 6} onClick={onVerify}>Verify</button></div>{message && <small>{message}</small>}</motion.div>; }
function AudienceCard({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) { return <Card className="audience-card"><div className="audience-title">{icon}<h3>{title}</h3></div>{children}</Card>; }
function AnalystSummary({ caseFile, policy, events }: { caseFile: StoryCase | null; policy: Record<string, unknown>; events: StreamEvent[] }) { const agents = record(caseFile?.agents); return <><p>Raw event evidence, detector scores, policy thresholds, and elapsed time between every step.</p><div className="analyst-facts"><span>Score <strong>{Math.round(number(policy.final_score))}</strong></span><span>Events <strong>{events.length}</strong></span><span>Outcome <strong>{text(caseFile?.outcome, "pending")}</strong></span></div><div className="analyst-bars">{(["frequency", "time", "geo"] as AgentName[]).map(agent => <AgentScoreBar key={agent} agent={agent} score={number(record(agents.scores)[agent])} />)}</div><Link href="#case-file" className="story-link">Open full case context <ArrowRight size={14} /></Link></>; }
function userSummary(finalEvent: StreamEvent | undefined, policy: Record<string, unknown>) { if (!finalEvent) return "The payment is being checked. This screen explains only what the customer needs to know."; if (finalEvent.stage === "APPROVED") return "Your payment was approved after the verification code was confirmed."; if (finalEvent.stage === "HELD") return "Your payment is temporarily held while the risk team reviews it."; if (finalEvent.stage === "BLOCKED") return "Your payment was blocked because the risk score crossed the block threshold."; return `A verification step is required for this payment. Current action: ${text(policy.action, "reviewing")}.`; }
