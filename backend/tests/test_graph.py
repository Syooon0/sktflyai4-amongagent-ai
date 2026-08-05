from collections import Counter
from collections.abc import Callable, Sequence
from typing import Any

import pytest

from app.graph import run_round
from app.domain import Game, GamePhase, GameResult, PlayerRole, QUESTIONS


def next_round(game: Game) -> Game:
    next_game = game.model_copy(deep=True)
    next_game.round_number += 1
    next_game.question = QUESTIONS[next_game.round_number - 1]
    next_game.phase = GamePhase.AWAITING_ANSWER
    next_game.verdict = None
    for player in next_game.players:
        player.answer = None
    return next_game


def test_round_one_calls_each_alive_ai_once_and_anonymizes_judge_payload(
    game: Game,
    fake_gateway_factory: Callable[[Sequence[str]], object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def put_highest_player_id_first(items: list[Any]) -> None:
        items.sort(reverse=True)

    monkeypatch.setattr("app.graph.random.shuffle", put_highest_player_id_first)
    gateway = fake_gateway_factory(["player_02"])

    result = run_round(game, "빗소리를 들으며 따뜻한 차를 마셔요.", gateway)

    assert Counter(role for role, _ in gateway.answer_calls) == Counter(
        {"INTJ": 1, "ENFP": 1, "ISTP": 1}
    )
    assert {question for _, question in gateway.answer_calls} == {QUESTIONS[0]}
    assert len(gateway.judge_calls) == 1
    judge_payload = gateway.judge_calls[0]
    assert judge_payload["question"] == QUESTIONS[0]
    assert set(judge_payload["answers"]) == {
        "player_01",
        "player_02",
        "player_03",
        "player_04",
    }
    assert list(judge_payload["answers"]) == [
        "player_04",
        "player_03",
        "player_02",
        "player_01",
    ]
    assert not set(judge_payload["answers"]) & {
        "human",
        "INTJ",
        "ENFP",
        "ISTP",
    }
    assert judge_payload["history"] == []
    assert result.phase == GamePhase.VERDICT


def test_removed_ai_is_not_called_or_judged_in_the_next_round(
    game: Game,
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    gateway = fake_gateway_factory(["player_02", "player_03"])
    first_result = run_round(game, "첫 번째 사람 답변입니다.", gateway)
    gateway.answer_calls.clear()

    second_result = run_round(
        next_round(first_result),
        "두 번째 사람 답변입니다.",
        gateway,
    )

    assert Counter(role for role, _ in gateway.answer_calls) == Counter(
        {"ENFP": 1, "ISTP": 1}
    )
    assert "player_02" not in gateway.judge_calls[1]["answers"]
    assert gateway.judge_calls[1]["history"] == [first_result.verdict]
    assert second_result.verdict is not None
    assert second_result.verdict.eliminated_player_id == "player_03"


def test_removing_human_ends_game_with_judge_win(
    game: Game,
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    result = run_round(
        game,
        "사람답게 쓴 답변이에요.",
        fake_gateway_factory(["player_01"]),
    )

    assert result.phase == GamePhase.FINISHED
    assert result.result == GameResult.JUDGE_WON
    assert next(player for player in result.players if player.role == "human").is_alive is False


def test_human_surviving_third_verdict_wins(
    game: Game,
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    gateway = fake_gateway_factory(["player_02", "player_03", "player_04"])

    result = run_round(game, "첫 번째 사람 답변입니다.", gateway)
    result = run_round(next_round(result), "두 번째 사람 답변입니다.", gateway)
    result = run_round(next_round(result), "세 번째 사람 답변입니다.", gateway)

    assert result.phase == GamePhase.FINISHED
    assert result.result == GameResult.HUMAN_WON
    assert len(result.verdict_history) == 3
    assert next(player for player in result.players if player.role == "human").is_alive is True


def test_invalid_judge_selection_is_rejected_without_mutating_game(
    game: Game,
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    with pytest.raises(ValueError, match="alive player"):
        run_round(
            game,
            "사람 답변입니다.",
            fake_gateway_factory(["player_99"]),
        )

    assert game.phase == GamePhase.AWAITING_ANSWER
    assert game.verdict_history == []
    assert all(player.is_alive and player.answer is None for player in game.players)
