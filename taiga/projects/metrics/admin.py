# -*- coding: utf-8 -*-

from django.contrib import admin

from . import models


class ProjectMetricsSnapshotAdmin(admin.ModelAdmin):
    list_display = ["project", "provider", "created_at", "computed_at"]
    list_filter = ["provider", "created_at"]
    search_fields = ["project__name", "project__slug"]
    ordering = ["-computed_at", "project"]


class ProjectMetricsConfigAdmin(admin.ModelAdmin):
    list_display = ["project", "provider", "external_project_id", "updated_at"]
    list_filter = ["provider", "updated_at"]
    search_fields = ["project__name", "project__slug", "external_project_id"]
    fields = ["project", "provider", "external_project_id"]
    ordering = ["project"]


admin.site.register(models.ProjectMetricsSnapshot, ProjectMetricsSnapshotAdmin)
admin.site.register(models.ProjectMetricsConfig, ProjectMetricsConfigAdmin)
