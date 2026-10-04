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
import { computed, resolveComponent } from "vue";

import { activeSectionKey, type OperatorSection } from "../presentation/appBar";
import { PHONE_BAR_SECTIONS, phoneBarLayout } from "../presentation/suiteChrome";

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

const NuxtLink = resolveComponent("NuxtLink");
const route = useRoute();
const active = computed(() => props.current ?? activeSectionKey(route.path, props.sections));
const barSections = computed(() => props.sections.filter((section) => section.where !== "rail"));
const layout = computed(() => phoneBarLayout(barSections.value, props.max));
</script>

<template>
  <nav
    v-if="barSections.length > 1"
    class="sticky bottom-0 z-30 mt-auto flex border-t border-border bg-card pb-[env(safe-area-inset-bottom)] rail:hidden print:hidden"
    :aria-label="label"
    data-operator-section-bar
    data-focus-obstruction
  >
    <component
      :is="section.to ? NuxtLink : 'button'"
      v-for="section in layout.visible"
      :key="section.key"
      :to="section.to"
      :type="section.to ? undefined : 'button'"
      :aria-current="active === section.key ? 'page' : undefined"
      :data-section="section.key"
      class="relative flex min-h-16 flex-1 flex-col items-center justify-center gap-[3px] pt-1.5 pb-1 text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
      :class="active === section.key ? 'text-foreground' : 'text-muted-foreground'"
      @click="section.to ? undefined : emit('select', section.key)"
    >
      <span
        class="grid h-[30px] w-14 place-items-center rounded-full"
        :class="active === section.key ? 'bg-secondary' : ''"
      >
        <Icon :name="section.icon" class="size-[22px]" aria-hidden="true" />
      </span>
      <span v-if="section.shortLabel && section.shortLabel !== section.label" aria-hidden="true" data-section-short>{{ section.shortLabel }}</span>
      <span v-if="section.shortLabel && section.shortLabel !== section.label" class="sr-only">{{ section.label }}</span>
      <span v-else class="max-w-full truncate px-0.5">{{ section.label }}</span>
      <span
        v-if="section.badge"
        aria-hidden="true"
        class="absolute top-1 left-[calc(50%+8px)] h-[18px] min-w-[18px] rounded-full bg-suite-badge px-[5px] text-[11px] leading-[18px] font-bold tabular-nums text-suite-badge-foreground"
      >{{ section.badge }}</span>
      <span
        v-else-if="section.attention"
        aria-hidden="true"
        class="absolute top-2.5 left-[calc(50%+10px)] size-[9px] rounded-full bg-suite-badge ring-2 ring-card"
      />
      <span v-if="section.badgeLabel" class="sr-only">, {{ section.badgeLabel }}</span>
      <span v-if="section.attention" class="sr-only">, {{ section.attention }}</span>
    </component>
    <OperatorPhoneMenu
      variant="bar"
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
