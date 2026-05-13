# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from taiga.base.api import serializers

from . import models


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Subject
        fields = ["id", "code", "name", "department", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class CourseEditionSerializer(serializers.ModelSerializer):
    subject = SubjectSerializer(read_only=True)
    subject_id = serializers.PrimaryKeyRelatedField(
        queryset=models.Subject.objects.filter(is_active=True),
        source="subject",
        write_only=True,
    )
    group_count = serializers.SerializerMethodField("get_group_count")
    professor_count = serializers.SerializerMethodField("get_professor_count")

    def get_group_count(self, obj):
        return obj.groups.filter(is_active=True).count()

    def get_professor_count(self, obj):
        return obj.professor_assignments.filter(is_active=True).count()

    def validate(self, data):
        if data.get("start_date") and data.get("end_date"):
            if data["start_date"] > data["end_date"]:
                raise serializers.ValidationError(
                    {"end_date": "end_date must be after start_date."}
                )
        return data

    def validate_status(self, value):
        if self.instance and value != self.instance.status:
            if not self.instance.can_transition_to(value):
                raise serializers.ValidationError(
                    f"Invalid status transition from '{self.instance.status}' to '{value}'."
                )
        return value

    class Meta:
        model = models.CourseEdition
        fields = [
            "id", "subject", "subject_id", "key", "academic_year", "term",
            "start_date", "end_date", "status", "group_count", "professor_count",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class GroupProjectLinkSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source="project.name", read_only=True)
    project_slug = serializers.CharField(source="project.slug", read_only=True)
    course_group_id = serializers.IntegerField(read_only=True)
    project_id = serializers.IntegerField()

    class Meta:
        model = models.GroupProjectLink
        fields = [
            "id", "course_group_id", "project_id", "project_name", "project_slug",
            "source_url", "is_active", "linked_at",
        ]
        read_only_fields = ["id", "linked_at"]


class CourseGroupSerializer(serializers.ModelSerializer):
    course_edition_id = serializers.PrimaryKeyRelatedField(
        queryset=models.CourseEdition.objects.all(),
        source="course_edition",
        write_only=True,
    )
    course_edition_key = serializers.CharField(source="course_edition.key", read_only=True)
    project_link = GroupProjectLinkSerializer(read_only=True)

    class Meta:
        model = models.CourseGroup
        fields = [
            "id", "course_edition_id", "course_edition_key", "group_code",
            "display_name", "is_active", "project_link", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_group_code(self, value):
        # group_code is immutable after creation
        if self.instance:
            return self.instance.group_code
        return value


class UserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    full_name = serializers.SerializerMethodField("get_full_name")
    email = serializers.EmailField(read_only=True)

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username


class TeacherProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = models.TeacherProfile
        fields = [
            "id", "user", "user_id", "teacher_code", "global_role",
            "is_active_teacher", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class SubjectCoordinatorAssignmentSerializer(serializers.ModelSerializer):
    subject_id = serializers.IntegerField()
    subject_code = serializers.CharField(source="subject.code", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    teacher_profile_id = serializers.IntegerField()
    teacher_username = serializers.CharField(source="teacher_profile.user.username", read_only=True)

    class Meta:
        model = models.SubjectCoordinatorAssignment
        fields = [
            "id", "subject_id", "subject_code", "subject_name",
            "teacher_profile_id", "teacher_username",
            "is_active", "valid_from", "valid_to", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class EditionProfessorAssignmentSerializer(serializers.ModelSerializer):
    course_edition_id = serializers.IntegerField()
    course_edition_key = serializers.CharField(source="course_edition.key", read_only=True)
    teacher_profile_id = serializers.IntegerField()
    teacher_username = serializers.CharField(source="teacher_profile.user.username", read_only=True)

    class Meta:
        model = models.EditionProfessorAssignment
        fields = [
            "id", "course_edition_id", "course_edition_key",
            "teacher_profile_id", "teacher_username",
            "is_active", "valid_from", "valid_to", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ProfessorGroupAssignmentSerializer(serializers.ModelSerializer):
    edition_professor_assignment_id = serializers.IntegerField()
    course_group_id = serializers.IntegerField()
    course_group_code = serializers.CharField(source="course_group.group_code", read_only=True)

    class Meta:
        model = models.ProfessorGroupAssignment
        fields = [
            "id", "edition_professor_assignment_id", "course_group_id", "course_group_code",
            "is_active", "assigned_at",
        ]
        read_only_fields = ["id", "assigned_at"]


class CourseMetricsPolicySerializer(serializers.ModelSerializer):
    course_edition_id = serializers.IntegerField()
    course_edition_key = serializers.CharField(source="course_edition.key", read_only=True)

    class Meta:
        model = models.CourseMetricsPolicy
        fields = [
            "id", "course_edition_id", "course_edition_key",
            "visible_to_students_metric_ids", "hidden_metric_ids",
            "group_metric_order", "project_metric_order",
            "allow_student_drilldown", "updated_at",
        ]
        read_only_fields = ["id", "updated_at"]


class CourseDashboardReaderSerializer(serializers.ModelSerializer):
    course_edition_id = serializers.IntegerField()
    course_edition_key = serializers.CharField(source="course_edition.key", read_only=True)
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField()

    class Meta:
        model = models.CourseDashboardReader
        fields = [
            "id", "course_edition_id", "course_edition_key",
            "user", "user_id", "is_active", "granted_at",
        ]
        read_only_fields = ["id", "granted_at"]
