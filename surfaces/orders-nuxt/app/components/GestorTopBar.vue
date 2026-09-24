<script setup lang="ts">
// Cabeçalho de seção do Gestor — mora no topo do CONTEÚDO (não é o rail). O desenho da
// barra, o alvo de toque, o `aria-current` e a revelação da aba ativa vêm do
// `OperatorAppBar` (kit): eram quatro barras à mão, desenhadas de três jeitos. Aqui
// fica só o que é do Gestor — quais são as seções e o que vai no cluster da direita.
// As funções comuns (Shopman Apps, operador, tema) vivem no OperatorRail à esquerda.
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";

// Canal ou feed desligado, pausado ou divergente: um ponto âmbar + "1 desligado" no
// item Canais. Estado normal não mostra nada.
const { attention } = useChannelAttention();

const sections = computed<OperatorSection[]>(() => [
  { key: "orders", label: "Pedidos", icon: "lucide:clipboard-list", to: "/" },
  { key: "catalog", label: "Catálogo", icon: "lucide:book-open", to: "/catalog" },
  {
    key: "feeds",
    label: "Canais",
    icon: "lucide:monitor-play",
    to: "/feeds",
    // `/channels/<ref>` é a mesma seção: quem abre um canal não saiu de Canais.
    match: ["/channels"],
    attention: attention.value?.label || undefined,
  },
]);

// Porta para o cadastro de clientes. Fica FORA do segmented control de propósito:
// aquele conjunto é de seções DESTE app, e esta é uma saída para o Admin — que
// hoje é o único lugar onde se busca, edita e cria cliente. Quem atende precisa
// de um caminho permanente até lá, não só do link que nasce dentro de um pedido.
// Quando o Gestor tiver a própria tela de clientes, isto vira mais uma aba.
const adminBaseUrl = useRuntimeConfig().public.adminBaseUrl as string;
const customersUrl = computed(() =>
  adminBaseUrl ? `${adminBaseUrl}/admin/guestman/customer/` : "",
);
</script>

<template>
  <OperatorAppBar :sections="sections" label="Seções do Gestor">
    <template #end>
      <a
        v-if="customersUrl"
        :href="customersUrl"
        target="_blank"
        rel="noopener"
        class="inline-flex min-h-control items-center gap-1.5 rounded-md px-2.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        title="Buscar, editar e cadastrar clientes (abre o Admin)"
        data-customers-link
      >
        <Icon name="lucide:users" class="size-4" />
        <span>Clientes</span>
        <Icon name="lucide:external-link" class="size-3 opacity-60" />
      </a>
    </template>
  </OperatorAppBar>
</template>
