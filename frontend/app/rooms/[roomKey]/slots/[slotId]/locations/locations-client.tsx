"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { RoomState, Slot, api } from "../../../../../../lib/api";

export default function LocationsClient({ roomKey, slotId }: { roomKey: string; slotId: number }) {
  const [state, setState] = useState<RoomState | null>(null);
  const [locationRows, setLocationRows] = useState<Array<{ id: number; name: string; checked: boolean }>>([]);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<"default" | "missing" | "collected">("default");
  const [message, setMessage] = useState("");

  useEffect(() => {
    Promise.all([
      api<RoomState>("/api/v1/rooms/" + roomKey + "/state"),
      api<Array<{ id: number; name: string; checked: boolean }>>("/api/v1/rooms/" + roomKey + "/slots/" + slotId + "/locations"),
    ])
      .then(([nextState, nextLocations]) => { setState(nextState); setLocationRows(nextLocations); })
      .catch((error) => setMessage(error.message));
  }, [roomKey, slotId]);

  const slot: Slot | undefined = state?.slots.find((item) => item.id === slotId);
  const visibleLocations = useMemo(() => {
    const filtered = locationRows
      .filter((location) => location.name.toLowerCase().includes(search.toLowerCase()))
      .filter((location) => sort === "default" || (sort === "collected" ? location.checked : !location.checked));
    return [...filtered].sort((left, right) => left.name.localeCompare(right.name));
  }, [locationRows, search, sort]);

  if (!state || !slot) return <main className="main"><Link className="button small back-button" href={"/rooms/" + roomKey}>← Room</Link><p className="muted">{message || "Loading locations..."}</p></main>;

  return <div className="page-shell">
    <header className="topbar"><h1>🏝️ Archipelago Tracker</h1></header>
    <main className="main">
      <section className="panel"><Link className="button small back-button" href={"/rooms/" + roomKey}>← Room</Link><h2>{slot.game || "Game"} <span className="muted">({slot.slot_name})</span></h2><div className="form-row"><input className="input" placeholder="Search locations" value={search} onChange={(event) => setSearch(event.target.value)} /><select className="select" value={sort} onChange={(event) => setSort(event.target.value as typeof sort)}><option value="default">All locations</option><option value="missing">Not collected</option><option value="collected">Collected</option></select><span className="muted">{slot.checks_done}/{slot.checks_total} collected</span></div></section>
      <section className="panel" style={{ marginTop: 14 }}><div className="location-list">{visibleLocations.map((location) => <div className={"location-row " + (location.checked ? "taken" : "missing")} key={location.id}><span className="location-icon" aria-label={location.checked ? "Collected" : "Not collected"}>{location.checked ? "✓" : "✕"}</span><span>{location.name}</span></div>)}</div>{!visibleLocations.length && <p className="muted">No matching locations.</p>}</section>
    </main>
  </div>;
}
