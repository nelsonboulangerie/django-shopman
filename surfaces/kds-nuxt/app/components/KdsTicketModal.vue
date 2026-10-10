<script setup lang="ts">
// Detalhe do pedido — aberto por um toque na área de leitura do card (a que mostra
// identidade e itens; o `i` é a marca dela). Canal, horário, cliente, quem iniciou,
// notas e itens completos. A ação (Iniciar/Pronto) mora no BOTÃO do card, e só
// lá — dois lugares para o mesmo gesto é um lugar a mais para tocar errado.
//
// O gesto daqui é outro: "Declarar volumes" (quem embalou declara, onde estiver;
// decisão do dono, 04/10/2026). O mesmo do Gestor: − N +, Gravar, zero apaga. Só no
// ticket de pedido (`volumes_order_ref`); comanda ainda sem pedido não tem onde gravar.
import type { KDSTicketProjection } from "~/types/kds";
import {
  elapsedLabel,
  lucideIcon,
  slaPercent,
  splitRef,
  targetLabel,
  ticketTone,
  toneBar,
  toneTimer,
} from "~/presentation/board";

const props = withDefaults(
  defineProps<{
    open: boolean;
    ticket: KDSTicketProjection | null;
    /** Gravando os volumes (o Gravar espera). */
    volumesBusy?: boolean;
  }>(),
  { volumesBusy: false },
);
const emit = defineEmits<{ "update:open": [boolean]; volumes: [number] }>();

const canDeclareVolumes = computed(() => Boolean(props.ticket?.volumes_order_ref));
const volumesEditing = ref(false);
const volumesDraft = ref(0);
watch(() => [props.open, props.ticket?.pk], () => { volumesEditing.value = false; });
function openVolumes() {
  const t = props.ticket;
  if (!t) return;
  const itemCount = t.items.length || 1;
  volumesDraft.value = t.volumes || Math.max(1, Math.min(itemCount, 99));
  volumesEditing.value = true;
}
function stepVolumes(delta: number) {
  volumesDraft.value = Math.max(0, Math.min(99, volumesDraft.value + delta));
}
function saveVolumes() {
  volumesEditing.value = false;
  emit("volumes", volumesDraft.value);
}

const ref_ = computed(() =>
  props.ticket ? splitRef(props.ticket.order_ref) : { prefix: "", code: "" },
);
const tone = computed(() =>
  props.ticket ? ticketTone(props.ticket.timer_class) : "ok",
);
const timerClasses = computed(() => toneTimer(tone.value));
const barFill = computed(() => toneBar(tone.value));
const description = computed(() => {
  const t = props.ticket;
  if (!t) return "";
  const count = t.items.length === 1 ? "1 item" : `${t.items.length} itens`;
  return `${t.customer_name || "Sem cliente"}: ${t.status_label}, ${count}.`;
});
const fill = computed(() =>
  props.ticket
    ? slaPercent(props.ticket.elapsed_seconds, props.ticket.target_seconds)
    : 0,
);
</script>

<template>
  <NuxtModal
    :open="open && Boolean(ticket)"
    :title="ticket ? `Pedido ${ticket.order_ref}` : 'Pedido'"
    :description="description"
    :ui="{ content: 'max-h-[90vh] sm:max-w-lg' }"
    @update:open="$emit('update:open', Boolean($event))"
  >
    <!-- O título e a descrição do diálogo ficam para o leitor de tela; a tela desenha o
         código grande e o relógio, como o ticket. -->
    <template #content>
    <div v-if="ticket" class="flex min-h-0 flex-1 flex-col overflow-hidden" data-kds-ticket-modal>
      <!-- header -->
      <div class="border-b">
        <div class="flex items-start justify-between gap-3 p-5">
          <div class="min-w-0">
            <p
              class="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground"
            >
              <Icon
                v-if="ticket.channel_icon"
                :name="`lucide:${lucideIcon(ticket.channel_icon)}`"
                class="size-3.5"
              />
              <Icon
                v-if="ticket.fulfillment_icon"
                :name="`lucide:${lucideIcon(ticket.fulfillment_icon)}`"
                class="size-3.5"
              />
              <span class="tabular-nums"
                >{{ ref_.prefix }}{{ ticket.created_at_display }}</span
              >
            </p>
            <p
              class="break-words text-4xl font-extrabold tracking-tight tabular-nums leading-none"
            >
              {{ ref_.code }}
            </p>
            <p
              v-if="ticket.previous_tab_ref"
              class="mt-1.5 text-sm font-semibold text-muted-foreground"
            >
              <span class="line-through">Comanda {{ ticket.previous_tab_ref }}</span>
              <span class="ml-1">· já liberada após o pagamento</span>
            </p>
            <p
              v-if="ticket.customer_name"
              class="mt-1.5 truncate text-sm font-medium text-foreground/80"
            >
              {{ ticket.customer_name }}
            </p>
            <p
              v-if="ticket.started_by"
              class="mt-1 op-label text-muted-foreground"
              data-kds-started
            >
              Iniciado por {{ ticket.started_by }}<template v-if="ticket.started_at_display"> às {{ ticket.started_at_display }}</template>
            </p>
          </div>
          <div
            class="flex shrink-0 flex-col items-end gap-0.5 rounded-md border px-3 py-2 text-right"
            :class="timerClasses"
          >
            <span
              class="flex items-center gap-1 text-3xl font-bold tabular-nums leading-none"
            >
              <Icon name="lucide:timer" class="size-5 opacity-70" />
              {{ elapsedLabel(ticket.elapsed_seconds) }}
            </span>
            <span
              v-if="ticket.target_seconds"
              class="text-xs font-medium uppercase tracking-wide opacity-60"
            >
              Alvo {{ targetLabel(ticket.target_seconds) }}
            </span>
          </div>
          <NuxtButton
            color="neutral"
            variant="ghost"
            icon="i-lucide-x"
            class="-mt-1 -mr-2 shrink-0"
            aria-label="Fechar o detalhe"
            data-kds-ticket-close
            @click="$emit('update:open', false)"
          />
        </div>
        <!-- time-to-SLA fill bar -->
        <div class="h-1.5 w-full bg-white/5" aria-hidden="true">
          <div
            class="h-full rounded-r-full transition-[width] duration-500"
            :class="barFill"
            :style="{ width: `${fill}%` }"
          />
        </div>
      </div>

      <!-- notas do pedido: diretiva de preparo do operador (cozinha) + nota do cliente
           (checkout). Aqui há espaço — mostra completo (sem clamp). -->
      <div
        v-if="ticket.kitchen_note || ticket.customer_note"
        class="flex flex-col gap-2 border-b p-4"
      >
        <p
          v-if="ticket.kitchen_note"
          class="flex items-start gap-2 rounded-md border border-foreground/20 bg-muted/60 px-3 py-2 text-sm font-medium leading-snug"
        >
          <Icon name="lucide:chef-hat" class="mt-0.5 size-4 shrink-0 opacity-70" />
          <span class="min-w-0 whitespace-pre-wrap">{{ ticket.kitchen_note }}</span>
        </p>
        <p
          v-if="ticket.customer_note"
          class="flex items-start gap-2 rounded-md border px-3 py-2 text-sm text-muted-foreground leading-snug"
        >
          <Icon name="lucide:user" class="mt-0.5 size-4 shrink-0" />
          <span class="min-w-0 whitespace-pre-wrap">{{ ticket.customer_note }}</span>
        </p>
      </div>

      <!-- volumes: quem embalou declara aqui mesmo (a mesma porta do Gestor). -->
      <div v-if="canDeclareVolumes" class="border-b px-4 py-3" data-kds-volumes>
        <div v-if="volumesEditing" class="flex flex-col gap-2" data-kds-volumes-editor>
          <p class="op-label font-semibold">Quantos volumes saem?</p>
          <div class="flex items-center gap-2">
            <NuxtButton
              size="xl"
              color="neutral"
              variant="outline"
              icon="i-lucide-minus"
              aria-label="Um volume a menos"
              @click="stepVolumes(-1)"
            />
            <span class="min-w-12 text-center op-title tabular-nums" aria-live="polite" data-kds-volumes-draft>{{ volumesDraft }}</span>
            <NuxtButton
              size="xl"
              color="neutral"
              variant="outline"
              icon="i-lucide-plus"
              aria-label="Um volume a mais"
              @click="stepVolumes(1)"
            />
            <NuxtButton
              size="xl"
              class="ml-auto"
              label="Gravar"
              :disabled="volumesBusy"
              data-kds-volumes-save
              @click="saveVolumes"
            />
          </div>
          <p class="op-micro text-muted-foreground">
            {{ volumesDraft === 0 ? "Zero apaga: o pedido volta a contar itens." : "Sacolas ou caixas, contadas por quem embalou." }}
          </p>
        </div>
        <NuxtButton
          v-else
          size="xl"
          color="neutral"
          variant="outline"
          block
          icon="i-lucide-package"
          class="justify-start"
          :label="ticket.volumes ? `Volumes: ${ticket.volumes} (mudar)` : 'Declarar volumes'"
          :disabled="volumesBusy"
          data-kds-volumes-open
          @click="openVolumes"
        />
      </div>

      <!-- itens: inteiros, observação em destaque -->
      <div class="min-h-0 flex-1 overflow-y-auto p-3">
        <div
          class="flex items-center justify-between px-1 pb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground"
        >
          <span>Itens</span>
          <span>{{ ticket.status_label }}</span>
        </div>
        <ul class="flex flex-col divide-y divide-border/50">
          <li
            v-for="(item, idx) in ticket.items"
            :key="idx"
            class="flex items-start gap-3 p-3"
          >
            <span class="shrink-0 text-lg font-bold leading-snug tabular-nums">{{ item.qty }}×</span>
            <div class="min-w-0 flex-1">
              <p class="break-words text-lg font-bold leading-snug">{{ item.name }}</p>
              <p
                v-if="item.notes"
                class="mt-1 flex items-start gap-1.5 text-base font-semibold leading-snug text-foreground/85"
              >
                <Icon name="lucide:corner-down-right" class="mt-1 size-4 shrink-0 opacity-60" />
                <span class="min-w-0 whitespace-pre-wrap break-words">{{ item.notes }}</span>
              </p>
              <p
                v-if="item.stock_warning"
                class="mt-1 flex items-start gap-1.5 text-sm font-semibold leading-snug"
              >
                <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
                <span class="min-w-0 break-words">{{ item.stock_warning }}</span>
              </p>
            </div>
          </li>
        </ul>
      </div>
    </div>
    </template>
  </NuxtModal>
</template>
