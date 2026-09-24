<script setup lang="ts">
// Uma seção de documento legal. Só existe dentro de `LegalDocument`, que lê o
// `id` e o título daqui para montar o índice — por isso o título é um slot
// (`#title`) e não uma prop: ele fica no template da página, junto do resto do
// texto que a trava de versão confere (tests/legalVersion.test.ts).
//
// O `id` é a âncora pública (`/privacy#sharing`): em inglês, como toda URL da
// casa, e estável — link compartilhado aponta para ele.
defineProps<{ id: string }>()
</script>

<template>
  <section
    :id="id"
    class="shop-legal-section"
    :aria-labelledby="`${id}-title`"
    :data-focus-target="id"
    data-legal-section
  >
    <h2 :id="`${id}-title`" class="shop-legal-heading">
      <slot name="title" />
    </h2>
    <div class="shop-legal-body">
      <slot />
    </div>
  </section>
</template>
