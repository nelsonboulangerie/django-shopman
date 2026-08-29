<script setup lang="ts">
// A trava da gaveta: o PDV não anda com a gaveta aberta.
//
// ⚠️ **O que a tela esconde é o PIN, não a desistência.** Um botão "gerente
// libera" na frente de todo operador ensina o bypass: a exceção vira o caminho
// conhecido, e a fraude aprende sozinha, sem nem precisar de má-fé — basta
// alguém achar que "é assim que se faz quando atrasa". Quem foi treinado sabe
// que **Esc** (ou os três pontinhos) abre o PIN; quem não foi, não descobre.
//
// O botão de fechar do canto CONTINUA existindo, e de propósito: ele não libera
// venda nenhuma — larga a venda que esperava, e a próxima tentativa trava de
// novo, porque a gaveta continua aberta. Tirá-lo transformaria o diálogo numa
// armadilha cuja única saída seria um gesto escondido: gaveta emperrada aberta
// + operador que não conhece o Esc = balcão congelado com fila na frente, que é
// exatamente o modo de falha que não se aceita aqui.
//
// O que ele PRECISAVA e não tinha era rastro: encerrava o bloqueio em silêncio.
// Agora sai como desfecho `dismissed`, com duração, e desistência repetida vira
// anomalia no B.I. E o rótulo diz o que ele faz, em vez de um "Close" genérico.
//
// O que fica escondido é a SAÍDA, nunca o ESTADO: `role="alertdialog"` +
// `aria-live` anunciam a gaveta aberta a leitor de tela normalmente.
//
// A saída normal continua não sendo botão nenhum — é fechar a gaveta. A tela
// sonda o sensor e sai sozinha. Não existe "Já fechei": auto-declaração era a
// mentira que o sensor existe para desmentir, e era o bypass mais barato do
// sistema (com o diálogo na tela, puxar o cabo e clicar nele liberava calado).
const emit = defineEmits<{
  "update:open": [boolean];
  manager: [];
}>();

const props = defineProps<{ open: boolean; sensorLost?: boolean; busy?: boolean }>();

// Esc é o gesto treinado, e precisa ser capturado ANTES de qualquer outro
// ouvinte: na fase de bolha o diálogo já teria se fechado, e o mesmo toque
// abriria a saída e desistiria da venda. `capture: true` + `stopPropagation`
// garantem que esta tecla não atravessa para o diálogo (nem para o PIN por
// cima, que tem o seu próprio Esc para voltar).
function onKeydownCapture(event: KeyboardEvent) {
  if (event.key !== "Escape" || !props.open) return;
  // Com o PIN aberto por cima, quem trata o Esc é ele (volta para a trava).
  if (document.querySelector('[data-drawer-manager-auth][data-state="open"]')) return;
  event.preventDefault();
  event.stopPropagation();
  emit("manager");
}

onMounted(() => document.addEventListener("keydown", onKeydownCapture, true));
onBeforeUnmount(() => document.removeEventListener("keydown", onKeydownCapture, true));
</script>

<template>
  <UiDialog :open="open" @update:open="(value) => emit('update:open', value)">
    <UiDialogContent
      class="sm:max-w-sm"
      role="alertdialog"
      hide-close
    >
      <!-- O fechar do canto, com o nome do que ele faz. O padrão do kit anuncia
           "Close" — genérico e em inglês —, e aqui a diferença importa: não é
           "fechar o aviso", é DESISTIR da venda que estava esperando. -->
      <template #close>
        <UiDialogClose
          class="absolute right-4 top-4 grid size-11 place-items-center rounded-md text-muted-foreground/70 transition hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Desistir desta venda"
          data-drawer-lock-dismiss
        >
          <Icon name="lucide:x" class="size-4" />
        </UiDialogClose>
      </template>
      <UiDialogHeader class="items-center text-center">
        <div class="mx-auto grid size-12 place-items-center rounded-md border border-warning/40 bg-warning/10 text-amber-600 dark:text-amber-400">
          <Icon name="lucide:inbox" class="size-6" />
        </div>
        <UiDialogTitle class="text-lg">Gaveta aberta</UiDialogTitle>
        <UiDialogDescription>
          Feche a gaveta para continuar.
        </UiDialogDescription>
      </UiDialogHeader>

      <!-- ⚠️ O `relative` vive AQUI, num wrapper, e não no `UiDialogContent`:
           lá ele sobrescreveria o `fixed` do reka-ui e o diálogo sairia do
           centro da tela. -->
      <div class="relative flex flex-col items-stretch gap-3 pb-1">
        <p class="flex items-center justify-center gap-2 text-sm text-muted-foreground" role="status" aria-live="polite">
          <Icon name="lucide:loader-circle" class="size-4 animate-spin" />
          Aguardando a gaveta fechar
        </p>

      <!-- A porta da emergência para quem NÃO tem teclado.
           Três pontinhos, sem rótulo, sem cadeado, sem explicação — quem foi
           treinado sabe; quem não foi não aprende olhando. O alvo de toque é
           grande (44px) mesmo com o desenho minúsculo: discrição é do desenho,
           nunca da área clicável, senão vira gerente cutucando o vidro na
           frente da fila. -->
        <button
          type="button"
          class="absolute -bottom-3 -left-4 grid size-11 place-items-center rounded-md text-muted-foreground/25 transition hover:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Mais opções"
          :disabled="busy"
          data-drawer-lock-escape-hatch
          @click="emit('manager')"
        >
          <Icon name="lucide:ellipsis" class="size-4" />
        </button>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
