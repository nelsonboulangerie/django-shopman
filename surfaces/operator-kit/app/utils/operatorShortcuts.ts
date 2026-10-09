import type {
  OperatorShortcutCollision,
  OperatorShortcutCombination,
  OperatorShortcutCommand,
  OperatorShortcutPlatform,
} from "../types/operatorShortcut";

const EDITABLE_SELECTOR = "input, textarea, select, [contenteditable='true'], [role='textbox'], [role='combobox']";
// A trava do terminal (`OperatorLock`) cobre a tela sem ser um diálogo, e a tela de
// baixo continua montada: atalho global nenhum opera o que ela esconde (o Alt+N do
// rail trocava de etapa por baixo do bloqueio da Produção).
const OVERLAY_SELECTOR =
  "[role='dialog'][data-state='open'], [role='alertdialog'], [aria-modal='true'], [data-operator-lock]";

export function operatorPlatform(
  navigatorLike: Pick<Navigator, "platform" | "userAgent"> | undefined =
    typeof navigator === "undefined" ? undefined : navigator,
): Exclude<OperatorShortcutPlatform, "all"> {
  const value = `${navigatorLike?.platform ?? ""} ${navigatorLike?.userAgent ?? ""}`.toLowerCase();
  return value.includes("mac") ? "macos" : "windows";
}

export function shortcutCombinationKey(combination: OperatorShortcutCombination): string {
  return [
    combination.platform ?? "all",
    combination.control ? "Control" : "",
    combination.meta ? "Meta" : "",
    combination.alt ? "Alt" : "",
    combination.shift ? "Shift" : "",
    combination.code,
  ]
    .filter(Boolean)
    .join("+");
}

export function shortcutMatches(
  event: KeyboardEvent,
  combination: OperatorShortcutCombination,
  platform = operatorPlatform(),
): boolean {
  if (combination.platform && combination.platform !== "all" && combination.platform !== platform) return false;
  const code = event.code || (
    event.key === "/" || event.key === "?"
      ? "Slash"
      : /^[a-z]$/i.test(event.key)
        ? `Key${event.key.toUpperCase()}`
        : /^\d$/.test(event.key)
          ? `Digit${event.key}`
          : event.key
  );
  const shift = event.shiftKey || (event.key === "?" && code === "Slash");
  return (
    code === combination.code &&
    event.altKey === Boolean(combination.alt) &&
    event.ctrlKey === Boolean(combination.control) &&
    event.metaKey === Boolean(combination.meta) &&
    shift === Boolean(combination.shift)
  );
}

export function shortcutEventAllowed(
  event: KeyboardEvent,
  command: OperatorShortcutCommand,
  activeContexts: ReadonlySet<string>,
): boolean {
  if (event.defaultPrevented || event.isComposing || event.key === "Process") return false;
  if (event.repeat && !command.allowRepeat) return false;
  const target = event.target instanceof Element ? event.target : null;
  if (!command.allowInEditable && target?.closest(EDITABLE_SELECTOR)) return false;
  if (command.ignoreWithin && target?.closest(command.ignoreWithin)) return false;
  if (!command.allowInOverlay && typeof document !== "undefined" && document.querySelector(OVERLAY_SELECTOR)) return false;
  if (command.forbiddenContexts.some((context) => activeContexts.has(context))) return false;
  return command.enabledContexts.length === 0 || command.enabledContexts.some((context) => activeContexts.has(context));
}

function combinationsOverlap(first: OperatorShortcutCombination, second: OperatorShortcutCombination): OperatorShortcutPlatform[] {
  const firstPlatforms = first.platform && first.platform !== "all" ? [first.platform] : ["macos", "windows"];
  const secondPlatforms = second.platform && second.platform !== "all" ? [second.platform] : ["macos", "windows"];
  if (shortcutCombinationKey({ ...first, platform: "all" }) !== shortcutCombinationKey({ ...second, platform: "all" })) return [];
  return firstPlatforms.filter((platform) => secondPlatforms.includes(platform)) as OperatorShortcutPlatform[];
}

export function findOperatorShortcutCollisions(
  commands: readonly OperatorShortcutCommand[],
): OperatorShortcutCollision[] {
  const collisions: OperatorShortcutCollision[] = [];
  for (let left = 0; left < commands.length; left += 1) {
    for (let right = left + 1; right < commands.length; right += 1) {
      const first = commands[left]!;
      const second = commands[right]!;
      const contexts = first.enabledContexts.filter((context) => second.enabledContexts.includes(context));
      if (!contexts.length && first.scope !== "suite" && second.scope !== "suite") continue;
      for (const a of first.combinations) {
        for (const b of second.combinations) {
          for (const platform of combinationsOverlap(a, b)) {
            collisions.push({
              platform,
              combination: shortcutCombinationKey({ ...a, platform }),
              first: first.id,
              second: second.id,
              contexts: [...contexts],
            });
          }
        }
      }
    }
  }
  return collisions;
}

export function defineOperatorShortcutMap<const T extends readonly OperatorShortcutCommand[]>(commands: T): T {
  const ids = new Set<string>();
  for (const command of commands) {
    if (!command.id || ids.has(command.id)) throw new Error(`Atalho com id ausente ou repetido: ${command.id || "<vazio>"}`);
    if (!command.combinations.length) throw new Error(`${command.id}: combinação ausente`);
    if (!command.alternative.trim()) throw new Error(`${command.id}: alternativa sem teclado ausente`);
    ids.add(command.id);
  }
  const collisions = findOperatorShortcutCollisions(commands);
  if (collisions.length) {
    const first = collisions[0]!;
    throw new Error(`Colisão de atalhos: ${first.first} e ${first.second} usam ${first.combination}`);
  }
  return commands;
}
