from flask import Flask, request, jsonify
from zoneinfo import ZoneInfo
from twilio.rest import Client
from dotenv import load_dotenv
import os, json, re, traceback
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# -------------------  ENV einlesen und Flask initialisieren  ------------------
load_dotenv()  # 1️⃣ .env
app = Flask(__name__)  # 2️⃣ Flask‑App


# Twilio-Konfiguration
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
from_number = os.getenv("TWILIO_FROM_NUMBER")
twilio_client = Client(account_sid, auth_token)

# Google Sheet-Konfiguration
google_sheet_id = os.getenv("GOOGLE_SHEET_ID")
credentials_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
creds_dict = json.loads(credentials_json)

try:
    creds_dict = json.loads(credentials_json)
except Exception as e:
    print("❌ Fehler beim Parsen von GOOGLE_SERVICE_ACCOUNT_JSON:", str(e))
    creds_dict = {}


CALLER_NUMBERS = {}


@app.route("/start-call", methods=["POST"])
def start_call():
    data = request.json or {}

    if not data:
        print("⚠️ Kein JSON-Daten empfangen")
    if "call_id" not in data:
        print("⚠️ call_id fehlt")
    if "caller" not in data:
        print("⚠️ caller fehlt")

    call_id = data.get("call_id")
    phone = data.get("caller", None)

    print(f"📞 Start Call: {call_id} – Nummer: {phone}")

    if call_id and phone:
        CALLER_NUMBERS[call_id] = phone
        print(f"✅ Nummer zwischengespeichert: {CALLER_NUMBERS}")
        return jsonify({"status": "ok"}), 200

    return jsonify({"status": "error", "message": "call_id oder Nummer fehlt"}), 400


@app.route("/save-transcript", methods=["POST"])
def save_transcript():
    data = request.json
    if data.get("event") != "call_ended":
        return jsonify({"status": "ignored", "message": "Kein call_ended Event"}), 200

    call_data = data.get("call", {})
    transcript = call_data.get("transcript", "")
    call_id = call_data.get("call_id", "unknown")

    now = datetime.now(ZoneInfo("Europe/Berlin"))
    datum = now.strftime("%Y-%m-%d")
    zeit = now.strftime("%H:%M")

    if not transcript:
        return jsonify({"status": "error", "message": "Transcript fehlt"}), 400

    # 🆕 Versuche Nummer aus globalem Store zu holen
    caller_phone = CALLER_NUMBERS.get(call_id, "unknown")

    print("📞 Call beendet – speichere Transkript")
    print("▶️ Daten für Google Sheet:", datum, zeit, caller_phone, transcript[:80])

    try:
        # Authentifizierung & Schreiben ins Sheet
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        gs_client = gspread.authorize(creds)
        sheet = gs_client.open_by_key(google_sheet_id).sheet1

        # 🧠 Jetzt mit Telefonnummer
        sheet.append_row([datum, zeit, caller_phone, transcript])
        print("✅ Transkript gespeichert")

        # Optional: Eintrag aus Cache löschen
        CALLER_NUMBERS.pop(call_id, None)

        return jsonify({"status": "success"}), 200

    except Exception as e:
        print("❌ Fehler beim Speichern:", str(e))
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/check-mobile", methods=["POST"])
def check_mobile():
    data = request.json
    caller = data.get("caller")

    # ✅ 2. F‑String korrekt einsetzen – Variable in geschweifte Klammern
    print(f"📞 Eingehende Nummer: {caller}")

    # --- Kein Caller ------------------------------------------------------
    if not caller:
        print("🚫 Keine Nummer im Header/Caller-Objekt sichtbar")
        return jsonify({"status": "no_number", "message": "Keine Nummer sichtbar"}), 200

    # --- Mobilnummer ------------------------------------------------------
    if caller.startswith(("+4915", "+4916", "+4917")):
        print("✅ Mobilnummer erkannt")
        return jsonify({"status": "mobile", "message": "Mobilnummer erkannt"}), 200

    # --- Festnetz / unbekannt --------------------------------------------
    print("ℹ️  Festnetz‑ oder unbekannte Nummer")
    return jsonify({"status": "not_mobile", "message": "Keine Mobilnummer"}), 200


@app.route("/send-sms", methods=["POST"])
def send_sms():
    data = request.json
    to = data.get("to")
    message = data.get("message")

    print("📨 SMS-Anfrage empfangen:")
    print("👉 An:", to)

    if message:
        print(f"📝 Nachricht (gekürzt): {message[:60]}…")
    else:
        print("📝 Nachricht fehlt oder ist leer.")

    if not to or not message:
        print("❌ Fehler: 'to' oder 'message' fehlt im Request.")
        return jsonify({"status": "error", "message": "Missing 'to' or 'message'"}), 400

    if (
        not account_sid
        or not auth_token
        or not from_number
        or account_sid == "placeholder"
        or auth_token == "placeholder"
    ):
        print("⚠️  Twilio-Daten fehlen oder Platzhalter aktiv – führe Simulation aus.")
        print(f"📵 (Simulation) SMS an {to}: {message}")
        return (
            jsonify(
                {"status": "mock", "message": f"(Simulation) SMS an {to}: {message}"}
            ),
            200,
        )

    try:
        print("📡 Versende SMS über Twilio …")
        sms = twilio_client.messages.create(to=to, from_=from_number, body=message)
        print("✅ SMS erfolgreich gesendet:", sms.sid)
        return jsonify({"status": "success", "sid": sms.sid}), 200

    except Exception as e:
        print("❌ Fehler beim Senden der SMS:", str(e))
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/parse-phone", methods=["POST"])
def parse_phone():
    """
    Erwartet:  {"last_user_message": "Meine Nummer ist 0176 1234567"}
    Antwort:   {"status": "ok", "mobile": "+491761234567"}
               {"status": "error"}                     (wenn nichts gefunden)
    """
    data = request.json or {}
    text = data.get("last_user_message", "")

    # 1️⃣  Ursprüngliche User‑Eingabe loggen
    print(f"🗣️  User‑Text: {text}")

    # 2️⃣  Regex (simple DE‑Handy‐Variante, Leer-/Bindestriche tolerant)
    match = re.search(r"(?:\+?49[ \-]?)?1[5-7]\d[ \-]?\d{6,}", text)
    if match:
        raw = match.group()  # z.B. "0176 1234567"
        digits = re.sub(r"\D", "", raw)  # nur Ziffern -> "01761234567"

        # 3️⃣  Ländervorwahl bereinigen
        if digits.startswith("0"):
            digits = digits[1:]  # führende 0 weg
        if not digits.startswith("49"):
            digits = "49" + digits  # ggf. 49 ergänzen

        mobile = f"+{digits}"
        # 4️⃣  🚀  Hier dein gewünschtes Print‑Statement
        print(f"📲 Erkannte Mobilnummer: {mobile}")

        return jsonify({"status": "ok", "mobile": mobile}), 200

    # ---  Kein Treffer ----------------------------------------------------
    print("🚫  Keine gültige Mobilnummer erkannt")
    return jsonify({"status": "error"}), 200


@app.route("/health", methods=["GET"])
def health_check():
    return "OK", 200


if __name__ == "__main__":
    print("Server wird gestartet ....")
    app.run(host="0.0.0.0", port=10000)
