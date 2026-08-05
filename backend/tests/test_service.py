from app.domain import Game, GamePhase, Player


def game_with_four_players(*, phase: GamePhase = GamePhase.AWAITING_ANSWER) -> Game:
    return Game(
        game_id="game-123",
        phase=phase,
        players=[
            Player(id="player_01", role="human", token="human-token"),
            Player(id="player_02", role="ai_empath"),
            Player(id="player_03", role="ai_wit"),
            Player(id="player_04", role="ai_story"),
        ],
    )


def test_public_game_marks_only_token_owner_and_hides_roles_before_finish() -> None:
    game = game_with_four_players()

    public_game = game.to_public("human-token")
    public_players = public_game.model_dump()["players"]

    assert len(public_players) == 4
    assert [player["id"] for player in public_players] == [
        "player_01",
        "player_02",
        "player_03",
        "player_04",
    ]
    assert [player["is_you"] for player in public_players] == [True, False, False, False]
    assert all("role" not in player for player in public_players)


def test_public_game_reveals_roles_only_after_game_finishes() -> None:
    in_progress_game = game_with_four_players()
    finished_game = game_with_four_players(phase=GamePhase.FINISHED)

    assert all(
        "role" not in player
        for player in in_progress_game.to_public("human-token").model_dump()["players"]
    )
    assert [player["role"] for player in finished_game.to_public("human-token").model_dump()["players"]] == [
        "human",
        "ai_empath",
        "ai_wit",
        "ai_story",
    ]
