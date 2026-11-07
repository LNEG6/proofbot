# Running Proofbot from WhatsApp

Proofbot is built for a [Switch room](../README.md#run-it-in-switch), where a team can answer questions together. If you work alone and want to text tasks from your phone, this WhatsApp front end does the same job for one person. It doesn't use Switch, and it needs Codex or Claude Code signed in on your PC.

`whatsapp_bot.py` was tested against a fake WhatsApp server that follows Meta's documented webhook and message formats, not against a real Meta app.

## Set it up

You need about 15 minutes, a Meta developer account, and [ngrok](https://ngrok.com).

1. Go to [developers.facebook.com](https://developers.facebook.com), create an app, and add the **WhatsApp** product.
2. In **WhatsApp > API Setup**, note the test number's **Phone number ID** and copy the **temporary access token**. Under **To**, add your own WhatsApp number and confirm the code Meta sends you.
3. In **App settings > Basic**, copy the **App secret**.
4. Copy `.env.example` to `.env` and fill it in: your workspace folder, test command, the token, phone number ID, app secret, a verify phrase you make up, and your own number.
5. Start the bot, and the tunnel in a second terminal:

```powershell
python whatsapp_bot.py
```

```powershell
ngrok http 8787
```

6. In **WhatsApp > Configuration**, set the callback URL to the ngrok `https://...` address plus `/webhook`, enter your verify phrase, and save. Under **Webhook fields**, subscribe to **messages**.
7. From your phone, text the test number: `Fix the typo in README.md`. You'll get "On it.", short progress messages, any questions about what you meant, then the proof.

Other messages it understands: `status`, `show 3` (resend job 3's report) and `verify 3 P3-...` (re-check a receipt and re-run its sealed checks).

The temporary token lasts 24 hours. For longer, create a system-user token with the `whatsapp_business_messaging` permission in Meta Business settings. Only your number can give orders, and only requests signed with your app secret are accepted.

## Letting the Codex sandbox run Python

With `AGENT=codex`, checks run inside Codex's Windows sandbox, which can only change the workspace. The sandbox runs as separate Windows accounts (`CodexSandboxOffline`, `CodexSandboxOnline`), and those can't read a Python installed just for you. Until that's fixed, `python proof.py doctor` reports a problem and the bot won't start with sandboxed checks.

Pick one:

- **Let the sandbox accounts run Python.** This changes permissions on your PC, so decide for yourself. It hasn't been tested. Afterwards, `doctor` should say OK.

```powershell
icacls "$env:LOCALAPPDATA\Programs\Python\Python311" /grant "CodexSandboxOffline:(OI)(CI)RX" /grant "CodexSandboxOnline:(OI)(CI)RX" /T
```

- **Or set `CHECK_RUNNER=direct` in `.env`.** Checks and tests then run as you, unsandboxed. Codex itself stays sandboxed, but the checks it writes run with your full access.
