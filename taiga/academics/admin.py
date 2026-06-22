# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django import forms
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
# Custom form for CourseTeam — includes metrics config fields
# ---------------------------------------------------------------------------

class CourseTeamAdminForm(forms.ModelForm):
    PROVIDER_CHOICES = [
        ("internal", "Internal (Taiga)"),
        ("external", "External (Learning Dashboard)"),
    ]
    metrics_provider = forms.ChoiceField(
        choices=PROVIDER_CHOICES,
        required=False,
        label="Metrics provider",
    )
    external_project_id = forms.CharField(
        required=False,
        label="External project ID (Learning Dashboard)",
        help_text="Only required when provider is External.",
    )

    class Meta:
        model = models.CourseTeam
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            try:
                config = self.instance.project_link.project.metrics_config
                self.fields["metrics_provider"].initial = config.provider
                self.fields["external_project_id"].initial = config.external_project_id
            except Exception:
                pass


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
    form = CourseTeamAdminForm
    list_display = ["__str__", "course_edition", "is_active", "linked_project", "metrics_provider_display"]
    list_filter = ["is_active", "course_edition__subject"]
    search_fields = ["team_code", "display_name", "course_edition__key"]
    inlines = [TeamProjectLinkInline, ProfessorTeamAssignmentInline]
    fieldsets = [
        (None, {
            "fields": ["course_edition", "team_code", "display_name", "is_active"],
        }),
        ("Metrics configuration", {
            "fields": ["metrics_provider", "external_project_id"],
            "description": "Configure whether this team's linked Taiga project uses internal or external metrics.",
        }),
    ]

    def linked_project(self, obj):
        if hasattr(obj, "project_link"):
            return obj.project_link.project.slug
        return "—"
    linked_project.short_description = "Linked project"

    def metrics_provider_display(self, obj):
        try:
            config = obj.project_link.project.metrics_config
            return "External (LD)" if config.provider == "external" else "Internal"
        except Exception:
            return "—"
    metrics_provider_display.short_description = "Metrics"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        provider = form.cleaned_data.get("metrics_provider")
        external_id = form.cleaned_data.get("external_project_id", "")
        if provider:
            try:
                from taiga.projects.metrics.models import ProjectMetricsConfig
                config, _ = ProjectMetricsConfig.objects.get_or_create(
                    project=obj.project_link.project
                )
                config.provider = provider
                config.external_project_id = external_id
                config.save()
            except Exception:
                pass


@admin.register(models.TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "is_academic_admin", "is_active_teacher"]
    list_filter = ["is_academic_admin", "is_active_teacher"]
    search_fields = ["user__username", "user__first_name", "user__last_name"]
