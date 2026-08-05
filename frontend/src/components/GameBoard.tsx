import type { FormEvent } from "react";

import type {
  PlayerId,
  PublicGame,
  RoundPresentationStage,
} from "../types";
import JudgePanel from "./JudgePanel";
import PlayerCard from "./PlayerCard";

interface GameBoardProps {
  game: PublicGame;
  answer: string;
  isSubmitting: boolean;
  isAdvancing: boolean;
  presentationStage: RoundPresentationStage | null;
  eliminatingPlayerId: PlayerId | null;
  error: string | null;
  onAnswerChange: (answer: string) => void;
  onSubmit: () => void;
  onNextRound: () => void;
  onRestart: () => void;
}

const PHASE_LABELS: Record<PublicGame["phase"], string> = {
  awaiting_answer: "답변 대기",
  judging: "판단 중",
  verdict: "판결 공개",
  finished: "게임 종료",
};

function handleSubmit(event: FormEvent, onSubmit: () => void) {
  event.preventDefault();
  onSubmit();
}

export default function GameBoard({
  game,
  answer,
  isSubmitting,
  isAdvancing,
  presentationStage,
  eliminatingPlayerId,
  error,
  onAnswerChange,
  onSubmit,
  onNextRound,
  onRestart,
}: GameBoardProps) {
  const aliveCount = game.players.filter((player) => player.is_alive).length;
  const revealRoles = game.phase === "finished";
  const sortedPlayers = [...game.players].sort((left, right) =>
    left.id.localeCompare(right.id),
  );

  return (
    <main className="game-screen">
      <header className="game-status">
        <h1 className="game-title">Among Agents</h1>
        <span>ROUND {game.round_number} / 3</span>
        <span>생존 {aliveCount}명</span>
        <span>{PHASE_LABELS[game.phase]}</span>
      </header>

      <section className="question-card" aria-labelledby="round-question">
        <p>이번 질문</p>
        <h2 id="round-question">{game.question}</h2>
      </section>

      {error && <p role="alert">{error}</p>}

      <section className="game-board" aria-labelledby="player-arena-heading">
        <h2 id="player-arena-heading" className="game-board__title">
          플레이어 아레나
        </h2>
        {sortedPlayers.map((player) => (
          <PlayerCard
            key={player.id}
            player={player}
            isThinking={
              isSubmitting &&
              (!presentationStage || presentationStage === "revealing") &&
              player.is_alive &&
              !player.is_you &&
              player.answer === null
            }
            isEliminating={player.id === eliminatingPlayerId}
            revealRole={revealRoles}
          />
        ))}
      </section>

      {game.phase === "awaiting_answer" && (
        <form className="answer-form" onSubmit={(event) => handleSubmit(event, onSubmit)}>
          <label htmlFor="answer">한 줄 답변</label>
          <input
            id="answer"
            value={answer}
            maxLength={120}
            disabled={isSubmitting}
            onChange={(event) => onAnswerChange(event.target.value)}
          />
          <button type="submit" disabled={isSubmitting || !answer.trim()}>
            {isSubmitting ? "판단 중…" : "답변 제출"}
          </button>
        </form>
      )}

      <JudgePanel
        isJudging={
          presentationStage === "judging" ||
          (!presentationStage && game.phase === "judging")
        }
        verdict={game.verdict}
      />

      {game.phase === "verdict" && (
        <button type="button" disabled={isAdvancing} onClick={onNextRound}>
          {isAdvancing ? "다음 라운드 준비 중…" : "다음 라운드"}
        </button>
      )}

      {game.phase === "finished" && (
        <section className="game-result">
          <h2>{game.result === "human_won" ? "인간 승리!" : "판단 에이전트 승리!"}</h2>
          <button type="button" onClick={onRestart}>
            다시 시작
          </button>
        </section>
      )}
    </main>
  );
}
