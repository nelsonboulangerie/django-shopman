<script setup lang="ts">
/**
 * "Não consegui conferir seu acesso" — a tela para quando a PERGUNTA falhou.
 *
 * Existe porque os apps de operador confundiam duas coisas muito diferentes:
 * a sessão MORREU (401/403 `not_authenticated`) e a pergunta NÃO PÔDE SER FEITA
 * (502/503/504 no redeploy, rede caindo, Django ainda subindo). Com
 * `canIdentify = session !== null`, qualquer falha zera a resposta e a tela sobe
 * o formulário de senha — dizendo "você foi deslogado" para quem não foi. O
 * alpha faz redeploy a cada push no `main`, várias vezes por dia, e era isso
 * que o operador via como "o login cai toda hora".
 *
 * Quem distingue os dois casos é `sessionUnavailable`, que já existia em
 * `useOperatorLock` e só o Marketing consumia. Aqui o desenho vira capability
 * do kit, para os consumidores não copiarem trinta linhas de markup cada um.
 *
 * Pedir de novo é a única ação: não há o que digitar quando o servidor é que
 * não respondeu.
 */
defineProps<{
  /** O que ficou inacessível, na voz do app. Ex.: "os pedidos", "o painel de Marketing". */
  scope?: string;
}>();

const emit = defineEmits<{ retry: [] }>();
</script>

<template>
  <main
    class="grid min-h-screen flex-1 place-items-center p-4"
    data-operator-session-unavailable
  >
    <NuxtEmpty
      class="max-w-sm text-center"
      icon="i-lucide-wifi-off"
      title="Não foi possível conferir seu acesso"
      :description="`Você continua conectado${scope ? `, mas ${scope} não carregou` : ''}. Isso costuma ser uma instabilidade de rede ou uma atualização no ar.`"
      :actions="[
        {
          label: 'Tentar de novo',
          icon: 'i-lucide-rotate-cw',
          color: 'neutral',
          variant: 'outline',
          onClick: () => emit('retry'),
        },
      ]"
    />
  </main>
</template>
