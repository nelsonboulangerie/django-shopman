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
