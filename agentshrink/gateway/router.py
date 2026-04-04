"""Routing adapter for using AgentShrink cluster matching behind the gateway."""

from __future__ import annotations

import pathlib


class GatewayRouter:
    def __init__(
        self,
        output_dir: str = ".agentshrink_output",
        confidence_threshold: float = 0.75,
        fallback_provider: str = "openai",
        fallback_model: str = "gpt-4o-mini",
    ):
        self.output_dir = output_dir
        self.confidence_threshold = confidence_threshold
        self.fallback_provider = fallback_provider
        self.fallback_model = fallback_model
        self._index = None
        self._load_index()

    def _load_index(self):
        try:
            from agentshrink.centroid_index import CentroidIndex

            self._index = CentroidIndex.from_output_dir(
                pathlib.Path(self.output_dir),
                confidence_threshold=self.confidence_threshold,
            )
        except Exception:
            self._index = None

    def route_prompt(self, prompt_text: str):
        from agentshrink.centroid_index import RoutingDecision

        if self._index is None:
            return RoutingDecision(
                cluster_id=-1,
                cluster_name="unknown",
                provider=self.fallback_provider,
                model_name=self.fallback_model,
                model_display=f"Fallback ({self.fallback_model})",
                confidence=0.0,
                is_local=False,
                reason="no index loaded",
                nearest_cluster_name=None,
                nearest_similarity=0.0,
                threshold=self.confidence_threshold,
            )
        return self._index.route(prompt_text)
