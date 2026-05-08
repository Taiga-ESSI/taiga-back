# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from typing import Dict, List, Optional

from taiga.projects.metrics.internal import get_or_build_snapshot

from .models import CourseEdition, Subject


def get_edition_dashboard(edition: CourseEdition, *, force: bool = False) -> Dict:
    """
    Aggregate metrics for all active groups in a CourseEdition that have a
    linked Taiga project. Uses cached snapshots (TTL-based) unless force=True.
    Applies CourseMetricsPolicy filtering and ordering if one exists.
    """
    groups_data = _collect_group_snapshots(edition, force=force)
    aggregated = _aggregate_metrics(groups_data)
    aggregated = _apply_policy(edition, groups_data, aggregated)

    return {
        "course_edition_id": edition.pk,
        "course_edition_key": edition.key,
        "groups": groups_data,
        "aggregated": aggregated,
    }


def get_subject_metrics(subject: Subject, *, force: bool = False) -> Dict:
    """
    Compare aggregated metrics across all CourseEditions of a subject.
    Returns one aggregated entry per edition (only editions with linked groups).
    """
    editions = (
        subject.editions
        .prefetch_related("groups__project_link__project")
        .order_by("-academic_year", "term")
    )

    editions_data = []
    for edition in editions:
        groups_data = _collect_group_snapshots(edition, force=force)
        if not groups_data:
            continue
        aggregated = _aggregate_metrics(groups_data)
        aggregated = _apply_policy(edition, groups_data, aggregated)
        editions_data.append({
            "edition_id": edition.pk,
            "edition_key": edition.key,
            "academic_year": edition.academic_year,
            "term": edition.term,
            "status": edition.status,
            "group_count": len(groups_data),
            "aggregated": aggregated,
        })

    return {
        "subject_id": subject.pk,
        "subject_code": subject.code,
        "subject_name": subject.name,
        "editions": editions_data,
    }


def _collect_group_snapshots(edition: CourseEdition, *, force: bool) -> List[Dict]:
    groups = (
        edition.groups
        .filter(is_active=True)
        .select_related("project_link__project")
    )

    result = []
    for group in groups:
        link = getattr(group, "project_link", None)
        if link is None or not link.is_active:
            continue

        project = link.project
        snapshot = get_or_build_snapshot(project, use_cache=not force, force=force)
        payload = snapshot.payload or {}

        result.append({
            "group_id": group.pk,
            "group_code": group.group_code,
            "display_name": group.display_name,
            "project_id": project.pk,
            "project_slug": project.slug,
            "project_name": project.name,
            "snapshot_computed_at": snapshot.computed_at.isoformat(),
            "metrics": payload.get("metrics", []),
            "students": payload.get("students", []),
            "is_new_project": payload.get("is_new_project", True),
        })

    return result


def _aggregate_metrics(groups_data: List[Dict]) -> Dict:
    """
    For each metric_id that appears across groups, compute avg/min/max
    and the per-group breakdown. Only aggregates project-level metrics
    (classification == "project") with numeric values.
    """
    buckets: Dict[str, Dict] = {}

    for group in groups_data:
        for metric in group.get("metrics", []):
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
                "group_id": group["group_id"],
                "group_code": group["group_code"],
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


def _apply_policy(edition: CourseEdition, groups_data: List[Dict], aggregated: Dict) -> Dict:
    """
    Apply CourseMetricsPolicy for the edition:
    - Remove metrics listed in hidden_metric_ids from aggregated and group metrics.
    - Reorder aggregated according to project_metric_order.

    hidden_metric_ids stores base metric IDs (e.g. "task_completion"). A metric
    is hidden if its full ID starts with any hidden base ID followed by "_".
    """
    policy = _get_policy(edition)
    if policy is None:
        return aggregated

    hidden: List[str] = policy.hidden_metric_ids or []
    order: List[str] = policy.project_metric_order or []

    if not hidden and not order:
        return aggregated

    def is_hidden(metric_id: str) -> bool:
        for base in hidden:
            if metric_id == base or metric_id.startswith(f"{base}_"):
                return True
        return False

    # Filter aggregated
    filtered = {mid: data for mid, data in aggregated.items() if not is_hidden(mid)}

    # Filter per-group metrics lists too so groups are consistent
    for group in groups_data:
        group["metrics"] = [
            m for m in group.get("metrics", [])
            if not is_hidden(m.get("id", ""))
        ]

    # Reorder aggregated by project_metric_order (unrecognised keys go to the end)
    if order:
        def sort_key(metric_id: str) -> int:
            for base in order:
                if metric_id == base or metric_id.startswith(f"{base}_"):
                    return order.index(base)
            return len(order)

        filtered = dict(sorted(filtered.items(), key=lambda kv: sort_key(kv[0])))

    return filtered


def _get_policy(edition: CourseEdition):
    """Return the CourseMetricsPolicy for an edition, or None if absent."""
    from .models import CourseMetricsPolicy
    try:
        return edition.metrics_policy
    except CourseMetricsPolicy.DoesNotExist:
        return None
