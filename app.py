import os
import sys
import re
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from flask import Flask, request, jsonify
from twilio.rest import Client
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import traceback

# ─────────────────────────────── logging setup ────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()  # INFO in Prod
LOG_FORMAT = "% (asctime)s | %(levelname)-8s | %(name)s: %(message)s"

logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    handlers=[logging.StreamHandler(sys.stdout)],  # Render‑Dashboard
)
file_handler = RotatingFileHandler("app.log", maxBytes=5_000_000, backupCount=3)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
logging.getLogger().addHandler(file_handler)

logger = logging.getLogger("voicebot")

# ─────────────────────────────── env / clients ────────────────────────────────
load_dotenv()

app = Flask(__name__)

# Twilio
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
from_number = os.getenv("TWILIO_FROM_NUMBER")
client = Client(account_sid, auth_token)

# Google Sheets
google_sheet_id = os.getenv("GOOGLE_SHEET_ID")
credentials_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
creds_dict = json.loads(credentials_json)


# ─────────────────────────────── helper routes ────────────────────────────────
@app.route("/check-mobile", methods=["POST"])
def check_mobile():
    data = request.json or {}
    caller = data.get("caller")
    logger.debug("📞 Eingehende Nummer payload: %s", data)

    if not caller:
        logger.info("🚫 Keine Nummer sichtbar")
        return jsonify({"status": "no_number"}), 200

    if caller.startswith(("+4915", "+4916", "+4917")):
        logger.info("✅ Mobilnummer erkannt: %s", caller)
        return jsonify({"status": "mobile"}), 200

    logger.info("ℹ️  Festnetz/unbekannt: %s", caller)
    return jsonify({"status": "not_mobile"}), 200


@app.route("/parse-phone", methods=["POST"])
def parse_phone():
    """Extract mobile number from the last user message."""
    data = request.json or {}
    text = data.get("last_user_message", "")
    logger.debug("🗣️  User‑Text: %s", text)

    match = re.search(r"(?:\+?49[ \-]?)?1[5-7]\d[ \-]?\d{6,}", text)
    if match:
        raw = re.sub(r"\D", "", match.group())  # only digits
        digits = raw.lstrip("0")  # drop leading 0 if present
        if not digits.startswith("49"):
            digits = "49" + digits
        mobile = f"+{digits}"
        logger.info("📲 Erkannte Mobilnummer: %s", mobile)
        return jsonify({"status": "ok", "mobile": mobile}), 200

    logger.warning("🚫 Keine gültige Mobilnummer erkannt")
    return jsonify({"status": "error"}), 200


@app.route("/send-sms", methods=["POST"])
def send_sms():
    data = request.json or {}
    to = data.get("to")
    message = data.get("message")

    logger.info("📨 SMS‑Request an %s", to)
    logger.debug("📝 Nachricht: %.60s", message)

    if not to or not message:
        logger.error("❌ 'to' oder 'message' fehlt im Request")
        return jsonify({"status": "error", "message": "Missing 'to' or 'message'"}), 400

    # Platzhalter‑Schutz (Sandbox‑Tests)
    if (
        not account_sid
        or not auth_token
        or not from_number
        or account_sid == "placeholder"
        or auth_token == "placeholder"
    ):
        logger.warning("⚠️  Twilio‑Credentials fehlen – Simulation aktiv")
        logger.debug("(Simulation) SMS an %s: %s", to, message)
        return jsonify({"status": "mock"}), 200

    try:
        sms = client.messages.create(to=to, from_=from_number, body=message)
        logger.info("✅ SMS gesendet – SID: %s", sms.sid)
        return jsonify({"status": "success", "sid": sms.sid}), 200
    except Exception as exc:
        logger.exception("❌ Fehler beim SMS‑Versand: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/save-transcript", methods=["POST"])
def save_transcript():
    data = request.json or {}
    if data.get("event") != "call_ended":
        return jsonify({"status": "ignored"}), 200

    call = data.get("call", {})
    trans = call.get("transcript", "")
    call_id = call.get("call_id", "unknown")

    if not trans:
        return jsonify({"status": "error", "message": "Transcript fehlt"}), 400

    datum = datetime.now().strftime("%Y-%m-%d")
    zeit = datetime.now().strftime("%H:%M")

    logger.info("📞 Call %s beendet – speichere Transkript", call_id)

    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        gc = gspread.authorize(creds)
        sheet = gc.open_by_key(google_sheet_id).sheet1
        sheet.append_row([datum, zeit, call_id, trans])
        logger.info("✅ Transkript gespeichert (%s Zeichen)", len(trans))
        return jsonify({"status": "success"}), 200

    except gspread.exceptions.APIError as gs_err:
        logger.error("❌ Google Sheets API Fehler: %s", gs_err)
        code = (
            "forbidden"
            if "403" in str(gs_err)
            else "not_found" if "404" in str(gs_err) else "error"
        )
        return jsonify({"status": code, "message": str(gs_err)}), 500
    except Exception as exc:
        logger.exception(
            "❌ Allgemeiner Fehler beim Speichern des Transkripts: %s", exc
        )
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/health", methods=["GET"])
def health_check():
    return "OK", 200


# ─────────────────────────────── main ────────────────────────────────
if __name__ == "__main__":
    logger.info("🚀 Server wird gestartet … Port 10000")
    app.run(host="0.0.0.0", port=10000)
