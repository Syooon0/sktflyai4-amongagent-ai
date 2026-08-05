import type { PlayerRole, PublicPlayer } from "../types";

const ROLE_LABELS: Record<PlayerRole, string> = {
  human: "HUMAN",
  INTJ: "AI · INTJ 전략가",
  INTP: "AI · INTP 사색가",
  ENTJ: "AI · ENTJ 통솔자",
  ENTP: "AI · ENTP 변론가",
  INFJ: "AI · INFJ 옹호자",
  INFP: "AI · INFP 중재자",
  ENFJ: "AI · ENFJ 사회운동가",
  ENFP: "AI · ENFP 활동가",
  ISTJ: "AI · ISTJ 논리주의자",
  ISFJ: "AI · ISFJ 수호자",
  ESTJ: "AI · ESTJ 관리자",
  ESFJ: "AI · ESFJ 외교관",
  ISTP: "AI · ISTP 재주꾼",
  ISFP: "AI · ISFP 예술가",
  ESTP: "AI · ESTP 사업가",
  ESFP: "AI · ESFP 연예인",
};

interface PlayerCardProps {
  player: PublicPlayer;
  isThinking: boolean;
  isEliminating: boolean;
  revealRole: boolean;
}

export default function PlayerCard({
  player,
  isThinking,
  isEliminating,
  revealRole,
}: PlayerCardProps) {
  return (
    <article
      className={`player-card player-card--${player.color}${
        player.is_alive ? "" : " player-card--out"
      }${isEliminating ? " player-card--eliminating" : ""}`}
      data-player-id={player.id}
    >
      <header className="player-card__header">
        <span className="player-card__character" aria-hidden="true">
          {player.character_emoji}
        </span>
        <h3>{player.nickname}</h3>
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
