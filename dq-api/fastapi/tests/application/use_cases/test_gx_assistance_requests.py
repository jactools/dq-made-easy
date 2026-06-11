from __future__ import annotations

from urllib.parse import unquote

import pytest
from fastapi import HTTPException

from app.application.use_cases.gx_assistance_requests import build_gx_assistance_mailto_url
from app.application.use_cases.gx_assistance_requests import RequestGxAssistanceCommand
from app.application.use_cases.gx_assistance_requests import request_gx_assistance


@pytest.mark.anyio
async def test_request_gx_assistance_email_infers_run_plan_version_from_error_message() -> None:
    result = await request_gx_assistance(
        command=RequestGxAssistanceCommand(
            assistance_mode="email",
            recipient_email="ops@example.com",
            it_system="",
            endpoint_url="",
            itsm_auth_token="",
            correlation_id="corr-42",
            run_plan_id=None,
            run_plan_version_id=None,
            workspace_id=None,
            error_message="run plan version ' rpv-42 ' failed",
            diagnostics=[],
        ),
        send_itsm_request=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("not used")),
    )

    assert result.mailto_url is not None
    assert "rpv-42" in unquote(result.mailto_url)


@pytest.mark.anyio
async def test_request_gx_assistance_email_uses_unknown_version_when_absent() -> None:
    result = await request_gx_assistance(
        command=RequestGxAssistanceCommand(
            assistance_mode="email",
            recipient_email="ops@example.com",
            it_system="",
            endpoint_url="",
            itsm_auth_token="",
            correlation_id="corr-43",
            run_plan_id=None,
            run_plan_version_id=None,
            workspace_id=None,
            error_message="no run plan version present",
            diagnostics=[],
        ),
        send_itsm_request=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("not used")),
    )

    assert result.mailto_url is not None
    assert "unknown-run-plan-version" in unquote(result.mailto_url)


def test_build_gx_assistance_mailto_url_includes_diagnostics_and_defaults() -> None:
    mailto = unquote(
        build_gx_assistance_mailto_url(
            "ops@example.com",
            run_plan_id=None,
            run_plan_version_id="rpv-77",
            workspace_id=None,
            error_message="Validation failed for run plan version 'rpv-77'",
            diagnostics=[{"message": "Expectation failed", "reason": "invalid_contract"}],
            correlation_id="corr-77",
        )
    )

    assert mailto.startswith("mailto:ops@example.com?")
    assert "GX run plan validation assistance requested: rpv-77" in mailto
    assert "Workspace: n/a" in mailto
    assert "Run plan: n/a" in mailto
    assert "Run plan version: rpv-77" in mailto
    assert "Correlation ID: corr-77" in mailto
    assert '"reason": "invalid_contract"' in mailto


def test_build_gx_assistance_mailto_url_omits_diagnostics_when_absent() -> None:
    mailto = unquote(
        build_gx_assistance_mailto_url(
            "ops@example.com",
            run_plan_id="run-plan-1",
            run_plan_version_id="rpv-explicit",
            workspace_id="workspace-1",
            error_message="Validation failed",
            diagnostics=None,
            correlation_id="corr-explicit",
        )
    )

    assert "Run plan version: rpv-explicit" in mailto
    assert "Diagnostics:" not in mailto


@pytest.mark.anyio
async def test_request_gx_assistance_email_requires_recipient() -> None:
    with pytest.raises(HTTPException) as error:
        await request_gx_assistance(
            command=RequestGxAssistanceCommand(
                assistance_mode="email",
                recipient_email="",
                it_system="",
                endpoint_url="",
                itsm_auth_token="",
                correlation_id="corr-missing-email",
                run_plan_id=None,
                run_plan_version_id=None,
                workspace_id=None,
                error_message="Validation failed",
                diagnostics=[],
            ),
            send_itsm_request=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("not used")),
        )

    assert error.value.status_code == 400
    assert error.value.detail["error"] == "assistance_email_missing"