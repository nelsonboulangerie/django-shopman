// Presentation — as seções da Produção no shell da suíte (`OperatorSuiteShell`). Puro:
// quem decide se o operador vê Receitas ou Relatórios é o servidor (as sondas de
// acesso); aqui só se monta a lista.
//
// O modelo de navegação (dono, 31/10/2026) agrupa os lugares pela forma da tela, e a
// forma nunca vira palavra na tela:
//   · chão (a bancada, de pé, com a mão na massa): a Bancada, os Timers e a Qualidade
//     (o gerente confere os lotes pelo celular). Sem barra de seções no celular: trocar
//     de lugar é pelo selo, e é raro;
//   · escritório (o gerente ou o dono, no computador): o Plano, as Receitas e os
//     Relatórios, com a barra de baixo no celular;
//   · parede: o Letreiro, a TV sem quem toque.
// Preparo, Produção e Finalização são etapas do MESMO trabalho, e quem está na bancada
// passa de uma para outra o dia todo: viram recorte na própria tela (`BENCH_CUTS`, as
// abas do topo), a um toque, em vez de três seções a dois toques pelo selo.
// Alt+1 a Alt+7 seguem a ordem da lista (regra do kit, `withSectionShortcuts`).
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";

export interface ProductionSectionsInput {
  /** Timers ativos neste dispositivo (o servidor não os conhece). */
  timersActive?: number;
  /** Timers tocando agora: vira o ponto de atenção do item Timers. */
  timersRinging?: number;
  /** Lotes fechados esperando a revisão da Qualidade (só quando a tela sabe). */
  qualityPending?: number;
  canViewRecipes?: boolean;
  canViewReports?: boolean;
}

export type BenchCut = "mise-en-place" | "open" | "close";

/** As etapas da Bancada, na ordem do dia: as abas do topo das três telas. */
export const BENCH_CUTS: readonly { key: BenchCut; label: string; to: string }[] = [
  { key: "mise-en-place", label: "Preparo", to: "/mise-en-place" },
  { key: "open", label: "Produção", to: "/" },
  { key: "close", label: "Finalização", to: "/close" },
];

export function benchSection(): OperatorSection {
  return {
    key: "bench",
    label: "Bancada",
    icon: "lucide:flame",
    to: "/",
    match: ["/mise-en-place", "/close"],
    form: "floor",
  };
}

export function timersSection({ timersActive = 0, timersRinging = 0 }: ProductionSectionsInput = {}): OperatorSection {
  return {
    key: "timers",
    label: "Timers",
    icon: "lucide:alarm-clock",
    to: "/timers",
    form: "floor",
    ...(timersActive ? { badge: String(timersActive) } : {}),
    ...(timersRinging ? { attention: `${timersRinging} tocando` } : {}),
  };
}

export function qualitySection({ qualityPending }: ProductionSectionsInput = {}): OperatorSection {
  return {
    key: "quality",
    label: "Qualidade",
    icon: "lucide:badge-check",
    to: "/quality",
    form: "floor",
    ...(qualityPending ? { badge: String(qualityPending) } : {}),
  };
}

/** O que se decide sentado: o Plano e as ferramentas que dependem de acesso. */
export function officeSections({ canViewRecipes = false, canViewReports = false }: ProductionSectionsInput = {}): OperatorSection[] {
  const office: OperatorSection[] = [
    { key: "plan", label: "Planejamento", shortLabel: "Plano", icon: "lucide:layout-grid", to: "/plan", form: "office", divider: true },
  ];
  if (canViewRecipes) office.push({ key: "recipes", label: "Receitas", icon: "lucide:book-open", to: "/recipes", form: "office" });
  if (canViewReports) office.push({ key: "reports", label: "Relatórios", icon: "lucide:table-2", to: "/reports", form: "office" });
  return office;
}

/**
 * A bancada, um traço, o escritório e o Letreiro. O pé da barra lateral é o da suíte
 * (Avisos, Atalhos, Bloquear, o operador).
 */
export function productionSections(input: ProductionSectionsInput = {}): OperatorSection[] {
  return [
    benchSection(),
    timersSection(input),
    qualitySection(input),
    ...officeSections(input),
    { key: "board", label: "Letreiro", icon: "lucide:tower-control", to: "/board", form: "wall" },
  ];
}
