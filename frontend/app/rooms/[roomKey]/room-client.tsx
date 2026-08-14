"use client";

import Link from "next/link";
import { FormEvent, Fragment, useEffect, useState } from "react";
import { closestCenter, DndContext, DragEndEvent, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { SortableContext, arrayMove, horizontalListSortingStrategy, useSortable } from "@dnd-kit/sortable";
import { Event, Preferences, RoomState, Slot, api, websocketUrl } from "../../../lib/api";

const BOXES = [
  { key: "checks", label: "Checks" },
  { key: "hints", label: "Hints" },
  { key: "deaths", label: "Deaths" },
  { key: "completion", label: "Completion" },
  { key: "actions", label: "Actions" },
];

const DEFAULT_PREFERENCES: Preferences = {
  order: BOXES.map((box) => box.key),
  visible: ["checks", "hints"],
};

function boxDefinition(key: string) {
  return BOXES.find((box) => box.key === key) || BOXES[0];
}

function connectionIcon(status: string) {
  if (status === "connected") return <span className="status-connected" title="Connected">●</span>;
  if (status === "error") return <span className="status-error" title="Connection error">●</span>;
  if (status === "sleeping") return <span className="status-sleeping" title="Sleeping">○</span>;
  return <span className="status-connecting" title={status}>○</span>;
}

function statusLabel(status: string) {
  return status === "completed" ? "Completed" : status === "canceled" ? "Canceled" : "In progress";
}

function CompactProgress({ value }: { value: number }) {
  return <div className="compact-progress-row"><span className="percent-bubble">{value.toFixed(2)}%</span><div className="progress compact-progress"><div style={{ width: Math.min(value, 100) + "%" }} /></div></div>;
}

function SlotBox({ slot, box, itemNames, onAction, locationHref }: {
  slot: Slot;
  box: string;
  itemNames: string[];
  onAction: (path: string, body?: unknown) => Promise<void>;
  locationHref: string;
}) {
  const [hint, setHint] = useState("");
  const [hintMessage, setHintMessage] = useState("");
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const suggestions = itemNames.filter((name) => !hint.trim() || name.toLowerCase().includes(hint.trim().toLowerCase())).slice(0, 8);

  async function sendHint() {
    if (!hint.trim()) {
      setHintMessage("");
      return;
    }
    try {
      await onAction("/hint", { item_name: hint });
      setHint("");
      setHintMessage("Hint request sent.");
    } catch (error) {
      setHintMessage((error as Error).message);
    }
  }

  if (box === "checks") return <div className="box"><h3>Checks</h3><div className="box-content">
    <div className="progress"><div style={{ width: Math.min(slot.checks_pct, 100) + "%" }} /><span>{slot.checks_pct.toFixed(2)}% done</span></div>
    <span>{slot.checks_done}/{slot.checks_total} · {slot.remaining_checks} left</span>
    <div className="box-actions"><Link className="button small" href={locationHref}>Locations</Link></div>
  </div></div>;

  if (box === "hints") return <div className="box"><h3>Hints</h3><div className="box-content">
    <div className="hint-autocomplete"><input className="input hint-input" autoComplete="off" placeholder="Search for an item" value={hint} onFocus={() => setSuggestionsOpen(true)} onBlur={() => setTimeout(() => setSuggestionsOpen(false), 100)} onChange={(event) => { setHint(event.target.value); setSuggestionsOpen(true); }} />{suggestionsOpen && suggestions.length > 0 && <div className="hint-suggestions" role="listbox">{suggestions.map((name) => <button className="hint-suggestion" type="button" role="option" key={name} onMouseDown={(event) => event.preventDefault()} onClick={() => { setHint(name); setSuggestionsOpen(false); }}>{name}</button>)}</div>}</div>
    <div className="box-actions"><button className="button small" onClick={sendHint}>Hint</button><span className="muted">{slot.hints.filter((item) => Boolean(item.found)).length}/{slot.hints.length} found</span></div>
    {hintMessage && <span className="muted">{hintMessage}</span>}
  </div></div>;

  if (box === "deaths") return <div className="box"><h3>Deaths</h3><div className="death-total">{slot.total_deaths}</div><div className="box-actions">
    <button className="button small" onClick={() => onAction("/death")}>+1</button>
    {slot.total_deaths > 0 && <button className="button small" onClick={() => onAction("/death/undo")}>-1</button>}
  </div></div>;

  if (box === "completion") return <div className="box"><h3>Completion</h3><div className="box-content">
    <span className={"tag " + (slot.completed ? "completed" : "")}>{slot.completed ? "Completed" : "In progress"}</span>
    <button className="button small" onClick={() => onAction("/complete", { value: !slot.completed })}>{slot.completed ? "Mark in progress" : "Mark done"}</button>
  </div></div>;

  return <div className="box"><h3>Actions</h3><div className="box-actions">
    <button className="button small" onClick={() => onAction("/reconnect")}>Reconnect</button>
    <button className="button small danger" onClick={() => onAction("/remove")}>Remove</button>
  </div></div>;
}

function HintInformation({ slot }: { slot: Slot }) {
  const [open, setOpen] = useState(false);
  if (!slot.hints.length) return null;
  const found = slot.hints.filter((hint) => Boolean(hint.found)).length;
  return <div className="hint-information"><button className="button small" onClick={() => setOpen(!open)}>{open ? "Hide hints" : "Show hints"} ({found}/{slot.hints.length})</button>{open && <div className="hint-list">{slot.hints.map((hint, index) =>
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
  )}</div>}</div>;
}

function SortablePreviewBox({ box, enabled, onToggle }: { box: typeof BOXES[number]; enabled: boolean; onToggle: () => void }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: box.key });
  const style = { transform: transform ? `translate3d(${transform.x}px, ${transform.y}px, 0)` : undefined, transition };
  return <div ref={setNodeRef} style={style} className={"preference-preview " + (!enabled ? "disabled" : "")} onClick={onToggle} {...attributes}>
    <div className="preview-heading"><strong>{box.label}</strong><button className="drag-handle" type="button" {...listeners} onClick={(event) => event.stopPropagation()} aria-label={"Drag " + box.label}>⋮⋮</button></div>
    <div className="preview-content"><span className="preview-line" /><span className="preview-line short" /><span className="preview-button">{box.key === "checks" ? "84.00%" : box.key === "hints" ? "1/2 found" : "Example"}</span></div>
  </div>;
}

function PlayerBoxes({ order, slot, itemNames, onAction, locationHref }: {
  order: string[]; slot: Slot; itemNames: string[]; onAction: (path: string, body?: unknown) => Promise<void>; locationHref: string;
}) {
  return <div className="box-grid">{order.map((box) => <SlotBox key={box} slot={slot} box={box} itemNames={itemNames} onAction={onAction} locationHref={locationHref} />)}</div>;
}

export default function RoomClient({ roomKey }: { roomKey: string }) {
  const [state, setState] = useState<RoomState | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [preferences, setPreferences] = useState<Preferences>(DEFAULT_PREFERENCES);
  const [showPreferences, setShowPreferences] = useState(false);
  const [expandedSlots, setExpandedSlots] = useState<Set<number>>(new Set());
  const [expandedLoaded, setExpandedLoaded] = useState(false);
  const [showInviteCode, setShowInviteCode] = useState(false);
  const [showConnection, setShowConnection] = useState(false);
  const [addSlot, setAddSlot] = useState({ slot_name: "", password: "", deathlink_listener: false });
  const [message, setMessage] = useState("");
  const [itemNames, setItemNames] = useState<Record<number, string[]>>({});

  async function refresh() {
    const next = await api<RoomState>("/api/v1/rooms/" + roomKey + "/state");
    setState(next);
    await Promise.all(next.slots.map(async (slot) => {
      try {
        const names = await api<string[]>("/api/v1/rooms/" + roomKey + "/slots/" + slot.id + "/item-names");
        setItemNames((current) => ({ ...current, [slot.id]: names }));
      } catch { return; }
    }));
  }

  async function loadEvents() { setEvents(await api<Event[]>("/api/v1/rooms/" + roomKey + "/events")); }

  useEffect(() => {
    refresh().catch((error) => setMessage((error as Error).message));
    loadEvents().catch(() => undefined);
    api<Preferences>("/api/v1/preferences/player-boxes").then((next) => setPreferences({ ...DEFAULT_PREFERENCES, ...next })).catch(() => undefined);
    const socket = new WebSocket(websocketUrl(roomKey));
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.type === "room.updated" || payload.type === "room.event") { refresh().catch(() => undefined); loadEvents().catch(() => undefined); }
    };
    socket.onerror = () => setMessage("Live updates unavailable; actions still refresh normally.");
    return () => socket.close();
  }, [roomKey]);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("ap-tracker-expanded-" + roomKey);
      if (saved) setExpandedSlots(new Set(JSON.parse(saved).map((id: number) => Number(id))));
    } catch { setExpandedSlots(new Set()); }
    setExpandedLoaded(true);
  }, [roomKey]);

  useEffect(() => {
    if (expandedLoaded) window.localStorage.setItem("ap-tracker-expanded-" + roomKey, JSON.stringify([...expandedSlots]));
  }, [expandedLoaded, expandedSlots, roomKey]);

  async function mutate(path: string, method = "POST", body?: unknown) {
    await api<unknown>("/api/v1/rooms/" + roomKey + path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
    await refresh();
    await loadEvents();
  }

  async function changeRoomStatus(nextStatus: "in_progress" | "completed" | "canceled") { try { await mutate("/status", "POST", { status: nextStatus }); } catch (error) { setMessage((error as Error).message); } }
  async function savePreferences(next: Preferences) {
    setPreferences(next);
    try { await api<Preferences>("/api/v1/preferences/player-boxes", { method: "PUT", body: JSON.stringify(next) }); } catch (error) { setMessage((error as Error).message); }
  }
  async function addPlayer(event: FormEvent) {
    event.preventDefault();
    try { await mutate("/slots", "POST", { ...addSlot, password: addSlot.password || null }); setAddSlot({ slot_name: "", password: "", deathlink_listener: false }); } catch (error) { setMessage((error as Error).message); }
  }
  async function removePlayer(slotId: number) { if (confirm("Remove this player?")) await mutate("/slots/" + slotId, "DELETE"); }
  async function doSlotAction(slotId: number, path: string, body?: unknown) {
    try { if (path === "/reconnect") await mutate("/reconnect"); else if (path === "/remove") await removePlayer(slotId); else await mutate("/slots/" + slotId + path, "POST", body); } catch (error) { setMessage((error as Error).message); }
  }
  function toggleSlot(slotId: number) { setExpandedSlots((current) => { const next = new Set(current); next.has(slotId) ? next.delete(slotId) : next.add(slotId); return next; }); }

  if (!state) return <main className="main"><Link className="button small" href="/">← All games</Link><p className="muted">{message || "Loading room..."}</p></main>;
  const nextRoomStatus = state.game_status === "canceled" ? "in_progress" : state.game_status === "completed" ? "in_progress" : "completed";

  return <div className="page-shell">
    <header className="topbar"><h1>🏝️ Archipelago Tracker</h1><div className="topbar-actions"><button className="button small" onClick={() => setShowPreferences(!showPreferences)}>Customize player boxes</button></div></header>
    <main className="main">
      <div className="room-head"><div><Link className="button small back-button" href="/">← All games</Link><h2>{state.label}</h2><div className="room-meta masked-connection" role="button" tabIndex={0} onClick={() => setShowConnection(!showConnection)}>{showConnection ? state.host + ":" + state.port : "Connection hidden"} <CopyButton value={state.host + ":" + state.port} /> · {state.sleeping ? "Sleeping" : "Active"} · <span className={"tag " + state.game_status}>{statusLabel(state.game_status)}</span></div></div><div className="room-actions">{state.game_status === "canceled" ? <button className="button small" onClick={() => changeRoomStatus("in_progress")}>Uncancel room</button> : <><button className="button small" onClick={() => changeRoomStatus(nextRoomStatus)}>{state.game_status === "completed" ? "Mark in progress" : "Mark completed"}</button><button className="button small danger" onClick={() => changeRoomStatus("canceled")}>Cancel room</button></>}</div></div>
      {showPreferences && <PreferencesEditor preferences={preferences} onSave={savePreferences} />}
      <div className="room-overview"><div className="panel quick-glance"><strong>{state.totals.completed} completed games · {state.totals.deaths} total deaths</strong><div className="quick-glance-progress-grid"><span>{state.totals.checks_done}/{state.totals.checks_total} total checks</span><CompactProgress value={state.totals.checks_pct} /><span className="checks-count-placeholder" aria-hidden="true" /> <div className="quick-glance-divider" />{state.slots.map((slot) => <Fragment key={slot.id}><span>{slot.slot_name} · {slot.game || "Connecting..."}</span><CompactProgress value={slot.checks_pct} /><span className="checks-count-bubble">{slot.checks_done}/{slot.checks_total}</span></Fragment>)}</div></div><div className="panel access-panel"><div><strong>Player invite code</strong><br /><code>{showInviteCode ? state.invite_code : "••••••••••••"}</code></div><button className="button small" onClick={() => setShowInviteCode(!showInviteCode)}>{showInviteCode ? "Hide" : "Show"}</button><CopyButton value={state.invite_code} /><div><strong>View-only link</strong><br /><code>{typeof window === "undefined" ? "" : window.location.origin + "/view/" + state.viewer_code}</code></div><CopyButton value={typeof window === "undefined" ? "" : window.location.origin + "/view/" + state.viewer_code} /></div></div>
      <section className="player-grid">{state.slots.map((slot) => { const expanded = expandedSlots.has(slot.id); const visibleBoxes = expanded ? preferences.order : preferences.order.filter((key) => preferences.visible.includes(key)); return <article className="player-card" key={slot.id}><div className="player-title"><button className="button expand" onClick={() => toggleSlot(slot.id)}>{expanded ? "−" : "+"}</button><span className="status-icon">{connectionIcon(slot.status)}</span><div className="player-name"><strong>{slot.game || "Connecting..."}</strong> <span>({slot.slot_name})</span></div><strong>{slot.total_deaths}</strong></div><PlayerBoxes order={visibleBoxes} slot={slot} itemNames={itemNames[slot.id] || []} onAction={(path, body) => doSlotAction(slot.id, path, body)} locationHref={"/rooms/" + roomKey + "/slots/" + slot.id + "/locations"} /><HintInformation slot={slot} /></article>; })}</section>
      <section className="panel" style={{ marginTop: 16 }}><h3>Activity feed</h3><div className="event-log">{events.map((event) => <div className="event-row" key={event.id}><span className="event-time">{new Date(event.ts).toLocaleTimeString()}</span><span dangerouslySetInnerHTML={{ __html: event.html || event.text }} /></div>)}</div></section>
      <section className="panel" style={{ marginTop: 16 }}><h3>Add player slot</h3><form className="form-row" onSubmit={addPlayer}><div className="field"><label>Slot name</label><input className="input" required value={addSlot.slot_name} onChange={(event) => setAddSlot({ ...addSlot, slot_name: event.target.value })} /></div><div className="field"><label>Room password</label><input className="input" type="password" value={addSlot.password} onChange={(event) => setAddSlot({ ...addSlot, password: event.target.value })} /></div><label className="deathlink-option"><input type="checkbox" checked={addSlot.deathlink_listener} onChange={(event) => setAddSlot({ ...addSlot, deathlink_listener: event.target.checked })} /> Enable DeathLink tracking</label><button className="button primary">Add player</button></form></section>
      {message && <p className="error">{message}</p>}
    </main>
  </div>;
}

function CopyButton({ value }: { value: string }) { const [copied, setCopied] = useState(false); return <button className="button small" onClick={(event) => { event.stopPropagation(); if (!value) return; navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1200); }}>{copied ? "Copied" : "Copy"}</button>; }

function PreferencesEditor({ preferences, onSave }: { preferences: Preferences; onSave: (next: Preferences) => Promise<void> }) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));
  function handleDragEnd(event: DragEndEvent) { if (!event.over || event.active.id === event.over.id) return; const from = preferences.order.indexOf(String(event.active.id)); const to = preferences.order.indexOf(String(event.over.id)); if (from >= 0 && to >= 0) onSave({ ...preferences, order: arrayMove(preferences.order, from, to) }).catch(() => undefined); }
  function toggle(key: string) { const visible = preferences.visible.includes(key) ? preferences.visible.filter((item) => item !== key) : [...preferences.visible, key]; onSave({ ...preferences, visible }).catch(() => undefined); }
  return <div className="preferences"><strong>Player boxes</strong><p className="muted">Click a box to show or hide it. Drag the handle to set the global order. Saving a global change resets individual player orders.</p><DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}><SortableContext items={preferences.order} strategy={horizontalListSortingStrategy}><div className="preference-preview-grid">{preferences.order.map((key) => <SortablePreviewBox key={key} box={boxDefinition(key)} enabled={preferences.visible.includes(key)} onToggle={() => toggle(key)} />)}</div></SortableContext></DndContext></div>;
}
