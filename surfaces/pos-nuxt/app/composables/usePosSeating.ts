import { toast } from "vue-sonner";

import {
  type DraftSpot,
  changeList,
  changesSummary,
  defaultSeats,
  freeSpot,
  nextSpotName,
  savePayload,
  snap,
  spotSize,
  toDraft,
} from "~/presentation/seating";
import type { SeatingFixtureKind, SeatingFixtureProjection, SeatingResponse, SpotShape } from "~/types/seating";

const SEATING_KEY = "pos-seating";
const HISTORY_LIMIT = 50;

interface Snapshot { spots: DraftSpot[]; removed: DraftSpot[]; areas: string[]; fixtures: SeatingFixtureProjection[] }

/** Onde nasce cada elemento fixo, e o tamanho (v4: a vitrine é a faixa ao lado do balcão). */
const FIXTURE_DEFAULTS: Record<SeatingFixtureKind, { width: number; height: number }> = {
  showcase: { width: 40, height: 320 },
  entrance: { width: 120, height: 16 },
};

/**
 * PDV › Ajustes › Salão: a leitura da planta e o rascunho que a tela edita.
 *
 * O rascunho vive só aqui até o Salvar (um salvar só, com a revisão que foi lida):
 * mover, girar, trocar a forma e os lugares, criar e tirar mesas mexem nele, com
 * Desfazer e Refazer. Descartar volta ao que o servidor leu. Leitura client-side
 * (`server: false`): a permissão é do operador identificado na estação.
 */
export function usePosSeating() {
  const apiPath = useApiPath();
  const action = usePosAction();
  const { data, pending, error, refresh } = useFetch<SeatingResponse>(
    () => apiPath("/api/v1/backstage/pos/seating/"),
    { key: SEATING_KEY, credentials: "include", server: false, lazy: true },
  );

  const original = ref<DraftSpot[]>([]);
  const spots = ref<DraftSpot[]>([]);
  const removed = ref<DraftSpot[]>([]);
  /** Áreas criadas na tela que ainda não têm mesa. */
  const areas = ref<string[]>([]);
  // A vitrine e caixa e a entrada (desenho, sem lugar e sem B.I.): uma lista só,
  // gravada inteira no mesmo Salvar.
  const originalFixtures = ref<SeatingFixtureProjection[]>([]);
  const fixtures = ref<SeatingFixtureProjection[]>([]);
  const selectedKey = ref<string | null>(null);
  const past = ref<Snapshot[]>([]);
  const future = ref<Snapshot[]>([]);
  const saving = ref(false);
  let newCounter = 0;

  function load(response: SeatingResponse | null | undefined) {
    if (!response) return;
    original.value = toDraft(response.spots);
    spots.value = original.value.map((spot) => ({ ...spot }));
    removed.value = [];
    areas.value = [];
    originalFixtures.value = (response.fixtures || []).map((fixture) => ({ ...fixture }));
    fixtures.value = originalFixtures.value.map((fixture) => ({ ...fixture }));
    past.value = [];
    future.value = [];
    if (selectedKey.value && !spots.value.some((spot) => spot.key === selectedKey.value)) selectedKey.value = null;
  }
  watch(data, (value) => load(value), { immediate: true });

  const selected = computed(() => spots.value.find((spot) => spot.key === selectedKey.value) ?? null);
  const selectedOriginal = computed(() => original.value.find((spot) => spot.key === selectedKey.value));
  const fixturesChanged = computed(() => JSON.stringify(fixtures.value) !== JSON.stringify(originalFixtures.value));
  const changes = computed(() => {
    const list = changeList(original.value, spots.value, removed.value);
    return fixturesChanged.value ? [...list, { key: "fixtures", text: "vitrine e entrada na planta" }] : list;
  });
  const summary = computed(() => changesSummary(changes.value));
  const dirty = computed(() => changes.value.length > 0);

  function snapshot(): Snapshot {
    return {
      spots: spots.value.map((spot) => ({ ...spot })),
      removed: removed.value.map((spot) => ({ ...spot })),
      areas: [...areas.value],
      fixtures: fixtures.value.map((fixture) => ({ ...fixture })),
    };
  }
  function restore(state: Snapshot) {
    spots.value = state.spots;
    removed.value = state.removed;
    areas.value = state.areas;
    fixtures.value = state.fixtures;
    if (selectedKey.value && !spots.value.some((spot) => spot.key === selectedKey.value)) selectedKey.value = null;
  }
  /** Guarda o estado de agora para o Desfazer (antes de cada gesto). */
  function checkpoint() {
    past.value = [...past.value.slice(-(HISTORY_LIMIT - 1)), snapshot()];
    future.value = [];
  }
  function undo() {
    const previous = past.value.at(-1);
    if (!previous) return;
    future.value = [snapshot(), ...future.value];
    past.value = past.value.slice(0, -1);
    restore(previous);
  }
  function redo() {
    const next = future.value[0];
    if (!next) return;
    past.value = [...past.value, snapshot()];
    future.value = future.value.slice(1);
    restore(next);
  }

  function update(key: string, patch: Partial<DraftSpot>, options: { checkpoint?: boolean } = {}) {
    const index = spots.value.findIndex((spot) => spot.key === key);
    if (index < 0) return;
    if (options.checkpoint !== false) checkpoint();
    const next = { ...spots.value[index]!, ...patch };
    if (next.shape === "stool") next.seats = 1;
    spots.value = spots.value.map((spot, i) => (i === index ? next : spot));
  }

  function add(shape: SpotShape, at?: { x: number; y: number }, area?: string) {
    checkpoint();
    const name = nextSpotName(shape, spots.value);
    const seats = defaultSeats(shape);
    const size = spotSize(shape, seats);
    const targetArea = area ?? selected.value?.area ?? "";
    // Solta da paleta: o centro é onde o dedo soltou. Toque: o primeiro lugar livre da área.
    const corner = at
      ? { x: snap(at.x - size.w / 2), y: snap(at.y - size.h / 2) }
      : freeSpot(spots.value, targetArea, shape, seats);
    newCounter += 1;
    const spot: DraftSpot = {
      key: `nova-${newCounter}`,
      label: name.label,
      short_label: name.short_label,
      area: targetArea,
      shape,
      seats,
      counts_in_capacity: true,
      x: corner.x,
      y: corner.y,
      rotation: 0,
      since_label: "",
      born_today: true,
    };
    spots.value = [...spots.value, spot];
    selectedKey.value = spot.key;
    return spot;
  }

  function duplicate(key: string) {
    const source = spots.value.find((spot) => spot.key === key);
    if (!source) return;
    const copy = add(source.shape, { x: source.x + 80 + spotSize(source.shape, source.seats).w / 2, y: source.y + spotSize(source.shape, source.seats).h / 2 }, source.area);
    if (!copy) return;
    update(copy.key, { seats: source.seats, counts_in_capacity: source.counts_in_capacity, rotation: source.rotation }, { checkpoint: false });
  }

  function rotate(key: string) {
    const spot = spots.value.find((item) => item.key === key);
    if (spot) update(key, { rotation: (spot.rotation + 90) % 360 });
  }

  function remove(key: string) {
    const spot = spots.value.find((item) => item.key === key);
    if (!spot) return;
    checkpoint();
    spots.value = spots.value.filter((item) => item.key !== key);
    if (spot.ref) {
      const pristine = original.value.find((item) => item.key === key) ?? spot;
      removed.value = [...removed.value, pristine];
    }
    if (selectedKey.value === key) selectedKey.value = null;
  }

  function addArea(name: string): boolean {
    const clean = name.trim();
    if (!clean) return false;
    if (spots.value.some((spot) => spot.area === clean) || areas.value.includes(clean)) return false;
    checkpoint();
    areas.value = [...areas.value, clean];
    return true;
  }

  /** Põe a vitrine e caixa ou a entrada na planta (uma de cada; a segunda move a primeira). */
  function addFixture(kind: SeatingFixtureKind, label: string, at: { x: number; y: number }) {
    checkpoint();
    const size = FIXTURE_DEFAULTS[kind];
    const fixture: SeatingFixtureProjection = { kind, label, plan_x: snap(Math.max(0, at.x - size.width / 2)), plan_y: snap(Math.max(0, at.y - size.height / 2)), ...size };
    fixtures.value = [...fixtures.value.filter((item) => item.kind !== kind), fixture];
  }
  function moveFixture(kind: SeatingFixtureKind, x: number, y: number) {
    fixtures.value = fixtures.value.map((item) => (item.kind === kind ? { ...item, plan_x: Math.max(0, x), plan_y: Math.max(0, y) } : item));
  }
  function rotateFixture(kind: SeatingFixtureKind) {
    checkpoint();
    fixtures.value = fixtures.value.map((item) => (item.kind === kind ? { ...item, width: item.height, height: item.width } : item));
  }
  function removeFixture(kind: SeatingFixtureKind) {
    checkpoint();
    fixtures.value = fixtures.value.filter((item) => item.kind !== kind);
  }

  function discard() {
    load(data.value);
  }

  async function save(): Promise<boolean> {
    if (!data.value || !dirty.value || saving.value) return false;
    saving.value = true;
    try {
      const response = await action.call<SeatingResponse>("/api/v1/backstage/pos/seating/", {
        method: "POST",
        body: {
          ...(savePayload(data.value.revision, original.value, spots.value, removed.value) as unknown as Record<string, unknown>),
          ...(fixturesChanged.value ? { fixtures: fixtures.value.map((f) => ({ kind: f.kind, label: f.label, plan_x: f.plan_x, plan_y: f.plan_y, width: f.width, height: f.height })) } : {}),
        },
      });
      data.value = response;
      toast.success("Salão salvo.", { description: "Vale a partir de hoje; os dias de antes não mudam." });
      return true;
    } catch (failure) {
      if (httpErrorCode(failure) === "seating_conflict") {
        toast.error(httpErrorMessage(failure, "Outro dispositivo salvou o salão. Atualize para ver a planta nova."), {
          description: "Atualize a planta e refaça a mudança.",
          action: { label: "Atualizar", onClick: () => void refresh() },
        });
      } else {
        toast.error(httpErrorMessage(failure, "Não foi possível salvar o salão. Tente de novo."));
      }
      return false;
    } finally {
      saving.value = false;
    }
  }

  return {
    data, pending, error, refresh,
    original, spots, removed, areas, selectedKey, selected, selectedOriginal, fixtures,
    changes, summary, dirty, saving,
    canUndo: computed(() => past.value.length > 0),
    canRedo: computed(() => future.value.length > 0),
    checkpoint, update, add, duplicate, rotate, remove, addArea, undo, redo, discard, save,
    addFixture, moveFixture, rotateFixture, removeFixture,
  };
}

export type PosSeating = ReturnType<typeof usePosSeating>;
