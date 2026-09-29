<script setup lang="ts">
// Cabeçalho de seção do Gestor — mora no topo do CONTEÚDO (não é o rail). O desenho da
// barra, o alvo de toque, o `aria-current` e a revelação da aba ativa vêm do
// `OperatorAppBar` (kit): eram quatro barras à mão, desenhadas de três jeitos. Aqui
// fica só o que é do Gestor: quais são as seções.
// As funções comuns (Shopman Apps, operador, tema) vivem no OperatorRail à esquerda.
import { gestorSections } from "~/presentation/gestorSections";

// Canal ou feed desligado, pausado ou divergente: um ponto âmbar + "1 desligado" no
// item Canais. Estado normal não mostra nada.
const { attention } = useChannelAttention();

// Clientes só aparece para quem pode usar a seção (`shop.manage_customers`, decisão do
// dono em 24/09/2026). A pergunta é a mesma da antessala, sobre quem está operando: o
// servidor responde sim/não, sem listar permissões. Troca de operador relê.
const { data: session } = useNuxtData<{ operator?: { id: number } }>("operator-session");
const operatorId = computed(() => session.value?.operator?.id ?? null);
const { data: customersAccess } = useFetch<{ authorized?: boolean }>("/api/v1/backstage/operator/session/", {
  key: useOperatorResourceKey("customers-access"),
  query: { perm: "shop.manage_customers" },
  server: true,
  watch: [operatorId],
});

const sections = computed(() =>
  gestorSections({
    channelsAttention: attention.value?.label || "",
    canManageCustomers: customersAccess.value?.authorized === true,
  }),
);
</script>

<template>
  <OperatorAppBar :sections="sections" label="Seções do Gestor" />
</template>
