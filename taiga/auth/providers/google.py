# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

import logging
import re
from typing import Iterable, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction as db_transaction
from django.utils.translation import gettext_lazy as _

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from taiga.auth.services import make_auth_response_data, register_auth_plugin
from taiga.base import exceptions as exc


logger = logging.getLogger(__name__)

CONFIG = getattr(settings, "GOOGLE_AUTH", {})
CLIENT_IDS: Iterable[str] = tuple(CONFIG.get("CLIENT_IDS", []))
ALLOWED_DOMAINS = {domain.lower() for domain in CONFIG.get("ALLOWED_DOMAINS", []) if domain}
AUTO_CREATE_USERS = bool(CONFIG.get("AUTO_CREATE_USERS", True))

if not CLIENT_IDS:
    raise ImproperlyConfigured("Google auth plugin requires at least one client id")

_GOOGLE_REQUEST = google_requests.Request()
_USERNAME_SANITIZER = re.compile(r"[^A-Za-z0-9._-]")


def _normalise_username(value: str) -> str:
    cleaned = _USERNAME_SANITIZER.sub("-", (value or "").lower()).strip(".-")
    cleaned = re.sub(r"-+", "-", cleaned)
    return cleaned or "user"


def _build_unique_username(email_local_part: str) -> str:
    base = _normalise_username(email_local_part)
    user_model = get_user_model()

    candidate = base
    suffix = 1
    while user_model.objects.filter(username=candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1

    return candidate


def _extract_full_name(payload: dict) -> str:
    full_name = (payload.get("name") or "").strip()
    if full_name:
        return full_name

    given = (payload.get("given_name") or "").strip()
    family = (payload.get("family_name") or "").strip()
    full_name = " ".join(part for part in (given, family) if part)
    return full_name or ""


def _verify_credential(raw_token: str, client_hint: Optional[str]) -> dict:
    if not raw_token:
        raise exc.BadRequest(_("Missing Google credential."))

    audiences = CLIENT_IDS
    if client_hint and client_hint in CLIENT_IDS:
        audiences = (client_hint,)

    last_error = None
    for audience in audiences:
        try:
            return id_token.verify_oauth2_token(raw_token, _GOOGLE_REQUEST, audience=audience)
        except ValueError as err:  # pragma: no cover - google-auth raises ValueError
            last_error = err

    logger.warning("Google credential verification failed: %s", last_error)
    raise exc.BadRequest(_("Invalid Google credential.")) from last_error


def _ensure_domain_allowed(email: str, hosted_domain: Optional[str]):
    email_domain = email.split("@")[-1].lower()
    if ALLOWED_DOMAINS and email_domain not in ALLOWED_DOMAINS:
        raise exc.BadRequest(_("Your Google account is not allowed to sign in."))

    if hosted_domain:
        hosted_domain = hosted_domain.lower()
        if ALLOWED_DOMAINS and hosted_domain not in ALLOWED_DOMAINS:
            raise exc.BadRequest(_("Your Google Workspace domain is not allowed."))


def _get_or_create_user(email: str, payload: dict):
    user_model = get_user_model()

    try:
        user = user_model.objects.get(email__iexact=email)
    except user_model.DoesNotExist:
        if not AUTO_CREATE_USERS:
            raise exc.BadRequest(_("This Google account is not associated with a Taiga user."))
        user = _create_user_from_payload(email, payload)
    else:
        if not user.is_active or user.is_system:
            raise exc.BadRequest(_("This user account is disabled."))

        update_fields = []
        if not user.verified_email:
            user.verified_email = True
            update_fields.append("verified_email")

        new_full_name = _extract_full_name(payload)
        if new_full_name and not user.full_name:
            user.full_name = new_full_name
            update_fields.append("full_name")

        if update_fields:
            user.save(update_fields=update_fields)

    return user


@db_transaction.atomic
def _create_user_from_payload(email: str, payload: dict):
    user_model = get_user_model()
    local_part = email.split("@")[0]
    username = _build_unique_username(local_part)
    full_name = _extract_full_name(payload)

    user = user_model(
        username=username,
        email=email,
        full_name=full_name,
        verified_email=True,
        accepted_terms=True,
        read_new_terms=True,
        new_email=None,
    )
    user.set_unusable_password()
    user.save()
    return user


# Pol Alcoverro: punto de entrada del login mediante Google Identity Services.
def login_with_google(request):
    try:
        raw_token = request.DATA.get("credential") or request.DATA.get("id_token")
        client_hint = request.DATA.get("client_id")

        payload = _verify_credential(raw_token, client_hint)

        with open("google_auth_debug.log", "a") as f:
            f.write(f"Payload: {payload}\n")

        if payload.get("aud") not in CLIENT_IDS:
            logger.warning("Rejected Google credential with unexpected audience: %s", payload.get("aud"))
            raise exc.BadRequest(_("Invalid Google credential."))

        if payload.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
            logger.warning("Rejected Google credential with invalid issuer: %s", payload.get("iss"))
            raise exc.BadRequest(_("Invalid Google credential."))

        if payload.get("email_verified") is not True:
            raise exc.BadRequest(_("Google has not verified this email address."))

        email = payload.get("email")
        if not email:
            raise exc.BadRequest(_("Google did not return an email address."))

        _ensure_domain_allowed(email, payload.get("hd"))

        user = _get_or_create_user(email.lower(), payload)
        return make_auth_response_data(user)
    except Exception as e:
        with open("google_auth_debug.log", "a") as f:
            f.write(f"Error: {e}\n")
            import traceback
            traceback.print_exc(file=f)
        raise


register_auth_plugin("google", login_with_google)
