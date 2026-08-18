import unittest

from app.services.ai_asset_service import AIAssetService
from app.services.ai_provider_config import AIProviderProfile


class AIProviderConfigTests(unittest.TestCase):
    def test_profile_round_trip_preserves_endpoints_auth_and_custom_models(self):
        profile = AIProviderProfile(
            profile_id="yunwu",
            name="Yunwu",
            base_url="https://api.example.test",
            generation_endpoint="/v1/images/generations",
            models_endpoint="/v1/models",
            api_key="secret",
            auth_mode="bearer",
            model_field="model_name",
            models=["gpt-image-1", "kling-v1", "gpt-image-1"],
            selected_model="kling-v1",
        )

        restored = AIProviderProfile.from_dict(profile.to_dict())

        self.assertEqual(restored.profile_id, "yunwu")
        self.assertEqual(restored.generation_endpoint, "/v1/images/generations")
        self.assertEqual(restored.models_endpoint, "/v1/models")
        self.assertEqual(restored.auth_mode, "bearer")
        self.assertEqual(restored.model_field, "model_name")
        self.assertEqual(restored.models, ["gpt-image-1", "kling-v1"])
        self.assertEqual(restored.selected_model, "kling-v1")

    def test_extract_model_ids_supports_common_api_response_shapes(self):
        response = {
            "data": [{"id": "gpt-image-1"}, {"name": "flux-pro"}],
            "models": ["kling-v1", {"model": "qwen-image"}],
        }

        model_ids = AIAssetService.extract_model_ids(response)

        self.assertEqual(
            model_ids,
            ["gpt-image-1", "flux-pro", "kling-v1", "qwen-image"],
        )


if __name__ == "__main__":
    unittest.main()
