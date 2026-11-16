"""A hora do Django no padrão da casa: "12h45" (dono, 16/11/2026).

O Admin escreve toda coluna de data nativa (``DateTimeField`` no changelist, campo
somente leitura, o filtro ``|date`` sem argumento) com o formato do locale. O do
``pt-br`` embarcado termina em hora, dois-pontos e minuto; este módulo troca só essa
ponta, e o resto do locale (data, moeda, separadores) continua vindo do Django.

A regra está em ``docs/reference/suite-vocabulary.md``, seção "Hora". O que o código
formata à mão passa por ``shopman.utils.formatting.format_clock``; isto aqui cobre o
que o Django formata sozinho.

⚠️ A linguagem de formato do Django não omite o minuto: a hora cheia sai "9h00" aqui,
e "9h" em todo o resto. É a única borda que sobra, e só no Admin.

``G`` é a hora de 0 a 23 sem zero à esquerda; ``h`` e ``s`` são letras de formato e
por isso vão escapadas. Campo de formulário não muda: os ``*_INPUT_FORMATS`` seguem
os do Django, como o ``<input type="time">`` do browser.
"""

DATETIME_FORMAT = r"j \d\e F \d\e Y \à\s G\hi"
SHORT_DATETIME_FORMAT = r"d/m/Y G\hi"
TIME_FORMAT = r"G\hi"
