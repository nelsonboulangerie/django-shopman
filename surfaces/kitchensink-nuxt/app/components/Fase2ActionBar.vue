<script setup lang="ts">
// Protótipo da `OperatorActionBar` (K3), rodada 2 (dono, 09/10: "mais contraste, como no
// Storefront; pode ser flutuante; superfície escura"). A estrutura de sucesso do
// `.shop-action-dock` da loja, como regra:
//   - FLUTUA sobre o conteúdo, com 12 px de folga nas laterais e acima da barra inferior;
//   - a superfície é INVERTIDA (escura no tema claro, creme no tema escuro): o polegar
//     acha a ação de longe, e nada da tela se confunde com ela;
//   - uma linha de contexto (o número que a ação mexe), UMA ação grande e o motivo
//     escrito quando ela não pode; a segunda ação, se existir, é `ghost`.
// Os tokens do Nuxt UI são redefinidos SÓ dentro da barra (o mesmo recurso do rail
// dourado no `app.config` do kit): o botão `neutral` `solid` vira o claro sobre o escuro,
// sem cor nova nem classe copiada. Quem a usa reserva a altura dela no fim do conteúdo
// (o último item nunca fica coberto) e a esconde com o teclado aberto.
withDefaults(
  defineProps<{
    contextLabel: string;
    contextValue: string;
    action: string;
    reason?: string;
    loading?: boolean;
    secondary?: string;
    icon?: string;
    /** Atalho de teclado mostrado na ação (PDV: F2). */
    kbd?: string;
  }>(),
  { reason: "", loading: false, secondary: "", icon: undefined, kbd: "" },
);
defineEmits<{ act: []; secondary: [] }>();

// O escopo invertido: o fundo é a tinta do texto da página; dentro dele, o texto passa
// a ser a cor clara e o "inverso" (o botão sólido neutro) volta a ser o cartão.
const INVERTED_SCOPE = [
  "bg-(--foreground) text-(--primary-foreground)",
  "[--ui-text:var(--primary-foreground)]",
  "[--ui-text-highlighted:var(--primary-foreground)]",
  "[--ui-text-toned:var(--primary-foreground)]",
  "[--ui-text-muted:color-mix(in_srgb,var(--primary-foreground)_72%,transparent)]",
  "[--ui-bg-inverted:var(--card)]",
  "[--ui-text-inverted:var(--foreground)]",
  "[--ui-bg-elevated:color-mix(in_srgb,var(--primary-foreground)_14%,transparent)]",
  "[--ui-border:color-mix(in_srgb,var(--primary-foreground)_28%,transparent)]",
  "[--ui-border-accented:color-mix(in_srgb,var(--primary-foreground)_40%,transparent)]",
].join(" ");
</script>

<template>
  <div
    class="space-y-2 rounded-lg p-3 shadow-lg"
    :class="INVERTED_SCOPE"
    role="region"
    :aria-label="contextLabel"
    data-focus-obstruction
    data-fase2-action-bar
  >
    <div class="flex items-baseline justify-between gap-3">
      <span class="text-sm text-muted">{{ contextLabel }}</span>
      <span class="text-base font-semibold tabular-nums">{{ contextValue }}</span>
    </div>
    <div class="flex items-center gap-2">
      <NuxtButton
        v-if="secondary"
        :label="secondary"
        color="neutral"
        variant="ghost"
        size="xl"
        @click="$emit('secondary')"
      />
      <NuxtButton
        :label="action"
        :icon="icon"
        color="neutral"
        size="xl"
        block
        :loading="loading"
        :disabled="Boolean(reason)"
        @click="$emit('act')"
      >
        <template v-if="kbd" #trailing><NuxtKbd :value="kbd" /></template>
      </NuxtButton>
    </div>
    <p v-if="reason" class="text-sm text-muted" role="status">{{ reason }}</p>
  </div>
</template>
