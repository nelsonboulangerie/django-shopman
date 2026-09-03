"""Concierge de WhatsApp: venda conversacional sobre o Shopman.

Divisão de trabalho, por módulo:

- ``service``   — a porta: recebe a mensagem (``receive_inbound``), roda o turno
                  (``run_turn``) e devolve a resposta pelo transporte.
- ``agent``     — o laço com o modelo: prompt, janela de memória, chamadas de
                  ferramenta, orçamento de tokens. Não conhece HTTP nem ManyChat.
- ``tools``     — as ferramentas: funções determinísticas sobre services do
                  Shopman (catálogo, disponibilidade, sacola, prazo, checkout,
                  pagamento, acompanhamento). O modelo escolhe QUAL chamar; o
                  código decide o QUE responder. Nenhum preço nasce no texto.
- ``prompt``    — o texto do sistema e a voz da casa.
- ``transport`` — falar com o ManyChat (enviar texto, ligar/desligar handoff).

Regra da casa (ADR-026): a língua é do modelo, o dinheiro é do código.
"""
