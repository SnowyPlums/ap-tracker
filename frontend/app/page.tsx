"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, Room, User } from "../lib/api";

function statusLabel(status: string) {
  return status === "completed" ? "Completed" : status === "canceled" ? "Cancelled" : "In progress";
}

export default function Dashboard() {
  const [user, setUser] = useState<User | null>(null);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [auth, setAuth] = useState({ username: "", password: "" });
  const [create, setCreate] = useState({ label: "", host: "archipelago.gg", port: "" });
  const [invite, setInvite] = useState("");
  const [message, setMessage] = useState("");
  const [visibleConnections, setVisibleConnections] = useState<Set<string>>(new Set());

  async function load() {
    try {
      const current = await api<User | null>("/api/v1/auth/me");
      setUser(current);
    } catch {
      setUser(null);
    }
    setRooms(await api<Room[]>("/api/v1/rooms"));
  }
  useEffect(() => { load().catch((error) => setMessage(error.message)); }, []);

  const filteredRooms = useMemo(() => rooms.filter((room) => {
    const query = search.toLowerCase();
    const matchesSearch = room.label.toLowerCase().includes(query) ||
      room.player_names.some((name) => name.toLowerCase().includes(query));
    return matchesSearch && (status === "all" || room.game_status === status);
  }), [rooms, search, status]);

  async function submitAuth(event: FormEvent) {
    event.preventDefault();
    try {
      const current = await api<User>("/api/v1/auth/" + authMode, { method: "POST", body: JSON.stringify(auth) });
      setUser(current); setAuth({ username: "", password: "" }); setMessage("Signed in.");
      setRooms(await api<Room[]>("/api/v1/rooms"));
    } catch (error) { setMessage((error as Error).message); }
  }
  async function createRoom(event: FormEvent) {
    event.preventDefault();
    try {
      await api<Room>("/api/v1/rooms", { method: "POST", body: JSON.stringify({ ...create, port: Number(create.port) }) });
      setCreate({ label: "", host: "archipelago.gg", port: "" }); await load();
    } catch (error) { setMessage((error as Error).message); }
  }
  async function joinRoom(event: FormEvent) {
    event.preventDefault();
    try {
      await api<Room>("/api/v1/rooms/join", { method: "POST", body: JSON.stringify({ invite_code: invite }) });
      setInvite(""); await load();
    } catch (error) { setMessage((error as Error).message); }
  }
  async function logout() {
    await api<void>("/api/v1/auth/logout", { method: "POST" }); setUser(null); setRooms([]);
  }
  async function deleteRoom(room: Room) {
    if (!confirm(`Delete "${room.label}" immediately? This permanently removes the room and its data.`)) return;
    try {
      await api<void>("/api/v1/rooms/" + room.room_key, { method: "DELETE" });
      setRooms((current) => current.filter((item) => item.room_key !== room.room_key));
      setMessage("Room deleted.");
    } catch (error) { setMessage((error as Error).message); }
  }

  return <div className="page-shell">
    <header className="topbar"><h1>🏝️ Archipelago Tracker</h1><div className="topbar-actions">
      {user ? <><span className="muted">{user.username}{user.role === "admin" ? " · admin" : ""}</span><button className="button small" onClick={logout}>Log out</button></>
        : <span className="muted">Dashboard view</span>}
    </div></header>
    <main className="main">
      {message && <p className="muted">{message}</p>}
      {!user && <section className="panel auth-panel"><h2>{authMode === "login" ? "Log in to manage rooms" : "Create an account"}</h2>
        <p className="muted">You can view the dashboard without an account. An account is required to create or join rooms.</p>
        <form className="form-stack" onSubmit={submitAuth}>
          <input className="input" placeholder="Username" value={auth.username} onChange={(e) => setAuth({ ...auth, username: e.target.value })} />
          <input className="input" type="password" placeholder="Password (4+ characters)" value={auth.password} onChange={(e) => setAuth({ ...auth, password: e.target.value })} />
          <button className="button primary">{authMode === "login" ? "Log in" : "Create account"}</button>
        </form>
        <button className="button small" onClick={() => setAuthMode(authMode === "login" ? "register" : "login")}>
          {authMode === "login" ? "Need an account?" : "Already have an account?"}
        </button>
      </section>}
      {user && <div className="dashboard-actions">
        <section className="panel"><h2>Create room</h2><form className="form-row" onSubmit={createRoom}>
          <div className="field"><label>Room name</label><input className="input" required value={create.label} onChange={(e) => setCreate({ ...create, label: e.target.value })} /></div>
          <div className="field"><label>Host</label><input className="input" required value={create.host} onChange={(e) => setCreate({ ...create, host: e.target.value })} /></div>
          <div className="field"><label>Port</label><input className="input" required inputMode="numeric" pattern="[0-9]*" type="text" placeholder="44487" value={create.port} onChange={(e) => setCreate({ ...create, port: e.target.value.replace(/\D/g, "") })} /></div>
          <button className="button primary">Create</button>
        </form></section>
        <section className="panel"><h2>Join room</h2><form className="form-row" onSubmit={joinRoom}>
          <div className="field"><label>Player invite code</label><input className="input" required value={invite} onChange={(e) => setInvite(e.target.value)} /></div>
          <button className="button primary">Join</button>
        </form></section>
      </div>}
      <div className="filters"><input className="input" placeholder="Search games" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="select" value={status} onChange={(e) => setStatus(e.target.value)}><option value="all">All statuses</option><option value="in_progress">In progress</option><option value="completed">Completed</option><option value="canceled">Cancelled</option></select>
      </div>
      <section className="cards">{filteredRooms.map((room) => <article className="card" key={room.room_key}>
        <Link className="card-link" href={"/rooms/" + room.room_key}>
          <div className="card-head"><h2>{room.label}</h2><span className={"tag " + room.game_status}>{statusLabel(room.game_status)}</span></div>
        </Link>
        <p className="muted"><button className="connection-toggle" type="button" title={visibleConnections.has(room.room_key) ? "Click to hide connection" : "Click to show connection"} aria-label={visibleConnections.has(room.room_key) ? "Hide room connection" : "Show room connection"} onClick={() => setVisibleConnections((current) => { const next = new Set(current); if (next.has(room.room_key)) next.delete(room.room_key); else next.add(room.room_key); return next; })}>{visibleConnections.has(room.room_key) ? room.host + ":" + room.port : "Connection hidden"}</button></p>
        <Link className="card-link" href={"/rooms/" + room.room_key}>
          <div className="progress dashboard-progress"><div style={{ width: Math.min(room.checks_pct, 100) + "%" }} /><span>{room.checks_pct.toFixed(2)}% done</span></div>
          <div className="card-stats"><div><strong>{room.players}</strong>Players</div><div><strong>{room.checks_total}</strong>Total checks</div><div><strong>{room.checks_done}</strong>Done</div></div>
        </Link>
        {user?.role === "admin" && <button className="button small danger room-delete" type="button" onClick={() => deleteRoom(room)}>Delete room</button>}
      </article>)}</section>
      {!filteredRooms.length && <p className="muted">No games match the current filters.</p>}
    </main>
  </div>;
}
