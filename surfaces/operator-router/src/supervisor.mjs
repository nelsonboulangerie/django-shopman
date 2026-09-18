// Supervisor dos processos Nitro do grupo.
//
// Cada app roda como filho próprio (`node .output/server/index.mjs`) numa porta
// interna. O supervisor sabe três coisas por app — está `starting`, `up` ou
// `down` — e reinicia o filho que morre, com backoff exponencial e log. "up"
// não é "processo existe": é "a porta aceitou conexão". Um Nitro que ainda está
// carregando o bundle não recebe tráfego.

import { spawn as nodeSpawn } from "node:child_process";
import { connect } from "node:net";
import { createInterface } from "node:readline";

export function log(event, fields = {}) {
  process.stdout.write(
    `${JSON.stringify({ ts: new Date().toISOString(), component: "operator-router", event, ...fields })}\n`,
  );
}

/** 500, 1000, 2000... até o teto. `attempt` começa em 0. */
export function backoffDelay(attempt, baseMs, maxMs) {
  return Math.min(maxMs, baseMs * 2 ** Math.min(attempt, 20));
}

function portAccepts(port, host = "127.0.0.1", timeoutMs = 500) {
  return new Promise((resolvePromise) => {
    const socket = connect({ port, host });
    const done = (ok) => {
      socket.removeAllListeners();
      socket.destroy();
      resolvePromise(ok);
    };
    socket.setTimeout(timeoutMs, () => done(false));
    socket.once("connect", () => done(true));
    socket.once("error", () => done(false));
  });
}

export class Supervisor {
  /**
   * @param {object} options
   * @param {Array<{id:string, port:number, entry:string, env:object}>} options.apps
   * @param {(app) => import('node:child_process').ChildProcess} [options.spawn]
   */
  constructor({
    apps,
    spawn,
    restartBaseMs = 500,
    restartMaxMs = 30000,
    restartStableMs = 60000,
    readyPollMs = 200,
    logger = log,
  }) {
    this.logger = logger;
    this.restartBaseMs = restartBaseMs;
    this.restartMaxMs = restartMaxMs;
    this.restartStableMs = restartStableMs;
    this.readyPollMs = readyPollMs;
    this.spawnChild = spawn || ((app) => nodeSpawn(process.execPath, [app.entry], {
      env: app.env,
      stdio: ["ignore", "pipe", "pipe"],
    }));
    this.stopping = false;
    this.slots = new Map(
      apps.map((app) => [app.id, {
        app,
        state: "starting",
        child: null,
        attempt: 0,
        restarts: 0,
        startedAt: 0,
        timer: null,
      }]),
    );
  }

  start() {
    for (const slot of this.slots.values()) this.#launch(slot);
  }

  state(id) {
    return this.slots.get(id)?.state ?? "unknown";
  }

  snapshot() {
    return Object.fromEntries(
      [...this.slots].map(([id, slot]) => [id, { state: slot.state, restarts: slot.restarts, pid: slot.child?.pid ?? null }]),
    );
  }

  #launch(slot) {
    if (this.stopping) return;
    const { app } = slot;
    slot.state = "starting";
    slot.startedAt = Date.now();
    let child;
    try {
      child = this.spawnChild(app);
    } catch (error) {
      this.logger("child_spawn_failed", { app: app.id, error: String(error?.message || error) });
      this.#scheduleRestart(slot, null, null);
      return;
    }
    slot.child = child;
    this.logger("child_spawned", { app: app.id, pid: child.pid, port: app.port, attempt: slot.attempt });

    for (const [stream, name] of [[child.stdout, "stdout"], [child.stderr, "stderr"]]) {
      if (!stream) continue;
      const out = name === "stderr" ? process.stderr : process.stdout;
      createInterface({ input: stream }).on("line", (line) => out.write(`[${app.id}] ${line}\n`));
    }

    child.once("error", (error) => {
      this.logger("child_error", { app: app.id, error: String(error?.message || error) });
    });
    child.once("exit", (code, signal) => {
      if (slot.child !== child) return;
      slot.child = null;
      if (this.stopping) {
        slot.state = "stopped";
        this.logger("child_stopped", { app: app.id, code, signal });
        return;
      }
      this.#scheduleRestart(slot, code, signal);
    });

    const poll = async () => {
      if (slot.child !== child || this.stopping) return;
      if (await portAccepts(app.port)) {
        if (slot.child !== child || this.stopping) return;
        slot.state = "up";
        this.logger("child_up", { app: app.id, pid: child.pid, port: app.port, boot_ms: Date.now() - slot.startedAt });
        return;
      }
      slot.timer = setTimeout(poll, this.readyPollMs);
    };
    poll();
  }

  #scheduleRestart(slot, code, signal) {
    const ranMs = slot.startedAt ? Date.now() - slot.startedAt : 0;
    // Filho que ficou de pé tempo bastante zera o backoff: um crash por semana
    // não pode herdar a espera de trinta segundos de um crash-loop antigo.
    if (ranMs >= this.restartStableMs) slot.attempt = 0;
    const delay = backoffDelay(slot.attempt, this.restartBaseMs, this.restartMaxMs);
    slot.attempt += 1;
    slot.restarts += 1;
    slot.state = "down";
    clearTimeout(slot.timer);
    this.logger("child_exit", { app: slot.app.id, code, signal, ran_ms: ranMs, restart_in_ms: delay, restarts: slot.restarts });
    slot.timer = setTimeout(() => this.#launch(slot), delay);
  }

  /** SIGTERM em todos; SIGKILL em quem não saiu até `killAfterMs`. */
  async stopAll({ killAfterMs = 5000 } = {}) {
    this.stopping = true;
    const waits = [];
    for (const slot of this.slots.values()) {
      clearTimeout(slot.timer);
      const child = slot.child;
      if (!child || child.exitCode !== null || child.signalCode !== null) {
        slot.state = "stopped";
        continue;
      }
      slot.state = "stopping";
      waits.push(new Promise((resolvePromise) => {
        const killer = setTimeout(() => {
          this.logger("child_kill", { app: slot.app.id, pid: child.pid });
          child.kill("SIGKILL");
        }, killAfterMs);
        child.once("exit", () => {
          clearTimeout(killer);
          resolvePromise();
        });
        child.kill("SIGTERM");
      }));
    }
    await Promise.all(waits);
  }
}
