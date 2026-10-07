<script setup lang="ts">
import {
  dashboardSegments,
  dashboardTabs,
  dashboardTeam,
  dashboardTrend,
} from "../fixtures/operatorDashboard";
import { kitchenSinkQueue } from "../fixtures/operatorKitchenSink";

const tab = ref("overview");
const bars = ref(false);
const completed = ref(18);
const detailOpen = ref(false);
const selectedTask = ref<(typeof kitchenSinkQueue)[number]>(
  kitchenSinkQueue[0]!,
);
const chartColumns = [
  { accessorKey: "label", header: "Hora" },
  { accessorKey: "orders", header: "Pedidos confirmados" },
];
</script>

<template>
  <section
    id="dashboard-exercises"
    class="space-y-4"
    aria-labelledby="dashboard-exercises-title"
    data-operator-audit-id="catalog-dashboard"
  >
    <div>
      <h2 id="dashboard-exercises-title" class="op-title">
        Dashboard de turno
      </h2>
      <p class="op-body text-muted">
        Central, B.I., Compras e Produção: contexto, comparação e próxima ação.
        Turno de fixture, 6 de outubro.
      </p>
    </div>
    <div class="grid gap-3 sm:grid-cols-3">
      <NuxtCard title="Pedidos abertos" description="Todos os canais"
        ><p class="op-figure">24</p>
        <NuxtBadge color="warning" variant="subtle"
          >3 precisam de decisão</NuxtBadge
        ></NuxtCard
      >
      <NuxtCard title="Produção concluída" description="18 de 24 pedidos"
        ><p class="op-figure">75%</p>
        <NuxtProgress
          :model-value="18"
          :max="24"
          :get-value-label="() => 'Produção concluída, 18 de 24 pedidos'"
      /></NuxtCard>
      <NuxtCard title="Equipe do turno" description="2 em atividade, 1 em pausa"
        ><NuxtAvatarGroup
          ><NuxtAvatar
            v-for="person in dashboardTeam"
            :key="person.name"
            :alt="person.name"
            :text="person.initials" /></NuxtAvatarGroup
      ></NuxtCard>
    </div>
    <NuxtTabs
      v-model="tab"
      :items="dashboardTabs"
      variant="link"
      :ui="{ list: 'w-full', label: 'whitespace-normal' }"
    >
      <template #overview>
        <div class="grid items-start gap-3 lg:grid-cols-2">
          <NuxtCard
            title="Pedidos confirmados por hora"
            description="125 pedidos entre 09h e 14h. Pico às 12h, com 31 pedidos."
          >
            <div class="mb-3 flex flex-wrap items-center gap-2">
              <NuxtSwitch v-model="bars" label="Mostrar em barras" /><NuxtBadge
                color="neutral"
                variant="outline"
                >Dados fixos</NuxtBadge
              >
            </div>
            <ClientOnly
              ><OperatorKitchenSinkChart :bars="bars" /><template #fallback
                ><NuxtSkeleton class="h-48" /></template
            ></ClientOnly>
            <p class="op-micro my-3">
              Unovis, como no template oficial de dashboard. Nuxt UI não oferece
              Chart. A tabela abaixo é a mesma série e permanece disponível no
              SSR.
            </p>
            <NuxtTable
              :data="dashboardTrend"
              :columns="chartColumns"
              caption="Dados do gráfico de pedidos"
            />
          </NuxtCard>
          <div class="space-y-3">
            <NuxtCard
              title="Distribuição da fila"
              description="Partes do mesmo total, sem somar grandezas diferentes"
              ><NuxtProgressGroup
                :items="dashboardSegments"
                :max="24"
                aria-label="Distribuição dos 24 pedidos"
            /></NuxtCard>
            <NuxtCard
              title="Separação do lote"
              description="Progresso com total conhecido e conclusão controlada"
            >
              <NuxtProgress
                :model-value="completed"
                :max="24"
                status
                :get-value-label="() => `Pedidos separados, ${completed} de 24`"
              />
              <div class="mt-3 flex flex-wrap gap-2">
                <NuxtButton
                  :disabled="completed === 24"
                  @click="completed = Math.min(24, completed + 1)"
                  >Separar próximo</NuxtButton
                ><NuxtButton
                  color="neutral"
                  variant="ghost"
                  @click="completed = 18"
                  >Reiniciar fixture</NuxtButton
                >
              </div>
            </NuxtCard>
            <NuxtCard
              title="Atualização em andamento"
              description="Sem percentual inventado quando o total é desconhecido"
              ><div role="status">
                Atualizando dados do turno<NuxtProgress
                  aria-hidden="true"
                /></div
            ></NuxtCard>
            <NuxtCard
              title="Teclado do dashboard"
              description="Atalhos reais, não rótulos sem comportamento"
            >
              <dl class="space-y-2">
                <div class="flex items-center justify-between gap-2">
                  <dt>Busca global</dt>
                  <dd><NuxtKbd value="meta" /> <NuxtKbd value="k" /></dd>
                </div>
                <div class="flex items-center justify-between gap-2">
                  <dt>Alternar tabs com foco na tab</dt>
                  <dd>
                    <NuxtKbd value="arrowleft" /> <NuxtKbd value="arrowright" />
                  </dd>
                </div>
                <div class="flex items-center justify-between gap-2">
                  <dt>Fechar overlay</dt>
                  <dd><NuxtKbd value="escape" /></dd>
                </div>
              </dl>
            </NuxtCard>
          </div>
        </div>
      </template>
      <template #queue>
        <NuxtCard
          title="Decisões pendentes"
          description="Urgência e ação explícitas, sem precisar abrir cada pedido"
        >
          <ul class="divide-y divide-default">
            <li
              v-for="(task, index) in kitchenSinkQueue"
              :key="task.ref"
              class="flex flex-wrap items-center gap-3 py-3 first:pt-0 last:pb-0"
            >
              <NuxtAvatar
                :alt="dashboardTeam[index]!.name"
                :text="dashboardTeam[index]!.initials"
              />
              <div class="min-w-0 flex-1">
                <p class="op-label">{{ task.ref }}: {{ task.title }}</p>
                <p class="op-body text-muted">{{ task.detail }}</p>
              </div>
              <NuxtBadge :color="task.tone" variant="subtle"
                >Requer decisão</NuxtBadge
              ><NuxtButton
                color="neutral"
                variant="outline"
                :aria-label="`Revisar ${task.ref}`"
                @click="
                  selectedTask = task;
                  detailOpen = true;
                "
                >Revisar</NuxtButton
              >
            </li>
          </ul>
        </NuxtCard>
      </template>
      <template #team>
        <NuxtCard
          title="Responsáveis"
          description="Avatar com iniciais, identidade textual e estado que não depende só da cor"
          ><ul class="space-y-3">
            <li
              v-for="person in dashboardTeam"
              :key="person.name"
              class="flex flex-wrap items-center gap-3"
            >
              <NuxtChip
                :color="person.status === 'Em pausa' ? 'warning' : 'success'"
                size="2xl"
                inset
                ><NuxtAvatar :alt="person.name" :text="person.initials"
              /></NuxtChip>
              <div class="min-w-0 flex-1">
                <p class="op-label">{{ person.name }}</p>
                <p class="op-body text-muted">{{ person.role }}</p>
              </div>
              <NuxtBadge color="neutral" variant="outline">{{
                person.status
              }}</NuxtBadge>
            </li>
          </ul></NuxtCard
        >
      </template>
    </NuxtTabs>
    <NuxtSlideover
      v-model:open="detailOpen"
      :title="selectedTask.ref"
      :description="selectedTask.title"
      ><template #body
        ><p class="op-body">{{ selectedTask.detail }}</p>
        <NuxtAlert
          role="status"
          class="mt-4"
          icon="i-lucide-info"
          title="Fixture de inspeção"
          description="Nenhuma decisão comercial é enviada. Este exemplo demonstra lista, seleção e detalhe contextual." /></template
      ><template #footer
        ><NuxtButton
          color="neutral"
          variant="outline"
          @click="detailOpen = false"
          >Voltar à fila</NuxtButton
        ></template
      ></NuxtSlideover
    >
  </section>
</template>
