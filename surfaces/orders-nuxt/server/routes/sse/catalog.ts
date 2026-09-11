export default defineEventHandler((event) => proxyEventStream(event, "/events/catalog/"));
