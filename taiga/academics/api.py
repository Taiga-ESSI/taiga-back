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


class SubjectViewSet(ModelCrudViewSet):
    permission_classes = (permissions.SubjectPermission,)
    serializer_class = serializers.SubjectSerializer

    def get_queryset(self):
        qs = models.Subject.objects.all()
        is_active = self.request.QUERY_PARAMS.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")
        search = self.request.QUERY_PARAMS.get("search")
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(code__icontains=search)
        return qs.distinct()


class CourseEditionViewSet(ModelCrudViewSet):
    permission_classes = (permissions.CourseEditionPermission,)
    serializer_class = serializers.CourseEditionSerializer

    def get_queryset(self):
        qs = models.CourseEdition.objects.select_related("subject").all()
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
    def dashboard(self, request, pk=None):
        edition = get_object_or_404(models.CourseEdition, pk=pk)
        self.check_permissions(request, "dashboard", edition)

        force = request.QUERY_PARAMS.get("refresh", "").lower() in ("1", "true", "yes")

        from .services import get_edition_dashboard
        data = get_edition_dashboard(edition, force=force)
        return response.Ok(data)

    @detail_route(methods=["get", "post"])
    def groups(self, request, pk=None):
        edition = get_object_or_404(models.CourseEdition, pk=pk)
        self.check_permissions(request, "groups", edition)

        if request.method == "GET":
            qs = edition.groups.all()
            if request.QUERY_PARAMS.get("is_active"):
                qs = qs.filter(is_active=request.QUERY_PARAMS["is_active"].lower() == "true")
            serializer = serializers.CourseGroupSerializer(qs, many=True)
            return response.Ok(serializer.data)

        # POST — create a new group in this edition
        data = request.DATA.copy()
        data["course_edition_id"] = edition.pk
        serializer = serializers.CourseGroupSerializer(data=data)
        if serializer.is_valid():
            serializer.save(course_edition=edition, created_by=request.user)
            return response.Created(serializer.data)
        return response.BadRequest(serializer.errors)


class CourseGroupViewSet(ModelCrudViewSet):
    permission_classes = (permissions.CourseGroupPermission,)
    serializer_class = serializers.CourseGroupSerializer

    def get_queryset(self):
        qs = models.CourseGroup.objects.select_related(
            "course_edition", "project_link__project"
        ).all()
        if self.request.QUERY_PARAMS.get("edition"):
            qs = qs.filter(course_edition_id=self.request.QUERY_PARAMS["edition"])
        if self.request.QUERY_PARAMS.get("is_active"):
            qs = qs.filter(is_active=self.request.QUERY_PARAMS["is_active"].lower() == "true")
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @detail_route(methods=["get", "post", "patch", "delete"])
    def project_link(self, request, pk=None):
        group = get_object_or_404(models.CourseGroup, pk=pk)

        if request.method == "GET":
            self.check_permissions(request, "project_link", group)
            link = getattr(group, "project_link", None)
            if link is None:
                return response.NotFound()
            return response.Ok(serializers.GroupProjectLinkSerializer(link).data)

        if request.method == "POST":
            self.check_permissions(request, "project_link_update", group)
            if hasattr(group, "project_link"):
                return response.BadRequest({"error": "ACADEMICS.GROUP_ALREADY_HAS_PROJECT_LINK"})
            serializer = serializers.GroupProjectLinkSerializer(data=request.DATA)
            if serializer.is_valid():
                serializer.save(course_group=group, linked_by=request.user)
                return response.Created(serializer.data)
            return response.BadRequest(serializer.errors)

        if request.method == "PATCH":
            self.check_permissions(request, "project_link_update", group)
            link = get_object_or_404(models.GroupProjectLink, course_group=group)
            serializer = serializers.GroupProjectLinkSerializer(
                link, data=request.DATA, partial=True
            )
            if serializer.is_valid():
                serializer.save()
                return response.Ok(serializer.data)
            return response.BadRequest(serializer.errors)

        if request.method == "DELETE":
            self.check_permissions(request, "project_link_update", group)
            link = get_object_or_404(models.GroupProjectLink, course_group=group)
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


class GroupProjectLinkViewSet(ModelCrudViewSet):
    permission_classes = (permissions.GroupProjectLinkPermission,)
    serializer_class = serializers.GroupProjectLinkSerializer

    def get_queryset(self):
        qs = models.GroupProjectLink.objects.select_related(
            "course_group", "project"
        ).all()
        if self.request.QUERY_PARAMS.get("group"):
            qs = qs.filter(course_group_id=self.request.QUERY_PARAMS["group"])
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


class ProfessorGroupAssignmentViewSet(ModelCrudViewSet):
    permission_classes = (permissions.ProfessorGroupAssignmentPermission,)
    serializer_class = serializers.ProfessorGroupAssignmentSerializer

    def get_queryset(self):
        qs = models.ProfessorGroupAssignment.objects.select_related(
            "edition_professor_assignment__teacher_profile__user",
            "edition_professor_assignment__course_edition",
            "course_group",
        ).all()
        if self.request.QUERY_PARAMS.get("edition_professor_assignment_id"):
            qs = qs.filter(
                edition_professor_assignment_id=self.request.QUERY_PARAMS["edition_professor_assignment_id"]
            )
        if self.request.QUERY_PARAMS.get("course_group_id"):
            qs = qs.filter(course_group_id=self.request.QUERY_PARAMS["course_group_id"])
        if self.request.QUERY_PARAMS.get("is_active"):
            qs = qs.filter(is_active=self.request.QUERY_PARAMS["is_active"].lower() == "true")
        return qs

    def perform_create(self, serializer):
        serializer.save(assigned_by=self.request.user)
