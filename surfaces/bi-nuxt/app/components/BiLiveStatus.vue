<script setup lang="ts">
// O ponto e a hora colados no título (prévia `depois-bi-vendas`, pino 2: "Título da
// tela com 'ao vivo' em ponto e hora; só cresce quando a leitura atrasa"). O B.I. é
// leitura calma (sem poll): a hora é a da última leitura que chegou. Falhou a última,
// o ponto fica vermelho e diz "Sem conexão", com a hora do que está na tela.
const props = defineProps<{ pending: boolean; error: unknown }>();

const lastRead = ref("");
function stamp() {
  lastRead.value = new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date());
}
onMounted(() => {
  if (!props.pending && !props.error) stamp();
});
watch(
  () => props.pending,
  (now, before) => {
    if (before && !now && !props.error) stamp();
  },
);
const failed = computed(() => Boolean(props.error));
</script>

<template>
  <OperatorLiveStatus
    :tone="failed ? 'off' : 'live'"
    :time="lastRead"
    :label="failed ? 'Sem conexão' : 'Atualizado'"
    :detail="failed ? 'A última leitura não chegou; os números na tela são os de antes.' : 'Leitura do período escolhido'"
    data-bi-live
  />
</template>
