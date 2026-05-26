# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.conf import settings
from django.contrib.auth import get_user_model

from taiga.base import response
from taiga.base.api import ModelCrudViewSet
from taiga.base.api.utils import get_object_or_404
from taiga.base.decorators import detail_route, list_route

from . import models
from . import serializers
from . import permissions

User = get_user_model()


def _is_admin_user(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    try:
        return (
            user.teacher_profile.is_active_teacher
            and user.teacher_profile.global_role == "ACADEMIC_ADMIN"
        )
    except Exception:
        return False


class SubjectViewSet(ModelCrudViewSet):
    permission_classes = (permissions.SubjectPermission,)
    serializer_class = serializers.SubjectSerializer

    def get_queryset(self):
        qs = models.Subject.objects.all()

        if not _is_admin_user(self.request.user):
            accessible = permissions.get_accessible_edition_ids(self.request.user)
            qs = qs.filter(editions__in=accessible).distinct()

        is_active = self.request.QUERY_PARAMS.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")
        search = self.request.QUERY_PARAMS.get("search")
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(code__icontains=search)
        return qs.distinct()

    @list_route(methods=["get"])
    def instructor_check(self, request):
        self.check_permissions(request, "instructor_check", None)
        from .permissions import get_accessible_edition_ids
        accessible = get_accessible_edition_ids(request.user)
        editions = list(accessible.values("pk", "key"))
        single_edition_key = editions[0]["key"] if len(editions) == 1 else None
        return response.Ok({"is_instructor": True, "single_edition_key": single_edition_key})

    @detail_route(methods=["get"])
    def metrics(self, request, pk=None):
        subject = get_object_or_404(models.Subject, pk=pk)
        self.check_permissions(request, "metrics", subject)

        force = request.QUERY_PARAMS.get("refresh", "").lower() in ("1", "true", "yes")

        from .services import get_subject_metrics
        data = get_subject_metrics(subject, force=force)
        return response.Ok(data)


class CourseEditionViewSet(ModelCrudViewSet):
    permission_classes = (permissions.CourseEditionPermission,)
    serializer_class = serializers.CourseEditionSerializer
    lookup_field = 'key'

    def get_queryset(self):
        qs = models.CourseEdition.objects.select_related("subject").all()

        if not _is_admin_user(self.request.user):
            accessible = permissions.get_accessible_edition_ids(self.request.user)
            qs = qs.filter(pk__in=accessible)

        if self.request.QUERY_PARAMS.get("subject_id"):
            qs = qs.filter(subject_id=self.request.QUERY_PARAMS["subject_id"])
        if self.request.QUERY_PARAMS.get("status"):
            qs = qs.filter(status=self.request.QUERY_PARAMS["status"])
        if self.request.QUERY_PARAMS.get("academic_year"):
            qs = qs.filter(academic_year=self.request.QUERY_PARAMS["academic_year"])
        if self.request.QUERY_PARAMS.get("term"):
            qs = qs.filter(term=self.request.QUERY_PARAMS["term"])
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @detail_route(methods=["get"])
    def dashboard(self, request, key=None):
        edition = get_object_or_404(models.CourseEdition, key=key)
        self.check_permissions(request, "dashboard", edition)

        force = request.QUERY_PARAMS.get("refresh", "").lower() in ("1", "true", "yes")
        raw   = request.QUERY_PARAMS.get("raw", "").lower() in ("1", "true", "yes")
        professor_view = request.QUERY_PARAMS.get("professor_view", "").lower() in ("1", "true", "yes")

        from .services import get_edition_dashboard
        from .permissions import IsEditionCoordinator
        data = get_edition_dashboard(edition, force=force, raw=raw, requesting_user=request.user, professor_view=professor_view)
        data["can_edit_settings"] = (
            _is_admin_user(request.user) or
            IsEditionCoordinator().check_permissions(request, self, edition)
        )
        return response.Ok(data)

    @detail_route(methods=["get", "post"])
    def teams(self, request, key=None):
        edition = get_object_or_404(models.CourseEdition, key=key)
        self.check_permissions(request, "teams", edition)

        if request.method == "GET":
            qs = edition.teams.all()
            if request.QUERY_PARAMS.get("is_active"):
                qs = qs.filter(is_active=request.QUERY_PARAMS["is_active"].lower() == "true")
            serializer = serializers.CourseTeamSerializer(qs, many=True)
            return response.Ok(serializer.data)

        # POST — create a new team in this edition
        data = request.DATA.copy()
        data["course_edition_id"] = edition.pk
        serializer = serializers.CourseTeamSerializer(data=data)
        if serializer.is_valid():
            serializer.save(course_edition=edition, created_by=request.user)
            return response.Created(serializer.data)
        return response.BadRequest(serializer.errors)


class CourseTeamViewSet(ModelCrudViewSet):
    permission_classes = (permissions.CourseTeamPermission,)
    serializer_class = serializers.CourseTeamSerializer

    def get_queryset(self):
        qs = models.CourseTeam.objects.select_related(
            "course_edition", "project_link__project"
        ).all()

        if not _is_admin_user(self.request.user):
            accessible = permissions.get_accessible_edition_ids(self.request.user)
            qs = qs.filter(course_edition__in=accessible)

        if self.request.QUERY_PARAMS.get("edition"):
            qs = qs.filter(course_edition_id=self.request.QUERY_PARAMS["edition"])
        if self.request.QUERY_PARAMS.get("is_active"):
            qs = qs.filter(is_active=self.request.QUERY_PARAMS["is_active"].lower() == "true")
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @detail_route(methods=["get", "post", "patch", "delete"])
    def project_link(self, request, pk=None):
        team = get_object_or_404(models.CourseTeam, pk=pk)

        if request.method == "GET":
            self.check_permissions(request, "project_link", team)
            link = getattr(team, "project_link", None)
            if link is None:
                return response.NotFound()
            return response.Ok(serializers.TeamProjectLinkSerializer(link).data)

        if request.method == "POST":
            self.check_permissions(request, "project_link_update", team)
            if hasattr(team, "project_link"):
                return response.BadRequest({"error": "ACADEMICS.TEAM_ALREADY_HAS_PROJECT_LINK"})
            serializer = serializers.TeamProjectLinkSerializer(data=request.DATA)
            if serializer.is_valid():
                serializer.save(course_team=team, linked_by=request.user)
                return response.Created(serializer.data)
            return response.BadRequest(serializer.errors)

        if request.method == "PATCH":
            self.check_permissions(request, "project_link_update", team)
            link = get_object_or_404(models.TeamProjectLink, course_team=team)
            serializer = serializers.TeamProjectLinkSerializer(
                link, data=request.DATA, partial=True
            )
            if serializer.is_valid():
                serializer.save()
                return response.Ok(serializer.data)
            return response.BadRequest(serializer.errors)

        if request.method == "DELETE":
            self.check_permissions(request, "project_link_update", team)
            link = get_object_or_404(models.TeamProjectLink, course_team=team)
            link.delete()
            return response.NoContent()


class TeacherProfileViewSet(ModelCrudViewSet):
    permission_classes = (permissions.TeacherProfilePermission,)
    serializer_class = serializers.TeacherProfileSerializer

    def get_queryset(self):
        qs = models.TeacherProfile.objects.select_related("user").all()
        if self.request.QUERY_PARAMS.get("is_active_teacher"):
            qs = qs.filter(
                is_active_teacher=self.request.QUERY_PARAMS["is_active_teacher"].lower() == "true"
            )
        if self.request.QUERY_PARAMS.get("global_role"):
            qs = qs.filter(global_role=self.request.QUERY_PARAMS["global_role"])
        if self.request.QUERY_PARAMS.get("search"):
            search = self.request.QUERY_PARAMS["search"]
            qs = qs.filter(user__username__icontains=search) | \
                 qs.filter(user__first_name__icontains=search) | \
                 qs.filter(user__last_name__icontains=search)
        return qs.distinct()

    def perform_create(self, serializer):
        user_id = self.request.DATA.get("user_id")
        user = get_object_or_404(User, pk=user_id)
        serializer.save(user=user)


class TeamProjectLinkViewSet(ModelCrudViewSet):
    permission_classes = (permissions.TeamProjectLinkPermission,)
    serializer_class = serializers.TeamProjectLinkSerializer

    def get_queryset(self):
        qs = models.TeamProjectLink.objects.select_related(
            "course_team", "project"
        ).all()
        if self.request.QUERY_PARAMS.get("team"):
            qs = qs.filter(course_team_id=self.request.QUERY_PARAMS["team"])
        return qs

    @list_route(methods=["post"])
    def resolve(self, request, **kwargs):
        """Resolve a Taiga project URL to its project_id and basic metadata."""
        self.check_permissions(request, "resolve", None)

        source_url = request.DATA.get("source_url", "").strip()
        if not source_url:
            return response.BadRequest({"error": "ACADEMICS.RESOLVE_URL_REQUIRED"})

        from taiga.projects.models import Project

        # Try to resolve by matching the slug in the URL
        slug = source_url.rstrip("/").split("/")[-1]
        project = Project.objects.filter(slug=slug).first()

        if project is None:
            return response.BadRequest({"error": "ACADEMICS.PROJECT_NOT_FOUND"})

        return response.Ok({
            "project_id": project.id,
            "project_name": project.name,
            "project_slug": project.slug,
            "description": project.description or "",
            "member_count": project.memberships.filter(user__isnull=False).count(),
            "is_accessible": True,
        })


class SubjectCoordinatorAssignmentViewSet(ModelCrudViewSet):
    permission_classes = (permissions.SubjectCoordinatorAssignmentPermission,)
    serializer_class = serializers.SubjectCoordinatorAssignmentSerializer

    def get_queryset(self):
        qs = models.SubjectCoordinatorAssignment.objects.select_related(
            "subject", "teacher_profile__user"
        ).all()
        if self.request.QUERY_PARAMS.get("subject_id"):
            qs = qs.filter(subject_id=self.request.QUERY_PARAMS["subject_id"])
        if self.request.QUERY_PARAMS.get("teacher_profile_id"):
            qs = qs.filter(teacher_profile_id=self.request.QUERY_PARAMS["teacher_profile_id"])
        if self.request.QUERY_PARAMS.get("is_active"):
            qs = qs.filter(is_active=self.request.QUERY_PARAMS["is_active"].lower() == "true")
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class EditionProfessorAssignmentViewSet(ModelCrudViewSet):
    permission_classes = (permissions.EditionProfessorAssignmentPermission,)
    serializer_class = serializers.EditionProfessorAssignmentSerializer

    def get_queryset(self):
        qs = models.EditionProfessorAssignment.objects.select_related(
            "course_edition", "teacher_profile__user"
        ).all()
        if self.request.QUERY_PARAMS.get("course_edition_id"):
            qs = qs.filter(course_edition_id=self.request.QUERY_PARAMS["course_edition_id"])
        if self.request.QUERY_PARAMS.get("teacher_profile_id"):
            qs = qs.filter(teacher_profile_id=self.request.QUERY_PARAMS["teacher_profile_id"])
        if self.request.QUERY_PARAMS.get("is_active"):
            qs = qs.filter(is_active=self.request.QUERY_PARAMS["is_active"].lower() == "true")
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ProfessorTeamAssignmentViewSet(ModelCrudViewSet):
    permission_classes = (permissions.ProfessorTeamAssignmentPermission,)
    serializer_class = serializers.ProfessorTeamAssignmentSerializer

    def get_queryset(self):
        qs = models.ProfessorTeamAssignment.objects.select_related(
            "edition_professor_assignment__teacher_profile__user",
            "edition_professor_assignment__course_edition",
            "course_team",
        ).all()
        if self.request.QUERY_PARAMS.get("edition_professor_assignment_id"):
            qs = qs.filter(
                edition_professor_assignment_id=self.request.QUERY_PARAMS["edition_professor_assignment_id"]
            )
        if self.request.QUERY_PARAMS.get("course_team_id"):
            qs = qs.filter(course_team_id=self.request.QUERY_PARAMS["course_team_id"])
        if self.request.QUERY_PARAMS.get("is_active"):
            qs = qs.filter(is_active=self.request.QUERY_PARAMS["is_active"].lower() == "true")
        return qs

    def perform_create(self, serializer):
        serializer.save(assigned_by=self.request.user)


class CourseMetricsPolicyViewSet(ModelCrudViewSet):
    permission_classes = (permissions.CourseMetricsPolicyPermission,)
    serializer_class = serializers.CourseMetricsPolicySerializer

    def get_queryset(self):
        qs = models.CourseMetricsPolicy.objects.select_related("course_edition").all()

        if not _is_admin_user(self.request.user):
            accessible = permissions.get_accessible_edition_ids(self.request.user)
            qs = qs.filter(course_edition__in=accessible)

        if self.request.QUERY_PARAMS.get("course_edition_id"):
            qs = qs.filter(course_edition_id=self.request.QUERY_PARAMS["course_edition_id"])
        if self.request.QUERY_PARAMS.get("course_edition_key"):
            qs = qs.filter(course_edition__key=self.request.QUERY_PARAMS["course_edition_key"])
        if self.request.QUERY_PARAMS.get("project_slug"):
            qs = qs.filter(
                course_edition__teams__project_link__project__slug=self.request.QUERY_PARAMS["project_slug"]
            ).distinct()
        return qs

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


