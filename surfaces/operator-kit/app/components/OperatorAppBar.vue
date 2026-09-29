<script setup lang="ts">
// A barra de seções do app — o cabeçalho que fica no topo do CONTEÚDO (não é o rail).
//
// Era escrita à mão em quatro apps (Gestor, B.I., Marketing, Compras) e desenhada de
// três jeitos. O raciocínio, a medição e o que cada um resolvia melhor estão em
// `~/presentation/appBar.ts`. Aqui fica o desenho único:
//
// - alvo de toque `min-h-control` (44px, o token da casa) — o B.I. e o Compras estavam
//   em `h-8`, metade disso, numa barra que se usa com a mão ocupada;
// - `aria-current="page"` na aba ativa, que faz o leitor de tela dizer onde ele está;
// - a aba ativa é trazida para dentro da área visível ao montar, ao trocar de seção e
//   DE NOVO quando a fonte da casa termina de carregar (a largura da aba muda quando a
//   fonte troca, e rolar "o mínimo necessário" depende da largura). Só o Marketing
//   fazia isso, e foi lá que o defeito apareceu: a 390px cabem duas abas e meia, e em
//   `/platforms` a seção ativa nascia fora da tela — o gestor lia a barra e concluía
//   que estava no Painel;
// - a tecla que leva à seção é ENSINADA na própria aba (a Produção já fazia), visível
//   onde há espaço e sempre anunciada em `aria-keyshortcuts`.
//
// O que é de cada app continua de cada app: a lista de seções, o que vai antes (`start`)
// e o cluster da direita (`end`).
import { computed, nextTick, onMounted, ref, resolveComponent, watch } from "vue";

import { activeSectionKey, type OperatorSection } from "../presentation/appBar";

const props = withDefaults(defineProps<{
  sections: readonly OperatorSection[];
  /** Nome da barra para quem navega por leitor de tela ("Seções do Gestor"). */
  label: string;
  /**
   * Seção ativa. Omitida, sai da ROTA — que é o caso dos apps cujas seções são
   * páginas. Apps cuja seção é estado (Compras) passam a chave e escutam `select`.
   */
  current?: string;
  /** Rota atual; só é usada quando `current` não vem. */
  path?: string;
}>(), {
  current: undefined,
  path: undefined,
});

const emit = defineEmits<{ select: [key: string] }>();

// Resolvido no setup: `<component :is>` precisa do componente, e o `NuxtLink` é
// registrado pelo app hospedeiro, não pela layer.
const NuxtLink = resolveComponent("NuxtLink");
const route = useRoute();
const active = computed(() => props.current ?? activeSectionKey(props.path ?? route.path, props.sections));

const nav = ref<HTMLElement | null>(null);
function revealActiveTab() {
  nav.value?.querySelector<HTMLElement>('[data-active="true"]')
    // `inline: "nearest"` rola só o contêiner que precisa e só o necessário; `block:
    // "nearest"` impede que isso arraste a PÁGINA junto quando a barra já está visível.
    ?.scrollIntoView({ inline: "nearest", block: "nearest" });
}

onMounted(() => {
  revealActiveTab();
  document.fonts?.ready.then(revealActiveTab).catch(() => {});
});
watch(active, () => nextTick(revealActiveTab));
</script>

<template>
  <header
    class="flex shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-2 print:hidden"
    data-operator-app-bar
  >
    <RailToggle />
    <div class="h-6 w-px shrink-0 bg-border" />
    <slot name="start" />

    <!-- min-w-0 + overflow-x-auto: no celular a nav rola DENTRO de si mesma. Sem isso
         ela empurra o cabeçalho e a página inteira ganha rolagem horizontal. -->
    <nav
      ref="nav"
      class="flex min-w-0 items-center gap-1 overflow-x-auto rounded-md bg-muted p-1"
      :aria-label="label"
    >
      <component
        :is="section.to ? NuxtLink : 'button'"
        v-for="section in sections"
        :key="section.key"
        :to="section.to"
        :type="section.to ? undefined : 'button'"
        :data-active="active === section.key"
        :data-section="section.key"
        :aria-current="active === section.key ? 'page' : undefined"
        :aria-keyshortcuts="section.shortcut"
        class="inline-flex min-h-control shrink-0 items-center gap-1.5 rounded-md px-3 text-sm transition-all focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        :class="active === section.key
          ? 'bg-card font-semibold text-foreground shadow-sm'
          : 'text-muted-foreground hover:bg-card/60 hover:text-foreground'"
        @click="section.to ? undefined : emit('select', section.key)"
      >
        <Icon
          :name="section.icon"
          class="size-4"
          :class="active === section.key ? 'text-foreground' : 'text-muted-foreground'"
        />
        <span>{{ section.label }}</span>
        <!-- Atenção: um ponto e o número. Estado normal não mostra nada — amarelo por
             escolha da casa é ruído, e ruído constante deixa de ser visto. -->
        <span
          v-if="section.attention"
          class="inline-flex items-center gap-1 text-xs font-medium text-warning"
          :data-attention="section.key"
        >
          <span class="size-1.5 rounded-full bg-warning" aria-hidden="true" />
          {{ section.attention }}
        </span>
        <OperatorKbd v-if="section.shortcut" class="ml-0.5 hidden xl:inline-flex">{{ section.shortcut }}</OperatorKbd>
      </component>
    </nav>

    <div v-if="$slots.end" class="ml-auto flex shrink-0 items-center gap-2">
      <slot name="end" />
    </div>
  </header>
</template>
