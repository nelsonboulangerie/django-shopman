<script setup lang="ts">
// As leituras da Produção, cada uma com o seu tempo (laudo F08): "Sobrou ou
// faltou" lê UM dia (`?day=`), "Lotes no período" e "Encomendas na Cozinha" leem uma
// janela (`?period=`). São abas da mesma tela, e a aba mora na URL (`?view=lots`,
// `?view=preorders`): o link copiado abre
// a mesma aba, e trocar de aba não perde o dia nem a janela. Abre a linha de
// recortes do cabeçalho.
import { PRODUCTION_VIEWS, productionView } from "~/presentation/production";

const route = useRoute();
const router = useRouter();
const view = computed({
  get: () => productionView(route.query.view),
  set: (next: string) => {
    const rest = { ...route.query };
    delete rest.view;
    void router.replace({ query: next === "day" ? rest : { ...rest, view: next } });
  },
});
</script>

<template>
  <NuxtTabs
    v-model="view"
    :items="[...PRODUCTION_VIEWS]"
    :content="false"
    variant="link"
    aria-label="Leituras da Produção"
    data-bi-production-nav
  />
</template>
