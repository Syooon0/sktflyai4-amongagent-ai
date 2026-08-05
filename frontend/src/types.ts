export type PlayerId = "player_01" | "player_02" | "player_03" | "player_04";

export type PlayerRole = "human" | "ai_empath" | "ai_wit" | "ai_story";

export type GamePhase = "awaiting_answer" | "judging" | "verdict" | "finished";

export type GameResult = "human_won" | "judge_won";

export interface Verdict {
  eliminated_player_id: PlayerId;
  reason: string;
  confidence: number;
}

export interface PublicPlayer {
  id: PlayerId;
  is_you: boolean;
  answer: string | null;
  is_alive: boolean;
  role?: PlayerRole;
}

export interface PublicGame {
  game_id: string;
  round_number: number;
  question: string;
  phase: GamePhase;
  players: PublicPlayer[];
  verdict: Verdict | null;
  verdict_history: Verdict[];
  result: GameResult | null;
}

export interface HealthResponse {
  status: "ok" | "unavailable";
  api_key_configured: boolean;
}

export interface CreateGameResponse {
  game: PublicGame;
  player_token: string;
}
