<script setup lang="ts">
// A barra do polegar: as quatro seções do Marketing no pé da tela, só no celular.
//
// ⚠️ Ela mora no FIM da coluna de conteúdo (ver `app.vue`), `sticky bottom-0`, e
// não `fixed inset-x-0`. Fixa na largura da janela ela passava por cima do rail à
// esquerda, e o botão "Tema escuro" do rail, no pé dele, ficava embaixo da barra:
// o operador tocava e o toque ia para a pílula (a11y.spec.ts, 320×568). Na coluna,
// a barra só ocupa a largura do conteúdo, nunca a do rail, e o conteúdo termina
// acima dela pelo próprio fluxo, sem padding reservado.
//
// `data-focus-obstruction` é a régua do kit para o que flutua na base: o próximo
// foco e o "Tem mais abaixo" descontam a altura dela.
const { activeSection, sections } = useMarketingSections();
</script>

<template>
  <nav
    class="sticky bottom-0 z-30 mt-auto grid grid-cols-4 border-t border-border bg-card pb-[env(safe-area-inset-bottom)] sm:hidden print:hidden"
    aria-label="Seções do Marketing no celular"
    data-marketing-bottom-bar
    data-focus-obstruction
  >
    <NuxtLink
      v-for="section in sections"
      :key="section.key"
      :to="section.to"
      :aria-current="activeSection === section.key ? 'page' : undefined"
      :data-section="section.key"
      class="flex min-h-16 flex-col items-center justify-center gap-1 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
      :class="
        activeSection === section.key
          ? 'font-semibold text-foreground'
          : 'text-muted-foreground'
      "
    >
      <span
        class="relative grid h-8 w-14 place-items-center rounded-full"
        :class="activeSection === section.key ? 'bg-primary/15' : ''"
      >
        <Icon :name="section.icon" class="size-5" aria-hidden="true" />
        <span
          v-if="section.attention"
          class="absolute -right-0.5 -top-1 grid min-w-5 place-items-center rounded-full bg-destructive px-1 text-[11px] font-bold tabular-nums text-white"
          aria-hidden="true"
          >{{ section.attention }}</span
        >
      </span>
      <span>{{ section.label }}</span>
      <span v-if="section.attention" class="sr-only"
        >, {{ section.attention }} esperando você</span
      >
    </NuxtLink>
  </nav>
</template>
