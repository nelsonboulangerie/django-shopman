<script setup lang="ts">
// A busca do PDV: a lupa, o campo grande do balcão (44 px, texto base) e, quando a
// tela tem atalho, a tecla impressa no fim do campo. Uma peça só para a grade de
// produtos da venda e para as Encomendas ("Cliente veio buscar?"), que antes
// desenhavam cada uma o seu campo.
//
// Atributos (placeholder, aria-label, data-*, `@keydown`) vão para o INPUT, não para
// o invólucro: é nele que o leitor de tela, o teste e o atalho mexem. O invólucro
// ocupa o espaço que sobra na linha (`flex-1`), como a busca da venda sempre fez, e
// nunca fica menor que 16rem (ou a linha inteira, no celular): espremido ao lado de
// um título, o campo não mostrava nem o começo do que se pode procurar.
defineOptions({ inheritAttrs: false });

const model = defineModel<string>({ required: true });
defineProps<{
  /** A tecla do atalho, impressa no fim do campo ("F3"). */
  kbd?: string;
}>();

const field = useTemplateRef<{ inputRef: HTMLInputElement | null }>("field");
const inputRef = computed(() => field.value?.inputRef ?? null);
defineExpose({ inputRef });
</script>

<template>
  <div class="relative min-w-[min(100%,16rem)] flex-1">
    <Icon
      name="lucide:search"
      class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
      aria-hidden="true"
    />
    <UiInput
      ref="field"
      v-model="model"
      type="search"
      class="h-11 pl-9 text-base"
      :class="kbd ? 'pr-12' : ''"
      v-bind="$attrs"
    />
    <OperatorKbd v-if="kbd" class="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2" aria-hidden="true">{{ kbd }}</OperatorKbd>
  </div>
</template>
