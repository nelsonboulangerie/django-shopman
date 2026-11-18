<script setup lang="ts">
// A porta do app instalado (`start_url` do manifesto das rotas): volta ao último link aberto
// neste celular; sem nenhum, a tela inicial (tema e "Adicionar à tela inicial").
useCourierPageHead()

const ready = ref(false)
onMounted(async () => {
  const last = lastCourierToken()
  if (last) {
    await navigateTo(`/rota/${encodeURIComponent(last)}`, { replace: true })
    return
  }
  ready.value = true
})
</script>

<template>
  <ClientOnly>
    <CourierRideApp v-if="ready" token="" />
  </ClientOnly>
</template>
