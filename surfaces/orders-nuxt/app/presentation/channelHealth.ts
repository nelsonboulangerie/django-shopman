// O checklist vivo de cada canal — funções puras, testáveis sem runtime.
// Copy: inequívoco primeiro (docs/reference/omotenashi-copy.md). Cada pendência
// traz o gesto que a resolve; o que já está certo fica recolhido.
import type { ChannelHealthItem, ChannelHealthLink, ChannelHealthProjection } from "~/types/channelHealth";

export interface Bases {
  djangoBase: string;
  adminBase: string;
}

/** O que o botão do item faz: navegar no app, abrir fora, parear a TV ou abrir as coleções. */
export type HealthAction =
  | { kind: "route"; label: string; to: string }
  | { kind: "external"; label: string; href: string }
  | { kind: "pair"; label: string }
  | { kind: "collections"; label: string };

export function itemAction(item: ChannelHealthItem, bases: Bases): HealthAction | null {
  if (!item.action_label) return null;
  switch (item.action_target) {
    case "gestor":
      return item.action_path ? { kind: "route", label: item.action_label, to: item.action_path } : null;
    case "admin":
      return item.action_path ? { kind: "external", label: item.action_label, href: `${bases.adminBase}${item.action_path}` } : null;
    case "django":
      return item.action_path ? { kind: "external", label: item.action_label, href: `${bases.djangoBase}${item.action_path}` } : null;
    case "pair":
      return { kind: "pair", label: item.action_label };
    case "collections":
      return { kind: "collections", label: item.action_label };
    default:
      return null;
  }
}

/** Link de "ver como o cliente vê": saída do Django ganha a base; externo vai como veio. */
export function previewHref(link: ChannelHealthLink, bases: Bases): string {
  return link.target === "django" ? `${bases.djangoBase}${link.path}` : link.path;
}

/** Pendências primeiro, na ordem do servidor; o que está certo vem depois. */
export function orderedItems(health: ChannelHealthProjection): ChannelHealthItem[] {
  return [...health.items.filter((i) => i.state !== "ok"), ...health.items.filter((i) => i.state === "ok")];
}

/** O endereço que a TV abre para se autorizar: a tela do quadro, servida pelo Django. */
export function pairUrl(health: ChannelHealthProjection, bases: Bases): string {
  const screen = health.preview.find((link) => link.target === "django");
  return screen ? previewHref(screen, bases) : "";
}
