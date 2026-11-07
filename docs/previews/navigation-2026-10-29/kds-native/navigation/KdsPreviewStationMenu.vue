<script setup lang="ts">
const props=withDefaults(defineProps<{title:string;actions?:Array<any>}>(),{actions:()=>[]});
const route=useRoute();
const {data:index}=useNuxtData<any>('kds-index');
const settingsOpen=useKdsSettingsOpen();
const items=computed(()=>[
  [{label:'Trocar de estação',type:'label'},...(index.value?.instances||[]).filter((i:any)=>i.type!=='expedition').map((i:any)=>({
    label:i.name,to:'/'+i.ref,icon:route.params.ref===i.ref?'i-lucide-check':i.type==='picking'?'i-lucide-layers':'i-lucide-flame',count:i.active_count,
    'aria-label':i.name+(route.params.ref===i.ref?' (estação atual)':'')
  }))],
  [{label:'Todas as estações',to:'/',icon:'i-lucide-layout-grid'}],
  ...(props.actions.length ? [[...props.actions.filter(a=>!a.label.startsWith('Ajustes da estação')).map(a=>({...a})),
    {label:'Som e tamanho do ticket',icon:'i-lucide-settings-2',onSelect:()=>{settingsOpen.value=true;}}]] : [])
]);
</script>
<template>
  <NuxtDropdownMenu :items="items" :content="{align:'start'}" :ui="{content:'w-72 max-w-[calc(100vw-24px)] max-h-[75dvh] overflow-y-auto'}">
    <NuxtButton :label="title" trailing-icon="i-lucide-chevron-down" color="neutral" variant="ghost"
      class="min-w-0 max-w-full font-semibold" :aria-label="'Trocar estação. Atual: '+title" data-preview-station-menu />
    <template #item-trailing="{item}"><OperatorCountChip v-if="item.count" :count="item.count" /></template>
  </NuxtDropdownMenu>
</template>
