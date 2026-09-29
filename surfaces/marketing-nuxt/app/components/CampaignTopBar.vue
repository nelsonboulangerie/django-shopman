<script setup lang="ts">
// Cabeçalho de seção do Marketing — mora no topo do CONTEÚDO (não é o rail). Segura a
// navegação própria (Painel/Campanhas/Plataformas) e o sino do Marketing.
//
// ⚠️ O Histórico saiu daqui: ele respondia uma pergunta fraca ("o que saiu?", cronológico). A
// forte — "esta campanha está funcionando?" — mora na campanha, e a linha do tempo completa
// ficou como "ver tudo" no Painel. Ver `docs/plans/MARKETING-UX-PLAN.md` §8.
// As funções comuns (Shopman Apps, operador, tema) vivem no OperatorRail à esquerda.
//
// A revelação da aba ativa (rolar a nav até a seção em que o gestor está, e de novo
// quando a fonte da casa carrega) nasceu AQUI, por causa de um defeito real: a 390px
// cabiam duas abas e meia, e em `/platforms` a aba ativa nascia fora da tela — ele lia
// a barra e concluía que estava no Painel. Agora isso vive no `OperatorAppBar` do kit,
// e vale para os outros apps, que tinham o mesmo defeito sem ter notado.
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";

const route = useRoute();
const v2SectionRefs = new Set(["today", "campaigns", "offers", "platforms"]);
const activeV2Section = computed(() => {
  if (route.path === "/campaigns" || route.path === "/templates")
    return "campaigns";
  if (route.path === "/platforms") return "platforms";
  if (route.path !== "/v2") return "today";
  const requested = String(route.query.area || "today");
  return v2SectionRefs.has(requested) ? requested : "today";
});

const v2Sections: OperatorSection[] = [
  {
    key: "today",
    label: "Hoje",
    icon: "lucide:sparkles",
    to: "/v2?area=today",
  },
  {
    key: "campaigns",
    label: "Campanhas",
    icon: "lucide:send",
    to: "/v2?area=campaigns",
    match: ["/campaigns", "/templates"],
  },
  {
    key: "offers",
    label: "Ofertas e cupons",
    icon: "lucide:badge-percent",
    to: "/v2?area=offers",
  },
  {
    key: "platforms",
    label: "Plataformas",
    icon: "lucide:share-2",
    to: "/v2?area=platforms",
    match: ["/platforms"],
  },
];

const sections = v2Sections;
</script>

<template>
  <OperatorAppBar
    :sections="sections"
    :current="activeV2Section"
    label="Seções do Marketing"
  >
    <template #end>
      <MarketingNotificationsBell />
    </template>
  </OperatorAppBar>
</template>
