<script setup lang="ts">
// A ação do momento na base, no celular (WP-FASE2-UX-OPERADOR, A10 e peça K3).
//
// A estrutura de sucesso do Storefront (`.shop-action-dock` da sacola, do finalizar e do
// produto) trazida como REGRA, não como classe: a linha de contexto (o número que a ação
// mexe), UMA ação larga e o motivo escrito quando ela não pode.
//
// Regras da peça:
//   - Cartão FLUTUANTE em superfície invertida (escura), com sombra, como a sacola do
//     Storefront: contraste com o conteúdo, e o polegar acha a ação sem procurar.
//   - Em FLUXO: a tela a põe como irmã do conteúdo que rola, depois dele, no rodapé do
//     painel (a mesma posição do `#footer` do `NuxtDashboardPanel`). Fica entre o
//     conteúdo e a barra inferior (`OperatorQuickBar`, 3 a 5 vagas), sem cobrir nenhum
//     dos dois e sem adivinhar altura: nada de `fixed`, nada de `bottom-16`.
//   - Só abaixo de `lg`: na mesa, a ação sobe para a barra superior primária.
//   - Some com o teclado aberto (`data-keyboard="open"` no `<html>`, escrito por
//     `plugins/visualViewport.client.ts`): o campo que a pessoa digita tem a tela.
//   - Marca `data-focus-obstruction`: o próximo foco e o "Tem mais abaixo" descontam a
//     altura dela.
//   - Botão `xl`: toque crítico, do conjunto mínimo. A ação é `solid`; a segunda, se
//     houver, é `outline` e nunca do mesmo peso.
//   - O motivo de não poder aparece escrito sob a ação (`role="status"`): no toque não
//     há dica de ponteiro.
import { computed, useId } from "vue";

import type { OperatorActionBarAction } from "../presentation/actionBar";

const props = withDefaults(
  defineProps<{
    /** A ação do momento. */
    action: OperatorActionBarAction;
    /** Uma segunda ação, de peso menor ("Recusar", "Algo não bate"). */
    secondary?: OperatorActionBarAction;
    /** A linha de contexto: o que a ação mexe ("Pedido 1048 · Ana Souza"). */
    contextLabel?: string;
    /** O número dessa linha ("R$ 48,70", "7 de 9 itens"). */
    contextValue?: string;
    /** Nome da região (leitor de tela). */
    label?: string;
  }>(),
  { secondary: undefined, contextLabel: "", contextValue: "", label: "Ação do momento" },
);

const reason = computed(() =>
  props.action.disabled && props.action.reason ? props.action.reason : "",
);

const reasonId = useId();

// Texto da casa não se corta: o rótulo do botão quebra linha em vez de "Iniciar
// prep…" (o oficial leva `truncate`). Uma vez aqui, nunca na tela.
const BUTTON_UI = { label: "text-clip whitespace-normal text-center" };

function run(action: OperatorActionBarAction, event: Event) {
  if (action.disabled || action.loading) return;
  action.onSelect?.(event);
}
</script>

<template>
  <footer
    class="shrink-0 px-3 pt-2 pb-3 lg:hidden in-data-[keyboard=open]:hidden"
    :aria-label="label"
    data-focus-obstruction
    data-operator-action-bar
  >
    <!-- O cartão flutuante em superfície invertida (dono, 09/10/2026: "mais contraste,
         como no Storefront, em modo escuro"). `dark` aqui troca os tokens só dentro
         do cartão: a ação primária e o texto seguem as cores do tema escuro. -->
    <div
      class="dark flex w-full flex-col gap-2 rounded-lg border border-border bg-background p-3 text-foreground shadow-lg"
      data-operator-action-bar-surface
    >
      <div
        v-if="contextLabel || contextValue"
        class="flex items-baseline justify-between gap-3"
        data-operator-action-bar-context
      >
        <span class="min-w-0 text-sm text-muted-foreground">{{ contextLabel }}</span>
        <span v-if="contextValue" class="shrink-0 text-base font-semibold tabular-nums">{{
          contextValue
        }}</span>
      </div>
      <div class="flex w-full items-center gap-2">
        <NuxtButton
          v-if="secondary"
          size="xl"
          variant="outline"
          :color="secondary.color ?? 'neutral'"
          :icon="secondary.icon"
          :label="secondary.label"
          :to="secondary.to"
          :loading="secondary.loading"
          :disabled="secondary.disabled"
          :ui="BUTTON_UI"
          data-operator-action-bar-secondary
          @click="run(secondary, $event)"
        />
        <NuxtButton
          size="xl"
          block
          class="min-w-0 flex-1"
          :color="action.color ?? 'primary'"
          :icon="action.icon"
          :label="action.label"
          :to="action.to"
          :loading="action.loading"
          :disabled="action.disabled"
          :aria-describedby="reason ? reasonId : undefined"
          :ui="BUTTON_UI"
          data-operator-action-bar-action
          @click="run(action, $event)"
        />
      </div>
      <p
        v-if="reason"
        :id="reasonId"
        class="text-sm text-muted-foreground"
        role="status"
        data-operator-action-bar-reason
      >
        {{ reason }}
      </p>
    </div>
  </footer>
</template>
