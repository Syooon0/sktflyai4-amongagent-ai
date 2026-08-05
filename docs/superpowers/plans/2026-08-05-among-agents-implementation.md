# Among Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-round web game where three independent OpenAI answer agents try to appear human and a judge agent uses only public answers to eliminate the hidden human.

**Architecture:** A FastAPI backend owns private roles and runs a typed LangGraph round workflow. A React/Vite frontend consumes only public DTOs and animates question, speech bubbles, verdict, elimination, and final role reveal. OpenAI calls sit behind a small model gateway so graph and API tests can use deterministic fakes.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic 2, LangGraph, LangChain OpenAI, pytest, React 18, TypeScript, Vite, Vitest, Testing Library

## Global Constraints

- Use the OpenAI API configured only through `.env` variable `OPENAI_API_KEY`.
- Use exactly three fixed Korean questions and at most three rounds.
- End immediately when the human is eliminated; human wins after surviving the third verdict.
- Never expose private role mappings, prompts, or internal agent names before game completion.
- AI answer agents run independently and cannot see one another's answers.
- The judge receives only the current question, alive answers, and prior public verdict history.
- Use a bright casual party-game visual direction, a desktop 2×2 arena, and a mobile single-column layout.
- Keep game state in memory for this demo; do not add authentication, a database, RAG, or deployment infrastructure.

---

## File Structure

```text
backend/
  pyproject.toml                 Python package and test configuration
  .env.example                  OpenAI configuration template
  app/
    __init__.py
    config.py                   Environment settings
    domain.py                   Private state and public DTO models
    agents.py                   Model gateway, prompts, structured judge output
    graph.py                    LangGraph round workflow
    service.py                  Game lifecycle and in-memory repository
    main.py                     FastAPI routes and error mapping
  tests/
    conftest.py                 Deterministic fake model gateway
    test_graph.py               Round transitions and victory rules
    test_service.py             Public/private boundary and lifecycle
    test_api.py                 HTTP contract and validation
frontend/
  package.json
  tsconfig.json
  vite.config.ts
  index.html
  src/
    main.tsx                    React entrypoint
    api.ts                      Typed API client
    types.ts                    Public response types
    App.tsx                     Screen/state orchestration
    components/GameBoard.tsx    Arena layout and phase controls
    components/PlayerCard.tsx   Character, speech bubble, OUT/YOU states
    components/JudgePanel.tsx   Judge reasoning and confidence
    styles.css                  Responsive party-game visual system
    test/App.test.tsx           Primary UI flows
README.md                       Setup, run, test, and architecture guide
```

### Task 1: Backend domain and public-state boundary

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.env.example`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/domain.py`
- Create: `backend/tests/test_service.py`

**Interfaces:**
- Produces: `Game`, `Player`, `PublicGame`, `GamePhase`, `GameResult`, `Verdict`, `QUESTIONS`, and `Game.to_public(player_token: str) -> PublicGame`.
- Consumes: no project interfaces.

- [ ] **Step 1: Add Python package configuration**

Create `backend/pyproject.toml` with Python `>=3.11`, runtime dependencies `fastapi`, `uvicorn[standard]`, `langgraph`, `langchain-openai`, `pydantic-settings`, and dev dependencies `pytest`, `pytest-asyncio`, `httpx`.

- [ ] **Step 2: Write failing public-boundary tests**

Test that a four-player `Game` returns four public players, marks only the token owner's slot with `is_you=True`, excludes every `role` field from `model_dump()`, and returns roles only when `phase == GamePhase.FINISHED`.

- [ ] **Step 3: Run the focused tests and confirm failure**

Run: `cd backend && python -m pytest tests/test_service.py -q`

Expected: collection fails because `app.domain` does not exist.

- [ ] **Step 4: Implement domain models and settings**

Define `PlayerRole = Literal["human", "ai_empath", "ai_wit", "ai_story"]`; four stable public IDs; `GamePhase` values `awaiting_answer`, `judging`, `verdict`, `finished`; `GameResult` values `human_won`, `judge_won`; and immutable Korean `QUESTIONS`. Implement separate private and public Pydantic models rather than serializing private objects and deleting fields.

- [ ] **Step 5: Run tests and commit**

Run: `cd backend && python -m pytest tests/test_service.py -q`

Expected: PASS.

Commit: `feat: add game domain models`

### Task 2: Independent agents and LangGraph round workflow

**Files:**
- Create: `backend/app/agents.py`
- Create: `backend/app/graph.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_graph.py`

**Interfaces:**
- Consumes: `Game`, `PlayerRole`, `Verdict`, `QUESTIONS` from `app.domain`.
- Produces: `AgentGateway.answer(role: PlayerRole, question: str) -> str`, `AgentGateway.judge(question: str, answers: dict[str, str], history: list[Verdict]) -> JudgeDecision`, and `run_round(game: Game, human_answer: str, gateway: AgentGateway) -> Game`.

- [ ] **Step 1: Write deterministic graph tests**

Create a fake gateway recording every answer role and judge payload. Test that three alive AI roles are called exactly once in round one, the judge sees four anonymous player IDs and no roles, a removed AI is not called next round, human removal yields `judge_won`, and survival through round three yields `human_won`.

- [ ] **Step 2: Run tests and confirm failure**

Run: `cd backend && python -m pytest tests/test_graph.py -q`

Expected: import failure for `app.graph`.

- [ ] **Step 3: Implement the model gateway**

Use three distinct system prompts for empathetic, witty, and experience-oriented answers. Enforce one Korean sentence and the same 120-character limit as the human input. Implement judge structured output with Pydantic `JudgeDecision(eliminated_player_id, reason, confidence)` and reject choices outside the supplied alive IDs. Configure timeout and one retry on `ChatOpenAI`.

- [ ] **Step 4: Implement the typed LangGraph**

Build nodes for each alive AI role and a judge node. Use LangGraph fan-out so independent AI nodes receive only `question` and their own persona; merge their answers, add the human answer, randomize public answer order, then invoke the judge. Apply verdict and result rules in a deterministic reducer after validating the judge selection.

- [ ] **Step 5: Run graph tests and commit**

Run: `cd backend && python -m pytest tests/test_graph.py -q`

Expected: PASS.

Commit: `feat: add multi-agent round graph`

### Task 3: Game service and FastAPI contract

**Files:**
- Create: `backend/app/service.py`
- Create: `backend/app/main.py`
- Modify: `backend/tests/test_service.py`
- Create: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `run_round`, `AgentGateway`, and all domain models.
- Produces: `GameService.create_game() -> tuple[PublicGame, str]`, `get_game(game_id, token) -> PublicGame`, `submit_answer(game_id, token, answer) -> PublicGame`, `next_round(game_id, token) -> PublicGame`; HTTP routes under `/api`.

- [ ] **Step 1: Write lifecycle and API tests**

Cover game creation, token ownership, empty and over-120-character answers, duplicate submission, next-round transition, missing game, missing API key health response, CORS, and absence of role/prompt fields in pre-finish JSON.

- [ ] **Step 2: Run tests and confirm failure**

Run: `cd backend && python -m pytest tests/test_service.py tests/test_api.py -q`

Expected: import failure for `app.service` or `app.main`.

- [ ] **Step 3: Implement service lifecycle**

Store games in a dictionary keyed by UUID. Generate a separate opaque player token, randomize roles across four visual slots, validate phase transitions, trim input, preserve the current state when the gateway raises, and use a per-game async lock to reject concurrent duplicate processing.

- [ ] **Step 4: Implement FastAPI routes**

Add the five approved endpoints. Return `409` for invalid phase transitions, `404` for missing games, `403` for invalid tokens, `422` for answer validation, and `503` for missing key or model failure. Read the token from `X-Player-Token`; return it only in the create response envelope. Permit the Vite development origin through CORS.

- [ ] **Step 5: Run the backend suite and commit**

Run: `cd backend && python -m pytest -q`

Expected: PASS.

Commit: `feat: expose Among Agents game API`

### Task 4: React arena and round interaction

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/components/GameBoard.tsx`
- Create: `frontend/src/components/PlayerCard.tsx`
- Create: `frontend/src/components/JudgePanel.tsx`
- Create: `frontend/src/test/App.test.tsx`

**Interfaces:**
- Consumes: JSON contracts from Task 3.
- Produces: a browser UI supporting start, answer, verdict, next round, finish, and restart.

- [ ] **Step 1: Scaffold Vite configuration and write UI tests**

Mock `fetch` and test the start screen, API-key warning, answer submission, `YOU` label, four player cards, judge reason, `OUT` state, next-round action, and final role reveal.

- [ ] **Step 2: Run tests and confirm failure**

Run: `cd frontend && npm test -- --run`

Expected: component imports fail.

- [ ] **Step 3: Implement typed API and screen orchestration**

Store the player token in component state, never local storage. Poll health on load, create a game on start, submit trimmed answers, render server errors without discarding current state, and request the next round only after the user clicks the enabled button.

- [ ] **Step 4: Implement arena components**

Render four stable cards from public IDs, with server-provided character emoji and colors, a `YOU` badge, speech bubbles, thinking dots, judge character, confidence meter, verdict reason, `OUT` overlay, and completed-game role labels.

- [ ] **Step 5: Run frontend tests and commit**

Run: `cd frontend && npm test -- --run`

Expected: PASS.

Commit: `feat: build interactive game arena`

### Task 5: Party-game styling, documentation, and end-to-end verification

**Files:**
- Create: `frontend/src/styles.css`
- Create: `README.md`
- Modify: `backend/.env.example`

**Interfaces:**
- Consumes: UI class names and run commands from Tasks 1–4.
- Produces: responsive polished UI and complete operator instructions.

- [ ] **Step 1: Add responsive visual system**

Use warm cream page background, coral/blue/yellow/mint player palettes, rounded cards, bold Korean-friendly system fonts, thick borders, soft offset shadows, large speech bubbles, and restrained entrance/shake/fade animations. Keep a 2×2 grid above 760px and one column below it; respect `prefers-reduced-motion`.

- [ ] **Step 2: Add setup and architecture documentation**

Document Python and Node prerequisites, virtual environment setup, `cp backend/.env.example backend/.env`, key insertion, backend command `uvicorn app.main:app --reload --app-dir backend`, frontend commands, both test suites, endpoint summary, and the four LangGraph agent nodes.

- [ ] **Step 3: Run all automated checks**

Run: `cd backend && python -m pytest -q`

Run: `cd frontend && npm test -- --run && npm run build`

Expected: every command exits zero.

- [ ] **Step 4: Perform browser smoke test**

Start both development servers, verify the start screen, API-key status, 2×2 desktop grid, mobile single-column layout, one answer submission, staged speech bubbles, judge verdict, elimination, and next/finish controls. Confirm the browser network payload contains no pre-finish roles.

- [ ] **Step 5: Commit**

Commit: `docs: finish Among Agents demo`

