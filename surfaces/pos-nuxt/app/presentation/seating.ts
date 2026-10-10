// Presentation: PDV › Ajustes › Salão (prévia v4 `salao-mesas4.html`).
//
// Puro: a geometria da planta (tamanho da mesa pela forma e pelos lugares, as
// cadeiras em volta, a caixa de cada área), o rascunho que a tela edita, o que mudou
// em relação ao que o servidor leu ("3 mudanças: M7 movida, C3 nova, C2 extra") e o
// corpo do Salvar, que leva só o que mudou.
//
// A regra de tempo é do servidor (`services/seating.py`): lugares e "conta na
// capacidade oficial" mudam por versão (vale de hoje em diante); desenho muda no
// lugar. Aqui ela só vira frase, no painel da mesa.

import type { SeatingSpotProjection, SpotShape } from "~/types/seating";

/** O passo da grade: o mesmo dos pontos do fundo da planta. */
export const GRID = 20;
/** O diâmetro da cadeira desenhada e a folga entre ela e a mesa. */
export const CHAIR = 14;
const CHAIR_GAP = 4;
/** A margem da caixa da área em volta das mesas (e o espaço do rótulo em cima). */
const AREA_PAD = 22;
const AREA_LABEL = 12;
/** Folga da planta além da última mesa. */
const CANVAS_MARGIN = 80;
export const ZOOM_STEPS = [0.5, 0.67, 0.75, 0.9, 1, 1.1, 1.25, 1.5];
export const NO_AREA = "Sem área";

export const SHAPES: { value: SpotShape; label: string }[] = [
  { value: "round", label: "Redonda" },
  { value: "square", label: "Quadrada" },
  { value: "long", label: "Comprida" },
  { value: "stool", label: "Banqueta" },
];

export function shapeLabel(shape: SpotShape): string {
  return SHAPES.find((item) => item.value === shape)?.label ?? shape;
}

/** O que a tela edita: a mesa do servidor, ou uma nova ainda sem `ref`. */
export interface DraftSpot {
  /** Identidade na tela: a `ref` ou `nova-N`. */
  key: string;
  ref?: string;
  label: string;
  short_label: string;
  area: string;
  shape: SpotShape;
  seats: number;
  counts_in_capacity: boolean;
  x: number;
  y: number;
  rotation: number;
  since_label: string;
  born_today: boolean;
}

export interface Box { x: number; y: number; w: number; h: number }

/** Tamanho da mesa na planta (sem as cadeiras), antes do giro. */
export function spotSize(shape: SpotShape, seats: number): { w: number; h: number } {
  if (shape === "stool") return { w: 40, h: 40 };
  if (shape === "round") {
    const d = seats <= 2 ? 56 : seats <= 4 ? 64 : Math.min(104, 56 + seats * 4);
    return { w: d, h: d };
  }
  if (shape === "square") return seats <= 4 ? { w: 70, h: 70 } : { w: 84, h: 84 };
  return { w: Math.max(120, Math.ceil(seats / 2) * 30 + 30), h: 60 };
}

/**
 * Centro de cada cadeira, relativo ao canto da mesa (antes do giro). Redonda: em
 * volta, começando em cima. Quadrada: um lado de cada vez (cima, baixo, esquerda,
 * direita). Comprida: em cima e embaixo. Banqueta é o próprio lugar: sem cadeira.
 */
export function chairCenters(shape: SpotShape, seats: number): { x: number; y: number }[] {
  if (shape === "stool" || seats < 1) return [];
  const { w, h } = spotSize(shape, seats);
  const off = CHAIR / 2 + CHAIR_GAP;
  if (shape === "round") {
    const r = w / 2 + off;
    return Array.from({ length: seats }, (_, i) => {
      const angle = -Math.PI / 2 + (i * 2 * Math.PI) / seats;
      return { x: Math.round(w / 2 + r * Math.cos(angle)), y: Math.round(h / 2 + r * Math.sin(angle)) };
    });
  }
  const sides = shape === "long" ? ["top", "bottom"] : ["top", "bottom", "left", "right"];
  const perSide: Record<string, number> = {};
  for (let i = 0; i < seats; i++) {
    const side = sides[i % sides.length]!;
    perSide[side] = (perSide[side] ?? 0) + 1;
  }
  const centers: { x: number; y: number }[] = [];
  for (const side of sides) {
    const count = perSide[side] ?? 0;
    for (let i = 0; i < count; i++) {
      const along = (i + 1) / (count + 1);
      if (side === "top") centers.push({ x: Math.round(w * along), y: -off });
      else if (side === "bottom") centers.push({ x: Math.round(w * along), y: h + off });
      else if (side === "left") centers.push({ x: -off, y: Math.round(h * along) });
      else centers.push({ x: w + off, y: Math.round(h * along) });
    }
  }
  return centers;
}

/** A caixa que a mesa ocupa com as cadeiras, já girada (giro de 90 em 90 em volta do centro). */
export function footprint(spot: Pick<DraftSpot, "shape" | "seats" | "x" | "y" | "rotation">): Box {
  const { w, h } = spotSize(spot.shape, spot.seats);
  const reach = spot.shape === "stool" ? 0 : CHAIR + CHAIR_GAP;
  const quarter = spot.rotation === 90 || spot.rotation === 270;
  const fw = (quarter ? h : w) + reach * 2;
  const fh = (quarter ? w : h) + reach * 2;
  const cx = spot.x + w / 2;
  const cy = spot.y + h / 2;
  return { x: cx - fw / 2, y: cy - fh / 2, w: fw, h: fh };
}

export function snap(value: number, enabled = true): number {
  const clamped = Math.max(0, Math.round(value));
  return enabled ? Math.round(clamped / GRID) * GRID : clamped;
}

/** A sigla dentro da mesa: a cadastrada, ou a inicial do nome com o número dele. */
export function shortLabelOf(spot: Pick<DraftSpot, "short_label" | "label">): string {
  if (spot.short_label.trim()) return spot.short_label.trim();
  const words = spot.label.trim().split(/\s+/).filter(Boolean);
  const number = spot.label.match(/(\d+)\s*$/)?.[1] ?? "";
  const initial = (words[0]?.charAt(0) ?? "?").toUpperCase();
  return `${initial}${number}`.slice(0, 8);
}

export function seatsLabel(seats: number): string {
  return `${seats} lug.`;
}

export function areaOf(spot: Pick<DraftSpot, "area">): string {
  return spot.area.trim() || NO_AREA;
}

/** Do servidor para o rascunho. Mesa sem posição ganha uma, abaixo do que já está desenhado. */
export function toDraft(spots: readonly SeatingSpotProjection[]): DraftSpot[] {
  const placed = spots.filter((spot) => spot.plan_x !== null && spot.plan_y !== null);
  let bottom = placed.reduce((max, spot) => {
    const box = footprint({ shape: spot.shape, seats: spot.seats, x: spot.plan_x!, y: spot.plan_y!, rotation: spot.rotation });
    return Math.max(max, box.y + box.h);
  }, 0);
  let cursorX = 40;
  const rowTop = placed.length ? bottom + 80 : 60;
  bottom = rowTop;
  return spots.map((spot) => {
    let x = spot.plan_x;
    let y = spot.plan_y;
    if (x === null || y === null) {
      const { w } = spotSize(spot.shape, spot.seats);
      if (cursorX + w > 760) {
        cursorX = 40;
        bottom += 120;
      }
      x = cursorX;
      y = bottom;
      cursorX += w + 60;
    }
    return {
      key: spot.ref,
      ref: spot.ref,
      label: spot.label,
      short_label: spot.short_label,
      area: spot.area,
      shape: spot.shape,
      seats: spot.seats,
      counts_in_capacity: spot.counts_in_capacity,
      x,
      y,
      rotation: spot.rotation,
      since_label: spot.since_label,
      born_today: spot.born_today,
    };
  });
}

export interface AreaBox extends Box {
  name: string;
  capacitySeats: number;
  extraSeats: number;
  /** Só extras de dia cheio: a área inteira é desenhada tracejada. */
  allExtra: boolean;
}

export interface AreaSummary { name: string; capacitySeats: number; extraSeats: number; spots: number }

/** As áreas da casa com a contagem, na ordem em que aparecem (e as recém-criadas, vazias). */
export function areaSummaries(spots: readonly DraftSpot[], extra: readonly string[] = []): AreaSummary[] {
  const order: string[] = [];
  const byName = new Map<string, AreaSummary>();
  for (const spot of spots) {
    const name = areaOf(spot);
    if (!byName.has(name)) {
      order.push(name);
      byName.set(name, { name, capacitySeats: 0, extraSeats: 0, spots: 0 });
    }
    const summary = byName.get(name)!;
    summary.spots += 1;
    if (spot.counts_in_capacity) summary.capacitySeats += spot.seats;
    else summary.extraSeats += spot.seats;
  }
  // Na ordem da planta: de cima para baixo (em faixas de 120), e da esquerda para a direita.
  const corner = new Map(areaBoxes(spots).map((box) => [box.name, box]));
  const placed = order.sort((a, b) => {
    const boxA = corner.get(a)!;
    const boxB = corner.get(b)!;
    return Math.floor(boxA.y / 120) - Math.floor(boxB.y / 120) || boxA.x - boxB.x;
  });
  for (const name of extra) {
    if (!byName.has(name)) {
      placed.push(name);
      byName.set(name, { name, capacitySeats: 0, extraSeats: 0, spots: 0 });
    }
  }
  return placed.map((name) => byName.get(name)!);
}

/** A caixa de cada área na planta: o contorno das mesas dela, com margem e lugar para o rótulo. */
export function areaBoxes(spots: readonly DraftSpot[]): AreaBox[] {
  const boxes = new Map<string, AreaBox>();
  for (const spot of spots) {
    const name = areaOf(spot);
    const fp = footprint(spot);
    const current = boxes.get(name);
    if (!current) {
      boxes.set(name, { name, ...fp, capacitySeats: 0, extraSeats: 0, allExtra: true });
    } else {
      const right = Math.max(current.x + current.w, fp.x + fp.w);
      const bottom = Math.max(current.y + current.h, fp.y + fp.h);
      current.x = Math.min(current.x, fp.x);
      current.y = Math.min(current.y, fp.y);
      current.w = right - current.x;
      current.h = bottom - current.y;
    }
    const box = boxes.get(name)!;
    if (spot.counts_in_capacity) {
      box.capacitySeats += spot.seats;
      box.allExtra = false;
    } else box.extraSeats += spot.seats;
  }
  return [...boxes.values()].map((box) => ({
    ...box,
    x: box.x - AREA_PAD,
    y: box.y - AREA_PAD - AREA_LABEL,
    w: box.w + AREA_PAD * 2,
    h: box.h + AREA_PAD * 2 + AREA_LABEL,
  }));
}

/** "Salão interno · 8 lugares", "Calçada · 8 lugares + 4 extras". */
export function areaTitle(box: Pick<AreaBox, "name" | "capacitySeats" | "extraSeats">): string {
  const parts = [`${box.capacitySeats} ${box.capacitySeats === 1 ? "lugar" : "lugares"}`];
  if (box.extraSeats) parts.push(`${box.extraSeats} ${box.extraSeats === 1 ? "extra" : "extras"}`);
  return `${box.name} · ${parts.join(" + ")}`;
}

/**
 * A margem fixa da planta antes da posição 0: cabe a caixa da área (margem, cadeira e
 * rótulo) de uma mesa encostada no canto, em múltiplo da grade (os pontos do fundo
 * coincidem com o encaixe). Fixa de propósito: se ela seguisse a mesa
 * mais à esquerda, a planta inteira pularia durante o arraste.
 */
export const PLAN_OFFSET = { x: 60, y: 80 };

/** O tamanho da planta: até a mesa mais distante, com folga para arrastar. */
export function canvasSize(spots: readonly DraftSpot[]): { w: number; h: number } {
  let w = 0;
  let h = 0;
  for (const box of areaBoxes(spots)) {
    w = Math.max(w, box.x + box.w);
    h = Math.max(h, box.y + box.h);
  }
  return {
    w: Math.max(600, Math.ceil(PLAN_OFFSET.x + w + CANVAS_MARGIN)),
    h: Math.max(480, Math.ceil(PLAN_OFFSET.y + h + CANVAS_MARGIN)),
  };
}

export function totals(spots: readonly DraftSpot[]): { capacitySeats: number; extraSeats: number; capacitySpots: number } {
  let capacitySeats = 0;
  let extraSeats = 0;
  let capacitySpots = 0;
  for (const spot of spots) {
    if (spot.counts_in_capacity) {
      capacitySeats += spot.seats;
      capacitySpots += 1;
    } else extraSeats += spot.seats;
  }
  return { capacitySeats, extraSeats, capacitySpots };
}

/** O nome e a sigla da mesa nova: o próximo número livre ("Mesa 10", "M10"; "Banqueta 7", "B7"). */
export function nextSpotName(shape: SpotShape, spots: readonly DraftSpot[]): { label: string; short_label: string } {
  const word = shape === "stool" ? "Banqueta" : "Mesa";
  const prefix = shape === "stool" ? "B" : "M";
  let max = 0;
  for (const spot of spots) {
    const match = shortLabelOf(spot).match(new RegExp(`^${prefix}(\\d+)$`));
    if (match) max = Math.max(max, Number(match[1]));
  }
  return { label: `${word} ${max + 1}`, short_label: `${prefix}${max + 1}` };
}

function overlaps(a: Box, b: Box, gap: number): boolean {
  return a.x < b.x + b.w + gap && b.x < a.x + a.w + gap && a.y < b.y + b.h + gap && b.y < a.y + a.h + gap;
}

/**
 * Onde cai a mesa nova tocada na paleta: o primeiro lugar livre (sem encostar em
 * outra mesa) na área escolhida, varrendo a caixa dela de cima para baixo e
 * transbordando para a direita e para baixo. Área sem mesa: abaixo de tudo.
 */
export function freeSpot(spots: readonly DraftSpot[], area: string, shape: SpotShape, seats: number): { x: number; y: number } {
  const size = spotSize(shape, seats);
  const boxes = spots.map((spot) => footprint(spot));
  const inArea = spots.filter((spot) => areaOf(spot) === (area.trim() || NO_AREA)).map((spot) => footprint(spot));
  let minX = 40;
  let minY = 40;
  let maxX = 760;
  let maxY = 600;
  if (inArea.length) {
    minX = Math.min(...inArea.map((box) => box.x));
    minY = Math.min(...inArea.map((box) => box.y));
    maxX = Math.max(...inArea.map((box) => box.x + box.w)) + 160;
    maxY = Math.max(...inArea.map((box) => box.y + box.h)) + 160;
  } else if (boxes.length) {
    minY = Math.max(...boxes.map((box) => box.y + box.h)) + 80;
    maxY = minY + 400;
  }
  for (let y = snap(minY); y <= maxY; y += GRID) {
    for (let x = snap(minX); x <= maxX; x += GRID) {
      const candidate = footprint({ shape, seats, x, y, rotation: 0 });
      if (candidate.x < 0 || candidate.y < 0) continue;
      if (!boxes.some((box) => overlaps(candidate, box, 12))) return { x, y };
    }
  }
  return { x: snap(minX), y: snap(maxY) + size.h };
}

export function defaultSeats(shape: SpotShape): number {
  if (shape === "stool") return 1;
  if (shape === "round") return 2;
  if (shape === "long") return 6;
  return 4;
}

const MEASURED: (keyof DraftSpot)[] = ["seats", "counts_in_capacity"];
const EDITABLE: (keyof DraftSpot)[] = ["label", "short_label", "area", "shape", "seats", "counts_in_capacity", "x", "y", "rotation"];
const WIRE: Partial<Record<keyof DraftSpot, string>> = { x: "plan_x", y: "plan_y" };

/** Mudou lugares ou a capacidade de uma mesa que já tem passado: o Salvar cria a versão de hoje. */
export function changesMeasure(original: DraftSpot | undefined, draft: DraftSpot): boolean {
  if (!original || original.born_today) return false;
  return MEASURED.some((key) => original[key] !== draft[key]);
}

export interface Change { key: string; text: string }

/** O que mudou, mesa por mesa, numa palavra: "M7 movida", "C3 nova", "C2 extra". */
export function changeList(
  original: readonly DraftSpot[],
  draft: readonly DraftSpot[],
  removed: readonly DraftSpot[],
): Change[] {
  const before = new Map(original.map((spot) => [spot.key, spot]));
  const changes: Change[] = [];
  for (const spot of draft) {
    const name = shortLabelOf(spot);
    const old = before.get(spot.key);
    if (!old) {
      changes.push({ key: spot.key, text: `${name} nova` });
      continue;
    }
    const words: string[] = [];
    if (old.counts_in_capacity !== spot.counts_in_capacity) words.push(spot.counts_in_capacity ? "na capacidade" : "extra");
    if (old.seats !== spot.seats) words.push(`com ${spot.seats} ${spot.seats === 1 ? "lugar" : "lugares"}`);
    if (old.shape !== spot.shape) words.push(shapeLabel(spot.shape).toLowerCase());
    if (old.x !== spot.x || old.y !== spot.y) words.push("movida");
    if (old.rotation !== spot.rotation) words.push("girada");
    if (old.area !== spot.area) words.push(`em ${areaOf(spot)}`);
    if (old.label !== spot.label || old.short_label !== spot.short_label) words.push("renomeada");
    if (words.length) changes.push({ key: spot.key, text: `${name} ${words.join(", ")}` });
  }
  for (const spot of removed) changes.push({ key: spot.key, text: `${shortLabelOf(spot)} saiu` });
  return changes;
}

/** "3 mudanças: M7 movida, C3 nova, C2 extra" (com "e mais N" quando passa de três). */
export function changesSummary(changes: readonly Change[]): string {
  if (!changes.length) return "";
  const head = `${changes.length} ${changes.length === 1 ? "mudança" : "mudanças"}`;
  const shown = changes.slice(0, 3).map((change) => change.text).join(", ");
  const rest = changes.length > 3 ? ` e mais ${changes.length - 3}` : "";
  return `${head}: ${shown}${rest}`;
}

export interface SavePayload {
  revision: string;
  spots: Record<string, unknown>[];
  removed: string[];
}

/** O corpo do Salvar: mesa existente leva só o que mudou; mesa nova leva tudo. */
export function savePayload(
  revision: string,
  original: readonly DraftSpot[],
  draft: readonly DraftSpot[],
  removed: readonly DraftSpot[],
): SavePayload {
  const before = new Map(original.map((spot) => [spot.key, spot]));
  const spots: Record<string, unknown>[] = [];
  for (const spot of draft) {
    const old = before.get(spot.key);
    const fields: Record<string, unknown> = {};
    for (const key of EDITABLE) {
      if (!old || old[key] !== spot[key]) fields[WIRE[key] ?? key] = spot[key];
    }
    if (!Object.keys(fields).length) continue;
    spots.push(old?.ref ? { ref: old.ref, ...fields } : fields);
  }
  return { revision, spots, removed: removed.filter((spot) => spot.ref).map((spot) => spot.ref!) };
}

/** A frase do "Existe desde" no painel da mesa, com a regra de tempo escrita no lugar. */
export function timeRule(original: DraftSpot | undefined, draft: DraftSpot, todayLabel: string): { title: string; note: string } {
  if (!original) {
    return {
      title: `Nova: passa a existir hoje (${todayLabel})`,
      note: "Entra na lotação a partir de hoje; os dias de antes não mudam.",
    };
  }
  const title = original.since_label ? `Existe desde ${original.since_label}` : "Existe desde o começo do cadastro";
  if (original.born_today) {
    return { title, note: "Nasceu hoje: lugares e forma ainda mudam sem criar versão." };
  }
  const seats = `${original.seats} ${original.seats === 1 ? "lugar" : "lugares"}`;
  if (changesMeasure(original, draft)) {
    return { title, note: `Ao salvar, vale a partir de hoje; os dias de antes continuam contados com ${seats}.` };
  }
  return { title, note: `Mudar lugares ou a capacidade vale a partir de hoje; os dias de antes continuam contados com ${seats}.` };
}
