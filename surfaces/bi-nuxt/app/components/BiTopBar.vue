<script setup lang="ts">
// Cabeçalho do B.I.: navegação por domínio + a janela de análise compartilhada.
// A janela mora aqui (e não em cada página) porque a pergunta "em que período?"
// é uma só para o app inteiro: trocar de aba não pode trocar de período. Ela vive
// na URL (`useBiWindow`), e por isso cada aba leva a query da janela no link.
//
// O controle de período nasceu aqui e foi promovido ao kit (`OperatorPeriodPicker`,
// Tipo 2 dos controles de data da casa, decisão do dono de 02/10/2026): UM botão
// que sempre DIZ a janela ativa, os chips e o personalizado no popover dele, e ‹ ›
// que andam um período igual ao escolhido.
//
// O desenho da barra (alvo de toque, `aria-current`, revelação da aba ativa) vem do
// `OperatorAppBar` do kit.
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";

const BASE_SECTIONS: OperatorSection[] = [
  { key: "production", label: "Produção", icon: "lucide:flame", to: "/" },
  { key: "sales", label: "Vendas", icon: "lucide:shopping-basket", to: "/sales" },
  { key: "cash", label: "Caixa", icon: "lucide:banknote", to: "/cash" },
  { key: "customers", label: "Clientes", icon: "lucide:users", to: "/customers" },
  { key: "profiles", label: "Perfis", icon: "lucide:armchair", to: "/profiles" },
  { key: "explore", label: "Explorar", icon: "lucide:compass", to: "/explore" },
  // As outras abas olham o que aconteceu; esta projeta.
  { key: "forecast", label: "Projeção", icon: "lucide:telescope", to: "/forecast" },
  // Última: a IA propõe cenários sobre os agregados; o gestor decide.
  { key: "scenarios", label: "Cenários", icon: "lucide:sparkles", to: "/scenarios" },
];

const { selection, bounds, presets, windowQuery } = useBiWindow();

const sections = computed<OperatorSection[]>(() => {
  const query = new URLSearchParams(windowQuery.value).toString();
  if (!query) return BASE_SECTIONS;
  return BASE_SECTIONS.map((section) => ({ ...section, to: `${section.to}?${query}` }));
});
</script>

<template>
  <OperatorAppBar :sections="sections" label="Seções do B.I.">
    <template #end>
      <OperatorPeriodPicker
        v-model="selection"
        :presets="presets"
        custom
        :today="bounds.today"
        :max="bounds.max"
        :epoch="bounds.epoch"
        label="Período de análise"
      />
    </template>
  </OperatorAppBar>
</template>
