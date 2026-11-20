<script setup lang="ts">
// TROCAR O ITEM QUE FALTA (#2765), no detalhe da encomenda.
//
// O Gestor abre a encomenda em `?swap=<sku>` depois do "Trocar por <produto>" do
// diálogo "Resolver". Um bloco por item a trocar, com o que sai (na quantidade
// da linha) e o fato do aviso; abaixo, UMA alternativa por linha, na largura
// inteira, com o que o lote da data cobre e a diferença de preço. O toque abre
// a conferência (`PosPreorderSwapDialog`); a troca grava pela edição da encomenda.
//
// A busca que rodou e não achou nada diz isso e oferece o Reagendar (a saída que
// sobra). A busca que não rodou não aparece aqui: o aviso do topo diz e traz o
// "Procurar de novo".
import { swapFocusKey, swapItemTitle } from "~/presentation/preorderSwap";
import type { PreorderSwapItem, PreorderSwapOption } from "~/types/preorders";

defineProps<{
  items: PreorderSwapItem[];
  busy?: boolean;
  /** O Reagendar está aberto para esta encomenda (`counter.reschedule.allowed`). */
  canReschedule?: boolean;
}>();

const emit = defineEmits<{
  pick: [item: PreorderSwapItem, option: PreorderSwapOption];
  reschedule: [];
}>();
</script>

<template>
  <div class="grid gap-4" data-preorder-swap>
    <section
      v-for="item in items"
      :key="item.sku"
      :data-focus-target="swapFocusKey(item.sku)"
      tabindex="-1"
      class="grid scroll-mt-24 gap-3 rounded-lg bg-default p-4 outline-none ring ring-default focus-visible:ring-2 focus-visible:ring-primary"
      :aria-label="swapItemTitle(item)"
      :data-preorder-swap-item="item.sku"
    >
      <header class="grid min-w-0 gap-1">
        <h2 class="break-words text-lg font-semibold" data-preorder-swap-title>{{ swapItemTitle(item) }}</h2>
        <p v-if="item.fact" class="text-sm text-muted" data-preorder-swap-fact>{{ item.fact }}</p>
      </header>

      <ul v-if="item.options.length" class="grid gap-2" data-preorder-swap-options>
        <li v-for="option in item.options" :key="option.sku" class="grid gap-1">
          <NuxtButton
            color="neutral"
            variant="outline"
            block
            class="min-h-14 justify-between gap-3 px-4 py-2 text-left"
            :disabled="busy || !option.enabled"
            :data-preorder-swap-option="option.sku"
            @click="emit('pick', item, option)"
          >
            <span class="grid min-w-0 gap-0.5">
              <span class="break-words text-base font-semibold">{{ option.label }}</span>
              <span class="text-sm font-normal text-muted" data-preorder-swap-available>{{ option.available_display }}</span>
            </span>
            <span
              v-if="option.enabled"
              class="shrink-0 text-right text-sm font-semibold tabular-nums"
              data-preorder-swap-difference
            >{{ option.difference_display }}</span>
          </NuxtButton>
          <p v-if="option.reason" class="text-sm text-muted" data-preorder-swap-reason>{{ option.reason }}</p>
        </li>
      </ul>

      <div v-else-if="item.searched" class="flex flex-wrap items-center gap-3" data-preorder-swap-empty>
        <p class="min-w-0 flex-1 text-sm">{{ item.empty_phrase }}</p>
        <NuxtButton
          v-if="canReschedule"
          color="neutral"
          variant="outline"
          class="min-h-11 justify-center"
          icon="i-lucide-calendar-clock"
          label="Reagendar"
          :disabled="busy"
          data-preorder-swap-reschedule
          @click="emit('reschedule')"
        />
      </div>
    </section>
  </div>
</template>
