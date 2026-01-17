# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

import pytest

from taiga.projects.validators import EpicStatusValidator
from .. import factories as f

pytestmark = pytest.mark.django_db(transaction=True)


def test_duplicated_name_validation():
    project = f.ProjectFactory.create()
    f.EpicStatusFactory.create(project=project, name="1")
    instance_2 = f.EpicStatusFactory.create(project=project, name="2")

    # No duplicated_name
    validator = EpicStatusValidator(data={"name": "3", "project": project.id})

    assert validator.is_valid()

    # Create duplicated_name
    validator = EpicStatusValidator(data={"name": "1", "project": project.id})

    assert not validator.is_valid()

    # Update name to existing one
    validator = EpicStatusValidator(data={"id": instance_2.id, "name": "1", "project": project.id})

    assert not validator.is_valid()
