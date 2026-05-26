from __future__ import annotations

import time
from pathlib import Path

from dimos.experimental.dogops.config_loader import DEFAULT_SITE, load_site_config
from dimos.experimental.dogops.detector import DetectedTag, DogOpsTagDetector
from dimos.experimental.dogops.models import Observation

try:  # pragma: no cover - exercised only inside a full DimOS checkout.
    from dimos.core.module import Module
except ModuleNotFoundError:

    class Module:
        @classmethod
        def blueprint(cls, **kwargs: object) -> dict[str, object]:
            return {"module": cls.__name__, "kwargs": kwargs}


class DogOpsObservationModule(Module):
    def __init__(self, *, site_path: str | Path = DEFAULT_SITE, **_: object) -> None:
        self.site_path = Path(site_path)
        self.site = load_site_config(self.site_path)
        self.detector = DogOpsTagDetector(self.site)

    def observe_simulated_tags(
        self,
        tag_ids: list[int],
        *,
        zone_id: str,
        run_id: str = "simulated",
    ) -> list[Observation]:
        return [
            self._observation_for_detection(detection, zone_id=zone_id, run_id=run_id)
            for detection in self.detector.detect_simulated(tag_ids)
        ]

    def observe_image(
        self,
        image_path: str | Path,
        *,
        zone_id: str,
        run_id: str = "image",
    ) -> list[Observation]:
        return [
            self._observation_for_detection(detection, zone_id=zone_id, run_id=run_id)
            for detection in self.detector.detect_image(image_path)
        ]

    def image_stream_status(self) -> dict[str, object]:
        return {
            "ok": False,
            "mode": "not_subscribed",
            "fallback": "use observe_simulated_tags or observe_image",
        }

    @staticmethod
    def _observation_for_detection(
        detection: DetectedTag,
        *,
        zone_id: str,
        run_id: str,
    ) -> Observation:
        return Observation(
            id=f"TAG-{detection.tag_id}",
            ts=time.time(),
            run_id=run_id,
            entity_id=detection.entity_id,
            tag_id=detection.tag_id,
            zone_id=zone_id,
            facts={
                "entity_kind": detection.entity_kind or "unknown",
                "detection_source": detection.source,
            },
            confidence=detection.confidence,
            source=detection.source,
        )
