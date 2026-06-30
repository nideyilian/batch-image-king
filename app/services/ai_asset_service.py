"""AI asset generation and lightweight local image processing service."""

from __future__ import annotations

from dataclasses import dataclass, field
import base64
import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class ImageSource:
    kind: str  # url | base64
    value: str


@dataclass(frozen=True)
class AIAssetRequest:
    base_url: str
    endpoint: str
    api_key: str
    model: str
    prompt: str
    negative_prompt: str = ""
    count: int = 1
    size: str = "1024x1024"
    group_name: str = "ai_assets"
    process_mode: str = "raw"  # raw | cutout | segments
    model_field: str = "model"  # model | model_name
    auth_mode: str = "bearer"  # bearer | x-api-key | none
    timeout: int = 120


@dataclass
class ProcessResult:
    source_path: str
    output_paths: List[str] = field(default_factory=list)
    error: str = ""


@dataclass
class AIAssetResult:
    success: bool
    workspace_dir: str
    raw_paths: List[str] = field(default_factory=list)
    output_paths: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata_path: str = ""


class AIAssetService:
    """Small service boundary for AI asset requests and deterministic post-processing."""

    def __init__(self, asset_root: Optional[str] = None):
        self.asset_root = asset_root or self.default_asset_root()

    @staticmethod
    def default_asset_root() -> str:
        if os.name == "nt":
            base_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
        else:
            base_dir = os.path.join(os.path.expanduser("~"), ".config")
        return os.path.join(base_dir, "批图王", "ai_assets")

    @staticmethod
    def safe_name(value: str, fallback: str = "ai_assets") -> str:
        name = (value or "").strip()
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name)
        name = re.sub(r"\s+", "_", name)
        name = name.strip("._ ")
        return name or fallback

    def create_asset_workspace(self, group_name: str, timestamp: Optional[str] = None) -> str:
        stamp = timestamp or time.strftime("%Y%m%d_%H%M%S")
        root_name = f"{self.safe_name(group_name)}_{stamp}"
        workspace = os.path.join(self.asset_root, root_name)
        for child in ("raw", "cutout", "segments"):
            os.makedirs(os.path.join(workspace, child), exist_ok=True)
        return workspace

    @staticmethod
    def extract_image_sources(response: Any) -> List[ImageSource]:
        sources: List[ImageSource] = []

        def add_value(key: str, value: Any) -> None:
            if not isinstance(value, str) or not value.strip():
                return
            text = value.strip()
            lowered_key = key.lower()
            if lowered_key in {"url", "image_url", "image"} and text.startswith(("http://", "https://")):
                sources.append(ImageSource("url", text))
            elif lowered_key in {"b64_json", "base64", "image_base64"}:
                sources.append(ImageSource("base64", text))
            elif text.startswith("data:image/") and "base64," in text:
                sources.append(ImageSource("base64", text))
            elif (key == "" or lowered_key in {"images", "data"}) and text.startswith(("http://", "https://")):
                sources.append(ImageSource("url", text))

        def walk(value: Any, key: str = "") -> None:
            if isinstance(value, dict):
                for child_key, child_value in value.items():
                    add_value(str(child_key), child_value)
                    if isinstance(child_value, (dict, list, tuple)):
                        walk(child_value, str(child_key))
            elif isinstance(value, (list, tuple)):
                for item in value:
                    add_value(key, item)
                    if isinstance(item, (dict, list, tuple)):
                        walk(item, key)
            else:
                add_value(key, value)

        walk(response)
        deduped: List[ImageSource] = []
        seen = set()
        for source in sources:
            marker = (source.kind, source.value)
            if marker not in seen:
                seen.add(marker)
                deduped.append(source)
        return deduped

    @staticmethod
    def extract_model_ids(response: Any) -> List[str]:
        models: List[str] = []

        def walk(value: Any, parent_key: str = "") -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    lowered = str(key).lower()
                    if lowered in {"id", "name", "model", "model_id"} and isinstance(child, str):
                        text = child.strip()
                        if text:
                            models.append(text)
                    elif isinstance(child, (dict, list, tuple)):
                        walk(child, lowered)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    if isinstance(child, str) and parent_key in {"models", "data", "items"}:
                        text = child.strip()
                        if text:
                            models.append(text)
                    else:
                        walk(child, parent_key)

        walk(response)
        result: List[str] = []
        seen = set()
        for model in models:
            if model not in seen:
                seen.add(model)
                result.append(model)
        return result

    def fetch_models(
        self,
        base_url: str,
        endpoint: str = "/v1/models",
        api_key: str = "",
        auth_mode: str = "bearer",
        timeout: int = 30,
    ) -> List[str]:
        url = self._join_url(base_url, endpoint)
        request = urllib.request.Request(
            url,
            headers=self._request_headers(api_key, auth_mode, include_content_type=False),
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=max(1, int(timeout or 30))) as response:
            body = response.read()
        return self.extract_model_ids(json.loads(body.decode("utf-8-sig")))

    def generate_assets(self, request: AIAssetRequest) -> AIAssetResult:
        workspace = self.create_asset_workspace(request.group_name)
        raw_paths: List[str] = []
        output_paths: List[str] = []
        errors: List[str] = []

        try:
            response = self._post_generation_request(request)
            sources = self.extract_image_sources(response)
            if not sources:
                raise ValueError("API response did not contain image URLs or base64 images")

            for index, source in enumerate(sources[: max(1, int(request.count or 1))], start=1):
                try:
                    raw_path = self._save_source(source, workspace, index, request.timeout)
                    raw_paths.append(raw_path)
                    processed = self.process_local_image(raw_path, workspace, request.process_mode)
                    output_paths.extend(processed.output_paths)
                    if processed.error:
                        errors.append(processed.error)
                except Exception as exc:
                    errors.append(str(exc))
        except Exception as exc:
            errors.append(str(exc))

        metadata_path = self._write_metadata(workspace, request, raw_paths, output_paths, errors)
        return AIAssetResult(
            success=bool(raw_paths) and not errors,
            workspace_dir=workspace,
            raw_paths=raw_paths,
            output_paths=output_paths or raw_paths,
            errors=errors,
            metadata_path=metadata_path,
        )

    def process_local_image(self, source_path: str, workspace: str, mode: str = "raw") -> ProcessResult:
        normalized_mode = (mode or "raw").lower()
        if normalized_mode == "raw":
            return ProcessResult(source_path, [source_path])

        image = Image.open(source_path).convert("RGBA")
        mask = self._build_foreground_mask(image)
        bbox = self._mask_bbox(mask)
        if bbox is None:
            return ProcessResult(source_path, [source_path], "No foreground detected")

        if normalized_mode == "cutout":
            cutout = self._image_with_mask(image, mask).crop(bbox)
            out_path = os.path.join(workspace, "cutout", f"{self._base_file_stem(source_path)}_cutout.png")
            cutout.save(out_path)
            return ProcessResult(source_path, [out_path])

        if normalized_mode != "segments":
            return ProcessResult(source_path, [source_path], f"Unknown process mode: {mode}")

        return ProcessResult(source_path, self._save_segments(image, mask, workspace, source_path))

    def _post_generation_request(self, request: AIAssetRequest) -> Any:
        url = self._join_url(request.base_url, request.endpoint)
        payload = self._build_payload(request)
        headers = self._request_headers(request.api_key, request.auth_mode, include_content_type=True)
        http_request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(http_request, timeout=max(1, int(request.timeout or 120))) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read()
        if content_type.startswith("image/"):
            encoded = base64.b64encode(body).decode("ascii")
            return {"data": [{"b64_json": encoded}]}
        return json.loads(body.decode("utf-8-sig"))

    @staticmethod
    def _request_headers(api_key: str, auth_mode: str, include_content_type: bool = True) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if include_content_type:
            headers["Content-Type"] = "application/json"
        if api_key and auth_mode == "x-api-key":
            headers["x-api-key"] = api_key
        elif api_key and auth_mode != "none":
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    @staticmethod
    def _build_payload(request: AIAssetRequest) -> Dict[str, Any]:
        model_field = request.model_field if request.model_field in {"model", "model_name"} else "model"
        payload: Dict[str, Any] = {
            model_field: request.model,
            "prompt": request.prompt,
            "n": max(1, int(request.count or 1)),
            "size": request.size,
        }
        if request.negative_prompt:
            payload["negative_prompt"] = request.negative_prompt
        return payload

    @staticmethod
    def _join_url(base_url: str, endpoint: str) -> str:
        endpoint = (endpoint or "").strip()
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        base = (base_url or "").strip().rstrip("/") + "/"
        return urllib.parse.urljoin(base, endpoint.lstrip("/"))

    def _save_source(self, source: ImageSource, workspace: str, index: int, timeout: int) -> str:
        raw_path = os.path.join(workspace, "raw", f"generated_{index:03d}.png")
        if source.kind == "url":
            http_request = urllib.request.Request(source.value, headers={"User-Agent": "BTPW-AIAssetStudio/1.0"})
            with urllib.request.urlopen(http_request, timeout=max(1, int(timeout or 120))) as response:
                data = response.read()
        elif source.kind == "base64":
            data_text = source.value.split("base64,", 1)[-1]
            data = base64.b64decode(data_text)
        else:
            raise ValueError(f"Unsupported image source kind: {source.kind}")

        with Image.open(self._bytes_as_file(data)) as image:
            image.convert("RGBA").save(raw_path)
        return raw_path

    @staticmethod
    def _bytes_as_file(data: bytes):
        import io

        return io.BytesIO(data)

    def _write_metadata(
        self,
        workspace: str,
        request: AIAssetRequest,
        raw_paths: Iterable[str],
        output_paths: Iterable[str],
        errors: Iterable[str],
    ) -> str:
        metadata = {
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "base_url": request.base_url,
            "endpoint": request.endpoint,
            "model": request.model,
            "model_field": request.model_field,
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "count": request.count,
            "size": request.size,
            "process_mode": request.process_mode,
            "raw_paths": list(raw_paths),
            "output_paths": list(output_paths),
            "errors": list(errors),
        }
        metadata_path = os.path.join(workspace, "metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as handle:
            json.dump(metadata, handle, ensure_ascii=False, indent=2)
        return metadata_path

    @staticmethod
    def _build_foreground_mask(image: Image.Image) -> np.ndarray:
        array = np.array(image.convert("RGBA"))
        rgb = array[:, :, :3].astype(np.int16)
        alpha = array[:, :, 3]
        if np.any(alpha < 250):
            return (alpha > 8).astype("uint8")

        h, w = alpha.shape
        sample = np.concatenate(
            [
                rgb[: max(1, h // 20), : max(1, w // 20)].reshape(-1, 3),
                rgb[: max(1, h // 20), -max(1, w // 20) :].reshape(-1, 3),
                rgb[-max(1, h // 20) :, : max(1, w // 20)].reshape(-1, 3),
                rgb[-max(1, h // 20) :, -max(1, w // 20) :].reshape(-1, 3),
            ],
            axis=0,
        )
        background = np.median(sample, axis=0)
        distance = np.linalg.norm(rgb - background, axis=2)
        threshold = max(24.0, float(np.std(sample)) * 2.0)
        return ((distance > threshold) & (alpha > 8)).astype("uint8")

    @staticmethod
    def _mask_bbox(mask: np.ndarray, padding: int = 2) -> Optional[tuple]:
        ys, xs = np.where(mask > 0)
        if len(xs) == 0 or len(ys) == 0:
            return None
        left = max(0, int(xs.min()) - padding)
        top = max(0, int(ys.min()) - padding)
        right = min(mask.shape[1], int(xs.max()) + padding + 1)
        bottom = min(mask.shape[0], int(ys.max()) + padding + 1)
        return left, top, right, bottom

    @staticmethod
    def _image_with_mask(image: Image.Image, mask: np.ndarray) -> Image.Image:
        array = np.array(image.convert("RGBA"))
        array[:, :, 3] = np.minimum(array[:, :, 3], (mask > 0).astype(np.uint8) * 255)
        return Image.fromarray(array)

    def _save_segments(self, image: Image.Image, mask: np.ndarray, workspace: str, source_path: str) -> List[str]:
        try:
            import cv2
        except Exception as exc:
            raise RuntimeError(f"OpenCV is required for segmentation: {exc}") from exc

        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype("uint8"), 8)
        min_area = max(30, int(mask.size * 0.00005))
        paths: List[str] = []
        base = self._base_file_stem(source_path)
        rgba = np.array(image.convert("RGBA"))
        for label in range(1, count):
            x, y, w, h, area = stats[label]
            if int(area) < min_area:
                continue
            component_mask = (labels == label).astype("uint8")
            bbox = self._mask_bbox(component_mask)
            if bbox is None:
                continue
            left, top, right, bottom = bbox
            crop = rgba[top:bottom, left:right].copy()
            crop_mask = component_mask[top:bottom, left:right]
            crop[:, :, 3] = np.minimum(crop[:, :, 3], crop_mask * 255)
            out_path = os.path.join(workspace, "segments", f"{base}_segment_{len(paths) + 1:03d}.png")
            Image.fromarray(crop).save(out_path)
            paths.append(out_path)
        if not paths:
            cutout = self._image_with_mask(image, mask)
            bbox = self._mask_bbox(mask)
            if bbox is not None:
                out_path = os.path.join(workspace, "segments", f"{base}_segment_001.png")
                cutout.crop(bbox).save(out_path)
                paths.append(out_path)
        return paths

    @staticmethod
    def _base_file_stem(path: str) -> str:
        stem = os.path.splitext(os.path.basename(path))[0]
        return AIAssetService.safe_name(stem, "image")
