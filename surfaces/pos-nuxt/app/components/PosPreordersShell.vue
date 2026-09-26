<script setup lang="ts">
// A moldura das telas de Encomendas: o rail do PDV, a barra de seções do kit
// (`OperatorAppBar`) com as quatro portas da seção, e a área de conteúdo que
// rola. As quatro telas e o detalhe dividem esta peça em vez de repetir rail e
// cabeçalho — o guardrail do cabeçalho (`guardrails.appBar.test.ts`) não deixa
// cabeçalho novo nascer à mão.
//
// No rail, as Encomendas acendem "Sessão de caixa": a seção mora na antesala, e
// é para lá que o item leva de volta.
import { toast } from "vue-sonner";

import { PREORDER_SECTIONS } from "~/presentation/preorders";
import type { POSProjection } from "~/types/pos";

withDefaults(defineProps<{
  pos: POSProjection | null;
  pending: boolean;
  /** Seção ativa. Omitida, sai da rota; `""` apaga todas (o detalhe). */
  current?: string;
  /** Largura do conteúdo: a grade semanal precisa da tela inteira. */
  wide?: boolean;
}>(), { current: undefined, wide: false });

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
      view="session"
      @board="navigateTo('/')"
      @cash="navigateTo('/session')"
      @display="openCustomerDisplay"
      @lock="lock()"
      @refresh="emit('refresh')"
    />

    <div class="flex min-w-0 flex-1 flex-col md:min-h-0 md:overflow-hidden">
      <OperatorAppBar :sections="PREORDER_SECTIONS" :current="current" label="Seções de Encomendas">
        <template #start>
          <NuxtLink
            to="/session"
            class="inline-flex min-h-control shrink-0 items-center gap-1.5 rounded-md px-2 text-base font-semibold hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            aria-label="Encomendas — voltar para a sessão de caixa"
          >
            <Icon name="lucide:package" class="size-5 text-muted-foreground" />
            <span class="hidden sm:inline">Encomendas</span>
          </NuxtLink>
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
