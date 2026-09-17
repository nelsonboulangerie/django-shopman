// Nitro de mentira para os testes do roteador: escuta em HOST:PORT como o
// `.output/server/index.mjs` real e expõe o mínimo para provar o proxy.
import { createServer } from "node:http";

const name = process.env.FAKE_NAME || "fake";
let openSse = 0;

const server = createServer((req, res) => {
  const url = new URL(req.url, "http://x");
  if (url.pathname === "/health/live") {
    if (process.env.FAKE_HTML_HEALTH === "1") {
      // Como um app com rota catch-all: 200, mas página.
      res.writeHead(200, { "content-type": "text/html;charset=utf-8" });
      res.end("<!doctype html><p>shell</p>");
      return;
    }
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ status: "ok", app: name }));
    return;
  }
  if (url.pathname === "/health/ready") {
    const ok = process.env.FAKE_READY !== "fail";
    res.writeHead(ok ? 200 : 503, { "content-type": "application/json" });
    res.end(JSON.stringify({ status: ok ? "ok" : "fail", app: name }));
    return;
  }
  if (url.pathname === "/echo") {
    const keys = (process.env.FAKE_ECHO_ENV || "").split(",").filter(Boolean);
    const body = JSON.stringify({
      app: name,
      host: req.headers.host,
      xff: req.headers["x-forwarded-for"] ?? null,
      env: Object.fromEntries(keys.map((k) => [k, process.env[k] ?? null])),
      port: process.env.PORT,
    });
    res.writeHead(200, [
      "content-type", "application/json",
      "content-security-policy", `script-src 'nonce-${name}'`,
      "set-cookie", "a=1; Path=/",
      "set-cookie", "b=2; Path=/",
    ]);
    res.end(body);
    return;
  }
  if (url.pathname === "/post") {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      res.writeHead(201, { "content-type": "text/plain" });
      res.end(`${name}:${Buffer.concat(chunks).toString()}`);
    });
    return;
  }
  if (url.pathname === "/slow") {
    setTimeout(() => {
      res.writeHead(200, { "content-type": "text/plain" });
      res.end(`${name}:slow-done`);
    }, Number(url.searchParams.get("ms") || 1000));
    return;
  }
  if (url.pathname === "/sse") {
    openSse += 1;
    res.writeHead(200, {
      "content-type": "text/event-stream",
      "cache-control": "no-cache, no-transform",
      connection: "keep-alive",
      "x-accel-buffering": "no",
    });
    let n = 0;
    const every = Number(url.searchParams.get("every") || 100);
    const timer = setInterval(() => {
      n += 1;
      res.write(`id: ${n}\ndata: ${JSON.stringify({ n, sentAt: Date.now() })}\n\n`);
    }, every);
    res.on("close", () => {
      clearInterval(timer);
      openSse -= 1;
    });
    return;
  }
  if (url.pathname === "/stats") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ openSse, pid: process.pid }));
    return;
  }
  if (url.pathname === "/crash") {
    res.writeHead(200);
    res.end("bye", () => process.exit(Number(url.searchParams.get("code") || 1)));
    return;
  }
  res.writeHead(404, { "content-type": "text/plain" });
  res.end(`${name}:404`);
});

server.on("upgrade", (req, socket) => {
  socket.write(
    "HTTP/1.1 101 Switching Protocols\r\nUpgrade: echo\r\nConnection: Upgrade\r\n\r\n",
  );
  socket.write(`hello-from-${name}\n`);
  socket.on("data", (data) => socket.write(data));
});

if (process.env.FAKE_BOOT_FAIL === "1") process.exit(3);
server.listen(Number(process.env.PORT), process.env.HOST || "127.0.0.1");
process.on("SIGTERM", () => {
  server.close();
  server.closeAllConnections();
  process.exit(0);
});
