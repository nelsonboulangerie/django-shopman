<script setup lang="ts">
// A busca do PDV: a lupa, o campo grande do balcão (44 px, texto base) e, quando a
// tela tem atalho, a tecla impressa no fim do campo. Uma peça só para a grade de
// produtos da venda e para as Encomendas ("Cliente veio buscar?"), que antes
// desenhavam cada uma o seu campo.
//
// Camada da suíte (v4, `pos-sale4.html`): o campo em foco ganha a borda de 2px na cor
// primária e o halo; a dica do gesto ("Enter adiciona") e as teclas ("F3", "/") ficam
// no fim do campo, do tablet deitado para cima (no celular só sobra o campo).
//
// Atributos (placeholder, aria-label, data-*, `@keydown`) vão para o INPUT, não para
// o invólucro: é nele que o leitor de tela, o teste e o atalho mexem. O invólucro
// ocupa o espaço que sobra na linha (`flex-1`), como a busca da venda sempre fez, e
// nunca fica menor que 16rem (ou a linha inteira, no celular): espremido ao lado de
// um título, o campo não mostrava nem o começo do que se pode procurar.
defineOptions({ inheritAttrs: false });

const model = defineModel<string>({ required: true });
const props = defineProps<{
  /** A tecla do atalho, impressa no fim do campo ("F3"), ou as teclas (["F3", "/"]). */
  kbd?: string | string[];
  /** A dica do gesto, no fim do campo ("Enter adiciona"). */
  hint?: string;
}>();

const keys = computed(() => (Array.isArray(props.kbd) ? props.kbd : props.kbd ? [props.kbd] : []));
const trailing = computed(() => keys.value.length > 0 || Boolean(props.hint));

const field = useTemplateRef<{ inputRef: HTMLInputElement | null }>("field");
const inputRef = computed(() => field.value?.inputRef ?? null);
defineExpose({ inputRef });
</script>

<template>
  <div class="relative min-w-[min(100%,16rem)] flex-1">
    <Icon
      name="lucide:search"
      class="pointer-events-none absolute left-3 top-1/2 size-5 -translate-y-1/2 text-muted-foreground"
      aria-hidden="true"
    />
    <UiInput
      ref="field"
      v-model="model"
      type="search"
      class="h-11 bg-card pl-10 text-base focus-visible:border-2 focus-visible:border-primary focus-visible:ring-[3px] focus-visible:ring-primary/15"
      :class="trailing ? (hint ? 'lg:pr-52 pr-24' : 'pr-24') : ''"
      v-bind="$attrs"
    />
    <span
      v-if="trailing"
      class="pointer-events-none absolute right-3 top-1/2 flex -translate-y-1/2 items-center gap-1.5"
      aria-hidden="true"
    >
      <span v-if="hint" class="hidden op-micro text-muted-foreground lg:inline">{{ hint }}</span>
      <OperatorKbd v-for="key in keys" :key="key">{{ key }}</OperatorKbd>
    </span>
  </div>
</template>
