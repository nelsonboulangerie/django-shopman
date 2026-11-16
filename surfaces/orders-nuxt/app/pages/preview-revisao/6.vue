<script setup lang="ts">
// Prévia 6 da revisão das Entregas: entrega das sacolas ao entregador, cancelar a
// corrida (antes e depois do aceite) e "Entregador voltou" por pedido.
// Dados fictícios, sem backend: nada aqui chama a API.
import { rideColor } from "~/presentation/ridePalette";

// Corrida aparece por letra (1 → A, 2 → B…); a cor segue rideColor(n - 1).
const rideLetter = (n: number) => String.fromCharCode(64 + n);
const rideN = 2;
const otherN = 1;
const ride = rideColor(rideN - 1); // corrida B: Verde
const other = rideColor(otherN - 1); // corrida A: Azul (só no mapa, para contexto)
const rideL = rideLetter(rideN);
const otherL = rideLetter(otherN);

interface Stop {
  code: string;
  place: string;
  pay: string;
  bags: number;
  x: number;
  y: number;
}
const stops: Stop[] = [
  { code: "A05", place: "Gleba Palhano", pay: "Cartão na entrega · maquininha Azul", bags: 2, x: 120, y: 190 },
  { code: "C12", place: "Centro", pay: "Dinheiro · troco R$ 20,00", bags: 1, x: 300, y: 70 },
];
const store = { x: 230, y: 150 };

// "Entregador voltou" por pedido: Entregue já marcado; A05 em "Voltou com a sacola".
const deliveredA = reactive<Record<string, boolean>>({ A05: false, C12: true });
const deliveredB = reactive<Record<string, boolean>>({ A05: false, C12: true });

const routePath = `M ${store.x} ${store.y} L ${stops[0]!.x} ${stops[0]!.y} L ${stops[1]!.x} ${stops[1]!.y}`;
const returnPath = `M ${stops[1]!.x} ${stops[1]!.y} L ${store.x} ${store.y}`;
</script>

<template>
  <!-- Prévia de olhar: cobre a casca do Gestor (barra lateral e rolagem interna)
       para a página ter os 1440 px inteiros e rolar com o documento. -->
  <div>
    <Teleport to="body">
      <div class="absolute inset-x-0 top-0 z-40 min-h-dvh bg-default" data-preview-overlay>
        <div class="mx-auto flex flex-col gap-6 bg-default p-6 text-default" style="width: 100%; max-width: 1440px">
          <!-- cabeçalho da prévia -->
          <header class="flex flex-col gap-1">
            <PreviewNav :current="6" />
            <h1 class="op-title font-semibold text-highlighted">Prévia 6 · Entrega ao entregador e volta</h1>
            <p class="op-body text-toned">
              Você decide: na corrida com retorno, o cliente recebe "Entregue" só depois que o entregador volta à loja (A) ou no fim da corrida, como hoje (B).
            </p>
          </header>

          <NuxtAlert
            color="warning"
            variant="subtle"
            icon="i-lucide-scale"
            title="Antes de decidir: dois documentos discordam e um deles é decisão sua"
          >
            <template #description>
              <ul class="list-inside list-disc op-body">
                <li>
                  O plano das entregas diz que o fim da corrida (a letra F da TaOn) chega depois da volta à loja. O roteiro de homologação diz que o F chega na porta do cliente. Nenhum dos dois foi medido numa corrida de verdade (lacuna L4).
                </li>
                <li>
                  A inverte a decisão 3 do plano: "finalização vira entregue automático, sem confirmação". Em A, na corrida com retorno, quem confirma é o balcão, na volta.
                </li>
                <li>
                  A medição proposta: uma corrida com retorno de 1 parada e outra de 2 paradas, anotando a hora de cada entrega, a hora do F e a hora em que a moto chegou à loja.
                </li>
              </ul>
            </template>
          </NuxtAlert>

          <!-- ========== IGUAL EM A E B ========== -->
          <section class="flex flex-col gap-3">
            <h2 class="op-title text-highlighted">Igual em A e B</h2>
            <div class="grid grid-cols-3 gap-6">
              <!-- (i) entrega das sacolas -->
              <div class="flex flex-col gap-2">
                <p class="op-micro text-muted">1. O entregador chegou à loja: entregar as sacolas</p>
                <NuxtCard>
                  <div class="flex flex-col gap-3">
                    <div class="flex items-center gap-2">
                      <span class="grid size-8 place-items-center rounded-lg op-label font-bold" :style="{ background: ride.bg, color: ride.fg }">{{ rideL }}</span>
                      <h3 class="op-title text-highlighted">Corrida {{ rideL }} · Entregador na loja</h3>
                    </div>
                    <div class="flex items-center gap-3 rounded-lg border border-default p-3">
                      <NuxtAvatar alt="Diego Martins" size="3xl" />
                      <div class="flex flex-col">
                        <span class="op-title text-highlighted">Diego Martins</span>
                        <span class="flex items-center gap-1.5 op-body text-toned">
                          <NuxtIcon name="i-lucide-bike" class="size-4" />Moto prata · ABC1D23
                        </span>
                        <span class="op-micro text-muted">(43) 99812-4410</span>
                      </div>
                    </div>
                    <NuxtAlert
                      color="warning"
                      variant="subtle"
                      icon="i-lucide-shield-check"
                      title="Leva a maquininha e o troco. Confira a placa antes de entregar."
                    />
                    <ul class="flex flex-col gap-1.5">
                      <li v-for="stop in stops" :key="stop.code" class="flex items-start gap-2 op-body">
                        <NuxtIcon name="i-lucide-package" class="mt-0.5 size-4 text-muted" />
                        <span>
                          <strong class="tabular-nums">{{ stop.code }}</strong> · {{ stop.bags }} {{ stop.bags === 1 ? "sacola" : "sacolas" }} · {{ stop.place }}
                          <span class="block op-micro text-muted">{{ stop.pay }}</span>
                        </span>
                      </li>
                    </ul>
                    <NuxtButton block color="primary" icon="i-lucide-package-check" label="Entreguei as 3 sacolas para o Diego" />
                  </div>
                </NuxtCard>

                <!-- mapa simples: loja preta, pinos na cor da corrida, volta tracejada -->
                <div class="overflow-hidden rounded-lg border border-default">
                  <svg viewBox="0 0 420 240" class="block w-full" role="img" :aria-label="`Mapa da corrida ${rideL}: loja, A05 e C12, com volta à loja`">
                    <defs>
                      <pattern id="grade6" width="20" height="20" patternUnits="userSpaceOnUse">
                        <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#e5e7eb" stroke-width="1" />
                      </pattern>
                    </defs>
                    <rect width="420" height="240" fill="#f8fafc" />
                    <rect width="420" height="240" fill="url(#grade6)" />
                    <text x="20" y="225" font-size="11" fill="#64748b">Gleba Palhano</text>
                    <text x="290" y="40" font-size="11" fill="#64748b">Centro</text>
                    <text x="320" y="200" font-size="11" fill="#64748b">Bela Suíça</text>
                    <path :d="routePath" fill="none" :stroke="ride.bg" stroke-width="4" stroke-linejoin="round" />
                    <path :d="returnPath" fill="none" :stroke="ride.bg" stroke-width="3" stroke-dasharray="6 6" />
                    <g>
                      <circle cx="360" cy="170" r="11" :fill="other.bg" />
                      <text x="360" y="174" font-size="10" text-anchor="middle" :fill="other.fg" font-weight="700">{{ otherL }}</text>
                    </g>
                    <rect :x="store.x - 12" :y="store.y - 12" width="24" height="24" rx="4" fill="#111111" />
                    <text :x="store.x" :y="store.y + 4" font-size="10" text-anchor="middle" fill="#ffffff" font-weight="700">L</text>
                    <g v-for="stop in stops" :key="stop.code">
                      <circle :cx="stop.x" :cy="stop.y" r="15" :fill="ride.bg" stroke="#ffffff" stroke-width="2" />
                      <text :x="stop.x" :y="stop.y + 4" font-size="10" text-anchor="middle" :fill="ride.fg" font-weight="700">{{ stop.code }}</text>
                    </g>
                  </svg>
                  <p class="border-t border-default px-3 py-1.5 op-micro text-muted">Corrida {{ rideL }}: loja, A05, C12 e volta à loja (tracejado). O {{ otherL }} azul é a corrida {{ otherL }}, em outra rota.</p>
                </div>
              </div>

              <!-- (ii-a) cancelar antes do aceite -->
              <div class="flex flex-col gap-2">
                <p class="op-micro text-muted">2. Cancelar antes do aceite: um toque arma, o segundo confirma</p>
                <NuxtCard>
                  <div class="flex flex-col gap-3">
                    <div class="flex items-center gap-2">
                      <span class="grid size-8 place-items-center rounded-lg op-label font-bold" :style="{ background: ride.bg, color: ride.fg }">{{ rideL }}</span>
                      <h3 class="op-title text-highlighted">Corrida {{ rideL }} · Procurando entregador</h3>
                    </div>
                    <p class="op-body text-toned">A05 e C12 · chamada às 14:12</p>
                    <NuxtAlert
                      color="error"
                      variant="subtle"
                      icon="i-lucide-ban"
                      :title="`Cancelar a corrida ${rideL}? A05 e C12 voltam para Aguardando.`"
                    >
                      <template #actions>
                        <NuxtButton color="error" variant="solid" :label="`Cancelar a corrida ${rideL}`" />
                        <NuxtButton color="error" variant="outline" label="Manter a corrida" />
                      </template>
                    </NuxtAlert>
                  </div>
                </NuxtCard>
              </div>

              <!-- (ii-b) cancelar depois do aceite -->
              <div class="flex flex-col gap-2">
                <p class="op-micro text-muted">3. Cancelar depois do aceite: o motivo é o próprio botão</p>
                <NuxtCard>
                  <div class="flex flex-col gap-3">
                    <div class="flex items-center gap-2">
                      <span class="grid size-8 place-items-center rounded-lg op-label font-bold" :style="{ background: ride.bg, color: ride.fg }">{{ rideL }}</span>
                      <h3 class="op-title text-highlighted">Corrida {{ rideL }} · Diego vem buscar</h3>
                    </div>
                    <p class="op-body text-toned">Aceitou às 14:14 · chega em 6 min</p>
                    <NuxtAlert
                      color="error"
                      variant="subtle"
                      icon="i-lucide-ban"
                      :title="`Por que cancelar a corrida ${rideL}?`"
                      description="A05 e C12 voltam para Aguardando."
                    />
                    <div class="flex flex-col gap-2">
                      <NuxtButton block color="error" variant="outline" icon="i-lucide-user-x" label="O entregador não está vindo" />
                      <NuxtButton block color="error" variant="outline" icon="i-lucide-timer-off" label="Está demorando demais" />
                      <NuxtButton block color="error" variant="outline" icon="i-lucide-phone-off" label="Não consegui falar com o entregador" />
                      <NuxtSeparator />
                      <NuxtButton block color="neutral" variant="ghost" label="Manter a corrida" />
                    </div>
                  </div>
                </NuxtCard>
              </div>
            </div>
          </section>

          <NuxtSeparator />

          <!-- ========== A CONTRA B ========== -->
          <section class="grid grid-cols-2 gap-6">
            <!-- coluna A -->
            <div class="flex flex-col gap-4">
              <div class="flex flex-col gap-0.5">
                <h2 class="flex items-center gap-2 text-xl font-semibold text-highlighted">
                  <span class="grid size-8 place-items-center rounded-lg bg-inverted text-inverted">A</span>
                  "Entregue" ao cliente só depois da volta
                </h2>
                <p class="op-body text-toned">Na corrida com retorno, o fim da corrida não avisa o cliente; o balcão confirma pedido por pedido quando o Diego volta.</p>
              </div>

              <div class="flex flex-col gap-2">
                <p class="op-micro text-muted">O que o cliente do A05 recebe</p>
                <NuxtCard>
                  <ol class="flex flex-col gap-2 op-body">
                    <li class="flex gap-2"><span class="w-12 tabular-nums text-muted">14:22</span>Seu pedido saiu para entrega.</li>
                    <li class="flex gap-2"><span class="w-12 tabular-nums text-muted">14:41</span><span class="text-muted">Fim da corrida na TaOn: nada é enviado.</span></li>
                    <li class="flex gap-2"><span class="w-12 tabular-nums text-muted">14:58</span>Não conseguimos entregar seu pedido. Podemos combinar uma nova entrega?</li>
                  </ol>
                </NuxtCard>
              </div>

              <div class="flex flex-col gap-2">
                <p class="op-micro text-muted">Entregador voltou: A05 voltou com a sacola</p>
                <NuxtCard>
                  <div class="flex flex-col gap-3">
                    <div>
                      <h3 class="op-title text-highlighted">Entregador voltou</h3>
                      <p class="op-body text-toned">Corrida {{ rideL }} · Diego. Marque o que foi entregue.</p>
                    </div>
                    <div class="flex flex-col gap-2 rounded-lg border border-default p-3">
                      <div class="flex items-center justify-between">
                        <span class="op-body"><strong class="tabular-nums">C12</strong> · Centro</span>
                        <NuxtCheckbox v-model="deliveredA.C12" label="Entregue" />
                      </div>
                      <p class="op-micro text-muted">Volta com R$ 50,00: R$ 30,00 da conta e os R$ 20,00 do troco que saíram da gaveta.</p>
                    </div>
                    <div class="flex flex-col gap-2 rounded-lg border border-warning p-3">
                      <div class="flex items-center justify-between">
                        <span class="op-body"><strong class="tabular-nums">A05</strong> · Gleba Palhano</span>
                        <NuxtCheckbox v-model="deliveredA.A05" label="Entregue" />
                      </div>
                      <NuxtBadge color="warning" icon="i-lucide-package-x" label="Voltou com a sacola" class="self-start" />
                      <p class="op-micro text-muted">Volta a maquininha Azul, sem venda. Ninguém atendeu na portaria.</p>
                      <div class="grid grid-cols-2 gap-2">
                        <NuxtButton block color="primary" icon="i-lucide-repeat" label="Entregar de novo" />
                        <NuxtButton block color="error" variant="outline" icon="i-lucide-undo-2" label="Devolver e estornar" />
                      </div>
                    </div>
                    <NuxtButton block color="primary" label="Conferido: C12 entregue, A05 voltou" />
                  </div>
                </NuxtCard>
              </div>

              <NuxtAlert
                color="info"
                variant="subtle"
                icon="i-lucide-info"
                title="O que A custa"
                description="O cliente de C12 só recebe 'Entregue' quando o Diego volta, uns 15 minutos depois de receber a sacola. Se o balcão esquecer de conferir, o aviso não sai."
              />
            </div>

            <!-- coluna B -->
            <div class="flex flex-col gap-4">
              <div class="flex flex-col gap-0.5">
                <h2 class="flex items-center gap-2 text-xl font-semibold text-highlighted">
                  <span class="grid size-8 place-items-center rounded-lg bg-inverted text-inverted">B</span>
                  "Entregue" no fim da corrida, como hoje
                </h2>
                <p class="op-body text-toned">O fim da corrida na TaOn avisa o cliente na hora; na volta, o balcão só desfaz o que não foi entregue.</p>
              </div>

              <div class="flex flex-col gap-2">
                <p class="op-micro text-muted">O que o cliente do A05 recebe</p>
                <NuxtCard>
                  <ol class="flex flex-col gap-2 op-body">
                    <li class="flex gap-2"><span class="w-12 tabular-nums text-muted">14:22</span>Seu pedido saiu para entrega.</li>
                    <li class="flex gap-2"><span class="w-12 tabular-nums text-muted">14:41</span><span>Seu pedido foi entregue. <NuxtBadge color="error" label="Não foi" /></span></li>
                    <li class="flex gap-2"><span class="w-12 tabular-nums text-muted">14:58</span>Não conseguimos entregar seu pedido. Podemos combinar uma nova entrega?</li>
                  </ol>
                </NuxtCard>
              </div>

              <div class="flex flex-col gap-2">
                <p class="op-micro text-muted">Entregador voltou: A05 voltou com a sacola</p>
                <NuxtCard>
                  <div class="flex flex-col gap-3">
                    <div>
                      <h3 class="op-title text-highlighted">Entregador voltou</h3>
                      <p class="op-body text-toned">Corrida {{ rideL }} · Diego. A TaOn já deu os dois como entregues.</p>
                    </div>
                    <div class="flex flex-col gap-2 rounded-lg border border-default p-3">
                      <div class="flex items-center justify-between">
                        <span class="op-body"><strong class="tabular-nums">C12</strong> · Centro</span>
                        <NuxtCheckbox v-model="deliveredB.C12" label="Entregue" />
                      </div>
                      <p class="op-micro text-muted">Volta com R$ 50,00: R$ 30,00 da conta e os R$ 20,00 do troco que saíram da gaveta.</p>
                    </div>
                    <div class="flex flex-col gap-2 rounded-lg border border-error p-3">
                      <div class="flex items-center justify-between">
                        <span class="op-body"><strong class="tabular-nums">A05</strong> · Gleba Palhano</span>
                        <NuxtCheckbox v-model="deliveredB.A05" label="Entregue" />
                      </div>
                      <NuxtAlert
                        color="error"
                        variant="subtle"
                        icon="i-lucide-message-square-warning"
                        title="O cliente já recebeu 'Entregue' às 14:41."
                        description="A nota e o estoque já fecharam como entregue. Escolher abaixo desfaz e avisa o cliente de novo."
                      />
                      <div class="grid grid-cols-2 gap-2">
                        <NuxtButton block color="primary" icon="i-lucide-repeat" label="Entregar de novo" />
                        <NuxtButton block color="error" variant="outline" icon="i-lucide-undo-2" label="Devolver e estornar" />
                      </div>
                    </div>
                    <NuxtButton block color="primary" label="Conferido: C12 entregue, A05 voltou" />
                  </div>
                </NuxtCard>
              </div>

              <NuxtAlert
                color="info"
                variant="subtle"
                icon="i-lucide-info"
                title="O que B custa"
                description="Quando a entrega falha na porta, o cliente lê 'Entregue' antes de ler que não foi. Se o F só chega na volta à loja (como diz o plano), B também avisa depois da volta, mas sem a conferência do balcão."
              />
            </div>
          </section>
        </div>
      </div>
    </Teleport>
  </div>
</template>
