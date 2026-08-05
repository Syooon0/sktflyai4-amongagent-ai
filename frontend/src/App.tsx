import { useEffect, useState } from "react";

import { advanceRound, createGame, getHealth, submitAnswer } from "./api";
import GameBoard from "./components/GameBoard";
import type { HealthResponse, PublicGame } from "./types";

type Operation = "start" | "submit" | "next" | null;

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "요청을 처리하지 못했습니다.";
}

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [game, setGame] = useState<PublicGame | null>(null);
  const [playerToken, setPlayerToken] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [operation, setOperation] = useState<Operation>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getHealth()
      .then((response) => {
        if (active) setHealth(response);
      })
      .catch((healthError: unknown) => {
        if (active) {
          setHealth({ status: "unavailable", api_key_configured: false });
          setError(errorMessage(healthError));
        }
      });
    return () => {
      active = false;
    };
  }, []);

  async function handleStart() {
    setOperation("start");
    setError(null);
    try {
      const response = await createGame();
      setGame(response.game);
      setPlayerToken(response.player_token);
      setAnswer("");
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
      setGame(updatedGame);
      setAnswer("");
    } catch (submitError) {
      setError(errorMessage(submitError));
    } finally {
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
  }

  if (game) {
    return (
      <GameBoard
        game={game}
        answer={answer}
        isSubmitting={operation === "submit"}
        isAdvancing={operation === "next"}
        error={error}
        onAnswerChange={setAnswer}
        onSubmit={handleSubmit}
        onNextRound={handleNextRound}
        onRestart={handleRestart}
      />
    );
  }

  const serverReady = health?.status === "ok" && health.api_key_configured;

  return (
    <main className="start-screen">
      <h1>Among Agents</h1>
      <p>AI 셋과 사람 한 명이 답합니다. 판단 에이전트에게 들키지 않고 세 라운드를 버티세요.</p>
      {health && !health.api_key_configured && (
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
