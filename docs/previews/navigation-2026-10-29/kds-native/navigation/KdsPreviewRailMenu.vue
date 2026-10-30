<script setup lang="ts">
const rail=useSuiteRail();
async function choose(state:string){for(let n=0;rail&&rail.state.value!==state&&n<3;n++)await rail.cycle();}
const items=computed(()=>[[{label:'Barra lateral',type:'label'},...[
  {state:'open',label:'Expandida',icon:'i-lucide-panel-left-open'},
  {state:'compact',label:'Compacta',icon:'i-lucide-panel-left'},
  {state:'hidden',label:'Oculta',icon:'i-lucide-panel-left-close'},
].map(i=>({label:i.label,icon:rail?.state.value===i.state?'i-lucide-check':i.icon,onSelect:()=>choose(i.state)}))]]);
</script>
<template><NuxtDropdownMenu v-if="rail" :items="items"><NuxtButton color="neutral" variant="ghost" square icon="i-lucide-panel-left" class="hidden lg:inline-flex" aria-label="Ajustar barra lateral" title="Barra lateral: expandida, compacta ou oculta" data-preview-rail-menu /></NuxtDropdownMenu></template>
