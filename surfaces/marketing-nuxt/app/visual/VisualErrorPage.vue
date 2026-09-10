<script setup lang="ts">
const route = useRoute();
const statusCode = Number(route.params.status);
const supported = [404, 426, 500, 503];

onMounted(() => {
  showError(
    createError({
      statusCode: supported.includes(statusCode) ? statusCode : 500,
      message: "Cenário hermético da matriz visual",
      data: {
        code: statusCode === 426 ? "unsupported_contract" : "visual_error",
        request_id: "visual-mkt046-request",
      },
    }),
  );
});
</script>

<template>
  <main class="grid min-h-screen place-items-center" aria-busy="true">
    <span class="sr-only">Preparando cenário visual…</span>
  </main>
</template>
