import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const chromePath =
  process.env.CHROME_PATH ??
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const frontendUrl = process.env.FRONTEND_URL ?? "http://127.0.0.1:5173/";
const debugPort = Number(process.env.CHROME_DEBUG_PORT ?? "9333");
const profileDirectory = await mkdtemp(join(tmpdir(), "among-agents-chrome-"));

const chrome = spawn(
  chromePath,
  [
    "--headless=new",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-extensions",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    `--remote-debugging-port=${debugPort}`,
    `--user-data-dir=${profileDirectory}`,
    "about:blank",
  ],
  { stdio: "ignore" },
);

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function fetchJsonWhenReady(url) {
  let lastError;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return response.json();
      lastError = new Error(`Chrome debug endpoint returned ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await delay(50);
  }
  throw lastError ?? new Error("Chrome debug endpoint did not become ready");
}

function createCdpClient(webSocketUrl) {
  const socket = new WebSocket(webSocketUrl);
  const pending = new Map();
  let nextId = 0;

  const opened = new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });

  socket.addEventListener("message", (event) => {
    const message = JSON.parse(String(event.data));
    if (!("id" in message)) return;
    const request = pending.get(message.id);
    if (!request) return;
    pending.delete(message.id);
    if (message.error) request.reject(new Error(message.error.message));
    else request.resolve(message.result);
  });

  return {
    opened,
    close: () => socket.close(),
    send(method, params = {}) {
      const id = ++nextId;
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject });
        socket.send(JSON.stringify({ id, method, params }));
      });
    },
  };
}

async function waitForPage(client, expectedUrl) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    const evaluation = await client.send("Runtime.evaluate", {
      expression: "({ href: location.href, readyState: document.readyState })",
      returnByValue: true,
    });
    const { href, readyState } = evaluation.result.value;
    if (
      href === expectedUrl &&
      ["interactive", "complete"].includes(readyState)
    ) {
      return;
    }
    await delay(50);
  }
  throw new Error("Frontend page did not become ready");
}

let client;
try {
  const targets = await fetchJsonWhenReady(
    `http://127.0.0.1:${debugPort}/json/list`,
  );
  const target = targets.find((candidate) => candidate.type === "page");
  if (!target) throw new Error("Chrome did not expose a page target");

  client = createCdpClient(target.webSocketDebuggerUrl);
  await client.opened;
  await client.send("Page.enable");
  await client.send("Page.navigate", { url: frontendUrl });
  await waitForPage(client, frontendUrl);

  const evaluation = await client.send("Runtime.evaluate", {
    awaitPromise: true,
    returnByValue: true,
    expression: `
      (async () => {
        const response = await fetch("/api/games", { method: "POST" });
        return { status: response.status, body: await response.json() };
      })()
    `,
  });
  if (evaluation.exceptionDetails) {
    throw new Error(evaluation.exceptionDetails.text);
  }

  const capture = evaluation.result.value;
  if (capture.status !== 201) {
    throw new Error(`Expected POST /api/games to return 201, got ${capture.status}`);
  }

  const expectedPlayerKeys = [
    "answer",
    "character_emoji",
    "color",
    "id",
    "is_alive",
    "is_you",
  ];
  const playerKeys = capture.body.game.players.map((player) =>
    Object.keys(player).sort(),
  );
  if (
    playerKeys.some(
      (keys) => JSON.stringify(keys) !== JSON.stringify(expectedPlayerKeys),
    )
  ) {
    throw new Error(`Unexpected pre-finish player keys: ${JSON.stringify(playerKeys)}`);
  }

  const evidence = {
    request: { method: "POST", url: "/api/games" },
    status: capture.status,
    responseEnvelopeKeys: Object.keys(capture.body).sort(),
    playerTokenType: typeof capture.body.player_token,
    gameKeys: Object.keys(capture.body.game).sort(),
    playerKeys,
    anyPlayerHasRole: capture.body.game.players.some((player) =>
      Object.prototype.hasOwnProperty.call(player, "role"),
    ),
    game: capture.body.game,
  };
  console.log(JSON.stringify(evidence, null, 2));
} finally {
  client?.close();
  chrome.kill("SIGTERM");
  await rm(profileDirectory, { recursive: true, force: true });
}
