// Presentation — as seções da Produção no shell da suíte (`OperatorSuiteShell`). Puro:
// quem decide se o operador vê Receitas ou Relatórios é o servidor (as sondas de
// acesso); aqui só se monta a lista.
//
// Em cima o ciclo do lote (Alt+1 a Alt+5, decisão #1433: Planejamento · Preparação ·
// Produção · Finalização · Qualidade), e logo abaixo os Timers da bancada, com a
// contagem de ativos no selo e o ponto quando um toca. Receitas, Relatórios e Letreiro
// têm destinos diretos, e o pé da barra lateral é o da suíte.
//
// O modelo de navegação (dono, 31/10/2026) dá a cada seção a forma da tela, que nunca
// vira palavra na tela:
//   · chão (de pé, com a mão na massa): Preparação, Produção, Finalização, Qualidade (o
//     gerente confere pelo celular) e Timers. No celular é a barra de baixo, as cinco,
//     porque a Produção troca de etapa o dia todo (dono, 03/11/2026: seção vai para
//     baixo; aba no topo é subdivisão da seção);
//   · escritório (o gerente ou o dono, no computador): Planejamento, Receitas, Relatórios;
//   · parede: o Letreiro, a TV sem quem toque.
// Na barra de baixo, Preparação aparece como "Preparo": o nome cheio não cabe em 1/5 de
// um celular de 320px. O nome acessível é o cheio.
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";

export interface ProductionSectionsInput {
  /** Dia consultado na grade: acompanha a navegação, sem fixar a URL do tablet. */
  date?: string;
  /** Timers ativos neste dispositivo (o servidor não os conhece). */
  timersActive?: number;
  /** Timers tocando agora: vira o ponto de atenção do item Timers. */
  timersRinging?: number;
  /** Lotes fechados esperando a revisão da Qualidade (só quando a tela sabe). */
  qualityPending?: number;
  canViewRecipes?: boolean;
  canViewReports?: boolean;
}

/** O ciclo do lote, na ordem do dia, com as teclas Alt+1 a Alt+5. */
export const PRODUCTION_STAGES: readonly OperatorSection[] = [
  { key: "plan", label: "Planejamento", shortLabel: "Plano", icon: "lucide:layout-grid", to: "/plan", shortcut: "Alt+1", form: "office" },
  { key: "mise-en-place", label: "Preparação", shortLabel: "Preparo", icon: "lucide:scale", to: "/mise-en-place", shortcut: "Alt+2", form: "floor", quick: true },
  { key: "open", label: "Produção", icon: "lucide:flame", to: "/", shortcut: "Alt+3", form: "floor", quick: true },
  { key: "close", label: "Finalização", icon: "lucide:package-check", to: "/close", shortcut: "Alt+4", form: "floor", quick: true },
  { key: "quality", label: "Qualidade", icon: "lucide:badge-check", to: "/quality", shortcut: "Alt+5", form: "floor", quick: true },
];

export function stageSections({ qualityPending, date }: ProductionSectionsInput = {}): OperatorSection[] {
  return PRODUCTION_STAGES.map((stage) => {
    const to = stage.key === "plan" && date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? `${stage.to}?date=${date}` : stage.to;
    if (stage.key !== "quality" || !qualityPending) return { ...stage, to };
    return {
      ...stage,
      to,
      badge: String(qualityPending),
    };
  });
}

export function timersSection({ timersActive = 0, timersRinging = 0 }: ProductionSectionsInput = {}): OperatorSection {
  return {
    key: "timers",
    label: "Timers",
    icon: "lucide:alarm-clock",
    to: "/timers",
    form: "floor",
    quick: true,
    ...(timersActive ? { badge: String(timersActive) } : {}),
    ...(timersRinging ? { attention: `${timersRinging} tocando` } : {}),
  };
}

/** Ferramentas que não são etapas do fluxo, cada uma com destino direto. */
export function toolSections({ canViewRecipes = false, canViewReports = false }: ProductionSectionsInput = {}): OperatorSection[] {
  const tools: OperatorSection[] = [];
  if (canViewRecipes) tools.push({ key: "recipes", label: "Receitas", icon: "lucide:book-open", to: "/recipes", form: "office" });
  if (canViewReports) tools.push({ key: "reports", label: "Relatórios", icon: "lucide:table-2", to: "/reports", form: "office" });
  tools.push({ key: "board", label: "Letreiro", icon: "lucide:tower-control", to: "/board", form: "wall" });
  return tools;
}

/**
 * O ciclo, um traço, Timers e as ferramentas diretas. O pé da barra lateral é o da
 * suíte (Avisos, Atalhos, Bloquear, o operador).
 */
export function productionSections(input: ProductionSectionsInput = {}): OperatorSection[] {
  return [...stageSections(input), { ...timersSection(input), divider: true }, ...toolSections(input)];
}
