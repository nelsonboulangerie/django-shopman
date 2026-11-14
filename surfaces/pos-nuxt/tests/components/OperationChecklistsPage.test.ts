// Rotinas no PDV (dono, 13/11/2026: abertura, rotina e fechamento moram perto do
// caixa). A tela é a mesma que vivia no Gestor; aqui no runtime Nuxt do PDV.
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

import type { OperationChecklistBoard } from "../../app/types/operationChecklists";

const { completeTask, superviseTask, completeRun, start } = vi.hoisted(() => ({
  completeTask: vi.fn(async () => true),
  superviseTask: vi.fn(async () => true),
  completeRun: vi.fn(async () => true),
  start: vi.fn(async () => true),
}));

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

const taskErrors = ref<Record<number, { field: string; message: string }>>({});

mockNuxtImport("useOperationChecklists", () => () => ({
  board,
  pending: ref(false),
  error: ref(null),
  refresh: vi.fn(),
  busy: ref(""),
  message: ref(""),
  taskErrors,
  start,
  completeTask,
  superviseTask,
  completeRun,
}));

const { default: OperationChecklistsPage } = await import("~/pages/checklists.vue");

describe("OperationChecklistsPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("envia referência de foto e oferece a dupla conferência na própria superfície", async () => {
    const wrapper = await mountSuspended(OperationChecklistsPage);

    const photo = wrapper.get('[data-checklist-task="showcase-photo"]');
    await photo
      .get("input")
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

  it("a recusa da evidência aparece embaixo do campo da tarefa (GES-23)", async () => {
    taskErrors.value = {
      9: {
        field: "evidence_data",
        message: "Cole o link ou o código da foto para concluir esta tarefa.",
      },
    };
    const wrapper = await mountSuspended(OperationChecklistsPage);
    const photo = wrapper.get('[data-checklist-task="showcase-photo"]');
    expect(photo.text()).toContain(
      "Cole o link ou o código da foto para concluir esta tarefa.",
    );
    taskErrors.value = {};
  });

  // Beta 05/11 (GES-16): "de 2026-11-05" no lugar da data como a casa escreve.
  it("o dia da loja sai como a casa escreve, nunca em ISO", async () => {
    const wrapper = await mountSuspended(OperationChecklistsPage);
    expect(wrapper.text()).toContain("Abertura, rotina e fechamento de Sáb 17/10.");
    expect(wrapper.text()).not.toContain("2026-10-17");
  });
});
