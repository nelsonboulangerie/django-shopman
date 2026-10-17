export type GestorSurfaceRole = "orders" | "expedition" | "catalog";

/** Landing declarada pelo servidor, fechada ao vocabulário do Gestor. */
export function gestorLandingPath(
  role: GestorSurfaceRole | null | undefined,
  projectedPath?: string,
): "/" | "/catalog" {
  if (role === "catalog" && projectedPath === "/catalog") return "/catalog";
  return "/";
}
