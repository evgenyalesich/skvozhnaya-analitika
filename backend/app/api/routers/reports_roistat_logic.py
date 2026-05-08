"""Compatibility facade for Roistat logic split by domain modules."""

from .reports_roistat_companies import roistat_weekly_by_company
from .reports_roistat_lessons import roistat_lessons
from .reports_roistat_tree import roistat_weekly_tree
from .reports_roistat_weekly import roistat_weekly

__all__ = [
    "roistat_weekly_by_company",
    "roistat_weekly_tree",
    "roistat_weekly",
    "roistat_lessons",
]
