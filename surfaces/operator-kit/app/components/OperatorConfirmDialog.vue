<script setup lang="ts">
// A caixa do `useConfirm()`: a pergunta "descartar o que não foi salvo?" no diálogo
// da casa. Montada UMA vez, pelo `OperatorPwaRuntime`, que todo app de operador já
// monta; nenhum app a monta de novo.
//
// O modal canônico do Nuxt UI mantém esta peça compartilhável entre os nove apps.
//
// "Continuar editando" vem primeiro e recebe o foco: Enter por reflexo nunca perde
// o que foi digitado.
//
// O botão do ato tem o tom do pedido (`tone`): vermelho quando descarta (o padrão),
// a cor da casa quando é um ato normal que só pede confirmação. Pintar de vermelho
// "mudar a encomenda de dia" seria rótulo que mente (docs/reference/omotenashi-copy.md).
import { computed } from "vue";

import { useConfirmState } from "../composables/useConfirm";

const { pending, answer } = useConfirmState();
const open = computed(() => pending.value !== null);

function onOpenChange(value: boolean) {
  // Esc e o "Continuar editando" chegam aqui como `false`: ficar.
  if (!value) answer(false);
}

// O FOCO DEPOIS DO SIM (`returnFocusOnConfirm: false`, ver `useConfirm`). Ao desmontar,
// o Reka devolve o foco a quem o tinha na abertura; quando o sim troca a tela, esse
// elemento está de saída, e quem pediu leva o foco ao gesto que segue. O `preventDefault`
// do `close-auto-focus` é o gancho do Reka para isso. A resposta já saiu de `pending`
// quando a caixa desmonta: a escolha fica guardada aqui.
let callerTakesFocus = false;
function confirm() {
  callerTakesFocus = pending.value?.returnFocusOnConfirm === false;
  answer(true);
}
function onCloseAutoFocus(event: Event) {
  if (callerTakesFocus) event.preventDefault();
  callerTakesFocus = false;
}
</script>

<template>
  <NuxtModal
    v-if="pending"
    :open="open"
    :title="pending.title"
    :description="pending.description"
    :close="false"
    :content="{ onCloseAutoFocus }"
    @update:open="onOpenChange"
  >
    <template #footer>
      <div class="flex w-full flex-col-reverse gap-2 sm:flex-row sm:justify-end" data-operator-confirm>
        <NuxtButton color="neutral" variant="outline" :label="pending.cancelLabel" data-operator-confirm-keep @click="answer(false)" />
        <NuxtButton
          :color="pending.tone === 'danger' ? 'error' : 'primary'"
          :label="pending.confirmLabel"
          data-operator-confirm-act
          :data-tone="pending.tone"
          @click="confirm"
        />
      </div>
    </template>
  </NuxtModal>
</template>
