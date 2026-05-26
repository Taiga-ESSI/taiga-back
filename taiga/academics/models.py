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
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"

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
    STATUS_CHOICES = [
        (STATUS_PLANNED, "Planned"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_CLOSED, "Closed"),
    ]

    # Valid status transitions: PLANNED→ACTIVE→CLOSED (no rollback)
    VALID_TRANSITIONS = {
        STATUS_PLANNED: [STATUS_ACTIVE],
        STATUS_ACTIVE: [STATUS_CLOSED],
        STATUS_CLOSED: [],
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
        verbose_name = "Course Edition"
        verbose_name_plural = "Course Editions"

    def __str__(self):
        return self.key

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])


class CourseTeam(models.Model):
    course_edition = models.ForeignKey(
        CourseEdition,
        related_name="teams",
        on_delete=models.CASCADE,
    )
    team_code = models.CharField(max_length=20)
    display_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="created_teams",
    )

    class Meta:
        ordering = ["team_code"]
        unique_together = [["course_edition", "team_code"]]
        verbose_name = "Team"
        verbose_name_plural = "Teams"

    def __str__(self):
        return f"{self.course_edition.key} / {self.team_code}"


class TeacherProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="teacher_profile",
        on_delete=models.CASCADE,
    )
    is_academic_admin = models.BooleanField(default=False)
    is_active_teacher = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]
        verbose_name = "Teacher Profile"
        verbose_name_plural = "Teacher Profiles"

    def __str__(self):
        role = "Admin" if self.is_academic_admin else "Teacher"
        return f"{self.user.username} ({role})"

    def is_admin(self):
        return self.is_active_teacher and self.is_academic_admin

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
        verbose_name = "Subject Coordinator Assignment"
        verbose_name_plural = "Subject Coordinator Assignments"

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
        verbose_name = "Edition Professor Assignment"
        verbose_name_plural = "Edition Professor Assignments"

    def __str__(self):
        return f"{self.teacher_profile.user.username} → {self.course_edition.key}"


class ProfessorTeamAssignment(models.Model):
    edition_professor_assignment = models.ForeignKey(
        EditionProfessorAssignment,
        related_name="team_assignments",
        on_delete=models.CASCADE,
    )
    course_team = models.ForeignKey(
        CourseTeam,
        related_name="professor_assignments",
        on_delete=models.CASCADE,
    )
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="created_team_assignments",
    )

    class Meta:
        ordering = ["edition_professor_assignment", "course_team"]
        unique_together = [["edition_professor_assignment", "course_team"]]
        verbose_name = "Professor Team Assignment"
        verbose_name_plural = "Professor Team Assignments"

    def __str__(self):
        return f"{self.edition_professor_assignment} / {self.course_team.team_code}"


class TeamProjectLink(models.Model):
    course_team = models.OneToOneField(
        CourseTeam,
        related_name="project_link",
        on_delete=models.CASCADE,
    )
    project = models.ForeignKey(
        "projects.Project",
        related_name="academic_team_links",
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
        ordering = ["course_team"]
        verbose_name = "Team Project Link"
        verbose_name_plural = "Team Project Links"

    def __str__(self):
        return f"{self.course_team} → {self.project.slug}"


class CourseMetricsPolicy(models.Model):
    course_edition = models.OneToOneField(
        CourseEdition,
        related_name="metrics_policy",
        on_delete=models.CASCADE,
    )
    visible_to_students_metric_ids = JSONField(default=list, blank=True)
    hidden_metric_ids = JSONField(default=list, blank=True)
    team_metric_order = JSONField(default=list, blank=True)
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
        verbose_name = "Course Metrics Policy"
        verbose_name_plural = "Course Metrics Policies"

    def __str__(self):
        return f"{self.course_edition.key} metrics policy"


