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

    if not account_sid or not auth_token or not from_number:
        print("⚠️  Twilio-Daten fehlen – SMS wird nicht versendet.")
        return (
            jsonify(
                {"status": "mock", "message": f"(Simulation) SMS an {to}: {message}"}
            ),
            200,
        )

    if not to or not message:
        return jsonify({"status": "error", "message": "Missing 'to' or 'message'"}), 400

    try:
        sms = client.messages.create(to=to, from_=from_number, body=message)
        return jsonify({"status": "success", "sid": sms.sid}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/save-transcript", methods=["POST"])
def save_transcript():
    data = request.json
    print("📥 Eingehender Payload von Retell:", data)


def save_transcript():
    data = request.json

    # Nur reagieren, wenn es ein Post-Call-Event ist
    if data.get("event") != "post_call_data":
        return (
            jsonify({"status": "ignored", "message": "Not a post_call_data event"}),
            200,
        )

    transcript = data.get("transcript")
    if not transcript:
        return jsonify({"status": "error", "message": "Missing transcript"}), 400

    caller = data.get("caller") or "Unbekannt"
    today = datetime.now().strftime("%d.%m.%Y")

    try:
        print("📞 Post-Call Event empfangen")
        print("👤 Caller:", caller)
        print("📝 Transcript:", transcript[:80], "...")

        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(google_sheet_id).sheet1

        sheet.append_row([today, caller, transcript])
        return jsonify({"status": "success", "message": "Transcript gespeichert"}), 200

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
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/health", methods=["GET"])
def health_check():
    return "OK", 200


if __name__ == "__main__":
    print("Server wird gestartet ....")
    app.run(host="0.0.0.0", port=10000)
