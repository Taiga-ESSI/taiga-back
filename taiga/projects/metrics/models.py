# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC
#
# Created by: Pol Alcoverro (Learning Dashboard integration)
# Extended by: Codex assistant

from django.db import models
from django.utils import timezone

from taiga.base.db.models.fields import JSONField


class ProjectMetricsSnapshot(models.Model):
    """
    Stores a serialized snapshot for internally computed project metrics so that
    we don't need to recalculate heavy aggregations on every request.
    """

    INTERNAL_PROVIDER = "internal"

    PROVIDER_CHOICES = (
        (INTERNAL_PROVIDER, "Internal Taiga data"),
    )

    project = models.ForeignKey(
        "projects.Project",
        related_name="metrics_snapshots",
        on_delete=models.CASCADE,
    )
    provider = models.CharField(
        max_length=32,
        choices=PROVIDER_CHOICES,
        default=INTERNAL_PROVIDER,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    computed_at = models.DateTimeField(default=timezone.now)
    payload = JSONField(default=dict)
    historical_payload = JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-computed_at", "-id"]
        indexes = [
            models.Index(fields=["project", "provider", "-computed_at"]),
        ]

    def __str__(self):
        return f"{self.project.slug} | {self.provider} @ {self.computed_at}"
