# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

import pytest
import django
from .fixtures import *


def pytest_addoption(parser):
    parser.addoption("--runslow", action="store_true", help="run slow tests")


def pytest_runtest_setup(item):
    if "slow" in item.keywords and not item.config.getoption("--runslow"):
        pytest.skip("need --runslow option to run")


def pytest_configure(config):
    django.setup()
    from taiga.celery import app
    app.conf.task_always_eager = True


@pytest.fixture(autouse=True)
def settings_override_tests(settings):
    settings.WEBHOOKS_ENABLED = True
    settings.IMPORTERS["github"]["active"] = True
    settings.IMPORTERS["trello"]["active"] = True
    settings.IMPORTERS["jira"]["active"] = True
    settings.IMPORTERS["asana"]["active"] = True

