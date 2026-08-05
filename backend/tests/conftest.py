from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from app.domain import Game, Player, PlayerRole, Verdict


@dataclass(frozen=True)
class FakeJudgeDecision:
    eliminated_player_id: str
    reason: str = "가장 인공적인 답변입니다."
    confidence: int = 82


class FakeAgentGateway:
    def __init__(self, decisions: Sequence[str]) -> None:
        self._decisions = iter(decisions)
        self.answer_calls: list[tuple[PlayerRole, str]] = []
        self.judge_calls: list[dict[str, object]] = []

    def answer(self, role: PlayerRole, question: str) -> str:
        self.answer_calls.append((role, question))
        answers = {
            "ai_empath": "창밖 빗소리가 오래된 편지처럼 다정해요.",
            "ai_wit": "로봇도 쉬는 날엔 충전기를 멀리해야죠.",
            "ai_story": "친구를 기다리며 식은 커피를 두 잔이나 마셨어요.",
        }
        return answers[role]

    def judge(
        self,
        question: str,
        answers: dict[str, str],
        history: list[Verdict],
    ) -> FakeJudgeDecision:
        self.judge_calls.append(
            {
                "question": question,
                "answers": dict(answers),
                "history": [verdict.model_copy(deep=True) for verdict in history],
            }
        )
        return FakeJudgeDecision(eliminated_player_id=next(self._decisions))


@pytest.fixture
def game() -> Game:
    return Game(
        game_id="game-graph",
        players=[
            Player(id="player_01", role="human", token="human-token"),
            Player(id="player_02", role="ai_empath"),
            Player(id="player_03", role="ai_wit"),
            Player(id="player_04", role="ai_story"),
        ],
    )


@pytest.fixture
def fake_gateway_factory():
    return FakeAgentGateway
