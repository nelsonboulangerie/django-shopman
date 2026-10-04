<script setup lang="ts">
// O ⋯ do cabeçalho (prévia `bi-sobra4.html`: "Mais: Exportar, Copiar link, Como é
// calculado"). O que se usa a cada leitura fica à vista; o resto mora aqui, a um toque.
// "Copiar link" é de toda tela: a leitura inteira (período, dia, recortes) vive na URL.
// Itens próprios da tela entram pelo slot (ex.: "Como é calculado").
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";

const open = ref(false);
const ITEM = "flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body transition hover:bg-accent";

const { run: copyLink, pending: copying } = usePendingAction(async () => {
  open.value = false;
  try {
    await navigator.clipboard.writeText(window.location.href);
    useSonner.success("Link copiado: quem abrir vê esta mesma leitura.");
  } catch {
    useSonner.warning("Não deu para copiar. O endereço na barra do navegador é o link desta leitura.");
  }
});

function close() {
  open.value = false;
}
</script>

<template>
  <PopoverRoot v-model:open="open">
    <PopoverTrigger as-child>
      <UiIconButton icon="lucide:ellipsis" label="Mais: copiar link e como é calculado" :active="open" data-bi-page-menu />
    </PopoverTrigger>
    <PopoverPortal>
      <PopoverContent
        side="bottom"
        align="end"
        :side-offset="6"
        :collision-padding="8"
        class="z-50 w-72 rounded-lg border bg-popover p-1.5 text-popover-foreground shadow-lg outline-hidden"
        data-bi-page-menu-panel
      >
        <div role="menu" class="flex flex-col">
          <button type="button" role="menuitem" :class="ITEM" :disabled="copying" @click="copyLink">
            <Icon name="lucide:link" class="size-4 text-muted-foreground" aria-hidden="true" />
            Copiar link desta leitura
          </button>
          <slot :item-class="ITEM" :close="close" />
        </div>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>
