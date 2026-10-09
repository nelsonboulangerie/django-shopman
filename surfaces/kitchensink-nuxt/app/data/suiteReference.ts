// Fixtures da página "Shell da suíte" (`/suite`) do Kitchen Sink: o shell de referência
// dos apps de operador (`OperatorSuiteShell`) com as peças da fase 2 do kit
// (docs/plans/WP-FASE2-UX-OPERADOR.md). Dados fixos: nada aqui fala com o Django.
import type { OperatorSwipeAction, OperatorSwipeCommit } from "../../../operator-kit/app/components/OperatorSwipeRow.vue";
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";
import type { ReadingChartPoint, ReadingChartSeries } from "../../../operator-kit/app/presentation/readingChart";
import type { OperatorScreenAlert } from "../../../operator-kit/app/presentation/screenState";

/**
 * As seções do shell de exemplo: quatro na barra inferior do celular e "Mais" (porque
 * sobra seção), um número (Fila) e um ponto (Cozinha) de sinal, uma seção no pé.
 */
export const SUITE_SECTIONS: OperatorSection[] = [
  { key: "pieces", label: "Peças", icon: "lucide:layout-template", to: "/suite", quick: true },
  { key: "queue", label: "Fila", icon: "lucide:list-checks", badge: "3", quick: true },
  { key: "kitchen", label: "Cozinha", icon: "lucide:chef-hat", attention: "1 atrasado", tone: "warning", quick: true },
  { key: "catalog", label: "Catálogo do kit", shortLabel: "Catálogo", icon: "lucide:flask-conical", to: "/", quick: true },
  { key: "reports", label: "Relatórios", icon: "lucide:chart-column" },
  { key: "settings", label: "Ajustes", icon: "lucide:settings", foot: true },
];

/** Os cenários do aviso da tela: nenhum, um, e três (um inteiro, o resto em "e mais N"). */
export type SuiteAlertScenario = "none" | "one" | "three";

export const SUITE_ALERT_SCENARIOS: { label: string; value: SuiteAlertScenario }[] = [
  { label: "Sem aviso", value: "none" },
  { label: "Um aviso", value: "one" },
  { label: "Três avisos", value: "three" },
];

/** Cada aviso leva aonde se resolve (a saída repete a cor do aviso). */
export function suiteAlerts(scenario: SuiteAlertScenario, go: (where: string) => void): OperatorScreenAlert[] {
  const all: OperatorScreenAlert[] = [
    {
      id: "late",
      color: "warning",
      title: "2 pedidos passaram do horário",
      description: "O 1049 e o 1053 já deveriam ter saído.",
      action: { label: "Ver os atrasados", onSelect: () => go("Ver os atrasados") },
    },
    {
      id: "vocation",
      color: "info",
      title: "33 produtos sem vocação",
      description: "Sem vocação, o produto não entra na sugestão de produção.",
      action: { label: "Dar vocação", onSelect: () => go("Dar vocação") },
    },
    {
      id: "fiscal",
      color: "error",
      title: "A nota do pedido 1046 foi recusada",
      description: "A Sefaz recusou o CPF informado.",
      action: { label: "Corrigir o CPF", onSelect: () => go("Corrigir o CPF") },
    },
  ];
  if (scenario === "none") return [];
  return scenario === "one" ? all.slice(0, 1) : all;
}

export interface SuiteSwipeRow {
  ref: string;
  customer: string;
  detail: string;
  actions: OperatorSwipeAction[];
  commit: OperatorSwipeCommit | null;
}

/**
 * Deslizar (`OperatorSwipeRow`), um estado por linha: as duas direções, só a gaveta, e a
 * gaveta com uma ação que não pode. No desktop o mouse não desliza: as mesmas ações
 * moram no ⋯ de cada linha.
 */
export const SUITE_SWIPE_ROWS: SuiteSwipeRow[] = [
  {
    ref: "U13",
    customer: "Ana Souza",
    detail: "Retirada · pronto há 4 min",
    actions: [
      { key: "assign", label: "Atender", icon: "lucide:user-plus", tone: "info" },
      { key: "reject", label: "Recusar", icon: "lucide:x", tone: "danger" },
    ],
    commit: { label: "Entregar U13 a Ana", icon: "lucide:hand-helping" },
  },
  {
    ref: "M09",
    customer: "Bruno Lima",
    detail: "Entrega · aguardando o entregador",
    actions: [{ key: "assign", label: "Atender", icon: "lucide:user-plus", tone: "info" }],
    commit: null,
  },
  {
    ref: "K21",
    customer: "Carla Dias",
    detail: "Retirada · pago no Pix",
    actions: [
      { key: "assign", label: "Atender", icon: "lucide:user-plus", tone: "info" },
      { key: "reject", label: "Recusar", icon: "lucide:x", tone: "danger", disabled: true },
    ],
    commit: { label: "Entregar K21 a Carla", icon: "lucide:hand-helping" },
  },
];

/** O gráfico empilhado do B.I. ("Fez × vendeu"): vendeu e sobrou são partes do que se fez. */
export const MADE_SOLD_SERIES: ReadingChartSeries[] = [
  { key: "sold", label: "Vendeu", tone: "primary" },
  { key: "left", label: "Sobrou", tone: "warning", fill: "tint" },
];

export const MADE_SOLD_POINTS: ReadingChartPoint[] = [
  { label: "Pão francês", values: { sold: 182, left: 18 } },
  { label: "Croissant de manteiga", values: { sold: 64, left: 6 } },
  { label: "Pão de fermentação natural de 36 horas", values: { sold: 22, left: 4 } },
  { label: "Brioche", values: { sold: 30, left: 0 } },
  { label: "Baguete", values: { sold: 41, left: 9 } },
];

export const HOURLY_SERIES: ReadingChartSeries[] = [
  { key: "counter", label: "Balcão", tone: "primary" },
  { key: "delivery", label: "Entrega", tone: "info" },
];

export const HOURLY_POINTS: ReadingChartPoint[] = [
  { label: "8h", values: { counter: 264, delivery: 60 } },
  { label: "9h", values: { counter: 372, delivery: 105 } },
  { label: "10h", values: { counter: 216, delivery: 135 } },
  { label: "11h", values: { counter: 168, delivery: 180 } },
  { label: "12h", values: { counter: 312, delivery: 225 } },
  { label: "13h", values: { counter: 228, delivery: 120 } },
];
