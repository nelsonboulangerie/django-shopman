import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { request } from "node:http";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
export const FAKE_NITRO = join(HERE, "fixtures", "fake-nitro.mjs");
export const MAIN = join(HERE, "..", "src", "main.mjs");

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function freePort() {
  return new Promise((resolvePromise, reject) => {
    const srv = createServer();
    srv.listen(0, "127.0.0.1", () => {
      const { port } = srv.address();
      srv.close(() => resolvePromise(port));
    });
    srv.on("error", reject);
  });
}

/** Porta base com N portas livres em sequência (as dos filhos são base+1..base+N). */
export async function freePortBase(count) {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    const base = 20000 + Math.floor(Math.random() * 30000);
    const ok = await Promise.all(
      Array.from({ length: count + 1 }, (_, i) => new Promise((r) => {
        const srv = createServer();
        srv.once("error", () => r(false));
        srv.listen(base + i, "127.0.0.1", () => srv.close(() => r(true)));
      })),
    );
    if (ok.every(Boolean)) return base;
  }
  throw new Error("sem portas livres");
}

/**
 * Monta um "container" de mentira: groups.json + apps/<surface>/.output/server/index.mjs
 * que importa o Nitro falso. Devolve o env para `loadRuntimeConfig`/`main.mjs`.
 */
export function fakeGroup({ group = "test-group", apps, extraEnv = {} }) {
  const root = mkdtempSync(join(tmpdir(), "operator-router-"));
  const appsDir = join(root, "apps");
  const groups = { [group]: { apps: apps.map(({ id, surface, readyPath }) => ({ id, surface, ...(readyPath ? { readyPath } : {}) })) } };
  // Um segundo grupo, para exercitar "prefixo de app de outro grupo".
  groups["other-group"] = { apps: [{ id: "intruder", surface: "intruder-nuxt" }] };
  const groupsFile = join(root, "groups.json");
  writeFileSync(groupsFile, JSON.stringify(groups));
  for (const app of apps) {
    const dir = join(appsDir, app.surface, ".output", "server");
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "index.mjs"), `import ${JSON.stringify(pathToFileURL(FAKE_NITRO).href)};\n`);
  }
  const env = {
    PATH: process.env.PATH,
    OPERATOR_GROUP: group,
    OPERATOR_GROUPS_FILE: groupsFile,
    OPERATOR_APPS_DIR: appsDir,
    OPERATOR_HOSTS: apps.map((a) => `${a.id}=${a.host}`).join(","),
    OPERATOR_HEALTH_CACHE_MS: "0",
    OPERATOR_RESTART_BASE_MS: "100",
    OPERATOR_RESTART_MAX_MS: "400",
    ...Object.fromEntries(apps.map((a) => [`${a.id.toUpperCase()}__FAKE_NAME`, a.id])),
    ...extraEnv,
  };
  return { root, env };
}

export function http({ port, host, path = "/", method = "GET", headers = {}, body, timeoutMs = 5000 }) {
  return new Promise((resolvePromise, reject) => {
    const req = request({ host: "127.0.0.1", port, path, method, headers: { host, ...headers }, agent: false }, (res) => {
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => resolvePromise({ status: res.statusCode, headers: res.headers, rawHeaders: res.rawHeaders, body: Buffer.concat(chunks).toString() }));
      res.on("error", reject);
    });
    req.setTimeout(timeoutMs, () => req.destroy(new Error("timeout")));
    req.on("error", reject);
    if (body) req.write(body);
    req.end();
  });
}

export async function waitFor(predicate, { timeoutMs = 10000, stepMs = 50 } = {}) {
  const deadline = Date.now() + timeoutMs;
  let last;
  while (Date.now() < deadline) {
    try {
      last = await predicate();
      if (last) return last;
    } catch (error) {
      last = error;
    }
    await sleep(stepMs);
  }
  throw new Error(`waitFor: tempo esgotado (último: ${last})`);
}
