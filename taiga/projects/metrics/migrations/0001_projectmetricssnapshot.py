# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.db import migrations, models
import django.db.models.deletion
import taiga.base.db.models.fields
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("projects", "0068_add_priority_custom_attribute"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectMetricsSnapshot",
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
                ("provider", models.CharField(choices=[("internal", "Internal Taiga data")], default="internal", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("computed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("payload", taiga.base.db.models.fields.JSONField(default=dict)),
                ("historical_payload", taiga.base.db.models.fields.JSONField(blank=True, default=dict)),
                (
                    "project",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="metrics_snapshots", to="projects.project"),
                ),
            ],
            options={
                "ordering": ["-computed_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="projectmetricssnapshot",
            index=models.Index(fields=["project", "provider", "-computed_at"], name="metrics_sn_project_f0c554_idx"),
        ),
    ]
