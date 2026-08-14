"""Backstage admin — KDS, closing, alerts, cash register, operation, dashboard."""

from shopman.backstage.admin.alerts import OperatorAlertAdmin  # noqa: F401
from shopman.backstage.admin.cash_register import CashShiftAdmin, POSTerminalAdmin  # noqa: F401
from shopman.backstage.admin.closing import DayClosingAdmin  # noqa: F401
from shopman.backstage.admin.kds import KDSInstanceAdmin  # noqa: F401
from shopman.backstage.admin.operation import (  # noqa: F401
    OperationChecklistRunAdmin,
    OperationChecklistTemplateAdmin,
    OperationTaskRunAdmin,
    OperationTaskTemplateAdmin,
)
from shopman.backstage.admin.operators import PinCredentialAdmin  # noqa: F401
from shopman.backstage.admin.pos import POSTabAdmin  # noqa: F401

# Por último: o backstage é o último app do INSTALLED_APPS, então neste ponto
# todo mundo (Core e shop) já registrou o que tinha para registrar.
from shopman.backstage.admin.curation import hide_curated_screens  # noqa: E402

hide_curated_screens()
