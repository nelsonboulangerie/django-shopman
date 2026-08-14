import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useOvenFacts } from "~/composables/useOvenFacts";

const env = installNuxtGlobals();

describe("useOvenFacts", () => {
  beforeEach(() => env.reset());

  it("armed declara o enfornar com a duração em segundos", async () => {
    await useOvenFacts().armed(42, 15);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/production/42/oven/arm/",
      expect.objectContaining({ method: "POST", body: { planned_seconds: 900 } }),
    );
  });

  it("armed nunca manda menos de 60s (o serviço rejeitaria)", async () => {
    await useOvenFacts().armed(42, 0.4);
    expect(env.fetchMock).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ body: { planned_seconds: 60 } }),
    );
  });

  it("concluded declara o retirar, sem corpo", async () => {
    await useOvenFacts().concluded(42);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/production/42/oven/conclude/",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("falha terminal não estoura nem toasta: vira relato de erro", async () => {
    // 400 não é transiente → sem retry, sem sleep: o teste fica rápido.
    env.fetchMock.mockRejectedValueOnce({ statusCode: 400, data: { detail: "nope" } });
    await expect(useOvenFacts().armed(42, 15)).resolves.toBeUndefined();
    expect(env.clientErrorReport).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ kind: "oven-fact" }),
    );
    expect(env.sonner.error).not.toHaveBeenCalled();
  });
});
