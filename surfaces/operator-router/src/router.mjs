// Roteador por Host: um servidor HTTP na porta do App Platform que encaminha
// cada pedido, byte a byte, para o Nitro do app dono daquele hostname.
//
// O que ele NÃO faz, de propósito (ADR-026 e ADR-030):
// - não reescreve cabeçalho de segurança, CSP/nonce, cookie nem corpo — cada
//   Nitro continua gerando o seu envelope;
// - não acrescenta `X-Forwarded-For`: o Django conta saltos dessa cadeia
//   (SHOPMAN_BFF_PROXY_SECRET) e um salto a mais gravaria o IP errado;
// - não bufferiza: SSE sai para o cliente chunk a chunk.
// Só remove cabeçalhos hop-by-hop (RFC 9110 §7.6.1), que por definição valem
// para UMA conexão e não atravessam proxy.

import { Agent, createServer, request as httpRequest } from "node:http";
import { connect } from "node:net";
import { LIVE_PATH, READY_PATH, normalizeHost } from "./config.mjs";
import { log } from "./supervisor.mjs";

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-connection",
  "transfer-encoding",
  "te",
  "trailer",
  "upgrade",
]);

/** rawHeaders ([k, v, k, v...]) sem hop-by-hop nem o que `Connection` nomeia. */
export function stripHopByHop(rawHeaders) {
  const named = new Set();
  for (let i = 0; i < rawHeaders.length; i += 2) {
    if (rawHeaders[i].toLowerCase() === "connection") {
      for (const token of rawHeaders[i + 1].split(",")) named.add(token.trim().toLowerCase());
    }
  }
  const out = [];
  for (let i = 0; i < rawHeaders.length; i += 2) {
    const key = rawHeaders[i].toLowerCase();
    if (HOP_BY_HOP.has(key) || named.has(key)) continue;
    out.push(rawHeaders[i], rawHeaders[i + 1]);
  }
  return out;
}

function plain(res, status, body, extra = {}) {
  if (res.headersSent) {
    res.destroy();
    return;
  }
  res.writeHead(status, {
    "content-type": "text/plain; charset=utf-8",
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    ...extra,
  });
  res.end(body);
}

function probe({ port, path, host, timeoutMs }) {
  return new Promise((resolvePromise) => {
    const req = httpRequest(
      { host: "127.0.0.1", port, path, method: "GET", headers: { host, accept: "application/json" }, agent: false },
      (res) => {
        res.resume();
        // 200 com HTML NÃO é saúde: app com rota catch-all renderiza a página
        // para qualquer caminho (medido no hub em 17/09: `/health/live` → 200
        // text/html). Só JSON conta — é o que as rotas de health devolvem.
        const json = String(res.headers["content-type"] || "").startsWith("application/json");
        res.once("end", () => resolvePromise(json ? res.statusCode : -res.statusCode));
        res.once("error", () => resolvePromise(0));
      },
    );
    req.setTimeout(timeoutMs, () => req.destroy(new Error("timeout")));
    req.once("error", () => resolvePromise(0));
    req.end();
  });
}

export function createRouter({
  group,
  apps,
  byHost,
  supervisor,
  healthCacheMs = 2000,
  healthTimeoutMs = 2000,
  logger = log,
}) {
  const appById = new Map(apps.map((app) => [app.id, app]));
  // Sem keep-alive para o filho: reusar socket que o Nitro acabou de fechar
  // (keepAliveTimeout de 5 s) devolve ECONNRESET ao cliente. Conexão local nova
  // custa décimos de milissegundo; 502 aleatório custa uma venda.
  const agent = new Agent({ keepAlive: false });
  const sseResponses = new Set();
  const inflight = new Set();
  const healthCache = new Map();
  const lastStatus = new Map();
  let draining = false;

  function appFor(req) {
    const byHostHeader = byHost.get(normalizeHost(req.headers.host));
    if (byHostHeader) return appById.get(byHostHeader);
    return null;
  }

  async function aggregate(kind) {
    const cached = healthCache.get(kind);
    if (cached && Date.now() - cached.at < healthCacheMs) return cached.result;
    const entries = await Promise.all(apps.map(async (app) => {
      const state = supervisor.state(app.id);
      if (state !== "up") return [app.id, { state, check: "fail" }];
      const path = kind === "ready" ? app.readyPath : app.livePath;
      const status = await probe({ port: app.port, path, host: app.hosts[0], timeoutMs: healthTimeoutMs });
      // status < 0: respondeu, mas não com JSON (ver `probe`).
      return [app.id, { state, check: status === 200 ? "ok" : "fail", status: Math.abs(status), json: status > 0 }];
    }));
    const checks = Object.fromEntries(entries);
    const ok = !draining && entries.every(([, entry]) => entry.check === "ok");
    const result = { status: ok ? "ok" : "fail", group, draining, apps: checks };
    healthCache.set(kind, { at: Date.now(), result });
    return result;
  }

  async function serveHealth(req, res, kind) {
    const result = await aggregate(kind);
    const body = req.method === "HEAD" ? undefined : JSON.stringify(result);
    res.writeHead(result.status === "ok" ? 200 : 503, {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    });
    res.end(body);
    // Loga a TRANSIÇÃO, não cada sonda: a DO pergunta a cada 10 s.
    if (lastStatus.get(kind) !== result.status) {
      logger(result.status === "ok" ? "group_healthy" : "group_unhealthy", { kind, apps: result.apps, draining });
      lastStatus.set(kind, result.status);
    }
  }

  function forward(req, res, app) {
    const upstream = httpRequest({
      host: "127.0.0.1",
      port: app.port,
      method: req.method,
      path: req.url,
      headers: stripHopByHop(req.rawHeaders),
      agent,
    });
    const entry = { res, upstream };
    inflight.add(entry);
    const finish = () => {
      inflight.delete(entry);
      sseResponses.delete(entry);
    };

    upstream.on("response", (up) => {
      const isSse = String(up.headers["content-type"] || "").startsWith("text/event-stream");
      if (isSse) sseResponses.add(entry);
      entry.up = up;
      res.writeHead(up.statusCode, up.statusMessage, stripHopByHop(up.rawHeaders));
      // Cabeçalho sai já: o EventSource só considera a conexão aberta quando
      // recebe o status, e o primeiro evento pode demorar minutos.
      res.flushHeaders();
      up.pipe(res);
      // Filho morreu no meio da resposta: corta a conexão do cliente em vez de
      // fechar o stream "limpo" — um corpo truncado não pode parecer completo.
      up.on("close", () => {
        if (!up.complete && !entry.endedByRouter) res.destroy();
      });
      up.on("error", () => res.destroy());
    });

    upstream.on("error", (error) => {
      finish();
      if (res.headersSent) {
        res.destroy();
        return;
      }
      const refused = error?.code === "ECONNREFUSED" || error?.code === "ECONNRESET";
      logger("upstream_error", { app: app.id, code: error?.code, message: String(error?.message || error) });
      plain(res, refused ? 503 : 502, refused ? `${app.id} indisponível` : `${app.id} falhou`, refused ? { "retry-after": "5" } : {});
    });

    // Cliente foi embora (fechou a aba, trocou de tela): derruba o pedido ao
    // filho, para o Nitro abortar o upstream do Django em vez de pendurá-lo.
    res.on("close", () => {
      finish();
      if (!res.writableFinished) upstream.destroy();
    });

    req.pipe(upstream);
  }

  const server = createServer((req, res) => {
    req.socket.setNoDelay(true);
    const app = appFor(req);
    if (!app) {
      const path = (req.url || "").split("?")[0];
      if ((req.method === "GET" || req.method === "HEAD") && (path === LIVE_PATH || path === READY_PATH)) {
        serveHealth(req, res, path === READY_PATH ? "ready" : "live").catch((error) => {
          logger("health_error", { message: String(error?.message || error) });
          plain(res, 503, "fail");
        });
        return;
      }
      plain(res, 404, "host desconhecido");
      return;
    }
    if (supervisor.state(app.id) !== "up") {
      plain(res, 503, `${app.id} indisponível`, { "retry-after": "5" });
      return;
    }
    forward(req, res, app);
  });

  // WebSocket/upgrade: nenhum app de operador usa hoje (conferido em 17/09),
  // mas um proxy que engole upgrade quebraria o primeiro que usar sem aviso.
  server.on("upgrade", (req, socket, head) => {
    const app = appFor(req);
    if (!app || supervisor.state(app.id) !== "up") {
      socket.end("HTTP/1.1 503 Service Unavailable\r\nconnection: close\r\ncontent-length: 0\r\n\r\n");
      return;
    }
    const upstream = connect({ host: "127.0.0.1", port: app.port }, () => {
      let head0 = `${req.method} ${req.url} HTTP/${req.httpVersion}\r\n`;
      for (let i = 0; i < req.rawHeaders.length; i += 2) head0 += `${req.rawHeaders[i]}: ${req.rawHeaders[i + 1]}\r\n`;
      upstream.write(`${head0}\r\n`);
      if (head?.length) upstream.write(head);
      upstream.pipe(socket);
      socket.pipe(upstream);
    });
    const close = () => {
      upstream.destroy();
      socket.destroy();
    };
    upstream.on("error", close);
    socket.on("error", close);
    upstream.on("close", close);
    socket.on("close", close);
  });

  return {
    server,
    get draining() {
      return draining;
    },
    stats() {
      return { inflight: inflight.size, sse: sseResponses.size };
    },
    startDraining() {
      draining = true;
      healthCache.clear();
    },
    /** Encerra os SSE com fim de stream limpo: o EventSource reconecta no contêiner novo. */
    endSseStreams() {
      for (const entry of [...sseResponses]) {
        entry.endedByRouter = true;
        entry.up?.unpipe(entry.res);
        entry.res.end();
        entry.upstream.destroy();
        sseResponses.delete(entry);
        inflight.delete(entry);
      }
    },
    nonSseInflight() {
      return inflight.size - sseResponses.size;
    },
  };
}
