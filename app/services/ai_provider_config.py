"""Persistent AI provider profiles shared by API settings and layer generation."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import uuid
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QSettings


def _dedupe_models(values) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values or []:
        model = str(value or "").strip()
        if model and model not in seen:
            seen.add(model)
            result.append(model)
    return result


@dataclass
class AIProviderProfile:
    profile_id: str
    name: str
    base_url: str = ""
    generation_endpoint: str = "/v1/images/generations"
    models_endpoint: str = "/v1/models"
    api_key: str = ""
    auth_mode: str = "bearer"  # bearer | x-api-key | none
    model_field: str = "model"
    models: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.profile_id = str(self.profile_id or uuid.uuid4().hex)
        self.name = str(self.name or "未命名接口").strip()
        self.models = _dedupe_models(self.models)
        if self.auth_mode not in {"bearer", "x-api-key", "none"}:
            self.auth_mode = "bearer"
        if self.model_field not in {"model", "model_name"}:
            self.model_field = "model"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "base_url": self.base_url,
            "generation_endpoint": self.generation_endpoint,
            "models_endpoint": self.models_endpoint,
            "api_key": self.api_key,
            "auth_mode": self.auth_mode,
            "model_field": self.model_field,
            "models": list(self.models),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AIProviderProfile":
        data = data or {}
        return cls(
            profile_id=str(data.get("profile_id") or uuid.uuid4().hex),
            name=str(data.get("name") or "未命名接口"),
            base_url=str(data.get("base_url") or ""),
            generation_endpoint=str(data.get("generation_endpoint") or "/v1/images/generations"),
            models_endpoint=str(data.get("models_endpoint") or "/v1/models"),
            api_key=str(data.get("api_key") or ""),
            auth_mode=str(data.get("auth_mode") or "bearer"),
            model_field=str(data.get("model_field") or "model"),
            models=list(data.get("models") or []),
        )


class AIProviderStore:
    SETTINGS_ORG = "批图王"
    SETTINGS_APP = "AIAssetStudio"

    def __init__(self, settings: Optional[QSettings] = None):
        self.settings = settings or QSettings(self.SETTINGS_ORG, self.SETTINGS_APP)

    def load_profiles(self) -> List[AIProviderProfile]:
        raw = str(self.settings.value("profiles_json", "") or "")
        if raw:
            try:
                values = json.loads(raw)
                return [AIProviderProfile.from_dict(item) for item in values if isinstance(item, dict)]
            except (TypeError, ValueError, json.JSONDecodeError):
                pass

        legacy = self._load_legacy_profile()
        return [legacy] if legacy else []

    def save_profiles(self, profiles: List[AIProviderProfile], active_profile_id: str = ""):
        values = [profile.to_dict() for profile in profiles]
        self.settings.setValue("profiles_json", json.dumps(values, ensure_ascii=False))
        valid_ids = {profile.profile_id for profile in profiles}
        active = active_profile_id if active_profile_id in valid_ids else (profiles[0].profile_id if profiles else "")
        self.settings.setValue("active_profile_id", active)

    def active_profile_id(self) -> str:
        return str(self.settings.value("active_profile_id", "") or "")

    def active_profile(self) -> Optional[AIProviderProfile]:
        profiles = self.load_profiles()
        active_id = self.active_profile_id()
        return next((profile for profile in profiles if profile.profile_id == active_id), profiles[0] if profiles else None)

    def _load_legacy_profile(self) -> Optional[AIProviderProfile]:
        base_url = str(self.settings.value("base_url", "") or "")
        endpoint = str(self.settings.value("endpoint", "") or "")
        api_key = str(self.settings.value("api_key", "") or "")
        default_model = str(self.settings.value("default_model", "") or "")
        if not any((base_url, endpoint, api_key, default_model)):
            return None
        return AIProviderProfile(
            profile_id="legacy-default",
            name="默认接口",
            base_url=base_url,
            generation_endpoint=endpoint or "/v1/images/generations",
            api_key=api_key,
            model_field=str(self.settings.value("model_field", "model") or "model"),
            models=[default_model] if default_model else [],
        )
