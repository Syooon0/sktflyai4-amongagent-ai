"""FastAPI application exposing the Among Agents game contract."""

from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.agents import AgentGateway
from app.config import Settings
from app.domain import PublicGame
from app.service import (
    AnswerValidationError,
    GameNotFoundError,
    GameService,
    InvalidPhaseError,
    InvalidTokenError,
    ModelGatewayError,
)

VITE_DEVELOPMENT_ORIGIN = "http://localhost:5173"


class CreateGameResponse(BaseModel):
    game: PublicGame
    player_token: str


class AnswerRequest(BaseModel):
    answer: str


class HealthResponse(BaseModel):
    status: str
    api_key_configured: bool


PlayerToken = Annotated[
    str | None,
    Header(alias="X-Player-Token"),
]


def create_app(
    *,
    settings: Settings | None = None,
    gateway: AgentGateway | None = None,
) -> FastAPI:
    runtime_settings = settings or Settings()
    api_key = (runtime_settings.openai_api_key or "").strip() or None
    live_gateway = gateway
    if live_gateway is None and api_key is not None:
        live_gateway = AgentGateway(api_key)
    service = GameService(live_gateway) if live_gateway is not None else None

    application = FastAPI(title="Among Agents API")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[VITE_DEVELOPMENT_ORIGIN],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Player-Token"],
    )

    def require_service() -> GameService:
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OPENAI_API_KEY is not configured",
            )
        return service

    @application.exception_handler(GameNotFoundError)
    async def game_not_found_handler(_, error: GameNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @application.exception_handler(InvalidTokenError)
    async def invalid_token_handler(_, error: InvalidTokenError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(error)})

    @application.exception_handler(InvalidPhaseError)
    async def invalid_phase_handler(_, error: InvalidPhaseError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @application.exception_handler(AnswerValidationError)
    async def answer_validation_handler(_, error: AnswerValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @application.exception_handler(ModelGatewayError)
    async def model_gateway_handler(_, __: ModelGatewayError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "Model service unavailable"},
        )

    @application.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse | JSONResponse:
        payload = HealthResponse(
            status="ok" if service is not None else "unavailable",
            api_key_configured=api_key is not None,
        )
        if service is None:
            return JSONResponse(status_code=503, content=payload.model_dump())
        return payload

    @application.post(
        "/api/games",
        response_model=CreateGameResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_game(
        game_service: Annotated[GameService, Depends(require_service)],
    ) -> CreateGameResponse:
        game, player_token = await game_service.create_game()
        return CreateGameResponse(game=game, player_token=player_token)

    @application.get("/api/games/{game_id}", response_model=PublicGame)
    async def get_game(
        game_id: str,
        game_service: Annotated[GameService, Depends(require_service)],
        x_player_token: PlayerToken = None,
    ) -> PublicGame:
        return game_service.get_game(game_id, x_player_token)

    @application.post("/api/games/{game_id}/answers", response_model=PublicGame)
    async def submit_answer(
        game_id: str,
        payload: AnswerRequest,
        game_service: Annotated[GameService, Depends(require_service)],
        x_player_token: PlayerToken = None,
    ) -> PublicGame:
        return await game_service.submit_answer(
            game_id, x_player_token, payload.answer
        )

    @application.post("/api/games/{game_id}/next", response_model=PublicGame)
    async def next_round(
        game_id: str,
        game_service: Annotated[GameService, Depends(require_service)],
        x_player_token: PlayerToken = None,
    ) -> PublicGame:
        return await game_service.next_round(game_id, x_player_token)

    return application


app = create_app()
