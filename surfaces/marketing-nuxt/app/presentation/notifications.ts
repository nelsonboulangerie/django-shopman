import type { MarketingActionProjectionV2 } from "~/types/campaign";
import type {
  MarketingNotification,
  NotificationLifecycle,
} from "~/types/notifications";

export type NotificationActionKind =
  "open_announcement" | "mark_notification_seen" | "acknowledge_notification";

// "Assumido" era *acknowledge* traduzido, e o gestor não assume plantão nenhum:
// ele diz que viu. A palavra da casa para esse gesto é **Visto**, e ela já vive
// nos timers da Produção (`FloorTimersPanel`, `AlertsBell`), no botão e no estado.
//
// `seen` fica SEM rótulo de propósito. Ele não é um gesto de ninguém: é o app
// registrando que mostrou o alerta ao abrir o painel. Dar a ele a mesma palavra
// do gesto do operador seria um carimbo para dois estados; dar outra palavra
// seria inventar vocabulário para uma informação que não decide nada. Sem chip,
// "não é mais novo" se lê pela ausência do "Novo".
const STATE_LABELS: Record<NotificationLifecycle, string> = {
  unseen: "Novo",
  seen: "",
  acknowledged: "Visto",
  resolved: "Resolvido",
  expired: "Expirado",
};

const REASON_LABELS: Record<string, string> = {
  missing_capability: "Seu acesso não permite abrir este anúncio.",
  review_window_expired: "O prazo de revisão terminou.",
  source_version_changed: "O anúncio mudou. Atualize os alertas.",
  announcement_no_longer_actionable: "Este anúncio já foi decidido.",
};

export function notificationStateLabel(state: NotificationLifecycle): string {
  return STATE_LABELS[state] ?? "Estado desconhecido";
}

export function notificationReasonLabel(reason: string): string {
  return REASON_LABELS[reason] ?? "Esta ação não está disponível agora.";
}

/** Resolve somente Actions canônicas que pertencem ao alerta e ao source exatos. */
export function notificationAction(
  notification: MarketingNotification,
  kind: NotificationActionKind,
): MarketingActionProjectionV2 | null {
  const expected = expectedAction(notification, kind);
  if (!expected) return null;
  return (
    notification.actions.find(
      (action) =>
        action.kind === kind &&
        action.resource_ref === expected.resourceRef &&
        action.href === expected.href &&
        action.method === expected.method &&
        !action.href.startsWith("//") &&
        action.href.startsWith("/"),
    ) ?? null
  );
}

function expectedAction(
  notification: MarketingNotification,
  kind: NotificationActionKind,
): { resourceRef: string; href: string; method: "GET" | "POST" } | null {
  if (kind === "mark_notification_seen") {
    return {
      resourceRef: `notification:${notification.pk}`,
      href: `/api/v1/backstage/notifications/${notification.pk}/read/`,
      method: "POST",
    };
  }
  if (kind === "acknowledge_notification") {
    return {
      resourceRef: `notification:${notification.pk}`,
      href: `/api/v1/backstage/notifications/${notification.pk}/acknowledge/`,
      method: "POST",
    };
  }
  const announcementId = announcementSourceId(notification);
  if (announcementId === null) return null;
  return {
    resourceRef: `announcement:${announcementId}`,
    href: `/announcements/${announcementId}#review`,
    method: "GET",
  };
}

export function announcementSourceId(
  notification: MarketingNotification,
): number | null {
  if (notification.source.condition !== "announcement_review") return null;
  const match = /^announcement:([1-9]\d*)$/.exec(notification.source.ref);
  if (!match) return null;
  return Number(match[1]);
}
