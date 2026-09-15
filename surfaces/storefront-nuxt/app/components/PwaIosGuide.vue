<script setup lang="ts">
import type { PwaCopyProjection } from '~/types/shopman'

const props = defineProps<{
  copy: PwaCopyProjection
  step: 0 | 1
}>()

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
      <p class="shop-kicker text-primary">
        Passo {{ step + 1 }} de {{ steps.length }}
      </p>
      <div
        class="flex flex-1 gap-2"
        role="progressbar"
        aria-label="Etapas da instalação"
        :aria-valuenow="step + 1"
        aria-valuemin="1"
        :aria-valuemax="steps.length"
      >
        <span
          v-for="(_, index) in steps"
          :key="index"
          class="h-2 flex-1 rounded-full transition-colors"
          :class="index <= step ? 'bg-primary' : 'bg-primary/15'"
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
          :id="`ios-install-step-${index + 1}`"
          :key="item.image"
          class="min-w-full"
          role="tabpanel"
          :aria-hidden="step !== index"
          :inert="step !== index"
          :data-testid="`ios-step-${index + 1}`"
        >
          <div class="rounded-lg border border-primary/15 bg-[#fcf7ee] px-4 py-3 shadow-sm">
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
