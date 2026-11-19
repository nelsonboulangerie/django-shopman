<script setup lang="ts">
// A pílula invertida do aviso que pede atenção (cor oposta ao tema, escolha do dono):
// ícone, o que é, um detalhe curto, os gestos do aviso (slot) e o X, que dispensa.
// Nasceu no Gestor (o pedido que pede atenção, no polegar); a pergunta que a Concierge
// levou à equipe usa a mesma (dono, 19/11/2026). Quem usa decide onde ela fica e quando
// volta depois do X: aqui é só a peça.
withDefaults(
  defineProps<{
    icon?: string;
    title: string;
    detail?: string;
    /** No escritório (md+) o detalhe cabe ao lado do título, numa linha só; no
     *  celular o título quebra em até duas linhas em vez de cortar no meio. */
    inline?: boolean;
    closeLabel?: string;
    /** Atributos do X (ex.: `data-attention-close`), para quem testa achar o gesto. */
    closeAttrs?: Record<string, string | boolean>;
  }>(),
  { icon: "i-lucide-bell-ring", detail: "", inline: false, closeLabel: "Fechar o aviso", closeAttrs: () => ({}) },
);
const emit = defineEmits<{ close: [] }>();
</script>

<template>
  <div
    class="flex items-center gap-2 rounded-2xl bg-inverted py-1.5 pl-4 pr-1.5 text-inverted shadow-lg"
    data-operator-attention-pill
  >
    <NuxtIcon :name="icon" class="size-5 shrink-0" />
    <p
      class="min-w-0 flex-1 leading-tight"
      :class="inline ? 'md:flex md:items-baseline md:gap-1.5' : ''"
    >
      <strong
        class="block"
        :class="inline ? 'line-clamp-2 md:truncate' : 'truncate'"
        data-operator-attention-pill-title
        >{{ title }}</strong
      >
      <span v-if="detail && inline" class="hidden opacity-80 md:inline" aria-hidden="true">·</span>
      <span
        v-if="detail"
        class="block truncate text-xs opacity-80"
        :class="inline ? 'md:shrink-0 md:text-sm' : ''"
        data-operator-attention-pill-detail
        >{{ detail }}</span
      >
    </p>
    <slot />
    <NuxtButton
      icon="i-lucide-x"
      color="neutral"
      variant="ghost"
      square
      class="size-11 justify-center text-inverted"
      :aria-label="closeLabel"
      v-bind="closeAttrs"
      @click="emit('close')"
    />
  </div>
</template>
