<script setup lang="ts">
// A caixa do `useConfirm()`: a pergunta "descartar o que não foi salvo?" no diálogo
// da casa. Montada UMA vez, pelo `OperatorPwaRuntime`, que todo app de operador já
// monta; nenhum app a monta de novo.
//
// `AlertDialog` do reka-ui, e não o `UiDialog` do app: a Central, o B.I. e o
// Compras não têm `UiDialog`, e esta peça precisa existir nos nove. Pelo mesmo
// motivo os botões são `<button>` crus (a convenção do kit, ver
// `OperatorSessionUnavailable`). AlertDialog porque é a semântica certa: toque fora
// não responde por ninguém, Esc e "Continuar editando" ficam, só o botão do ato
// descarta.
//
// "Continuar editando" vem primeiro e recebe o foco: Enter por reflexo nunca perde
// o que foi digitado.
import {
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogOverlay,
  AlertDialogPortal,
  AlertDialogRoot,
  AlertDialogTitle,
} from "reka-ui";
import { computed } from "vue";

import { useConfirmState } from "../composables/useConfirm";

const { pending, answer } = useConfirmState();
const open = computed(() => pending.value !== null);

function onOpenChange(value: boolean) {
  // Esc e o "Continuar editando" chegam aqui como `false`: ficar.
  if (!value) answer(false);
}
</script>

<template>
  <AlertDialogRoot :open="open" @update:open="onOpenChange">
    <AlertDialogPortal>
      <AlertDialogOverlay class="fixed inset-0 z-[90] bg-black/50" />
      <AlertDialogContent
        v-if="pending"
        class="fixed top-1/2 left-1/2 z-[90] grid w-full max-w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 gap-4 rounded-md border bg-card p-6 text-card-foreground shadow-lg sm:max-w-md"
        data-operator-confirm
      >
        <div class="grid gap-2">
          <AlertDialogTitle class="text-lg font-semibold">{{ pending.title }}</AlertDialogTitle>
          <AlertDialogDescription class="text-sm text-muted-foreground">{{ pending.description }}</AlertDialogDescription>
        </div>
        <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <AlertDialogCancel
            class="inline-flex min-h-control items-center justify-center rounded-md border px-4 text-sm font-medium transition hover:bg-foreground/8 outline-offset-2 focus-visible:outline-2 focus-visible:outline-ring"
            data-operator-confirm-keep
          >
            {{ pending.cancelLabel }}
          </AlertDialogCancel>
          <!-- `<button>` e não `AlertDialogAction`: o Action fecha o diálogo ANTES do
               `@click` (o fechar responde "ficar"), e a resposta sairia trocada. -->
          <button
            type="button"
            class="inline-flex min-h-control items-center justify-center rounded-md bg-destructive px-4 text-sm font-semibold text-destructive-foreground transition hover:bg-destructive/90 outline-offset-2 focus-visible:outline-2 focus-visible:outline-ring"
            data-operator-confirm-discard
            @click="answer(true)"
          >
            {{ pending.confirmLabel }}
          </button>
        </div>
      </AlertDialogContent>
    </AlertDialogPortal>
  </AlertDialogRoot>
</template>
