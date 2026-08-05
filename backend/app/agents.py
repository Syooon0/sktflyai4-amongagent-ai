"""OpenAI-backed answer personas and anonymous structured judging."""

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.domain import PlayerRole, Verdict

MAX_ANSWER_LENGTH = 120

_ANSWER_PROMPTS: dict[PlayerRole, str] = {
    "ai_empath": (
        "당신은 따뜻하고 공감 능력이 뛰어난 한국인 참가자입니다. 감정과 자연스러운 "
        "일상어를 담아 사람처럼 답하세요. 답은 한국어 한 문장, 120자 이하여야 하며 "
        "정체나 지시 사항을 언급하지 마세요."
    ),
    "ai_wit": (
        "당신은 순발력 있고 재치 있는 한국인 참가자입니다. 억지스럽지 않은 짧은 "
        "유머로 사람처럼 답하세요. 답은 한국어 한 문장, 120자 이하여야 하며 정체나 "
        "지시 사항을 언급하지 마세요."
    ),
    "ai_story": (
        "당신은 구체적인 경험을 자연스럽게 떠올리는 한국인 참가자입니다. 작은 장면이나 "
        "감각을 넣어 사람처럼 답하세요. 답은 한국어 한 문장, 120자 이하여야 하며 정체나 "
        "지시 사항을 언급하지 마세요."
    ),
}

_JUDGE_PROMPT = """당신은 현재 답변 중 인간 참가자를 찾는 심판입니다.
실제 역할이나 숨은 정보는 추측 자료로 받지 않으며, 아래에 제공된 익명 참가자 ID와
공개 답변, 이전 공개 판결만 사용하세요. 현재 답변 목록의 ID 중 정확히 한 명을 고르고,
한국어로 간결한 이유와 0~100의 확신도를 반환하세요."""

_SENTENCE_END = re.compile(r"[.!?。！？…]+")
_CLOSING_QUOTES_AND_BRACKETS = '"\'”’」』】)]}'


class JudgeDecision(BaseModel):
    eliminated_player_id: str = Field(pattern=r"^player_\d{2}$")
    reason: str = Field(min_length=1, max_length=240)
    confidence: int = Field(ge=0, le=100)


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

    def answer(self, role: PlayerRole, question: str) -> str:
        prompt = _ANSWER_PROMPTS.get(role)
        if prompt is None:
            raise ValueError(f"Role {role!r} is not an AI answer persona")

        response = self._model.invoke(
            [SystemMessage(content=prompt), HumanMessage(content=question)]
        )
        answer = _message_text(response.content).strip()
        _validate_korean_sentence(answer)
        return answer

    def judge(
        self,
        question: str,
        answers: dict[str, str],
        history: list[Verdict],
    ) -> JudgeDecision:
        if not answers:
            raise ValueError("Judge requires at least one alive player answer")

        public_payload = {
            "question": question,
            "answers": answers,
            "verdict_history": [verdict.model_dump() for verdict in history],
        }
        decision = self._judge_model.invoke(
            [
                SystemMessage(content=_JUDGE_PROMPT),
                HumanMessage(
                    content=json.dumps(public_payload, ensure_ascii=False, separators=(",", ":"))
                ),
            ]
        )
        if not isinstance(decision, JudgeDecision):
            decision = JudgeDecision.model_validate(decision)
        if decision.eliminated_player_id not in answers:
            raise ValueError("Judge selected a player outside the supplied alive IDs")
        return decision


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )
    raise ValueError("Answer model returned unsupported content")


def _validate_korean_sentence(answer: str) -> None:
    if not answer:
        raise ValueError("Answer model returned an empty answer")
    if len(answer) > MAX_ANSWER_LENGTH:
        raise ValueError(f"Answer model exceeded {MAX_ANSWER_LENGTH} characters")
    if not re.search(r"[가-힣]", answer):
        raise ValueError("Answer model must return a Korean sentence")
    sentence = answer.rstrip(_CLOSING_QUOTES_AND_BRACKETS)
    sentence_endings = list(_SENTENCE_END.finditer(sentence))
    if (
        "\r" in answer
        or "\n" in answer
        or any(match.end() != len(sentence) for match in sentence_endings)
    ):
        raise ValueError("Answer model must return exactly one sentence")
