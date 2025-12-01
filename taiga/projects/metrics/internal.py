# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos
#
# Internal metrics provider used to calculate Learning Dashboard compatible
# payloads without depending on the external service.

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


DEFAULT_SNAPSHOT_TTL_MINUTES = 60


def _dictfetchall(cursor) -> List[Dict]:
    columns = [col[0] for col in cursor.description] if cursor.description else []
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _dictfetchone(cursor) -> Dict:
    row = cursor.fetchone()
    if not row:
        return {}
    columns = [col[0] for col in cursor.description] if cursor.description else []
    return dict(zip(columns, row))


@dataclass
class SnapshotResult:
    payload: Dict
    historical: Dict


class InternalMetricsCalculator:
    """
    Encapsulates all the SQL required to compute metrics directly from Taiga's
    database. Each helper method focuses on a specific KPI so that it can be
    reused independently and unit tested.
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
        metrics = [
            self._metric_task_completion(),
            self._metric_user_story_completion(),
            self._metric_issue_resolution(),
        ]
        metrics = [metric for metric in metrics if metric]

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
            # Not shown in the current UI: keep empty to simplify payload
            "strategic_indicators": [],
            "quality_factors": [],
            "hours": self._build_hours_breakdown(metrics),
            "errors": {},
            "is_new_project": self._is_new_project(metrics, student_metric_entries),
        }

        historical = self._build_historical_payload()

        return SnapshotResult(payload=payload, historical=historical)

    # ------------------------------------------------------------------ #
    # Metric builders
    # ------------------------------------------------------------------ #
    def _metric_task_completion(self) -> Optional[Dict]:
        """
        KPI: Closed tasks (Project)
        - Source: tasks_task + projects_taskstatus.is_closed
        - Meaning: ratio of closed tasks vs total tasks in the project.
        - Used in: Project metrics cards (tiene metadata.total/closed/recent_closed).
        """
        sql = """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE ts.is_closed) AS closed,
                COUNT(*) FILTER (
                    WHERE ts.is_closed AND t.finished_date >= NOW() - INTERVAL '7 days'
                ) AS recent_closed
            FROM tasks_task t
            LEFT JOIN projects_taskstatus ts ON ts.id = t.status_id
            WHERE t.project_id = %s
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, [self.project.id])
            row = _dictfetchone(cursor)

        total = row.get("total") or 0
        closed = row.get("closed") or 0
        recent_closed = row.get("recent_closed") or 0

        if total == 0:
            ratio = 0.0
        else:
            ratio = closed / float(total)

        return {
            "id": f"task_completion_{self.project.slug}",
            "name": "Closed tasks",
            "value": round(ratio, 4),
            "value_description": f"{closed}/{total} tasks closed",
            "description": "Porcentaje de tareas en estado cerrado dentro del proyecto.",
            "qualityFactors": ["Delivery"],
            "metadata": {
                "total": total,
                "closed": closed,
                "recent_closed": recent_closed,
            },
        }
    
    

    def _metric_user_story_completion(self) -> Optional[Dict]:
        """
        KPI: Historias completadas (Project)
        - Source: userstories_userstory + projects_userstorystatus.is_closed
        - Meaning: ratio de user stories cerradas vs total en el proyecto.
        """
        sql = """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE st.is_closed) AS closed
            FROM userstories_userstory us
            LEFT JOIN projects_userstorystatus st ON st.id = us.status_id
            WHERE us.project_id = %s
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, [self.project.id])
            row = _dictfetchone(cursor)

        total = row.get("total") or 0
        closed = row.get("closed") or 0
        ratio = (closed / float(total)) if total else 0.0

        return {
            "id": f"userstory_completion_{self.project.slug}",
            "name": "Historias completadas",
            "value": round(ratio, 4),
            "value_description": f"{closed}/{total} historias cerradas",
            "description": "Porcentaje de user stories en estado finalizado.",
            "qualityFactors": ["Planning"],
            "metadata": {"total": total, "closed": closed},
        }

    def _metric_issue_resolution(self) -> Optional[Dict]:
        """
        KPI: Incidencias resueltas (Project)
        - Source: issues_issue + projects_issuestatus.is_closed
        - Meaning: ratio de issues cerradas vs total en el proyecto (incluye recent_closed 14d).
        """
        sql = """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE st.is_closed) AS closed,
                COUNT(*) FILTER (
                    WHERE st.is_closed AND i.finished_date >= NOW() - INTERVAL '14 days'
                ) AS recent_closed
            FROM issues_issue i
            LEFT JOIN projects_issuestatus st ON st.id = i.status_id
            WHERE i.project_id = %s
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, [self.project.id])
            row = _dictfetchone(cursor)

        total = row.get("total") or 0
        closed = row.get("closed") or 0
        recent_closed = row.get("recent_closed") or 0
        ratio = (closed / float(total)) if total else 0.0

        return {
            "id": f"issue_resolution_{self.project.slug}",
            "name": "Incidencias resueltas",
            "value": round(ratio, 4),
            "value_description": f"{closed}/{total} issues resueltos",
            "description": "Estado de resolución de incidencias dentro del proyecto.",
            "qualityFactors": ["Quality"],
            "metadata": {
                "total": total,
                "closed": closed,
                "recent_closed": recent_closed,
            },
        }

    # ------------------------------------------------------------------ #
    # Student metrics
    # ------------------------------------------------------------------ #
    def _build_student_metrics(self) -> (List[Dict], List[Dict]):
        """
        Aggregates metrics per student (membership) using SQL. Returns both the
        student payload and the flattened metric entries that mimic the format
        of the external service.
        KPIs generados (por usuario):
        - assignedtasks_<user>: tareas asignadas
        - closedtasks_<user>: tareas cerradas
        - totalus_<user>: historias asignadas
        - completedus_<user>: historias finalizadas
        Estos se usan en Team (radar y comparación).
        """
        sql = """
            SELECT
                u.id AS user_id,
                u.username,
                COALESCE(NULLIF(u.full_name, ''), u.username) AS full_name,
                COUNT(t.id) FILTER (WHERE t.assigned_to_id = u.id) AS assigned_tasks,
                COUNT(t.id) FILTER (WHERE t.assigned_to_id = u.id AND ts.is_closed) AS closed_tasks,
                COUNT(us.id) FILTER (WHERE us.assigned_to_id = u.id) AS assigned_stories,
                COUNT(us.id) FILTER (WHERE us.assigned_to_id = u.id AND uss.is_closed) AS closed_stories
            FROM projects_membership m
            JOIN users_user u ON u.id = m.user_id
            LEFT JOIN tasks_task t ON t.project_id = m.project_id AND t.assigned_to_id = u.id
            LEFT JOIN projects_taskstatus ts ON ts.id = t.status_id
            LEFT JOIN userstories_userstory us ON us.project_id = m.project_id AND us.assigned_to_id = u.id
            LEFT JOIN projects_userstorystatus uss ON uss.id = us.status_id
            WHERE m.project_id = %s AND m.user_id IS NOT NULL
            GROUP BY u.id, u.username, full_name
            ORDER BY full_name ASC
        """
        results: List[Dict] = []
        with connection.cursor() as cursor:
            cursor.execute(sql, [self.project.id])
            results = _dictfetchall(cursor)

        students: List[Dict] = []
        metric_entries: List[Dict] = []

        for row in results:
            username = row["username"]
            full_name = row["full_name"]
            assigned_tasks = row["assigned_tasks"] or 0
            closed_tasks = row["closed_tasks"] or 0
            assigned_stories = row["assigned_stories"] or 0
            closed_stories = row["closed_stories"] or 0

            student_metrics = [
                self._student_metric(username, full_name, "assignedtasks", "Tareas asignadas", assigned_tasks),
                self._student_metric(username, full_name, "closedtasks", "Tareas cerradas", closed_tasks),
                self._student_metric(username, full_name, "totalus", "Historias asignadas", assigned_stories),
                self._student_metric(username, full_name, "completedus", "Historias finalizadas", closed_stories),
            ]

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

    def _student_metric(self, username: str, display_name: str, metric_key: str, label: str, value: float) -> Dict:
        """
        Helper that formats per-student metrics so they look identical to the
        Learning Dashboard payload.
        """
        display = display_name or username
        return {
            "id": f"{metric_key}_{username}",
            "name": f"{label} · {display}" if display else label,
            "value": float(value or 0),
            "value_description": str(value) if value is not None else None,
            "description": f"{label} de {display}" if display else label,
            "qualityFactors": ["Team"],
            "date": timezone.now().isoformat(),
            "student": username,
            "student_display": display,
            "metadata": {
                "student": username,
                "student_display": display,
                "metric": metric_key,
            },
        }

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
    # Historical metrics
    # ------------------------------------------------------------------ #
    def _build_historical_payload(self) -> Dict:
        return {
            "strategicMetrics": self._historical_project_completion(),
            "projectMetrics": self._historical_task_vs_issue(),
            "userMetrics": self._historical_user_activity(),
            # Not rendered in current UI
            "qualityFactors": {},
        }

    def _historical_project_completion(self) -> Dict[str, List[Dict]]:
        """
        Histórico Project:
        - task_completion: ratio de tareas cerradas por semana (últimos ~180d).
        """
        sql = """
            SELECT
                DATE_TRUNC('week', COALESCE(t.finished_date, t.created_date))::date AS bucket,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE ts.is_closed) AS closed
            FROM tasks_task t
            LEFT JOIN projects_taskstatus ts ON ts.id = t.status_id
            WHERE
                t.project_id = %s
                AND COALESCE(t.finished_date, t.created_date) >= NOW() - INTERVAL '180 days'
            GROUP BY bucket
            ORDER BY bucket
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, [self.project.id])
            rows = _dictfetchall(cursor)

        series = []
        for row in rows:
            total = row.get("total") or 0
            closed = row.get("closed") or 0
            ratio = (closed / float(total)) if total else 0.0
            bucket = row["bucket"].isoformat() if row.get("bucket") else None
            series.append(
                {
                    "id": "task_completion",
                    "name": "Cierre semanal de tareas",
                    "date": bucket,
                    "value": round(ratio, 4),
                }
            )
        return {"task_completion": series}

    def _historical_task_vs_issue(self) -> Dict[str, List[Dict]]:
        """
        Histórico Project:
        - closed_tasks: tareas cerradas/semana.
        - closed_issues: issues cerradas/semana.
        Ambas se muestran en “Historical Project” (serie comparativa).
        """
        sql = """
            WITH buckets AS (
                SELECT
                    DATE_TRUNC('week', COALESCE(finished_date, created_date))::date AS bucket,
                    COUNT(*) FILTER (WHERE ts.is_closed) AS closed_tasks,
                    COUNT(*) AS total_tasks
                FROM tasks_task t
                LEFT JOIN projects_taskstatus ts ON ts.id = t.status_id
                WHERE
                    t.project_id = %s
                    AND COALESCE(t.finished_date, t.created_date) >= NOW() - INTERVAL '180 days'
                GROUP BY bucket
            )
            SELECT bucket, closed_tasks, total_tasks FROM buckets ORDER BY bucket
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, [self.project.id])
            task_rows = _dictfetchall(cursor)

        sql_issues = """
            SELECT
                DATE_TRUNC('week', COALESCE(i.finished_date, i.created_date))::date AS bucket,
                COUNT(*) FILTER (WHERE st.is_closed) AS closed_issues,
                COUNT(*) AS total_issues
            FROM issues_issue i
            LEFT JOIN projects_issuestatus st ON st.id = i.status_id
            WHERE
                i.project_id = %s
                AND COALESCE(i.finished_date, i.created_date) >= NOW() - INTERVAL '180 days'
            GROUP BY bucket
            ORDER BY bucket
        """
        with connection.cursor() as cursor:
            cursor.execute(sql_issues, [self.project.id])
            issue_rows = _dictfetchall(cursor)

        project_metrics = {
            "closed_tasks": [
                {
                    "id": "closed_tasks",
                    "name": "Tareas cerradas",
                    "date": row["bucket"].isoformat() if row.get("bucket") else None,
                    "value": row.get("closed_tasks") or 0,
                }
                for row in task_rows
            ],
            "closed_issues": [
                {
                    "id": "closed_issues",
                    "name": "Issues resueltos",
                    "date": row["bucket"].isoformat() if row.get("bucket") else None,
                    "value": row.get("closed_issues") or 0,
                }
                for row in issue_rows
            ],
        }

        return project_metrics

    def _historical_user_activity(self) -> Dict[str, List[Dict]]:
        """
        Histórico Team:
        - user_closed_tasks: tareas cerradas por usuario y semana (últimos ~90d).
        Si no hay datos, la vista histórica de Team queda vacía.
        """
        sql = """
            SELECT
                DATE_TRUNC('week', COALESCE(t.finished_date, t.created_date))::date AS bucket,
                u.username,
                COUNT(*) FILTER (WHERE ts.is_closed) AS closed_tasks
            FROM tasks_task t
            LEFT JOIN projects_taskstatus ts ON ts.id = t.status_id
            LEFT JOIN users_user u ON u.id = t.assigned_to_id
            WHERE
                t.project_id = %s
                AND u.username IS NOT NULL
                AND COALESCE(t.finished_date, t.created_date) >= NOW() - INTERVAL '90 days'
            GROUP BY bucket, u.username
            ORDER BY bucket, u.username
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, [self.project.id])
            rows = _dictfetchall(cursor)

        grouped: Dict[str, List[Dict]] = defaultdict(list)
        for row in rows:
            bucket = row["bucket"].isoformat() if row.get("bucket") else None
            username = row.get("username")
            grouped["user_closed_tasks"].append(
                {
                    "id": "user_closed_tasks",
                    "name": "Tareas cerradas por usuario",
                    "date": bucket,
                    "value": row.get("closed_tasks") or 0,
                    "student": username,
                }
            )

        return grouped

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
