import { describe, expect, it } from "vitest";
import {
  operatorSessionState,
  type OperatorSessionRequestStatus,
} from "../app/presentation/operatorSessionState";
import type { OperatorSession } from "../app/types/operator";

const session = (over: Partial<OperatorSession> = {}): OperatorSession => ({
  station: "balcao",
  operator: { id: 7, username: "bia", name: "Bia" },
  locked: false,
  pin_must_change: false,
  authorized: true,
  ...over,
});

function state(
  over: Partial<{
    expired: boolean;
    requestStatus: OperatorSessionRequestStatus;
    session: OperatorSession | null;
  }> = {},
) {
  return operatorSessionState({
    expired: false,
    requestStatus: "success",
    session: session(),
    ...over,
  });
}

describe("operatorSessionState", () => {
  it("does not authenticate while the session is still being checked", () => {
    expect(state({ requestStatus: "idle" })).toBe("checking");
    expect(state({ requestStatus: "pending" })).toBe("checking");
  });

  it("distinguishes authenticated, anonymous, expired and forbidden", () => {
    expect(state()).toBe("authenticated");
    expect(state({ session: session({ operator: null, locked: true }) })).toBe("anonymous");
    expect(state({ expired: true })).toBe("expired");
    expect(state({ session: session({ authorized: false }) })).toBe("forbidden");
  });

  it("never treats a forced PIN change as authenticated", () => {
    expect(state({ session: session({ pin_must_change: true }) })).toBe("anonymous");
  });
});
