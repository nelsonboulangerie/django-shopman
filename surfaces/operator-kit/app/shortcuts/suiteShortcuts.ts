import type { OperatorShortcutCommand } from "../types/operatorShortcut";
import { defineOperatorShortcutMap } from "../utils/operatorShortcuts";

const shared = {
  scope: "suite" as const,
  owner: "operator-kit",
  enabledContexts: ["ready"] as const,
  forbiddenContexts: ["locked"] as const,
};

export const SUITE_SEARCH_SHORTCUTS = defineOperatorShortcutMap([
  {
    ...shared,
    id: "suite.search.slash",
    label: "Buscar na suíte",
    combinations: [{ code: "Slash" }],
    alternative: "Botão Buscar no cabeçalho",
  },
  {
    ...shared,
    id: "suite.search.mod-k",
    label: "Buscar na suíte",
    combinations: [
      { code: "KeyK", control: true, platform: "windows" },
      { code: "KeyK", meta: true, platform: "macos" },
    ],
    alternative: "Botão Buscar no cabeçalho",
    allowInEditable: true,
  },
] satisfies readonly OperatorShortcutCommand[]);

export const SUITE_HELP_SHORTCUT = defineOperatorShortcutMap([
  {
    ...shared,
    id: "suite.shortcuts-help",
    label: "Abrir ajuda de atalhos",
    combinations: [{ code: "Slash", shift: true }],
    alternative: "Item Atalhos na barra lateral ou no menu",
  },
] satisfies readonly OperatorShortcutCommand[]);

export const SUITE_SECTION_SHORTCUTS = defineOperatorShortcutMap(
  Array.from({ length: 9 }, (_, index) => ({
    ...shared,
    id: `suite.section.${index + 1}`,
    label: `Abrir seção ${index + 1}`,
    combinations: [{ code: `Digit${index + 1}`, alt: true }],
    alternative: "Item nomeado na barra lateral ou na barra inferior",
  })) satisfies readonly OperatorShortcutCommand[],
);

export const SUITE_RAIL_SHORTCUT = defineOperatorShortcutMap([
  {
    ...shared,
    id: "suite.rail.cycle",
    label: "Barra lateral: aberta, compacta ou oculta",
    combinations: [{ code: "KeyC" }],
    alternative: "Botão da barra lateral na barra do topo",
  },
] satisfies readonly OperatorShortcutCommand[]);

// Anterior e próximo dentro da lista de origem (`OperatorRecordNav`). J/K como nas
// listas com teclado; ←/→ para quem não conhece o J/K. As setas cedem a vez a quem já
// anda com elas (abas, rádio, menu, tabela navegável, o divisor de painéis).
const RECORD_NAV_ARROW_OWNERS =
  "[role='tablist'], [role='radiogroup'], [role='menu'], [role='menubar'], [role='listbox'], [role='grid'], [role='tree'], [role='slider'], [role='separator'], [role='spinbutton']";

const recordNav = {
  scope: "screen" as const,
  owner: "OperatorRecordNav",
  enabledContexts: [] as const,
  forbiddenContexts: [] as const,
  alternative: "Botões ‹ › ao lado de \"3 de 18\" no cabeçalho",
};

export const RECORD_NAV_SHORTCUTS = defineOperatorShortcutMap([
  {
    ...recordNav,
    id: "record.previous",
    label: "Registro anterior da lista",
    combinations: [{ code: "KeyK" }, { code: "ArrowLeft" }],
    ignoreWithin: RECORD_NAV_ARROW_OWNERS,
  },
  {
    ...recordNav,
    id: "record.next",
    label: "Próximo registro da lista",
    combinations: [{ code: "KeyJ" }, { code: "ArrowRight" }],
    ignoreWithin: RECORD_NAV_ARROW_OWNERS,
  },
] satisfies readonly OperatorShortcutCommand[]);

// Esc limpa a seleção da barra de seleção (`OperatorBulkBar`). Cede a vez a campo de
// texto e a diálogo, lista ou menu aberto (a regra do kit para atalho em sobreposição):
// ali o Esc é de quem está aberto.
export const BULK_BAR_SHORTCUTS = defineOperatorShortcutMap([
  {
    scope: "screen" as const,
    owner: "OperatorBulkBar",
    enabledContexts: [] as const,
    forbiddenContexts: [] as const,
    id: "bulk.clear",
    label: "Limpar a seleção",
    combinations: [{ code: "Escape" }],
    alternative: "Botão × da barra de seleção",
  },
] satisfies readonly OperatorShortcutCommand[]);
