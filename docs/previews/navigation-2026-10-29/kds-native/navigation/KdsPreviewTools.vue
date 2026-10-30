<script setup lang="ts">
const props=defineProps<{query:string;filter:string;filters:Array<any>;actions:Array<any>;shown:number;total:number}>();
const emit=defineEmits<{filter:[string];clear:[]}>();
const filtersOpen=ref(false);
const {request:search}=useSuiteSearchRequest();
const active=computed(()=>Boolean(props.query.trim()||props.filter!=='all'));
</script>
<template>
  <div class="min-w-0 w-full" data-preview-tools>
    <div class="flex w-full min-w-0 items-stretch overflow-hidden rounded-lg border border-default bg-default" role="group" aria-label="Filtrar, buscar e opções da estação">
      <NuxtButton icon="i-lucide-list-filter" square color="neutral" variant="ghost" class="size-11 shrink-0 rounded-none border-r border-default" :aria-label="filter==='all'?'Filtros da fila':'Filtros da fila: '+(filters.find(item=>item.key===filter)?.label||'Ativo')" :aria-expanded="filtersOpen" @click="filtersOpen=true" />
      <NuxtButton icon="i-lucide-search" color="neutral" variant="ghost" class="min-h-11 min-w-0 flex-1 justify-start rounded-none px-3" :aria-label="query?'Buscar. Busca ativa: '+query:'Buscar pedido por código, cliente ou item'" @click="search()"><span class="min-w-0 break-words whitespace-normal text-left">{{query||'Buscar pedido'}}</span></NuxtButton>
      <NuxtDropdownMenu :items="[actions]" :content="{align:'end'}" :ui="{content:'w-64 max-w-[calc(100vw-24px)]'}">
        <NuxtButton icon="i-lucide-ellipsis-vertical" square color="neutral" variant="ghost" class="size-11 shrink-0 rounded-none border-l border-default" aria-label="Opções da estação" />
      </NuxtDropdownMenu>
    </div>
    <div v-if="active" class="flex items-start gap-2 pt-1.5 text-sm" data-preview-active-query>
      <p class="min-w-0 flex-1 break-words"><span v-if="query">Busca: <strong>{{query}}</strong>. </span><span v-if="filter!=='all'">{{filters.find(i=>i.key===filter)?.label}}. </span>{{shown}} exibidos · {{total}} ativos na estação.</p>
      <NuxtButton color="neutral" variant="ghost" class="min-h-11 shrink-0" label="Limpar" aria-label="Limpar busca e filtros" @click="emit('clear')" />
    </div>
    <NuxtDrawer v-model:open="filtersOpen" title="Filtros da fila" description="Busca e filtros não escondem mudanças ou cancelamentos que pedem ciência.">
      <template #title><div class="flex w-full items-center gap-2"><span class="flex-1">Filtros da fila</span><NuxtButton icon="i-lucide-x" square aria-label="Fechar filtros" variant="ghost" color="neutral" class="size-11" @click="filtersOpen=false"/></div></template>
      <template #body><div class="flex flex-col gap-2"><NuxtButton v-for="item in filters" :key="item.key" :label="item.label+' · '+item.count" :icon="filter===item.key?'i-lucide-check':item.icon" color="neutral" :variant="filter===item.key?'soft':'ghost'" class="min-h-11 justify-start" @click="emit('filter',item.key)" /></div></template>
      <template #footer><div class="flex gap-2"><NuxtButton label="Limpar" color="neutral" variant="ghost" class="min-h-11" @click="emit('clear')"/><NuxtButton label="Ver fila" class="min-h-11 flex-1 justify-center" @click="filtersOpen=false"/></div></template>
    </NuxtDrawer>
  </div>
</template>
