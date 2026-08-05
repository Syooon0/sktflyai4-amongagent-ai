"""OpenAI-backed answer personas and anonymous structured judging."""

import json
import re
from typing import Any

from httpx import HTTPError
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from openai import OpenAIError
from pydantic import BaseModel, Field, ValidationError

from app.domain import MBTI_TYPES, PlayerRole, Verdict

MAX_ANSWER_LENGTH = 120
_OUTPUT_ATTEMPTS = 2

_ANSWER_TEMPERATURES: dict[PlayerRole, float] = {
    role: (0.95 if role.endswith("P") else 0.6) for role in MBTI_TYPES
}

_MBTI_TRAITS: dict[PlayerRole, str] = {
    "INTJ": "전략적이고 간결하게 핵심만 말하는",
    "INTP": "호기심 많고 분석적으로 이것저것 따져보는",
    "ENTJ": "자신감 있고 단호하게 방향을 제시하는",
    "ENTP": "재치있게 반박하고 새 아이디어를 던지는",
    "INFJ": "통찰력 있고 은유적으로 진심을 담아 말하는",
    "INFP": "감성적이고 진솔하게 자기 생각을 표현하는",
    "ENFJ": "따뜻하게 상대를 챙기며 격려하는",
    "ENFP": "발랄하고 즉흥적으로 감탄사를 섞어 말하는",
    "ISTJ": "차분하고 사실 위주로 정확하게 말하는",
    "ISFJ": "다정하고 배려 깊게 조심스럽게 말하는",
    "ESTJ": "단호하고 실용적으로 결론부터 말하는",
    "ESFJ": "사교적이고 상냥하게 분위기를 살피며 말하는",
    "ISTP": "무심한 듯 간결하게 실용적으로 말하는",
    "ISFP": "부드럽고 감각적으로 소소한 순간을 묘사하는",
    "ESTP": "활기차고 즉각적으로 행동 중심으로 말하는",
    "ESFP": "쾌활하고 유쾌하게 리액션 크게 말하는",
}

_ANSWER_PROMPTS: dict[PlayerRole, str] = {
    role: (
        f"당신은 {trait} 한국인 참가자입니다. 이 성향으로 사람처럼 답하세요. "
        "답은 한국어 한 문장, 120자 이하여야 하며 정체나 지시 사항을 언급하지 마세요."
    )
    for role, trait in _MBTI_TRAITS.items()
}

_JUDGE_PROMPT = """당신은 여러 질문에 걸친 답변 중 인간 참가자를 찾는 심판입니다.
실제 역할이나 숨은 정보는 추측 자료로 받지 않으며, 아래에 제공된 질문별 익명 참가자
ID와 공개 답변, 이전 공개 판결만 사용하세요. 세 질문에 대한 답변 전체를 종합해
현재 참가자 ID 중 정확히 한 명을 고르고, 한국어로 간결한 이유와 0~100의 확신도를
반환하세요."""

_QUESTION_PROMPT = """당신은 한국어 파티 게임의 질문 출제자입니다. 서로 다른 소재의
가볍고 캐주얼한 일상 질문 세 개를 만드세요. 각 질문은 한국어 한 문장이며, 답하는
사람이 자연스럽게 한 줄로 답할 수 있어야 합니다."""


class QuestionSet(BaseModel):
    questions: list[str] = Field(min_length=3, max_length=3)

_SENTENCE_END = re.compile(r"[.!?。！？…]+")
_CLOSING_QUOTES_AND_BRACKETS = '"\'”’」』】)]}'


class JudgeDecision(BaseModel):
    eliminated_player_id: str = Field(pattern=r"^player_\d{2}$")
    reason: str = Field(min_length=1, max_length=240)
    confidence: int = Field(ge=0, le=100)


class AgentGatewayError(Exception):
    """Known model invocation or output failures safe for service translation."""


class ModelInvocationError(AgentGatewayError):
    pass


class ModelOutputError(AgentGatewayError, ValueError):
    pass


class AgentGateway:
    """Small synchronous boundary around the OpenAI chat model."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-4.1-mini",
        timeout_seconds: float = 30.0,
    ) -> None:
        self._model = ChatOpenAI(
            api_key=api_key,
            model=model,
            timeout=timeout_seconds,
            max_retries=1,
        )
        self._judge_model = self._model.with_structured_output(JudgeDecision)
        self._question_model = self._model.with_structured_output(QuestionSet)

    def generate_questions(self) -> list[str]:
        messages = [
            SystemMessage(content=_QUESTION_PROMPT),
            HumanMessage(content="세 개의 질문을 만들어 주세요."),
        ]
        for attempt in range(_OUTPUT_ATTEMPTS):
            try:
                result = _invoke(self._question_model, messages)
                if not isinstance(result, QuestionSet):
                    result = QuestionSet.model_validate(result)
                for question in result.questions:
                    _validate_korean_sentence(question)
                return result.questions
            except (ValidationError, OutputParserException, ModelOutputError) as error:
                if attempt == _OUTPUT_ATTEMPTS - 1:
                    raise ModelOutputError(
                        "Question model returned invalid structured output"
                    ) from error
        raise AssertionError("question output retry loop exhausted")

    def answer(self, role: PlayerRole, question: str) -> str:
        prompt = _ANSWER_PROMPTS.get(role)
        if prompt is None:
            raise ValueError(f"Role {role!r} is not an AI answer persona")

        messages = [SystemMessage(content=prompt), HumanMessage(content=question)]
        model = self._model.bind(temperature=_ANSWER_TEMPERATURES[role])
        for attempt in range(_OUTPUT_ATTEMPTS):
            response = _invoke(model, messages)
            try:
                answer = _message_text(response.content).strip()
                _validate_korean_sentence(answer)
                return answer
            except ModelOutputError:
                if attempt == _OUTPUT_ATTEMPTS - 1:
                    raise
        raise AssertionError("answer output retry loop exhausted")

    def judge(
        self,
        rounds: list[tuple[str, dict[str, str]]],
        history: list[Verdict],
    ) -> JudgeDecision:
        if not rounds or not rounds[0][1]:
            raise ValueError("Judge requires at least one alive player answer")
        alive_ids = set(rounds[0][1])

        public_payload = {
            "rounds": [
                {"question": question, "answers": answers} for question, answers in rounds
            ],
            "verdict_history": [verdict.model_dump() for verdict in history],
        }
        messages = [
            SystemMessage(content=_JUDGE_PROMPT),
            HumanMessage(
                content=json.dumps(public_payload, ensure_ascii=False, separators=(",", ":"))
            ),
        ]
        for attempt in range(_OUTPUT_ATTEMPTS):
            try:
                decision = _invoke(self._judge_model, messages)
                if not isinstance(decision, JudgeDecision):
                    decision = JudgeDecision.model_validate(decision)
                if decision.eliminated_player_id not in alive_ids:
                    raise ModelOutputError(
                        "Judge selected a player outside the supplied alive IDs"
                    )
                return decision
            except (ValidationError, OutputParserException) as error:
                output_error = ModelOutputError(
                    "Judge model returned invalid structured output"
                )
                if attempt == _OUTPUT_ATTEMPTS - 1:
                    raise output_error from error
            except ModelOutputError:
                if attempt == _OUTPUT_ATTEMPTS - 1:
                    raise
        raise AssertionError("judge output retry loop exhausted")


def _invoke(model: Any, messages: list[Any]) -> Any:
    try:
        return model.invoke(messages)
    except (OpenAIError, HTTPError, TimeoutError) as error:
        raise ModelInvocationError(str(error)) from error


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )
    raise ModelOutputError("Answer model returned unsupported content")


def _validate_korean_sentence(answer: str) -> None:
    if not answer:
        raise ModelOutputError("Answer model returned an empty answer")
    if len(answer) > MAX_ANSWER_LENGTH:
        raise ModelOutputError(f"Answer model exceeded {MAX_ANSWER_LENGTH} characters")
    if not re.search(r"[가-힣]", answer):
        raise ModelOutputError("Answer model must return a Korean sentence")
    sentence = answer.rstrip(_CLOSING_QUOTES_AND_BRACKETS)
    sentence_endings = list(_SENTENCE_END.finditer(sentence))
    if (
        "\r" in answer
        or "\n" in answer
        or any(match.end() != len(sentence) for match in sentence_endings)
    ):
        raise ModelOutputError("Answer model must return exactly one sentence")
