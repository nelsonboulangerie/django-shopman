<script setup lang="ts">
// Moldura de dispositivo para a maquete das barras: celular (390 px) ou mesa. A
// mesa rola DENTRO da moldura quando a tela é estreita; a página nunca rola na
// horizontal.
withDefaults(defineProps<{ kind?: "phone" | "desk"; label: string; tall?: boolean }>(), {
  kind: "phone",
  tall: false,
});
</script>

<template>
  <figure class="min-w-0 space-y-2" :data-fase2-frame="kind">
    <figcaption class="text-xs font-medium text-muted">{{ label }}</figcaption>
    <div
      class="overflow-x-auto rounded-lg border border-default bg-default"
      :class="kind === 'phone' ? 'w-full max-w-sm' : 'w-full'"
    >
      <div :class="[kind === 'phone' ? 'flex flex-col' : 'flex min-w-3xl flex-col', tall ? 'min-h-160' : '']">
        <slot />
      </div>
    </div>
  </figure>
</template>
