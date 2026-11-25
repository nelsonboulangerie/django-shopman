# Benchmark linux-8core × ubuntu-latest (25/11/2026)

Run [45666175682](https://github.com/nelsonboulangerie/django-shopman/actions/runs/45666175682) do `runner-benchmark.yml`: os 6 jobs que seguram o relógio da fila, mesmo commit, ao mesmo tempo, 3 repetições em cada runner. 36/36 verdes. Mediana de 3.

**Job inteiro** (`ci_baseline.py --compare-runners --run 45666175682`):

| job | ubuntu-latest (4 vCPU, grátis) | linux-8core (8 vCPU, pago) | aceleração |
|---|---:|---:|---:|
| test-backstage-rest | 17,6 min | 12,2 min | 1,44x |
| test-backstage-seed | 16,3 min | 9,0 min | 1,81x |
| test-backstage-heavy | 12,3 min | 10,8 min | 1,14x |
| pos-nuxt | 11,0 min | 10,9 min | 1,01x |
| test-shop-rest | 10,2 min | 9,6 min | 1,07x |
| test-shop-heavy | 7,5 min | 5,9 min | 1,26x |

**Só o passo de teste** (instalação de 1–1,4 min igual nos dois):

| job | grátis | 8-core | aceleração |
|---|---:|---:|---:|
| test-backstage-seed | 14,7 | 7,5 | 1,95x |
| test-backstage-rest | 16,0 | 10,8 | 1,47x |
| test-shop-heavy | 5,9 | 4,5 | 1,31x |
| test-backstage-heavy | 10,9 | 9,2 | 1,19x |
| test-shop-rest | 8,7 | 7,8 | 1,11x |
| pos-nuxt (fases da fila) | 10,5 | 10,3 | 1,02x |

Mediana dos 6 jobs: **1,20x** (regra do piloto: ≥ 1,4x). Custo: ~180 min de 8-core ≈ US$ 4 (estimado pelos minutos; a fatura do dia ainda não fechou).
