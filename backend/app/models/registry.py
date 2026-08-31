"""Single import point for every ORM model.

Alembic autogeneration and ``Base.metadata.create_all`` both need every mapped
class to have been imported. Importing this module guarantees that, without
scattering imports through ``env.py`` or ``conftest.py``.
"""

from __future__ import annotations

from app.db.base import Base
from app.models.anomaly import Anomaly
from app.models.dataset import Dataset, DatasetAnalysis
from app.models.finding import Finding, FindingFeedback
from app.models.project import Project
from app.models.user import User

__all__ = [
    "Anomaly",
    "Base",
    "Dataset",
    "DatasetAnalysis",
    "Finding",
    "FindingFeedback",
    "Project",
    "User",
]
