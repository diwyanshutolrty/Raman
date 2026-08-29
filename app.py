import os
import sqlite3
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime
from dotenv import load_dotenv
import webbrowser
import threading

# Load environment variables
load_dotenv()

# --- Twilio SMS ---
try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    print("WARNING: twilio not installed. Run: pip install twilio")

app = Flask(__name__, static_folder='.')
CORS(app) # Enable CORS for frontend connectivity

@app.route('/')
def index():
    return send_from_directory('.', 'chatbot.html')

# --- CONFIGURATION ---
# ============================================================
# SMS CONFIGURATION
FAST2SMS_API_KEY = os.getenv("FAST2SMS_API_KEY", "YOUR_FAST2SMS_API_KEY")

TWILIO_ACCOUNT_SID  = os.getenv("TWILIO_ACCOUNT_SID", "YOUR_TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN   = os.getenv("TWILIO_AUTH_TOKEN", "YOUR_TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER  = os.getenv("TWILIO_FROM_NUMBER", "YOUR_TWILIO_PHONE_NUMBER")

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "YOUR_OPENWEATHER_API_KEY")
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")

# --- ADMIN NOTIFICATION ---
# This number will be notified whenever ANYONE registers or logs in.
ADMIN_PHONE = "9153120416"

# --- HELPER: Send SMS ---
def send_sms(name, phone):
    """
    Tries Fast2SMS first (free, India), then Twilio.
    Returns a status string.
    """
    message_body = f"Welcome {name}! You have successfully registered on the AI Voice Assistant platform. Your session is now active."

    # --- OPTION 1: Fast2SMS (Free, Best for India) ---
    if FAST2SMS_API_KEY and "YOUR_FAST2SMS" not in FAST2SMS_API_KEY:
        try:
            # Strip everything except digits and only keep last 10 digits for Fast2SMS
            clean_phone = ''.join(filter(str.isdigit, phone))[-10:]
            url = "https://www.fast2sms.com/dev/bulkV2"
            headers = {"authorization": FAST2SMS_API_KEY}
            payload = {
                "route": "q",
                "message": message_body,
                "language": "english",
                "flash": 0,
                "numbers": clean_phone
            }
            response = requests.post(url, headers=headers, data=payload)
            result = response.json()
            print(f"Fast2SMS Response: {result}")
            if result.get("return") == True:
                return f"Delivered via Fast2SMS"
            else:
                return f"Fast2SMS Error: {result.get('message', 'Unknown error')}"
        except Exception as e:
            print(f"Fast2SMS Error: {e}")
            # Fall through to Twilio if Fast2SMS fails

    # --- OPTION 2: Twilio (Fallback) ---
    if TWILIO_AVAILABLE and TWILIO_ACCOUNT_SID and "YOUR_TWILIO" not in TWILIO_ACCOUNT_SID:
        try:
            # Ensure number starts with + for Twilio
            formatted_phone = phone.strip()
            if not formatted_phone.startswith('+'):
                # Default to +91 if no country code provided and it looks like an Indian number
                if len(formatted_phone) == 10:
                    formatted_phone = "+91" + formatted_phone
                else:
                    # Try adding + if it's already a full number without it
                    formatted_phone = "+" + formatted_phone

            twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            msg = twilio_client.messages.create(
                body=message_body,
                from_=TWILIO_FROM_NUMBER,
                to=formatted_phone
            )
            return f"Delivered via Twilio (SID: {msg.sid})"
        except Exception as e:
            print(f"Twilio Error: {e}")
            return f"Twilio Failed: {e}"

    # --- No real API configured ---
    print(f"NOTIFY (Simulated): Welcome SMS would be sent to {phone}")
    
    # Always notify the Admin as well (simulated or real)
    if phone != ADMIN_PHONE:
        print(f"NOTIFY (Simulated): Admin alert sent to {ADMIN_PHONE} regarding {phone}'s login.")
        
    return "Simulated — Add Fast2SMS or Twilio API key to send real SMS"

# --- DATABASE SETUP ---
DB_NAME = "assistant_data.db"

def init_db():
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute('PRAGMA journal_mode=WAL;') # Enable Write-Ahead Logging
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT UNIQUE NOT NULL,
                registration_date TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT,
                command TEXT,
                timestamp TEXT
            )
        ''')
        conn.commit()
    except Exception as e:
        print(f"Database Init Error: {e}")
    finally:
        if conn: conn.close()

init_db()

# --- API ENDPOINTS ---

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400

        name = data.get('name')
        phone = data.get('phone')

        if not name or not phone:
            return jsonify({"error": "Name and phone are required"}), 400

        conn = None
        try:
            conn = sqlite3.connect(DB_NAME, timeout=10)
            conn.execute('PRAGMA journal_mode=WAL;')
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (name, phone, registration_date) VALUES (?, ?, ?)",
                           (name, phone, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            is_new_user = True
        except sqlite3.IntegrityError:
            is_new_user = False
            # If already registered, we can fetch the name from the DB to be accurate
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM users WHERE phone = ?", (phone,))
                row = cursor.fetchone()
                if row: name = row[0]
        finally:
            if conn: conn.close()

        # Always send SMS notification on login/registration attempt
        sms_status = send_sms(name, phone)
        
        # If the logging-in user is NOT the admin, also notify the admin specifically
        if phone != ADMIN_PHONE:
            admin_alert_body = f"ALERT: User {name} ({phone}) has just logged into the AI Assistant."
            # We reuse send_sms logic or call it directly for admin
            send_sms("Admin", ADMIN_PHONE) # This will send the standard welcome to admin
            print(f"Admin {ADMIN_PHONE} notified about {name}'s login.")

        print(f"SMS Status for {phone}: {sms_status}")

        return jsonify({
            "message": "Registration successful",
            "sms_status": sms_status,
            "user": {"name": name, "phone": phone}
        })
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Registration Error:\n{error_trace}")
        return jsonify({"error": str(e), "traceback": error_trace}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    if not data:
        return jsonify({"response": "Error: Invalid request format."}), 400

    message = data.get('message')
    phone = data.get('phone')

    if not message:
        return jsonify({"error": "Message is required"}), 400

    # Log activity
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute('PRAGMA journal_mode=WAL;')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO activity_log (phone, command, timestamp) VALUES (?, ?, ?)",
                       (phone, message, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    except Exception as e:
        print(f"Activity Log Error: {e}")
    finally:
        if conn: conn.close()

    # Call AI API (Real AI integration)
    try:
        if "YOUR_GEMINI_API_KEY" in GEMINI_API_KEY:
            return jsonify({"response": f"AI Backend: I received your message '{message}'. (Please set a real Gemini API key in app.py to get intelligent responses)"})

        # Dynamic URL construction with the current API key
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        
        payload = {
            "contents": [{"parts": [{"text": message}]}]
        }
        response = requests.post(api_url, json=payload)
        ai_data = response.json()
        
        if response.status_code != 200:
            error_msg = ai_data.get('error', {}).get('message', 'Unknown AI API Error')
            return jsonify({"response": f"AI API Error: {error_msg}"})

        ai_response = ai_data['candidates'][0]['content']['parts'][0]['text']
        return jsonify({"response": ai_response})
    except Exception as e:
        print(f"Chat Error: {e}")
        return jsonify({"response": "I'm having trouble connecting to my brain right now. Please try again later."}), 500

@app.route('/api/weather', methods=['GET'])
def get_weather():
    city = request.args.get('city')
    if not city:
        return jsonify({"error": "City is required"}), 400

    try:
        if "YOUR_OPENWEATHER_API_KEY" in OPENWEATHER_API_KEY:
            return jsonify({"weather": f"Weather for {city} requires a real OpenWeather API key in app.py."})

        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
        response = requests.get(url)
        weather_data = response.json()
        
        if response.status_code == 200:
            temp = weather_data['main']['temp']
            desc = weather_data['weather'][0]['description']
            return jsonify({"weather": f"It's currently {temp}°C in {city} with {desc}."})
        else:
            return jsonify({"weather": f"I couldn't find weather info for {city}."})
    except Exception as e:
        return jsonify({"weather": "Weather service is currently unavailable."}), 500

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    phone = request.args.get('phone')
    if not phone:
        return jsonify({"error": "Phone is required"}), 400

    conn = None
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute('PRAGMA journal_mode=WAL;')
        cursor = conn.cursor()
        cursor.execute("SELECT command, timestamp FROM activity_log WHERE phone = ? ORDER BY id DESC LIMIT 10", (phone,))
        rows = cursor.fetchall()
        history = [{"command": r[0], "time": r[1]} for r in rows]
        return jsonify({"history": history})
    except Exception as e:
        print(f"Dashboard Error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    # Automatically open the browser after a short delay
    def open_browser():
        import time
        time.sleep(2)
        webbrowser.open("http://127.0.0.1:5005")
    
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Changed to 5005 to avoid port 5000 conflicts
    app.run(debug=True, port=5005, host='0.0.0.0')
