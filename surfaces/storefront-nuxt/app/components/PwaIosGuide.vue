<script setup lang="ts">
import type { PwaCopyProjection } from '~/types/shopman'

const props = defineProps<{
  copy: PwaCopyProjection
  step: 0 | 1
}>()

const emit = defineEmits<{ 'update:step': [step: 0 | 1] }>()

const steps = computed(() => [
  {
    image: '/pwa/ios-share-step.svg',
    message: props.copy.ios_share_step.message
  },
  {
    image: '/pwa/ios-add-step.svg',
    message: props.copy.ios_add_step.message
  }
])
</script>

<template>
  <div class="px-4 pt-4 pb-2">
    <div class="mb-4 flex items-center justify-between gap-4">
      <p class="text-xs font-bold tracking-[0.12em] text-primary uppercase">
        Passo {{ step + 1 }} de {{ steps.length }}
      </p>
      <div class="flex flex-1 gap-2" role="tablist" aria-label="Etapas da instalação">
        <button
          v-for="(_, index) in steps"
          :key="index"
          type="button"
          role="tab"
          :aria-selected="step === index"
          :aria-label="`Ir para o passo ${index + 1}`"
          :aria-controls="`ios-install-step-${index + 1}`"
          class="h-2 flex-1 rounded-full transition-colors"
          :class="index <= step ? 'bg-primary' : 'bg-primary/15'"
          @click="emit('update:step', index as 0 | 1)"
        />
      </div>
    </div>

    <div class="overflow-hidden">
      <div
        class="flex w-full transition-transform duration-300 ease-out motion-reduce:transition-none"
        :style="{ transform: `translateX(-${step * 100}%)` }"
        aria-live="polite"
      >
        <section
          v-for="(item, index) in steps"
          :key="item.image"
          :id="`ios-install-step-${index + 1}`"
          class="min-w-full"
          role="tabpanel"
          :aria-hidden="step !== index"
          :inert="step !== index"
          :data-testid="`ios-step-${index + 1}`"
        >
          <div class="rounded-2xl border border-primary/15 bg-[#fcf7ee] px-4 py-3 shadow-sm">
            <img
              :src="item.image"
              alt=""
              class="mx-auto h-[min(31dvh,240px)] min-h-44 w-full object-contain"
              width="320"
              height="240"
            >
          </div>
          <p class="mx-auto mt-4 max-w-sm text-center text-base leading-snug font-semibold text-foreground">
            {{ item.message }}
          </p>
        </section>
      </div>
    </div>
  </div>
</template>
