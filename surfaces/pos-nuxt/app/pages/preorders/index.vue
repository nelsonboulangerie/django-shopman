<script setup lang="ts">
// ENCOMENDAS · CLIENTE VEIO BUSCAR — "vim buscar a encomenda da Ana". Um campo,
// que aceita nome, telefone ou número do pedido (inclusive o número do iFood), e
// o resultado a um toque do detalhe.
//
// A busca olha de uma semana atrás até um mês à frente (`searchRange`): quem
// chega hoje para buscar a encomenda de ontem é justamente o caso em que o
// balcão mais precisa achar o pedido.
import { watchDebounced } from "@vueuse/core";

import { isoDate } from "~/presentation/orderTickets";
import {
  SEARCH_MIN_CHARS,
  canSearch,
  flattenDays,
  preorderCountLabel,
  searchEmptyMessage,
  searchRange,
} from "~/presentation/preorders";

useHead({ title: "Cliente veio buscar" });

const { pos, pending: posPending, refresh: refreshPos } = await usePosTerminal();

const today = isoDate(new Date());
const range = ref(searchRange(today));
const typed = ref("");
// O que foi perguntado ao servidor: a digitação assenta antes de virar busca.
const query = ref("");
watchDebounced(typed, (value) => { query.value = value.trim(); }, { debounce: 250 });

const enabled = computed(() => canSearch(query.value));
const preorders = usePosPreorders({ key: "pos-preorders-search", range, query, enabled });
const results = computed(() => flattenDays(preorders.days.value));

// O campo nasce focado: tocar o card "Cliente veio buscar" já foi a decisão,
// digitar é o próximo gesto.
const searchField = useTemplateRef<{ inputRef: HTMLInputElement | null }>("searchField");
onMounted(() => { void nextTick(() => searchField.value?.inputRef?.focus()); });
</script>

<template>
  <PosPreordersShell :pos="pos" :pending="posPending || preorders.pending.value" @refresh="refreshPos(); preorders.refresh()">
    <h1 class="text-lg font-semibold">Cliente veio buscar</h1>

    <label class="grid gap-1.5">
      <span class="text-sm text-muted-foreground">Nome, telefone ou número do pedido</span>
      <UiInput
        ref="searchField"
        v-model="typed"
        type="search"
        inputmode="search"
        autocomplete="off"
        class="h-12 text-base"
        placeholder="Ex.: Ana, 99988-7766 ou NB-1234"
        data-preorders-search
      />
    </label>

    <p v-if="!enabled" class="text-sm text-muted-foreground" data-preorders-hint>
      Digite pelo menos {{ SEARCH_MIN_CHARS }} letras ou números para procurar.
    </p>

    <p v-else-if="preorders.pending.value && !preorders.list.value" class="p-4 text-sm text-muted-foreground">
      Procurando…
    </p>

    <p
      v-else-if="preorders.error.value"
      class="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
    >
      <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
      <span>{{ httpErrorMessage(preorders.error.value, "A busca não respondeu.") }} Tente de novo.</span>
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
  </PosPreordersShell>
</template>
