import asyncio
from collections.abc import Callable, Sequence
from threading import Event

import pytest

from app.domain import GamePhase, QUESTIONS
from app.service import (
    AnswerValidationError,
    GameNotFoundError,
    GameService,
    InvalidPhaseError,
    InvalidTokenError,
    ModelGatewayError,
)


def service_with_human_in_first_slot(
    monkeypatch: pytest.MonkeyPatch,
    gateway: object,
) -> GameService:
    monkeypatch.setattr("app.service.random.shuffle", lambda roles: None)
    return GameService(gateway)  # type: ignore[arg-type]


def test_create_game_assigns_one_random_human_slot_and_separate_opaque_token(
    monkeypatch: pytest.MonkeyPatch,
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    shuffle_calls = 0

    def reverse_roles(roles: list[str]) -> None:
        nonlocal shuffle_calls
        shuffle_calls += 1
        roles.reverse()

    monkeypatch.setattr("app.service.random.shuffle", reverse_roles)
    service = GameService(fake_gateway_factory(["player_02"]))  # type: ignore[arg-type]

    first_game, first_token = service.create_game()
    second_game, second_token = service.create_game()

    assert first_game.game_id != second_game.game_id
    assert first_token != second_token
    assert first_token not in {first_game.game_id, second_game.game_id}
    assert len(first_token) >= 32
    assert first_game.phase == GamePhase.AWAITING_ANSWER
    assert first_game.question == QUESTIONS[0]
    assert len(first_game.players) == 4
    assert shuffle_calls == 2
    assert [player.id for player in first_game.players if player.is_you] == ["player_04"]
    assert [
        (player.id, player.character_emoji, player.color)
        for player in first_game.players
    ] == [
        ("player_01", "🤖", "coral"),
        ("player_02", "👾", "blue"),
        ("player_03", "🛸", "yellow"),
        ("player_04", "🦾", "mint"),
    ]
    assert all("role" not in player.model_dump() for player in first_game.players)


def test_get_game_requires_the_issuing_token_and_existing_game(
    monkeypatch: pytest.MonkeyPatch,
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    service = service_with_human_in_first_slot(
        monkeypatch, fake_gateway_factory(["player_02"])
    )
    game, token = service.create_game()

    assert service.get_game(game.game_id, token) == game
    with pytest.raises(InvalidTokenError):
        service.get_game(game.game_id, "wrong-token")
    with pytest.raises(InvalidTokenError):
        service.get_game(game.game_id, None)
    with pytest.raises(GameNotFoundError):
        service.get_game("missing-game", token)


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", ["", "  \n\t  ", "가" * 121])
async def test_submit_answer_rejects_empty_or_over_120_characters(
    monkeypatch: pytest.MonkeyPatch,
    fake_gateway_factory: Callable[[Sequence[str]], object],
    answer: str,
) -> None:
    service = service_with_human_in_first_slot(
        monkeypatch, fake_gateway_factory(["player_02"])
    )
    game, token = service.create_game()

    with pytest.raises(AnswerValidationError):
        await service.submit_answer(game.game_id, token, answer)

    assert service.get_game(game.game_id, token).phase == GamePhase.AWAITING_ANSWER


@pytest.mark.asyncio
async def test_submit_trims_answer_rejects_duplicate_and_next_advances_round(
    monkeypatch: pytest.MonkeyPatch,
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    service = service_with_human_in_first_slot(
        monkeypatch, fake_gateway_factory(["player_02", "player_03"])
    )
    game, token = service.create_game()

    verdict_game = await service.submit_answer(
        game.game_id, token, "  사람이 쓴 첫 답변입니다.  "
    )

    assert verdict_game.phase == GamePhase.VERDICT
    assert next(player for player in verdict_game.players if player.is_you).answer == (
        "사람이 쓴 첫 답변입니다."
    )
    with pytest.raises(InvalidPhaseError):
        await service.submit_answer(game.game_id, token, "중복 답변입니다.")

    next_game = service.next_round(game.game_id, token)
    assert next_game.round_number == 2
    assert next_game.question == QUESTIONS[1]
    assert next_game.phase == GamePhase.AWAITING_ANSWER
    assert next_game.verdict is None
    assert all(player.answer is None for player in next_game.players)
    with pytest.raises(InvalidPhaseError):
        service.next_round(game.game_id, token)


@pytest.mark.asyncio
async def test_gateway_failure_restores_state_and_allows_retry(
    monkeypatch: pytest.MonkeyPatch,
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    class FailsOnceGateway:
        def __init__(self) -> None:
            self.failed = False
            self.fallback = fake_gateway_factory(["player_02"])

        def answer(self, role: str, question: str) -> str:
            if not self.failed:
                self.failed = True
                raise RuntimeError("model unavailable")
            return self.fallback.answer(role, question)

        def judge(self, question: str, answers: dict[str, str], history: list[object]):
            return self.fallback.judge(question, answers, history)

    service = service_with_human_in_first_slot(monkeypatch, FailsOnceGateway())
    game, token = service.create_game()

    with pytest.raises(ModelGatewayError, match="model unavailable"):
        await service.submit_answer(game.game_id, token, "재시도할 답변입니다.")

    restored = service.get_game(game.game_id, token)
    assert restored == game
    assert restored.phase == GamePhase.AWAITING_ANSWER

    retried = await service.submit_answer(
        game.game_id, token, "재시도할 답변입니다."
    )
    assert retried.phase == GamePhase.VERDICT


@pytest.mark.asyncio
async def test_concurrent_submission_is_rejected_while_first_is_processing(
    monkeypatch: pytest.MonkeyPatch,
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    started = Event()
    release = Event()
    fallback = fake_gateway_factory(["player_02"])

    class BlockingGateway:
        def answer(self, role: str, question: str) -> str:
            started.set()
            assert release.wait(timeout=2)
            return fallback.answer(role, question)

        def judge(self, question: str, answers: dict[str, str], history: list[object]):
            return fallback.judge(question, answers, history)

    service = service_with_human_in_first_slot(monkeypatch, BlockingGateway())
    game, token = service.create_game()
    first = asyncio.create_task(
        service.submit_answer(game.game_id, token, "첫 번째 답변입니다.")
    )
    assert await asyncio.to_thread(started.wait, 2)

    with pytest.raises(InvalidPhaseError):
        await service.submit_answer(game.game_id, token, "두 번째 답변입니다.")

    release.set()
    assert (await first).phase == GamePhase.VERDICT


@pytest.mark.asyncio
async def test_cancelled_submission_restores_the_pre_submit_state(
    monkeypatch: pytest.MonkeyPatch,
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    started = Event()
    release = Event()

    def blocking_round(game, answer, gateway):
        started.set()
        assert release.wait(timeout=2)
        return game

    monkeypatch.setattr("app.service.random.shuffle", lambda roles: None)
    service = GameService(
        fake_gateway_factory(["player_02"]),  # type: ignore[arg-type]
        round_runner=blocking_round,
    )
    game, token = service.create_game()
    submission = asyncio.create_task(
        service.submit_answer(game.game_id, token, "취소할 답변입니다.")
    )
    assert await asyncio.to_thread(started.wait, 2)

    submission.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await submission

    assert service.get_game(game.game_id, token) == game


def test_next_round_requires_token_existing_game_and_verdict_phase(
    monkeypatch: pytest.MonkeyPatch,
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    service = service_with_human_in_first_slot(
        monkeypatch, fake_gateway_factory(["player_02"])
    )
    game, token = service.create_game()

    with pytest.raises(InvalidTokenError):
        service.next_round(game.game_id, "wrong-token")
    with pytest.raises(GameNotFoundError):
        service.next_round("missing-game", token)
    with pytest.raises(InvalidPhaseError):
        service.next_round(game.game_id, token)
