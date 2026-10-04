// Presentation — as seções da Produção no rail da suíte (V4-PROD). Puro: quem decide
// se o operador vê Receitas ou Relatórios é o servidor (as sondas de acesso); aqui só
// se monta a lista.
//
// Desenho da prévia v4 (`plano-porque4.html`, `producao-qualidade4.html`): em cima o
// ciclo do lote, com a tecla impressa sob o nome (Alt1 a Alt5, decisão #1433:
// Planejamento · Preparação · Abertura · Fechamento · Qualidade), e logo abaixo os
// Timers da bancada, com a contagem de ativos no selo e o ponto quando um toca. No pé,
// longe do ciclo, o que não é etapa: Receitas (o inventário da casa), Relatórios (o
// gestor) e o Letreiro (o kiosk de TV, tela cheia). No celular a barra do polegar leva
// só o ciclo (`phoneSections`); Timers sobe para o cabeçalho e o resto vai para o ⋯.
// Na barra do polegar, Planejamento e Preparação aparecem como "Plano" e "Preparo"
// (as prévias v4 do celular e da Qualidade): os cinco nomes cheios não cabem em 1/5 de
// um celular de 320px. O nome acessível continua o cheio.
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

/** O ciclo do lote, na ordem do dia, com as teclas Alt+1 a Alt+5. */
export const PRODUCTION_STAGES: readonly OperatorSection[] = [
  { key: "plan", label: "Planejamento", shortLabel: "Plano", icon: "lucide:layout-grid", to: "/plan", shortcut: "Alt+1" },
  { key: "mise-en-place", label: "Preparação", shortLabel: "Preparo", icon: "lucide:scale", to: "/mise-en-place", shortcut: "Alt+2" },
  { key: "open", label: "Abertura", icon: "lucide:flame", to: "/", shortcut: "Alt+3" },
  { key: "close", label: "Fechamento", icon: "lucide:package-check", to: "/close", shortcut: "Alt+4" },
  { key: "quality", label: "Qualidade", icon: "lucide:badge-check", to: "/quality", shortcut: "Alt+5" },
];

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

export function stageSections({ qualityPending }: ProductionSectionsInput = {}): OperatorSection[] {
  return PRODUCTION_STAGES.map((stage) => {
    if (stage.key !== "quality" || !qualityPending) return { ...stage };
    return {
      ...stage,
      badge: String(qualityPending),
      badgeLabel: plural(qualityPending, "lote para confirmar", "lotes para confirmar"),
    };
  });
}

export function timersSection({ timersActive = 0, timersRinging = 0 }: ProductionSectionsInput = {}): OperatorSection {
  return {
    key: "timers",
    label: "Timers",
    icon: "lucide:alarm-clock",
    to: "/timers",
    ...(timersActive ? { badge: String(timersActive), badgeLabel: plural(timersActive, "timer ativo", "timers ativos") } : {}),
    ...(timersRinging ? { attention: `${timersRinging} tocando` } : {}),
  };
}

/** O que não é etapa do fluxo: no pé do rail (e no ⋯ do celular). */
export function toolSections({ canViewRecipes = false, canViewReports = false }: ProductionSectionsInput = {}): OperatorSection[] {
  const tools: OperatorSection[] = [];
  if (canViewRecipes) tools.push({ key: "recipes", label: "Receitas", icon: "lucide:book-open", to: "/recipes", foot: true });
  if (canViewReports) tools.push({ key: "reports", label: "Relatórios", icon: "lucide:table-2", to: "/reports", foot: true });
  tools.push({ key: "board", label: "Letreiro", icon: "lucide:tower-control", to: "/board", foot: true });
  return tools;
}

/** Rail (tablet e desktop): ciclo, Timers e, no pé, as ferramentas. */
export function productionSections(input: ProductionSectionsInput = {}): OperatorSection[] {
  return [...stageSections(input), timersSection(input), ...toolSections(input)];
}

/** Barra do polegar (celular): só o ciclo, cinco alvos largos. */
export function phoneSections(input: ProductionSectionsInput = {}): OperatorSection[] {
  return stageSections(input);
}
