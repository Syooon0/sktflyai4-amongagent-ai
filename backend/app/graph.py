"""Typed LangGraph workflow for one complete judging round."""

import random
from collections.abc import Callable, Sequence
from typing import Annotated, Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.agents import AgentGateway, JudgeDecision
from app.domain import (
    MBTI_TYPES,
    TOTAL_ROUNDS,
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
    ai_players: Sequence[tuple[PlayerId, PlayerRole]]
    answers: Annotated[dict[str, str], _merge_answers]
    gateway: AgentGateway


class AnswerNodeState(TypedDict):
    question: str
    player_id: PlayerId
    gateway: AgentGateway


_ANSWER_NODE_NAMES = {role: f"answer_{role.lower()}" for role in MBTI_TYPES}


def _route_answer_agents(state: RoundState) -> list[Send] | Literal["__end__"]:
    if not state["ai_players"]:
        return END
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


def _build_answers_graph():
    builder = StateGraph(RoundState)
    for role, node_name in _ANSWER_NODE_NAMES.items():
        builder.add_node(node_name, _answer_node(cast(PlayerRole, role)))
    builder.add_conditional_edges(
        START,
        _route_answer_agents,
        [*_ANSWER_NODE_NAMES.values(), END],
    )
    for node_name in _ANSWER_NODE_NAMES.values():
        builder.add_edge(node_name, END)
    return builder.compile()


_ANSWERS_GRAPH = _build_answers_graph()


def run_round(game: Game, human_answer: str, gateway: AgentGateway) -> Game:
    """Collect one question's answers; judge only once all questions are answered."""

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
    graph_result = _ANSWERS_GRAPH.invoke(
        {
            "question": game.round_questions[game.question_index],
            "ai_players": ai_players,
            "answers": {human.id: human_answer},
            "gateway": gateway,
        }
    )
    answers = cast(dict[str, str], graph_result["answers"])

    next_game = game.model_copy(deep=True)
    for player in next_game.players:
        if player.is_alive:
            player.answer = answers[player.id]
            player.answers.append(answers[player.id])

    if next_game.question_index < len(next_game.round_questions) - 1:
        next_game.question_index += 1
        next_game.phase = GamePhase.AWAITING_ANSWER
        return next_game

    rounds: list[tuple[str, dict[str, str]]] = []
    for index, question in enumerate(next_game.round_questions):
        per_question = {
            player.id: player.answers[index]
            for player in next_game.players
            if player.is_alive
        }
        items = list(per_question.items())
        random.shuffle(items)
        rounds.append((question, dict(items)))

    nicknames = {
        player.id: player.nickname for player in next_game.players if player.is_alive
    }
    decision = gateway.judge(rounds, list(next_game.verdict_history), nicknames)
    return _apply_verdict(next_game, decision)


def _apply_verdict(game: Game, decision: JudgeDecision) -> Game:
    alive_ids = {player.id for player in game.players if player.is_alive}
    if decision.eliminated_player_id not in alive_ids:
        raise ValueError("Judge must select an alive player")

    next_game = game.model_copy(deep=True)
    for player in next_game.players:
        if player.id == decision.eliminated_player_id:
            player.is_alive = False

    verdict = Verdict(
        eliminated_player_id=cast(PlayerId, decision.eliminated_player_id),
        reason=decision.reason,
        confidence=decision.confidence,
        player_scores=cast(dict[PlayerId, int], decision.player_scores),
    )
    next_game.verdict = verdict
    next_game.verdict_history.append(verdict)

    eliminated_player = next(
        player for player in next_game.players if player.id == decision.eliminated_player_id
    )
    if eliminated_player.role == "human":
        next_game.phase = GamePhase.FINISHED
        next_game.result = GameResult.JUDGE_WON
    elif next_game.round_number == TOTAL_ROUNDS:
        next_game.phase = GamePhase.FINISHED
        next_game.result = GameResult.HUMAN_WON
    else:
        next_game.phase = GamePhase.VERDICT
        next_game.result = None
    return next_game
