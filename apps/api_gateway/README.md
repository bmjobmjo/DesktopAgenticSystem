# DAS API Gateway

This service exposes HTTP API endpoints over the existing DAS core runtime.

## Run

From repository root:

```powershell
python api_start.py
```

Direct:

```powershell
cd apps/api_gateway
python main.py
```

Default bind: `127.0.0.1:8787`

## Core endpoints

- `GET /health`
- `POST /uiport/chat/send`
- `POST /auth/login`
- `GET /auth/me`
- `POST /auth/logout`
- `POST /auth/change-password`
- `GET /settings` (auth required)
- `PUT /settings` (auth required)
- `GET /admin/users` (admin)
- `POST /admin/users` (admin)
- `POST /admin/users/{id}/send-new-password` (admin)

## Bootstrap admin

Uses env vars on first run if no admin exists:

- `DAS_BOOTSTRAP_ADMIN_USERNAME` (default `admin`)
- `DAS_BOOTSTRAP_ADMIN_EMAIL` (default `admin@local`)
- `DAS_BOOTSTRAP_ADMIN_PASSWORD` (default `admin123`)

## Password Delivery Mode

Admin user creation and password reset now run in manual handover mode:

- API always returns `temporary_password`
- `password_sent` is always `false`
- SMTP is not used by default for these flows
