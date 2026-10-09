<script setup lang="ts">
// O menu do toque longo no celular (prévia v4 `cozinha-celular` b, nota 7: "Desfazer,
// reabrir e o pedido no toque longo, sem botões a mais na tela"). Sobe da base
// (`NuxtDrawer`), ao alcance do polegar, com os gestos que o tablet mostra no card:
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
  <NuxtDrawer
    :open="open"
    :title="code ? `Pedido ${code}` : 'Pedido'"
    description="O que fazer com este pedido"
    data-kds-hold-sheet
    @update:open="emit('update:open', Boolean($event))"
  >
    <template #body>
      <div class="flex flex-col gap-1.5 pb-[env(safe-area-inset-bottom)]">
        <NuxtButton
          v-if="ticket"
          size="xl"
          color="neutral"
          variant="ghost"
          block
          icon="i-lucide-receipt-text"
          class="justify-start"
          :label="`Ver o pedido ${code}`"
          data-kds-hold-view
          @click="choose('view')"
        />
        <NuxtButton
          v-if="finishing"
          size="xl"
          color="neutral"
          variant="ghost"
          block
          icon="i-lucide-undo-2"
          class="justify-start"
          :label="`Desfazer o Pronto de ${code}`"
          data-kds-hold-undo
          @click="choose('undo')"
        />
        <NuxtButton
          v-if="recentCount"
          size="xl"
          color="neutral"
          variant="ghost"
          block
          icon="i-lucide-rotate-ccw"
          class="justify-start"
          :label="`Reabrir um concluído (${recentCount})`"
          data-kds-hold-reopen
          @click="choose('reopen')"
        />
      </div>
    </template>
  </NuxtDrawer>
</template>
