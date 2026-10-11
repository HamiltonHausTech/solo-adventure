type PartyMember = { name: string; hp: number; max_hp: number; mana?: number; max_mana?: number };
type HealthEvent = { event_id: string; type: string; actor: string | null; data: Record<string, number> };
type OffensiveSpell = { name: string; mana_cost: number; target_type: string; contexts: string[]; available: boolean };
type Props = {
  spellbook: OffensiveSpell[];
  player: PartyMember;
  companions: PartyMember[];
  phase: string;
  gameOver: boolean;
  cleared: boolean;
  canUsePotion: boolean;
  canCamp: boolean;
  busy: boolean;
  events: HealthEvent[];
  onPotion: () => void;
  onCamp: () => void;
};

/** Snapshot warnings persist; command-only net HP feedback never replays on resume. */
export function CombatAwareness({ player, companions, spellbook, phase, gameOver, cleared, canUsePotion, canCamp, busy, events, onPotion, onCamp }: Props) {
  const party = [player, ...companions];
  // Enemy-targeted damage and control spells are offensive; costs and current
  // usability come from the same authoritative spellbook as the cast controls.
  const offensive = spellbook.filter(spell => spell.target_type === "enemy" && spell.contexts.includes(phase));
  const unaffordable = offensive.filter(spell => spell.mana_cost > (player.mana ?? 0));
  const availableOffensive = offensive.filter(spell => spell.available);
  const availableOther = spellbook.filter(spell => spell.target_type !== "enemy" && spell.available);
  const lowHealth = (actor: PartyMember) => actor.hp > 0 && actor.hp <= actor.max_hp / 4;
  const recovering = party.some(actor => actor.hp > 0 && (actor.hp < actor.max_hp || (actor.mana ?? 0) < (actor.max_mana ?? 0)));
  const postBattle = !gameOver && player.hp > 0 && phase === "exploration" && cleared && recovering;
  return <section className="combat-awareness" aria-label="Party readiness" aria-live="polite" aria-atomic="true">
    {gameOver ? <p className="readiness-danger"><strong>{player.hp <= 0 ? `Adventure ended · ${player.name} has fallen · ${player.hp}/${player.max_hp} HP` : "Campaign complete"}</strong></p> : party.map((actor, index) => <div key={index}>
      {actor.hp <= 0 ? <p className="readiness-danger"><strong>{actor.name}: Fallen · {actor.hp}/{actor.max_hp} HP</strong></p> : lowHealth(actor) && <p className="readiness-danger"><strong>{actor.name}: Low health · {actor.hp}/{actor.max_hp} HP</strong></p>}
      {actor.hp > 0 && (actor.max_mana ?? 0) > 0 && (actor.mana ?? 0) <= (actor.max_mana ?? 0) / 4 && <p className="readiness-mana"><strong>{actor.name}: {actor.mana === 0 ? "Mana depleted" : "Low mana"} · {actor.mana ?? 0}/{actor.max_mana} mana</strong>{index === 0 && <span> Spell costs and availability are shown in the spellbook.</span>}</p>}
    </div>)}
    {!gameOver && player.hp > 0 && unaffordable.length > 0 && <p className="readiness-mana">
      <strong>{player.name}: {unaffordable.length === offensive.length ? "Cannot afford any learned offensive spells" : "Some learned offensive spells are unaffordable"} · {player.mana ?? 0}/{player.max_mana} mana</strong>
      <span> {unaffordable.map(spell => `${spell.name} requires ${spell.mana_cost} mana`).join("; ")}.</span>
      {availableOffensive.length > 0 && <span> Available offensive spells: {availableOffensive.map(spell => spell.name).join(", ")}.</span>}
      {availableOther.length > 0 && <span> Other available spells: {availableOther.map(spell => spell.name).join(", ")}.</span>}
    </p>}
    {!gameOver && lowHealth(player) && canUsePotion && <button disabled={busy} onClick={onPotion}>Use healing potion on {player.name}</button>}
    {events.filter(event => event.type === "health_changed" && event.data.hp_delta < 0).map(event => {
      const actor = event.actor === "player" ? player : companions[Number(event.actor?.split(":")[1])];
      if (!actor) return null;
      return <p className="readiness-damage" key={event.event_id}><strong>{actor.name}: health fell {-event.data.hp_delta} this turn · {event.data.hp_after}/{event.data.max_hp} HP</strong><span> Net change after all healing and damage, not an individual hit.</span></p>;
    })}
    {postBattle && <section className="post-battle" aria-label="Post-battle recovery">
      <h3>Battle won · Check your party before moving on</h3>
      <ul>{party.map((actor, index) => <li key={index}>{actor.name}: {actor.hp}/{actor.max_hp} HP{(actor.max_mana ?? 0) > 0 && ` · ${actor.mana ?? 0}/${actor.max_mana} mana`}{actor.hp <= 0 && " · Fallen"}</li>)}</ul>
      {canCamp ? <button disabled={busy} onClick={onCamp}>Review camp recovery</button> : <p>Review your supplies and available recovery actions.</p>}
    </section>}
  </section>;
}
