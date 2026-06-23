# GEDU / GEDULink Rasa Render Deployment

This package deploys your Rasa chatbot to Render using two Docker web services:

1. `gedu-rasa-action-uniuwa47` — Rasa SDK custom action server
2. `gedu-rasa-server-uniuwa47` — Rasa REST webhook server

## Deploy steps

1. Create a new GitHub repository.
2. Upload all files from this folder to the repository root.
3. In Render, choose **New > Blueprint**.
4. Connect the GitHub repository and select the `render.yaml` file.
5. Add environment variables:
   - `GEMINI_API_KEY` on the action service if you want Gemini fallback.
   - `VITE_LEAD_WEBHOOK_URL` on the action service if you use a lead webhook.
6. Deploy both services.
7. Use this webhook URL in your frontend:

```txt
https://gedu-rasa-server-uniuwa47.onrender.com/webhooks/rest/webhook
```

If Render asks you to change service names because a name is unavailable, update the `ACTION_ENDPOINT_URL` value to match the new action service URL.

## Test with curl

```bash
curl -X POST https://gedu-rasa-server-uniuwa47.onrender.com/webhooks/rest/webhook \
  -H "Content-Type: application/json" \
  -d '{"sender":"test_user","message":"مرحبا"}'
```

Expected response: JSON array with at least one bot message.


## Patch note: Action server startup

If Render logs show `error: unrecognized arguments: --host 0.0.0.0` for `gedu-rasa-action-uniuwa47`, the action server command should be:

```bash
python -m rasa_sdk --actions actions --port ${PORT:-5055}
```

The Rasa SDK action server does not accept the `--host` flag in this image.
