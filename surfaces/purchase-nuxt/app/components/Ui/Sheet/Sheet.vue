<template>
  <DialogRoot data-slot="sheet" v-bind="forwarded">
    <slot />
  </DialogRoot>
</template>

<script lang="ts" setup>
  /**
   * A gaveta da casa — `reka-ui` por baixo, o mesmo componente que o app de
   * produção usa.
   *
   * A alternativa (um `fixed inset-0` escrito à mão) perde o que ninguém
   * lembra de escrever de novo: trava de foco, `Esc`, `aria-modal`, retorno do
   * foco para quem abriu, e o corpo da página que não rola por baixo.
   */
  import { DialogRoot, useForwardPropsEmits } from "reka-ui";
  import type { DialogRootEmits, DialogRootProps } from "reka-ui";

  const props = defineProps<DialogRootProps>();
  const emit = defineEmits<DialogRootEmits>();

  const forwarded = useForwardPropsEmits(props, emit);
</script>
