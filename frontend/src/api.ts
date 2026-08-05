import type { CreateGameResponse, HealthResponse, PublicGame } from "./types";

interface ErrorResponse {
  detail?: string;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function readJson<T>(response: Response): Promise<T> {
  const payload: unknown = await response.json();
  if (!response.ok) {
    const errorPayload = payload as ErrorResponse | null;
    const message =
      errorPayload && typeof errorPayload.detail === "string"
        ? errorPayload.detail
        : "요청을 처리하지 못했습니다.";
    throw new ApiError(message, response.status);
  }
  return payload as T;
}

function tokenHeaders(playerToken: string): HeadersInit {
  return { "X-Player-Token": playerToken };
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch("/api/health");
  const payload: unknown = await response.json();
  if (!response.ok && response.status !== 503) {
    throw new ApiError("서버 상태를 확인하지 못했습니다.", response.status);
  }
  if (
    typeof payload !== "object" ||
    payload === null ||
    !("status" in payload) ||
    !["ok", "unavailable"].includes(String(payload.status)) ||
    !("api_key_configured" in payload) ||
    typeof payload.api_key_configured !== "boolean"
  ) {
    throw new ApiError("서버 상태 응답이 올바르지 않습니다.", response.status);
  }
  return payload as HealthResponse;
}

export async function createGame(): Promise<CreateGameResponse> {
  return readJson<CreateGameResponse>(
    await fetch("/api/games", { method: "POST" }),
  );
}

export async function submitAnswer(
  gameId: string,
  playerToken: string,
  answer: string,
): Promise<PublicGame> {
  return readJson<PublicGame>(
    await fetch(`/api/games/${gameId}/answers`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...tokenHeaders(playerToken),
      },
      body: JSON.stringify({ answer }),
    }),
  );
}

export async function advanceRound(
  gameId: string,
  playerToken: string,
): Promise<PublicGame> {
  return readJson<PublicGame>(
    await fetch(`/api/games/${gameId}/next`, {
      method: "POST",
      headers: tokenHeaders(playerToken),
    }),
  );
}
