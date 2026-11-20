// Os entregadores da casa na página Entregas (M3, #2526): a escala de hoje (os chips
// "Entregadores de hoje") e, por corrida em edição, o valor da tabela de cada pessoa na
// escala para aqueles pedidos. Uma resposta velha (a corrida mudou de pedidos) nunca
// sobrescreve a nova; sem ninguém na escala, nada é perguntado por corrida.
import { onScopeDispose, ref, watch, type Ref } from "vue";
import {
  HOUSE_CREW_PATH,
  houseShiftPath,
  onShift,
  type HouseCrew,
} from "~/presentation/houseCouriers";

export function useHouseCrew(rides: Ref<readonly { number: number; refs: string[] }[]>, waitMs = 350) {
  const { data: crew, refresh } = useFetch<HouseCrew>(HOUSE_CREW_PATH, {
    key: "orders:house-crew",
    server: false,
  });
  /** `{numero da corrida: {ref do entregador: "R$ 15,00"}}`. */
  const values = ref<Record<number, Record<string, string>>>({});
  const asked = new Map<number, string>();
  const timers: Record<number, ReturnType<typeof setTimeout>> = {};

  watch(
    [rides, () => onShift(crew.value).map((courier) => courier.ref).join("|")],
    ([list, people]) => {
      const alive = new Set(list.map((ride) => ride.number));
      for (const key of Object.keys(values.value)) {
        if (!alive.has(Number(key))) {
          clearTimeout(timers[Number(key)]);
          asked.delete(Number(key));
          const { [Number(key)]: _gone, ...rest } = values.value;
          values.value = rest;
        }
      }
      if (!people) return;
      for (const ride of list) {
        const key = `${people}::${ride.refs.join("|")}`;
        if (!ride.refs.length || asked.get(ride.number) === key) continue;
        asked.set(ride.number, key);
        clearTimeout(timers[ride.number]);
        const number = ride.number;
        const refs = [...ride.refs];
        timers[number] = setTimeout(async () => {
          try {
            const answer = await $fetch<HouseCrew>(HOUSE_CREW_PATH, { query: { refs } });
            if (asked.get(number) !== key) return;
            values.value = {
              ...values.value,
              [number]: Object.fromEntries(answer.couriers.map((courier) => [courier.ref, courier.value])),
            };
          } catch {
            // Sem o valor, o chip mostra só o estado: chamar continua possível.
          }
        }, waitMs);
      }
    },
    { deep: true, immediate: true },
  );
  onScopeDispose(() => Object.values(timers).forEach((timer) => clearTimeout(timer)));

  const toggling = ref("");
  async function toggleShift(ref: string, on: boolean) {
    toggling.value = ref;
    try {
      crew.value = await $fetch<HouseCrew>(houseShiftPath(ref), { method: "POST", body: { on_shift: on } });
    } catch (error) {
      useSonner.error(httpErrorMessage(error, "Não foi possível mudar a escala agora. Tente de novo."));
    } finally {
      toggling.value = "";
    }
  }

  return { crew, values, refresh, toggleShift, toggling };
}
