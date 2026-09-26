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

const sections: OperatorSection[] = [
  { key: "board", label: "Painel", icon: "lucide:megaphone", to: "/" },
  // "Campanhas", não "Regras": a entidade é `Campaign`, e a tela tinha um terceiro nome.
  // `/templates` conta como Campanhas: a biblioteca de modelos é vista secundária dela,
  // não seção irmã — o gestor pensa "o que a padaria diz", não "modelos e regras".
  {
    key: "campaigns",
    label: "Campanhas",
    icon: "lucide:sliders-horizontal",
    to: "/campaigns",
    match: ["/templates"],
  },
  {
    key: "v2-preview",
    label: "Prévia V2",
    icon: "lucide:sparkles",
    to: "/v2",
  },
  // Plataformas: por onde o anúncio SAI. Não confundir com canal, que é por onde se vende
  // (ADR-020 §10). Era a casa que faltava — sem ela, a config vazava para o painel.
  { key: "platforms", label: "Plataformas", icon: "lucide:share-2", to: "/platforms" },
];
</script>

<template>
  <OperatorAppBar :sections="sections" label="Seções do Marketing">
    <template #end>
      <MarketingNotificationsBell />
    </template>
  </OperatorAppBar>
</template>
