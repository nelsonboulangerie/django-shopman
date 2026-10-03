<script setup lang="ts">
// A moldura das Encomendas: o rail do PDV, a barra do kit (`OperatorAppBar`)
// e a área de conteúdo que rola. A tela da seção e o detalhe dividem esta peça
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
  <main class="flex flex-wrap content-start min-h-dvh bg-background text-foreground md:h-[100dvh] md:min-h-0 md:flex-nowrap md:overflow-hidden">
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
      <!-- `flex-wrap`: com o Período na barra, a tela estreita leva o Período para a
           linha de baixo em vez de empurrar a página para o lado. O Período entra
           direto na barra (slot `period`, dentro do `start`) e não no `end` do kit,
           cujo invólucro não encolhe: assim, na linha dele, o rótulo quebra em vez
           de passar da borda. -->
      <OperatorAppBar :sections="[]" label="Encomendas" class="flex-wrap">
        <template #start>
          <p class="inline-flex min-h-control shrink-0 items-center gap-1.5 px-2 text-base font-semibold" data-preorders-title>
            <Icon name="lucide:package" class="size-5 text-muted-foreground" aria-hidden="true" />
            Encomendas
          </p>
          <slot name="period" />
          <!-- As ações também entram no `start`, e não no `end` do kit, pela mesma
               razão do Período: o invólucro do `end` não encolhe, e no celular o
               lote passava da borda. Aqui elas quebram de linha. -->
          <div v-if="$slots.actions" class="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-2" data-preorders-actions>
            <slot name="actions" />
          </div>
        </template>
      </OperatorAppBar>

      <div class="relative flex-1 md:min-h-0 md:overflow-y-auto">
        <div class="mx-auto grid w-full gap-4 p-4 md:py-6" :class="wide ? 'max-w-screen-2xl' : 'max-w-3xl'">
          <slot />
          <MoreBelow />
        </div>
      </div>
    </div>
  </main>
</template>
