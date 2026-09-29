<script setup lang="ts">
// A moldura das Encomendas: o rail do PDV, a barra do kit (`OperatorAppBar`)
// com os dois modos da tela — Dia | Semana —, e a área de conteúdo que rola. A
// tela da seção e o detalhe dividem esta peça em vez de repetir rail e
// cabeçalho — o guardrail do cabeçalho (`guardrails.appBar.test.ts`) não deixa
// cabeçalho novo nascer à mão.
//
// No rail, as Encomendas acendem o próprio item: a porta da seção é a barra
// lateral (decisão do dono, 26/09), e o nome no começo da barra leva à casa.
import { toast } from "vue-sonner";

import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";
import { isoDate } from "~/presentation/orderTickets";
import { modeSections } from "~/presentation/preorders";
import type { POSProjection } from "~/types/pos";

const props = withDefaults(defineProps<{
  pos: POSProjection | null;
  pending: boolean;
  /** Modo ativo (`day`/`week`); `""` apaga as abas (o detalhe). */
  current?: string;
  /**
   * As abas Dia | Semana com o estado da tela (data e filtros) dentro do link.
   * Omitidas (o detalhe), levam ao dia e à semana de hoje.
   */
  sections?: OperatorSection[];
  /** Largura do conteúdo: a grade semanal precisa da tela inteira. */
  wide?: boolean;
}>(), { current: "", sections: undefined, wide: false });

const tabs = computed(() => props.sections ?? modeSections(null, isoDate(new Date())));

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
      <OperatorAppBar :sections="tabs" :current="current" label="Modo das Encomendas">
        <template #start>
          <NuxtLink
            to="/preorders"
            class="inline-flex min-h-control shrink-0 items-center gap-1.5 rounded-md px-2 text-base font-semibold hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            aria-label="Encomendas: voltar para o início da seção"
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
