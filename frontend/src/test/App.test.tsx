import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";

type MockJson = Record<string, unknown>;

const initialGame = {
  game_id: "game-123",
  round_number: 1,
  question: "비 오는 날 가장 먼저 떠오르는 장면을 한 문장으로 표현해 주세요.",
  phase: "awaiting_answer",
  players: [
    { id: "player_01", is_you: false, answer: null, is_alive: true },
    { id: "player_02", is_you: true, answer: null, is_alive: true },
    { id: "player_03", is_you: false, answer: null, is_alive: true },
    { id: "player_04", is_you: false, answer: null, is_alive: true },
  ],
  verdict: null,
  verdict_history: [],
  result: null,
} as const;

const verdictGame = {
  ...initialGame,
  phase: "verdict",
  players: [
    { id: "player_01", is_you: false, answer: "빗소리를 들으며 창밖을 봐요.", is_alive: true },
    { id: "player_02", is_you: true, answer: "우산 위로 빗방울이 춤춰요.", is_alive: true },
    { id: "player_03", is_you: false, answer: "도로 위 네온빛이 번져요.", is_alive: false },
    { id: "player_04", is_you: false, answer: "젖은 흙 냄새가 떠올라요.", is_alive: true },
  ],
  verdict: {
    eliminated_player_id: "player_03",
    reason: "표현이 지나치게 정돈되어 AI처럼 느껴졌어요.",
    confidence: 84,
  },
  verdict_history: [
    {
      eliminated_player_id: "player_03",
      reason: "표현이 지나치게 정돈되어 AI처럼 느껴졌어요.",
      confidence: 84,
    },
  ],
} as const;

const secondRoundGame = {
  ...verdictGame,
  round_number: 2,
  question: "로봇에게도 휴일이 필요하다면 무엇을 하며 보내야 할까요?",
  phase: "awaiting_answer",
  players: verdictGame.players.map((player) => ({ ...player, answer: null })),
  verdict: null,
} as const;

const finishedGame = {
  ...verdictGame,
  phase: "finished",
  result: "human_won",
  players: [
    { ...verdictGame.players[0], role: "ai_empath" },
    { ...verdictGame.players[1], role: "human" },
    { ...verdictGame.players[2], role: "ai_wit" },
    { ...verdictGame.players[3], role: "ai_story" },
  ],
} as const;

function jsonResponse(body: MockJson, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetchSequence(...responses: Response[]) {
  const fetchMock = vi.fn<typeof fetch>();
  for (const response of responses) {
    fetchMock.mockResolvedValueOnce(response);
  }
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("Among Agents arena", () => {
  beforeEach(() => {
    mockFetchSequence(jsonResponse({ status: "ok", api_key_configured: true }));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows the rules and start action before a game exists", async () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "Among Agents" })).toBeInTheDocument();
    expect(screen.getByText(/AI 셋과 사람 한 명/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "게임 시작" })).toBeEnabled();
    });
  });

  it("warns that the server API key must be configured", async () => {
    mockFetchSequence(
      jsonResponse({ status: "unavailable", api_key_configured: false }, 503),
    );

    render(<App />);

    const warning = await screen.findByRole("alert");
    expect(warning).toHaveTextContent("OPENAI_API_KEY");
    expect(warning).toHaveTextContent(".env");
    expect(screen.getByRole("button", { name: "게임 시작" })).toBeDisabled();
  });

  it("submits a trimmed answer and advances only after the next-round action", async () => {
    const fetchMock = mockFetchSequence(
      jsonResponse({ status: "ok", api_key_configured: true }),
      jsonResponse({ game: initialGame, player_token: "secret-token" }, 201),
      jsonResponse(verdictGame),
      jsonResponse(secondRoundGame),
    );
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "게임 시작" }));

    const cards = await screen.findAllByRole("article");
    expect(cards).toHaveLength(4);
    expect(screen.getByText("YOU")).toBeInTheDocument();
    expect(screen.getByText("PLAYER 02").closest("article")).toContainElement(
      screen.getByText("YOU"),
    );

    await user.type(screen.getByLabelText("한 줄 답변"), "  우산 위로 빗방울이 춤춰요.  ");
    await user.click(screen.getByRole("button", { name: "답변 제출" }));

    expect(await screen.findByText("표현이 지나치게 정돈되어 AI처럼 느껴졌어요.")).toBeInTheDocument();
    expect(within(screen.getByText("PLAYER 03").closest("article")!).getByText("OUT")).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "판단 확신도" })).toHaveAttribute("aria-valuenow", "84");
    expect(screen.getByText("ROUND 1 / 3")).toBeInTheDocument();

    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/games/game-123/answers",
      expect.objectContaining({
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Player-Token": "secret-token",
        },
        body: JSON.stringify({ answer: "우산 위로 빗방울이 춤춰요." }),
      }),
    );
    expect(fetchMock).toHaveBeenCalledTimes(3);

    await user.click(screen.getByRole("button", { name: "다음 라운드" }));

    expect(await screen.findByText(secondRoundGame.question)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/api/games/game-123/next",
      expect.objectContaining({
        method: "POST",
        headers: { "X-Player-Token": "secret-token" },
      }),
    );
  });

  it("keeps the current arena when submission fails", async () => {
    mockFetchSequence(
      jsonResponse({ status: "ok", api_key_configured: true }),
      jsonResponse({ game: initialGame, player_token: "secret-token" }, 201),
      jsonResponse({ detail: "Model service unavailable" }, 503),
    );
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "게임 시작" }));
    await user.type(await screen.findByLabelText("한 줄 답변"), "사람 답변입니다.");
    await user.click(screen.getByRole("button", { name: "답변 제출" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Model service unavailable");
    expect(screen.getAllByRole("article")).toHaveLength(4);
    expect(screen.getByLabelText("한 줄 답변")).toHaveValue("사람 답변입니다.");
  });

  it("reveals every role at game end and restarts to the start screen", async () => {
    mockFetchSequence(
      jsonResponse({ status: "ok", api_key_configured: true }),
      jsonResponse({ game: initialGame, player_token: "secret-token" }, 201),
      jsonResponse(finishedGame),
    );
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "게임 시작" }));
    await user.type(await screen.findByLabelText("한 줄 답변"), "우산 위로 빗방울이 춤춰요.");
    await user.click(screen.getByRole("button", { name: "답변 제출" }));

    expect(await screen.findByRole("heading", { name: "인간 승리!" })).toBeInTheDocument();
    expect(screen.getByText("HUMAN")).toBeInTheDocument();
    expect(screen.getByText("AI · 공감형")).toBeInTheDocument();
    expect(screen.getByText("AI · 재치형")).toBeInTheDocument();
    expect(screen.getByText("AI · 경험형")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "다시 시작" }));

    expect(screen.getByRole("button", { name: "게임 시작" })).toBeEnabled();
    expect(screen.queryByRole("heading", { name: "인간 승리!" })).not.toBeInTheDocument();
  });
});
