import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { Material, PurchaseList, ReceiptLine, Supplier } from "~/types/purchase";
import {
  RECEIPT_DRAFT_MAX_AGE_MS,
  materialBySku,
  purchaseWorkSet,
  supplierByRef,
  receiptDraftFromStore,
  receiptDraftToStore,
} from "~/presentation/purchaseWorkSet";
import { invoiceKeyHint, materialFacts, moneyInputError, receiptHasStarted, resaleCopy } from "~/presentation/purchase";
import {
  COUNT_FORBIDDEN,
  supplierLacksOrderContact,
  supplierLeadTimeLabel,
  supplierReliabilityLabel,
} from "~/presentation/purchaseUi";

// Beta test 05/11/2026, frente Compras.
// CMP-01: Receber, Custos, Comprar e o Painel liam a página 1 da Base (30 insumos).
// CMP-03: o detalhe por link direto procurava o insumo nessa mesma página.
// CMP-04: recarregar apagava a conferência inteira do recebimento.

const material = (sku: string, name = sku): Material => ({
  sku,
  name,
  unit: "g",
  shelfLifeDays: null,
  isActive: true,
  category: "Secos",
  stockOnHand: 0,
  dailyUse: 0,
  minStock: 0,
  recipes: [],
});

const supplier = (ref: string) => ({ ref, name: ref, displayName: ref, isActive: true }) as unknown as Supplier;

const page = <T>(items: T[], total: number): PurchaseList<T> => ({
  items,
  total,
  has_next: total > items.length,
  page: 1,
  page_size: 30,
  query: "",
  order: "name",
});

describe("base de trabalho x página da tabela (CMP-01)", () => {
  const firstPage = Array.from({ length: 30 }, (_, index) => material(`A-${String(index).padStart(2, "0")}`));
  const farinha = material("FARINHA-BAGATELLE-T45", "Farinha de trigo T45");

  it("trabalha sobre todos os ativos, não sobre os 30 da página", () => {
    const set = purchaseWorkSet({
      materials: page(firstPage, 121),
      suppliers: page([supplier("alto")], 2),
      activeMaterials: [...firstPage, farinha],
      activeSuppliers: [supplier("alto"), supplier("zz-moinho")],
    });

    expect(set.materialPage.items).toHaveLength(30);
    expect(set.materialPage.total).toBe(121);
    expect(set.materials.map((item) => item.sku)).toContain("FARINHA-BAGATELLE-T45");
    expect(set.suppliers.map((item) => item.ref)).toEqual(["alto", "zz-moinho"]);
  });

  it("resposta de ação (lista inteira, sem página) continua servindo as duas", () => {
    const set = purchaseWorkSet({ materials: [farinha], suppliers: [supplier("alto")] });

    expect(set.materials).toEqual([farinha]);
    expect(set.materialPage.items).toEqual([farinha]);
    expect(set.materialPage.total).toBe(1);
  });
});

describe("detalhe pelo SKU (CMP-03)", () => {
  it("acha o insumo fora da página e nunca devolve outro no lugar", () => {
    const work = [material("ALECRIM"), material("WASABI")];
    const shown = [material("ALECRIM")];

    expect(materialBySku("WASABI", work, shown)?.sku).toBe("WASABI");
    expect(materialBySku("NAO-EXISTE", work, shown)).toBeNull();
  });

  it("acha o arquivado aberto pela própria tabela", () => {
    const archived = { ...material("VELHO"), isActive: false };
    expect(materialBySku("VELHO", [material("ALECRIM")], [archived])?.sku).toBe("VELHO");
  });
});

describe("rascunho do recebimento no dispositivo (CMP-04)", () => {
  const line: ReceiptLine = {
    id: "receipt-1",
    materialSku: "ALECRIM",
    conversionId: null,
    purchaseQty: 1200,
    costInput: "110,00",
    expiryDate: "2026-11-06",
    lineNote: "Faltou 300 g",
    checked: true,
  };
  const draft = { mode: "manual" as const, supplierRef: "espaco", invoiceInput: "", note: "", lines: [line], invoiceVolumes: 0 };

  it("a conferência lançada volta depois da recarga", () => {
    const stored = receiptDraftToStore(draft, 1_000);
    const restored = receiptDraftFromStore(stored, 1_000 + 60_000);

    expect(restored?.mode).toBe("manual");
    expect(restored?.supplierRef).toBe("espaco");
    expect(restored?.lines).toEqual([line]);
  });

  it("rascunho vazio não se grava: confirmar ou recusar limpa o dispositivo", () => {
    expect(receiptDraftToStore({ ...draft, lines: [] }, 1_000)).toBeNull();
  });

  it("rascunho de outra entrega (velho) não volta", () => {
    const stored = receiptDraftToStore(draft, 1_000);
    expect(receiptDraftFromStore(stored, 1_000 + RECEIPT_DRAFT_MAX_AGE_MS + 1)).toBeNull();
  });

  it("conteúdo estranho no armazenamento é ignorado", () => {
    expect(receiptDraftFromStore("{não é json", 0)).toBeNull();
    expect(receiptDraftFromStore(JSON.stringify({ mode: "outro", lines: [], savedAt: 0 }), 0)).toBeNull();
  });
});

describe("fornecedor sem contato e sem histórico (CMP-09, CMP-14)", () => {
  it("o cartão de Comprar sabe antes que o pedido não tem por onde sair", () => {
    expect(supplierLacksOrderContact({ canReceiveOrder: false })).toBe(true);
    expect(supplierLacksOrderContact({ canReceiveOrder: true })).toBe(false);
    // Sem fornecedor é outro caso (Lançar custo), não falta de contato.
    expect(supplierLacksOrderContact(null)).toBe(false);
  });

  it("sem entrega registrada não mostra 100% nem 0 dias", () => {
    expect(supplierReliabilityLabel({ reliabilityPercent: 100, lastDeliveryAt: "" })).toBe("sem histórico");
    expect(supplierReliabilityLabel({ reliabilityPercent: 92, lastDeliveryAt: "2026-11-01" })).toBe("92%");
    expect(supplierLeadTimeLabel({ leadTimeDays: 0 })).toBe("não informado");
    expect(supplierLeadTimeLabel({ leadTimeDays: 1 })).toBe("1 dia");
    expect(supplierLeadTimeLabel({ leadTimeDays: 3 })).toBe("3 dias");
  });
});

describe("Receber não pula sob o dedo (CMP-10)", () => {
  it("as abas Com NF/Sem NF ficam até entrar o primeiro item", () => {
    expect(receiptHasStarted([])).toBe(false);
    expect(receiptHasStarted([{ id: "1" }])).toBe(true);
  });

  it("chave só de números que não fecha 44 dígitos avisa junto do campo", () => {
    expect(invoiceKeyHint("12345")).toBe("A chave da NF tem 44 dígitos; faltam 39.");
    expect(invoiceKeyHint("1".repeat(45))).toBe("A chave da NF tem 44 dígitos; aqui há 45.");
    expect(invoiceKeyHint("4126 1012 3456 7800 0190 5500 1000 0128 8410 0012 3417")).toBe("");
    // QR (URL) e campo vazio: quem decide é a leitura.
    expect(invoiceKeyHint("https://www.fazenda.pr.gov.br/nfce/qrcode?p=4126...")).toBe("");
    expect(invoiceKeyHint("")).toBe("");
  });
});

describe("dinheiro abaixo do centavo (CMP-07) e o motivo junto do botão (CMP-16)", () => {
  it("0,055 por g é recusado com o valor que cabe, em vez de virar 0,06 calado", () => {
    const copy = resaleCopy("g", "0,055");
    expect(copy.ready).toBe(false);
    expect(copy.error).toBe("O valor guarda centavos: escreva até duas casas, como 0,06.");
  });

  it("preço negativo diz o motivo, não só apaga o botão", () => {
    expect(resaleCopy("un", "-3").error).toBe("O preço precisa ser maior que zero.");
  });

  it("preço com centavos passa", () => {
    expect(resaleCopy("un", "12,50")).toMatchObject({ ready: true, error: "" });
    expect(moneyInputError("")).toBe("");
  });
});

describe("detalhe do insumo mostra os números (CMP-13)", () => {
  it("estoque, mínimo, cobertura e custo preferencial", () => {
    const facts = materialFacts({
      unit: "g",
      stockOnHand: 1200,
      minStock: 500,
      minStockDeclared: true,
      coverageDays: Number.POSITIVE_INFINITY,
      preferredBaseCostQ: null,
    });
    expect(facts.map((fact) => fact.label)).toEqual(["Estoque", "Mínimo", "Cobertura", "Custo preferencial"]);
    expect(facts.find((fact) => fact.key === "cost")?.value).toBe("sem custo");
    expect(facts.find((fact) => fact.key === "coverage")?.value).toBe("sem consumo");
  });

  it("sem mínimo declarado diz nenhum", () => {
    const facts = materialFacts({ unit: "g", stockOnHand: 0, minStock: 0, minStockDeclared: false, coverageDays: 3, preferredBaseCostQ: 9 });
    expect(facts.find((fact) => fact.key === "minimum")?.value).toBe("nenhum");
    expect(facts.find((fact) => fact.key === "cost")?.value).toContain("/ g");
  });
});

describe("Contar estoque sem permissão (CMP-12)", () => {
  it("diz qual permissão conta e oferece a troca de operador", () => {
    expect(COUNT_FORBIDDEN.title).toContain("permissão de auditoria");
    expect(`${COUNT_FORBIDDEN.title} ${COUNT_FORBIDDEN.description}`).not.toMatch(/gestor/i);
    expect(COUNT_FORBIDDEN.action).toBe("Trocar operador");
  });
});

describe("arquivado aberto pelo filtro continua achável (revisão do #2151)", () => {
  // A base de trabalho só tem os ATIVOS. O arquivado vive só na página da tabela
  // (filtro "Arquivados"): o detalhe do fornecedor e os formulários de edição
  // procuravam só nos ativos, e o formulário de editar um insumo arquivado abria
  // vazio, como se fosse cadastro novo.
  it("o fornecedor arquivado é achado na página quando não está entre os ativos", () => {
    const archived = { ...supplier("velho"), isActive: false };
    expect(supplierByRef("velho", [supplier("alto")], [archived])?.ref).toBe("velho");
    expect(supplierByRef("nao-existe", [supplier("alto")], [archived])).toBeNull();
  });

  it("detalhe do fornecedor e formulários de edição procuram nos ativos E na página", () => {
    const desk = readFileSync(resolve(__dirname, "../app/composables/usePurchaseDesk.ts"), "utf8");
    const detail = readFileSync(resolve(__dirname, "../app/pages/base/suppliers/[ref].vue"), "utf8");

    expect(desk).toMatch(/materialFormSource = computed\(\(\) =>\s*materialBySku\(materialForm\.value\.sku, materials\.value, materialList\.value\.items\)/);
    expect(desk).toMatch(/supplierFormSource = computed\(\(\) => findSupplier\(supplierForm\.value\.ref\)\)/);
    expect(desk).toMatch(/supplierByRef\(ref, suppliers\.value, supplierList\.value\.items\)/);
    expect(detail).toContain("findSupplier(supplierRef.value)");
  });
});
