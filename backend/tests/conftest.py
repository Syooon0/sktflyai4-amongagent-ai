from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from app.domain import Game, Player, PlayerRole, Verdict

TEST_QUESTIONS: tuple[str, str, str] = (
    "여행 가서 하루를 통째로 비운다면 뭘 하고 싶어?",
    "갑자기 하루가 25시간이 된다면 어떨 것 같아?",
    "친한 친구가 갑자기 연락이 끊기면 어떤 생각이 들어?",
)


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
        self.question_calls: int = 0

    def answer(self, role: PlayerRole, question: str) -> str:
        self.answer_calls.append((role, question))
        return f"{role} 성향으로 답한 한 줄입니다."

    def generate_questions(self) -> list[str]:
        self.question_calls += 1
        return list(TEST_QUESTIONS)

    def judge(
        self,
        rounds: list[tuple[str, dict[str, str]]],
        history: list[Verdict],
    ) -> FakeJudgeDecision:
        self.judge_calls.append(
            {
                "rounds": [(question, dict(answers)) for question, answers in rounds],
                "history": [verdict.model_copy(deep=True) for verdict in history],
            }
        )
        return FakeJudgeDecision(eliminated_player_id=next(self._decisions))


@pytest.fixture
def game() -> Game:
    return Game(
        game_id="game-graph",
        round_questions=list(TEST_QUESTIONS),
        players=[
            Player(id="player_01", role="human", nickname="수상한 스컹크", token="human-token"),
            Player(id="player_02", role="INTJ", nickname="어색한 수달"),
            Player(id="player_03", role="ENFP", nickname="이상한 토끼"),
            Player(id="player_04", role="ISTP", nickname="괴상한 여우"),
        ],
    )


@pytest.fixture
def fake_gateway_factory():
    return FakeAgentGateway
