# linux-4core × ubuntu-latest, por job (fila de 18, 19 e 21/11/2026)

Execução p50 (started→completed) dos jobs verdes do Runtime e do Surfaces Gate no `merge_group`, separados pelo rótulo do runner. Gerado por `scripts/ci_baseline.py` (cache) em 25/11/2026.

| job | n std | p50 std | n 4core | p50 4core | aceleração |
|---|---:|---:|---:|---:|---:|
| Surfaces Gate › pos-nuxt | 515 | 14.6 | 21 | 13.1 | 1.12x |
| Runtime Gate › Backstage rest | 498 | 13.9 | 46 | 13.9 | 1.00x |
| Runtime Gate › Backstage heavy | 537 | 13.0 | 60 | 12.6 | 1.03x |
| Runtime Gate › Backstage seed | 536 | 12.0 | 59 | 11.8 | 1.02x |
| Surfaces Gate › purchase-nuxt | 527 | 11.2 | 58 | 11.0 | 1.02x |
| Surfaces Gate › Preview interno — kitchensink-nuxt | 539 | 10.3 | 58 | 10.7 | 0.97x |
| Runtime Gate › PostgreSQL + Redis runtime stress gate | 541 | 9.9 | 60 | 9.8 | 1.01x |
| Runtime Gate › Shop rest | 456 | 9.1 | 52 | 9.0 | 1.01x |
| Surfaces Gate › orders-nuxt | 532 | 9.0 | 58 | 8.6 | 1.05x |
| Runtime Gate › Quality + deploy contract | 541 | 8.0 | 59 | 7.5 | 1.07x |
| Runtime Gate › Shop heavy | 510 | 7.2 | 59 | 6.9 | 1.04x |
| Surfaces Gate › production-nuxt | 509 | 6.3 | 51 | 6.2 | 1.01x |
| Runtime Gate › Testes (test-storefront) | 515 | 6.0 | 58 | 6.0 | 1.00x |
| Surfaces Gate › operator-kit | 544 | 5.7 | 58 | 5.2 | 1.09x |
| Surfaces Gate › PWA — orders | 540 | 5.6 | 57 | 5.7 | 0.99x |
| Surfaces Gate › bi-nuxt | 544 | 4.2 | 58 | 4.0 | 1.04x |
| Surfaces Gate › marketing-nuxt | 563 | 4.1 | 40 | 3.9 | 1.07x |
| Surfaces Gate › kds-nuxt | 545 | 3.9 | 58 | 3.8 | 1.03x |
| Runtime Gate › Testes (test-cores) | 542 | 3.5 | 58 | 3.4 | 1.01x |
| Runtime Gate › Admin/Unfold gate | 542 | 3.3 | 58 | 3.4 | 0.97x |
| Surfaces Gate › PWA — pos | 545 | 3.3 | 58 | 3.2 | 1.04x |
| Surfaces Gate › PWA — production | 542 | 3.1 | 58 | 3.0 | 1.01x |
| Surfaces Gate › PWA — marketing | 544 | 3.0 | 58 | 2.9 | 1.06x |
| Surfaces Gate › PWA — bi | 544 | 2.9 | 58 | 2.7 | 1.05x |
| Surfaces Gate › PWA — kds | 544 | 2.8 | 58 | 2.8 | 1.00x |
| Surfaces Gate › PWA — hub | 544 | 2.8 | 58 | 2.6 | 1.05x |
| Runtime Gate › Docker deploy image | 542 | 2.6 | 60 | 2.6 | 0.98x |
| Surfaces Gate › PWA — purchase | 545 | 2.4 | 58 | 2.3 | 1.03x |
| Surfaces Gate › storefront-nuxt | 545 | 2.0 | 58 | 2.1 | 0.97x |
| Runtime Gate › Testes (test-counter-agent) | 542 | 1.7 | 58 | 1.7 | 1.00x |
| Surfaces Gate › PWA — storefront | 541 | 1.7 | 58 | 1.6 | 1.02x |
| Surfaces Gate › hub-nuxt | 544 | 1.0 | 58 | 1.0 | 1.02x |
| Runtime Gate › Coverage Gate | 385 | 0.7 | 41 | 0.6 | 1.05x |
| Surfaces Gate › PWA — status | 544 | 0.6 | 58 | 0.6 | 1.01x |
| Surfaces Gate › status-nuxt | 545 | 0.6 | 58 | 0.6 | 1.00x |
| Runtime Gate › Gate da meia-correção | 543 | 0.3 | 60 | 0.3 | 1.06x |
| Surfaces Gate › Versões das superfícies | 547 | 0.2 | 59 | 0.2 | 1.08x |
| Surfaces Gate › Supply chain — operator-kit | 546 | 0.2 | 58 | 0.2 | 1.17x |
| Surfaces Gate › Supply chain — marketing | 546 | 0.2 | 58 | 0.2 | 1.17x |
| Surfaces Gate › Contrato canônico das superfícies | 547 | 0.2 | 58 | 0.2 | 1.00x |
| Runtime Gate › Escopo do PR | 480 | 0.1 | 62 | 0.1 | 0.83x |
| Surfaces Gate › Escopo do PR | 484 | 0.1 | 59 | 0.1 | 0.83x |
| Runtime Gate › Testes (test-shop) | 439 | 0.1 | 51 | 0.1 | 1.00x |
| Runtime Gate › Testes (test-backstage) | 495 | 0.1 | 44 | 0.1 | 1.00x |
