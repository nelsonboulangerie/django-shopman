"""Backstage models — KDS, DayClosing, OperatorAlert, CashShift, Operation."""

from .alerts import OperatorAlert
from .bi_view import BIView
from .blind_prep import BlindPrepCode
from .cash_register import CashMovement, CashShift, POSTerminal
from .closing import DayClosing
from .consumption import ConsumptionRole, ProductConsumptionTag, Reading
from .day_context import DayContext, HolidayScope
from .historical_sale import HistoricalSale, HistoricalSaleItem
from .kds import KDSInstance, KDSTicket
from .operation import (
    OperationArea,
    OperationChecklistRun,
    OperationChecklistTemplate,
    OperationChecklistTemplateTask,
    OperationEvidence,
    OperationMoment,
    OperationRunStatus,
    OperationTaskRun,
    OperationTaskStatus,
    OperationTaskTemplate,
)
from .operation_episode import (
    EpisodeStatus,
    OperationEpisode,
    OperationEpisodeKind,
)
from .oven_run import OvenRun
from .pos import POSTab
from .pos_event import POSEvent
from .seating import SeatingSpot, SpotKind
from .shelf_outage import OutageReason, ShelfOutage

__all__ = [
    "OperatorAlert",
    "BIView",
    "BlindPrepCode",
    "CashMovement",
    "CashShift",
    "ConsumptionRole",
    "DayClosing",
    "DayContext",
    "HolidayScope",
    "HistoricalSale",
    "HistoricalSaleItem",
    "KDSInstance",
    "KDSTicket",
    "EpisodeStatus",
    "OperationArea",
    "OperationEpisode",
    "OperationEpisodeKind",
    "OperationChecklistRun",
    "OperationChecklistTemplate",
    "OperationChecklistTemplateTask",
    "OperationEvidence",
    "OperationMoment",
    "OperationRunStatus",
    "OperationTaskRun",
    "OperationTaskStatus",
    "OperationTaskTemplate",
    "OvenRun",
    "POSEvent",
    "POSTab",
    "ProductConsumptionTag",
    "Reading",
    "SeatingSpot",
    "SpotKind",
    "OutageReason",
    "ShelfOutage",
    "POSTerminal",
]
