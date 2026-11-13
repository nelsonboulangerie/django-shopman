<script setup lang="ts">
// Encomendas no Gestor (dono, 13/11/2026; o vocabulário fechado diz Encomenda, não
// Agendado): os pedidos dos próximos dias, abaixo do quadro, numa
// lista simples. Não entra no fluxo do dia; está ali para conferir de relance o que vem
// pela frente. Cada linha abre o pedido (o mesmo detalhe das Encomendas, com os
// gestos dele, inclusive o aceite da encomenda nova); o cabeçalho leva às Encomendas
// do PDV, onde mora o trabalho de planejar e entregar.
import type { PreorderGroup } from "~/presentation/board";
import { splitRef } from "~/presentation/board";
import { useOperatorAppLink } from "../../../operator-kit/app/composables/useOperatorAppLink";

const props = defineProps<{ groups: PreorderGroup[]; count: number }>();

const config = useRuntimeConfig();
const preordersHref = computed(() => {
  const base = String(config.public.posUrl || "");
  return base ? `${base.replace(/\/$/, "")}/preorders` : "";
});
const { attrsFor } = useOperatorAppLink();
const link = computed(() => attrsFor(preordersHref.value));
const total = computed(() => props.count);
</script>

<template>
  <section class="mt-6" data-preorders-section>
    <div class="flex items-center gap-2 border-b border-default pb-2">
      <h2 class="font-semibold text-highlighted">Encomendas</h2>
      <OperatorCountChip :count="total" />
      <NuxtButton
        v-if="preordersHref"
        class="ms-auto"
        :to="preordersHref"
        :target="link.target"
        :rel="link.rel"
        external
        color="neutral"
        variant="link"
        trailing-icon="i-lucide-arrow-up-right"
        label="Abrir Encomendas"
        data-preorders-open
      />
    </div>
    <div v-for="group in groups" :key="group.date" class="mt-3">
      <h3 class="op-micro font-semibold text-muted-foreground">
        {{ group.label }}
      </h3>
      <ul class="mt-1 divide-y divide-default">
        <li v-for="card in group.cards" :key="card.ref">
          <NuxtLink
            :to="`/${card.ref}`"
            class="flex min-h-11 items-center gap-3 py-2 hover:bg-elevated/50"
            :data-preorder-row="card.ref"
          >
            <span class="w-16 shrink-0 font-semibold tabular-nums text-highlighted">
              {{ splitRef(card.ref).code }}
            </span>
            <span class="w-40 shrink-0 truncate">{{ card.customer_name }}</span>
            <span class="min-w-0 flex-1 truncate text-muted">
              {{ card.items_summary }}
            </span>
            <span
              v-if="card.attention"
              class="shrink-0 op-micro font-semibold text-primary"
            >
              Precisa de você
            </span>
            <span class="shrink-0 tabular-nums">{{ card.total_display }}</span>
          </NuxtLink>
        </li>
      </ul>
    </div>
  </section>
</template>
