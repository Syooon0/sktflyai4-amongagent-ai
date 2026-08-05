import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
const chromePath =
  process.env.CHROME_PATH ??
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const frontendUrl = process.env.FRONTEND_URL ?? "http://127.0.0.1:5173/";
const runDeadline = Date.now() + 39_000;
function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}
function beforeDeadline(promise, label) {
  const remaining = runDeadline - Date.now();
  if (remaining <= 0) return Promise.reject(new Error(`${label} timed out`));
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label} timed out`)), remaining);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}
function within(promise, milliseconds, label) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label} timed out`)), milliseconds);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}
function cdpClient(url) {
  const socket = new WebSocket(url);
  const pending = new Map();
  let nextId = 0;
  const opened = new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  socket.addEventListener("message", ({ data }) => {
    const message = JSON.parse(String(data));
    const request = pending.get(message.id);
    if (!request) return;
    pending.delete(message.id);
    if (message.error) request.reject(new Error(message.error.message));
    else request.resolve(message.result);
  });
  return {
    opened,
    send(method, params = {}, sessionId) {
      return beforeDeadline(
        new Promise((resolve, reject) => {
          const id = ++nextId;
          pending.set(id, { resolve, reject });
          socket.send(
            JSON.stringify({
              id,
              method,
              params,
              ...(sessionId ? { sessionId } : {}),
            }),
          );
        }),
        method,
      );
    },
    close() {
      if (socket.readyState === WebSocket.CLOSED) return Promise.resolve();
      const closed = new Promise((resolve) =>
        socket.addEventListener("close", resolve, { once: true }),
      );
      socket.close();
      return closed;
    },
  };
}
async function waitForExit(child, milliseconds) {
  if (child.exitCode !== null || child.signalCode !== null) {
    return { code: child.exitCode, signal: child.signalCode };
  }
  return within(
    new Promise((resolve) =>
      child.once("exit", (code, signal) => resolve({ code, signal })),
    ),
    milliseconds,
    "Chrome exit",
  );
}
async function stopChrome(child) {
  if (child.exitCode !== null || child.signalCode !== null) {
    return waitForExit(child, 0);
  }
  child.kill("SIGTERM");
  try {
    return await waitForExit(child, 2000);
  } catch {
    child.kill("SIGKILL");
    return waitForExit(child, 2000);
  }
}
async function ownedEndpoint(profile, child, childError) {
  const activePortFile = join(profile, "DevToolsActivePort");
  while (Date.now() < runDeadline) {
    if (childError.value) throw childError.value;
    if (child.exitCode !== null || child.signalCode !== null) {
      throw new Error("Chrome exited before opening DevTools");
    }
    try {
      const [portText, browserPath] = (await readFile(activePortFile, "utf8"))
        .trim()
        .split("\n");
      const port = Number(portText);
      if (!Number.isInteger(port) || !browserPath?.startsWith("/devtools/browser/")) {
        throw new Error("Invalid DevToolsActivePort file");
      }
      const response = await beforeDeadline(
        fetch(`http://127.0.0.1:${port}/json/version`),
        "Chrome version endpoint",
      );
      const version = await response.json();
      const websocket = new URL(version.webSocketDebuggerUrl);
      if (
        websocket.hostname !== "127.0.0.1" ||
        Number(websocket.port) !== port ||
        websocket.pathname !== browserPath
      ) {
        throw new Error("DevTools endpoint is not owned by the spawned profile");
      }
      return { port, url: version.webSocketDebuggerUrl };
    } catch {
      await sleep(50);
    }
  }
  throw new Error("Chrome DevTools startup timed out");
}
async function waitForPage(client, sessionId) {
  while (Date.now() < runDeadline) {
    const result = await client.send(
      "Runtime.evaluate",
      { expression: "({href:location.href,ready:document.readyState})", returnByValue: true },
      sessionId,
    );
    if (
      result.result.value.href === frontendUrl &&
      ["interactive", "complete"].includes(result.result.value.ready)
    ) {
      return;
    }
    await sleep(50);
  }
  throw new Error("Frontend load timed out");
}
const profile = await beforeDeadline(
  mkdtemp(join(tmpdir(), "among-agents-chrome-")),
  "Profile creation",
);
const chrome = spawn(
  chromePath,
  [
    "--headless=new",
    "--disable-background-networking",
    "--disable-extensions",
    "--no-first-run",
    "--remote-debugging-port=0",
    `--user-data-dir=${profile}`,
    "about:blank",
  ],
  { stdio: "ignore" },
);
const childError = { value: null };
chrome.once("error", (error) => {
  childError.value = error;
});
let client;
let evidence;
let chromeExit;
try {
  const endpoint = await ownedEndpoint(profile, chrome, childError);
  client = cdpClient(endpoint.url);
  await beforeDeadline(client.opened, "DevTools websocket");
  const { targetId } = await client.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await client.send("Target.attachToTarget", {
    targetId,
    flatten: true,
  });
  await client.send("Page.enable", {}, sessionId);
  await client.send("Page.navigate", { url: frontendUrl }, sessionId);
  await waitForPage(client, sessionId);
  const result = await client.send(
    "Runtime.evaluate",
    {
      expression: `(async()=>{const r=await fetch('/api/games',{method:'POST'});return {status:r.status,body:await r.json()}})()`,
      awaitPromise: true,
      returnByValue: true,
    },
    sessionId,
  );
  const capture = result.result.value;
  const playerKeys = capture.body.game.players.map((player) => Object.keys(player).sort());
  const expected = ["answer", "character_emoji", "color", "id", "is_alive", "is_you"];
  if (
    capture.status !== 201 ||
    playerKeys.some((keys) => JSON.stringify(keys) !== JSON.stringify(expected))
  ) {
    throw new Error("Real pre-finish payload failed its public-key contract");
  }
  evidence = {
    automation: {
      debugPortMode: "ephemeral",
      debugPort: endpoint.port,
      endpointOwnedBySpawnedProfile: true,
      dedicatedTarget: true,
    },
    status: capture.status,
    envelopeKeys: Object.keys(capture.body).sort(),
    gameKeys: Object.keys(capture.body.game).sort(),
    playerKeys,
    anyPlayerHasRole: capture.body.game.players.some((player) => "role" in player),
  };
} finally {
  const socketClosed = client?.close();
  chromeExit = await stopChrome(chrome);
  if (socketClosed) await within(socketClosed, 500, "Websocket close").catch(() => {});
  await within(rm(profile, { recursive: true, force: true }), 500, "Profile cleanup");
}
console.log(JSON.stringify({ ...evidence, chromeExit, cleanupComplete: true }, null, 2));
