// Dicionário puro do teclado da Produção. As páginas executam os efeitos;
// manter a resolução aqui faz botão, tecla, ajuda e testes falarem a mesma
// língua sem espalhar `event.key` pelo app.

export type ProductionGlobalShortcut =
  | "plan"
  | "mise-en-place"
  | "produce"
  | "expedite"
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
  Digit3: "produce",
  Digit4: "expedite",
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
