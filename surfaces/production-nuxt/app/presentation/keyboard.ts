// Dicionário puro do teclado da Produção. As páginas executam os efeitos;
// manter a resolução aqui faz botão, tecla, ajuda e testes falarem a mesma
// língua sem espalhar `event.key` pelo app.

import type { ShortcutGroup } from "../../../operator-kit/app/presentation/suiteChrome";

/**
 * O que a ajuda de atalhos da suíte lista para a Produção, além de "Em todo o app" (as
 * etapas, Alt+1 a Alt+5, e o "?", que o kit monta com as seções do rail).
 */
export const PRODUCTION_SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: "Em toda tela da Produção",
    items: [
      { keys: ["/"], label: "Buscar por produto, SKU ou receita" },
      { keys: ["R"], label: "Atualizar os dados da tela" },
    ],
  },
  {
    title: "Listas e diálogos",
    items: [
      { keys: ["Tab", "Shift+Tab"], label: "Percorrer os comandos" },
      { keys: ["Enter", "Espaço"], label: "Acionar o comando em foco" },
      { keys: ["Esc"], label: "Fechar ou voltar sem confirmar" },
      { keys: ["Enter"], label: "Confirmar uma quantidade digitada" },
    ],
  },
  {
    title: "QC e timer",
    items: [
      { keys: ["0–9"], label: "Digitar quantidade ou minutos" },
      { keys: ["Backspace"], label: "Apagar o último dígito" },
      { keys: ["C", "Delete"], label: "Limpar o número" },
      { keys: ["Enter numérico"], label: "Confirmar pelo numpad físico" },
      { keys: ["Enter"], label: "Iniciar o timer; quando tocar, marcar Visto" },
    ],
  },
];

export const PRODUCTION_SHORTCUTS_DESCRIPTION =
  "Toque e teclado executam os mesmos comandos. Os atalhos pausam sob bloqueio, confirmação ou edição de texto.";

export type ProductionGlobalShortcut =
  | "plan"
  | "mise-en-place"
  | "open"
  | "close"
  | "quality"
  | "focus-search"
  | "refresh"
  | "help";

export type QuantityKeyboardShortcut =
  | { kind: "digit"; digit: string }
  | { kind: "backspace" }
  | { kind: "clear" }
  | { kind: "confirm" };

type ShortcutEvent = Pick<
  KeyboardEvent,
  "key" | "code" | "altKey" | "ctrlKey" | "metaKey" | "shiftKey"
>;

const STAGE_BY_ALT_CODE: Record<string, ProductionGlobalShortcut> = {
  Digit1: "plan",
  Digit2: "mise-en-place",
  Digit3: "open",
  Digit4: "close",
  Digit5: "quality",
};

export function resolveProductionGlobalShortcut(
  event: ShortcutEvent,
): ProductionGlobalShortcut | null {
  if (event.ctrlKey || event.metaKey) return null;

  const altStage = event.altKey ? STAGE_BY_ALT_CODE[event.code] : null;
  if (altStage) return altStage;

  if (event.altKey) return null;
  if (event.key === "/") return "focus-search";
  if (event.key === "r" || event.key === "R") return "refresh";
  if (event.key === "?") return "help";
  return null;
}

export function resolveQuantityKeyboardShortcut(
  event: ShortcutEvent,
): QuantityKeyboardShortcut | null {
  if (event.altKey || event.ctrlKey || event.metaKey) return null;
  if (/^[0-9]$/.test(event.key)) {
    return { kind: "digit", digit: event.key };
  }
  if (event.key === "Backspace") return { kind: "backspace" };
  if (event.key === "Delete" || event.key === "c" || event.key === "C") {
    return { kind: "clear" };
  }
  if (event.key === "Enter") return { kind: "confirm" };
  return null;
}

export function isEditableKeyboardTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return Boolean(
    target.closest(
      "input, textarea, select, [contenteditable='true'], [role='textbox']",
    ),
  );
}

export function isNativeActionTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return Boolean(target.closest("button, a, [role='button']"));
}

// A tela continua montada sob locks e diálogos. Atalho global jamais pode
// operar o conteúdo escondido, nem abandonar o QC que está sendo preenchido.
export function productionGlobalKeysBlocked(): boolean {
  if (typeof document === "undefined") return true;
  return Boolean(
    document.querySelector(
      "[data-operator-lock], [data-production-shortcut-scope='exclusive'], [role='dialog'][data-state='open'], [role='alertdialog'][data-state='open']",
    ),
  );
}

// Os handlers contextuais (QC/timer) aceitam seu próprio diálogo, mas ainda
// precisam calar quando o terminal é travado por cima.
export function productionContextKeysBlocked(): boolean {
  if (typeof document === "undefined") return true;
  return Boolean(document.querySelector("[data-operator-lock]"));
}

export function hasOpenDialogOutside(exceptionSelector?: string): boolean {
  if (typeof document === "undefined") return true;
  const dialogs = document.querySelectorAll(
    '[role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"]',
  );
  return Array.from(dialogs).some(
    (dialog) => !exceptionSelector || !dialog.matches(exceptionSelector),
  );
}
