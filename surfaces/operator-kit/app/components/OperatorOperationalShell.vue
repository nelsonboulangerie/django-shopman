<template>
  <NuxtMain class="min-h-dvh min-w-0 bg-default" data-operator-operational-shell>
    <slot name="navigation" />
    <div class="min-w-0 flex-1">
      <slot name="header" />
      <slot />
      <slot name="actions" />
    </div>
  </NuxtMain>
</template>
