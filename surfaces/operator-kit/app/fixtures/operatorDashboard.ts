import type {
  ReadingChartPoint,
  ReadingChartSeries,
  ReadingDivergingLabels,
} from "../presentation/readingChart";

// Turno fixo: não usa relógio, dados vivos, imagens externas ou aleatoriedade.
export const dashboardTrend: ReadingChartPoint[] = [
  { label: "09h", values: { orders: 12 } },
  { label: "10h", values: { orders: 18 } },
  { label: "11h", values: { orders: 25 } },
  { label: "12h", values: { orders: 31 } },
  { label: "13h", values: { orders: 23 } },
  { label: "14h", values: { orders: 16 } },
];
export const dashboardTrendSeries: ReadingChartSeries[] = [
  { key: "orders", label: "Pedidos confirmados" },
];
// Faturamento da semana contra a anterior (barras e o traço tracejado da comparação).
// Quarta sem registro na semana anterior: ponto sem dado, nunca zero.
export const dashboardRevenue: ReadingChartPoint[] = [
  { label: "Seg 05/10", values: { current: 3180, previous: 2950 } },
  { label: "Ter 06/10", values: { current: 2840, previous: 3020 } },
  { label: "Qua 07/10", values: { current: 3310, previous: null } },
  { label: "Qui 08/10", values: { current: 3560, previous: 3270 } },
  { label: "Sex 09/10", values: { current: 4720, previous: 4410 } },
  { label: "Sáb 10/10", values: { current: 5980, previous: 5640 } },
  { label: "Dom 11/10", values: { current: 4130, previous: 4300 } },
];
export const dashboardRevenueSeries: ReadingChartSeries[] = [
  { key: "current", label: "Esta semana" },
  { key: "previous", label: "Semana anterior" },
];
// Sobrou (acima de zero) ou faltou (abaixo) por produto, em unidades.
export const dashboardOverShort: ReadingChartPoint[] = [
  { label: "Croissant", values: { difference: 6 } },
  { label: "Pão de fermentação natural", values: { difference: -4 } },
  { label: "Baguete", values: { difference: 0 } },
  { label: "Pain au chocolat", values: { difference: 3 } },
  { label: "Brioche", values: { difference: -2 } },
];
export const dashboardOverShortSeries: ReadingChartSeries[] = [
  { key: "difference", label: "Sobra ou falta" },
];
export const dashboardOverShortLabels: ReadingDivergingLabels = {
  positive: "Sobrou",
  negative: "Faltou",
  zero: "Vendeu o que fez",
  positiveTone: "warning",
  negativeTone: "error",
};
export const dashboardTeam = [
  { name: "Ana Ferreira", role: "Caixa", initials: "AF", status: "Ativa" },
  { name: "João Santos", role: "Produção", initials: "JS", status: "Ativo" },
  {
    name: "Maria Oliveira",
    role: "Retirada",
    initials: "MO",
    status: "Em pausa",
  },
];
export const dashboardTabs = [
  {
    label: "Resumo",
    value: "overview",
    slot: "overview",
    icon: "i-lucide-chart-no-axes-combined",
  },
  {
    label: "Fila",
    value: "queue",
    slot: "queue",
    icon: "i-lucide-list-checks",
    badge: 3,
  },
  {
    label: "Equipe",
    value: "team",
    slot: "team",
    icon: "i-lucide-users",
    badge: 3,
  },
];
export const dashboardSegments = [
  { label: "Prontos", value: 18, color: "success" as const },
  { label: "Em preparo", value: 4, color: "info" as const },
  { label: "Aguardando", value: 2, color: "warning" as const },
];
