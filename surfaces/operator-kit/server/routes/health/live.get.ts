// Liveness do BFF: processo Nitro vivo, sem chamar o Django. É o health check
// da plataforma para os oito apps de operador (ver server/utils/healthProbe.ts).
import { defineEventHandler } from "h3";
import { ProbeRateLimiter, respondHealthLive } from "../../utils/healthProbe";

const limiter = new ProbeRateLimiter();

export default defineEventHandler((event) => respondHealthLive(event, limiter));
