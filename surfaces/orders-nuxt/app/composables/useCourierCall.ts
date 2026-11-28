// Chamar o entregador: a orquestração das corridas em edição e do sheet de chamar
// (`CourierCallSheet`), a MESMA nas três telas que chamam (#2876):
//  · a página Entregas (`/delivery`), que monta as corridas no mapa e na coluna;
//  · o cartão Pronto do Painel e o detalhe do pedido, que abrem o sheet para UM pedido
//    (`openOrder`), com quem a casa sugere levar junto já marcado (decisão 1 = A).
//
// A fonte é a projeção das Entregas (`DeliveriesProjection`): as paradas com troco,
// maquininha e coordenada, as letras livres, as maquininhas livres e o plano da casa.
// Nada é gravado até "Chamar": a chamada vai pelo protocolo de intenção (`courier-ride`
// para várias paradas, `courier-dispatch` para uma, a rota da casa para quem é da casa).
import { computed, nextTick, ref, watch, type Ref } from "vue";
import type { DeliveriesProjection, DeliveryStopProjection } from "~/generated/ordersContract";
import type { CallSheetCompanions, CallSheetMap, CallSheetRide } from "~/components/CourierCallSheet.vue";
import { rideColor } from "~/presentation/ridePalette";
import {
  assignMachines,
  changeValue,
  failureStops,
  machineShortfall,
  nextFreeNumber,
  quoteLines,
  rideCalls,
  rideFailureTitle,
  rideLetter,
  ridesNeedingMachine,
  routeOrder,
  suggestionLate,
  suggestionQuoteLines,
  suggestionsHeadline,
  type EditingRide,
  type RideFailure,
  type RideSuggestion,
} from "~/presentation/deliveries";
import {
  DEFAULT_CARRIER,
  HOUSE_RIDE_PATH,
  busyNotice,
  callSummaryByCarrier,
  carrierChips,
  chipValue,
  choiceFromChip,
  chosenCarrier,
  houseQuoteLines,
  houseRideAction,
  houseRideInputs,
  houseRideResource,
  mixedTotalLines,
  noteLabel,
  otherCouriers,
  rideValueQ,
  sendLabel,
  shiftChips,
  type HouseRideResult,
} from "~/presentation/houseCouriers";
import {
  companionChoices,
  companionNote,
  drawerLine,
  initialRide,
  orderCallDescription,
  orderCallLabel,
  orderCallTitle,
  planServiceName,
  suggestionFor,
} from "~/presentation/courierCall";

/** Sem a TaOn e sem ninguém da casa na escala, não há quem leve (M3c, #2899). */
export const NOBODY_TAKES = "Ponha um entregador da casa na escala de hoje para chamar.";

export interface CourierCallOptions {
  data: Ref<DeliveriesProjection | null | undefined>;
  /** Relê a projeção das Entregas (depois de chamar). */
  refresh: () => Promise<unknown>;
  /** As corridas em edição: a página Entregas mostra todas; o Painel, só a do sheet. */
  editing?: Ref<EditingRide[]>;
  /** A corrida ativa da página Entregas (o mapa e a coluna); no Painel, a do sheet. */
  active?: Ref<number>;
  /** Depois de uma chamada que abriu corrida: o Painel e o detalhe releem o que mostram. */
  onCalled?: (refs: string[]) => unknown;
}

export function useCourierCall(options: CourierCallOptions) {
  const { data, refresh } = options;
  const intentions = useOrderIntention();
  const editing = options.editing ?? ref<EditingRide[]>([]);
  const active = options.active ?? ref(0);

  const waitingAll = computed(() => data.value?.waiting ?? []);
  const maxStops = computed(() => data.value?.max_stops ?? 4);
  const byRef = computed(() => new Map(waitingAll.value.map((stop) => [stop.ref, stop])));
  const origin = computed(() => data.value?.origin ?? null);
  // Os números livres vêm do servidor (`free_numbers`: as corridas na rua já
  // descontadas, até 26 letras); a tela só desconta as que ela mesma está editando.
  const freeNumbers = computed(() => data.value?.free_numbers ?? []);
  const ready = computed(() => editing.value.filter((ride) => ride.refs.length));
  const editingCount = computed(() => ready.value.reduce((sum, ride) => sum + ride.refs.length, 0));
  const planSuggestions = computed(() => (data.value?.ride_plan?.suggestions ?? []) as RideSuggestion[]);
  // O serviço que leva a corrida a chamar, como o cadastro diz: as frases o usam (#3139).
  const planService = computed(() => planServiceName(data.value?.ride_plan));

  watch(freeNumbers, (free) => {
    // Uma corrida chamada enquanto se editava (em outro dispositivo) pode ter pego o
    // número (e com ele a letra): a editada troca para um livre.
    for (const ride of editing.value) {
      if (free.includes(ride.number)) continue;
      const next = nextFreeNumber(free, editing.value.filter((r) => r !== ride).map((r) => r.number));
      if (!next) continue;
      if (active.value === ride.number) active.value = next;
      sheetNumbers.value = sheetNumbers.value.map((number) => (number === ride.number ? next : number));
      ride.number = next;
    }
  });
  // O que sumiu da lista (chamado em outro lugar, cancelado) sai da edição.
  watch(waitingAll, (list) => {
    const alive = new Set(list.map((stop) => stop.ref));
    for (const ride of editing.value) ride.refs = ride.refs.filter((ref) => alive.has(ref));
  });

  // ── cotação e ordem de cada corrida (P1-10, J03) ───────────────────────────
  const quotes = useEditingQuotes(editing);
  const stopsOf = (ride: EditingRide) =>
    ride.refs.map((ref) => byRef.value.get(ref)).filter((stop): stop is DeliveryStopProjection => Boolean(stop));
  // A ordem que o entregador segue: a da cotação (o servidor já ordenou a rota),
  // senão o espelho do `courier._route` aqui na tela. Nunca a ordem dos toques.
  function routeOf(ride: EditingRide): DeliveryStopProjection[] {
    const stops = stopsOf(ride);
    const quoted = quotes.value[ride.number]?.quote?.stops;
    if (quoted && quoted.length === stops.length && stops.every((stop) => quoted.includes(stop.ref)))
      return quoted.map((ref) => stops.find((stop) => stop.ref === ref)!);
    return routeOrder(origin.value, stops);
  }
  const linesOf = (ride: EditingRide) => {
    const who = carrierOf(ride.number);
    if (who) {
      // Quem é da casa: uma linha só, o valor da tabela (a TaOn não cota esta corrida).
      const value = houseValues.value[ride.number]?.[who.ref];
      return value === undefined ? [] : houseQuoteLines(value);
    }
    const state = quotes.value[ride.number];
    return quoteLines(state?.quote ?? null, ride.refs.length, state?.failure ?? "");
  };

  // ── quem leva (M3, #2526) ──────────────────────────────────────────────────
  // O padrão do Admin vem marcado; quem da casa está na escala aparece como opção. A
  // escolha é por corrida, só da tela, e vale até chamar.
  const crewRides = computed(() => ready.value.map((ride) => ({ number: ride.number, refs: routeOf(ride).map((stop) => stop.ref) })));
  const { crew, values: houseValues, valuesQ: houseValuesQ, refresh: refreshCrew, toggleShift, toggling } = useHouseCrew(crewRides);
  watch(data, () => void refreshCrew());
  const carrier = ref<Record<number, string>>({});
  // Sem a TaOn (M3c, #2899), quem leva é sempre da casa: vem marcado o primeiro livre.
  const serviceOn = computed(() => data.value?.courier_on ?? true);
  const carrierOf = (number: number) => chosenCarrier(crew.value, carrier.value[number], serviceOn.value);
  function chooseCarrier(number: number, key: string) {
    carrier.value = { ...carrier.value, [number]: choiceFromChip(crew.value, key) };
  }
  // A observação para o entregador da casa, por corrida (vai à página do link).
  const notes = ref<Record<number, string>>({});
  function setNote(number: number, value: string) {
    notes.value = { ...notes.value, [number]: value };
  }
  // O "Outro da casa": a lista de quem não ganhou chip, com o estado e o valor desta rota.
  const othersOf = (ride: EditingRide) =>
    otherCouriers(crew.value).map((courier) => ({
      value: courier.ref,
      label: [courier.name, courier.state_label, houseValues.value[ride.number]?.[courier.ref] ?? courier.value].filter(Boolean).join(" · "),
    }));
  // A corrida que saiu da edição (Voltar, desfazer, chamada) leva a escolha junto: a
  // próxima com a mesma letra nasce com o padrão marcado.
  watch(
    () => editing.value.map((ride) => ride.number).join("|"),
    () => {
      const alive = new Set(editing.value.map((ride) => ride.number));
      carrier.value = Object.fromEntries(Object.entries(carrier.value).filter(([number]) => alive.has(Number(number))));
      notes.value = Object.fromEntries(Object.entries(notes.value).filter(([number]) => alive.has(Number(number))));
    },
  );
  const chipsOf = (ride: EditingRide) => {
    const state = quotes.value[ride.number];
    return carrierChips(crew.value, {
      quoteQ: state?.quote?.value_q ?? null,
      quoting: Boolean(state?.pending),
      values: houseValues.value[ride.number],
      chosen: carrierOf(ride.number)?.ref ?? DEFAULT_CARRIER,
      serviceOn: serviceOn.value,
    });
  };
  const shift = computed(() => shiftChips(crew.value));
  // O valor de cada corrida pelo serviço que a leva: a casa pela tabela, a TaOn pela
  // cotação (a viva; no sheet, a do plano enquanto a viva não chega).
  function valueOf(ride: EditingRide, planQ: number | null = null): number | null {
    const who = carrierOf(ride.number);
    const live = quotes.value[ride.number]?.quote?.value_q;
    return rideValueQ({
      house: Boolean(who),
      houseValueQ: who ? houseValuesQ.value[ride.number]?.[who.ref] : null,
      quoteQ: typeof live === "number" ? live : planQ,
    });
  }

  // ── maquininha de cada corrida (P1-12) ──────────────────────────────────────
  const machines = computed(() => data.value?.machines ?? []);
  const freeMachineRefs = computed(() => machines.value.map((m) => String(m.ref)));
  const machineItems = computed(() => machines.value.map((m) => ({ label: String(m.label), value: String(m.ref) })));
  const needing = computed(() => ridesNeedingMachine(ready.value, waitingAll.value));
  const machineChoice = ref<Record<number, string>>({});
  const assigned = computed(() => assignMachines(needing.value, freeMachineRefs.value, machineChoice.value));
  const shortfall = computed(() => machineShortfall(needing.value.length, freeMachineRefs.value.length));
  function chooseMachine(number: number, value: string) {
    machineChoice.value = { ...assigned.value, [number]: value };
  }

  // ── troco conferido ─────────────────────────────────────────────────────────
  // O que o operador digitou, por pedido; sem mexer, vale o sugerido.
  const change = ref<Record<string, string>>({});
  const changeOf = (stop: DeliveryStopProjection) => changeValue(stop, change.value);
  function setChange(ref: string, value: string | number) {
    change.value = { ...change.value, [ref]: String(value ?? "") };
  }

  // ── chamar, com balanço por corrida ─────────────────────────────────────────
  const sending = ref(false);
  // A chamada que parou tudo (sem rede, servidor fora): as que faltavam ficam para chamar.
  const failure = ref("");
  // Um aviso por corrida que não abriu, preso ao cartão dela (J08, J14).
  const failures = ref<Record<number, RideFailure>>({});
  watch(
    editing,
    (list) => {
      // A corrida mudou de pedidos (ou saiu): o aviso de antes já não é dela.
      const next: Record<number, RideFailure> = {};
      for (const ride of list) {
        const old = failures.value[ride.number];
        if (old && old.refs.join("|") === ride.refs.join("|")) next[ride.number] = old;
      }
      failures.value = next;
    },
    { deep: true },
  );
  function dismissFailure(number: number) {
    const { [number]: _gone, ...rest } = failures.value;
    failures.value = rest;
  }
  const callLabel = computed(() => {
    if (ready.value.length !== 1) return `Chamar ${ready.value.length} corridas`;
    const ride = ready.value[0]!;
    const who = carrierOf(ride.number);
    return who ? sendLabel(who.name, routeOf(ride).map((stop) => stop.code)) : `Chamar a corrida ${rideLetter(ride.number)}`;
  });
  const machineMissing = computed(() => needing.value.some((number) => !assigned.value[number]));
  const nobodyTakes = computed(() => !serviceOn.value && ready.value.some((ride) => !carrierOf(ride.number)));
  const canCall = computed(() => ready.value.length > 0 && !sending.value && !machineMissing.value && !nobodyTakes.value);
  // O total segue quem leva cada corrida (a casa pela tabela, a TaOn pela cotação).
  const summary = computed(() =>
    callSummaryByCarrier(editingCount.value, ready.value.length, ready.value.map((ride) => valueOf(ride))),
  );

  async function call(only?: number[]) {
    sending.value = true;
    failure.value = "";
    const targets = only ? ready.value.filter((ride) => only.includes(ride.number)) : ready.value;
    const calls = rideCalls(targets, waitingAll.value, assigned.value, change.value);
    // As corridas da casa abrem o WhatsApp do dispositivo. A aba nasce AGORA, no toque,
    // antes de qualquer espera: aberta depois da resposta, o navegador a bloquearia.
    const tabs: Record<number, Window | null> = {};
    for (const item of calls) {
      if (!carrierOf(item.number)) continue;
      const tab = window.open("", "_blank");
      if (tab) tab.opener = null;
      tabs[item.number] = tab;
    }
    let sentDetail = "";
    const called: string[] = [];
    let opened = 0;
    // A corrida que já existia com os mesmos pedidos (chamada em outro dispositivo):
    // o servidor diz, e a frase é a dele.
    let already = "";
    for (const item of calls) {
      try {
        const who = carrierOf(item.number);
        if (who) {
          // A casa: a corrida vai para a pessoa escolhida, na ordem da rota, e o link
          // segue pelo WhatsApp do dispositivo (a aba aberta no toque).
          const ride = editing.value.find((entry) => entry.number === item.number);
          const ordered = ride ? routeOf(ride).filter((stop) => item.refs.includes(stop.ref)) : [];
          const refs = ordered.length === item.refs.length ? ordered.map((stop) => stop.ref) : item.refs;
          const stops = refs.map((ref) => byRef.value.get(ref)).filter((stop): stop is DeliveryStopProjection => Boolean(stop));
          const result = (await intentions.executePath(
            houseRideResource(refs),
            HOUSE_RIDE_PATH,
            houseRideAction(stops),
            houseRideInputs({ refs, courier: who.ref, change_out: item.change_out, machine: item.machine, number: item.number, note: notes.value[item.number] ?? "" }),
            undefined,
            { subject: "a corrida foi enviada", where: "os pedidos" },
          )) as unknown as HouseRideResult;
          const tab = tabs[item.number];
          Reflect.deleteProperty(tabs, item.number);
          if (result.whatsapp_url) {
            if (tab) tab.location.href = result.whatsapp_url;
            else window.open(result.whatsapp_url, "_blank", "noopener");
          } else tab?.close();
          sentDetail = result.detail ?? "";
        } else if (item.kind === "group") {
          // Pelo protocolo de intenção, como a chamada de um pedido só: quem a tela
          // leu, a revisão de cada pedido e uma chave por corrida, guardada até a
          // resposta definitiva (`group_action` da projeção).
          const result = await intentions.executeRide(data.value?.group_action, {
            refs: item.refs,
            change_out: item.change_out,
            machine: item.machine,
            ride_number: item.number,
          });
          if (result.already_called && result.detail) already = result.detail;
        } else {
          const ref = item.refs[0]!;
          await intentions.execute(ref, "courier-dispatch", byRef.value.get(ref)?.dispatch_action ?? undefined, {
            ...(item.change_out[ref] ? { change_out: item.change_out[ref] } : {}),
            ...(item.machine ? { equipment: [item.machine] } : {}),
            ride_number: item.number,
          });
        }
        called.push(...item.refs);
        opened += 1;
      } catch (err) {
        const codes = item.refs.map((ref) => byRef.value.get(ref)?.code ?? ref);
        const detail = httpErrorMessage(err, "A chamada não chegou. Confira a internet deste dispositivo.");
        failures.value = {
          ...failures.value,
          [item.number]: { number: item.number, refs: item.refs, title: rideFailureTitle(item.number, codes), detail },
        };
        // Recusa do servidor é desta corrida: as outras seguem. Sem rede (ou servidor
        // fora), a próxima falharia igual: para, e as que faltavam ficam na edição.
        if (failureStops(httpError(err).status)) {
          const left = calls.length - opened - 1;
          failure.value = left > 0 ? `Parou na corrida ${rideLetter(item.number)}. ${left === 1 ? "A outra ficou" : `As outras ${left} ficaram`} para chamar.` : "";
          break;
        }
      }
    }
    // A aba que ficou sem corrida (a chamada falhou antes) fecha: nada abre à toa.
    for (const tab of Object.values(tabs)) tab?.close();
    if (opened)
      useSonner.success(
        opened === 1 && calls.length === 1
          ? sentDetail || already || `Corrida chamada. A ${planService.value} avisa quando alguém aceitar.`
          : `${opened} ${opened === 1 ? "corrida chamada" : "corridas chamadas"}.`,
      );
    const done = new Set(called);
    editing.value = editing.value.filter((ride) => !ride.refs.some((ref) => done.has(ref)));
    if (!editing.value.some((ride) => ride.number === active.value)) active.value = editing.value[0]?.number ?? 0;
    sending.value = false;
    await refresh();
    if (called.length) await options.onCalled?.(called);
    return called;
  }
  // "Chamar separadas": a corrida que não abriu vira uma corrida por pedido, com o
  // mesmo troco e as maquininhas redistribuídas, e só elas são chamadas.
  function callSeparately(number: number) {
    const ride = editing.value.find((item) => item.number === number);
    if (!ride || ride.refs.length < 2) return;
    const taken = editing.value.filter((item) => item !== ride).map((item) => item.number);
    const numbers: number[] = [];
    for (const _ of ride.refs) {
      const next = nextFreeNumber(freeNumbers.value, [...taken, ...numbers]) ?? (numbers.length ? null : number);
      if (next === null) {
        useSonner.info("Não há letras livres para separar agora. Chame de novo juntas.");
        return;
      }
      numbers.push(next);
    }
    const singles = ride.refs.map((ref, k) => ({ number: numbers[k]!, refs: [ref] }));
    editing.value = [...editing.value.filter((item) => item !== ride), ...singles];
    dismissFailure(number);
    void nextTick(() => call(numbers));
  }

  // ── o sheet de chamar ──────────────────────────────────────────────────────
  // As corridas que esperam a confirmação no sheet (vieram de sugestões, ou do pedido).
  const sheetNumbers = ref<number[]>([]);
  // Aberto por UM pedido (Painel, detalhe): o pedido, e quem pode ir junto dele.
  const anchor = ref("");
  const suggestionOf = (refs: readonly string[]) =>
    planSuggestions.value.find((item) => item.refs.join("|") === refs.join("|"));

  function openSheet(numbers: number[]) {
    anchor.value = "";
    sheetNumbers.value = numbers;
  }
  /**
   * Abre o sheet para um pedido: ele e, quando a casa sugere juntar (cotada e mais
   * barata), quem vai com ele, já marcado. Devolve a frase do que impediu, ou "".
   */
  function openOrder(ref: string): string {
    const stop = byRef.value.get(ref);
    if (!stop) return "Este pedido não está mais esperando entregador. Atualize a tela.";
    if (stop.dispatch_again_action) return stop.error || "A última chamada deste pedido ficou sem resposta.";
    const taken = editing.value.filter((ride) => !sheetNumbers.value.includes(ride.number));
    const number = nextFreeNumber(freeNumbers.value, taken.map((ride) => ride.number));
    if (number === null) return "Não há letras livres agora. Espere uma corrida fechar.";
    const busy = new Set(taken.flatMap((ride) => ride.refs));
    if (busy.has(ref)) return "Este pedido já está numa corrida em edição nas Entregas.";
    const refs = initialRide(ref, suggestionFor(ref, planSuggestions.value), maxStops.value, busy);
    editing.value = [...taken, { number, refs }];
    active.value = number;
    sheetNumbers.value = [number];
    anchor.value = ref;
    return "";
  }
  const sheetRide = computed(() => (anchor.value ? editing.value.find((ride) => ride.number === sheetNumbers.value[0]) : undefined));
  // O pedido saiu da corrida (chamado em outro dispositivo, cancelado): o sheet fecha.
  watch(
    () => sheetRide.value?.refs.includes(anchor.value),
    (inside) => {
      if (anchor.value && sheetNumbers.value.length && !inside) closeSheet();
    },
  );
  function toggleCompanion(ref: string) {
    const ride = sheetRide.value;
    if (!ride) return;
    if (ride.refs.includes(ref)) ride.refs = ride.refs.filter((item) => item !== ref);
    else if (ride.refs.length < maxStops.value) ride.refs = [...ride.refs, ref];
  }
  // "Voltar": as corridas do sheet saem da edição; as que o operador já montava ficam.
  function closeSheet() {
    const numbers = sheetNumbers.value;
    sheetNumbers.value = [];
    anchor.value = "";
    editing.value = editing.value.filter((ride) => !numbers.includes(ride.number));
    if (!editing.value.some((ride) => ride.number === active.value)) active.value = editing.value[0]?.number ?? 0;
  }
  async function confirmSheet() {
    const numbers = sheetNumbers.value;
    sheetNumbers.value = [];
    anchor.value = "";
    const called = await call(numbers);
    // O que não abriu fica na edição da página Entregas; no Painel, sem a coluna, sai.
    if (!options.editing) editing.value = editing.value.filter((ride) => !numbers.includes(ride.number));
    return called;
  }
  // "Chamar só A47": o companheiro sai e a corrida é só do pedido.
  async function confirmAlone() {
    const ride = sheetRide.value;
    if (!ride || !anchor.value) return [];
    ride.refs = [anchor.value];
    await nextTick();
    return confirmSheet();
  }

  const sheetRides = computed<CallSheetRide[]>(() =>
    sheetNumbers.value
      .map((number) => editing.value.find((ride) => ride.number === number))
      .filter((ride): ride is EditingRide => Boolean(ride))
      .map((ride) => {
        const stops = routeOf(ride);
        const plan = suggestionOf(ride.refs) ?? suggestionOf(stops.map((stop) => stop.ref));
        const live = linesOf(ride);
        const who = carrierOf(ride.number);
        // Aberto por um pedido, a cotação da sugestão já mora sob o companheiro: com a
        // corrida igual à sugestão, a do cartão não se repete.
        const repeats = Boolean(anchor.value && plan && !who);
        return {
          number: ride.number,
          letter: rideLetter(ride.number),
          color: rideColor(ride.number - 1),
          stops: stops.map((stop) => ({
            ref: stop.ref, code: stop.code, customer: stop.customer, place: stop.place,
            change_out_suggested_q: stop.change_out_suggested_q, change: changeOf(stop),
          })),
          // A cotação viva da corrida (a mesma que a chamada vai abrir); enquanto ela
          // não chega, a do plano.
          lines: repeats ? [] : live.length || who ? live : plan ? suggestionQuoteLines(plan as RideSuggestion) : [],
          carriers: chipsOf(ride),
          carrier: chipValue(crew.value, who?.ref ?? DEFAULT_CARRIER),
          others: othersOf(ride),
          otherValue: who?.ref ?? "",
          noteLabel: who ? noteLabel(who.name) : "",
          note: notes.value[ride.number] ?? "",
          notice: busyNotice(who),
          late: plan && !repeats ? suggestionLate(plan) : "",
          needsMachine: needing.value.includes(ride.number),
          machine: assigned.value[ride.number] ?? "",
        };
      }),
  );
  const anchorStop = computed(() => (anchor.value ? byRef.value.get(anchor.value) : undefined));
  const sheetTitle = computed(() => {
    if (anchorStop.value) return orderCallTitle(anchorStop.value.code);
    return sheetRides.value.length === 1 ? `Chamar a corrida ${sheetRides.value[0]!.letter}` : `Chamar ${sheetRides.value.length} corridas`;
  });
  const sheetDescription = computed(() => (anchorStop.value ? orderCallDescription(anchorStop.value) : ""));
  const sheetLines = computed(() => {
    if (anchor.value) return [];
    const list = sheetRides.value
      .map((ride) => suggestionOf(editing.value.find((item) => item.number === ride.number)?.refs ?? []))
      .filter(Boolean) as RideSuggestion[];
    // O juntas×separadas compara cotações da TaOn: com alguma corrida da casa, o total
    // vira a soma por quem leva cada uma (com uma corrida só, a linha dela já diz tudo).
    if (sheetRides.value.some((ride) => ride.carrier !== DEFAULT_CARRIER)) {
      if (sheetRides.value.length < 2) return [];
      return mixedTotalLines(
        sheetRides.value.map((ride) => {
          const editingRide = editing.value.find((item) => item.number === ride.number);
          const plan = editingRide ? suggestionOf(editingRide.refs) : undefined;
          return editingRide ? valueOf(editingRide, (plan as RideSuggestion | undefined)?.together_q ?? null) : null;
        }),
      );
    }
    return list.length === sheetRides.value.length ? suggestionsHeadline(list).lines : [];
  });
  // "Vai junto nesta corrida?": só no sheet aberto por um pedido.
  const sheetCompanions = computed<CallSheetCompanions | null>(() => {
    const stop = anchorStop.value;
    const ride = sheetRide.value;
    if (!stop || !ride) return null;
    const plan = suggestionFor(stop.ref, planSuggestions.value);
    const taken = new Set(editing.value.filter((item) => item !== ride).flatMap((item) => item.refs));
    const choices = companionChoices(stop, waitingAll.value, ride.refs, { plan, maxStops: maxStops.value, taken });
    if (!choices.length) return null;
    return {
      choices,
      lines: plan ? suggestionQuoteLines(plan) : [],
      late: plan ? suggestionLate(plan) : "",
      note: companionNote(plan, choices, planService.value),
    };
  });
  const sheetMap = computed<CallSheetMap | null>(() => {
    const located = (stop: DeliveryStopProjection): stop is DeliveryStopProjection & { latitude: number; longitude: number } =>
      stop.latitude !== null && stop.longitude !== null;
    const building = sheetNumbers.value
      .map((number) => editing.value.find((ride) => ride.number === number))
      .filter((ride): ride is EditingRide => Boolean(ride))
      .map((ride) => ({ number: ride.number, stops: routeOf(ride).filter(located) }));
    const inRide = new Set(sheetRide.value?.refs ?? []);
    const waiting = (sheetCompanions.value?.choices ?? [])
      .filter((choice) => !inRide.has(choice.ref))
      .map((choice) => byRef.value.get(choice.ref))
      .filter((stop): stop is DeliveryStopProjection & { latitude: number; longitude: number } => Boolean(stop && located(stop)))
      .map((stop) => ({ ...stop, preparing: stop.stage !== "Pronto" }));
    if (!building.some((ride) => ride.stops.length) && !waiting.length) return null;
    return { origin: origin.value, building, waiting, active: sheetNumbers.value[0] ?? 0, mapsKey: data.value?.maps_key ?? "" };
  });
  const sheetDrawer = computed(() => drawerLine(sheetRides.value.flatMap((ride) => ride.stops.map((stop) => stop.change))));
  const sheetMachineMissing = computed(() => sheetRides.value.some((ride) => ride.needsMachine && !ride.machine));
  const sheetNobodyTakes = computed(() => !serviceOn.value && sheetRides.value.some((ride) => !carrierOf(ride.number)));
  const sheetCallLabel = computed(() => {
    const ride = sheetRides.value[0];
    if (sheetRides.value.length !== 1 || !ride) return `Chamar as ${sheetRides.value.length} corridas`;
    const who = carrierOf(ride.number);
    if (who) return sendLabel(who.name, ride.stops.map((stop) => stop.code));
    if (anchorStop.value) {
      // O pedido primeiro, os companheiros depois: como o operador o chamou.
      const codes = [anchorStop.value.code, ...ride.stops.map((stop) => stop.code).filter((code) => code !== anchorStop.value!.code)];
      return orderCallLabel(codes);
    }
    return `Chamar a corrida ${ride.letter}`;
  });
  // Com companheiro marcado, chamar só o pedido é um toque, ao lado do principal.
  const sheetAloneLabel = computed(() =>
    anchorStop.value && (sheetRide.value?.refs.length ?? 0) > 1 ? `Chamar só ${anchorStop.value.code}` : "",
  );
  const sheet = computed(() => ({
    open: sheetRides.value.length > 0,
    title: sheetTitle.value,
    description: sheetDescription.value,
    lines: sheetLines.value,
    rides: sheetRides.value,
    companions: sheetCompanions.value,
    map: sheetMap.value,
    drawer: sheetDrawer.value,
    machineItems: machineItems.value,
    callLabel: sheetCallLabel.value,
    aloneLabel: sheetAloneLabel.value,
    canCall: !sending.value && !sheetMachineMissing.value && !sheetNobodyTakes.value,
    reason: sheetNobodyTakes.value
      ? NOBODY_TAKES
      : sheetMachineMissing.value
        ? shortfall.value || "Escolha a maquininha de cada corrida."
        : "",
    busy: sending.value,
  }));

  return {
    editing,
    active,
    waitingAll,
    maxStops,
    byRef,
    freeNumbers,
    ready,
    editingCount,
    origin,
    quotes,
    routeOf,
    linesOf,
    crew,
    toggleShift,
    toggling,
    serviceOn,
    carrierOf,
    chooseCarrier,
    notes,
    setNote,
    othersOf,
    chipsOf,
    shift,
    machineItems,
    needing,
    assigned,
    shortfall,
    chooseMachine,
    changeOf,
    setChange,
    sending,
    failure,
    failures,
    dismissFailure,
    callLabel,
    machineMissing,
    nobodyTakes,
    canCall,
    summary,
    call,
    callSeparately,
    sheetNumbers,
    anchor,
    openSheet,
    openOrder,
    toggleCompanion,
    closeSheet,
    confirmSheet,
    confirmAlone,
    sheet,
  };
}

/**
 * O sheet de chamar aberto por UM pedido, fora da página Entregas: o cartão Pronto do
 * Painel e o detalhe do pedido (#2876). Lê a projeção das Entregas só no toque (o
 * Painel não paga o plano das corridas a cada push) e abre o MESMO sheet, com quem a
 * casa sugere levar junto já marcado. O gesto cai de 3 para 2: tocar e chamar.
 */
export function useOrderCourierCall(options: { onCalled?: (refs: string[]) => unknown } = {}) {
  const data = ref<DeliveriesProjection | null>(null);
  const calling = ref("");
  async function load() {
    data.value = await $fetch<DeliveriesProjection>("/api/v1/backstage/deliveries/");
  }
  const flow = useCourierCall({
    data,
    refresh: async () => {
      try {
        await load();
      } catch {
        // A leitura nova falhou: a próxima abertura lê de novo.
      }
    },
    onCalled: options.onCalled,
  });
  /** Abre o sheet para o pedido; a frase do que impediu vai para o aviso. */
  async function open(ref: string) {
    if (calling.value) return;
    calling.value = ref;
    try {
      await load();
      const problem = flow.openOrder(ref);
      if (problem) useSonner.info(problem);
    } catch (error) {
      useSonner.error(httpErrorMessage(error, "Não foi possível abrir a chamada. Confira a internet e tente de novo."));
    } finally {
      calling.value = "";
    }
  }
  return {
    calling,
    open,
    sheet: flow.sheet,
    closeSheet: flow.closeSheet,
    confirmSheet: flow.confirmSheet,
    confirmAlone: flow.confirmAlone,
    toggleCompanion: flow.toggleCompanion,
    setChange: flow.setChange,
    chooseMachine: flow.chooseMachine,
    chooseCarrier: flow.chooseCarrier,
    setNote: flow.setNote,
  };
}
