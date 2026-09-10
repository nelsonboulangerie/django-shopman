import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import { flushPromises, mount } from "@vue/test-utils";

import ProductionLabelPrintDialog from "../../app/components/ProductionLabelPrintDialog.vue";
import WeighingLabels from "../../app/components/WeighingLabels.vue";
import type {
  ProductionLabelPrintDocument,
  ProductionPrintJobProjection,
} from "../../app/types/productionPrinting";

function ticket() {
  return {
    ticket_ref: "ticket-1",
    recipe_ref: "massa-base",
    output_sku: "MASSA-BASE",
    name: "Massa base",
    output_quantity_display: "12 un.",
    dough_weight_display: "2 kg",
    total_weight_display: "2.000 g",
    sources_display: "12 un.",
    blind_code: "D8",
    made_display: "10/09",
    expiry_display: "11/09",
    ingredients: [],
    table: { contract_version: 1, headers: [], rows: [] },
  };
}

function job(
  status: string,
  overrides: Partial<ProductionPrintJobProjection> = {},
) {
  return {
    ref: "print-1",
    status,
    status_label: status,
    message: "",
    target_label: "EPSON · Preparação",
    label_count: 1,
    copy_number: 1,
    can_retry: false,
    can_reprint: false,
    can_confirm: false,
    poll_after_ms: 1000,
    print_document: frozenDocument(),
    document_sha256: "frozen-sha-256",
    ...overrides,
  };
}

function frozenDocument(
  overrides: Partial<ProductionLabelPrintDocument> = {},
): ProductionLabelPrintDocument {
  return {
    mode: "blind",
    selected_date: "2026-09-10",
    scale_precision_g: "2",
    scale_precision_display: "2 g",
    scale_rounding_note: "Alvos congelados · balança 2 g",
    tickets: [
      {
        ticket_ref: "frozen-ticket:flour",
        blind_code: "Z9",
        made_display: "10/09",
        expiry_display: "11/09",
        ingredients: [
          {
            name: "Farinha congelada",
            sku: "FARINHA-FROZEN",
            quantity_display: "102 g",
            target_display: "102 g",
            annotation: "(≈ 2 un.)",
          },
        ],
      },
    ],
    ...overrides,
  };
}

const printing = {
  job: ref<ProductionPrintJobProjection | null>(null),
  isOnline: ref(true),
  busy: ref(false),
  operation: ref<string | null>(null),
  block: ref<null | { detail: string }>(null),
  statusLabel: ref("Pronta para enviar"),
  destinationLabel: ref("EPSON · Preparação"),
  destinationStatusLabel: ref("Pronta"),
  errorMessage: ref(""),
  errorCode: ref(""),
  createUncertain: ref(false),
  pollingMessage: ref(""),
  create: vi.fn(),
  confirm: vi.fn(),
  retry: vi.fn(),
  reprint: vi.fn(),
  recordBrowserResult: vi.fn(),
  refreshSource: vi.fn(),
  reset: vi.fn(),
};

const stubs = {
  UiDialog: {
    props: ["open"],
    template: '<div v-if="open"><slot /></div>',
  },
  UiDialogContent: { template: "<div><slot /></div>" },
  UiDialogHeader: { template: "<header><slot /></header>" },
  UiDialogTitle: { template: "<h2><slot /></h2>" },
  UiDialogDescription: { template: "<p><slot /></p>" },
  UiDialogFooter: { template: "<footer><slot /></footer>" },
  UiBadge: { template: "<span><slot /></span>" },
  UiButton: {
    props: ["disabled", "loading"],
    emits: ["click"],
    template:
      '<button :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
  },
  Icon: true,
};

const baseProps = {
  open: true,
  printMode: "pesagem" as const,
  labels: [
    {
      code: "D8",
      ingredient: "Farinha T65",
      sku: "FARINHA-T65",
      weight: "1.000 g",
      date: "10 set 2026",
      key: "ticket-1-farinha",
    },
  ],
  tickets: [ticket()],
  selectedDate: "2026-09-10",
  dateDisplay: "10 set 2026",
  projection: {
    selected_date: "2026-09-10",
    source_revision: "weighing:7",
    scale_rounding_note: "Alvos arredondados para cima · balança 2 g",
  },
  refreshProjection: vi.fn(),
};

function wrapper(props: Record<string, unknown> = {}) {
  return mount(ProductionLabelPrintDialog, {
    props: { ...baseProps, ...props } as never,
    global: { stubs, components: { WeighingLabels } },
  });
}

beforeEach(() => {
  vi.stubGlobal("useProductionLabelPrinting", () => printing);
  vi.stubGlobal(
    "print",
    vi.fn(() => window.dispatchEvent(new Event("beforeprint"))),
  );
  printing.job.value = null;
  printing.isOnline.value = true;
  printing.busy.value = false;
  printing.operation.value = null;
  printing.block.value = null;
  printing.statusLabel.value = "Pronta para enviar";
  printing.errorMessage.value = "";
  printing.errorCode.value = "";
  printing.createUncertain.value = false;
  printing.pollingMessage.value = "";
  for (const fn of [
    printing.create,
    printing.confirm,
    printing.retry,
    printing.reprint,
    printing.recordBrowserResult,
    printing.refreshSource,
    printing.reset,
  ]) {
    fn.mockReset().mockResolvedValue(true);
  }
  printing.create.mockImplementation(
    async (_selection: unknown, transport: "relay" | "browser") => {
      printing.job.value = job(transport === "browser" ? "prepared" : "queued");
      return true;
    },
  );
});

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("ProductionLabelPrintDialog", () => {
  it("mostra preview lógico, contagem, Nome + SKU, destino e CTAs explícitas", () => {
    const view = wrapper();

    expect(view.text()).toContain("Prévia lógica · bobina 80 mm");
    expect(view.text()).toContain("1 etiqueta · 10 set 2026");
    expect(view.text()).toContain("Farinha T65");
    expect(view.text()).toContain("FARINHA-T65");
    expect(view.text()).toContain("1.000 g");
    expect(view.text()).toContain("Alvos arredondados para cima · balança 2 g");
    expect(view.get('[data-testid="print-destination"]').text()).toContain(
      "EPSON · Preparação",
    );
    expect(view.text()).toContain("Imprimir 1 etiqueta");
    expect(view.text()).toContain("Imprimir neste dispositivo");
  });

  it("conta ingredientes na pesagem e preparos na etiqueta explícita", () => {
    const secondTicket = {
      ...ticket(),
      ticket_ref: "ticket-2",
      output_sku: "MASSA-2",
      name: "Massa 2",
    };
    const secondLabel = {
      ...baseProps.labels[0],
      key: "ticket-1-sal",
      ingredient: "Sal",
      sku: "SAL",
    };
    const blind = wrapper({ labels: [...baseProps.labels, secondLabel] });
    expect(blind.text()).toContain("2 etiquetas · 10 set 2026");
    blind.unmount();

    const explicit = wrapper({
      printMode: "preparo",
      labels: [...baseProps.labels, secondLabel, secondLabel],
      tickets: [ticket(), secondTicket],
    });
    expect(explicit.text()).toContain("2 etiquetas · 10 set 2026");
    expect(explicit.text()).not.toContain("3 etiquetas · 10 set 2026");
  });

  it("não deixa a identificação interna inventar validade", () => {
    const explicit = wrapper({
      printMode: "preparo",
      tickets: [
        {
          ...ticket(),
          expiry_display: "",
          validity_configured: false,
        },
      ],
    });

    expect(explicit.text()).toContain("Validade não configurada");
    expect(explicit.text()).toContain("não presume D+1");
    const printButtons = explicit
      .findAll("button")
      .filter((button) => button.text().includes("Imprimir"));
    expect(printButtons).toHaveLength(2);
    expect(
      printButtons.every(
        (button) => button.attributes("disabled") !== undefined,
      ),
    ).toBe(true);
  });

  it("envia o ticket_ref pela ação principal sem chamar window.print", async () => {
    const view = wrapper();
    await view
      .findAll("button")
      .find((button) => button.text().includes("Imprimir 1 etiqueta"))!
      .trigger("click");

    expect(printing.create).toHaveBeenCalledWith(
      { mode: "blind", ticketRefs: ["ticket-1"] },
      "relay",
    );
    expect(window.print).not.toHaveBeenCalled();
  });

  it("congela preview e DOM físico no documento retornado mesmo se a projeção viva mudar", async () => {
    const view = wrapper();
    const resetCountBeforeCreate = printing.reset.mock.calls.length;

    await view
      .findAll("button")
      .find((button) => button.text().includes("Imprimir 1 etiqueta"))!
      .trigger("click");
    await flushPromises();

    const physical = view.get('[data-testid="frozen-print-payload"]');
    expect(physical.attributes("data-document-sha256")).toBe("frozen-sha-256");
    expect(physical.text()).toContain("Farinha congelada");
    expect(physical.text()).toContain("FARINHA-FROZEN");
    expect(physical.text()).toContain("102 g");
    expect(physical.text()).toContain("(≈ 2 un.)");
    expect(physical.text()).not.toContain("Referência:");

    await view.setProps({
      labels: [
        {
          code: "LIVE",
          ingredient: "Ingrediente alterado na projeção",
          sku: "LIVE-SKU",
          weight: "999 g",
          date: "12 set 2026",
          key: "live-label",
        },
      ],
      projection: {
        ...baseProps.projection,
        source_revision: "weighing:8",
        scale_rounding_note: "Nota viva que não pode contaminar o job",
      },
    });
    await nextTick();

    expect(printing.reset).toHaveBeenCalledTimes(resetCountBeforeCreate);
    expect(physical.text()).toContain("Farinha congelada");
    expect(physical.text()).not.toContain("Ingrediente alterado");
    expect(view.text()).toContain("Alvos congelados · balança 2 g");
    expect(view.text()).not.toContain("Nota viva que não pode contaminar");
  });

  it("só abre o diálogo nativo depois de criar o job browser e não presume sucesso", async () => {
    vi.useFakeTimers();
    const view = wrapper();

    await view
      .findAll("button")
      .find((button) => button.text().includes("neste dispositivo"))!
      .trigger("click");
    await flushPromises();
    await vi.advanceTimersByTimeAsync(220);
    await flushPromises();

    expect(printing.create).toHaveBeenCalledWith(
      { mode: "blind", ticketRefs: ["ticket-1"] },
      "browser",
    );
    expect(window.print).toHaveBeenCalledOnce();
    expect(printing.recordBrowserResult).toHaveBeenCalledWith("dialog_opened");
    expect(printing.confirm).not.toHaveBeenCalled();
  });

  it("registra função window.print inerte como indisponível", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("print", vi.fn());
    const view = wrapper();

    await view
      .findAll("button")
      .find((button) => button.text().includes("neste dispositivo"))!
      .trigger("click");
    await flushPromises();
    await vi.advanceTimersByTimeAsync(220);
    await flushPromises();

    expect(printing.recordBrowserResult).toHaveBeenCalledWith(
      "dialog_unavailable",
    );
  });

  it("não abre window.print sem o documento congelado do servidor", async () => {
    printing.create.mockImplementationOnce(async () => {
      printing.job.value = {
        ...job("prepared"),
        print_document: undefined,
      } as unknown as ProductionPrintJobProjection;
      return true;
    });
    const view = wrapper();

    await view
      .findAll("button")
      .find((button) => button.text().includes("neste dispositivo"))!
      .trigger("click");
    await flushPromises();

    expect(window.print).not.toHaveBeenCalled();
    expect(view.get('[data-testid="print-error"]').text()).toContain(
      "documento congelado",
    );
  });

  it("pede confirmação física com dois resultados inequívocos", async () => {
    printing.job.value = job("awaiting_confirmation", { can_confirm: true });
    const view = wrapper();
    expect(view.text()).toContain("A etiqueta saiu corretamente?");

    await view
      .findAll("button")
      .find((button) => button.text().includes("Sim, saíram"))!
      .trigger("click");
    await view
      .findAll("button")
      .find((button) => button.text().includes("Não saíram"))!
      .trigger("click");

    expect(printing.confirm).toHaveBeenNthCalledWith(1, true);
    expect(printing.confirm).toHaveBeenNthCalledWith(2, false);
  });

  it("não pergunta pelo papel enquanto o job ainda aguarda a estação", () => {
    printing.job.value = job("queued", { can_confirm: false });
    const view = wrapper();

    expect(view.text()).not.toContain("saiu corretamente?");
    expect(view.text()).not.toContain("Sim, saíram");
  });

  it("mostra retry só na falha comprovada e reprint nos estados ambíguos", async () => {
    printing.job.value = job("failed", { can_retry: true });
    const failed = wrapper();
    expect(failed.text()).toContain("Tentar novamente");
    expect(failed.text()).not.toContain("Reimprimir 1 etiqueta");
    failed.unmount();

    printing.job.value = job("uncertain", { can_reprint: true });
    await nextTick();
    const unknown = wrapper();
    expect(unknown.text()).not.toContain("Tentar novamente");
    expect(unknown.text()).toContain("Reimprimir 1 etiqueta");
  });

  it("marca a via no papel do navegador para uma reimpressão", () => {
    printing.job.value = job("confirmed", {
      can_reprint: true,
      copy_number: 2,
    });
    const view = wrapper();

    expect(view.get('[data-testid="frozen-print-payload"]').text()).toContain(
      "2ª via",
    );
  });

  it("bloqueia mutação offline/stale sem esconder o preview", () => {
    printing.block.value = {
      detail:
        "Sem conexão. A ação não foi enviada e seus dados foram preservados.",
    };
    const view = wrapper();

    expect(view.text()).toContain("Farinha T65");
    expect(view.text()).toContain("Sem conexão");
    const action = view
      .findAll("button")
      .find((button) => button.text().includes("Imprimir 1 etiqueta"));
    expect(action?.attributes("disabled")).toBeDefined();
  });

  it("bloqueia só o relay quando o destino está indisponível", () => {
    const view = wrapper({
      projection: {
        ...baseProps.projection,
        print_destination: {
          label: "Estação da Preparação",
          status_label: "Relay offline",
          available: false,
        },
      },
    });
    const relay = view
      .findAll("button")
      .find((button) => button.text().includes("Imprimir 1 etiqueta"));
    const browser = view
      .findAll("button")
      .find((button) => button.text().includes("neste dispositivo"));

    expect(view.text()).toContain("Relay offline");
    expect(relay?.attributes("disabled")).toBeDefined();
    expect(browser?.attributes("disabled")).toBeUndefined();
  });
});
