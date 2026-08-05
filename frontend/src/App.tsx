import { useEffect, useState } from "react";

import { advanceRound, createGame, getHealth, submitAnswer } from "./api";
import GameBoard from "./components/GameBoard";
import type {
  PlayerId,
  PublicGame,
  RoundPresentationStage,
} from "./types";

type Operation = "start" | "submit" | "next" | null;
type HealthState = "checking" | "ready" | "missing_key" | "unreachable";

interface RoundPresentation {
  result: PublicGame;
  revealOrder: PlayerId[];
  revealedCount: number;
  stage: RoundPresentationStage;
  reducedMotion: boolean;
}

const PRESENTATION_DELAYS = {
  revealing: 500,
  judging: 700,
  verdict: 650,
  eliminating: 450,
  out: 300,
} satisfies Record<RoundPresentationStage, number>;

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "요청을 처리하지 못했습니다.";
}

function stableScore(value: string): number {
  let score = 2166136261;
  for (const character of value) {
    score ^= character.codePointAt(0) ?? 0;
    score = Math.imul(score, 16777619);
  }
  return score >>> 0;
}

function revealOrder(current: PublicGame, result: PublicGame): PlayerId[] {
  const aliveIds = new Set(
    current.players.filter((player) => player.is_alive).map((player) => player.id),
  );
  const roundSeed = `${result.game_id}:${result.round_number}`;
  return result.players
    .filter((player) => aliveIds.has(player.id) && player.answer !== null)
    .map((player) => player.id)
    .sort(
      (left, right) =>
        stableScore(`${roundSeed}:${left}`) - stableScore(`${roundSeed}:${right}`) ||
        left.localeCompare(right),
    );
}

function displayedGame(
  current: PublicGame,
  presentation: RoundPresentation | null,
): PublicGame {
  if (!presentation) return current;

  const visibleAnswers = new Set(
    presentation.revealOrder.slice(0, presentation.revealedCount),
  );
  const showVerdict = ["verdict", "eliminating", "out"].includes(
    presentation.stage,
  );
  const showOut = presentation.stage === "out";

  return {
    ...presentation.result,
    phase: "judging",
    result: null,
    verdict: showVerdict ? presentation.result.verdict : null,
    players: presentation.result.players.map((player) => ({
      ...player,
      answer: visibleAnswers.has(player.id) ? player.answer : null,
      is_alive: showOut
        ? player.is_alive
        : (current.players.find((existing) => existing.id === player.id)?.is_alive ??
          player.is_alive),
    })),
  };
}

export default function App() {
  const [healthState, setHealthState] = useState<HealthState>("checking");
  const [game, setGame] = useState<PublicGame | null>(null);
  const [playerToken, setPlayerToken] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [operation, setOperation] = useState<Operation>(null);
  const [error, setError] = useState<string | null>(null);
  const [presentation, setPresentation] = useState<RoundPresentation | null>(null);

  useEffect(() => {
    let active = true;
    getHealth()
      .then((response) => {
        if (!active) return;
        if (!response.api_key_configured) {
          setHealthState("missing_key");
        } else if (response.status === "ok") {
          setHealthState("ready");
        } else {
          setHealthState("unreachable");
          setError("게임 서버를 사용할 수 없습니다.");
        }
      })
      .catch((healthError: unknown) => {
        if (active) {
          setHealthState("unreachable");
          setError(errorMessage(healthError));
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!presentation) return;

    const delay = presentation.reducedMotion
      ? 0
      : PRESENTATION_DELAYS[presentation.stage];
    const timer = window.setTimeout(() => {
      if (
        presentation.stage === "revealing" &&
        presentation.revealedCount < presentation.revealOrder.length
      ) {
        setPresentation((current) =>
          current === presentation
            ? { ...current, revealedCount: current.revealedCount + 1 }
            : current,
        );
        return;
      }

      const nextStage: Partial<
        Record<RoundPresentationStage, RoundPresentationStage>
      > = {
        revealing: "judging",
        judging: "verdict",
        verdict: "eliminating",
        eliminating: "out",
      };
      const next = nextStage[presentation.stage];
      if (next) {
        setPresentation((current) =>
          current === presentation ? { ...current, stage: next } : current,
        );
        return;
      }

      setGame(presentation.result);
      setPresentation(null);
      setOperation(null);
    }, delay);

    return () => window.clearTimeout(timer);
  }, [presentation]);

  async function handleStart() {
    setOperation("start");
    setError(null);
    try {
      const response = await createGame();
      setGame(response.game);
      setPlayerToken(response.player_token);
      setAnswer("");
      setPresentation(null);
    } catch (startError) {
      setError(errorMessage(startError));
    } finally {
      setOperation(null);
    }
  }

  async function handleSubmit() {
    const trimmedAnswer = answer.trim();
    if (!game || !playerToken || !trimmedAnswer) return;

    setOperation("submit");
    setError(null);
    try {
      const updatedGame = await submitAnswer(
        game.game_id,
        playerToken,
        trimmedAnswer,
      );
      setAnswer("");
      if (updatedGame.phase === "awaiting_answer") {
        setGame(updatedGame);
        setOperation(null);
        return;
      }
      setPresentation({
        result: updatedGame,
        revealOrder: revealOrder(game, updatedGame),
        revealedCount: 0,
        stage: "revealing",
        reducedMotion:
          typeof window.matchMedia === "function" &&
          window.matchMedia("(prefers-reduced-motion: reduce)").matches,
      });
    } catch (submitError) {
      setError(errorMessage(submitError));
      setOperation(null);
    }
  }

  async function handleNextRound() {
    if (!game || !playerToken) return;

    setOperation("next");
    setError(null);
    try {
      setGame(await advanceRound(game.game_id, playerToken));
      setAnswer("");
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setOperation(null);
    }
  }

  function handleRestart() {
    setGame(null);
    setPlayerToken(null);
    setAnswer("");
    setOperation(null);
    setError(null);
    setPresentation(null);
  }

  if (game) {
    const gameForDisplay = displayedGame(game, presentation);
    return (
      <GameBoard
        game={gameForDisplay}
        answer={answer}
        isSubmitting={operation === "submit"}
        isAdvancing={operation === "next"}
        presentationStage={presentation?.stage ?? null}
        eliminatingPlayerId={
          presentation?.stage === "eliminating"
            ? presentation.result.verdict?.eliminated_player_id ?? null
            : null
        }
        error={error}
        onAnswerChange={setAnswer}
        onSubmit={handleSubmit}
        onNextRound={handleNextRound}
        onRestart={handleRestart}
      />
    );
  }

  const serverReady = healthState === "ready";

  return (
    <main className="start-screen">
      <h1>Among Agents</h1>
      <p>AI 셋과 사람 한 명이 답합니다. 판단 에이전트에게 들키지 않고 세 라운드를 버티세요.</p>
      {healthState === "missing_key" && (
        <p role="alert">게임을 시작하려면 backend/.env에 OPENAI_API_KEY를 설정해 주세요.</p>
      )}
      {error && <p role="alert">{error}</p>}
      <button
        type="button"
        disabled={!serverReady || operation === "start"}
        onClick={handleStart}
      >
        {operation === "start" ? "게임 만드는 중…" : "게임 시작"}
      </button>
    </main>
  );
}
