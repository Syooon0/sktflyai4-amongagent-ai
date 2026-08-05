# Task 5 report: Party-game styling, documentation, and verification

## Status

Implemented the responsive party-game visual system, complete setup and
architecture documentation, environment-file guidance, and automated plus
browser-backed verification. No game behavior or API contract was changed.

## Implementation

- Added a warm cream page treatment and a named visual-token palette for coral,
  blue, yellow, and mint player cards.
- Styled rounded cards, thick outlines, offset shadows, status chips, large
  speech bubbles, the answer form, judge confidence, OUT state, and final result.
- Added Korean-friendly system font fallbacks, `word-break: keep-all`, long-text
  containment, keyboard focus indicators, touch-sized controls, and mobile form
  reflow.
- Implemented a mobile-first single-column arena and a two-column arena from
  761px upward, with `minmax(0, 1fr)` and overflow protection.
- Added restrained entrance, bubble, thinking, and elimination animations, plus
  a `prefers-reduced-motion: reduce` override for animation and transition time.
- Added the stylesheet import without changing the established component hooks.
- Added a README covering prerequisites, venv and npm setup, environment loading,
  both development commands, test/build commands, endpoint behavior, privacy
  boundary, in-memory storage, and all four LangGraph nodes.
- Expanded `.env.example` with safe key-placement guidance and no credential.

## Automated verification

Fresh required checks after implementation:

```text
cd backend && python -m pytest -q
34 passed in 3.20s

cd frontend && npm test -- --run && npm run build
1 test file passed; 8 tests passed
tsc --noEmit: exit 0
vite build: 19 modules transformed, built in 105ms
```

The backend suite includes API-boundary coverage proving pre-finish serialized
players have no `role` field. The frontend suite covers start/readiness, create,
answer, verdict, OUT, next round, finish, role reveal, restart, and failures.

## Browser smoke

Both Vite and FastAPI development servers were started locally.

- Against the real backend with no configured key, the start screen displayed
  the Korean `OPENAI_API_KEY` warning and kept `게임 시작` disabled; the backend
  logged the proxied `GET /api/health` as `503`.
- A deterministic local mock API was then used for browser-only UI verification,
  avoiding any external model call or credential. Start/create, answer entry,
  three live AI thinking indicators, verdict reason, 84% confidence, OUT overlay,
  next-round control, second-round finish, four role labels, and restart control
  were all observed.
- At a 1000px viewport, computed grid columns were `460.406px 460.406px`; player
  card positions formed two rows of two and horizontal overflow was absent.
- At a 390px viewport, computed grid columns were `358px`; all four cards had
  distinct increasing top positions, the document scroll width equaled 390px,
  and horizontal overflow was absent.
- Browser-computed typography included the Korean font fallback chain and
  `word-break: keep-all`. The loaded stylesheet exposed both the 761px desktop
  breakpoint and the reduced-motion media rule.
- The pre-finish mock response intentionally omitted roles and browser rendering
  contained zero role labels before finish. The later review fix below adds a
  direct browser-context capture of the real FastAPI creation response.

## Review fix round 1/5

The browser-network acceptance check was repeated against the real application,
not the mock service. FastAPI ran with the non-billable dummy process variable
`OPENAI_API_KEY=sk-dummy-nonbillable`; Vite ran normally on port 5173. No answer
was submitted, so the dummy key was never sent to an external model.

The in-app browser backend had no connected browser at this point. Following the
review fallback requirement, `frontend/scripts/verify-public-game-payload.mjs`
was added as a repeatable, dependency-free browser automation check. It launches
local headless Google Chrome, connects through the Chrome DevTools Protocol,
loads the actual Vite origin, performs `fetch("/api/games", { method: "POST" })`
inside that page, captures the complete JSON body, and asserts the exact public
player keys. Run it while the documented backend and frontend servers are up:

```text
cd frontend && npm run verify:public-payload
request: POST /api/games
status: 201
responseEnvelopeKeys: ["game", "player_token"]
playerTokenType: "string"
gameKeys: ["game_id", "phase", "players", "question", "result",
           "round_number", "verdict", "verdict_history"]
playerKeys (all four players):
  ["answer", "character_emoji", "color", "id", "is_alive", "is_you"]
anyPlayerHasRole: false
phase: "awaiting_answer"
round_number: 1
all answers: null
verdict: null
result: null
```

The real FastAPI access log for this capture contained exactly:

```text
POST /api/games HTTP/1.1 201 Created
```

There was no `POST /answers` request. This directly confirms that the actual
pre-finish browser response contains no `role` key before any model-backed work.

The second review finding was addressed by giving all 12 `box-shadow` rules a
modest nonzero blur (`0.2rem`–`1rem`) with a shared translucent ink shadow token.
Thick borders and offset direction preserve the comic-party character while the
shadow edges are now visibly soft. Static inspection found no zero-blur shadow.

Fresh verification after both fixes:

```text
cd backend && python -m pytest -q
34 passed in 1.48s

cd frontend && npm test -- --run && npm run build
1 test file passed; 8 tests passed
tsc --noEmit: exit 0
vite build: 19 modules transformed, built in 51ms

git diff --check
exit 0
```

## Self-review

No repository-specific coding standards were present. A two-axis review against
the task brief found no missing requirement or scope creep. The maintainability
review identified repeated palette literals and shared speech-bubble structure;
these were addressed with named CSS design tokens and combined base selectors.
`git diff --check` passed after the review fixes.

## Review fix round 2/5

The browser payload runner no longer uses or accepts fixed debug port `9333`.
Chrome now receives `--remote-debugging-port=0` and an isolated directory from
`mkdtemp`. The runner reads `DevToolsActivePort` only from that exact profile,
then verifies that the reported loopback port and browser WebSocket path exactly
match `/json/version`. It never enumerates an existing debug endpoint.

The runner creates a new target with `Target.createTarget`, attaches to that
specific target ID, and performs the real payload request only in that dedicated
session. Browser work has a 39-second deadline, preserving a bounded cleanup
budget: close the WebSocket, send `SIGTERM`, wait at most two seconds, escalate
to `SIGKILL` and wait at most two more seconds, then remove only the private
`mkdtemp` profile. The compact runner is 223 lines.

Fresh static verification:

```text
node --check frontend/scripts/verify-public-game-payload.mjs
exit 0

git diff --check
exit 0
```

One externally bounded live rerun was attempted exactly once as directed:

```text
timeout 20s npm run verify:public-payload
exit 124
```

The run produced only the npm command preamble and the real FastAPI access log
contained no `POST /api/games`, so it timed out before payload capture. Both
25-second bounded development servers then exited with code `124` and FastAPI
completed normal shutdown. No retry was made. Functional payload evidence
remains the successful real Chrome/FastAPI capture recorded in review round 1;
round 2 supplies the new port-ownership, dedicated-target, overall-deadline, and
bounded-cleanup implementation for re-review.

## Remaining concern

No real OpenAI key was available, so a live model-backed answer/judge round was
not executed. Model-account access, external latency, and real structured-output
behavior therefore remain the one manual follow-up; the same complete frontend
lifecycle was exercised with delayed API mocks, and gateway/API behavior is
covered by the backend suite.

## Files

- Created `frontend/src/styles.css`
- Modified `frontend/src/main.tsx`
- Created `README.md`
- Modified `backend/.env.example`
- Created this task report
