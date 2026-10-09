<script setup lang="ts">
// O menu do operador onde o rail não existe: celular e tablet em pé (V6-KIT, K06/T-07).
//
// Do tablet deitado para cima, tema, giro, capacidade e o posto moram no menu das
// iniciais, no pé do `OperatorSuiteRail`, e Bloquear tem item próprio. Sem o rail, esta
// peça leva as mesmas funções a um toque, em todo app:
//
//   - `variant="bar"` (padrão): o "Mais" (⋯) no fim da barra do polegar, como na v4
//     (`cozinha-celular4.html`). Abre uma folha por baixo com as seções que não
//     couberam na barra e, depois, o menu do operador (Bloquear, que é como se troca de
//     operador; tema; giro; capacidade). A `OperatorSectionBar` monta sozinha.
//   - `variant="header"`: as iniciais na barra de 56px, para quem não tem barra embaixo
//     (a Central, uma seção só, como em `depois-hub-celular`).
import { computed } from "vue";

import type { OperatorSection } from "../presentation/appBar";

const props = withDefaults(
  defineProps<{
    /** Operador ativo: dá as iniciais e o Bloquear. */
    operatorName?: string;
    variant?: "bar" | "header";
    /** `bar`: as seções que não couberam na barra. */
    overflow?: readonly OperatorSection[];
    /** `bar`: a seção ativa (acende o "Mais" quando ela mora nele). */
    current?: string;
    /**
     * `bar`: desenha o próprio botão "Mais". `false` quando quem monta já tem o
     * gatilho (a `OperatorSectionBar`, que põe o "Mais" como item da barra, no mesmo
     * desenho das seções) e abre a folha por `v-model:open`.
     */
    trigger?: boolean;
  }>(),
  {
    operatorName: undefined,
    variant: "bar",
    overflow: () => [],
    current: undefined,
    trigger: true,
  },
);

const emit = defineEmits<{ lock: []; select: [key: string] }>();

const initials = computed(() => {
  const words = (props.operatorName || "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "";
  const first = words[0]!.charAt(0);
  const last =
    words.length > 1 ? words[words.length - 1]!.charAt(0) : words[0]!.charAt(1);
  return `${first}${last}`.toUpperCase();
});

const activeInOverflow = computed(() =>
  props.overflow.some((section) => section.key === props.current),
);
const overflowAttention = computed(() =>
  props.overflow.some((section) => section.badge || section.attention),
);
const overflowItems = computed(() =>
  props.overflow.map((section) => ({
    label: section.label,
    icon: section.icon,
    to: section.to,
    badge: section.badge
      ? String(section.badge)
      : section.attention || undefined,
    active: props.current === section.key,
    "data-section": section.key,
    onSelect: () => choose(section),
  })),
);

const open = defineModel<boolean>("open", { default: false });
function lock() {
  open.value = false;
  emit("lock");
}
function choose(section: OperatorSection) {
  open.value = false;
  if (!section.to) emit("select", section.key);
}
</script>

<template>
  <!-- Barra do polegar: o "Mais". -->
  <NuxtDrawer
    v-if="variant === 'bar'"
    v-model:open="open"
    title="Mais"
    description="Outras seções do app e o menu do operador."
    direction="bottom"
  >
    <NuxtChip
      v-if="trigger"
      :show="overflowAttention"
      color="warning"
      size="2xl"
      inset
      class="shrink-0"
    >
      <NuxtButton
        icon="i-lucide-ellipsis"
        label="Mais"
        class="suite-page:min-h-control"
        :color="activeInOverflow ? 'primary' : 'neutral'"
        :variant="activeInOverflow ? 'soft' : 'ghost'"
        :aria-label="
          operatorName
            ? `Mais: outras seções e o menu de ${operatorName}`
            : 'Mais: outras seções e o menu do dispositivo'
        "
        data-operator-phone-menu
        data-variant="bar"
        :data-active="activeInOverflow || undefined"
      />
    </NuxtChip>
    <template #body>
      <div data-operator-phone-menu-panel>
        <NuxtNavigationMenu
          v-if="overflow.length"
          orientation="vertical"
          :items="overflowItems"
          aria-label="Outras seções"
        />
        <div v-if="$slots.extra" data-operator-phone-menu-extra>
          <slot name="extra" />
        </div>
        <OperatorMenuItems
          mode="phone"
          :operator-name="operatorName"
          @lock="lock"
        />
      </div>
    </template>
  </NuxtDrawer>

  <!-- Barra de 56px (quem não tem barra embaixo): as iniciais. -->
  <NuxtPopover v-else v-model:open="open">
    <NuxtButton
      class="rail:hidden suite-page:size-control suite-page:justify-center"
      color="neutral"
      variant="ghost"
      square
      :avatar="initials ? { text: initials } : undefined"
      :icon="initials ? undefined : 'i-lucide-settings-2'"
      :aria-label="
        operatorName ? `Menu de ${operatorName}` : 'Menu do dispositivo'
      "
      data-operator-phone-menu
      data-variant="header"
    />
    <template #content>
      <div data-operator-phone-menu-panel>
        <OperatorMenuItems
          mode="phone"
          :operator-name="operatorName"
          @lock="lock"
        />
      </div>
    </template>
  </NuxtPopover>
</template>
