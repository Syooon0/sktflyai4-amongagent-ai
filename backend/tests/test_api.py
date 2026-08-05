from collections.abc import Callable, Sequence
from typing import Any

import pytest
from starlette.testclient import TestClient

from app.agents import ModelInvocationError
from app.config import Settings
from app.main import create_app


def configured_client(gateway: object) -> TestClient:
    app = create_app(
        settings=Settings(openai_api_key="settings-api-key"),
        gateway=gateway,  # type: ignore[arg-type]
    )
    return TestClient(app)


def create_game(client: TestClient) -> tuple[dict[str, Any], str]:
    response = client.post("/api/games")
    assert response.status_code == 201
    payload = response.json()
    return payload["game"], payload["player_token"]


@pytest.mark.parametrize("api_key", [None, "   "])
def test_health_is_unavailable_when_settings_has_no_api_key(
    api_key: str | None,
) -> None:
    client = TestClient(create_app(settings=Settings(openai_api_key=api_key)))

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "api_key_configured": False,
    }
    assert client.post("/api/games").status_code == 503


def test_live_gateway_is_constructed_only_from_settings_api_key(monkeypatch) -> None:
    constructor_keys: list[str] = []

    class StubGateway:
        def __init__(self, api_key: str) -> None:
            constructor_keys.append(api_key)

    monkeypatch.setattr("app.main.AgentGateway", StubGateway)

    app = create_app(settings=Settings(openai_api_key="key-from-settings"))

    assert constructor_keys == ["key-from-settings"]
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "api_key_configured": True}


def test_create_returns_token_once_and_pre_finish_json_contains_no_private_fields(
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    client = configured_client(fake_gateway_factory(["player_02"]))

    game, token = create_game(client)

    serialized = str(game).lower()
    assert token
    assert "player_token" not in game
    assert "token" not in serialized
    assert "role" not in serialized
    assert "prompt" not in serialized
    assert [
        (player["id"], player["character_emoji"], player["color"])
        for player in game["players"]
    ] == [
        ("player_01", "🤖", "coral"),
        ("player_02", "👾", "blue"),
        ("player_03", "🛸", "yellow"),
        ("player_04", "🦾", "mint"),
    ]
    response = client.get(
        f"/api/games/{game['game_id']}",
        headers={"X-Player-Token": token},
    )
    assert response.status_code == 200
    assert response.json() == game
    assert "player_token" not in response.json()


def test_game_routes_map_auth_missing_validation_and_phase_errors(
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    client = configured_client(fake_gateway_factory(["player_02"]))
    game, token = create_game(client)
    game_url = f"/api/games/{game['game_id']}"

    assert client.get("/api/games/missing", headers={"X-Player-Token": token}).status_code == 404
    assert client.get(game_url).status_code == 403
    assert client.get(game_url, headers={"X-Player-Token": "wrong"}).status_code == 403
    assert client.get(
        game_url,
        headers=[(b"X-Player-Token", "잘못된".encode("utf-8"))],
    ).status_code == 403
    assert client.post(
        f"{game_url}/answers",
        headers={"X-Player-Token": token},
        json={"answer": "   "},
    ).status_code == 422
    assert client.post(
        f"{game_url}/answers",
        headers={"X-Player-Token": token},
        json={"answer": "가" * 121},
    ).status_code == 422
    assert client.post(
        f"{game_url}/next",
        headers={"X-Player-Token": token},
    ).status_code == 409


def test_submit_and_next_routes_drive_the_round_lifecycle(
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    client = configured_client(fake_gateway_factory(["player_02", "player_03"]))
    game, token = create_game(client)
    headers = {"X-Player-Token": token}
    game_url = f"/api/games/{game['game_id']}"

    verdict = client.post(
        f"{game_url}/answers",
        headers=headers,
        json={"answer": "  첫 번째 사람 답변입니다.  "},
    )

    assert verdict.status_code == 200
    assert verdict.json()["phase"] in {"verdict", "finished"}
    assert "role" not in str(verdict.json()).lower() or verdict.json()["phase"] == "finished"
    duplicate = client.post(
        f"{game_url}/answers",
        headers=headers,
        json={"answer": "중복 답변입니다."},
    )
    assert duplicate.status_code == 409

    if verdict.json()["phase"] == "verdict":
        next_round = client.post(f"{game_url}/next", headers=headers)
        assert next_round.status_code == 200
        assert next_round.json()["round_number"] == 2
        assert next_round.json()["phase"] == "awaiting_answer"


def test_api_hides_roles_before_finish_and_reveals_them_after_finish(
    monkeypatch: pytest.MonkeyPatch,
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    monkeypatch.setattr("app.service.random.shuffle", lambda values: None)
    client = configured_client(fake_gateway_factory(["player_01"]))
    game, token = create_game(client)
    headers = {"X-Player-Token": token}
    game_url = f"/api/games/{game['game_id']}"

    assert all("role" not in player for player in game["players"])

    response = client.post(
        f"{game_url}/answers",
        headers=headers,
        json={"answer": "사람 참가자의 답변입니다."},
    )

    assert response.status_code == 200
    finished = response.json()
    assert finished["phase"] == "finished"
    assert [player["role"] for player in finished["players"]] == [
        "human",
        "ai_empath",
        "ai_wit",
        "ai_story",
    ]


def test_model_failures_return_503_without_discarding_current_game(
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    class FailingGateway:
        def answer(self, role: str, question: str) -> str:
            raise ModelInvocationError("upstream failed")

        def judge(self, question: str, answers: dict[str, str], history: list[object]):
            raise AssertionError("judge must not run")

    client = configured_client(FailingGateway())
    game, token = create_game(client)
    headers = {"X-Player-Token": token}
    game_url = f"/api/games/{game['game_id']}"

    response = client.post(
        f"{game_url}/answers",
        headers=headers,
        json={"answer": "사람 답변입니다."},
    )

    assert response.status_code == 503
    current = client.get(game_url, headers=headers)
    assert current.status_code == 200
    assert current.json() == game


def test_cors_permits_vite_development_origin(
    fake_gateway_factory: Callable[[Sequence[str]], object],
) -> None:
    client = configured_client(fake_gateway_factory(["player_02"]))

    response = client.options(
        "/api/games",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
