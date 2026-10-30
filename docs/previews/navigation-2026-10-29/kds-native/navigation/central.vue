<script setup lang="ts">
import identities from '../../../../operator-kit/app-identity.json';
const apps=Object.entries(identities.apps).filter(([key])=>key!=='hub');
const back=useState<string>('preview-kds-return',()=>'/bancada');
function destination(key:string){return key==='kds'?back.value:'/preview/apps/'+key;}
</script>
<template>
  <main class="min-h-dvh bg-background text-foreground">
    <header class="flex min-h-16 items-center gap-2 border-b border-default px-3"><KdsPreviewAppLink app="hub"/><h1 class="font-semibold">Central</h1><NuxtButton :to="back" class="ms-auto" color="neutral" variant="outline" icon="i-lucide-chef-hat" label="Voltar à Cozinha" /></header>
    <section class="mx-auto max-w-4xl p-4 sm:p-6"><h2 class="text-xl font-semibold">Aplicativos</h2><p class="mt-1 text-sm text-muted">Escolha onde continuar o trabalho.</p>
      <div class="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <NuxtLink v-for="[key,app] in apps" :key="key" :to="destination(key)" class="flex min-h-32 flex-col items-start justify-center gap-3 rounded-xl border border-default bg-default p-4 hover:bg-elevated">
          <span class="grid size-10 place-items-center rounded-lg text-white" :style="{background:app.color}"><NuxtIcon :name="'i-lucide-'+app.fallbackIcon" class="size-6"/></span><span class="font-semibold">{{app.label}}</span>
        </NuxtLink>
      </div>
    </section>
  </main>
</template>
