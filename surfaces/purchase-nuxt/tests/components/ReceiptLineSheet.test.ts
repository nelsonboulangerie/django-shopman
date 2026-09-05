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
import { computed, nextTick } from "vue";
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import ReceiptLineSheet from "../../app/components/ReceiptLineSheet.vue";
import ReceiptField from "../../app/components/ReceiptField.vue";
import UiSheet from "../../app/components/Ui/Sheet/Sheet.vue";
import UiSheetContent from "../../app/components/Ui/Sheet/Content.vue";
import UiSheetPortal from "../../app/components/Ui/Sheet/Portal.vue";
import UiSheetOverlay from "../../app/components/Ui/Sheet/Overlay.vue";
import UiSheetHeader from "../../app/components/Ui/Sheet/Header.vue";
import UiSheetFooter from "../../app/components/Ui/Sheet/Footer.vue";
import UiSheetTitle from "../../app/components/Ui/Sheet/Title.vue";
import UiSheetDescription from "../../app/components/Ui/Sheet/Description.vue";
import UiSheetClose from "../../app/components/Ui/Sheet/Close.vue";
import UiSheetX from "../../app/components/Ui/Sheet/X.vue";
import { receiptFieldSelector } from "../../app/utils/receiptFocus";
import { receiptLinePreview } from "../../app/presentation/purchase";
import type { Material, ReceiptLine } from "../../app/types/purchase";

// Auto-imports do Nuxt que o SFC usa como global (sem runtime Nuxt aqui).
vi.stubGlobal("computed", computed);

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

function mountSheet(patch: Partial<ReceiptLine> = {}, open = true) {
  return mount(ReceiptLineSheet, {
    props: {
      open,
      preview: previewOf(patch),
      materials: [ovos],
      conversions: [],
      stockAfter: 18,
    },
    global: {
      components: {
        UiSheet,
        UiSheetContent,
        UiSheetPortal,
        UiSheetOverlay,
        UiSheetHeader,
        UiSheetFooter,
        UiSheetTitle,
        UiSheetDescription,
        UiSheetClose,
        UiSheetX,
        ReceiptField,
      },
      stubs: { Icon: true, MaterialPicker: true, ReceiptConversion: true },
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

  it("gaveta fechada não monta formulário nenhum", async () => {
    mountSheet({}, false);
    await settle();

    expect(document.body.querySelector("[data-receipt-sheet]")).toBeNull();
  });
});
