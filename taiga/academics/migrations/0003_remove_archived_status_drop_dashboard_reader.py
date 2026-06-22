# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0002_rename_group_to_team"),
    ]

    operations = [
        # Remove ARCHIVED as a valid status value for CourseEdition.
        # Existing rows with status='ARCHIVED' should be migrated to 'CLOSED' before applying.
        migrations.AlterField(
            model_name="courseedition",
            name="status",
            field=models.CharField(
                max_length=10,
                choices=[
                    ("PLANNED", "Planned"),
                    ("ACTIVE", "Active"),
                    ("CLOSED", "Closed"),
                ],
                default="PLANNED",
            ),
        ),
        migrations.DeleteModel(
            name="CourseDashboardReader",
        ),
    ]
