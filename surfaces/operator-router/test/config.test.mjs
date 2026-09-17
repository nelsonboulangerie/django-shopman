import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ConfigError,
  DEFAULT_GROUPS_FILE,
  buildChildEnv,
  loadGroups,
  normalizeHost,
  parseHosts,
  resolveGroup,
} from "../src/config.mjs";
import { backoffDelay } from "../src/supervisor.mjs";

const groups = loadGroups(DEFAULT_GROUPS_FILE);
const floor = resolveGroup(groups, "operator-floor");
const office = resolveGroup(groups, "operator-office");
const app = (group, id) => group.apps.find((a) => a.id === id);

test("os dois grupos da decisão de 17/09, sem app repetido nem de fora", () => {
  assert.deepEqual(floor.apps.map((a) => a.surface), ["pos-nuxt", "kds-nuxt", "orders-nuxt", "production-nuxt", "hub-nuxt"]);
  assert.deepEqual(office.apps.map((a) => a.surface), ["marketing-nuxt", "bi-nuxt", "purchase-nuxt"]);
  assert.equal(app(office, "marketing").readyPath, "/health/ready");
  assert.ok(!JSON.stringify(groups).includes("storefront"), "storefront não entra em grupo");
});

test("grupo ausente ou desconhecido é erro de boot", () => {
  assert.throws(() => resolveGroup(groups, ""), ConfigError);
  assert.throws(() => resolveGroup(groups, "operator-everything"), ConfigError);
});

test("normalizeHost tira porta e caixa", () => {
  assert.equal(normalizeHost("PDV.Boulangerie.com.br:443"), "pdv.boulangerie.com.br");
  assert.equal(normalizeHost("[::1]:3000"), "[::1]");
  assert.equal(normalizeHost(undefined), "");
});

test("OPERATOR_HOSTS: todo app precisa de host; host de fora do grupo é erro", () => {
  const ok = parseHosts("pos=pdv.x,kds=kds.x,orders=gestor.x,production=prod.x,hub=central.x,pos=pos.localhost", floor);
  assert.equal(ok.byHost.get("pdv.x"), "pos");
  assert.equal(ok.byHost.get("pos.localhost"), "pos");
  assert.deepEqual(ok.hostsByApp.get("pos"), ["pdv.x", "pos.localhost"]);
  assert.throws(() => parseHosts("pos=pdv.x", floor), /sem host para: kds, orders, production, hub/);
  assert.throws(() => parseHosts("pos=pdv.x,kds=kds.x,orders=gestor.x,production=prod.x,hub=central.x,bi=bi.x", floor), /bi não pertence/);
  assert.throws(() => parseHosts("pos=pdv.x,kds=pdv.x,orders=g,production=p,hub=c", floor), /aponta para pos e kds/);
  assert.throws(() => parseHosts("pdv.x", floor), /sem "app=host"/);
});

test("env do filho: prefixo é privado do app, sem prefixo é do grupo, prefixo vence", () => {
  const env = {
    PATH: "/bin",
    SHOPMAN_ENVIRONMENT: "staging",
    NUXT_DJANGO_BASE_URL: "https://api.x",
    NUXT_PUBLIC_OPERATOR_HUB_URL: "https://central.x",
    POS__NUXT_PUBLIC_ORDERS_URL: "https://gestor.x/",
    POS__NUXT_PUBLIC_OPERATOR_HUB_URL: "https://central-pos.x",
    HUB__NUXT_PUBLIC_POS_URL: "https://pdv.x/",
    OPERATOR_HOSTS: "pos=pdv.x",
    OPERATOR_GROUP: "operator-floor",
    PORT: "3000",
    HOST: "0.0.0.0",
  };
  const pos = buildChildEnv({ app: app(floor, "pos"), group: floor, groups, env, port: 3101 });
  const kds = buildChildEnv({ app: app(floor, "kds"), group: floor, groups, env, port: 3102 });
  const hub = buildChildEnv({ app: app(floor, "hub"), group: floor, groups, env, port: 3105 });

  assert.equal(pos.NUXT_PUBLIC_ORDERS_URL, "https://gestor.x/");
  assert.equal(pos.NUXT_PUBLIC_OPERATOR_HUB_URL, "https://central-pos.x", "prefixo vence o grupo");
  assert.equal(pos.NUXT_PUBLIC_POS_URL, undefined, "env do hub não vaza para o PDV");
  assert.equal(kds.NUXT_PUBLIC_ORDERS_URL, undefined, "env do PDV não vaza para o KDS");
  assert.equal(kds.NUXT_PUBLIC_OPERATOR_HUB_URL, "https://central.x");
  assert.equal(hub.NUXT_PUBLIC_POS_URL, "https://pdv.x/");

  for (const child of [pos, kds, hub]) {
    assert.equal(child.NUXT_DJANGO_BASE_URL, "https://api.x");
    assert.equal(child.SHOPMAN_ENVIRONMENT, "staging");
    assert.equal(child.HOST, "127.0.0.1");
    assert.equal(child.NITRO_HOST, "127.0.0.1");
    assert.equal(child.PORT, child.NITRO_PORT);
    assert.ok(!Object.keys(child).some((k) => k.includes("__")), "nenhuma chave prefixada chega crua");
    assert.ok(!Object.keys(child).some((k) => k.startsWith("OPERATOR_")), "config do roteador não chega ao app");
  }
  assert.equal(pos.PORT, "3101");
  assert.equal(kds.PORT, "3102");
});

test("tamanho do contêiner (medidor de capacidade) chega igual a TODOS os filhos do grupo", () => {
  const env = { SHOPMAN_CONTAINER_MEMORY_LIMIT_BYTES: "1073741824", SHOPMAN_CONTAINER_CPU_CORES: "1" };
  for (const group of [floor, office]) {
    group.apps.forEach((child, index) => {
      const built = buildChildEnv({ app: child, group, groups, env, port: 3101 + index });
      assert.equal(built.SHOPMAN_CONTAINER_MEMORY_LIMIT_BYTES, "1073741824", `${child.id} sem limite de memória`);
      assert.equal(built.SHOPMAN_CONTAINER_CPU_CORES, "1", `${child.id} sem núcleos`);
    });
  }
});

test("env do filho: erros que não podem passar calados", () => {
  const build = (env) => buildChildEnv({ app: app(floor, "pos"), group: floor, groups, env, port: 3101 });
  assert.throws(() => build({ PDV__NUXT_PUBLIC_ORDERS_URL: "x" }), /PDV__ não é app/);
  assert.throws(() => build({ MARKETING__NUXT_PUBLIC_X: "x" }), /marketing não pertence ao grupo operator-floor/);
  assert.throws(() => build({ POS__PORT: "9999" }), /definida pelo launcher/);
  // Chave com `__` que não é de runtime de app e não nomeia app: é do grupo.
  assert.equal(build({ FOO__BAR: "1" }).FOO__BAR, "1");
});

test("backoff dobra até o teto", () => {
  assert.deepEqual([0, 1, 2, 3, 10].map((n) => backoffDelay(n, 500, 30000)), [500, 1000, 2000, 4000, 30000]);
});
