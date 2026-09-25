<script setup lang="ts">
// Ficha do cliente — quem é, o que comprou, e quem PODE ser a mesma pessoa.
//
// Os candidatos vêm com o motivo escrito ("Mesmo cliente no iFood", "Mesmo CPF",
// "Mesmo nome"): é sugestão, e a unificação é sempre um gesto do gestor, depois da
// prévia lado a lado (`CustomerMergeDialog`).
import type { CustomerCandidateProjection } from "~/generated/ordersContract";

const route = useRoute();
const router = useRouter();
const customerRef = computed(() => String(route.params.ref || ""));
const { customer, pending, error, refresh, readMetadata } = useCustomerDetail(customerRef);

useHead({ title: computed(() => customer.value?.name || "Cliente") });

const mergeOpen = ref(false);
const mergeWith = ref<CustomerCandidateProjection | null>(null);
function compare(candidate: CustomerCandidateProjection | null) {
  mergeWith.value = candidate;
  mergeOpen.value = true;
}

async function onMerged({ targetRef, sourceRef }: { targetRef: string; sourceRef: string }) {
  useSonner.success(`${sourceRef} foi unificado a ${targetRef}. Dá para desfazer em Unificações por 24 horas.`);
  if (targetRef !== customerRef.value) await router.push(`/customers/${encodeURIComponent(targetRef)}`);
  else await refresh();
}

const canMerge = computed(() => Boolean(customer.value?.is_active && customer.value.actions.some((action) => action.ref === "merge_preview")));
// Editar o cadastro (nome, contato, observações) continua no Admin.
const adminBaseUrl = useRuntimeConfig().public.adminBaseUrl as string;
const adminUrl = computed(() => (adminBaseUrl ? `${adminBaseUrl}/admin/guestman/customer/?q=${encodeURIComponent(customerRef.value)}` : ""));
const notFound = computed(() => httpError(error.value).status === 404);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <UiToolbar>
      <div class="flex min-w-0 items-center gap-2">
        <NuxtLink
          to="/customers"
          class="inline-flex min-h-control items-center gap-1 rounded-md px-2 text-sm text-muted-foreground transition hover:bg-accent hover:text-foreground"
          @click.prevent="router.back()"
        >
          <Icon name="lucide:chevron-left" class="size-4" />
          Clientes
        </NuxtLink>
        <h1 v-if="customer" class="truncate text-sm font-semibold">{{ customer.name }}</h1>
      </div>
      <template #end>
        <a
          v-if="adminUrl && customer"
          :href="adminUrl"
          target="_blank"
          rel="noopener"
          class="inline-flex min-h-control items-center gap-1.5 rounded-md border px-3 text-sm font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground"
          title="Editar este cadastro (abre o Admin)"
        >
          <Icon name="lucide:pencil" class="size-4" />
          <span class="hidden sm:inline">Editar no Admin</span>
          <Icon name="lucide:external-link" class="size-3.5 opacity-60" />
        </a>
        <UiIconButton icon="lucide:refresh-cw" label="Atualizar" :spinning="pending" @click="refresh()" />
      </template>
    </UiToolbar>
    <ReadFreshness :metadata="readMetadata" :failed="Boolean(error)" />

    <section class="min-h-0 flex-1 overflow-auto p-4">
      <div v-if="notFound" class="rounded-lg border border-dashed p-6 text-center text-sm">
        Este cadastro não existe.
        <NuxtLink to="/customers" class="ml-1 underline">Voltar para Clientes</NuxtLink>
      </div>
      <div v-else-if="error" role="alert" class="mb-3 rounded-md border border-destructive p-3 text-sm">
        {{ httpErrorMessage(error, "Não foi possível carregar a ficha.") }}
        <button type="button" class="ml-2 min-h-11 underline" @click="refresh()">Tentar de novo</button>
      </div>

      <div v-if="pending && !customer" class="space-y-3">
        <div v-for="i in 3" :key="i" class="h-28 animate-pulse rounded-lg border bg-muted/40"></div>
      </div>

      <div v-else-if="customer" class="mx-auto grid max-w-5xl gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <!-- Absorvido: a ficha diz para onde foi, e não oferece nada além disso. -->
        <div
          v-if="!customer.is_active"
          class="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-100 lg:col-span-2"
          data-customer-absorbed
        >
          <template v-if="customer.merged_into_ref">
            Este cadastro foi unificado a
            <NuxtLink :to="`/customers/${encodeURIComponent(customer.merged_into_ref)}`" class="font-medium underline">{{ customer.merged_into_ref }}</NuxtLink>.
            Os pedidos e contatos dele estão lá.
          </template>
          <template v-else>Este cadastro está desativado.</template>
        </div>

        <article class="rounded-lg border bg-card p-4 lg:col-span-2" data-customer-header>
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="text-lg font-semibold">{{ customer.name }}</p>
              <p class="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span class="font-mono">{{ customer.ref }}</span>
                <span v-if="customer.source_label" class="rounded bg-muted px-1.5 py-0.5">{{ customer.source_label }}</span>
                <span v-if="customer.created_display">Cadastrado em {{ customer.created_display }}</span>
              </p>
            </div>
            <button
              v-if="canMerge"
              type="button"
              class="inline-flex min-h-control items-center gap-1.5 rounded-md border px-3 text-sm font-medium transition hover:bg-accent"
              data-customer-merge-any
              @click="compare(null)"
            >
              <Icon name="lucide:merge" class="size-4" />
              Unificar com outro cadastro…
            </button>
          </div>
          <dl class="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
            <div class="flex gap-2"><dt class="text-muted-foreground">Telefone</dt><dd>{{ customer.phone_display || "Sem telefone" }}</dd></div>
            <div class="flex gap-2"><dt class="text-muted-foreground">E-mail</dt><dd>{{ customer.email || "Sem e-mail" }}</dd></div>
            <div class="flex gap-2"><dt class="text-muted-foreground">CPF</dt><dd>{{ customer.document_display || "Sem CPF" }}</dd></div>
            <div v-if="customer.birthday_display" class="flex gap-2"><dt class="text-muted-foreground">Aniversário</dt><dd>{{ customer.birthday_display }}</dd></div>
          </dl>
          <p v-if="customer.notes" class="mt-3 whitespace-pre-line rounded bg-muted/50 p-2 text-sm">{{ customer.notes }}</p>
        </article>

        <!-- Quem pode ser a mesma pessoa -->
        <article v-if="customer.candidates.length" class="rounded-lg border border-amber-300 bg-card p-4 lg:col-span-2 dark:border-amber-500/40" data-customer-candidates>
          <h2 class="text-sm font-semibold">Pode ser a mesma pessoa</h2>
          <p class="text-xs text-muted-foreground">Sugestão da tela, com o motivo em cada linha. Confira antes de unificar.</p>
          <ul class="mt-2 divide-y">
            <li v-for="candidate in customer.candidates" :key="candidate.ref" class="flex flex-wrap items-center justify-between gap-3 py-2">
              <div class="min-w-0 text-sm">
                <NuxtLink :to="`/customers/${encodeURIComponent(candidate.ref)}`" class="font-medium hover:underline">{{ candidate.name }}</NuxtLink>
                <span class="ml-2 font-mono text-xs text-muted-foreground">{{ candidate.ref }}</span>
                <p class="text-xs text-muted-foreground">
                  <span class="font-medium text-amber-800 dark:text-amber-200">{{ candidate.reason_label }}</span>
                  · {{ candidate.phone_display || "sem telefone" }}
                  <template v-if="candidate.source_label"> · {{ candidate.source_label }}</template>
                  · {{ candidate.orders_label }}
                </p>
              </div>
              <button
                type="button"
                class="min-h-control rounded-md border px-3 text-sm font-medium transition hover:bg-accent"
                :data-customer-compare="candidate.ref"
                @click="compare(candidate)"
              >
                Comparar
              </button>
            </li>
          </ul>
        </article>

        <article class="rounded-lg border bg-card p-4">
          <h2 class="text-sm font-semibold">Pedidos</h2>
          <p class="text-sm">
            {{ customer.orders_label }}<template v-if="customer.total_spent_display"> · {{ customer.total_spent_display }} no total</template>
            <template v-if="customer.last_order_display"> · último {{ customer.last_order_display }}</template>
          </p>
          <ul v-if="customer.recent_orders.length" class="mt-2 divide-y text-sm">
            <li v-for="order in customer.recent_orders" :key="order.ref">
              <NuxtLink :to="`/${encodeURIComponent(order.ref)}`" class="flex flex-wrap items-center justify-between gap-2 py-1.5 hover:underline">
                <span><span class="font-mono text-xs">{{ order.ref }}</span> · {{ order.channel_label }}</span>
                <span class="text-xs text-muted-foreground">{{ order.ordered_at_display }} · {{ order.status_label }} · {{ order.total_display }}</span>
              </NuxtLink>
            </li>
          </ul>
        </article>

        <article class="rounded-lg border bg-card p-4">
          <h2 class="text-sm font-semibold">Identificadores</h2>
          <p class="text-xs text-muted-foreground">As chaves pelas quais os canais reconhecem esta pessoa.</p>
          <ul v-if="customer.identifiers.length" class="mt-2 space-y-1 text-sm">
            <li v-for="identifier in customer.identifiers" :key="`${identifier.type_label}:${identifier.value}`" class="flex gap-2">
              <span class="text-muted-foreground">{{ identifier.type_label }}</span>
              <span class="break-all font-mono text-xs leading-5">{{ identifier.value }}</span>
            </li>
          </ul>
          <p v-else class="mt-2 text-sm text-muted-foreground">Nenhum identificador.</p>
          <h2 class="mt-4 text-sm font-semibold">Endereços</h2>
          <ul v-if="customer.addresses.length" class="mt-1 space-y-1 text-sm">
            <li v-for="address in customer.addresses" :key="address">{{ address }}</li>
          </ul>
          <p v-else class="mt-1 text-sm text-muted-foreground">Nenhum endereço salvo.</p>
        </article>
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
