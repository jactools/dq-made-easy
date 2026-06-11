from app.api.v1.schemas.auth_view import LoginResponseView


def resolve_login_response_view(payload: dict) -> LoginResponseView:
    return LoginResponseView.model_validate(payload)
