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
                COALESCE(SUM(CASE WHEN ts.is_closed THEN 1 ELSE 0 END), 0) AS closed,
                COALESCE(SUM(CASE 
                    WHEN ts.is_closed AND t.finished_date >= NOW() - INTERVAL '7 days' 
                    THEN 1 
                    ELSE 0 
                END), 0) AS recent_closed
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
                COALESCE(SUM(CASE WHEN st.is_closed THEN 1 ELSE 0 END), 0) AS closed
            FROM userstories_userstory us
            LEFT JOIN projects_userstorystatus st ON st.id = us.status_id
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
                COALESCE(SUM(CASE WHEN st.is_closed THEN 1 ELSE 0 END), 0) AS closed,
                COALESCE(SUM(CASE 
                    WHEN st.is_closed AND i.finished_date >= NOW() - INTERVAL '14 days' 
                    THEN 1 
                    ELSE 0 
                END), 0) AS recent_closed
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
                COALESCE(SUM(CASE WHEN t.assigned_to_id IS NOT NULL THEN 1 ELSE 0 END), 0) AS assigned
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
                COALESCE(SUM(CASE WHEN t.is_blocked = TRUE THEN 1 ELSE 0 END), 0) AS blocked
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
                COUNT(DISTINCT CASE 
                    WHEN EXISTS (SELECT 1 FROM tasks_task t WHERE t.user_story_id = us.id) 
                    THEN us.id 
                    ELSE NULL 
                END) AS stories_with_tasks
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
                    COUNT(DISTINCT CASE WHEN t.assigned_to_id IS NOT NULL THEN t.assigned_to_id ELSE NULL END) AS members_with_tasks
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
                    COUNT(DISTINCT CASE WHEN t.assigned_to_id IS NOT NULL THEN t.assigned_to_id ELSE NULL END) AS members_with_tasks
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
                COALESCE(SUM(CASE 
                    WHEN t.due_date IS NOT NULL AND t.due_date < CURRENT_DATE 
                    THEN 1 
                    ELSE 0 
                END), 0) AS overdue
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
    Historical: task completion ratio per week (last ~360 days).
    """
    
    series_id = "task_completion"
    name = "Cierre semanal de tareas"
    interval_days = 360
    
    def calculate_series(self) -> Dict[str, List[Dict]]:
        sql = """
            SELECT
                DATE_TRUNC('week', COALESCE(t.finished_date, t.created_date))::date AS bucket,
                COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN ts.is_closed THEN 1 ELSE 0 END), 0) AS closed
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
    interval_days = 360
    
    def calculate_series(self) -> Dict[str, List[Dict]]:
        # Tasks
        sql_tasks = """
            SELECT
                DATE_TRUNC('week', COALESCE(finished_date, created_date))::date AS bucket,
                COALESCE(SUM(CASE WHEN ts.is_closed THEN 1 ELSE 0 END), 0) AS closed_tasks
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
                COALESCE(SUM(CASE WHEN st.is_closed THEN 1 ELSE 0 END), 0) AS closed_issues
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
    Historical Team: closed tasks per user per week (last ~360 days).
    """
    
    series_id = "user_closed_tasks"
    name = "Tareas cerradas por usuario"
    interval_days = 360
    
    def calculate_series(self) -> Dict[str, List[Dict]]:
        sql = """
            SELECT
                DATE_TRUNC('week', COALESCE(t.finished_date, t.created_date))::date AS bucket,
                u.username,
                COALESCE(SUM(CASE WHEN ts.is_closed THEN 1 ELSE 0 END), 0) AS closed_tasks
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


@register_historical_metric
class UserStoryPointsHistoricalMetric(BaseHistoricalMetric):
    """
    Historical Team: Story Points completados por usuario por semana.
    Cuenta los SPs de las User Stories donde el usuario cerró tareas.
    """
    
    series_id = "user_story_points"
    name = "Story Points por usuario"
    interval_days = 360
    
    def calculate_series(self) -> Dict[str, List[Dict]]:
        # Get story points per user based on tasks they completed
        # Each user gets full SP credit for US where they completed at least one task
        # total_points is calculated from userstories_rolepoints + projects_points
        sql = """
            WITH us_points AS (
                SELECT 
                    us.id,
                    us.finish_date,
                    COALESCE(SUM(pp.value), 0) AS total_points
                FROM userstories_userstory us
                LEFT JOIN userstories_rolepoints rp ON rp.user_story_id = us.id
                LEFT JOIN projects_points pp ON pp.id = rp.points_id
                WHERE us.project_id = %s
                GROUP BY us.id, us.finish_date
            )
            SELECT
                DATE_TRUNC('week', usp.finish_date)::date AS bucket,
                u.username,
                COALESCE(SUM(DISTINCT usp.total_points), 0) AS total_points
            FROM us_points usp
            JOIN userstories_userstory us ON us.id = usp.id
            JOIN projects_userstorystatus uss ON uss.id = us.status_id
            JOIN tasks_task t ON t.user_story_id = us.id
            JOIN projects_taskstatus ts ON ts.id = t.status_id
            JOIN users_user u ON u.id = t.assigned_to_id
            WHERE
                uss.is_closed = TRUE
                AND ts.is_closed = TRUE
                AND usp.finish_date IS NOT NULL
                AND usp.finish_date >= NOW() - INTERVAL '%s days'
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
                "value": float(row.get("total_points") or 0),
                "student": row.get("username"),
            })

        return {self.series_id: series}


@register_historical_metric
class RoleStoryPointsHistoricalMetric(BaseHistoricalMetric):
    """
    Historical Team: Story Points completados por rol por semana.
    Muestra la distribución del trabajo por área funcional (UX, Design, Front, Back).
    """
    
    series_id = "role_story_points"
    name = "Story Points por rol"
    interval_days = 360
    
    def calculate_series(self) -> Dict[str, List[Dict]]:
        # Get story points per role when US is closed, grouped by week
        # Uses the role_points system from Taiga
        sql = """
            SELECT
                DATE_TRUNC('week', us.finish_date)::date AS bucket,
                r.name AS role_name,
                COALESCE(SUM(p.value), 0) AS role_points
            FROM userstories_userstory us
            JOIN userstories_rolepoints rp ON rp.user_story_id = us.id
            JOIN users_role r ON r.id = rp.role_id
            JOIN projects_points p ON p.id = rp.points_id
            LEFT JOIN projects_userstorystatus uss ON uss.id = us.status_id
            WHERE
                us.project_id = %s
                AND uss.is_closed = TRUE
                AND us.finish_date IS NOT NULL
                AND us.finish_date >= NOW() - INTERVAL '%s days'
                AND p.value IS NOT NULL
            GROUP BY bucket, r.name
            ORDER BY bucket, r.name
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, [self.project.id, self.interval_days])
            rows = _dictfetchall(cursor)

        series = []
        for row in rows:
            bucket = row["bucket"].isoformat() if row.get("bucket") else None
            role_name = row.get("role_name", "Unknown")
            series.append({
                "id": self.series_id,
                "name": f"SP {role_name}",
                "date": bucket,
                "value": float(row.get("role_points") or 0),
                "role": role_name,
            })

        return {self.series_id: series}


@register_historical_metric
class UserStoriesClosedHistoricalMetric(BaseHistoricalMetric):
    """
    Historical Team: User Stories cerradas por usuario por semana.
    Permite ver la productividad en términos de historias completadas.
    """
    
    series_id = "user_stories_closed"
    name = "Historias cerradas por usuario"
    interval_days = 360
    
    def calculate_series(self) -> Dict[str, List[Dict]]:
        sql = """
            SELECT
                DATE_TRUNC('week', us.finish_date)::date AS bucket,
                u.username,
                COUNT(*) AS stories_closed
            FROM userstories_userstory us
            LEFT JOIN users_user u ON u.id = us.assigned_to_id
            LEFT JOIN projects_userstorystatus uss ON uss.id = us.status_id
            WHERE
                us.project_id = %s
                AND uss.is_closed = TRUE
                AND us.finish_date IS NOT NULL
                AND us.finish_date >= NOW() - INTERVAL '%s days'
                AND u.username IS NOT NULL
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
                "value": row.get("stories_closed") or 0,
                "student": row.get("username"),
            })

        return {self.series_id: series}


@register_historical_metric
class SprintVelocityHistoricalMetric(BaseHistoricalMetric):
    """
    Historical: Story Points completados por sprint.
    Muestra la velocidad del equipo a lo largo de los sprints.
    """
    
    series_id = "sprint_velocity"
    name = "Velocidad por Sprint"
    interval_days = 360
    
    def calculate_series(self) -> Dict[str, List[Dict]]:
        # total_points is calculated from userstories_rolepoints + projects_points
        sql = """
            WITH us_points AS (
                SELECT 
                    us.id,
                    us.milestone_id,
                    us.status_id,
                    COALESCE(SUM(pp.value), 0) AS total_points
                FROM userstories_userstory us
                LEFT JOIN userstories_rolepoints rp ON rp.user_story_id = us.id
                LEFT JOIN projects_points pp ON pp.id = rp.points_id
                WHERE us.project_id = %s
                GROUP BY us.id, us.milestone_id, us.status_id
            )
            SELECT
                m.name AS sprint_name,
                m.estimated_finish AS finish_date,
                COALESCE(SUM(
                    CASE WHEN uss.is_closed THEN usp.total_points ELSE 0 END
                ), 0) AS completed_points,
                COALESCE(SUM(usp.total_points), 0) AS total_points
            FROM milestones_milestone m
            LEFT JOIN us_points usp ON usp.milestone_id = m.id
            LEFT JOIN projects_userstorystatus uss ON uss.id = usp.status_id
            WHERE 
                m.project_id = %s
                AND m.estimated_finish >= NOW() - INTERVAL '%s days'
            GROUP BY m.id, m.name, m.estimated_finish
            ORDER BY m.estimated_finish
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, [self.project.id, self.project.id, self.interval_days])
            rows = _dictfetchall(cursor)

        series = []
        for row in rows:
            finish_date = row.get("finish_date")
            date_str = finish_date.isoformat() if finish_date else None
            series.append({
                "id": self.series_id,
                "name": row.get("sprint_name", "Sprint"),
                "date": date_str,
                "value": float(row.get("completed_points") or 0),
                "metadata": {
                    "total_planned": float(row.get("total_points") or 0),
                    "sprint_name": row.get("sprint_name"),
                }
            })

        return {self.series_id: series}


# ============================================================================ #
# STUDENT/TEAM METRICS
# ============================================================================ #
# These are per-user metrics used in Team comparisons (radar, bar charts)

from taiga.projects.metrics.base import BaseStudentMetric, register_student_metric


@register_student_metric
class AssignedTasksStudentMetric(BaseStudentMetric):
    """Proporción de tareas asignadas a cada usuario (suma de todos = 1)."""
    metric_key = "assignedtasks"
    label = "Tareas asignadas"
    
    def __init__(self, project, context=None):
        super().__init__(project, context)
        self._user_assigned = 0
        self._total = 0
    
    def get_value_for_user(self, user_data: Dict) -> float:
        self._user_assigned = user_data.get("assigned_tasks", 0)
        self._total = self.context.get("total_tasks", 0)
        if self._total > 0:
            return self._user_assigned / float(self._total)
        return 0.0
    
    def build_metric_for_user(self, username: str, display_name: str, value: float) -> Dict:
        metric_dict = super().build_metric_for_user(username, display_name, value)
        metric_dict["value_description"] = f"{self._user_assigned}/{self._total}"
        return metric_dict


@register_student_metric
class ClosedTasksStudentMetric(BaseStudentMetric):
    """Ratio de tareas cerradas / asignadas por usuario."""
    metric_key = "closedtasks"
    label = "Tareas cerradas"
    
    def __init__(self, project, context=None):
        super().__init__(project, context)
        self._closed = 0
        self._assigned = 0
    
    def get_value_for_user(self, user_data: Dict) -> float:
        self._assigned = user_data.get("assigned_tasks", 0)
        self._closed = user_data.get("closed_tasks", 0)
        if self._assigned > 0:
            return self._closed / float(self._assigned)
        return 0.0
    
    def build_metric_for_user(self, username: str, display_name: str, value: float) -> Dict:
        metric_dict = super().build_metric_for_user(username, display_name, value)
        metric_dict["value_description"] = f"{self._closed}/{self._assigned}"
        return metric_dict


@register_student_metric
class AssignedStoriesStudentMetric(BaseStudentMetric):
    """Proporción de historias asignadas a cada usuario (suma de todos = 1)."""
    metric_key = "totalus"
    label = "Historias asignadas"
    
    def __init__(self, project, context=None):
        super().__init__(project, context)
        self._user_assigned = 0
        self._total = 0
    
    def get_value_for_user(self, user_data: Dict) -> float:
        self._user_assigned = user_data.get("assigned_stories", 0)
        self._total = self.context.get("total_stories", 0)
        if self._total > 0:
            return self._user_assigned / float(self._total)
        return 0.0
    
    def build_metric_for_user(self, username: str, display_name: str, value: float) -> Dict:
        metric_dict = super().build_metric_for_user(username, display_name, value)
        metric_dict["value_description"] = f"{self._user_assigned}/{self._total}"
        return metric_dict


@register_student_metric
class CompletedStoriesStudentMetric(BaseStudentMetric):
    """Ratio de historias completadas / asignadas por usuario."""
    metric_key = "completedus"
    label = "Historias finalizadas"

    def __init__(self, project, context=None):
        super().__init__(project, context)
        self._last_assigned = 0
        self._last_closed = 0

    def get_value_for_user(self, user_data: Dict) -> float:
        self._last_assigned = user_data.get("assigned_stories", 0)
        self._last_closed = user_data.get("closed_stories", 0)
        return (self._last_closed / float(self._last_assigned)) if self._last_assigned > 0 else 0.0

    def build_metric_for_user(self, username: str, display_name: str, value: float) -> Dict:
        """
        Overridden to provide "X/Y" description for the ratio.
        """
        metric_dict = super().build_metric_for_user(username, display_name, value)
        metric_dict["value_description"] = f"{self._last_closed}/{self._last_assigned}"
        return metric_dict


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
# NOTE: SprintVelocityHistoricalMetric is now implemented above as a real metric.
# 
# Example of another potential historical metric:
#
# @register_historical_metric
# class IssueResolutionTimeHistoricalMetric(BaseHistoricalMetric):
#     """Average issue resolution time per week."""
#     
#     series_id = "issue_resolution_time"
#     name = "Tiempo de resolución de issues"
#     interval_days = 360
#     
#     def calculate_series(self) -> Dict[str, List[Dict]]:
#         sql = """
#             SELECT
#                 DATE_TRUNC('week', i.finished_date)::date AS bucket,
#                 AVG(EXTRACT(EPOCH FROM (i.finished_date - i.created_date)) / 3600) AS avg_hours
#             FROM issues_issue i
#             LEFT JOIN projects_issuestatus ist ON ist.id = i.status_id
#             WHERE
#                 i.project_id = %s
#                 AND ist.is_closed = TRUE
#                 AND i.finished_date IS NOT NULL
#                 AND i.finished_date >= NOW() - INTERVAL '%s days'
#             GROUP BY bucket
#             ORDER BY bucket
#         """
#         with connection.cursor() as cursor:
#             cursor.execute(sql, [self.project.id, self.interval_days])
#             rows = _dictfetchall(cursor)
#
#         return {
#             self.series_id: [
#                 {
#                     "id": self.series_id,
#                     "name": self.name,
#                     "date": row["bucket"].isoformat() if row.get("bucket") else None,
#                     "value": round(row.get("avg_hours") or 0, 2),
#                 }
#                 for row in rows
#             ]
#         }
