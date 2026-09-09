import { beforeEach, describe, expect, it } from "vitest";
import { ref } from "vue";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useOvenFacts } from "~/composables/useOvenFacts";
import type { QCKioskProjection } from "~/generated/productionContract";

const env = installNuxtGlobals();

function facts(overrides: Record<string, unknown> = {}) {
  const projection = {
    generated_at: "2099-01-01T11:59:00Z",
    source_revision: "qc:1",
    fresh_until: "2099-01-01T12:01:00Z",
    contract_version: 1,
    actions: [
      {
        ref: "oven_arm:42",
        enabled: true,
        proof: "oven-arm-proof",
        expected_rev: 6,
      },
      {
        ref: "oven_conclude:42",
        enabled: true,
        proof: "oven-conclude-proof",
        expected_rev: 7,
      },
    ],
    ...overrides,
  } as QCKioskProjection;
  return useOvenFacts(ref(projection), env.refresh);
}

describe("useOvenFacts", () => {
  beforeEach(() => env.reset());

  it("armed declara o enfornar com a duração em segundos", async () => {
    await facts().armed(42, 6, 15);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/production/42/oven/arm/",
      expect.objectContaining({
        method: "POST",
        body: expect.objectContaining({
          planned_seconds: 900,
          expected_rev: 6,
          projection_generated_at: "2099-01-01T11:59:00Z",
          source_revision: "qc:1",
          fresh_until: "2099-01-01T12:01:00Z",
          contract_version: 1,
          action_ref: "oven_arm:42",
          action_proof: "oven-arm-proof",
          idempotency_key: expect.any(String),
        }),
      }),
    );
  });

  it("armed nunca manda menos de 60s (o serviço rejeitaria)", async () => {
    await facts().armed(42, 6, 0.4);
    expect(env.fetchMock).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        body: expect.objectContaining({
          planned_seconds: 60,
          expected_rev: 6,
          idempotency_key: expect.any(String),
        }),
      }),
    );
  });

  it("concluded declara o retirar com revisão e identidade da tentativa", async () => {
    await facts().concluded(42, 7);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/production/42/oven/conclude/",
      expect.objectContaining({
        method: "POST",
        body: expect.objectContaining({
          expected_rev: 7,
          source_revision: "qc:1",
          contract_version: 1,
          action_ref: "oven_conclude:42",
          action_proof: "oven-conclude-proof",
          idempotency_key: expect.any(String),
        }),
      }),
    );
  });

  it("falha terminal bloqueia o fato local e mantém erro reconciliável", async () => {
    // 400 não é transiente → sem retry, sem sleep: o teste fica rápido.
    env.fetchMock.mockRejectedValueOnce({ statusCode: 400, data: { detail: "nope" } });
    const ovenFacts = facts();
    await expect(ovenFacts.armed(42, 6, 15)).resolves.toBe(false);
    expect(ovenFacts.errorFor(42)).toBe("nope");
    expect(ovenFacts.isPending(42)).toBe(false);
    expect(env.clientErrorReport).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ kind: "oven-fact" }),
    );
    expect(env.sonner.error).not.toHaveBeenCalled();
  });

  it("não cria timer/fato remoto quando offline", async () => {
    env.isOnline.value = false;
    const ovenFacts = facts();

    await expect(ovenFacts.armed(42, 6, 15)).resolves.toBe(false);
    expect(env.fetchMock).not.toHaveBeenCalled();
    expect(ovenFacts.isPending(42)).toBe(false);
    expect(ovenFacts.errorFor(42)).toContain("Sem conexão");
  });
});
