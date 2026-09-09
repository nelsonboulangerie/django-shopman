import { beforeEach, describe, expect, it } from "vitest";
import { ref } from "vue";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import {
  projectionFreshUntilMs,
  useProductionMutationGuard,
} from "~/composables/useProductionMutationGuard";

const env = installNuxtGlobals();

function projection(overrides: Record<string, unknown> = {}) {
  return ref({
    generated_at: "2026-09-08T12:00:00.123456+00:00",
    source_revision: "production:17",
    fresh_until: "2026-09-08T12:01:30+00:00",
    contract_version: 1,
    actions: [
      {
        ref: "start:42",
        kind: "start" as const,
        label: "Iniciar",
        priority: 10,
        enabled: true,
        reason: "",
        method: "POST" as const,
        href: "/api/v1/backstage/production/42/start/",
        payload_schema: "ProductionStartMutationRequest",
        expected_rev: 3,
        idempotency: { required: true, key_scope: "production.start:42" },
        confirmation: {
          required: false,
          reason_required: false,
          title: "",
          confirm_label: "Confirmar",
        },
        approval_requirement: null,
        source_alert_ref: null,
        source_alert_effect: null,
        proof: "signed-start-proof",
      },
    ],
    ...overrides,
  });
}

describe("useProductionMutationGuard", () => {
  beforeEach(() => env.reset());

  it("authorizes a fresh projection and captures its four request metadata fields", () => {
    const guard = useProductionMutationGuard(projection(), env.refresh, () =>
      Date.parse("2026-09-08T12:01:00Z"),
    );

    expect(guard.authorizeMutation("start:42")).toEqual({
      ok: true,
      action: expect.objectContaining({ ref: "start:42", expected_rev: 3 }),
      metadata: {
        projection_generated_at: "2026-09-08T12:00:00.123456+00:00",
        source_revision: "production:17",
        fresh_until: "2026-09-08T12:01:30+00:00",
        contract_version: 1,
        action_ref: "start:42",
        action_proof: "signed-start-proof",
      },
    });
  });

  it("fails closed for absent, ambiguous or impossible projection timestamps", () => {
    const now = () => Date.parse("2026-09-08T12:01:00Z");

    for (const fresh_until of [
      "",
      "09/08/2026 12:02",
      "2026-02-31T12:02:00Z",
    ]) {
      const guard = useProductionMutationGuard(
        projection({ fresh_until }),
        env.refresh,
        now,
      );
      expect(guard.currentBlock()?.code).toBe("stale_projection");
    }
    expect(projectionFreshUntilMs("2026-02-31T12:02:00Z")).toBeNull();
    expect(
      useProductionMutationGuard(
        projection({ contract_version: 0 }),
        env.refresh,
        now,
      ).currentBlock()?.code,
    ).toBe("stale_projection");
  });

  it("gives offline precedence and offers refresh without issuing a write", () => {
    env.isOnline.value = false;
    const guard = useProductionMutationGuard(projection(), env.refresh);

    const authorization = guard.authorizeMutation("start:42");
    expect(authorization.ok).toBe(false);
    if (authorization.ok) throw new Error("expected offline block");
    expect(authorization.blocked.code).toBe("offline");

    const options = env.sonner.error.mock.calls[0]?.[1] as {
      action: { label: string; onClick: () => void };
    };
    expect(options.action.label).toBe("Atualizar ao reconectar");
    options.action.onClick();
    expect(env.refresh).toHaveBeenCalledOnce();
  });

  it("fails closed when the exact enabled action was not projected", () => {
    const now = () => Date.parse("2026-09-08T12:01:00Z");
    const guard = useProductionMutationGuard(projection(), env.refresh, now);

    const absent = guard.authorizeMutation("void:42");
    expect(absent.ok).toBe(false);
    if (absent.ok) throw new Error("expected absent-action block");
    expect(absent.blocked.code).toBe("action_not_projected");

    const enabled = guard.authorizeMutation("start:42");
    expect(enabled.ok).toBe(true);
    const disabled = useProductionMutationGuard(
      projection({
        actions: [
          {
            ...projection().value.actions[0]!,
            enabled: false,
            reason: "Etapas concluídas.",
            proof: "",
          },
        ],
      }),
      env.refresh,
      now,
    ).authorizeMutation("start:42");
    expect(disabled.ok).toBe(false);
    if (disabled.ok) throw new Error("expected disabled-action block");
    expect(disabled.blocked.code).toBe("action_disabled");
    const withoutProof = useProductionMutationGuard(
      projection({
        actions: [
          {
            ...projection().value.actions[0]!,
            enabled: true,
            proof: "",
          },
        ],
      }),
      env.refresh,
      now,
    ).authorizeMutation("start:42");
    expect(withoutProof.ok).toBe(false);
  });

  it("consumes the forbidden envelope and presents its request-access recovery", () => {
    const guard = useProductionMutationGuard(projection(), env.refresh);
    const handled = guard.handleMutationError({
      data: {
        detail: "Apenas gestores podem concluir esta ação.",
        error: {
          code: "forbidden",
          capability: "production.override_shortage",
          recovery: {
            action: "request_access",
            label: "Peça acesso ao gestor",
          },
        },
      },
    });

    expect(handled).toBe(true);
    expect(env.sonner.error).toHaveBeenCalledWith(
      "Apenas gestores podem concluir esta ação.",
      { description: "Peça acesso ao gestor" },
    );
  });
});
