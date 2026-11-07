<script setup lang="ts">
import identities from '../../../operator-kit/app-identity.json';
const props=withDefaults(defineProps<{app?:string;rail?:boolean;collapsed?:boolean}>(),{app:'kds',rail:false,collapsed:false});
const table=identities.apps as Record<string,{label:string;fallbackIcon:string;color:string}>;
const identity=computed(()=>table[props.app]||table.kds);
const railControl=useSuiteRail();
const {attrsFor}=useOperatorAppLink();
const destination='/preview/central';
</script>
<template>
  <div class="flex min-w-0 items-center gap-2" :class="rail?'':railControl?.state.value==='hidden'?'':'lg:hidden'">
    <NuxtButton :to="destination" v-bind="attrsFor(destination)" square color="neutral" variant="ghost"
      class="shrink-0 size-11" :aria-label="identity.label + ': ir à Central'" title="Central e aplicativos" data-preview-app-link>
      <span class="grid size-8 place-items-center rounded-lg text-white" :style="{background:identity.color}">
        <NuxtIcon :name="'i-lucide-'+identity.fallbackIcon" class="size-5" />
      </span>
    </NuxtButton>
    <span v-if="rail&&!collapsed" class="font-semibold">{{identity.label}}</span>
  </div>
</template>
