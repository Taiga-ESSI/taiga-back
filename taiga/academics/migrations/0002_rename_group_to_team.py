# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC
#
# Rename CourseGroup → CourseTeam, ProfessorGroupAssignment → ProfessorTeamAssignment,
# GroupProjectLink → TeamProjectLink, and related fields/columns.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0001_initial"),
    ]

    operations = [
        # ── Model renames ──────────────────────────────────────────────────────
        migrations.RenameModel("CourseGroup", "CourseTeam"),
        migrations.RenameModel("ProfessorGroupAssignment", "ProfessorTeamAssignment"),
        migrations.RenameModel("GroupProjectLink", "TeamProjectLink"),

        # ── Field renames on CourseTeam ────────────────────────────────────────
        migrations.RenameField("CourseTeam", "group_code", "team_code"),

        # ── FK field renames ───────────────────────────────────────────────────
        migrations.RenameField("TeamProjectLink", "course_group", "course_team"),
        migrations.RenameField("ProfessorTeamAssignment", "course_group", "course_team"),

        # ── policy field rename ────────────────────────────────────────────────
        migrations.RenameField("CourseMetricsPolicy", "group_metric_order", "team_metric_order"),
    ]
