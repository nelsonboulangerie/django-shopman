// Ponto de entrada do container de grupo (operator-floor / operator-office).
//
// Sobe os Nitro do grupo como filhos, abre o roteador na porta do App Platform
// e cuida do encerramento. Ver docs/decisions/adr-030-operator-nuxt-dois-servicos.md.

import { realpathSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { ConfigError, loadRuntimeConfig } from "./config.mjs";
import { createRouter } from "./router.mjs";
import { Supervisor, log } from "./supervisor.mjs";

const sleep = (ms) => new Promise((resolvePromise) => setTimeout(resolvePromise, ms));

export async function waitUntil(predicate, timeoutMs, stepMs = 100) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (predicate()) return true;
    await sleep(stepMs);
  }
  return predicate();
}

/**
 * Encerramento em três tempos, dentro dos ~30 s que o orquestrador dá entre o
 * SIGTERM e o SIGKILL:
 *
 * 1. `drainDelayMs` (3 s): segue servindo TUDO. O SIGTERM e a saída do balanceador
 *    acontecem ao mesmo tempo; fechar a porta já faria o pedido que ainda chega
 *    virar 503 da plataforma. A saúde passa a responder 503.
 * 2. Fecha a porta, encerra os SSE com fim de stream limpo (o EventSource
 *    reconecta — e cai no contêiner novo, que já passou no health check) e espera
 *    os pedidos comuns em voo até `shutdownGraceMs` (15 s): uma venda no meio do
 *    POST termina.
 * 3. Corta o que sobrou, SIGTERM nos filhos, SIGKILL em quem não sair em
 *    `childKillAfterMs` (5 s).
 */
export async function shutdown({ router, supervisor, config, signal, exit = process.exit }) {
  log("shutdown_start", { signal, ...router.stats() });
  router.startDraining();
  await sleep(config.drainDelayMs);

  router.server.close();
  router.server.closeIdleConnections();
  router.endSseStreams();
  const drained = await waitUntil(() => router.nonSseInflight() <= 0, config.shutdownGraceMs);
  log("shutdown_drained", { drained, ...router.stats() });
  router.server.closeAllConnections();

  await supervisor.stopAll({ killAfterMs: config.childKillAfterMs });
  log("shutdown_done", { signal });
  exit(0);
}

export function main(env = process.env) {
  let config;
  try {
    config = loadRuntimeConfig(env);
  } catch (error) {
    if (error instanceof ConfigError) {
      log("config_error", { message: error.message });
      process.exit(78); // EX_CONFIG
    }
    throw error;
  }

  const supervisor = new Supervisor({
    apps: config.apps,
    restartBaseMs: config.restartBaseMs,
    restartMaxMs: config.restartMaxMs,
    restartStableMs: config.restartStableMs,
  });
  const router = createRouter({
    group: config.group,
    apps: config.apps,
    byHost: config.byHost,
    supervisor,
    healthCacheMs: config.healthCacheMs,
    healthTimeoutMs: config.healthTimeoutMs,
  });

  log("boot", {
    group: config.group,
    port: config.listenPort,
    apps: config.apps.map((app) => ({ id: app.id, port: app.port, hosts: app.hosts, ready: app.readyPath })),
  });
  supervisor.start();
  router.server.listen(config.listenPort, config.listenHost);

  let stopping = false;
  for (const signal of ["SIGTERM", "SIGINT"]) {
    process.on(signal, () => {
      if (stopping) return;
      stopping = true;
      shutdown({ router, supervisor, config, signal }).catch((error) => {
        log("shutdown_error", { message: String(error?.message || error) });
        process.exit(1);
      });
    });
  }

  // Roteador quebrado não pode ficar de pé com filhos órfãos: sai, e a
  // plataforma reinicia o contêiner inteiro (RESTART_COUNT avisa).
  process.on("uncaughtException", (error) => {
    log("uncaught_exception", { message: String(error?.stack || error) });
    supervisor.stopAll({ killAfterMs: 2000 }).finally(() => process.exit(1));
  });

  return { config, supervisor, router };
}

if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  main();
}
