// Travas da conformidade V6 do Compras com a v4 (auditoria pdv-prod-compras, ids C*).
// Cada bloco segura uma classe de divergência que já voltou uma vez.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { materialForEan, normalizeGtin, parseGs1, receiptLineForEan } from "../app/presentation/scanning";
import type { Material, ReceiptLine } from "../app/types/purchase";

const app = (path: string) => readFileSync(resolve(__dirname, "../app", path), "utf8");
const kit = (path: string) => readFileSync(resolve(__dirname, "../../operator-kit/app", path), "utf8");
const GS = String.fromCharCode(29);

describe("C21: Ler da embalagem (GS1)", () => {
  it("lê validade (17) e lote (10) com parênteses", () => {
    expect(parseGs1("(01)07891000315507(17)261012(10)L42")).toEqual({
      gtin: "07891000315507",
      expiry: "2026-10-12",
      lot: "L42",
    });
  });

  it("lê o código cru com o separador FNC1 e o lote no meio", () => {
    expect(parseGs1(`010789100031550710AB12${GS}17261031`)).toEqual({
      gtin: "07891000315507",
      expiry: "2026-10-31",
      lot: "AB12",
    });
  });

  it("dia 00 é o último dia do mês; 'consumir antes de' (15) vale quando falta a 17", () => {
    expect(parseGs1("(15)270200")?.expiry).toBe("2027-02-28");
  });

  it("EAN comum não é GS1 com validade", () => {
    expect(parseGs1("7891000315507")).toBeNull();
  });
});

describe("C11: Ler EAN acha o item", () => {
  const lines = [
    { id: "l1", materialSku: "MANT", invoiceEan: "7891000315507" },
    { id: "l2", materialSku: "FAR", invoicePackageEan: "17891000999993" },
    { id: "l3", materialSku: "OVOS" },
  ] as ReceiptLine[];
  const materials = [{ sku: "OVOS", eans: ["7890000000017"] }] as unknown as Material[];

  it("pelo EAN da nota (unidade e caixa) e pelo que o cadastro já conhece", () => {
    expect(receiptLineForEan("7891000315507", lines, materials)?.id).toBe("l1");
    expect(receiptLineForEan("17891000999993", lines, materials)?.id).toBe("l2");
    expect(receiptLineForEan("7890000000017", lines, materials)?.id).toBe("l3");
    expect(receiptLineForEan("1111111111116", lines, materials)).toBeNull();
    expect(materialForEan("07890000000017", materials)?.sku).toBe("OVOS");
    expect(normalizeGtin("00789100031550")).toBe("789100031550");
  });
});

describe("C01: a busca da Base aparece (o kit lê $slots no render)", () => {
  it("o cabeçalho do kit não guarda a busca num computed sobre useSlots()", () => {
    const header = kit("components/OperatorPageHeader.vue");
    expect(header).not.toMatch(/computed\(\(\) => Boolean\(slots\.search\)\)/);
    // Sem `#search`, a busca padrão da suíte (V6-BUSCA): `$slots.search || search`.
    expect(header).toMatch(/v-if="\$slots\.search(?: \|\| search)?"/);
  });
});

describe("C02/C04/C05/C06: a Base (fase 2)", () => {
  const page = app("pages/base/materials.vue");
  it("ordenar pelo cabeçalho da tabela da suíte; o ⋯ como dados do cabeçalho", () => {
    expect(page).toContain("<OperatorTable");
    expect(page).toContain("enableSorting: true");
    expect(page).toContain(':actions="headerActions"');
  });
  it("etiquetas quebram em vez de cortar", () => {
    expect(page).toContain("data-base-role-tags");
    expect(page).not.toContain("truncate");
  });
  it("sub-seções: lista no celular, abas na mesa, decididas pelo CSS", () => {
    const sections = app("components/PurchaseBaseSections.vue");
    expect(sections).toContain("<NuxtSelect");
    expect(sections).toContain('class="w-44 sm:hidden"');
    expect(sections).toContain("max-sm:hidden");
  });
});

describe("C12 a C19: o Receber no celular (fase 2)", () => {
  const page = app("pages/receive.vue");
  it("voltar na barra do documento; o ⋯ é o do cabeçalho, com Atualizar dentro", () => {
    expect(page).toContain("data-receipt-back");
    expect(page).toContain("data-receipt-subtitle");
    expect(page).toContain(':actions="headerActions"');
    expect(page).not.toContain("PurchaseMoreMenu");
  });
  it("a ação do momento mora no OperatorActionBar (Escanear NF, Contei N volumes, Confirmar entrada)", () => {
    expect(page).toContain("<OperatorActionBar");
    expect(page).toContain('label: actionPending.value ? "Lendo a NF" : "Escanear NF"');
    expect(page).toContain('label: `Contei ${plural(volumesDraft.value, "volume", "volumes")}`');
    expect(page).toContain('label: actionPending.value ? "Confirmando a entrada" : "Confirmar entrada"');
    expect(page).not.toMatch(/sticky bottom-/);
  });
  it("os pendentes não se repetem no painel quando a conferência por exceção está na tela", () => {
    expect(page).toContain("pendingLines: exceptionFlowOn.value ? [] : receiptPendingLines.value");
  });
  it("o item aberto tem endereço e anda com OperatorRecordNav", () => {
    expect(page).toContain("route.query.line");
    expect(page).toContain("<OperatorRecordNav");
  });
});

describe("C09/C10: a gaveta do item", () => {
  const sheet = app("components/ReceiptLineSheet.vue");
  it("encaixa ao lado da lista no tablet e tem numérico na tela", () => {
    expect(sheet).toContain("data-receipt-sheet-docked");
    expect(sheet).toContain("data-sheet-numpad");
    expect(sheet).toContain("OperatorDayPicker");
  });
  it("EAN, Ler da embalagem e Devolver só este item na gaveta", () => {
    expect(sheet).toContain("data-sheet-scan-ean");
    expect(sheet).toContain("data-sheet-read-package");
    expect(sheet).toContain("data-sheet-reject-line");
  });
});

describe("T-06: Atualizar mora no ⋯, com a tecla R", () => {
  it("toda tela declara Atualizar nas ações do cabeçalho; a tecla é do app", () => {
    for (const page of ["pages/index.vue", "pages/buy.vue", "pages/base/materials.vue"]) {
      expect(app(page), page).toContain('{ label: "Atualizar", icon: "i-lucide-refresh-cw", kbds: ["R"]');
    }
    expect(app("app.vue")).toContain('onKeyStroke(["r", "R"]');
  });
});
