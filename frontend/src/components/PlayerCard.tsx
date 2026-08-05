import type { PlayerId, PlayerRole, PublicPlayer } from "../types";

const ROLE_LABELS: Record<PlayerRole, string> = {
  human: "HUMAN",
  ai_empath: "AI · 공감형",
  ai_wit: "AI · 재치형",
  ai_story: "AI · 경험형",
};

interface PlayerCardProps {
  player: PublicPlayer;
  isThinking: boolean;
  revealRole: boolean;
}

function playerNumber(id: PlayerId): string {
  return id.slice(-2);
}

export default function PlayerCard({
  player,
  isThinking,
  revealRole,
}: PlayerCardProps) {
  return (
    <article
      className={`player-card player-card--${player.color}${
        player.is_alive ? "" : " player-card--out"
      }`}
      data-player-id={player.id}
    >
      <header className="player-card__header">
        <span className="player-card__character" aria-hidden="true">
          {player.character_emoji}
        </span>
        <h3>PLAYER {playerNumber(player.id)}</h3>
        {player.is_you && <span className="player-card__you">YOU</span>}
      </header>

      <div className="player-card__bubble" aria-live="polite">
        {isThinking ? (
          <span className="thinking-dots" aria-label="답변 생각 중">
            <span aria-hidden="true">● ● ●</span>
          </span>
        ) : (
          player.answer ?? "답변을 기다리는 중…"
        )}
      </div>

      {revealRole && player.role && (
        <p className="player-card__role">{ROLE_LABELS[player.role]}</p>
      )}
      {!player.is_alive && <div className="player-card__out">OUT</div>}
    </article>
  );
}
