from app.api.v1.endpoints.profiling_enqueue import EnqueueRequest, _build_queue_payload


def test_build_queue_payload():
    req = EnqueueRequest(
        type="t",
        payload={"x": 1},
        headers={"h": "v"},
        job_id="jid",
        profiling_request_id="prid",
        data_source_id="ds",
        requested_by_user_id="user",
        correlation_id=None,
    )

    payload = _build_queue_payload(req, "corr-id")
    assert "job_id" in payload and payload["job_id"] == "jid"
    assert "profiling_request_id" in payload and payload["profiling_request_id"] == "prid"
    assert payload["correlation_id"] == "corr-id"
    assert isinstance(payload["headers"], dict)
