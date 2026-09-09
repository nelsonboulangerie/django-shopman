export default defineEventHandler((event) => {
  applyOperatorSecurityHeaders(event, {
    cacheControl: isImmutableOperatorAssetPath(event.path)
      ? OPERATOR_IMMUTABLE_CACHE_CONTROL
      : OPERATOR_PRIVATE_CACHE_CONTROL,
  });
});
