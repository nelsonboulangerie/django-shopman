import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { request } from "node:http";
import { test } from "node:test";
import { MAIN, fakeGroup, freePort, freePortBase, http, waitFor } from "./helpers.mjs";

function startMain(env) {
  const child = spawn(process.execPath, [MAIN], { env, stdio: ["ignore", "pipe", "pipe"] });
  const lines = [];
  child.stdout.setEncoding("utf8");
  child.stdout.on("data", (d) => lines.push(...d.split("\n").filter(Boolean)));
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (d) => lines.push(...d.split("\n").filter(Boolean)));
  const exited = new Promise((r) => child.once("exit", (code, signal) => r({ code, signal })));
  return { child, lines, exited };
}

const events = (lines) => lines.filter((l) => l.startsWith("{")).map((l) => JSON.parse(l));

test("config inválida: sai com 78 e diz por quê (deploy reprova alto)", async () => {
  const { env } = fakeGroup({ apps: [{ id: "alpha", surface: "alpha-nuxt", host: "alpha.test" }] });
  const { lines, exited } = startMain({ ...env, OPERATOR_HOSTS: "", PORT: String(await freePort()) });
  const { code } = await exited;
  assert.equal(code, 78);
  assert.match(events(lines).find((e) => e.event === "config_error").message, /sem host para: alpha/);
});

test("SIGTERM: pedido em voo termina, SSE fecha limpo, filhos saem, processo sai 0", async () => {
  const base = await freePortBase(2);
  const port = await freePort();
  const { env } = fakeGroup({
    apps: [
      { id: "alpha", surface: "alpha-nuxt", host: "alpha.test" },
      { id: "beta", surface: "beta-nuxt", host: "beta.test" },
    ],
    extraEnv: {
      PORT: String(port),
      HOST: "127.0.0.1",
      OPERATOR_CHILD_PORT_BASE: String(base),
      OPERATOR_SHUTDOWN_DRAIN_DELAY_MS: "300",
      OPERATOR_SHUTDOWN_GRACE_MS: "3000",
    },
  });
  const { child, lines, exited } = startMain(env);
  await waitFor(async () => (await http({ port, host: "probe", path: "/health/live" })).status === 200, { timeoutMs: 15000 });
  const childPids = await Promise.all(["alpha.test", "beta.test"].map(async (host) => JSON.parse((await http({ port, host, path: "/stats" })).body).pid));

  // SSE aberto, esperando o fim.
  const sse = new Promise((resolvePromise) => {
    const req = request({ host: "127.0.0.1", port, path: "/sse?every=100", headers: { host: "alpha.test" }, agent: false }, (res) => {
      let events = 0;
      res.setEncoding("utf8");
      res.on("data", (c) => { events += (c.match(/data:/g) || []).length; });
      res.on("end", () => resolvePromise({ how: "end", events }));
      res.on("error", (e) => resolvePromise({ how: `error:${e.code}`, events }));
      res.on("aborted", () => resolvePromise({ how: "aborted", events }));
    });
    req.on("error", (e) => resolvePromise({ how: `req-error:${e.code}`, events: 0 }));
    req.end();
  });
  await new Promise((r) => setTimeout(r, 250));

  // Pedido lento (1,2 s) em voo quando o SIGTERM chega.
  const slow = http({ port, host: "beta.test", path: "/slow?ms=1200", timeoutMs: 8000 });
  await new Promise((r) => setTimeout(r, 100));
  const sentAt = Date.now();
  child.kill("SIGTERM");

  // Durante o atraso de drenagem, ainda serve — e a saúde já diz 503.
  const duringDrain = await http({ port, host: "alpha.test", path: "/echo" });
  assert.equal(duringDrain.status, 200);
  assert.equal((await http({ port, host: "probe", path: "/health/live" })).status, 503);

  const slowRes = await slow;
  assert.equal(slowRes.status, 200);
  assert.equal(slowRes.body, "beta:slow-done");

  const sseResult = await sse;
  assert.equal(sseResult.how, "end", "SSE termina com fim de stream, não com conexão cortada");
  assert.ok(sseResult.events >= 2);

  const { code } = await exited;
  assert.equal(code, 0);
  assert.ok(Date.now() - sentAt < 3000 + 300 + 2000, "não estoura a janela de encerramento");
  for (const pid of childPids) {
    assert.throws(() => process.kill(pid, 0), /ESRCH/, `filho ${pid} ficou órfão`);
  }
  const names = events(lines).map((e) => e.event);
  for (const expected of ["shutdown_start", "shutdown_drained", "child_stopped", "shutdown_done"]) {
    assert.ok(names.includes(expected), `log sem ${expected}`);
  }
  assert.ok(!names.includes("child_exit"), "encerramento não é tratado como crash (sem restart)");
});
