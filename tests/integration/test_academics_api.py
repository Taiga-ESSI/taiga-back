# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

import pytest
from django.urls import reverse

from taiga.base.utils import json

from .. import factories as f

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Bloque B — SubjectViewSet
# ---------------------------------------------------------------------------

def test_admin_can_create_subject(client):
    user = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=True)

    url = reverse("academics-subjects-list")
    data = {"code": "CS101", "name": "Introduction to CS", "department": "CS"}
    client.login(user)
    response = client.json.post(url, json.dumps(data))

    assert response.status_code == 201


def test_professor_cannot_create_subject(client):
    user = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=False)

    url = reverse("academics-subjects-list")
    data = {"code": "CS102", "name": "Data Structures", "department": "CS"}
    client.login(user)
    response = client.json.post(url, json.dumps(data))

    assert response.status_code == 403


def test_active_teacher_can_list_subjects(client):
    user = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=False)

    url = reverse("academics-subjects-list")
    client.login(user)
    response = client.json.get(url)

    assert response.status_code == 200


def test_admin_sees_all_subjects(client):
    admin = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=admin, is_active_teacher=True, is_academic_admin=True)
    f.SubjectFactory.create()
    f.SubjectFactory.create()

    url = reverse("academics-subjects-list")
    client.login(admin)
    response = client.json.get(url)

    assert response.status_code == 200
    assert len(response.data) >= 2


# ---------------------------------------------------------------------------
# Bloque B — TeacherProfileViewSet
# ---------------------------------------------------------------------------

def test_admin_can_list_teacher_profiles(client):
    admin = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=admin, is_active_teacher=True, is_academic_admin=True)
    f.TeacherProfileFactory.create()

    url = reverse("academics-teachers-list")
    client.login(admin)
    response = client.json.get(url)

    assert response.status_code == 200
    assert len(response.data) >= 2


def test_admin_can_create_teacher_profile(client):
    admin = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=admin, is_active_teacher=True, is_academic_admin=True)
    new_user = f.UserFactory.create()

    url = reverse("academics-teachers-list")
    data = {"user_id": new_user.id, "is_academic_admin": False, "is_active_teacher": True}
    client.login(admin)
    response = client.json.post(url, json.dumps(data))

    assert response.status_code == 201


def test_professor_cannot_create_teacher_profile(client):
    user = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=False)
    other_user = f.UserFactory.create()

    url = reverse("academics-teachers-list")
    data = {"user_id": other_user.id, "is_academic_admin": False, "is_active_teacher": True}
    client.login(user)
    response = client.json.post(url, json.dumps(data))

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Bloque B — EditionProfessorAssignmentViewSet
# ---------------------------------------------------------------------------

def test_admin_can_assign_professor_to_edition(client):
    admin = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=admin, is_active_teacher=True, is_academic_admin=True)

    prof_user = f.UserFactory.create()
    prof_teacher = f.TeacherProfileFactory.create(
        user=prof_user, is_active_teacher=True, is_academic_admin=False
    )
    edition = f.CourseEditionFactory.create()

    url = reverse("academics-professor-assignments-list")
    data = {
        "course_edition_id": edition.id,
        "teacher_profile_id": prof_teacher.id,
        "is_active": True,
    }
    client.login(admin)
    response = client.json.post(url, json.dumps(data))

    assert response.status_code == 201


def test_coordinator_can_assign_professor_to_edition(client):
    coord_user = f.UserFactory.create()
    coord_teacher = f.TeacherProfileFactory.create(
        user=coord_user, is_active_teacher=True, is_academic_admin=False
    )
    subject = f.SubjectFactory.create()
    edition = f.CourseEditionFactory.create(subject=subject)
    f.SubjectCoordinatorAssignmentFactory.create(subject=subject, teacher_profile=coord_teacher)

    prof_user = f.UserFactory.create()
    prof_teacher = f.TeacherProfileFactory.create(
        user=prof_user, is_active_teacher=True, is_academic_admin=False
    )

    url = reverse("academics-professor-assignments-list")
    data = {
        "course_edition_id": edition.id,
        "teacher_profile_id": prof_teacher.id,
        "is_active": True,
    }
    client.login(coord_user)
    response = client.json.post(url, json.dumps(data))

    assert response.status_code == 201


def test_non_coordinator_professor_cannot_assign_professor(client):
    user = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=user, is_active_teacher=True, is_academic_admin=False)

    prof_user = f.UserFactory.create()
    prof_teacher = f.TeacherProfileFactory.create(
        user=prof_user, is_active_teacher=True, is_academic_admin=False
    )
    edition = f.CourseEditionFactory.create()

    url = reverse("academics-professor-assignments-list")
    data = {
        "course_edition_id": edition.id,
        "teacher_profile_id": prof_teacher.id,
        "is_active": True,
    }
    client.login(user)
    response = client.json.post(url, json.dumps(data))

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Bloque B — ProfessorTeamAssignmentViewSet
# ---------------------------------------------------------------------------

def test_coordinator_can_assign_team_to_professor(client):
    coord_user = f.UserFactory.create()
    coord_teacher = f.TeacherProfileFactory.create(
        user=coord_user, is_active_teacher=True, is_academic_admin=False
    )
    subject = f.SubjectFactory.create()
    edition = f.CourseEditionFactory.create(subject=subject)
    f.SubjectCoordinatorAssignmentFactory.create(subject=subject, teacher_profile=coord_teacher)

    prof_user = f.UserFactory.create()
    prof_teacher = f.TeacherProfileFactory.create(
        user=prof_user, is_active_teacher=True, is_academic_admin=False
    )
    prof_assignment = f.EditionProfessorAssignmentFactory.create(
        course_edition=edition, teacher_profile=prof_teacher
    )
    team = f.CourseTeamFactory.create(course_edition=edition)

    url = reverse("academics-team-assignments-list")
    data = {
        "edition_professor_assignment_id": prof_assignment.id,
        "course_team_id": team.id,
        "is_active": True,
    }
    client.login(coord_user)
    response = client.json.post(url, json.dumps(data))

    assert response.status_code == 201


def test_admin_can_assign_team_to_professor(client):
    admin = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=admin, is_active_teacher=True, is_academic_admin=True)

    prof_user = f.UserFactory.create()
    prof_teacher = f.TeacherProfileFactory.create(
        user=prof_user, is_active_teacher=True, is_academic_admin=False
    )
    edition = f.CourseEditionFactory.create()
    prof_assignment = f.EditionProfessorAssignmentFactory.create(
        course_edition=edition, teacher_profile=prof_teacher
    )
    team = f.CourseTeamFactory.create(course_edition=edition)

    url = reverse("academics-team-assignments-list")
    data = {
        "edition_professor_assignment_id": prof_assignment.id,
        "course_team_id": team.id,
        "is_active": True,
    }
    client.login(admin)
    response = client.json.post(url, json.dumps(data))

    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Bloque B — CourseEditionViewSet.teams action
# ---------------------------------------------------------------------------

def test_coordinator_can_list_teams_in_edition(client):
    user = f.UserFactory.create()
    teacher = f.TeacherProfileFactory.create(
        user=user, is_active_teacher=True, is_academic_admin=False
    )
    subject = f.SubjectFactory.create()
    edition = f.CourseEditionFactory.create(subject=subject)
    f.SubjectCoordinatorAssignmentFactory.create(subject=subject, teacher_profile=teacher)
    f.CourseTeamFactory.create(course_edition=edition)
    f.CourseTeamFactory.create(course_edition=edition)

    url = reverse("academics-course-editions-teams", kwargs={"key": edition.key})
    client.login(user)
    response = client.json.get(url)

    assert response.status_code == 200
    assert len(response.data) == 2


def test_professor_can_list_teams_in_assigned_edition(client):
    user = f.UserFactory.create()
    teacher = f.TeacherProfileFactory.create(
        user=user, is_active_teacher=True, is_academic_admin=False
    )
    edition = f.CourseEditionFactory.create()
    f.EditionProfessorAssignmentFactory.create(course_edition=edition, teacher_profile=teacher)
    f.CourseTeamFactory.create(course_edition=edition)

    url = reverse("academics-course-editions-teams", kwargs={"key": edition.key})
    client.login(user)
    response = client.json.get(url)

    # professors can read (teams_perms = IsAcademicAdmin() | IsEditionCoordinator())
    # but a plain professor without coordinator role is denied
    assert response.status_code == 403


def test_coordinator_can_create_team_in_edition(client):
    user = f.UserFactory.create()
    teacher = f.TeacherProfileFactory.create(
        user=user, is_active_teacher=True, is_academic_admin=False
    )
    subject = f.SubjectFactory.create()
    edition = f.CourseEditionFactory.create(subject=subject)
    f.SubjectCoordinatorAssignmentFactory.create(subject=subject, teacher_profile=teacher)

    url = reverse("academics-course-editions-teams", kwargs={"key": edition.key})
    data = {"team_code": "G01", "display_name": "Group 01"}
    client.login(user)
    response = client.json.post(url, json.dumps(data))

    assert response.status_code == 201


def test_admin_can_create_team_in_edition(client):
    admin = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=admin, is_active_teacher=True, is_academic_admin=True)
    edition = f.CourseEditionFactory.create()

    url = reverse("academics-course-editions-teams", kwargs={"key": edition.key})
    data = {"team_code": "G02", "display_name": "Group 02"}
    client.login(admin)
    response = client.json.post(url, json.dumps(data))

    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Bloque B.2 — SubjectViewSet: instructor_check y filtros
# ---------------------------------------------------------------------------

def test_teacher_with_one_edition_gets_single_edition_key(client):
    user = f.UserFactory.create()
    teacher = f.TeacherProfileFactory.create(
        user=user, is_active_teacher=True, is_academic_admin=False
    )
    subject = f.SubjectFactory.create()
    edition = f.CourseEditionFactory.create(subject=subject)
    f.EditionProfessorAssignmentFactory.create(course_edition=edition, teacher_profile=teacher)

    url = reverse("academics-subjects-instructor-check")
    client.login(user)
    response = client.json.get(url)

    assert response.status_code == 200
    assert response.data["is_instructor"] is True
    assert response.data["single_edition_key"] == edition.key


def test_teacher_with_multiple_editions_gets_no_single_key(client):
    user = f.UserFactory.create()
    teacher = f.TeacherProfileFactory.create(
        user=user, is_active_teacher=True, is_academic_admin=False
    )
    subject = f.SubjectFactory.create()
    e1 = f.CourseEditionFactory.create(subject=subject)
    e2 = f.CourseEditionFactory.create(subject=subject)
    f.EditionProfessorAssignmentFactory.create(course_edition=e1, teacher_profile=teacher)
    f.EditionProfessorAssignmentFactory.create(course_edition=e2, teacher_profile=teacher)

    url = reverse("academics-subjects-instructor-check")
    client.login(user)
    response = client.json.get(url)

    assert response.status_code == 200
    assert response.data["single_edition_key"] is None


def test_admin_can_filter_subjects_by_is_active(client):
    admin = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=admin, is_active_teacher=True, is_academic_admin=True)
    f.SubjectFactory.create(is_active=True)
    f.SubjectFactory.create(is_active=False)

    url = reverse("academics-subjects-list") + "?is_active=true"
    client.login(admin)
    response = client.json.get(url)

    assert response.status_code == 200
    assert all(s["is_active"] for s in response.data)


def test_admin_can_filter_subjects_by_search(client):
    admin = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=admin, is_active_teacher=True, is_academic_admin=True)
    f.SubjectFactory.create(name="Algebra", code="ALG01")
    f.SubjectFactory.create(name="Physics", code="PHY01")

    url = reverse("academics-subjects-list") + "?search=Algebra"
    client.login(admin)
    response = client.json.get(url)

    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["name"] == "Algebra"


# ---------------------------------------------------------------------------
# Bloque B.3 — CourseEditionViewSet: filtros de queryset
# ---------------------------------------------------------------------------

def test_admin_can_filter_editions_by_status(client):
    admin = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=admin, is_active_teacher=True, is_academic_admin=True)
    f.CourseEditionFactory.create(status="PLANNED")
    f.CourseEditionFactory.create(status="ACTIVE")

    url = reverse("academics-course-editions-list") + "?status=PLANNED"
    client.login(admin)
    response = client.json.get(url)

    assert response.status_code == 200
    assert all(e["status"] == "PLANNED" for e in response.data)


def test_admin_can_filter_editions_by_academic_year(client):
    admin = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=admin, is_active_teacher=True, is_academic_admin=True)
    f.CourseEditionFactory.create(academic_year=2023)
    f.CourseEditionFactory.create(academic_year=2024)

    url = reverse("academics-course-editions-list") + "?academic_year=2024"
    client.login(admin)
    response = client.json.get(url)

    assert response.status_code == 200
    assert all(e["academic_year"] == 2024 for e in response.data)


# ---------------------------------------------------------------------------
# Bloque B.4 — filtros en otros ViewSets
# ---------------------------------------------------------------------------

def test_admin_can_filter_professor_assignments_by_edition(client):
    admin = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=admin, is_active_teacher=True, is_academic_admin=True)
    edition1 = f.CourseEditionFactory.create()
    edition2 = f.CourseEditionFactory.create()
    prof = f.TeacherProfileFactory.create()
    f.EditionProfessorAssignmentFactory.create(course_edition=edition1, teacher_profile=prof)
    f.EditionProfessorAssignmentFactory.create(course_edition=edition2, teacher_profile=prof)

    url = "{}?course_edition_id={}".format(
        reverse("academics-professor-assignments-list"), edition1.id
    )
    client.login(admin)
    response = client.json.get(url)

    assert response.status_code == 200
    assert len(response.data) == 1


def test_admin_can_filter_team_assignments_by_team(client):
    admin = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=admin, is_active_teacher=True, is_academic_admin=True)
    edition = f.CourseEditionFactory.create()
    prof = f.TeacherProfileFactory.create()
    prof_assignment = f.EditionProfessorAssignmentFactory.create(
        course_edition=edition, teacher_profile=prof
    )
    team1 = f.CourseTeamFactory.create(course_edition=edition)
    team2 = f.CourseTeamFactory.create(course_edition=edition)
    f.ProfessorTeamAssignmentFactory.create(
        edition_professor_assignment=prof_assignment, course_team=team1
    )
    f.ProfessorTeamAssignmentFactory.create(
        edition_professor_assignment=prof_assignment, course_team=team2
    )

    url = "{}?course_team_id={}".format(
        reverse("academics-team-assignments-list"), team1.id
    )
    client.login(admin)
    response = client.json.get(url)

    assert response.status_code == 200
    assert len(response.data) == 1


def test_admin_can_filter_coordinator_assignments_by_subject(client):
    admin = f.UserFactory.create()
    f.TeacherProfileFactory.create(user=admin, is_active_teacher=True, is_academic_admin=True)
    subject1 = f.SubjectFactory.create()
    subject2 = f.SubjectFactory.create()
    teacher = f.TeacherProfileFactory.create()
    f.SubjectCoordinatorAssignmentFactory.create(subject=subject1, teacher_profile=teacher)
    f.SubjectCoordinatorAssignmentFactory.create(subject=subject2, teacher_profile=teacher)

    url = "{}?subject_id={}".format(
        reverse("academics-coordinator-assignments-list"), subject1.id
    )
    client.login(admin)
    response = client.json.get(url)

    assert response.status_code == 200
    assert len(response.data) == 1
