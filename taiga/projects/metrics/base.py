# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos
# Author: Pol Alcoverro
#
# Abstract base classes for internal metrics calculation.
# This design allows easy extension: just subclass BaseMetric and implement calculate().

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, TYPE_CHECKING

from django.db import connection
from django.utils import timezone

if TYPE_CHECKING:
    from taiga.projects.models import Project


def _dictfetchall(cursor) -> List[Dict]:
    """Helper to fetch all rows as a list of dictionaries."""
    columns = [col[0] for col in cursor.description] if cursor.description else []
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _dictfetchone(cursor) -> Dict:
    """Helper to fetch a single row as a dictionary."""
    row = cursor.fetchone()
    if not row:
        return {}
    columns = [col[0] for col in cursor.description] if cursor.description else []
    return dict(zip(columns, row))


def get_active_sprint(project_id: int) -> Optional[Dict]:
    """
    Returns the active sprint (milestone) for a project.
    Priority:
    1. Open sprint where today is between estimated_start and estimated_finish.
    2. First open sprint ordered by estimated_finish.
    """
    # 1. Try to find a sprint currently in progress
    sql_current = """
        SELECT m.id, m.name, m.estimated_start, m.estimated_finish
        FROM milestones_milestone m
        WHERE m.project_id = %s 
          AND m.closed = FALSE
          AND m.estimated_start <= CURRENT_DATE
          AND m.estimated_finish >= CURRENT_DATE
        LIMIT 1
    """
    with connection.cursor() as cursor:
        cursor.execute(sql_current, [project_id])
        current = _dictfetchone(cursor)
        if current:
            return current

    # 2. Fallback: first open sprint
    sql_fallback = """
        SELECT m.id, m.name, m.estimated_start, m.estimated_finish
        FROM milestones_milestone m
        WHERE m.project_id = %s 
          AND m.closed = FALSE
        ORDER BY m.estimated_finish ASC
        LIMIT 1
    """
    with connection.cursor() as cursor:
        cursor.execute(sql_fallback, [project_id])
        return _dictfetchone(cursor)


class BaseMetric(ABC):
    """
    Abstract base class for all internal metrics.
    
    To create a new metric:
    1. Subclass BaseMetric
    2. Set the class attributes (metric_id, name, description, quality_factors)
    3. Implement the calculate() method
    4. Register the metric in METRIC_REGISTRY
    
    Example:
        class MyCustomMetric(BaseMetric):
            metric_id = "my_custom_metric"
            name = "My Custom Metric"
            description = "Description of what this metric measures"
            quality_factors = ["Planning"]
            
            def calculate(self) -> Optional[Dict]:
                # Your SQL and logic here
                return {...}
    """
    
    # Override these in subclasses
    metric_id: str = ""
    name: str = ""
    description: str = ""
    quality_factors: List[str] = []
    
    def __init__(self, project: "Project"):
        self.project = project
    
    @abstractmethod
    def calculate(self) -> Optional[Dict]:
        """
        Calculate the metric value for the project.
        
        Returns:
            A dictionary with the metric data following the Learning Dashboard format:
            {
                "id": str,
                "name": str,
                "value": float (0.0 to 1.0 for ratios),
                "value_description": str,
                "description": str,
                "qualityFactors": List[str],
                "metadata": Dict (optional, for additional data)
            }
            
            Returns None if the metric cannot be calculated.
        """
        pass
    
    def _build_result(
        self,
        value: float,
        value_description: str,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Helper to build a standardized metric result dictionary.
        """
        return {
            "id": f"{self.metric_id}_{self.project.slug}",
            "name": self.name,
            "value": round(value, 4),
            "value_description": value_description,
            "description": self.description,
            "qualityFactors": self.quality_factors,
            "metadata": metadata or {},
        }


class BaseStudentMetric(ABC):
    """
    Abstract base class for per-student (team) metrics.
    
    These metrics are calculated for each team member and used in
    team comparisons (radar charts, bar charts, etc.)
    
    Example:
        class ClosedTasksStudentMetric(BaseStudentMetric):
            metric_key = "closedtasks"
            label = "Tareas cerradas"
            
            def get_value_for_user(self, user_data: Dict) -> float:
                return user_data.get("closed_tasks", 0)
    """
    
    metric_key: str = ""
    label: str = ""
    quality_factors: List[str] = ["Team"]
    
    def __init__(self, project: "Project"):
        self.project = project
    
    @abstractmethod
    def get_value_for_user(self, user_data: Dict) -> float:
        """
        Extract the metric value from the user data row.
        
        Args:
            user_data: Dictionary with user info from the SQL query
                      (contains assigned_tasks, closed_tasks, etc.)
        
        Returns:
            The numeric value for this metric.
        """
        pass
    
    def build_metric_for_user(self, username: str, display_name: str, value: float) -> Dict:
        """
        Build a standardized per-student metric result.
        """
        display = display_name or username
        return {
            "id": f"{self.metric_key}_{username}",
            "name": f"{self.label} · {display}" if display else self.label,
            "value": float(value or 0),
            "value_description": str(int(value)) if value is not None else None,
            "description": f"{self.label} de {display}" if display else self.label,
            "qualityFactors": self.quality_factors,
            "date": timezone.now().isoformat(),
            "student": username,
            "student_display": display,
            "metadata": {
                "student": username,
                "student_display": display,
                "metric": self.metric_key,
            },
        }


class BaseHistoricalMetric(ABC):
    """
    Abstract base class for historical/time-series metrics.
    
    These metrics return data points over time for trend analysis.
    """
    
    series_id: str = ""
    name: str = ""
    interval_days: int = 180
    
    def __init__(self, project: "Project"):
        self.project = project
    
    @abstractmethod
    def calculate_series(self) -> Dict[str, List[Dict]]:
        """
        Calculate historical data points.
        
        Returns:
            Dictionary mapping series_id to list of data points:
            {
                "series_id": [
                    {"id": str, "name": str, "date": str, "value": float},
                    ...
                ]
            }
        """
        pass


# ---------------------------------------------------------------------- #
# Metric Registry
# ---------------------------------------------------------------------- #
# Add your custom metrics here to have them automatically included
# in the metrics calculation.

METRIC_REGISTRY: List[type] = []
STUDENT_METRIC_REGISTRY: List[type] = []
HISTORICAL_METRIC_REGISTRY: List[type] = []


def register_metric(metric_class: type) -> type:
    """Decorator to register a project-level metric."""
    METRIC_REGISTRY.append(metric_class)
    return metric_class


def register_student_metric(metric_class: type) -> type:
    """Decorator to register a student-level metric."""
    STUDENT_METRIC_REGISTRY.append(metric_class)
    return metric_class


def register_historical_metric(metric_class: type) -> type:
    """Decorator to register a historical metric."""
    HISTORICAL_METRIC_REGISTRY.append(metric_class)
    return metric_class
