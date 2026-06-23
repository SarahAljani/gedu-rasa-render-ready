# GEDULink Rasa + Gemini Knowledge Setup

Replace these files in your `gedu-rasa-render-ready` GitHub repo:

- `actions/actions.py`
- `config.yml`
- `domain.yml`
- `data/nlu.yml`
- `data/rules.yml`
- `data/stories.yml`
- `render.yaml`

## Render environment variables

In Render, open the **action service**:

`gedu-rasa-action-uniuwa47 → Environment`

Add:

```text
GEMINI_API_KEY=your_real_gemini_key
LEAD_WEBHOOK_URL=https://hook.eu1.make.com/your_make_webhook
GEMINI_MODEL=gemini-2.5-flash
GEDULINK_WEBSITE_URLS=https://gedulink.com/,https://gedulink.com/programs,https://gedulink.com/destinations,https://gedulink.com/services,https://gedulink.com/contact
```

Then redeploy:

1. `gedu-rasa-action-uniuwa47` → Manual Deploy → Deploy latest commit
2. `gedu-rasa-server-uniuwa47` → Manual Deploy → Clear build cache & deploy

## How it works

Frontend sends message to Rasa server:

`/webhooks/rest/webhook`

Rasa detects broad intent, then calls:

`action_ask_gemini`

The action server:

1. Reads GEDULink static knowledge.
2. Fetches limited public text from GEDULink website URLs.
3. Sends the user question + knowledge + website context to Gemini.
4. Returns Gemini's answer to the website chatbot.
5. If phone/email is detected, sends lead data to Make webhook.
