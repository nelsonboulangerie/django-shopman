import { beforeEach, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import Manager from "../../app/components/CatalogCategoryManager.vue";

for (const [key, value] of Object.entries({ computed, ref }))
  vi.stubGlobal(key, value);

const change = vi.fn();
const board = () =>
  ({
    catalog_ref: "catalog-A",
    category_action: { enabled: true, reason: "" },
    categories_error: "",
    categories: [
      {
        ref: "category-A",
        name: "Pães",
        status: "AVAILABLE",
        index: 1,
        mapped_collections: 0,
      },
    ],
    collections: [
      {
        ref: "paes",
        name: "Pães da casa",
        category_ref: "",
        category_name: "",
      },
    ],
  }) as any;

const render = (data: any = board()) =>
  mount(Manager, {
    props: { board: data, busy: false, stale: false, change },
  });

const button = (wrapper: ReturnType<typeof render>, text: string) =>
  wrapper.findAll("button").find((item) => item.text() === text)!;

beforeEach(() => {
  change.mockReset();
  change.mockResolvedValue(true);
});

it("renomeia inline com corpo mínimo e confirmação explícita", async () => {
  const wrapper = render();
  await button(wrapper, "Renomear").trigger("click");
  await wrapper.get('input[type="text"]').setValue("Padaria");
  await button(wrapper, "Aplicar").trigger("click");
  await flushPromises();

  expect(change).toHaveBeenCalledWith({
    action: "rename",
    catalog_ref: "catalog-A",
    category_ref: "category-A",
    name: "Padaria",
  });
  expect(wrapper.find('input[type="text"]').exists()).toBe(false);
});

it("erro confirmado pela projeção fica legível e não expõe identificadores", () => {
  const data = board();
  data.categories_error =
    "Não foi possível confirmar as categorias agora. Exibindo a última captura disponível.";
  const wrapper = render(data);

  expect(wrapper.text()).toContain("A lista atual não pôde ser confirmada");
  expect(wrapper.text()).toContain("Exibindo a última captura disponível");
  expect(wrapper.text()).not.toContain("category-A");
  expect(wrapper.text()).not.toContain("catalog-A");
});

it("mantém cartões irmãos e bloqueia ações enquanto a leitura está desatualizada", () => {
  const wrapper = mount(Manager, {
    props: { board: board(), busy: false, stale: true, change },
  });

  expect(button(wrapper, "Renomear").attributes("disabled")).toBeDefined();
  expect(
    button(wrapper, "Alterar posição").attributes("disabled"),
  ).toBeDefined();
  expect(
    wrapper
      .findAll("article")
      .every((card) => card.classes().includes("h-full")),
  ).toBe(true);
});
