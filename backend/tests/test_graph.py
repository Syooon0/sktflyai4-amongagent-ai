from collections import Counter
from collections.abc import Callable, Sequence
from typing import Any

import pytest

from app.graph import run_round
from app.domain import Game, GamePhase, GameResult, QUESTIONS_PER_ROUND
from tests.conftest import TEST_QUESTIONS


def next_round(game: Game) -> Game:
    next_game = game.model_copy(deep=True)
    next_game.round_number += 1
    next_game.round_questions = list(TEST_QUESTIONS)
    next_game.question_index = 0
    next_game.phase = GamePhase.AWAITING_ANSWER
    next_game.verdict = None
    for player in next_game.players:
        player.answer = None
        player.answers = []
    return next_game


def answer_full_round(
    game: Game,
    gateway: object,
    human_answers: Sequence[str] = (
        "첫 번째 질문 답변입니다.",
        "두 번째 질문 답변입니다.",
        "세 번째 질문 답변입니다.",
    ),
) -> Game:
    """Submit all three questions of the round; judge only fires on the last one."""

    current = game
    for human_answer in human_answers:
        current = run_round(current, human_answer, gateway)
    return current


def test_first_two_questions_await_the_next_answer_without_judging(
    game: Game,
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    gateway = fake_gateway_factory(["player_02"])

    after_q1 = run_round(game, "첫 번째 질문 답변입니다.", gateway)
    assert after_q1.phase == GamePhase.AWAITING_ANSWER
    assert after_q1.question_index == 1
    assert gateway.judge_calls == []

    after_q2 = run_round(after_q1, "두 번째 질문 답변입니다.", gateway)
    assert after_q2.phase == GamePhase.AWAITING_ANSWER
    assert after_q2.question_index == 2
    assert gateway.judge_calls == []
    assert Counter(role for role, _ in gateway.answer_calls) == Counter(
        {"INTJ": 2, "ENFP": 2, "ISTP": 2}
    )


def test_third_question_calls_each_alive_ai_once_and_anonymizes_judge_payload(
    game: Game,
    fake_gateway_factory: Callable[[Sequence[str]], object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def put_highest_player_id_first(items: list[Any]) -> None:
        items.sort(reverse=True)

    monkeypatch.setattr("app.graph.random.shuffle", put_highest_player_id_first)
    gateway = fake_gateway_factory(["player_02"])

    result = answer_full_round(game, gateway)

    assert Counter(role for role, _ in gateway.answer_calls) == Counter(
        {"INTJ": QUESTIONS_PER_ROUND, "ENFP": QUESTIONS_PER_ROUND, "ISTP": QUESTIONS_PER_ROUND}
    )
    assert len(gateway.judge_calls) == 1
    judge_payload = gateway.judge_calls[0]
    assert [question for question, _ in judge_payload["rounds"]] == list(TEST_QUESTIONS)
    for _, anonymous_answers in judge_payload["rounds"]:
        assert set(anonymous_answers) == {"player_01", "player_02", "player_03", "player_04"}
        assert list(anonymous_answers) == ["player_04", "player_03", "player_02", "player_01"]
        assert not set(anonymous_answers) & {"human", "INTJ", "ENFP", "ISTP"}
    assert judge_payload["history"] == []
    assert result.phase == GamePhase.VERDICT


def test_removed_ai_is_not_called_or_judged_in_the_next_round(
    game: Game,
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    gateway = fake_gateway_factory(["player_02", "player_03"])
    first_result = answer_full_round(game, gateway)
    gateway.answer_calls.clear()

    second_result = answer_full_round(next_round(first_result), gateway)

    assert Counter(role for role, _ in gateway.answer_calls) == Counter(
        {"ENFP": QUESTIONS_PER_ROUND, "ISTP": QUESTIONS_PER_ROUND}
    )
    assert "player_02" not in dict(gateway.judge_calls[1]["rounds"][0][1])
    assert gateway.judge_calls[1]["history"] == [first_result.verdict]
    assert second_result.verdict is not None
    assert second_result.verdict.eliminated_player_id == "player_03"


def test_removing_human_ends_game_with_judge_win(
    game: Game,
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    result = answer_full_round(game, fake_gateway_factory(["player_01"]))

    assert result.phase == GamePhase.FINISHED
    assert result.result == GameResult.JUDGE_WON
    assert next(player for player in result.players if player.role == "human").is_alive is False


def test_human_surviving_third_verdict_wins(
    game: Game,
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    gateway = fake_gateway_factory(["player_02", "player_03", "player_04"])

    result = answer_full_round(game, gateway)
    result = answer_full_round(next_round(result), gateway)
    result = answer_full_round(next_round(result), gateway)

    assert result.phase == GamePhase.FINISHED
    assert result.result == GameResult.HUMAN_WON
    assert len(result.verdict_history) == 3
    assert next(player for player in result.players if player.role == "human").is_alive is True


def test_invalid_judge_selection_is_rejected_without_mutating_final_answers(
    game: Game,
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    gateway = fake_gateway_factory(["player_99"])
    mid_round = run_round(game, "첫 번째 질문 답변입니다.", gateway)
    mid_round = run_round(mid_round, "두 번째 질문 답변입니다.", gateway)

    with pytest.raises(ValueError, match="alive player"):
        run_round(mid_round, "세 번째 질문 답변입니다.", gateway)
