from flask import Flask, request, jsonify
from twilio.rest import Client
from dotenv import load_dotenv
import os
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import traceback

load_dotenv()
app = Flask(__name__)

# Twilio-Konfiguration
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
from_number = os.getenv("TWILIO_FROM_NUMBER")
client = Client(account_sid, auth_token)

# Google Sheet-Konfiguration
google_sheet_id = os.getenv("GOOGLE_SHEET_ID")
credentials_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")

print("📄 SHEET ID:", google_sheet_id)
print("🔑 JSON FILE:", credentials_file)


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
    caller = data.get("caller")
    transcript = data.get("transcript")
    today = datetime.now().strftime("%d.%m.%Y")

    if not caller or not transcript:
        return (
            jsonify({"status": "error", "message": "Missing 'caller' or 'transcript'"}),
            400,
        )

    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            credentials_file, scope
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_key(google_sheet_id).sheet1

        print("🔍 Verfügbare Sheets:", client.open_by_key(google_sheet_id).worksheets())

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
        print("❌ Allgemeiner Fehler:", type(e), "-", str(e))
        print("❌ Fehler beim Speichern im Google Sheet:", e)
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    print("Server wird gestartet...")
    app.run(debug=True)
