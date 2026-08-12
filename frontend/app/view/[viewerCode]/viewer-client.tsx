"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Event, ViewerSlot, ViewerState, api, viewerWebsocketUrl } from "../../../lib/api";

function statusLabel(status: string) {
  return status === "completed" ? "Completed" : status === "canceled" ? "Canceled" : "In progress";
}

function ViewerHints({ slot }: { slot: ViewerSlot }) {
  const found = slot.hints.filter((hint) => Boolean(hint.found)).length;
  if (!slot.hints.length) return null;
  return <details className="hint-information"><summary>Show hints ({found}/{slot.hints.length})</summary><div className="hint-list">{slot.hints.map((hint, index) =>
    <div className={"hint-row " + (hint.found ? "found" : "pending")} key={index}>
      <span className={"hint-state-icon " + (hint.found ? "found" : "pending")} title={hint.found ? "Found" : "Not found"} aria-label={hint.found ? "Found" : "Not found"}>{hint.found ? "✓" : "○"}</span>
      <div className="hint-fields">
        <div className="hint-field"><span>Finder</span><strong className="hint-player">{String(hint.finding_player || "Unknown player")}</strong></div>
        <div className="hint-field"><span>Finder game</span><strong className="hint-game">{String(hint.finding_game || "Unknown game")}</strong></div>
        <div className="hint-field"><span>Receiver</span><strong className="hint-player">{String(hint.receiving_player || "Unknown player")}</strong></div>
        <div className="hint-field"><span>Receiver game</span><strong className="hint-game">{String(hint.receiving_game || "Unknown game")}</strong></div>
        <div className="hint-field"><span>Item</span><strong className={"hint-item " + (hint.key_item ? "hint-key" : "")}>{String(hint.item || "Unknown item")}</strong></div>
        <div className="hint-field"><span>Location</span><strong className="hint-location">{String(hint.location || "Unknown location")}</strong></div>
      </div>
    </div>
  )}</div></details>;
}

export default function ViewerClient({ viewerCode }: { viewerCode: string }) {
  const [state, setState] = useState<ViewerState | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [message, setMessage] = useState("");

  async function refresh() {
    setState(await api<ViewerState>("/api/v1/view/" + viewerCode));
    setEvents(await api<Event[]>("/api/v1/view/" + viewerCode + "/events"));
  }

  useEffect(() => {
    refresh().catch((error) => setMessage(error.message));
    const socket = new WebSocket(viewerWebsocketUrl(viewerCode));
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.type === "room.updated" || payload.type === "room.event") refresh().catch(() => undefined);
    };
    return () => socket.close();
  }, [viewerCode]);

  if (!state) return <main className="main"><p className="muted">{message || "Loading viewer room..."}</p></main>;

  return <div className="page-shell"><header className="topbar"><h1>🏝️ {state.label}</h1><div className="topbar-actions"><span className={"tag " + state.game_status}>{statusLabel(state.game_status)}</span><Link className="button small" href="/">Dashboard</Link></div></header><main className="main">
    <p className="muted">View-only room · {state.sleeping ? "Sleeping" : "Active"}</p>
    <section className="panel" style={{ marginBottom: 14 }}><div className="card-stats"><div><strong>{state.totals.checks_done}/{state.totals.checks_total}</strong>Checks</div><div><strong>{state.totals.completed}/{state.slots.length}</strong>Completed</div><div><strong>{state.totals.deaths}</strong>Deaths</div></div></section>
    <section className="player-grid">{state.slots.map((slot) => <article className="player-card" key={slot.id}><div className="player-title"><div className="player-name"><strong>{slot.game || "Unknown game"}</strong> <span>({slot.slot_name})</span></div><strong>{slot.total_deaths}</strong></div><div className="box-grid"><div className="box"><h3>Checks</h3><div className="box-content"><div className="progress"><div style={{ width: slot.checks_pct + "%" }} /><span>{slot.checks_pct.toFixed(2)}% done</span></div><span>{slot.checks_done}/{slot.checks_total} collected</span></div></div><div className="box"><h3>Hints</h3><div className="box-content"><span>{slot.hints.filter((hint) => Boolean(hint.found)).length}/{slot.hints.length} found</span></div></div></div><ViewerHints slot={slot} /></article>)}</section>
    <section className="panel" style={{ marginTop: 16 }}><h3>Activity feed</h3><div className="event-log">{events.map((event) => <div className="event-row" key={event.id}><span className="event-time">{new Date(event.ts).toLocaleTimeString()}</span><span dangerouslySetInnerHTML={{ __html: event.html || event.text }} /></div>)}</div></section>
  </main></div>;
}
