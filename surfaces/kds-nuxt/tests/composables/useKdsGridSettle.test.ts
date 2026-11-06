import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, ref } from "vue";
import {
  KDS_GRID_SETTLE_MAX_MS,
  KDS_GRID_SETTLE_MS,
  KDS_GRID_SETTLE_RECHECK_MS,
  placementSignature,
  useKdsGridSettle,
} from "~/composables/useKdsGridSettle";
import { focusSlice } from "~/presentation/board";

// O toque no pedido errado (06/11/2026, Encomendas, 800×600): chegou o P30, a fila se
// reorganizou e, com os tickets deslizando uns sobre os outros, o "Iniciar preparo" do
// P30 abriu o detalhe do T69. Enquanto a grade se acomoda, nenhum toque age.

const card = (pk: number) => ({ pk });

function signatureOf(pks: number[], columns = 3, rows = 2) {
  const slice = focusSlice(pks.map(card) as never, { columns, rows });
  return placementSignature(slice.visible, slice.placements);
}

describe("placementSignature", () => {
  it("muda quando um pedido novo entra na frente e empurra a fila", () => {
    expect(signatureOf([69, 9, 12])).not.toBe(signatureOf([30, 69, 9, 12]));
  });

  it("muda quando um ticket troca de célula sem ninguém entrar nem sair", () => {
    expect(signatureOf([69, 9])).not.toBe(signatureOf([9, 69]));
  });

  it("não muda quando a fila é a mesma (o refetch não trava a grade)", () => {
    expect(signatureOf([69, 9, 12])).toBe(signatureOf([69, 9, 12]));
  });
});

describe("useKdsGridSettle", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  function setup(initial: number[]) {
    const pks = ref(initial);
    const scope = effectScope();
    const settle = scope.run(() =>
      useKdsGridSettle(() => signatureOf(pks.value)),
    )!;
    return { pks, scope, ...settle };
  }

  it("com a grade parada, o toque age pelo pedido tocado", () => {
    const { guard, settling, scope } = setup([69, 9]);
    const acted: number[] = [];
    guard(() => acted.push(69));
    expect(settling.value).toBe(false);
    expect(acted).toEqual([69]);
    scope.stop();
  });

  it("enquanto a fila se reorganiza, o toque não age; acomodada, volta a agir", () => {
    const { pks, guard, settling, scope } = setup([69, 9]);
    const acted: number[] = [];

    pks.value = [30, 69, 9];
    // A trava liga no mesmo instante, antes do DOM se mexer.
    expect(settling.value).toBe(true);
    guard(() => acted.push(30));
    expect(acted).toEqual([]);

    vi.advanceTimersByTime(KDS_GRID_SETTLE_MS - 1);
    guard(() => acted.push(30));
    expect(acted).toEqual([]);

    vi.advanceTimersByTime(1);
    expect(settling.value).toBe(false);
    guard(() => acted.push(30));
    expect(acted).toEqual([30]);
    scope.stop();
  });

  it("uma segunda mudança no meio da acomodação estica a trava", () => {
    const { pks, settling, scope } = setup([69, 9]);
    pks.value = [30, 69, 9];
    vi.advanceTimersByTime(KDS_GRID_SETTLE_MS - 100);
    pks.value = [30, 9];
    vi.advanceTimersByTime(KDS_GRID_SETTLE_MS - 1);
    expect(settling.value).toBe(true);
    vi.advanceTimersByTime(1);
    expect(settling.value).toBe(false);
    scope.stop();
  });

  it("num tablet lento, espera o último ticket parar de se mexer, com teto", () => {
    const pks = ref([69, 9]);
    let moving = true;
    const scope = effectScope();
    const { settling } = scope.run(() =>
      useKdsGridSettle(() => signatureOf(pks.value), {
        stillMoving: () => moving,
      }),
    )!;

    pks.value = [30, 69, 9];
    vi.advanceTimersByTime(KDS_GRID_SETTLE_MS + KDS_GRID_SETTLE_RECHECK_MS * 3);
    expect(settling.value).toBe(true);
    moving = false;
    vi.advanceTimersByTime(KDS_GRID_SETTLE_RECHECK_MS);
    expect(settling.value).toBe(false);

    // Animação que nunca termina não deixa a grade surda para sempre.
    moving = true;
    pks.value = [9];
    vi.advanceTimersByTime(KDS_GRID_SETTLE_MAX_MS + KDS_GRID_SETTLE_RECHECK_MS);
    expect(settling.value).toBe(false);
    scope.stop();
  });

  it("com movimento reduzido não há animação, então não há o que esperar", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    const { pks, settling, scope } = setup([69, 9]);
    pks.value = [30, 69, 9];
    expect(settling.value).toBe(false);
    scope.stop();
  });
});

describe("a grade da estação usa a trava", () => {
  const page = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), "../../app/pages/[ref].vue"),
    "utf8",
  );

  it("todo ato do ticket na grade passa pela trava, pelo pk do ticket tocado", () => {
    for (const act of [
      '@open="whenSettled(() => (openTicketPk = card.pk))"',
      '@start="whenSettled(() => start(card.pk))"',
      '@finish="whenSettled(() => finish(card.pk))"',
      '@undo="whenSettled(() => undoFinish(card.pk))"',
      '@seen="whenSettled(() => acknowledgeChange(card.pk))"',
      '@locked="whenSettled(() => warnLocked(card.pk))"',
    ]) {
      expect(page).toContain(act);
    }
  });

  it("a grade não recebe toque enquanto se acomoda, e o ticket que sai fica atrás", () => {
    expect(page).toContain(
      ":class=\"{ 'pointer-events-none': gridSettling }\"",
    );
    expect(page).toMatch(
      /\.kds-card-leave-active \{\s*z-index: 0;\s*pointer-events: none;/,
    );
  });

  it("o deslize da grade cabe na trava", () => {
    const move = page.match(
      /\.kds-card-move \{\s*transition: transform ([\d.]+)s/,
    );
    expect(move).not.toBeNull();
    expect(Number(move![1]) * 1000).toBeLessThan(KDS_GRID_SETTLE_MS);
  });
});
