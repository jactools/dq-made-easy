from __future__ import annotations

from typing import Any


def compose_user_display_name(first_name: object, last_name: object, *, fallback: object = "") -> str:
    parts = [str(part).strip() for part in (first_name, last_name) if str(part or "").strip()]
    if parts:
        return " ".join(parts)
    return str(fallback or "").strip()


def normalize_user_name_parts(first_name: object, last_name: object, *, fallback: object = "") -> tuple[str, str]:
    normalized_first_name = str(first_name or "").strip()
    normalized_last_name = str(last_name or "").strip()
    if normalized_first_name and normalized_last_name:
        return normalized_first_name, normalized_last_name

    fallback_value = str(fallback or "").strip()
    if "@" in fallback_value:
        fallback_value = fallback_value.split("@", 1)[0].strip()
    fallback_value = fallback_value or "User"

    return normalized_first_name or fallback_value, normalized_last_name or fallback_value


def name_parts_from_profile(profile: dict[str, Any], *, fallback: object = "") -> tuple[str, str]:
    first_name = str(
        profile.get("given_name")
        or profile.get("first_name")
        or profile.get("firstName")
        or ""
    ).strip()
    last_name = str(
        profile.get("family_name")
        or profile.get("last_name")
        or profile.get("lastName")
        or ""
    ).strip()

    if not first_name or not last_name:
        display_name = str(profile.get("name") or "").strip()
        if display_name:
            parts = display_name.split(None, 1)
            first_name = first_name or parts[0].strip()
            last_name = last_name or (parts[1].strip() if len(parts) > 1 else parts[0].strip())

    return normalize_user_name_parts(first_name, last_name, fallback=fallback)