import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useRecipeBookAccess } from "~/composables/useRecipeBookAccess";

const env = installNuxtGlobals();

describe("useRecipeBookAccess", () => {
  beforeEach(() => env.reset());

  it("exposes the three flags from the access probe", () => {
    env.fetchData.value = { access: { can_view: true, can_edit: true, capture_available: false } };
    const { canView, canEdit, captureAvailable } = useRecipeBookAccess();
    expect(canView.value).toBe(true);
    expect(canEdit.value).toBe(true);
    expect(captureAvailable.value).toBe(false);
  });

  it("read-only operator: sees the rail entry, never the write affordances", () => {
    env.fetchData.value = { access: { can_view: true, can_edit: false, capture_available: true } };
    const { canView, canEdit, captureAvailable } = useRecipeBookAccess();
    expect(canView.value).toBe(true);
    expect(canEdit.value).toBe(false);
    expect(captureAvailable.value).toBe(true);
  });

  it("hides everything without a payload (403 probe, floor operator)", () => {
    env.fetchData.value = null;
    const { canView, canEdit, captureAvailable } = useRecipeBookAccess();
    expect(canView.value).toBe(false);
    expect(canEdit.value).toBe(false);
    expect(captureAvailable.value).toBe(false);
  });

  it("an error wins over a stale payload (fails closed)", () => {
    env.fetchData.value = { access: { can_view: true, can_edit: true, capture_available: true } };
    env.fetchError.value = { status: 403 };
    const { canView, canEdit } = useRecipeBookAccess();
    expect(canView.value).toBe(false);
    expect(canEdit.value).toBe(false);
  });
});
