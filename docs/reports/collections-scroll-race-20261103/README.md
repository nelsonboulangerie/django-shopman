# Corrida no teste da faixa de coleções

Owner: coordenação Codex. Escopo restrito ao teste `collectionsStrip.spec.ts`.

O sintético da #2112 `a0e8df1a4c15d83b027154eb4881943bba17ed03`, run41673199414/job126047089508, falhou no segundo clique da seta em1024px. O trace mostra clique às27023ms, espera fixa400ms, isEnabled às27487ms e clique às27503ms já desabilitado pela conclusão da rolagem suave. Os99demais cenários browser passaram.

A correção0168bcd6d foi publicada na #2112 e o job pos-nuxt do head passou, mas a PR foi fechada por supersessão da UI pela #2113. O main após #2115 ainda contém a pausa fixa; esta frente preserva exclusivamente o teste, sem reaplicar UI, baselines ou aceite. Próximo passo: reaplicar a espera pela posição destino e estado do botão, validar, publicar e enfileirar.
