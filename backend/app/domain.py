"""Private game state and the DTOs safe to send to a player."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

PlayerRole = Literal[
    "human",
    "ENFJ", "ENFP", "ENTJ", "ENTP",
    "ESFJ", "ESFP", "ESTJ", "ESTP",
    "INFJ", "INFP", "INTJ", "INTP",
    "ISFJ", "ISFP", "ISTJ", "ISTP",
]
PlayerId = Literal["player_01", "player_02", "player_03", "player_04"]
PlayerColor = Literal["coral", "blue", "yellow", "mint"]

MBTI_TYPES: tuple[PlayerRole, ...] = (
    "ENFJ", "ENFP", "ENTJ", "ENTP",
    "ESFJ", "ESFP", "ESTJ", "ESTP",
    "INFJ", "INFP", "INTJ", "INTP",
    "ISFJ", "ISFP", "ISTJ", "ISTP",
)

PLAYER_IDS: tuple[PlayerId, ...] = (
    "player_01",
    "player_02",
    "player_03",
    "player_04",
)

PLAYER_PRESENTATION: dict[PlayerId, tuple[str, PlayerColor]] = {
    "player_01": ("🤖", "coral"),
    "player_02": ("👾", "blue"),
    "player_03": ("🛸", "yellow"),
    "player_04": ("🦾", "mint"),
}

QUESTIONS: tuple[str, ...] = (
    "비 오는 날 가장 먼저 떠오르는 장면을 한 문장으로 표현해 주세요.",
    "로봇에게도 휴일이 필요하다면 무엇을 하며 보내야 할까요?",
    "친구가 중요한 약속에 한 시간 늦었을 때 첫마디는 무엇인가요?",
)


class GamePhase(str, Enum):
    AWAITING_ANSWER = "awaiting_answer"
    JUDGING = "judging"
    VERDICT = "verdict"
    FINISHED = "finished"


class GameResult(str, Enum):
    HUMAN_WON = "human_won"
    JUDGE_WON = "judge_won"


class Player(BaseModel):
    """Private participant state. Never serialize this model for clients."""

    id: PlayerId
    role: PlayerRole
    token: str | None = None
    answer: str | None = None
    is_alive: bool = True


class Verdict(BaseModel):
    eliminated_player_id: PlayerId
    reason: str
    confidence: int = Field(ge=0, le=100)


class PublicPlayer(BaseModel):
    id: PlayerId
    character_emoji: str
    color: PlayerColor
    is_you: bool
    answer: str | None
    is_alive: bool


class FinishedPublicPlayer(PublicPlayer):
    role: PlayerRole


class PublicGame(BaseModel):
    game_id: str
    round_number: int = Field(ge=1, le=len(QUESTIONS))
    question: str
    phase: GamePhase
    players: list[PublicPlayer | FinishedPublicPlayer]
    verdict: Verdict | None
    verdict_history: list[Verdict]
    result: GameResult | None


class Game(BaseModel):
    """Server-only game state, including the role mapping and player token."""

    game_id: str
    players: list[Player]
    round_number: int = Field(default=1, ge=1, le=len(QUESTIONS))
    question: str = QUESTIONS[0]
    phase: GamePhase = GamePhase.AWAITING_ANSWER
    verdict: Verdict | None = None
    verdict_history: list[Verdict] = Field(default_factory=list)
    result: GameResult | None = None

    def to_public(self, player_token: str) -> PublicGame:
        """Return a new DTO containing only data visible in the current phase."""

        if self.phase == GamePhase.FINISHED:
            public_players: list[PublicPlayer | FinishedPublicPlayer] = [
                FinishedPublicPlayer(
                    id=player.id,
                    character_emoji=PLAYER_PRESENTATION[player.id][0],
                    color=PLAYER_PRESENTATION[player.id][1],
                    is_you=player.token == player_token,
                    answer=player.answer,
                    is_alive=player.is_alive,
                    role=player.role,
                )
                for player in self.players
            ]
        else:
            public_players = [
                PublicPlayer(
                    id=player.id,
                    character_emoji=PLAYER_PRESENTATION[player.id][0],
                    color=PLAYER_PRESENTATION[player.id][1],
                    is_you=player.token == player_token,
                    answer=player.answer,
                    is_alive=player.is_alive,
                )
                for player in self.players
            ]

        return PublicGame(
            game_id=self.game_id,
            round_number=self.round_number,
            question=self.question,
            phase=self.phase,
            players=public_players,
            verdict=self.verdict,
            verdict_history=self.verdict_history,
            result=self.result,
        )
