import { beforeEach, describe, expect, it, vi } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useAlerts } from "../../app/composables/useAlerts";
import type { AlertProjection } from "../../app/types/orders";

const env = installNuxtGlobals();
vi.stubGlobal("useNuxtData", () => ({ data: { value: { operator: { id: 1 } } } }));

const READ = {
  generated_at: "2026-09-25T10:00:00-03:00",
  source_revision: "sha256:abc:alerts:active:user:1",
  fresh_until: "2026-09-25T10:01:30-03:00",
  contract_version: 1,
};

function alert(pk: number, withAck = true): AlertProjection {
  return {
    pk,
    type: "fiscal_emit_failed",
    type_label: "Emissão da NFC-e falhou",
    severity: "critical",
    severity_label: "Crítico",
    message: "A NFC-e do pedido X não foi autorizada.",
    order_ref: "X",
    created_at_display: "25/09 às 10:00",
    actions: withAck
      ? [{ ref: `acknowledge:${pk}`, kind: "acknowledge_alert", label: "Visto", enabled: true, href: "", expected_rev: 3, proof: "p" }]
      : [],
  };
}

describe("useAlerts", () => {
  beforeEach(() => env.reset());

  it("deriva alerts + contadores; degrada para []/0", () => {
    env.fetchData.value = { alerts: [{ pk: 1 }], counts: { active: 2, critical: 1 } };
    const a = useAlerts();
    expect(a.alerts.value).toEqual([{ pk: 1 }]);
    expect(a.activeCount.value).toBe(2);
    expect(a.criticalCount.value).toBe(1);

    env.fetchData.value = null;
    const b = useAlerts();
    expect(b.alerts.value).toEqual([]);
    expect(b.activeCount.value).toBe(0);
    expect(b.criticalCount.value).toBe(0);
  });

  it("Visto manda o gesto que o servidor ofereceu, com a leitura e a prova", async () => {
    env.fetchData.value = { alerts: [alert(7)], counts: { active: 1, critical: 1 }, ...READ };
    const a = useAlerts();

    await a.ack(alert(7));

    const [url, options] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/alerts/7/ack/");
    expect(options.method).toBe("POST");
    expect(options.body).toMatchObject({
      expected_rev: 3,
      projection_generated_at: READ.generated_at,
      source_revision: READ.source_revision,
      fresh_until: READ.fresh_until,
      contract_version: 1,
      action_ref: "acknowledge:7",
      action_proof: "p",
    });
    expect(typeof options.body.idempotency_key).toBe("string");
    expect(env.refresh).toHaveBeenCalledTimes(1);
  });

  it("alerta já visto não oferece o gesto e não posta nada", async () => {
    env.fetchData.value = { alerts: [alert(8, false)], counts: { active: 1, critical: 0 }, ...READ };
    const a = useAlerts();

    expect(a.ackAction(alert(8, false))).toBeNull();
    await a.ack(alert(8, false));
    expect(env.fetchMock).not.toHaveBeenCalled();
  });

  it("leitura vencida (409): relê e pede para tocar de novo", async () => {
    env.fetchData.value = { alerts: [alert(9)], counts: { active: 1, critical: 1 }, ...READ };
    env.fetchMock.mockRejectedValueOnce(Object.assign(new Error("stale"), { status: 409, statusCode: 409 }));
    const a = useAlerts();

    await a.ack(alert(9));

    expect(env.refresh).toHaveBeenCalledTimes(1);
    expect(env.sonner.error).toHaveBeenCalledWith("Os alertas mudaram. Confira e toque em Visto de novo.");
  });

  it("outra falha acende o toast do servidor e não derruba", async () => {
    env.fetchData.value = { alerts: [alert(10)], counts: { active: 1, critical: 1 }, ...READ };
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "Alerta já resolvido." } });
    const a = useAlerts();

    await a.ack(alert(10));

    expect(env.sonner.error).toHaveBeenCalledWith("Alerta já resolvido.");
  });
});
