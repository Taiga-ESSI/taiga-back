# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.contrib import admin

from . import models


# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------

class SubjectCoordinatorAssignmentInline(admin.TabularInline):
    model = models.SubjectCoordinatorAssignment
    extra = 1
    fields = ["teacher_profile", "is_active"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "teacher_profile":
            kwargs["queryset"] = models.TeacherProfile.objects.filter(
                is_active_teacher=True
            ).select_related("user")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class EditionProfessorAssignmentInline(admin.TabularInline):
    model = models.EditionProfessorAssignment
    extra = 1
    fields = ["teacher_profile", "is_active"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "teacher_profile":
            kwargs["queryset"] = models.TeacherProfile.objects.filter(
                is_active_teacher=True
            ).select_related("user")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class CourseTeamInline(admin.TabularInline):
    model = models.CourseTeam
    extra = 0
    fields = ["team_code", "display_name", "is_active", "linked_project"]
    readonly_fields = ["linked_project"]
    show_change_link = True

    def linked_project(self, obj):
        if obj.pk and hasattr(obj, "project_link"):
            return obj.project_link.project.slug
        return "—"
    linked_project.short_description = "Linked project"


class TeamProjectLinkInline(admin.StackedInline):
    model = models.TeamProjectLink
    extra = 0
    max_num = 1
    fields = ["project", "source_url", "is_active"]


class ProfessorTeamAssignmentInline(admin.TabularInline):
    model = models.ProfessorTeamAssignment
    extra = 1
    fields = ["edition_professor_assignment", "is_active"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "edition_professor_assignment":
            team_pk = request.resolver_match.kwargs.get("object_id")
            if team_pk:
                try:
                    team = models.CourseTeam.objects.get(pk=team_pk)
                    kwargs["queryset"] = models.EditionProfessorAssignment.objects.filter(
                        course_edition=team.course_edition,
                        is_active=True,
                    ).select_related("teacher_profile__user")
                except models.CourseTeam.DoesNotExist:
                    pass
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ---------------------------------------------------------------------------
# Model admins
# ---------------------------------------------------------------------------

@admin.register(models.Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "department", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["code", "name"]
    inlines = [SubjectCoordinatorAssignmentInline]


@admin.register(models.CourseEdition)
class CourseEditionAdmin(admin.ModelAdmin):
    list_display = ["key", "subject", "academic_year", "term", "status"]
    list_filter = ["status", "term", "subject"]
    search_fields = ["key"]
    inlines = [CourseTeamInline, EditionProfessorAssignmentInline]


@admin.register(models.CourseTeam)
class CourseTeamAdmin(admin.ModelAdmin):
    list_display = ["__str__", "course_edition", "is_active", "linked_project"]
    list_filter = ["is_active", "course_edition__subject"]
    search_fields = ["team_code", "display_name", "course_edition__key"]
    inlines = [TeamProjectLinkInline, ProfessorTeamAssignmentInline]

    def linked_project(self, obj):
        if hasattr(obj, "project_link"):
            return obj.project_link.project.slug
        return "—"
    linked_project.short_description = "Linked project"


@admin.register(models.TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "is_academic_admin", "is_active_teacher"]
    list_filter = ["is_academic_admin", "is_active_teacher"]
    search_fields = ["user__username", "user__first_name", "user__last_name", "teacher_code"]


@admin.register(models.SubjectCoordinatorAssignment)
class SubjectCoordinatorAssignmentAdmin(admin.ModelAdmin):
    list_display = ["teacher_profile", "subject", "is_active"]
    list_filter = ["is_active", "subject"]
    search_fields = ["teacher_profile__user__username", "subject__code"]


@admin.register(models.EditionProfessorAssignment)
class EditionProfessorAssignmentAdmin(admin.ModelAdmin):
    list_display = ["teacher_profile", "course_edition", "is_active"]
    list_filter = ["is_active", "course_edition__subject"]
    search_fields = ["teacher_profile__user__username", "course_edition__key"]


@admin.register(models.ProfessorTeamAssignment)
class ProfessorTeamAssignmentAdmin(admin.ModelAdmin):
    list_display = ["__str__", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["edition_professor_assignment__teacher_profile__user__username", "course_team__team_code"]


@admin.register(models.TeamProjectLink)
class TeamProjectLinkAdmin(admin.ModelAdmin):
    list_display = ["course_team", "project", "is_active", "linked_at"]
    list_filter = ["is_active"]
    search_fields = ["course_team__team_code", "project__slug"]


@admin.register(models.CourseMetricsPolicy)
class CourseMetricsPolicyAdmin(admin.ModelAdmin):
    list_display = ["course_edition", "allow_student_drilldown", "updated_at"]
    search_fields = ["course_edition__key"]
