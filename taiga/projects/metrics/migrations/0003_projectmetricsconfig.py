# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import taiga.base.db.models.fields


class Migration(migrations.Migration):

    dependencies = [
        ("metrics", "0002_auto_20251117_1414"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectMetricsConfig",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "provider",
                    models.CharField(
                        choices=[("external", "External"), ("internal", "Internal")],
                        default="external",
                        max_length=32,
                    ),
                ),
                (
                    "external_project_id",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                ("classification", taiga.base.db.models.fields.JSONField(blank=True, default=dict)),
                ("project_metrics_order", taiga.base.db.models.fields.JSONField(blank=True, default=list)),
                ("team_metrics_order", taiga.base.db.models.fields.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "project",
                    models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="metrics_config", to="projects.project"),
                ),
                (
                    "updated_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_metrics_configs", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={
                "ordering": ["project"],
            },
        ),
    ]
