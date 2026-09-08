import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useOvenFacts } from "~/composables/useOvenFacts";

const env = installNuxtGlobals();

describe("useOvenFacts", () => {
  beforeEach(() => env.reset());

  it("armed declara o enfornar com a duração em segundos", async () => {
    await useOvenFacts().armed(42, 6, 15);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/production/42/oven/arm/",
      expect.objectContaining({
        method: "POST",
        body: { planned_seconds: 900, expected_rev: 6, idempotency_key: expect.any(String) },
      }),
    );
  });

  it("armed nunca manda menos de 60s (o serviço rejeitaria)", async () => {
    await useOvenFacts().armed(42, 6, 0.4);
    expect(env.fetchMock).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        body: { planned_seconds: 60, expected_rev: 6, idempotency_key: expect.any(String) },
      }),
    );
  });

  it("concluded declara o retirar com revisão e identidade da tentativa", async () => {
    await useOvenFacts().concluded(42, 7);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/production/42/oven/conclude/",
      expect.objectContaining({
        method: "POST",
        body: { expected_rev: 7, idempotency_key: expect.any(String) },
      }),
    );
  });

  it("falha terminal bloqueia o fato local e mantém erro reconciliável", async () => {
    // 400 não é transiente → sem retry, sem sleep: o teste fica rápido.
    env.fetchMock.mockRejectedValueOnce({ statusCode: 400, data: { detail: "nope" } });
    const facts = useOvenFacts();
    await expect(facts.armed(42, 6, 15)).resolves.toBe(false);
    expect(facts.errorFor(42)).toBe("nope");
    expect(facts.isPending(42)).toBe(false);
    expect(env.clientErrorReport).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ kind: "oven-fact" }),
    );
    expect(env.sonner.error).not.toHaveBeenCalled();
  });
});
