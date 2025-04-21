from flask import Flask, request, jsonify
from twilio.rest import Client
from dotenv import load_dotenv
import os
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import traceback
import json

load_dotenv()
app = Flask(__name__)

# Twilio-Konfiguration
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
from_number = os.getenv("TWILIO_FROM_NUMBER")
client = Client(account_sid, auth_token)

# Google Sheet-Konfiguration
google_sheet_id = os.getenv("GOOGLE_SHEET_ID")
credentials_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
creds_dict = json.loads(credentials_json)


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
        sms = client.messages.create(to=to, from_=from_number, body=message)
        print("✅ SMS erfolgreich gesendet:", sms.sid)
        return jsonify({"status": "success", "sid": sms.sid}), 200

    except Exception as e:
        print("❌ Fehler beim Senden der SMS:", str(e))
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/save-transcript", methods=["POST"])
def save_transcript():
    data = request.json

    # print("📥 Eingehender Payload von Retell:", data)

    if data.get("event") != "call_ended":
        return jsonify({"status": "ignored", "message": "Kein call_ended Event"}), 200

    call_data = data.get("call", {})
    transcript = call_data.get("transcript", "")
    call_id = call_data.get("call_id", "unknown")
    now = datetime.now()
    datum = now.strftime("%Y-%m-%d")
    zeit = now.strftime("%H:%M")

    if not transcript:
        return jsonify({"status": "error", "message": "Transcript fehlt"}), 400

    try:
        print("📞 Call beendet – speichere Transkript")
        print("▶️ Daten für Google Sheet:", datum, zeit, call_id, transcript[:80])

        # Authentifizierung
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(google_sheet_id).sheet1

        # Schreibe Zeile
        sheet.append_row([datum, zeit, call_id, transcript])
        print("✅ Transkript gespeichert")

        return jsonify({"status": "success"}), 200

    except gspread.exceptions.APIError as e:
        error_str = str(e)
        print("❌ Google Sheets API Fehler:", error_str)

        if "403" in error_str:
            return (
                jsonify(
                    {
                        "status": "forbidden",
                        "message": "Zugriff verweigert – bitte Freigabe des Sheets für den Service Account prüfen.",
                    }
                ),
                403,
            )
        elif "404" in error_str:
            return (
                jsonify(
                    {
                        "status": "not_found",
                        "message": "Sheet nicht gefunden – bitte die SHEET ID prüfen.",
                    }
                ),
                404,
            )
        else:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Unbekannter Google Sheets API Fehler",
                    }
                ),
                500,
            )
    except Exception as e:
        print("❌ Allgemeiner Fehler:", type(e), "-", str(e))
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/health", methods=["GET"])
def health_check():
    return "OK", 200


if __name__ == "__main__":
    print("Server wird gestartet ....")
    app.run(host="0.0.0.0", port=10000)
