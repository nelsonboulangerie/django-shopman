<!-- O título é o nome do passo ("Recebido", "Aceito"): conteúdo, não enfeite. Sem
     aria-hidden, como o Item; só o Indicator e o Separator são decorativos (#2609). -->
<template>
  <Primitive
    data-slot="timeline-title"
    v-bind="forwarded"
    :class="styles({ class: normalizeClass(props.class) || undefined })"
  >
    <slot />
  </Primitive>
</template>

<script lang="ts" setup>
  import { reactiveOmit } from "@vueuse/core";
  import { Primitive, useForwardProps } from "reka-ui";
  import type { PrimitiveProps } from "reka-ui";
  import { normalizeClass } from "vue";
  import type { HTMLAttributes } from "vue";

  const styles = tv({
    base: "text-sm font-medium",
  });
  const props = defineProps<
    PrimitiveProps & {
      class?: HTMLAttributes["class"];
    }
  >();

  const forwarded = useForwardProps(reactiveOmit(props, ["class"]));
</script>
