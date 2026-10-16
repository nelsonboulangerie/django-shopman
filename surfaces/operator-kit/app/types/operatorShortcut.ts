export type OperatorShortcutPlatform = "all" | "macos" | "windows";

export type OperatorShortcutScope = "suite" | "app" | "screen" | "overlay";

export interface OperatorShortcutCombination {
  /** KeyboardEvent.code, para não depender do caractere produzido pelo layout. */
  code: string;
  alt?: boolean;
  control?: boolean;
  meta?: boolean;
  shift?: boolean;
  platform?: OperatorShortcutPlatform;
}

export interface OperatorShortcutCommand<Context extends string = string> {
  id: string;
  label: string;
  combinations: readonly OperatorShortcutCombination[];
  scope: OperatorShortcutScope;
  owner: string;
  enabledContexts: readonly Context[];
  forbiddenContexts: readonly Context[];
  alternative: string;
  allowInEditable?: boolean;
  allowInOverlay?: boolean;
  allowRepeat?: boolean;
  /**
   * Seletor de onde a tecla é de OUTRO dono: com o foco dentro dele, o atalho não age (e
   * não toma a tecla). As setas do anterior/próximo deixam as abas, os grupos de rádio e
   * os menus andarem com as próprias setas.
   */
  ignoreWithin?: string;
}

export interface OperatorShortcutCollision {
  platform: OperatorShortcutPlatform;
  combination: string;
  first: string;
  second: string;
  contexts: string[];
}
