<script setup lang="ts">
// LOTES — o painel Solari em modo KIOSK (refino Pablo):
// · página à parte, sem o chrome do backstage (o link de entrada vive na
//   aba "Painel" da UI normal); botão de tela cheia para a TV;
// · tipografia Oswald (grotesca condensada de painel), DUAS escalas apenas:
//   display (título · relógio · aviso) e linha (todas as palhetas). As duas
//   crescem com a ALTURA da tela, sem teto de tablet: numa TV de 1080 a linha
//   se lê a dois metros (WP-F04). A largura só limita quando os nomes do dia
//   não caberiam;
// · NOME do produto nas palhetas (SKU saiu), na largura do maior nome do dia;
//   quantidade com a unidade que a projeção traz ("12 UN", "18,5 KG");
// · sem conexão, o último quadro fica no ar e o aviso, com a hora da leitura,
//   é a maior coisa da tela;
// · atrasado não pisca: as palhetas RE-GIRAM periodicamente até o mesmo
//   valor, como os painéis mecânicos reais fazem;
// · ordem de aeroporto: cronológica pelo horário — status muda cor, nunca
//   posição; confirmados saem pelo TTL.
import type {
  ForecastStatus,
  ProductionForecastProjection,
} from "~/types/production";
import {
  BOARD_ETA_CHARS,
  BOARD_STATUS_CHARS,
  STORE_TIME_ZONE,
  boardNameChars,
  boardNameLines,
  boardQtyChars,
  boardQtyLabel,
  boardRowSpoken,
  boardStaleNotice,
  forecastTimeTone,
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
import { formatClock } from "../../../operator-kit/app/presentation/clock";

const { forecast, selectedDate, pending, error } = useProductionForecast();
// Kiosk aberto o dia todo: se a conexão cair, mantém o último quadro no ar (dado
// velho visível > tela em branco). O `useFetch` zera o dado quando a leitura falha,
// então o Letreiro guarda a última leitura boa; trocar de data a descarta.
const lastRead = shallowRef<ProductionForecastProjection | null>(null);
watch(
  forecast,
  (next) => {
    if (next) lastRead.value = next;
  },
  { immediate: true },
);
watch(selectedDate, () => {
  lastRead.value = null;
});
const rows = computed(() => lastRead.value?.rows ?? []);
const stale = computed(() =>
  isStale({ error: !!error.value, hasData: rows.value.length > 0 }),
);
const staleNotice = computed(() =>
  boardStaleNotice(lastRead.value?.generated_at_display ?? ""),
);
const sound = useFlapClack();

// Paginação de aeroporto: N linhas fixas (medidas na tela), excedente vira
// páginas em ciclo de 12s — manhã cheia não rola, VIRA, com clac-storm.
const pages = useBoardPages(
  rows,
  (row) => boardNameLines(row.recipe_name, NAME_CHARS.value).length,
);
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
    // O relógio da padaria, não o do dispositivo (TV configurada em outro fuso).
    clock.value = formatClock(new Date(), STORE_TIME_ZONE) || "--:--";
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

// ── Status → cor do tempo (o mesmo mapa do Gestor e da Cozinha) ────────────
const TIME_TONE_CLASS: Record<ReturnType<typeof forecastTimeTone>, string> = {
  late: "tone-red",
  warning: "tone-amber",
  neutral: "tone-neutral",
  ready: "tone-green",
};
const statusToneClass = (status: ForecastStatus) =>
  TIME_TONE_CLASS[forecastTimeTone(status)];

// As colunas medem o dia: o maior nome e a maior quantidade cabem inteiros.
const NAME_CHARS = computed(() => boardNameChars(rows.value));
const QTY_CHARS = computed(() => boardQtyChars(rows.value));
const STATUS_CHARS = BOARD_STATUS_CHARS;
const ETA_CHARS = BOARD_ETA_CHARS;
// A escala divide a largura útil pelo total de palhetas da linha (TV: uma linha só;
// celular: o nome em cima, os três mostradores embaixo). Só depois de montar: a
// hidratação do Vue não corrige `style` divergente do HTML do servidor, e a
// escala medida lá (sem as linhas do dia) ficaria valendo na TV.
const scaleReady = ref(false);
onMounted(() => {
  scaleReady.value = true;
});
const boardScale = computed(() => !scaleReady.value ? {} : ({
  "--row-chars": NAME_CHARS.value + QTY_CHARS.value + ETA_CHARS + STATUS_CHARS,
  "--row-chars-narrow": Math.max(
    NAME_CHARS.value,
    QTY_CHARS.value + ETA_CHARS + STATUS_CHARS + 3,
  ),
}));
</script>

<template>
  <main class="board flex h-dvh flex-col overflow-hidden" :style="boardScale">
    <!-- Altura da tela, nunca mais: o kiosk não rola, o excedente vira página. -->
    <header class="flex flex-col gap-2 px-4 pb-2 pt-4 md:px-8">
      <div class="board-labels flex flex-wrap items-center gap-x-3 gap-y-2">
        <NuxtButton
          to="/"
          color="neutral"
          variant="ghost"
          icon="i-lucide-arrow-left"
          aria-label="Voltar à produção"
          title="Voltar à produção"
          class="board-key"
        />
        <span>{{ fullDateLabel(selectedDate) }}</span>
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
        <h1 class="board-title">Letreiro</h1>
        <ClientOnly>
          <SplitFlap :value="clock" :chars="5" class="board-display" />
        </ClientOnly>
      </div>
    </header>

    <section
      class="flex min-h-0 flex-1 flex-col overflow-hidden px-4 pb-4 pt-4 md:px-8"
    >
      <!-- Sem conexão: a maior coisa da tela, primeiro conteúdo abaixo do topo,
           com a hora da leitura que continua no ar. Volta sozinho quando a
           leitura seguinte dá certo. -->
      <div
        v-if="stale"
        role="alert"
        data-board-stale
        class="board-stale mb-4 flex shrink-0 items-center gap-[0.5em]"
      >
        <Icon name="lucide:wifi-off" class="board-stale-icon shrink-0" />
        <span>{{ staleNotice }}</span>
      </div>

      <p v-if="pending && !rows.length" class="board-labels py-8">
        Carregando…
      </p>
      <p v-else-if="error && !rows.length" class="board-labels py-8">
        Sem conexão. Tentando ler de novo…
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
              :data-board-lines="boardNameLines(row.recipe_name, NAME_CHARS).length"
              class="board-row"
              :aria-label="boardRowSpoken(row)"
            >
              <div data-board-name class="board-name flex min-w-0 flex-col">
                <SplitFlap
                  v-for="(line, index) in boardNameLines(row.recipe_name, NAME_CHARS)"
                  :key="index"
                  :value="line"
                  :chars="NAME_CHARS"
                  class="board-flap min-w-0"
                />
              </div>
              <SplitFlap
                :value="boardQtyLabel(row.qty, row.unit)"
                :chars="QTY_CHARS"
                align="right"
                class="board-flap"
              />
              <SplitFlap
                :value="row.eta_display"
                :chars="ETA_CHARS"
                align="right"
                class="board-flap"
                :class="
                  row.status === 'delayed'
                    ? 'tone-red'
                    : 'tone-neutral'
                "
              />
              <SplitFlap
                :value="row.status_label"
                :chars="STATUS_CHARS"
                align="right"
                class="board-flap"
                :class="statusToneClass(row.status)"
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
            :class="{ 'board-pagedot-current': pages.page.value === p - 1 }"
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

  /* DUAS escalas, e só: display (título · relógio · aviso) e linha (palhetas).
     Crescem com a altura da tela (5vh: 54px numa TV de 1080, contra os 24px do teto
     antigo). A largura entra só como limite: o total de palhetas da linha
     (`--row-chars`, medido no dia) × 0,87em (célula + vão) mais a moldura fixa
     (margens, bordas e vãos entre colunas, ~11rem) cabe em 100vw. */
  --row-chars: 42;
  --row-chars-narrow: 24;
  --scale-display: clamp(1.9rem, 6.5vh, 5rem);
  --scale-row: max(
    1rem,
    min(5vh, calc((100vw - 11rem) / (var(--row-chars) * 0.87)))
  );
  --scale-label: clamp(0.85rem, 1.9vh, 1.4rem);

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
.board-name {
  gap: 0.12em;
  font-size: var(--scale-row);
}
.board-flap {
  font-size: var(--scale-row);
  font-weight: 500;
}

.board-labels {
  font-size: var(--scale-label);
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

/* O aviso de conexão: alto contraste (âmbar cheio, letra escura), na escala do
   título, maior que qualquer palheta. */
.board-stale {
  font-size: var(--scale-display);
  font-weight: 600;
  line-height: 1.1;
  padding: 0.3em 0.5em;
  border-radius: 0.75rem;
  background: var(--board-amber);
  color: var(--board-bg);
}
.board-stale-icon {
  width: 1em;
  height: 1em;
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
.board-pagedot-current,
.board-pagedot-current:hover {
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
  padding: 0.5rem 1rem;
}

.tone-green :deep(.flap-cell) {
  color: var(--board-green);
}
.tone-amber :deep(.flap-cell) {
  color: var(--board-amber);
}
.tone-red :deep(.flap-cell) {
  color: var(--destructive);
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
    /* Celular: o nome ocupa a linha de cima sozinho; a escala divide a largura
       pela maior das duas linhas (nome, ou os três mostradores). */
    --scale-row: max(
      0.85rem,
      min(1.6rem, calc((100vw - 6rem) / (var(--row-chars-narrow) * 0.87)))
    );
    --scale-display: clamp(1.6rem, 8vw, 2.4rem);
  }
}
</style>
