from typing import Protocol

from app.domain.entities import SuggestionsMetricsSummaryEntity
from app.domain.entities import SystemDatabaseInfoEntity


class SystemRepository(Protocol):
    def get_system_info(self) -> SystemDatabaseInfoEntity: ...

    def get_suggestions_metrics_summary(self) -> SuggestionsMetricsSummaryEntity: ...