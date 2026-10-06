<script setup lang="ts">
// O ⋯ do quadro (UX-KIT-V2, prévia v4 `gestor-fila4.html`, pino 8: "Som, ordenar,
// Ciente de todos, exportar, imprimir e atualizar no cabeçalho e no ⋯"). O cabeçalho
// fica com o que se usa a cada pedido; o resto mora aqui, a um toque.
//
// `full`: o posto Saída e o celular, onde o cabeçalho não tem lugar para ordenar,
// trocar a visão e o som: tudo isso entra no painel. Atualizar não fecha o painel, para
// a frase da última leitura útil mostrar na hora se a leitura entrou ou falhou.
import type { ReadMetadata } from "~/types/readMetadata";
import { SORT_OPTIONS, type SortKey, type ViewMode } from "~/presentation/board";

defineProps<{
  metadata?: ReadMetadata | null;
  failed?: boolean;
  pending?: boolean;
  sort: SortKey;
  viewMode: ViewMode;
  soundOn: boolean;
  soundBlocked: boolean;
  attentionPending: boolean;
  selecting: boolean;
  full?: boolean;
  /** Quadro com alguma coluna recolhida: oferece as três de volta. */
  canShowAll?: boolean;
  /** A Fila existe nesta largura (desktop e tablet deitado, fora do posto Saída). */
  queueAvailable?: boolean;
}>();

const emit = defineEmits<{
  refresh: [];
  acknowledge: [];
  select: [];
  sort: [key: SortKey];
  view: [mode: ViewMode];
  sound: [];
  export: [];
  print: [];
  showAll: [];
}>();

const ITEM = "flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left text-sm transition hover:bg-accent";
</script>

<template>
  <div class="flex flex-col p-1.5" role="menu" data-board-menu>
    <div class="px-2.5 pt-1 pb-2">
      <ReadFreshness inline :metadata="metadata" :failed="failed" />
    </div>
    <button type="button" role="menuitem" :class="ITEM" aria-label="Atualizar (atalho: r)" data-board-refresh @click="emit('refresh')">
      <Icon name="lucide:refresh-cw" class="size-4 text-muted-foreground" :class="pending ? 'motion-safe:animate-spin' : ''" aria-hidden="true" />
      <span class="flex-1">Atualizar</span>
      <kbd class="hidden font-mono text-xs text-muted-foreground pointer-fine:inline" aria-hidden="true">R</kbd>
    </button>
    <button v-if="attentionPending" type="button" role="menuitem" :class="ITEM" aria-label="Reconhecer aviso de pedido novo" @click="emit('acknowledge')">
      <Icon name="lucide:check" class="size-4 text-muted-foreground" aria-hidden="true" />
      Ciente de todos
    </button>
    <button v-if="full" type="button" role="menuitem" :class="ITEM" data-board-menu-sound @click="emit('sound')">
      <Icon :name="soundOn ? 'lucide:volume-2' : 'lucide:volume-x'" class="size-4 text-muted-foreground" aria-hidden="true" />
      {{ soundOn && soundBlocked ? "Som bloqueado: toque para ativar" : soundOn ? "Som de pedido novo: ligado" : "Som de pedido novo: desligado" }}
    </button>
    <button v-if="canShowAll" type="button" role="menuitem" :class="ITEM" @click="emit('showAll')">
      <Icon name="lucide:columns-3" class="size-4 text-muted-foreground" aria-hidden="true" />
      Mostrar as 3 colunas
    </button>
    <!-- as três colunas (Entrada, Preparo, Saída): fora do alternador Fila | Supervisão -->
    <button v-if="!full" type="button" role="menuitemradio" :aria-checked="viewMode === 'board'" :class="ITEM" data-board-columns-view @click="emit('view', viewMode === 'board' ? (queueAvailable ? 'queue' : 'table') : 'board')">
      <Icon name="lucide:columns-3" class="size-4" :class="viewMode === 'board' ? 'text-primary' : 'text-muted-foreground'" aria-hidden="true" />
      <span class="flex-1">{{ viewMode === "board" ? "Voltar à Fila" : "Ver em colunas" }}</span>
      <kbd class="hidden font-mono text-xs text-muted-foreground pointer-fine:inline" aria-hidden="true">V</kbd>
    </button>
    <button type="button" role="menuitem" :class="ITEM" data-board-select @click="emit('select')">
      <Icon name="lucide:list-checks" class="size-4 text-muted-foreground" aria-hidden="true" />
      {{ selecting ? "Sair da seleção" : "Selecionar pedidos" }}
    </button>

    <template v-if="full">
      <p class="mt-1.5 border-t border-border px-2.5 pt-2.5 pb-1 text-xs uppercase tracking-wider font-semibold text-muted-foreground">Ordenar</p>
      <button
        v-for="opt in SORT_OPTIONS"
        :key="opt.key"
        type="button"
        role="menuitemradio"
        :aria-checked="sort === opt.key"
        :class="ITEM"
        @click="emit('sort', opt.key)"
      >
        <Icon :name="sort === opt.key ? 'lucide:check' : 'lucide:arrow-up-down'" class="size-4" :class="sort === opt.key ? 'text-primary' : 'text-muted-foreground'" aria-hidden="true" />
        {{ opt.label }}
      </button>
      <p class="mt-1.5 border-t border-border px-2.5 pt-2.5 pb-1 text-xs uppercase tracking-wider font-semibold text-muted-foreground">Ver como</p>
      <button v-if="queueAvailable" type="button" role="menuitemradio" :aria-checked="viewMode === 'queue'" :class="ITEM" @click="emit('view', 'queue')">
        <Icon name="lucide:list-checks" class="size-4" :class="viewMode === 'queue' ? 'text-primary' : 'text-muted-foreground'" aria-hidden="true" />
        Fila
      </button>
      <button type="button" role="menuitemradio" :aria-checked="viewMode === 'board'" :class="ITEM" @click="emit('view', 'board')">
        <Icon name="lucide:columns-3" class="size-4" :class="viewMode === 'board' ? 'text-primary' : 'text-muted-foreground'" aria-hidden="true" />
        Colunas
      </button>
      <button type="button" role="menuitemradio" :aria-checked="viewMode === 'table'" :class="ITEM" @click="emit('view', 'table')">
        <Icon name="lucide:table-2" class="size-4" :class="viewMode === 'table' ? 'text-primary' : 'text-muted-foreground'" aria-hidden="true" />
        Supervisão
      </button>
    </template>

    <div class="mt-1.5 border-t border-border pt-1.5">
      <button type="button" role="menuitem" :class="ITEM" @click="emit('export')">
        <Icon name="lucide:download" class="size-4 text-muted-foreground" aria-hidden="true" /> Exportar CSV
      </button>
      <button type="button" role="menuitem" :class="ITEM" @click="emit('print')">
        <Icon name="lucide:printer" class="size-4 text-muted-foreground" aria-hidden="true" /> Imprimir fila
      </button>
    </div>
  </div>
</template>
