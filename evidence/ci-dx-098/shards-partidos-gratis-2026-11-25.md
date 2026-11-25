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

## Com o `shop rest` também partido

Run [45688139461](https://github.com/nelsonboulangerie/django-shopman/actions/runs/45688139461), `ubuntu-latest`, 2 repetições, 18/18 verdes:

| job | min (p50) |
|---|---:|
| pos-nuxt (Surfaces Gate) | 13,0 |
| backstage heavy | 12,6 |
| backstage rest-2 | 10,6 |
| backstage rest-1 | 9,0 |
| backstage seed-2 | 8,5 |
| shop heavy | 8,5 |
| shop rest-2 | 8,1 |
| backstage seed-1 | 7,7 |
| shop rest-1 | 7,5 |

`shop rest` 10,2–12,7 → 7,5 / 8,1 min. O job mais longo do Runtime Gate passou a ser o `backstage heavy` (12,6), e o do grupo, o `pos-nuxt` (Surfaces Gate). Próximos candidatos: partir o `heavy` pelo mesmo mecanismo e encurtar a cadeia do Surfaces Gate (#3635).

## Com o `backstage heavy` também partido

Run [45697517315](https://github.com/nelsonboulangerie/django-shopman/actions/runs/45697517315), `ubuntu-latest`, 2 repetições, 20/20 verdes:

| job | min (p50) |
|---|---:|
| pos-nuxt (Surfaces Gate) | 13,8 |
| backstage rest-2 | 11,6 |
| shop heavy | 10,3 |
| backstage heavy-2 | 10,0 |
| backstage seed-1 | 9,3 |
| backstage seed-2 | 8,9 |
| backstage rest-1 | 8,8 |
| shop rest-1 | 7,3 |
| shop rest-2 | 6,3 |
| backstage heavy-1 | 6,0 |

Job mais longo do Runtime Gate: **17,6 → 11,6 min** ao longo do dia, sem custo. O `heavy` partiu 6,0 × 10,0 na CI contra 647 × 650 s nos pesos locais: o peso relativo de alguns arquivos é outro no runner da CI. É o caso que a vigia corrige, re-medindo os pesos pelo junit da fila (`make shard-weights run=<id>`). Este run saiu mais lento em geral que os anteriores (seed 9,3 contra 7,7): n=2, oscilação entre horários.

## `pos-nuxt`: geometria e navegador juntos (Surfaces Gate)

Linha do tempo de 12 grupos verdes da fila (25/11): a cadeia do Surfaces Gate custa ~0,4 min (jobs criados juntos, espera 0,1 min); o caminho crítico é o próprio `pos-nuxt`, 14,6 min de execução, com geometria (6,2) e navegador (3,9) em série. Dentro da geometria, `saleColumn.spec.ts` sozinho leva 5,1 min num worker: todos os testes dele usam a mesma comanda do mock, que guarda estado, e por isso NÃO se soltou o paralelismo dentro do arquivo.

O que se fez: as duas fases (mock, app, portas e outputDir próprios, provados pelo `surface_contract.mjs validate`) rodam juntas, com largada escalonada. Largando juntas, 1 de 2 rodadas locais estourou 120 s no primeiro teste da geometria (o `nuxt build` do navegador disputou CPU com a compilação a frio do `nuxt dev`). Escalonado: 3/3 local e 5/5 na CI.

Run [45706524929](https://github.com/nelsonboulangerie/django-shopman/actions/runs/45706524929), `ubuntu-latest`, 5 repetições:

| rodada | geometria + navegador juntas | job inteiro |
|---|---:|---:|
| 1 | 341 s | 8,8 min |
| 2 | 365 s | 10,1 min |
| 3 | 493 s | 12,9 min |
| 4 | 517 s | 13,6 min |
| 5 | 376 s | 10,2 min |
| mediana | **376 s (6,3 min)** contra 606 s em série na fila | **10,2 min** contra 14,6 |

As rodadas 3 e 4 caíram em máquinas mais lentas (os testes de componente levaram 182 e 191 s, contra 121 a 136 s nas outras).
