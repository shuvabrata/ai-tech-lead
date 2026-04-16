"""Configuration models and defaults for collaboration network analytics."""

from typing import Any, Dict, Iterable, Mapping

from pydantic import BaseModel, Field, field_validator


LAYER_ORDER = [
    "reporter_assignee",
    "pr_reviews",
    "shared_file_commits",
    "sprint_coworkers",
    "explicit_review_requests",
    "epic_overlap",
]

LAYER_LABELS: Dict[str, str] = {
    "reporter_assignee": "Reporter-Assignee (Jira)",
    "pr_reviews": "PR Reviews (GitHub)",
    "shared_file_commits": "Shared File Commits",
    "sprint_coworkers": "Sprint Co-workers",
    "explicit_review_requests": "Explicit Review Requests",
    "epic_overlap": "Epic Overlap",
}

DEFAULT_LAYER_WEIGHTS: Dict[str, float] = {
    "reporter_assignee": 2.0,
    "pr_reviews": 3.0,
    "shared_file_commits": 5.0,
    "sprint_coworkers": 2.0,
    "explicit_review_requests": 2.0,
    "epic_overlap": 1.0,
}

DEFAULT_LOOKBACK_DAYS = 90
DEFAULT_MIN_PAIR_SCORE = 1.0
DEFAULT_TOP_N_EDGES_PER_NODE = 0
DEFAULT_EXCLUDE_BOTS = True
DEFAULT_ENSURE_MIN_CONNECTION = True
DEFAULT_EXCLUDED_FILE_SUFFIXES = [".json", ".md", ".lock"]
DEFAULT_COMMUNITY_GAP_X = 1560.0
DEFAULT_COMMUNITY_GAP_Y = 1170.0


class CollaborationNetworkConfig(BaseModel):
    """Runtime configuration for collaboration network generation."""

    enabled_layers: list[str] = Field(default_factory=lambda: list(LAYER_ORDER))
    weights: Dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_LAYER_WEIGHTS))
    lookback_days: int = Field(default=DEFAULT_LOOKBACK_DAYS, ge=1, le=365)
    min_pair_score: float = Field(default=DEFAULT_MIN_PAIR_SCORE, ge=0)
    top_n_edges_per_node: int = Field(default=DEFAULT_TOP_N_EDGES_PER_NODE, ge=0, le=200)
    community_gap_x: float = Field(default=DEFAULT_COMMUNITY_GAP_X, ge=200, le=10000)
    community_gap_y: float = Field(default=DEFAULT_COMMUNITY_GAP_Y, ge=200, le=10000)
    ensure_min_connection: bool = Field(default=DEFAULT_ENSURE_MIN_CONNECTION)
    exclude_bots: bool = Field(default=DEFAULT_EXCLUDE_BOTS)
    excluded_file_suffixes: list[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDED_FILE_SUFFIXES))

    @field_validator("enabled_layers")
    @classmethod
    def _validate_enabled_layers(cls, value: list[str]) -> list[str]:
        if not value:
            return []
        normalized = []
        for layer in value:
            if layer not in LAYER_ORDER:
                raise ValueError(f"Unknown collaboration layer: {layer}")
            if layer not in normalized:
                normalized.append(layer)
        return normalized

    @field_validator("weights")
    @classmethod
    def _validate_weights(cls, value: Dict[str, float]) -> Dict[str, float]:
        merged = dict(DEFAULT_LAYER_WEIGHTS)
        for key, weight in value.items():
            if key not in LAYER_ORDER:
                raise ValueError(f"Unknown weight key: {key}")
            merged[key] = float(weight)

        for key in LAYER_ORDER:
            if merged[key] < 0:
                raise ValueError(f"Weight must be >= 0 for layer '{key}'")

        return merged

    def to_cypher_parameters(self) -> Dict[str, Any]:
        """Return Neo4j Cypher parameters for the collaboration query."""
        params: Dict[str, Any] = {
            "lookback_days": self.lookback_days,
            "min_pair_score": self.min_pair_score,
            "exclude_bots": self.exclude_bots,
            "excluded_file_suffixes": self.excluded_file_suffixes,
        }

        enabled = set(self.enabled_layers)
        for layer in LAYER_ORDER:
            params[f"include_{layer}"] = layer in enabled
            params[f"weight_{layer}"] = self.weights[layer]

        return params

    def to_summary(self) -> Dict[str, Any]:
        """Return a UI-friendly summary of the active configuration."""
        return {
            "enabled_layers": self.enabled_layers,
            "weights": self.weights,
            "lookback_days": self.lookback_days,
            "min_pair_score": self.min_pair_score,
            "top_n_edges_per_node": self.top_n_edges_per_node,
            "community_gap_x": self.community_gap_x,
            "community_gap_y": self.community_gap_y,
            "ensure_min_connection": self.ensure_min_connection,
            "exclude_bots": self.exclude_bots,
            "excluded_file_suffixes": self.excluded_file_suffixes,
        }

    @classmethod
    def from_query_values(cls, values: Mapping[str, Any]) -> "CollaborationNetworkConfig":
        """Build config from query string-like key/value input."""
        def _as_bool(raw: Any, default: bool) -> bool:
            if raw is None:
                return default
            if isinstance(raw, bool):
                return raw
            return str(raw).strip().lower() in {"1", "true", "yes", "on"}

        def _as_int(raw: Any, default: int) -> int:
            if raw is None or raw == "":
                return default
            return int(raw)

        def _as_float(raw: Any, default: float) -> float:
            if raw is None or raw == "":
                return default
            return float(raw)

        def _as_list(raw: Any) -> list[str]:
            if raw is None:
                return []
            if isinstance(raw, str):
                chunks = [raw]
            elif isinstance(raw, Iterable):
                chunks = [str(v) for v in raw]
            else:
                chunks = [str(raw)]

            parsed: list[str] = []
            for chunk in chunks:
                for item in chunk.split(","):
                    cleaned = item.strip()
                    if cleaned:
                        parsed.append(cleaned)
            return parsed

        layers = _as_list(values.get("layers"))
        weight_overrides: Dict[str, float] = {}
        for layer in LAYER_ORDER:
            weight_key = f"w_{layer}"
            if values.get(weight_key) is not None and values.get(weight_key) != "":
                weight_overrides[layer] = _as_float(values.get(weight_key), DEFAULT_LAYER_WEIGHTS[layer])

        excluded_suffixes = _as_list(values.get("exclude_suffixes"))

        payload: Dict[str, Any] = {
            "enabled_layers": layers or list(LAYER_ORDER),
            "weights": {**DEFAULT_LAYER_WEIGHTS, **weight_overrides},
            "lookback_days": _as_int(values.get("lookback_days"), DEFAULT_LOOKBACK_DAYS),
            "min_pair_score": _as_float(values.get("min_pair_score"), DEFAULT_MIN_PAIR_SCORE),
            "top_n_edges_per_node": _as_int(values.get("top_n_edges_per_node"), DEFAULT_TOP_N_EDGES_PER_NODE),
            "community_gap_x": _as_float(values.get("community_gap_x"), DEFAULT_COMMUNITY_GAP_X),
            "community_gap_y": _as_float(values.get("community_gap_y"), DEFAULT_COMMUNITY_GAP_Y),
            "ensure_min_connection": _as_bool(values.get("ensure_min_connection"), DEFAULT_ENSURE_MIN_CONNECTION),
            "exclude_bots": _as_bool(values.get("exclude_bots"), DEFAULT_EXCLUDE_BOTS),
            "excluded_file_suffixes": excluded_suffixes or list(DEFAULT_EXCLUDED_FILE_SUFFIXES),
        }
        return cls.model_validate(payload)
