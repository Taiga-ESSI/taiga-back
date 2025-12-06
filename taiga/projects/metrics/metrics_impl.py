# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos
# Author: Pol Alcoverro
#
# Concrete metric implementations using the abstract base classes.
# To add a new metric, create a class that extends BaseMetric and use @register_metric.
#
# NOTE: All metrics filter by ACTIVE SPRINT when available.

from __future__ import annotations

from typing import Dict, List, Optional

from django.db import connection

from taiga.projects.metrics.base import (
    BaseMetric,
    BaseHistoricalMetric,
    _dictfetchall,
    _dictfetchone,
    get_active_sprint,
    register_metric,
    register_historical_metric,
)


# ============================================================================ #
# PROJECT METRICS (filtered by active sprint)
# ============================================================================ #

@register_metric
class TaskCompletionMetric(BaseMetric):
    """
    KPI: Closed tasks (Sprint)
    - Source: tasks_task + projects_taskstatus.is_closed
    - Meaning: ratio of closed tasks vs total tasks in the ACTIVE SPRINT.
    - Used in: Project metrics cards.
    """
    
    metric_id = "task_completion"
    name = "Closed tasks"
    description = "Porcentaje de tareas cerradas en el sprint actual."
    quality_factors = ["Delivery"]
    
    def calculate(self) -> Optional[Dict]:
        sprint = get_active_sprint(self.project.id)
        sprint_filter = "AND t.milestone_id = %s" if sprint else ""
        sprint_name = sprint.get("name", "Sprint") if sprint else "Proyecto"
        
        sql = f"""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE ts.is_closed) AS closed,
                COUNT(*) FILTER (
                    WHERE ts.is_closed AND t.finished_date >= NOW() - INTERVAL '7 days'
                ) AS recent_closed
            FROM tasks_task t
            LEFT JOIN projects_taskstatus ts ON ts.id = t.status_id
            WHERE t.project_id = %s {sprint_filter}
        """
        params = [self.project.id]
        if sprint:
            params.append(sprint["id"])
            
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = _dictfetchone(cursor)

        total = row.get("total") or 0
        closed = row.get("closed") or 0
        recent_closed = row.get("recent_closed") or 0

        ratio = (closed / float(total)) if total > 0 else 0.0

        return self._build_result(
            value=ratio,
            value_description=f"{closed}/{total} en {sprint_name}",
            metadata={
                "total": total,
                "closed": closed,
                "recent_closed": recent_closed,
                "sprint_name": sprint_name,
                "has_active_sprint": sprint is not None,
            }
        )


@register_metric
class UserStoryCompletionMetric(BaseMetric):
    """
    KPI: Historias completadas (Sprint)
    - Source: userstories_userstory.is_closed
    - Meaning: ratio de user stories cerradas en el sprint activo.
    """
    
    metric_id = "userstory_completion"
    name = "Historias completadas"
    description = "Porcentaje de user stories cerradas en el sprint actual."
    quality_factors = ["Planning"]
    
    def calculate(self) -> Optional[Dict]:
        sprint = get_active_sprint(self.project.id)
        sprint_filter = "AND us.milestone_id = %s" if sprint else ""
        sprint_name = sprint.get("name", "Sprint") if sprint else "Proyecto"
        
        sql = f"""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE us.is_closed) AS closed
            FROM userstories_userstory us
            WHERE us.project_id = %s {sprint_filter}
        """
        params = [self.project.id]
        if sprint:
            params.append(sprint["id"])
            
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = _dictfetchone(cursor)

        total = row.get("total") or 0
        closed = row.get("closed") or 0
        ratio = (closed / float(total)) if total > 0 else 0.0

        return self._build_result(
            value=ratio,
            value_description=f"{closed}/{total} en {sprint_name}",
            metadata={
                "total": total, 
                "closed": closed,
                "sprint_name": sprint_name,
                "has_active_sprint": sprint is not None,
            }
        )


@register_metric
class IssueResolutionMetric(BaseMetric):
    """
    KPI: Incidencias resueltas (Sprint)
    - Source: issues_issue + projects_issuestatus.is_closed
    - Meaning: ratio de issues cerradas en el sprint activo.
    """
    
    metric_id = "issue_resolution"
    name = "Incidencias resueltas"
    description = "Estado de resolución de incidencias en el sprint actual."
    quality_factors = ["Quality"]
    
    def calculate(self) -> Optional[Dict]:
        sprint = get_active_sprint(self.project.id)
        sprint_filter = "AND i.milestone_id = %s" if sprint else ""
        sprint_name = sprint.get("name", "Sprint") if sprint else "Proyecto"
        
        sql = f"""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE st.is_closed) AS closed,
                COUNT(*) FILTER (
                    WHERE st.is_closed AND i.finished_date >= NOW() - INTERVAL '14 days'
                ) AS recent_closed
            FROM issues_issue i
            LEFT JOIN projects_issuestatus st ON st.id = i.status_id
            WHERE i.project_id = %s {sprint_filter}
        """
        params = [self.project.id]
        if sprint:
            params.append(sprint["id"])
            
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = _dictfetchone(cursor)

        total = row.get("total") or 0
        closed = row.get("closed") or 0
        recent_closed = row.get("recent_closed") or 0
        ratio = (closed / float(total)) if total > 0 else 0.0

        return self._build_result(
            value=ratio,
            value_description=f"{closed}/{total} en {sprint_name}",
            metadata={
                "total": total,
                "closed": closed,
                "recent_closed": recent_closed,
                "sprint_name": sprint_name,
                "has_active_sprint": sprint is not None,
            }
        )


@register_metric
class TaskAssignmentMetric(BaseMetric):
    """
    KPI: Tareas asignadas (Sprint)
    - Meaning: ratio de tareas que tienen un usuario asignado.
    - Útil para: detectar tareas huérfanas sin responsable.
    """
    
    metric_id = "task_assignment"
    name = "Tareas asignadas"
    description = "Porcentaje de tareas con responsable en el sprint actual."
    quality_factors = ["Planning"]
    
    def calculate(self) -> Optional[Dict]:
        sprint = get_active_sprint(self.project.id)
        sprint_filter = "AND t.milestone_id = %s" if sprint else ""
        sprint_name = sprint.get("name", "Sprint") if sprint else "Proyecto"
        
        sql = f"""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE t.assigned_to_id IS NOT NULL) AS assigned
            FROM tasks_task t
            WHERE t.project_id = %s {sprint_filter}
        """
        params = [self.project.id]
        if sprint:
            params.append(sprint["id"])
            
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = _dictfetchone(cursor)

        total = row.get("total") or 0
        assigned = row.get("assigned") or 0
        ratio = (assigned / float(total)) if total > 0 else 1.0

        return self._build_result(
            value=ratio,
            value_description=f"{assigned}/{total} en {sprint_name}",
            metadata={
                "total": total, 
                "assigned": assigned, 
                "unassigned": total - assigned,
                "sprint_name": sprint_name,
            }
        )


@register_metric
class BlockedTasksMetric(BaseMetric):
    """
    KPI: Tareas sin bloquear (Sprint)
    - Meaning: ratio de tareas que NO están bloqueadas.
    - Útil para: detectar problemas de flujo de trabajo.
    """
    
    metric_id = "blocked_tasks"
    name = "Tareas sin bloquear"
    description = "Porcentaje de tareas no bloqueadas en el sprint actual."
    quality_factors = ["Quality"]
    
    def calculate(self) -> Optional[Dict]:
        sprint = get_active_sprint(self.project.id)
        sprint_filter = "AND t.milestone_id = %s" if sprint else ""
        sprint_name = sprint.get("name", "Sprint") if sprint else "Proyecto"
        
        sql = f"""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE t.is_blocked = TRUE) AS blocked
            FROM tasks_task t
            LEFT JOIN projects_taskstatus ts ON ts.id = t.status_id
            WHERE t.project_id = %s AND ts.is_closed = FALSE {sprint_filter}
        """
        params = [self.project.id]
        if sprint:
            params.append(sprint["id"])
            
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = _dictfetchone(cursor)

        total = row.get("total") or 0
        blocked = row.get("blocked") or 0
        ratio = 1.0 - (blocked / float(total)) if total > 0 else 1.0

        return self._build_result(
            value=ratio,
            value_description=f"{blocked} bloqueadas en {sprint_name}",
            metadata={
                "total_open": total, 
                "blocked": blocked,
                "sprint_name": sprint_name,
            }
        )


@register_metric
class StoriesWithTasksMetric(BaseMetric):
    """
    KPI: Historias con tareas (Sprint)
    - Meaning: ratio de historias que tienen tareas asociadas.
    - Útil para: ver si las historias están bien desglosadas.
    """
    
    metric_id = "stories_with_tasks"
    name = "Historias con tareas"
    description = "Porcentaje de user stories con tareas en el sprint actual."
    quality_factors = ["Planning"]
    
    def calculate(self) -> Optional[Dict]:
        sprint = get_active_sprint(self.project.id)
        sprint_filter = "AND us.milestone_id = %s" if sprint else ""
        sprint_name = sprint.get("name", "Sprint") if sprint else "Proyecto"
        
        sql = f"""
            SELECT
                COUNT(DISTINCT us.id) AS total_stories,
                COUNT(DISTINCT us.id) FILTER (
                    WHERE EXISTS (SELECT 1 FROM tasks_task t WHERE t.user_story_id = us.id)
                ) AS stories_with_tasks
            FROM userstories_userstory us
            WHERE us.project_id = %s {sprint_filter}
        """
        params = [self.project.id]
        if sprint:
            params.append(sprint["id"])
            
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = _dictfetchone(cursor)

        total = row.get("total_stories") or 0
        with_tasks = row.get("stories_with_tasks") or 0
        ratio = (with_tasks / float(total)) if total > 0 else 1.0

        return self._build_result(
            value=ratio,
            value_description=f"{with_tasks}/{total} en {sprint_name}",
            metadata={
                "total_stories": total, 
                "with_tasks": with_tasks,
                "sprint_name": sprint_name,
            }
        )


@register_metric  
class TeamParticipationMetric(BaseMetric):
    """
    KPI: Participación del equipo (Sprint)
    - Meaning: ratio de miembros del equipo que tienen tareas asignadas.
    - Útil para: detectar desequilibrios en la carga de trabajo.
    """
    
    metric_id = "team_participation"
    name = "Participación del equipo"
    description = "Porcentaje de miembros con tareas en el sprint actual."
    quality_factors = ["Team"]
    
    def calculate(self) -> Optional[Dict]:
        sprint = get_active_sprint(self.project.id)
        sprint_name = sprint.get("name", "Sprint") if sprint else "Proyecto"
        
        if sprint:
            sql = """
                SELECT
                    COUNT(DISTINCT m.user_id) AS total_members,
                    COUNT(DISTINCT t.assigned_to_id) FILTER (
                        WHERE t.assigned_to_id IS NOT NULL
                    ) AS members_with_tasks
                FROM projects_membership m
                LEFT JOIN tasks_task t ON t.project_id = m.project_id 
                                      AND t.assigned_to_id = m.user_id
                                      AND t.milestone_id = %s
                WHERE m.project_id = %s AND m.user_id IS NOT NULL
            """
            params = [sprint["id"], self.project.id]
        else:
            sql = """
                SELECT
                    COUNT(DISTINCT m.user_id) AS total_members,
                    COUNT(DISTINCT t.assigned_to_id) FILTER (
                        WHERE t.assigned_to_id IS NOT NULL
                    ) AS members_with_tasks
                FROM projects_membership m
                LEFT JOIN tasks_task t ON t.project_id = m.project_id 
                                      AND t.assigned_to_id = m.user_id
                WHERE m.project_id = %s AND m.user_id IS NOT NULL
            """
            params = [self.project.id]
            
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = _dictfetchone(cursor)

        total = row.get("total_members") or 0
        with_tasks = row.get("members_with_tasks") or 0
        ratio = (with_tasks / float(total)) if total > 0 else 0.0

        return self._build_result(
            value=ratio,
            value_description=f"{with_tasks}/{total} en {sprint_name}",
            metadata={
                "total_members": total, 
                "members_with_tasks": with_tasks,
                "sprint_name": sprint_name,
            }
        )


@register_metric
class OverdueTasksMetric(BaseMetric):
    """
    KPI: Tareas en plazo (Sprint)
    - Meaning: ratio de tareas abiertas que NO están vencidas.
    - Útil para: detectar retrasos.
    """
    
    metric_id = "tasks_on_time"
    name = "Tareas en plazo"
    description = "Porcentaje de tareas no vencidas en el sprint actual."
    quality_factors = ["Delivery"]
    
    def calculate(self) -> Optional[Dict]:
        sprint = get_active_sprint(self.project.id)
        sprint_filter = "AND t.milestone_id = %s" if sprint else ""
        sprint_name = sprint.get("name", "Sprint") if sprint else "Proyecto"
        
        sql = f"""
            SELECT
                COUNT(*) AS total_open,
                COUNT(*) FILTER (
                    WHERE t.due_date IS NOT NULL AND t.due_date < CURRENT_DATE
                ) AS overdue
            FROM tasks_task t
            LEFT JOIN projects_taskstatus ts ON ts.id = t.status_id
            WHERE t.project_id = %s AND ts.is_closed = FALSE {sprint_filter}
        """
        params = [self.project.id]
        if sprint:
            params.append(sprint["id"])
            
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = _dictfetchone(cursor)

        total_open = row.get("total_open") or 0
        overdue = row.get("overdue") or 0
        ratio = 1.0 - (overdue / float(total_open)) if total_open > 0 else 1.0

        return self._build_result(
            value=ratio,
            value_description=f"{overdue} vencidas en {sprint_name}",
            metadata={
                "total_open": total_open, 
                "overdue": overdue, 
                "on_time": total_open - overdue,
                "sprint_name": sprint_name,
            }
        )


# ============================================================================ #
# HISTORICAL METRICS
# ============================================================================ #

@register_historical_metric
class TaskCompletionHistoricalMetric(BaseHistoricalMetric):
    """
    Historical: task completion ratio per week (last ~180 days).
    """
    
    series_id = "task_completion"
    name = "Cierre semanal de tareas"
    interval_days = 180
    
    def calculate_series(self) -> Dict[str, List[Dict]]:
        sql = """
            SELECT
                DATE_TRUNC('week', COALESCE(t.finished_date, t.created_date))::date AS bucket,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE ts.is_closed) AS closed
            FROM tasks_task t
            LEFT JOIN projects_taskstatus ts ON ts.id = t.status_id
            WHERE
                t.project_id = %s
                AND COALESCE(t.finished_date, t.created_date) >= NOW() - INTERVAL '%s days'
            GROUP BY bucket
            ORDER BY bucket
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, [self.project.id, self.interval_days])
            rows = _dictfetchall(cursor)

        series = []
        for row in rows:
            total = row.get("total") or 0
            closed = row.get("closed") or 0
            ratio = (closed / float(total)) if total > 0 else 0.0
            bucket = row["bucket"].isoformat() if row.get("bucket") else None
            series.append({
                "id": self.series_id,
                "name": self.name,
                "date": bucket,
                "value": round(ratio, 4),
            })
        
        return {self.series_id: series}


@register_historical_metric
class TaskVsIssueHistoricalMetric(BaseHistoricalMetric):
    """
    Historical: closed tasks vs closed issues per week.
    """
    
    series_id = "task_vs_issue"
    name = "Tareas vs Issues"
    interval_days = 180
    
    def calculate_series(self) -> Dict[str, List[Dict]]:
        # Tasks
        sql_tasks = """
            SELECT
                DATE_TRUNC('week', COALESCE(finished_date, created_date))::date AS bucket,
                COUNT(*) FILTER (WHERE ts.is_closed) AS closed_tasks
            FROM tasks_task t
            LEFT JOIN projects_taskstatus ts ON ts.id = t.status_id
            WHERE
                t.project_id = %s
                AND COALESCE(t.finished_date, t.created_date) >= NOW() - INTERVAL '%s days'
            GROUP BY bucket
            ORDER BY bucket
        """
        with connection.cursor() as cursor:
            cursor.execute(sql_tasks, [self.project.id, self.interval_days])
            task_rows = _dictfetchall(cursor)

        # Issues
        sql_issues = """
            SELECT
                DATE_TRUNC('week', COALESCE(i.finished_date, i.created_date))::date AS bucket,
                COUNT(*) FILTER (WHERE st.is_closed) AS closed_issues
            FROM issues_issue i
            LEFT JOIN projects_issuestatus st ON st.id = i.status_id
            WHERE
                i.project_id = %s
                AND COALESCE(i.finished_date, i.created_date) >= NOW() - INTERVAL '%s days'
            GROUP BY bucket
            ORDER BY bucket
        """
        with connection.cursor() as cursor:
            cursor.execute(sql_issues, [self.project.id, self.interval_days])
            issue_rows = _dictfetchall(cursor)

        return {
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


@register_historical_metric
class UserActivityHistoricalMetric(BaseHistoricalMetric):
    """
    Historical Team: closed tasks per user per week (last ~90 days).
    """
    
    series_id = "user_closed_tasks"
    name = "Tareas cerradas por usuario"
    interval_days = 90
    
    def calculate_series(self) -> Dict[str, List[Dict]]:
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
                AND COALESCE(t.finished_date, t.created_date) >= NOW() - INTERVAL '%s days'
            GROUP BY bucket, u.username
            ORDER BY bucket, u.username
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, [self.project.id, self.interval_days])
            rows = _dictfetchall(cursor)

        series = []
        for row in rows:
            bucket = row["bucket"].isoformat() if row.get("bucket") else None
            series.append({
                "id": self.series_id,
                "name": self.name,
                "date": bucket,
                "value": row.get("closed_tasks") or 0,
                "student": row.get("username"),
            })

        return {self.series_id: series}


# ============================================================================ #
# STUDENT/TEAM METRICS
# ============================================================================ #
# These are per-user metrics used in Team comparisons (radar, bar charts)

from taiga.projects.metrics.base import BaseStudentMetric, register_student_metric


@register_student_metric
class AssignedTasksStudentMetric(BaseStudentMetric):
    """Tareas asignadas a cada usuario."""
    metric_key = "assignedtasks"
    label = "Tareas asignadas"
    
    def get_value_for_user(self, user_data: Dict) -> float:
        return user_data.get("assigned_tasks", 0)


@register_student_metric
class ClosedTasksStudentMetric(BaseStudentMetric):
    """Tareas cerradas por cada usuario."""
    metric_key = "closedtasks"
    label = "Tareas cerradas"
    
    def get_value_for_user(self, user_data: Dict) -> float:
        return user_data.get("closed_tasks", 0)


@register_student_metric
class AssignedStoriesStudentMetric(BaseStudentMetric):
    """Historias asignadas a cada usuario."""
    metric_key = "totalus"
    label = "Historias asignadas"
    
    def get_value_for_user(self, user_data: Dict) -> float:
        return user_data.get("assigned_stories", 0)


@register_student_metric
class CompletedStoriesStudentMetric(BaseStudentMetric):
    """Historias completadas por cada usuario."""
    metric_key = "completedus"
    label = "Historias finalizadas"
    
    def get_value_for_user(self, user_data: Dict) -> float:
        return user_data.get("closed_stories", 0)


# NOTA: TaskCompletionRateStudentMetric y TotalWorkItemsStudentMetric eliminadas
# porque el frontend espera valores absolutos comparables (no ratios 0-1 mezclados
# con números absolutos). Si quieres añadirlas, el frontend necesita saber
# qué tipo de valor es cada métrica para mostrarla correctamente.


@register_student_metric
class AssignedIssuesStudentMetric(BaseStudentMetric):
    """Issues asignadas a cada usuario."""
    metric_key = "assignedissues"
    label = "Issues asignadas"
    
    def get_value_for_user(self, user_data: Dict) -> float:
        return user_data.get("assigned_issues", 0)


@register_student_metric
class ClosedIssuesStudentMetric(BaseStudentMetric):
    """Issues resueltas por cada usuario."""
    metric_key = "closedissues"
    label = "Issues resueltas"
    
    def get_value_for_user(self, user_data: Dict) -> float:
        return user_data.get("closed_issues", 0)


# NOTA: BlockedTasksStudentMetric eliminada temporalmente porque 
# puede confundir (alto = malo, pero el frontend muestra alto como bueno)


# ============================================================================ #
# HOW TO ADD NEW METRICS - EXAMPLES
# ============================================================================ #
#
# -------------------- PROJECT METRIC EXAMPLE --------------------
# @register_metric
# class UnassignedTasksMetric(BaseMetric):
#     """Ratio of tasks that have an assigned user."""
#     
#     metric_id = "unassigned_tasks"
#     name = "Tareas sin asignar"
#     description = "Porcentaje de tareas que tienen usuario asignado."
#     quality_factors = ["Planning"]
#     
#     def calculate(self) -> Optional[Dict]:
#         sql = """
#             SELECT
#                 COUNT(*) AS total,
#                 COUNT(*) FILTER (WHERE t.assigned_to_id IS NULL) AS unassigned
#             FROM tasks_task t
#             WHERE t.project_id = %s
#         """
#         with connection.cursor() as cursor:
#             cursor.execute(sql, [self.project.id])
#             row = _dictfetchone(cursor)
#
#         total = row.get("total") or 0
#         unassigned = row.get("unassigned") or 0
#         ratio = 1.0 - (unassigned / float(total)) if total > 0 else 1.0
#
#         return self._build_result(
#             value=ratio,
#             value_description=f"{total - unassigned}/{total} asignadas",
#             metadata={"total": total, "unassigned": unassigned}
#         )
#
#
# -------------------- STUDENT/TEAM METRIC EXAMPLE --------------------
# @register_student_metric
# class TaskCompletionRateStudentMetric(BaseStudentMetric):
#     """Ratio of closed tasks vs assigned tasks per user."""
#     metric_key = "taskcompletionrate"
#     label = "Tasa de completado"
#     
#     def get_value_for_user(self, user_data: Dict) -> float:
#         assigned = user_data.get("assigned_tasks", 0)
#         closed = user_data.get("closed_tasks", 0)
#         return (closed / float(assigned)) if assigned > 0 else 0.0
#
#
# -------------------- HISTORICAL METRIC EXAMPLE --------------------
# @register_historical_metric
# class SprintVelocityHistoricalMetric(BaseHistoricalMetric):
#     """Story points completed per sprint."""
#     
#     series_id = "sprint_velocity"
#     name = "Velocidad por Sprint"
#     interval_days = 365
#     
#     def calculate_series(self) -> Dict[str, List[Dict]]:
#         sql = """
#             SELECT
#                 m.name AS sprint_name,
#                 m.estimated_finish AS date,
#                 SUM(us.total_points) FILTER (WHERE us.is_closed) AS points
#             FROM milestones_milestone m
#             LEFT JOIN userstories_userstory us ON us.milestone_id = m.id
#             WHERE m.project_id = %s
#             GROUP BY m.id, m.name, m.estimated_finish
#             ORDER BY m.estimated_finish
#         """
#         with connection.cursor() as cursor:
#             cursor.execute(sql, [self.project.id])
#             rows = _dictfetchall(cursor)
#
#         return {
#             self.series_id: [
#                 {
#                     "id": self.series_id,
#                     "name": row.get("sprint_name", "Sprint"),
#                     "date": row["date"].isoformat() if row.get("date") else None,
#                     "value": row.get("points") or 0,
#                 }
#                 for row in rows
#             ]
#         }
