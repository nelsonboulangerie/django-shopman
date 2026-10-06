<script setup lang="ts">
import { computed, toValue } from "vue";

// Header canônico do Gestor: consome o model provido pelo index.vue (dono do estado e
// dos efeitos) e delega a anatomia ao primitivo de kit OperatorCanonicalHeader.
// Os conteúdos ricos (busca/ações/recortes) continuam na página, via slots.
const header = useGestorBoardHeader();
const eyebrow = computed(() => toValue(header.eyebrow));
</script>

<template>
  <OperatorCanonicalHeader :title="header.title" :eyebrow="eyebrow">
    <template v-if="$slots.status" #status><slot name="status" /></template>
    <template v-if="$slots.search" #search><slot name="search" /></template>
    <template v-if="$slots.actions" #actions><slot name="actions" /></template>
    <template v-if="$slots.filters" #filters><slot name="filters" /></template>
    <template v-if="$slots.below" #below><slot name="below" /></template>
  </OperatorCanonicalHeader>
</template>
