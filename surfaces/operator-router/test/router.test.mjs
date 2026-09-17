import assert from "node:assert/strict";
import { request } from "node:http";
import { connect } from "node:net";
import { after, before, describe, test } from "node:test";
import { loadRuntimeConfig } from "../src/config.mjs";
import { createRouter, stripHopByHop } from "../src/router.mjs";
import { Supervisor } from "../src/supervisor.mjs";
import { fakeGroup, freePort, freePortBase, http, sleep, waitFor } from "./helpers.mjs";

const quiet = () => {};

test("stripHopByHop remove só o que é da conexão", () => {
  const out = stripHopByHop([
    "Connection", "keep-alive, X-Private-Hop",
    "Keep-Alive", "timeout=5",
    "Transfer-Encoding", "chunked",
    "X-Private-Hop", "1",
    "Content-Security-Policy", "script-src 'nonce-a'",
    "Set-Cookie", "a=1",
    "Set-Cookie", "b=2",
    "X-Forwarded-For", "1.2.3.4, 5.6.7.8",
  ]);
  assert.deepEqual(out, [
    "Content-Security-Policy", "script-src 'nonce-a'",
    "Set-Cookie", "a=1",
    "Set-Cookie", "b=2",
    "X-Forwarded-For", "1.2.3.4, 5.6.7.8",
  ]);
});

describe("roteador com dois Nitro de verdade (processos filhos)", () => {
  let config;
  let supervisor;
  let router;
  let port;

  before(async () => {
    const base = await freePortBase(2);
    const { env } = fakeGroup({
      apps: [
        { id: "alpha", surface: "alpha-nuxt", host: "alpha.test" },
        { id: "beta", surface: "beta-nuxt", host: "beta.test", readyPath: "/health/ready" },
      ],
      extraEnv: {
        OPERATOR_CHILD_PORT_BASE: String(base),
        FAKE_ECHO_ENV: "SHARED_THING,ONLY_ALPHA,ONLY_BETA",
        SHARED_THING: "grupo",
        ALPHA__ONLY_ALPHA: "a",
        BETA__ONLY_BETA: "b",
      },
    });
    config = loadRuntimeConfig(env);
    supervisor = new Supervisor({ apps: config.apps, restartBaseMs: 100, restartMaxMs: 400, logger: quiet });
    router = createRouter({ group: config.group, apps: config.apps, byHost: config.byHost, supervisor, healthCacheMs: 0, logger: quiet });
    port = await freePort();
    supervisor.start();
    await new Promise((r) => router.server.listen(port, "127.0.0.1", r));
    await waitFor(() => supervisor.state("alpha") === "up" && supervisor.state("beta") === "up");
  });

  after(async () => {
    router.server.closeAllConnections();
    router.server.close();
    await supervisor.stopAll({ killAfterMs: 1000 });
  });

  test("Host decide o app; porta no Host não atrapalha; env de um não chega ao outro", async () => {
    const a = JSON.parse((await http({ port, host: "alpha.test", path: "/echo" })).body);
    const b = JSON.parse((await http({ port, host: "BETA.test:443", path: "/echo" })).body);
    assert.equal(a.app, "alpha");
    assert.equal(b.app, "beta");
    assert.deepEqual(a.env, { SHARED_THING: "grupo", ONLY_ALPHA: "a", ONLY_BETA: null });
    assert.deepEqual(b.env, { SHARED_THING: "grupo", ONLY_ALPHA: null, ONLY_BETA: "b" });
    assert.notEqual(a.port, b.port);
    assert.equal(b.host, "BETA.test:443", "Host chega ao Nitro como veio");
  });

  test("cabeçalhos passam intactos: CSP do app, set-cookie duplicado, XFF sem salto a mais", async () => {
    const res = await http({ port, host: "alpha.test", path: "/echo", headers: { "x-forwarded-for": "200.1.1.1, 10.0.0.1" } });
    assert.equal(res.headers["content-security-policy"], "script-src 'nonce-alpha'");
    assert.deepEqual(res.headers["set-cookie"], ["a=1; Path=/", "b=2; Path=/"]);
    assert.equal(JSON.parse(res.body).xff, "200.1.1.1, 10.0.0.1");
    const noXff = JSON.parse((await http({ port, host: "alpha.test", path: "/echo" })).body);
    assert.equal(noXff.xff, null, "o roteador não inventa X-Forwarded-For");
  });

  test("corpo de POST atravessa", async () => {
    const res = await http({ port, host: "beta.test", path: "/post", method: "POST", body: "venda=42", headers: { "content-type": "text/plain", "content-length": "8" } });
    assert.equal(res.status, 201);
    assert.equal(res.body, "beta:venda=42");
  });

  test("host desconhecido: 404, exceto as sondas de saúde do grupo", async () => {
    assert.equal((await http({ port, host: "gamma.test", path: "/" })).status, 404);
    const live = await http({ port, host: "10.0.0.7:3000", path: "/health/live" });
    assert.equal(live.status, 200);
    const body = JSON.parse(live.body);
    assert.equal(body.status, "ok");
    assert.deepEqual(Object.keys(body.apps), ["alpha", "beta"]);
    // No host de um app, /health/live é do APP, não do grupo.
    assert.equal(JSON.parse((await http({ port, host: "alpha.test", path: "/health/live" })).body).app, "alpha");
  });

  test("SSE sai sem buffer: cada evento chega no ritmo em que o Nitro escreve", async () => {
    const arrivals = await new Promise((resolvePromise, reject) => {
      const seen = [];
      const started = Date.now();
      const req = request({ host: "127.0.0.1", port, path: "/sse?every=150", headers: { host: "alpha.test", accept: "text/event-stream" }, agent: false }, (res) => {
        assert.equal(res.headers["content-type"], "text/event-stream");
        assert.equal(res.headers["x-accel-buffering"], "no");
        res.setEncoding("utf8");
        res.on("data", (chunk) => {
          for (const m of chunk.matchAll(/data: (\{.*\})/g)) {
            seen.push({ ...JSON.parse(m[1]), at: Date.now() - started, delay: Date.now() - JSON.parse(m[1]).sentAt });
          }
          if (seen.length >= 4) {
            req.destroy();
            resolvePromise(seen);
          }
        });
      });
      req.on("error", (e) => (e.code === "ECONNRESET" ? null : reject(e)));
      req.end();
    });
    // Buffer apareceria como eventos chegando juntos no fim. Aqui cada um chega
    // em < 100 ms depois de escrito, e espaçados pelo ritmo do emissor.
    for (const event of arrivals) assert.ok(event.delay < 100, `evento ${event.n} atrasou ${event.delay} ms`);
    for (let i = 1; i < arrivals.length; i += 1) {
      assert.ok(arrivals[i].at - arrivals[i - 1].at >= 80, `eventos ${i} e ${i + 1} chegaram colados`);
    }
  });

  test("cliente que fecha o SSE fecha a conexão no Nitro também", async () => {
    const req = request({ host: "127.0.0.1", port, path: "/sse?every=50", headers: { host: "beta.test" }, agent: false });
    req.on("error", () => {});
    await new Promise((r) => {
      req.on("response", (res) => res.once("data", r));
      req.end();
    });
    await waitFor(async () => JSON.parse((await http({ port, host: "beta.test", path: "/stats" })).body).openSse === 1);
    req.destroy();
    await waitFor(async () => JSON.parse((await http({ port, host: "beta.test", path: "/stats" })).body).openSse === 0);
  });

  test("upgrade (WebSocket) atravessa nos dois sentidos", async () => {
    const socket = connect({ port, host: "127.0.0.1" });
    let received = "";
    socket.setEncoding("utf8");
    socket.on("data", (d) => { received += d; });
    socket.write("GET /ws HTTP/1.1\r\nHost: alpha.test\r\nConnection: Upgrade\r\nUpgrade: echo\r\n\r\n");
    await waitFor(() => received.includes("hello-from-alpha"));
    socket.write("ping\n");
    await waitFor(() => received.includes("ping"));
    assert.match(received, /^HTTP\/1\.1 101/);
    socket.destroy();
  });

  test("app morto: 503 só no host dele, o outro segue; supervisor reinicia; grupo volta a saudável", async () => {
    const pidBefore = JSON.parse((await http({ port, host: "beta.test", path: "/stats" })).body).pid;
    await http({ port, host: "beta.test", path: "/crash" });
    await waitFor(() => supervisor.state("beta") !== "up");

    const dead = await http({ port, host: "beta.test", path: "/echo" });
    assert.equal(dead.status, 503);
    assert.equal(dead.headers["retry-after"], "5");
    assert.equal((await http({ port, host: "alpha.test", path: "/echo" })).status, 200, "alpha não cai junto");

    const live = await http({ port, host: "probe", path: "/health/live" });
    assert.equal(live.status, 503);
    assert.equal(JSON.parse(live.body).apps.beta.check, "fail");
    assert.equal(JSON.parse(live.body).apps.alpha.check, "ok");

    await waitFor(() => supervisor.state("beta") === "up");
    const pidAfter = JSON.parse((await http({ port, host: "beta.test", path: "/stats" })).body).pid;
    assert.notEqual(pidAfter, pidBefore, "é um processo novo");
    assert.equal(supervisor.snapshot().beta.restarts, 1);
    assert.equal((await http({ port, host: "probe", path: "/health/live" })).status, 200);
  });

  test("readiness usa o readyPath do app (o do Marketing inclui o Django)", async () => {
    const ready = JSON.parse((await http({ port, host: "probe", path: "/health/ready" })).body);
    assert.equal(ready.status, "ok");
    assert.equal(ready.apps.beta.status, 200);
  });
});

test("saúde agregada não aceita 200 em HTML (app com catch-all renderizando a página)", async () => {
  const base = await freePortBase(2);
  const { env } = fakeGroup({
    apps: [
      { id: "json", surface: "json-nuxt", host: "json.test" },
      { id: "page", surface: "page-nuxt", host: "page.test" },
    ],
    extraEnv: { OPERATOR_CHILD_PORT_BASE: String(base), PAGE__FAKE_HTML_HEALTH: "1" },
  });
  const config = loadRuntimeConfig(env);
  const supervisor = new Supervisor({ apps: config.apps, logger: quiet });
  const router = createRouter({ group: config.group, apps: config.apps, byHost: config.byHost, supervisor, healthCacheMs: 0, logger: quiet });
  const port = await freePort();
  supervisor.start();
  await new Promise((r) => router.server.listen(port, "127.0.0.1", r));
  try {
    await waitFor(() => supervisor.state("json") === "up" && supervisor.state("page") === "up");
    const res = await http({ port, host: "probe", path: "/health/live" });
    const body = JSON.parse(res.body);
    assert.equal(res.status, 503);
    assert.deepEqual(body.apps.page, { state: "up", check: "fail", status: 200, json: false });
    assert.equal(body.apps.json.check, "ok");
  } finally {
    router.server.closeAllConnections();
    router.server.close();
    await supervisor.stopAll({ killAfterMs: 1000 });
  }
});

describe("supervisor", () => {
  test("filho que não sobe fica em backoff crescente e nunca vira up", async () => {
    const base = await freePortBase(1);
    const { env } = fakeGroup({
      apps: [{ id: "broken", surface: "broken-nuxt", host: "broken.test" }],
      extraEnv: { OPERATOR_CHILD_PORT_BASE: String(base), BROKEN__FAKE_BOOT_FAIL: "1" },
    });
    const config = loadRuntimeConfig(env);
    const events = [];
    const supervisor = new Supervisor({
      apps: config.apps,
      restartBaseMs: 50,
      restartMaxMs: 200,
      logger: (event, fields) => events.push({ event, ...fields }),
    });
    supervisor.start();
    await waitFor(() => events.filter((e) => e.event === "child_exit").length >= 4, { timeoutMs: 10000 });
    await supervisor.stopAll({ killAfterMs: 500 });
    const delays = events.filter((e) => e.event === "child_exit").map((e) => e.restart_in_ms);
    assert.deepEqual(delays.slice(0, 4), [50, 100, 200, 200]);
    assert.equal(events.find((e) => e.event === "child_exit").code, 3);
    assert.ok(!events.some((e) => e.event === "child_up"));
    await sleep(300);
    assert.equal(events.filter((e) => e.event === "child_spawned").length, delays.length, "parado não reinicia");
  });
});
