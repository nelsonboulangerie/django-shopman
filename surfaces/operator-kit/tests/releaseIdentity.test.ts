// WP-RELEASE-01 R1: o endereço /health/release do BFF e a linha "Versão do serviço".
import { describe, expect, it } from "vitest";
import { releaseLabel } from "../app/presentation/release";
import { readReleaseIdentity } from "../server/utils/releaseIdentity";

const SHA = "d".repeat(40);
const RELEASE_ID = "20261102-1403-ddddddd";

describe("readReleaseIdentity", () => {
  it("lê a identidade da imagem e diz qual app respondeu", () => {
    expect(
      readReleaseIdentity(
        { SHOPMAN_BUILD_SHA: SHA, SHOPMAN_RELEASE_ID: RELEASE_ID, SHOPMAN_RELEASE_COMPONENT: "operator-floor" },
        "pos",
      ),
    ).toEqual({ schema_version: 1, component: "operator-floor", app: "pos", release_id: RELEASE_ID, build_sha: SHA });
  });

  it("nunca inventa valor: build sem identidade responde vazio", () => {
    expect(readReleaseIdentity({}, "kds")).toEqual({
      schema_version: 1,
      component: "",
      app: "kds",
      release_id: "",
      build_sha: "",
    });
  });

  it("valor fora do contrato vira vazio", () => {
    const identity = readReleaseIdentity({ SHOPMAN_BUILD_SHA: "main", SHOPMAN_RELEASE_ID: "v2.3.1" }, "");
    expect(identity.build_sha).toBe("");
    expect(identity.release_id).toBe("");
  });

  it("não expõe nenhuma outra variável do ambiente", () => {
    const identity = readReleaseIdentity({ NUXT_DJANGO_PROXY_SECRET: "segredo", SHOPMAN_BUILD_SHA: SHA }, "pos");
    expect(JSON.stringify(identity)).not.toContain("segredo");
    expect(Object.keys(identity).sort()).toEqual(["app", "build_sha", "component", "release_id", "schema_version"]);
  });
});

describe("releaseLabel", () => {
  it("diz a versão do serviço com o Release ID", () => {
    expect(releaseLabel({ release_id: RELEASE_ID })).toBe(`Versão do serviço: ${RELEASE_ID}`);
  });

  it("some sem identidade, sem resposta ou com valor fora do contrato", () => {
    expect(releaseLabel(null)).toBe("");
    expect(releaseLabel({ release_id: "" })).toBe("");
    expect(releaseLabel({ release_id: "latest" })).toBe("");
  });
});
