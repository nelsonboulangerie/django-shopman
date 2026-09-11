<script setup lang="ts">
import {
  notificationAction,
  notificationOwnerLabel,
  notificationReasonLabel,
  notificationStateLabel,
} from "~/presentation/notifications";
import type { MarketingNotification } from "~/types/notifications";
import { expirySummary, scheduleSummary } from "~/utils/marketingSchedule";

const {
  notifications,
  unseenCount,
  unresolvedCount,
  shopTimezone,
  hasMore,
  realtime,
  loading,
  error,
  mutationError,
  acknowledging,
  markingSeen,
  refresh,
  markVisible,
  acknowledge,
  openHref,
} = useMarketingNotificationInbox();

const open = ref(false);
const trigger = ref<HTMLButtonElement | null>(null);
const panel = ref<HTMLElement | null>(null);
const panelTitle = ref<HTMLElement | null>(null);

function setBackgroundInert(value: boolean) {
  const root = document.querySelector<HTMLElement>("[data-marketing-app-root]");
  if (!root) return;
  if (value) {
    root.setAttribute("inert", "");
    root.setAttribute("aria-hidden", "true");
  } else {
    root.removeAttribute("inert");
    root.removeAttribute("aria-hidden");
  }
}

async function openPanel() {
  open.value = true;
  void markVisible();
  await nextTick();
  panelTitle.value?.focus();
  setBackgroundInert(true);
}

function closePanel(restoreFocus = true) {
  open.value = false;
  setBackgroundInert(false);
  if (restoreFocus) nextTick(() => trigger.value?.focus());
}

function toggle() {
  if (open.value) closePanel();
  else void openPanel();
}

function trapPanelFocus(event: KeyboardEvent) {
  const focusable = Array.from(
    panel.value?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ) ?? [],
  );
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable.at(-1);
  if (
    event.shiftKey &&
    (document.activeElement === first || document.activeElement === panelTitle.value)
  ) {
    event.preventDefault();
    last?.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first?.focus();
  }
}

async function review(notification: MarketingNotification) {
  const href = openHref(notification);
  if (!href) return;
  closePanel(false);
  await navigateTo(href);
}

function reviewAction(notification: MarketingNotification) {
  return notificationAction(notification, "open_announcement");
}

function reviewReason(notification: MarketingNotification): string {
  const action = reviewAction(notification);
  if (!action)
    return "O alerta mudou. Atualize para encontrar a revisão correta.";
  return action.enabled ? "" : notificationReasonLabel(action.reason);
}

function deadline(notification: MarketingNotification): string {
  return notification.expires_at
    ? expirySummary(notification.expires_at, shopTimezone.value)
    : "Sem prazo automático";
}

function escalation(notification: MarketingNotification): string {
  if (!notification.escalation.role) return "";
  const owner = notificationOwnerLabel(notification.escalation.role);
  const when = notification.escalation.at
    ? scheduleSummary(notification.escalation.at, shopTimezone.value)
    : "se continuar pendente";
  const timezone = notification.escalation.at ? ` (${shopTimezone.value})` : "";
  return `Escala para ${owner} ${when}${timezone}`;
}

onBeforeUnmount(() => setBackgroundInert(false));
</script>

<template>
  <div class="relative shrink-0">
    <!-- O gatilho preserva o badge dinâmico, indisponível no botão de ícone canônico. -->
    <button
      ref="trigger"
      type="button"
      class="relative grid size-11 place-items-center rounded-md border border-border text-muted-foreground transition hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      :aria-label="`Alertas: ${unresolvedCount} pendentes, ${unseenCount} novos`"
      :aria-expanded="open"
      aria-controls="marketing-notifications-panel"
      title="Alertas que precisam de atenção"
      @click="toggle"
    >
      <Icon name="lucide:bell" class="size-5" />
      <span
        v-if="unresolvedCount"
        class="absolute -right-1 -top-1 grid min-w-5 place-items-center rounded-full bg-destructive px-1 text-xs font-bold tabular-nums text-white"
        aria-hidden="true"
        >{{ unresolvedCount > 99 ? "99+" : unresolvedCount }}</span
      >
    </button>

    <Teleport to="body">
      <div
        v-if="open"
        class="fixed inset-0 z-40 bg-background/20"
        aria-hidden="true"
        @click="closePanel()"
      />

      <section
        v-if="open"
        id="marketing-notifications-panel"
        ref="panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="marketing-notifications-title"
        aria-describedby="marketing-notifications-status"
        class="fixed inset-x-3 top-16 z-50 flex max-h-[calc(100vh-5rem)] flex-col overflow-hidden rounded-md border border-border bg-card shadow-xl sm:right-3 sm:left-auto sm:w-96"
        @keydown.esc.stop="closePanel()"
        @keydown.tab="trapPanelFocus"
      >
      <header
        class="flex items-center justify-between gap-3 border-b border-border px-4 py-3"
      >
        <div class="min-w-0">
          <h2
            id="marketing-notifications-title"
            ref="panelTitle"
            tabindex="-1"
            class="text-sm font-bold"
          >
            Alertas pessoais
          </h2>
          <p id="marketing-notifications-status" class="text-xs text-muted-foreground">
            {{ unresolvedCount }} pendente{{
              unresolvedCount === 1 ? "" : "s"
            }}
            · {{ realtime === "live" ? "ao vivo" : "reconectando" }}
          </p>
        </div>
        <div class="flex items-center gap-1">
          <UiIconButton
            icon="lucide:refresh-cw"
            label="Atualizar alertas"
            :spinning="loading"
            :disabled="loading"
            @click="refresh"
          />
          <UiIconButton
            icon="lucide:x"
            label="Fechar alertas"
            @click="closePanel()"
          />
        </div>
      </header>

      <p
        v-if="mutationError"
        class="border-b border-destructive/30 bg-destructive/10 px-4 py-2.5 text-sm text-destructive"
        role="alert"
      >
        {{ mutationError }}
      </p>

      <div class="min-h-0 flex-1 overflow-y-auto p-2">
        <div
          v-if="loading && !notifications.length"
          class="grid place-items-center gap-2 py-10 text-center text-muted-foreground"
          aria-busy="true"
        >
          <Icon
            name="lucide:loader-circle"
            class="size-6 animate-spin motion-reduce:animate-none"
          />
          <p class="text-sm">Buscando seus alertas…</p>
        </div>

        <div
          v-else-if="error && !notifications.length"
          class="grid place-items-center gap-2 px-4 py-8 text-center"
          role="alert"
        >
          <Icon name="lucide:cloud-off" class="size-6 text-destructive" />
          <p class="text-sm font-semibold">
            Não foi possível carregar os alertas.
          </p>
          <p class="text-xs text-muted-foreground">
            Nada foi descartado. Tente novamente.
          </p>
          <UiButton
            type="button"
            variant="outline"
            class="mt-1"
            @click="refresh"
          >
            Tentar novamente
          </UiButton>
        </div>

        <div
          v-else-if="!notifications.length"
          class="grid place-items-center gap-1.5 py-10 text-center text-muted-foreground"
        >
          <Icon name="lucide:check-circle-2" class="size-6" />
          <p class="text-sm">Nenhum alerta pendente.</p>
        </div>

        <ul v-else class="flex flex-col gap-2">
          <li
            v-for="notification in notifications"
            :key="notification.pk"
            class="rounded-lg border border-border p-3"
            :class="
              notification.lifecycle === 'unseen'
                ? 'bg-accent/40'
                : 'bg-background'
            "
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <p
                  class="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                >
                  {{ notificationStateLabel(notification.lifecycle) }} ·
                  {{ notificationOwnerLabel(notification.owner.role) }}
                </p>
                <h3 class="mt-1 break-words text-sm font-bold">
                  {{ notification.title }}
                </h3>
              </div>
              <span
                v-if="notification.lifecycle === 'unseen'"
                class="mt-0.5 size-2.5 shrink-0 rounded-full bg-destructive"
                aria-hidden="true"
              />
            </div>

            <p class="mt-1.5 break-words text-sm text-foreground">
              {{ notification.message }}
            </p>
            <p class="mt-2 text-xs text-muted-foreground">
              {{ deadline(notification) }}
            </p>
            <p class="mt-0.5 text-xs text-muted-foreground">
              Criado {{ notification.created_at_display }} · origem v{{
                notification.source.version
              }}
            </p>
            <p
              v-if="escalation(notification)"
              class="mt-0.5 text-xs text-muted-foreground"
            >
              {{ escalation(notification) }}
            </p>

            <div class="mt-3 flex flex-wrap gap-2">
              <UiButton
                type="button"
                class="flex-1"
                :disabled="!reviewAction(notification)?.enabled"
                @click="review(notification)"
              >
                Revisar anúncio
              </UiButton>
              <UiButton
                v-if="
                  notificationAction(notification, 'acknowledge_notification')
                    ?.enabled
                "
                type="button"
                variant="outline"
                :disabled="acknowledging.has(notification.pk)"
                @click="acknowledge(notification)"
              >
                {{
                  acknowledging.has(notification.pk) ? "Assumindo…" : "Assumir"
                }}
              </UiButton>
            </div>
            <p
              v-if="reviewReason(notification)"
              class="mt-2 text-xs text-muted-foreground"
            >
              {{ reviewReason(notification) }}
            </p>
          </li>
        </ul>

        <p
          v-if="hasMore"
          class="px-2 py-3 text-center text-xs text-muted-foreground"
        >
          Mostrando os 100 alertas mais recentes.
        </p>
      </div>

      <p
        v-if="markingSeen"
        class="border-t border-border px-4 py-2 text-xs text-muted-foreground"
        aria-live="polite"
      >
        Registrando os alertas que ficaram visíveis…
      </p>
      </section>
    </Teleport>
  </div>
</template>
