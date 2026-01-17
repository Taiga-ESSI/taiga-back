# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from copy import deepcopy

from django.db import migrations


US_CUSTOM_ATTRIBUTES = [
    {
        "name": "Priority",
        "description": "Sets the priority of the user story",
        "type": "dropdown",
        "order": 1,
        "extra": ["Low", "Medium", "High"],
    },
    {
        "name": "Acceptance Criteria",
        "description": "Enumerates the acceptance criteria for the user story",
        "type": "richtext",
        "order": 2,
        "extra": None,
    },
]


TASK_CUSTOM_ATTRIBUTES = [
    {
        "name": "Estimated Effort",
        "description": "Estimated number of hours for completing the task",
        "type": "number",
        "order": 1,
        "extra": None,
    },
    {
        "name": "Actual Effort",
        "description": "Actual number of hours invested in completing the task",
        "type": "number",
        "order": 2,
        "extra": None,
    },
]


def add_custom_attributes(apps, schema_editor):
    ProjectTemplate = apps.get_model("projects", "ProjectTemplate")

    for template in ProjectTemplate.objects.all():
        us_attrs = list(template.us_custom_attributes or [])
        task_attrs = list(template.task_custom_attributes or [])

        next_us_order = max((attr.get("order", 0) for attr in us_attrs), default=0)
        changed = False

        for definition in US_CUSTOM_ATTRIBUTES:
            if any(attr.get("name") == definition["name"] for attr in us_attrs):
                continue

            next_us_order += 1
            attr_copy = deepcopy(definition)
            attr_copy["order"] = next_us_order
            us_attrs.append(attr_copy)
            changed = True

        next_task_order = max((attr.get("order", 0) for attr in task_attrs), default=0)

        for definition in TASK_CUSTOM_ATTRIBUTES:
            if any(attr.get("name") == definition["name"] for attr in task_attrs):
                continue

            next_task_order += 1
            attr_copy = deepcopy(definition)
            attr_copy["order"] = next_task_order
            task_attrs.append(attr_copy)
            changed = True

        if changed:
            template.us_custom_attributes = us_attrs
            template.task_custom_attributes = task_attrs
            template.save(update_fields=["us_custom_attributes", "task_custom_attributes", "modified_date"])


def remove_custom_attributes(apps, schema_editor):
    ProjectTemplate = apps.get_model("projects", "ProjectTemplate")

    us_names = {attr["name"] for attr in US_CUSTOM_ATTRIBUTES}
    task_names = {attr["name"] for attr in TASK_CUSTOM_ATTRIBUTES}

    for template in ProjectTemplate.objects.all():
        us_attrs = list(template.us_custom_attributes or [])
        task_attrs = list(template.task_custom_attributes or [])

        filtered_us = [attr for attr in us_attrs if attr.get("name") not in us_names]
        filtered_task = [attr for attr in task_attrs if attr.get("name") not in task_names]

        if filtered_us == us_attrs and filtered_task == task_attrs:
            continue

        template.us_custom_attributes = filtered_us
        template.task_custom_attributes = filtered_task
        template.save(update_fields=["us_custom_attributes", "task_custom_attributes", "modified_date"])


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0067_auto_20201230_1237"),
    ]

    operations = [
        migrations.RunPython(add_custom_attributes, remove_custom_attributes),
    ]
