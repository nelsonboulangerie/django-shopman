import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { h, nextTick } from "vue";

import OperatorRecordNav from "../../app/components/OperatorRecordNav.vue";
import { recordTrailOf } from "../../app/presentation/recordTrail";

const { navigate } = vi.hoisted(() => ({ navigate: vi.fn() }));
mockNuxtImport("navigateTo", () => navigate);

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

const KEY = "teste-pedidos";
const to = (id: string) => `/${id}`;

function storeTrail(ids: string[]) {
  sessionStorage.setItem(
    `operator-record-trail:${KEY}`,
    JSON.stringify(recordTrailOf(ids, "/?scope=late", "Pedidos")),
  );
}

async function mountNav(current: string) {
  mounted = await mountSuspended(OperatorRecordNav, {
    attachTo: document.body,
    props: { trail: KEY, current, to, previousLabel: "Pedido anterior", nextLabel: "Próximo pedido" },
  });
  await nextTick();
}

function press(code: string, target: EventTarget = document.body) {
  const event = new KeyboardEvent("keydown", { code, key: code.replace(/^Key/, "").toLowerCase(), bubbles: true });
  target.dispatchEvent(event);
}

beforeEach(() => {
  navigate.mockReset();
  sessionStorage.clear();
  useState(`operator-record-trail-${KEY}`).value = null;
});

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

describe("OperatorRecordNav: ‹ 3 de 18 › dentro da lista de origem", () => {
  it("diz a posição na lista de onde a pessoa veio, com links de verdade", async () => {
    storeTrail(["1046", "1048", "1051", "1053"]);
    await mountNav("1051");
    const group = document.querySelector<HTMLElement>("[data-operator-record-nav]")!;
    expect(group.getAttribute("role")).toBe("group");
    expect(group.getAttribute("aria-label")).toBe("Pedidos: 3 de 4");
    expect(document.querySelector("[data-operator-record-count]")!.textContent!.trim()).toBe("3 de 4");
    const previous = document.querySelector<HTMLElement>("[data-operator-record-previous]")!;
    const next = document.querySelector<HTMLElement>("[data-operator-record-next]")!;
    expect(previous.getAttribute("href")).toBe("/1048");
    expect(next.getAttribute("href")).toBe("/1053");
    expect(previous.getAttribute("aria-label")).toBe("Pedido anterior");
    expect(next.getAttribute("title")).toBe("Próximo pedido (J)");
  });

  it("na ponta, o lado que falta fica desabilitado", async () => {
    storeTrail(["1046", "1048", "1051"]);
    await mountNav("1046");
    const previous = document.querySelector<HTMLElement>("[data-operator-record-previous]")!;
    expect(previous.hasAttribute("disabled") || previous.getAttribute("aria-disabled") === "true").toBe(true);
    expect(document.querySelector("[data-operator-record-next]")!.getAttribute("href")).toBe("/1048");
  });

  it("sem trilha, ou com o registro fora dela, o par não aparece", async () => {
    await mountNav("1048");
    expect(document.querySelector("[data-operator-record-nav]")).toBeNull();
    mounted!.unmount();
    storeTrail(["1046", "1051"]);
    await mountNav("1048");
    expect(document.querySelector("[data-operator-record-nav]")).toBeNull();
  });

  it("J e → vão ao próximo; K e ← ao anterior", async () => {
    storeTrail(["1046", "1048", "1051"]);
    await mountNav("1048");
    press("KeyJ");
    press("ArrowLeft");
    expect(navigate.mock.calls.map(([target]) => target)).toEqual(["/1051", "/1046"]);
  });

  it("as teclas não agem num campo nem onde as setas já têm dono (abas)", async () => {
    storeTrail(["1046", "1048", "1051"]);
    mounted = await mountSuspended(
      { render: () => h("div", [h("input", { "data-test-field": "" }), h("div", { role: "tablist" }, [h("button", { "data-test-tab": "" }, "Aba")])]) },
      { attachTo: document.body },
    );
    const page = mounted;
    await mountNav("1048");
    press("KeyJ", document.querySelector("[data-test-field]")!);
    press("ArrowRight", document.querySelector("[data-test-tab]")!);
    expect(navigate).not.toHaveBeenCalled();
    press("ArrowRight", document.body);
    expect(navigate).toHaveBeenCalledWith("/1051");
    page.unmount();
  });
});
