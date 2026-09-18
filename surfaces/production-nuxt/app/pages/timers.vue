<script setup lang="ts">
// TIMERS — a página dos lembretes da bancada (pedido do Pablo, 18/09/2026).
//
// Era um diálogo no cabeçalho; virou tela porque o gesto de toda hora não cabia
// num modal: no fournil o timer não é uma coisa que se abre e fecha, é uma
// coisa que fica à vista. A tela tem dois blocos, nesta ordem:
//
// 1. DISPARAR — a fileira de etiquetas. UM toque na etiqueta já arma o timer
//    com a duração dela: zero digitação, zero confirmação. É o caminho
//    principal e por isso é o bloco mais gordo da tela. "Novo timer" fica no
//    fim da mesma fileira, porque ele é o caso que a fileira não previu.
// 2. EM ANDAMENTO — os cards, na linguagem do KDS. Toque no corpo faz a única
//    coisa que faz sentido no estado do card (ver presentation/timers.ts).
//
// A lista de etiquetas é do servidor; o timer continua sendo do dispositivo. Rede
// caída não apaga lembrete correndo, e a fileira em cache ainda dispara.
import { filterTags, minutesLabel } from "~/presentation/timers";
import type { TimerTagProjection } from "~/composables/useTimerTags";

const timers = useFloorTimers();
const { tags, pending, forbidden, refresh, createTag, saving } = useTimerTags();

const query = ref("");
const creating = ref(false);

// O contador vem do localStorage — o servidor não o conhece —, então o
// primeiro render do cliente precisa BATER com o SSR (0) e só depois de montar
// mostrar o real. Mesmo cuidado do botão no cabeçalho.
const hydrated = ref(false);
onMounted(() => (hydrated.value = true));
const entries = computed(() => (hydrated.value ? timers.entries.value : []));
const activeCount = computed(() => (hydrated.value ? timers.activeCount.value : 0));

const visibleTags = computed(() => filterTags(tags.value, query.value));

/** O caminho principal: um toque, e o tempo já está correndo. */
function fireTag(tag: TimerTagProjection) {
  timers.create(tag.minutes, { label: tag.label });
  useSonner.success(`${tag.label} · ${minutesLabel(tag.minutes)}`);
}

async function startFree(payload: {
  minutes: number;
  label: string;
  saveAsTag: boolean;
}) {
  // O timer PRIMEIRO: guardar a etiqueta é um extra, e um extra que falha não
  // pode levar junto o lembrete que a pessoa pediu.
  timers.create(payload.minutes, { label: payload.label });
  creating.value = false;
  if (!payload.saveAsTag) return;
  const result = await createTag(payload.label, payload.minutes);
  if (!result.ok) return;
  useSonner.success(
    result.created
      ? `“${result.tag?.label}” entrou na fileira do fournil.`
      : `“${result.tag?.label}” já estava na fileira.`,
  );
}

useHead({ title: "Timers" });
</script>

<template>
  <main class="flex min-h-screen flex-col">
    <ProductionHeader
      v-model:query="query"
      title="Timers"
      :count="activeCount"
      count-label="ativos"
      :pending="pending"
      @refresh="refresh()"
    />

    <section class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <!-- ── 1. Disparar ────────────────────────────────────────────────── -->
      <h2 class="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
        Disparar
      </h2>
      <div class="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
        <button
          v-for="tag in visibleTags"
          :key="tag.ref"
          type="button"
          class="flex min-h-28 flex-col items-start justify-between rounded-lg border bg-card p-4 text-left transition hover:bg-accent active:translate-y-px"
          :aria-label="`Disparar ${tag.label}, ${minutesLabel(tag.minutes)}`"
          @click="fireTag(tag)"
        >
          <span class="w-full truncate text-lg font-semibold leading-tight">{{
            tag.label
          }}</span>
          <span class="text-3xl font-bold tabular-nums text-muted-foreground">{{
            minutesLabel(tag.minutes)
          }}</span>
        </button>

        <button
          type="button"
          class="flex min-h-28 flex-col items-start justify-between rounded-lg border border-dashed bg-card p-4 text-left transition hover:bg-accent active:translate-y-px"
          @click="creating = true"
        >
          <span class="text-lg font-semibold leading-tight">Novo timer</span>
          <span class="flex items-center gap-1.5 text-sm text-muted-foreground">
            <Icon name="lucide:plus" class="size-4" /> Escolher os minutos
          </span>
        </button>
      </div>

      <p
        v-if="forbidden"
        class="mb-6 rounded-md border border-dashed p-3 text-sm text-muted-foreground"
      >
        Sem acesso à fileira de etiquetas. O timer com minutos digitados continua
        funcionando.
      </p>
      <p
        v-else-if="!tags.length && !pending"
        class="mb-6 rounded-md border border-dashed p-3 text-sm text-muted-foreground"
      >
        Nenhuma etiqueta cadastrada ainda. Crie a primeira em “Novo timer”,
        marcando “Guardar como etiqueta”.
      </p>
      <p
        v-else-if="!visibleTags.length"
        class="mb-6 rounded-md border border-dashed p-3 text-sm text-muted-foreground"
      >
        Nenhuma etiqueta com “{{ query }}”.
      </p>

      <!-- ── 2. Em andamento ───────────────────────────────────────────── -->
      <h2 class="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
        Em andamento
      </h2>
      <ul
        v-if="entries.length"
        class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4"
      >
        <FloorTimerCard
          v-for="entry in entries"
          :key="entry.key"
          :entry="entry"
          :remaining="timers.remainingLabel(entry.key)"
          @seen="timers.seen(entry.key)"
          @clear="timers.clear(entry.key)"
          @extend="(extra: number) => timers.extend(entry.key, extra)"
        />
      </ul>
      <p
        v-else
        class="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground"
      >
        Nenhum timer correndo. Toque numa etiqueta acima para começar.
      </p>
    </section>

    <FloorTimerCreateDialog
      v-model:open="creating"
      :last-minutes="timers.lastMinutes.value"
      :tags="tags"
      :saving-tag="saving"
      @start="startFree"
    />
  </main>
</template>
