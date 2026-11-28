import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, ref, watch } from "vue";

import { flushPromises, mount } from "@vue/test-utils";

import CustomerGroupAddMembersDialog from "../../app/components/CustomerGroupAddMembersDialog.vue";
import CustomerGroupBulkDialog from "../../app/components/CustomerGroupBulkDialog.vue";
import type { CustomerRowProjection } from "../../app/generated/ordersContract";

// Auto-imports do Nuxt que o SFC usa como globais (sem runtime Nuxt aqui).
vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
vi.stubGlobal("watchDebounced", (source: unknown, cb: (value: string) => void) => watch(source as never, cb as never));
vi.stubGlobal("httpErrorMessage", (_error: unknown, fallback: string) => fallback);
vi.stubGlobal("httpError", () => ({ status: 400 }));

function row(ref_: string, name: string, groups: string[] = ["varejo"]): CustomerRowProjection {
  return {
    ref: ref_, name, phone_display: "", email: "", document_display: "", source_label: "",
    is_ifood: false, orders_label: "Nenhum pedido", last_order_display: "", duplicate_hint: "",
    groups: groups.map((group, index) => ({ ref: group, name: group, is_primary: index === 0 })),
  };
}

let searchCustomers: ReturnType<typeof vi.fn>;
let changeCustomerGroupMembers: ReturnType<typeof vi.fn>;

beforeEach(() => {
  searchCustomers = vi.fn(async () => [row("CLI-1", "Ana"), row("CLI-2", "Bruno", ["equipe", "varejo"]), row("CLI-3", "Carla")]);
  changeCustomerGroupMembers = vi.fn(async (_ref: string, payload: { refs: string[] }) => ({
    outcome: "applied", operation: "add", group: { ref: "equipe", name: "Equipe" },
    applied: payload.refs, unchanged: [], skipped: [], moved_to_default: [], default_group: null,
  }));
  vi.stubGlobal("searchCustomers", searchCustomers);
  vi.stubGlobal("changeCustomerGroupMembers", changeCustomerGroupMembers);
});

afterEach(() => { vi.clearAllMocks(); });

describe("CustomerGroupAddMembersDialog", () => {
  function mountDialog() {
    return mount(CustomerGroupAddMembersDialog, {
      props: { open: true, group: { ref: "equipe", name: "Equipe" } },
      attachTo: document.body,
    });
  }

  it("abre com os clientes recentes e marca travado quem já está no grupo", async () => {
    const wrapper = mountDialog();
    await flushPromises();

    expect(searchCustomers).toHaveBeenCalledWith("");
    const bruno = document.querySelector("[data-customer-group-add-row='CLI-2']");
    expect(bruno?.textContent).toContain("Já está no grupo");
    expect(bruno?.querySelector("button[role='checkbox']")?.hasAttribute("disabled")).toBe(true);
    wrapper.unmount();
  });

  it("marca vários e adiciona numa ida, dizendo o resultado no botão", async () => {
    const wrapper = mountDialog();
    await flushPromises();
    const confirm = () => document.querySelector<HTMLButtonElement>("[data-customer-group-add-confirm]")!;
    expect(confirm().disabled).toBe(true);

    document.querySelector<HTMLButtonElement>("[data-customer-group-add-row='CLI-1'] button[role='checkbox']")!.click();
    document.querySelector<HTMLButtonElement>("[data-customer-group-add-row='CLI-3'] button[role='checkbox']")!.click();
    await flushPromises();

    expect(confirm().textContent).toContain("Adicionar 2 clientes ao grupo Equipe");
    confirm().click();
    await flushPromises();

    expect(changeCustomerGroupMembers).toHaveBeenCalledWith(
      "equipe", { operation: "add", refs: ["CLI-1", "CLI-3"] }, expect.any(String),
    );
    expect(wrapper.emitted("saved")?.[0]?.[0]).toMatchObject({ applied: ["CLI-1", "CLI-3"] });
    expect(wrapper.emitted("update:open")?.at(-1)).toEqual([false]);
    wrapper.unmount();
  });

  it("a marcação atravessa buscas", async () => {
    const wrapper = mountDialog();
    await flushPromises();
    document.querySelector<HTMLButtonElement>("[data-customer-group-add-row='CLI-1'] button[role='checkbox']")!.click();
    searchCustomers.mockResolvedValueOnce([row("CLI-9", "Davi")]);
    const input = document.querySelector<HTMLInputElement>("[data-customer-group-add-search] input, input[data-customer-group-add-search]")!;
    input.value = "davi";
    input.dispatchEvent(new Event("input"));
    await flushPromises();
    document.querySelector<HTMLButtonElement>("[data-customer-group-add-row='CLI-9'] button[role='checkbox']")!.click();
    await flushPromises();

    expect(document.querySelector("[data-customer-group-add-chosen]")?.textContent).toContain("Ana, Davi");
    wrapper.unmount();
  });

  it("recusa do servidor fica na caixa, sem fechar", async () => {
    changeCustomerGroupMembers.mockRejectedValueOnce(new Error("400"));
    const wrapper = mountDialog();
    await flushPromises();
    document.querySelector<HTMLButtonElement>("[data-customer-group-add-row='CLI-1'] button[role='checkbox']")!.click();
    await flushPromises();
    document.querySelector<HTMLButtonElement>("[data-customer-group-add-confirm]")!.click();
    await flushPromises();

    expect(document.body.textContent).toContain("Não foi possível adicionar os clientes.");
    expect(wrapper.emitted("saved")).toBeUndefined();
    wrapper.unmount();
  });
});

describe("CustomerGroupBulkDialog", () => {
  const groups = [
    { value: "varejo", label: "Varejo" },
    { value: "equipe", label: "Equipe" },
  ];

  it("lista recortada por grupo abre em tirar, com o grupo escolhido", async () => {
    const wrapper = mount(CustomerGroupBulkDialog, {
      props: { open: true, count: 3, groups, initialGroup: "equipe" },
      attachTo: document.body,
    });
    await flushPromises();
    const confirm = document.querySelector<HTMLButtonElement>("[data-customer-group-bulk-confirm]")!;
    expect(confirm.textContent).toContain("Tirar 3 clientes do grupo Equipe");
    confirm.click();
    expect(wrapper.emitted("save")?.[0]?.[0]).toEqual({ operation: "remove", groupRef: "equipe" });
    wrapper.unmount();
  });

  it("sem grupo escolhido não deixa confirmar", async () => {
    const wrapper = mount(CustomerGroupBulkDialog, {
      props: { open: true, count: 1, groups },
      attachTo: document.body,
    });
    await flushPromises();
    const confirm = document.querySelector<HTMLButtonElement>("[data-customer-group-bulk-confirm]")!;
    expect(confirm.disabled).toBe(true);
    expect(confirm.textContent).toContain("Adicionar 1 cliente");
    expect(document.body.textContent).toContain("Os outros grupos de cada cliente continuam.");
    wrapper.unmount();
  });
});
