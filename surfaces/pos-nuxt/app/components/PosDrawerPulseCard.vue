<script setup lang="ts">
// O cartão "Dinheiro da comanda" do tablet (pos-tablet-fluxo.jpg, passo 3).
//
// A comanda fechou na mesa em dinheiro; o tablet guarda este cartão até o
// atendente chegar à gaveta. O botão abre a gaveta do Balcão pelo relay e o
// estado diz o que aconteceu, sem fingir sucesso. A autoria é de quem está
// neste dispositivo; o Balcão registra a abertura no livro-caixa.
import {
  drawerOpeningDone,
  drawerOpeningFailed,
  type DrawerOpeningState,
  OPEN_DRAWER_HINT,
  openDrawerLabel,
  pendingCashLine,
  pendingCashTitle,
  type PendingCashDrawer,
} from "~/presentation/drawerOpening";

const props = defineProps<{
  pending: PendingCashDrawer;
  terminalLabel: string;
  /** O estado do pedido de abrir, quando ESTE cartão é o que está abrindo. */
  state: DrawerOpeningState;
  message: string;
  /** Aviso do servidor quando o agente do Balcão sumiu há pouco ("" = respondendo). */
  relayWarning?: string;
  /** Compacto: a faixa no topo da venda, depois da "Nova venda". */
  compact?: boolean;
}>();

const emit = defineEmits<{ open: []; dismiss: [] }>();

const title = computed(() => pendingCashTitle(props.pending));
const line = computed(() => pendingCashLine(props.pending, props.terminalLabel));
const label = computed(() => openDrawerLabel(props.terminalLabel));
const sending = computed(() => props.state === "sending");
const failed = computed(() => drawerOpeningFailed(props.state));
const done = computed(() => drawerOpeningDone(props.state));
/**
 * Dispensar o cartão é sempre possível (dono, 10/10/2026: "tem que ter um
 * dismiss"). Antes ele só aparecia depois de uma falha, e o cartão ficava de pé
 * no topo de toda venda seguinte quando o dinheiro já tinha ido para a gaveta
 * por outro caminho. Depois de uma falha o gesto tem nome próprio: abriu na chave.
 */
const dismissLabel = computed(() => (failed.value || props.state === "uncertain" ? "Abri com a chave" : "Visto"));
</script>

<template>
  <section
    class="grid w-full gap-3 rounded-lg border-2 border-primary/50 bg-card p-4 text-left"
    :class="compact ? 'max-w-none' : 'max-w-md'"
    data-drawer-pulse-card
    :data-state="state"
  >
    <header class="flex items-start gap-3">
      <div class="grid size-10 shrink-0 place-items-center rounded-md bg-primary/10 text-primary">
        <Icon name="lucide:banknote" class="size-5" />
      </div>
      <div class="min-w-0">
        <p class="text-base font-semibold">{{ title }}</p>
        <p class="text-sm text-muted-foreground">{{ line }}</p>
      </div>
    </header>

    <ol v-if="!compact" class="grid gap-1.5 text-sm">
      <li class="flex items-center gap-2">
        <Icon name="lucide:circle-check" class="size-4 text-success" />
        Recebido na mesa
      </li>
      <li class="flex items-center gap-2">
        <span class="grid size-4 place-items-center rounded-full bg-muted text-xs font-semibold">2</span>
        Na frente da gaveta, abra por aqui
      </li>
    </ol>

    <UiButton
      size="lg"
      class="h-12 w-full gap-2 text-base"
      :disabled="sending || done"
      :aria-busy="sending ? 'true' : undefined"
      data-open-drawer
      @click="emit('open')"
    >
      <Icon :name="sending ? 'lucide:loader-circle' : 'lucide:archive'" class="size-5" :class="sending ? 'animate-spin' : ''" />
      {{ failed ? `Tentar de novo: ${label}` : label }}
    </UiButton>
    <p class="text-center text-xs text-muted-foreground">{{ OPEN_DRAWER_HINT }}</p>

    <p
      v-if="message"
      class="rounded-md px-3 py-2 text-sm"
      :class="done ? 'bg-success/10 text-success' : failed || state === 'uncertain' ? 'bg-destructive/10 text-destructive' : 'bg-muted text-foreground'"
      role="status"
      aria-live="polite"
      data-drawer-pulse-status
    >
      {{ message }}
    </p>
    <p v-else-if="relayWarning" class="rounded-md bg-warning/10 px-3 py-2 text-sm text-warning" role="status">
      {{ relayWarning }}
    </p>

    <div v-if="!compact" class="grid gap-1 rounded-md bg-muted/60 p-3 text-xs text-muted-foreground">
      <p class="flex items-start gap-1.5">
        <Icon name="lucide:hand" class="mt-0.5 size-3.5 shrink-0" />
        Nunca abre sozinha enquanto você está na mesa. A gaveta abre em segundos e o {{ terminalLabel }} registra quem abriu.
      </p>
      <p class="flex items-start gap-1.5">
        <Icon name="lucide:key-round" class="mt-0.5 size-3.5 shrink-0" />
        Sem energia, abra com a chave.
      </p>
    </div>
    <UiButton
      v-if="!done"
      variant="ghost"
      size="sm"
      class="justify-self-center text-muted-foreground"
      :disabled="sending"
      data-drawer-dismiss
      @click="emit('dismiss')"
    >
      {{ dismissLabel }}
    </UiButton>
  </section>
</template>
