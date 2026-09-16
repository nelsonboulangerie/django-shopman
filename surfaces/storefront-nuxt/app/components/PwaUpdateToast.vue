<script setup lang="ts">
import type { PwaCopyProjection } from '~/types/shopman'
import { toast } from 'vue-sonner'

const props = defineProps<{ copy?: PwaCopyProjection }>()
const { needRefresh, update } = usePwaUpdate()
let shown = false

watch(needRefresh, (value) => {
  if (!value || shown) return
  shown = true
  toast(props.copy?.update_title.title || 'Nova versão disponível', {
    duration: Infinity,
    action: {
      label: props.copy?.update_cta.title || 'Atualizar',
      onClick: () => { void update() }
    }
  })
})
</script>

<template>
  <span v-if="false" />
</template>
