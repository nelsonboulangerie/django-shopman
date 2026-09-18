// Configuração do grupo: quais apps, em que Host, com que variáveis.
//
// Tudo aqui é função pura sobre (groups.json, env). Erro de configuração é
// ERRO DE BOOT: o processo sai com código ≠ 0 e o deploy da DigitalOcean
// reprova, com o motivo no log. Um grupo que sobe "meio configurado" é o modo
// de falhar que se descobre no balcão.

import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
export const DEFAULT_GROUPS_FILE = join(HERE, "..", "groups.json");
export const DEFAULT_APPS_DIR = join(HERE, "..", "..", "apps");

export const LIVE_PATH = "/health/live";
export const READY_PATH = "/health/ready";

// Chaves que o launcher DEFINE para cada filho. Herdar do container faria dois
// Nitro disputarem a mesma porta; aceitar por prefixo (`POS__PORT`) seria abrir
// a mesma porta por outro caminho.
const RESERVED_CHILD_KEYS = new Set(["PORT", "HOST", "NITRO_PORT", "NITRO_HOST"]);

// Configuração do próprio roteador. Não é da conta de app nenhum.
const ROUTER_KEY = /^OPERATOR_(GROUP|GROUPS_FILE|HOSTS|APPS_DIR|CHILD_PORT_BASE|HEALTH_|SHUTDOWN_|RESTART_)/;

// `<APP>__<CHAVE>`: o prefixo é o id do app em maiúsculas.
const PREFIXED = /^([A-Z][A-Z0-9]*)__(.+)$/;
// Chave que parece destinada a um app (runtime do Nuxt/Nitro/Node). Com prefixo
// desconhecido, é quase sempre erro de digitação (`PDV__` no lugar de `POS__`)
// e, se passasse calada, o app subiria sem a URL que o operador precisa.
const APP_LOOKING = /^(NUXT_|NITRO_|NODE_)/;

export class ConfigError extends Error {
  constructor(message) {
    super(message);
    this.name = "ConfigError";
  }
}

export function loadGroups(file = DEFAULT_GROUPS_FILE) {
  return JSON.parse(readFileSync(file, "utf8"));
}

export function envPrefix(appId) {
  return `${appId.toUpperCase()}__`;
}

/** Todos os ids de app de todos os grupos — para reconhecer prefixo de OUTRO grupo. */
export function allAppIds(groups) {
  return Object.values(groups).flatMap((group) => group.apps.map((app) => app.id));
}

export function resolveGroup(groups, name) {
  if (!name) throw new ConfigError("OPERATOR_GROUP ausente: o container não sabe que grupo é.");
  const group = groups[name];
  if (!group) {
    throw new ConfigError(
      `OPERATOR_GROUP=${name} desconhecido; grupos: ${Object.keys(groups).join(", ")}.`,
    );
  }
  const ids = new Set();
  for (const app of group.apps) {
    if (!/^[a-z][a-z0-9]*$/.test(app.id)) throw new ConfigError(`id de app inválido: ${app.id}`);
    if (ids.has(app.id)) throw new ConfigError(`app repetido no grupo ${name}: ${app.id}`);
    ids.add(app.id);
  }
  return { name, apps: group.apps };
}

/** Host sem porta, minúsculo. `[::1]:3000` → `[::1]`. */
export function normalizeHost(raw) {
  if (!raw) return "";
  const value = String(raw).trim().toLowerCase();
  if (value.startsWith("[")) {
    const end = value.indexOf("]");
    return end === -1 ? value : value.slice(0, end + 1);
  }
  const colon = value.indexOf(":");
  return colon === -1 ? value : value.slice(0, colon);
}

/**
 * `OPERATOR_HOSTS="pos=pdv.boulangerie.com.br,kds=kds.boulangerie.com.br"`.
 * Um app pode ter mais de um host (`pos=pdv.x,pos=pdv.localhost`). Todo app do
 * grupo precisa de pelo menos um; host de app fora do grupo é erro.
 */
export function parseHosts(raw, group) {
  const ids = new Set(group.apps.map((app) => app.id));
  const byHost = new Map();
  const hostsByApp = new Map(group.apps.map((app) => [app.id, []]));
  for (const pair of String(raw || "").split(",").map((p) => p.trim()).filter(Boolean)) {
    const eq = pair.indexOf("=");
    if (eq <= 0) throw new ConfigError(`OPERATOR_HOSTS: par sem "app=host": ${pair}`);
    const id = pair.slice(0, eq).trim();
    const host = normalizeHost(pair.slice(eq + 1));
    if (!ids.has(id)) throw new ConfigError(`OPERATOR_HOSTS: app ${id} não pertence ao grupo ${group.name}.`);
    if (!host) throw new ConfigError(`OPERATOR_HOSTS: host vazio para ${id}.`);
    if (byHost.has(host) && byHost.get(host) !== id) {
      throw new ConfigError(`OPERATOR_HOSTS: ${host} aponta para ${byHost.get(host)} e ${id}.`);
    }
    byHost.set(host, id);
    hostsByApp.get(id).push(host);
  }
  const orphans = [...hostsByApp].filter(([, hosts]) => hosts.length === 0).map(([id]) => id);
  if (orphans.length) {
    throw new ConfigError(`OPERATOR_HOSTS sem host para: ${orphans.join(", ")} (grupo ${group.name}).`);
  }
  return { byHost, hostsByApp };
}

/**
 * O ambiente de UM filho. Regra (documentada na ADR-030 e no README):
 *
 * 1. `<APP>__<CHAVE>` chega a ESTE app como `<CHAVE>`, e a nenhum outro.
 * 2. Chave sem prefixo de app é do GRUPO: chega a todos os filhos. É onde
 *    moram as envs do nível do app na DO e as que os apps do grupo têm com o
 *    mesmo valor (`NUXT_DJANGO_BASE_URL`, `NUXT_DJANGO_PROXY_SECRET`...).
 * 3. O prefixo vence a chave do grupo.
 * 4. `PORT`/`HOST`/`NITRO_PORT`/`NITRO_HOST` são do launcher; `OPERATOR_*` é
 *    do roteador. Nenhum dos dois chega ao app.
 *
 * Falha alto (ConfigError) para: prefixo de app de OUTRO grupo (spec copiado
 * errado), prefixo desconhecido em chave de runtime (`PDV__NUXT_...`) e
 * tentativa de fixar chave reservada por prefixo.
 */
export function buildChildEnv({ app, group, groups, env, port }) {
  const everyId = new Set(allAppIds(groups));
  const groupIds = new Set(group.apps.map((a) => a.id));
  const shared = {};
  const own = {};
  for (const [key, value] of Object.entries(env)) {
    if (value === undefined) continue;
    if (ROUTER_KEY.test(key)) continue;
    const match = PREFIXED.exec(key);
    if (match) {
      const id = match[1].toLowerCase();
      const inner = match[2];
      if (groupIds.has(id)) {
        if (RESERVED_CHILD_KEYS.has(inner)) {
          throw new ConfigError(`${key}: ${inner} é definida pelo launcher, não por app.`);
        }
        if (id === app.id) own[inner] = value;
        continue;
      }
      if (everyId.has(id)) {
        throw new ConfigError(`${key}: ${id} não pertence ao grupo ${group.name}.`);
      }
      if (APP_LOOKING.test(inner)) {
        throw new ConfigError(`${key}: prefixo ${match[1]}__ não é app de grupo nenhum.`);
      }
    }
    if (RESERVED_CHILD_KEYS.has(key)) continue;
    shared[key] = value;
  }
  return {
    ...shared,
    ...own,
    HOST: "127.0.0.1",
    PORT: String(port),
    NITRO_HOST: "127.0.0.1",
    NITRO_PORT: String(port),
  };
}

function intFrom(env, key, fallback) {
  const raw = env[key];
  if (raw === undefined || raw === "") return fallback;
  const value = Number.parseInt(raw, 10);
  if (!Number.isFinite(value) || value < 0) throw new ConfigError(`${key}=${raw} não é inteiro ≥ 0.`);
  return value;
}

/** Tudo o que o main precisa, validado. Lança ConfigError. */
export function loadRuntimeConfig(env = process.env) {
  const groups = loadGroups(env.OPERATOR_GROUPS_FILE || DEFAULT_GROUPS_FILE);
  const group = resolveGroup(groups, env.OPERATOR_GROUP);
  const hosts = parseHosts(env.OPERATOR_HOSTS, group);
  const appsDir = resolve(env.OPERATOR_APPS_DIR || DEFAULT_APPS_DIR);
  const portBase = intFrom(env, "OPERATOR_CHILD_PORT_BASE", 3100);
  const apps = group.apps.map((app, index) => {
    const port = portBase + 1 + index;
    return {
      id: app.id,
      surface: app.surface,
      port,
      entry: join(appsDir, app.surface, ".output", "server", "index.mjs"),
      livePath: app.livePath || LIVE_PATH,
      readyPath: app.readyPath || app.livePath || LIVE_PATH,
      hosts: hosts.hostsByApp.get(app.id),
      env: buildChildEnv({ app, group, groups, env, port }),
    };
  });
  return {
    group: group.name,
    apps,
    byHost: hosts.byHost,
    listenPort: intFrom(env, "PORT", 3000),
    listenHost: env.HOST || "0.0.0.0",
    healthCacheMs: intFrom(env, "OPERATOR_HEALTH_CACHE_MS", 2000),
    healthTimeoutMs: intFrom(env, "OPERATOR_HEALTH_TIMEOUT_MS", 2000),
    drainDelayMs: intFrom(env, "OPERATOR_SHUTDOWN_DRAIN_DELAY_MS", 3000),
    shutdownGraceMs: intFrom(env, "OPERATOR_SHUTDOWN_GRACE_MS", 15000),
    childKillAfterMs: intFrom(env, "OPERATOR_SHUTDOWN_CHILD_KILL_MS", 5000),
    restartBaseMs: intFrom(env, "OPERATOR_RESTART_BASE_MS", 500),
    restartMaxMs: intFrom(env, "OPERATOR_RESTART_MAX_MS", 30000),
    restartStableMs: intFrom(env, "OPERATOR_RESTART_STABLE_MS", 60000),
  };
}
