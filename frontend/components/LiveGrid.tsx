"use client";

import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";
import { AllCommunityModule, ColDef, GridApi, GridReadyEvent, ModuleRegistry, RowClickedEvent, themeQuartz } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { ActionBadge } from "@/components/ui";
import type { Action, Alert, LiveFeedRow } from "@/lib/types";

ModuleRegistry.registerModules([AllCommunityModule]);

type GridRow = LiveFeedRow | Alert;
type Props = {
  rows: GridRow[];
  onRowClick: (txnId: number) => void;
  onInvestigate: (txnId: number) => void;
  onApprove: (txnId: number) => void;
  onBlock: (txnId: number) => void;
  busyTxnId?: number | null;
};

const gridTheme = themeQuartz.withParams({
  backgroundColor: "#101c2d",
  foregroundColor: "#edf4ff",
  borderColor: "#243650",
  headerBackgroundColor: "#0b1728",
  headerTextColor: "#8ea0bb",
  oddRowBackgroundColor: "#0d192a",
  rowHoverColor: "#16253a",
  selectedRowBackgroundColor: "#12313b",
  fontFamily: "ui-monospace, monospace",
  fontSize: "11px",
});

export default function LiveGrid({ rows, onRowClick, onInvestigate, onApprove, onBlock, busyTxnId = null }: Props) {
  const [quickFilter, setQuickFilter] = useState("");
  const [gridApi, setGridApi] = useState<GridApi<GridRow> | null>(null);
  const knownIds = useRef(new Set<number>());
  const initialised = useRef(false);
  const columns = useMemo<ColDef<GridRow>[]>(() => [
    { headerName: "Time", field: "event_time", minWidth: 130, valueFormatter: params => params.value ? new Date(params.value).toLocaleString() : "-" },
    { headerName: "Txn", field: "txn_id", width: 82 },
    { headerName: "Account", field: "account_id", minWidth: 145, flex: 1 },
    { headerName: "Amount", field: "amount", width: 100, valueFormatter: params => `$${Number(params.value ?? 0).toFixed(2)}` },
    { headerName: "Frequency", field: "frequency_score", width: 100, cellClass: "score-frequency", valueFormatter: params => String(Math.round(Number(params.value ?? 0))) },
    { headerName: "Time", field: "time_score", width: 82, cellClass: "score-time", valueFormatter: params => String(Math.round(Number(params.value ?? 0))) },
    { headerName: "Geo", field: "geo_score", width: 82, cellClass: "score-geo", valueFormatter: params => String(Math.round(Number(params.value ?? 0))) },
    { headerName: "Action", field: "action", width: 150, cellRenderer: ActionCell },
    { headerName: "Payment status", width: 135, valueGetter: params => params.data && "payment_status" in params.data ? params.data.payment_status : params.data?.action ?? "-" },
    { headerName: "Actions", width: 250, sortable: false, filter: false, cellRenderer: ActionButtonsCell, cellRendererParams: { onInvestigate, onApprove, onBlock, busyTxnId } },
  ], [busyTxnId, onApprove, onBlock, onInvestigate]);

  useEffect(() => {
    if (!gridApi) return;
    gridApi.setGridOption("quickFilterText", quickFilter);
  }, [gridApi, quickFilter]);

  useEffect(() => {
    if (!gridApi) return;
    const nextRows = rows.slice(0, 500);
    const nextIds = new Set(nextRows.map(row => row.txn_id));
    if (!initialised.current) {
      gridApi.setGridOption("rowData", nextRows);
      knownIds.current = nextIds;
      initialised.current = true;
      return;
    }
    const additions = nextRows.filter(row => !knownIds.current.has(row.txn_id));
    const updates = nextRows.filter(row => knownIds.current.has(row.txn_id));
    const currentRows: GridRow[] = [];
    gridApi.forEachNode(node => { if (node.data) currentRows.push(node.data); });
    const removals = currentRows.filter(row => !nextIds.has(row.txn_id));
    if (additions.length || updates.length || removals.length) {
      gridApi.applyTransaction({ add: additions, addIndex: 0, update: updates, remove: removals });
    }
    knownIds.current = nextIds;
  }, [gridApi, rows]);

  const onGridReady = (event: GridReadyEvent<GridRow>) => setGridApi(event.api);
  const onRowClicked = (event: RowClickedEvent<GridRow>) => { if (event.data) onRowClick(event.data.txn_id); };

  return <div className="live-grid-shell"><div className="grid-toolbar"><label htmlFor="live-grid-filter">Quick filter</label><input id="live-grid-filter" value={quickFilter} onChange={event => setQuickFilter(event.target.value)} placeholder="Search account, action, txn..." /><span>Sort and filter any column</span></div><div className="ag-theme-quartz-dark live-ag-grid"><AgGridReact<GridRow> theme={gridTheme} columnDefs={columns} defaultColDef={{ sortable: true, filter: true, resizable: true }} getRowId={params => String(params.data.txn_id)} rowData={[]} onGridReady={onGridReady} onRowClicked={onRowClicked} animateRows={false} headerHeight={36} rowHeight={42} /></div></div>;
}

function ActionCell({ value }: { value: Action }) { return <ActionBadge action={value ?? "-"} />; }

function ActionButtonsCell({ data, onInvestigate, onApprove, onBlock, busyTxnId }: { data: GridRow; onInvestigate: (txnId: number) => void; onApprove: (txnId: number) => void; onBlock: (txnId: number) => void; busyTxnId: number | null }) {
  if (!data) return null;
  return <div className="grid-actions" onClick={event => event.stopPropagation()}><button className="grid-investigate" onClick={() => onInvestigate(data.txn_id)} disabled={busyTxnId === data.txn_id}>{busyTxnId === data.txn_id ? "Working" : "Investigate"}</button><button className="grid-approve" onClick={() => onApprove(data.txn_id)}>Approve</button><button className="grid-block" onClick={() => onBlock(data.txn_id)}>Block</button></div>;
}
