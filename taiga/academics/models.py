# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.conf import settings
from django.db import models

from taiga.base.db.models.fields import JSONField


class Subject(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    department = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class CourseEdition(models.Model):
    TERM_Q1 = "Q1"
    TERM_Q2 = "Q2"
    TERM_ANNUAL = "ANNUAL"
    TERM_CHOICES = [
        (TERM_Q1, "First Quarter"),
        (TERM_Q2, "Second Quarter"),
        (TERM_ANNUAL, "Annual"),
    ]

    STATUS_PLANNED = "PLANNED"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_CLOSED = "CLOSED"
    STATUS_ARCHIVED = "ARCHIVED"
    STATUS_CHOICES = [
        (STATUS_PLANNED, "Planned"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_CLOSED, "Closed"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    # Valid status transitions: PLANNED→ACTIVE→CLOSED→ARCHIVED (no rollback)
    VALID_TRANSITIONS = {
        STATUS_PLANNED: [STATUS_ACTIVE],
        STATUS_ACTIVE: [STATUS_CLOSED],
        STATUS_CLOSED: [STATUS_ARCHIVED],
        STATUS_ARCHIVED: [],
    }

    subject = models.ForeignKey(
        Subject,
        related_name="editions",
        on_delete=models.CASCADE,
    )
    key = models.CharField(max_length=100, unique=True)
    academic_year = models.PositiveIntegerField()
    term = models.CharField(max_length=10, choices=TERM_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PLANNED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="created_editions",
    )

    class Meta:
        ordering = ["-academic_year", "term", "key"]

    def __str__(self):
        return self.key

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])


class CourseGroup(models.Model):
    course_edition = models.ForeignKey(
        CourseEdition,
        related_name="groups",
        on_delete=models.CASCADE,
    )
    group_code = models.CharField(max_length=20)
    display_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="created_groups",
    )

    class Meta:
        ordering = ["group_code"]
        unique_together = [["course_edition", "group_code"]]

    def __str__(self):
        return f"{self.course_edition.key} / {self.group_code}"


class TeacherProfile(models.Model):
    ROLE_ADMIN = "ACADEMIC_ADMIN"
    ROLE_NONE = "NONE"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Academic Administrator"),
        (ROLE_NONE, "None"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="teacher_profile",
        on_delete=models.CASCADE,
    )
    teacher_code = models.CharField(max_length=50, blank=True, default="")
    global_role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_NONE)
    is_active_teacher = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"{self.user.username} ({self.global_role})"

    def is_admin(self):
        return self.is_active_teacher and self.global_role == self.ROLE_ADMIN

    def is_coordinator_of(self, subject):
        return self.coordinated_subjects.filter(
            subject=subject, is_active=True
        ).exists()

    def is_professor_of(self, course_edition):
        return self.edition_assignments.filter(
            course_edition=course_edition, is_active=True
        ).exists()


class SubjectCoordinatorAssignment(models.Model):
    subject = models.ForeignKey(
        Subject,
        related_name="coordinator_assignments",
        on_delete=models.CASCADE,
    )
    teacher_profile = models.ForeignKey(
        TeacherProfile,
        related_name="coordinated_subjects",
        on_delete=models.CASCADE,
    )
    is_active = models.BooleanField(default=True)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="created_coordinator_assignments",
    )

    class Meta:
        ordering = ["subject", "teacher_profile"]
        unique_together = [["subject", "teacher_profile"]]

    def __str__(self):
        return f"{self.teacher_profile.user.username} → {self.subject.code}"


class EditionProfessorAssignment(models.Model):
    course_edition = models.ForeignKey(
        CourseEdition,
        related_name="professor_assignments",
        on_delete=models.CASCADE,
    )
    teacher_profile = models.ForeignKey(
        TeacherProfile,
        related_name="edition_assignments",
        on_delete=models.CASCADE,
    )
    is_active = models.BooleanField(default=True)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="created_professor_assignments",
    )

    class Meta:
        ordering = ["course_edition", "teacher_profile"]
        unique_together = [["course_edition", "teacher_profile"]]

    def __str__(self):
        return f"{self.teacher_profile.user.username} → {self.course_edition.key}"


class ProfessorGroupAssignment(models.Model):
    edition_professor_assignment = models.ForeignKey(
        EditionProfessorAssignment,
        related_name="group_assignments",
        on_delete=models.CASCADE,
    )
    course_group = models.ForeignKey(
        CourseGroup,
        related_name="professor_assignments",
        on_delete=models.CASCADE,
    )
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="created_group_assignments",
    )

    class Meta:
        ordering = ["edition_professor_assignment", "course_group"]
        unique_together = [["edition_professor_assignment", "course_group"]]

    def __str__(self):
        return f"{self.edition_professor_assignment} / {self.course_group.group_code}"


class GroupProjectLink(models.Model):
    course_group = models.OneToOneField(
        CourseGroup,
        related_name="project_link",
        on_delete=models.CASCADE,
    )
    project = models.ForeignKey(
        "projects.Project",
        related_name="academic_group_links",
        on_delete=models.CASCADE,
    )
    source_url = models.URLField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    linked_at = models.DateTimeField(auto_now_add=True)
    linked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="created_project_links",
    )

    class Meta:
        ordering = ["course_group"]

    def __str__(self):
        return f"{self.course_group} → {self.project.slug}"


class CourseMetricsPolicy(models.Model):
    course_edition = models.OneToOneField(
        CourseEdition,
        related_name="metrics_policy",
        on_delete=models.CASCADE,
    )
    visible_to_students_metric_ids = JSONField(default=list, blank=True)
    hidden_metric_ids = JSONField(default=list, blank=True)
    group_metric_order = JSONField(default=list, blank=True)
    project_metric_order = JSONField(default=list, blank=True)
    allow_student_drilldown = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_metrics_policies",
    )

    class Meta:
        ordering = ["course_edition"]

    def __str__(self):
        return f"{self.course_edition.key} metrics policy"


class CourseDashboardReader(models.Model):
    course_edition = models.ForeignKey(
        CourseEdition,
        related_name="dashboard_readers",
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="readable_editions",
        on_delete=models.CASCADE,
    )
    is_active = models.BooleanField(default=True)
    granted_at = models.DateTimeField(auto_now_add=True)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="granted_dashboard_reads",
    )

    class Meta:
        ordering = ["course_edition", "user"]
        unique_together = [["course_edition", "user"]]

    def __str__(self):
        return f"{self.user.username} → {self.course_edition.key}"
