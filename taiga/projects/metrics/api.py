# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC
#
# CREADOR POR: POL ALCOVERRO
# Descripción: Endpoints DRF que actúan como proxy con Learning Dashboard para autenticación,
#              sesión y agregación de métricas del proyecto.

import logging
import re
from datetime import datetime, timedelta

import requests
from django.conf import settings

from taiga.base import response
from taiga.base.api import ReadOnlyListViewSet
from taiga.base.api.utils import get_object_or_404
from taiga.base.decorators import list_route
from taiga.projects.models import Project

from . import permissions
from .internal import get_or_build_snapshot

logger = logging.getLogger(__name__)


class MetricsViewSet(ReadOnlyListViewSet):
    """
    ViewSet to retrieve project metrics from gessi-dashboard (Q-Rapids).
    Acts as a proxy to the external metrics service.
    """

    permission_classes = (permissions.MetricsPermission,)

    LD_TAIGA_BACKEND_URL = getattr(settings, "LD_TAIGA_BACKEND_URL", "http://gessi-dashboard.essi.upc.edu:8888")
    LD_TAIGA_TIMEOUT = getattr(settings, "LD_TAIGA_TIMEOUT", 15)
    SESSION_KEY = "ld_metrics_auth"
    DEFAULT_PROVIDER = getattr(settings, "METRICS_PROVIDER", "external")

    ##########################################################################
    # Helper methods
    ##########################################################################
    @staticmethod
    def _normalize_identifier(value):
        if not value:
            return ""
        return re.sub(r"[^a-z0-9]", "", value.lower())

    def _build_backend_url(self, path):
        """Build full URL for gessi-dashboard API endpoint"""
        base = self.LD_TAIGA_BACKEND_URL.rstrip("/")
        return f"{base}{path}"

    def _request_backend(self, method, path, *, params=None):
        """Make request to gessi-dashboard API"""
        url = self._build_backend_url(path)
        try:
            response_obj = requests.request(
                method,
                url,
                params=params,
                timeout=self.LD_TAIGA_TIMEOUT
            )
            logger.info(f"gessi-dashboard {method.upper()} {url} -> {response_obj.status_code}")
            return response_obj
        except requests.RequestException as exc:
            logger.exception("Error contacting gessi-dashboard (%s %s): %s", method.upper(), url, exc)
            raise

    def _ensure_authenticated(self, request):
        """Check if user has authenticated with metrics backend"""
        return request.session.get(self.SESSION_KEY)

    def _store_session_auth(self, request, username, external_project_id=None):
        """Store metrics authentication in session"""
        request.session[self.SESSION_KEY] = {
            "username": username,
            "external_project_id": external_project_id or username,
        }
        request.session.modified = True

    def _clear_session_auth(self, request):
        """Clear metrics authentication from session"""
        if self.SESSION_KEY in request.session:
            del request.session[self.SESSION_KEY]
            request.session.modified = True

    @staticmethod
    def _safe_json(response_obj):
        """Safely parse JSON response"""
        if not response_obj.content:
            return None
        try:
            return response_obj.json()
        except ValueError:
            return None

    @staticmethod
    def _enrich_metrics_with_catalog(metrics_list, catalog):
        """
        Attach metadata (like category names) from the metrics catalog endpoint
        to the live metrics payload fetched from /api/metrics/current.
        """
        if not metrics_list or not catalog:
            return

        if isinstance(catalog, dict):
            catalog_entries = catalog.get("results")
            if isinstance(catalog_entries, list):
                entries = catalog_entries
            else:
                entries = [catalog]
        elif isinstance(catalog, list):
            entries = catalog
        else:
            return

        category_map = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            external_id = entry.get("externalId") or entry.get("id")
            if not external_id:
                continue
            normalized_id = str(external_id).strip().lower()
            if not normalized_id:
                continue
            category_name = entry.get("categoryName") or entry.get("category")
            if category_name:
                category_map[normalized_id] = category_name

        if not category_map:
            return

        for metric in metrics_list:
            metric_id = metric.get("id")
            if not metric_id:
                continue
            lookup = str(metric_id).strip().lower()
            if not lookup:
                continue
            category_name = category_map.get(lookup)
            if category_name:
                metric["categoryName"] = category_name

    def _resolve_provider(self, request):
        """
        Determines which provider should be used for the current request.
        Query param / body param `source` can override the configured default.
        """
        source = None
        if hasattr(request, "DATA"):
            source = request.DATA.get("source")
        if not source:
            source = request.QUERY_PARAMS.get("source")

        if isinstance(source, str):
            source = source.strip().lower()
            if source in {"internal", "external"}:
                return source

        return (self.DEFAULT_PROVIDER or "external").lower()

    ##########################################################################
    # Authentication endpoints
    ##########################################################################
    @list_route(methods=["POST"])
    def login(self, request, **kwargs):
        """
        Authenticate against gessi-dashboard by validating credentials.
        gessi-dashboard doesn't have a /login endpoint, so we validate
        by attempting to fetch metrics for the project.
        """
        provider = self._resolve_provider(request)

        if provider == "internal":
            if not request.user.is_authenticated:
                return response.Unauthorized({"error": "METRICS.ERROR_AUTH_REQUIRED"})

            username = request.DATA.get("username") or request.user.username
            external_project = request.DATA.get("project") or request.DATA.get("external") or request.user.username
            self._store_session_auth(request, username, external_project_id=external_project)
            return response.Ok({
                "status": "authenticated",
                "username": username,
                "provider": provider,
            })

        if not request.user.is_authenticated:
            return response.Unauthorized({"error": "METRICS.ERROR_AUTH_REQUIRED"})

        data = request.DATA or {}
        username = data.get("username")  # This is the project ID
        external_project = data.get("project")

        if not username:
            return response.BadRequest({"error": "METRICS.ERROR_MISSING_USERNAME"})

        # Validate credentials by trying to fetch metrics
        # gessi-dashboard requires: ?prj=PROJECT_ID
        # Authentication is validated implicitly - if we get data back, credentials are valid
        try:
            validation_response = self._request_backend(
                "get",
                "/api/metrics/current",
                params={"prj": username}
            )
        except requests.RequestException:
            return response.BadRequest({"error": "METRICS.ERROR_METRICS_BACKEND_UNREACHABLE"})

        # Check response
        if validation_response.status_code == 404:
            # Project doesn't exist or invalid credentials
            return response.BadRequest({"error": "METRICS.ERROR_INVALID_PROJECT_ID"})
        elif validation_response.status_code == 200:
            data = self._safe_json(validation_response)
            if data is None or (isinstance(data, list) and len(data) == 0):
                # Project exists but has no metrics
                return response.Ok({
                    "status": "authenticated",
                    "username": username,
                    "warning": "METRICS.ERROR_PROJECT_HAS_NO_METRICS"
                })
            else:
                # Success - credentials are valid and project has metrics
                self._store_session_auth(request, username, external_project_id=external_project or username)
                return response.Ok({
                    "status": "authenticated",
                    "username": username
                })
        else:
            # Other error
            error_data = self._safe_json(validation_response) or {}
            return response.Response(
                {"error": "METRICS.ERROR_BACKEND_ERROR", "details": error_data},
                status=validation_response.status_code
            )

    @list_route(methods=["POST"])
    def logout(self, request, **kwargs):
        """Clear the metrics authentication session"""
        provider = self._resolve_provider(request)

        if provider == "internal":
            if self.SESSION_KEY in request.session:
                self._clear_session_auth(request)
            return response.Ok({"status": "logged_out", "provider": provider})

        if not request.user.is_authenticated:
            return response.Unauthorized({"error": "METRICS.ERROR_AUTH_REQUIRED"})

        self._clear_session_auth(request)
        return response.Ok({"status": "logged_out"})

    @list_route(methods=["GET"])
    def status(self, request, **kwargs):
        """Return the current authentication status for metrics"""
        provider = self._resolve_provider(request)

        if provider == "internal":
            if not request.user.is_authenticated:
                return response.Ok({"authenticated": False, "username": None, "provider": provider})
            return response.Ok({
                "authenticated": True,
                "username": request.user.username,
                "external_project_id": request.user.username,
                "provider": provider,
            })

        if not request.user.is_authenticated:
            return response.Ok({"authenticated": False, "username": None})

        auth_state = self._ensure_authenticated(request)
        if not auth_state:
            return response.Ok({"authenticated": False, "username": None})

        return response.Ok({
            "authenticated": True,
            "username": auth_state.get("username"),
            "external_project_id": auth_state.get("external_project_id"),
        })

    ##########################################################################
    # Metrics aggregation endpoint
    ##########################################################################
    def list(self, request, *args, **kwargs):
        """
        Get metrics for a specific project from the chosen provider.
        Query params:
            - project: Taiga project slug (required)
            - external: optional external project identifier override
            - source: optional provider override (internal/external)
            - refresh: truthy flag to force regeneration of internal snapshots
        """
        project_slug = request.QUERY_PARAMS.get("project")
        if not project_slug:
            return response.BadRequest({"error": "METRICS.ERROR_PROJECT_REQUIRED"})

        project = get_object_or_404(Project, slug=project_slug)
        self.check_permissions(request, "list", project)

        provider = self._resolve_provider(request)

        if provider == "internal":
            refresh_flag = (request.QUERY_PARAMS.get("refresh") or "").lower()
            force_refresh = refresh_flag in ("1", "true", "yes")
            snapshot = get_or_build_snapshot(
                project,
                use_cache=not force_refresh,
                force=force_refresh,
            )
            payload = dict(snapshot.payload or {})
            payload.setdefault("project_slug", project_slug)
            payload.setdefault("project_name", project.name)
            payload.setdefault("external_project_id", payload.get("external_project_id") or project.slug)
            payload["provider"] = provider
            return response.Ok(payload)

        auth_state = self._ensure_authenticated(request)
        if not auth_state:
            return response.Unauthorized({"error": "METRICS.ERROR_METRICS_AUTH_REQUIRED"})

        # Get the project ID to use with gessi-dashboard
        explicit_external = request.QUERY_PARAMS.get("external")
        external_project_id = explicit_external or auth_state.get("external_project_id") or auth_state.get("username")

        logger.info(f"📊 Metrics request for {project_slug} | external={external_project_id}")

        # gessi-dashboard API endpoints
        # All use ?prj=PROJECT_ID format
        endpoints = {
            "metrics": {
                "path": "/api/metrics/current",
                "params": {"prj": external_project_id}
            },
            "students": {
                "path": "/api/metrics/students",
                "params": {"prj": external_project_id}
            },
            "metrics_categories": {
                "path": "/api/metrics/categories",
                "params": {"prj": external_project_id}
            },
            "metrics_catalog": {
                "path": "/api/metrics",
                "params": {"prj": external_project_id}
            },
        }

        aggregated = {}
        errors = {}

        for key, endpoint in endpoints.items():
            try:
                backend_response = self._request_backend(
                    "get",
                    endpoint["path"],
                    params=endpoint.get("params")
                )
            except requests.RequestException as exc:
                aggregated[key] = []
                errors[key] = {
                    "error": "METRICS.ERROR_METRICS_BACKEND_UNREACHABLE",
                    "details": str(exc)
                }
                continue

            if backend_response.status_code == 200:
                data = self._safe_json(backend_response)
                aggregated[key] = data if data is not None else []
                errors[key] = None
            elif backend_response.status_code == 404:
                aggregated[key] = []
                errors[key] = None
            else:
                aggregated[key] = []
                payload = self._safe_json(backend_response)
                errors[key] = {
                    "status": backend_response.status_code,
                    "detail": payload or backend_response.text
                }

        # Attach metadata (category names, etc.) coming from /api/metrics
        self._enrich_metrics_with_catalog(
            aggregated.get("metrics"),
            aggregated.get("metrics_catalog"),
        )

        # Check if project has any data
        has_data = any(
            aggregated.get(key) and len(aggregated[key]) > 0
            for key in ["metrics", "students"]
        )

        response_payload = {
            "project_slug": project_slug,
            "project_name": project.name,
            "external_project_id": external_project_id,
            "metrics": aggregated.get("metrics", []),
            "students": aggregated.get("students", []),
            "metrics_categories": aggregated.get("metrics_categories", []),
            "metrics_catalog": aggregated.get("metrics_catalog", []),
            "errors": {k: v for k, v in errors.items() if v},
            "is_new_project": not has_data,
            "provider": provider,
        }

        return response.Ok(response_payload)

    ##########################################################################
    # Historical metrics endpoint
    ##########################################################################
    @list_route(methods=["GET"])
    def historical(self, request, **kwargs):
        """
        Get historical metrics data for a specific project from gessi-dashboard API.
        Fetches data from multiple endpoints and aggregates them into categories.
        Query params:
            - project: Taiga project slug (required)
            - external: optional external project identifier override
            - source: optional provider override (internal/external)
        """
        project_slug = request.QUERY_PARAMS.get("project")
        if not project_slug:
            return response.BadRequest({"error": "METRICS.ERROR_PROJECT_REQUIRED"})

        project = get_object_or_404(Project, slug=project_slug)
        self.check_permissions(request, "historical", project)

        provider = self._resolve_provider(request)

        if provider == "internal":
            refresh_flag = (request.QUERY_PARAMS.get("refresh") or "").lower()
            force_refresh = refresh_flag in ("1", "true", "yes")
            snapshot = get_or_build_snapshot(
                project,
                use_cache=not force_refresh,
                force=force_refresh,
            )
            payload = {
                "project_slug": project_slug,
                "project_name": project.name,
                "external_project_id": (snapshot.payload or {}).get("external_project_id") or project.slug,
                "historical_data": snapshot.historical_payload or {},
                "errors": {},
                "provider": provider,
            }
            return response.Ok(payload)

        auth_state = self._ensure_authenticated(request)
        if not auth_state:
            return response.Unauthorized({"error": "METRICS.ERROR_METRICS_AUTH_REQUIRED"})

        # Get the project ID to use with gessi-dashboard
        explicit_external = request.QUERY_PARAMS.get("external")
        external_project_id = explicit_external or auth_state.get("external_project_id") or auth_state.get("username")

        logger.info(f"📊 Historical metrics request for {project_slug} | external={external_project_id}")

        # Date range for historical data (default: from 2020-01-01 to today)
        date_from = "2020-01-01"
        date_to = datetime.now().strftime("%Y-%m-%d")

        # gessi-dashboard API historical endpoints
        endpoints = {
            "strategicMetrics": "/api/strategicIndicators/historical",
            "userMetrics": "/api/metrics/students/historical",
            "projectMetrics": "/api/metrics/historical",
            "qualityFactors": "/api/qualityFactors/historical"
        }

        aggregated = {}
        errors = {}

        for key, endpoint in endpoints.items():
            try:
                backend_response = self._request_backend(
                    "get",
                    endpoint,
                    params={
                        "prj": external_project_id,
                        "from": date_from,
                        "to": date_to
                    }
                )
            except requests.RequestException as exc:
                aggregated[key] = {}
                errors[key] = {
                    "error": "METRICS.ERROR_METRICS_BACKEND_UNREACHABLE",
                    "details": str(exc)
                }
                logger.error(f"Error fetching {key}: {exc}")
                continue

            if backend_response.status_code == 200:
                raw_data = self._safe_json(backend_response)
                
                # Process the data based on type
                if key == "userMetrics":
                    # User metrics come as an object with usernames as keys
                    # Each user has a "metrics" array
                    processed = self._process_user_historical_metrics(raw_data)
                    aggregated[key] = processed
                else:
                    # Other metrics come as arrays and need to be grouped by ID
                    processed = self._group_historical_by_id(raw_data)
                    aggregated[key] = processed
                
                errors[key] = None
                logger.info(f"✓ {key} fetched successfully, {len(processed)} metrics")
            elif backend_response.status_code == 404:
                aggregated[key] = {}
                errors[key] = None
                logger.warning(f"No {key} found (404)")
            else:
                aggregated[key] = {}
                payload = self._safe_json(backend_response)
                errors[key] = {
                    "status": backend_response.status_code,
                    "detail": payload or backend_response.text
                }
                logger.error(f"Error fetching {key}: {backend_response.status_code}")

        response_payload = {
            "project_slug": project_slug,
            "project_name": project.name,
            "external_project_id": external_project_id,
            "historical_data": aggregated,
            "errors": {k: v for k, v in errors.items() if v},
        }

        return response.Ok(response_payload)
    
    def _process_user_historical_metrics(self, raw_data):
        """
        Process user historical metrics from gessi-dashboard format.
        Input: Can be either:
          - Array: [{"name": "user1", "metrics": [...]}, ...]
          - Dict: {"username": {"metrics": [...]}, ...}
        Output: {"metricId": [{date, value, name, student}, ...], ...}
        """
        if not raw_data:
            return {}
        
        processed = {}
        
        # Handle array format from gessi-dashboard
        if isinstance(raw_data, list):
            for user_data in raw_data:
                if not isinstance(user_data, dict):
                    continue
                
                username = user_data.get("name") or user_data.get("username")
                metrics = user_data.get("metrics", [])
                if not isinstance(metrics, list):
                    continue
                
                for metric in metrics:
                    if not isinstance(metric, dict):
                        continue
                    
                    metric_id = metric.get("id")
                    if not metric_id:
                        continue
                    
                    if metric_id not in processed:
                        processed[metric_id] = []
                    
                    # Add student/username info to metric for frontend
                    metric_with_user = metric.copy()
                    if username:
                        metric_with_user["student"] = username
                    
                    processed[metric_id].append(metric_with_user)
        
        # Handle dict format (legacy)
        elif isinstance(raw_data, dict):
            for username, user_data in raw_data.items():
                if not isinstance(user_data, dict):
                    continue
                
                metrics = user_data.get("metrics", [])
                if not isinstance(metrics, list):
                    continue
                
                for metric in metrics:
                    if not isinstance(metric, dict):
                        continue
                    
                    metric_id = metric.get("id")
                    if not metric_id:
                        continue
                    
                    if metric_id not in processed:
                        processed[metric_id] = []
                    
                    # Add student/username info to metric for frontend
                    metric_with_user = metric.copy()
                    if username:
                        metric_with_user["student"] = username
                    
                    processed[metric_id].append(metric_with_user)
        
        return processed
    
    def _group_historical_by_id(self, raw_data):
        """
        Group historical metrics array by metric ID.
        Input: [{id: "metric1", date: "...", value: ...}, ...]
        Output: {"metric1": [{date, value, name}, ...], ...}
        """
        if not raw_data or not isinstance(raw_data, list):
            return {}
        
        grouped = {}
        
        for item in raw_data:
            if not isinstance(item, dict):
                continue
            
            metric_id = item.get("id")
            if not metric_id:
                continue
            
            if metric_id not in grouped:
                grouped[metric_id] = []
            
            grouped[metric_id].append(item)
        
        return grouped
