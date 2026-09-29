<script setup lang="ts">
// ENCOMENDAS — a casa da seção. Chega-se aqui pela barra lateral (decisão do dono,
// 26/09): o item "Encomendas" é a porta, e esta página responde às quatro
// perguntas do balcão numa tela só.
//
//   Cliente veio buscar — o campo vem primeiro e nasce focado: "vim buscar a
//                         encomenda da Ana" é a zero gestos. Nome, telefone ou
//                         número do pedido (inclusive o do iFood); leitor de
//                         código que "digita" com o foco fora do campo cai nele.
//   A receber           — hoje e nos próximos 7 dias, cada total a um toque da
//                         lista já filtrada.
//   Hoje · Semana · Via Pedido – painel — os cards.
//
// A busca olha de uma semana atrás até um mês à frente (`searchRange`): quem
// chega hoje para buscar a encomenda de ontem é justamente o caso em que o
// balcão mais precisa achar o pedido. Enquanto há busca, o resultado toma o
// lugar dos cards.
import { useEventListener, watchDebounced } from "@vueuse/core";

import type { SessionTile } from "~/presentation/cash";
import { isoDate } from "~/presentation/orderTickets";
import {
  PREORDERS_SCOPE_NOTE,
  PREORDER_TILE_ROUTES,
  SEARCH_MIN_CHARS,
  canSearch,
  checkPaymentNotice,
  flattenDays,
  homeSummary,
  preorderCountLabel,
  preorderHomeTiles,
  searchEmptyMessage,
  searchRange,
  toReceiveLine,
} from "~/presentation/preorders";

useHead({ title: "Encomendas" });

const { pos, pending: posPending, refresh: refreshPos } = await usePosTerminal();

// ── A casa: a semana que começa hoje (a mesma leitura do selo da barra) ──
const ahead = usePosPreordersAhead();
const summary = computed(() => (ahead.list.value ? homeSummary(ahead.list.value) : null));
const tiles = computed(() => (summary.value ? preorderHomeTiles(summary.value) : []));
const checkNotice = computed(() => checkPaymentNotice(summary.value?.checkCount ?? 0));

function selectTile(tile: SessionTile) {
  const to = PREORDER_TILE_ROUTES[tile.key];
  if (to) void navigateTo(to);
}

// ── Cliente veio buscar ──
const today = isoDate(new Date());
const range = ref(searchRange(today));
const typed = ref("");
// O que foi perguntado ao servidor: a digitação assenta antes de virar busca.
const query = ref("");
watchDebounced(typed, (value) => { query.value = value.trim(); }, { debounce: 250 });

const searching = computed(() => typed.value.trim().length > 0);
const enabled = computed(() => canSearch(query.value));
const search = usePosPreorders({ key: "pos-preorders-search", range, query, enabled });
const results = computed(() => flattenDays(search.days.value));

const searchField = useTemplateRef<{ inputRef: HTMLInputElement | null }>("searchField");
onMounted(() => { void nextTick(() => searchField.value?.inputRef?.focus()); });

// Leitor de código (ou alguém digitando) com o foco fora de qualquer campo: a
// primeira tecla leva o foco ao campo de busca, e o resto da leitura cai nele.
useEventListener(typeof window === "undefined" ? null : window, "keydown", (event: KeyboardEvent) => {
  if (event.key.length !== 1 || event.ctrlKey || event.metaKey || event.altKey) return;
  const target = event.target as HTMLElement | null;
  if (target?.closest("input, textarea, select, [contenteditable='true'], [role='dialog']")) return;
  searchField.value?.inputRef?.focus();
});

function refreshAll() {
  void refreshPos();
  void ahead.refresh();
  if (enabled.value) void search.refresh();
}
</script>

<template>
  <PosPreordersShell :pos="pos" :pending="posPending || ahead.pending.value || search.pending.value" @refresh="refreshAll">
    <div class="grid gap-0.5">
      <h1 class="text-lg font-semibold">Encomendas</h1>
      <p class="text-sm text-muted-foreground">{{ PREORDERS_SCOPE_NOTE }}</p>
    </div>

    <!-- CLIENTE VEIO BUSCAR: o primeiro gesto da seção, já com o foco. -->
    <label class="grid gap-1.5" data-preorders-search-block>
      <span class="text-base font-semibold">Cliente veio buscar</span>
      <UiInput
        ref="searchField"
        v-model="typed"
        type="search"
        inputmode="search"
        autocomplete="off"
        class="h-12 text-base"
        placeholder="Nome, telefone ou número do pedido"
        aria-label="Cliente veio buscar: nome, telefone ou número do pedido"
        data-preorders-search
      />
    </label>

    <template v-if="searching">
      <p v-if="!enabled" class="text-sm text-muted-foreground" data-preorders-hint>
        Digite pelo menos {{ SEARCH_MIN_CHARS }} letras ou números para procurar.
      </p>

      <p v-else-if="search.pending.value && !search.list.value" class="p-4 text-sm text-muted-foreground">
        Procurando…
      </p>

      <p
        v-else-if="search.error.value"
        class="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
      >
        <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
        <span>{{ httpErrorMessage(search.error.value, "A busca não respondeu.") }} Tente de novo.</span>
      </p>

      <section
        v-else-if="!results.length"
        class="grid justify-items-center gap-2 rounded-md border border-dashed border-border p-8 text-center"
        data-preorders-empty
      >
        <Icon name="lucide:search-x" class="size-6 text-muted-foreground" />
        <p class="text-sm text-muted-foreground">{{ searchEmptyMessage(query, range, today) }}</p>
      </section>

      <section v-else class="grid gap-2" data-preorders-results>
        <h2 class="text-sm font-semibold text-muted-foreground">{{ preorderCountLabel(results.length) }}</h2>
        <ul class="grid gap-2">
          <li v-for="card in results" :key="card.ref">
            <PosPreorderRow :card="card" show-date />
          </li>
        </ul>
      </section>
    </template>

    <template v-else>
      <p v-if="ahead.pending.value && !summary" class="p-4 text-sm text-muted-foreground">
        Carregando as encomendas…
      </p>

      <p
        v-else-if="ahead.error.value && !summary"
        class="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
      >
        <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
        <span>{{ httpErrorMessage(ahead.error.value, "Não deu para ler as encomendas agora.") }} Tente de novo em Atualizar, no menu ao lado.</span>
      </p>

      <template v-else-if="summary">
        <!-- A RECEBER: o dinheiro que ainda falta entrar, cada total a um toque
             da lista já filtrada. Conta da casa e "a conferir" ficam de fora. -->
        <section class="grid grid-cols-1 gap-3 sm:grid-cols-2" aria-label="A receber" data-preorders-to-receive-totals>
          <NuxtLink
            to="/preorders/today?pay=to_receive"
            class="grid gap-0.5 rounded-md border border-border bg-card p-4 transition hover:border-primary/40 hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            data-preorders-to-receive-today
          >
            <span class="text-sm text-muted-foreground">Hoje</span>
            <span class="text-lg font-semibold tabular-nums">{{ toReceiveLine(summary.todayToReceiveQ, summary.todayToReceiveDisplay) }}</span>
          </NuxtLink>
          <NuxtLink
            to="/preorders/week?pay=to_receive"
            class="grid gap-0.5 rounded-md border border-border bg-card p-4 transition hover:border-primary/40 hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            data-preorders-to-receive-week
          >
            <span class="text-sm text-muted-foreground">Hoje e os próximos 6 dias</span>
            <span class="text-lg font-semibold tabular-nums">{{ toReceiveLine(summary.weekToReceiveQ, summary.weekToReceiveDisplay) }}</span>
          </NuxtLink>
        </section>

        <div
          v-if="checkNotice"
          class="flex flex-wrap items-start gap-2 rounded-md border border-warning/30 bg-warning/10 p-3 text-sm text-warning"
          data-preorders-check-notice
        >
          <Icon name="lucide:circle-help" class="mt-0.5 size-4 shrink-0" />
          <span class="min-w-0 flex-1">{{ checkNotice }}</span>
          <UiButton variant="outline" size="sm" to="/preorders/week?pay=check">Ver quais são</UiButton>
        </div>

        <ul class="grid grid-cols-1 gap-3 sm:grid-cols-3" data-preorders-tiles>
          <li v-for="tile in tiles" :key="tile.key">
            <PosSessionTile :tile="tile" @select="selectTile" />
          </li>
        </ul>
      </template>
    </template>
  </PosPreordersShell>
</template>
