# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos
# Author: Pol Alcoverro
#
# Internal metrics provider used to calculate Learning Dashboard compatible
# payloads without depending on the external service.
#
# ARCHITECTURE:
# - base.py: Abstract base classes (BaseMetric, BaseStudentMetric, BaseHistoricalMetric)
# - metrics_impl.py: Concrete implementations registered via decorators
# - internal.py (this file): Calculator that orchestrates all metrics
#
# To add a new metric, see metrics_impl.py for examples.

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, List, Optional, Sequence

from django.conf import settings
from django.db import connection
from django.utils import timezone

from taiga.projects.metrics.models import ProjectMetricsSnapshot
from taiga.projects.models import Project

# Import to trigger metric registration via decorators
from taiga.projects.metrics.base import (
    METRIC_REGISTRY,
    STUDENT_METRIC_REGISTRY,
    HISTORICAL_METRIC_REGISTRY,
    _dictfetchall,
    _dictfetchone,
    get_active_sprint,
)
import taiga.projects.metrics.metrics_impl  # noqa: F401 - registers metrics


DEFAULT_SNAPSHOT_TTL_MINUTES = 60


@dataclass
class SnapshotResult:
    payload: Dict
    historical: Dict


class InternalMetricsCalculator:
    """
    Orchestrates all internal metric calculations using registered metric classes.
    
    Metrics are auto-discovered from METRIC_REGISTRY and HISTORICAL_METRIC_REGISTRY
    which are populated by the @register_metric and @register_historical_metric
    decorators in metrics_impl.py.
    
    To add a new metric, simply create a class in metrics_impl.py that extends
    BaseMetric and decorate it with @register_metric.
    """

    def __init__(self, project: Project):
        self.project = project

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def build_snapshot(self) -> SnapshotResult:
        """
        Creates both the real-time payload and the historical payload so the
        API can serve the same schema as the external Learning Dashboard.
        """
        # Calculate all registered project metrics
        metrics = self._calculate_all_metrics()

        student_metrics, student_metric_entries = self._build_student_metrics()

        # Include per-user metrics in the global metrics list so the frontend
        # can re-associate them to each student (mimics Learning Dashboard).
        metrics.extend(student_metric_entries)

        payload = {
            "project_slug": self.project.slug,
            "project_name": self.project.name,
            "external_project_id": self.project.slug,
            "metrics": metrics,
            "students": student_metrics,
            "metrics_categories": self._build_metric_categories(),
            "strategic_indicators": [],
            "quality_factors": [],
            "hours": self._build_hours_breakdown(metrics),
            "errors": {},
            "is_new_project": self._is_new_project(metrics, student_metric_entries),
        }

        historical = self._build_historical_payload()

        return SnapshotResult(payload=payload, historical=historical)

    def _calculate_all_metrics(self) -> List[Dict]:
        """
        Instantiate and calculate all registered metrics.
        Uses the METRIC_REGISTRY populated by @register_metric decorators.
        """
        metrics = []
        for metric_class in METRIC_REGISTRY:
            try:
                metric_instance = metric_class(self.project)
                result = metric_instance.calculate()
                if result:
                    metrics.append(result)
            except Exception:
                # Log error but continue with other metrics
                pass
        return metrics

    # ------------------------------------------------------------------ #
    # Student metrics (using registered metric classes)
    # ------------------------------------------------------------------ #
    def _build_student_metrics(self) -> tuple[List[Dict], List[Dict]]:
        """
        Aggregates metrics per student (membership) using SQL and registered
        student metric classes from STUDENT_METRIC_REGISTRY.
        
        Returns both the student payload and the flattened metric entries
        that mimic the format of the external Learning Dashboard.
        """
        # Get active sprint for filtering
        sprint = get_active_sprint(self.project.id)
        
        if sprint:
            # Filter by active sprint
            sql = """
                SELECT
                    u.id AS user_id,
                    u.username,
                    COALESCE(NULLIF(u.full_name, ''), u.username) AS full_name,
                    COUNT(DISTINCT t.id) FILTER (WHERE t.assigned_to_id = u.id) AS assigned_tasks,
                    COUNT(DISTINCT t.id) FILTER (WHERE t.assigned_to_id = u.id AND ts.is_closed) AS closed_tasks,
                    COUNT(DISTINCT t.id) FILTER (WHERE t.assigned_to_id = u.id AND t.is_blocked) AS blocked_tasks,
                    COUNT(DISTINCT us.id) FILTER (WHERE us.assigned_to_id = u.id) AS assigned_stories,
                    COUNT(DISTINCT us.id) FILTER (WHERE us.assigned_to_id = u.id AND usst.is_closed) AS closed_stories,
                    COUNT(DISTINCT i.id) FILTER (WHERE i.assigned_to_id = u.id) AS assigned_issues,
                    COUNT(DISTINCT i.id) FILTER (WHERE i.assigned_to_id = u.id AND ist.is_closed) AS closed_issues
                FROM projects_membership m
                JOIN users_user u ON u.id = m.user_id
                LEFT JOIN tasks_task t ON t.project_id = m.project_id 
                                      AND t.assigned_to_id = u.id 
                                      AND t.milestone_id = %s
                LEFT JOIN projects_taskstatus ts ON ts.id = t.status_id
                LEFT JOIN userstories_userstory us ON us.project_id = m.project_id 
                                                  AND us.assigned_to_id = u.id
                                                  AND us.milestone_id = %s
                LEFT JOIN projects_userstorystatus usst ON usst.id = us.status_id
                LEFT JOIN issues_issue i ON i.project_id = m.project_id 
                                        AND i.assigned_to_id = u.id
                                        AND i.milestone_id = %s
                LEFT JOIN projects_issuestatus ist ON ist.id = i.status_id
                WHERE m.project_id = %s AND m.user_id IS NOT NULL
                GROUP BY u.id, u.username, full_name
                ORDER BY full_name ASC
            """
            params = [sprint["id"], sprint["id"], sprint["id"], self.project.id]
        else:
            # No active sprint: show all project data
            sql = """
                SELECT
                    u.id AS user_id,
                    u.username,
                    COALESCE(NULLIF(u.full_name, ''), u.username) AS full_name,
                    COUNT(DISTINCT t.id) FILTER (WHERE t.assigned_to_id = u.id) AS assigned_tasks,
                    COUNT(DISTINCT t.id) FILTER (WHERE t.assigned_to_id = u.id AND ts.is_closed) AS closed_tasks,
                    COUNT(DISTINCT t.id) FILTER (WHERE t.assigned_to_id = u.id AND t.is_blocked) AS blocked_tasks,
                    COUNT(DISTINCT us.id) FILTER (WHERE us.assigned_to_id = u.id) AS assigned_stories,
                    COUNT(DISTINCT us.id) FILTER (WHERE us.assigned_to_id = u.id AND usst.is_closed) AS closed_stories,
                    COUNT(DISTINCT i.id) FILTER (WHERE i.assigned_to_id = u.id) AS assigned_issues,
                    COUNT(DISTINCT i.id) FILTER (WHERE i.assigned_to_id = u.id AND ist.is_closed) AS closed_issues
                FROM projects_membership m
                JOIN users_user u ON u.id = m.user_id
                LEFT JOIN tasks_task t ON t.project_id = m.project_id AND t.assigned_to_id = u.id
                LEFT JOIN projects_taskstatus ts ON ts.id = t.status_id
                LEFT JOIN userstories_userstory us ON us.project_id = m.project_id AND us.assigned_to_id = u.id
                LEFT JOIN projects_userstorystatus usst ON usst.id = us.status_id
                LEFT JOIN issues_issue i ON i.project_id = m.project_id AND i.assigned_to_id = u.id
                LEFT JOIN projects_issuestatus ist ON ist.id = i.status_id
                WHERE m.project_id = %s AND m.user_id IS NOT NULL
                GROUP BY u.id, u.username, full_name
                ORDER BY full_name ASC
            """
            params = [self.project.id]
            
        results: List[Dict] = []
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            results = _dictfetchall(cursor)

        # Calculate totals for normalization (sum of all users = 1)
        total_tasks = sum(row.get("assigned_tasks", 0) for row in results)
        total_stories = sum(row.get("assigned_stories", 0) for row in results)
        
        # Context passed to metric classes for proper normalization
        context = {
            "total_tasks": total_tasks,
            "total_stories": total_stories,
        }

        # Instantiate all registered student metrics with context
        student_metric_instances = [
            metric_class(self.project, context) for metric_class in STUDENT_METRIC_REGISTRY
        ]

        students: List[Dict] = []
        metric_entries: List[Dict] = []

        for row in results:
            username = row["username"]
            full_name = row["full_name"]

            # Calculate all metrics for this user using registered classes
            student_metrics = []
            for metric_instance in student_metric_instances:
                try:
                    value = metric_instance.get_value_for_user(row)
                    metric_dict = metric_instance.build_metric_for_user(username, full_name, value)
                    student_metrics.append(metric_dict)
                    print(f"✅ Student metric: {metric_dict.get('id')} = {value}")
                except Exception as e:
                    print(f"❌ Error in {metric_instance.__class__.__name__} for {username}: {e}")

            metric_entries.extend(student_metrics)

            students.append(
                {
                    "username": username,
                    "name": full_name,
                    "displayName": full_name,
                    "identities": {"TAIGA": {"username": username}},
                    "metrics": student_metrics,
                }
            )

        return students, metric_entries

    # ------------------------------------------------------------------ #
    # Supporting builders
    # ------------------------------------------------------------------ #
    def _build_metric_categories(self) -> List[Dict]:
        return [
            # Shared palette: rojo (mal) -> ámbar (mejora) -> verde (OK)
            {"name": "Delivery", "upperThreshold": 0.5, "color": "#EF4444", "type": "percentage"},
            {"name": "Delivery", "upperThreshold": 0.8, "color": "#F59E0B", "type": "percentage"},
            {"name": "Delivery", "upperThreshold": 1.0, "color": "#22C55E", "type": "percentage"},
            {"name": "Planning", "upperThreshold": 0.5, "color": "#EF4444", "type": "percentage"},
            {"name": "Planning", "upperThreshold": 0.8, "color": "#F59E0B", "type": "percentage"},
            {"name": "Planning", "upperThreshold": 1.0, "color": "#22C55E", "type": "percentage"},
            {"name": "Quality", "upperThreshold": 0.5, "color": "#EF4444", "type": "percentage"},
            {"name": "Quality", "upperThreshold": 0.8, "color": "#F59E0B", "type": "percentage"},
            {"name": "Quality", "upperThreshold": 1.0, "color": "#22C55E", "type": "percentage"},
            {"name": "Team", "upperThreshold": 100, "color": "#8B5CF6", "type": "absolute"},
        ]

    def _build_hours_breakdown(self, metrics: Sequence[Dict]) -> Dict:
        """
        Produces a light-weight hours/effort distribution so the front-end pie
        chart can render data even when the external provider is absent.
        """
        total_tasks = 0
        closed_tasks = 0
        total_issues = 0
        closed_issues = 0
        for metric in metrics:
            metadata = metric.get("metadata") if metric else {}
            if not metadata:
                continue
            if "total" in metadata and metric["id"].startswith("task_completion"):
                total_tasks = metadata.get("total", 0)
                closed_tasks = metadata.get("closed", 0)
            if "total" in metadata and metric["id"].startswith("issue_resolution"):
                total_issues = metadata.get("total", 0)
                closed_issues = metadata.get("closed", 0)

        return {
            "execution": closed_tasks,
            "pending": max(total_tasks - closed_tasks, 0),
            "quality": closed_issues,
            "incidents": max(total_issues - closed_issues, 0),
        }

    def _is_new_project(self, metrics: Sequence[Dict], student_entries: Sequence[Dict]) -> bool:
        if any(metric.get("metadata", {}).get("total") for metric in metrics if metric):
            return False
        return len(student_entries) == 0

    # ------------------------------------------------------------------ #
    # Historical metrics (using registered metric classes)
    # ------------------------------------------------------------------ #
    def _build_historical_payload(self) -> Dict:
        """
        Build historical payload using registered historical metric classes.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        strategic_metrics: Dict[str, List[Dict]] = {}
        project_metrics: Dict[str, List[Dict]] = {}
        user_metrics: Dict[str, List[Dict]] = {}

        logger.info(f"📊 Building historical payload for project {self.project.slug}")
        logger.info(f"   Registered historical metrics: {len(HISTORICAL_METRIC_REGISTRY)}")

        for metric_class in HISTORICAL_METRIC_REGISTRY:
            try:
                metric_instance = metric_class(self.project)
                series_data = metric_instance.calculate_series()
                
                logger.info(f"   ✓ {metric_class.__name__}: {len(series_data)} series")
                
                # Classify based on series_id patterns
                for series_id, data in series_data.items():
                    logger.info(f"     - {series_id}: {len(data)} data points")
                    # User/Team metrics (per-user data for team comparison charts)
                    if "user" in series_id.lower():
                        user_metrics[series_id] = data
                    # Strategic metrics (high-level KPIs)
                    elif series_id in ("task_completion", "sprint_velocity"):
                        strategic_metrics[series_id] = data
                    # Project metrics (project-level trends like role distribution)
                    else:
                        project_metrics[series_id] = data
            except Exception as e:
                logger.error(f"   ✗ {metric_class.__name__}: {e}")

        logger.info(f"   Total: strategic={len(strategic_metrics)}, project={len(project_metrics)}, user={len(user_metrics)}")

        return {
            "strategicMetrics": strategic_metrics,
            "projectMetrics": project_metrics,
            "userMetrics": user_metrics,
            "qualityFactors": {},
        }

# ---------------------------------------------------------------------- #
# Snapshot helpers
# ---------------------------------------------------------------------- #
def get_or_build_snapshot(
    project: Project,
    *,
    use_cache: bool = True,
    force: bool = False,
) -> ProjectMetricsSnapshot:
    """
    Returns a cached snapshot if it is still fresh, otherwise recalculates the
    metrics and persists them for future requests.
    """
    ttl_minutes = getattr(settings, "METRICS_INTERNAL_SNAPSHOT_TTL_MINUTES", DEFAULT_SNAPSHOT_TTL_MINUTES)
    cutoff = timezone.now() - timedelta(minutes=max(ttl_minutes, 1))

    queryset = ProjectMetricsSnapshot.objects.filter(
        project=project,
        provider=ProjectMetricsSnapshot.INTERNAL_PROVIDER,
    )

    if use_cache and not force:
        snapshot = queryset.filter(computed_at__gte=cutoff).first()
        if snapshot:
            return snapshot

    calculator = InternalMetricsCalculator(project)
    result = calculator.build_snapshot()

    snapshot = ProjectMetricsSnapshot.objects.create(
        project=project,
        provider=ProjectMetricsSnapshot.INTERNAL_PROVIDER,
        payload=result.payload,
        historical_payload=result.historical,
        computed_at=timezone.now(),
    )

    # Keep only the latest snapshot to avoid storing excessive history.
    stale = queryset.exclude(id=snapshot.id)
    stale.delete()

    return snapshot
