"use client";

import { motion } from "framer-motion";
import type { AgentName, StoryCase } from "@/lib/types";

type TimelineStep = { label: string; detail?: string; score?: number; time?: string; seconds?: number | null };
const number = (value: unknown, fallback = 0) => typeof value === "number" ? value : Number(value) || fallback;
const text = (value: unknown) => typeof value === "string" ? value : "";
const record = (value: unknown): Record<string, unknown> => value && typeof value === "object" ? value as Record<string, unknown> : {};

export default function CaseTimeline({ data }: { data: StoryCase }) {
  const agentData = record(data.agents);
  const scores = record(agentData.scores);
  const details = record(agentData.agents);
  const steps: TimelineStep[] = [];
  for (const event of data.events ?? []) {
    if (event.stage === "AGENTS_SCORED") {
      for (const agent of ["frequency", "time", "geo"] as AgentName[]) {
        const detail = record(details[agent]);
        steps.push({
          label: `${agent} score`,
          detail: Array.isArray(detail.reasons) ? detail.reasons.join("; ") : "",
          score: number(detail.score, number(scores[agent])),
          time: event.created_at,
          seconds: event.seconds_since_previous,
        });
      }
    } else {
      const eventDetail = record(event.detail);
      steps.push({
        label: event.stage.replaceAll("_", " "),
        detail: text(eventDetail.action) || text(eventDetail.status),
        time: event.created_at,
        seconds: event.seconds_since_previous,
      });
    }
  }
  return <div className="evidence-timeline">{steps.map((step, index) => <motion.div className="evidence-step" key={`${step.label}-${index}`} initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: index * .04 }}><span className="timeline-dot" /><div><div className="step-top"><strong>{step.label}</strong><time>{step.time ? new Date(step.time).toLocaleString() : ""}{step.seconds != null ? ` · +${step.seconds.toFixed(1)}s` : ""}</time></div>{step.score !== undefined && <div className="timeline-score"><span style={{ width: `${Math.min(100, Math.max(0, step.score))}%` }} /><b>{Math.round(step.score)}</b></div>}{step.detail && <small>{step.detail}</small>}</div></motion.div>)}</div>;
}
