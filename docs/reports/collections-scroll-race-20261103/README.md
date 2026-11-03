# Corrida no teste da faixa de coleções

Owner: coordenação Codex. Escopo restrito ao teste `collectionsStrip.spec.ts`.

O sintético da #2112 `a0e8df1a4c15d83b027154eb4881943bba17ed03`, run 41673199414, job 126047089508, falhou no segundo clique da seta em 1024 px. O trace mostra clique às 27023 ms, espera fixa de 400 ms, isEnabled às 27487 ms e clique às 27503 ms já desabilitado pela conclusão da rolagem suave. Os 99 demais cenários browser passaram.

A correção `0168bcd6d` foi publicada na #2112 e o job pos-nuxt do head passou, mas a PR foi fechada por supersessão da UI pela #2113. O main após #2115 ainda contém a pausa fixa; esta frente preserva exclusivamente o teste, sem reaplicar UI, baselines ou aceite. A correção agora espera a posição destino e o estado do botão antes do próximo clique. Validação na base atual: Node 22, Chromium pinado, teste focado nas duas larguras com três repetições: `6 passed (35.9s)`. Nenhuma baseline foi regenerada.
