"""WhatsApp front end for proof.py: text a task, Codex does it in your workspace, the bot replies with proof.

Uses Meta's official WhatsApp Cloud API. Only messages signed by Meta (APP_SECRET) and sent from
OWNER_NUMBER are acted on. The bot itself sends every report, so the agent never writes or edits it.
Settings are read from .env next to this file; see .env.example.
"""
import hashlib
import hmac
import json
import queue
import re
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import proof

REQUIRED = ("WORKSPACE", "WHATSAPP_TOKEN", "PHONE_NUMBER_ID", "APP_SECRET", "VERIFY_TOKEN", "OWNER_NUMBER")
HELP = """Text me a task and I'll do it in your workspace, then send proof that it's really done.
Other messages I understand:
status - what I'm working on
show 3 - the report for job 3 again
verify 3 P3-abc123 - re-check a receipt
help - this message"""


def digits(number):
    return re.sub(r"\D", "", number)


class Bot:
    def __init__(self, env):
        missing = [key for key in REQUIRED if not env.get(key)]
        if missing:
            raise SystemExit(f"Missing in .env: {', '.join(missing)}. Copy .env.example to .env and fill it in.")
        self.settings = proof.Settings.from_env(env)
        self.settings.home.mkdir(parents=True, exist_ok=True)
        self.token, self.phone_id = env["WHATSAPP_TOKEN"], env["PHONE_NUMBER_ID"]
        self.secret, self.verify_token = env["APP_SECRET"].encode(), env["VERIFY_TOKEN"]
        self.owner = digits(env["OWNER_NUMBER"])
        self.graph = env.get("GRAPH_BASE", "https://graph.facebook.com/v23.0").rstrip("/")
        self.tasks = queue.Queue()
        self.current = None
        self.answers = queue.Queue()
        self.waiting = False
        self.seen_file = self.settings.home / "seen_messages.json"
        self.seen = set(json.loads(self.seen_file.read_text())) if self.seen_file.exists() else set()
        self.seen_lock = threading.Lock()

    def send(self, text):
        """Send a text message to the owner, split at line breaks if it is too long for one."""
        parts, part = [], ""
        for line in text.splitlines():
            if len(part) + len(line) + 1 > 4000:
                parts.append(part)
                part = ""
            part += line + "\n"
        parts.append(part)
        for body in filter(str.strip, parts):
            payload = {"messaging_product": "whatsapp", "to": self.owner, "type": "text",
                       "text": {"preview_url": False, "body": body.rstrip()}}
            request = urllib.request.Request(f"{self.graph}/{self.phone_id}/messages",
                                             data=json.dumps(payload).encode("utf-8"), method="POST",
                                             headers={"Authorization": f"Bearer {self.token}",
                                                      "Content-Type": "application/json"})
            try:
                urllib.request.urlopen(request, timeout=30).read()
            except urllib.error.HTTPError as error:
                print(f"WhatsApp refused a message: {error.code} {error.read().decode('utf-8', 'replace')[:300]}")
            except urllib.error.URLError as error:
                print(f"Could not reach WhatsApp: {error.reason}")

    def ask(self, text):
        """Put a question to the owner and wait for the reply. No work starts until they answer."""
        self.waiting = True
        self.send(f"{text}\nReply with a letter, or say what you meant.")
        try:
            return self.answers.get(timeout=3600)
        except queue.Empty:
            raise RuntimeError("nobody answered within an hour, so no work was done") from None
        finally:
            self.waiting = False

    def first_time(self, message_id):
        """Meta retries webhooks, so act on each message ID once."""
        with self.seen_lock:
            if message_id in self.seen:
                return False
            self.seen.add(message_id)
            self.seen_file.write_text(json.dumps(sorted(self.seen)[-5000:]))
            return True

    def handle(self, sender, message_id, text):
        if digits(sender) != self.owner:
            print(f"Ignored a message from {sender}: only OWNER_NUMBER can give orders.")
            return
        if not self.first_time(message_id):
            return
        if self.waiting:
            self.answers.put(text.strip())
            return
        words = text.strip().split()
        command = words[0].lower() if words else ""
        if command == "help" or not words:
            self.send(HELP)
        elif command == "status" and len(words) == 1:
            waiting = self.tasks.qsize()
            self.send(f"Working on: {self.current}\n{waiting} more waiting." if self.current else "Idle. Send me a task.")
        elif command == "show" and len(words) == 2 and words[1].isdigit():
            report = proof.job_dir(self.settings, int(words[1])) / "report.txt"
            self.send(report.read_text(encoding="utf-8") if report.exists() else f"Job {words[1]} has no report yet.")
        elif command == "verify" and len(words) == 3 and words[1].isdigit():
            self.send(proof.verify(self.settings, int(words[1]), words[2], recheck=True)[1])
        else:
            self.tasks.put(text.strip())
            ahead = self.tasks.qsize() - 1 + (self.current is not None)
            self.send(f"On it{f' after {ahead} other job(s)' if ahead else ''}. I'll text you the proof when it's done.")

    def work(self):
        while True:
            request = self.tasks.get()
            self.current = request[:120]
            try:
                _, report = proof.run_job(self.settings, request, self.send, self.ask)
                self.send(report)
            except Exception as error:  # report every failure to the owner rather than dying silently
                self.send(f"The job stopped before it could be proven: {error}")
            finally:
                self.current = None


def make_handler(bot):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, body=b"ok"):
            self.send_response(code)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/health":
                return self.reply(200)
            query = parse_qs(url.query)
            if url.path == "/webhook" and query.get("hub.mode") == ["subscribe"] and hmac.compare_digest(
                    query.get("hub.verify_token", [""])[0], bot.verify_token):
                return self.reply(200, query.get("hub.challenge", [""])[0].encode())
            self.reply(403, b"forbidden")

        def do_POST(self):
            if urlparse(self.path).path != "/webhook":
                return self.reply(404, b"not found")
            length = int(self.headers.get("Content-Length", 0))
            if length > 1_000_000:
                return self.reply(413, b"too large")
            body = self.rfile.read(length)
            expected = "sha256=" + hmac.new(bot.secret, body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(self.headers.get("X-Hub-Signature-256", ""), expected):
                return self.reply(403, b"bad signature")
            self.reply(200)
            try:
                data = json.loads(body)
            except ValueError:
                return
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    for message in change.get("value", {}).get("messages", []):
                        text = message.get("text", {}).get("body", "") if message.get("type") == "text" else ""
                        threading.Thread(target=bot.handle, daemon=True,
                                         args=(message.get("from", ""), message.get("id", ""), text or "help")).start()

        def log_message(self, *args):
            pass

    return Handler


def serve(env, port=None):
    bot = Bot(env)
    threading.Thread(target=bot.work, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", int(port if port is not None else env.get("PORT", 8787))), make_handler(bot))
    return bot, server


def main():
    env = proof.load_env(Path(__file__).with_name(".env"))
    bot, server = serve(env)
    ok, detail = proof.sandbox_works(bot.settings)
    if not ok:
        sys.exit("The sandbox cannot run Python, so sealed checks cannot run safely:\n  " + detail +
                 "\nSee 'Let the sandbox run Python' in README.md, or set CHECK_RUNNER=direct to run checks unsandboxed.")
    port = server.server_address[1]
    print(f"WhatsApp bot ready. Workspace: {bot.settings.workspace}\n"
          f"Webhook: http://127.0.0.1:{port}/webhook. Expose it with: ngrok http {port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
