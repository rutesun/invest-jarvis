"""Legacy compatibility wrapper for structure zone detector.

Phase 2 refactor moves implementation to `components/structure_zones.py`.
This module keeps the old import path stable during migration.
"""

from src.tools.technical.components.structure_zones import (
    StructureZoneDetector,
    calculate_zone_half_width,
    cluster_price_candidates,
)
from src.tools.technical.models import StructureZoneConfig


__all__ = [
    "StructureZoneConfig",
    "StructureZoneDetector",
    "calculate_zone_half_width",
    "cluster_price_candidates",
]
