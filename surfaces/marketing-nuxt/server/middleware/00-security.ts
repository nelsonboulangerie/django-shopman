export default defineEventHandler((event) => {
  applyOperatorSecurityHeaders(event, {
    // Vite dev injeta CSS HMR em <style> criado no browser, portanto não
    // consegue receber o nonce por request do SSR. A exceção existe apenas no
    // bundle dev; produção continua exigindo nonce/self.
    allowUnsafeInlineStyleElements: import.meta.dev,
    cacheControl: isImmutableOperatorAssetPath(event.path)
      ? OPERATOR_IMMUTABLE_CACHE_CONTROL
      : OPERATOR_PRIVATE_CACHE_CONTROL,
  });
});
