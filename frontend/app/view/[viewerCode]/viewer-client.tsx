"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Event, ViewerSlot, ViewerState, api, viewerWebsocketUrl } from "../../../lib/api";

function statusLabel(status: string) {
  return status === "completed" ? "Completed" : status === "canceled" ? "Cancelled" : "In progress";
}

function hintKey(hint: Record<string, unknown>) {
  return String(hint.hint_key || ["finding_player", "receiving_player", "location", "item"].map((field) => String(hint[field] || "")).join(":"));
}

function ViewerHintRow({ hint }: { hint: Record<string, unknown> }) {
  const found = Boolean(hint.found);
  const favorite = Boolean(hint.favorite) && !found;
  return <div className={"hint-row " + (found ? "found" : "pending")}>
    <span className={"hint-favorite " + (favorite ? "active" : "")} title={favorite ? "Favorite hint" : undefined} aria-label={favorite ? "Favorite hint" : undefined}>★</span>
    <span className={"hint-state-icon " + (found ? "found" : "pending")} title={found ? "Found" : "Not found"} aria-label={found ? "Found" : "Not found"}>{found ? "✓" : "○"}</span>
    <div className="hint-fields">
      <div className="hint-field"><span>Receiver</span><strong className="hint-player">{String(hint.receiving_player || "Unknown player")}</strong></div>
      <div className="hint-field"><span>Receiver game</span><strong className="hint-game">{String(hint.receiving_game || "Unknown game")}</strong></div>
      <div className="hint-field"><span>Item</span><strong className={"hint-item " + (hint.key_item ? "hint-key" : "")}>{String(hint.item || "Unknown item")}</strong></div>
      <div className="hint-field"><span>Finder</span><strong className="hint-player">{String(hint.finding_player || "Unknown player")}</strong></div>
      <div className="hint-field"><span>Finder game</span><strong className="hint-game">{String(hint.finding_game || "Unknown game")}</strong></div>
      <div className="hint-field"><span>Location</span><strong className="hint-location">{String(hint.location || "Unknown location")}</strong></div>
    </div>
  </div>;
}

function ViewerHintSection({ label, hints, open, onToggleOpen }: { label: string; hints: Record<string, unknown>[]; open: boolean; onToggleOpen: () => void }) {
  return <div className="hint-section"><button className="hint-section-toggle" type="button" onClick={onToggleOpen} aria-expanded={open}><span>{label}</span><span className="hint-section-chevron" aria-hidden="true">{open ? "▾" : "▸"}</span></button>{open && (hints.length ? <div className="hint-list">{hints.map((hint, index) => <ViewerHintRow key={hintKey(hint) || String(index)} hint={hint} />)}</div> : <p className="hint-section-empty">No hints in this section.</p>)}</div>;
}

function ViewerHints({ slot }: { slot: ViewerSlot }) {
  const [open, setOpen] = useState(false);
  const [trackedOpen, setTrackedOpen] = useState(() => slot.hints.some((hint) => Boolean(hint.favorite) && !hint.found));
  const [activeOpen, setActiveOpen] = useState(true);
  const [completedOpen, setCompletedOpen] = useState(false);
  const found = slot.hints.filter((hint) => Boolean(hint.found)).length;
  if (!slot.hints.length) return null;
  const ordered = [...slot.hints].sort((left, right) => Number(right.hint_order || 0) - Number(left.hint_order || 0));
  const favorites = ordered.filter((hint) => Boolean(hint.favorite) && !hint.found);
  const active = ordered.filter((hint) => !hint.found && !hint.favorite);
  const completed = ordered.filter((hint) => Boolean(hint.found));
  return <div className="hint-information"><button className="button small" onClick={() => setOpen((current) => !current)}>{open ? "Hide hints" : "Show hints"} ({found}/{slot.hints.length})</button>{open && <>
    <ViewerHintSection label="Tracked" hints={favorites} open={trackedOpen} onToggleOpen={() => setTrackedOpen((current) => !current)} />
    <ViewerHintSection label="Active Hints" hints={active} open={activeOpen} onToggleOpen={() => setActiveOpen((current) => !current)} />
    <ViewerHintSection label="Completed Hints" hints={completed} open={completedOpen} onToggleOpen={() => setCompletedOpen((current) => !current)} />
  </>}</div>;
}

function ActivityFeed({ events }: { events: Event[] }) {
  const logRef = useRef<HTMLDivElement>(null);
  const atNewestRef = useRef(true);
  const [atNewest, setAtNewest] = useState(true);

  function updatePosition() {
    const log = logRef.current;
    if (!log) return;
    const newest = log.scrollHeight - log.clientHeight - log.scrollTop <= 8;
    atNewestRef.current = newest;
    setAtNewest(newest);
  }

  useEffect(() => {
    const log = logRef.current;
    if (!log) return;
    requestAnimationFrame(() => {
      if (atNewestRef.current) log.scrollTop = log.scrollHeight;
      updatePosition();
    });
  }, [events]);

  function goToNewest() {
    const log = logRef.current;
    if (!log) return;
    log.scrollTop = log.scrollHeight;
    atNewestRef.current = true;
    setAtNewest(true);
  }

  return <section className="panel activity-panel"><div className="activity-heading"><h3>Activity feed</h3>{!atNewest && <button className="button small" onClick={goToNewest}>To Newest</button>}</div><div className="event-log" ref={logRef} onScroll={updatePosition}>{events.map((event) => <div className="event-row" key={event.id}><span className="event-time">{new Date(event.ts).toLocaleTimeString()}</span><span dangerouslySetInnerHTML={{ __html: event.html || event.text }} /></div>)}</div></section>;
}

export default function ViewerClient({ viewerCode }: { viewerCode: string }) {
  const [state, setState] = useState<ViewerState | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [message, setMessage] = useState("");
  const refreshInFlight = useRef<Promise<void> | null>(null);
  const refreshQueued = useRef(false);
  const eventsInFlight = useRef<Promise<void> | null>(null);
  const eventsQueued = useRef(false);
  const latestEventId = useRef(0);
  const latestRevision = useRef(0);

  async function refresh() {
    if (refreshInFlight.current) {
      refreshQueued.current = true;
      return refreshInFlight.current;
    }
    const run = (async () => {
      const next = await api<ViewerState>("/api/v1/view/" + viewerCode);
      if (next.revision >= latestRevision.current) { latestRevision.current = next.revision; setState(next); }
    })();
    refreshInFlight.current = run;
    try { await run; } finally {
      refreshInFlight.current = null;
      if (refreshQueued.current) { refreshQueued.current = false; void refresh(); }
    }
  }

  async function loadEvents() {
    if (eventsInFlight.current) {
      eventsQueued.current = true;
      return eventsInFlight.current;
    }
    const afterId = latestEventId.current;
    const run = (async () => {
      const incoming = await api<Event[]>("/api/v1/view/" + viewerCode + "/events?after_id=" + afterId);
      if (incoming.length) latestEventId.current = Math.max(latestEventId.current, ...incoming.map((event) => event.id));
      setEvents((current) => {
        const byId = new Map(current.map((event) => [event.id, event]));
        incoming.forEach((event) => byId.set(event.id, event));
        return [...byId.values()].sort((left, right) => left.id - right.id).slice(-500);
      });
    })();
    eventsInFlight.current = run;
    try { await run; } finally {
      eventsInFlight.current = null;
      if (eventsQueued.current) { eventsQueued.current = false; void loadEvents(); }
    }
  }

  useEffect(() => {
    refresh().catch((error) => setMessage(error.message));
    loadEvents().catch(() => undefined);
    let socket: WebSocket | null = null;
    let reconnectTimer = 0;
    let stopped = false;
    const connect = () => {
      if (stopped) return;
      socket = new WebSocket(viewerWebsocketUrl(viewerCode));
      socket.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        if (payload.type === "room.updated" || payload.type === "room.event") { refresh().catch(() => undefined); loadEvents().catch(() => undefined); }
      };
      socket.onclose = () => { if (!stopped) reconnectTimer = window.setTimeout(connect, 1500); };
    };
    connect();
    const refreshTimer = window.setInterval(() => { refresh().catch(() => undefined); loadEvents().catch(() => undefined); }, 10000);
    return () => {
      window.clearInterval(refreshTimer);
      stopped = true;
      window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [viewerCode]);

  if (!state) return <main className="main"><p className="muted">{message || "Loading viewer room..."}</p></main>;

  return <div className="page-shell"><header className="topbar"><h1>🏝️ {state.label}</h1><div className="topbar-actions"><span className={"tag " + state.game_status}>{statusLabel(state.game_status)}</span><Link className="button small" href="/">Dashboard</Link></div></header><main className="main">
    <p className="muted">View-only room · {state.sleeping ? "Sleeping" : "Active"}</p>
    <section className="panel" style={{ marginBottom: 14 }}><div className="card-stats"><div><strong>{state.totals.checks_done}/{state.totals.checks_total}</strong>Checks</div><div><strong>{state.totals.completed}/{state.slots.length}</strong>Completed</div><div><strong>{state.totals.deaths}</strong>Deaths</div></div></section>
    <section className="player-grid">{state.slots.map((slot) => <article className="player-card" key={slot.id}><div className="player-title"><div className="player-name"><strong>{slot.game || "Unknown game"}</strong> <span>({slot.slot_name})</span></div><strong>{slot.total_deaths}</strong></div><div className="box-grid"><div className="box"><h3>Checks</h3><div className="box-content"><div className="progress"><div style={{ width: slot.checks_pct + "%" }} /><span>{slot.checks_pct.toFixed(2)}% done</span></div><span>{slot.checks_done}/{slot.checks_total} collected</span></div></div><div className="box"><h3>Hints</h3><div className="box-content"><span>{slot.hints.filter((hint) => Boolean(hint.found)).length}/{slot.hints.length} found</span></div></div></div><ViewerHints slot={slot} /></article>)}</section>
    <ActivityFeed events={events} />
  </main></div>;
}
