import json
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from app.agents import AgentGateway, JudgeDecision, ModelOutputError, QuestionSet
from app.domain import Verdict


class StubRunnable:
    def __init__(self, responses: Sequence[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[list[Any]] = []
        self.binds: list[dict[str, Any]] = []

    def bind(self, **kwargs: Any) -> "StubRunnable":
        self.binds.append(kwargs)
        return self

    def invoke(self, messages: list[Any]) -> Any:
        self.calls.append(messages)
        return self.responses.pop(0)


class StubChatModel(StubRunnable):
    def __init__(
        self,
        answer_contents: Sequence[Any],
        judge_responses: Sequence[Any],
        question_responses: Sequence[Any] = (),
    ) -> None:
        super().__init__([SimpleNamespace(content=content) for content in answer_contents])
        self.judge_model = StubRunnable(judge_responses)
        self.question_model = StubRunnable(question_responses)
        self.structured_schemas: list[type[Any]] = []

    def with_structured_output(self, schema: type[Any]) -> StubRunnable:
        self.structured_schemas.append(schema)
        return self.judge_model if schema is JudgeDecision else self.question_model


def gateway_with_stub(
    monkeypatch: pytest.MonkeyPatch,
    *,
    answer_contents: Sequence[Any] = (),
    judge_responses: Sequence[Any] = (),
    question_responses: Sequence[Any] = (),
) -> tuple[AgentGateway, StubChatModel, dict[str, Any]]:
    model = StubChatModel(answer_contents, judge_responses, question_responses)
    constructor_kwargs: dict[str, Any] = {}

    def build_chat_model(**kwargs: Any) -> StubChatModel:
        constructor_kwargs.update(kwargs)
        return model

    monkeypatch.setattr("app.agents.ChatOpenAI", build_chat_model)
    gateway = AgentGateway(
        "test-api-key",
        model="test-model",
        timeout_seconds=12.5,
    )
    return gateway, model, constructor_kwargs


def test_gateway_configures_model_and_uses_distinct_persona_prompts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway, model, constructor_kwargs = gateway_with_stub(
        monkeypatch,
        answer_contents=[
            "비 오는 날에는 창가에서 빗소리를 들어요.",
            [{"type": "text", "text": "로봇도 쉬는 날엔 충전기를 멀리해야죠!"}],
            "“친구를 기다리며 식은 커피를 두 잔 마셨어요.”",
        ],
    )

    answers = [
        gateway.answer("INTJ", "같은 질문"),
        gateway.answer("ENFP", "같은 질문"),
        gateway.answer("ISTP", "같은 질문"),
    ]

    assert constructor_kwargs == {
        "api_key": "test-api-key",
        "model": "test-model",
        "timeout": 12.5,
        "max_retries": 1,
    }
    assert answers == [
        "비 오는 날에는 창가에서 빗소리를 들어요.",
        "로봇도 쉬는 날엔 충전기를 멀리해야죠!",
        "“친구를 기다리며 식은 커피를 두 잔 마셨어요.”",
    ]
    prompts = [messages[0].content for messages in model.calls]
    assert len(set(prompts)) == 3
    assert "효율" in prompts[0]
    assert "가능성" in prompts[1]
    assert "원인과 결과" in prompts[2]
    assert all("한국어 한 문장" in prompt and "120자" in prompt for prompt in prompts)
    assert [messages[1].content for messages in model.calls] == ["같은 질문"] * 3
    assert model.binds == [
        {"temperature": 0.6},
        {"temperature": 0.95},
        {"temperature": 0.95},
    ]
    assert model.structured_schemas == [JudgeDecision, QuestionSet]


@pytest.mark.parametrize(
    ("model_content", "message"),
    [
        ("   ", "empty"),
        ("This answer is English.", "Korean"),
        ("가" * 121, "120 characters"),
        ("비가 와요. 우산을 써요.", "one sentence"),
        ("비가 오면\r우산을 써요", "one sentence"),
    ],
)
def test_gateway_rejects_invalid_answer_content(
    monkeypatch: pytest.MonkeyPatch,
    model_content: str,
    message: str,
) -> None:
    gateway, model, _ = gateway_with_stub(
        monkeypatch, answer_contents=[model_content, model_content]
    )

    with pytest.raises(ModelOutputError, match=message):
        gateway.answer("INTJ", "질문")

    assert len(model.calls) == 2


def test_gateway_retries_only_the_invalid_answer_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway, model, _ = gateway_with_stub(
        monkeypatch,
        answer_contents=["This answer is English.", "비 오는 창가를 바라봐요."],
    )

    answer = gateway.answer("INTJ", "질문")

    assert answer == "비 오는 창가를 바라봐요."
    assert len(model.calls) == 2


def test_gateway_rejects_human_role_without_calling_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway, model, _ = gateway_with_stub(monkeypatch)

    with pytest.raises(ValueError, match="not an AI answer persona"):
        gateway.answer("human", "질문")

    assert model.calls == []


def test_gateway_uses_structured_judge_output_with_only_public_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway, model, _ = gateway_with_stub(
        monkeypatch,
        judge_responses=[
            {
                "eliminated_player_id": "player_03",
                "reason": "표현이 지나치게 정돈되어 있습니다.",
                "confidence": 74,
            }
        ],
    )
    answers = {
        "player_01": "창밖을 봐요.",
        "player_03": "빗소리를 들어요.",
    }
    history = [
        Verdict(
            eliminated_player_id="player_02",
            reason="이전 공개 판결입니다.",
            confidence=61,
        )
    ]

    decision = gateway.judge([("오늘의 질문", answers)], history)

    assert decision == JudgeDecision(
        eliminated_player_id="player_03",
        reason="표현이 지나치게 정돈되어 있습니다.",
        confidence=74,
    )
    payload = json.loads(model.judge_model.calls[0][1].content)
    assert payload == {
        "rounds": [{"question": "오늘의 질문", "answers": answers}],
        "verdict_history": [history[0].model_dump(mode="json")],
    }
    assert not {"role", "prompt", "persona"} & payload.keys()


def test_gateway_rejects_judge_id_outside_supplied_alive_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway, _, _ = gateway_with_stub(
        monkeypatch,
        judge_responses=[
            JudgeDecision(
                eliminated_player_id="player_04",
                reason="선택 이유입니다.",
                confidence=50,
            ),
            JudgeDecision(
                eliminated_player_id="player_04",
                reason="선택 이유입니다.",
                confidence=50,
            ),
        ],
    )

    with pytest.raises(ModelOutputError, match="outside the supplied alive IDs"):
        gateway.judge([("질문", {"player_01": "답변"})], [])


def test_gateway_validates_structured_judge_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway, model, _ = gateway_with_stub(
        monkeypatch,
        judge_responses=[
            {
                "eliminated_player_id": "player_01",
                "reason": "선택 이유입니다.",
                "confidence": 101,
            },
            {
                "eliminated_player_id": "player_01",
                "reason": "선택 이유입니다.",
                "confidence": 101,
            },
        ],
    )

    with pytest.raises(ModelOutputError) as error:
        gateway.judge([("질문", {"player_01": "답변"})], [])

    assert isinstance(error.value.__cause__, ValidationError)
    assert len(model.judge_model.calls) == 2


def test_gateway_retries_only_the_invalid_judge_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway, model, _ = gateway_with_stub(
        monkeypatch,
        judge_responses=[
            {
                "eliminated_player_id": "player_01",
                "reason": "확신도가 잘못되었습니다.",
                "confidence": 101,
            },
            {
                "eliminated_player_id": "player_01",
                "reason": "선택 이유입니다.",
                "confidence": 73,
            },
        ],
    )

    decision = gateway.judge([("질문", {"player_01": "답변"})], [])

    assert decision.confidence == 73
    assert len(model.judge_model.calls) == 2
