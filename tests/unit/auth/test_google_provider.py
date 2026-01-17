# Pol Alcoverro
# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

import importlib
from types import SimpleNamespace

import pytest

from django.contrib.auth import get_user_model

from taiga.base import exceptions as exc

from tests import factories as f


class DummyRequest(SimpleNamespace):
    def __init__(self, data):
        super().__init__(DATA=data)


@pytest.fixture
def reload_google(settings):
    from taiga.auth import services as auth_services

    original_plugins = dict(auth_services.auth_plugins)

    def _reload(extra_settings=None):
        config = {
            "CLIENT_IDS": ["test-client"],
            "ALLOWED_DOMAINS": ["upc.edu", "estudiantat.upc.edu"],
            "AUTO_CREATE_USERS": True,
            "ENABLED": True,
        }
        if extra_settings:
            config.update(extra_settings)
        settings.GOOGLE_AUTH = config

        import taiga.auth.providers.google as google_module

        module = importlib.reload(google_module)
        return module

    yield _reload

    auth_services.auth_plugins.clear()
    auth_services.auth_plugins.update(original_plugins)


@pytest.mark.django_db
def test_login_creates_new_user(monkeypatch, reload_google):
    google_module = reload_google()

    captured_user = {}

    def fake_verify(raw_token, request, audience):
        assert raw_token == "good-token"
        assert audience == "test-client"
        return {
            "aud": "test-client",
            "iss": "accounts.google.com",
            "email": "john@upc.edu",
            "email_verified": True,
            "name": "John Doe",
        }

    def fake_auth_response(user):
        captured_user["instance"] = user
        return {"auth_token": "dummy", "refresh": "dummy"}

    monkeypatch.setattr(google_module.id_token, "verify_oauth2_token", fake_verify)
    monkeypatch.setattr(google_module, "make_auth_response_data", fake_auth_response)

    request = DummyRequest({"credential": "good-token", "client_id": "test-client"})

    response = google_module.login_with_google(request)

    user_model = get_user_model()
    user = user_model.objects.get(email="john@upc.edu")

    assert response == {"auth_token": "dummy", "refresh": "dummy"}
    assert captured_user["instance"] == user
    assert user.full_name == "John Doe"
    assert user.verified_email is True
    assert user.has_usable_password() is False


@pytest.mark.django_db
def test_login_updates_existing_user(monkeypatch, reload_google):
    google_module = reload_google()

    user = f.UserFactory(
        username="existing",
        email="existing@upc.edu",
        verified_email=False,
        full_name="",
        is_system=False,
    )

    def fake_verify(raw_token, request, audience):
        return {
            "aud": "test-client",
            "iss": "https://accounts.google.com",
            "email": "existing@upc.edu",
            "email_verified": True,
            "name": "Existing User",
        }

    def fake_auth_response(auth_user):
        assert auth_user == user
        return {"auth_token": "dummy", "refresh": "dummy"}

    monkeypatch.setattr(google_module.id_token, "verify_oauth2_token", fake_verify)
    monkeypatch.setattr(google_module, "make_auth_response_data", fake_auth_response)

    request = DummyRequest({"credential": "valid", "client_id": "test-client"})

    result = google_module.login_with_google(request)

    user.refresh_from_db()
    assert result["auth_token"] == "dummy"
    assert user.verified_email is True
    assert user.full_name == "Existing User"


@pytest.mark.django_db
def test_login_rejects_disallowed_domain(monkeypatch, reload_google):
    google_module = reload_google()

    def fake_verify(raw_token, request, audience):
        return {
            "aud": "test-client",
            "iss": "accounts.google.com",
            "email": "intruder@gmail.com",
            "email_verified": True,
        }

    monkeypatch.setattr(google_module.id_token, "verify_oauth2_token", fake_verify)

    request = DummyRequest({"credential": "token", "client_id": "test-client"})

    with pytest.raises(exc.BadRequest) as error_info:
        google_module.login_with_google(request)

    assert "not allowed" in str(error_info.value.detail)


@pytest.mark.django_db
def test_login_rejects_when_auto_create_disabled(monkeypatch, reload_google):
    google_module = reload_google({"AUTO_CREATE_USERS": False})
    assert google_module.AUTO_CREATE_USERS is False

    def fake_verify(raw_token, request, audience):
        return {
            "aud": "test-client",
            "iss": "accounts.google.com",
            "email": "new@upc.edu",
            "email_verified": True,
        }

    monkeypatch.setattr(google_module.id_token, "verify_oauth2_token", fake_verify)

    request = DummyRequest({"credential": "token", "client_id": "test-client"})

    with pytest.raises(exc.BadRequest) as error_info:
        google_module.login_with_google(request)

    assert "not associated" in str(error_info.value.detail)


@pytest.mark.django_db
def test_login_generates_unique_username(monkeypatch, reload_google):
    google_module = reload_google()

    f.UserFactory(username="john", email="john@example.com")

    created_users = {}

    def fake_verify(raw_token, request, audience):
        return {
            "aud": "test-client",
            "iss": "accounts.google.com",
            "email": "john@upc.edu",
            "email_verified": True,
            "given_name": "John",
            "family_name": "Smith",
        }

    def fake_auth_response(user):
        created_users["instance"] = user
        return {"auth_token": "dummy", "refresh": "dummy"}

    monkeypatch.setattr(google_module.id_token, "verify_oauth2_token", fake_verify)
    monkeypatch.setattr(google_module, "make_auth_response_data", fake_auth_response)

    request = DummyRequest({"credential": "token", "client_id": "test-client"})

    google_module.login_with_google(request)

    user_model = get_user_model()
    user = user_model.objects.get(email="john@upc.edu")
    assert created_users["instance"].username == "john-1"
    assert user.username == "john-1"


@pytest.mark.django_db
def test_login_rejects_unexpected_audience(monkeypatch, reload_google):
    google_module = reload_google()

    def fake_verify(raw_token, request, audience):
        return {
            "aud": "other-client",
            "iss": "accounts.google.com",
            "email": "john@upc.edu",
            "email_verified": True,
        }

    monkeypatch.setattr(google_module.id_token, "verify_oauth2_token", fake_verify)

    request = DummyRequest({"credential": "token", "client_id": "test-client"})

    with pytest.raises(exc.BadRequest) as error_info:
        google_module.login_with_google(request)

    assert "Invalid Google credential" in str(error_info.value.detail)
