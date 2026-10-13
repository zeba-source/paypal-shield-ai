"use client";
import { motion, useMotionValueEvent, useSpring } from "framer-motion";
import { AlertTriangle, CheckCircle2, Clock3, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import type { Action, AgentName } from "@/lib/types";

export const actionTone: Record<Action, string> = { ALLOW: "allow", REQUEST_2FA: "twofa", HOLD_FOR_REVIEW: "hold", BLOCK: "block" };
export const agentTone: Record<AgentName, string> = { frequency: "frequency", time: "time", geo: "geo" };

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) { return <section className={`panel ${className}`}>{children}</section>; }
export function SectionTitle({ eyebrow, title, detail }: { eyebrow?: string; title: string; detail?: string }) { return <div className="section-title"><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div>{detail && <span className="section-detail">{detail}</span>}</div>; }
export function ActionBadge({ action }: { action: Action | string }) { return <span className={`action-badge ${actionTone[action as Action] ?? "neutral"}`}>{action.replaceAll("_", " ")}</span>; }
export function AgentScoreBar({ agent, score }: { agent: AgentName; score: number }) { return <div className="score-row"><span className={`agent-dot ${agentTone[agent]}`} /> <span className="score-name">{agent}</span><div className="score-track"><motion.div className={`score-fill ${agentTone[agent]}`} initial={{ width: 0 }} animate={{ width: `${score}%` }} transition={{ duration: .65 }} /></div><strong>{Math.round(score)}</strong></div>; }
export function KpiTile({ label, value, suffix = "", icon }: { label: string; value: number; suffix?: string; icon?: React.ReactNode }) { const spring = useSpring(0, { duration: 700 }); const [display, setDisplay] = useState(0); useMotionValueEvent(spring, "change", current => setDisplay(Math.round(current))); useEffect(() => spring.set(value), [spring, value]); return <Card className="kpi"><div className="kpi-top"><span>{icon}</span><span className="eyebrow">{label}</span></div><div className="kpi-value">{display.toLocaleString()}{suffix}</div></Card>; }
export function Narrative({ children }: { children: React.ReactNode }) { return <p className="narrative">{children}</p>; }
export function DataNote({ children = "Time and location are simulated because PaySim has no real timestamps or locations." }: { children?: React.ReactNode }) { return <div className="data-note"><AlertTriangle size={15} />{children}</div>; }
export function ConnectionPill({ apiUp, streamConnected }: { apiUp: boolean; streamConnected: boolean }) { return <div className="connection"><span className={apiUp ? "live-dot" : "dead-dot"} /> API {apiUp ? "up" : "offline"}<span className={streamConnected ? "live-dot" : "dead-dot"} /> Stream {streamConnected ? "connected" : "reconnecting"}</div>; }
export function Skeleton({ className = "" }: { className?: string }) { return <div className={`skeleton ${className}`} />; }
export function EmptyState({ title, detail }: { title: string; detail: string }) { return <div className="empty"><ShieldAlert size={22} /><strong>{title}</strong><span>{detail}</span></div>; }
export const statusIcon = { ALLOW: <CheckCircle2 size={15} />, REQUEST_2FA: <Clock3 size={15} />, HOLD_FOR_REVIEW: <AlertTriangle size={15} />, BLOCK: <ShieldAlert size={15} /> };
