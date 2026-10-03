import type {
  SaleSuggestion,
  SkuRoles,
  CountItem,
  CountRow,
  CountSummary,
  EnrichedMaterial,
  Material,
  MaterialConversion,
  MaterialIssue,
  MaterialTone,
  ReceiptBlocker,
  ReceiptConferenceTally,
  ReceiptConversionSuggestion,
  ReceiptExceptionView,
  ReceiptExpiryShortcut,
  ReceiptFieldAnchor,
  ReceiptFiscalDivergence,
  ReceiptLine,
  ReceiptLineDifference,
  ReceiptLinePreview,
  ReceiptLineRow,
  ReceiptLineStatus,
  ReceiptLineStatusBadge,
  ReceiptLineSuggestion,
  ReceiptMode,
  ReceiptOutcome,
  ReceiptPendingItem,
  PurchaseCostBatchPayload,
  ReceiptWarning,
  ReorderBlocker,
  ReorderRow,
  QuotePreview,
  Supplier,
  SupplierCostRow,
  SupplierMaterialCost,
} from "~/types/purchase";
import { addDays, shortDayMonth, weekdayShort } from "../../../operator-kit/app/presentation/dates";

const moneyFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
});

const quantityFormatter = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

export function formatMoney(cents: number | null | undefined): string {
  if (cents === null || cents === undefined || Number.isNaN(cents)) return "—";
  return moneyFormatter.format(cents / 100);
}

/**
 * Dinheiro digitado → centavos, com a MESMA regra do `parseQtyInput` abaixo:
 * **vírgula presente decide a notação**.
 *
 * ⚠️ Isto removia TODOS os pontos antes de olhar a vírgula, então o teclado do
 * sistema divergia do servidor em até 100×:
 *
 *     "12.50"  tela: R$ 1.250,00   servidor: R$ 12,50
 *     "12.5"   tela: R$ 125,00     servidor: R$ 12,50
 *
 * Nenhum dos dois lados avisava. O caminho pré-preenchido pela NF estava a salvo —
 * o buraco era a DIGITAÇÃO, que é exatamente o modo manual "sem NF".
 */
export function parseMoneyInput(value: string): number {
  const text = value.trim().replace(/[R$\s]/g, "");
  if (!text) return 0;
  const normalized = text.includes(",") ? text.replace(/\./g, "").replace(",", ".") : text;
  const parsed = Number(normalized);
  if (!Number.isFinite(parsed) || parsed <= 0) return 0;
  return Math.round(parsed * 100);
}

export function formatQty(value: number, unit: string): string {
  if (!Number.isFinite(value)) return "—";
  return `${quantityFormatter.format(value)} ${unit}`;
}

/** Explica o FC sem reaplicá-lo: suggestedQty/dailyUse já são brutos no ledger. */
export function purchaseSuggestionLabel(
  material: Pick<Material, "unit" | "weightedUsableFactor" | "suggestedNetQty">,
  suggestedQty: number,
): string {
  const factor = material.weightedUsableFactor;
  if (factor === null || factor === undefined || !Number.isFinite(factor) || factor <= 0 || factor >= 1) {
    return formatQty(suggestedQty, material.unit);
  }
  const net = material.suggestedNetQty;
  const netQty = net !== null && net !== undefined && Number.isFinite(net) ? net : suggestedQty * factor;
  const percent = quantityFormatter.format(factor * 100);
  return `≈ ${formatQty(suggestedQty, material.unit)} a comprar (${formatQty(netQty, material.unit)} limpos ÷ ${percent}%)`;
}

/**
 * O saldo do insumo, com o "≈" quando ele atravessou uma ponte aproximada.
 *
 * ADR-024, R3: "some o ≈, some a informação". Um saldo de 1,5 kg que veio de
 * "30 ovos ≈ 50 g cada" não é o mesmo número que 1,5 kg pesados na balança, e a
 * tela é o último lugar onde ainda dá para dizer isso.
 */
export function formatStockOnHand(material: Pick<Material, "stockOnHand" | "unit" | "stockIsApproximate">): string {
  const quantity = formatQty(material.stockOnHand, material.unit);
  return material.stockIsApproximate ? `≈ ${quantity}` : quantity;
}

export function formatFactor(value: number, unit: string, approximate = false): string {
  const prefix = approximate ? "≈ " : "";
  return `${prefix}${quantityFormatter.format(value)} ${unit}`;
}

const shortDateFormatter = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit" });

/**
 * Data curta (dd/mm) para carimbo de tela — "—" quando não há data.
 *
 * `Intl.DateTimeFormat.format()` **lança** `RangeError: Invalid time value`
 * diante de um Invalid Date, em vez de devolver texto. Como a projeção manda
 * `lastDeliveryAt: ""` para todo fornecedor que ainda não entregou, formatar
 * sem checar derrubava o render inteiro da aba Fornecedores. Ausência de data é
 * um estado normal do domínio, não um erro: ela vira travessão, não exceção.
 */
export function formatShortDate(value: string | null | undefined): string {
  const text = (value ?? "").trim();
  if (!text) return "—";
  const parsed = new Date(`${text}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return "—";
  return shortDateFormatter.format(parsed);
}

export function coverageDays(material: Pick<Material, "stockOnHand" | "dailyUse">): number {
  if (material.dailyUse <= 0) return Number.POSITIVE_INFINITY;
  return material.stockOnHand / material.dailyUse;
}

// O limiar vem do servidor (prazo do fornecedor + revisão + segurança, política
// no Admin); 3 é só o fallback do modo demonstração, sem backend.
export function replenishAtDays(material: Pick<Material, "replenishAtDays">): number {
  const days = material.replenishAtDays ?? 0;
  return Number.isFinite(days) && days > 0 ? days : 3;
}

export function coverageLabel(days: number): string {
  if (!Number.isFinite(days)) return "sem consumo";
  if (days < 1) return "< 1 dia";
  return `${quantityFormatter.format(days)} dias`;
}

export function conversionFor(
  cost: SupplierMaterialCost,
  conversions: MaterialConversion[],
): MaterialConversion | null {
  if (!cost.conversionId) return null;
  return conversions.find((conversion) => conversion.id === cost.conversionId) ?? null;
}

export function purchaseUnitLabel(
  cost: SupplierMaterialCost,
  material: Material | undefined,
  conversions: MaterialConversion[],
): string {
  return conversionFor(cost, conversions)?.label ?? material?.unit ?? "";
}

export function baseFactor(cost: SupplierMaterialCost, conversions: MaterialConversion[]): number {
  return conversionFor(cost, conversions)?.toBaseFactor ?? 1;
}

export function isApproximateCost(cost: SupplierMaterialCost, conversions: MaterialConversion[]): boolean {
  return conversionFor(cost, conversions)?.kind === "approximate";
}

export function costPerBaseUnitQ(cost: SupplierMaterialCost, conversions: MaterialConversion[]): number {
  const factor = baseFactor(cost, conversions);
  return Math.round(cost.costQ / factor);
}

export function quotePreview(
  input: string,
  material: Material | undefined,
  conversion: MaterialConversion | null,
): QuotePreview | null {
  const costQ = parseMoneyInput(input);
  if (!material || costQ <= 0) return null;
  const factor = conversion?.toBaseFactor ?? 1;
  return {
    costQ,
    purchaseUnitLabel: conversion?.label ?? material.unit,
    baseFactor: factor,
    baseCostQ: Math.round(costQ / factor),
    approximate: conversion?.kind === "approximate",
  };
}

export function parseInvoiceAccessKey(raw: string): string | null {
  const compact = raw.replace(/\D/g, "");
  const match = compact.match(/\d{44}/);
  return match?.[0] ?? null;
}

export function invoiceProbe(raw: string) {
  const accessKey = parseInvoiceAccessKey(raw);
  return {
    raw,
    accessKey,
    valid: Boolean(accessKey),
  };
}

export function receiptBaseQty(line: ReceiptLine, conversion: MaterialConversion | null): number {
  const factor = conversion?.toBaseFactor ?? 1;
  return line.purchaseQty * factor;
}

export function receiptLineSuggestion(line: ReceiptLine, materials: Material[]): ReceiptLineSuggestion | null {
  const sku = line.suggestedMaterialSku ?? "";
  if (line.materialSku || !sku) return null;
  const material = materials.find((item) => item.sku === sku);
  return {
    sku,
    name: material?.name ?? sku,
    scorePercent: Math.round(line.suggestionScore ?? 0),
    byBarcode: line.suggestionSource === "gtin",
  };
}

export function receiptConversionSuggestion(line: ReceiptLine): ReceiptConversionSuggestion | null {
  const suggestion = line.conversionSuggestion;
  if (!suggestion?.label) return null;
  const factor = Number(suggestion.factor);
  return Number.isFinite(factor) && factor > 0 ? suggestion : null;
}

/**
 * A NF discorda da conversão que a linha já usa.
 *
 * Compara os FATORES em vez de confiar na simples presença da sugestão. O
 * servidor de fato cala a sugestão quando os dois batem — mas só no momento do
 * scan, e a linha muda depois disso: aceitar a conversão sugerida cria a
 * conversão e a seleciona sem um novo scan, e aí a sugestão continua na linha
 * concordando com ela. Sem a comparação, o gesto de aceitar terminava
 * acusando divergência consigo mesmo.
 *
 * É o alerta de ordem de grandeza da ADR-024: saco declarado de 25 kg com nota
 * dizendo 20 é erro de 20% no custo e no estoque, e passa liso se ninguém
 * perguntar.
 */
export function receiptConversionDiverges(
  line: ReceiptLine,
  conversion: MaterialConversion | null,
): boolean {
  const suggestion = receiptConversionSuggestion(line);
  if (!conversion || !suggestion) return false;
  const suggested = Number(suggestion.factor);
  const chosen = conversion.toBaseFactor;
  if (!Number.isFinite(chosen) || chosen <= 0) return false;
  // Mesma tolerância relativa do servidor: 0,5 e 0,500000 são o mesmo fator.
  return Math.abs(chosen - suggested) > Math.max(chosen, suggested) * 0.001;
}

/**
 * O que a nota diz sobre este item, em uma linha.
 *
 * É a âncora do card: sem ela o operador vê uma fila de "Definir insumo" e não
 * tem como saber qual linha do papel está olhando. Os dois eixos aparecem lado
 * a lado quando divergem ("4 SC · 100 KG na NF"), porque é essa divergência que
 * explica de onde a conversão sugerida saiu.
 */
export function receiptInvoiceSummary(line: ReceiptLine): string {
  const parts: string[] = [];
  const qty = line.invoiceQty ?? 0;
  if (qty > 0 && line.invoiceUnit) parts.push(`${quantityFormatter.format(qty)} ${line.invoiceUnit}`);
  const taxQty = line.invoiceTaxQty ?? 0;
  if (taxQty > 0 && line.invoiceTaxUnit) {
    parts.push(`${quantityFormatter.format(taxQty)} ${line.invoiceTaxUnit} na NF`);
  }
  if (line.invoiceLot) parts.push(`lote ${line.invoiceLot}`);
  if (line.invoiceProductCode) parts.push(`cód ${line.invoiceProductCode}`);
  return parts.join(" · ");
}

/**
 * A frase do que fazer AGORA nesta linha — uma só, a mais urgente.
 *
 * O painel de bloqueios listava dez pílulas iguais ("Definir insumo",
 * "Definir insumo", …) sem dizer de qual item, e o card não dizia nada. Uma
 * instrução por linha, na própria linha, é o que responde "o que eu faço?".
 */
export function receiptNextStep(warnings: ReceiptWarning[]): string {
  const blocker = warnings.find((warning) => warning.tone === "block");
  return blocker?.label ?? "";
}

/** Bloqueios que o card do próprio campo já anuncia — o topo não os repete. */
const FIELD_LEVEL_BLOCKERS = new Set([
  "difference-reason",
  "confirm-suggestion",
  "missing-material",
  "confirm-conversion",
  "missing-conversion",
  "missing-expiry",
]);

export function receiptNextStepIsOnField(warnings: ReceiptWarning[]): boolean {
  const blocker = warnings.find((warning) => warning.tone === "block");
  return Boolean(blocker && FIELD_LEVEL_BLOCKERS.has(blocker.key));
}

/**
 * O ENDERECO de cada bloqueio dentro do card da linha.
 *
 * Um aviso que sabe o que falta e nao sabe onde nao e um aviso, e uma acusacao:
 * "informe a validade" no rodape de uma nota de dez itens deixa o operador
 * rolando a tela para achar qual item e qual campo. Com a ancora, o mesmo aviso
 * vira um gesto — a tela rola ate o campo e foca nele.
 */
const BLOCKER_FIELD: Record<ReceiptWarning["key"], ReceiptFieldAnchor | null> = {
  "missing-material": "material",
  "confirm-suggestion": "material",
  "confirm-conversion": "conversion",
  "missing-conversion": "conversion",
  "invalid-qty": "qty",
  "difference-reason": "reason",
  "missing-expiry": "expiry",
  "diverging-conversion": null,
  "fiscal-divergence": null,
  "missing-cost": null,
  "approximate-conversion": null,
  "manual-source": null,
};

export function receiptNextStepField(warnings: ReceiptWarning[]): ReceiptFieldAnchor | null {
  const blocker = warnings.find((warning) => warning.tone === "block");
  return blocker ? BLOCKER_FIELD[blocker.key] : null;
}

/**
 * COMO o item se chama — o mesmo nome na lista, na gaveta e na pendência.
 *
 * O operador nunca pode ter dúvida sobre qual item está mexendo, e essa
 * certeza só existe se os três lugares disserem a mesma palavra. Eram três
 * fórmulas parecidas em três arquivos, e a do cabeçalho perdia o nome do
 * insumo quando a entrada era lançada à mão.
 */
export function receiptLineLabel(preview: ReceiptLinePreview): string {
  if (preview.line.invoiceDescription) return preview.line.invoiceDescription;
  if (preview.line.materialSku) return preview.material.name;
  return "Item lançado à mão";
}

/**
 * Avisos que pedem OLHO, e não gesto.
 *
 * `manual-source` fica de fora de propósito: "sem documento fiscal" é a origem
 * que a CASA escolheu para a entrada inteira, e não uma anomalia deste item.
 * Pintar de âmbar todas as linhas de um romaneio é ruído — o amarelo que
 * aparece sempre não avisa nada.
 */
const ATTENTION_WARNINGS = new Set<ReceiptWarning["key"]>([
  "diverging-conversion",
  "fiscal-divergence",
  "approximate-conversion",
  "missing-cost",
]);

/**
 * O estado do item, em uma palavra — a cor da linha sai daqui e de nenhum
 * outro lugar.
 *
 * A ordem não é arbitrária:
 *
 * 1. **bloqueio ganha de tudo**, inclusive de conferido: dá para marcar como
 *    conferido e depois trocar o insumo, e a linha verde com bloqueio seria uma
 *    mentira — o `Confirmar entrada` continuaria travado sem a lista dizer por
 *    quê.
 * 2. **conferido ganha da atenção**: a divergência foi vista e assinada pelo
 *    operador; repintar de âmbar o que ele acabou de confirmar desfaz o gesto.
 */
export function receiptLineStatus(preview: ReceiptLinePreview, matched = false): ReceiptLineStatus {
  if (preview.warnings.some((warning) => warning.tone === "block")) return "blocked";
  if (preview.line.checked) return "checked";
  if (matched) return "matched";
  if (preview.warnings.some((warning) => ATTENTION_WARNINGS.has(warning.key))) return "attention";
  return "ready";
}

const RECEIPT_LINE_STATUS_BADGE: Record<ReceiptLineStatus, ReceiptLineStatusBadge> = {
  blocked: { label: "Pendente", icon: "lucide:circle-alert" },
  attention: { label: "Revisar", icon: "lucide:triangle-alert" },
  ready: { label: "Confirmável", icon: "lucide:circle-dashed" },
  matched: { label: "Bate com a nota", icon: "lucide:circle-check" },
  checked: { label: "Conferido", icon: "lucide:circle-check-big" },
};

export function receiptLineStatusBadge(status: ReceiptLineStatus): ReceiptLineStatusBadge {
  return RECEIPT_LINE_STATUS_BADGE[status];
}

/**
 * A segunda linha da lista: o que já está apurado, ou o que a nota diz.
 *
 * Sem insumo escolhido não há o que apurar — repetir a quantidade na unidade
 * errada ("4 kg" para 4 sacos) seria exatamente o engano que a conversão
 * existe para evitar. Aí a linha mostra o que veio na nota, que é o que o
 * operador tem na mão.
 */
export function receiptLineDigest(preview: ReceiptLinePreview): string {
  return preview.line.materialSku ? receiptSettledSummary(preview) : preview.invoiceSummary;
}

/**
 * A LISTA da entrada — uma linha por item, pronta para desenhar.
 *
 * A tela do recebimento era uma pilha de formulários abertos, um por item: para
 * saber o que faltava numa nota de dez linhas, o operador rolava dez cards. A
 * lista dá a visão geral que faltava, e cada linha já diz em que pé está.
 */
export function receiptLineRows(
  previews: ReceiptLinePreview[],
  matchedIds: ReadonlySet<string> = new Set(),
): ReceiptLineRow[] {
  return previews.map((preview) => {
    const status = receiptLineStatus(preview, matchedIds.has(preview.line.id));
    const badge = receiptLineStatusBadge(status);
    return {
      id: preview.line.id,
      label: receiptLineLabel(preview),
      digest: receiptLineDigest(preview),
      status,
      statusLabel: badge.label,
      statusIcon: badge.icon,
      nextStep: preview.nextStep,
      note: preview.line.lineNote,
      // Enquanto ninguém digitou o valor, o número que existe é o da NOTA — e
      // dizer "R$ 0,00" seria afirmar um preço que ninguém apurou.
      total: preview.totalCostQ > 0 ? formatMoney(preview.totalCostQ) : (preview.line.invoiceTotal ?? ""),
    };
  });
}

/**
 * As pendencias da entrada, uma por item, com nome e endereco.
 *
 * Entram duas coisas que travam o `Confirmar entrada`, e nao so uma: o bloqueio
 * de campo (validade, insumo, embalagem, quantidade) e a linha COMPLETA que
 * ninguem conferiu ainda. A segunda nao aparecia em lugar nenhum — o botao
 * ficava cinza sem que nada na tela dissesse por que.
 */
export function receiptPendingItems(
  previews: ReceiptLinePreview[],
  // As linhas que batem com a nota: não pedem o ok, porque a contagem de
  // volumes (pendência própria, fora da linha) responde por elas.
  excused: ReadonlySet<string> = new Set(),
): ReceiptPendingItem[] {
  return previews.flatMap<ReceiptPendingItem>((preview) => {
    const label = receiptLineLabel(preview);
    if (preview.nextStep) {
      return [
        {
          id: preview.line.id,
          label,
          step: preview.nextStep,
          field: preview.nextStepField ?? "material",
          tone: "block",
        },
      ];
    }
    if (!preview.line.checked && !excused.has(preview.line.id)) {
      return [{ id: preview.line.id, label, step: "Marcar como conferido", field: "check", tone: "watch" }];
    }
    return [];
  });
}

/**
 * O rascunho ainda nao comecou.
 *
 * Confirmar a entrada zera o rascunho, e um rascunho zerado dispara os mesmos
 * bloqueios de sempre ("Ler QR, codigo de barras ou chave da NF"). O operador
 * acabava de acertar tudo e recebia um vermelho por cima do verde. Rascunho em
 * branco nao e erro: e convite.
 */
export function receiptIsBlank(lines: ReceiptLine[], invoiceInput: string, note: string): boolean {
  return lines.length === 0 && !invoiceInput.trim() && !note.trim();
}

/**
 * O primeiro gesto que falta para confirmar — na ordem em que a tela os pede.
 *
 * Documento e fornecedor vem antes das linhas porque sem eles a entrada nao tem
 * de onde vir. `null` significa pronto para confirmar.
 */
export function receiptFirstBlocker(
  documentBlockers: string[],
  supplierBlockers: string[],
  pending: ReceiptPendingItem[],
  hasLines: boolean,
  // A contagem de volumes que falta (ou que não fechou), em uma frase.
  volumesStep = "",
): ReceiptBlocker | null {
  if (documentBlockers.length) {
    return { scope: "document", step: documentBlockers[0]!, label: "", lineId: "", field: null, anchor: "invoice" };
  }
  if (supplierBlockers.length) {
    return { scope: "supplier", step: supplierBlockers[0]!, label: "", lineId: "", field: null, anchor: "supplier" };
  }
  if (!hasLines) {
    return { scope: "document", step: "Lance ao menos um item para dar entrada", label: "", lineId: "", field: null, anchor: "invoice" };
  }
  if (volumesStep) {
    return { scope: "volumes", step: volumesStep, label: "", lineId: "", field: null, anchor: "volumes" };
  }
  const item = pending[0];
  if (!item) return null;
  return { scope: "line", step: item.step, label: item.label, lineId: item.id, field: item.field, anchor: null };
}

/** O recibo em uma frase: "7 itens · R$ 1.480,00 · Moinho SP". */
export function receiptOutcomeSummary(outcome: ReceiptOutcome): string {
  const parts = [`${outcome.lineCount} ${outcome.lineCount === 1 ? "item" : "itens"}`];
  if (outcome.totalCostQ > 0) parts.push(formatMoney(outcome.totalCostQ));
  if (outcome.supplierName) parts.push(outcome.supplierName);
  return parts.join(" · ");
}

/**
 * A linha veio da nota já na unidade-base do insumo?
 *
 * O leitor de NF-e responde isso, e não a tela: quando a unidade da nota
 * alcança a base pela física (a própria base, ou kg↔g, l↔ml), o servidor já
 * converte a quantidade e devolve a linha sem conversão e sem pedir uma
 * (`conversionId: null`, `requiresConversion: false`). Aplicar a embalagem
 * padrão do insumo por cima multiplicava de novo: "5 KG" de creme de leite
 * virava "5.000 × litros = 5.050.000 g".
 */
export function receiptLineInBaseUnit(line: ReceiptLine): boolean {
  return Boolean(line.invoiceUnit) && !line.conversionId && !line.requiresConversion;
}

/**
 * A conversão que a linha recebe quando ninguém escolheu uma: a primeira das
 * candidatas, salvo quando a nota já veio na unidade-base (aí nenhuma).
 */
export function receiptDefaultConversionId(line: ReceiptLine, candidates: MaterialConversion[]): string | null {
  if (receiptLineInBaseUnit(line)) return null;
  return candidates[0]?.id ?? null;
}

/**
 * Em que unidade está a quantidade desta linha — "4 o quê?".
 *
 * A resposta nunca é "não sei": a nota já diz `4 SC` antes de qualquer insumo
 * estar escolhido. A ordem é a da certeza:
 *
 * 1. **conversão escolhida** → o rótulo dela ("saco 25 kg"), que é o vocabulário
 *    em que o operador está contando;
 * 2. **conversão ainda pendente, ou insumo ainda indefinido** → a unidade da
 *    NOTA. Dizer "kg" aqui seria repetir no rótulo o mesmo erro que esta frente
 *    existe para corrigir — 4 sacos não são 4 kg;
 * 3. **entrada na própria base** (ou lançamento à mão) → a unidade do insumo.
 */
export function receiptPurchaseUnitLabel(
  line: ReceiptLine,
  material: Material | undefined,
  conversion: MaterialConversion | null,
): string {
  if (conversion) return conversion.label;
  if ((line.requiresConversion || !material) && line.invoiceUnit) return line.invoiceUnit;
  return material?.unit ?? line.invoiceUnit ?? "";
}

/**
 * Os dois eixos da nota, quando eles bastam para propor uma conversão.
 *
 * "7 CX = 35 KG" é o que a NF diz — e é dito sem precisar do insumo. O fator
 * ("1 caixa = 5 kg") já precisa da unidade-base, e por isso é o servidor que o
 * calcula: a física vive em `shopman.utils.units` e uma segunda cópia aqui
 * seria exatamente a tabela paralela que a ADR-024 proíbe.
 */
export function receiptInvoiceAxes(line: ReceiptLine): string {
  const qty = line.invoiceQty ?? 0;
  const taxQty = line.invoiceTaxQty ?? 0;
  if (qty <= 0 || taxQty <= 0 || !line.invoiceUnit || !line.invoiceTaxUnit) return "";
  return `${quantityFormatter.format(qty)} ${line.invoiceUnit} = ${quantityFormatter.format(taxQty)} ${line.invoiceTaxUnit}`;
}

/**
 * As divergências fiscais que valem para o item que a linha aponta AGORA.
 *
 * O servidor confere a nota contra o produto resolvido (ou sugerido) no scan;
 * trocar o item da linha torna a conferência de outro produto, e ela se cala.
 */
export function receiptFiscalDivergences(line: ReceiptLine): ReceiptFiscalDivergence[] {
  const sku = line.materialSku;
  if (!sku) return [];
  return (line.fiscalDivergences ?? []).filter((divergence) => divergence.sku === sku);
}

export function receiptLineWarnings(
  line: ReceiptLine,
  mode: ReceiptMode,
  material: Material | undefined,
  conversion: MaterialConversion | null,
): ReceiptWarning[] {
  const warnings: ReceiptWarning[] = [];
  if (!material) {
    return line.suggestedMaterialSku ?
        [{ key: "confirm-suggestion", label: "Confirme o item sugerido", tone: "block" }]
      : [{ key: "missing-material", label: "Escolha o item desta linha", tone: "block" }];
  }
  if (!Number.isFinite(line.purchaseQty) || line.purchaseQty <= 0) {
    warnings.push({ key: "invalid-qty", label: "Informe a quantidade recebida", tone: "block" });
  }
  if (line.requiresConversion && !conversion) {
    // A NF sabe o fator: a linha continua bloqueando, mas o bloqueio agora tem
    // um gesto do lado — aceitar o que a nota diz — em vez de só uma acusação.
    warnings.push(
      receiptConversionSuggestion(line) ?
        { key: "confirm-conversion", label: "Confirme a conversão que a NF sugere", tone: "block" }
      : { key: "missing-conversion", label: "Cadastre a conversão da embalagem", tone: "block" },
    );
  }
  if (receiptConversionDiverges(line, conversion)) {
    warnings.push({ key: "diverging-conversion", label: "NF diverge da conversão", tone: "watch" });
  }
  if (receiptFiscalDivergences(line).length) {
    // Não bloqueia: a mercadoria entra. O cadastro fiscal é conferido depois,
    // no Admin, e o recebimento deixa a sugestão e o aviso para isso.
    warnings.push({ key: "fiscal-divergence", label: "NF diverge do cadastro fiscal", tone: "watch" });
  }
  if (parseMoneyInput(line.costInput) <= 0) {
    warnings.push({ key: "missing-cost", label: "Conferir valor", tone: "watch" });
  }
  if (receiptLineDifference(line) && !line.lineNote.trim()) {
    // A nota diz 20, chegaram 18: não entra em silêncio. O servidor recusa
    // igual (`receipt_difference_reason_required`).
    warnings.push({ key: "difference-reason", label: "Escolha o motivo da diferença", tone: "block" });
  }
  if (material.shelfLifeDays !== null && !line.expiryDate) {
    warnings.push({ key: "missing-expiry", label: "Informe a validade", tone: "block" });
  }
  if (conversion?.kind === "approximate") {
    warnings.push({ key: "approximate-conversion", label: "Conversão estimada", tone: "watch" });
  }
  if (mode === "manual") {
    warnings.push({ key: "manual-source", label: "Sem documento fiscal", tone: "watch" });
  }
  return warnings;
}

/**
 * A linha conferida em uma frase: "4 × Saco 25 kg = 100 kg · R$ 730,00".
 *
 * É o que sobra visível quando o item recolhe. Tem de bastar para a conferência
 * de olho — numa nota de dez itens, quem já decidiu não quer rolar por dez
 * formulários abertos para achar o que ainda falta.
 */
export function receiptSettledSummary(preview: ReceiptLinePreview): string {
  const parts: string[] = [];
  const unit = preview.purchaseUnitLabel;
  parts.push(unit ? `${quantityFormatter.format(preview.line.purchaseQty)} × ${unit}` : formatQty(preview.line.purchaseQty, preview.material.unit));
  if (preview.baseQtyKnown && preview.purchaseUnitLabel !== preview.material.unit) {
    parts.push(`= ${formatQty(preview.baseQty, preview.material.unit)}`);
  }
  const settled = parts.join(" ");
  return preview.totalCostQ > 0 ? `${settled} · ${formatMoney(preview.totalCostQ)}` : settled;
}

export function receiptLinePreview(
  line: ReceiptLine,
  mode: ReceiptMode,
  materials: Material[],
  conversions: MaterialConversion[],
): ReceiptLinePreview | null {
  const matchedMaterial = materials.find((item) => item.sku === line.materialSku);
  const material = matchedMaterial ?? {
    sku: line.materialSku || "",
    name: line.materialSku || "Definir insumo",
    unit: "un",
    shelfLifeDays: null,
    isActive: false,
    category: "Importado da NF",
    stockOnHand: 0,
    dailyUse: 0,
    minStock: 0,
    recipes: [],
  } satisfies Material;
  const conversion = line.conversionId ?
    conversions.find((item) => item.id === line.conversionId) ?? null
  : null;
  const baseQty = receiptBaseQty(line, conversion);
  const baseQtyKnown = Boolean(conversion) || !line.requiresConversion;
  const totalCostQ = parseMoneyInput(line.costInput);
  const warnings = receiptLineWarnings(line, mode, matchedMaterial, conversion);
  return {
    line,
    material,
    conversion,
    purchaseUnitLabel: receiptPurchaseUnitLabel(line, matchedMaterial, conversion),
    baseQty,
    baseQtyKnown,
    baseCostQ: baseQtyKnown && baseQty > 0 ? Math.round(totalCostQ / baseQty) : 0,
    totalCostQ,
    approximate: conversion?.kind === "approximate",
    suggestion: receiptLineSuggestion(line, materials),
    invoiceSummary: receiptInvoiceSummary(line),
    nextStep: receiptNextStep(warnings),
    nextStepIsOnField: receiptNextStepIsOnField(warnings),
    nextStepField: receiptNextStepField(warnings),
    needsExpiry: Boolean(matchedMaterial && matchedMaterial.shelfLifeDays !== null && !line.expiryDate),
    conversionSuggestion: receiptConversionSuggestion(line),
    invoiceAxes: receiptInvoiceAxes(line),
    conversionDiverges: receiptConversionDiverges(line, conversion),
    fiscalDivergences: receiptFiscalDivergences(line),
    warnings,
  };
}

export function materialTone(material: Material, issues: MaterialIssue[]): MaterialTone {
  if (!material.isActive) return "watch";
  if (issues.some((issue) => issue.tone === "urgent")) return "urgent";
  if (issues.length) return "watch";
  return "ok";
}

export function materialIssues(
  material: Material,
  costs: SupplierMaterialCost[],
  conversions: MaterialConversion[],
): MaterialIssue[] {
  const materialCosts = costs.filter((cost) => cost.materialSku === material.sku);
  const preferred = materialCosts.find((cost) => cost.isPreferred) ?? null;
  const activeConversions = conversions.filter(
    (conversion) => conversion.materialSku === material.sku && conversion.isActive,
  );
  const days = coverageDays(material);
  const issues: MaterialIssue[] = [];

  if (!material.isActive) {
    issues.push({ key: "inactive-material", label: "Inativo", tone: "watch" });
  }
  if (days <= replenishAtDays(material) || material.stockOnHand < material.minStock) {
    issues.push({ key: "low-stock", label: "Reposição", tone: "urgent" });
  }
  if (!preferred) {
    issues.push({ key: "missing-preferred", label: "Sem custo preferencial", tone: "watch" });
  }
  if (preferred && isApproximateCost(preferred, conversions)) {
    issues.push({ key: "approximate-cost", label: "Custo estimado", tone: "watch" });
  }
  if (material.stockIsApproximate) {
    issues.push({ key: "approximate-stock", label: "Saldo estimado", tone: "watch" });
  }
  if (!activeConversions.length && materialCosts.some((cost) => cost.conversionId)) {
    issues.push({ key: "no-conversion", label: "Conversão inativa", tone: "watch" });
  }

  return issues;
}

export function enrichMaterial(
  material: Material,
  costs: SupplierMaterialCost[],
  conversions: MaterialConversion[],
): EnrichedMaterial {
  const materialCosts = costs.filter((cost) => cost.materialSku === material.sku);
  const preferredCost = materialCosts.find((cost) => cost.isPreferred) ?? null;
  const issues = materialIssues(material, costs, conversions);
  return {
    ...material,
    coverageDays: coverageDays(material),
    preferredCost,
    preferredBaseCostQ: preferredCost ? costPerBaseUnitQ(preferredCost, conversions) : null,
    supplierCount: new Set(materialCosts.map((cost) => cost.supplierRef)).size,
    conversionCount: conversions.filter((conversion) => conversion.materialSku === material.sku && conversion.isActive).length,
    tone: materialTone(material, issues),
    issues,
  };
}

// Contagem aceita o teclado da casa ("1.250,5" ou "12,5") e o do sistema
// ("12.5"): vírgula presente decide a notação. Vazio = linha não contada.
export function parseQtyInput(value: string): number | null {
  const text = value.trim().replace(/\s/g, "");
  if (!text) return null;
  const normalized = text.includes(",") ? text.replace(/\./g, "").replace(",", ".") : text;
  const parsed = Number(normalized);
  if (!Number.isFinite(parsed) || parsed < 0) return null;
  return Math.round(parsed * 1000) / 1000;
}

export function countRow(item: CountItem, input: string, reason: string): CountRow {
  const counted = parseQtyInput(input);
  const diff = counted === null ? 0 : Math.round((counted - item.systemQty) * 1000) / 1000;
  const divergent = counted !== null && diff !== 0;
  return {
    item,
    input,
    reason,
    counted,
    diff,
    divergent,
    missingReason: divergent && !reason.trim(),
  };
}

export function countRows(
  items: CountItem[],
  inputs: Record<string, string>,
  reasons: Record<string, string>,
): CountRow[] {
  return items.map((item) => countRow(item, inputs[item.sku] ?? "", reasons[item.sku] ?? ""));
}

export function countSummary(rows: CountRow[]): CountSummary {
  const filled = rows.filter((row) => row.counted !== null);
  const divergent = filled.filter((row) => row.divergent);
  const missingReason = divergent.filter((row) => row.missingReason);
  return {
    filled: filled.length,
    divergent: divergent.length,
    missingReason: missingReason.length,
    ready: filled.length > 0 && missingReason.length === 0,
  };
}

export function countConfirmPayload(rows: CountRow[]) {
  return {
    counts: rows
      .filter((row) => row.counted !== null)
      .map((row) => ({
        materialSku: row.item.sku,
        countedQty: row.counted as number,
        reason: row.reason.trim(),
      })),
  };
}

export function formatQtyDiff(diff: number, unit: string): string {
  if (diff === 0) return "—";
  const sign = diff > 0 ? "+" : "−";
  return `${sign}${quantityFormatter.format(Math.abs(diff))} ${unit}`;
}

export function supplierCostRows(
  material: Material,
  costs: SupplierMaterialCost[],
  suppliers: Supplier[],
  conversions: MaterialConversion[],
): SupplierCostRow[] {
  const materialCosts = costs.filter((cost) => cost.materialSku === material.sku);
  const preferredBaseCost =
    materialCosts.find((cost) => cost.isPreferred) ?
      costPerBaseUnitQ(materialCosts.find((cost) => cost.isPreferred) as SupplierMaterialCost, conversions)
    : Math.min(...materialCosts.map((cost) => costPerBaseUnitQ(cost, conversions)), Number.POSITIVE_INFINITY);

  return materialCosts
    .map((cost) => {
      const supplier = suppliers.find((item) => item.ref === cost.supplierRef);
      if (!supplier) return null;
      const baseCostQ = costPerBaseUnitQ(cost, conversions);
      const deltaQ = Number.isFinite(preferredBaseCost) ? baseCostQ - preferredBaseCost : 0;
      const deltaPercent = preferredBaseCost ? Math.round((deltaQ * 1000) / preferredBaseCost) / 10 : 0;
      return {
        cost,
        supplier,
        conversion: conversionFor(cost, conversions),
        purchaseUnitLabel: purchaseUnitLabel(cost, material, conversions),
        baseCostQ,
        approximate: isApproximateCost(cost, conversions),
        deltaQ,
        deltaPercent,
      };
    })
    .filter((row): row is SupplierCostRow => Boolean(row))
    .sort((a, b) => a.baseCostQ - b.baseCostQ);
}

/**
 * A fila de compra — quem precisa ser reposto, quanto e de quem.
 *
 * **A quantidade é a do servidor.** `Material.suggestedQty` já é a resposta da
 * política de reposição (prazo do fornecedor + revisão + segurança, limitada
 * pela validade do insumo), calculada em `_suggested_qty` na projeção. A tela
 * mostra esse número; não o recalcula.
 *
 * Antes havia duas contas para a mesma pergunta: o servidor respondia uma coisa
 * e o painel refazia a conta com uma heurística própria
 * (`ceil(max(minStock*2, dailyUse*7) - stockOnHand)`, sobre um filtro próprio).
 * O resultado foi o painel anunciar "Comprar 8 · R$ 4.293,97" enquanto a tela
 * Comprar, com os mesmos dados, mostrava 0 e R$ 0,00 — e um painel que promete
 * oito e entrega zero queima a confiança no app inteiro. Uma pergunta, um dono.
 */
export function reorderRows(
  materials: Material[],
  suppliers: Supplier[],
  costs: SupplierMaterialCost[],
  conversions: MaterialConversion[],
): ReorderRow[] {
  return materials
    .filter((material) => (material.suggestedQty ?? 0) > 0)
    .map((material) => {
      const enriched = enrichMaterial(material, costs, conversions);
      const preferred = enriched.preferredCost;
      const supplier = preferred ? (suppliers.find((item) => item.ref === preferred.supplierRef) ?? null) : null;
      const suggestedQty = material.suggestedQty ?? 0;
      const estimatedCostQ =
        enriched.preferredBaseCostQ === null ? null : Math.round(enriched.preferredBaseCostQ * suggestedQty);
      return { material: enriched, supplier, suggestedQty, estimatedCostQ };
    })
    .sort((a, b) => a.material.coverageDays - b.material.coverageDays);
}

/**
 * A tabela de preços digitada vira o corpo do POST em lote.
 *
 * Só a linha com valor entra: a tela lista todos os insumos justamente para o
 * operador percorrer a lista e preencher o que sabe, e uma linha em branco é
 * omissão, não erro. O `makePreferred` é sempre verdadeiro porque o lote existe
 * para tornar o insumo comprável, e sem custo preferencial ele continua fora do
 * pedido.
 */
export function costBatchPayload(
  supplierRef: string,
  inputs: Record<string, string>,
  conversionIds: Record<string, string>,
  visibleSkus: string[],
): PurchaseCostBatchPayload {
  // Só vai o que está NA TELA. O filtro ("só os que faltam", a busca) esconde
  // linhas já preenchidas, e mandá-las assim mesmo quebra a promessa do lote:
  // como ele é tudo-ou-nada, uma linha escondida e inválida derruba tudo, e o
  // erro dela não tem onde aparecer — o operador lê "corrija as linhas
  // indicadas" com todas as linhas visíveis limpas.
  const visible = new Set(visibleSkus);
  const costs = Object.entries(inputs)
    .filter(([materialSku, value]) => visible.has(materialSku) && Boolean((value ?? "").trim()))
    .map(([materialSku, value]) => ({
      materialSku,
      costInput: value.trim(),
      conversionId: conversionIds[materialSku] || null,
    }));
  // `makePreferred` fica FALSE de propósito. O servidor já promove o primeiro
  // custo de um insumo (`prefer_if_missing`), que é o que destrava os insumos
  // sem custo preferencial — o objetivo do lote. Pedir a promoção explícita
  // repontaria o custo canônico (o que alimenta o custeio de receita) de
  // dezenas de insumos de uma vez, ao gesto de "atualizar a tabela do
  // fornecedor". Trocar o padrão é escolha de uma linha só, no formulário
  // avulso, onde ela tem botão próprio.
  return { supplierRef, makePreferred: false, costs };
}

/**
 * Traduz a recusa do lote em "qual linha errou, e por quê".
 *
 * O lote é tudo-ou-nada no servidor. Sem apontar a linha, a recusa manda o
 * operador procurar o erro entre dezenas de campos preenchidos — e o custo de
 * procurar é maior que o de digitar tudo de novo. O servidor manda os erros em
 * `error.lines` (o dialeto `errors` fala por campo, e linha não cabe ali);
 * aqui eles viram um mapa por SKU, que é como a tabela endereça suas linhas.
 */
export function costBatchLineErrors(data: unknown): Record<string, string> {
  const body = data as { error?: { lines?: unknown } } | null | undefined;
  const lines = body?.error?.lines;
  if (!Array.isArray(lines)) return {};
  const entries = lines
    .map((line) => line as { materialSku?: unknown; detail?: unknown })
    .filter((line) => typeof line?.materialSku === "string" && typeof line?.detail === "string")
    .map((line) => [line.materialSku as string, line.detail as string] as const);
  return Object.fromEntries(entries);
}

/**
 * O que impede a fila de compra de existir — vazio explicado, com o caminho.
 *
 * Um zero mudo é indistinguível de um app quebrado: o operador não sabe se não
 * precisa comprar nada ou se a conta não fecha por falta de cadastro. Os dois
 * estados pedem reações opostas, e só um deles tem conserto do lado dele.
 *
 * A ordem é a da causa: sem insumo não há o que medir; sem consumo medido não
 * há sugestão; sem custo preferencial a sugestão não vira pedido. Quando há
 * fila, não há o que explicar — a lista fala por si.
 */
export function reorderBlockers(materials: Material[], costs: SupplierMaterialCost[]): ReorderBlocker[] {
  if (materials.some((material) => (material.suggestedQty ?? 0) > 0)) return [];

  const active = materials.filter((material) => material.isActive);
  if (!active.length) {
    return [
      {
        key: "no-materials",
        headline: "Nenhum insumo ativo na base",
        detail: "Sem insumo cadastrado não há o que repor. Cadastre os insumos para o Compras ter o que calcular.",
        count: 0,
        action: { label: "Abrir Insumos", baseView: "materials" },
      },
    ];
  }

  const blockers: ReorderBlocker[] = [];

  // O consumo não é digitado: sai das baixas de estoque que a produção lança ao
  // FINALIZAR uma ficha (Move negativo, kind=MAKE). Enquanto o lote não for
  // fechado no sistema, o insumo tem consumo zero e o Compras não sugere nada.
  const semConsumo = active.filter((material) => material.dailyUse <= 0);
  if (semConsumo.length) {
    blockers.push({
      key: "no-consumption",
      headline: `${semConsumo.length} de ${active.length} insumos sem consumo medido`,
      detail:
        "A sugestão de reposição vem do consumo real, e o consumo é registrado quando um lote é finalizado na Produção. Sem lote fechado, não há quanto repor. Defina o estoque mínimo do insumo para comprar mesmo assim.",
      count: semConsumo.length,
      action: { label: "Abrir Insumos", baseView: "materials" },
    });
  }

  const preferidos = new Set(costs.filter((cost) => cost.isPreferred).map((cost) => cost.materialSku));
  const semCusto = active.filter((material) => !preferidos.has(material.sku));
  if (semCusto.length) {
    blockers.push({
      key: "no-preferred-cost",
      headline: `${semCusto.length} de ${active.length} insumos sem custo preferencial`,
      detail:
        "Só dá para enviar pedido de um insumo que tenha custo padrão e fornecedor definidos. Cadastre em Custos (dá para lançar vários de uma vez pelo mesmo fornecedor).",
      count: semCusto.length,
      action: { label: "Abrir Custos", baseView: "costs" },
    });
  }

  if (!blockers.length) {
    blockers.push({
      key: "stocked",
      headline: "Nenhum insumo abaixo do ponto de reposição",
      detail: "Todo insumo com consumo medido tem estoque para cobrir o prazo de entrega. Não há o que comprar agora.",
      count: 0,
      action: null,
    });
  }

  return blockers;
}

/**
 * Os selos do SKU, na ordem em que o operador pensa: de onde vem, para onde vai.
 *
 * Só aparece o que é verdade — selo ausente é "não é", e a tela não escreve
 * "Não vendável" em cada linha de farinha.
 */
export function skuRoleBadges(roles: SkuRoles | undefined): string[] {
  if (!roles) return [];
  const badges: string[] = [];
  if (roles.purchasable) badges.push("Comprável");
  if (roles.sellable) badges.push("Vendável");
  if (roles.produced) badges.push("Produzido");
  if (roles.usedInRecipe) badges.push("Usado em receita");
  return badges;
}

/**
 * A copy do "Permitir revenda" para um item — curta e sem ambiguidade.
 *
 * Vendido por peso (unidade kg) é só no balcão: o preço final nasce na balança,
 * e quem compra de longe não vê a peça. O resto entra no PDV e, com foto, na
 * loja online. Preço zero nunca vende: o gesto só fica pronto com preço > 0.
 */
export function resaleCopy(unit: string, priceInput: string) {
  const byWeight = unit === "kg";
  return {
    priceLabel: byWeight ? "Preço por kg (R$)" : `Preço de venda (R$ por ${unit})`,
    reach: byWeight ? "Vendido só no balcão, por peso." : "Entra no PDV. Na loja online, só com foto.",
    ready: parseMoneyInput(priceInput) > 0,
  };
}

/**
 * A sugestão de preço da revenda, pronta para o campo e para a explicação ao lado.
 *
 * `input` é o texto que o campo recebe ("42,00"), editável; `basis` diz de onde
 * o número saiu, para ninguém confirmar um preço sem saber por quê.
 */
export function resaleSuggestionView(suggestion: SaleSuggestion | null | undefined, unit: string) {
  if (!suggestion || suggestion.priceQ <= 0) return null;
  const category = suggestion.markupCategory ? `categoria ${suggestion.markupCategory}` : "padrão da loja";
  return {
    input: (suggestion.priceQ / 100).toFixed(2).replace(".", ","),
    basis: `custo ${formatMoney(suggestion.costQ)}/${unit} · markup ${suggestion.markupPct}% (${category})`,
  };
}

/** Unidades em que o aberto pode ser medido — o que se pesa ou se mede. */
export const OPENED_UNITS = ["kg", "g", "l", "ml"] as const;

/**
 * "Quando aberto, vira": só embalagem contada por unidade se abre, e o aberto é
 * um insumo pesado ou medido. Devolve as opções do seletor (sem a própria
 * embalagem) e o resumo do que já está declarado.
 */
export function openingView(material: Material, materials: Material[]) {
  const canOpen = material.unit === "un" && !material.roles?.produced;
  const options = materials
    .filter((item) => item.isActive && item.sku !== material.sku && (OPENED_UNITS as readonly string[]).includes(item.unit))
    .map((item) => ({ value: item.sku, label: `${item.name} (${item.unit})` }));
  const declared = material.opensInto;
  const summary =
    declared ?
      `Vira ${formatDecimalPtBr(declared.quantity)} ${declared.unit} de ${declared.name}` +
      (declared.shelfLifeDays !== null ? ` · depois de aberta, vale ${declared.shelfLifeDays} dias` : "")
    : "";
  return { canOpen, options, summary, suggestedQuantity: formatDecimalPtBr(material.netContentKg ?? "") };
}

function formatDecimalPtBr(value: string): string {
  return value ? value.replace(".", ",") : "";
}

// ── Recebimento por exceção (UX-C1) ──────────────────────────────────────────
//
// Decisão do dono (03/10/2026): "recebimento por exceção, sim; validade é
// incontornável". O que bate com a nota entra com UM ato físico, contar os
// volumes; a validade de perecível é pedida sempre; só o item que não bate pede
// atenção. As contas aqui são o espelho das do servidor
// (`services/purchase.py::receipt_expected_volumes` e `_line_matches_invoice`):
// a tela promete o que o servidor aceita, nem mais nem menos.

/** Os motivos de diferença, em lista curta. Gravam na ocorrência da linha. */
export const RECEIPT_DIFFERENCE_REASONS = ["Faltou", "Avariado", "Trocado", "Outro"] as const;

const MASS_UNITS = new Set(["mg", "g", "kg"]);
const VOLUME_UNITS = new Set(["ml", "l", "lt", "lts", "litro", "litros", "liter", "liters"]);
const MEASURE_UNITS = new Set([...MASS_UNITS, ...VOLUME_UNITS]);

/** As duas unidades são peso, ou as duas são volume: a física leva uma à outra. */
function sameMeasureDimension(first: string | undefined, second: string | undefined): boolean {
  const a = (first ?? "").trim().toLowerCase();
  const b = (second ?? "").trim().toLowerCase();
  return (MASS_UNITS.has(a) && MASS_UNITS.has(b)) || (VOLUME_UNITS.has(a) && VOLUME_UNITS.has(b));
}

function sameQty(a: number, b: number): boolean {
  return Math.abs(a - b) < 1e-9;
}

/** A nota × o que chegou; `null` quando a linha não veio de nota ou bate. */
export function receiptLineDifference(line: ReceiptLine): ReceiptLineDifference | null {
  const invoiceQty = line.invoicePurchaseQty;
  if (invoiceQty === null || invoiceQty === undefined || !(invoiceQty > 0)) return null;
  if (!Number.isFinite(line.purchaseQty) || sameQty(line.purchaseQty, invoiceQty)) return null;
  return { invoiceQty, arrivedQty: line.purchaseQty, difference: line.purchaseQty - invoiceQty };
}

/**
 * O que a diferença FAZ, escrito: entra o que chegou, e a falta fica anotada
 * para cobrar o fornecedor.
 */
export function receiptDifferenceConsequence(preview: ReceiptLinePreview): string {
  const difference = receiptLineDifference(preview.line);
  if (!difference) return "";
  const unit = preview.purchaseUnitLabel;
  const arrived = unit ? `${quantityFormatter.format(difference.arrivedQty)} × ${unit}` : quantityFormatter.format(difference.arrivedQty);
  return difference.difference < 0 ?
      `Entra ${arrived}. A falta fica anotada na entrada para cobrar o fornecedor.`
    : `Entra ${arrived}, mais do que a nota diz. Fica anotado na entrada.`;
}

/** A linha se conta em embalagens (caixa, saco, fardo, unidade)? Peso e volume não. */
export function receiptLineCountsInPackages(preview: ReceiptLinePreview): boolean {
  if (preview.conversion) return true;
  return !MEASURE_UNITS.has((preview.line.invoiceUnit ?? "").trim().toLowerCase());
}

/**
 * A linha bate com a nota: insumo resolvido, quantidade, valor e embalagem
 * iguais aos da nota, e nenhuma ocorrência. Validade NÃO entra aqui: é pedida
 * sempre, à parte.
 */
export function receiptLineMatchesInvoice(preview: ReceiptLinePreview, mode: ReceiptMode): boolean {
  if (mode !== "invoice") return false;
  const line = preview.line;
  if (preview.warnings.some((warning) => warning.tone === "block" && warning.key !== "missing-expiry")) return false;
  if (preview.conversionDiverges) return false;
  // A nota veio em peso ou volume que já alcança a base (o leitor converteu a
  // quantidade). Uma embalagem escolhida por cima multiplica de novo: isso não
  // bate com a nota, pede o ok da linha. O servidor recusa igual.
  if (preview.conversion && sameMeasureDimension(line.invoiceUnit, preview.material.unit)) return false;
  const invoiceQty = line.invoicePurchaseQty;
  if (invoiceQty === null || invoiceQty === undefined || !(invoiceQty > 0) || !sameQty(line.purchaseQty, invoiceQty)) {
    return false;
  }
  const invoiceTotal = parseMoneyInput(line.invoiceTotal ?? "");
  if (invoiceTotal <= 0 || parseMoneyInput(line.costInput) !== invoiceTotal) return false;
  return !line.lineNote.trim();
}

/**
 * Quantos volumes devem estar na doca, dado o que chegou.
 *
 * Base: os volumes que a nota declara; sem eles, a soma das embalagens, desde
 * que todas as linhas se contem em embalagens. Ajuste: a diferença das linhas
 * de embalagem (a caixa que faltou some da conta). `null` = não há o que contar.
 */
export function receiptExpectedVolumes(previews: ReceiptLinePreview[], declared: number): number | null {
  let base: number;
  if (declared > 0) {
    base = declared;
  } else if (
    previews.length &&
    previews.every((preview) => receiptLineCountsInPackages(preview) && (preview.line.invoicePurchaseQty ?? 0) > 0)
  ) {
    base = previews.reduce((total, preview) => total + (preview.line.invoicePurchaseQty ?? 0), 0);
  } else {
    return null;
  }
  const adjust = previews
    .filter(receiptLineCountsInPackages)
    .reduce((total, preview) => total + (receiptLineDifference(preview.line)?.difference ?? 0), 0);
  const expected = base + adjust;
  const rounded = Math.round(expected);
  if (expected <= 0 || !sameQty(expected, rounded)) return null;
  return rounded;
}

/** Os atalhos de validade: a da última entrega (se ainda vale) e a típica do insumo. */
export function receiptExpiryShortcuts(material: Material, today: string): ReceiptExpiryShortcut[] {
  const caption = (date: string) => `${shortDayMonth(date)} · ${weekdayShort(date)}`;
  const shortcuts: ReceiptExpiryShortcut[] = [];
  const last = material.lastDeliveryExpiry ?? "";
  if (last && last >= today) {
    shortcuts.push({ key: "last", label: "Mesma da última entrega", date: last, caption: caption(last) });
  }
  const days = material.shelfLifeDays ?? 0;
  if (days > 0) {
    const date = addDays(today, days);
    if (date !== last) {
      shortcuts.push({
        key: "typical",
        label: `Típica: +${days} ${days === 1 ? "dia" : "dias"}`,
        date,
        caption: caption(date),
      });
    }
  }
  return shortcuts;
}

/**
 * Quantos itens estão prontos para entrar, e o que ainda falta, numa frase.
 *
 * Era "3 de 3 conferidos" com os três itens em "Pendente": a contagem de
 * volumes assina a QUANTIDADE, mas a validade continua incontornável, e o selo
 * do `Confirmar entrada` dizia o contrário do cabeçalho. Agora pronto é o que
 * entra se confirmar agora: assinado (ok da linha, ou batendo com a nota com os
 * volumes contados) e sem bloqueio nenhum.
 */
export function receiptConferenceTally(
  previews: ReceiptLinePreview[],
  matchedIds: ReadonlySet<string>,
  countOk: boolean,
): ReceiptConferenceTally {
  const total = previews.length;
  const ready = previews.filter(
    (preview) =>
      (preview.line.checked || (countOk && matchedIds.has(preview.line.id))) &&
      !preview.warnings.some((warning) => warning.tone === "block"),
  ).length;
  const missingExpiry = previews.filter((preview) => preview.needsExpiry).length;
  const parts = [`${ready} de ${total} prontos para entrar`];
  if (missingExpiry > 0) parts.push(`falta a validade de ${missingExpiry}`);
  return { total, ready, missingExpiry, label: total ? parts.join(" · ") : "Nenhum item ainda" };
}

/** A conferência por exceção da entrada: o que bate, o que não bate, e o passo da vez. */
export function receiptExceptionView(
  previews: ReceiptLinePreview[],
  mode: ReceiptMode,
  declaredVolumes: number,
  countedVolumes: number | null,
): ReceiptExceptionView {
  const matched = previews.filter((preview) => receiptLineMatchesInvoice(preview, mode));
  const exceptions = previews.filter((preview) => !matched.includes(preview));
  const expectedVolumes = mode === "invoice" ? receiptExpectedVolumes(previews, declaredVolumes) : null;
  const available = expectedVolumes !== null && matched.length > 0;
  const countOk = available && countedVolumes !== null && countedVolumes === expectedVolumes;
  const perishables = previews.filter((preview) => preview.material.shelfLifeDays !== null && Boolean(preview.line.materialSku));
  const expiryDone = perishables.filter((preview) => Boolean(preview.line.expiryDate)).length;
  const nextExpiry = perishables.find((preview) => !preview.line.expiryDate) ?? null;
  const unresolved = exceptions.some(
    (preview) => !preview.line.checked || preview.warnings.some((warning) => warning.tone === "block" && warning.key !== "missing-expiry"),
  );
  const step: ReceiptExceptionView["step"] =
    available && !countOk ? "count"
    : nextExpiry ? "expiry"
    : unresolved ? "exceptions"
    : "done";
  return { available, expectedVolumes, countedVolumes, countOk, matched, exceptions, perishables, expiryDone, nextExpiry, step };
}

/** A frase do que falta na contagem, ou vazio quando não falta (ou não se aplica). */
export function receiptVolumesStep(view: ReceiptExceptionView): string {
  if (!view.available || view.countOk) return "";
  if (view.countedVolumes === null) return "Contar os volumes da entrega";
  return `Contou ${view.countedVolumes} de ${view.expectedVolumes}: ache o item que não bate`;
}
