import type {
  OperatorPwaIcon,
  OperatorPwaShortcut,
  ResolvedOperatorPwa,
} from "../../pwa.config";
import { operatorAppName, type OperatorAppName } from "../../app/presentation/windowTitle";

export function operatorPwaIcons(icons: OperatorPwaIcon[]) {
  return icons.map((icon) => ({
    src: icon.src,
    sizes: icon.sizes,
    type: icon.type || "image/png",
    purpose: icon.purpose || "any",
  }));
}

export function operatorPwaShortcuts(shortcuts: OperatorPwaShortcut[] = []) {
  return shortcuts.map((shortcut) => ({
    name: shortcut.name,
    short_name: shortcut.shortName || shortcut.name,
    url: shortcut.url,
    ...(shortcut.icon
      ? { icons: [{ src: shortcut.icon, sizes: "192x192", type: "image/png" }] }
      : {}),
  }));
}

/**
 * Manifesto do app de operador. `name` é `"<casa> · <App>"` — exatamente o começo do
 * título da janela (`windowTitle`), senão o Chrome prefixa `"<name> - "` na barra.
 * `short_name` é só o rótulo ("PDV"): aparece onde falta espaço (ícone no launcher
 * Android), e lá a casa se repetiria igual em todos os apps e cortaria o que distingue
 * um do outro ("Nelson · Pro…"). Desktop (macOS/Windows/ChromeOS) mostra o `name`.
 */
export function buildOperatorManifest(
  options: ResolvedOperatorPwa,
  appName: OperatorAppName = operatorAppName("", options.manifest.label),
) {
  return {
    id: "/",
    name: appName.name,
    short_name: appName.label,
    description: options.manifest.description,
    lang: "pt-BR",
    dir: "ltr",
    start_url: "/?source=pwa",
    scope: "/",
    display: options.display,
    display_override: [options.display],
    orientation: options.manifest.orientation || "any",
    theme_color: options.manifest.themeColor,
    background_color: options.manifest.backgroundColor,
    icons: operatorPwaIcons(options.manifest.icons),
    shortcuts: operatorPwaShortcuts(options.manifest.shortcuts),
  };
}
