import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import { mount, type VueWrapper } from "@vue/test-utils";

import QcCloseScreen from "../../app/components/QcCloseScreen.vue";
import type {
  QCDefectProjection,
  QCGradeProjection,
} from "../../app/types/production";

const GRADES: QCGradeProjection[] = [
  {
    ref: "excellent",
    label: "Ótimo",
    rank: 40,
    markdown_percent: 0,
    is_default: false,
  },
  {
    ref: "standard",
    label: "Normal",
    rank: 30,
    markdown_percent: 0,
    is_default: true,
  },
  {
    ref: "fair",
    label: "Razoável",
    rank: 20,
    markdown_percent: 20,
    is_default: false,
  },
  {
    ref: "minimal",
    label: "Mínimo",
    rank: 10,
    markdown_percent: 50,
    is_default: false,
  },
];

const DEFECTS: QCDefectProjection[] = [
  {
    ref: "shape",
    label: "Formato",
    hint: "Fora do padrão visual",
    forces_discard: false,
  },
  {
    ref: "color",
    label: "Cor",
    hint: "Assamento fora do ponto",
    forces_discard: false,
  },
  {
    ref: "burned",
    label: "Queimado",
    hint: "Sem condição de venda",
    forces_discard: true,
  },
];

const passthrough = { template: "<div><slot /></div>" };
const stubs = {
  Icon: true,
  OperatorNumpad: {
    props: ["disabled"],
    emits: ["digit", "backspace", "clear"],
    template: `
      <div>
        <button v-for="digit in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']"
          :key="digit" type="button" :disabled="disabled" :data-digit="digit" @click="$emit('digit', digit)">
          {{ digit }}
        </button>
        <button type="button" :disabled="disabled" data-backspace @click="$emit('backspace')">⌫</button>
        <button type="button" :disabled="disabled" data-clear @click="$emit('clear')">Limpar</button>
      </div>
    `,
  },
  UiSheet: {
    props: ["open"],
    template: "<div v-if='open'><slot /></div>",
  },
  UiSheetContent: {
    props: ["title"],
    template: "<section><h2>{{ title }}</h2><slot name='content' /></section>",
  },
  UiBadge: passthrough,
};

function installGlobals() {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("onMounted", onMounted);
  vi.stubGlobal("onBeforeUnmount", onBeforeUnmount);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("useSonner", { warning: vi.fn() });
}

function mountQc(
  overrides: Partial<InstanceType<typeof QcCloseScreen>["$props"]> = {},
) {
  return mount(QcCloseScreen, {
    props: {
      title: "Pão francês",
      subtitle: "WO-001",
      planned: 40,
      started: 40,
      grades: GRADES,
      defects: DEFECTS,
      submitting: false,
      ...overrides,
    },
    global: { stubs },
  });
}

const buttonByText = (wrapper: VueWrapper, text: string) =>
  wrapper.findAll("button").find((button) => button.text().includes(text));

async function enter(wrapper: VueWrapper, value: string) {
  for (const digit of value) {
    await wrapper.find(`[data-digit="${digit}"]`).trigger("click");
  }
}

beforeEach(installGlobals);
afterEach(() => vi.unstubAllGlobals());

describe("QcCloseScreen — classificação por grau", () => {
  it("usa Normal como saldo e envia no máximo um bucket por cada grau", async () => {
    const wrapper = mountQc();

    await buttonByText(wrapper, "Ótimo")!.trigger("click");
    await enter(wrapper, "10");
    await buttonByText(wrapper, "Razoável")!.trigger("click");
    await enter(wrapper, "5");
    await buttonByText(wrapper, "Mínimo")!.trigger("click");
    await enter(wrapper, "3");
    await buttonByText(wrapper, "Confirmar")!.trigger("click");

    await buttonByText(wrapper, "Formato")!.trigger("click");
    await nextTick();
    await buttonByText(wrapper, "Cor")!.trigger("click");

    const payload = wrapper.emitted("confirm")?.[0]?.[0] as {
      partition: Array<{
        quantity: string;
        quality_grade_ref?: string;
        quality_defect_ref?: string;
      }>;
    };
    expect(payload.partition).toEqual([
      { quantity: "10", quality_grade_ref: "excellent" },
      { quantity: "22", quality_grade_ref: "standard" },
      {
        quantity: "5",
        quality_grade_ref: "fair",
        quality_defect_ref: "shape",
      },
      {
        quantity: "3",
        quality_grade_ref: "minimal",
        quality_defect_ref: "color",
      },
    ]);
    expect(
      new Set(payload.partition.map((group) => group.quality_grade_ref)).size,
    ).toBe(payload.partition.length);
  });

  it("Ótimo pede somente quantidade e fecha sem motivo", async () => {
    const wrapper = mountQc();

    await buttonByText(wrapper, "Ótimo")!.trigger("click");
    await enter(wrapper, "40");
    await buttonByText(wrapper, "Confirmar")!.trigger("click");

    expect(wrapper.emitted("confirm")?.[0]?.[0]).toMatchObject({
      quantity: "40",
      partition: [{ quantity: "40", quality_grade_ref: "excellent" }],
    });
    expect(wrapper.text()).not.toContain("O que houve");
  });

  it("Razoável exige motivo mesmo com markdown configurado em zero", async () => {
    const grades = GRADES.map((grade) =>
      grade.ref === "fair" ? { ...grade, markdown_percent: 0 } : grade,
    );
    const wrapper = mountQc({ grades });

    await buttonByText(wrapper, "Razoável")!.trigger("click");
    await enter(wrapper, "5");
    await buttonByText(wrapper, "Confirmar")!.trigger("click");

    expect(wrapper.emitted("confirm")).toBeUndefined();
    await buttonByText(wrapper, "Formato")!.trigger("click");
    expect(wrapper.emitted("confirm")?.[0]?.[0]).toMatchObject({
      partition: expect.arrayContaining([
        {
          quantity: "5",
          quality_grade_ref: "fair",
          quality_defect_ref: "shape",
        },
      ]),
    });
  });

  it("mantém Perda separada, com quantidade e motivo próprios", async () => {
    const wrapper = mountQc();

    await buttonByText(wrapper, "Perda")!.trigger("click");
    await enter(wrapper, "4");
    await buttonByText(wrapper, "Confirmar")!.trigger("click");
    await buttonByText(wrapper, "Queimado")!.trigger("click");

    expect(wrapper.emitted("confirm")?.[0]?.[0]).toMatchObject({
      quantity: "40",
      partition: [
        { quantity: "36", quality_grade_ref: "standard" },
        {
          quantity: "4",
          quality_defect_ref: "burned",
          loss: true,
        },
      ],
    });
  });

  it("registra perda total como conclusão auditável, nunca como estorno", async () => {
    const wrapper = mountQc();

    await buttonByText(wrapper, "Perda")!.trigger("click");
    await enter(wrapper, "40");
    await buttonByText(wrapper, "Confirmar")!.trigger("click");
    await buttonByText(wrapper, "Queimado")!.trigger("click");

    expect(wrapper.emitted("confirm")?.[0]?.[0]).toMatchObject({
      quantity: "40",
      partition: [
        {
          quantity: "40",
          quality_defect_ref: "burned",
          loss: true,
        },
      ],
    });
    expect(wrapper.text()).not.toContain("estorno");
  });

  it("não oferece ações paralelas de detalhamento ou variação", () => {
    const wrapper = mountQc();

    expect(wrapper.text()).not.toContain("Detalhar");
    expect(wrapper.text()).not.toContain("Registrar variação");
  });

  it("não sequestra Tab/Enter de botões interativos", async () => {
    const wrapper = mountQc();
    const grade = buttonByText(wrapper, "Razoável")!;
    const tab = new KeyboardEvent("keydown", {
      key: "Tab",
      bubbles: true,
      cancelable: true,
    });

    grade.element.dispatchEvent(tab);
    await grade.trigger("keydown", { key: "Enter" });

    expect(tab.defaultPrevented).toBe(false);
    expect(wrapper.emitted("confirm")).toBeUndefined();
  });

  it("confirma antes de descartar um QC preenchido", async () => {
    const confirm = vi.fn(() => false);
    vi.stubGlobal("confirm", confirm);
    const wrapper = mountQc();
    await buttonByText(wrapper, "Razoável")!.trigger("click");
    await enter(wrapper, "5");

    await buttonByText(wrapper, "Voltar")!.trigger("click");
    expect(wrapper.emitted("back")).toBeUndefined();

    confirm.mockReturnValue(true);
    await buttonByText(wrapper, "Voltar")!.trigger("click");
    expect(wrapper.emitted("back")).toHaveLength(1);
  });

  it("desabilita o numpad enquanto Normal é apenas o saldo automático", () => {
    const wrapper = mountQc();

    expect(wrapper.find('[data-digit="1"]').attributes("disabled")).toBe("");
  });
});

describe("QcCloseScreen — correção auditável", () => {
  const initialPartition = [
    { quantity: "30", quality_grade_ref: "standard" },
    {
      quantity: "6",
      quality_grade_ref: "fair",
      quality_defect_ref: "shape",
    },
    { quantity: "4", quality_defect_ref: "burned", loss: true },
  ];

  it("mantém o total, edita Perda com um número e integra cada motivo ao bucket", async () => {
    const wrapper = mountQc({
      mode: "correct",
      initialPartition,
    });

    expect(wrapper.text()).toContain("Correção de qualidade");
    expect(
      wrapper.find('[data-grade-ref="standard"]').attributes("aria-label"),
    ).toContain("30 unidades");
    const fairReason = wrapper.find(
      'button[aria-label="Editar motivo de Razoável: Formato"]',
    );
    expect(fairReason.text()).toBe("Formato");
    expect(fairReason.classes()).toContain("min-h-11");
    expect(fairReason.classes()).toContain("rounded-full");
    expect(fairReason.find('icon-stub[name="lucide:pencil"]').exists()).toBe(
      true,
    );
    expect(
      wrapper
        .find('[data-grade-card="fair"]')
        .text()
        .match(/Formato/g),
    ).toHaveLength(1);
    const lossReason = wrapper.find(
      'button[aria-label="Editar motivo da perda: Queimado"]',
    );
    expect(lossReason.text()).toBe("Queimado");
    expect(lossReason.classes()).toContain("min-h-11");
    expect(lossReason.classes()).toContain("rounded-full");
    expect(lossReason.find('icon-stub[name="lucide:pencil"]').exists()).toBe(
      true,
    );

    await buttonByText(wrapper, "Perda")!.trigger("click");
    await enter(wrapper, "8");
    expect(
      wrapper.find('button[aria-label="Perda: 8 unidades"]').exists(),
    ).toBe(true);
    expect(
      wrapper.find('[data-grade-ref="standard"]').attributes("aria-label"),
    ).toContain("26 unidades");

    await wrapper
      .find('button[aria-label="Editar motivo de Razoável: Formato"]')
      .trigger("click");
    await buttonByText(wrapper, "Cor")!.trigger("click");
    await wrapper
      .find('button[aria-label="Editar motivo da perda: Queimado"]')
      .trigger("click");
    await buttonByText(wrapper, "Formato")!.trigger("click");

    const submit = buttonByText(wrapper, "Salvar correção")!;
    expect(submit.attributes("disabled")).toBeUndefined();
    await submit.trigger("click");

    const payload = wrapper.emitted("confirm")?.[0]?.[0] as {
      quantity: string;
      reason: string;
      partition: Array<{
        quantity: string;
        quality_grade_ref?: string;
        quality_defect_ref?: string;
        loss?: boolean;
      }>;
    };
    expect(payload).toEqual({
      quantity: "40",
      partition: [
        { quantity: "26", quality_grade_ref: "standard" },
        {
          quantity: "6",
          quality_grade_ref: "fair",
          quality_defect_ref: "color",
        },
        {
          quantity: "8",
          quality_defect_ref: "shape",
          loss: true,
        },
      ],
      yield_deviation_confirmed: false,
      yield_deviation_reason: "",
      reason: "Revisão do QC registrada no quiosque.",
    });
    expect(payload.partition.filter((group) => group.loss)).toEqual([
      { quantity: "8", quality_defect_ref: "shape", loss: true },
    ]);
  });

  it("permite criar e zerar Perda sem alterar a âncora", async () => {
    const wrapper = mountQc({
      mode: "correct",
      initialPartition: [{ quantity: "40", quality_grade_ref: "standard" }],
    });

    expect(wrapper.text()).toContain("Saldo automático");
    expect(wrapper.text()).toContain("Sem perda");

    await buttonByText(wrapper, "Perda")!.trigger("click");
    await enter(wrapper, "5");
    expect(
      wrapper.find('[data-grade-ref="standard"]').attributes("aria-label"),
    ).toContain("35 unidades");

    await wrapper.find("[data-clear]").trigger("click");
    expect(
      wrapper.find('[data-grade-ref="standard"]').attributes("aria-label"),
    ).toContain("40 unidades");
    expect(
      wrapper.find('button[aria-label^="Editar motivo da perda"]').exists(),
    ).toBe(false);
  });

  it("não trata o preenchimento inicial como alteração e mostra o estado de envio", async () => {
    const confirm = vi.fn(() => false);
    vi.stubGlobal("confirm", confirm);
    const wrapper = mountQc({
      mode: "correct",
      initialPartition,
    });

    await buttonByText(wrapper, "Voltar")!.trigger("click");
    expect(confirm).not.toHaveBeenCalled();
    expect(wrapper.emitted("back")).toHaveLength(1);

    await wrapper.setProps({ submitting: true });
    const submit = buttonByText(wrapper, "Salvando correção…")!;
    expect(submit.attributes("disabled")).toBeDefined();
  });
});
