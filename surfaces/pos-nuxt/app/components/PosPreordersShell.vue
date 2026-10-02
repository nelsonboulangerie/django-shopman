<script setup lang="ts">
// A moldura das Encomendas: o rail do PDV, a barra do kit (`OperatorAppBar`)
// e a área de conteúdo que rola. A tela da seção e o detalhe dividem esta peça
// em vez de repetir rail e cabeçalho — o guardrail do cabeçalho
// (`guardrails.appBar.test.ts`) não deixa cabeçalho novo nascer à mão.
//
// Uma navegação por destino (sessão Encomendas, 02/10):
// - a PORTA da seção é o item "Encomendas" do rail (decisão do dono, 26/09). O
//   nome no começo da barra é só o título: não é segundo link para o mesmo lugar;
// - Dia | Semana mora num lugar só, o Período do kit (`OperatorPeriodPicker`) no
//   quadro do período, onde o operador já olha a data e o ‹ ›. A barra não leva
//   abas que gravariam o mesmo estado.
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
      <OperatorAppBar :sections="[]" label="Encomendas">
        <template #start>
          <p class="inline-flex min-h-control shrink-0 items-center gap-1.5 px-2 text-base font-semibold" data-preorders-title>
            <Icon name="lucide:package" class="size-5 text-muted-foreground" aria-hidden="true" />
            Encomendas
          </p>
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
