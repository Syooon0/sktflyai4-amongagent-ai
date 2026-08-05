"""Typed LangGraph workflow for one complete judging round."""

import random
from collections.abc import Callable, Sequence
from typing import Annotated, Literal, NotRequired, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.agents import AgentGateway, JudgeDecision
from app.domain import (
    QUESTIONS,
    Game,
    GamePhase,
    GameResult,
    PlayerId,
    PlayerRole,
    Verdict,
)


def _merge_answers(left: dict[str, str], right: dict[str, str]) -> dict[str, str]:
    overlap = left.keys() & right.keys()
    if overlap and any(left[player_id] != right[player_id] for player_id in overlap):
        raise ValueError("Multiple graph nodes answered for the same player")
    return left | right


class RoundState(TypedDict):
    question: str
    history: list[Verdict]
    ai_players: Sequence[tuple[PlayerId, PlayerRole]]
    answers: Annotated[dict[str, str], _merge_answers]
    gateway: AgentGateway
    decision: NotRequired[JudgeDecision]


class AnswerNodeState(TypedDict):
    question: str
    player_id: PlayerId
    gateway: AgentGateway


_ANSWER_NODE_NAMES = {
    "ai_empath": "answer_ai_empath",
    "ai_wit": "answer_ai_wit",
    "ai_story": "answer_ai_story",
}


def _route_answer_agents(state: RoundState) -> list[Send] | Literal["judge"]:
    if not state["ai_players"]:
        return "judge"
    return [
        Send(
            _ANSWER_NODE_NAMES[role],
            {
                "question": state["question"],
                "player_id": player_id,
                "gateway": state["gateway"],
            },
        )
        for player_id, role in state["ai_players"]
    ]


def _answer_node(
    role: PlayerRole,
) -> Callable[[AnswerNodeState], dict[str, dict[str, str]]]:
    def answer(state: AnswerNodeState) -> dict[str, dict[str, str]]:
        return {
            "answers": {
                state["player_id"]: state["gateway"].answer(role, state["question"])
            }
        }

    return answer


def _judge(state: RoundState) -> dict[str, JudgeDecision]:
    answer_items = list(state["answers"].items())
    random.shuffle(answer_items)
    anonymous_answers = dict(answer_items)
    return {
        "decision": state["gateway"].judge(
            state["question"], anonymous_answers, state["history"]
        )
    }


def _build_round_graph():
    builder = StateGraph(RoundState)
    for role, node_name in _ANSWER_NODE_NAMES.items():
        builder.add_node(node_name, _answer_node(cast(PlayerRole, role)))
    builder.add_node("judge", _judge)
    builder.add_conditional_edges(
        START,
        _route_answer_agents,
        [*_ANSWER_NODE_NAMES.values(), "judge"],
    )
    for node_name in _ANSWER_NODE_NAMES.values():
        builder.add_edge(node_name, "judge")
    builder.add_edge("judge", END)
    return builder.compile()


_ROUND_GRAPH = _build_round_graph()


def run_round(game: Game, human_answer: str, gateway: AgentGateway) -> Game:
    """Run independent alive AI answers, anonymous judging, and verdict reduction."""

    human = next(
        (player for player in game.players if player.role == "human" and player.is_alive),
        None,
    )
    if human is None:
        raise ValueError("Round requires one alive human player")

    ai_players = [
        (player.id, player.role)
        for player in game.players
        if player.is_alive and player.role != "human"
    ]
    graph_result = _ROUND_GRAPH.invoke(
        {
            "question": game.question,
            "history": list(game.verdict_history),
            "ai_players": ai_players,
            "answers": {human.id: human_answer},
            "gateway": gateway,
        }
    )
    decision = cast(JudgeDecision, graph_result["decision"])
    answers = cast(dict[str, str], graph_result["answers"])
    return _apply_verdict(game, answers, decision)


def _apply_verdict(
    game: Game,
    answers: dict[str, str],
    decision: JudgeDecision,
) -> Game:
    alive_ids = {player.id for player in game.players if player.is_alive}
    if decision.eliminated_player_id not in alive_ids:
        raise ValueError("Judge must select an alive player")

    next_game = game.model_copy(deep=True)
    for player in next_game.players:
        if player.is_alive:
            player.answer = answers[player.id]
        if player.id == decision.eliminated_player_id:
            player.is_alive = False

    verdict = Verdict(
        eliminated_player_id=cast(PlayerId, decision.eliminated_player_id),
        reason=decision.reason,
        confidence=decision.confidence,
    )
    next_game.verdict = verdict
    next_game.verdict_history.append(verdict)

    eliminated_player = next(
        player for player in next_game.players if player.id == decision.eliminated_player_id
    )
    if eliminated_player.role == "human":
        next_game.phase = GamePhase.FINISHED
        next_game.result = GameResult.JUDGE_WON
    elif next_game.round_number == len(QUESTIONS):
        next_game.phase = GamePhase.FINISHED
        next_game.result = GameResult.HUMAN_WON
    else:
        next_game.phase = GamePhase.VERDICT
        next_game.result = None
    return next_game
