"""Incidentes: o alerta de produção visto pelo tipo, com dono e prova de volta.

O ``OperatorAlert`` é a fonte única. Daqui saem o resumo por tipo (quem é o dono,
desde quando está aberto, quantas vezes voltou, desde quando está verde) e,
nas fases seguintes, o acionamento dos remédios que o próprio domínio já tem.

O que este pacote NÃO faz: consertar. A cura mora onde a falha nasce (os retries
da Directive, os sweeps e reconciliações do ``maintenance_worker``, os gestos de
cada domínio). Aqui se detecta, se roteia e se confere.
Contrato: docs/reference/incidents.md.
"""
