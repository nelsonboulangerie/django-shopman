"""
Production Backend Adapter (vNext).

Implements Stockman's ProductionBackend protocol for Craftsman.
This allows Stockman to request production when stock reaches reorder point.

All writes cross the canonical backstage production facade.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from django.utils.module_loading import import_string
from shopman.craftsman.conf import get_setting
from shopman.craftsman.exceptions import CraftError

if TYPE_CHECKING:
    from shopman.stockman.protocols.production import ProductionResult, ProductionStatus

logger = logging.getLogger(__name__)

# Singleton instance
_lock = threading.Lock()
_production_backend = None


class CraftsmanProductionBackend:
    """
    Implements ProductionBackend for Stockman to request production.

    Usage:
        from shopman.craftsman.contrib.stockman.production import get_production_backend

        backend = get_production_backend()
        result = backend.request_production(ProductionRequest(
            sku="CROISSANT",
            quantity=Decimal("50"),
            target_date=date(2026, 2, 25),
        ))
    """

    def request_production(self, request) -> ProductionResult:
        """
        Request production of a product (Protocol-compliant signature).

        Args:
            request: ProductionRequest dataclass from shopman.stockman.protocols.production
        """

        sku = request.sku
        qty = request.quantity
        target_date = request.target_date
        priority = ""
        if hasattr(request, "priority") and request.priority:
            priority = request.priority.value if hasattr(request.priority, "value") else str(request.priority)
        return self._create_work_order(
            sku,
            qty,
            target_date,
            metadata=dict(request.metadata or {}),
            priority=priority,
            reference=request.reference,
        )

    def request_production_simple(
        self,
        sku: str,
        qty: Decimal,
        *,
        reference: str,
        needed_by: datetime | None = None,
        priority: int = 50,
        metadata: dict | None = None,
    ) -> ProductionResult:
        """Request production — simplified API."""
        target_date = needed_by.date() if needed_by else None
        return self._create_work_order(
            sku,
            qty,
            target_date,
            metadata=dict(metadata or {}),
            priority=priority,
            reference=reference,
        )

    def _create_work_order(
        self,
        sku: str,
        qty: Decimal,
        target_date: date | None,
        metadata: dict | None,
        priority="",
        reference: str | None = None,
    ) -> ProductionResult:
        """Create or replay a request through the authoritative facade."""
        from shopman.craftsman.models import WorkOrder
        from shopman.craftsman.services.recipes import get_active_recipe_for_output_sku
        from shopman.stockman.protocols.production import ProductionResult, ProductionStatusEnum

        try:
            recipe = get_active_recipe_for_output_sku(sku)

            if not recipe:
                return ProductionResult(
                    success=False,
                    message=f"No active recipe found for SKU {sku}",
                )

            effective_date = target_date or timezone.localdate()
            stocking_request = {
                "sku": str(sku),
                "quantity": str(qty),
                "target_date": effective_date.isoformat(),
                "priority": (priority.value if hasattr(priority, "value") else str(priority or "")),
                "reference": str(reference or ""),
                "metadata": dict(metadata or {}),
            }
            request_key = _stocking_request_key(
                reference=reference,
                payload=stocking_request,
            )
            _, work_order_ref, _, _ = _production_commands().plan(
                recipe_id=recipe.pk,
                quantity=qty,
                target_date_value=effective_date,
                reason=f"stocking_request:{reference or sku}",
                actor="stocking:reorder",
                source_ref="stocking:reorder",
                idempotency_key=request_key,
                planning_meta={"stocking_request": stocking_request},
                create_new=True,
            )
            wo = WorkOrder.objects.get(ref=work_order_ref)

            logger.info(
                "Production requested for SKU %s: WorkOrder %s created",
                sku,
                wo.ref,
            )

            return ProductionResult(
                success=True,
                work_order_id=str(wo.pk),
                status=ProductionStatusEnum.PLANNED,
                request_id=f"production:{wo.pk}",
            )

        except (CraftError, ValueError) as e:
            logger.warning("Production request denied for SKU %s: %s", sku, e)
            return ProductionResult(success=False, message=str(e))
        except Exception as e:
            logger.error("Failed to request production for SKU %s: %s", sku, e, exc_info=True)
            return ProductionResult(success=False, message=str(e))

    def check_status(self, request_id: str) -> ProductionStatus | None:
        """Check status of a production request."""
        from shopman.craftsman.models import WorkOrder
        from shopman.stockman.protocols.production import ProductionStatus, ProductionStatusEnum

        try:
            if request_id.startswith("production:"):
                pk = int(request_id.split(":")[1])
                wo = WorkOrder.objects.get(pk=pk)
            else:
                wo = WorkOrder.objects.filter(ref=request_id).first()
                if not wo:
                    return None

            status_map = {
                WorkOrder.Status.PLANNED: ProductionStatusEnum.PLANNED,
                WorkOrder.Status.STARTED: ProductionStatusEnum.STARTED,
                WorkOrder.Status.FINISHED: ProductionStatusEnum.FINISHED,
                WorkOrder.Status.VOID: ProductionStatusEnum.VOIDED,
            }

            return ProductionStatus(
                request_id=f"production:{wo.pk}",
                sku=wo.output_sku,
                quantity=wo.quantity,
                status=status_map[wo.status],
                target_date=wo.target_date,
                estimated_completion=None,
                work_order_id=str(wo.pk),
            )
        except WorkOrder.DoesNotExist:
            return None

    def cancel_request(self, request_id: str, reason: str = "cancelled") -> ProductionResult:
        """Cancel a production request through the authoritative facade."""
        from shopman.craftsman.models import WorkOrder
        from shopman.stockman.protocols.production import ProductionResult, ProductionStatusEnum

        try:
            if request_id.startswith("production:"):
                pk = int(request_id.split(":")[1])
                wo = WorkOrder.objects.get(pk=pk)
            else:
                wo = WorkOrder.objects.filter(ref=request_id).first()
                if not wo:
                    return ProductionResult(
                        success=False,
                        message=f"WorkOrder {request_id} not found",
                    )

            normalized_reason = str(reason or "cancelled").strip() or "cancelled"
            _production_commands().void(
                wo.pk,
                actor="stocking:cancel",
                expected_rev=wo.rev,
                idempotency_key=_stocking_cancel_key(request_id),
                reason=normalized_reason,
            )
            logger.info("Production request %s cancelled: %s", wo.ref, normalized_reason)

            return ProductionResult(
                success=True,
                request_id=request_id,
                status=ProductionStatusEnum.VOIDED,
                work_order_id=str(wo.pk),
            )
        except WorkOrder.DoesNotExist:
            return ProductionResult(
                success=False,
                message=f"WorkOrder {request_id} not found",
            )
        except (CraftError, ValueError) as e:
            logger.warning("Cannot cancel WorkOrder %s: %s", request_id, e)
            return ProductionResult(success=False, message=str(e))
        except Exception as e:
            logger.error("Failed to cancel WorkOrder %s: %s", request_id, e, exc_info=True)
            return ProductionResult(success=False, message=str(e))

    def list_pending(
        self,
        sku: str | None = None,
        target_date: date | None = None,
    ) -> list[ProductionStatus]:
        """List pending production requests."""
        from shopman.craftsman.models import WorkOrder
        from shopman.stockman.protocols.production import ProductionStatus, ProductionStatusEnum

        qs = WorkOrder.objects.filter(
            status__in=[WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED],
            source_ref__startswith="stocking:",
        )

        if sku:
            qs = qs.filter(output_sku=sku)

        if target_date:
            qs = qs.filter(target_date=target_date)

        results = []
        for wo in qs:
            results.append(
                ProductionStatus(
                    request_id=f"production:{wo.pk}",
                    sku=wo.output_sku,
                    quantity=wo.quantity,
                    status=ProductionStatusEnum.PLANNED
                    if wo.status == WorkOrder.Status.PLANNED
                    else ProductionStatusEnum.STARTED,
                    target_date=wo.target_date,
                    estimated_completion=None,
                    work_order_id=str(wo.pk),
                )
            )

        return results


def get_production_backend() -> CraftsmanProductionBackend:
    """Get the production backend instance (singleton)."""
    global _production_backend
    if _production_backend is None:
        with _lock:
            if _production_backend is None:
                _production_backend = CraftsmanProductionBackend()
    return _production_backend


def reset_production_backend():
    """Reset the singleton (useful for testing)."""
    global _production_backend
    _production_backend = None


def _production_commands():
    backend_path = get_setting("PRODUCTION_COMMAND_BACKEND")
    if not backend_path:
        raise CraftError(
            "PRODUCTION_COMMAND_BACKEND_REQUIRED",
            message="O host deve configurar o adaptador canônico de comandos de produção.",
        )
    return import_string(backend_path)()


def _canonical_digest(payload: dict) -> str:
    canonical = json.dumps(
        payload,
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _stocking_request_key(*, reference: str | None, payload: dict) -> str:
    normalized_reference = str(reference or "").strip()
    if normalized_reference:
        return f"stocking:request:ref:{_canonical_digest({'reference': normalized_reference})}"
    raise CraftError(
        "STOCKING_REFERENCE_REQUIRED",
        message="A solicitação de reposição exige uma referência única da tentativa.",
    )


def _stocking_cancel_key(request_id: str) -> str:
    return f"stocking:cancel:{_canonical_digest({'request_id': str(request_id)})}"
