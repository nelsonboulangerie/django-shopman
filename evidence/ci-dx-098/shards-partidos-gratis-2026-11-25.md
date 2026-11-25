# Shards do backstage partidos por peso, medidos na CI grátis (25/11/2026)

Run [45673961882](https://github.com/nelsonboulangerie/django-shopman/actions/runs/45673961882) do `runner-benchmark.yml`, só `ubuntu-latest` (4 vCPU, grátis), 2 repetições, 16/16 verdes. Comparado com o run [45666175682](https://github.com/nelsonboulangerie/django-shopman/actions/runs/45666175682) (mesmo workflow, mesmo runner, shards inteiros). Mediana do job inteiro.

| shard | antes (inteiro) | agora (partido) |
|---|---:|---:|
| backstage seed | 16,3 min | seed-1 8,8 · seed-2 7,9 |
| backstage rest | 17,6 min | rest-1 12,6 · rest-2 10,1 |
| backstage heavy | 12,3 | 12,9 |
| shop rest | 10,2 | 12,7 |
| shop heavy | 7,5 | 9,5 |
| pos-nuxt | 11,0 | 12,5 |

Job mais longo do Runtime Gate: ~17,6 → ~12,9 min, sem custo. Os jobs que não mudaram oscilaram de 1 a 2 min entre os dois runs (horário e carga diferentes; n=2). O próximo limite é o patamar de ~13 min (`heavy`, `shop rest`, `rest-1`) e, no grupo, a cadeia do Surfaces Gate (#3635).
