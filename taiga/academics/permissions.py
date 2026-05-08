# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from taiga.base.api.permissions import (
    TaigaResourcePermission,
    PermissionComponent,
    IsAuthenticated,
    IsSuperUser,
)


# ---------------------------------------------------------------------------
# Custom permission components
# ---------------------------------------------------------------------------

class IsAcademicAdmin(PermissionComponent):
    """User has an active TeacherProfile with global_role = ACADEMIC_ADMIN."""

    def check_permissions(self, request, view, obj=None):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            profile = request.user.teacher_profile
            return profile.is_active_teacher and profile.global_role == "ACADEMIC_ADMIN"
        except Exception:
            return False


class IsActiveTeacher(PermissionComponent):
    """User has any active TeacherProfile (any role)."""

    def check_permissions(self, request, view, obj=None):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            return request.user.teacher_profile.is_active_teacher
        except Exception:
            return False


class IsSubjectCoordinator(PermissionComponent):
    """User coordinates the subject referenced by the current object or view kwargs."""

    def check_permissions(self, request, view, obj=None):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            profile = request.user.teacher_profile
            if not profile.is_active_teacher:
                return False
        except Exception:
            return False

        # Resolve subject_id from obj, view kwargs, or query params
        subject_id = None
        if obj is not None:
            if hasattr(obj, "subject_id"):
                subject_id = obj.subject_id
            elif hasattr(obj, "subject"):
                subject_id = obj.subject_id
        if subject_id is None:
            subject_id = view.kwargs.get("subject_id") or request.QUERY_PARAMS.get("subject_id")

        if subject_id is None:
            return False

        from .models import SubjectCoordinatorAssignment
        return SubjectCoordinatorAssignment.objects.filter(
            subject_id=subject_id,
            teacher_profile=profile,
            is_active=True,
        ).exists()


class IsEditionCoordinator(PermissionComponent):
    """User coordinates the subject that owns the current course edition."""

    def check_permissions(self, request, view, obj=None):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            profile = request.user.teacher_profile
            if not profile.is_active_teacher:
                return False
        except Exception:
            return False

        edition = _resolve_edition(obj, view, request)
        if edition is None:
            return False

        from .models import SubjectCoordinatorAssignment
        return SubjectCoordinatorAssignment.objects.filter(
            subject_id=edition.subject_id,
            teacher_profile=profile,
            is_active=True,
        ).exists()


class IsEditionProfessor(PermissionComponent):
    """User is assigned as professor to the current course edition."""

    def check_permissions(self, request, view, obj=None):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            profile = request.user.teacher_profile
            if not profile.is_active_teacher:
                return False
        except Exception:
            return False

        edition = _resolve_edition(obj, view, request)
        if edition is None:
            return False

        from .models import EditionProfessorAssignment
        return EditionProfessorAssignment.objects.filter(
            course_edition=edition,
            teacher_profile=profile,
            is_active=True,
        ).exists()


class IsEditionReader(PermissionComponent):
    """User has been granted explicit read access to the current course edition."""

    def check_permissions(self, request, view, obj=None):
        if not request.user or not request.user.is_authenticated:
            return False

        edition = _resolve_edition(obj, view, request)
        if edition is None:
            return False

        from .models import CourseDashboardReader
        return CourseDashboardReader.objects.filter(
            course_edition=edition,
            user=request.user,
            is_active=True,
        ).exists()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _resolve_edition(obj, view, request):
    """Try to find the CourseEdition from the current context."""
    from .models import CourseEdition, CourseGroup

    if obj is not None:
        if isinstance(obj, CourseEdition):
            return obj
        if hasattr(obj, "course_edition"):
            return obj.course_edition
        if hasattr(obj, "course_group") and hasattr(obj.course_group, "course_edition"):
            return obj.course_group.course_edition

    edition_id = view.kwargs.get("edition_id") or request.QUERY_PARAMS.get("edition_id")
    if edition_id:
        return CourseEdition.objects.filter(pk=edition_id).first()

    return None


# ---------------------------------------------------------------------------
# ViewSet permission classes
# ---------------------------------------------------------------------------

class SubjectPermission(TaigaResourcePermission):
    enough_perms = IsAcademicAdmin() | IsSuperUser()
    global_perms = None
    list_perms = IsActiveTeacher()
    retrieve_perms = IsActiveTeacher()
    create_perms = IsAcademicAdmin()
    update_perms = IsAcademicAdmin()
    partial_update_perms = IsAcademicAdmin()
    destroy_perms = IsAcademicAdmin()
    metrics_perms = IsActiveTeacher()


class CourseEditionPermission(TaigaResourcePermission):
    enough_perms = IsAcademicAdmin() | IsSuperUser()
    global_perms = None
    list_perms = IsActiveTeacher()
    retrieve_perms = IsActiveTeacher()
    create_perms = IsAcademicAdmin() | IsSubjectCoordinator()
    update_perms = IsAcademicAdmin() | IsEditionCoordinator()
    partial_update_perms = IsAcademicAdmin() | IsEditionCoordinator()
    destroy_perms = IsAcademicAdmin()
    # Custom action: dashboard
    dashboard_perms = IsActiveTeacher() | IsEditionReader()
    # Custom action: groups (list/create groups of an edition)
    groups_perms = IsAcademicAdmin() | IsEditionCoordinator()


class CourseGroupPermission(TaigaResourcePermission):
    enough_perms = IsAcademicAdmin() | IsSuperUser()
    global_perms = None
    list_perms = IsActiveTeacher()
    retrieve_perms = IsActiveTeacher()
    create_perms = IsAcademicAdmin() | IsEditionCoordinator()
    update_perms = IsAcademicAdmin() | IsEditionCoordinator()
    partial_update_perms = IsAcademicAdmin() | IsEditionCoordinator()
    destroy_perms = IsAcademicAdmin() | IsEditionCoordinator()
    # Custom action: project_link
    project_link_perms = IsActiveTeacher()
    project_link_update_perms = IsAcademicAdmin() | IsEditionCoordinator()


class TeacherProfilePermission(TaigaResourcePermission):
    enough_perms = IsAcademicAdmin() | IsSuperUser()
    global_perms = None
    list_perms = IsActiveTeacher()
    retrieve_perms = IsActiveTeacher()
    create_perms = IsAcademicAdmin()
    update_perms = IsAcademicAdmin()
    partial_update_perms = IsAcademicAdmin()
    destroy_perms = IsAcademicAdmin()


class GroupProjectLinkPermission(TaigaResourcePermission):
    enough_perms = IsAcademicAdmin() | IsSuperUser()
    global_perms = None
    list_perms = IsActiveTeacher()
    retrieve_perms = IsActiveTeacher()
    create_perms = IsAcademicAdmin() | IsEditionCoordinator()
    update_perms = IsAcademicAdmin() | IsEditionCoordinator()
    partial_update_perms = IsAcademicAdmin() | IsEditionCoordinator()
    destroy_perms = IsAcademicAdmin() | IsEditionCoordinator()
    resolve_perms = IsActiveTeacher()


class SubjectCoordinatorAssignmentPermission(TaigaResourcePermission):
    enough_perms = IsAcademicAdmin() | IsSuperUser()
    global_perms = None
    list_perms = IsActiveTeacher()
    retrieve_perms = IsActiveTeacher()
    create_perms = IsAcademicAdmin()
    update_perms = IsAcademicAdmin()
    partial_update_perms = IsAcademicAdmin()
    destroy_perms = IsAcademicAdmin()


class EditionProfessorAssignmentPermission(TaigaResourcePermission):
    enough_perms = IsAcademicAdmin() | IsSuperUser()
    global_perms = None
    list_perms = IsActiveTeacher()
    retrieve_perms = IsActiveTeacher()
    create_perms = IsAcademicAdmin() | IsEditionCoordinator()
    update_perms = IsAcademicAdmin() | IsEditionCoordinator()
    partial_update_perms = IsAcademicAdmin() | IsEditionCoordinator()
    destroy_perms = IsAcademicAdmin() | IsEditionCoordinator()


class ProfessorGroupAssignmentPermission(TaigaResourcePermission):
    enough_perms = IsAcademicAdmin() | IsSuperUser()
    global_perms = None
    list_perms = IsActiveTeacher()
    retrieve_perms = IsActiveTeacher()
    create_perms = IsAcademicAdmin() | IsEditionCoordinator()
    update_perms = IsAcademicAdmin() | IsEditionCoordinator()
    partial_update_perms = IsAcademicAdmin() | IsEditionCoordinator()
    destroy_perms = IsAcademicAdmin() | IsEditionCoordinator()
