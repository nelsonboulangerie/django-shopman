// A gaveta do item: o operador nunca pode ter dúvida sobre o que está mexendo.
//
// Três coisas são contrato, e não estilo:
//
// 1. **o título fica FORA do que rola.** Numa gaveta com insumo, embalagem,
//    quantidade, validade e lote, quem rola até o meio perde de vista em qual
//    das dez linhas da nota está;
// 2. **os campos têm endereço lá dentro.** "Ir até lá" procura o campo pelo
//    seletor de `receiptFocus`; se a gaveta parar de carimbar
//    `data-receipt-field`, a pendência vira um clique que não faz nada;
// 3. **conferir FECHA.** É o gesto que devolve o operador à lista, onde a linha
//    acabou de mudar de cor.
import { computed, nextTick, ref } from "vue";
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import ReceiptLineSheet from "../../app/components/ReceiptLineSheet.vue";
import ReceiptField from "../../app/components/ReceiptField.vue";
import { receiptFieldSelector } from "../../app/utils/receiptFocus";
import { receiptLinePreview } from "../../app/presentation/purchase";
import type { Material, ReceiptLine } from "../../app/types/purchase";

// Auto-imports do Nuxt que o SFC usa como global (sem runtime Nuxt aqui).
vi.stubGlobal("computed", computed);
vi.stubGlobal("useCoarsePointer", () => ref(false));

const ovos: Material = {
  sku: "OVOS",
  name: "Ovos",
  unit: "kg",
  shelfLifeDays: 21,
  isActive: true,
  category: "Frescos",
  stockOnHand: 16,
  dailyUse: 4,
  minStock: 12,
  recipes: [],
};

function lineOf(patch: Partial<ReceiptLine> = {}): ReceiptLine {
  return {
    id: "line-1",
    materialSku: "OVOS",
    conversionId: null,
    purchaseQty: 2,
    costInput: "24,00",
    expiryDate: "2026-10-01",
    lineNote: "",
    invoiceDescription: "OVOS BRANCOS CX 30",
    checked: false,
    ...patch,
  };
}

function previewOf(patch: Partial<ReceiptLine> = {}) {
  return receiptLinePreview(lineOf(patch), "invoice", [ovos], [])!;
}

function mountSheet(patch: Partial<ReceiptLine> = {}, open = true, extra: { docked?: boolean } = {}) {
  return mount(ReceiptLineSheet, {
    props: {
      open,
      preview: previewOf(patch),
      materials: [ovos],
      conversions: [],
      stockAfter: 18,
      ...extra,
    },
    slots: { nav: '<nav data-test-record-nav>Item 2 de 5</nav>' },
    global: {
      components: { ReceiptField },
      stubs: { Icon: true, OperatorDayPicker: true, ReceiptConversion: true, ReceiptDifference: true },
    },
    attachTo: document.body,
  });
}

async function settle() {
  await nextTick();
  await nextTick();
  await nextTick();
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("ReceiptLineSheet — a gaveta do item", () => {
  it("abre no item que o operador tocou, e o diz pelo nome", async () => {
    mountSheet();
    await settle();

    const sheet = document.body.querySelector('[data-receipt-sheet="line-1"]');
    expect(sheet).not.toBeNull();
    expect(sheet!.querySelector('[data-slot="sheet-title"]')!.textContent).toContain("OVOS BRANCOS CX 30");
  });

  it("o título fica FORA do que rola — é a promessa da tela", async () => {
    mountSheet();
    await settle();

    const sheet = document.body.querySelector('[data-receipt-sheet="line-1"]')!;
    const title = sheet.querySelector('[data-slot="sheet-title"]')!;
    const scroller = sheet.querySelector(".overflow-y-auto")!;

    expect(scroller).not.toBeNull();
    expect(scroller.contains(title)).toBe(false);
    expect(sheet.querySelector('[data-slot="sheet-header"]')!.contains(title)).toBe(true);
  });

  it("cada campo tem o endereço que o 'Ir até lá' procura", async () => {
    mountSheet({ materialSku: "OVOS" });
    await settle();

    for (const field of ["material", "conversion", "qty", "expiry", "check"] as const) {
      expect(document.querySelector(receiptFieldSelector("line-1", field))).not.toBeNull();
    }
  });

  it("conferir assina o item E fecha a gaveta", async () => {
    const wrapper = mountSheet();
    await settle();

    const check = document.querySelector<HTMLButtonElement>(receiptFieldSelector("line-1", "check"))!;
    expect(check.textContent).toContain("Marcar como conferido");
    check.click();
    await nextTick();

    expect(wrapper.emitted("check")?.at(-1)).toEqual([true]);
    expect(wrapper.emitted("update:open")?.at(-1)).toEqual([false]);
  });

  it("item já conferido oferece desmarcar, e desmarcar NÃO fecha", async () => {
    const wrapper = mountSheet({ checked: true });
    await settle();

    const check = document.querySelector<HTMLButtonElement>(receiptFieldSelector("line-1", "check"))!;
    expect(check.textContent).toContain("desmarcar");
    check.click();
    await nextTick();

    expect(wrapper.emitted("check")?.at(-1)).toEqual([false]);
    expect(wrapper.emitted("update:open")).toBeUndefined();
  });

  it("o que falta neste item é dito no cabeçalho, junto do nome", async () => {
    mountSheet({ expiryDate: "" });
    await settle();

    const header = document.body.querySelector('[data-slot="sheet-header"]')!;
    expect(header.textContent).toContain("Informe a validade");
    expect(header.textContent).toContain("Pendente");
  });

  it("o ir e vir entre itens é da página: o slot `nav` mora no cabeçalho, nos dois jeitos", async () => {
    for (const docked of [false, true]) {
      mountSheet({}, true, { docked });
      await settle();

      const header = document.body.querySelector('[data-slot="sheet-header"]')!;
      expect(header.querySelector("[data-test-record-nav]")?.textContent).toBe("Item 2 de 5");
      document.body.innerHTML = "";
    }
  });

  it("por cima, Fechar fecha a gaveta; encaixada, não há Fechar", async () => {
    const wrapper = mountSheet();
    await settle();

    document.querySelector<HTMLButtonElement>("[data-receipt-sheet-close]")!.click();
    await nextTick();
    expect(wrapper.emitted("update:open")?.at(-1)).toEqual([false]);
    document.body.innerHTML = "";

    mountSheet({}, true, { docked: true });
    await settle();
    expect(document.querySelector("[data-receipt-sheet-docked]")).not.toBeNull();
    expect(document.querySelector("[data-receipt-sheet-close]")).toBeNull();
  });

  it("o numérico escreve no campo ativo, e o −1/+1 mexe na quantidade", async () => {
    const wrapper = mountSheet();
    await settle();

    document.querySelector<HTMLButtonElement>('[aria-label="Um a mais"]')!.click();
    await nextTick();
    expect(wrapper.emitted("update")?.at(-1)).toEqual([{ purchaseQty: 3 }]);

    document.querySelector<HTMLButtonElement>("[data-sheet-cost-field]")!.click();
    await nextTick();
    document.querySelector<HTMLButtonElement>('[aria-label="Dígito 7"]')!.click();
    await nextTick();
    expect(wrapper.emitted("update")?.at(-1)).toEqual([{ costInput: "7" }]);
  });

  it("gaveta fechada não monta formulário nenhum", async () => {
    mountSheet({}, false);
    await settle();

    expect(document.body.querySelector("[data-receipt-sheet]")).toBeNull();
  });
});
