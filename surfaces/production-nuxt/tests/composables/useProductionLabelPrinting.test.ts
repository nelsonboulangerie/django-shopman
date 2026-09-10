import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import {
  isProvenPrintFailure,
  isReprintState,
  printJobStatusLabel,
  useProductionLabelPrinting,
} from "~/composables/useProductionLabelPrinting";
import type {
  ProductionLabelPrintDocument,
  ProductionPrintJobProjection,
  ProductionPrintingSourceProjection,
} from "~/types/productionPrinting";

const env = installNuxtGlobals();

function projection(overrides: Record<string, unknown> = {}) {
  return ref({
    selected_date: "2026-09-10",
    selected_date_display: "10 set 2026",
    selected_position_ref: "",
    selected_base_recipe: "",
    tickets: [],
    access: {},
    actions: [
      {
        ref: "print_weighing:2026-09-10::",
        kind: "print_labels",
        label: "Imprimir etiquetas",
        priority: 80,
        enabled: true,
        reason: "",
        method: "POST",
        href: "/api/v1/backstage/production/weighing/print-jobs/",
        payload_schema: "ProductionWeighingPrintJobRequest",
        expected_rev: null,
        idempotency: { required: true, key_scope: "production.print" },
        confirmation: {
          required: false,
          reason_required: false,
          title: "",
          confirm_label: "Confirmar",
        },
        approval_requirement: null,
        source_alert_ref: null,
        source_alert_effect: null,
        proof: "signed-print-proof",
      },
    ],
    generated_at: "2026-09-10T10:00:00Z",
    source_revision: "weighing:7",
    fresh_until: "2099-09-10T10:05:00Z",
    contract_version: 4,
    print_destination: {
      label: "EPSON · Preparação",
      status_label: "Pronta",
      available: true,
    },
    ...overrides,
  } as unknown as ProductionPrintingSourceProjection);
}

function job(
  status: string,
  overrides: Partial<ProductionPrintJobProjection> = {},
): ProductionPrintJobProjection {
  return {
    ref: "print-7",
    status,
    status_label: status,
    message: "",
    target_label: "EPSON · Preparação",
    label_count: 2,
    copy_number: 1,
    can_retry: status === "failed",
    can_reprint: ["accepted", "unknown", "confirmed"].includes(status),
    can_confirm: ["accepted", "awaiting_confirmation"].includes(status),
    poll_after_ms: 750,
    print_document: frozenDocument(),
    document_sha256: "document-sha-256",
    ...overrides,
  };
}

function frozenDocument(): ProductionLabelPrintDocument {
  return {
    mode: "blind",
    selected_date: "2026-09-10",
    scale_precision_g: "2",
    scale_precision_display: "2 g",
    scale_rounding_note: "Alvos arredondados para cima · balança 2 g",
    tickets: [
      {
        ticket_ref: "ticket-1:farinha",
        blind_code: "D8",
        made_display: "10/09",
        expiry_display: "11/09",
        ingredients: [
          {
            name: "Farinha T65",
            sku: "FARINHA-T65",
            quantity_display: "102 g",
            target_display: "102 g",
          },
        ],
      },
    ],
  };
}

function composable(source = projection()) {
  return useProductionLabelPrinting({
    projection: source,
    selectedDate: ref("2026-09-10"),
    refreshProjection: env.refresh,
  });
}

const selection = {
  mode: "blind" as const,
  ticketRefs: ["ticket-1"],
};

beforeEach(() => env.reset());
afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe("useProductionLabelPrinting", () => {
  it("ergue busy sincronamente e dois toques criam uma única tentativa", async () => {
    let resolveRequest!: (value: unknown) => void;
    env.fetchMock.mockImplementation(
      () => new Promise((resolve) => (resolveRequest = resolve)),
    );
    const printing = composable();

    const first = printing.create(selection, "relay");
    const second = printing.create(selection, "relay");

    expect(printing.busy.value).toBe(true);
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    await expect(second).resolves.toBe(false);
    resolveRequest({ print_job: job("awaiting_station") });
    await expect(first).resolves.toBe(true);

    const [, options] = env.fetchMock.mock.calls[0]!;
    expect(options).toMatchObject({
      method: "POST",
      body: {
        mode: "blind",
        selected_date: "2026-09-10",
        position: "",
        base_recipe: "",
        ticket_refs: ["ticket-1"],
        source_revision: "weighing:7",
        projection_generated_at: "2026-09-10T10:00:00Z",
        fresh_until: "2099-09-10T10:05:00Z",
        contract_version: 4,
        transport: "relay",
        action_ref: "print_weighing:2026-09-10::",
        action_proof: "signed-print-proof",
      },
    });
    expect(options.body.idempotency_key).toEqual(expect.any(String));
    printing.reset();
  });

  it("isola o documento congelado da resposta que originou o job", async () => {
    const responseJob = job("prepared");
    env.fetchMock.mockResolvedValueOnce({ print_job: responseJob });
    const printing = composable();

    await printing.create(selection, "browser");
    responseJob.print_document.tickets[0]!.ingredients[0]!.name =
      "Mutação externa";

    expect(
      printing.job.value?.print_document.tickets[0]?.ingredients[0]?.name,
    ).toBe("Farinha T65");
    expect(printing.job.value?.document_sha256).toBe("document-sha-256");
    printing.reset();
  });

  it("bloqueia offline e projeção vencida antes do POST sem perder a seleção", async () => {
    env.isOnline.value = false;
    const offline = composable();
    await expect(offline.create(selection, "relay")).resolves.toBe(false);
    expect(offline.errorCode.value).toBe("offline");
    expect(env.fetchMock).not.toHaveBeenCalled();

    env.isOnline.value = true;
    const stale = composable(
      projection({ fresh_until: "2020-01-01T00:00:00Z" }),
    );
    await expect(stale.create(selection, "relay")).resolves.toBe(false);
    expect(stale.errorCode.value).toBe("stale_projection");
    expect(env.fetchMock).not.toHaveBeenCalled();
  });

  it("falha fechado quando a action print_labels/proof não foi projetada", async () => {
    const absent = composable(projection({ actions: [] }));
    await expect(absent.create(selection, "relay")).resolves.toBe(false);
    expect(absent.errorCode.value).toBe("action_not_projected");
    expect(env.fetchMock).not.toHaveBeenCalled();

    const disabledSource = projection();
    disabledSource.value.actions[0]!.enabled = false;
    disabledSource.value.actions[0]!.reason = "Sem permissão para imprimir.";
    const disabled = composable(disabledSource);
    await expect(disabled.create(selection, "relay")).resolves.toBe(false);
    expect(disabled.errorMessage.value).toBe("Sem permissão para imprimir.");
  });

  it("acompanha o job por GET curto e chama fila de fila, nunca impressão física", async () => {
    vi.useFakeTimers();
    env.fetchMock
      .mockResolvedValueOnce({ print_job: job("awaiting_station") })
      .mockResolvedValueOnce({
        print_job: job("accepted", { status_label: "Impresso" }),
      });
    const printing = composable();

    await printing.create(selection, "relay");
    expect(printing.statusLabel.value).toBe("Aguardando estação");
    await vi.advanceTimersByTimeAsync(750);

    expect(env.fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/v1/backstage/production/weighing/print-jobs/print-7/",
    );
    expect(printing.statusLabel.value).toBe("Enviado à fila");
    expect(printing.statusLabel.value).not.toContain("Impresso");
    printing.reset();
  });

  it("só oferece retry após falha comprovada", async () => {
    env.fetchMock.mockResolvedValueOnce({
      print_job: job("queued", { can_retry: true }),
    });
    const queued = composable();
    await queued.create(selection, "relay");
    await expect(queued.retry()).resolves.toBe(false);
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    queued.reset();

    env.fetchMock
      .mockResolvedValueOnce({ print_job: job("failed") })
      .mockResolvedValueOnce({ print_job: job("awaiting_station") });
    const failed = composable();
    await failed.create(selection, "relay");
    await expect(failed.retry()).resolves.toBe(true);
    expect(env.fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/backstage/production/weighing/print-jobs/print-7/retry/",
      expect.objectContaining({ method: "POST" }),
    );
    failed.reset();
  });

  it("registra confirmação física, recusa e reimpressão em endpoints distintos", async () => {
    env.fetchMock
      .mockResolvedValueOnce({ print_job: job("accepted") })
      .mockResolvedValueOnce({ print_job: job("failed") });
    const printing = composable();
    await printing.create(selection, "relay");
    await printing.confirm(false);

    expect(env.fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/backstage/production/weighing/print-jobs/print-7/confirm/",
      expect.objectContaining({
        body: expect.objectContaining({ result: "incomplete" }),
      }),
    );

    env.fetchMock.mockResolvedValueOnce({
      print_job: job("confirmed", { copy_number: 2 }),
    });
    printing.job.value = job("uncertain", { can_reprint: true });
    await printing.reprint("browser");
    expect(env.fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/backstage/production/weighing/print-jobs/print-7/reprint/",
      expect.objectContaining({
        body: expect.objectContaining({ transport: "browser" }),
      }),
    );
    printing.reset();
  });

  it("preserva a confirmação física quando a conexão cai", async () => {
    env.fetchMock.mockResolvedValueOnce({
      print_job: job("spooled", { can_confirm: true }),
    });
    const printing = composable();
    await printing.create(selection, "relay");
    env.isOnline.value = false;

    await expect(printing.confirm(true)).resolves.toBe(false);
    expect(printing.errorCode.value).toBe("offline");
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    printing.reset();
  });

  it("registra abertura do diálogo sem promover afterprint a sucesso", async () => {
    env.fetchMock
      .mockResolvedValueOnce({ print_job: job("prepared") })
      .mockResolvedValueOnce({ print_job: job("awaiting_confirmation") });
    const printing = composable();

    await printing.create(selection, "browser");
    await printing.recordBrowserResult("dialog_opened");

    expect(env.fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/backstage/production/weighing/print-jobs/print-7/browser-result/",
      expect.objectContaining({
        body: expect.objectContaining({ result: "dialog_opened" }),
      }),
    );
    expect(printing.statusLabel.value).toBe("Aguardando confirmação");
    printing.reset();
  });

  it("reconcilia resposta perdida repetindo o POST com a mesma chave", async () => {
    env.fetchMock
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce({ print_job: job("awaiting_station") });
    const printing = composable();

    await expect(printing.create(selection, "relay")).resolves.toBe(false);
    expect(printing.createUncertain.value).toBe(true);
    const firstKey = env.fetchMock.mock.calls[0]![1].body.idempotency_key;
    await expect(printing.create(selection, "relay")).resolves.toBe(true);
    const secondKey = env.fetchMock.mock.calls[1]![1].body.idempotency_key;

    expect(secondKey).toBe(firstKey);
    expect(printing.createUncertain.value).toBe(false);
    printing.reset();
  });

  it("mantém predicados conservadores para retry e reimpressão", () => {
    expect(isProvenPrintFailure(job("failed"))).toBe(true);
    expect(isProvenPrintFailure(job("unknown"))).toBe(false);
    expect(isReprintState(job("accepted"))).toBe(true);
    expect(isReprintState(job("queued"))).toBe(false);
    expect(
      isReprintState(job("failed", { can_retry: false, can_reprint: true })),
    ).toBe(true);
    expect(
      isReprintState(job("failed", { can_retry: true, can_reprint: true })),
    ).toBe(false);
    expect(isReprintState(job("confirmed"))).toBe(true);
    expect(isReprintState(job("uncertain"))).toBe(true);
    expect(
      printJobStatusLabel(job("confirmed", { status_label: "Impresso" })),
    ).toBe("Saída confirmada");
  });
});
