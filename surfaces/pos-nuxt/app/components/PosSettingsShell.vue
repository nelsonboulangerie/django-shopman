<script setup lang="ts">
// A casca das abas de PDV › Ajustes que não são o Salão: o rail do PDV, o cabeçalho
// "Ajustes › <aba>" com as abas embaixo, e o conteúdo rolando. O Salão tem casca
// própria (planta em tela cheia), com as mesmas abas.
import { toast } from "vue-sonner";

defineProps<{
  title: string;
  /** O que a aba ajusta, em poucas palavras, ao lado do título. */
  subtitle?: string;
}>();

const { pos, pending: posPending, refresh: refreshPos } = await usePosTerminal();
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
      :pending="posPending"
      view="settings"
      @board="navigateTo('/')"
      @cash="navigateTo('/session')"
      @display="openCustomerDisplay"
      @lock="lock()"
      @refresh="refreshPos()"
    />
    <div class="flex min-w-0 flex-1 flex-col md:min-h-0 md:overflow-hidden">
      <OperatorPageHeader :title="title">
        <template #lead>
          <span class="hidden items-center gap-1 op-label text-muted-foreground md:inline-flex">
            Ajustes<Icon name="lucide:chevron-right" class="size-4" aria-hidden="true" />
          </span>
        </template>
        <template v-if="subtitle" #status>
          <span class="hidden op-micro text-muted-foreground lg:inline">{{ subtitle }}</span>
        </template>
        <template #actions>
          <slot name="actions" />
        </template>
        <template #below>
          <PosSettingsTabs />
        </template>
      </OperatorPageHeader>
      <div class="min-h-0 flex-1 overflow-y-auto">
        <div class="mx-auto grid w-full max-w-4xl gap-4 p-4 pb-24 md:p-6">
          <slot :pos="pos" :refresh-pos="refreshPos" />
        </div>
      </div>
    </div>
  </main>
</template>
