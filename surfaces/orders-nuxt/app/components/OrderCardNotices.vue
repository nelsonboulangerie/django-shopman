<script setup lang="ts">
// Os avisos do cartão do pedido (dono, 07/10/2026): a pílula com a cor e o nome; o
// texto e o gesto no Popover. Um lugar só para o cartão inteiro e o enxuto do Painel.
//
// O aviso com mais de um fato (a promessa em risco, WP-G08: um item por linha, com o
// porquê) escreve as linhas no lugar da descrição, com as sugestões de cada item em
// lista (`OrderPromiseSuggestions`), depois a frase do servidor quando há, e as saídas
// dele (`OrderPromiseExits`, na cor do aviso): "Resolver" chama o `onResolve` do aviso,
// que sobe até a página, e "Abrir a Produção" é atalho.
import type { CardNotice } from "./OrderCard.vue";
import OrderPromiseExits from "./OrderPromiseExits.vue";
import OrderPromiseSuggestions from "./OrderPromiseSuggestions.vue";
import { alertActions } from "../../../operator-kit/app/utils/alertActions";

defineProps<{ notices: CardNotice[] }>();
</script>

<template>
  <div v-if="notices.length" class="flex flex-wrap gap-1.5" data-card-notices>
    <NuxtPopover
      v-for="notice in notices"
      :key="notice.key"
      :content="{ side: 'bottom', align: 'start' }"
    >
      <NuxtButton
        :color="notice.color"
        variant="soft"
        :icon="notice.icon"
        :label="notice.label"
        :data-card-notice="notice.key"
      />
      <template #content>
        <NuxtAlert
          class="max-w-80"
          :color="notice.color"
          variant="subtle"
          :icon="notice.icon"
          :title="notice.title"
          :description="notice.description"
          :actions="alertActions(notice.color, notice.actions ?? [])"
          v-bind="notice.attrs"
        >
          <template
            v-if="notice.lines?.length || notice.notes?.length || notice.nextStep"
            #description
          >
            <div class="flex flex-col gap-2">
              <ul v-if="notice.lines?.length" class="flex flex-col gap-1.5">
                <li
                  v-for="line in notice.lines"
                  :key="line.key"
                  class="flex flex-col"
                  data-card-notice-line
                >
                  <span class="font-medium">{{ line.label }}</span>
                  <span v-if="line.detail">{{ line.detail }}</span>
                  <OrderPromiseSuggestions
                    v-if="line.suggestions?.length"
                    class="mt-1.5"
                    :options="line.suggestions"
                  />
                </li>
              </ul>
              <!-- O que fazer agora, com as palavras do servidor. -->
              <p
                v-if="notice.nextStep"
                class="font-medium"
                data-card-notice-next-step
              >
                {{ notice.nextStep }}
              </p>
              <!-- Por que uma saída não pode agora, escrito. -->
              <p
                v-for="note in notice.notes"
                :key="note"
                class="text-xs"
                data-card-notice-note
              >
                {{ note }}
              </p>
            </div>
          </template>
          <template v-if="notice.exits?.length" #actions>
            <OrderPromiseExits
              :exits="notice.exits"
              :code="notice.code ?? ''"
              tone="alert"
              @resolve="notice.onResolve?.()"
            />
          </template>
        </NuxtAlert>
      </template>
    </NuxtPopover>
  </div>
</template>
