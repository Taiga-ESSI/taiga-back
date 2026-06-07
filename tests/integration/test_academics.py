# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from unittest import mock

import pytest
from django.urls import reverse

from taiga.base.utils import json

from .. import factories as f

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Bloque 1 — Sistema de permisos
# ---------------------------------------------------------------------------

def test_user_without_teacher_profile_sees_empty_list_on_course_editions(client):
    """
    Taiga's ListModelMixin no llama check_permissions — filtra el queryset.
    Un usuario sin TeacherProfile recibe 200 con lista vacía, no 403.
    """
    user = f.UserFactory.create()
    edition = f.CourseEditionFactory.create()  # existe una edición pero no es accesible
    url = reverse("academics-course-editions-list")

    client.login(user)
    response = client.json.get(url)

    assert response.status_code == 200
    assert response.data == []


def test_active_professor_can_list_course_editions(client):
    user = f.UserFactory.create()
    teacher = f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=False)
    subject = f.SubjectFactory.create()
    edition = f.CourseEditionFactory.create(subject=subject)
    f.EditionProfessorAssignmentFactory.create(course_edition=edition, teacher_profile=teacher)

    url = reverse("academics-course-editions-list")
    client.login(user)
    response = client.json.get(url)

    assert response.status_code == 200


def test_professor_cannot_create_course_edition(client):
    user = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=False)
    subject = f.SubjectFactory.create()

    url = reverse("academics-course-editions-list")
    data = {
        "subject_id": subject.id,
        "key": "2024-Q1-TEST",
        "academic_year": 2024,
        "term": "Q1",
        "start_date": "2024-01-15",
        "end_date": "2024-05-31",
    }
    client.login(user)
    response = client.json.post(url, json.dumps(data))

    assert response.status_code == 403


def test_coordinator_can_create_course_edition(client):
    """
    IsSubjectCoordinator resolves subject_id from view kwargs or QUERY_PARAMS
    during create (obj=None), so it must be passed as a query parameter.
    """
    user = f.UserFactory.create()
    teacher = f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=False)
    subject = f.SubjectFactory.create()
    f.SubjectCoordinatorAssignmentFactory.create(subject=subject, teacher_profile=teacher)

    url = "{}?subject_id={}".format(reverse("academics-course-editions-list"), subject.id)
    data = {
        "subject_id": subject.id,
        "key": "2024-Q1-COORD",
        "academic_year": 2024,
        "term": "Q1",
        "start_date": "2024-01-15",
        "end_date": "2024-05-31",
    }
    client.login(user)
    response = client.json.post(url, json.dumps(data))

    assert response.status_code == 201


def test_professor_cannot_access_dashboard_of_unassigned_edition(client):
    user = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=False)
    # edition exists but user has no EditionProfessorAssignment
    edition = f.CourseEditionFactory.create()

    url = reverse("academics-course-editions-dashboard", kwargs={"key": edition.key})
    client.login(user)
    response = client.json.get(url)

    assert response.status_code == 403


def test_professor_can_access_dashboard_of_assigned_edition(client):
    user = f.UserFactory.create()
    teacher = f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=False)
    edition = f.CourseEditionFactory.create()
    f.EditionProfessorAssignmentFactory.create(course_edition=edition, teacher_profile=teacher)

    url = reverse("academics-course-editions-dashboard", kwargs={"key": edition.key})
    client.login(user)

    with mock.patch("taiga.academics.services._collect_team_snapshots", return_value=[]):
        response = client.json.get(url)

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Bloque 2 — Endpoint del dashboard
# ---------------------------------------------------------------------------

def test_dashboard_professor_view_false_returns_all_teams(client):
    """
    Un coordinador que también es profesor, sin professor_view, recibe
    visible_team_ids=None → _collect_team_snapshots procesa todos los equipos.
    """
    user = f.UserFactory.create()
    teacher = f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=False)
    subject = f.SubjectFactory.create()
    edition = f.CourseEditionFactory.create(subject=subject)
    f.SubjectCoordinatorAssignmentFactory.create(subject=subject, teacher_profile=teacher)
    prof_assignment = f.EditionProfessorAssignmentFactory.create(course_edition=edition, teacher_profile=teacher)
    team1 = f.CourseTeamFactory.create(course_edition=edition)
    f.ProfessorTeamAssignmentFactory.create(edition_professor_assignment=prof_assignment, course_team=team1)

    url = reverse("academics-course-editions-dashboard", kwargs={"key": edition.key})
    client.login(user)

    with mock.patch("taiga.academics.services._collect_team_snapshots", return_value=[]) as collect_mock:
        # no professor_view param → defaults to false
        response = client.json.get(url)

    assert response.status_code == 200
    args, call_kwargs = collect_mock.call_args
    assert call_kwargs["visible_team_ids"] is None


def test_dashboard_professor_view_true_restricts_to_assigned_teams(client):
    """
    Un coordinador que también es profesor, con professor_view=true, recibe
    visible_team_ids con solo sus equipos asignados.
    """
    user = f.UserFactory.create()
    teacher = f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=False)
    subject = f.SubjectFactory.create()
    edition = f.CourseEditionFactory.create(subject=subject)
    f.SubjectCoordinatorAssignmentFactory.create(subject=subject, teacher_profile=teacher)
    prof_assignment = f.EditionProfessorAssignmentFactory.create(course_edition=edition, teacher_profile=teacher)
    team1 = f.CourseTeamFactory.create(course_edition=edition)
    f.ProfessorTeamAssignmentFactory.create(edition_professor_assignment=prof_assignment, course_team=team1)

    url = "{}?professor_view=true".format(
        reverse("academics-course-editions-dashboard", kwargs={"key": edition.key})
    )
    client.login(user)

    with mock.patch("taiga.academics.services._collect_team_snapshots", return_value=[]) as collect_mock:
        response = client.json.get(url)

    assert response.status_code == 200
    args, call_kwargs = collect_mock.call_args
    assert call_kwargs["visible_team_ids"] == {team1.pk}


def test_dashboard_coordinator_without_professor_role_sees_all_teams(client):
    """
    Un coordinador que NO es profesor de la edición siempre recibe
    visible_team_ids=None, ignorando el valor de professor_view.
    """
    user = f.UserFactory.create()
    teacher = f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=False)
    subject = f.SubjectFactory.create()
    edition = f.CourseEditionFactory.create(subject=subject)
    f.SubjectCoordinatorAssignmentFactory.create(subject=subject, teacher_profile=teacher)
    # Sin EditionProfessorAssignment: is_professor=False → effective_professor_view=False

    url = "{}?professor_view=true".format(
        reverse("academics-course-editions-dashboard", kwargs={"key": edition.key})
    )
    client.login(user)

    with mock.patch("taiga.academics.services._collect_team_snapshots", return_value=[]) as collect_mock:
        response = client.json.get(url)

    assert response.status_code == 200
    args, call_kwargs = collect_mock.call_args
    assert call_kwargs["visible_team_ids"] is None
