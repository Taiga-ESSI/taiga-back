# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.contrib import admin

from . import models

admin.site.register(models.Subject)
admin.site.register(models.CourseEdition)
admin.site.register(models.CourseGroup)
admin.site.register(models.TeacherProfile)
admin.site.register(models.SubjectCoordinatorAssignment)
admin.site.register(models.EditionProfessorAssignment)
admin.site.register(models.ProfessorGroupAssignment)
admin.site.register(models.GroupProjectLink)
admin.site.register(models.CourseMetricsPolicy)
admin.site.register(models.CourseDashboardReader)
