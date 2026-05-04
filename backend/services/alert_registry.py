"""Alert indicator registry.

Each indicator declares its capabilities (which conditions it supports) and
exposes value providers. The alert engine dispatches by looking up
(target_type, indicator_key) → IndicatorSpec.
"""
from dataclasses import dataclass
from typing import Callable


@dataclass
class IndicatorSpec:
    key: str
    label: str
    unit: str
    target_type: str  # "indicator" | "stock_indicator"
    supported_conditions: set[str]

    get_latest_value: Callable[[str], float | None]
    get_history: Callable[[str, int], list[float]] | None = None
    get_percentile: Callable[[str], float | None] | None = None
    get_yoy: Callable[[str], float | None] | None = None

    def supports(self, condition: str) -> bool:
        return condition in self.supported_conditions


_INDICATOR_REGISTRY: dict[str, IndicatorSpec] = {}
_STOCK_INDICATOR_REGISTRY: dict[str, IndicatorSpec] = {}


def register_indicator(spec: IndicatorSpec) -> None:
    if spec.target_type == "indicator":
        _INDICATOR_REGISTRY[spec.key] = spec
    elif spec.target_type == "stock_indicator":
        _STOCK_INDICATOR_REGISTRY[spec.key] = spec
    else:
        raise ValueError(f"Unsupported target_type: {spec.target_type}")


def get_indicator(target_type: str, key: str) -> IndicatorSpec | None:
    if target_type == "indicator":
        return _INDICATOR_REGISTRY.get(key)
    if target_type == "stock_indicator":
        return _STOCK_INDICATOR_REGISTRY.get(key)
    return None


def list_indicators(target_type: str) -> list[IndicatorSpec]:
    if target_type == "indicator":
        return sorted(_INDICATOR_REGISTRY.values(), key=lambda s: s.key)
    if target_type == "stock_indicator":
        return sorted(_STOCK_INDICATOR_REGISTRY.values(), key=lambda s: s.key)
    return []


def all_indicators() -> dict[str, list[IndicatorSpec]]:
    return {
        "indicator": list_indicators("indicator"),
        "stock_indicator": list_indicators("stock_indicator"),
    }
