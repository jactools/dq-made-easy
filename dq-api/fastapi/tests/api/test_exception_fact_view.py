from __future__ import annotations

from app.api.v1.schemas.exception_fact_view import DeliveryExceptionSummaryView


def _empty_analytics() -> dict:
    return {
        "total_failed_records": 0,
        "runs_with_failures": 0,
        "trend_buckets": [],
        "top_rules": [],
        "top_data_objects": [],
        "top_reasons": [],
        "reason_trend_buckets": [],
        "reason_fluctuations": [],
    }


def test_delivery_exception_summary_view_requires_classification() -> None:
    view = DeliveryExceptionSummaryView.model_validate(
        {
            "deliveryId": "del-1",
            "analytics": _empty_analytics(),
        }
    )
    assert view.deliveryId == "del-1"
    assert view.objectStorageClassification == ""
    assert view.evidenceClassification == ""


def test_delivery_exception_summary_view_populates_classification() -> None:
    view = DeliveryExceptionSummaryView.model_validate(
        {
            "deliveryId": "del-2",
            "objectStorageClassification": "synthetic_test",
            "evidenceClassification": "synthetic_result",
            "analytics": _empty_analytics(),
        }
    )
    assert view.objectStorageClassification == "synthetic_test"
    assert view.evidenceClassification == "synthetic_result"


def test_delivery_exception_summary_view_model_dump_includes_classification() -> None:
    view = DeliveryExceptionSummaryView.model_validate(
        {
            "deliveryId": "del-3",
            "objectStorageClassification": "real_evidence",
            "evidenceClassification": "real_evidence",
            "analytics": _empty_analytics(),
        }
    )
    dumped = view.model_dump(by_alias=True, mode="json")
    # SnakeModel emits snake_case aliases
    assert dumped["object_storage_classification"] == "real_evidence"
    assert dumped["evidence_classification"] == "real_evidence"
