<script setup lang="ts">
// Ponte autenticada para a prévia estática. A página só é instanciada depois do
// gate de operador em app.vue; nenhum comando ou API de publicação é chamado.
useHead({ title: "Prévia V2" });

onMounted(() => {
  window.location.assign("/marketing-v2-preview/index.html#campaigns");
});
</script>

<template>
  <main class="mx-auto grid w-full max-w-4xl flex-1 place-items-center px-4 py-12">
    <section class="max-w-md rounded-lg border bg-card p-6 text-center shadow-sm">
      <Icon name="lucide:sparkles" class="mx-auto size-7 text-primary" />
      <h1 class="mt-3 text-lg font-semibold">Abrindo a prévia do Marketing V2</h1>
      <p class="mt-2 text-sm text-muted-foreground">
        É um ambiente navegável de demonstração. Nenhuma publicação, mensagem ou
        autorização externa será enviada.
      </p>
      <a
        href="/marketing-v2-preview/index.html#campaigns"
        class="mt-4 inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground"
      >
        Abrir prévia
      </a>
    </section>
  </main>
</template>
