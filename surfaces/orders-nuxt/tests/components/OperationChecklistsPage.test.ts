import { beforeEach, describe, expect, it, vi } from "vitest";
import { computed, defineComponent, h, reactive, ref } from "vue";
import { mount } from "@vue/test-utils";

import type { OperationChecklistBoard } from "../../app/types/operationChecklists";

const completeTask = vi.fn(async () => true);
const superviseTask = vi.fn(async () => true);
const completeRun = vi.fn(async () => true);
const start = vi.fn(async () => true);

const board = ref<OperationChecklistBoard>({
  business_date: "2026-10-17",
  can_supervise: true,
  templates: [
    {
      id: 1,
      ref: "opening",
      title: "Abertura da loja",
      description: "Preparar a casa.",
      moment: "opening",
      moment_label: "Abertura",
      runs: [
        {
          id: 3,
          shift_ref: "manhã",
          status: "open",
          status_label: "Aberto",
          started_by: "Ana",
          completed_by: "",
          progress_percent: 50,
          tasks: [
            {
              id: 9,
              ref: "showcase-photo",
              title: "Registrar foto da vitrine",
              description: "",
              area: "room",
              area_label: "Salão",
              status: "pending",
              status_label: "Pendente",
              required: true,
              evidence_required: "photo",
              evidence_required_label: "Foto",
              evidence_text: "",
              evidence_number: null,
              evidence_data: {},
              notes: "",
              requires_supervision: false,
              supervised: false,
              executed_by: "",
              supervised_by: "",
            },
            {
              id: 10,
              ref: "keys-check",
              title: "Conferir chaves",
              description: "",
              area: "management",
              area_label: "Gestão",
              status: "done",
              status_label: "Concluída",
              required: true,
              evidence_required: "double_check",
              evidence_required_label: "Dupla conferência",
              evidence_text: "",
              evidence_number: null,
              evidence_data: {},
              notes: "",
              requires_supervision: true,
              supervised: false,
              executed_by: "Bruno",
              supervised_by: "",
            },
          ],
        },
      ],
    },
  ],
});

vi.stubGlobal("computed", computed);
vi.stubGlobal("reactive", reactive);
vi.stubGlobal("useHead", vi.fn());
vi.stubGlobal("httpErrorMessage", () => "Falha");
vi.stubGlobal("useOperationChecklists", () => ({
  board,
  pending: ref(false),
  error: ref(null),
  refresh: vi.fn(),
  busy: ref(""),
  message: ref(""),
  start,
  completeTask,
  superviseTask,
  completeRun,
}));

const { default: OperationChecklistsPage } =
  await import("../../app/pages/checklists.vue");

const OperatorPageHeader = defineComponent({
  setup(_, { slots }) {
    return () => h("header", [slots.default?.(), slots.filters?.()]);
  },
});

describe("OperationChecklistsPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("envia referência de foto e oferece a dupla conferência na própria superfície", async () => {
    const wrapper = mount(OperationChecklistsPage, {
      global: { components: { OperatorPageHeader } },
    });

    const photo = wrapper.get('[data-checklist-task="showcase-photo"]');
    await photo
      .get('input[aria-label="Foto (link ou referência)"]')
      .setValue("drive://abertura/vitrine-01");
    await photo.get("button").trigger("click");
    expect(completeTask).toHaveBeenCalledWith(3, 9, {
      evidence_text: "",
      evidence_number: null,
      evidence_data: { photo_ref: "drive://abertura/vitrine-01" },
    });

    const doubleCheck = wrapper.get('[data-checklist-task="keys-check"]');
    expect(doubleCheck.text()).toContain("Fazer dupla conferência");
    await doubleCheck.get("button").trigger("click");
    expect(superviseTask).toHaveBeenCalledWith(3, 10);

    const close = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Concluir rotina"));
    expect(close?.attributes("disabled")).toBeDefined();
  });
});
