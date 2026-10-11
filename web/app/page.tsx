"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE as apiBase, apiFetch } from "./api";
import { useDialogFocus } from "./use-dialog-focus";
import { ConnectionScreen } from "./connection-screen";
import { CombatAwareness } from "./combat-awareness";

type EngineEvent = {
  event_id: string;
  turn: number;
  type: string;
  phase: string;
  message: string;
  actor: string | null;
  data: Record<string, number>;
};

type Actor = {
  name: string;
  sex?: string;
  race?: string;
  cls?: string;
  hp: number;
  max_hp: number;
  ac: number;
  damage?: string;
  trust?: number;
  mood?: string;
  tactic?: string;
  memories?: string[];
  mana?: number;
  max_mana?: number;
  xp?: number;
  level?: number;
  conditions?: Record<string, number>;
};

type Item = {
  id: string;
  name: string;
  kind: string;
  slot?: string;
  effect?: { type?: string; dice?: string; bonus?: number; damage?: string; attack_bonus?: number } | null;
  quantity?: number;
  sell_value?: number;
  buy_value?: number;
  tier?: number;
  description?: string;
};

type AvailableAction = {
  id: string;
  label: string;
  spell?: string;
  target?: string;
  mana_cost?: number;
  requires?: string[];
  options?: string[];
  informational?: boolean;
  description?: string;
  disabled?: boolean;
  disabled_reason?: string | null;
};

type Challenge = {
  title: string;
  prompt: string;
  required: boolean;
  options: Array<{ id: string; label: string; description?: string; available: boolean; reason?: string | null }>;
};

type SpellbookEntry = {
  name: string;
  category: string;
  mana_cost: number;
  contexts: string[];
  target_type: string;
  description: string;
  targets: Array<{ id: string; label: string }>;
  available: boolean;
  reason?: string | null;
};

type EngineState = {
  schema_version: number;
  campaign: { id: string; name: string; description: string; room_order: string[] };
  phase: "exploration" | "combat" | "victory" | "defeat";
  turn: number;
  room: {
    id: string;
    name: string;
    description: string;
    recommended_level: number;
    max_item_tier: number;
    kind: string;
    exits: Record<string, string>;
  };
  player: Actor & { gold: number; learned_spells: string[] };
  companions: Actor[];
  enemies: Array<Actor & { id: number }>;
  inventory: Item[];
  equipment: Record<string, Item | null>;
  flags: Record<string, unknown>;
  available_actions: AvailableAction[];
  spellbook: SpellbookEntry[];
  challenge?: Challenge | null;
  journey?: {
    objective: { title: string; description: string };
    journal: Array<{ id: string; text: string }>;
    locations: Array<{ id: string; name: string; statuses: string[] }>;
  };
  camp?: {
    available: boolean;
    reason: string | null;
    recovery_turns: number;
    recovery: Array<{ name: string; hp: number; mana: number }>;
  };
  game_over: boolean;
  save: { visited: string[] };
};

type ApiResponse = {
  game_id: string;
  accepted?: boolean;
  events?: EngineEvent[];
  state: EngineState;
  error?: string | null;
};

type Catalog = {
  campaigns: Array<{
    id: string;
    name: string;
    description: string;
    recommended_level: number;
    max_item_tier: number;
    companions: Array<{
      id: string;
      name: string;
      hp: number;
      ac: number;
      attack_bonus: number;
      damage: string;
      mana: number;
      spells: string[];
      personality: string;
      default_tactic: string;
      role: string;
      description: string;
      best_for: string;
    }>;
  }>;
  classes: Array<{ name: string; role: string; description: string; base_hp: number; base_ac: number; spells: string[] }>;
  races: Array<{ name: string; description: string; stat_mods: Record<string, number>; abilities: string[] }>;
};

type Setup = {
  name: string;
  sex: "Male" | "Female";
  campaign_id: string;
  player_class: string;
  race: string;
  companion_id: string;
  stats: Record<string, number>;
  adventurer_game_id?: string;
  adventurer_id?: string;
};

type SavedAdventurer = {
  adventurer_id: string;
  source_game_id: string;
  name: string;
  sex: string;
  race: string;
  class: string;
  level: number;
  xp: number;
  gold: number;
  stats: Record<string, number>;
  inventory_count: number;
  inventory_slots: number;
  equipment_count: number;
  last_campaign_id: string;
  updated_at: string;
};

type ManagedAdventurer = {
  adventurer_id: string;
  player: Actor & { gold: number; learned_spells: string[]; stats: Record<string, number> };
  inventory: Item[];
  equipment: Record<string, Item | null>;
  companions: Actor[];
  inventory_limit: number;
  inventory_slots: number;
  progression: {
    attribute_cap: number;
    unspent_attribute_points: number;
    unspent_class_upgrades: number;
    current_level_xp: number;
    next_level_xp: number | null;
    upgrade_options: Array<{ id: string; name: string; description: string }>;
    chosen_upgrades: string[];
  };
  shop: { healing_potion_price: number; bundle_quantity: number; stack_limit: number; items: Item[] };
};

type SavedAdventure = {
  game_id: string;
  campaign_id: string;
  character_name: string;
  sex: string;
  room_id: string;
  turn: number;
  status: "in_progress" | "complete" | "defeat";
  race: string;
  class: string;
  level: number;
  hp: number;
  max_hp: number;
  companion_name?: string;
  updated_at: string;
};

type ShopTab = "weapons" | "armor" | "consumables" | "sell";
type PendingPurchase = {
  label: string;
  price: number;
  command: "buy_item" | "buy_potions";
  options: { item?: string; quantity?: number };
};

const DEFAULT_SETUP: Setup = {
  name: "Rowan",
  sex: "Male",
  campaign_id: "ruined_watchtower",
  player_class: "Fighter",
  race: "Human",
  companion_id: "mara",
  stats: { STR: 2, DEX: 2, CON: 2, INT: 2, WIS: 2, CHA: 2 },
};

const ROOM_KICKERS: Record<string, string> = {
  courtyard: "The outer watch",
  cellar: "Below the tower",
  barracks: "The old garrison",
  spire: "Open to the storm",
};

const ATTRIBUTE_HELP: Record<string, string> = {
  STR: "Strength checks",
  DEX: "Agility and lock checks",
  CON: "Health · +1 max HP",
  INT: "Knowledge · Wizard mana",
  WIS: "Awareness · Cleric mana",
  CHA: "Persuasion checks",
};

function meter(value: number, max: number) {
  return `${Math.max(0, Math.min(100, (value / Math.max(1, max)) * 100))}%`;
}

function itemStats(item: Item | null | undefined) {
  if (!item?.effect) return item?.kind === "quest" ? "Campaign item" : "No combat effect";
  if (item.effect.type === "ac") {
    const stats = [];
    if (item.effect.bonus) stats.push(`+${item.effect.bonus} Armor`);
    if (item.effect.attack_bonus) stats.push(`+${item.effect.attack_bonus} attack`);
    return stats.join(" · ") || "No combat bonus";
  }
  if (item.effect.type === "weapon") return `${item.effect.damage || "—"} damage${item.effect.attack_bonus ? ` · +${item.effect.attack_bonus} attack` : ""}`;
  if (item.effect.type === "heal") return `Heals ${item.effect.dice || "—"}`;
  return "No combat effect";
}

function itemComparison(item: Item, equipped: Item | null | undefined) {
  if (!item.slot) return "";
  if (!equipped) return `Empty ${item.slot} slot`;
  if (item.effect?.type === "ac") {
    const armorDelta = (item.effect.bonus || 0) - (equipped.effect?.bonus || 0);
    const attackDelta = (item.effect.attack_bonus || 0) - (equipped.effect?.attack_bonus || 0);
    if (!armorDelta && !attackDelta) return `Matches ${equipped.name}`;
    const changes = [];
    if (armorDelta) changes.push(`${armorDelta > 0 ? "+" : ""}${armorDelta} Armor`);
    if (attackDelta) changes.push(`${attackDelta > 0 ? "+" : ""}${attackDelta} attack`);
    return `${changes.join(" · ")} vs ${equipped.name}`;
  }
  return `Compare with ${equipped.name}`;
}

function eventIcon(type: string) {
  if (type.includes("condition")) return "☠";
  if (type.includes("damage")) return "⚔";
  if (type.includes("roll")) return "20";
  if (type.includes("loot") || type.includes("progression")) return "✦";
  if (type.includes("room")) return "→";
  if (type.includes("combat")) return "!";
  return "•";
}

function eventClass(type: string) {
  if (type.includes("condition")) return "damage";
  if (type.includes("damage")) return "damage";
  if (type.includes("roll")) return "roll";
  if (type.includes("loot") || type.includes("progression")) return "loot";
  if (type.includes("room")) return "move";
  return "story";
}

export default function Home() {
  const [gameId, setGameId] = useState<string | null>(null);
  const [game, setGame] = useState<EngineState | null>(null);
  const [events, setEvents] = useState<EngineEvent[]>([]);
  const [recentEvents, setRecentEvents] = useState<EngineEvent[]>([]);
  const [sound, setSound] = useState(false);
  const [voice, setVoice] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [showSetup, setShowSetup] = useState(false);
  const [setup, setSetup] = useState<Setup>(DEFAULT_SETUP);
  const [savedAdventurers, setSavedAdventurers] = useState<SavedAdventurer[]>([]);
  const [savedAdventures, setSavedAdventures] = useState<SavedAdventure[]>([]);
  const [rosterAttempt, setRosterAttempt] = useState(0);
  const [rosterErrors, setRosterErrors] = useState<Partial<Record<"adventurers" | "games", string>>>({});
  const [managedAdventurer, setManagedAdventurer] = useState<ManagedAdventurer | null>(null);
  const [attributeDraft, setAttributeDraft] = useState<Record<string, number>>({});
  const [upgradeDraft, setUpgradeDraft] = useState("");
  const [shopOpen, setShopOpen] = useState(false);
  const [shopTab, setShopTab] = useState<ShopTab>("weapons");
  const [pendingPurchase, setPendingPurchase] = useState<PendingPurchase | null>(null);
  const [spellbookOpen, setSpellbookOpen] = useState(false);
  const [campOpen, setCampOpen] = useState(false);

  const [connectionAttempt, setConnectionAttempt] = useState(0);
  const [selecting, setSelecting] = useState(false);
  const selectionVersion = useRef(0);
  const mutationPending = useRef(false);
  const audioContext = useRef<AudioContext | null>(null);
  useEffect(() => () => {
    selectionVersion.current++;
    void audioContext.current?.close();
    window.speechSynthesis?.cancel();
  }, []);
  useDialogFocus(shopOpen || spellbookOpen || campOpen || Boolean(game && showSetup), () => {
    if (campOpen && mutationPending.current) return;
    setCampOpen(false);
    setShopOpen(false);
    setPendingPurchase(null);
    setSpellbookOpen(false);
    if (game) setShowSetup(false);
  });

  const playFeedback = useCallback((newEvents: EngineEvent[]) => {
    if (!newEvents.length) return;
    const latest = newEvents[newEvents.length - 1];
    if (voice && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(latest.message);
      utterance.rate = 0.92;
      utterance.pitch = 0.82;
      window.speechSynthesis.speak(utterance);
    }
    if (sound) {
      const AudioContextClass = window.AudioContext || (window as typeof window & { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      if (!AudioContextClass) return;
      const ctx = audioContext.current ?? new AudioContextClass();
      audioContext.current = ctx;
      void ctx.resume();
      const oscillator = ctx.createOscillator();
      const gain = ctx.createGain();
      oscillator.type = latest.type.includes("damage") ? "sawtooth" : "sine";
      oscillator.frequency.value = latest.type.includes("damage") ? 105 : latest.type.includes("loot") ? 540 : 250;
      gain.gain.setValueAtTime(0.055, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.18);
      oscillator.connect(gain).connect(ctx.destination);
      oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
      oscillator.start();
      oscillator.stop(ctx.currentTime + 0.18);
    }
  }, [sound, voice]);

  const startGame = useCallback(async (creation: Setup = DEFAULT_SETUP) => {
    if (mutationPending.current) return;
    mutationPending.current = true;
    selectionVersion.current++;
    setSelecting(false);
    const safeCreation = creation && typeof creation.name === "string"
      ? creation
      : DEFAULT_SETUP;
    setBusy(true);
    setError(null);
    try {
      const response = await apiFetch(`/api/games`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          campaign_id: safeCreation.campaign_id,
          name: safeCreation.name.trim() || "Adventurer",
          sex: safeCreation.sex,
          class: safeCreation.player_class,
          race: safeCreation.race,
          companion_id: safeCreation.companion_id,
          stats: safeCreation.stats,
          adventurer_game_id: safeCreation.adventurer_game_id,
          adventurer_id: safeCreation.adventurer_id,
        }),
      });
      const payload = await response.json() as ApiResponse;
      if (!response.ok) throw new Error(payload.error || "Could not create the game.");
      setGameId(payload.game_id);
      setGame(payload.state);
      setRecentEvents([]);
      setEvents([{
        event_id: "opening",
        turn: 0,
        type: "narrative",
        phase: "exploration",
        actor: null,
        data: {},
        message: payload.state.room.description,
      }]);
      setShowSetup(false);
      window.localStorage.setItem("solo-adventure-game-id", payload.game_id);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The game engine is unavailable.");
    } finally {
      mutationPending.current = false;
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function connect() {
      setBusy(true);
      try {
        const response = await apiFetch("/api/catalog");
        const payload = await response.json() as Catalog;
        if (!payload.campaigns?.length || !payload.classes?.length || !payload.races?.length) {
          throw new Error("Game engine catalog is incomplete. Retry the connection.");
        }
        if (!cancelled) { setCatalog(payload); setShowSetup(true); setError(null); }
      } catch (requestError) {
        if (!cancelled) setError(requestError instanceof Error ? requestError.message : "The game engine is unavailable.");
      } finally {
        if (!cancelled) setBusy(false);
      }
    }
    void connect();
    return () => { cancelled = true; };
  }, [connectionAttempt]);

  useEffect(() => {
    if (!showSetup || busy) return;
    let cancelled = false;
    async function refreshList(list: "adventurers" | "games") {
      try {
        const response = await apiFetch(`/api/${list}`);
        const payload = await response.json() as { adventurers?: SavedAdventurer[]; games?: SavedAdventure[] };
        // Check after JSON parsing too: a retry/exit/mutation invalidates this request.
        if (cancelled) return;
        if (list === "adventurers") setSavedAdventurers(payload.adventurers || []);
        else setSavedAdventures(payload.games || []);
        setRosterErrors((current) => ({ ...current, [list]: undefined }));
      } catch (requestError) {
        if (cancelled) return;
        // Preserve both previously loaded lists while exposing the failed one.
        setRosterErrors((current) => ({ ...current, [list]: requestError instanceof Error ? requestError.message : "The game engine is unavailable." }));
      }
    }
    void refreshList("adventurers");
    void refreshList("games");
    return () => { cancelled = true; };
  }, [showSetup, busy, rosterAttempt]);

  async function resumeAdventure(saved: SavedAdventure) {
    if (mutationPending.current) return;
    mutationPending.current = true;
    selectionVersion.current++;
    setSelecting(false);
    setBusy(true);
    setError(null);
    try {
      const response = await apiFetch(`/api/games/${saved.game_id}`);
      const payload = await response.json() as ApiResponse;
      if (!response.ok) throw new Error(payload.error || "That adventure could not be restored.");
      setGameId(saved.game_id);
      setGame(payload.state);
      setRecentEvents([]);
      setEvents([{
        event_id: `resume-${saved.game_id}`,
        turn: payload.state.turn,
        type: "narrative",
        phase: payload.state.phase,
        actor: null,
        data: {},
        message: `The adventure resumes in ${payload.state.room.name}.`,
      }]);
      setShowSetup(false);
      window.localStorage.setItem("solo-adventure-game-id", saved.game_id);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "That adventure could not be restored.");
    } finally {
      mutationPending.current = false;
      setBusy(false);
    }
  }

  async function chooseAdventurer(saved: SavedAdventurer) {
    if (mutationPending.current) return;
    const version = ++selectionVersion.current;
    setSelecting(true);
    setManagedAdventurer(null);
    setShopOpen(false);
    setPendingPurchase(null);
    setAttributeDraft({});
    setUpgradeDraft("");
    setSetup((current) => ({
      ...current,
      name: saved.name,
      sex: saved.sex === "Female" ? "Female" : "Male",
      race: saved.race,
      player_class: saved.class,
      stats: saved.stats,
      adventurer_game_id: saved.source_game_id,
      adventurer_id: saved.adventurer_id,
    }));
    setError(null);
    try {
      const response = await apiFetch(`/api/adventurers/${saved.adventurer_id}`);
      const payload = await response.json() as { adventurer?: ManagedAdventurer; error?: string };
      if (version !== selectionVersion.current) return;
      if (!response.ok || !payload.adventurer) throw new Error(payload.error || "Could not open that adventurer.");
      setManagedAdventurer(payload.adventurer);
      setShopOpen(false);
      setPendingPurchase(null);
      setAttributeDraft({});
      setUpgradeDraft("");
    } catch (requestError) {
      if (version === selectionVersion.current) setError(requestError instanceof Error ? requestError.message : "Could not open that adventurer.");
    } finally {
      if (version === selectionVersion.current) setSelecting(false);
    }
  }

  async function manageAdventurer(commandName: "equip" | "unequip" | "drop" | "apply_progression" | "buy_potions" | "buy_item" | "sell", options: { item?: string; target?: string; allocations?: Record<string, number>; upgrade?: string; quantity?: number }) {
    if (!managedAdventurer || selecting || busy || mutationPending.current) return;
    mutationPending.current = true;
    setBusy(true);
    setError(null);
    try {
      const response = await apiFetch(`/api/adventurers/${managedAdventurer.adventurer_id}/commands`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: commandName, ...options }),
      });
      const payload = await response.json() as { adventurer?: ManagedAdventurer; error?: string };
      if (!response.ok || !payload.adventurer) throw new Error(payload.error || "Could not update that adventurer.");
      setManagedAdventurer(payload.adventurer);
      if (commandName === "apply_progression") {
        setAttributeDraft({});
        setUpgradeDraft("");
      }
      setSavedAdventurers((current) => current.map((entry) => entry.adventurer_id === payload.adventurer?.adventurer_id ? {
        ...entry,
        gold: payload.adventurer.player.gold,
        level: payload.adventurer.player.level ?? entry.level,
        xp: payload.adventurer.player.xp ?? entry.xp,
        stats: payload.adventurer.player.stats,
        inventory_count: payload.adventurer.inventory.reduce((sum, item) => sum + (item.quantity || 1), 0),
        inventory_slots: payload.adventurer.inventory_slots,
        equipment_count: Object.values(payload.adventurer.equipment).filter(Boolean).length,
      } : entry));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not update that adventurer.");
    } finally {
      mutationPending.current = false;
      setBusy(false);
    }
  }

  function returnToRoster() {
    if (mutationPending.current) return;
    selectionVersion.current++;
    setSelecting(false);
    setManagedAdventurer(null);
    setSetup(DEFAULT_SETUP);
    setAttributeDraft({});
    setUpgradeDraft("");
    setShopOpen(false);
    setPendingPurchase(null);
    setSpellbookOpen(false);
    setGame(null);
    setCampOpen(false);
    setShowSetup(true);
    setError(null);
  }

  function adjustStat(stat: string, delta: number) {
    setSetup((current) => {
      const value = current.stats[stat] || 0;
      const spent = Object.values(current.stats).reduce((sum, item) => sum + item, 0);
      if (value + delta < 0 || value + delta > 4 || (delta > 0 && spent >= 12)) return current;
      return { ...current, stats: { ...current.stats, [stat]: value + delta } };
    });
  }

  async function command(
    commandName: string,
    options: { target?: string; spell?: string; item?: string } = {},
  ) {
    if (!gameId || busy || mutationPending.current) return;
    setRecentEvents([]);
    mutationPending.current = true;
    setBusy(true);
    setError(null);
    try {
      const response = await apiFetch(`/api/games/${gameId}/commands`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: commandName, ...options }),
      });
      const payload = await response.json() as ApiResponse;
      if (!response.ok) throw new Error(payload.error || "The action could not be resolved.");
      const newEvents = payload.events || [];
      setRecentEvents(newEvents);
      setGame(payload.state);
      setEvents((current) => [...current, ...newEvents].slice(-60));
      playFeedback(newEvents);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The game engine is unavailable.");
    } finally {
      mutationPending.current = false;
      setBusy(false);
    }
  }

  async function confirmCamp() {
    if (busy || mutationPending.current || !game?.camp?.available) return;
    await command("camp");
    // Close even on an uncertain response: never retry a potentially committed camp.
    setCampOpen(false);
  }

  if (!game && !showSetup) {
    return <ConnectionScreen error={error} apiBase={apiBase} onRetry={() => {
      setError(null);
      setConnectionAttempt((value) => value + 1);
    }} />;
  }

  if (!game && showSetup) {
    const spent = Object.values(setup.stats).reduce((sum, item) => sum + item, 0);
    const campaign = catalog?.campaigns.find((item) => item.id === setup.campaign_id);
    const classProfile = catalog?.classes.find((item) => item.name === setup.player_class);
    const raceProfile = catalog?.races.find((item) => item.name === setup.race);
    const companionProfile = campaign?.companions.find((item) => item.id === setup.companion_id);
    const managedPotionCount = managedAdventurer?.inventory.find((item) => item.id === "healing_potion")?.quantity || 0;
    const visibleShopItems = managedAdventurer?.shop.items.filter((item) =>
      shopTab === "weapons" ? item.kind === "weapon" : shopTab === "armor" ? item.kind === "armor" : false
    ) || [];
    return (
      <main className="game-shell creation-screen">
        <section className="creation-card">
          <div className="creation-heading"><span className="eyebrow">Solo Adventure</span><h1>Choose your adventurer</h1><p>Continue a persistent story or begin another campaign.</p></div>
          {error && <div className="creation-error" role="alert">{error}</div>}
          {(rosterErrors.games || rosterErrors.adventurers) && <div className="creation-error" role="alert">
            {rosterErrors.games && <p>Could not refresh saved adventures: {rosterErrors.games}</p>}
            {rosterErrors.adventurers && <p>Could not refresh saved adventurers: {rosterErrors.adventurers}</p>}
            <button type="button" disabled={busy} onClick={() => setRosterAttempt((attempt) => attempt + 1)}>Retry saved lists</button>
          </div>}
          {savedAdventures.length > 0 && (
            <section className="saved-roster saved-adventures">
              <div className="roster-heading"><span className="section-label">Continue an adventure</span><small>Resume the exact campaign state</small></div>
              <div className="roster-list">
                {savedAdventures.map((saved) => (
                  <button key={saved.game_id} onClick={() => resumeAdventure(saved)} disabled={busy}>
                    <span className="roster-avatar adventure-avatar">{saved.character_name[0]?.toUpperCase()}</span>
                    <span className="roster-copy"><b>{saved.character_name} · {catalog?.campaigns.find((item) => item.id === saved.campaign_id)?.name || saved.campaign_id}</b><small>{saved.sex !== "Unspecified" ? `${saved.sex} · ` : ""}{saved.race} {saved.class} · Level {saved.level} · {saved.companion_name || "Solo"}</small><em>{saved.room_id.replaceAll("_", " ")} · Turn {saved.turn}</em></span>
                    <span className={`session-status ${saved.status}`}>{saved.status === "in_progress" ? `${saved.hp}/${saved.max_hp} HP` : saved.status}</span>
                    <span className="roster-arrow">↗</span>
                  </button>
                ))}
              </div>
            </section>
          )}
          <div className="new-adventurer-divider"><span>Start a different adventure</span></div>
          {savedAdventurers.length > 0 && (
            <section className="saved-roster">
              <div className="roster-heading"><span className="section-label">Use a saved adventurer</span><small>Carry progression into a new campaign</small></div>
              <div className="roster-list">
                {savedAdventurers.map((saved) => (
                  <button key={saved.source_game_id} className={setup.adventurer_game_id === saved.source_game_id ? "selected" : ""} onClick={() => chooseAdventurer(saved)} disabled={busy}>
                    <span className="roster-avatar">{saved.name[0]?.toUpperCase()}</span>
                    <span className="roster-copy"><b>{saved.name}</b><small>{saved.sex !== "Unspecified" ? `${saved.sex} · ` : ""}{saved.race} {saved.class} · Level {saved.level} · {saved.xp} XP</small><em>{saved.gold} gold · {saved.inventory_count} carried items · {saved.equipment_count} equipped</em></span>
                    <span className="session-status in_progress">Use character</span>
                    <span className="roster-arrow">→</span>
                  </button>
                ))}
              </div>
            </section>
          )}
          <div className="new-adventurer-divider"><span>Or create a new adventurer</span></div>
          {setup.adventurer_id && <button className="clear-saved-character" disabled={busy} onClick={() => { selectionVersion.current++; setSelecting(false); setSetup(DEFAULT_SETUP); setManagedAdventurer(null); setShopOpen(false); setPendingPurchase(null); setError(null); }}>Using {setup.name}. Manage equipment below or choose a campaign. <b>Create new instead</b></button>}
          {selecting && <p role="status">Loading adventurer…</p>}
          {managedAdventurer && (
            <section className="adventurer-hub" aria-label={`${managedAdventurer.player.name} character management`}>
              <div className="hub-heading"><div><span className="eyebrow">Between adventures</span><h2>{managedAdventurer.player.name}</h2><p>{managedAdventurer.player.sex && managedAdventurer.player.sex !== "Unspecified" ? `${managedAdventurer.player.sex} · ` : ""}{managedAdventurer.player.race} {managedAdventurer.player.cls} · Level {managedAdventurer.player.level} · {managedAdventurer.player.xp || 0} XP</p></div><div><b>{managedAdventurer.player.gold} gold</b><span>{managedAdventurer.inventory_slots}/{managedAdventurer.inventory_limit} pack slots</span></div></div>
              <section className="progression-hub">
                <div className="progression-heading"><div><span className="section-label">Character progression</span><h3>Shape the next level</h3></div><div><b>{managedAdventurer.progression.unspent_attribute_points}</b><span>attribute points</span><b>{managedAdventurer.progression.unspent_class_upgrades}</b><span>class upgrades</span></div></div>
                <div className="xp-progress"><div><span>Level {managedAdventurer.player.level}</span><b>{managedAdventurer.progression.next_level_xp ? `${managedAdventurer.player.xp} / ${managedAdventurer.progression.next_level_xp} XP` : "Maximum level"}</b></div><i><span style={{ width: managedAdventurer.progression.next_level_xp ? meter((managedAdventurer.player.xp ?? 0) - managedAdventurer.progression.current_level_xp, managedAdventurer.progression.next_level_xp - managedAdventurer.progression.current_level_xp) : "100%" }} /></i></div>
                {(managedAdventurer.progression.unspent_attribute_points > 0 || managedAdventurer.progression.unspent_class_upgrades > 0) ? <>
                  <div className="attribute-allocation"><span className="section-label">Allocate attributes</span><small>Choose up to one point per attribute in this confirmation. Unused points remain banked.</small><div>{Object.entries(managedAdventurer.player.stats).map(([stat, value]) => { const draft = attributeDraft[stat] || 0; const draftedTotal = Object.values(attributeDraft).reduce((sum, point) => sum + point, 0); return <article key={stat}><div><b>{stat}</b><small>{ATTRIBUTE_HELP[stat]}</small></div><button onClick={() => setAttributeDraft((current) => ({ ...current, [stat]: 0 }))} disabled={busy || !draft}>−</button><strong>{value}{draft ? ` → ${value + draft}` : ""}</strong><button onClick={() => setAttributeDraft((current) => ({ ...current, [stat]: 1 }))} disabled={busy || Boolean(draft) || value >= managedAdventurer.progression.attribute_cap || draftedTotal >= managedAdventurer.progression.unspent_attribute_points}>+</button></article>; })}</div></div>
                  {managedAdventurer.progression.unspent_class_upgrades > 0 && <div className="upgrade-allocation"><span className="section-label">Choose one class upgrade</span><div>{managedAdventurer.progression.upgrade_options.map((upgrade) => <button key={upgrade.id} className={upgradeDraft === upgrade.id ? "selected" : ""} disabled={busy} onClick={() => setUpgradeDraft(upgradeDraft === upgrade.id ? "" : upgrade.id)}><b>{upgrade.name}</b><small>{upgrade.description}</small></button>)}</div></div>}
                  <div className="progression-confirm"><p><b>Pending:</b> {Object.entries(attributeDraft).filter(([, value]) => value).map(([stat]) => `${stat} +1`).join(", ") || "No attributes"}{upgradeDraft ? ` · ${managedAdventurer.progression.upgrade_options.find((item) => item.id === upgradeDraft)?.name}` : " · No class upgrade"}</p><button onClick={() => manageAdventurer("apply_progression", { allocations: attributeDraft, upgrade: upgradeDraft })} disabled={busy || (!Object.values(attributeDraft).some(Boolean) && !upgradeDraft)}>Confirm permanent changes</button></div>
                </> : <p className="progression-empty">No upgrade decisions are pending. Earn XP in adventures to unlock more choices.</p>}
              </section>
              <div className="hub-columns">
                <div className="hub-equipment"><span className="section-label">Equipped</span>{Object.entries(managedAdventurer.equipment).map(([slot, item]) => <div key={slot}><span>{slot}</span>{item ? <><span className="item-copy"><b>{item.name}</b><small>{itemStats(item)}</small></span><button onClick={() => manageAdventurer("unequip", { target: slot })} disabled={busy}>Unequip</button></> : <em>Empty</em>}</div>)}</div>
                <div className="hub-inventory"><span className="section-label">Pack</span>{managedAdventurer.inventory.map((item, index) => <div key={`${item.id}-${index}`}><span className="item-copy"><b>{item.name}</b><small>{item.kind}{item.quantity && item.quantity > 1 ? ` · ×${item.quantity}` : ""} · {itemStats(item)}</small>{item.slot && <em>{itemComparison(item, managedAdventurer.equipment[item.slot])}</em>}</span>{["armor", "weapon"].includes(item.kind) && <button onClick={() => manageAdventurer("equip", { item: item.name })} disabled={busy}>Equip</button>}{Boolean(item.sell_value) && <button onClick={() => manageAdventurer("sell", { item: item.name })} disabled={busy}>Sell · {item.sell_value}g</button>}<button onClick={() => manageAdventurer("drop", { item: item.name })} disabled={busy || item.kind === "quest"}>Drop{item.quantity && item.quantity > 1 ? " one" : ""}</button></div>)}</div>
              </div>
              <section className="provisioner-callout"><div><span className="section-label">Roadside provisioner</span><h3>Supplies, equipment, and trade</h3><p>Browse larger item details, compare equipped gear, or sell unwanted equipment.</p></div><button onClick={() => { setShopTab("weapons"); setShopOpen(true); }}>Open provisioner</button></section>
              <div className="hub-stats">{Object.entries(managedAdventurer.player.stats).map(([stat, value]) => <span key={stat}><small>{stat}</small><b>{value}</b></span>)}</div>
              {shopOpen && <div className="shop-backdrop" role="presentation" onMouseDown={() => { setShopOpen(false); setPendingPurchase(null); }}><section className="shop-dialog" role="dialog" aria-modal="true" aria-label="Roadside provisioner" onMouseDown={(event) => event.stopPropagation()}><header><div><span className="eyebrow">Roadside provisioner</span><h2>Outfit the next expedition</h2></div><div className="shop-resources"><span><b>{managedAdventurer.player.gold}</b> gold</span><span><b>{managedAdventurer.inventory_slots}</b> / {managedAdventurer.inventory_limit} pack slots</span><button aria-label="Close provisioner" onClick={() => { setShopOpen(false); setPendingPurchase(null); }}>Close</button></div></header><nav className="shop-tabs" aria-label="Shop categories">{(["weapons", "armor", "consumables", "sell"] as ShopTab[]).map((tab) => <button key={tab} className={shopTab === tab ? "active" : ""} onClick={() => { setShopTab(tab); setPendingPurchase(null); }}>{tab}</button>)}</nav><div className="shop-content">{["weapons", "armor"].includes(shopTab) && <div className="shop-catalog">{visibleShopItems.map((item) => { const equipped = item.slot ? managedAdventurer.equipment[item.slot] : null; const price = item.buy_value || 0; return <article key={item.id}><div className="shop-item-heading"><span>{item.slot}</span><em>Tier {item.tier}</em></div><h3>{item.name}</h3><p>{item.description}</p><div className="shop-item-stats"><b>{itemStats(item)}</b><span>{itemComparison(item, equipped)}</span></div><div className="shop-equipped"><small>Currently equipped</small><b>{equipped?.name || `Empty ${item.slot} slot`}</b><span>{equipped ? itemStats(equipped) : "No bonuses"}</span></div><button className="shop-buy" onClick={() => setPendingPurchase({ label: item.name, price, command: "buy_item", options: { item: item.id } })} disabled={busy || managedAdventurer.player.gold < price || managedAdventurer.inventory_slots >= managedAdventurer.inventory_limit}><span>Purchase</span><b>{price} gold</b></button></article>; })}</div>}{shopTab === "consumables" && <div className="consumable-shop"><article><div><span className="section-label">Healing supply</span><h3>Healing Potion</h3><p>Restores 1d6+2 health to you or your companion. A stack occupies one pack slot.</p></div><div className="potion-stock"><span>Carried</span><b>{managedPotionCount} / {managedAdventurer.shop.stack_limit}</b></div><div className="potion-options"><button onClick={() => setPendingPurchase({ label: "one Healing Potion", price: managedAdventurer.shop.healing_potion_price, command: "buy_potions", options: { quantity: 1 } })} disabled={busy || managedPotionCount + 1 > managedAdventurer.shop.stack_limit || managedAdventurer.player.gold < managedAdventurer.shop.healing_potion_price}>Buy one · {managedAdventurer.shop.healing_potion_price} gold</button><button onClick={() => setPendingPurchase({ label: `${managedAdventurer.shop.bundle_quantity} Healing Potions`, price: managedAdventurer.shop.healing_potion_price * managedAdventurer.shop.bundle_quantity, command: "buy_potions", options: { quantity: managedAdventurer.shop.bundle_quantity } })} disabled={busy || managedPotionCount + managedAdventurer.shop.bundle_quantity > managedAdventurer.shop.stack_limit || managedAdventurer.player.gold < managedAdventurer.shop.healing_potion_price * managedAdventurer.shop.bundle_quantity}>Buy ×{managedAdventurer.shop.bundle_quantity} · {managedAdventurer.shop.healing_potion_price * managedAdventurer.shop.bundle_quantity} gold</button></div></article></div>}{shopTab === "sell" && <div className="sell-list">{managedAdventurer.inventory.filter((item) => Boolean(item.sell_value)).map((item, index) => <article key={`${item.id}-${index}`}><div><span>{item.slot || item.kind}</span><h3>{item.name}</h3><p>{itemStats(item)}{item.quantity && item.quantity > 1 ? ` · ${item.quantity} carried` : ""}</p></div><button onClick={() => manageAdventurer("sell", { item: item.name })} disabled={busy}>Sell one · {item.sell_value} gold</button></article>)}{!managedAdventurer.inventory.some((item) => Boolean(item.sell_value)) && <p className="shop-empty">You have no ordinary equipment to sell.</p>}</div>}</div>{pendingPurchase && <aside className="purchase-confirm" aria-live="polite"><div><span className="section-label">Confirm purchase</span><p>Buy <b>{pendingPurchase.label}</b> for <b>{pendingPurchase.price} gold</b>?</p></div><button onClick={() => setPendingPurchase(null)}>Cancel</button><button className="confirm-buy" disabled={busy} onClick={async () => { const purchase = pendingPurchase; setPendingPurchase(null); await manageAdventurer(purchase.command, purchase.options); }}>Confirm purchase</button></aside>}</section></div>}
            </section>
          )}
          <div className="creation-grid">
            <label className="field wide"><span>Name</span><input value={setup.name} disabled={Boolean(setup.adventurer_id)} maxLength={30} onChange={(event) => setSetup({ ...setup, name: event.target.value })} /></label>
            <label className="field"><span>Campaign</span><select value={setup.campaign_id} onChange={(event) => setSetup({ ...setup, campaign_id: event.target.value, companion_id: catalog?.campaigns.find((item) => item.id === event.target.value)?.companions[0]?.id || "" })}>{catalog?.campaigns.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><small>{campaign?.description} {campaign ? `Recommended level ${campaign.recommended_level} · Equipment through tier ${campaign.max_item_tier}.` : ""}</small></label>
            <label className="field"><span>Class</span><select value={setup.player_class} disabled={Boolean(setup.adventurer_id)} onChange={(event) => setSetup({ ...setup, player_class: event.target.value })}>{catalog?.classes.map((item) => <option key={item.name}>{item.name}</option>)}</select><small>{classProfile?.description} {classProfile?.spells.length ? `Spells: ${classProfile.spells.join(", ")}.` : ""}</small></label>
            <label className="field"><span>Race</span><select value={setup.race} disabled={Boolean(setup.adventurer_id)} onChange={(event) => setSetup({ ...setup, race: event.target.value })}>{catalog?.races.map((item) => <option key={item.name}>{item.name}</option>)}</select><small>{raceProfile?.description}</small></label>
            <label className="field"><span>Sex</span><select value={setup.sex} disabled={Boolean(setup.adventurer_id)} onChange={(event) => setSetup({ ...setup, sex: event.target.value as "Male" | "Female" })}><option value="Female">Female</option><option value="Male">Male</option></select><small>Stored with this adventurer across campaigns.</small></label>
            <section className="companion-picker" aria-label="Companion selection">
              <label className="field"><span>Companion</span><select value={setup.companion_id} onChange={(event) => setSetup({ ...setup, companion_id: event.target.value })}>{campaign?.companions.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.role}</option>)}</select><small>Your companion acts automatically after you.</small></label>
              {companionProfile && (
                <article className="companion-dossier" aria-live="polite">
                  <div className="dossier-heading"><span className="roster-avatar">{companionProfile.name[0]}</span><div><span className="section-label">{companionProfile.role}</span><h3>{companionProfile.name}</h3></div><em>{companionProfile.personality}</em></div>
                  <p>{companionProfile.description}</p>
                  <div className="dossier-stats"><span><small>Health</small><b>{companionProfile.hp}</b></span><span><small>Armor</small><b>{companionProfile.ac} AC</b></span><span><small>Attack</small><b>+{companionProfile.attack_bonus}</b></span><span><small>Damage</small><b>{companionProfile.damage}</b></span>{Boolean(companionProfile.mana) && <span><small>Mana</small><b>{companionProfile.mana}</b></span>}</div>
                  {companionProfile.spells.length > 0 && <p className="dossier-spells"><b>Spells</b> {companionProfile.spells.join(" · ")}</p>}
                  <p className="dossier-fit"><b>Best for</b> {companionProfile.best_for}</p>
                  <small className="dossier-tactic">Begins with the <b>{companionProfile.default_tactic}</b> companion tactic. You can change it during play.</small>
                </article>
              )}
            </section>
          </div>
          {!setup.adventurer_id && <div className="stat-builder">
            <div><span className="section-label">Allocate attributes</span><b className={spent === 12 ? "complete" : ""}>{spent} / 12 points</b></div>
            <div className="stat-grid">
              {Object.entries(setup.stats).map(([stat, value]) => (
                <div className="stat-stepper" key={stat}><span>{stat}</span><button onClick={() => adjustStat(stat, -1)} aria-label={`Decrease ${stat}`}>−</button><b>{value}</b><button onClick={() => adjustStat(stat, 1)} aria-label={`Increase ${stat}`}>+</button></div>
              ))}
            </div>
          </div>}
          <button className="begin-button" disabled={busy || selecting || (Boolean(setup.adventurer_id) && !managedAdventurer) || (!setup.adventurer_id && spent !== 12) || !setup.name.trim() || !catalog} onClick={() => startGame(setup)}>{busy ? "Creating…" : setup.adventurer_id ? `Begin a new campaign with ${setup.name}` : "Enter the watchtower"}</button>
        </section>
      </main>
    );
  }

  if (!game) return null;

  const companion = game.companions[0];
  const activeCompanionProfile = catalog?.campaigns
    .find((item) => item.id === game.campaign.id)?.companions
    .find((item) => item.name === companion.name);
  const potions = game.inventory
    .filter((item) => item.id === "healing_potion" && item.kind === "potion" && item.effect?.type === "heal")
    .reduce((sum, item) => sum + (item.quantity || 1), 0);
  const playerWounded = game.player.hp < game.player.max_hp;
  const companionWounded = companion.hp < companion.max_hp;
  const potionTarget = companionWounded && companion.hp / companion.max_hp < game.player.hp / game.player.max_hp
    ? companion.name
    : "me";
  const lastEvent = events[events.length - 1];
  const locations = game.journey?.locations || [{ id: game.room.id, name: game.room.name, statuses: ["current"] }];
  const corpses = game.flags.corpses as Record<string, Array<{ looted?: boolean }>> | undefined;
  const hasLoot = Boolean(corpses?.[game.room.id]?.some((corpse) => !corpse.looted));
  const available = game.available_actions.filter((action) => !action.informational && !["use", "companion_advice"].includes(action.id)
    && !(game.challenge && game.room.kind === "loot" && ["search", "inspect", "open", "loot"].includes(action.id)));
  const suggestion = game.journey?.objective.description || (game.phase === "combat"
    ? game.player.hp <= 5 && potions ? "You're bleeding. Drink the potion—I can hold them." : "Keep your guard up. We finish this together."
    : game.room.id === "courtyard" && !game.flags.social_done
      ? "That scout knows this place. Words may save us blood."
      : game.room.id === "spire"
        ? "There. The chest. Mind the lock—it looks stubborn."
        : "Listen first. Old stone has a way of warning you.");

  const runAction = (action: AvailableAction) => {
    if (busy || mutationPending.current) return;
    if (action.id === "camp") { if (game.camp?.available) setCampOpen(true); return; }
    if (action.id === "spellbook") { setSpellbookOpen(true); return; }
    if (action.id === "move" && action.target) return command("move", { target: action.target });
    if (action.id === "challenge" && action.target) return command("challenge", { target: action.target });
    if (action.id === "loot") return command("loot", { target: hasLoot ? "all" : undefined });
    // Attack and Special share the engine default: the lowest-HP living enemy.
    // Enemy IDs retain their original slots, so "1" may already be defeated.
    return command(action.id);
  };

  return (
    <main className="game-shell">
      <header className="topbar">
        <a className="brand" href="#" aria-label="Solo Adventure home">
          <span className="brand-mark">SA</span>
          <span><b>Solo Adventure</b><small>Python engine connected</small></span>
        </a>
        <div className="engine-status"><i />Authoritative engine</div>
        <div className="header-actions">
          <button className={`icon-button ${sound ? "active" : ""}`} onClick={() => setSound(!sound)} aria-pressed={sound}>{sound ? "Sound on" : "Sound off"}</button>
          <button className={`icon-button ${voice ? "active" : ""}`} onClick={() => setVoice(!voice)} aria-pressed={voice}>{voice ? "Voice on" : "Voice off"}</button>
          <button className="new-button" disabled={busy} onClick={() => setShowSetup(true)}>New game</button>
        </div>
      </header>

      <section className="campaign-bar">
        <div><span className="eyebrow">Campaign 01</span><strong>{game.campaign.name}</strong></div>
        <div className="journey-position">{game.room.name}<small>{locations.length} known locations</small></div>
        <div className="turn-counter"><span>Turn</span><b>{String(game.turn).padStart(2, "0")}</b></div>
      </section>

      {error && <div className="error-banner" role="alert">{error} <button disabled={busy} onClick={returnToRoster}>Return to adventurer roster</button></div>}

      {game.journey && <section className="journey-panel" aria-label="Current objective">
        <span className="section-label">Current objective</span>
        <h2>{game.journey.objective.title}</h2>
        <p>{game.journey.objective.description}</p>
        <details>
          <summary>Journal and known locations</summary>
          <div className="journey-details">
            <div><h3>Journal</h3><ul aria-label="Journal">{game.journey.journal.map((entry) => <li key={entry.id}>{entry.text}</li>)}</ul>{!game.journey.journal.length && <p>No discoveries recorded yet.</p>}</div>
            <div><h3>Known locations</h3><ul aria-label="Known locations">{locations.map((location) => <li key={location.id} aria-current={location.id === game.room.id ? "location" : undefined}><b>{location.name}</b><small>{location.statuses.join(" · ")}</small></li>)}</ul></div>
          </div>
        </details>
      </section>}

      <section className="play-grid">
        <aside className="party-panel">
          <div className="section-label">Your party</div>
          <article className="character-card">
            <div className="portrait player-portrait">{game.player.name[0]}</div>
            <div className="character-info"><div><strong>{game.player.name}</strong><span>{game.player.race} {game.player.cls} · Lv {game.player.level}</span></div><b className="ac">AC {game.player.ac}</b></div>
            <div className="health-label"><span>Health</span><b>{game.player.hp} / {game.player.max_hp}</b></div>
            <div className="health-track"><i style={{ width: meter(game.player.hp, game.player.max_hp) }} /></div>
            {Object.entries(game.player.conditions || {}).map(([condition, rounds]) => <div className={`condition-badge ${condition}`} key={condition}><b>{condition}</b><span>{rounds} round{rounds === 1 ? "" : "s"}</span></div>)}
            {Boolean(game.player.max_mana) && <><div className="health-label"><span>Mana</span><b>{game.player.mana} / {game.player.max_mana}</b></div><div className="health-track mana"><i style={{ width: meter(game.player.mana || 0, game.player.max_mana || 1) }} /></div></>}
          </article>
          <article className={`character-card compact ${companion.hp > 0 && companion.hp <= Math.max(3, Math.floor(companion.max_hp / 4)) ? "critical" : ""}`}>
            <div className="portrait mara-portrait">{companion.name[0]}</div>
            <div className="character-info"><div><strong>{companion.name}</strong><span>{activeCompanionProfile?.role || "Companion"} · {companion.tactic || "balanced"} tactic</span></div><b className="ac">AC {companion.ac}</b></div>
            <div className="health-label"><span>Health</span><b>{companion.hp} / {companion.max_hp}</b></div>
            <div className="health-track companion"><i style={{ width: meter(companion.hp, companion.max_hp) }} /></div>
            {Object.entries(companion.conditions || {}).map(([condition, rounds]) => <div className={`condition-badge ${condition}`} key={condition}><b>{condition}</b><span>{rounds} round{rounds === 1 ? "" : "s"}</span></div>)}
            <div className="relationship-row"><span>Trust {companion.trust ?? 50}</span><span>{companion.mood || "steady"}</span></div>
            {companion.hp > 0 && companion.hp <= Math.max(3, Math.floor(companion.max_hp / 4)) && <div className="critical-warning">Critical · protect or heal {companion.name}</div>}
          </article>
          <blockquote><span>{companion.name} suggests</span>“{suggestion}”</blockquote>
          <div className="companion-tools">
            <div className="section-label">Companion</div>
            <div className="companion-actions">
              <button onClick={() => command("companion_talk")} disabled={busy || game.phase === "combat"}>Talk</button>
              <button onClick={() => command("companion_advice")} disabled={busy}>Ask advice</button>
            </div>
            <span className="tactic-label">Companion tactic</span>
            <div className="tactic-picker">
              {["cautious", "balanced", "aggressive"].map((tactic) => (
                <button key={tactic} className={(companion.tactic || "balanced") === tactic ? "selected" : ""} onClick={() => command("set_tactic", { target: tactic })} disabled={busy}>{tactic}</button>
              ))}
            </div>
          </div>
          <div className="inventory">
            <div className="section-label">Pack · {game.inventory.length}/10</div>
            <button onClick={() => command("use", { item: "healing potion", target: potionTarget })} disabled={busy || !potions || (!playerWounded && !companionWounded)}>
              <span className="potion">✦</span><span><b>Healing potion</b><small>Use on most wounded</small></span><em>×{potions}</em>
            </button>
            {game.inventory.filter((item) => item.id !== "healing_potion").map((item, index) => (
              <div className="inventory-item" key={`${item.id}-${item.name}-${index}`}>
                <button className="item-use" onClick={() => ["armor", "weapon"].includes(item.kind) ? command("equip", { item: item.name }) : undefined} disabled={busy || !["armor", "weapon"].includes(item.kind)}>
                  <span className="potion">◇</span><span><b>{item.name}</b><small>{item.kind}{item.slot ? ` · ${item.slot}` : ""}</small></span><em>{["armor", "weapon"].includes(item.kind) ? "+" : ""}</em>
                </button>
                <button className="drop-item" onClick={() => command("drop", { item: item.name })} disabled={busy || item.kind === "quest"}>Drop</button>
              </div>
            ))}
            <div className="xp-row"><span>Experience · {game.player.gold} gold</span><b>{game.player.xp} XP</b></div>
          </div>
        </aside>

        <section className="scene-panel">
          <div className={`scene-art room-${game.room.id}`}>
            <div className="moon" /><div className="tower"><i /><i /><i /></div><div className="mist mist-one" /><div className="mist mist-two" />
            <div className="scene-caption">
              <span>{ROOM_KICKERS[game.room.id] || game.room.kind}</span>
              <h1>{game.room.name}</h1>
              <p>{game.room.description}</p>
            </div>
          </div>

          {game.phase === "combat" && (
            <div className="enemy-strip">
              {game.enemies.map((enemy) => (
                <article key={enemy.id}>
                  <div className="enemy-token">!</div>
                  <div><strong>{enemy.name}</strong><span>AC {enemy.ac}</span>{Object.entries(enemy.conditions || {}).map(([condition, rounds]) => <em className={`enemy-condition ${condition}`} key={condition}>{condition} · {rounds}</em>)}</div>
                  <div className="enemy-health"><i style={{ width: meter(enemy.hp, enemy.max_hp) }} /></div>
                  <b>{enemy.hp} HP</b>
                </article>
              ))}
            </div>
          )}

          <div className="action-area">
            <CombatAwareness player={game.player} companions={game.companions} spellbook={game.spellbook} phase={game.phase} gameOver={game.game_over}
              cleared={Array.isArray(game.flags.defeated_rooms) && game.flags.defeated_rooms.includes(game.room.id)}
              canUsePotion={potions > 0 && game.available_actions.some(action => action.id === "use" && !action.disabled)}
              canCamp={Boolean(game.camp?.available)} busy={busy} events={recentEvents}
              onPotion={() => command("use", { item: "healing potion", target: "me" })} onCamp={() => setCampOpen(true)} />
            {game.challenge && <div className="challenge-callout"><span>{game.challenge.required ? "Path challenge" : "Optional opportunity"}</span><h2>{game.challenge.title}</h2><p>{game.challenge.prompt}</p></div>}
            <div className="action-heading"><span className="section-label">{game.phase === "combat" ? "Choose your move" : game.game_over ? "Campaign resolved" : "What do you do?"}</span><small>{busy ? "Resolving…" : "Resolved by Python rules"}</small></div>
            <div className="action-grid">
              {game.game_over ? (
                <button className="primary-action wide-action" onClick={() => setShowSetup(true)}><span>↻</span><b>Begin again</b><small>Create a new persistent character</small></button>
              ) : (
                <>
                  {available.map((action, index) => (
                    <button key={`${action.id}-${action.spell || ""}-${action.target || index}`} className={index === 0 ? "primary-action" : ""} onClick={() => runAction(action)} disabled={busy || action.disabled || (action.id === "camp" && !game.camp?.available) || (action.id === "loot" && !hasLoot && game.room.kind !== "passage") || (action.id === "cast" && (game.player.mana || 0) < (action.mana_cost || 0))} title={action.disabled_reason || undefined}>
                      <span>{action.id === "attack" ? "⚔" : action.id === "defend" ? "◇" : action.id === "move" ? "→" : action.id === "rest" ? "☾" : action.id === "challenge" ? "⌘" : action.id === "cast" ? "✦" : "◌"}</span>
                      <b>{action.id === "loot" && hasLoot ? "Loot all" : action.label}</b>
                      <small>{action.disabled_reason || action.description || (action.id === "move" && action.target ? `Travel to ${action.target}` : action.id === "attack" ? game.player.damage : action.id === "cast" ? `${action.mana_cost} mana` : "Engine action")}</small>
                      {action.id === "move" && <small className="location-status">{locations.find((location) => location.id === action.target)?.statuses.join(" · ")}</small>}
                      {action.id === "camp" && game.camp?.reason && !action.disabled_reason && <small>{game.camp.reason}</small>}
                    </button>
                  ))}
                  {game.room.kind === "loot" && !game.challenge && !available.some((action) => action.id === "open") && <button className="primary-action" onClick={() => command("open")} disabled={busy}><span>⌑</span><b>Open the chest</b><small>Dexterity check</small></button>}
                  <button onClick={() => command("use", { item: "healing potion", target: "me" })} disabled={busy || !potions || !playerWounded}><span>✦</span><b>Heal {game.player.name}</b><small>{potions} potions remaining</small></button>
                  <button onClick={() => command("use", { item: "healing potion", target: companion.name })} disabled={busy || !potions || !companionWounded}><span>✦</span><b>{companion.hp <= 0 ? "Revive" : "Heal"} {companion.name}</b><small>{potions} potions remaining</small></button>
                </>
              )}
            </div>
          </div>
        </section>

        <aside className="chronicle-panel">
          <div className="chronicle-header"><div><span className="section-label">Chronicle</span><h2>Authoritative events</h2></div><span className="live-dot">Live</span></div>
          <div className="event-list" aria-live="polite">
            {[...events].reverse().map((item, index) => (
              <article key={item.event_id} className={`${eventClass(item.type)} ${index === 0 ? "latest" : ""}`}>
                <span className="event-icon">{eventIcon(item.type)}</span>
                <div><small>{item.type.replaceAll("_", " ")}</small><p>{item.message}</p></div>
              </article>
            ))}
          </div>
          <div className="last-roll"><span>Latest event</span><p>{lastEvent?.type.replaceAll("_", " ")}</p></div>
        </aside>
      </section>
      {campOpen && game.camp && <div className="setup-overlay">
        <section className="setup-confirm camp-dialog" role="dialog" aria-modal="true" aria-labelledby="camp-title" aria-describedby="camp-preview" aria-busy={busy}>
          <span className="eyebrow">Rest together</span>
          <h2 id="camp-title">Make camp</h2>
          <p id="camp-preview">Recover over {game.camp.recovery_turns} {game.camp.recovery_turns === 1 ? "turn" : "turns"}. The camp ends as soon as recovery is complete, up to 100 turns.</p>
          <ul aria-label="Expected recovery">{game.camp.recovery.map((actor, index) => <li key={`${actor.name}-${index}`}><b>{actor.name}</b><span>+{actor.hp} HP · +{actor.mana} mana</span></li>)}</ul>
          <div><button disabled={busy} onClick={() => setCampOpen(false)}>Cancel</button><button className="primary-confirm" disabled={busy || !game.camp.available} onClick={confirmCamp}>{busy ? "Making camp…" : "Confirm camp"}</button></div>
        </section>
      </div>}
      {spellbookOpen && (
        <div className="spellbook-backdrop" role="dialog" aria-modal="true" aria-label="Spellbook" onClick={() => setSpellbookOpen(false)}>
          <section className="spellbook-dialog" onClick={(event) => event.stopPropagation()}>
            <header>
              <div><span className="eyebrow">Known magic</span><h2>{game.player.name}&apos;s spellbook</h2></div>
              <div className="spellbook-mana"><span>Mana</span><b>{game.player.mana} / {game.player.max_mana}</b></div>
              <button className="spellbook-close" onClick={() => setSpellbookOpen(false)} aria-label="Close spellbook">×</button>
            </header>
            <div className="spell-list">
              {game.spellbook.map((spell) => (
                <article key={spell.name} className={!spell.available ? "unavailable" : ""}>
                  <div className="spell-heading"><span className={`spell-rune ${spell.category}`}>✦</span><div><small>{spell.category} · {spell.contexts.join(" / ")}</small><h3>{spell.name}</h3></div><b>{spell.mana_cost} mana</b></div>
                  <p>{spell.description}</p>
                  {spell.available ? (
                    <div className="spell-targets">
                      {spell.targets.map((target) => <button key={target.id} disabled={busy} onClick={() => { setSpellbookOpen(false); command("cast", { spell: spell.name, target: target.id }); }}>Cast on {target.label}</button>)}
                    </div>
                  ) : <div className="spell-reason">{spell.reason}</div>}
                </article>
              ))}
            </div>
          </section>
        </div>
      )}
      {showSetup && (
        <div className="setup-overlay" role="dialog" aria-modal="true" aria-label="Create a new character">
          <div className="setup-confirm">
            <span className="eyebrow">New campaign</span>
            <h2>Leave this adventure?</h2>
            <p>Your current game is safely stored. Creating another character starts a separate session.</p>
            <div><button onClick={() => setShowSetup(false)}>Keep playing</button><button className="primary-confirm" onClick={returnToRoster}>Create character</button></div>
          </div>
        </div>
      )}
    </main>
  );
}
