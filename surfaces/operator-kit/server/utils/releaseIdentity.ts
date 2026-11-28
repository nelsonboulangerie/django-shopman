// Identidade da release do BFF (WP-RELEASE-01 R1, docs/reference/release-contract.md).
//
// O valor vem da IMAGEM: o deploy-images.yml passa SHOPMAN_BUILD_SHA,
// SHOPMAN_RELEASE_ID e SHOPMAN_RELEASE_COMPONENT como build args, e a última
// camada do Dockerfile os vira ENV. No grupo de operador (ADR-030) o roteador
// repassa a env do grupo a cada filho, então os cinco apps do chão respondem o
// mesmo commit, com `app` dizendo quem respondeu.
//
// Nada aqui chama GitHub, DigitalOcean ou Django: a resposta é constante durante a
// vida do processo. Valor fora do contrato vira vazio, porque um número inventado
// é pior que "sem identidade" (a sonda do Watchman reprova o vazio).
import { setResponseHeaders, type H3Event } from "h3";

export const RELEASE_SCHEMA_VERSION = 1;
export const RELEASE_HEADER = "x-shopman-release";

const SHA = /^[0-9a-f]{40}$/;
const RELEASE_ID = /^\d{8}-\d{4}-[0-9a-f]{7}$/;
const COMPONENT = /^[a-z0-9][a-z0-9-]{0,62}$/;

export interface ReleaseIdentity {
  schema_version: typeof RELEASE_SCHEMA_VERSION;
  component: string;
  app: string;
  release_id: string;
  build_sha: string;
}

type Env = Record<string, string | undefined>;

function clean(value: string | undefined, pattern: RegExp): string {
  const text = (value ?? "").trim().toLowerCase();
  return pattern.test(text) ? text : "";
}

/** Identidade deste processo, lida da env da imagem. Pura: o teste passa a env. */
export function readReleaseIdentity(env: Env, app: string, defaultComponent = ""): ReleaseIdentity {
  return {
    schema_version: RELEASE_SCHEMA_VERSION,
    component: clean(env.SHOPMAN_RELEASE_COMPONENT, COMPONENT) || defaultComponent,
    app: clean(app, COMPONENT),
    release_id: clean(env.SHOPMAN_RELEASE_ID, RELEASE_ID),
    build_sha: clean(env.SHOPMAN_BUILD_SHA, SHA),
  };
}

/** Corpo de GET /health/release: público, sem cache, sem segredo. */
export function respondReleaseIdentity(event: H3Event, identity: ReleaseIdentity): ReleaseIdentity {
  setResponseHeaders(event, {
    "cache-control": "no-store",
    "content-type": "application/json; charset=utf-8",
    "x-content-type-options": "nosniff",
    "x-robots-tag": "noindex",
  });
  return identity;
}
