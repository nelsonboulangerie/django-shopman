<script setup lang="ts">
// Prévia M3 (DEV-2026-030): o que o entregador da casa recebe (celular, 375 px) e o que o
// cliente vê na corrida da casa. Dados fictícios: nada aqui chama a API.
import { reactive } from "vue";
import { rideColor } from "~/presentation/ridePalette";

const tone = rideColor(0);
type Phase = "before" | "route" | "back" | "expired";
interface Stop {
  code: string;
  name: string;
  street: string;
  extra: string;
  charge: string;
  bags: number;
  state: "open" | "done" | "failed";
}
const ride = reactive({
  phase: "before" as Phase,
  stops: [
    { code: "A47", name: "Marina", street: "Rua Caracas, 420, apto 41", extra: "Gleba Palhano · Interfone 41", charge: "Cobrar R$ 58,00 em dinheiro · Troco para R$ 100,00", bags: 2, state: "open" },
    { code: "C03", name: "Paulo", street: "Rua Bélgica, 155", extra: "Gleba Palhano · Casa de portão verde", charge: "Cobrar R$ 30,00 em dinheiro · Troco para R$ 50,00", bags: 1, state: "open" },
  ] as Stop[],
});
const open = () => ride.stops.filter((s) => s.state === "open");
function mark(s: Stop, state: "done" | "failed") {
  s.state = state;
  if (!open().length) ride.phase = "back";
}
// O que volta com ele: a maquininha sempre; o dinheiro de quem pagou; a sacola de quem não recebeu.
function backLine(): string {
  const codes = (st: Stop["state"]) => ride.stops.filter((s) => s.state === st).map((s) => s.code);
  const join = (c: string[]) => (c.length > 1 ? `${c.slice(0, -1).join(", ")} e ${c.at(-1)}` : c[0] ?? "");
  const parts = ["a maquininha azul"];
  if (codes("done").length) parts.push(`o dinheiro de ${join(codes("done"))}`);
  const failed = codes("failed");
  if (failed.length) parts.push(failed.length > 1 ? `as sacolas de ${join(failed)}` : `a sacola de ${failed[0]}`);
  return `Volte à loja com ${join(parts)}.`;
}
function reset() {
  ride.phase = "before";
  ride.stops.forEach((s) => (s.state = "open"));
}
</script>

<template>
  <div>
    <Teleport to="body">
      <div class="absolute inset-x-0 top-0 z-40 min-h-dvh bg-default pb-32" data-preview-overlay>
        <main class="mx-auto flex w-full max-w-[1440px] flex-col gap-6 px-8 py-8">
          <header class="flex flex-col gap-1">
            <MsPreviewNav :current="3" />
            <h1 class="op-title font-semibold text-highlighted">Prévia M3 · O que o entregador da casa recebe</h1>
            <p class="op-body text-toned">
              Você decide: o entregador recebe um link no WhatsApp, que ele toca para dizer que saiu e que entregou (A, a minha
              recomendação, sempre com a via impressa junto), ou só a via impressa, e quem avança é o operador no Gestor (B). Os botões do
              link funcionam aqui: experimente.
            </p>
            <p class="op-micro text-muted">
              Cena: corrida A, de Diego, com A47 e C03. Dado do cliente no mínimo: primeiro nome, endereço e instruções; telefone só no botão
              "Ligar" enquanto a parada está aberta; sem CPF, sem itens, sem preço dos itens. O link vale até 2 h depois da corrida fechar.
            </p>
          </header>

          <div class="flex items-start gap-10">
            <!-- A: o link -->
            <div class="flex flex-col gap-2">
              <div class="flex items-start gap-3">
                <span class="grid size-9 shrink-0 place-items-center rounded-lg bg-inverted text-lg font-bold text-inverted">A</span>
                <p class="op-body w-[330px] pt-1.5 text-toned">O link do entregador. <strong class="text-highlighted">Recomendo.</strong></p>
              </div>
              <div class="flex w-[375px] flex-col overflow-hidden rounded-[2rem] border-8 border-black/80 bg-[#faf7f2]">
                <div class="flex items-center gap-3 px-4 pt-4 pb-3" :style="{ background: tone.bg, color: tone.fg }">
                  <span class="grid size-10 place-items-center rounded-lg bg-white/15 text-2xl font-black">A</span>
                  <div class="flex flex-col">
                    <span class="text-sm opacity-80">Nelson Boulangerie</span>
                    <span class="text-lg font-bold">Corrida A · Diego</span>
                  </div>
                </div>

                <template v-if="ride.phase === 'expired'">
                  <div class="flex flex-col items-center gap-2 px-6 py-16 text-center text-black/70">
                    <NuxtIcon name="i-lucide-lock" class="size-8" />
                    <p class="text-lg font-semibold text-black">Esta corrida terminou.</p>
                    <p class="text-sm">O endereço e o telefone dos clientes não aparecem mais aqui.</p>
                  </div>
                </template>

                <template v-else>
                  <div class="flex flex-col gap-1 border-b border-black/10 px-4 py-3 text-black">
                    <p class="text-base font-semibold">Você recebe R$ 15,00 por esta corrida.</p>
                    <p class="text-sm text-black/70">2 entregas · 7,4 km com a volta · Tabela da casa</p>
                  </div>

                  <div v-if="ride.phase === 'before'" class="flex flex-col gap-1 border-b border-black/10 px-4 py-3 text-black">
                    <p class="text-sm font-semibold">Leve da loja</p>
                    <p class="text-sm">3 sacolas: 2 de A47 e 1 de C03</p>
                    <p class="text-sm">Troco: R$ 70,00 (R$ 50,00 de A47 e R$ 20,00 de C03)</p>
                    <p class="flex items-center gap-1.5 text-sm">Maquininha: <span class="size-3 rounded-full bg-[#2563eb]" />azul</p>
                    <p class="mt-1 rounded-lg bg-black/5 px-2.5 py-1.5 text-sm">Da loja: "Paulo pediu para tocar a campainha, o interfone não funciona."</p>
                  </div>

                  <div class="flex flex-col gap-2 px-4 py-3">
                    <div class="flex items-center justify-between">
                      <p class="text-sm font-semibold text-black">A rota, nesta ordem</p>
                      <a class="text-sm font-semibold text-[#0047ff] underline" href="#">Abrir a rota no mapa</a>
                    </div>
                    <div
                      v-for="(s, i) in ride.stops"
                      :key="s.code"
                      class="flex flex-col gap-1.5 rounded-xl bg-white p-3 text-black ring-1 ring-black/10"
                      :class="s.state !== 'open' ? 'opacity-60' : ''"
                    >
                      <div class="flex items-center gap-2">
                        <span class="grid size-6 place-items-center rounded-full bg-black text-xs font-bold text-white">{{ i + 1 }}</span>
                        <span class="text-base font-bold">{{ s.code }} · {{ s.name }}</span>
                        <span class="ms-auto text-xs text-black/60">{{ s.bags }} {{ s.bags === 1 ? "sacola" : "sacolas" }}</span>
                      </div>
                      <p class="text-sm">{{ s.street }}</p>
                      <p class="text-sm text-black/60">{{ s.extra }}</p>
                      <p class="text-sm font-semibold" :class="s.charge.startsWith('Pago') ? 'text-[#00a03c]' : 'text-[#b45309]'">{{ s.charge }}</p>
                      <p v-if="s.state === 'done'" class="text-sm font-semibold text-[#00a03c]">Entregue às 12h52</p>
                      <p v-if="s.state === 'failed'" class="text-sm font-semibold text-[#b91c1c]">Não entregue. Traga a sacola de volta.</p>
                      <div v-if="s.state === 'open'" class="flex gap-2 pt-1">
                        <a href="#" class="flex-1 rounded-lg bg-black/5 py-2 text-center text-sm font-semibold">Mapa</a>
                        <a href="#" class="flex-1 rounded-lg bg-black/5 py-2 text-center text-sm font-semibold">Ligar</a>
                      </div>
                      <div v-if="s.state === 'open' && ride.phase === 'route'" class="flex flex-col gap-1.5">
                        <button type="button" class="rounded-lg bg-[#00a03c] py-2.5 text-base font-bold text-black" @click="mark(s, 'done')">Entreguei {{ s.code }}</button>
                        <button type="button" class="rounded-lg py-1.5 text-sm font-semibold text-black/70 underline" @click="mark(s, 'failed')">Não consegui entregar</button>
                      </div>
                    </div>
                  </div>

                  <div class="px-4 pb-4">
                    <button v-if="ride.phase === 'before'" type="button" class="w-full rounded-xl py-3 text-lg font-bold" :style="{ background: tone.bg, color: tone.fg }" @click="ride.phase = 'route'">Saí da loja</button>
                    <div v-else-if="ride.phase === 'back'" class="flex flex-col gap-2">
                      <p class="text-center text-sm text-black/70">{{ backLine() }}</p>
                      <button type="button" class="w-full rounded-xl py-3 text-lg font-bold" :style="{ background: tone.bg, color: tone.fg }" @click="ride.phase = 'expired'">Voltei à loja</button>
                    </div>
                    <p class="pt-3 text-center text-xs text-black/50">Este link vale até 2 h depois da corrida terminar.</p>
                  </div>
                </template>
              </div>
              <NuxtButton class="self-start" size="xs" color="neutral" variant="outline" icon="i-lucide-rotate-ccw" label="Recomeçar a cena" @click="reset" />
            </div>

            <!-- B: só a via impressa -->
            <div class="flex flex-col gap-2">
              <div class="flex items-start gap-3">
                <span class="grid size-9 shrink-0 place-items-center rounded-lg bg-inverted text-lg font-bold text-inverted">B</span>
                <p class="op-body w-[300px] pt-1.5 text-toned">Só a via impressa (#2406). Quem diz "saiu" e "entregue" é o operador no Gestor. Em A ela sai igual, com o QR do link.</p>
              </div>
              <div class="w-[300px] bg-white px-4 py-5 font-mono text-[12px] leading-snug text-black shadow-lg ring-1 ring-black/10">
                <p class="text-center font-bold">NELSON BOULANGERIE</p>
                <p class="text-center">Via do entregador (identificada)</p>
                <p class="mt-2 text-center text-base font-bold">CORRIDA A · DIEGO</p>
                <p class="text-center">Você recebe R$ 15,00</p>
                <p class="mt-2">--------------------------------</p>
                <p class="font-bold">1. A47 · Marina · 2 sacolas</p>
                <p>Rua Caracas, 420, apto 41</p>
                <p>Gleba Palhano · Interfone 41</p>
                <p class="font-bold">Cobrar R$ 58,00 em dinheiro</p>
                <p>Troco para R$ 100,00</p>
                <p class="mt-2 font-bold">2. C03 · Paulo · 1 sacola</p>
                <p>Rua Bélgica, 155</p>
                <p>Gleba Palhano · Casa de portão verde</p>
                <p class="font-bold">Cobrar R$ 30,00 em dinheiro</p>
                <p>Troco para R$ 50,00</p>
                <p class="mt-2">--------------------------------</p>
                <p>Leva: troco R$ 70,00 · maquininha azul</p>
                <p>Obs.: Paulo pediu para tocar a campainha.</p>
                <div class="mx-auto mt-3 grid size-24 place-items-center bg-[repeating-conic-gradient(#000_0_25%,#fff_0_50%)] bg-[length:12px_12px]" aria-label="QR do link da corrida" />
                <p class="mt-1 text-center">Aponte a câmera: rota e entregas</p>
              </div>
            </div>

            <!-- o cliente -->
            <div class="flex flex-col gap-2">
              <div class="flex items-start gap-3">
                <span class="grid size-9 shrink-0 place-items-center rounded-lg bg-elevated text-lg font-bold text-highlighted ring-1 ring-default">6</span>
                <p class="op-body w-[300px] pt-1.5 text-toned">O que o cliente vê depois da saída (pergunta 6). Sem link de terceiro, sem "corrida", na voz já decidida na prévia 7 da revisão.</p>
              </div>
              <div v-for="alt in [1, 2]" :key="alt" class="flex w-[300px] flex-col gap-2 rounded-2xl bg-[#faf7f2] p-4 text-black ring-1 ring-black/10">
                <p class="text-xs font-semibold text-black/50">{{ alt === 1 ? "1 · Nome e hora (recomendo)" : "2 · Com a posição ao vivo" }}</p>
                <p class="text-sm text-black/60">Pedido A47</p>
                <p class="text-lg font-bold">Diego está a caminho.</p>
                <p class="text-base">Deve chegar por volta de 12h45.</p>
                <div v-if="alt === 2" class="relative h-32 overflow-hidden rounded-xl bg-[#e8eef3]">
                  <span class="absolute top-10 left-16 size-3 rounded-full bg-[#0047ff] ring-4 ring-[#0047ff]/25" />
                  <span class="absolute right-10 bottom-8 size-3 rounded-sm bg-black" />
                  <p class="absolute bottom-1 left-2 text-[10px] text-black/50">Posição de há 20 s</p>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </Teleport>
  </div>
</template>
