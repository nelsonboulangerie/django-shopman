import { ref } from "vue";
import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useRecipeBook } from "~/composables/useRecipeBook";
import { useRecipeEntry } from "~/composables/useRecipeEntry";
import { useRecipeFavorite } from "~/composables/useRecipeFavorite";

const env = installNuxtGlobals();

const BOOK = {
  book: {
    entries: [
      { ref: "pao", name: "Pão", is_favorite: false },
      { ref: "brioche", name: "Brioche", is_favorite: true },
    ],
    kinds: [],
    count: 2,
  },
  access: { can_view: true, can_edit: false, capture_available: false },
};

describe("useRecipeFavorite", () => {
  beforeEach(() => env.reset());

  it("POST marks and DELETE unmarks on the favorite endpoint, returning the server state", async () => {
    const { setFavorite } = useRecipeFavorite();
    env.fetchMock.mockResolvedValueOnce({ ref: "pão/1", is_favorite: true });
    expect(await setFavorite("pão/1", true)).toBe(true);
    expect(env.fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/backstage/recipes/p%C3%A3o%2F1/favorite/",
      expect.objectContaining({ method: "POST" }),
    );

    env.fetchMock.mockResolvedValueOnce({ ref: "pao", is_favorite: false });
    expect(await setFavorite("pao", false)).toBe(false);
    expect(env.fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/backstage/recipes/pao/favorite/",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("a refused tap toasts the server message and returns null (the star stays as it was)", async () => {
    env.fetchMock.mockRejectedValueOnce({ status: 403, data: { detail: "Sem permissão." } });
    const { setFavorite, isFavoriteBusy } = useRecipeFavorite();
    expect(await setFavorite("pao", true)).toBeNull();
    expect(env.sonner.error).toHaveBeenCalledWith("Sem permissão.");
    expect(isFavoriteBusy("pao")).toBe(false);
  });

  it("one tap in flight per recipe", async () => {
    let resolve: (value: unknown) => void = () => {};
    env.fetchMock.mockReturnValueOnce(new Promise((r) => (resolve = r)));
    const { setFavorite, isFavoriteBusy } = useRecipeFavorite();
    const first = setFavorite("pao", true);
    expect(isFavoriteBusy("pao")).toBe(true);
    expect(await setFavorite("pao", true)).toBeNull();
    resolve({ ref: "pao", is_favorite: true });
    expect(await first).toBe(true);
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("the star on the inventory and on the recipe", () => {
  beforeEach(() => env.reset());

  it("the inventory lights the card in place, without refetching the list", async () => {
    env.fetchData.value = BOOK;
    const { entries, toggleFavorite } = useRecipeBook(ref(""), ref(""), ref(false));
    env.fetchMock.mockResolvedValueOnce({ ref: "pao", is_favorite: true });
    expect(await toggleFavorite("pao", true)).toBe(true);
    expect(entries.value.map((entry) => [entry.ref, entry.is_favorite])).toEqual([
      ["pao", true],
      ["brioche", true],
    ]);
    expect(env.refresh).not.toHaveBeenCalled();
  });

  it("a failed tap leaves the card as it was", async () => {
    env.fetchData.value = BOOK;
    const { entries, toggleFavorite } = useRecipeBook(ref(""), ref(""), ref(false));
    env.fetchMock.mockRejectedValueOnce({ status: 500 });
    expect(await toggleFavorite("brioche", false)).toBe(false);
    expect(entries.value.find((entry) => entry.ref === "brioche")?.is_favorite).toBe(true);
  });

  it("the recipe detail lights its star in place", async () => {
    env.fetchData.value = { entry: { ref: "pao", name: "Pão", is_favorite: false, versions: [] } };
    const { entry, toggleFavorite, favoriteBusy } = useRecipeEntry("pao");
    env.fetchMock.mockResolvedValueOnce({ ref: "pao", is_favorite: true });
    expect(await toggleFavorite(true)).toBe(true);
    expect(entry.value?.is_favorite).toBe(true);
    expect(favoriteBusy.value).toBe(false);
    expect(env.fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/backstage/recipes/pao/favorite/",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
