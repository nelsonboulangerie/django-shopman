<script setup lang="ts">
// PRÉVIA (14/11) — o ciclo das corridas, com dados de exemplo. Não vai ao ar.
import type { PlannerOrder } from "~/components/CourierRidePlanner.vue";

const route = useRoute();
const moment = computed(() => String(route.query.moment || "montar"));
const C: Record<string, [number, number]> = {
  "Gleba Palhano": [-23.331, -51.181], Centro: [-23.309, -51.161], "Jardim Higienópolis": [-23.319, -51.148], "Bela Suíça": [-23.343, -51.165],
};
const raw: [string, string, string, "Pronto" | "Em preparo", number, number, ("troco" | "maquininha" | "")?][] = [
  ["A12", "Maria Santos", "Gleba Palhano", "Pronto", 0.002, -0.001],
  ["A14", "João Oliveira", "Gleba Palhano", "Pronto", -0.0015, 0.002, "troco"],
  ["A17", "Pedro Alves", "Gleba Palhano", "Em preparo", -0.001, -0.0025],
  ["A18", "Fernanda Dias", "Gleba Palhano", "Pronto", 0.0022, 0.0028],
  ["B03", "Ana Lima", "Centro", "Pronto", 0.001, 0.0025],
  ["B05", "Beatriz Rocha", "Centro", "Pronto", 0.0025, 0.001, "maquininha"],
  ["B09", "Juliana Mendes", "Centro", "Pronto", 0.0005, -0.002],
  ["C04", "Carlos Souza", "Jardim Higienópolis", "Em preparo", -0.002, -0.0015],
  ["C08", "Rafael Costa", "Jardim Higienópolis", "Pronto", -0.0025, 0.001],
  ["D07", "Lúcia Ferreira", "Bela Suíça", "Pronto", 0.0015, 0.0015],
  ["D10", "Tiago Martins", "Bela Suíça", "Pronto", -0.001, 0.002],
];
const orders: PlannerOrder[] = raw.map(([code, customer, place, stage, dl, dg, asks]) => ({
  ref: code, code, customer, place, stage, latitude: C[place]![0] + dl, longitude: C[place]![1] + dg, asks: asks ?? "",
}));
const origin = { latitude: -23.3105, longitude: -51.1695 };
const initial = computed(() =>
  moment.value === "vazio" ? [[]] : [["A12", "A14", "A18"], ["B03", "B09"]],
);
</script>

<template>
  <div class="min-h-dvh bg-[color-mix(in_oklab,var(--ui-bg-elevated)_60%,var(--ui-bg))] p-6" data-preview-corridas>
    <div v-if="moment === 'montar' || moment === 'vazio'" class="mx-auto max-w-6xl overflow-hidden rounded-2xl bg-default shadow-2xl ring-1 ring-default">
      <div class="flex items-start justify-between border-b border-default px-6 py-4">
        <div>
          <p class="op-title font-semibold text-highlighted">Juntar entregas</p>
          <p class="op-body text-muted">11 entregas esperando entregador. Monte uma ou mais corridas da TaOn; cada uma leva até 4 pedidos.</p>
        </div>
        <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" aria-label="Fechar" />
      </div>
      <CourierRidePlanner :orders="orders" :origin="origin" :initial="initial" :initial-active="moment === 'vazio' ? 0 : 1" />
    </div>

    <div v-else class="mx-auto grid max-w-6xl grid-cols-3 gap-4">
      <CourierRideCard :number="1" color="#8b6a2f" state="atStore" :courier="{ name: 'Diego', vehicle: 'Moto vermelha · ABC1D23' }"
        :stops="[{ code: 'A12', customer: 'Maria Santos', place: 'Gleba Palhano', state: 'ready' }, { code: 'A14', customer: 'João Oliveira', place: 'Gleba Palhano', state: 'ready' }, { code: 'A18', customer: 'Fernanda Dias', place: 'Gleba Palhano', state: 'ready' }]"
        :handoff="['3 sacolas', 'Troco R$ 20,00 (A14)']" cost="R$ 18,40" />
      <CourierRideCard :number="2" color="#2f6f9f" state="coming" eta="6 min" :courier="{ name: 'Rita', vehicle: 'Moto preta · QWE4R56' }"
        :stops="[{ code: 'B03', customer: 'Ana Lima', place: 'Centro', state: 'ready' }, { code: 'B05', customer: 'Beatriz Rocha', place: 'Centro', state: 'prep' }]"
        :handoff="['2 sacolas', 'Maquininha Azul (B05)']" cost="R$ 11,90" />
      <CourierRideCard :number="3" color="#3f7f4f" state="searching" since="1 min"
        :stops="[{ code: 'C04', customer: 'Carlos Souza', place: 'Jardim Higienópolis', state: 'ready' }, { code: 'C08', customer: 'Rafael Costa', place: 'Jardim Higienópolis', state: 'ready' }]" cost="R$ 12,50" />
      <CourierRideCard :number="4" color="#8f3a4a" state="route" :courier="{ name: 'Léo', vehicle: 'Moto azul · JKL7M89' }"
        :stops="[{ code: 'D07', customer: 'Lúcia Ferreira', place: 'Bela Suíça', state: 'done' }, { code: 'D10', customer: 'Tiago Martins', place: 'Bela Suíça', state: 'now', eta: '12:41' }, { code: 'D11', customer: 'Sofia Ramos', place: 'Bela Suíça', state: 'next', eta: '12:49' }]" />
      <CourierRideCard :number="5" color="#8b6a2f" state="back" :courier="{ name: 'Marcos', vehicle: 'Moto vermelha · XYZ9K87' }"
        :stops="[{ code: 'E01', customer: 'Paula Nunes', place: 'Centro', state: 'done' }, { code: 'E02', customer: 'Rui Prado', place: 'Centro', state: 'done' }]"
        :handoff="['Maquininha Azul', 'R$ 48,00 em dinheiro (E02)']" />
      <CourierRideCard :number="6" color="#2f6f9f" state="late" since="9 min"
        :stops="[{ code: 'F03', customer: 'Igor Lins', place: 'Gleba Palhano', state: 'ready' }, { code: 'F05', customer: 'Nina Reis', place: 'Centro', state: 'ready' }]" />
    </div>
  </div>
</template>
