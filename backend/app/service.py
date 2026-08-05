"""Application service for authenticated, in-memory game lifecycles."""

import asyncio
import random
import secrets
from collections.abc import Callable
from uuid import uuid4

from app.agents import AgentGateway, MAX_ANSWER_LENGTH
from app.domain import (
    PLAYER_IDS,
    QUESTIONS,
    Game,
    GamePhase,
    Player,
    PlayerRole,
    PublicGame,
)
from app.graph import run_round


class GameServiceError(Exception):
    """Base class for errors exposed at the application boundary."""


class GameNotFoundError(GameServiceError):
    pass


class InvalidTokenError(GameServiceError):
    pass


class InvalidPhaseError(GameServiceError):
    pass


class AnswerValidationError(GameServiceError):
    pass


class ModelGatewayError(GameServiceError):
    pass


class InMemoryGameRepository:
    """Process-local game storage with one processing lock per game."""

    def __init__(self) -> None:
        self._games: dict[str, Game] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def add(self, game: Game) -> None:
        self._games[game.game_id] = game
        self._locks[game.game_id] = asyncio.Lock()

    def get(self, game_id: str) -> Game:
        try:
            return self._games[game_id]
        except KeyError as error:
            raise GameNotFoundError("Game not found") from error

    def replace(self, game: Game) -> None:
        self._games[game.game_id] = game

    def lock_for(self, game_id: str) -> asyncio.Lock:
        self.get(game_id)
        return self._locks[game_id]


RoundRunner = Callable[[Game, str, AgentGateway], Game]


class GameService:
    def __init__(
        self,
        gateway: AgentGateway,
        *,
        repository: InMemoryGameRepository | None = None,
        round_runner: RoundRunner = run_round,
    ) -> None:
        self._gateway = gateway
        self._repository = repository or InMemoryGameRepository()
        self._round_runner = round_runner

    def create_game(self) -> tuple[PublicGame, str]:
        player_token = secrets.token_urlsafe(32)
        roles: list[PlayerRole] = ["human", "ai_empath", "ai_wit", "ai_story"]
        random.shuffle(roles)
        game = Game(
            game_id=str(uuid4()),
            players=[
                Player(
                    id=player_id,
                    role=role,
                    token=player_token if role == "human" else None,
                )
                for player_id, role in zip(PLAYER_IDS, roles, strict=True)
            ],
        )
        self._repository.add(game)
        return game.to_public(player_token), player_token

    def get_game(self, game_id: str, token: str | None) -> PublicGame:
        game = self._authorized_game(game_id, token)
        return game.to_public(token)

    async def submit_answer(
        self,
        game_id: str,
        token: str | None,
        answer: str,
    ) -> PublicGame:
        game = self._authorized_game(game_id, token)
        normalized_answer = self._validated_answer(answer)
        if game.phase != GamePhase.AWAITING_ANSWER:
            raise InvalidPhaseError("Game is not awaiting an answer")

        lock = self._repository.lock_for(game_id)
        if lock.locked():
            raise InvalidPhaseError("A submission is already being processed")

        async with lock:
            current_game = self._authorized_game(game_id, token)
            if current_game.phase != GamePhase.AWAITING_ANSWER:
                raise InvalidPhaseError("Game is not awaiting an answer")

            original_game = current_game.model_copy(deep=True)
            judging_game = current_game.model_copy(deep=True)
            judging_game.phase = GamePhase.JUDGING
            self._repository.replace(judging_game)

            try:
                completed_game = await asyncio.to_thread(
                    self._round_runner,
                    original_game.model_copy(deep=True),
                    normalized_answer,
                    self._gateway,
                )
            except Exception as error:
                self._repository.replace(original_game)
                raise ModelGatewayError(str(error)) from error

            self._repository.replace(completed_game)
            return completed_game.to_public(token)

    def next_round(self, game_id: str, token: str | None) -> PublicGame:
        game = self._authorized_game(game_id, token)
        if game.phase != GamePhase.VERDICT:
            raise InvalidPhaseError("Game is not ready for the next round")

        next_game = game.model_copy(deep=True)
        next_game.round_number += 1
        next_game.question = QUESTIONS[next_game.round_number - 1]
        next_game.phase = GamePhase.AWAITING_ANSWER
        next_game.verdict = None
        for player in next_game.players:
            player.answer = None
        self._repository.replace(next_game)
        return next_game.to_public(token)

    def _authorized_game(self, game_id: str, token: str | None) -> Game:
        game = self._repository.get(game_id)
        human = next(player for player in game.players if player.role == "human")
        if not token or not secrets.compare_digest(human.token or "", token):
            raise InvalidTokenError("Invalid player token")
        return game

    @staticmethod
    def _validated_answer(answer: str) -> str:
        if not isinstance(answer, str):
            raise AnswerValidationError("Answer must be text")
        normalized = answer.strip()
        if not normalized:
            raise AnswerValidationError("Answer cannot be empty")
        if len(normalized) > MAX_ANSWER_LENGTH:
            raise AnswerValidationError(
                f"Answer cannot exceed {MAX_ANSWER_LENGTH} characters"
            )
        return normalized
