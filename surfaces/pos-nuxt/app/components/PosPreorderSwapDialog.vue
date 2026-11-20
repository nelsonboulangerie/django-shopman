<script setup lang="ts">
// A conferência da troca (#2765): o que sai, o que entra, o total antes e depois
// e o que acontece com a diferença. Os números são do servidor (a prévia da
// edição da encomenda); a tela só mostra. Confirmar grava pela edição; quando a
// encomenda paga fica mais barata, o PIN do gerente sobe por cima (na página).
import { swapConfirmTitle } from "~/presentation/preorderSwap";
import type { PreorderSwapItem, PreorderSwapOption } from "~/types/preorders";

const props = defineProps<{
  open: boolean;
  item: PreorderSwapItem | null;
  option: PreorderSwapOption | null;
  busy?: boolean;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  confirm: [];
}>();

const title = computed(() => (props.item && props.option ? swapConfirmTitle(props.item, props.option) : ""));
</script>

<template>
  <NuxtModal
    :open="open && !!item && !!option"
    :title="title"
    description="Confira com o cliente antes de trocar."
    :ui="{ content: 'sm:max-w-lg' }"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <template #body>
      <div v-if="item && option" class="grid gap-4" data-preorder-swap-dialog>
        <dl class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-base">
          <dt class="text-muted">Sai</dt>
          <dd class="break-words font-medium" data-preorder-swap-out>{{ item.qty_label }}</dd>
          <dt class="text-muted">Entra</dt>
          <dd class="break-words font-medium" data-preorder-swap-in>{{ option.qty_label }}</dd>
          <dt class="text-muted">Total antes</dt>
          <dd class="tabular-nums" data-preorder-swap-before>{{ option.total_before_display }}</dd>
          <dt class="text-muted">Total depois</dt>
          <dd class="font-semibold tabular-nums" data-preorder-swap-after>{{ option.total_after_display }}</dd>
          <dt class="text-muted">Diferença</dt>
          <dd class="font-semibold tabular-nums" data-preorder-swap-dialog-difference>{{ option.difference_display }}</dd>
        </dl>
        <p v-if="option.money" class="text-sm" data-preorder-swap-money>{{ option.money }}</p>
        <p v-if="option.requires_manager_approval" class="text-sm text-muted" data-preorder-swap-manager>
          Encomenda paga que fica mais barata: um gerente precisa autorizar a devolução.
        </p>
      </div>
    </template>
    <template #footer>
      <div class="flex w-full flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <NuxtButton
          color="neutral"
          variant="outline"
          class="min-h-11 justify-center"
          label="Voltar"
          @click="emit('update:open', false)"
        />
        <NuxtButton
          class="min-h-11 justify-center"
          :label="option?.label || 'Trocar'"
          :loading="busy"
          :disabled="busy"
          data-preorder-swap-confirm
          @click="emit('confirm')"
        />
      </div>
    </template>
  </NuxtModal>
</template>
