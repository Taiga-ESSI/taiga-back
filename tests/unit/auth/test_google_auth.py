
import pytest
from unittest.mock import patch, MagicMock
from taiga.auth.providers.google import login_with_google
from django.contrib.auth import get_user_model
from django.test.utils import override_settings
from taiga.base import exceptions as exc

User = get_user_model()

@pytest.fixture
def google_payload():
    return {
        "iss": "https://accounts.google.com",
        "aud": "client-id-123",
        "sub": "1234567890",
        "email": "test@example.com",
        "email_verified": True,
        "name": "Test User",
        "given_name": "Test",
        "family_name": "User",
        "hd": "example.com"
    }

@override_settings(GOOGLE_AUTH={
    "ENABLED": True,
    "CLIENT_IDS": ["client-id-123"],
    "ALLOWED_DOMAINS": ["example.com"],
    "AUTO_CREATE_USERS": True
})
@pytest.mark.django_db
def test_login_with_google_success_creates_user(google_payload):
    request = MagicMock()
    request.DATA = {"credential": "valid-token"}
    
    with patch("taiga.auth.providers.google.id_token.verify_oauth2_token") as mock_verify, \
         patch("taiga.auth.providers.google.CLIENT_IDS", ["client-id-123"]), \
         patch("taiga.auth.providers.google.ALLOWED_DOMAINS", {"example.com"}), \
         patch("taiga.auth.providers.google.AUTO_CREATE_USERS", True):
             
        mock_verify.return_value = google_payload
        
        response = login_with_google(request)
        
        assert "auth_token" in response
        assert response["username"]
        assert User.objects.filter(email="test@example.com").exists()
        user = User.objects.get(email="test@example.com")
        assert user.full_name == "Test User"
        assert user.accepted_terms is True

@override_settings(GOOGLE_AUTH={
    "ENABLED": True,
    "CLIENT_IDS": ["client-id-123"],
    "ALLOWED_DOMAINS": ["example.com"],
    "AUTO_CREATE_USERS": True
})
def test_login_with_google_invalid_issuer(google_payload):
    request = MagicMock()
    request.DATA = {"credential": "token"}
    google_payload["iss"] = "evil.com"
    
    with patch("taiga.auth.providers.google.id_token.verify_oauth2_token") as mock_verify, \
         patch("taiga.auth.providers.google.CLIENT_IDS", ["client-id-123"]):
         
        mock_verify.return_value = google_payload
        
        with pytest.raises(exc.BadRequest) as e:
            login_with_google(request)
        assert "Invalid Google credential" in str(e.value)

@override_settings(GOOGLE_AUTH={
    "ENABLED": True,
    "CLIENT_IDS": ["client-id-123"],
    "ALLOWED_DOMAINS": ["example.com"],
    "AUTO_CREATE_USERS": True
})
def test_login_with_google_email_not_verified(google_payload):
    request = MagicMock()
    request.DATA = {"credential": "token"}
    google_payload["email_verified"] = False
    
    with patch("taiga.auth.providers.google.id_token.verify_oauth2_token") as mock_verify, \
         patch("taiga.auth.providers.google.CLIENT_IDS", ["client-id-123"]):
         
        mock_verify.return_value = google_payload
        
        with pytest.raises(exc.BadRequest) as e:
            login_with_google(request)
        assert "Google has not verified this email" in str(e.value)

@override_settings(GOOGLE_AUTH={
    "ENABLED": True,
    "CLIENT_IDS": ["client-id-123"],
    "ALLOWED_DOMAINS": ["allowed.com"],
    "AUTO_CREATE_USERS": True
})
def test_login_with_google_domain_not_allowed(google_payload):
    request = MagicMock()
    request.DATA = {"credential": "token"}
    google_payload["email"] = "test@other.com"
    google_payload["hd"] = "other.com"
    
    with patch("taiga.auth.providers.google.id_token.verify_oauth2_token") as mock_verify, \
         patch("taiga.auth.providers.google.CLIENT_IDS", ["client-id-123"]), \
         patch("taiga.auth.providers.google.ALLOWED_DOMAINS", {"allowed.com"}):
         
        mock_verify.return_value = google_payload
        
        with pytest.raises(exc.BadRequest) as e:
            login_with_google(request)
        assert "not allowed to sign in" in str(e.value)

@override_settings(GOOGLE_AUTH={
    "ENABLED": True,
    "CLIENT_IDS": ["client-id-123"],
    "ALLOWED_DOMAINS": [],
    "AUTO_CREATE_USERS": False
})
@pytest.mark.django_db
def test_login_with_google_no_auto_create(google_payload):
    request = MagicMock()
    request.DATA = {"credential": "token"}
    
    with patch("taiga.auth.providers.google.id_token.verify_oauth2_token") as mock_verify, \
         patch("taiga.auth.providers.google.CLIENT_IDS", ["client-id-123"]), \
         patch("taiga.auth.providers.google.ALLOWED_DOMAINS", set()), \
         patch("taiga.auth.providers.google.AUTO_CREATE_USERS", False):
         
        mock_verify.return_value = google_payload
        
        with pytest.raises(exc.BadRequest) as e:
            login_with_google(request)
        assert "not associated with a Taiga user" in str(e.value)
