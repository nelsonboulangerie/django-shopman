export type QuantityUnit = "g" | "kg" | "ml" | "L" | "un";

const QUANTITY_RULES: Record<
  QuantityUnit,
  { step: number; min: number; maximumFractionDigits: number }
> = {
  g: { step: 1, min: 1, maximumFractionDigits: 0 },
  kg: { step: 0.001, min: 0.001, maximumFractionDigits: 3 },
  ml: { step: 1, min: 1, maximumFractionDigits: 0 },
  L: { step: 0.001, min: 0.001, maximumFractionDigits: 3 },
  un: { step: 1, min: 1, maximumFractionDigits: 0 },
};

const MASS_FACTOR: Partial<Record<QuantityUnit, number>> = { g: 1, kg: 1000 };
const VOLUME_FACTOR: Partial<Record<QuantityUnit, number>> = { ml: 1, L: 1000 };

export function quantityRule(unit: QuantityUnit) {
  return QUANTITY_RULES[unit];
}

export function normalizeQuantity(value: number, unit: QuantityUnit): number {
  const factor = 10 ** quantityRule(unit).maximumFractionDigits;
  return Math.round((value + Number.EPSILON) * factor) / factor;
}

export function convertQuantity(
  quantity: number,
  from: QuantityUnit,
  to: QuantityUnit,
): number | null {
  const factors =
    MASS_FACTOR[from] && MASS_FACTOR[to]
      ? MASS_FACTOR
      : VOLUME_FACTOR[from] && VOLUME_FACTOR[to]
        ? VOLUME_FACTOR
        : null;
  if (!factors) return from === to ? normalizeQuantity(quantity, to) : null;
  return normalizeQuantity(
    (quantity * (factors[from] ?? 1)) / (factors[to] ?? 1),
    to,
  );
}
