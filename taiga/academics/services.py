# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from typing import Dict, List

from taiga.projects.metrics.internal import get_or_build_snapshot

from .models import CourseEdition


def get_edition_dashboard(edition: CourseEdition, *, force: bool = False) -> Dict:
    """
    Aggregate metrics for all active groups in a CourseEdition that have a
    linked Taiga project. Uses cached snapshots (TTL-based) unless force=True.

    Returns a dict with:
      - course_edition_id, course_edition_key
      - groups: per-group snapshot summary
      - aggregated: per-metric avg/min/max across groups
    """
    groups_data = _collect_group_snapshots(edition, force=force)
    aggregated = _aggregate_metrics(groups_data)

    return {
        "course_edition_id": edition.pk,
        "course_edition_key": edition.key,
        "groups": groups_data,
        "aggregated": aggregated,
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
    # bucket: metric_id -> list of {group_id, group_code, value}
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
