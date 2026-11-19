// A agenda com cobertura como o servidor a manda (WP-G10). As frases são as de
// `shopman/backstage/projections/preorder_coverage.py` e dos exemplos de
// `shopman/backstage/tests/test_preorder_coverage.py`: o teste da tela não inventa frase.
import type {
  PreorderCoverageDayProjection,
  PreorderCoverageProductProjection,
} from "../../app/types/orders";

export function product(
  over: Partial<PreorderCoverageProductProjection> = {},
): PreorderCoverageProductProjection {
  return {
    sku: "BAGUETE",
    name: "Baguete de tradição",
    unit: "un",
    state: "short",
    state_label: "Lote não cobre",
    promised_qty: "16",
    promised_display: "16x",
    planned_qty: "10",
    planned_display: "10x",
    missing_qty: "6",
    surplus_qty: "0",
    label: "Faltam 6 Baguete de tradição",
    detail: "As encomendas somam 16x e os lotes, 10x.",
    orders_count: 2,
    batch_count: 1,
    ...over,
  };
}

export const noBatch = (
  over: Partial<PreorderCoverageProductProjection> = {},
) =>
  product({
    sku: "CIABATTA",
    name: "Ciabatta",
    state: "no_batch",
    state_label: "Sem lote",
    promised_qty: "8",
    promised_display: "8x",
    planned_qty: "0",
    planned_display: "0x",
    missing_qty: "8",
    label: "Sem lote para Ciabatta",
    detail: "Nenhum lote planejado para o dia.",
    batch_count: 0,
    ...over,
  });

export const covered = (
  over: Partial<PreorderCoverageProductProjection> = {},
) =>
  product({
    sku: "CAMPAGNE",
    name: "Pain de campagne",
    state: "covered",
    state_label: "Lote cobre",
    promised_qty: "4",
    promised_display: "4x",
    planned_qty: "12",
    planned_display: "12x",
    missing_qty: "0",
    surplus_qty: "8",
    label: "",
    detail: "As encomendas somam 4x e os lotes, 12x.",
    ...over,
  });

export const madeToOrder = (
  over: Partial<PreorderCoverageProductProjection> = {},
) =>
  product({
    sku: "CAFE",
    name: "Café coado",
    state: "made_to_order",
    state_label: "Feito na hora",
    promised_qty: "3",
    promised_display: "3x",
    planned_qty: "",
    planned_display: "",
    missing_qty: "",
    surplus_qty: "",
    label: "",
    detail: "Feito na hora: não depende de lote.",
    batch_count: 0,
    ...over,
  });

export const fromStock = (
  over: Partial<PreorderCoverageProductProjection> = {},
) =>
  product({
    sku: "GELEIA",
    name: "Geleia de morango",
    state: "from_stock",
    state_label: "Do estoque",
    promised_qty: "2",
    promised_display: "2x",
    planned_qty: "",
    planned_display: "",
    missing_qty: "",
    surplus_qty: "",
    label: "",
    detail: "Sai do estoque: a casa não produz este item.",
    batch_count: 0,
    ...over,
  });

/** Um dia em que falta: sábado, daqui a três dias, com um produto de cada estado. */
export function day(
  over: Partial<PreorderCoverageDayProjection> = {},
): PreorderCoverageDayProjection {
  return {
    date: "2026-11-21",
    day_label: "sáb, 21/11",
    days_ahead: 3,
    state: "short",
    state_label: "Produção não cobre",
    headline: "Faltam 6 Baguete de tradição. Sem lote para Ciabatta.",
    orders_count: 3,
    products: [product(), noBatch(), covered(), madeToOrder(), fromStock()],
    production_url: "https://producao.exemplo/plan?date=2026-11-21",
    production_label: "Abrir a Produção",
    ...over,
  };
}

export const coveredDay = (
  over: Partial<PreorderCoverageDayProjection> = {},
) =>
  day({
    date: "2026-11-19",
    day_label: "amanhã",
    days_ahead: 1,
    state: "covered",
    state_label: "Produção cobre",
    headline: "A produção cobre as encomendas.",
    products: [covered(), madeToOrder()],
    production_url: "https://producao.exemplo/plan?date=2026-11-19",
    ...over,
  });
