import type {
  OperatorPwaCapabilityOptions,
  OperatorPwaIcon,
  OperatorPwaShortcut,
} from "../../pwa.config";

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

export function buildOperatorManifest(options: OperatorPwaCapabilityOptions) {
  return {
    id: "/",
    name: options.manifest.name,
    short_name: options.manifest.shortName.slice(0, 12).trimEnd(),
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
