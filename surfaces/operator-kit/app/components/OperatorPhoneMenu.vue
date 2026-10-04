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
import { computed, ref, resolveComponent } from "vue";
import {
  DialogContent,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
  DialogTrigger,
  PopoverContent,
  PopoverPortal,
  PopoverRoot,
  PopoverTrigger,
} from "reka-ui";

import type { OperatorSection } from "../presentation/appBar";

const props = withDefaults(defineProps<{
  /** Operador ativo: dá as iniciais e o Bloquear. */
  operatorName?: string;
  variant?: "bar" | "header";
  /** `bar`: as seções que não couberam na barra. */
  overflow?: readonly OperatorSection[];
  /** `bar`: a seção ativa (acende o "Mais" quando ela mora nele). */
  current?: string;
}>(), { operatorName: undefined, variant: "bar", overflow: () => [], current: undefined });

const emit = defineEmits<{ lock: []; select: [key: string] }>();

const NuxtLink = resolveComponent("NuxtLink");

const initials = computed(() => {
  const words = (props.operatorName || "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "";
  const first = words[0]!.charAt(0);
  const last = words.length > 1 ? words[words.length - 1]!.charAt(0) : words[0]!.charAt(1);
  return `${first}${last}`.toUpperCase();
});

const activeInOverflow = computed(() => props.overflow.some((section) => section.key === props.current));
const overflowAttention = computed(() => props.overflow.some((section) => section.badge || section.attention));

const open = ref(false);
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
  <DialogRoot v-if="variant === 'bar'" v-model:open="open">
    <DialogTrigger
      class="relative flex min-h-16 flex-1 flex-col items-center justify-center gap-[3px] pt-1.5 pb-1 text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
      :class="activeInOverflow ? 'text-foreground' : 'text-muted-foreground'"
      :aria-label="operatorName ? `Mais: outras seções e o menu de ${operatorName}` : 'Mais: outras seções e o menu do dispositivo'"
      data-operator-phone-menu
      data-variant="bar"
    >
      <span class="grid h-[30px] w-14 place-items-center rounded-full" :class="activeInOverflow ? 'bg-secondary' : ''">
        <Icon name="lucide:ellipsis" class="size-[22px]" aria-hidden="true" />
      </span>
      <span aria-hidden="true">Mais</span>
      <span
        v-if="overflowAttention"
        aria-hidden="true"
        class="absolute top-2.5 left-[calc(50%+10px)] size-[9px] rounded-full bg-suite-badge ring-2 ring-card"
      />
    </DialogTrigger>
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-[70] bg-black/40" />
      <DialogContent
        class="fixed inset-x-0 bottom-0 z-[70] max-h-[85dvh] overflow-y-auto rounded-t-2xl border-t border-border bg-popover p-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] text-popover-foreground shadow-lg outline-hidden"
        data-operator-phone-menu-panel
      >
        <div class="mx-auto mt-1 mb-2 h-1 w-10 rounded-full bg-border" aria-hidden="true" />
        <DialogTitle class="sr-only">Mais</DialogTitle>
        <DialogDescription class="sr-only">Outras seções do app e o menu do operador.</DialogDescription>
        <nav v-if="overflow.length" class="flex flex-col border-b border-border pb-1.5 mb-1.5" aria-label="Outras seções">
          <component
            :is="section.to ? NuxtLink : 'button'"
            v-for="section in overflow"
            :key="section.key"
            :to="section.to"
            :type="section.to ? undefined : 'button'"
            :aria-current="current === section.key ? 'page' : undefined"
            :data-section="section.key"
            class="flex min-h-12 w-full items-center gap-3 rounded-md px-2.5 text-left op-body transition hover:bg-accent"
            :class="current === section.key ? 'bg-secondary font-semibold' : ''"
            @click="choose(section)"
          >
            <Icon :name="section.icon" class="size-5 text-muted-foreground" aria-hidden="true" />
            <span class="min-w-0 flex-1">{{ section.label }}</span>
            <span v-if="section.attention" class="op-micro text-muted-foreground">{{ section.attention }}</span>
            <span
              v-if="section.badge"
              class="h-[18px] min-w-[18px] rounded-full bg-suite-badge px-[5px] text-[11px] leading-[18px] font-bold tabular-nums text-suite-badge-foreground"
            >{{ section.badge }}</span>
          </component>
        </nav>
        <div v-if="$slots.extra" class="mb-1.5 border-b border-border pb-1.5" data-operator-phone-menu-extra>
          <slot name="extra" />
        </div>
        <OperatorMenuItems mode="phone" :operator-name="operatorName" @lock="lock" />
      </DialogContent>
    </DialogPortal>
  </DialogRoot>

  <!-- Barra de 56px (quem não tem barra embaixo): as iniciais. -->
  <PopoverRoot v-else v-model:open="open">
    <PopoverTrigger as-child>
      <button
        type="button"
        class="grid size-12 shrink-0 place-items-center rounded-md rail:hidden"
        :aria-label="operatorName ? `Menu de ${operatorName}` : 'Menu do dispositivo'"
        data-operator-phone-menu
        data-variant="header"
      >
        <span
          class="grid size-9 place-items-center rounded-full bg-muted text-[13px] font-semibold text-foreground"
          aria-hidden="true"
        >
          <template v-if="initials">{{ initials }}</template>
          <Icon v-else name="lucide:settings-2" class="size-5" />
        </span>
      </button>
    </PopoverTrigger>
    <PopoverPortal>
      <PopoverContent
        side="bottom"
        align="end"
        :side-offset="4"
        :collision-padding="8"
        class="z-50 w-72 rounded-lg border bg-popover p-1.5 text-popover-foreground shadow-lg outline-hidden"
        data-operator-phone-menu-panel
      >
        <OperatorMenuItems mode="phone" :operator-name="operatorName" @lock="lock" />
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>
