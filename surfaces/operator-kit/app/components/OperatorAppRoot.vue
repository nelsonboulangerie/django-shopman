<script setup lang="ts">
import { pt_br as ptBr } from "@nuxt/ui/locale";

// Locale canônico do Nuxt UI. Sem isto, rótulos internos (barra lateral, alertas,
// calendário, busca) saem em inglês. O catálogo e as apps que adotam o
// OperatorAppRoot falam português; a tradução vive na camada, não em cada tela.
withDefaults(defineProps<{ scrollBody?: boolean }>(), { scrollBody: true });
</script>

<template>
  <NuxtApp
    :scroll-body="scrollBody"
    :toaster="{ position: 'top-right' }"
    :locale="ptBr"
  >
    <slot />
  </NuxtApp>
</template>
