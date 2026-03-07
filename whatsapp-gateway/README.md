# WhatsApp Gateway

Local Node.js gateway using Baileys for WhatsApp transport.

## Endpoints

- `GET /health`
- `GET /status`
- `GET /qr`
- `POST /send` body: `{ "to": "<jid>", "text": "<message>" }`
- `POST /disconnect`

## Environment

Copy `.env.example` to `.env` and adjust values.
- `MEDIA_DIR` controls where inbound WhatsApp media files are saved before being forwarded to Python webhook.

## Start

```bash
npm install
npm start
```

The gateway posts inbound messages to the Python webhook URL configured in `.env`.
