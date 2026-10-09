<script setup lang="ts">
// A moldura das Encomendas dentro do shell da suíte (fase 2): o cabeçalho de uma
// linha do kit (`OperatorPageHeader`) e a área de conteúdo que rola. A navegação
// (barra lateral, gaveta, barra inferior) é do shell, montada uma vez em
// `PosOperatorShell`. A tela da seção e o detalhe dividem esta peça em vez de
// repetir o cabeçalho — o guardrail do cabeçalho (`guardrails.appBar.test.ts`) não
// deixa cabeçalho novo nascer à mão.
//
// Uma navegação por destino (sessão Encomendas, 02/10):
// - a PORTA da seção é o item "Encomendas" da barra lateral (decisão do dono,
//   26/09). O nome no começo da barra é só o título: não é segundo link para o
//   mesmo lugar;
// - Dia | Semana mora num lugar só, o Período do kit (`OperatorPeriodPicker`), que
//   a tela da seção põe na barra (slot `period`).
// - à direita da barra (slot `actions`), o que age sobre o que a tela mostra: a
//   grade ou a lista e o lote das Vias Pedido (OBS0310-D). "Atualizar" mora no
//   ⋯ "Mais ações", como em toda tela da suíte.
import type { OperatorHeaderAction } from "../../../operator-kit/app/presentation/pageHeader";
import type { POSProjection } from "~/types/pos";

withDefaults(defineProps<{
  pos: POSProjection | null;
  pending: boolean;
  /** Largura do conteúdo: a grade semanal precisa da tela inteira. */
  wide?: boolean;
}>(), { wide: false });

const emit = defineEmits<{ refresh: [] }>();

const headerActions = computed<OperatorHeaderAction[]>(() => [
  { label: "Atualizar", icon: "i-lucide-refresh-cw", onSelect: () => emit("refresh") },
]);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col" data-preorders-shell>
    <!-- Cabeçalho de uma linha da suíte (kit): o título, o Período ao lado (slot
         `period`) e as ações à direita. -->
    <OperatorPageHeader title="Encomendas" :actions="headerActions" actions-label="Mais ações das Encomendas">
      <!-- O campo da tela é o "cliente veio buscar" (com o `/`); a busca da suíte fica no
           Ctrl K e na lupa do celular, sem um segundo campo na mesma tela. -->
      <template #search>
        <OperatorSuiteSearch variant="hotkey" placeholder="Buscar pedido, cliente, produto ou tela" />
      </template>
      <template v-if="$slots.period" #status>
        <slot name="period" />
      </template>
      <template v-if="$slots.actions" #actions>
        <div class="flex min-w-0 flex-wrap items-center justify-end gap-2" data-preorders-actions>
          <slot name="actions" />
        </div>
      </template>
    </OperatorPageHeader>

    <div class="relative min-h-0 flex-1 overflow-y-auto">
      <div class="mx-auto grid w-full gap-4 p-4 md:py-6" :class="wide ? 'max-w-screen-2xl' : 'max-w-3xl'">
        <slot />
        <MoreBelow />
      </div>
    </div>
  </main>
</template>
