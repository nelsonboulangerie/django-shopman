<script setup lang="ts">
await navigateTo(
  { path: "/v2", query: { area: "today" } },
  { redirectCode: 301, replace: true },
);
</script>

<template>
  <div />
</template>
