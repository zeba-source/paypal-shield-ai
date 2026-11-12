"use client";

import { useState } from "react";
import { Card, EmptyState, SectionTitle } from "@/components/ui";
import LiveGrid from "@/components/LiveGrid";
import { api } from "@/lib/api";
import type { Alert, Investigation } from "@/lib/types";

export default function ReviewQueueGrid({ queue, onRowClick }: { queue: Alert[]; onRowClick: (txnId: number) => void }) {
  const [analyst, setAnalyst] = useState("");
  const [message, setMessage] = useState("");
  const [investigations, setInvestigations] = useState<Record<number, Investigation>>({});
  const [busyTxnId, setBusyTxnId] = useState<number | null>(null);

  const review = async (txnId: number, decision: "APPROVE" | "BLOCK") => {
    if (!analyst.trim()) {
      setMessage("Enter an analyst name first.");
      return;
    }
    try {
      await api.review(txnId, decision, analyst.trim());
      setMessage(`Transaction ${txnId}: ${decision}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Review failed");
    }
  };

  const investigate = async (txnId: number) => {
    if (busyTxnId === txnId) return;
    setBusyTxnId(txnId);
    setMessage("");
    try {
      const result = await api.investigate(txnId);
      setInvestigations(current => ({ ...current, [txnId]: result }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Investigation failed");
    } finally {
      setBusyTxnId(null);
    }
  };

  const selectedInvestigation = Object.values(investigations).at(-1);
  return <Card className="ops-panel review-grid-panel">
    <SectionTitle eyebrow="ANALYST WORKBENCH" title="Review queue" detail={`${queue.length} held`} />
    <input className="analyst-input" value={analyst} onChange={event => setAnalyst(event.target.value)} placeholder="Analyst name" aria-label="Analyst name" />
    {queue.length ? <LiveGrid rows={queue} onRowClick={onRowClick} onInvestigate={investigate} onApprove={txnId => review(txnId, "APPROVE")} onBlock={txnId => review(txnId, "BLOCK")} busyTxnId={busyTxnId} /> : <EmptyState title="Queue clear" detail="Held transactions will need an analyst decision." />}
    {selectedInvestigation && <div className="investigation-card review-investigation-summary"><div className="investigation-card-head"><span className="eyebrow">INVESTIGATION / {selectedInvestigation.source}</span><span>{Math.round(selectedInvestigation.confidence * 100)}% confidence</span></div><p>{selectedInvestigation.summary}</p><ul>{selectedInvestigation.key_evidence.map(evidence => <li key={evidence}>{evidence}</li>)}</ul><button className="button" onClick={() => selectedInvestigation.recommended_action === "APPROVE" ? review(selectedInvestigation.txn_id, "APPROVE") : selectedInvestigation.recommended_action === "BLOCK" ? review(selectedInvestigation.txn_id, "BLOCK") : setMessage("This recommendation requires more information; choose an analyst decision.")} disabled={selectedInvestigation.recommended_action === "REQUEST_MORE_INFO"}>Apply recommendation: {selectedInvestigation.recommended_action.replaceAll("_", " ")}</button></div>}
    {message && <span className="ops-message">{message}</span>}
  </Card>;
}
