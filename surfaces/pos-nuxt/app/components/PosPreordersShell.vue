<script setup lang="ts">
// A moldura das Encomendas: o rail do PDV, o cabeçalho de uma linha do kit
// (`OperatorPageHeader`, onda V4) e a área de conteúdo que rola. A tela da seção e o detalhe dividem esta peça
// em vez de repetir rail e cabeçalho — o guardrail do cabeçalho
// (`guardrails.appBar.test.ts`) não deixa cabeçalho novo nascer à mão.
//
// Uma navegação por destino (sessão Encomendas, 02/10):
// - a PORTA da seção é o item "Encomendas" do rail (decisão do dono, 26/09). O
//   nome no começo da barra é só o título: não é segundo link para o mesmo lugar;
// - Dia | Semana mora num lugar só, o Período do kit (`OperatorPeriodPicker`), que
//   a tela da seção põe na barra (slot `period`): o mesmo lugar em que a Produção,
//   o KDS e o B.I. o põem. A barra não leva abas que gravariam o mesmo estado.
// - à direita da barra (slot `actions`), o que age sobre o que a tela mostra: a
//   grade ou a lista e o lote das Vias Pedido (OBS0310-D, como o cabeçalho do
//   balcão leva os botões da tela à direita).
import { toast } from "vue-sonner";

import type { POSProjection } from "~/types/pos";

withDefaults(defineProps<{
  pos: POSProjection | null;
  pending: boolean;
  /** Largura do conteúdo: a grade semanal precisa da tela inteira. */
  wide?: boolean;
}>(), { wide: false });

const emit = defineEmits<{ refresh: [] }>();

const { operator: activeOperator, lock } = useOperatorLock("cashman.operate_pos");

const customerDisplayWindow = useCustomerDisplayWindow();
function openCustomerDisplay() {
  if (!customerDisplayWindow.open()) toast.error("O navegador bloqueou a Tela do Cliente.", {
    description: "Permita pop-ups para este site e tente novamente.",
  });
}
</script>

<template>
  <main class="flex min-h-dvh flex-col bg-background text-foreground md:h-[100dvh] md:min-h-0 md:flex-row md:overflow-hidden">
    <PosFunctionRail
      v-if="pos"
      :pos="pos"
      :has-open-cash-session="pos.has_open_cash_session"
      :operator-name="activeOperator?.name || ''"
      :pending="pending"
      view="preorders"
      @board="navigateTo('/')"
      @cash="navigateTo('/session')"
      @display="openCustomerDisplay"
      @lock="lock()"
      @refresh="emit('refresh')"
    />

    <div class="flex min-w-0 flex-1 flex-col md:min-h-0 md:overflow-hidden">
      <!-- Cabeçalho de uma linha da suíte (kit, onda V4): o título, o Período ao lado
           (slot `period`) e as ações à direita. No celular as ações descem para uma
           linha que rola, sem empurrar a página para o lado. -->
      <OperatorPageHeader title="Encomendas">
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

      <div class="relative flex-1 md:min-h-0 md:overflow-y-auto">
        <div class="mx-auto grid w-full gap-4 p-4 md:py-6" :class="wide ? 'max-w-screen-2xl' : 'max-w-3xl'">
          <slot />
          <MoreBelow />
        </div>
      </div>
      <PosFunctionRail place="bar" @board="navigateTo('/')" @cash="navigateTo('/session')" @display="openCustomerDisplay" />
    </div>
  </main>
</template>
