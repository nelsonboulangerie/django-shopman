<script setup lang="ts">
// A barra do polegar: as seções do app no pé da tela onde o rail não existe (celular e
// tablet em pé; V6-KIT, `depois-navegacao.jpg` nível 1). Par do `OperatorSuiteRail`.
// Medidas do `.nav` de `orders-phone3.html`: pílula de 56×30 no item ativo, rótulo de
// 12px, selo âmbar e ponto de atenção iguais aos do rail.
//
// Até 4 seções + "Mais" (v4 `cozinha-celular4.html`, T-08): o que não cabe vai para o
// "Mais", junto com o menu do operador (Bloquear, trocar de operador, tema, giro,
// capacidade). O "Mais" existe sempre: sem ele o celular não trava nem troca de
// operador (K06, regressão de função).
//
// ⚠️ Mora no FIM da coluna de conteúdo, `sticky bottom-0` (não `fixed inset-x-0`): fixa
// na largura da janela ela cobria o que estivesse à esquerda. `data-focus-obstruction`
// é a régua do kit para o que flutua na base: o próximo foco e o "Tem mais abaixo"
// descontam a altura dela.
import { computed, ref } from "vue";

import { activeSectionKey, type OperatorSection } from "../presentation/appBar";
import {
  PHONE_BAR_SECTIONS,
  phoneBarLayout,
  railSignalChip,
  sectionDescription,
  sectionRailSignal,
} from "../presentation/suiteChrome";
import { TAB_BAR_UI } from "../presentation/tabBar";

const props = withDefaults(defineProps<{
  sections: readonly OperatorSection[];
  label: string;
  current?: string;
  /** Operador ativo: o "Mais" mostra o nome dele e o Bloquear. */
  operatorName?: string;
  /**
   * Quantas seções antes do "Mais". Padrão 4 (navegação v3, "até 4 + Mais"); a Cozinha
   * usa 3, como a v4 do celular (Preparo · Saída · Estações · Mais).
   */
  max?: number;
}>(), { current: undefined, operatorName: undefined, max: PHONE_BAR_SECTIONS });

const emit = defineEmits<{ select: [key: string]; lock: [] }>();

const route = useRoute();
const active = computed(() => props.current ?? activeSectionKey(route.path, props.sections));
const barSections = computed(() => props.sections.filter((section) => section.where !== "rail"));
const layout = computed(() => phoneBarLayout(barSections.value, props.max));
// O "Mais" é item da MESMA barra (ícone em cima, nome embaixo, como as seções): o
// desenho "With bottom tab bar" do kit (`TAB_BAR_UI`, o mesmo da barra inferior do
// shell). A folha é a do `OperatorPhoneMenu`, aberta por aqui.
const moreOpen = ref(false);
const activeInOverflow = computed(() => layout.value.overflow.some((section) => section.key === active.value));
const overflowAttention = computed(() => layout.value.overflow.some((section) => section.badge || section.attention));
const visibleItems = computed(() => [
  ...layout.value.visible.map((section) => ({
    label: section.shortLabel || section.label,
    icon: section.icon,
    to: section.to,
    active: active.value === section.key,
    // O sinal é o MESMO da barra lateral e da barra inferior do shell: o chip do item.
    chip: (() => {
      const signal = sectionRailSignal(section);
      return signal ? railSignalChip(signal) : undefined;
    })(),
    "aria-label": sectionDescription(section),
    "data-section": section.key,
    onSelect: () => {
      if (!section.to) emit("select", section.key);
    },
  })),
  {
    label: "Mais",
    icon: "i-lucide-ellipsis",
    active: activeInOverflow.value,
    chip: overflowAttention.value ? { color: "warning" as const } : undefined,
    "aria-label": props.operatorName
      ? `Mais: outras seções e o menu de ${props.operatorName}`
      : "Mais: outras seções e o menu do dispositivo",
    "aria-haspopup": "dialog",
    "data-operator-phone-menu": "",
    "data-variant": "bar",
    "data-active": activeInOverflow.value || undefined,
    onSelect: () => {
      moreOpen.value = true;
    },
  },
]);
</script>

<template>
  <nav
    v-if="barSections.length > 1"
    class="sticky bottom-0 z-[var(--op-layer-chrome)] mt-auto flex border-t border-border bg-card pb-[var(--op-safe-bottom)] rail:hidden print:hidden"
    :aria-label="label"
    data-operator-section-bar
    data-focus-obstruction
  >
    <NuxtNavigationMenu
      class="w-full min-w-0"
      orientation="horizontal"
      :items="visibleItems"
      :ui="TAB_BAR_UI"
      :aria-label="label"
      data-operator-section-items
    />
    <OperatorPhoneMenu
      v-model:open="moreOpen"
      variant="bar"
      :trigger="false"
      :operator-name="operatorName"
      :overflow="layout.overflow"
      :current="active"
      @lock="emit('lock')"
      @select="emit('select', $event)"
    >
      <!-- O que é do app no "Mais", acima do menu do operador (o Terminal do PDV). -->
      <template v-if="$slots.more" #extra><slot name="more" /></template>
    </OperatorPhoneMenu>
  </nav>
</template>
