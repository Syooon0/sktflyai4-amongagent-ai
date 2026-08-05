<img width="580" height="181" alt="스크린샷 2026-08-05 오후 4 05 37" src="https://github.com/user-attachments/assets/56d735b2-818d-42ea-b20b-8ae40e449cdf" />
# sktflyai4-amongagent-ai — Among Agents

Among Agents는 인간 1명이 AI 플레이어 3명 사이에 섞여 들키지 않으려 하는
3라운드 한국어 파티 게임입니다. 모든 참가자가 같은 질문에 답하면, 독립된
판단 에이전트가 인간이 썼다고 생각되는 답변을 제거합니다. 역할은 게임이
끝날 때까지 비공개로 유지됩니다.

## 사전 준비물

- Python 3.11 이상
- Node.js 20.19+ 또는 22.12+, 그리고 npm
- `gpt-4.1-mini`를 사용할 수 있는 OpenAI API 키

## 설치 및 실행

아래 명령은 저장소 루트에서 실행합니다. 먼저 백엔드 가상환경을 만들고
활성화합니다.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e "backend[dev]"
```

로컬 환경 파일을 만든 뒤 `backend/.env`를 열어 `OPENAI_API_KEY=` 뒤에
실제 키를 입력합니다. 이 파일은 절대 커밋하지 않습니다.

```bash
cp backend/.env.example backend/.env
```

설정 로더는 프로세스 환경 변수에서 값을 읽습니다. 저장소 루트에서 로컬
파일을 로드하고 API를 시작합니다.

```bash
set -a
source backend/.env
set +a
uvicorn app.main:app --reload --app-dir backend
```

다른 터미널에서 프론트엔드 패키지를 설치하고 Vite를 시작합니다.

```bash
cd frontend
npm install
npm run dev
```

[http://localhost:5173](http://localhost:5173) 을 엽니다. Vite가 `/api`
요청을 8000번 포트의 백엔드로 프록시합니다. API 키가 설정되지 않은 동안은
시작 버튼이 비활성 상태로 남고, 화면에 무엇이 빠졌는지 안내가 표시됩니다.

## 테스트와 프로덕션 빌드

저장소 루트에서 백엔드 전체 테스트 스위트를 실행합니다.

```bash
cd backend
python -m pytest -q
```

프론트엔드 테스트와 타입 체크를 포함한 프로덕션 빌드를 실행합니다.

```bash
cd frontend
npm test -- --run
npm run build
```

두 개발 서버가 모두 실행 중일 때, 로컬 헤드리스 Chrome으로 실제 게임 생성
직후(pre-finish) 페이로드를 캡처하고 검증합니다.

```bash
cd frontend
npm run verify:public-payload
```

이 검사는 `POST /api/games`만 호출합니다. 답변을 제출하거나 모델을
호출하지 않습니다. Google Chrome이 macOS 기본 경로가 아닌 곳에 설치되어
있다면 `CHROME_PATH`를 지정하세요.

## API 요약

헬스체크와 게임 생성을 제외한 모든 게임 라우트는 생성 응답에서 받은 불투명
토큰을 `X-Player-Token` 헤더에 담아야 합니다. 게임 데이터는 백엔드
프로세스 안에만 보관되며, 프로세스가 재시작되면 사라집니다.

| 메서드 | 엔드포인트 | 용도 |
| --- | --- | --- |
| `GET` | `/api/health` | 서버 상태와 API 키 설정 여부를 반환합니다. |
| `POST` | `/api/games` | 게임을 생성하고 공개 상태와 플레이어 토큰을 반환합니다. |
| `GET` | `/api/games/{game_id}` | 인증된 플레이어의 현재 공개 게임 상태를 반환합니다. |
| `POST` | `/api/games/{game_id}/answers` | `{ "answer": "..." }`를 제출하고 해당 라운드를 실행합니다. |
| `POST` | `/api/games/{game_id}/next` | 판결 연출이 끝난 뒤 다음 라운드로 이동합니다. |

종료 단계 이전에는 공개 플레이어 객체에 연출 데이터, 답변, 탈락 여부,
`is_you` 표시가 포함되지만 `role`은 절대 포함되지 않습니다. 종료된 게임의
응답에는 네 명의 역할이 모두 공개됩니다. 플레이어 토큰은 게임 생성 시에만
반환되며, 브라우저 저장소가 아닌 React 메모리에만 유지됩니다.

## 아키텍처

FastAPI 계층이 인증과 HTTP 계약을 담당합니다. `GameService`가 게임
생명주기와 프로세스 내부 저장소를 관리하고, domain 모듈은 비공개 플레이어
상태와 공개 응답 모델을 분리해 유지합니다. React 앱은 그 공개 모델만
사용하며 시작, 답변, 판결, 다음 라운드, 종료, 재시작 상태를 순서대로
이동합니다.

하나의 LangGraph 라운드에는 MBTI 16개 성향별 답변 노드(`answer_intj`,
`answer_enfp` 등)와 판단 노드가 있습니다.

- 게임 생성 시 16개 MBTI 성향 중 3개를 무작위로 뽑아 AI 플레이어에게
  배정합니다. 각 성향은 고유한 한국어 시스템 프롬프트와 온도(temperature)를
  가지며, Judging형(J)은 낮은 온도로 일관되게, Perceiving형(P)은 높은
  온도로 즉흥적으로 답합니다.
- `judge` — 섞인 익명 생존자 답변과 공개 판결 기록만 받아, 탈락시킬
  플레이어 ID와 이유, 확신도를 반환합니다.

그 라운드에 배정된 AI 성향의 답변 노드만 생존 플레이어에 대해 각각
독립적으로 병렬 실행됩니다. 그 결과는 인간의 답변과 합쳐진 뒤 판단 노드로
전달되며, 탈락한 플레이어는 이후 라운드에 참여하지 않습니다.
