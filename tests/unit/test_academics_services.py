# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from datetime import datetime
from datetime import timezone as dt_timezone
from unittest import mock

import pytest

from taiga.academics.services import (
    _aggregate_metrics,
    _apply_policy,
    _apply_student_drilldown_policy,
    _collect_team_snapshots,
    _fetch_ld_payload,
    _get_user_role_info,
    _get_visible_team_ids,
    get_subject_metrics,
)

from .. import factories as f

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Bloque 4 — Servicio de agregación: _get_visible_team_ids
# ---------------------------------------------------------------------------

def test_get_visible_team_ids_returns_none_for_admin():
    """Un administrador académico tiene acceso irrestricto → None."""
    user = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=True)
    edition = f.CourseEditionFactory.create()

    result = _get_visible_team_ids(edition, user)

    assert result is None


def test_get_visible_team_ids_returns_none_for_coordinator():
    """Un coordinador de la asignatura tiene acceso irrestricto → None."""
    user = f.UserFactory.create()
    teacher = f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=False)
    subject = f.SubjectFactory.create()
    edition = f.CourseEditionFactory.create(subject=subject)
    f.SubjectCoordinatorAssignmentFactory.create(subject=subject, teacher_profile=teacher)

    result = _get_visible_team_ids(edition, user)

    assert result is None


def test_get_visible_team_ids_returns_assigned_ids_for_professor_with_groups():
    """Un profesor con equipos asignados recibe un conjunto con esos IDs."""
    user = f.UserFactory.create()
    teacher = f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=False)
    edition = f.CourseEditionFactory.create()
    team = f.CourseTeamFactory.create(course_edition=edition)
    prof_assignment = f.EditionProfessorAssignmentFactory.create(
        course_edition=edition, teacher_profile=teacher
    )
    f.ProfessorTeamAssignmentFactory.create(
        edition_professor_assignment=prof_assignment, course_team=team
    )

    result = _get_visible_team_ids(edition, user)

    assert isinstance(result, set)
    assert result == {team.pk}


def test_get_visible_team_ids_returns_empty_set_for_professor_without_groups():
    """
    Un profesor asignado a la edición pero sin ProfessorTeamAssignment
    debe recibir un conjunto vacío (sin acceso a ningún equipo).

    Nota: la implementación actual devuelve None en este caso
    (assigned_ids vacío → fallback irrestricto). Si este test falla,
    la línea `return assigned_ids if assigned_ids else None`
    en services._get_visible_team_ids debe cambiarse a `return assigned_ids`
    para aplicar la restricción correctamente.
    """
    user = f.UserFactory.create()
    teacher = f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=False)
    edition = f.CourseEditionFactory.create()
    f.EditionProfessorAssignmentFactory.create(course_edition=edition, teacher_profile=teacher)
    # Sin ProfessorTeamAssignment

    result = _get_visible_team_ids(edition, user)

    assert result == set()


# ---------------------------------------------------------------------------
# Bloque A — _get_user_role_info: rutas adicionales
# ---------------------------------------------------------------------------

def test_get_user_role_info_superuser_is_coordinator_not_professor():
    """Un superusuario sin TeacherProfile es coordinador pero no profesor."""
    user = f.UserFactory.create(is_superuser=True)
    edition = f.CourseEditionFactory.create()

    is_coordinator, is_professor = _get_user_role_info(edition, user)

    assert is_coordinator is True
    assert is_professor is False


def test_get_user_role_info_superuser_with_assignment_is_professor():
    """Un superusuario con EditionProfessorAssignment también es professor."""
    user = f.UserFactory.create(is_superuser=True)
    teacher = f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=False)
    edition = f.CourseEditionFactory.create()
    f.EditionProfessorAssignmentFactory.create(course_edition=edition, teacher_profile=teacher)

    is_coordinator, is_professor = _get_user_role_info(edition, user)

    assert is_coordinator is True
    assert is_professor is True


def test_get_user_role_info_admin_with_assignment_is_both():
    """Un admin que también es professor de la edición recibe ambas flags."""
    user = f.UserFactory.create()
    teacher = f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=True)
    edition = f.CourseEditionFactory.create()
    f.EditionProfessorAssignmentFactory.create(course_edition=edition, teacher_profile=teacher)

    is_coordinator, is_professor = _get_user_role_info(edition, user)

    assert is_coordinator is True
    assert is_professor is True


def test_get_user_role_info_no_teacher_profile_returns_false_false():
    """Un usuario sin TeacherProfile no es coordinador ni profesor."""
    user = f.UserFactory.create()
    edition = f.CourseEditionFactory.create()

    is_coordinator, is_professor = _get_user_role_info(edition, user)

    assert is_coordinator is False
    assert is_professor is False


def test_get_user_role_info_coordinator_and_professor():
    """Un coordinador de la asignatura que también tiene assignment en la edición."""
    user = f.UserFactory.create()
    teacher = f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=False)
    subject = f.SubjectFactory.create()
    edition = f.CourseEditionFactory.create(subject=subject)
    f.SubjectCoordinatorAssignmentFactory.create(subject=subject, teacher_profile=teacher)
    f.EditionProfessorAssignmentFactory.create(course_edition=edition, teacher_profile=teacher)

    is_coordinator, is_professor = _get_user_role_info(edition, user)

    assert is_coordinator is True
    assert is_professor is True


# ---------------------------------------------------------------------------
# Bloque A — _aggregate_metrics
# ---------------------------------------------------------------------------

def _make_team(group_id, group_code, metrics):
    return {"group_id": group_id, "group_code": group_code, "metrics": metrics}


def _make_metric(metric_id, value, classification="project", name=None):
    return {
        "id": metric_id,
        "name": name or metric_id,
        "value": value,
        "classification": classification,
        "description": "",
        "qualityFactors": [],
        "value_description": "",
    }


def test_aggregate_metrics_computes_avg_min_max():
    teams_data = [
        _make_team(1, "T01", [_make_metric("commits", 10.0)]),
        _make_team(2, "T02", [_make_metric("commits", 20.0)]),
        _make_team(3, "T03", [_make_metric("commits", 30.0)]),
    ]

    result = _aggregate_metrics(teams_data)

    assert "commits" in result
    assert result["commits"]["avg"] == 20.0
    assert result["commits"]["min"] == 10.0
    assert result["commits"]["max"] == 30.0
    assert len(result["commits"]["values"]) == 3


def test_aggregate_metrics_ignores_team_classification():
    """Solo agrega métricas de clasificación 'project', no 'team'."""
    teams_data = [
        _make_team(1, "T01", [
            _make_metric("proj_m", 5.0, classification="project"),
            _make_metric("team_m", 3.0, classification="team"),
        ])
    ]

    result = _aggregate_metrics(teams_data)

    assert "proj_m" in result
    assert "team_m" not in result


def test_aggregate_metrics_empty_returns_empty():
    assert _aggregate_metrics([]) == {}


def test_aggregate_metrics_skips_non_numeric_values():
    teams_data = [
        _make_team(1, "T01", [_make_metric("m1", "not-a-number")]),
    ]

    result = _aggregate_metrics(teams_data)

    assert result == {}


# ---------------------------------------------------------------------------
# Bloque A — _apply_student_drilldown_policy
# ---------------------------------------------------------------------------

def test_apply_student_drilldown_policy_removes_data_when_disabled():
    """Con allow_student_drilldown=False, se eliminan students y métricas team."""
    edition = f.CourseEditionFactory.create()
    f.CourseMetricsPolicyFactory.create(course_edition=edition, allow_student_drilldown=False)

    teams_data = [
        {
            "group_id": 1,
            "metrics": [
                _make_metric("proj_m", 5.0, classification="project"),
                _make_metric("team_m", 3.0, classification="team"),
            ],
            "students": [{"name": "Alice"}],
        }
    ]

    _apply_student_drilldown_policy(edition, teams_data)

    assert teams_data[0]["drilldown_allowed"] is False
    assert teams_data[0]["students"] == []
    metric_ids = [m["id"] for m in teams_data[0]["metrics"]]
    assert "proj_m" in metric_ids
    assert "team_m" not in metric_ids


def test_apply_student_drilldown_policy_preserves_data_when_enabled():
    """Con allow_student_drilldown=True (o sin policy), se conservan students."""
    edition = f.CourseEditionFactory.create()
    # Sin policy → drilldown_allowed por defecto

    teams_data = [
        {
            "group_id": 1,
            "metrics": [_make_metric("proj_m", 5.0)],
            "students": [{"name": "Alice"}],
        }
    ]

    _apply_student_drilldown_policy(edition, teams_data)

    assert teams_data[0]["drilldown_allowed"] is True
    assert teams_data[0]["students"] == [{"name": "Alice"}]


# ---------------------------------------------------------------------------
# Bloque A — _apply_policy
# ---------------------------------------------------------------------------

def test_apply_policy_returns_aggregated_unchanged_when_no_policy():
    """Sin CourseMetricsPolicy no se modifica nada."""
    edition = f.CourseEditionFactory.create()
    aggregated = {"commits": {"metric_id": "commits", "values": []}}

    result = _apply_policy(edition, [], aggregated)

    assert result == aggregated


def test_apply_policy_filters_hidden_metrics_from_aggregated_and_teams():
    """Las métricas en hidden_metric_ids desaparecen de aggregated y de teams."""
    edition = f.CourseEditionFactory.create()
    f.CourseMetricsPolicyFactory.create(
        course_edition=edition,
        hidden_metric_ids=["commits"],
    )

    teams_data = [
        _make_team(1, "T01", [
            _make_metric("commits", 10.0),
            _make_metric("tasks", 5.0),
        ])
    ]
    aggregated = {
        "commits": {"metric_id": "commits", "values": []},
        "tasks": {"metric_id": "tasks", "values": []},
    }

    result = _apply_policy(edition, teams_data, aggregated)

    assert "commits" not in result
    assert "tasks" in result
    remaining_ids = [m["id"] for m in teams_data[0]["metrics"]]
    assert "commits" not in remaining_ids
    assert "tasks" in remaining_ids


def test_apply_policy_reorders_project_metrics():
    """project_metric_order reordena las métricas de tipo project en cada equipo."""
    edition = f.CourseEditionFactory.create()
    f.CourseMetricsPolicyFactory.create(
        course_edition=edition,
        project_metric_order=["tasks", "commits"],
    )

    teams_data = [
        _make_team(1, "T01", [
            _make_metric("commits", 10.0, classification="project"),
            _make_metric("tasks", 5.0, classification="project"),
        ])
    ]
    aggregated = {
        "commits": {"metric_id": "commits", "values": []},
        "tasks": {"metric_id": "tasks", "values": []},
    }

    _apply_policy(edition, teams_data, aggregated)

    ordered = [m["id"] for m in teams_data[0]["metrics"]]
    assert ordered == ["tasks", "commits"]


# ---------------------------------------------------------------------------
# Bloque A.2 — _collect_team_snapshots
# ---------------------------------------------------------------------------

def test_collect_team_snapshots_returns_empty_for_no_teams():
    edition = f.CourseEditionFactory.create()

    result = _collect_team_snapshots(edition, force=False, visible_team_ids=None)

    assert result == []


def test_collect_team_snapshots_skips_team_without_project_link():
    edition = f.CourseEditionFactory.create()
    f.CourseTeamFactory.create(course_edition=edition, is_active=True)

    result = _collect_team_snapshots(edition, force=False, visible_team_ids=None)

    assert result == []


def test_collect_team_snapshots_skips_inactive_link():
    from taiga.academics.models import TeamProjectLink

    edition = f.CourseEditionFactory.create()
    team = f.CourseTeamFactory.create(course_edition=edition, is_active=True)
    project = f.ProjectFactory.create()
    TeamProjectLink.objects.create(
        course_team=team, project=project, source_url="http://x.com", is_active=False
    )

    result = _collect_team_snapshots(edition, force=False, visible_team_ids=None)

    assert result == []


def test_collect_team_snapshots_uses_internal_snapshot():
    from taiga.academics.models import TeamProjectLink

    edition = f.CourseEditionFactory.create()
    team = f.CourseTeamFactory.create(course_edition=edition, is_active=True)
    project = f.ProjectFactory.create()
    TeamProjectLink.objects.create(
        course_team=team, project=project, source_url="http://x.com", is_active=True
    )

    snapshot_mock = mock.Mock()
    snapshot_mock.payload = {
        "metrics": [{"id": "m1", "value": 5.0}],
        "students": [],
        "metrics_categories": [],
        "is_new_project": False,
    }
    snapshot_mock.computed_at = datetime(2024, 1, 1, tzinfo=dt_timezone.utc)

    with mock.patch("taiga.academics.services.get_or_build_snapshot", return_value=snapshot_mock):
        result = _collect_team_snapshots(edition, force=False, visible_team_ids=None)

    assert len(result) == 1
    assert result[0]["group_id"] == team.pk
    assert result[0]["group_code"] == team.team_code
    assert result[0]["metrics"] == [{"id": "m1", "value": 5.0}]
    assert result[0]["metrics_provider"] == "internal"


def test_collect_team_snapshots_filters_by_visible_team_ids():
    from taiga.academics.models import TeamProjectLink

    edition = f.CourseEditionFactory.create()
    team1 = f.CourseTeamFactory.create(course_edition=edition, is_active=True)
    team2 = f.CourseTeamFactory.create(course_edition=edition, is_active=True)
    project1 = f.ProjectFactory.create()
    project2 = f.ProjectFactory.create()
    TeamProjectLink.objects.create(
        course_team=team1, project=project1, source_url="http://x.com", is_active=True
    )
    TeamProjectLink.objects.create(
        course_team=team2, project=project2, source_url="http://y.com", is_active=True
    )

    snapshot_mock = mock.Mock()
    snapshot_mock.payload = {"metrics": [], "students": [], "metrics_categories": [], "is_new_project": True}
    snapshot_mock.computed_at = datetime(2024, 1, 1, tzinfo=dt_timezone.utc)

    with mock.patch("taiga.academics.services.get_or_build_snapshot", return_value=snapshot_mock):
        result = _collect_team_snapshots(edition, force=False, visible_team_ids={team1.pk})

    assert len(result) == 1
    assert result[0]["group_id"] == team1.pk


# ---------------------------------------------------------------------------
# Bloque A.3 — _fetch_ld_payload
# ---------------------------------------------------------------------------

def _make_ld_resp(data):
    r = mock.Mock()
    r.raise_for_status = mock.Mock()
    r.json.return_value = data
    return r


def test_fetch_ld_payload_network_error_returns_empty():
    with mock.patch(
        "taiga.academics.services.requests.get", side_effect=ConnectionError("timeout")
    ):
        payload, computed_at = _fetch_ld_payload("EXT123")

    assert payload["metrics"] == []
    assert payload["students"] == []
    assert payload["is_new_project"] is True
    assert isinstance(computed_at, str)


def test_fetch_ld_payload_non_list_response_returns_empty():
    with mock.patch(
        "taiga.academics.services.requests.get",
        return_value=_make_ld_resp({"error": "not a list"}),
    ):
        payload, computed_at = _fetch_ld_payload("EXT123")

    assert payload["metrics"] == []
    assert payload["is_new_project"] is True


def test_fetch_ld_payload_success_with_team_metric():
    ld_metrics = [
        {
            "id": "commits",
            "name": "Commits",
            "value": "20",
            "scope": "team",
            "value_description": "",
            "description": "",
            "qualityFactors": [],
        }
    ]

    with mock.patch("taiga.academics.services.requests.get", side_effect=[
        _make_ld_resp(ld_metrics),
        _make_ld_resp([]),
        _make_ld_resp([]),
    ]):
        payload, computed_at = _fetch_ld_payload("EXT123")

    assert len(payload["metrics"]) == 1
    assert payload["metrics"][0]["id"] == "commits"
    assert payload["metrics"][0]["classification"] == "project"
    assert payload["students"] == []
    assert payload["is_new_project"] is False


def test_fetch_ld_payload_individual_metric_creates_student_entry():
    ld_metrics = [
        {
            "id": "commits_alice",
            "name": "Alice commits",
            "value": "5",
            "scope": "individual",
            "value_description": "",
            "description": "",
            "qualityFactors": [],
        }
    ]

    with mock.patch("taiga.academics.services.requests.get", side_effect=[
        _make_ld_resp(ld_metrics),
        _make_ld_resp([]),
        _make_ld_resp([]),
    ]):
        payload, computed_at = _fetch_ld_payload("EXT123")

    assert len(payload["students"]) == 1
    assert payload["students"][0]["username"] == "alice"
    assert payload["students"][0]["name"] == "Alice"
    # Individual metrics appear in main list with classification="team"
    assert any(m["classification"] == "team" for m in payload["metrics"])


def test_fetch_ld_payload_categories_api_failure_degrades_gracefully():
    """Si la API de categorías falla, el resto de la respuesta sigue siendo válida."""
    ld_metrics = [
        {
            "id": "tasks",
            "name": "Tasks",
            "value": "10",
            "scope": "team",
            "value_description": "",
            "description": "",
            "qualityFactors": [],
        }
    ]

    def fail_on_second(url, **kwargs):
        if "categories" in url:
            raise ConnectionError("categories unavailable")
        return _make_ld_resp(ld_metrics)

    with mock.patch("taiga.academics.services.requests.get", side_effect=fail_on_second):
        payload, computed_at = _fetch_ld_payload("EXT123")

    assert payload["metrics_categories"] == []
    assert len(payload["metrics"]) == 1


# ---------------------------------------------------------------------------
# Bloque A.4 — get_subject_metrics
# ---------------------------------------------------------------------------

def test_get_subject_metrics_returns_empty_for_subject_with_no_editions():
    subject = f.SubjectFactory.create()

    result = get_subject_metrics(subject)

    assert result["subject_id"] == subject.pk
    assert result["subject_code"] == subject.code
    assert result["editions"] == []


def test_get_subject_metrics_skips_editions_with_no_team_snapshots():
    subject = f.SubjectFactory.create()
    f.CourseEditionFactory.create(subject=subject)

    with mock.patch("taiga.academics.services._collect_team_snapshots", return_value=[]):
        result = get_subject_metrics(subject)

    assert result["editions"] == []


def test_get_subject_metrics_includes_editions_with_snapshots():
    subject = f.SubjectFactory.create()
    edition = f.CourseEditionFactory.create(subject=subject)
    teams_data = [
        {"group_id": 1, "group_code": "T01", "metrics": [
            _make_metric("commits", 10.0),
        ]},
    ]

    with mock.patch("taiga.academics.services._collect_team_snapshots", return_value=teams_data):
        result = get_subject_metrics(subject)

    assert len(result["editions"]) == 1
    entry = result["editions"][0]
    assert entry["edition_id"] == edition.pk
    assert entry["edition_key"] == edition.key
    assert entry["team_count"] == 1
    assert "commits" in entry["aggregated"]
