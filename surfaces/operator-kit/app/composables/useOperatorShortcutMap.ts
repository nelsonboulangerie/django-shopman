import { onBeforeUnmount, onMounted, type Ref } from "vue";

import type { OperatorShortcutCommand } from "../types/operatorShortcut";
import { operatorPlatform, shortcutEventAllowed, shortcutMatches } from "../utils/operatorShortcuts";

export function useOperatorShortcutMap(
  commands: readonly OperatorShortcutCommand[],
  handlers: Readonly<Record<string, (event: KeyboardEvent) => void>>,
  activeContexts: Ref<ReadonlySet<string>>,
) {
  function onKeydown(event: KeyboardEvent) {
    const platform = operatorPlatform();
    for (const command of commands) {
      const handler = handlers[command.id];
      if (!handler || !shortcutEventAllowed(event, command, activeContexts.value)) continue;
      if (!command.combinations.some((combination) => shortcutMatches(event, combination, platform))) continue;
      event.preventDefault();
      handler(event);
      return;
    }
  }

  onMounted(() => window.addEventListener("keydown", onKeydown));
  onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));

  return { onKeydown };
}
