# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

import logging
from datetime import datetime, timezone as dt_timezone
from typing import Dict, List, Optional, Tuple

import requests
from django.conf import settings

from taiga.projects.metrics.internal import get_or_build_snapshot

from .models import CourseEdition, Subject

logger = logging.getLogger(__name__)


def get_edition_dashboard(edition: CourseEdition, *, force: bool = False, raw: bool = False, requesting_user=None, professor_view: bool = False) -> Dict:
    """
    Aggregate metrics for all active teams in a CourseEdition that have a
    linked Taiga project. Uses cached snapshots (TTL-based) unless force=True.
    Applies CourseMetricsPolicy filtering, ordering, and student drilldown rules.
    Pass raw=True to skip policy filtering (used by the settings panel).
    Pass requesting_user to restrict teams to those assigned via ProfessorTeamAssignment.
    Pass professor_view=True to force professor-level team filtering even for coordinators
    (only applies when the user is both coordinator and professor of the edition).
    """
    is_coordinator, is_professor = _get_user_role_info(edition, requesting_user)
    effective_professor_view = professor_view and is_coordinator and is_professor

    visible_team_ids = _get_visible_team_ids(edition, requesting_user, professor_view=effective_professor_view)
    teams_data = _collect_team_snapshots(edition, force=force, visible_team_ids=visible_team_ids)
    aggregated = _aggregate_metrics(teams_data)
    if not raw:
        aggregated = _apply_policy(edition, teams_data, aggregated)
        _apply_student_drilldown_policy(edition, teams_data)

    return {
        "course_edition_id": edition.pk,
        "course_edition_key": edition.key,
        "groups": teams_data,
        "aggregated": aggregated,
        "is_coordinator": is_coordinator,
        "is_professor": is_professor,
    }


def get_subject_metrics(subject: Subject, *, force: bool = False) -> Dict:
    """
    Compare aggregated metrics across all CourseEditions of a subject.
    Returns one aggregated entry per edition (only editions with linked teams).
    """
    editions = (
        subject.editions
        .prefetch_related("teams__project_link__project")
        .order_by("-academic_year", "term")
    )

    editions_data = []
    for edition in editions:
        teams_data = _collect_team_snapshots(edition, force=force)
        if not teams_data:
            continue
        aggregated = _aggregate_metrics(teams_data)
        aggregated = _apply_policy(edition, teams_data, aggregated)
        editions_data.append({
            "edition_id": edition.pk,
            "edition_key": edition.key,
            "academic_year": edition.academic_year,
            "term": edition.term,
            "status": edition.status,
            "team_count": len(teams_data),
            "aggregated": aggregated,
        })

    return {
        "subject_id": subject.pk,
        "subject_code": subject.code,
        "subject_name": subject.name,
        "editions": editions_data,
    }


def _get_user_role_info(edition: CourseEdition, user) -> Tuple[bool, bool]:
    """Returns (is_coordinator: bool, is_professor: bool) for the given user on this edition."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False, False

    try:
        teacher = user.teacher_profile
    except Exception:
        teacher = None

    if getattr(user, "is_superuser", False):
        is_professor = (
            teacher is not None
            and teacher.is_active_teacher
            and edition.professor_assignments.filter(
                teacher_profile=teacher, is_active=True
            ).exists()
        )
        return True, is_professor

    if teacher is None or not teacher.is_active_teacher:
        return False, False

    if teacher.global_role == "ACADEMIC_ADMIN":
        is_professor = edition.professor_assignments.filter(
            teacher_profile=teacher, is_active=True
        ).exists()
        return True, is_professor

    is_coordinator = teacher.coordinated_subjects.filter(
        subject=edition.subject, is_active=True
    ).exists()
    is_professor = edition.professor_assignments.filter(
        teacher_profile=teacher, is_active=True
    ).exists()
    return is_coordinator, is_professor


def _get_visible_team_ids(edition: CourseEdition, user, professor_view: bool = False) -> Optional[set]:
    """
    Returns the set of team IDs the user is restricted to, or None if unrestricted
    (admin, coordinator, or professor with no specific team assignments).
    When professor_view=True, coordinators who are also professors of this edition
    will be filtered to their professor-assigned teams instead of seeing all.
    """
    if user is None:
        return None

    try:
        teacher = user.teacher_profile
    except Exception:
        teacher = None

    is_superuser = getattr(user, "is_superuser", False)
    is_admin = (
        teacher is not None
        and teacher.is_active_teacher
        and teacher.global_role == "ACADEMIC_ADMIN"
    )
    is_coordinator = (
        teacher is not None
        and teacher.is_active_teacher
        and teacher.coordinated_subjects.filter(subject=edition.subject, is_active=True).exists()
    )

    has_full_access = is_superuser or is_admin or is_coordinator

    if has_full_access and not professor_view:
        return None  # coordinator/admin mode: unrestricted access to all teams

    if not has_full_access and (teacher is None or not teacher.is_active_teacher):
        return None  # reader or no teacher profile — permissions already validated upstream

    # Either professor_view=True (coordinator/admin switching to professor view)
    # or a regular professor. In both cases, restrict to assigned teams.
    from .models import ProfessorTeamAssignment
    try:
        prof_assignment = edition.professor_assignments.get(
            teacher_profile=teacher, is_active=True
        )
    except Exception:
        return None  # no professor assignment → unrestricted fallback

    assigned_ids = set(
        ProfessorTeamAssignment.objects.filter(
            edition_professor_assignment=prof_assignment, is_active=True
        ).values_list("course_team_id", flat=True)
    )

    return assigned_ids if assigned_ids else None


# Display names for known LD individual metric base IDs (used in settings panel)
_LD_BASE_METRIC_DISPLAY: Dict[str, str] = {
    "assignedtasks": "Tasks",
    "closedtasks": "Closed tasks",
    "commits": "Commits",
    "modifiedlines": "Modified lines",
}

# Suffixes to strip from LD individual metric names to extract the person name.
# Order matters: longer suffixes must come first.
_LD_INDIVIDUAL_NAME_SUFFIXES = [
    " closed tasks",
    " modified lines",
    " tasks",
    " commits",
]


def _ld_extract_person_name(metric_name: str) -> str:
    """Strip the metric type suffix from a LD individual metric name to get the person name."""
    lower = metric_name.lower()
    for suffix in _LD_INDIVIDUAL_NAME_SUFFIXES:
        if lower.endswith(suffix):
            return metric_name[: len(metric_name) - len(suffix)].strip()
    return metric_name


def _fetch_ld_payload(external_project_id: str) -> Tuple[Dict, str]:
    """
    Fetch current metrics from Learning Dashboard for the given project externalId.
    Returns (payload_dict, computed_at_iso) in the same format as an internal snapshot.
    On any network or parsing error, returns an empty payload so the team still appears.
    """
    base_url = getattr(settings, "LD_TAIGA_BACKEND_URL", "https://gessi-dashboard.essi.upc.edu").rstrip("/")
    timeout = getattr(settings, "LD_TAIGA_TIMEOUT", 15)
    computed_at = datetime.now(dt_timezone.utc).isoformat()

    try:
        resp = requests.get(
            f"{base_url}/api/metrics/current",
            params={"prj": external_project_id},
            timeout=timeout,
        )
        resp.raise_for_status()
        ld_list = resp.json()
    except Exception as exc:
        logger.warning("LD metrics fetch failed for %s: %s", external_project_id, exc)
        return {"metrics": [], "students": [], "metrics_categories": [], "is_new_project": True}, computed_at

    if not isinstance(ld_list, list):
        return {"metrics": [], "students": [], "metrics_categories": [], "is_new_project": True}, computed_at

    try:
        cat_resp = requests.get(
            f"{base_url}/api/metrics/categories",
            params={"prj": external_project_id},
            timeout=timeout,
        )
        cat_resp.raise_for_status()
        _cat_data = cat_resp.json()
        metrics_categories = _cat_data if isinstance(_cat_data, list) else []
    except Exception:
        metrics_categories = []

    # Fetch the metrics catalog to get categoryName per metric (same as the student metrics view).
    # This map lets the frontend look up the right color palette for each metric.
    category_name_map: Dict[str, str] = {}
    try:
        catalog_resp = requests.get(
            f"{base_url}/api/metrics",
            params={"prj": external_project_id},
            timeout=timeout,
        )
        catalog_resp.raise_for_status()
        _catalog_data = catalog_resp.json()
        catalog_entries = _catalog_data if isinstance(_catalog_data, list) else (
            _catalog_data.get("results", []) if isinstance(_catalog_data, dict) else []
        )
        for entry in catalog_entries:
            if not isinstance(entry, dict):
                continue
            ext_id = entry.get("externalId") or entry.get("id")
            cat_name = entry.get("categoryName") or entry.get("category")
            if ext_id and cat_name:
                category_name_map[str(ext_id).strip().lower()] = cat_name
    except Exception:
        pass

    metrics = []
    # Keyed by person display name to group metrics across different username formats
    students_dict: Dict[str, Dict] = {}

    for m in ld_list:
        if not isinstance(m, dict) or not m.get("id"):
            continue

        scope = m.get("scope", "team")
        metric_id = m["id"]
        ld_name = m.get("name", metric_id)
        value = float(m.get("value") or 0)
        value_description = m.get("value_description", "")
        description = m.get("description", "")
        quality_factors = m.get("qualityFactors", [])

        if scope == "individual":
            # Derive base metric id and display name for settings deduplication
            base_id = metric_id.split("_", 1)[0]
            username = metric_id.split("_", 1)[1] if "_" in metric_id else metric_id
            base_display = _LD_BASE_METRIC_DISPLAY.get(base_id, base_id.capitalize())

            # Format name with · so the settings panel regex strips the username suffix
            metric_name = f"{base_display} · {username}"

            # Group by person display name (consistent across different username formats)
            person_name = _ld_extract_person_name(ld_name)
            if person_name not in students_dict:
                students_dict[person_name] = {
                    "username": username,
                    "name": person_name,
                    "displayName": person_name,
                    "identities": {},
                    "metrics": [],
                }
            cat_name = category_name_map.get(metric_id.lower())
            students_dict[person_name]["metrics"].append({
                "id": metric_id,
                "name": ld_name,
                "base_name": base_display,
                "value": value,
                "value_description": value_description,
                "description": description,
                "qualityFactors": quality_factors,
                "classification": "team",
                "scope": scope,
                "student": username,
                **( {"categoryName": cat_name} if cat_name else {} ),
            })
        else:
            metric_name = ld_name

        cat_name = category_name_map.get(metric_id.lower())
        metrics.append({
            "id": metric_id,
            "name": metric_name,
            "value": value,
            "value_description": value_description,
            "description": description,
            "qualityFactors": quality_factors,
            "classification": "team" if scope == "individual" else "project",
            "scope": scope,
            **( {"categoryName": cat_name} if cat_name else {} ),
        })

    return {
        "metrics": metrics,
        "students": list(students_dict.values()),
        "metrics_categories": metrics_categories,
        "is_new_project": len(metrics) == 0,
    }, computed_at


def _collect_team_snapshots(edition: CourseEdition, *, force: bool, visible_team_ids: Optional[set] = None) -> List[Dict]:
    teams = (
        edition.teams
        .filter(is_active=True)
        .select_related("project_link__project")
    )

    if visible_team_ids is not None:
        teams = teams.filter(pk__in=visible_team_ids)

    result = []
    for team in teams:
        link = getattr(team, "project_link", None)
        if link is None or not link.is_active:
            continue

        project = link.project

        try:
            config = project.metrics_config
            use_external = config.provider == "external" and bool(config.external_project_id)
        except Exception:
            use_external = False

        if use_external:
            payload, computed_at = _fetch_ld_payload(config.external_project_id)
        else:
            snapshot = get_or_build_snapshot(project, use_cache=not force, force=force)
            payload = snapshot.payload or {}
            computed_at = snapshot.computed_at.isoformat()

        result.append({
            "group_id": team.pk,
            "group_code": team.team_code,
            "display_name": team.display_name,
            "project_id": project.pk,
            "project_slug": project.slug,
            "project_name": project.name,
            "snapshot_computed_at": computed_at,
            "metrics_provider": "external" if use_external else "internal",
            "metrics": payload.get("metrics", []),
            "students": payload.get("students", []),
            "metrics_categories": payload.get("metrics_categories", []),
            "is_new_project": payload.get("is_new_project", True),
        })

    return result


def _aggregate_metrics(teams_data: List[Dict]) -> Dict:
    """
    For each metric_id that appears across teams, compute avg/min/max
    and the per-team breakdown. Only aggregates project-level metrics
    (classification == "project") with numeric values.
    """
    buckets: Dict[str, Dict] = {}

    for team in teams_data:
        for metric in team.get("metrics", []):
            if not isinstance(metric, dict):
                continue
            if metric.get("classification") != "project":
                continue

            raw_value = metric.get("value")
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue

            metric_id = metric.get("id", "")
            if not metric_id:
                continue

            if metric_id not in buckets:
                buckets[metric_id] = {
                    "metric_id": metric_id,
                    "metric_name": metric.get("name", metric_id),
                    "description": metric.get("description", ""),
                    "quality_factors": metric.get("qualityFactors", []),
                    "values": [],
                }

            buckets[metric_id]["values"].append({
                "group_id": team["group_id"],
                "group_code": team["group_code"],
                "value": value,
                "value_description": metric.get("value_description", ""),
            })

    aggregated = {}
    for metric_id, bucket in buckets.items():
        values = [entry["value"] for entry in bucket["values"]]
        if not values:
            continue
        aggregated[metric_id] = {
            **bucket,
            "avg": round(sum(values) / len(values), 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
        }

    return aggregated


def _apply_policy(edition: CourseEdition, teams_data: List[Dict], aggregated: Dict) -> Dict:
    """
    Apply CourseMetricsPolicy for the edition:
    - Remove metrics listed in hidden_metric_ids from aggregated and team metrics.
    - Reorder aggregated according to project_metric_order.
    - Reorder per-team metric lists according to project_metric_order and team_metric_order.

    hidden_metric_ids stores base metric IDs (e.g. "task_completion"). A metric
    is hidden if its full ID starts with any hidden base ID followed by "_".
    """
    policy = _get_policy(edition)
    if policy is None:
        return aggregated

    hidden: List[str] = policy.hidden_metric_ids or []
    project_order: List[str] = policy.project_metric_order or []
    team_order: List[str] = policy.team_metric_order or []

    if not hidden and not project_order and not team_order:
        return aggregated

    def is_hidden(metric_id: str) -> bool:
        for base in hidden:
            if metric_id == base or metric_id.startswith(f"{base}_"):
                return True
        return False

    def rank(order_list: List[str], metric_id: str) -> int:
        for i, base in enumerate(order_list):
            if metric_id == base or metric_id.startswith(f"{base}_"):
                return i
        return len(order_list)

    # Filter aggregated
    filtered = {mid: data for mid, data in aggregated.items() if not is_hidden(mid)}

    # Filter and reorder per-team metric lists
    for team in teams_data:
        metrics = [m for m in team.get("metrics", []) if not is_hidden(m.get("id", ""))]
        if project_order or team_order:
            proj = sorted(
                [m for m in metrics if m.get("classification") == "project"],
                key=lambda m: rank(project_order, m.get("id", ""))
            ) if project_order else [m for m in metrics if m.get("classification") == "project"]
            team_m = sorted(
                [m for m in metrics if m.get("classification") == "team"],
                key=lambda m: rank(team_order, m.get("id", ""))
            ) if team_order else [m for m in metrics if m.get("classification") == "team"]
            other = [m for m in metrics if m.get("classification") not in ("project", "team")]
            metrics = proj + team_m + other
        team["metrics"] = metrics

    # Reorder aggregated by project_metric_order
    if project_order:
        filtered = dict(sorted(filtered.items(), key=lambda kv: rank(project_order, kv[0])))

    return filtered


def _apply_student_drilldown_policy(edition: CourseEdition, teams_data: List[Dict]) -> None:
    """
    If CourseMetricsPolicy.allow_student_drilldown is False, remove all
    individual student data from the teams payload (GDPR compliance).
    Adds drilldown_allowed flag to each team so the frontend can hide the
    students section entirely rather than showing "no students found".
    Modifies teams_data in place.
    """
    policy = _get_policy(edition)
    drilldown_allowed = policy is None or bool(policy.allow_student_drilldown)
    for team in teams_data:
        team["drilldown_allowed"] = drilldown_allowed
    if not drilldown_allowed:
        for team in teams_data:
            team["students"] = []
            team["metrics"] = [
                m for m in team.get("metrics", [])
                if m.get("classification") != "team"
            ]


def _get_policy(edition: CourseEdition):
    """Return the CourseMetricsPolicy for an edition, or None if absent."""
    from .models import CourseMetricsPolicy
    try:
        return edition.metrics_policy
    except CourseMetricsPolicy.DoesNotExist:
        return None
