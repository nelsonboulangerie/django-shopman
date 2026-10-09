<script setup lang="ts">
import { useMediaQuery } from "@vueuse/core";
// Ficha do cliente — quem é, o que comprou, e quem PODE ser a mesma pessoa.
//
// Os candidatos vêm com o motivo escrito ("Mesmo cliente no iFood", "Mesmo CPF",
// "Mesmo nome"): é sugestão, e a unificação é sempre um gesto do gestor, depois da
// prévia lado a lado (`CustomerMergeDialog`).
import type { CustomerCandidateProjection } from "~/generated/ordersContract";

const route = useRoute();
const router = useRouter();
const customerRef = computed(() => String(route.params.ref || ""));
const { customer, pending, error, refresh, readMetadata } =
  useCustomerDetail(customerRef);

useHead({ title: computed(() => customer.value?.name || "Cliente") });

const mergeOpen = ref(false);
const mergeWith = ref<CustomerCandidateProjection | null>(null);
function compare(candidate: CustomerCandidateProjection | null) {
  mergeWith.value = candidate;
  mergeOpen.value = true;
}

async function onMerged({
  targetRef,
  sourceRef,
}: {
  targetRef: string;
  sourceRef: string;
}) {
  useSonner.success(
    `${sourceRef} foi unificado a ${targetRef}. Dá para desfazer em Unificações por 24 horas.`,
  );
  if (targetRef !== customerRef.value)
    await router.push(`/customers/${encodeURIComponent(targetRef)}`);
  else await refresh();
}

const canMerge = computed(() =>
  Boolean(
    customer.value?.is_active &&
    customer.value.actions.some((action) => action.ref === "merge_preview"),
  ),
);
// Editar o cadastro (nome, contato, observações) continua no Admin.
const adminBaseUrl = useRuntimeConfig().public.adminBaseUrl as string;
const adminUrl = computed(() =>
  adminBaseUrl
    ? `${adminBaseUrl}/admin/guestman/customer/?q=${encodeURIComponent(customerRef.value)}`
    : "",
);
const notFound = computed(() => httpError(error.value).status === 404);
// Celular (abaixo de `sm`, README do kit "Barra do topo no celular" e "Toolbar no
// celular"): as ações da toolbar vão para o ⋯ da barra do topo e a leitura (frescor)
// desce para a faixa de texto abaixo da linha. Do `sm` para cima, tudo como está.
const isNarrow = useMediaQuery("(max-width: 639.98px)");
const phoneHeaderActions = computed(() =>
  isNarrow.value
    ? [
        ...(adminUrl.value && customer.value
          ? [{ label: "Editar no Admin", icon: "i-lucide-pencil", to: adminUrl.value, target: "_blank" }]
          : []),
        { label: "Atualizar", icon: "i-lucide-refresh-cw", onSelect: () => void refresh() },
      ]
    : undefined,
);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader
      :title="customer?.name || 'Cliente'"
      :filters-wrap="false"
      :actions="phoneHeaderActions"
    >
      <template #lead>
        <NuxtButton
          to="/customers"
          icon="i-lucide-chevron-left"
          color="neutral"
          variant="ghost"
          square
          aria-label="Voltar para Clientes"
          @click.prevent="router.back()"
        />
      </template>
      <template v-if="!isNarrow" #filters>
        <NuxtButton
          v-if="adminUrl && customer"
          :to="adminUrl"
          target="_blank"
          icon="i-lucide-pencil"
          trailing-icon="i-lucide-external-link"
          label="Editar no Admin"
          color="neutral"
          variant="outline"
          title="Editar este cadastro (abre o Admin)"
        />
        <NuxtButton
          icon="i-lucide-refresh-cw"
          label="Atualizar"
          color="neutral"
          variant="outline"
          :loading="pending"
          @click="refresh()"
        />
      </template>
      <template #filters-end>
        <ReadFreshness
          inline
          :metadata="readMetadata"
          :failed="Boolean(error)"
        />
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 space-y-4 overflow-auto p-4 sm:p-6">
      <NuxtEmpty
        v-if="notFound"
        icon="i-lucide-user-x"
        title="Este cadastro não existe"
        :actions="[{ label: 'Voltar para Clientes', to: '/customers' }]"
      />
      <NuxtAlert
        v-else-if="error"
        color="error"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        title="Não foi possível carregar a ficha"
        :description="
          httpErrorMessage(error, 'Não foi possível carregar a ficha.')
        "
        :actions="[
          {
            label: 'Tentar de novo',
            color: 'error',
            variant: 'outline',
            onClick: () => refresh(),
          },
        ]"
      />

      <div v-if="pending && !customer" class="space-y-3">
        <NuxtSkeleton
          v-for="i in 3"
          :key="i"
          class="h-24 w-full"
          aria-label="Carregando cliente"
        />
      </div>

      <div
        v-else-if="customer"
        class="mx-auto grid max-w-5xl gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"
      >
        <!-- Absorvido: a ficha diz para onde foi, e não oferece nada além disso. -->
        <NuxtAlert
          v-if="!customer.is_active"
          color="warning"
          variant="subtle"
          icon="i-lucide-merge"
          title="Cadastro unificado ou desativado"
          :description="
            customer.merged_into_ref
              ? `Este cadastro foi unificado a ${customer.merged_into_ref}. Os pedidos e contatos dele estão lá.`
              : 'Este cadastro está desativado.'
          "
          :actions="
            customer.merged_into_ref
              ? [
                  {
                    label: `Abrir ${customer.merged_into_ref}`,
                    color: 'warning',
                    variant: 'outline',
                    to: `/customers/${encodeURIComponent(customer.merged_into_ref)}`,
                  },
                ]
              : []
          "
          data-customer-absorbed
        />

        <NuxtCard as="article" class="lg:col-span-2" data-customer-header>
          <template #header>
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <h2 class="text-xl font-semibold">{{ customer.name }}</h2>
                <p
                  class="flex flex-wrap items-center gap-2 text-xs text-muted-foreground"
                >
                  <span class="font-mono">{{ customer.ref }}</span>
                  <NuxtBadge
                    v-if="customer.source_label"
                    color="neutral"
                    :label="customer.source_label"
                  />
                  <span v-if="customer.created_display"
                    >Cadastrado em {{ customer.created_display }}</span
                  >
                </p>
              </div>
              <NuxtButton
                v-if="canMerge"
                type="button"
                icon="i-lucide-merge"
                label="Unificar com outro cadastro…"
                data-customer-merge-any
                @click="compare(null)"
              />
            </div>
          </template>
          <div class="space-y-3">
            <dl class="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
              <div class="flex gap-2">
                <dt class="text-muted-foreground">Telefone</dt>
                <dd>{{ customer.phone_display || "Sem telefone" }}</dd>
              </div>
              <div class="flex gap-2">
                <dt class="text-muted-foreground">E-mail</dt>
                <dd>{{ customer.email || "Sem e-mail" }}</dd>
              </div>
              <div class="flex gap-2">
                <dt class="text-muted-foreground">CPF</dt>
                <dd>{{ customer.document_display || "Sem CPF" }}</dd>
              </div>
              <div v-if="customer.birthday_display" class="flex gap-2">
                <dt class="text-muted-foreground">Aniversário</dt>
                <dd>{{ customer.birthday_display }}</dd>
              </div>
            </dl>
            <NuxtAlert
              v-if="customer.notes"
              color="info"
              variant="subtle"
              title="Observação"
              :description="customer.notes"
            />
          </div>
        </NuxtCard>

        <!-- Quem pode ser a mesma pessoa -->
        <NuxtCard
          v-if="customer.candidates.length"
          as="article"
          class="lg:col-span-2"
          data-customer-candidates
        >
          <template #header>
            <div>
              <h2 class="op-title">Pode ser a mesma pessoa</h2>
              <p class="op-micro text-muted-foreground">
                Sugestão da tela, com o motivo em cada linha. Confira antes de
                unificar.
              </p>
            </div>
          </template>
          <ul class="divide-y divide-border">
            <li
              v-for="candidate in customer.candidates"
              :key="candidate.ref"
              class="flex flex-wrap items-center justify-between gap-3 py-2"
            >
              <div class="min-w-0 text-sm">
                <NuxtLink
                  :to="`/customers/${encodeURIComponent(candidate.ref)}`"
                  class="font-medium hover:underline"
                  >{{ candidate.name }}</NuxtLink
                >
                <span class="ms-2 font-mono text-xs text-muted-foreground">{{
                  candidate.ref
                }}</span>
                <p class="text-xs text-muted-foreground">
                  <NuxtBadge
                    color="warning"
                    :label="candidate.reason_label"
                  />
                  · {{ candidate.phone_display || "sem telefone" }}
                  <template v-if="candidate.source_label">
                    · {{ candidate.source_label }}</template
                  >
                  · {{ candidate.orders_label }}
                </p>
              </div>
              <NuxtButton
                type="button"
                label="Comparar"
                :data-customer-compare="candidate.ref"
                @click="compare(candidate)"
              />
            </li>
          </ul>
        </NuxtCard>

        <NuxtCard as="article">
          <template #header>
            <div>
              <h2 class="op-title">Pedidos</h2>
              <p class="op-micro text-muted-foreground">
                {{ customer.orders_label
                }}<template v-if="customer.total_spent_display">
                  · {{ customer.total_spent_display }} no total</template
                >
                <template v-if="customer.last_order_display">
                  · último {{ customer.last_order_display }}</template
                >
              </p>
            </div>
          </template>
          <ul
            v-if="customer.recent_orders.length"
            class="divide-y divide-border text-sm"
          >
            <li v-for="order in customer.recent_orders" :key="order.ref">
              <NuxtLink
                :to="`/${encodeURIComponent(order.ref)}`"
                class="flex flex-wrap items-center justify-between gap-2 py-1.5 hover:underline"
              >
                <span
                  ><span class="font-mono text-xs">{{ order.ref }}</span> ·
                  {{ order.channel_label }}</span
                >
                <span class="text-xs text-muted-foreground"
                  >{{ order.ordered_at_display }} · {{ order.status_label }} ·
                  {{ order.total_display }}</span
                >
              </NuxtLink>
            </li>
          </ul>
        </NuxtCard>

        <NuxtCard as="article">
          <template #header>
            <div>
              <h2 class="op-title">Identificadores</h2>
              <p class="op-micro text-muted-foreground">
                As chaves pelas quais os canais reconhecem esta pessoa.
              </p>
            </div>
          </template>
          <ul v-if="customer.identifiers.length" class="space-y-1 text-sm">
            <li
              v-for="identifier in customer.identifiers"
              :key="`${identifier.type_label}:${identifier.value}`"
              class="flex gap-2"
            >
              <span class="text-muted-foreground">{{
                identifier.type_label
              }}</span>
              <span class="break-all font-mono text-xs leading-5">{{
                identifier.value
              }}</span>
            </li>
          </ul>
          <p v-else class="text-sm text-muted-foreground">
            Nenhum identificador.
          </p>
          <template #footer>
            <h2 class="op-title">Endereços</h2>
            <ul v-if="customer.addresses.length" class="mt-1 space-y-1 text-sm">
              <li v-for="address in customer.addresses" :key="address">
                {{ address }}
              </li>
            </ul>
            <p v-else class="mt-1 text-sm text-muted-foreground">
              Nenhum endereço salvo.
            </p>
          </template>
        </NuxtCard>
      </div>
    </section>

    <CustomerMergeDialog
      v-if="customer"
      v-model:open="mergeOpen"
      :current="customer"
      :initial-other="mergeWith"
      @merged="onMerged"
    />
  </main>
</template>
