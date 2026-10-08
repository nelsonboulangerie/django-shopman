// Contrato gerado pelo Django (fonte única: projections bi_*). Regenerar com
// `python manage.py export_bi_schema`; o teste de drift falha se divergir.
export type {
  BICashDay,
  BICashHourRow,
  BICashMethodRow,
  BICashOperatorRow,
  BICashReport,
  BIChangeReport,
  BIConsumptionProfilesReport,
  BICustomerSegmentRow,
  BICustomersReport,
  BICustomersWeekRow,
  BIForecastReport,
  BIOvenTimeRow,
  BIOverShortHour,
  BIOverShortLot,
  BIOverShortReport,
  BIOverShortRow,
  BIOverShortSummary,
  BIOverShortTypical,
  BIOverShortUnavailable,
  BIOverShortAnswerGroup,
  BIProductionDay,
  BIProductionReport,
  BIProfileBand,
  BIProfileBeverage,
  BIProfileCategoryRow,
  BIProfileRange,
  BIProfileReading,
  BIProfileRow,
  BIProfileSensitivity,
  BIProfilesPrevious,
  BIRevpashRow,
  BISalesChannelRow,
  BISalesChannelOption,
  BISalesDay,
  BISalesReport,
  BIStrikeCell,
  BIScenario,
  BIScenarioFocus,
  BIScenarioReportView,
  BIScenariosPage,
  BISourceConflict,
  BITopSkuRow,
  ChangeHabit,
  ChangeMix,
  DayChangeForecast,
  DayForecast,
  Expectation,
  ForecastBasis,
  ForecastBranch,
  ForecastOccasion,
  OccasionYear,
} from "~/generated/biContract";

/**
 * A resposta de toda leitura do B.I. (`shopman/backstage/api/bi.py::_bi_reading`):
 * o relatório em `bi` e, fora dele, a hora em que o SERVIDOR o gerou (ISO com fuso).
 * É o carimbo que o `ReadFreshness` mostra.
 */
export interface BIReading<T> {
  bi: T;
  generated_at?: string | null;
}
