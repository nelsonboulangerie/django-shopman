<script setup lang="ts">
// O menu do toque longo no celular (prévia v4 `cozinha-celular` b, nota 7: "Desfazer,
// reabrir e o pedido no toque longo, sem botões a mais na tela"). Sobe da base, ao
// alcance do polegar, com os gestos que o tablet mostra no cabeçalho e no card:
// ver o pedido, desfazer o pronto (na janela de 5 s) e reabrir um concluído.
import type { KDSTicketProjection } from "~/types/kds";
import { splitRef } from "~/presentation/board";

const props = defineProps<{
  open: boolean;
  ticket: KDSTicketProjection | null;
  /** O pronto deste ticket ainda está na janela de desfazer. */
  finishing: boolean;
  /** Concluídos dos últimos 30 minutos que dá para reabrir. */
  recentCount: number;
}>();
const emit = defineEmits<{ "update:open": [boolean]; view: []; undo: []; reopen: [] }>();

const code = computed(() => (props.ticket ? splitRef(props.ticket.order_ref).code : ""));

function choose(action: "view" | "undo" | "reopen") {
  // O gesto antes de fechar: quem escuta ainda sabe de qual pedido é.
  if (action === "view") emit("view");
  else if (action === "undo") emit("undo");
  else emit("reopen");
  emit("update:open", false);
}
</script>

<template>
  <UiSheet :open="open" @update:open="emit('update:open', Boolean($event))">
    <UiSheetContent side="bottom" class="gap-0 rounded-t-2xl p-0 pb-[env(safe-area-inset-bottom)]" data-suite="v3" data-kds-hold-sheet>
      <template #header>
        <div class="border-b px-5 pt-5 pb-3">
          <UiSheetTitle class="op-title">{{ code ? `Pedido ${code}` : "Pedido" }}</UiSheetTitle>
          <UiSheetDescription class="op-label text-muted-foreground">O que fazer com este pedido</UiSheetDescription>
        </div>
      </template>
      <template #content>
        <div class="flex flex-col gap-1.5 p-3">
          <button
            v-if="ticket"
            type="button"
            class="flex min-h-14 items-center gap-3 rounded-xl px-4 text-left op-title transition hover:bg-accent active:bg-accent/70"
            data-kds-hold-view
            @click="choose('view')"
          >
            <Icon name="lucide:receipt-text" class="size-5 shrink-0 text-muted-foreground" />
            Ver o pedido {{ code }}
          </button>
          <button
            v-if="finishing"
            type="button"
            class="flex min-h-14 items-center gap-3 rounded-xl px-4 text-left op-title transition hover:bg-accent active:bg-accent/70"
            data-kds-hold-undo
            @click="choose('undo')"
          >
            <Icon name="lucide:undo-2" class="size-5 shrink-0 text-muted-foreground" />
            Desfazer o pronto de {{ code }}
          </button>
          <button
            v-if="recentCount"
            type="button"
            class="flex min-h-14 items-center gap-3 rounded-xl px-4 text-left op-title transition hover:bg-accent active:bg-accent/70"
            data-kds-hold-reopen
            @click="choose('reopen')"
          >
            <Icon name="lucide:rotate-ccw" class="size-5 shrink-0 text-muted-foreground" />
            <span class="min-w-0 flex-1">Reabrir um concluído</span>
            <span class="op-label tabular-nums text-muted-foreground">{{ recentCount }}</span>
          </button>
        </div>
      </template>
    </UiSheetContent>
  </UiSheet>
</template>
