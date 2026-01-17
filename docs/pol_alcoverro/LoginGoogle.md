# Google SSO Backend Integration

## Overview
- Adds a `google` auth plugin to `/api/v1/auth` that accepts Google Identity Services ID tokens.
- Tokens are verified with `google-auth==2.29.0`, the official library maintained by Google (Apache 2.0, compatible with MPL/AGPL obligations).
- Only emails from `@upc.edu` and `@estudiantat.upc.edu` are allowed by default; domains can be tuned via configuration while the backend enforces the restriction server-side.
- Existing users are matched by email (case-insensitive). New accounts are auto-provisioned with verified-email status unless disabled.

## Cambios aplicados (taiga-back)
- `taiga-back/settings/common.py`: se anadio el bloque `GOOGLE_AUTH` con nuevas variables de entorno (`GOOGLE_AUTH_CLIENT_IDS`, `GOOGLE_AUTH_ALLOWED_DOMAINS`, `GOOGLE_AUTH_AUTO_CREATE`, `GOOGLE_AUTH_ENABLED`) y valores por defecto pensados para desarrollo UPC.
- `taiga-back/requirements.in` y `taiga-back/requirements.txt`: se incluyo el paquete `google-auth` y dependencias derivadas para validar tokens de Google desde Django.
- `taiga-back/taiga/auth/services.py`: el cargador de plugins comprueba `settings.GOOGLE_AUTH['ENABLED']` y registra dinamicamente el proveedor Google; ante configuraciones invalidas devuelve un `400` controlado.
- `taiga-back/taiga/auth/providers/google.py`: nuevo manejador `login_with_google` que valida el token, comprueba dominio permitido, crea usuarios cuando `AUTO_CREATE_USERS` esta activo y responde con el mismo payload que el login clasico.
- Traducciones: se introdujeron mensajes traducibles especificos en `taiga/auth/providers/google.py` para exponer errores de configuracion o dominio de manera controlada.
- `taiga-back/taiga/auth/services.py`: Pol Alcoverro comentó el login y registro clásicos (`login`, `public_register`, `private_register_for_new_user`) para que ahora respondan con un `400` controlado y dejó el código original comentado para referencia.

## Configuration
Set the following environment variables (e.g. in `settings/local.py` or process env):

| Variable | Default | Description |
| --- | --- | --- |
| `GOOGLE_AUTH_CLIENT_IDS` | `286907234950-enq7c1j4085fbj662otfptqqo24hk93u.apps.googleusercontent.com` | Comma-separated list of OAuth 2.0 client IDs issued by Google (typically the web client ID). Override in production with your own ID(s). |
| `GOOGLE_AUTH_ENABLED` | auto (`true` when client IDs provided) | Explicitly enable/disable the plugin. |
| `GOOGLE_AUTH_ALLOWED_DOMAINS` | `upc.edu,estudiantat.upc.edu` | Comma-separated list of domains accepted for login; compared against both the email domain and the `hd` claim. |
| `GOOGLE_AUTH_AUTO_CREATE` | `true` | When `true`, a Taiga account is created automatically for first-time allowed domain users; when `false`, only pre-existing users can log in. |

Behavioural notes:
- Users created through Google SSO receive an unusable password, `verified_email=True`, and inherit default limits/terms acceptance flags. Rename/update their profile as usual via the UI.
- When `invitation_token` is sent alongside the login payload, the normal invitation acceptance flow still runs.
- If configuration is invalid (missing dependency, missing client IDs), the API returns `400` with a friendly error instead of exposing internal tracebacks.
- The sample development client ID ships in `settings/common.py`; set the environment variable in every deployed environment to replace it with your own credential(s).

## Request Payload
The frontend posts to `/api/v1/auth` with `type=google` and the Google credential:

```json
{
  "type": "google",
  "credential": "<ID_TOKEN>",
  "client_id": "<matching Google client ID>",
  "invitation_token": "<optional invitation token>"
}
```

The response mirrors Taiga's standard auth payload (user information, `auth_token`, `refresh`).

## Dependencies and Licensing
- `google-auth==2.29.0` plus its transitive requirements (`cachetools`, `rsa`, `pyasn1`, `pyasn1-modules`) are pinned in `requirements.txt`.
- `google-auth` is Apache 2.0 licensed; Apache 2.0 is compatible with MPL 2.0 / AGPL compliance duties already observed in Taiga. Keep NOTICE files intact if you redistribute binaries.
- Google Identity Services usage must comply with Google's OAuth Terms of Service; no user data beyond the ID token is stored server-side.

## Logging & Error Surfaces
- Invalid tokens, audience mismatches, or non-permitted domains raise `400 Bad Request` with translated messages (consumed by the frontend notifier).
- Disabled or system users produce a controlled `400` with an explicit explanation.
- Token verification failures are logged at warning level for traceability but avoid leaking token contents.

## Operational Checklist
1. Obtain the OAuth 2.0 Web client ID from [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
2. Configure redirect URIs as needed for GIS One Tap/button usage; no backend redirect endpoints are required because we exchange ID tokens only.
3. Override `GOOGLE_AUTH_CLIENT_IDS` (and optionally the other knobs) via environment variables or your deployment tooling, then restart the backend.
4. Install/update dependencies: `pip install -r requirements.txt`.
5. Optionally add integration tests exercising `/api/v1/auth` with mocked Google responses (the helper accepts patching `google.oauth2.id_token.verify_oauth2_token`).

## Residual Considerations
- Rate limiting relies on existing login throttles; heavy misuse could still surface, so monitor failed login metrics.
- If additional domains must be admitted later, update both `GOOGLE_AUTH_ALLOWED_DOMAINS` and the frontend hint text (the UI reads the list dynamically).
- Revoking auto-provisioning requires `GOOGLE_AUTH_AUTO_CREATE=false` and ensuring target users are pre-created by admins.
