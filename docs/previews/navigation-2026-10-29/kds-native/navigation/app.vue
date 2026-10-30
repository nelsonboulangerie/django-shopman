<script setup lang="ts">
import identities from '../../../../../operator-kit/app-identity.json';
const route=useRoute();const table=identities.apps as Record<string,any>;
const key=computed(()=>String(route.params.app));const identity=computed(()=>table[key.value]);
const back=useState<string>('preview-kds-return',()=>'/bancada');
</script>
<template>
  <main class="min-h-dvh bg-background text-foreground">
    <header class="flex min-h-16 items-center gap-2 border-b border-default px-3"><KdsPreviewAppLink :app="key"/><h1 class="font-semibold">{{identity?.label||'Aplicativo'}}</h1><NuxtButton to="/preview/central" class="ms-auto" color="neutral" variant="ghost" icon="i-lucide-layout-grid" label="Central" /></header>
    <section class="mx-auto grid max-w-2xl gap-4 p-4 sm:p-6">
      <NuxtCard><h2 class="text-xl font-semibold">{{route.query.columns==='expedition'?'Saída':identity?.label}}</h2><p class="mt-2 text-muted">Destino da simulação de troca de aplicativos. A operação deste app não é reproduzida nesta tela.</p></NuxtCard>
      <NuxtButton :to="back" icon="i-lucide-chef-hat" label="Voltar à estação da Cozinha"/>
    </section>
  </main>
</template>
