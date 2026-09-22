<script setup lang="ts">
// Mais opções do Gestor → "A loja no iFood". Pedido literal do dono: não tão à vista,
// mas acessível pelo gestor. Fecha (pausa) o iFood por estratégia com a loja aberta
// — cozinha cheia, sem entregador — e retoma. Quem pausou, por quê e até quando
// ficam na tela. Some por inteiro enquanto a integração estiver desligada.
import {
  ifoodStatusLine,
  menuNeedsAttention,
  pauseTrail,
  refusedPauseLine,
} from "~/presentation/ifoodStore";

const REASON_PRESETS = ["Cozinha cheia", "Sem entregador", "Falta de produto"];

const { store, busy, pause, resume } = useIFoodStore();

const menuOpen = ref(false);
const dialogOpen = ref(false);
const duration = ref("");
const reason = ref("");

const visible = computed(() => Boolean(store.value?.enabled));
const attention = computed(() => menuNeedsAttention(store.value));
const statusLine = computed(() => (store.value ? ifoodStatusLine(store.value) : ""));
const refused = computed(() => (store.value ? refusedPauseLine(store.value) : ""));
const livePause = computed(() => store.value?.pause ?? null);
const canResume = computed(() =>
  Boolean(livePause.value && livePause.value.state !== "pending_remove"),
);
const canConfirm = computed(() => {
  const option = store.value?.options.find((item) => item.key === duration.value);
  return Boolean(option?.enabled && reason.value.trim());
});

function openPauseDialog() {
  menuOpen.value = false;
  duration.value = "";
  reason.value = "";
  dialogOpen.value = true;
}

async function confirmPause() {
  if (!canConfirm.value || busy.value) return;
  if (await pause(duration.value, reason.value.trim())) dialogOpen.value = false;
}

async function confirmResume() {
  menuOpen.value = false;
  await resume();
}
</script>

<template>
  <div v-if="visible" class="relative" data-ifood-store-menu>
    <button
      type="button"
      class="relative grid size-control place-items-center rounded-md border text-muted-foreground transition hover:bg-accent hover:text-foreground"
      aria-haspopup="menu"
      :aria-expanded="menuOpen"
      aria-label="Mais opções"
      title="Mais opções"
      @click="menuOpen = !menuOpen"
    >
      <Icon name="lucide:ellipsis-vertical" class="size-4" />
      <span v-if="attention" class="absolute -right-1 -top-1 size-2 rounded-full bg-warning" aria-hidden="true" />
    </button>

    <div v-if="menuOpen" class="fixed inset-0 z-40" @click="menuOpen = false" />
    <div
      v-if="menuOpen && store"
      class="absolute right-0 z-50 mt-1 w-80 overflow-hidden rounded-md border bg-card shadow-lg"
      role="menu"
      aria-label="Mais opções"
    >
      <div class="border-b px-3 py-2.5">
        <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">A loja no iFood</p>
        <p class="mt-1 text-sm font-semibold text-foreground" data-ifood-status>{{ statusLine }}</p>
        <p v-if="livePause" class="mt-0.5 text-xs text-muted-foreground">{{ pauseTrail(livePause) }}</p>
        <p v-if="refused" class="mt-1 text-xs text-destructive" role="alert" data-ifood-refused>{{ refused }}</p>
        <ul v-if="store.diverges && store.ifood_problems.length" class="mt-1 flex flex-col gap-0.5 text-xs text-amber-700 dark:text-amber-300">
          <li v-for="(problem, i) in store.ifood_problems" :key="i">{{ problem }}</li>
        </ul>
      </div>

      <template v-if="store.can_pause">
        <button
          v-if="livePause"
          type="button"
          role="menuitem"
          class="flex min-h-control w-full items-center gap-2 px-3 py-2 text-left text-sm transition hover:bg-accent disabled:opacity-50"
          :disabled="!canResume || busy"
          data-ifood-resume
          @click="confirmResume"
        >
          <Icon name="lucide:play" class="size-4" />
          Voltar a receber pedidos do iFood
        </button>
        <button
          v-else
          type="button"
          role="menuitem"
          class="flex min-h-control w-full items-center gap-2 px-3 py-2 text-left text-sm transition hover:bg-accent disabled:opacity-50"
          :disabled="!store.shop_open || busy"
          :title="store.shop_open ? '' : 'A loja já está fechada: o iFood fecha junto.'"
          data-ifood-pause
          @click="openPauseDialog"
        >
          <Icon name="lucide:pause" class="size-4" />
          Pausar o iFood…
        </button>
      </template>
      <p v-else class="px-3 py-2 text-xs text-muted-foreground">Pausar o iFood é permissão de gerente.</p>
    </div>

    <UiDialog :open="dialogOpen" @update:open="(value: boolean) => { if (!busy) dialogOpen = value; }">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Pausar o iFood</UiDialogTitle>
          <UiDialogDescription>
            O iFood deixa de receber pedidos novos pelo tempo escolhido. O balcão e a loja online
            continuam abertos, e os pedidos do iFood já aceitos seguem normalmente.
          </UiDialogDescription>
        </UiDialogHeader>

        <fieldset class="flex flex-col gap-1.5">
          <legend class="mb-1 text-sm font-medium">Por quanto tempo</legend>
          <label
            v-for="option in store?.options ?? []"
            :key="option.key"
            class="flex min-h-control items-center gap-2 rounded-md border px-3 py-1.5 text-sm"
            :class="option.enabled ? 'cursor-pointer hover:bg-accent' : 'opacity-50'"
            :title="option.reason"
          >
            <input v-model="duration" type="radio" name="ifood-pause-duration" :value="option.key" :disabled="!option.enabled">
            {{ option.label }}
          </label>
        </fieldset>

        <div class="flex flex-col gap-1.5">
          <span class="text-sm font-medium">Motivo</span>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="preset in REASON_PRESETS"
              :key="preset"
              type="button"
              :aria-pressed="reason === preset"
              class="min-h-control min-w-control rounded-full border px-3 py-1 text-xs font-medium transition hover:bg-accent"
              :class="reason === preset ? 'border-primary bg-primary/10 text-primary' : 'text-muted-foreground'"
              @click="reason = preset"
            >
              {{ preset }}
            </button>
          </div>
          <textarea
            v-model="reason"
            rows="2"
            maxlength="200"
            placeholder="Por que o iFood vai pausar…"
            class="min-h-control w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
            aria-label="Motivo da pausa"
          />
        </div>

        <UiDialogFooter>
          <button type="button" class="min-h-control min-w-control rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" :disabled="busy" @click="dialogOpen = false">
            Voltar
          </button>
          <button
            type="button"
            :disabled="busy || !canConfirm"
            class="min-h-action min-w-action rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            data-ifood-pause-confirm
            @click="confirmPause"
          >
            Pausar o iFood
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </div>
</template>
