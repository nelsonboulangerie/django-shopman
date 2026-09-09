import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useAlerts } from "~/composables/useAlerts";

const env = installNuxtGlobals();

function alertProjection(pk = 9) {
  return {
    pk,
    rev: 0,
    type: "stale_new_order",
    type_label: "Pedido parado",
    severity: "warning" as const,
    severity_label: "Aviso",
    audience: "orders",
    message: "Pedido parado",
    order_ref: "ORD-9",
    created_at_display: "09/09 às 10:00",
    actions: [
      {
        ref: `acknowledge:${pk}`,
        kind: "acknowledge_alert" as const,
        label: "Reconhecer",
        priority: 20,
        enabled: true,
        reason: "",
        method: "POST" as const,
        href: `/api/v1/backstage/alerts/${pk}/ack/`,
        payload_schema: "AlertAckMutationRequest" as const,
        expected_rev: 0,
        idempotency: { required: true as const, key_scope: `backstage.alert-ack:${pk}` },
        confirmation: {
          required: false,
          reason_required: false,
          title: "",
          confirm_label: "Confirmar",
        },
        approval_requirement: null,
        source_alert_ref: String(pk),
        source_alert_effect: "acknowledges" as const,
        proof: `proof-${pk}`,
      },
    ],
  };
}

function response(alerts = [alertProjection()]) {
  return {
    alerts,
    counts: { active: alerts.length, critical: 0 },
    generated_at: "2099-01-01T00:00:00Z",
    source_revision: "signed-alert-revision",
    fresh_until: "2099-01-01T00:01:30Z",
    contract_version: 1,
  };
}

describe("useAlerts", () => {
  beforeEach(() => env.reset());

  it("derives alerts and the active/critical counts", () => {
    const payload = response([alertProjection(1), alertProjection(2)]);
    payload.counts.critical = 1;
    env.fetchData.value = payload;
    const { alerts, activeCount, criticalCount } = useAlerts();
    expect(alerts.value).toHaveLength(2);
    expect(activeCount.value).toBe(2);
    expect(criticalCount.value).toBe(1);
  });

  it("degrades to zero when the payload is null", () => {
    env.fetchData.value = null;
    const { alerts, activeCount, criticalCount } = useAlerts();
    expect(alerts.value).toEqual([]);
    expect(activeCount.value).toBe(0);
    expect(criticalCount.value).toBe(0);
  });

  it("ack POSTs to the per-alert endpoint and reconciles", async () => {
    const alert = alertProjection();
    env.fetchData.value = response([alert]);
    await useAlerts().ack(alert);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/alerts/9/ack/",
      expect.objectContaining({
        method: "POST",
        body: expect.objectContaining({
          expected_rev: 0,
          action_ref: "acknowledge:9",
          action_proof: "proof-9",
          source_revision: "signed-alert-revision",
        }),
      }),
    );
    expect(env.refresh).toHaveBeenCalled();
  });

  it("toasts if ack fails", async () => {
    const alert = alertProjection();
    env.fetchData.value = response([alert]);
    env.fetchMock.mockRejectedValue({ data: { detail: "sem rede" } });
    await useAlerts().ack(alert);
    expect(env.sonner.error).toHaveBeenCalledWith("sem rede");
  });

  it("does not send an acknowledgement absent from the projection", async () => {
    const alert = { ...alertProjection(), actions: [] };
    env.fetchData.value = response([alert]);

    await useAlerts().ack(alert);

    expect(env.fetchMock).not.toHaveBeenCalled();
  });
});
