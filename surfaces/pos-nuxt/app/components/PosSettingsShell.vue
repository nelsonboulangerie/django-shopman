<script setup lang="ts">
// A casca das abas de PDV › Ajustes que não são o Salão, dentro do shell da suíte
// (fase 2): o cabeçalho "Ajustes › <aba>" com as abas na toolbar, e o conteúdo
// rolando. A navegação (barra lateral, gaveta, barra inferior) é do shell, montada
// uma vez em `PosOperatorShell`. O Salão tem casca própria (planta em tela cheia),
// com as mesmas abas.
import type { OperatorHeaderAction } from "../../../operator-kit/app/presentation/pageHeader";
import type { OperatorScreenAlert } from "../../../operator-kit/app/presentation/screenState";

const props = defineProps<{
  title: string;
  /** O que a aba ajusta, em poucas palavras, ao lado do título. */
  subtitle?: string;
  /**
   * O que o "Atualizar" relê. Padrão: os dados dos Ajustes (`pos-settings`, a mesma
   * chave do `usePosSettings`), e só eles: reler o terminal inteiro trazia de novo
   * a venda, as comandas e o caixa para trocar uma impressora. A aba que mostra
   * outra leitura (Terminal: a saúde do balcão) passa a dela.
   */
  refresh?: () => unknown;
  /** Os avisos da aba, no lugar único do cabeçalho (fecham no X). */
  alerts?: OperatorScreenAlert[];
}>();

const { pos, refresh: refreshPos } = await usePosTerminal();
const refreshing = ref(false);
async function refreshSettings() {
  refreshing.value = true;
  try {
    await (props.refresh ? props.refresh() : refreshNuxtData("pos-settings"));
  } finally {
    refreshing.value = false;
  }
}
const headerActions = computed<OperatorHeaderAction[]>(() => [
  { label: "Atualizar", icon: "i-lucide-refresh-cw", disabled: refreshing.value, onSelect: () => void refreshSettings() },
]);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col" data-pos-settings-shell data-compact-page>
    <!-- No celular, a linha do chão: o selo diz "Ajustes, <aba>" e troca de seção; as
         abas descem logo abaixo, porque a faixa de filtros do cabeçalho some ali. -->
    <PosCompactBar :title="`Ajustes, ${title}`" :options="headerActions" />
    <!-- As abas descem para o celular. A ação da aba (Gravar atalhos, Nova maquininha)
         NÃO se repete aqui: o cabeçalho do kit já a desce para a linha própria no
         celular, e as duas juntas desenhavam "Nova maquininha" duas vezes (beta 05/11,
         PDV-07). -->
    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-default px-3 py-2 md:hidden" data-compact-settings-tabs>
      <PosSettingsTabs />
    </div>
    <OperatorPageHeader :title="title" :actions="headerActions" :alerts="alerts ?? []" actions-label="Mais ações dos Ajustes">
      <template #lead>
        <span class="hidden items-center gap-1 text-sm text-muted-foreground md:inline-flex">
          Ajustes<Icon name="lucide:chevron-right" class="size-4" aria-hidden="true" />
        </span>
      </template>
      <template v-if="subtitle" #status>
        <span class="hidden text-xs text-muted-foreground lg:inline">{{ subtitle }}</span>
      </template>
      <template v-if="$slots.actions" #actions>
        <slot name="actions" />
      </template>
      <template #filters-primary>
        <PosSettingsTabs />
      </template>
    </OperatorPageHeader>
    <div class="min-h-0 flex-1 overflow-y-auto">
      <div class="mx-auto grid w-full max-w-4xl gap-4 p-4 md:p-6">
        <slot :pos="pos" :refresh-pos="refreshPos" />
      </div>
    </div>
  </main>
</template>
