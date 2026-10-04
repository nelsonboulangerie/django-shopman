<script setup lang="ts">
// A barra do polegar: as seções do app no pé da tela, só no celular (abaixo de `md`).
// Par do `OperatorSuiteRail` (que mostra as mesmas seções do tablet para cima). Medidas
// do `.nav` de `orders-phone3.html`: pílula de 56×30 no item ativo, rótulo de 12px,
// selo âmbar e ponto de atenção iguais aos do rail.
//
// Nasceu no Marketing (`MarketingSectionBar.vue`, UX-M1), que deixou escrito: "quando
// outro app pedir a barra do pé, ela vira peça da layer". O Gestor pediu.
//
// ⚠️ Mora no FIM da coluna de conteúdo, `sticky bottom-0` (não `fixed inset-x-0`): fixa
// na largura da janela ela cobria o que estivesse à esquerda. Com mais de 6 seções, a
// barra rola na horizontal em vez de espremer os alvos abaixo de 44px.
// `data-focus-obstruction` é a régua do kit para o que flutua na base: o próximo foco e
// o "Tem mais abaixo" descontam a altura dela.
import { computed, resolveComponent } from "vue";

import { activeSectionKey, type OperatorSection } from "../presentation/appBar";

const props = withDefaults(defineProps<{
  sections: readonly OperatorSection[];
  label: string;
  current?: string;
}>(), { current: undefined });

const emit = defineEmits<{ select: [key: string] }>();

const NuxtLink = resolveComponent("NuxtLink");
const route = useRoute();
const active = computed(() => props.current ?? activeSectionKey(route.path, props.sections));
const crowded = computed(() => props.sections.length > 6);
</script>

<template>
  <nav
    v-if="sections.length > 1"
    class="sticky bottom-0 z-30 mt-auto flex border-t border-border bg-card pb-[env(safe-area-inset-bottom)] md:hidden print:hidden"
    :class="crowded ? 'overflow-x-auto no-scrollbar' : ''"
    :aria-label="label"
    data-operator-section-bar
    data-focus-obstruction
  >
    <component
      :is="section.to ? NuxtLink : 'button'"
      v-for="section in sections"
      :key="section.key"
      :to="section.to"
      :type="section.to ? undefined : 'button'"
      :aria-current="active === section.key ? 'page' : undefined"
      :data-section="section.key"
      class="relative flex min-h-16 flex-col items-center justify-center gap-[3px] pt-1.5 pb-1 text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
      :class="[
        crowded ? 'min-w-[4.5rem] flex-none px-1' : 'flex-1',
        active === section.key ? 'text-foreground' : 'text-muted-foreground',
      ]"
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
      <span v-else>{{ section.label }}</span>
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
  </nav>
</template>
