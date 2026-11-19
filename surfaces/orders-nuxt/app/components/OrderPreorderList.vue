<script setup lang="ts">
// Encomendas no Gestor (dono, 13/11/2026; o vocabulário fechado diz Encomenda, não
// Agendado): os pedidos dos próximos dias, abaixo do painel. Não entra no fluxo do dia;
// está ali para conferir o que vem pela frente. A encomenda de HOJE também mora aqui
// enquanto espera a hora da Cozinha (dono, 18/11/2026; WP-G02): a linha diz "Vai para a
// Cozinha às 17h15", e só nessa hora o pedido entra no quadro, pedindo "Iniciar preparo".
//
// Cada linha responde, sem abrir o pedido (WP-G03): quando, retirada ou entrega, se
// está paga e se a produção cobre. A linha abre o pedido; "Remarcar no PDV" abre AQUELA
// encomenda no PDV, onde mora o remarcar (D-003). O cabeçalho leva à lista do PDV.
//
// A encomenda que perdeu o lastro (WP-G08) diz "Promessa em risco", o item sem
// reserva e o que fazer agora, e a linha abre o pedido já na faixa das saídas.
import type { PreorderGroup } from "~/presentation/board";
import {
  preorderFocusKey,
  preorderGroupLabel,
  preorderLine,
  preorderRescheduleHref,
} from "~/presentation/preorderList";
import { useOperatorAppLink } from "../../../operator-kit/app/composables/useOperatorAppLink";

const props = defineProps<{
  groups: PreorderGroup[];
  count: number;
  /** A encomenda recém-aceita, para quem veio do aviso achar a linha de relance. */
  highlightRef?: string;
}>();

const config = useRuntimeConfig();
const posUrl = computed(() => String(config.public.posUrl || ""));
const preordersHref = computed(() => {
  const base = posUrl.value.replace(/\/$/, "");
  return base ? `${base}/preorders` : "";
});
const { attrsFor } = useOperatorAppLink();
const link = computed(() => attrsFor(preordersHref.value));
const total = computed(() => props.count);
const rows = computed(() =>
  props.groups.map((group) => ({
    date: group.date,
    label: preorderGroupLabel(group.label),
    lines: group.cards.map((card) => {
      const href = preorderRescheduleHref(posUrl.value, card.ref);
      return { ...preorderLine(card), href, link: attrsFor(href) };
    }),
  })),
);
</script>

<template>
  <section class="mt-6" data-preorders-section>
    <div class="flex items-center gap-2 border-b border-default pb-2">
      <h2 class="font-semibold text-highlighted">Encomendas</h2>
      <OperatorCountChip :count="total" />
      <NuxtButton
        v-if="preordersHref"
        class="ms-auto"
        :to="preordersHref"
        :target="link.target"
        :rel="link.rel"
        external
        color="neutral"
        variant="ghost"
        trailing-icon="i-lucide-arrow-up-right"
        label="Abrir Encomendas"
        data-preorders-open
      />
    </div>
    <div v-for="group in rows" :key="group.date" class="mt-3">
      <h3 class="op-micro font-semibold text-muted-foreground">
        {{ group.label }}
      </h3>
      <ul class="mt-1 divide-y divide-default">
        <li
          v-for="line in group.lines"
          :key="line.ref"
          class="flex flex-wrap items-center gap-x-3 gap-y-1 py-2"
          :class="line.ref === highlightRef ? 'bg-elevated' : ''"
          :data-preorder-row="line.ref"
          :data-preorder-at-risk="line.risk ? '' : undefined"
          :data-focus-target="preorderFocusKey(line.ref)"
          :aria-current="line.ref === highlightRef || undefined"
        >
          <NuxtLink
            :to="line.to"
            class="flex min-h-11 min-w-0 flex-1 basis-64 flex-col justify-center gap-0.5 hover:bg-elevated/50"
            :aria-label="`Abrir pedido ${line.ref}`"
            data-focus-control
          >
            <!-- Primeira linha: quem e quando. Quebra, nunca corta: o dia e a janela
                 são o motivo da lista. -->
            <span class="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
              <span class="font-semibold tabular-nums text-highlighted">{{ line.code }}</span>
              <span class="min-w-0 truncate">{{ line.who }}</span>
              <span v-if="line.when" class="font-medium text-highlighted" data-preorder-when>{{ line.when }}</span>
              <!-- A de hoje que espera a hora da Cozinha: a mesma frase do cartão. -->
              <NuxtBadge
                v-if="line.kitchenWait"
                color="neutral"
                :icon="line.kitchenWait.icon"
                :label="line.kitchenWait.label"
                data-preorder-kitchen-wait
              />
              <!-- A promessa em risco: o nome do estado, em vermelho, ao lado do dia. -->
              <NuxtBadge
                v-if="line.risk"
                color="error"
                icon="i-lucide-package-x"
                :label="line.risk.label"
                data-preorder-risk
              />
              <span class="ms-auto shrink-0 tabular-nums">{{ line.total }}</span>
            </span>
            <!-- Segunda linha: como recebe, o pagamento, a produção e os itens. -->
            <span class="flex flex-wrap gap-x-3 gap-y-0.5 op-micro text-muted">
              <span data-preorder-how>{{ line.how }}</span>
              <span
                v-if="line.payment"
                :class="line.awaitingPayment ? 'font-semibold text-highlighted' : ''"
                data-preorder-payment
                >{{ line.payment }}</span
              >
              <span
                v-if="line.risk?.items"
                class="font-semibold text-error"
                data-preorder-risk-items
                >{{ line.risk.items }}</span
              >
              <!-- O próximo passo, escrito: a linha abre o pedido, onde estão os gestos. -->
              <span
                v-if="line.risk?.nextStep"
                class="font-medium text-highlighted"
                data-preorder-risk-next-step
                >{{ line.risk.nextStep }}</span
              >
              <span v-if="line.production" data-preorder-production>{{ line.production }}</span>
              <span
                v-if="line.needsYou"
                class="font-semibold text-primary"
                data-preorder-needs-you
                >Precisa de você</span
              >
              <span class="min-w-0" data-preorder-items>{{ line.items }}</span>
            </span>
          </NuxtLink>
          <!-- No celular o botão vai para a direita e perde a seta: a dica "tem mais
               abaixo" flutua no centro da base, e os dois não podem se encontrar
               (auditoria da prévia, 18/11/2026). O nome do gesto é o mesmo. -->
          <NuxtButton
            v-if="line.href"
            class="ms-auto shrink-0 sm:hidden"
            :to="line.href"
            :target="line.link.target"
            :rel="line.link.rel"
            external
            color="neutral"
            variant="outline"
            label="Remarcar no PDV"
            :aria-label="`Remarcar a encomenda ${line.code} no PDV`"
            data-preorder-reschedule="narrow"
          />
          <NuxtButton
            v-if="line.href"
            class="hidden shrink-0 sm:inline-flex"
            :to="line.href"
            :target="line.link.target"
            :rel="line.link.rel"
            external
            color="neutral"
            variant="outline"
            trailing-icon="i-lucide-arrow-up-right"
            label="Remarcar no PDV"
            :aria-label="`Remarcar a encomenda ${line.code} no PDV`"
            data-preorder-reschedule
          />
        </li>
      </ul>
    </div>
  </section>
</template>
