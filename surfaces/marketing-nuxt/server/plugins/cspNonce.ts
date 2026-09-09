export default defineNitroPlugin((nitroApp) => {
  nitroApp.hooks.hook("render:response", (response, { event }) => {
    const nonce = ensureOperatorCspNonce(event);
    if (typeof response.body === "string") {
      response.body = addCspNonceToHtml(response.body, nonce);
    }

    response.headers = Object.fromEntries(
      Object.entries(response.headers || {}).filter(([name]) => name.toLowerCase() !== "x-powered-by"),
    );
    Object.assign(
      response.headers,
      operatorSecurityHeaders(
        nonce,
        OPERATOR_PRIVATE_CACHE_CONTROL,
        import.meta.dev,
      ),
    );
  });
});
