# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

import pytest

from taiga.academics.models import CourseEdition
from taiga.academics.serializers import CourseEditionSerializer

from .. import factories as f

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Bloque 3 — Serializers
# ---------------------------------------------------------------------------

def test_course_edition_serializer_rejects_start_date_greater_than_end_date():
    subject = f.SubjectFactory.create()
    data = {
        "subject_id": subject.id,
        "key": "2024-Q1-BAD",
        "academic_year": 2024,
        "term": "Q1",
        "start_date": "2024-05-31",
        "end_date": "2024-01-15",  # end before start
    }

    serializer = CourseEditionSerializer(data=data)

    assert not serializer.is_valid()
    assert "end_date" in serializer.errors


def test_course_edition_serializer_accepts_valid_date_range():
    subject = f.SubjectFactory.create()
    data = {
        "subject_id": subject.id,
        "key": "2024-Q1-OK",
        "academic_year": 2024,
        "term": "Q1",
        "start_date": "2024-01-15",
        "end_date": "2024-05-31",
    }

    serializer = CourseEditionSerializer(data=data)

    assert serializer.is_valid(), serializer.errors


def test_can_transition_planned_to_active_is_valid():
    """Prueba directamente el método del modelo, sin pasar por el serializer."""
    edition = CourseEdition(status=CourseEdition.STATUS_PLANNED)

    assert edition.can_transition_to(CourseEdition.STATUS_ACTIVE) is True


def test_cannot_transition_closed_to_active():
    """Prueba directamente el método del modelo, sin pasar por el serializer."""
    edition = CourseEdition(status=CourseEdition.STATUS_CLOSED)

    assert edition.can_transition_to(CourseEdition.STATUS_ACTIVE) is False


def test_serializer_rejects_invalid_status_transition():
    """
    El serializer valida transiciones ilegales al hacer PATCH del status.
    validate_status usa la convención taiga: (attrs, source) → attrs.
    """
    edition = f.CourseEditionFactory.create(status=CourseEdition.STATUS_CLOSED)
    data = {"status": CourseEdition.STATUS_ACTIVE}

    serializer = CourseEditionSerializer(instance=edition, data=data, partial=True)
    assert not serializer.is_valid()
    assert "status" in serializer.errors
