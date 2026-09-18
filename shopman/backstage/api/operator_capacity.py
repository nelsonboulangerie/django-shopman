"""Capacidade dos apps de operação — amostra do contêiner + limites do Admin.

``POST /api/v1/backstage/operator/capacity/`` é chamado pelo BFF da layer
``operator-kit`` (rota ``/health/capacity``), nunca pelo navegador direto: o Nitro
lê o próprio contêiner (cgroup ou soma dos processos) e manda a amostra com o cookie do operador. Uma
chamada só faz as três coisas de que a rota precisa — prova que há operador
identificado (``IsBackstageOperator``), devolve os limites de atenção/crítico
que o Admin guarda e anda a regra de aviso (``shop/services/operator_capacity``).

Sem PII: o corpo é um nome de serviço e dois percentuais.
"""

from __future__ import annotations

import logging

from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import IsBackstageOperator
from shopman.shop.operator_capacity_policy import resolve_operator_capacity_policy
from shopman.shop.services.observability import operational_event
from shopman.shop.services.operator_capacity import (
    InvalidCapacitySample,
    evaluate_sample,
    level_for,
    parse_sample,
)

logger = logging.getLogger(__name__)


# Cada aba aberta reporta a cada 30–60 s; com vários apps no mesmo balcão o teto é
# folgado. Passou dele, a leitura continua respondida e só a amostra não conta.
@method_decorator(
    ratelimit(key="user_or_ip", rate="120/m", method="POST", block=False),
    name="dispatch",
)
class OperatorCapacityView(APIView):
    permission_classes = [IsBackstageOperator]

    @extend_schema(tags=["operator"], summary="Report container capacity and read the Admin thresholds")
    def post(self, request):
        try:
            sample = parse_sample(request.data if hasattr(request, "data") else None)
        except InvalidCapacitySample as exc:
            return Response(
                {"detail": "Amostra de capacidade fora do contrato.", "field": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        policy = resolve_operator_capacity_policy()
        if getattr(request, "limited", False):
            recorded = False
            level = level_for(sample.peak, policy)
        else:
            evaluation = evaluate_sample(sample, policy)
            recorded = evaluation.recorded
            level = evaluation.level

        # Folga não vira linha de log a cada 45 s por aba; aperto vira (com quem reportou).
        operational_event(
            "operator_capacity.sample",
            level=logging.INFO if level in {"attention", "critical"} else logging.DEBUG,
            service=sample.service,
            available=sample.available,
            memory_percent=sample.memory_percent,
            cpu_percent=sample.cpu_percent,
            capacity_level=level,
            recorded=recorded,
            actor_id=getattr(request.user, "pk", None),
        )
        return Response(
            {
                "service": sample.service,
                "level": level,
                "recorded": recorded,
                "thresholds": policy.as_payload(),
            }
        )
