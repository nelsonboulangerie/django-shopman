<script setup lang="ts">
// A rota do entregador da casa (DEV-2026-030, M2): o link que o balcão manda pelo WhatsApp.
// Rota em português porque é do Storefront (CLAUDE.md, "URL é em inglês"). Vive aqui e não
// num app novo para não criar componente nem DNS na DigitalOcean.
const route = useRoute()
const token = computed(() => String(route.params.token || ''))

useCourierPageHead()
</script>

<template>
  <ClientOnly>
    <CourierRideApp :token="token" />
  </ClientOnly>
</template>
