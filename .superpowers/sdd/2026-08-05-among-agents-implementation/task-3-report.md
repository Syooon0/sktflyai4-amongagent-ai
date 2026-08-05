# Task 3 report: Game service and FastAPI contract

## Status

Implemented the game lifecycle service, process-local repository, player-token
authorization boundary, concurrent submission guard, and the five approved
FastAPI endpoints.

## Implementation

- Added `InMemoryGameRepository`, keyed by UUID game IDs, with one
  `asyncio.Lock` per game.
- Added `GameService` with create/get/submit/next lifecycle operations.
- Game creation uses `secrets.token_urlsafe(32)` for a separate opaque player
  token and shuffles the four private roles across the four fixed visual slots.
- Every protected operation validates the issuing human token with
  `secrets.compare_digest` before returning public state.
- Answer submission trims input, rejects empty or over-120-character answers,
  marks the stored game as judging, and runs the synchronous LangGraph round in
  a worker thread.
- A duplicate submission is rejected while the per-game lock is held. Gateway
  or graph errors restore the deep-copied pre-submit state, allowing a safe
  retry.
- Next-round transition is allowed only from `verdict`; it advances the fixed
  question, clears the current verdict and prior answers, and preserves verdict
  history and eliminations.
- Added `/api/health`, `POST /api/games`, `GET /api/games/{game_id}`,
  `POST /api/games/{game_id}/answers`, and `POST /api/games/{game_id}/next`.
- Added HTTP mappings: missing game `404`, invalid/missing token `403`, invalid
  transition `409`, answer validation `422`, and unavailable key/model `503`.
- Added CORS for `http://localhost:5173` and the `X-Player-Token` header.
- The player token appears only in the create response envelope; all game
  payloads use `PublicGame`, so roles remain hidden until the finished phase and
  prompts/internal agent names are never serialized.

## Configuration boundary

`create_app()` obtains the live OpenAI credential only from
`Settings.openai_api_key` and passes that value to `AgentGateway`. It does not
read `OPENAI_API_KEY` directly. Missing, empty, or whitespace-only configured
values leave the app unavailable and produce the documented health response.
Tests may inject a fake gateway without constructing a live gateway.

## TDD evidence

Initial focused run, before production modules existed:

```text
python -m pytest tests/test_service.py tests/test_api.py -q
ERROR tests/test_service.py: ModuleNotFoundError: No module named 'app.service'
ERROR tests/test_api.py: ModuleNotFoundError: No module named 'app.main'
```

During self-review, a whitespace-only API key test was added and observed
failing because `AgentGateway("")` was constructed. Key normalization was then
changed and the same focused regression passed (`2 passed`).

Final verification:

```text
python -m pytest -q
32 passed, 1 warning in 1.32s
python -m compileall -q app
exit 0
git diff --check
exit 0
```

The warning is the environment's existing `StarletteDeprecationWarning` for
importing `httpx` through `fastapi.testclient`; there are no test failures.

## Files

- Created `backend/app/service.py`
- Created `backend/app/main.py`
- Expanded `backend/tests/test_service.py`
- Created `backend/tests/test_api.py`

## Self-review

- Verified each task-brief behavior against an observable service or HTTP test.
- Strengthened the role-randomization test so removing the shuffle fails it.
- Confirmed no live gateway is constructed from an environment lookup outside
  `Settings`.
- Confirmed gateway failure and overlapping submission tests assert stored state
  rather than mock call counts.
- No unresolved functional concerns. The repository is intentionally
  process-local and non-persistent, as required for the demo architecture.
