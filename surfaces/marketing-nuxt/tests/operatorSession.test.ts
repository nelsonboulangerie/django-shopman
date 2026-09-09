import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  flagMarketingSessionError,
  operatorSessionOnError,
} from "~/utils/operatorSession";
import {
  MARKETING_DECISION_REAUTH_STATE,
  PENDING_MARKETING_DECISION_STATE,
} from "~/presentation/marketingDecisionSession";
import { ref } from "vue";

const flagIfUnauthenticated = vi.fn();
const flagIfStationLocked = vi.fn();
const refreshNuxtData = vi.fn();
const states = new Map<string, ReturnType<typeof ref>>();

beforeEach(() => {
  flagIfUnauthenticated.mockReset().mockReturnValue(false);
  flagIfStationLocked.mockReset().mockReturnValue(false);
  refreshNuxtData.mockReset();
  states.clear();
  Object.assign(globalThis, {
    useOperatorSession: () => ({ flagIfUnauthenticated }),
    useStationLock: () => ({ flagIfStationLocked }),
    refreshNuxtData,
    useState: (key: string, init: () => unknown) => {
      if (!states.has(key)) states.set(key, ref(init()));
      return states.get(key)!;
    },
  });
});

describe("Marketing session error policy", () => {
  it("re-gates an expired 401", () => {
    flagIfUnauthenticated.mockReturnValue(true);

    expect(flagMarketingSessionError({ status: 401 })).toBe(true);
    expect(refreshNuxtData).toHaveBeenCalledWith("operator-session");
  });

  it("downgrades an open challenge to actor-bound intent on a read-side 401", () => {
    flagIfUnauthenticated.mockReturnValue(true);
    states.set(
      PENDING_MARKETING_DECISION_STATE,
      ref({
        announcementId: 42,
        action: "approve",
        href: "/api/v1/backstage/marketing/announcements/42/approve/",
        body: { base_version: 7 },
        idempotencyKey: "read-expiry-key",
        ownerRef: "operator:7",
        challenge: { token: "must-not-survive" },
      }),
    );

    flagMarketingSessionError({ status: 401 });

    expect(states.get(PENDING_MARKETING_DECISION_STATE)?.value).toBeNull();
    expect(states.get(MARKETING_DECISION_REAUTH_STATE)?.value).toMatchObject({
      idempotencyKey: "read-expiry-key",
      ownerRef: "operator:7",
    });
    expect(
      states.get(MARKETING_DECISION_REAUTH_STATE)?.value,
    ).not.toHaveProperty("challenge");
  });

  it("does not turn a capability 403 into authentication", () => {
    const denied = { status: 403, data: { detail: "Sem permissão." } };

    expect(flagMarketingSessionError(denied)).toBe(false);
    expect(flagIfUnauthenticated).toHaveBeenCalledWith(denied);
    expect(flagIfStationLocked).toHaveBeenCalledWith(denied);
    expect(refreshNuxtData).not.toHaveBeenCalled();
  });

  it("reopens only the station lock for station_locked", () => {
    flagIfStationLocked.mockReturnValue(true);

    operatorSessionOnError({
      response: {
        status: 403,
        _data: { error: { code: "station_locked" } },
      },
    });

    expect(flagIfStationLocked).toHaveBeenCalledWith({
      status: 403,
      data: { error: { code: "station_locked" } },
    });
    expect(refreshNuxtData).toHaveBeenCalledWith("operator-session");
  });
});
