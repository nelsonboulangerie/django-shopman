const DESTINATIONS = {
  orders: "ordersUrl",
  pos: "posUrl",
  production: "productionUrl",
} as const;

export default defineEventHandler((event) => {
  const surface = getRouterParam(event, "surface") || "";
  if (!(surface in DESTINATIONS)) throw createError({ statusCode: 404 });

  const config = useRuntimeConfig(event).public as Record<string, unknown>;
  const target = config[DESTINATIONS[surface as keyof typeof DESTINATIONS]];
  if (typeof target !== "string" || !target.startsWith("http")) {
    throw createError({ statusCode: 503, statusMessage: "Surface indisponível" });
  }
  return sendRedirect(event, target, 302);
});
