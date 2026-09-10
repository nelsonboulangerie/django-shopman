<script setup lang="ts">
// O sino da caixa PESSOAL. Uma implementação, oito apps de operador.
//
// ⚠️ **Não interrompe.** Contador discreto e lista consultável: sem modal, sem
// som, sem roubo de foco. O balcão está atendendo, e um aviso de acesso não vale
// uma venda perdida — ele espera o operador olhar.
//
// ⚠️ **Realce, nunca silo.** O aviso suspeito fica na MESMA lista, marcado. Uma
// aba "suspeitos" esconderia o resto e o dono pediu o contrário: ver tudo, com o
// olho parando no que é anômalo.
import { useNotifications } from "../composables/useNotifications";
import {
  anomalyLabels,
  badgeCount,
  isHighlighted,
  signInSummary,
} from "../presentation/notifications";

const { items, unread, markRead, signIns, loadSignIns } = useNotifications();

const open = ref(false);
// Duas vistas no MESMO painel: a caixa e o log de acessos. O log não tem página
// própria (a conta do operador é plano futuro), e mandar a pessoa para o Admin
// noutro domínio não é "conferir sempre que quiser" — então ele mora aqui.
const view = ref<"inbox" | "signIns">("inbox");

const count = computed(() => badgeCount(unread.value));

function toggle() {
  open.value = !open.value;
  if (open.value) view.value = "inbox";
}

async function showSignIns() {
  view.value = "signIns";
  await loadSignIns();
}
</script>

<template>
  <div class="relative">
    <button
      type="button"
      class="relative inline-flex size-9 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-muted hover:text-foreground"
      :aria-label="unread ? `Avisos (${unread} não lidos)` : 'Avisos'"
      @click="toggle"
    >
      <Icon name="lucide:bell" class="size-5" />
      <!-- Discreto: um ponto com número, sem cor de alarme. Quem precisa ver, vê. -->
      <span
        v-if="count"
        data-notification-count
        class="absolute -right-0.5 -top-0.5 grid min-w-4 place-items-center rounded-full bg-primary px-1 text-[10px] font-bold leading-4 text-primary-foreground"
      >{{ count }}</span>
    </button>

    <div
      v-if="open"
      data-notification-panel
      class="absolute right-0 z-50 mt-2 w-80 rounded-xl border bg-card p-2 shadow-lg"
    >
      <template v-if="view === 'inbox'">
        <p
          v-if="!items.length"
          class="px-2 py-6 text-center text-sm text-muted-foreground"
        >
          Nada por aqui.
        </p>

        <ul v-else class="max-h-96 space-y-1 overflow-y-auto">
          <li
            v-for="item in items"
            :key="item.pk"
            data-notification-item
            :data-highlight="isHighlighted(item) ? 'true' : undefined"
            class="rounded-lg border p-2 text-sm"
            :class="
              isHighlighted(item)
                ? 'border-warning/40 bg-warning/10'
                : 'border-transparent'
            "
          >
            <div class="flex items-start gap-2">
              <Icon
                v-if="isHighlighted(item)"
                name="lucide:alert-triangle"
                class="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400"
              />
              <div class="min-w-0 flex-1">
                <p class="font-medium" :class="{ 'text-muted-foreground': item.is_read }">
                  {{ item.title }}
                </p>
                <p class="whitespace-pre-line text-xs text-muted-foreground">
                  {{ item.message }}
                </p>
                <p v-if="anomalyLabels(item).length" class="sr-only">
                  Acesso destacado.
                </p>
                <div class="mt-1 flex items-center gap-2">
                  <span class="text-xs text-muted-foreground">
                    {{ item.created_at_display }}
                  </span>
                  <button
                    v-if="!item.is_read"
                    type="button"
                    class="text-xs text-muted-foreground underline-offset-2 hover:underline"
                    @click="markRead(item.pk)"
                  >
                    Marcar como lida
                  </button>
                </div>
              </div>
            </div>
          </li>
        </ul>

        <button
          type="button"
          data-see-sign-ins
          class="mt-2 inline-flex w-full items-center justify-center gap-1 rounded-lg py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
          @click="showSignIns"
        >
          <Icon name="lucide:history" class="size-4" /> Meus acessos
        </button>
      </template>

      <template v-else>
        <button
          type="button"
          class="mb-1 inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-muted-foreground hover:text-foreground"
          @click="view = 'inbox'"
        >
          <Icon name="lucide:arrow-left" class="size-4" /> Avisos
        </button>

        <p v-if="!signIns.length" class="px-2 py-6 text-center text-sm text-muted-foreground">
          Nenhum acesso registrado.
        </p>

        <ul v-else class="max-h-96 space-y-1 overflow-y-auto">
          <li
            v-for="entry in signIns"
            :key="entry.pk"
            data-sign-in-item
            :data-highlight="entry.highlight ? 'true' : undefined"
            class="rounded-lg border p-2 text-sm"
            :class="
              entry.highlight
                ? 'border-warning/40 bg-warning/10'
                : 'border-transparent'
            "
          >
            <p class="font-medium">{{ signInSummary(entry) }}</p>
            <p class="text-xs text-muted-foreground">{{ entry.created_at_display }}</p>
            <p
              v-if="entry.anomaly_labels.length"
              class="text-xs text-amber-700 dark:text-amber-300"
            >
              {{ entry.anomaly_labels.join("; ") }}
            </p>
          </li>
        </ul>
      </template>
    </div>
  </div>
</template>
