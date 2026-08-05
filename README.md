# Among Agents

Among Agents is a three-round Korean party game where one human tries to blend
in with three AI players. Each player answers the same prompt, then an
independent judge agent eliminates the answer it thinks came from the human.
Roles stay private until the game finishes.

## Prerequisites

- Python 3.11 or newer
- Node.js 20.19+ or 22.12+ and npm
- An OpenAI API key with access to `gpt-4.1-mini`

## Setup and run

Run the following from the repository root. Create and activate the backend
virtual environment first:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e "backend[dev]"
```

Create the local environment file, then open `backend/.env` and place the real
key after `OPENAI_API_KEY=`. Never commit that file.

```bash
cp backend/.env.example backend/.env
```

The settings loader reads environment variables from the process. Load the
local file and start the API from the repository root:

```bash
set -a
source backend/.env
set +a
uvicorn app.main:app --reload --app-dir backend
```

In a second terminal, install the frontend packages and start Vite:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api`
requests to the backend on port 8000. The start action remains disabled and the
page explains what is missing when the API key is not configured.

## Tests and production build

Run the complete backend suite from the repository root:

```bash
cd backend
python -m pytest -q
```

Run the frontend tests and type-checked production build:

```bash
cd frontend
npm test -- --run
npm run build
```

With both development servers running, capture and assert the real pre-finish
game-creation payload in local headless Chrome:

```bash
cd frontend
npm run verify:public-payload
```

This check performs only `POST /api/games`; it never submits an answer or calls
the model. Set `CHROME_PATH` if Google Chrome is installed somewhere other than
the default macOS application path.

## API summary

Except for health and game creation, game routes require the opaque token from
the creation response in the `X-Player-Token` header. Game data is kept in the
backend process and is lost whenever that process restarts.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Report server and API-key readiness. |
| `POST` | `/api/games` | Create a game and return its public state plus the player token. |
| `GET` | `/api/games/{game_id}` | Read the authorized player's current public game state. |
| `POST` | `/api/games/{game_id}/answers` | Submit `{ "answer": "..." }` and run the current round. |
| `POST` | `/api/games/{game_id}/next` | Advance from a verdict to the next round. |

Before the finished phase, public player objects include presentation data,
answers, elimination state, and the `is_you` marker, but never `role`. Finished
payloads reveal all four roles. The player token is returned only by game
creation and is held in React memory rather than browser storage.

## Architecture

The FastAPI layer owns authentication and the HTTP contract. `GameService`
handles the lifecycle and the process-local repository, while the domain module
keeps private player state separate from public response models. The React app
uses only those public models and moves through start, answer, verdict, next,
finish, and restart states.

One LangGraph round has four agent nodes:

- `answer_ai_empath` writes a warm, empathetic Korean answer.
- `answer_ai_wit` writes a concise, playful Korean answer.
- `answer_ai_story` writes a concrete, experience-oriented Korean answer.
- `judge` receives the shuffled, anonymous alive-player answers and public
  verdict history, then returns the eliminated player ID, reason, and confidence.

The three answer nodes fan out independently for living AI players. Their output
is merged with the human answer before the judge runs; removed players do not
participate in later rounds.
