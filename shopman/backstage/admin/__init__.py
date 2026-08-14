"""Backstage admin — KDS, closing, alerts, cash register, operation, dashboard."""

from shopman.backstage.admin.alerts import OperatorAlertAdmin  # noqa: F401
from shopman.backstage.admin.cash_register import CashShiftAdmin, POSTerminalAdmin  # noqa: F401
from shopman.backstage.admin.closing import DayClosingAdmin  # noqa: F401
from shopman.backstage.admin.curation import hide_curated_screens  # noqa: F401
from shopman.backstage.admin.kds import KDSInstanceAdmin  # noqa: F401
from shopman.backstage.admin.operation import (  # noqa: F401
    OperationChecklistRunAdmin,
    OperationChecklistTemplateAdmin,
    OperationTaskRunAdmin,
    OperationTaskTemplateAdmin,
)
from shopman.backstage.admin.operators import PinCredentialAdmin  # noqa: F401
from shopman.backstage.admin.pos import POSTabAdmin  # noqa: F401

# Depois de todo mundo registrar: o backstage é o último app do INSTALLED_APPS, e
# esta chamada é a última linha do módulo, então Core e shop já colocaram no site
# tudo que tinham para colocar. Tirar antes disso não tiraria nada.
hide_curated_screens()
