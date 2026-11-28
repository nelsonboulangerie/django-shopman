# Benchmark Ubicloud `ubicloud-standard-4` × `ubuntu-latest` (26/11/2026)

Run [45788867113](https://github.com/nelsonboulangerie/django-shopman/actions/runs/45788867113) do `runner-benchmark.yml`: mesmo commit, ao mesmo tempo, 3 repetições. Mesmos 4 vCPU nos dois lados, para isolar a velocidade POR NÚCLEO (o que faltou no 8-core do GitHub). A Ubicloud mandou 29 dos 30 jobs para o "premium" (AMD Ryzen 9 7950X3D) e 1 para o padrão (AMD EPYC 9454P). Custo real no console: **US$ 1,02** (~260 min, ~US$ 0,004/min).

| job | ubuntu-latest | Ubicloud | aceleração |
|---|---:|---:|---:|
| **pos-nuxt** (navegador) | 13,2 min | premium 8,3 (n=2) · padrão 7,8 (n=1) | **1,59x–1,71x** |
| backstage seed-1 | 8,0 | 7,0 | 1,15x |
| shop heavy | 7,4 | 6,3 | 1,17x |
| backstage rest-1 | 12,5 | 11,1 | 1,12x |
| backstage seed-2 | 8,6 | 7,9 | 1,09x |
| shop rest-2 | 6,7 | 6,6 | 1,01x |
| backstage heavy-2 | 8,7 | 8,8 | 0,98x |
| backstage rest-2 | 8,4 | 10,0 | 0,85x |
| backstage heavy-1 | 5,6 | 7,1 | 0,79x |

`shop rest-1` reprovou nas 6 rodadas (grátis e Ubicloud): bomba-relógio de data num teste do iFood, consertada no #3642. Não é da máquina.

**Leitura:** o job de NAVEGADOR (`pos-nuxt`) acelera 1,6–1,7x num processador mais rápido por núcleo, o que o 8-core (mais núcleos, mesmo processador) não deu. As suítes Python ficam em ~1,0x: o ganho delas já veio, de graça, da divisão em shards. Pela regra (≥ 1,4x), a Ubicloud passa **só para a classe de jobs de navegador**, nunca para os shards Python.
