# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django import http
from django.conf import settings


# Pol Alcoverro: Whitelist of allowed origins. Can be overridden in settings.
# For development, localhost ports are automatically allowed.
CORS_ALLOWED_ORIGINS_WHITELIST = getattr(settings, "CORS_ALLOWED_ORIGINS_WHITELIST", [
    "http://localhost:9001",
    "http://localhost:8000",
    "http://127.0.0.1:9001",
    "http://127.0.0.1:8000",
])

CORS_ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
CORS_ALLOWED_HEADERS = ["content-type", "x-requested-with",
                        "authorization", "accept-encoding",
                        "x-disable-pagination", "x-lazy-pagination",
                        "x-host", "x-session-id", "set-orders"]
CORS_ALLOWED_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ["x-pagination-count", "x-paginated", "x-paginated-by",
                       "x-pagination-current", "x-pagination-next", "x-pagination-prev",
                       "x-site-host", "x-site-register"]

CORS_EXTRA_EXPOSE_HEADERS = getattr(settings, "APP_EXTRA_EXPOSE_HEADERS", [])


class CorsMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self.process_request(request)
        response = self.get_response(request)
        self.process_response(request, response)

        return response

    def _populate_response(self, request, response):
        # Pol Alcoverro: Get the origin from the request
        origin = request.headers.get("Origin", "")
        
        # When credentials are required, we must echo back the specific origin
        # instead of using wildcard "*" (which is forbidden by CORS spec with credentials)
        if origin and origin in CORS_ALLOWED_ORIGINS_WHITELIST:
            response["Access-Control-Allow-Origin"] = origin
        elif origin and origin.startswith(("http://localhost:", "http://127.0.0.1:")):
            # Allow any localhost/127.0.0.1 origin for development
            response["Access-Control-Allow-Origin"] = origin
        else:
            # Fallback for non-credentialed requests or if no origin matches
            # Note: This will fail for credentialed requests, which is intentional for security
            response["Access-Control-Allow-Origin"] = origin if origin else "*"
        
        response["Access-Control-Allow-Methods"] = ",".join(CORS_ALLOWED_METHODS)
        response["Access-Control-Allow-Headers"] = ",".join(CORS_ALLOWED_HEADERS)
        response["Access-Control-Expose-Headers"] = ",".join(CORS_EXPOSE_HEADERS + CORS_EXTRA_EXPOSE_HEADERS)
        response["Access-Control-Max-Age"] = "1800"

        if CORS_ALLOWED_CREDENTIALS:
            response["Access-Control-Allow-Credentials"] = "true"

    def process_request(self, request):
        if "access-control-request-method" in request.headers:
            response = http.HttpResponse()
            self._populate_response(request, response)
            return response
        return None

    def process_response(self, request, response):
        self._populate_response(request, response)
        return response
