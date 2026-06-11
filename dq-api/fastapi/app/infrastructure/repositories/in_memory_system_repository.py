from app.domain.interfaces.v1.system_repository import SystemRepository


class InMemorySystemRepository(SystemRepository):
    def get_system_info(self) -> dict[str, str | None]:
        return {
            "dbSchemaVersion": "unknown",
            "dbSchemaUpdated": None,
            "dbGitCommit": None,
        }

    def get_suggestions_metrics_summary(self) -> dict:
        return {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "successRate": 1,
            "operations": [],
        }