Starten mit: 
export FLASK_APP=app.py
flask run

Dann erreichst du deinen Webhook unter:
http://localhost:5000/send-sms

# SMS VoiceBot Webhook (Retell + Google Sheets)

## Setup

- Flask-Server mit /send-sms und /save-transcript Endpunkten
- Daten werden in ein Google Sheet gespeichert
- SMS-Versand via Twilio

## Deployment
über Render