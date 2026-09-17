import { mockNuxtImport } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { installNuxtGlobals } from "../support/composableEnv";
import { CAPACITY_ROUTE, useOperatorCapacity } from "../../app/composables/useOperatorCapacity";

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));

mockNuxtImport("$fetch", () => fetchMock);

const env = installNuxtGlobals();

const RESPONSE = {
  service: "pos",
  available: true,
  memory: { used_bytes: 1, limit_bytes: 2, percent: 50 },
  cpu: { percent: 10, limit_cores: 1, window_ms: 30_000 },
  measured_at: "2026-09-17T15:00:00.000Z",
  level: "normal",
  thresholds: { attention_percent: 75, critical_percent: 90, sustain_minutes: 5 },
};

function setVisibility(state: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
}

describe("useOperatorCapacity — leitura calma do serviço", () => {
  beforeEach(() => {
    env.reset();
    fetchMock.mockReset();
    setVisibility("visible");
  });
  afterEach(() => setVisibility("visible"));

  it("lê a rota da layer e marca como autorizado", async () => {
    fetchMock.mockResolvedValue(RESPONSE);

    const { refresh, reading, authorized, stale } = useOperatorCapacity();
    await refresh();

    expect(fetchMock).toHaveBeenCalledWith(CAPACITY_ROUTE, expect.anything());
    expect(reading.value).toEqual(RESPONSE);
    expect(authorized.value).toBe(true);
    expect(stale.value).toBe(false);
  });

  it("aba em segundo plano não mede (o processo medido não trabalha à toa)", async () => {
    setVisibility("hidden");

    const { refresh } = useOperatorCapacity();
    await refresh();

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sessão caída ou sem permissão esconde o indicador", async () => {
    fetchMock.mockResolvedValueOnce(RESPONSE).mockRejectedValueOnce({ statusCode: 403 });

    const { refresh, reading, authorized } = useOperatorCapacity();
    await refresh();
    await refresh();

    expect(authorized.value).toBe(false);
    expect(reading.value).toBeNull();
  });

  it("falha de rede mantém a última leitura, marcada como sem resposta", async () => {
    fetchMock.mockResolvedValueOnce(RESPONSE).mockRejectedValueOnce({ statusCode: 502 });

    const { refresh, reading, authorized, stale } = useOperatorCapacity();
    await refresh();
    await refresh();

    expect(authorized.value).toBe(true);
    expect(reading.value).toEqual(RESPONSE);
    expect(stale.value).toBe(true);
  });
});
