# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0003_remove_archived_status_drop_dashboard_reader"),
    ]

    operations = [
        # TeacherProfile: remove teacher_code and global_role, add is_academic_admin
        migrations.RemoveField(
            model_name="teacherprofile",
            name="teacher_code",
        ),
        migrations.RemoveField(
            model_name="teacherprofile",
            name="global_role",
        ),
        migrations.AddField(
            model_name="teacherprofile",
            name="is_academic_admin",
            field=models.BooleanField(default=False),
        ),
        # SubjectCoordinatorAssignment: remove valid_from and valid_to
        migrations.RemoveField(
            model_name="subjectcoordinatorassignment",
            name="valid_from",
        ),
        migrations.RemoveField(
            model_name="subjectcoordinatorassignment",
            name="valid_to",
        ),
        # EditionProfessorAssignment: remove valid_from and valid_to
        migrations.RemoveField(
            model_name="editionprofessorassignment",
            name="valid_from",
        ),
        migrations.RemoveField(
            model_name="editionprofessorassignment",
            name="valid_to",
        ),
    ]
