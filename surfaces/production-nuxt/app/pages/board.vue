<script setup lang="ts">
// LOTES — o painel Solari em modo KIOSK (refino Pablo):
// · página à parte, sem o chrome do backstage (o link de entrada vive na
//   aba "Painel" da UI normal); botão de tela cheia para a TV;
// · tipografia Oswald (grotesca condensada de painel), DUAS escalas apenas:
//   display (título · relógio) e linha (todas as palhetas);
// · NOME do produto nas palhetas (SKU saiu); quantidade com UN embutido
//   ("12 UN" — doze o quê? unidades); horário como estava;
// · atrasado não pisca: as palhetas RE-GIRAM periodicamente até o mesmo
//   valor, como os painéis mecânicos reais fazem;
// · ordem de aeroporto: cronológica pelo horário — status muda cor, nunca
//   posição; confirmados saem pelo TTL.
import type { ForecastStatus } from "~/types/production";
import {
  fullDateLabel,
  isStale,
  isoForOffset,
  resolveDayRollover,
} from "~/presentation/production";
import {
  periodAnchor,
  periodOfDay,
  type PeriodSelection,
} from "../../../operator-kit/app/presentation/dates";

const { rows, selectedDate, pending, error } = useProductionForecast();
// Kiosk aberto o dia todo: se o sinal cair, mantém o último quadro no ar (dado velho
// visível > tela em branco) e acende um aviso discreto de "sem sinal".
const stale = computed(() =>
  isStale({ error: !!error.value, hasData: rows.value.length > 0 }),
);
const sound = useFlapClack();

// Paginação de aeroporto: N linhas fixas (medidas na tela), excedente vira
// páginas em ciclo de 12s — manhã cheia não rola, VIRA, com clac-storm.
const pages = useBoardPages(rows);
function setBoardList(el: unknown) {
  pages.listEl.value = (el as HTMLElement | null) ?? null;
}

// ── Data: seletor discreto (a TV vive em Hoje; o vendedor consulta Amanhã) ──
// Reativo: à meia-noite a TV precisa VIRAR o dia sozinha (senão amanhece nas
// lotes de ontem). O tick do relógio (abaixo) chama rollDay() a cada segundo.
const todayISO = ref(isoForOffset(0));
function rollDay(): void {
  const r = resolveDayRollover(todayISO.value, selectedDate.value);
  if (!r.rolled) return;
  todayISO.value = r.todayISO;
  selectedDate.value = r.selectedDate;
}
// O "Período" do kit em Dia (Tipo 2): ‹ › andam um dia; o toque destrava o som.
const period = computed<PeriodSelection>({
  get: () => periodOfDay("day", selectedDate.value, todayISO.value),
  set: (next) => {
    sound.unlock();
    selectedDate.value = periodAnchor(next, todayISO.value);
  },
});
// ── Relógio vivo ────────────────────────────────────────────────────────────
const clock = ref("--:--");
let clockTimer: ReturnType<typeof setInterval> | null = null;

// ── O tique do atraso: re-gira as palhetas do status a cada 25s ────────────
const respinTick = ref(0);
let respinTimer: ReturnType<typeof setInterval> | null = null;

onMounted(() => {
  sound.unlock();
  const tick = () => {
    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    clock.value = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
    rollDay(); // vira o dia à meia-noite (a TV não amanhece em ontem)
  };
  tick();
  clockTimer = setInterval(tick, 1000);
  respinTimer = setInterval(() => {
    respinTick.value++;
  }, 25_000);
});
onUnmounted(() => {
  if (clockTimer) clearInterval(clockTimer);
  if (respinTimer) clearInterval(respinTimer);
});

// ── Tela cheia (kiosk de verdade na TV) ─────────────────────────────────────
// A mesma capability que governa o app mantém a semântica progressiva: entrar
// continua exigindo o gesto da pessoa, e ausência/recusa da API nunca derruba o painel.
const kiosk = useKioskMode();
const isFullscreen = kiosk.isFullscreen;
async function toggleFullscreen() {
  sound.unlock();
  if (isFullscreen.value) await kiosk.exit();
  else await kiosk.enter();
}

// ── Status → cor (uma cor, um significado) ─────────────────────────────────
const STATUS_TONE: Record<ForecastStatus, string> = {
  scheduled: "tone-neutral",
  in_progress: "tone-cyan",
  delayed: "tone-amber",
  arrived: "tone-green",
};

const NAME_CHARS = 22; // maior nome atual: "Pão de Forma Artesanal"
const QTY_CHARS = 6; // "999 UN"
const STATUS_CHARS = 10; // CONFIRMADO
</script>

<template>
  <main class="board flex min-h-screen flex-col">
    <header class="flex flex-col gap-2 px-4 pb-2 pt-4 md:px-8">
      <div class="board-labels flex flex-wrap items-center gap-x-3 gap-y-2">
        <span>{{ fullDateLabel(selectedDate) }}</span>
        <span
          v-if="stale"
          role="status"
          aria-live="polite"
          class="inline-flex items-center gap-1.5 tone-amber"
          title="Sem sinal: mostrando o último quadro"
        >
          <Icon name="lucide:wifi-off" class="size-4" />
          <span>sem sinal</span>
        </span>
        <span aria-hidden="true">·</span>
        <!-- O controle de período da casa, vestido com a paleta do painel. -->
        <OperatorPeriodPicker
          v-model="period"
          class="board-period"
          :presets="['day']"
          :today="todayISO"
          label="Data"
          align="start"
        />
        <div class="ml-auto flex items-center gap-2.5">
          <!-- Teclas do kiosk (som e tela cheia): o botão canônico vestido com a pele do
               letreiro (`.board-key`), sem o desenho do shell operador. -->
          <NuxtButton
            size="xl"
            color="neutral"
            variant="ghost"
            square
            class="board-key"
            :icon="sound.enabled.value ? 'i-lucide-volume-2' : 'i-lucide-volume-x'"
            :aria-label="
              sound.enabled.value
                ? 'Silenciar palhetas'
                : 'Ativar som das palhetas'
            "
            @click="sound.toggle()"
          />
          <NuxtButton
            size="xl"
            color="neutral"
            variant="ghost"
            square
            class="board-key"
            :icon="isFullscreen ? 'i-lucide-minimize' : 'i-lucide-maximize'"
            :aria-label="isFullscreen ? 'Sair da tela cheia' : 'Tela cheia'"
            @click="toggleFullscreen()"
          />
        </div>
      </div>

      <div class="flex items-baseline justify-between gap-6">
        <h1 class="board-title">Lotes</h1>
        <ClientOnly>
          <SplitFlap :value="clock" :chars="5" class="board-display" />
        </ClientOnly>
      </div>
    </header>

    <section
      class="flex min-h-0 flex-1 flex-col overflow-hidden px-4 pb-4 pt-4 md:px-8"
    >
      <p v-if="pending && !rows.length" class="board-labels py-8">
        Carregando…
      </p>
      <p v-else-if="error && !rows.length" class="board-labels py-8">
        Sinal perdido. Reconectando…
      </p>

      <div
        v-else-if="!rows.length"
        class="board-labels grid place-items-center gap-2 py-24 text-center"
      >
        <Icon name="lucide:tower-control" class="size-9" />
        <p>Nenhum lote programado para esta data.</p>
      </div>

      <template v-else>
        <div :ref="setBoardList" class="min-h-0 flex-1 overflow-hidden">
          <TransitionGroup
            tag="div"
            name="board-row"
            class="relative flex flex-col gap-1.5"
          >
            <article
              v-for="row in pages.visible.value"
              :key="row.ref"
              data-board-row
              class="board-row"
              :aria-label="`${row.recipe_name}: ${row.qty} unidades às ${row.eta_display}, ${row.status_label}`"
            >
              <SplitFlap
                :value="row.recipe_name"
                :chars="NAME_CHARS"
                class="board-flap min-w-0"
              />
              <SplitFlap
                :value="`${row.qty} UN`"
                :chars="QTY_CHARS"
                align="right"
                class="board-flap"
              />
              <SplitFlap
                :value="row.eta_display"
                :chars="5"
                align="right"
                class="board-flap"
                :class="
                  row.status === 'delayed'
                    ? 'tone-amber'
                    : row.eta_is_actual
                      ? 'tone-green'
                      : ''
                "
              />
              <SplitFlap
                :value="row.status_label"
                :chars="STATUS_CHARS"
                align="right"
                class="board-flap"
                :class="STATUS_TONE[row.status]"
                :pulse="row.status === 'delayed' ? respinTick : 0"
              />
            </article>
          </TransitionGroup>
        </div>

        <div
          v-if="pages.pageCount.value > 1"
          class="flex shrink-0 items-center justify-center gap-2.5 pt-3"
          role="group"
          aria-label="Páginas do painel"
        >
          <!-- Pontos de paginação: navegação espacial do letreiro. O botão canônico,
               com a pele do ponto (`.board-pagedot`) no lugar do desenho do shell. -->
          <NuxtButton
            v-for="p in pages.pageCount.value"
            :key="p"
            color="neutral"
            variant="ghost"
            square
            class="board-pagedot"
            :class="{ 'board-pagedot--active': pages.page.value === p - 1 }"
            :aria-label="`Página ${p}`"
            :aria-pressed="pages.page.value === p - 1"
            @click="
              sound.unlock();
              pages.goTo(p - 1);
            "
          />
        </div>
      </template>
    </section>
  </main>
</template>

<style scoped>
/* ── A pele do Solari: noturna por natureza, alheia ao tema do app ── */
.board {
  /* V4-PROD: os tokens e a tipografia da suíte no escuro (os do \`.dark\` do
     operator-theme: marrom quase-preto, cartão, borda, creme, o âmbar do selo),
     fixos aqui porque o Letreiro é noturno por natureza, alheio ao tema do app. */
  --board-bg: #1a110c;
  --board-panel: #2b1d16;
  --board-line: #463528;
  --board-text: #f0e6d2;
  --board-dim: #c2ae96;
  --board-green: #7eb26e;
  --board-amber: #f2c46b;
  --board-cyan: #6fa0c0;

  /* DUAS escalas, e só: display (título · relógio) e linha (palhetas). */
  --scale-display: clamp(1.9rem, 4vw, 2.6rem);
  --scale-row: clamp(1.05rem, 2vw, 1.5rem);

  background:
    radial-gradient(120% 90% at 50% 0%, #2b1d16 0%, var(--board-bg) 60%),
    var(--board-bg);
  color: var(--board-text);
  font-family: var(--font-sans);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.01em;
}

.board-title {
  font-size: var(--scale-display);
  font-weight: 600;
  line-height: 1;
  letter-spacing: -0.01em;
}
.board-display {
  font-size: var(--scale-display);
  font-weight: 600;
}
.board-flap {
  font-size: var(--scale-row);
  font-weight: 500;
}

.board-labels {
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--board-dim);
}

/* O controle do kit desenha com os tokens da casa; aqui eles viram os do painel. */
.board-period {
  --background: var(--board-panel);
  --card: var(--board-panel);
  --foreground: var(--board-text);
  --muted: var(--board-bg);
  --muted-foreground: var(--board-dim);
  --border: var(--board-line);
  --accent: var(--board-line);
  --primary: var(--board-text);
  --primary-foreground: var(--board-bg);
  --ring: var(--board-text);
  letter-spacing: normal;
  text-transform: none;
}

.board-key {
  display: grid;
  place-items: center;
  width: 2.75rem;
  height: 2.75rem;
  padding: 0;
  border-radius: 0.5rem;
  border: 1px solid var(--board-line);
  background: var(--board-panel);
  color: var(--board-dim);
  transition:
    color 150ms,
    border-color 150ms;
}
.board-key:hover {
  color: var(--board-text);
  border-color: var(--board-dim);
  background: var(--board-panel);
}
.board-key :deep(.iconify),
.board-key :deep(svg) {
  width: 1rem;
  height: 1rem;
}

.board-pagedot {
  width: 0.45rem;
  height: 0.45rem;
  min-width: 0;
  padding: 0;
  border-radius: 9999px;
  background: var(--board-line);
  transition:
    background 200ms,
    transform 200ms;
}
.board-pagedot:hover {
  background: var(--board-line);
}
.board-pagedot--active,
.board-pagedot--active:hover {
  background: var(--board-text);
  transform: scale(1.25);
}

/* ── Grade: TV = uma linha; celular = nome em cima, mostradores embaixo ── */
.board-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto;
  gap: 1.25rem;
  align-items: center;
  border: 1px solid var(--board-line);
  border-radius: 0.75rem;
  background: var(--board-panel);
  padding: 0.7rem 1rem;
}

.tone-green :deep(.flap-cell) {
  color: var(--board-green);
}
.tone-amber :deep(.flap-cell) {
  color: var(--board-amber);
}
.tone-cyan :deep(.flap-cell) {
  color: var(--board-cyan);
}
.tone-neutral :deep(.flap-cell) {
  color: var(--board-text);
}

/* Entrada/saída de lotes (lote novo; confirmado expirou o TTL). */
.board-row-enter-active,
.board-row-leave-active {
  transition:
    opacity 400ms ease,
    transform 400ms ease;
}
.board-row-enter-from {
  opacity: 0;
  transform: translateY(-0.5rem);
}
.board-row-leave-to {
  opacity: 0;
  transform: translateY(0.5rem);
}
.board-row-leave-active {
  position: absolute;
  width: 100%;
}

@media (max-width: 700px) {
  .board-row {
    grid-template-columns: auto auto auto;
    grid-template-areas:
      "nome nome nome"
      "qtd horario status";
    justify-content: space-between;
    row-gap: 0.6rem;
  }
  .board-row > :nth-child(1) {
    grid-area: nome;
  }
  .board-row > :nth-child(2) {
    grid-area: qtd;
  }
  .board-row > :nth-child(3) {
    grid-area: horario;
  }
  .board-row > :nth-child(4) {
    grid-area: status;
  }
  .board {
    --scale-row: 0.92rem;
  }
}
</style>
