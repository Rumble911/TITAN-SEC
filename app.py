import os
import re
import secrets
import string
import hashlib
import base64
import io
import json
import psycopg2
import psycopg2.extras
import psycopg2.errors
import pyotp  # type: ignore
import qrcode  # type: ignore
import datetime
import time
import tempfile
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, render_template_string, send_file, session, Response  # type: ignore
from cryptography.fernet import Fernet  # type: ignore
from cryptography.hazmat.primitives import hashes  # type: ignore
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC  # type: ignore
import requests  # type: ignore
from functools import lru_cache
from PIL import Image  # type: ignore
from pypdf import PdfReader, PdfWriter  # type: ignore
import random
import uuid
import socket
import concurrent.futures
import subprocess
import threading
import wave
import psutil  # type: ignore
import exifread  # type: ignore
from cryptography.hazmat.primitives.asymmetric import rsa  # type: ignore
from cryptography.hazmat.primitives import serialization, hashes  # type: ignore
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes  # type: ignore
import urllib.parse
import smtplib
from email.mime.text import MIMEText
import urllib.request
import json as _json

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # حد أقصى للملفات 16 ميجابايت
app.secret_key = os.environ.get('SECRET_KEY', 'TITAN_ULTRA_SECRET_KEY_2025')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True   # HTTPS only on Render
app.config['SESSION_COOKIE_NAME'] = 'titan_session'
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(hours=12)

# --- قاعدة بيانات المستخدمين (SQLite) ---
# PostgreSQL - connection via DATABASE_URL env var

# --- إعدادات الإيميل (Brevo SMTP) ---
BREVO_SMTP_SERVER = 'smtp-relay.brevo.com'
BREVO_SMTP_PORT = 587
BREVO_SMTP_LOGIN = os.environ.get('BREVO_SMTP_LOGIN', '')
BREVO_SMTP_KEY = os.environ.get('BREVO_SMTP_KEY', '')
SENDER_EMAIL = 'noreply@titan-cyber.me'
SENDER_NAME = 'TITAN'
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "abdallahalqam4040@gmail.com")

# --- DigitalOcean AI Agent Config ---
DO_AI_ENDPOINT = os.environ.get('DO_AI_ENDPOINT', 'https://y4l7lnqc5wj5frtdqugl6dqs.agents.do-ai.run')
DO_AI_KEY = os.environ.get('DO_AI_KEY', '')

_dash_metrics_lock = threading.Lock()
_dash_prev_net = None
_dash_prev_ts = 0.0
_dash_prev_disk_io = None
_dash_prev_disk_io_ts = 0.0
_dash_cpu_primed = False
_dash_public_ip = 'غير متاح'
_dash_public_ip_ts = 0.0


def _dash_local_ip():
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(('8.8.8.8', 80))
        return sock.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return 'غير متاح'
    finally:
        try:
            if sock:
                sock.close()
        except Exception:
            pass


def _dash_public_ip_cached():
    global _dash_public_ip, _dash_public_ip_ts
    now = time.time()
    if _dash_public_ip != 'غير متاح' and (now - _dash_public_ip_ts) < 60:
        return _dash_public_ip
    try:
        pub_ip_data = requests.get('https://api.ipify.org?format=json', timeout=2).json()
        _dash_public_ip = pub_ip_data.get('ip', 'غير متاح')
        _dash_public_ip_ts = now
    except Exception:
        pass
    return _dash_public_ip

def _call_do_ai(message: str) -> str:
    """استدعاء TITAN AI عبر DigitalOcean Agent"""
    headers = {
        'Authorization': f'Bearer {DO_AI_KEY}',
        'Content-Type': 'application/json',
    }
    payload = {
        "messages": [{"role": "user", "content": message}]
    }
    res = requests.post(
        f"{DO_AI_ENDPOINT}/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=30
    )
    res.raise_for_status()
    data = res.json()
    return data['choices'][0]['message']['content']


def _resend_send(to_email, subject, body):
    """إرسال إيميل عبر Brevo SMTP"""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
        msg['To'] = to_email
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        with smtplib.SMTP(BREVO_SMTP_SERVER, BREVO_SMTP_PORT) as server:
            server.starttls()
            server.login(BREVO_SMTP_LOGIN, BREVO_SMTP_KEY)
            server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        print(f"[Brevo] Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"[Brevo] Error: {e}")
        return False

def send_otp_email(target_email, otp_code):
    """وظيفة إرسال كود التحقق عبر SendGrid"""
    body = f"""مرحباً بك في TITAN SEC.
كود التحقق الخاص بك هو: {otp_code}
يرجى إدخاله في الموقع لإتمام عملية التسجيل."""
    return _resend_send(target_email, "TITAN", body)

def _send_email_async(subject, body, to=None):
    """إرسال إيميل في الخلفية (بدون تأخير الاستجابة)"""
    target = to or ADMIN_EMAIL
    def _worker():
        try:
            _resend_send(target, subject, body)
        except Exception as e:
            print(f"[TITAN Email] {e}")
    threading.Thread(target=_worker, daemon=True).start()


def send_login_alert_email(username, ip, user_agent):
    """تنبيه لكل تسجيل دخول ناجح"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = f"""TITAN Security Alert - Login Notification

تم تسجيل دخول الى النظام:
- المستخدم: {username}
- عنوان IP: {ip}
- المتصفح: {user_agent[:120]}
- الوقت: {now}

"""
    _send_email_async(f"TITAN - {username}", body)


def send_new_device_alert(username, ip, user_agent, email):
    """تنبيه الدخول من جهاز جديد"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = f"""TITAN - تنبيه دخول من جهاز جديد

مرحبا {username}،
رصد دخول من متصفح/جهاز جديد:
- IP: {ip}
- المتصفح: {user_agent[:120]}
- الوقت: {now}

اذا لم تكن انت، غير كلمة السر فورا.
"""
    _send_email_async(f"TITAN - {username}", body, to=email)
    _send_email_async(f"TITAN - {username}", body)


def send_geo_fence_alert(username, ip, old_country, new_country, email):
    """تنبيه دخول من دولة مختلفة"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = f"""TITAN - تنبيه دخول مشبوه!

مرحبا {username}،
دخول من دولة مختلفة:
- الدولة المعتادة: {old_country}
- الدولة الجديدة: {new_country}
- IP: {ip}
- الوقت: {now}
"""
    _send_email_async(f"TITAN - {username}", body, to=email)
    _send_email_async(f"TITAN - {username}", body)


def send_canary_alert(ip, user_agent):
    """تنبيه عند وصول أي شخص لملف الكناري honeypot"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = f"""TITAN HONEYPOT TRIGGERED!

شخص حاول الوصول لملف passwords.txt السري!
- IP: {ip}
- المتصفح: {user_agent[:150]}
- الوقت: {now}
"""
    _send_email_async("TITAN", body)



def get_db_conn():
    import os
    db_url = os.environ.get('DATABASE_URL', '')
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    return conn

def init_db():

    import os
    db_url = os.environ.get('DATABASE_URL', '')
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT DEFAULT NULL,
            is_verified INTEGER DEFAULT 0,
            otp_code TEXT DEFAULT NULL,
            vault_password_hash TEXT DEFAULT NULL,
            created_at TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0
        )
    ''')
    # Support upgrading existing DBs — add new columns safely
    conn.commit()  # commit CREATE TABLE before migrations
    for col_def in [
        "ALTER TABLE users ADD COLUMN vault_password_hash TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN email TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN otp_code TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN failed_attempts INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN lockout_until TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN last_user_agent TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN last_login_ip TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN last_login_at TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN last_country TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN vault_otp_code TEXT DEFAULT NULL",
        # --- تحديث جدول الجلسات (Migration) ---
        "ALTER TABLE active_sessions ADD COLUMN token TEXT",
        "ALTER TABLE active_sessions ADD COLUMN user_agent TEXT DEFAULT ''",
        "ALTER TABLE active_sessions ADD COLUMN ip TEXT DEFAULT ''",
        "ALTER TABLE active_sessions ADD COLUMN country TEXT DEFAULT ''",
        "ALTER TABLE active_sessions ADD COLUMN created_at TEXT",
    ]:
        try:
            c.execute(col_def)
            conn.commit()
        except Exception:
            conn.rollback()  # PostgreSQL requires rollback after any error

    # --- جدول سجلات الأمان (Security Logs) ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS security_logs (
            id SERIAL PRIMARY KEY,
            time TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT DEFAULT '',
            ip TEXT DEFAULT '',
            username TEXT DEFAULT ''
        )
    ''')

    # --- جدول الجلسات النشطة (Active Sessions) ---
    c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='active_sessions' AND column_name='session_token'")
    if c.fetchone():
         c.execute("DROP TABLE active_sessions")
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS active_sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            user_agent TEXT DEFAULT '',
            ip TEXT DEFAULT '',
            country TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    ''')

    # --- جدول القبو الزمني (Time-Locked Vault) ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS vault_timelocked (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            enc_data BYTEA NOT NULL,
            unlock_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')

    # --- جدول الكناري (Canary Log) ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS canary_log (
            id SERIAL PRIMARY KEY,
            time TEXT NOT NULL,
            ip TEXT DEFAULT '',
            user_agent TEXT DEFAULT ''
        )
    ''')

    # --- جدول Integrity Baseline ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS integrity_baseline (
            id SERIAL PRIMARY KEY,
            file_path TEXT NOT NULL,
            hash TEXT NOT NULL,
            set_at TEXT NOT NULL
        )
    ''')

    # --- Incident Response Cases ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS incident_cases (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            severity TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'open',
            description TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS incident_iocs (
            id SERIAL PRIMARY KEY,
            case_id INTEGER NOT NULL,
            ioc_type TEXT NOT NULL,
            ioc_value TEXT NOT NULL,
            risk_score INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS incident_evidence (
            id SERIAL PRIMARY KEY,
            case_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS entity_graph_cases (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            nodes_json TEXT NOT NULL,
            edges_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS hunting_alerts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            details TEXT DEFAULT '',
            severity TEXT DEFAULT 'medium',
            created_at TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS advanced_hidden_vaults (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            container_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS advanced_timelock_messages (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            enc_payload BYTEA NOT NULL,
            unlock_at TEXT NOT NULL,
            one_time_read INTEGER DEFAULT 1,
            is_used INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS advanced_keyring (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            key_name TEXT NOT NULL,
            key_material TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            rotated_from INTEGER DEFAULT NULL,
            created_at TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS support_tickets (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            category TEXT DEFAULT 'technical',
            priority TEXT DEFAULT 'normal',
            details TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            admin_note TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')

    conn.commit()
    
    # --- Create root user if not exists ---
    c.execute("SELECT id FROM users WHERE username = 'root'")
    if not c.fetchone():
        root_pass_hash = hash_password('Facebook123@@')
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO users (username, password_hash, is_verified, created_at, is_admin) VALUES (%s, %s, 1, %s, 1)",
                  ('root', root_pass_hash, now))
        conn.commit()
        print("[TITAN] Root user created.")

    conn.close()

    # --- بناء ملف الكناري (Honeypot) عند أول تشغيل ---
    _create_canary_file()
    # --- حساب Hash الأساسي (Integrity Baseline) ---
    _ensure_integrity_baseline()


def _create_canary_file():
    """يُنشئ ملف وهمي passwords.txt كفخ للمتسللين"""
    canary_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'passwords.txt')
    if not os.path.exists(canary_path):
        with open(canary_path, 'w', encoding='utf-8') as f:
            f.write("# TITAN System Credentials - DO NOT SHARE\n")
            f.write("admin:T1TAN_S3CR3T_2025!\n")
            f.write("root:P@ssw0rd123\n")
            f.write("dbuser:sql_vault_key_9x\n")


def _ensure_integrity_baseline():
    """يحسب Hash لملف app.py ويخزنه إذا لم يكن موجوداً"""
    app_path = os.path.abspath(__file__)
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT hash FROM integrity_baseline WHERE file_path = %s", (app_path,))
        row = c.fetchone()
        if not row:
            with open(app_path, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
            c.execute("INSERT INTO integrity_baseline (file_path, hash, set_at) VALUES (%s, %s, %s)",
                      (app_path, file_hash, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
    except Exception as e:
        print(f"[TITAN] Integrity baseline error: {e}")
    finally:
        if conn:
            conn.close()

def get_vault_file(user_id: int) -> str:
    """Returns per-user vault file path."""
    return f'vault_user_{user_id}.titan'

def get_vault_recovery_file(user_id: int) -> str:
    """Returns per-user vault recovery file path."""
    return f'vault_recovery_user_{user_id}.json'


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    pw_hash = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{pw_hash}"

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, pw_hash = stored_hash.split(':')
        return hashlib.sha256((salt + password).encode()).hexdigest() == pw_hash
    except Exception:
        return False



# --- نظام سجل النشاط الأمني (Audit Log) ---
AUDIT_LOGS = []
BURN_NOTES = {}


def add_audit_log(action, details="", ip="", username=""):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    event = {"time": now, "action": action, "details": details, "ip": ip, "username": username}
    AUDIT_LOGS.insert(0, event)
    if len(AUDIT_LOGS) > 200: AUDIT_LOGS.pop()
    # Persist to DB
    conn = None
    try:
        conn = get_db_conn()
        _c = conn.cursor()
        _c.execute("INSERT INTO security_logs (time, action, details, ip, username) VALUES (%s,%s,%s,%s,%s)",
                     (now, action, details, ip, username))
        conn.commit()
    except Exception as e:
        print(f"[TITAN] Audit log DB error: {e}")
    finally:
        if conn:
            conn.close()

# --- المنطق البرمجي: تشفير وفك تشفير ---

def derive_key(password: str, salt: bytes) -> bytes:
    """اشتقاق مفتاح تشفير آمن من كلمة سر"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

def derive_raw_key(password: str, salt: bytes) -> bytes:
    """اشتقاق مفتاح خام 32 بايت (بدون base64) لـ ChaCha20"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return kdf.derive(password.encode())

def encrypt_data(data: bytes, password: str) -> bytes:
    salt = os.urandom(16)
    key = derive_key(password, salt)
    f = Fernet(key)
    encrypted_data = f.encrypt(data)
    # ندمج الملح (salt) مع البيانات المشفرة لنتمكن من فكها لاحقاً
    return salt + encrypted_data

def decrypt_data(encrypted_content: bytes, password: str) -> bytes:
    try:
        salt = encrypted_content[:16]  # type: ignore
        data = encrypted_content[16:]  # type: ignore
        key = derive_key(password, salt)
        f = Fernet(key)
        return f.decrypt(data)
    except Exception:
        raise ValueError("كلمة السر خاطئة أو الملف معطوب")

# --- ميزات الخصوصية المتقدمة (Privacy & Steganography) ---

def remove_image_metadata(img_bytes: bytes) -> bytes:
    """إزالة كافة الميتابيانات عن طريق إعادة حفظ الصورة بدون EXIF"""
    img = Image.open(io.BytesIO(img_bytes))
    data = list(img.getdata())
    img_no_meta = Image.new(img.mode, img.size)
    img_no_meta.putdata(data)
    
    out = io.BytesIO()
    # نحافظ على التنسيق الأصلي إذا أمكن أو نحول لـ PNG للسلامة
    fmt = img.format if img.format else "PNG"
    img_no_meta.save(out, format=fmt)
    return out.getvalue()

def lsb_encode(img_bytes: bytes, secret_data: str) -> bytes:
    """إخفاء نص في بيانات الصورة (Least Significant Bit)"""
    img = Image.open(io.BytesIO(img_bytes)).convert('RGBA')
    width, height = img.size
    
    # تحويل النص لـ UTF-8 ثم لـ Binary مع علامة نهاية
    binary_data = ''.join([format(b, "08b") for b in secret_data.encode('utf-8')]) + '1111111111111110'
    
    if len(binary_data) > width * height * 3:
        raise ValueError("البيانات كبيرة جداً بالنسبة لهذه الصورة!")
        
    pixels = img.load()
    if pixels is None:
        raise ValueError("تعذر الوصول إلى بيانات البكسلات في الصورة")
    data_idx = 0
    
    for y in range(height):
        for x in range(width):
            if data_idx < len(binary_data):
                r, g, b, a = pixels[x, y]  # type: ignore
                # تعديل R
                r = (r & ~1) | int(binary_data[data_idx])  # type: ignore
                data_idx += 1
                if data_idx < len(binary_data):
                    # تعديل G
                    g = (g & ~1) | int(binary_data[data_idx])  # type: ignore
                    data_idx += 1
                if data_idx < len(binary_data):
                    # تعديل B
                    b = (b & ~1) | int(binary_data[data_idx])  # type: ignore
                    data_idx += 1
                pixels[x, y] = (r, g, b, a)
            else:
                break
        if data_idx >= len(binary_data): break
        
    out = io.BytesIO()
    img.save(out, format="PNG") # PNG يحافظ على البكسلات بدقة
    return out.getvalue()

def lsb_decode(img_bytes: bytes) -> str:
    """استخراج النص المخفي من الصورة"""
    img = Image.open(io.BytesIO(img_bytes)).convert('RGBA')
    width, height = img.size
    pixels = img.load()
    if pixels is None:
        return "تعذر قراءة بكسلات الصورة."
    
    bits: list[int] = []
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]  # type: ignore
            bits.append(r & 1)  # type: ignore
            bits.append(g & 1)
            bits.append(b & 1)
    
    # Search for the end marker 1111111111111110 in the bitstream
    END_MARKER = [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0]
    for i in range(len(bits) - 15):
        if bits[i:i+16] == END_MARKER:  # type: ignore[misc]
            # All bits before this marker are our message
            data_bits: list[int] = bits[:i]  # type: ignore[misc]
            # Only take complete bytes
            num_bytes = len(data_bits) // 8
            if num_bytes == 0:
                return "لم يتم العثور على بيانات مخفية!"
            byte_data = bytes([int(''.join(str(b) for b in data_bits[j*8:(j+1)*8]), 2) for j in range(num_bytes)])
            try:
                return byte_data.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    return byte_data.decode('latin-1')
                except Exception:
                    return "فشل استخراج النص: الصورة لا تحتوي على بيانات مخفية بواسطة هذه الأداة."
                
    return "لم يتم العثور على بيانات مخفية في هذه الصورة!"


# --- استخبارات الصور (Image EXIF OSINT) ---
def extract_exif_data(img_bytes: bytes) -> dict:
    tags = exifread.process_file(io.BytesIO(img_bytes), details=False)
    extracted = {}
    important_tags = ['Image Make', 'Image Model', 'Image DateTime', 'Image Software', 'GPS GPSLatitude', 'GPS GPSLongitude']
    for tag in tags.keys():
        if any(imp in tag for imp in important_tags):
            extracted[tag] = str(tags[tag])
    return extracted if extracted else {"Info": "لا توجد أي بيانات وصفية مخفية (EXIF) في هذه الصورة."}

# --- فحص الإيميل عبر IPQualityScore API ---
def check_email_intelligence(email: str) -> dict:
    API_KEY = '1ZFJTNYsuxNXvJwdiETskE0DqpHJDIc4'
    url = f'https://ipqualityscore.com/api/json/email/{API_KEY}/{email}'
    params = {
        'timeout': 7,
        'fast': 'false',
        'abuse_strictness': 0
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        return data
    except Exception as e:
        return {"success": False, "message": str(e), "error": str(e)}

# --- فحص رقم الهاتف عبر IPQualityScore API ---
def check_phone_intelligence(phone: str) -> dict:
    API_KEY = '1ZFJTNYsuxNXvJwdiETskE0DqpHJDIc4'
    # تنظيف وتجهيز رقم الهاتف
    phone_clean = urllib.parse.quote(phone.strip())
    url = f'https://www.ipqualityscore.com/api/json/phone/{API_KEY}/{phone_clean}'
    params = {}
        
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        return data
    except Exception as e:
        return {"success": False, "message": str(e), "error": str(e)}

# --- فحص الروابط المشبوهة عبر IPQualityScore API ---
def check_url_intelligence(target_url: str) -> dict:
    API_KEY = '1ZFJTNYsuxNXvJwdiETskE0DqpHJDIc4'
    url_clean = urllib.parse.quote(target_url.strip(), safe='')
    url = f'https://www.ipqualityscore.com/api/json/url/{API_KEY}/{url_clean}'
    params = {'fast': 'true', 'strictness': 0}
        
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        return data
    except Exception as e:
        return {"success": False, "message": str(e), "error": str(e)}

# --- فحص تسريب الإيميل وكلمة السر معاً عبر IPQualityScore API ---
def check_leaked_emailpass(email: str, password: str) -> dict:
    API_KEY = '1ZFJTNYsuxNXvJwdiETskE0DqpHJDIc4'
    url = f"https://www.ipqualityscore.com/api/json/leaked/emailpass/{API_KEY}"
    post_data = {
        "email": email,
        "password": password
    }
    
    try:
        response = requests.post(url, json=post_data, timeout=10)
        data = response.json()
        return data
    except Exception as e:
        return {"success": False, "message": str(e), "error": str(e)}

# --- جلب سجلات الاستخدام من IPQualityScore ---
def get_ipqs_requests_list(req_type: str, start_date: str) -> dict:
    API_KEY = '1ZFJTNYsuxNXvJwdiETskE0DqpHJDIc4'
    url = f'https://www.ipqualityscore.com/api/json/requests/{API_KEY}/list'
    params = {
        'type': req_type,
        'start_date': start_date
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        return data
    except Exception as e:
        return {"success": False, "message": str(e), "error": str(e)}

# --- إخفاء البيانات في الصوت (Audio Steganography) ---
def wave_lsb_encode(wav_bytes: bytes, secret_data: str, filename: str = "") -> bytes:
    """إخفاء نص في ملف صوتي (WAV LSB أو EOF للأنواع المضغوطة)."""
    try:
        # Marker for extraction
        marker = b'##TITAN_SECURE##'
        full_secret = secret_data.encode('utf-8') + marker

        lower_name = (filename or '').lower()
        eof_exts = ('.mp3', '.webm', '.ogg', '.m4a', '.aac')
        if lower_name.endswith(eof_exts):
            # EOF append mode for compressed formats and browser recordings
            return wav_bytes + marker + secret_data.encode('utf-8')

        # WAV Steganography: Modify frames
        try:
            with wave.open(io.BytesIO(wav_bytes), 'rb') as wav:
                params = wav.getparams()
                frames = bytearray(wav.readframes(wav.getnframes()))
        except Exception:
            # Fallback for unknown/unsupported container types
            return wav_bytes + marker + secret_data.encode('utf-8')

        # Convert to bitstream
        bits = ''.join(format(b, '08b') for b in full_secret)
        
        if len(bits) > len(frames):
            raise ValueError("النص كبير جداً بالنسبة لملف الصوت المحدد!")

        # Apply LSB
        for i, bit in enumerate(bits):
            frames[i] = (frames[i] & ~1) | int(bit)

        out = io.BytesIO()
        with wave.open(out, 'wb') as wav_out:
            wav_out.setparams(params)
            wav_out.writeframes(frames)
        
        return out.getvalue()
    except Exception as e:
        raise ValueError(f"فشل تشفير الصوت: {str(e)}")

def wave_lsb_decode(wav_bytes: bytes, filename: str = "") -> str:
    """استخراج النص المخفي من ملف صوتي (WAV LSB أو EOF)."""
    try:
        marker = b'##TITAN_SECURE##'

        lower_name = (filename or '').lower()
        eof_exts = ('.mp3', '.webm', '.ogg', '.m4a', '.aac')
        if lower_name.endswith(eof_exts):
            if marker in wav_bytes:
                return wav_bytes.split(marker)[-1].decode('utf-8', errors='ignore')
            return "لم يتم العثور على بيانات مخفية في الملف الصوتي."

        # WAV LSB Decode
        try:
            with wave.open(io.BytesIO(wav_bytes), 'rb') as wav:
                frames = bytearray(wav.readframes(wav.getnframes()))
        except Exception:
            # As a safe fallback, try EOF marker extraction
            if marker in wav_bytes:
                return wav_bytes.split(marker)[-1].decode('utf-8', errors='ignore')
            return "تعذر تحليل تنسيق الصوت أو لا توجد بيانات مخفية."

        bits = [str(f & 1) for f in frames]
        byte_list = []
        # Reconstruct bytes
        for i in range(0, len(bits), 8):
            if i + 8 > len(bits): break
            byte_val = int(''.join(bits[i:i+8]), 2)
            byte_list.append(byte_val)
        
        raw_result = bytes(byte_list)
        if marker in raw_result:
            return raw_result.split(marker)[0].decode('utf-8', errors='ignore')
        
        return "لم يتم العثور على بصمة نص مخفي في ملف الصوت."
    except Exception as e:
        return f"خطأ في تحليل البيانات: {str(e)}"


# --- إخفاء البيانات في الفيديو (Video Steganography) ---
def _save_temp_bytes(data: bytes, suffix: str) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data)
        return tmp.name
    finally:
        tmp.close()


def video_lsb_encode(video_bytes: bytes, secret_data: str) -> bytes:
    """إخفاء نص داخل فيديو عبر تعديل أقل بت مؤثر في قناة اللون الأزرق."""
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        raise ValueError("مكتبات الفيديو غير متاحة في الخادم")

    in_path = _save_temp_bytes(video_bytes, '.mp4')
    out_path = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4').name
    marker = b'##TITAN_VIDEO_END##'
    payload_bits = ''.join(format(b, '08b') for b in (secret_data.encode('utf-8') + marker))

    cap = cv2.VideoCapture(in_path)
    if not cap.isOpened():
        cap.release()
        os.remove(in_path)
        raise ValueError("تعذر قراءة ملف الفيديو")

    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    if width <= 0 or height <= 0 or frame_count <= 0:
        cap.release()
        os.remove(in_path)
        raise ValueError("تعذر تحليل خصائص الفيديو")

    capacity_bits = frame_count * width * height
    if len(payload_bits) > capacity_bits:
        cap.release()
        os.remove(in_path)
        raise ValueError("النص كبير جداً بالنسبة لسعة الفيديو")

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

    bit_index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if bit_index < len(payload_bits):
            blue_flat = frame[:, :, 0].reshape(-1)
            remaining = len(payload_bits) - bit_index
            n = min(remaining, blue_flat.size)
            bit_chunk = payload_bits[bit_index:bit_index + n]
            bits_np = np.fromiter((1 if c == '1' else 0 for c in bit_chunk), dtype=np.uint8, count=n)
            blue_flat[:n] = (blue_flat[:n] & 0xFE) | bits_np
            bit_index += n

        writer.write(frame)

    cap.release()
    writer.release()
    os.remove(in_path)

    if bit_index < len(payload_bits):
        if os.path.exists(out_path):
            os.remove(out_path)
        raise ValueError("تعذر إكمال عملية الإخفاء داخل الفيديو")

    try:
        with open(out_path, 'rb') as f:
            return f.read()
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)


def video_lsb_decode(video_bytes: bytes) -> str:
    """استخراج النص المخفي من الفيديو."""
    try:
        import cv2  # type: ignore
    except Exception:
        return "مكتبات الفيديو غير متاحة في الخادم"

    in_path = _save_temp_bytes(video_bytes, '.mp4')
    marker = b'##TITAN_VIDEO_END##'

    cap = cv2.VideoCapture(in_path)
    if not cap.isOpened():
        cap.release()
        os.remove(in_path)
        return "تعذر قراءة ملف الفيديو"

    decoded = bytearray()
    current_byte = 0
    bit_count = 0
    max_bytes = 1024 * 1024

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        blue_flat = frame[:, :, 0].reshape(-1)
        for val in blue_flat:
            current_byte = (current_byte << 1) | int(val & 1)
            bit_count += 1
            if bit_count == 8:
                decoded.append(current_byte)
                if len(decoded) >= len(marker) and decoded[-len(marker):] == marker:
                    cap.release()
                    os.remove(in_path)
                    payload = bytes(decoded[:-len(marker)])
                    try:
                        return payload.decode('utf-8')
                    except UnicodeDecodeError:
                        return payload.decode('latin-1', errors='ignore')

                if len(decoded) > max_bytes:
                    cap.release()
                    os.remove(in_path)
                    return "لم يتم العثور على بيانات مخفية داخل الفيديو"

                bit_count = 0
                current_byte = 0

    cap.release()
    os.remove(in_path)
    return "لم يتم العثور على بيانات مخفية داخل الفيديو"


def scan_video_clip(video_bytes: bytes, original_name: str = '') -> dict:
    """فحص سريع لخصائص الفيديو وتقدير السعة وإشارة وجود نص مخفي."""
    try:
        import cv2  # type: ignore
    except Exception:
        return {"success": False, "error": "مكتبات الفيديو غير متاحة"}

    in_path = _save_temp_bytes(video_bytes, '.mp4')
    cap = cv2.VideoCapture(in_path)
    if not cap.isOpened():
        cap.release()
        os.remove(in_path)
        return {"success": False, "error": "تعذر فتح ملف الفيديو"}

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = (frame_count / fps) if fps > 0 else 0.0
    cap.release()
    os.remove(in_path)

    capacity_bits = max(frame_count, 0) * max(width, 0) * max(height, 0)
    capacity_bytes = capacity_bits // 8
    hidden_probe = video_lsb_decode(video_bytes)
    has_hidden_payload = "لم يتم العثور" not in hidden_probe and "تعذر" not in hidden_probe

    return {
        "success": True,
        "filename": original_name,
        "fps": round(fps, 2),
        "width": width,
        "height": height,
        "frame_count": frame_count,
        "duration_seconds": round(duration, 2),
        "estimated_capacity_bytes": capacity_bytes,
        "has_hidden_payload": has_hidden_payload,
    }

# --- تنظيف ملفات PDF من الميتابيانات ---
def clean_pdf_metadata(pdf_bytes: bytes) -> bytes:
    """إزالة الميتابيانات وكافة المعلومات الوصفية من ملف PDF"""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        
        # إفراغ الميتابيانات تماماً
        writer.add_metadata({}) 
        
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception as e:
        raise ValueError(f"فشل تنظيف PDF: {str(e)}")


def extract_image_ocr_text(image_bytes: bytes, max_chars: int = 5000) -> tuple[str, str | None]:
    """Extract text from image using OCR. Returns (text, error)."""
    try:
        import pytesseract  # type: ignore
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return "", "OCR library missing"

    try:
        # Decode image safely then enhance contrast for better OCR quality.
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return "", "invalid image"

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(gray, 3)
        thr = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 35, 11)

        text = ""
        # Try Arabic+English first, then fallback to English.
        for lang in ("ara+eng", "eng"):
            try:
                candidate = pytesseract.image_to_string(thr, lang=lang, config='--psm 6').strip()
                if candidate:
                    text = candidate
                    break
            except Exception:
                continue

        if not text:
            return "", "no text detected"
        return text[:max_chars], None
    except Exception as e:
        return "", str(e)

# --- ميزات استخباراتية إضافية ---
def get_dns_leak_info() -> dict:
    """محاكاة فحص تسريب DNS"""
    return {
        "success": True,
        "leaked": False,
        "dns_servers": ["1.1.1.1 (Cloudflare)", "8.8.8.8 (Google)"],
        "isp": "TITAN Secure Relay"
    }

def get_shodan_intel(ip: str) -> dict:
    """محاكاة جلب بيانات Shodan لعنوان IP"""
    return {
        "success": True,
        "ip": ip,
        "ports": [80, 443, 21, 22] if random.random() > 0.5 else [80, 443],
        "vulnerabilities": ["CVE-2023-TITAN (Simulated)"] if random.random() > 0.8 else [],
        "last_scan": datetime.datetime.now().strftime("%Y-%m-%d")
    }

# --- فحص البرمجيات الخبيثة (Malware) عبر IPQualityScore API ---
def handle_malware_result(data) -> dict:
    if data.status_code != 200:
        return {"success": False, "message": f"Error: {data.status_code}", "error": f"Error: {data.status_code}"}
    
    try:
        res_json = data.json()
        if not isinstance(res_json, dict):
            return {"success": False, "message": "استجابة غير صالحة من الخدمة"}
        if res_json.get("status") != "pending":
            # إرجاع بيانات الفحص
            return res_json
            
        # إذا كان الفحص قيد الانتظار، ننتظر ثانية ونسأل مجدداً
        while True:
            time.sleep(1)
            update_url = res_json.get("update_url")
            if not update_url:
                break
            data = requests.post(update_url)
            return handle_malware_result(data)
        return {"success": False, "message": "انتهت مهلة انتظار نتيجة الفحص"}
    except Exception as e:
        return {"success": False, "message": "فشل تحليل استجابة الموقع", "error": str(e)}

def scan_malware_url(url: str) -> dict:
    API_KEY = '1ZFJTNYsuxNXvJwdiETskE0DqpHJDIc4'
    try:
        data = requests.post(f"https://www.ipqualityscore.com/api/json/malware/scan/{API_KEY}", data={'url': url})
        return handle_malware_result(data)
    except Exception as e:
        return {"success": False, "message": "فشل الاتصال بالخدمة", "error": str(e)}

def scan_malware_file(file_path: str) -> dict:
    API_KEY = '1ZFJTNYsuxNXvJwdiETskE0DqpHJDIc4'
    try:
        with open(file_path, "rb") as f:
            data = requests.post(f"https://www.ipqualityscore.com/api/json/malware/scan/{API_KEY}", files={'file': f})
        return handle_malware_result(data)
    except Exception as e:
        return {"success": False, "message": "فشل رفع الملف", "error": str(e)}

# --- فحص الأجهزة المتصلة بالشبكة المحلية (Network LAN Scanner) ---
def scan_local_network():
    devices = []
    seen_keys = set()
    local_ip = _dash_local_ip()

    def _safe_decode(raw: bytes) -> str:
        for enc in ('utf-8', 'cp1256', 'cp1252', 'latin1'):
            try:
                return raw.decode(enc)
            except Exception:
                continue
        return raw.decode('latin1', errors='ignore')

    def _classify_device(ip: str):
        icon = "💻"
        label = "جهاز مستخدم"
        if ip.endswith('.1'):
            icon = "🌐"
            label = "جهاز التوجيه"
        elif ip.endswith('.10') or ip.endswith('.20'):
            icon = "📱"
            label = "هاتف محمول"
        return icon, label

    def _reverse_dns(ip: str) -> str:
        try:
            name = socket.gethostbyaddr(ip)[0]
            return (name or '').strip()
        except Exception:
            return ''

    def _push_device(ip: str, mac: str, type_: str):
        if not ip:
            return
        if ip.startswith('224.') or ip.startswith('239.') or ip == '255.255.255.255':
            return

        norm_mac = (mac or '').replace('-', ':').upper()
        key = (ip, norm_mac)
        if key in seen_keys:
            return
        seen_keys.add(key)

        icon, label = _classify_device(ip)
        is_self = ip == local_ip
        if is_self:
            icon = "🛡️"
            label = "هذا جهازك"
        devices.append({
            "ip": ip,
            "mac": norm_mac or "غير متاح",
            "type": (type_ or 'dynamic').strip(),
            "icon": icon,
            "label": label,
            "hostname": _reverse_dns(ip),
            "is_self": is_self
        })

    try:
        cmd = "arp -a"
        output = _safe_decode(subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT))

        ip_re = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
        mac_re = re.compile(r'\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b')

        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            ip_m = ip_re.search(line)
            mac_m = mac_re.search(line)
            if ip_m and mac_m:
                type_guess = 'dynamic' if 'dynamic' in line.lower() else ('static' if 'static' in line.lower() else 'unknown')
                _push_device(ip_m.group(0), mac_m.group(0), type_guess)

        # Fallback for Linux/macOS-like environments where arp format differs.
        if not devices:
            try:
                neigh_out = _safe_decode(subprocess.check_output("ip neigh", shell=True, stderr=subprocess.STDOUT))
                for raw_line in neigh_out.splitlines():
                    line = raw_line.strip()
                    ip_m = ip_re.search(line)
                    mac_m = mac_re.search(line)
                    if ip_m and mac_m:
                        type_guess = 'reachable' if 'REACHABLE' in line.upper() else 'neighbor'
                        _push_device(ip_m.group(0), mac_m.group(0), type_guess)
            except Exception:
                pass

        devices.sort(key=lambda d: list(map(int, d["ip"].split('.'))))
        return {
            "success": True,
            "devices": devices,
            "count": len(devices),
            "local_ip": local_ip
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"فشل الفحص: {str(e)}",
            "devices": [],
            "count": 0
        }


def analyze_hash_indicator(hash_value: str) -> dict:
    clean = (hash_value or '').strip().lower()
    if not re.fullmatch(r'[a-f0-9]{32}|[a-f0-9]{40}|[a-f0-9]{64}', clean):
        return {
            "success": False,
            "error": "Hash format غير صالح. استخدم MD5/SHA1/SHA256 بصيغة hex."
        }

    hash_type = 'MD5' if len(clean) == 32 else ('SHA1' if len(clean) == 40 else 'SHA256')
    known_bad = {
        '44d88612fea8a8f36de82e1278abb02f': 'EICAR test malware (MD5)',
        '3395856ce81f2b7382dee72602f798b642f14140': 'EICAR test malware (SHA1)'
    }

    unique_chars = len(set(clean))
    entropy_hint = round(unique_chars / 16 * 8, 2)
    reputation = known_bad.get(clean, 'unknown')
    risk_score = 90 if clean in known_bad else 25

    return {
        "success": True,
        "hash": clean,
        "hash_type": hash_type,
        "length": len(clean),
        "entropy_hint": entropy_hint,
        "reputation": reputation,
        "risk_score": risk_score
    }


def check_username_presence(username: str) -> dict:
    u = (username or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9._-]{3,30}', u):
        return {
            "success": False,
            "error": "اسم المستخدم غير صالح. المسموح: أحرف/أرقام/._- وبطول 3-30."
        }

    platforms = {
        "github": f"https://github.com/{u}",
        "reddit": f"https://www.reddit.com/user/{u}",
        "instagram": f"https://www.instagram.com/{u}/",
        "x": f"https://x.com/{u}",
        "tiktok": f"https://www.tiktok.com/@{u}",
        "pinterest": f"https://www.pinterest.com/{u}/",
        "youtube": f"https://www.youtube.com/@{u}",
        "medium": f"https://medium.com/@{u}",
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    not_found_markers = [
        "page not found",
        "sorry, this page isn't available",
        "this account doesn't exist",
        "couldn't find that page",
        "doesn't exist"
    ]

    def _probe(item):
        platform, url = item
        try:
            r = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
            status = r.status_code
            body = (r.text or '').lower()
            if status == 404:
                exists = False
            elif status in (200, 301, 302):
                exists = not any(m in body for m in not_found_markers)
            else:
                exists = False
            return {
                "platform": platform,
                "url": url,
                "status_code": status,
                "exists": exists
            }
        except Exception as e:
            return {
                "platform": platform,
                "url": url,
                "status_code": 0,
                "exists": False,
                "error": str(e)
            }

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(_probe, platforms.items()))

    found = [r for r in rows if r.get("exists")]
    missing = [r for r in rows if not r.get("exists") and not r.get("error")]
    unknown = [r for r in rows if r.get("error")]

    return {
        "success": True,
        "username": u,
        "found_count": len(found),
        "found": found,
        "not_found": missing,
        "unknown": unknown,
        "checked_at": datetime.datetime.utcnow().isoformat() + 'Z'
    }


def build_link_analysis_graph(nodes: list[dict]) -> dict:
    clean_nodes = []
    for n in nodes:
        val = (n.get('value') or '').strip()
        typ = (n.get('type') or 'unknown').strip().lower()
        nid = (n.get('id') or str(uuid.uuid4())).strip()
        if val:
            clean_nodes.append({"id": nid, "type": typ, "value": val})

    edges = []
    for i, a in enumerate(clean_nodes):
        for b in clean_nodes[i+1:]:
            rel = None
            av = a['value'].lower()
            bv = b['value'].lower()
            if a['type'] == b['type'] and av == bv:
                rel = 'same-indicator'
            elif a['type'] == 'email' and b['type'] in ('domain', 'url') and av.split('@')[-1] in bv:
                rel = 'email-domain-match'
            elif b['type'] == 'email' and a['type'] in ('domain', 'url') and bv.split('@')[-1] in av:
                rel = 'email-domain-match'
            elif a['type'] == 'url' and b['type'] == 'domain' and b['value'].lower() in a['value'].lower():
                rel = 'url-hosts-domain'
            elif b['type'] == 'url' and a['type'] == 'domain' and a['value'].lower() in b['value'].lower():
                rel = 'url-hosts-domain'
            elif a['type'] == 'username' and b['type'] == 'email' and a['value'].lower() in b['value'].lower():
                rel = 'username-appears-in-email'
            elif b['type'] == 'username' and a['type'] == 'email' and b['value'].lower() in a['value'].lower():
                rel = 'username-appears-in-email'

            if rel:
                edges.append({
                    "source": a['id'],
                    "target": b['id'],
                    "source_value": a['value'],
                    "target_value": b['value'],
                    "relation": rel
                })

    return {"nodes": clean_nodes, "edges": edges}


def generate_typosquatting_variants(domain: str) -> list[str]:
    d = (domain or '').strip().lower()
    if '.' not in d:
        return []
    name, ext = d.rsplit('.', 1)
    variants = set()
    if len(name) > 2:
        variants.add(name[:-1] + '.' + ext)
        variants.add(name[1:] + '.' + ext)
        variants.add(name[0] + name[0] + name[1:] + '.' + ext)
    variants.add(name.replace('o', '0') + '.' + ext)
    variants.add(name.replace('l', '1') + '.' + ext)
    variants.add(name.replace('e', '3') + '.' + ext)
    variants.add(name + '-secure.' + ext)
    variants.add(name + '-login.' + ext)
    return sorted(v for v in variants if v != d)[:25]


def create_social_defense_scenario(scenario_type: str) -> dict:
    scenarios = {
        'phishing_email': {
            'scenario': 'تلقيت ايميل عاجل يطلب تحديث كلمة السر عبر رابط خارجي مع تهديد بتعطيل الحساب خلال ساعة.',
            'red_flags': ['Urgency language', 'External lookalike domain', 'Mismatched sender display name'],
            'defense_actions': ['Do not click link', 'Verify sender domain', 'Open service manually from trusted URL', 'Report to security team']
        },
        'vishing_call': {
            'scenario': 'متصل يدعي انه من الدعم الفني ويطلب رمز OTP للتحقق من هويتك.',
            'red_flags': ['Requesting OTP', 'Pressure tactics', 'Unverified caller ID'],
            'defense_actions': ['Never share OTP', 'Hang up and call official support number', 'Document call details']
        },
        'pretexting': {
            'scenario': 'شخص يرسل رسالة باسم المدير ويطلب تحويل بيانات حساسة فوراً بدون المرور بالاجراءات.',
            'red_flags': ['Authority impersonation', 'Policy bypass request', 'Out-of-band urgency'],
            'defense_actions': ['Enforce approval process', 'Verify request through second channel', 'Escalate to manager']
        },
        'baiting_usb': {
            'scenario': 'تم العثور على USB مجهول قرب المكتب مكتوب عليه Payroll/Q4.',
            'red_flags': ['Unknown removable media', 'Curiosity bait label', 'No chain-of-custody'],
            'defense_actions': ['Do not plug in', 'Submit device to IT/SOC', 'Scan in isolated forensic environment only']
        }
    }
    return scenarios.get(scenario_type, scenarios['phishing_email'])


def split_secret_shares(secret_text: str, n: int = 5, k: int = 3) -> list[str]:
    if k < 2 or n < k:
        raise ValueError("Invalid n/k values")
    data = secret_text.encode('utf-8')
    prime = 257
    shares: list[dict] = [{"x": i + 1, "ys": []} for i in range(n)]
    for byte_val in data:
        coeffs = [byte_val] + [secrets.randbelow(prime) for _ in range(k - 1)]
        for s in shares:
            x = s["x"]
            y = 0
            for power, coeff in enumerate(coeffs):
                y = (y + coeff * pow(x, power, prime)) % prime
            s["ys"].append(y)
    encoded = []
    for s in shares:
        raw = json.dumps(s, separators=(',', ':')).encode('utf-8')
        encoded.append(base64.urlsafe_b64encode(raw).decode('ascii'))
    return encoded


def recover_secret_shares(shares: list[str]) -> str:
    if len(shares) < 3:
        raise ValueError("At least 3 shares are required")
    prime = 257
    parsed = []
    for sh in shares:
        item = json.loads(base64.urlsafe_b64decode(sh.encode('ascii')).decode('utf-8'))
        parsed.append(item)
    ys_len = len(parsed[0]["ys"])
    for p in parsed:
        if len(p["ys"]) != ys_len:
            raise ValueError("Share lengths mismatch")

    def lagrange_at_zero(points: list[tuple[int, int]]) -> int:
        total = 0
        for i, (xi, yi) in enumerate(points):
            num = 1
            den = 1
            for j, (xj, _yj) in enumerate(points):
                if i == j:
                    continue
                num = (num * (-xj)) % prime
                den = (den * (xi - xj)) % prime
            inv_den = pow(den % prime, -1, prime)
            total = (total + yi * num * inv_den) % prime
        return total

    out_bytes = bytearray()
    points_base = parsed[:3]
    for idx in range(ys_len):
        pts = [(int(p["x"]), int(p["ys"][idx])) for p in points_base]
        val = lagrange_at_zero(pts)
        if val > 255:
            raise ValueError("Recovered value out of byte range")
        out_bytes.append(val)
    return out_bytes.decode('utf-8')


def evaluate_advanced_policy(policy: dict, context: dict) -> dict:
    reasons = []
    allowed = True

    allowed_ips = policy.get('allowed_ips') or []
    if allowed_ips and context.get('ip') not in allowed_ips:
        allowed = False
        reasons.append('IP not allowed')

    allowed_countries = policy.get('allowed_countries') or []
    if allowed_countries and context.get('country') not in allowed_countries:
        allowed = False
        reasons.append('Country not allowed')

    if policy.get('require_otp'):
        expected = str(policy.get('otp_code', ''))
        provided = str(context.get('otp', ''))
        if not expected or provided != expected:
            allowed = False
            reasons.append('OTP mismatch')

    now_h = datetime.datetime.now().hour
    min_h = int(policy.get('min_hour', 0))
    max_h = int(policy.get('max_hour', 23))
    if now_h < min_h or now_h > max_h:
        allowed = False
        reasons.append('Outside allowed time window')

    return {"allowed": allowed, "reasons": reasons, "evaluated_at": datetime.datetime.now().isoformat()}


def create_watermark_signature(file_bytes: bytes, label: str, user_id: int) -> dict:
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    raw_secret = app.secret_key or 'titan'
    secret = raw_secret if isinstance(raw_secret, (bytes, bytearray)) else str(raw_secret).encode('utf-8')
    payload = f"{user_id}|{label}|{file_hash}".encode('utf-8')
    signature = hashlib.sha256(secret + payload).hexdigest()
    return {"file_hash": file_hash, "signature": signature}

# --- المنطق البرمجي: فحص قوة كلمة السر ---

def generate_strong_password(length=16):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in password) and any(c.isupper() for c in password)
                and sum(c.isdigit() for c in password) >= 3):
            break
    return password

def generate_readable_passphrase(num_words=4):
    words = ["titan", "secure", "vault", "crypto", "shield", "phantom", "cyber", "ghost", 
             "delta", "omega", "matrix", "alpha", "zenith", "nebula", "storm", "blade",
             "orbit", "pulse", "static", "vector", "quantum", "binary", "proxy", "pixel"]
    selected = random.sample(words, num_words)
    return "-".join(selected) + str(random.randint(10, 99))

def get_strength_details(password):
    score = 0
    if len(password) >= 12: score += 1
    if re.search(r"[A-Z]", password): score += 1
    if re.search(r"[0-9]", password): score += 1
    if re.search(r"[!@#$%^&*]", password): score += 1
    if len(password) >= 16: score += 1
    levels = ["ضعيف جداً", "ضعيف", "متوسط", "قوي", "قوي جداً (TITAN Level)"]
    return levels[min(score, 4)], score

# --- فحص التسريبات (HIBP) ---

@lru_cache(maxsize=128)
def check_hibp_leak(password: str) -> int:
    if not password: return 0
    sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]  # type: ignore
    try:
        r = requests.get(f"https://api.pwnedpasswords.com/range/{prefix}", timeout=5)
        r.raise_for_status()
        for line in r.text.splitlines():
            s, count = line.split(':')
            if s == suffix: return int(count)
    except: pass
    return 0

# --- فحص IP ---
def get_ip_intelligence_data(ip=""):
    if not ip or ip == "127.0.0.1" or ip == "8.8.8.8":
        url = "http://ip-api.com/json/?fields=status,message,country,countryCode,regionName,city,zip,lat,lon,timezone,isp,org,as,proxy,query"
        ip_target = ""
    else:
        url = f"http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,regionName,city,zip,lat,lon,timezone,isp,org,as,proxy,query"
        ip_target = ip
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                is_proxy = data.get("proxy", False)
                
                # فحص إضافي وموثوق للـ VPN باستخدام أداة مجانية أخرى (proxycheck.io)
                try:
                    target = ip_target or data.get("query", "")
                    if target:
                        pc_url = f"http://proxycheck.io/v2/{target}?vpn=1&asn=1"
                        pc_res = requests.get(pc_url, timeout=5)
                        if pc_res.status_code == 200:
                            pc_data = pc_res.json()
                            if target in pc_data and pc_data[target].get("proxy") == "yes":
                                is_proxy = True
                except Exception:
                    pass

                # تنسيق البيانات لتتوافق مع ما يتوقعه سكريبت الجافاسكريبت
                return {
                    "success": True,
                    "proxy": is_proxy,
                    "vpn": is_proxy,
                    "fraud_score": 100 if is_proxy else 0,
                    "country_code": data.get("countryCode", "US"),
                    "ISP": data.get("isp", "Unknown"),
                    "query": data.get("query", ip)
                }
            else:
                 return {"success": False, "message": data.get("message", "فشل جلب البيانات")}
        else:
            return {"success": False, "message": f"Error {response.status_code}: {response.text}"}
    except Exception as e:
        return {"success": False, "message": str(e), "error": str(e)}

# --- واجهة المستخدم (HTML) ---

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TITAN | التشفير والأمن السيبراني</title>
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIj48cmVjdCB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgcng9IjE4IiBmaWxsPSIjMGQwZDFhIi8+PHRleHQgeD0iNTAiIHk9IjY4IiBmb250LWZhbWlseT0iQXJpYWwgQmxhY2ssc2Fucy1zZXJpZiIgZm9udC1zaXplPSI1NCIgZm9udC13ZWlnaHQ9IjkwMCIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZmlsbD0idXJsKCNnKSI+VEFOPC90ZXh0PjxkZWZzPjxsaW5lYXJHcmFkaWVudCBpZD0iZyIgeDE9IjAlIiB5MT0iMCUiIHgyPSIxMDAlIiB5Mj0iMTAwJSI+PHN0b3Agb2Zmc2V0PSIwJSIgc3RvcC1jb2xvcj0iI2MwODRmYyIvPjxzdG9wIG9mZnNldD0iMTAwJSIgc3RvcC1jb2xvcj0iIzdjM2FlZCIvPjwvbGluZWFyR3JhZGllbnQ+PC9kZWZzPjwvc3ZnPg==">
    <link rel="stylesheet" href="/tailwind.css?v=3">
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Tajawal', sans-serif; background: #070b19; color: white; margin: 0; overflow-x: hidden; cursor: crosshair; }
        #matrix-bg, #intro-matrix { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; pointer-events: none; }
        #matrix-bg { z-index: -1; }
        #intro-matrix { z-index: 0; opacity: 0.6; }
        .glass { background: rgba(10, 15, 30, 0.85); backdrop-filter: blur(16px); border: 1px solid rgba(168, 85, 247, 0.2); box-shadow: 0 0 30px rgba(0,0,0,0.5); }
        button, a, input { cursor: pointer; }
        .titan-gradient { background: linear-gradient(135deg, #a855f7 0%, #7c3aed 100%); }
        
        /* Scanlines & CRT Effect */
        body::after { content: " "; display: block; position: fixed; top: 0; left: 0; bottom: 0; right: 0; background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.06), rgba(0, 255, 0, 0.02), rgba(0, 0, 255, 0.06)); z-index: 999; background-size: 100% 2px, 3px 100%; pointer-events: none; }
        
        /* Premium Ambient Background */
        #intro-overlay { 
            background: linear-gradient(180deg, #050505 0%, #0a0a0a 100%);
            position: fixed; inset: 0; z-index: 9999; 
            display: flex; flex-direction: column; justify-content: center; align-items: center; 
            transition: opacity 1.5s cubic-bezier(0.4, 0, 0.2, 1); 
            overflow: hidden; 
        }
        /* Animated Dark Violet Glows */
        #intro-overlay::before, #intro-overlay::after {
            content: ''; position: absolute; border-radius: 50%; filter: blur(140px); z-index: 0; pointer-events: none;
            animation: float-glowing-bars 12s ease-in-out infinite alternate;
        }
        #intro-overlay::before {
            width: 80vw; height: 30vh; background: rgba(168, 85, 247, 0.15); /* Purple */
            top: 20%; left: 10%;
        }
        #intro-overlay::after {
            width: 60vw; height: 40vh; background: rgba(139, 92, 246, 0.12); /* Deep Violet */
            bottom: 10%; right: 20%;
            animation-delay: -6s;
        }
        /* Dynamic Horizontal Scans (like the reference image background) */
        .premium-bg-scan {
            position: absolute; inset: 0; z-index: 1; pointer-events: none; opacity: 0.3;
            background: repeating-linear-gradient(90deg, transparent, transparent 40px, rgba(168, 85, 247, 0.03) 40px, rgba(168, 85, 247, 0.03) 80px);
            mask-image: linear-gradient(to bottom, transparent, black 20%, black 80%, transparent);
            -webkit-mask-image: linear-gradient(to bottom, transparent, black 20%, black 80%, transparent);
            animation: bg-pan 30s linear infinite;
        }
        @keyframes bg-pan { 0% { background-position: 0 0; } 100% { background-position: 400px 0; } }
        @keyframes float-glowing-bars { 0% { transform: translateY(-20px) scale(1); opacity: 0.8; } 100% { transform: translateY(20px) scale(1.1); opacity: 1; } }

        /* Premium Typography */
        .premium-title { 
            font-size: 4.5rem; font-weight: 800; color: #ffffff; 
            position: relative; z-index: 10;
            line-height: 1.1; letter-spacing: -1px;
            text-align: center; margin-bottom: 1.5rem;
        }
        .premium-subtitle {
            font-size: 1.1rem; color: #94a3b8; z-index: 10;
            max-width: 600px; text-align: center; margin-top: 1rem; line-height: 1.6;
        }
        
        /* Fingerprint Scanner Button (Violet Theme) */
        .fingerprint-btn { margin-top: 3.5rem; width: 75px; height: 95px; border: 2px solid transparent; background: transparent; cursor: pointer; position: relative; transition: all 0.3s ease; opacity: 0; transform: translateY(20px); z-index: 10; display: inline-flex; flex-direction: column; align-items: center;}
        .fingerprint-btn.show { opacity: 1; transform: translateY(0); }
        .fingerprint-btn svg { width: 100%; height: 100%; fill: #a855f7; filter: drop-shadow(0 0 10px rgba(168, 85, 247, 0.6)); transition: all 0.3s ease; }
        .fingerprint-btn:hover svg { fill: #c084fc; filter: drop-shadow(0 0 18px rgba(192, 132, 252, 0.8)); }
        .scanner-line { position: absolute; top: 0; left: 0; width: 100%; height: 4px; background: #c084fc; box-shadow: 0 0 12px #c084fc, 0 0 25px #a855f7; border-radius: 50%; opacity: 0; pointer-events: none; }
        .fingerprint-btn:hover .scanner-line { opacity: 1; animation: scan 1.5s infinite linear; }
        @keyframes scan { 0% { top: 0; } 50% { top: 100%; } 100% { top: 0; } }
        
        /* Radar Animation for IP */
        .radar-box { position: relative; width: 150px; height: 150px; border-radius: 50%; border: 2px solid #22c55e; background: rgba(34, 197, 94, 0.1); overflow: hidden; margin: 0 auto; box-shadow: 0 0 20px rgba(34,197,94,0.3); }
        .radar-box::before { content: ''; position: absolute; top: 50%; left: 50%; width: 50%; height: 50%; transform-origin: top left; background: linear-gradient(45deg, rgba(34,197,94,0.8) 0%, transparent 50%); animation: radar-spin 2s linear infinite; }
        .radar-box::after { content: ''; position: absolute; top: 50%; left: 0; right: 0; border-top: 1px solid rgba(34,197,94,0.5); }
        .radar-cross { position: absolute; left: 50%; top: 0; bottom: 0; border-left: 1px solid rgba(34,197,94,0.5); }
        .radar-target { position: absolute; width: 8px; height: 8px; background: #ef4444; border-radius: 50%; box-shadow: 0 0 10px #ef4444; opacity: 0; top: 30%; left: 60%; animation: target-ping 2s infinite; }
        @keyframes radar-spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes target-ping { 0%, 100% { transform: scale(1); opacity: 0; } 50% { transform: scale(1.5); opacity: 1; } }

    </style>
</head>
<body class="min-h-screen relative">
    <!-- ===== AUTH OVERLAY (Login / Register) ===== -->
    <div id="auth-overlay" style="display:none; position:fixed; inset:0; z-index:99999; background:#050510; overflow:hidden;">
        <!-- Matrix Canvas inside Auth -->
        <canvas id="auth-matrix" style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:0;"></canvas>

        <!-- Glowing Orbs -->
        <div style="position:absolute;width:60vw;height:60vw;border-radius:50%;background:radial-gradient(circle,rgba(139,92,246,0.18) 0%,transparent 70%);top:-20%;left:-10%;filter:blur(80px);animation:orbFloat 10s ease-in-out infinite alternate;pointer-events:none;z-index:1;"></div>
        <div style="position:absolute;width:40vw;height:40vw;border-radius:50%;background:radial-gradient(circle,rgba(168,85,247,0.14) 0%,transparent 70%);bottom:-15%;right:5%;filter:blur(80px);animation:orbFloat 14s ease-in-out infinite alternate-reverse;pointer-events:none;z-index:1;"></div>

        <!-- Auth Card -->
        <div style="position:relative;z-index:10;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:1.5rem;" id="auth-card-wrapper">
            <div style="width:100%;max-width:420px;background:rgba(10,10,30,0.85);border:1px solid rgba(139,92,246,0.35);border-radius:24px;padding:2.5rem 2rem;box-shadow:0 0 80px rgba(139,92,246,0.25),0 25px 60px rgba(0,0,0,0.6);backdrop-filter:blur(24px);">

                <!-- Logo -->
                <div style="text-align:center;margin-bottom:2rem;">
                    <div style="font-size:3.5rem;font-weight:900;letter-spacing:-2px;background:linear-gradient(135deg,#a855f7,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;line-height:1;">TITAN</div>
                    <div style="color:#6d28d9;font-size:0.7rem;letter-spacing:0.4em;text-transform:uppercase;margin-top:4px;">Security Protocol</div>
                    <div style="width:60px;height:1px;background:linear-gradient(90deg,transparent,#a855f7,transparent);margin:1rem auto 0;"></div>
                </div>

                <!-- Tab Toggle -->
                <div style="display:flex;background:rgba(15,15,40,0.8);border-radius:12px;padding:4px;margin-bottom:1.8rem;border:1px solid rgba(139,92,246,0.2);">
                    <button id="auth-tab-login" onclick="switchAuthTab('login')" style="flex:1;padding:0.6rem;border-radius:9px;border:none;cursor:pointer;font-weight:700;font-size:0.85rem;transition:all 0.25s;background:linear-gradient(135deg,#a855f7,#7c3aed);color:white;box-shadow:0 0 15px rgba(168,85,247,0.4);font-family:Tajawal,sans-serif;">تسجيل الدخول</button>
                    <button id="auth-tab-register" onclick="switchAuthTab('register')" style="flex:1;padding:0.6rem;border-radius:9px;border:none;cursor:pointer;font-weight:700;font-size:0.85rem;transition:all 0.25s;background:transparent;color:#6b7280;font-family:Tajawal,sans-serif;">إنشاء حساب</button>
                </div>

                <!-- Login Form -->
                <div id="auth-login-form">
                    <div style="margin-bottom:1rem;">
                        <label style="display:block;color:#9ca3af;font-size:0.78rem;margin-bottom:6px;letter-spacing:0.05em;">اسم المستخدم</label>
                        <input id="auth-login-user" type="text" placeholder="اسم المستخدم..." autocomplete="username" style="width:100%;box-sizing:border-box;padding:0.85rem 1rem;background:rgba(15,15,40,0.9);border:1px solid rgba(139,92,246,0.3);border-radius:12px;color:white;font-size:0.95rem;outline:none;transition:border-color 0.2s;font-family:Tajawal,sans-serif;" onfocus="this.style.borderColor='#a855f7'" onblur="this.style.borderColor='rgba(139,92,246,0.3)'">
                    </div>
                    <div style="margin-bottom:1.7rem;">
                        <label style="display:block;color:#9ca3af;font-size:0.78rem;letter-spacing:0.05em;margin-bottom:6px;">كلمة السر</label>
                        <input id="auth-login-pass" type="password" placeholder="كلمة السر..." autocomplete="current-password" style="width:100%;box-sizing:border-box;padding:0.85rem 1rem;background:rgba(15,15,40,0.9);border:1px solid rgba(139,92,246,0.3);border-radius:12px;color:white;font-size:0.95rem;outline:none;transition:border-color 0.2s;font-family:Tajawal,sans-serif;" onfocus="this.style.borderColor='#a855f7'" onblur="this.style.borderColor='rgba(139,92,246,0.3)'">
                        <div style="margin-top:0.95rem;display:flex;justify-content:flex-end;">
                            <a href="#" onclick="switchAuthTab('forgot'); return false;" style="color:#a855f7;font-size:0.75rem;text-decoration:none;transition:color 0.2s;line-height:1.2;" onmouseover="this.style.color='#e9d5ff'" onmouseout="this.style.color='#a855f7'">نسيت كلمة السر؟</a>
                        </div>
                    </div>
                    <div id="auth-login-error" style="display:none;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.4);border-radius:10px;padding:0.7rem 1rem;color:#f87171;font-size:0.82rem;margin-bottom:1rem;text-align:center;"></div>
                    <button onclick="doLogin()" style="width:100%;padding:0.9rem;background:linear-gradient(135deg,#a855f7,#7c3aed);border:none;border-radius:12px;color:white;font-size:1rem;font-weight:700;cursor:pointer;transition:all 0.2s;box-shadow:0 0 20px rgba(168,85,247,0.4);font-family:Tajawal,sans-serif;" onmouseover="this.style.boxShadow='0 0 35px rgba(168,85,247,0.7)'" onmouseout="this.style.boxShadow='0 0 20px rgba(168,85,247,0.4)'" id="auth-login-btn">
                        دخول إلى TITAN 🔐
                    </button>
                </div>

                <!-- Register Form -->
                <div id="auth-register-form" style="display:none;">
                    <div style="margin-bottom:1rem;">
                        <label style="display:block;color:#9ca3af;font-size:0.78rem;margin-bottom:6px;letter-spacing:0.05em;">اسم المستخدم (3 أحرف على الأقل)</label>
                        <input id="auth-reg-user" type="text" placeholder="اختر اسم مستخدم..." autocomplete="username" style="width:100%;box-sizing:border-box;padding:0.85rem 1rem;background:rgba(15,15,40,0.9);border:1px solid rgba(139,92,246,0.3);border-radius:12px;color:white;font-size:0.95rem;outline:none;transition:border-color 0.2s;font-family:Tajawal,sans-serif;" onfocus="this.style.borderColor='#a855f7'" onblur="this.style.borderColor='rgba(139,92,246,0.3)'">
                    </div>
                    <div style="margin-bottom:1rem;">
                        <label style="display:block;color:#9ca3af;font-size:0.78rem;margin-bottom:6px;letter-spacing:0.05em;">البريد الإلكتروني</label>
                        <input id="auth-reg-email" type="email" placeholder="بريدك الإلكتروني (لتفعيل الحساب)..." autocomplete="email" style="width:100%;box-sizing:border-box;padding:0.85rem 1rem;background:rgba(15,15,40,0.9);border:1px solid rgba(139,92,246,0.3);border-radius:12px;color:white;font-size:0.95rem;outline:none;transition:border-color 0.2s;font-family:Tajawal,sans-serif;" onfocus="this.style.borderColor='#a855f7'" onblur="this.style.borderColor='rgba(139,92,246,0.3)'">
                    </div>
                    <div style="margin-bottom:1rem;">
                        <label style="display:block;color:#9ca3af;font-size:0.78rem;margin-bottom:6px;letter-spacing:0.05em;">كلمة السر (6 أحرف على الأقل)</label>
                        <input id="auth-reg-pass" type="password" placeholder="اختر كلمة سر قوية..." autocomplete="new-password" style="width:100%;box-sizing:border-box;padding:0.85rem 1rem;background:rgba(15,15,40,0.9);border:1px solid rgba(139,92,246,0.3);border-radius:12px;color:white;font-size:0.95rem;outline:none;transition:border-color 0.2s;font-family:Tajawal,sans-serif;" onfocus="this.style.borderColor='#a855f7'" onblur="this.style.borderColor='rgba(139,92,246,0.3)'">
                    </div>
                    <div style="margin-bottom:1.5rem;">
                        <label style="display:block;color:#9ca3af;font-size:0.78rem;margin-bottom:6px;letter-spacing:0.05em;">تأكيد كلمة السر</label>
                        <input id="auth-reg-pass2" type="password" placeholder="أعد كتابة كلمة السر..." autocomplete="new-password" style="width:100%;box-sizing:border-box;padding:0.85rem 1rem;background:rgba(15,15,40,0.9);border:1px solid rgba(139,92,246,0.3);border-radius:12px;color:white;font-size:0.95rem;outline:none;transition:border-color 0.2s;font-family:Tajawal,sans-serif;" onfocus="this.style.borderColor='#a855f7'" onblur="this.style.borderColor='rgba(139,92,246,0.3)'">
                    </div>
                    <div style="margin-bottom:1rem;">
                        <label style="display:block;color:#9ca3af;font-size:0.78rem;margin-bottom:6px;letter-spacing:0.05em;">الشروط والأحكام (إلزامية)</label>
                        <button id="auth-open-terms-btn" type="button" onclick="openTermsModal()" style="width:100%;padding:0.65rem;background:rgba(168,85,247,0.15);border:1px solid rgba(168,85,247,0.35);border-radius:10px;color:#e9d5ff;font-size:0.82rem;font-weight:700;cursor:pointer;font-family:Tajawal,sans-serif;">قراءة الشروط والأحكام</button>
                        <div id="auth-terms-read-state" style="margin-top:0.45rem;color:#6b7280;font-size:0.72rem;">الحالة: لم يتم تأكيد القراءة بعد.</div>
                        <label id="auth-reg-terms-label" style="margin-top:0.7rem;display:flex;align-items:center;gap:0.5rem;color:#6b7280;font-size:0.8rem;opacity:0.55;cursor:not-allowed;">
                            <input id="auth-reg-terms" type="checkbox" disabled onchange="updateRegisterButtonState()" style="accent-color:#a855f7;cursor:not-allowed;">
                            أوافق على الشروط والأحكام
                        </label>
                        <div style="color:#6b7280;font-size:0.72rem;margin-top:0.25rem;">لن تستطيع إنشاء الحساب قبل قراءة الأحكام والموافقة عليها.</div>
                    </div>
                    <div id="auth-terms-modal" style="display:none;position:fixed;inset:0;z-index:100000;background:rgba(0,0,0,0.8);align-items:center;justify-content:center;padding:1rem;">
                        <div style="width:100%;max-width:560px;background:rgba(9,12,30,0.98);border:1px solid rgba(168,85,247,0.35);border-radius:18px;box-shadow:0 0 60px rgba(168,85,247,0.25);overflow:hidden;">
                            <div style="padding:1rem 1rem 0.6rem 1rem;border-bottom:1px solid rgba(148,163,184,0.2);">
                                <h3 style="margin:0;color:#e9d5ff;font-size:1rem;font-weight:800;">الشروط والأحكام</h3>
                                <div style="color:#94a3b8;font-size:0.75rem;margin-top:0.25rem;">قم بالتمرير حتى نهاية النص لتفعيل زر الموافقة.</div>
                            </div>
                            <div id="auth-terms-modal-content" onscroll="handleTermsModalScroll()" style="max-height:300px;overflow:auto;padding:1rem;line-height:1.75;color:#cbd5e1;font-size:0.82rem;">
                                <p style="margin:0 0 0.7rem 0;">باستخدام منصة TITAN فأنت تقر بأنك مسؤول عن أي نشاط يتم عبر حسابك، وأنك لن تستخدم الأدوات لأي نشاط مخالف للقانون أو إساءة.</p>
                                <p style="margin:0 0 0.7rem 0;">تقوم المنصة بمعالجة بيانات مثل البريد الإلكتروني، عنوان IP، نوع المتصفح، وسجلات الأمان لتحسين الحماية والتحقق من الدخولات المشبوهة.</p>
                                <p style="margin:0 0 0.7rem 0;">المنصة قد ترسل إشعارات وكود تحقق عبر البريد الإلكتروني، وتقوم بحفظ سجلات أمنية تشغيلية لحماية الحساب والنظام.</p>
                                <p style="margin:0 0 0.7rem 0;">أنت مسؤول بشكل كامل عن سرية كلمة المرور وأي استخدام يتم عبر حسابك. في حال الاشتباه بأي اختراق يجب تغيير كلمة المرور فوراً.</p>
                                <p style="margin:0 0 0.7rem 0;">يُمنع منعاً باتاً استخدام النظام في أي نشاط هجومي أو غير قانوني مثل فحص أو جمع بيانات أو استهداف جهات دون تصريح.</p>
                                <p style="margin:0 0 0.7rem 0;">يحق لإدارة النظام تعليق أو حذف الحساب في حال مخالفة هذه الشروط أو استخدام غير مشروع للخدمات.</p>
                                <p style="margin:0;">بالضغط على زر الموافقة، أنت تؤكد أنك قرأت النص كاملاً وتقبل جميع الشروط والأحكام.</p>
                            </div>
                            <div style="padding:0.9rem;display:flex;gap:0.55rem;">
                                <button type="button" onclick="closeTermsModal()" style="flex:1;padding:0.65rem;background:transparent;border:1px solid rgba(148,163,184,0.35);border-radius:10px;color:#94a3b8;cursor:pointer;font-family:Tajawal,sans-serif;">إغلاق</button>
                                <button id="auth-terms-confirm-btn" type="button" onclick="confirmTermsRead()" disabled style="flex:1;padding:0.65rem;background:rgba(124,58,237,0.25);border:1px solid rgba(124,58,237,0.35);border-radius:10px;color:#c4b5fd;cursor:not-allowed;font-weight:700;font-family:Tajawal,sans-serif;opacity:0.65;">قرأت وأوافق</button>
                            </div>
                        </div>
                    </div>
                    <div id="auth-reg-error" style="display:none;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.4);border-radius:10px;padding:0.7rem 1rem;color:#f87171;font-size:0.82rem;margin-bottom:1rem;text-align:center;"></div>
                    <div id="auth-reg-success" style="display:none;background:rgba(34,197,94,0.15);border:1px solid rgba(34,197,94,0.4);border-radius:10px;padding:0.7rem 1rem;color:#4ade80;font-size:0.82rem;margin-bottom:1rem;text-align:center;"></div>
                    <button onclick="doRegister()" style="width:100%;padding:0.9rem;background:linear-gradient(135deg,#7c3aed,#5b21b6);border:none;border-radius:12px;color:white;font-size:1rem;font-weight:700;cursor:not-allowed;transition:all 0.2s;box-shadow:0 0 20px rgba(124,58,237,0.2);font-family:Tajawal,sans-serif;opacity:0.55;" onmouseover="if(!this.disabled){this.style.boxShadow='0 0 35px rgba(124,58,237,0.7)'}" onmouseout="if(!this.disabled){this.style.boxShadow='0 0 20px rgba(124,58,237,0.4)'}" id="auth-reg-btn" disabled>
                        إنشاء حساب جديد ✨
                    </button>
                </div>

                <!-- Verification Form -->
                <div id="auth-verify-form" style="display:none;">
                    <div style="text-align:center;margin-bottom:1.5rem;">
                        <div style="font-size:2.5rem;margin-bottom:0.5rem;">📩</div>
                        <h3 style="color:#a855f7;font-weight:700;">تحقق من بريدك الإلكتروني</h3>
                        <p style="color:#9ca3af;font-size:0.8rem;margin-top:0.5rem;">أدخل الرمز المكون من 6 أرقام المرسل إليك</p>
                    </div>
                    <div style="margin-bottom:1.5rem;">
                        <input id="auth-verify-otp" type="text" placeholder="000000" maxlength="6" style="width:100%;box-sizing:border-box;padding:1rem;background:rgba(15,15,40,0.9);border:1px solid rgba(139,92,246,0.3);border-radius:12px;color:white;font-size:1.8rem;outline:none;transition:border-color 0.2s;font-family:monospace,sans-serif;text-align:center;letter-spacing:0.5em;" onfocus="this.style.borderColor='#a855f7'" onblur="this.style.borderColor='rgba(139,92,246,0.3)'">
                    </div>
                    <input type="hidden" id="auth-verify-username">
                    <div id="auth-verify-error" style="display:none;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.4);border-radius:10px;padding:0.7rem 1rem;color:#f87171;font-size:0.82rem;margin-bottom:1rem;text-align:center;"></div>
                    <button onclick="doVerify()" style="width:100%;padding:0.9rem;background:linear-gradient(135deg,#a855f7,#7c3aed);border:none;border-radius:12px;color:white;font-size:1rem;font-weight:700;cursor:pointer;transition:all 0.2s;box-shadow:0 0 20px rgba(168,85,247,0.4);font-family:Tajawal,sans-serif;" onmouseover="this.style.boxShadow='0 0 35px rgba(168,85,247,0.7)'" onmouseout="this.style.boxShadow='0 0 20px rgba(168,85,247,0.4)'" id="auth-verify-btn">
                        تفعيل الحساب 🛡️
                    </button>
                    <button onclick="switchAuthTab('login')" style="width:100%;margin-top:1rem;background:transparent;border:none;color:#9ca3af;font-size:0.85rem;cursor:pointer;text-decoration:underline;">إلغاء والعودة للدخول</button>
                </div>

                <!-- Forgot Password Form -->
                <div id="auth-forgot-form" style="display:none;">
                    <!-- Step 1: Enter username -->
                    <div id="forgot-step1">
                        <div style="text-align:center;margin-bottom:1.5rem;">
                            <div style="font-size:2.5rem;margin-bottom:0.5rem;">🔑</div>
                            <h3 style="color:#a855f7;font-weight:700;">استعادة كلمة السر</h3>
                            <p style="color:#9ca3af;font-size:0.8rem;margin-top:0.5rem;">أدخل اسم المستخدم الخاص بك وسيُرسل كود التحقق إلى إيميلك.</p>
                        </div>
                        <div style="margin-bottom:1rem;">
                            <label style="display:block;color:#9ca3af;font-size:0.78rem;margin-bottom:6px;">اسم المستخدم</label>
                            <input id="forgot-username" type="text" placeholder="اسم المستخدم..." style="width:100%;box-sizing:border-box;padding:0.85rem 1rem;background:rgba(15,15,40,0.9);border:1px solid rgba(139,92,246,0.3);border-radius:12px;color:white;font-size:0.95rem;outline:none;font-family:Tajawal,sans-serif;" onfocus="this.style.borderColor='#a855f7'" onblur="this.style.borderColor='rgba(139,92,246,0.3)'">
                        </div>
                        <div id="forgot-step1-error" style="display:none;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.4);border-radius:10px;padding:0.7rem 1rem;color:#f87171;font-size:0.82rem;margin-bottom:1rem;text-align:center;"></div>
                        <button onclick="doForgotSend()" style="width:100%;padding:0.9rem;background:linear-gradient(135deg,#a855f7,#7c3aed);border:none;border-radius:12px;color:white;font-size:1rem;font-weight:700;cursor:pointer;font-family:Tajawal,sans-serif;box-shadow:0 0 20px rgba(168,85,247,0.4);" id="forgot-send-btn">
                            📧 إرسال كود التحقق
                        </button>
                        <button onclick="switchAuthTab('login')" style="width:100%;margin-top:0.75rem;background:transparent;border:none;color:#9ca3af;font-size:0.85rem;cursor:pointer;text-decoration:underline;">العودة للدخول</button>
                    </div>
                    <!-- Step 2: Enter code -->
                    <div id="forgot-step2" style="display:none;">
                        <div style="text-align:center;margin-bottom:1.5rem;">
                            <div style="font-size:2.5rem;margin-bottom:0.5rem;">📩</div>
                            <h3 style="color:#a855f7;font-weight:700;">أدخل كود التحقق</h3>
                            <p style="color:#9ca3af;font-size:0.8rem;margin-top:0.5rem;">تحقق من بريدك الإلكتروني وأدخل الكود المكوّن من 6 أرقام.</p>
                        </div>
                        <div style="margin-bottom:1.5rem;">
                            <input id="forgot-otp" type="text" placeholder="000000" maxlength="6" style="width:100%;box-sizing:border-box;padding:1rem;background:rgba(15,15,40,0.9);border:1px solid rgba(139,92,246,0.3);border-radius:12px;color:white;font-size:1.8rem;outline:none;font-family:monospace;text-align:center;letter-spacing:0.5em;">
                        </div>
                        <div id="forgot-step2-error" style="display:none;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.4);border-radius:10px;padding:0.7rem 1rem;color:#f87171;font-size:0.82rem;margin-bottom:1rem;text-align:center;"></div>
                        <button onclick="doForgotVerify()" style="width:100%;padding:0.9rem;background:linear-gradient(135deg,#a855f7,#7c3aed);border:none;border-radius:12px;color:white;font-size:1rem;font-weight:700;cursor:pointer;font-family:Tajawal,sans-serif;box-shadow:0 0 20px rgba(168,85,247,0.4);">
                            ✅ تحقق من الكود
                        </button>
                        <button onclick="switchAuthTab('login')" style="width:100%;margin-top:0.75rem;background:transparent;border:none;color:#9ca3af;font-size:0.85rem;cursor:pointer;text-decoration:underline;">إلغاء والعودة</button>
                    </div>
                    <!-- Step 3: New password -->
                    <div id="forgot-step3" style="display:none;">
                        <div style="text-align:center;margin-bottom:1.5rem;">
                            <div style="font-size:2.5rem;margin-bottom:0.5rem;">🔐</div>
                            <h3 style="color:#a855f7;font-weight:700;">تعيين كلمة سر جديدة</h3>
                        </div>
                        <div style="margin-bottom:1rem;">
                            <label style="display:block;color:#9ca3af;font-size:0.78rem;margin-bottom:6px;">كلمة السر الجديدة</label>
                            <input id="forgot-newpass" type="password" placeholder="كلمة السر الجديدة..." style="width:100%;box-sizing:border-box;padding:0.85rem 1rem;background:rgba(15,15,40,0.9);border:1px solid rgba(139,92,246,0.3);border-radius:12px;color:white;font-size:0.95rem;outline:none;font-family:Tajawal,sans-serif;" onfocus="this.style.borderColor='#a855f7'" onblur="this.style.borderColor='rgba(139,92,246,0.3)'">
                        </div>
                        <div style="margin-bottom:1.5rem;">
                            <label style="display:block;color:#9ca3af;font-size:0.78rem;margin-bottom:6px;">تأكيد كلمة السر</label>
                            <input id="forgot-newpass2" type="password" placeholder="أعد كتابة كلمة السر..." style="width:100%;box-sizing:border-box;padding:0.85rem 1rem;background:rgba(15,15,40,0.9);border:1px solid rgba(139,92,246,0.3);border-radius:12px;color:white;font-size:0.95rem;outline:none;font-family:Tajawal,sans-serif;" onfocus="this.style.borderColor='#a855f7'" onblur="this.style.borderColor='rgba(139,92,246,0.3)'">
                        </div>
                        <div id="forgot-step3-error" style="display:none;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.4);border-radius:10px;padding:0.7rem 1rem;color:#f87171;font-size:0.82rem;margin-bottom:1rem;text-align:center;"></div>
                        <button onclick="doForgotReset()" style="width:100%;padding:0.9rem;background:linear-gradient(135deg,#22c55e,#16a34a);border:none;border-radius:12px;color:white;font-size:1rem;font-weight:700;cursor:pointer;font-family:Tajawal,sans-serif;box-shadow:0 0 20px rgba(34,197,94,0.4);">
                            🔑 تغيير كلمة السر
                        </button>
                    </div>
                </div>

                <!-- Footer -->
                <div style="text-align:center;margin-top:1.5rem;color:#374151;font-size:0.72rem;letter-spacing:0.05em;">
                    🛡️ TITAN SECURITY PROTOCOL — ALL DATA ENCRYPTED
                </div>
            </div>
        </div>

        <style>
            @keyframes orbFloat { 0%{transform:translate(0,0) scale(1);} 100%{transform:translate(3%,5%) scale(1.08);} }

            .tab-nav-modern {
                background: linear-gradient(145deg, rgba(15, 23, 42, 0.72), rgba(2, 6, 23, 0.8));
                border: 1px solid rgba(148, 163, 184, 0.2);
                box-shadow: inset 0 0 30px rgba(15, 23, 42, 0.35), 0 10px 35px rgba(2, 6, 23, 0.55);
            }

            .tab-nav-modern .tab-group-title {
                color: #c4b5fd;
                letter-spacing: 0.06em;
                font-size: 0.72rem;
                font-weight: 800;
                display: flex;
                align-items: center;
                gap: 0.35rem;
                margin-bottom: 0.55rem;
                text-transform: uppercase;
            }

            .tab-nav-modern .tab-search-input {
                width: 100%;
                padding: 0.62rem 0.85rem;
                border-radius: 0.75rem;
                border: 1px solid rgba(148, 163, 184, 0.26);
                background: rgba(15, 23, 42, 0.7);
                color: #e2e8f0;
                font-size: 0.78rem;
                outline: none;
                transition: border-color 0.2s ease, box-shadow 0.2s ease;
            }

            .tab-nav-modern .tab-search-input:focus {
                border-color: rgba(168, 85, 247, 0.55);
                box-shadow: 0 0 0 1px rgba(168, 85, 247, 0.28), 0 0 16px rgba(88, 28, 135, 0.28);
            }

            .tab-nav-modern .tab-search-input::placeholder {
                color: #64748b;
            }

            .tab-nav-modern .tab-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 0.45rem;
            }

            .tab-nav-modern .tab-grid button {
                width: 100%;
                justify-content: center;
                text-align: center;
                min-height: 2.3rem;
                border: 1px solid rgba(148, 163, 184, 0.18);
                background: rgba(15, 23, 42, 0.55);
                color: #cbd5e1;
                transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease, background 0.2s ease;
            }

            @media (max-width: 640px) {
                .tab-nav-modern .tab-grid button {
                    min-height: 2.15rem;
                }
            }

            .tab-nav-modern .tab-grid button:hover {
                transform: translateY(-1px);
                border-color: rgba(168, 85, 247, 0.45);
                box-shadow: 0 8px 18px rgba(88, 28, 135, 0.28);
            }

            .tab-nav-modern .tab-grid button.tab-active {
                background: linear-gradient(135deg, rgba(139, 92, 246, 0.95), rgba(109, 40, 217, 0.95));
                border-color: rgba(196, 181, 253, 0.7);
                color: #ffffff;
                box-shadow: 0 0 0 1px rgba(196, 181, 253, 0.25), 0 0 18px rgba(139, 92, 246, 0.45);
            }

            .tab-nav-modern .tab-grid button.tab-active-vault {
                background: linear-gradient(135deg, rgba(245, 158, 11, 0.95), rgba(217, 119, 6, 0.95));
                border-color: rgba(253, 230, 138, 0.65);
                color: #0f172a;
                box-shadow: 0 0 0 1px rgba(251, 191, 36, 0.3), 0 0 18px rgba(234, 179, 8, 0.35);
            }

            .result-panel {
                background: linear-gradient(145deg, rgba(15, 23, 42, 0.86), rgba(2, 6, 23, 0.88));
                border: 1px solid rgba(148, 163, 184, 0.26);
                border-radius: 0.95rem;
                box-shadow: 0 14px 30px rgba(2, 6, 23, 0.45), inset 0 1px 0 rgba(148, 163, 184, 0.06);
                padding: 0.95rem;
                animation: resultSlideIn 0.35s ease;
                position: relative;
            }

            .result-panel::before {
                content: '';
                position: absolute;
                inset: 0;
                border-radius: inherit;
                pointer-events: none;
                border: 1px solid transparent;
            }

            .result-panel.risk-safe::before {
                border-color: rgba(34, 197, 94, 0.35);
                box-shadow: 0 0 18px rgba(34, 197, 94, 0.18);
            }

            .result-panel.risk-warn::before {
                border-color: rgba(245, 158, 11, 0.42);
                box-shadow: 0 0 18px rgba(245, 158, 11, 0.16);
            }

            .result-panel.risk-danger::before {
                border-color: rgba(239, 68, 68, 0.45);
                box-shadow: 0 0 18px rgba(239, 68, 68, 0.2);
            }

            .result-panel--loading {
                border-color: rgba(129, 140, 248, 0.45);
            }

            .result-head {
                display: flex;
                flex-wrap: wrap;
                justify-content: space-between;
                align-items: center;
                gap: 0.6rem;
                margin-bottom: 0.75rem;
            }

            .result-title {
                font-size: 0.74rem;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                color: #a5b4fc;
                font-weight: 800;
            }

            .result-badge {
                font-size: 0.68rem;
                font-weight: 700;
                border-radius: 999px;
                border: 1px solid rgba(148, 163, 184, 0.28);
                background: rgba(15, 23, 42, 0.7);
                color: #cbd5e1;
                padding: 0.2rem 0.55rem;
            }

            .result-kv-grid {
                display: grid;
                grid-template-columns: repeat(1, minmax(0, 1fr));
                gap: 0.6rem;
            }

            @media (min-width: 768px) {
                .result-kv-grid.cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
                .result-kv-grid.cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
            }

            .result-kv-item {
                border: 1px solid rgba(71, 85, 105, 0.55);
                background: rgba(2, 6, 23, 0.58);
                border-radius: 0.8rem;
                padding: 0.72rem;
                transition: border-color 0.2s ease, transform 0.2s ease;
            }

            .result-kv-item:hover {
                border-color: rgba(129, 140, 248, 0.55);
                transform: translateY(-1px);
            }

            .result-kv-label {
                font-size: 0.64rem;
                color: #94a3b8;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                margin-bottom: 0.35rem;
            }

            .result-kv-value {
                font-size: 0.9rem;
                color: #e2e8f0;
                font-weight: 700;
                line-height: 1.45;
                word-break: break-word;
            }

            .result-tone-danger .result-kv-value { color: #f87171; }
            .result-tone-safe .result-kv-value { color: #4ade80; }
            .result-tone-warn .result-kv-value { color: #fbbf24; }
            .result-tone-info .result-kv-value { color: #93c5fd; }

            .result-list {
                display: grid;
                gap: 0.5rem;
            }

            .result-list-item {
                border: 1px solid rgba(71, 85, 105, 0.45);
                background: rgba(15, 23, 42, 0.58);
                border-radius: 0.7rem;
                padding: 0.6rem 0.7rem;
                font-size: 0.78rem;
            }

            .result-skeleton {
                position: relative;
                overflow: hidden;
                border: 1px solid rgba(71, 85, 105, 0.45);
                background: rgba(15, 23, 42, 0.6);
                border-radius: 0.7rem;
                height: 40px;
            }

            .result-skeleton::after {
                content: '';
                position: absolute;
                inset: 0;
                transform: translateX(-100%);
                background: linear-gradient(90deg, transparent, rgba(148, 163, 184, 0.18), transparent);
                animation: resultShimmer 1.4s linear infinite;
            }

            @keyframes resultSlideIn {
                from { opacity: 0; transform: translateY(6px) scale(0.99); }
                to { opacity: 1; transform: translateY(0) scale(1); }
            }

            @keyframes resultShimmer {
                100% { transform: translateX(100%); }
            }

            .tab-section-enter {
                animation: tabSectionIn 0.32s cubic-bezier(0.2, 0.9, 0.2, 1);
            }

            @keyframes tabSectionIn {
                from {
                    opacity: 0;
                    transform: translateY(8px) scale(0.995);
                    filter: blur(3px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0) scale(1);
                    filter: blur(0);
                }
            }
        </style>
    </div>
    <!-- END AUTH OVERLAY -->

    <!-- شاشة المقدمة الفاخرة (Premium Intro) -->

    <div id="intro-overlay">
        <div class="premium-bg-scan"></div>
        <canvas id="intro-matrix"></canvas> <!-- 3D Matrix Background inside Intro -->
        <div class="flex flex-col items-center justify-center h-full w-full opacity-0 translate-y-8 transition-all duration-1000 z-10 p-4" id="intro-center-logo">
            <div class="mb-2" style="filter: drop-shadow(0 0 40px rgba(168,85,247,0.8));">
                <div style="font-size:5rem;font-weight:900;letter-spacing:-4px;background:linear-gradient(135deg,#c084fc,#a855f7,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;line-height:1;text-align:center;">TITAN</div>
                <div style="text-align:center;color:#a855f7;font-size:0.75rem;letter-spacing:0.5em;text-transform:uppercase;margin-top:2px;opacity:0.8;">SEC</div>
            </div>
            <p class="premium-subtitle text-gray-400" dir="ltr">The Next-Gen Encryption & Intelligence Platform to protect your data with state-of-the-art security algorithms in a seamless interface.</p>
            
            <button id="start-btn" onclick="startSystem()" class="fingerprint-btn" title="Initiate System">
                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12,2C6.48,2 2,6.48 2,12C2,17.52 6.48,22 12,22C17.52,22 22,17.52 22,12C22,6.48 17.52,2 12,2M11,19.93C7.05,19.43 4,16.05 4,12C4,7.59 7.59,4 12,4C16.41,4 20,7.59 20,12C20,16.05 16.95,19.43 13,19.93V17H11V19.93M13,6.5A5.5,5.5 0 0,0 7.5,12H9.5A3.5,3.5 0 0,1 13,8.5V6.5M13,10A2,2 0 0,0 11,12H13V10Z" />
                </svg>
                <div class="scanner-line"></div>
                <!-- Glowing Circle Echo -->
                <div class="absolute inset-0 rounded-full border border-purple-500/30 animate-ping" style="animation-duration: 2.5s; z-index: -1; transform: scale(1.6);"></div>
                <div class="text-purple-400 text-xs mt-8 uppercase font-bold tracking-[0.2em] text-center animate-pulse whitespace-nowrap" style="text-shadow: 0 0 10px rgba(168, 85, 247, 0.8);">Touch To Authenticate</div>
            </button>
        </div>
    </div>

    <div id="main-app" class="opacity-0 transition-opacity duration-1000 ease-in-out pointer-events-none">
        <canvas id="matrix-bg"></canvas>
        <div class="container mx-auto px-4 py-12 max-w-4xl relative z-10">
        <header class="text-center mb-12 relative">
            <div style="display:inline-flex;flex-direction:column;align-items:center;margin-bottom:0.5rem;">
                <div style="font-size:4.5rem;font-weight:900;letter-spacing:-3px;background:linear-gradient(135deg,#c084fc,#a855f7,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;line-height:1;text-shadow:none;filter:drop-shadow(0 0 20px rgba(168,85,247,0.5));">TITAN</div>
                <div style="color:#a855f7;font-size:0.6rem;letter-spacing:0.5em;text-transform:uppercase;margin-top:1px;opacity:0.75;">SEC</div>
            </div>
            <p class="text-gray-400 text-lg text-purple-400">نظام التشفير وحماية البيانات المتطور</p>
            
            <div style="position:absolute;top:0;left:0;display:flex;align-items:center;gap:0.5rem;">
                <span id="header-username" style="color:#a855f7;font-size:0.75rem;font-weight:700;letter-spacing:0.05em;background:rgba(168,85,247,0.1);border:1px solid rgba(168,85,247,0.3);padding:4px 10px;border-radius:8px;"></span>
                <button onclick="doLogout()" title="تسجيل الخروج" style="background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.3);color:#f87171;padding:4px 10px;border-radius:8px;cursor:pointer;font-size:0.75rem;font-weight:700;transition:all 0.2s;" onmouseover="this.style.background='rgba(239,68,68,0.3)'" onmouseout="this.style.background='rgba(239,68,68,0.15)'">🚪 خروج</button>
            </div>
        </header>

        <div class="glass p-8 rounded-2xl shadow-2xl">
            <!-- Navigation -->
            <div class="tab-nav-modern mb-8 p-3 rounded-xl space-y-3">
                <div class="px-1">
                    <input id="tab-search-input" class="tab-search-input" type="text" placeholder="ابحث عن أداة... مثال: OSINT أو القبو" oninput="filterNavTabs(this.value)">
                    <div id="tab-search-empty" class="hidden text-[11px] text-rose-300 mt-2 font-bold">لا يوجد تبويب مطابق للبحث.</div>
                </div>

                <div class="tab-group">
                    <div class="tab-group-title px-1"><span>🧱</span> الحماية الأساسية</div>
                    <div class="tab-grid">
                    <button onclick="showTab('dash')" id="btn-dash" class="px-3 py-1.5 rounded-lg hover:bg-purple-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-purple-500/30"><span>📊</span> الإحصائيات</button>
                    <button onclick="showTab('pass')" id="btn-pass" class="px-3 py-1.5 rounded-lg hover:bg-purple-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-purple-500/30"><span>🔑</span> كلمات السر</button>
                    <button onclick="showTab('vault'); checkVaultPasswordSetup();" id="btn-vault" class="px-3 py-1.5 rounded-lg hover:bg-yellow-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-yellow-500/30"><span>🗄️</span> القبو</button>
                    <button onclick="showTab('crypt')" id="btn-crypt" class="px-3 py-1.5 rounded-lg hover:bg-blue-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-blue-500/30"><span>🔐</span> التشفير</button>
                    <button onclick="showTab('suite')" id="btn-suite" class="px-3 py-1.5 rounded-lg hover:bg-purple-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-purple-500/30"><span>🛠️</span> الأدوات الذكية</button>
                </div>
                </div>

                <div class="tab-group">
                    <div class="tab-group-title px-1"><span>🧭</span> التحليل والاستقصاء</div>
                    <div class="tab-grid">
                    <button onclick="showTab('tools')" id="btn-tools" class="px-3 py-1.5 rounded-lg hover:bg-purple-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-purple-500/30"><span>🌐</span> تتبع IP</button>
                    <button onclick="showTab('ghost')" id="btn-ghost" class="px-3 py-1.5 rounded-lg hover:bg-pink-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-pink-500/30"><span class="inline-block animate-pulse" style="animation-duration:1.3s;">🔥</span> قنوات الشبح</button>
                    <button onclick="showTab('osint')" id="btn-osint" class="px-3 py-1.5 rounded-lg hover:bg-indigo-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-indigo-500/30"><span>🕵️</span> OSINT</button>
                    <button onclick="showTab('ir')" id="btn-ir" class="px-3 py-1.5 rounded-lg hover:bg-red-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-red-500/30"><span>🚨</span> الحوادث</button>
                    <button onclick="showTab('maltego')" id="btn-maltego" class="px-3 py-1.5 rounded-lg hover:bg-fuchsia-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-fuchsia-500/30"><span>🕸️</span> الرسم البياني</button>
                    <button onclick="showTab('hunting')" id="btn-hunting" class="px-3 py-1.5 rounded-lg hover:bg-orange-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-orange-500/30"><span>🎯</span> الصيد التهديدي</button>
                    <button onclick="showTab('forensics')" id="btn-forensics" class="px-3 py-1.5 rounded-lg hover:bg-teal-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-teal-500/30"><span>🧪</span> الجنائي الرقمي</button>
                    <button onclick="showTab('brand')" id="btn-brand" class="px-3 py-1.5 rounded-lg hover:bg-cyan-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-cyan-500/30"><span>🛡️</span> حماية العلامة</button>
                    <button onclick="showTab('se')" id="btn-se" class="px-3 py-1.5 rounded-lg hover:bg-pink-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-pink-500/30"><span>🎭</span> الهندسة الاجتماعية</button>
                </div>
                </div>

                <div class="tab-group">
                    <div class="tab-group-title px-1"><span>🧪</span> المختبر المتقدم</div>
                    <div class="tab-grid">
                    <button onclick="showTab('advcrypto')" id="btn-advcrypto" class="px-3 py-1.5 rounded-lg hover:bg-emerald-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-emerald-500/30"><span>🧬</span> تشفير متقدم</button>
                    <button onclick="showTab('audio')" id="btn-audio" class="px-3 py-1.5 rounded-lg hover:bg-orange-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-orange-500/30"><span>🎵</span> إخفاء صوتي</button>
                    <button onclick="showTab('video')" id="btn-video" class="px-3 py-1.5 rounded-lg hover:bg-rose-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-rose-500/30"><span>🎬</span> فيديو مشفر</button>
                    <button onclick="showTab('qr')" id="btn-qr" class="px-3 py-1.5 rounded-lg hover:bg-green-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-green-500/30"><span>🔳</span> QR آمن</button>
                    <button onclick="showTab('identity')" id="btn-identity" class="px-3 py-1.5 rounded-lg hover:bg-cyan-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-cyan-500/30"><span>🪪</span> هوية وهمية</button>
                    <button onclick="showTab('extreme')" id="btn-extreme" class="px-3 py-1.5 rounded-lg hover:bg-red-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-red-500/30"><span>💣</span> أوامر متطرفة</button>
                    <button onclick="showTab('netintel')" id="btn-netintel" class="px-3 py-1.5 rounded-lg hover:bg-sky-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-sky-500/30"><span>🛰️</span> استخبارات الشبكة</button>
                    <button onclick="openAiSection()" id="btn-ai" class="hidden px-3 py-1.5 rounded-lg hover:bg-purple-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-purple-500/30"><span>🤖</span> الذكاء الاصطناعي</button>
                    <button onclick="showAdminTab()" id="btn-admin" class="hidden px-3 py-1.5 rounded-lg text-xs font-bold text-white transition-all items-center gap-1.5 border border-red-600/40 hover:bg-red-600/20 bg-red-600/10"><span>👑</span> لوحة الإدارة</button>
                </div>
                </div>
            </div>


            <!-- ===== AI SECTION ===== -->
            <div id="ai-section" class="hidden fixed right-4 bottom-24 z-[9998] w-[min(92vw,34rem)] max-h-[78vh] overflow-y-auto rounded-2xl border border-purple-900/40 bg-slate-950/96 shadow-[0_0_40px_rgba(139,92,246,0.24)] p-4 space-y-4" style="display:none;">
                <div class="flex items-center justify-between border-b border-slate-700 pb-2">
                    <h2 class="text-lg font-bold text-purple-300">&#129302; TITAN AI</h2>
                    <button type="button" onclick="closeAiBubble()" class="text-xs px-2 py-1 rounded-lg border border-slate-700 text-gray-300 hover:bg-slate-800">✕</button>
                </div>

                <div class="flex flex-wrap items-center justify-start gap-3 bg-slate-900/50 p-3 rounded-xl border border-slate-700">
                    <div class="flex items-center gap-2">
                        <span class="text-xs text-gray-400 font-bold">النموذج:</span>
                        <select id="ai-model-select" class="bg-slate-800 border border-slate-700 text-gray-300 text-xs rounded-lg p-2 outline-none">
                            <option value="titan_ultimate">TITAN ULTIMATE</option>
                            <option value="titan_sec">TITAN SEC</option>
                        </select>
                    </div>
                    <div class="flex items-center justify-end gap-2 ml-auto">
                        <button id="ai-subtab-support" onclick="showAiSubTab('support')" class="px-3 py-1.5 rounded-lg text-xs font-bold transition-all border border-slate-700 text-gray-300 bg-slate-800/60 hover:bg-purple-600/20 hover:border-purple-500/40">Support</button>
                        <button id="ai-subtab-analysis" onclick="showAiSubTab('analysis')" class="px-3 py-1.5 rounded-lg text-xs font-bold transition-all border border-slate-700 text-gray-300 bg-slate-800/60 hover:bg-purple-600/20 hover:border-purple-500/40">Analysis</button>
                        <button id="ai-subtab-chat" onclick="showAiSubTab('chat')" class="px-3 py-1.5 rounded-lg text-xs font-bold transition-all border border-purple-700/50 bg-purple-900/40 text-purple-300">Chat</button>
                    </div>
                </div>

                <div id="ai-sub-content-chat" class="space-y-4">
                <div id="ai-chat-shell" class="bg-slate-900/70 rounded-2xl border border-purple-900/30 overflow-hidden h-[34rem] flex flex-col">
                    <div class="p-3 border-b border-slate-700">
                        <span class="text-purple-300 text-sm font-bold">&#128172; محادثة مع AI</span>
                    </div>
                    <div id="ai-chat-messages" class="flex-1 overflow-y-auto p-4 space-y-3 bg-gradient-to-b from-slate-950/40 to-slate-900/20">
                        <div class="min-h-full flex flex-col justify-end gap-3" id="ai-chat-flow">
                            <div class="flex justify-start items-end gap-2">
                                <div class="w-7 h-7 rounded-full bg-purple-900/50 border border-purple-700/40 flex items-center justify-center text-xs">🤖</div>
                                <div class="bg-slate-800 text-gray-300 px-4 py-3 rounded-2xl rounded-bl-md max-w-[80%] text-sm shadow-lg border border-slate-700/60">
                                    مرحباً! أنا TITAN AI. كيف يمكنني مساعدتك اليوم؟
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="p-3 border-t border-slate-700 bg-slate-950/70 sticky bottom-0 space-y-2">
                        <div id="ai-attach-list" class="hidden flex flex-wrap gap-1.5"></div>
                        <input id="ai-file-input" type="file" class="hidden" multiple accept="image/*,.pdf,.txt,.md,.csv,.json,.log,.doc,.docx,.zip,.rar,.7z">
                        <div class="flex gap-2">
                            <button type="button" onclick="document.getElementById('ai-file-input').click()" class="bg-slate-800 hover:bg-slate-700 text-gray-200 px-3 py-2 rounded-xl font-bold text-sm border border-slate-600/70">📎</button>
                        <input type="text" id="ai-chat-input" placeholder="اسأل عن الأمن السيبراني..."
                            class="flex-1 bg-slate-800 border border-slate-700 text-gray-300 text-sm rounded-xl px-4 py-2 outline-none">
                        <button onclick="sendAiMessage()" id="ai-send-btn"
                            class="bg-purple-600 hover:bg-purple-500 text-white px-5 py-2 rounded-xl font-bold text-sm">
                            إرسال
                        </button>
                    </div>
                    </div>
                </div>
                </div>

                <div id="ai-sub-content-support" class="hidden space-y-4">
                <div class="bg-slate-900/70 rounded-2xl border border-purple-900/30 overflow-hidden">
                    <div class="p-3 border-b border-slate-700 flex items-center justify-between">
                        <span class="text-purple-300 text-sm font-bold">🎫 الدعم الفني - إنشاء تيكت</span>
                        <button onclick="loadSupportTickets()" class="text-xs px-3 py-1 rounded-lg bg-purple-900/30 border border-purple-800/50 text-purple-300">تحديث</button>
                    </div>
                    <div class="p-4 grid grid-cols-1 md:grid-cols-4 gap-2">
                        <input id="supportTicketSubject" type="text" placeholder="عنوان المشكلة" class="md:col-span-2 bg-slate-800 border border-slate-700 text-gray-300 text-xs rounded-lg p-2 outline-none">
                        <select id="supportTicketCategory" class="bg-slate-800 border border-slate-700 text-gray-300 text-xs rounded-lg p-2 outline-none">
                            <option value="technical">Technical</option>
                            <option value="billing">Billing</option>
                            <option value="account">Account</option>
                            <option value="security">Security</option>
                        </select>
                        <select id="supportTicketPriority" class="bg-slate-800 border border-slate-700 text-gray-300 text-xs rounded-lg p-2 outline-none">
                            <option value="low">Low</option>
                            <option value="normal" selected>Normal</option>
                            <option value="high">High</option>
                            <option value="urgent">Urgent</option>
                        </select>
                        <textarea id="supportTicketDetails" rows="3" placeholder="اشرح المشكلة بالتفصيل..." class="md:col-span-4 bg-slate-800 border border-slate-700 text-gray-300 text-xs rounded-lg p-2 outline-none resize-none"></textarea>
                        <button onclick="createSupportTicket()" class="md:col-span-4 bg-purple-600 hover:bg-purple-500 text-white rounded-lg p-2 font-bold text-sm">إنشاء تيكت دعم</button>
                    </div>
                    <div id="supportTicketsList" class="px-4 pb-4 space-y-2 max-h-56 overflow-y-auto"></div>
                </div>
                </div>

                <div id="ai-sub-content-analysis" class="hidden space-y-4">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="bg-slate-900/50 p-5 rounded-xl border border-purple-900/40">
                        <h3 class="font-bold text-purple-400 mb-3">&#128273; تحليل كلمة السر بالـ AI</h3>
                        <input type="password" id="ai-pass-input" placeholder="أدخل كلمة السر للتحليل..."
                            class="w-full bg-slate-800 border border-slate-700 text-gray-300 text-sm rounded-xl px-4 py-2 outline-none mb-3">
                        <button onclick="analyzePassword()" class="w-full bg-purple-900/50 hover:bg-purple-800 text-purple-300 font-bold p-2 rounded-xl border border-purple-800/50 text-sm">
                            تحليل بالذكاء الاصطناعي
                        </button>
                        <div id="ai-pass-result" class="hidden mt-3 p-3 bg-slate-800 rounded-xl text-sm text-gray-300 border border-slate-700"></div>
                    </div>
                    <div class="bg-slate-900/50 p-5 rounded-xl border border-violet-900/40">
                        <h3 class="font-bold text-violet-300 mb-3">&#128269; تحليل أمني بالـ AI</h3>
                        <textarea id="ai-security-input" rows="3" placeholder="الصق نتائج فحص IP هنا..."
                            class="w-full bg-slate-800 border border-slate-700 text-gray-300 text-sm rounded-xl px-4 py-2 outline-none mb-3 resize-none"></textarea>
                        <button onclick="analyzeSecurity()" class="w-full bg-violet-900/50 hover:bg-violet-800 text-violet-300 font-bold p-2 rounded-xl border border-violet-800/50 text-sm">
                            تحليل بالذكاء الاصطناعي
                        </button>
                        <div id="ai-security-result" class="hidden mt-3 p-3 bg-slate-800 rounded-xl text-sm text-gray-300 border border-slate-700"></div>
                    </div>
                </div>
                </div>

            </div>

            <button id="ai-float-launcher" type="button" onclick="toggleAiBubble()" class="hidden fixed right-5 bottom-6 z-[9999] w-14 h-14 rounded-full bg-gradient-to-br from-purple-500 to-violet-600 text-white text-2xl font-black shadow-[0_0_25px_rgba(139,92,246,0.55)] border border-purple-300/40 hover:scale-105 transition-all" title="TITAN AI">🤖</button>

            <!-- ===== ADMIN SECTION ===== -->
            <div id="admin-section" class="hidden space-y-6">
                <h2 class="text-2xl font-black text-red-600 border-b border-red-900/40 pb-2 flex items-center gap-2">👑 لوحة تحكم المسؤول (ROOT CMD)</h2>
                
                <div class="bg-red-950/20 border border-red-900/30 p-6 rounded-2xl relative overflow-hidden group">
                    <div class="absolute top-0 right-0 p-4 opacity-10 text-6xl group-hover:rotate-12 transition-transform">⚠️</div>
                    <h3 class="text-lg font-bold text-red-500 mb-2">إعادة ضبط المصنع (System Wipe/Reset)</h3>
                    <p class="text-sm text-gray-400 mb-6 font-semibold">احذر: هذا الإجراء سيقوم بحذف كافة المستخدمين، الجلسات، وسجلات الأمان، وملفات القبو نهائياً. سيتم الإبقاء فقط على حساب root.</p>
                    
                    <div class="bg-black/40 p-4 rounded-xl border border-red-900/50 mb-6">
                        <p class="text-xs text-red-400 font-mono mb-2 animate-pulse">> WARNING: DATA DELETION IS PERMANENT</p>
                        <div class="flex items-center gap-3">
                            <input type="checkbox" id="admin-confirm-reset" class="w-5 h-5 accent-red-600 cursor-pointer">
                            <label for="admin-confirm-reset" class="text-xs text-gray-300 font-bold select-none cursor-pointer">أقر بأنني مسؤول عن حذف كافة البيانات</label>
                        </div>
                    </div>
                    
                    <button onclick="adminNukeSystem()" id="admin-nuke-btn" class="w-full py-4 bg-gradient-to-r from-red-600 to-red-900 hover:from-red-500 hover:to-red-800 text-white font-black rounded-xl transition-all shadow-[0_0_30px_rgba(220,38,38,0.3)] flex items-center justify-center gap-2 text-lg">
                        <span>🔥</span> تنفيذ المسح الشامل (FACTORY RESET)
                    </button>
                    <div id="admin-reset-msg" class="mt-4 hidden p-3 rounded-lg text-center font-mono text-sm border"></div>
                </div>

                <div class="bg-slate-900/50 border border-slate-700 p-5 rounded-2xl">
                    <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
                        <h3 class="text-lg font-bold text-cyan-300">🎫 إدارة تذاكر الدعم الفني</h3>
                        <div class="flex items-center gap-2">
                            <select id="adminTicketStatusFilter" onchange="loadAdminSupportTickets()" class="bg-slate-800 border border-slate-700 text-gray-300 text-xs rounded-lg px-2 py-1.5 outline-none">
                                <option value="all">All Statuses</option>
                                <option value="open">Open</option>
                                <option value="in_progress">In Progress</option>
                                <option value="resolved">Resolved</option>
                                <option value="closed">Closed</option>
                            </select>
                            <button onclick="loadAdminSupportTickets()" class="px-3 py-1.5 rounded-lg bg-cyan-900/30 border border-cyan-800/50 text-cyan-300 text-xs font-bold">تحديث</button>
                        </div>
                    </div>
                    <div id="adminSupportTicketsList" class="space-y-3 max-h-[30rem] overflow-y-auto"></div>
                </div>
            </div>

            <div id="security-section" class="hidden"></div> <!-- Security section completely removed per user request -->

            <!-- ===== DASHBOARD SECTION ===== -->

            <div id="dash-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-purple-400 border-b border-slate-700 pb-2">📊 لوحة التحكم – معلومات النظام</h2>
                <div class="text-[11px] text-gray-500 -mt-4 flex items-center gap-2">آخر تحديث: <span id="dashUpdatedAt" class="text-purple-300 font-mono">—</span><span id="dashPulse" class="inline-block w-2 h-2 rounded-full bg-gray-600 opacity-60"></span></div>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3" id="dashCards">
                    <div id="dashCpuCard" class="bg-slate-900 rounded-xl p-4 border border-purple-800/40 text-center transition-all duration-300">
                        <div class="text-3xl font-black text-purple-400" id="dashCpu">—</div>
                        <div class="text-xs text-gray-500 mt-1">CPU %</div>
                    </div>
                    <div id="dashRamCard" class="bg-slate-900 rounded-xl p-4 border border-blue-800/40 text-center transition-all duration-300">
                        <div class="text-3xl font-black text-blue-400" id="dashRam">—</div>
                        <div class="text-xs text-gray-500 mt-1">RAM %</div>
                    </div>
                    <div id="dashDiskCard" class="bg-slate-900 rounded-xl p-4 border border-green-800/40 text-center transition-all duration-300">
                        <div class="text-3xl font-black text-green-400" id="dashDisk">—</div>
                        <div class="text-xs text-gray-500 mt-1">Disk I/O (KB/s)</div>
                    </div>
                    <div class="bg-slate-900 rounded-xl p-4 border border-yellow-800/40 text-center">
                        <div class="text-3xl font-black text-yellow-400" id="dashBurn">—</div>
                        <div class="text-xs text-gray-500 mt-1">Burn Notes</div>
                    </div>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="bg-slate-900/70 rounded-xl p-4 border border-slate-700">
                        <div class="text-xs text-gray-400 mb-3 font-bold">🌐 معلومات الشبكة</div>
                        <div class="space-y-2 text-sm font-mono">
                            <div class="flex justify-between"><span class="text-gray-500">IP المحلي</span><span class="text-green-400" id="dashLocalIp">—</span></div>
                            <div class="flex justify-between"><span class="text-gray-500">IP العام</span><span class="text-blue-400" id="dashPubIp">—</span></div>
                            <div class="flex justify-between"><span class="text-gray-500">سرعة صادر (KB/s)</span><span class="text-purple-400" id="dashSent">—</span></div>
                            <div class="flex justify-between"><span class="text-gray-500">سرعة وارد (KB/s)</span><span class="text-purple-400" id="dashRecv">—</span></div>
                            <div class="flex justify-between"><span class="text-gray-500">إجمالي صادر (MB)</span><span class="text-violet-300" id="dashSentTotal">—</span></div>
                            <div class="flex justify-between"><span class="text-gray-500">إجمالي وارد (MB)</span><span class="text-violet-300" id="dashRecvTotal">—</span></div>
                        </div>
                    </div>
                    <div class="bg-slate-900/70 rounded-xl p-4 border border-slate-700">
                        <div class="text-xs text-gray-400 mb-3 font-bold">📋 آخر النشاطات</div>
                        <div id="dashLogs" class="space-y-1 text-xs font-mono max-h-36 overflow-y-auto"></div>
                    </div>
                </div>
                <button onclick="loadDashboard()" class="titan-gradient px-6 py-2 rounded-xl font-bold text-sm">🔄 تحديث</button>
            </div>

            <!-- ===== PASSWORD SECTION ===== -->
            <div id="pass-section">
                <label class="block text-sm text-gray-400 mb-2">اختبر قوة كلمة السر:</label>
                <input type="password" id="passInput" class="w-full p-4 rounded-xl bg-slate-900 border border-slate-700 mb-4 text-left focus:ring-2 focus:ring-purple-500 outline-none transition-all">
                <div id="pass-result" class="mb-6 hidden">
                    <div class="flex justify-between items-center mb-2">
                        <span id="strength-text" class="font-bold"></span>
                        <span id="strength-percent" class="text-sm text-gray-400"></span>
                    </div>
                    <div class="h-3 bg-slate-700 rounded-full mb-4 overflow-hidden"><div id="strength-bar" class="h-full w-0 transition-all duration-700"></div></div>
                    <div id="leak-info" class="p-4 rounded-xl border hidden text-sm"></div>
                </div>
                <div class="flex gap-4">
                    <button onclick="generatePass('random')" class="text-purple-400 hover:text-purple-300 font-bold">✨ توليد كلمة سر TITAN</button>
                    <button onclick="generatePass('passphrase')" class="text-purple-400 hover:text-purple-300 font-bold">📖 توليد عبارت نصية (Passphrase)</button>
                </div>
                <div id="suggested-pass-container" class="mt-4 hidden p-4 bg-slate-900/50 rounded-xl border border-dashed border-purple-500/50 flex justify-between items-center">
                    <code id="suggested-pass" class="text-purple-400 font-mono text-lg"></code>
                    <button onclick="copyPass()" class="text-xs bg-slate-800 px-2 py-1 rounded">نسخ</button>
                </div>
            </div>

            <div id="suite-section" class="hidden space-y-8">
                <!-- ===== GLOBAL THREAT DASHBOARD (Interactive) ===== -->
                <div class="relative rounded-2xl border border-purple-900/50 overflow-hidden shadow-[0_0_40px_rgba(168,85,247,0.12)]" style="background:#050508;">

                    <!-- Animated Canvas Background -->
                    <canvas id="threatCanvas" class="absolute inset-0 w-full h-full opacity-40" style="height:220px;"></canvas>

                    <!-- Scanline overlay -->
                    <div class="absolute inset-0 pointer-events-none" style="background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.08) 2px,rgba(0,0,0,0.08) 4px);"></div>

                    <!-- Content -->
                    <div class="relative z-10 p-5" style="min-height:220px;">
                        <!-- Header Row -->
                        <div class="flex items-start justify-between mb-3">
                            <div>
                                <div class="flex items-center gap-2 mb-0.5">
                                    <span class="w-2 h-2 rounded-full bg-red-500 animate-pulse shadow-[0_0_8px_#ef4444]"></span>
                                    <span class="text-[10px] font-mono text-red-400 uppercase tracking-[0.3em]">LIVE FEED</span>
                                </div>
                                <h3 class="text-xl font-black text-purple-300 tracking-tight">Global Threat Dashboard</h3>
                                <p class="text-[10px] font-mono text-gray-500 tracking-[0.2em] uppercase mt-0.5">Neural Threat Intelligence · Active Protocols <span id="gtd-protocols" class="text-purple-400">04</span></p>
                            </div>
                            <!-- Live clock -->
                            <div class="text-right">
                                <div id="gtd-clock" class="font-mono text-purple-400 text-sm font-bold tracking-widest"></div>
                                <div class="text-[9px] text-gray-600 font-mono mt-0.5">UTC+03:00</div>
                            </div>
                        </div>

                        <!-- Stats Row -->
                        <div class="grid grid-cols-4 gap-2 mb-3">
                            <div class="bg-black/40 border border-red-900/40 rounded-xl p-2 text-center">
                                <div id="gtd-threats" class="text-lg font-black text-red-400 font-mono leading-none">0</div>
                                <div class="text-[9px] text-gray-500 mt-0.5 uppercase tracking-wider">Threats Blocked</div>
                            </div>
                            <div class="bg-black/40 border border-purple-900/40 rounded-xl p-2 text-center">
                                <div id="gtd-enc" class="text-lg font-black text-purple-400 font-mono leading-none">0</div>
                                <div class="text-[9px] text-gray-500 mt-0.5 uppercase tracking-wider">Encrypt Ops/s</div>
                            </div>
                            <div class="bg-black/40 border border-blue-900/40 rounded-xl p-2 text-center">
                                <div id="gtd-nodes" class="text-lg font-black text-blue-400 font-mono leading-none">0</div>
                                <div class="text-[9px] text-gray-500 mt-0.5 uppercase tracking-wider">Active Nodes</div>
                            </div>
                            <div class="bg-black/40 border border-green-900/40 rounded-xl p-2 text-center">
                                <div id="gtd-entropy" class="text-lg font-black text-green-400 font-mono leading-none">0.00</div>
                                <div class="text-[9px] text-gray-500 mt-0.5 uppercase tracking-wider">Entropy</div>
                            </div>
                        </div>

                        <!-- Scrolling Cyber Ticker -->
                        <div class="overflow-hidden rounded-lg bg-black/50 border border-purple-900/30 py-1.5 px-0 relative" style="height:28px;">
                            <div id="gtd-ticker" class="flex gap-8 items-center font-mono text-[10px] whitespace-nowrap absolute" style="animation:gtdScroll 30s linear infinite;top:6px;left:0;">
                                <span class="text-purple-400">AES-256-GCM · SHA3-512 · BLAKE3</span>
                                <span class="text-red-400">⚠ INTRUSION ATTEMPT BLOCKED: 185.220.101.x</span>
                                <span class="text-green-400">∑(p·log₂p) = 7.998 bits/byte</span>
                                <span class="text-blue-400">RSA-4096 · ECDH-P521 · X25519</span>
                                <span class="text-yellow-400">⚡ CIPHER: ChaCha20-Poly1305 · IV: 96bit nonce</span>
                                <span class="text-purple-300">∀x∈{0,1}ⁿ: H(x) = H(k‖x) mod 2²⁵⁶</span>
                                <span class="text-red-400">⚠ BRUTEFORCE DETECTED → FIREWALL ENGAGED</span>
                                <span class="text-cyan-400">TLS 1.3 · HSTS · OCSP Stapling · CT Logs</span>
                                <span class="text-green-300">KDF: PBKDF2-HMAC-SHA512 · 310,000 iterations</span>
                                <span class="text-orange-400">⚡ ZERO-DAY SIGNATURE UPDATED: CVE-2025-TITAN</span>
                                <!-- duplicate for seamless loop -->
                                <span class="text-purple-400">AES-256-GCM · SHA3-512 · BLAKE3</span>
                                <span class="text-red-400">⚠ INTRUSION ATTEMPT BLOCKED: 185.220.101.x</span>
                                <span class="text-green-400">∑(p·log₂p) = 7.998 bits/byte</span>
                                <span class="text-blue-400">RSA-4096 · ECDH-P521 · X25519</span>
                            </div>
                        </div>
                    </div>
                </div>

                <style>
                    @keyframes gtdScroll { from { transform:translateX(0) } to { transform:translateX(-50%) } }
                    #threatCanvas { width: 100%; height: 100%; position: absolute; top: 0; left: 0; pointer-events: none; opacity: 0.4; }
                </style>

                <script>
                (function(){
                    const canvas = document.getElementById('threatCanvas');
                    if(!canvas) return;
                    const ctx = canvas.getContext('2d');
                    
                    function resizeCanvas(){
                        canvas.width = canvas.offsetWidth;
                        canvas.height = canvas.offsetHeight;
                    }
                    resizeCanvas();
                    window.addEventListener('resize', resizeCanvas);

                    // === Canvas Cyber Streams ===
                    const CHARS = '01アイウエオカキクケコ∑∆∇∫∂π≠≡◊⊕⊗⊞⊟ABCDEF'.split('');
                    const cols = Math.floor(canvas.width / 14) || 50;
                    const drops = Array.from({length: cols + 1}, () => Math.random() * -50);
                    const speeds = Array.from({length: cols + 1}, () => Math.random() * 0.4 + 0.15);
                    const colors = ['#7c3aed','#a855f7','#c084fc','#f43f5e','#3b82f6'];

                    // === Threat Pings ===
                    const pings = [];
                    function createPing() {
                        if(pings.length > 5) return;
                        pings.push({ 
                            x: Math.random() * canvas.width, 
                            y: Math.random() * canvas.height, 
                            r: 0, 
                            alpha: 1 
                        });
                    }
                    setInterval(createPing, 3000);

                    function drawThreatPings() {
                        for (let i = pings.length - 1; i >= 0; i--) {
                            const p = pings[i];
                            ctx.beginPath();
                            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
                            ctx.strokeStyle = `rgba(239, 68, 68, ${p.alpha})`;
                            ctx.lineWidth = 2;
                            ctx.stroke();
                            
                            ctx.beginPath();
                            ctx.arc(p.x, p.y, 2, 0, Math.PI * 2);
                            ctx.fillStyle = `rgba(239, 68, 68, ${p.alpha})`;
                            ctx.fill();

                            p.r += 1.5;
                            p.alpha -= 0.015;
                            if (p.alpha <= 0) pings.splice(i, 1);
                        }
                    }

                    function drawCyberStream(){
                        ctx.fillStyle = 'rgba(5,5,8,0.18)';
                        ctx.fillRect(0,0,canvas.width,canvas.height);
                        drawThreatPings();
                        for(let i=0;i<cols;i++){
                            const char = CHARS[Math.floor(Math.random()*CHARS.length)];
                            const color = colors[i % colors.length];
                            ctx.font = `bold 12px monospace`;
                            // head glow
                            ctx.fillStyle = '#fff';
                            ctx.shadowColor = color;
                            ctx.shadowBlur = 8;
                            ctx.fillText(char, i*14, drops[i]*14);
                            // trail
                            ctx.fillStyle = color + 'aa';
                            ctx.shadowBlur = 3;
                            ctx.fillText(CHARS[Math.floor(Math.random()*CHARS.length)], i*14, (drops[i]-1)*14);
                            ctx.shadowBlur = 0;
                            if(drops[i]*14 > canvas.height && Math.random() > 0.975) drops[i] = 0;
                            drops[i] += speeds[i];
                        }
                    }
                    setInterval(drawCyberStream, 50);

                    // === Live Counters ===
                    let threats = 14872, enc = 0, nodes = 217, entropy = 7.94;
                    function updateCounters(){
                        threats += Math.floor(Math.random()*3);
                        enc = Math.floor(Math.random()*9999 + 5000);
                        nodes = 200 + Math.floor(Math.random()*40);
                        entropy = (7.90 + Math.random()*0.09).toFixed(3);
                        const t = document.getElementById('gtd-threats');
                        const e = document.getElementById('gtd-enc');
                        const n = document.getElementById('gtd-nodes');
                        const en = document.getElementById('gtd-entropy');
                        if(t) t.textContent = threats.toLocaleString();
                        if(e) e.textContent = enc.toLocaleString();
                        if(n) n.textContent = nodes;
                        if(en) en.textContent = entropy;
                    }
                    updateCounters();
                    setInterval(updateCounters, 1200);

                    // === Live Clock ===
                    function updateClock(){
                        const now = new Date();
                        const h = String(now.getHours()).padStart(2,'0');
                        const m = String(now.getMinutes()).padStart(2,'0');
                        const s = String(now.getSeconds()).padStart(2,'0');
                        const el = document.getElementById('gtd-clock');
                        if(el) el.textContent = h + ':' + m + ':' + s;
                    }
                    updateClock();
                    setInterval(updateClock, 1000);
                })();
                </script>


                <!-- Features Grid -->
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="bg-slate-900/50 p-5 rounded-xl border border-slate-700 hover:border-purple-500/50 transition-all group">
                        <div class="flex items-center gap-3 mb-4">
                            <div class="w-10 h-10 rounded-lg bg-purple-900/30 flex items-center justify-center text-purple-400">🖼️</div>
                            <h4 class="font-bold">Privacy Guard (Metadata)</h4>
                        </div>
                        <p class="text-[11px] text-gray-500 mb-4 h-8">حذف البيانات المخفية (EXIF) من الصور لحماية خصوصيتك عند المشاركة.</p>
                        <input type="file" id="metadataFile" class="hidden" accept="image/*" onchange="processMetadata()">
                        <button onclick="document.getElementById('metadataFile').click()" class="w-full py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-sm transition-all border border-slate-700">تنظيف صورة 🧹</button>
                    </div>
                    
                    <div class="bg-slate-900/50 p-5 rounded-xl border border-slate-700 hover:border-blue-500/50 transition-all group">
                        <div class="flex items-center gap-3 mb-4">
                            <div class="w-10 h-10 rounded-lg bg-blue-900/30 flex items-center justify-center text-blue-400">🕵️‍♂️</div>
                            <h4 class="font-bold">Image OSINT Intel</h4>
                        </div>
                        <p class="text-[11px] text-gray-500 mb-4 h-8">استخراج احداثيات GPS الأجهزة والتواريخ الفائتة المخفية في الصورة.</p>
                        <input type="file" id="osintFile" class="hidden" accept="image/*" onchange="processExifOsint()">
                        <button onclick="document.getElementById('osintFile').click()" class="w-full py-2 bg-blue-900/40 hover:bg-blue-800/50 text-blue-400 rounded-lg text-sm transition-all border border-blue-800/50">تحليل الصورة 👁️</button>
                        <div id="osintResult" class="hidden mt-3 p-3 bg-black/50 border border-slate-700 rounded text-[10px] font-mono whitespace-pre-wrap max-h-32 overflow-y-auto w-full" dir="ltr"></div>
                    </div>

                    <div class="bg-slate-900/50 p-5 rounded-xl border border-slate-700 hover:border-purple-500/50 transition-all group text-right">
                        <div class="flex items-center justify-end gap-3 mb-4">
                            <h4 class="font-bold">Stegano-Vault (تشفير الصور)</h4>
                            <div class="w-10 h-10 rounded-lg bg-purple-900/30 flex items-center justify-center text-purple-400">🕵️</div>
                        </div>
                        <p class="text-[11px] text-gray-500 mb-4 h-8">إخفاء رسائل نصية مشفرة داخل بكسلات الصور بشكل غير مرئي تماماً.</p>
                        <div class="flex gap-2">
                             <button onclick="showStego('encode')" class="flex-1 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-sm transition-all border border-slate-700">إخفاء نص 🔒</button>
                             <button onclick="showStego('decode')" class="flex-1 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-sm transition-all border border-slate-700">استخراج 🔓</button>
                        </div>
                    </div>
                </div>

                <!-- Phase 4 System Defense Grid -->
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                    <!-- USB Guardian -->
                    <div class="bg-teal-900/10 p-5 rounded-xl border border-teal-900/40 hover:border-teal-500/50 transition-all group relative overflow-hidden">
                        <div class="absolute top-0 right-0 w-16 h-16 bg-teal-600/10 rounded-bl-full z-0 pointer-events-none"></div>
                        <div class="flex items-center gap-3 mb-3 relative z-10">
                            <div class="w-10 h-10 rounded-lg bg-teal-900/30 flex items-center justify-center text-teal-500 text-lg">🛡️</div>
                            <div>
                                <h4 class="font-bold text-teal-400">حارس USB (USB Guardian)</h4>
                                <span id="usbStatusBadge" class="text-[9px] px-2 py-0.5 rounded-full bg-slate-800 text-gray-400 border border-slate-700">متوقف</span>
                            </div>
                        </div>
                        <p class="text-[11px] text-gray-400 mb-4 h-10 relative z-10">مراقبة المنافذ والتدخل التلقائي لفحص أي فلاش ميموري (USB) بمجرد تركيبه للكشف عن فيروسات التشغيل التلقائي.</p>
                        
                        <div class="flex gap-2 relative z-10">
                            <button onclick="toggleUsbGuardian('start')" class="flex-1 py-2 bg-teal-900/40 hover:bg-teal-800 text-teal-300 rounded-lg text-sm transition-all border border-teal-800/50">تفعيل الحارس</button>
                            <button onclick="toggleUsbGuardian('stop')" class="flex-1 py-2 bg-slate-800 hover:bg-slate-700 text-gray-400 rounded-lg text-sm transition-all border border-slate-700">إيقاف</button>
                        </div>
                    </div>
                    
                    <!-- File Integrity Monitor (FIM) -->
                    <div class="bg-orange-900/10 p-5 rounded-xl border border-orange-900/40 hover:border-orange-500/50 transition-all group relative overflow-hidden">
                        <div class="absolute top-0 right-0 w-16 h-16 bg-orange-600/10 rounded-bl-full z-0 pointer-events-none"></div>
                        <div class="flex items-center gap-3 mb-3 relative z-10">
                            <div class="w-10 h-10 rounded-lg bg-orange-900/30 flex items-center justify-center text-orange-500 text-lg">⚖️</div>
                            <div>
                                <h4 class="font-bold text-orange-400">مراقب تكامل الملفات (FIM)</h4>
                                <span id="fimStatusBadge" class="text-[9px] px-2 py-0.5 rounded-full bg-slate-800 text-gray-400 border border-slate-700">متوقف</span>
                            </div>
                        </div>
                        <p class="text-[11px] text-gray-400 mb-3 h-8 relative z-10">رصد التغييرات الطفيفة في ملفاتك الحساسة لمنع حقن الأكواد الخبيثة.</p>
                        
                        <div class="flex gap-2 relative z-10 flex-col">
                            <div class="flex gap-2">
                                <input type="text" id="fimTargetPath" class="flex-1 p-2 text-left text-[10px] font-mono rounded-lg bg-black border border-orange-900/50 text-orange-300 outline-none" placeholder="C:\\Windows\\System32\\drivers\\etc\\hosts" value="C:\\Windows\\System32\\drivers\\etc\\hosts">
                            </div>
                            <div class="flex gap-2 mt-1">
                                <button onclick="toggleFim('start')" class="flex-1 py-2 bg-orange-900/40 hover:bg-orange-800 text-orange-300 rounded-lg text-sm transition-all border border-orange-800/50">بدء المراقبة</button>
                                <button onclick="toggleFim('stop')" class="flex-1 py-2 bg-slate-800 hover:bg-slate-700 text-gray-400 rounded-lg text-sm transition-all border border-slate-700">إيقاف</button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 2FA Tool -->
                <div class="bg-black/40 rounded-xl border border-slate-800 p-6 mb-6">
                    <h2 class="text-xl font-bold text-purple-400 mb-4 border-b border-slate-700 pb-2">🔐 المصادقة الثنائية (2FA)</h2>
                    <button onclick="generate2FA()" class="titan-gradient px-4 py-2 rounded-lg font-bold mb-4">إنشاء مفتاح 2FA جديد</button>
                    
                    <div id="tfaResult" class="hidden bg-slate-900/80 p-6 rounded-xl border border-slate-700 flex flex-col items-center">
                        <p class="text-gray-400 mb-4 text-center">امسح رمز الاستجابة السريعة (QR Code) باستخدام تطبيق مثل Google Authenticator</p>
                        <img id="qrCodeImg" src="" alt="QR Code" class="w-48 h-48 bg-white p-2 rounded-lg mb-4">
                        <div class="bg-slate-800 p-3 rounded-xl w-full text-center mb-6 border border-slate-700">
                            <span class="text-xs text-gray-500 block mb-1">المفتاح السري (لإدخاله يدوياً):</span>
                            <code id="tfaSecret" class="text-purple-400 font-mono text-xl tracking-widest"></code>
                        </div>
                        
                        <div class="w-full border-t border-slate-700 pt-4">
                            <label class="block text-sm text-gray-400 mb-2">التحقق من الرمز:</label>
                            <div class="flex gap-2">
                                <input type="text" id="tfaCodeInput" placeholder="مكون من 6 أرقام..." class="flex-1 p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-purple-500 outline-none text-center tracking-widest text-lg font-mono">
                                <button onclick="verify2FA()" class="bg-green-600 hover:bg-green-700 px-6 py-3 rounded-xl font-bold transition-all">تحقق</button>
                            </div>
                        </div>
                    </div>
                </div>

            </div>

                </div>

                <!-- ===== CRYPTOGRAPHY SECTION ===== -->
                <div id="crypt-section" class="hidden">
                    <div class="space-y-6">
                        <div>
                            <label class="block text-sm text-gray-400 mb-2">1. مفتاح التشفير (كلمة السر):</label>
                            <input type="password" id="cryptKey" class="w-full p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-purple-500 outline-none">
                        </div>
                        <hr class="border-slate-700">
                        <div>
                            <label class="block text-sm text-gray-400 mb-2 text-purple-400 font-bold italic">تشفير نصوص:</label>
                            <textarea id="cryptText" rows="3" class="w-full p-3 rounded-xl bg-slate-900 border border-slate-700 mb-2 text-sm outline-none" placeholder="اكتب النص هنا..."></textarea>
                            <div class="flex gap-2">
                                <button onclick="processText('encrypt')" class="flex-1 titan-gradient p-2 rounded-lg font-bold">تشفير النص</button>
                                <button onclick="processText('decrypt')" class="flex-1 bg-slate-700 p-2 rounded-lg font-bold">فك التشفير</button>
                            </div>
                        </div>
                        <hr class="border-slate-700">
                        <div>
                            <label class="block text-sm text-gray-400 mb-2 text-purple-400 font-bold italic">تشفير ملفات:</label>
                            <input type="file" id="fileInput" class="block w-full text-sm text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-purple-600 file:text-white hover:file:bg-purple-700">
                            <div class="flex gap-2 mt-3">
                                <button onclick="processFile('encrypt')" class="flex-1 titan-gradient p-2 rounded-lg font-bold">تشفير الملف</button>
                                <button onclick="processFile('decrypt')" class="flex-1 bg-slate-700 p-2 rounded-lg font-bold">فك تشفير الملف</button>
                            </div>
                        </div>

                        <hr class="border-slate-700 mt-5 mb-5">
                        <div>
                            <label class="block text-sm text-gray-400 mb-2 text-purple-400 font-bold italic">حماية ملفات PDF بكلمة سر:</label>
                            <input type="password" id="pdfPass" placeholder="أدخل كلمة السر..." class="w-full p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-purple-500 outline-none mb-3 text-center tracking-widest">
                            <input type="file" id="pdfFileInput" accept="application/pdf" class="block w-full text-sm text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-red-900/40 file:text-red-400 hover:file:bg-red-800/60 border border-slate-700 p-2 rounded-xl">
                            <div class="flex gap-2 mt-4">
                                <button onclick="processPdf('lock')" class="flex-1 bg-red-900/50 hover:bg-red-800 text-red-400 font-bold p-3 rounded-xl transition-all border border-red-900/30 shadow-[0_0_15px_rgba(239,68,68,0.15)] flex justify-center items-center gap-2">قفل الملف 🔒</button>
                                <button onclick="processPdf('unlock')" class="flex-1 bg-green-900/50 hover:bg-green-800 text-green-400 font-bold p-3 rounded-xl transition-all border border-green-900/30 shadow-[0_0_15px_rgba(34,197,94,0.15)] flex justify-center items-center gap-2">فك الحماية 🔓</button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- ===== AUDIO STEGANOGRAPHY SECTION ===== -->
                <div id="audio-section" class="hidden space-y-6">
                    <h2 class="text-xl font-bold text-blue-400 border-b border-slate-700 pb-2">🎵 إخفاء البيانات في الصوت (Audio Stegano)</h2>
                    <div class="bg-slate-900/50 p-4 rounded-2xl border border-cyan-500/20 space-y-3">
                        <div class="flex flex-wrap items-center gap-2">
                            <button onclick="startAudioRecording()" id="audioRecStartBtn" class="px-4 py-2 bg-cyan-700 hover:bg-cyan-600 rounded-lg text-xs font-bold">🎙️ بدء التسجيل</button>
                            <button onclick="stopAudioRecording()" id="audioRecStopBtn" class="px-4 py-2 bg-red-700 hover:bg-red-600 rounded-lg text-xs font-bold" disabled>⏹️ إيقاف التسجيل</button>
                            <span id="audioRecStatus" class="text-xs text-cyan-300">جاهز للتسجيل من الميكروفون</span>
                        </div>
                        <audio id="audioRecordedPreview" controls class="w-full hidden"></audio>
                        <div class="text-[11px] text-gray-500">يمكنك التسجيل مباشرة ثم إخفاء النص المشفر داخل التسجيل بدون رفع ملف يدوي.</div>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div class="bg-slate-900/50 p-6 rounded-2xl border border-blue-500/20">
                            <label class="block text-sm text-blue-400 mb-3 font-bold">🛠️ تشفير (إخفاء):</label>
                            <input type="file" id="audioFileEncrypt" accept=".wav, .mp3, .ogg, .webm, .m4a, .aac" class="hidden" onchange="document.getElementById('audioEncryptName').innerText = this.files[0].name">
                            <label for="audioFileEncrypt" class="w-full text-xs text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-xs file:font-semibold file:bg-blue-600/10 file:text-blue-400 hover:file:bg-blue-600/20 mb-4 cursor-pointer flex items-center justify-center p-2 rounded-xl border border-blue-600/30">
                                <span id="audioEncryptName" class="truncate">اختر ملف صوتي أو استخدم التسجيل المباشر</span>
                            </label>
                            <textarea id="audioSecretText" placeholder="أدخل النص السري هنا..." class="w-full h-24 p-3 rounded-xl bg-slate-950 border border-slate-800 text-sm focus:border-blue-500 outline-none mb-4"></textarea>
                            <input type="password" id="audioSecretPass" placeholder="كلمة سر لتشفير النص قبل الإخفاء (اختياري لكن موصى به)" class="w-full p-3 rounded-xl bg-slate-950 border border-slate-800 text-sm focus:border-blue-500 outline-none mb-4">
                            <button onclick="processAudio('encode')" class="w-full py-3 bg-blue-600 hover:bg-blue-500 rounded-xl font-bold transition-all shadow-lg shadow-blue-900/20">حفظ النص في الملف 💾</button>
                        </div>
                        <div class="bg-slate-900/50 p-6 rounded-2xl border border-purple-500/20">
                            <label class="block text-sm text-purple-400 mb-3 font-bold">🔍 فك التشفير (استخراج):</label>
                            <input type="file" id="audioFileDecrypt" accept=".wav, .mp3, .ogg, .webm, .m4a, .aac" class="hidden" onchange="document.getElementById('audioDecryptName').innerText = this.files[0].name">
                            <label for="audioFileDecrypt" class="w-full text-xs text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-xs file:font-semibold file:bg-purple-600/10 file:text-purple-400 hover:file:bg-purple-600/20 mb-4 cursor-pointer flex items-center justify-center p-2 rounded-xl border border-purple-600/30">
                                <span id="audioDecryptName" class="truncate">اختر ملف صوتي للتحليل</span>
                            </label>
                            <input type="password" id="audioDecodePass" placeholder="كلمة سر فك النص (إذا كان مشفراً)" class="w-full p-3 rounded-xl bg-slate-950 border border-slate-800 text-sm focus:border-purple-500 outline-none mb-4">
                            <div id="audioDecodedResult" class="w-full h-24 p-3 rounded-xl bg-slate-950 border border-slate-800 text-sm overflow-y-auto mb-4 text-gray-400 font-mono italic">سيظهر النص المستخرج هنا...</div>
                            <button onclick="processAudio('decode')" class="w-full py-3 bg-purple-600 hover:bg-purple-500 rounded-xl font-bold transition-all shadow-lg shadow-purple-900/20">استخراج النص السري 🔑</button>
                        </div>
                    </div>
                </div>

                <!-- ===== VIDEO STEGANOGRAPHY SECTION ===== -->
                <div id="video-section" class="hidden space-y-6">
                    <h2 class="text-xl font-bold text-rose-400 border-b border-slate-700 pb-2">🎬 فحص وإخفاء البيانات داخل الفيديو</h2>
                    <div class="bg-slate-900/50 p-4 rounded-2xl border border-rose-500/20 space-y-3">
                        <label class="block text-sm text-rose-400 font-bold">🧪 فحص مقطع فيديو:</label>
                        <input type="file" id="videoScanFile" accept="video/*" class="block w-full text-xs text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-xs file:font-semibold file:bg-rose-600/10 file:text-rose-400 hover:file:bg-rose-600/20 border border-slate-700 p-2 rounded-xl">
                        <button onclick="scanVideoClip()" class="w-full py-2 bg-rose-700/40 hover:bg-rose-700/60 rounded-lg text-sm font-bold border border-rose-700/40">فحص خصائص الفيديو 🔍</button>
                        <pre id="videoScanResult" class="hidden p-3 bg-black/50 rounded-xl border border-slate-800 text-[11px] text-rose-200 whitespace-pre-wrap overflow-x-auto max-h-44"></pre>
                    </div>

                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div class="bg-slate-900/50 p-6 rounded-2xl border border-cyan-500/20">
                            <label class="block text-sm text-cyan-400 mb-3 font-bold">🛠️ إخفاء نص داخل الفيديو:</label>
                            <input type="file" id="videoFileEncrypt" accept="video/*" class="block w-full text-xs text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-xs file:font-semibold file:bg-cyan-600/10 file:text-cyan-400 hover:file:bg-cyan-600/20 border border-slate-700 p-2 rounded-xl mb-4">
                            <textarea id="videoSecretText" placeholder="اكتب النص المراد إخفاؤه داخل الفيديو..." class="w-full h-24 p-3 rounded-xl bg-slate-950 border border-slate-800 text-sm focus:border-cyan-500 outline-none mb-4"></textarea>
                            <input type="password" id="videoSecretPass" placeholder="كلمة سر لتشفير النص قبل الإخفاء (اختياري)" class="w-full p-3 rounded-xl bg-slate-950 border border-slate-800 text-sm focus:border-cyan-500 outline-none mb-4">
                            <button onclick="processVideo('encode')" class="w-full py-3 bg-cyan-600 hover:bg-cyan-500 rounded-xl font-bold transition-all shadow-lg shadow-cyan-900/20">تشفير وإخفاء النص 💾</button>
                        </div>

                        <div class="bg-slate-900/50 p-6 rounded-2xl border border-amber-500/20">
                            <label class="block text-sm text-amber-400 mb-3 font-bold">🔓 استخراج وفك التشفير:</label>
                            <input type="file" id="videoFileDecrypt" accept="video/*" class="block w-full text-xs text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-xs file:font-semibold file:bg-amber-600/10 file:text-amber-400 hover:file:bg-amber-600/20 border border-slate-700 p-2 rounded-xl mb-4">
                            <input type="password" id="videoDecodePass" placeholder="كلمة سر فك النص (إذا كان مشفراً)" class="w-full p-3 rounded-xl bg-slate-950 border border-slate-800 text-sm focus:border-amber-500 outline-none mb-4">
                            <div id="videoDecodedResult" class="w-full h-24 p-3 rounded-xl bg-slate-950 border border-slate-800 text-sm overflow-y-auto mb-4 text-gray-400 font-mono italic">سيظهر النص المستخرج هنا...</div>
                            <button onclick="processVideo('decode')" class="w-full py-3 bg-amber-600 hover:bg-amber-500 rounded-xl font-bold transition-all shadow-lg shadow-amber-900/20">استخراج النص 🔑</button>
                        </div>
                    </div>

                    <div class="bg-slate-900/50 p-6 rounded-2xl border border-emerald-500/20 space-y-4">
                        <label class="block text-sm text-emerald-400 font-bold">🔐 تشفير ملف الفيديو بالكامل (وليس النص فقط):</label>
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <input type="file" id="videoFileCrypt" accept="video/*,.titan" class="block w-full text-xs text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-xs file:font-semibold file:bg-emerald-600/10 file:text-emerald-400 hover:file:bg-emerald-600/20 border border-slate-700 p-2 rounded-xl">
                            <input type="password" id="videoFileCryptPass" placeholder="كلمة سر تشفير/فك ملف الفيديو" class="w-full p-3 rounded-xl bg-slate-950 border border-slate-800 text-sm focus:border-emerald-500 outline-none">
                        </div>
                        <div class="flex flex-col md:flex-row gap-3">
                            <button onclick="processVideoFile('encrypt')" class="flex-1 py-3 bg-emerald-700/60 hover:bg-emerald-600 rounded-xl font-bold transition-all border border-emerald-700/40">تشفير الملف الكامل 📦</button>
                            <button onclick="processVideoFile('decrypt')" class="flex-1 py-3 bg-lime-700/60 hover:bg-lime-600 rounded-xl font-bold transition-all border border-lime-700/40">فك تشفير الملف الكامل 📂</button>
                        </div>
                        <div class="text-[11px] text-gray-500">ينتج ملف مشفر بامتداد .titan ويمكن استعادته بنفس كلمة السر.</div>
                    </div>
                </div>
            <!-- ===== VAULT SECTION ===== -->
            <div id="vault-section" class="hidden space-y-4">
                <h2 class="text-xl font-bold text-yellow-400 border-b border-yellow-900/50 pb-2 flex items-center gap-2">🗄️ قبو كلمات المرور الآمن</h2>

                <!-- === FIRST-TIME SETUP PANEL (shown if user has no vault password yet) === -->
                <div id="vault-setup" class="hidden bg-gradient-to-br from-yellow-900/20 to-orange-900/10 rounded-2xl border border-yellow-800/40 p-6 shadow-[0_0_30px_rgba(234,179,8,0.08)]">
                    <div class="text-center mb-5">
                        <div class="text-4xl mb-2">🔐</div>
                        <h3 class="text-lg font-bold text-yellow-400">إعداد كلمة سر قبوك لأول مرة</h3>
                        <p class="text-xs text-gray-400 mt-1">هذه الكلمة ستُستخدم لتشفير قبوك الشخصي. لا يمكن استعادتها إذا نسيتها!</p>
                    </div>
                    <div class="space-y-3 max-w-sm mx-auto">
                        <div>
                            <label class="block text-xs text-gray-400 mb-1">كلمة سر القبو الجديدة</label>
                            <input type="password" id="vaultSetupPass1" placeholder="أدخل كلمة سر قوية..." class="w-full p-3 rounded-xl bg-slate-900 border border-yellow-800/50 focus:ring-2 focus:ring-yellow-500 outline-none text-center tracking-widest text-lg font-mono">
                        </div>
                        <div>
                            <label class="block text-xs text-gray-400 mb-1">تأكيد كلمة السر</label>
                            <input type="password" id="vaultSetupPass2" placeholder="أعد إدخال الكلمة..." class="w-full p-3 rounded-xl bg-slate-900 border border-yellow-800/50 focus:ring-2 focus:ring-yellow-500 outline-none text-center tracking-widest text-lg font-mono">
                        </div>
                        <div id="vaultSetupError" class="hidden text-red-400 text-xs p-3 bg-red-900/20 border border-red-800/40 rounded-xl text-center"></div>
                        <button onclick="setVaultPassword()" class="w-full py-3 bg-gradient-to-r from-yellow-600 to-orange-600 hover:from-yellow-500 hover:to-orange-500 rounded-xl font-bold text-white transition-all shadow-[0_0_20px_rgba(234,179,8,0.25)]">
                            🔑 تأكيد وإنشاء القبو
                        </button>
                    </div>
                </div>

                <!-- === VAULT LOGIN PANEL === -->
                <div id="vault-login" class="bg-slate-900/70 rounded-2xl border border-yellow-900/40 p-6">
                    <p class="text-gray-400 text-sm mb-4 text-center">أدخل كلمة سر قبوك للوصول إلى بياناتك المحفوظة</p>
                    <div class="flex gap-2 max-w-md mx-auto mb-4">
                        <input type="password" id="vaultMasterKey" placeholder="كلمة سر القبو..." class="flex-1 p-3 rounded-xl bg-slate-900 border border-yellow-800/50 focus:ring-2 focus:ring-yellow-500 outline-none font-mono tracking-widest text-lg text-center">
                        <button onclick="unlockVault()" class="bg-yellow-600 hover:bg-yellow-500 px-6 rounded-xl font-bold transition-all">فتح 🔓</button>
                    </div>
                    <div class="text-center">
                        <button onclick="showVaultForgot()" class="text-yellow-500/60 hover:text-yellow-500 text-xs font-bold transition-all underline decoration-dotted">نسيت كلمة سر القبو؟</button>
                    </div>
                </div>

                <!-- === VAULT FORGOT MODAL === -->
                <div id="vault-forgot-modal" style="display:none;position:fixed;inset:0;z-index:999999;background:rgba(0,0,0,0.85);align-items:center;justify-content:center;">
                    <div style="background:#0a0a1e;border:1px solid rgba(234,179,8,0.4);border-radius:20px;padding:2rem;max-width:420px;width:90%;box-shadow:0 0 60px rgba(234,179,8,0.2);">
                        <div id="vf-step1">
                            <div style="text-align:center;margin-bottom:1.5rem;">
                                <div style="font-size:2rem">📧</div>
                                <h3 style="color:#fbbf24;font-weight:700;margin:0.5rem 0;">استعادة كلمة سر القبو</h3>
                                <p style="color:#6b7280;font-size:0.75rem;">سيصلك كود تحقق على إيميلك المسجل لإعادة تعيين كلمة السر.</p>
                            </div>
                            <button onclick="doVaultForgotSend()" id="vf-send-btn" style="width:100%;padding:0.75rem;background:linear-gradient(135deg,#d97706,#b45309);border:none;border-radius:12px;color:white;font-weight:700;cursor:pointer;font-size:0.9rem;">إرسال الكود 📲</button>
                            <button onclick="closeVaultForgot()" style="width:100%;margin-top:0.75rem;background:transparent;border:none;color:#4b5563;font-size:0.8rem;cursor:pointer;">إلغاء</button>
                        </div>

                        <div id="vf-step2" style="display:none;">
                            <div style="text-align:center;margin-bottom:1.5rem;">
                                <div style="font-size:2rem">🔢</div>
                                <h3 style="color:#fbbf24;font-weight:700;margin:0.5rem 0;">أدخل الكود</h3>
                                <p style="color:#6b7280;font-size:0.75rem;">أدخل الكود المرسل إلى إيميلك (6 أرقام).</p>
                            </div>
                            <input id="vf-otp" type="text" placeholder="000000" maxlength="6" style="width:100%;padding:1rem;background:#050510;border:1px solid #d97706;border-radius:12px;color:white;font-size:1.8rem;text-align:center;letter-spacing:0.5em;margin-bottom:1.5rem;outline:none;">
                            <button onclick="doVaultForgotVerify()" style="width:100%;padding:0.75rem;background:linear-gradient(135deg,#d97706,#b45309);border:none;border-radius:12px;color:white;font-weight:700;cursor:pointer;font-size:0.9rem;">تحقق ✅</button>
                        </div>

                        <div id="vf-step3" style="display:none;">
                            <div style="text-align:center;margin-bottom:1.5rem;">
                                <div style="font-size:2rem">🔐</div>
                                <h3 style="color:#fbbf24;font-weight:700;margin:0.5rem 0;">كلمة سر جديدة</h3>
                            </div>
                            <input id="vf-new-pass" type="password" placeholder="كلمة السر الجديدة..." style="width:100%;padding:0.8rem;background:#050510;border:1px solid #d97706;border-radius:12px;color:white;margin-bottom:1rem;outline:none;">
                            <input id="vf-new-pass2" type="password" placeholder="تأكيد كلمة السر..." style="width:100%;padding:0.8rem;background:#050510;border:1px solid #d97706;border-radius:12px;color:white;margin-bottom:1.5rem;outline:none;">
                            <button onclick="doVaultForgotReset()" style="width:100%;padding:0.75rem;background:linear-gradient(135deg,#d97706,#b45309);border:none;border-radius:12px;color:white;font-weight:700;cursor:pointer;font-size:0.9rem;">حفظ كلمة السر الجديدة 💾</button>
                        </div>
                        <div id="vf-error" style="display:none;margin-top:1rem;color:#f87171;font-size:0.75rem;text-align:center;padding:0.5rem;background:rgba(239,68,68,0.1);border-radius:8px;"></div>
                    </div>
                </div>


                <!-- === VAULT CONTENT (shown after unlock) === -->
                <div id="vault-content" class="hidden space-y-4">


                    <!-- 2. Action Bar -->
                    <div class="flex items-center justify-between gap-2 py-2 px-1 border-y border-slate-800">
                        <!-- Left: Lock -->
                        <button onclick="lockVault()" class="flex items-center gap-2 px-4 py-2 bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded-xl text-sm font-bold border border-red-900/40 transition-all">
                            🔒 <span>قفل القبو</span>
                        </button>
                        <!-- Right: Backup · Restore · Security Qs -->
                        <div class="flex items-center gap-2">
                            <button onclick="backupVault()" title="تصدير نسخة احتياطية" class="flex items-center gap-1.5 px-3 py-2 bg-blue-900/30 hover:bg-blue-800/50 text-blue-400 rounded-xl text-xs font-bold border border-blue-900/40 transition-all whitespace-nowrap">
                                💾 <span class="hidden sm:inline">نسخة احتياطية</span>
                            </button>
                            <label title="استعادة النسخة الاحتياطية" class="flex items-center gap-1.5 px-3 py-2 bg-purple-900/30 hover:bg-purple-800/50 text-purple-400 rounded-xl text-xs font-bold border border-purple-900/40 transition-all whitespace-nowrap cursor-pointer">
                                📂 <span class="hidden sm:inline">استعادة</span>
                                <input type="file" class="hidden" id="vaultRestoreFile" accept=".bak" onchange="restoreVault()">
                            </label>
                        </div>
                    </div>



                    <!-- 3. Password Vault (items — last) -->
                    <div class="bg-slate-900/60 rounded-xl border border-slate-700 p-4 space-y-3">
                        <h3 class="text-sm font-bold text-yellow-400 flex items-center gap-2">🗄️ قبو كلمات المرور</h3>
                        <div class="grid grid-cols-1 md:grid-cols-3 gap-2">
                            <input type="text" id="vaultItemTitle" placeholder="الموقع / الخدمة" class="p-2 rounded-lg bg-slate-800 border border-slate-700 text-sm outline-none focus:ring-1 focus:ring-yellow-500">
                            <input type="text" id="vaultItemUsername" placeholder="اسم المستخدم / الإيميل" class="p-2 rounded-lg bg-slate-800 border border-slate-700 text-sm outline-none focus:ring-1 focus:ring-yellow-500">
                            <input type="password" id="vaultItemPass" placeholder="كلمة السر" class="p-2 rounded-lg bg-slate-800 border border-slate-700 text-sm outline-none focus:ring-1 focus:ring-yellow-500">
                        </div>
                        <button onclick="addVaultItem()" class="w-full py-2 bg-yellow-700/50 hover:bg-yellow-600/50 border border-yellow-700/50 rounded-lg font-bold text-yellow-300 text-sm transition-all">إضافة ➕</button>
                        <div id="vaultItemsContainer" class="space-y-2 max-h-80 overflow-y-auto custom-scrollbar pr-1 mt-1"></div>
                    </div>

                </div>
                <!-- /vault-content -->

            </div>
            <!-- /vault-section -->

            <div id="tools-section" class="hidden space-y-8">
                <!-- IP Tool With Radar -->
                <div>
                    <h2 class="text-xl font-bold text-purple-400 mb-4 border-b border-slate-700 pb-2">🌐 فحص واستخبارات IP</h2>
                    <div class="flex gap-2 mb-4">
                        <input type="text" id="ipInput" placeholder="أدخل IP (أو اتركه فارغاً لفحص اتصالك)" class="flex-1 p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-purple-500 outline-none font-mono">
                        <button onclick="checkIP()" class="titan-gradient px-6 py-3 rounded-xl font-bold border border-purple-400/30 hover:shadow-[0_0_15px_rgba(168,85,247,0.5)] transition-all">تتبع الهدف 🎯</button>
                    </div>
                    
                    <div id="ipResult" class="hidden p-6 bg-slate-900/90 rounded-xl border border-slate-700 shadow-[0_0_25px_rgba(0,0,0,0.6)] relative overflow-hidden">
                        <div class="flex flex-col md:flex-row gap-8 relative z-10 items-center justify-between min-h-[160px]">
                            <!-- قسم البيانات -->
                            <div id="ipDataBox" class="flex-1 w-full order-2 md:order-1 transition-all"></div>
                            
                            <!-- الرادار -->
                            <div id="radarContainer" class="hidden md:flex flex-col items-center justify-center border-r border-slate-700/50 pr-8 pl-4 order-1 md:order-2">
                                <div class="radar-box">
                                    <div class="radar-cross"></div>
                                    <div class="radar-target"></div>
                                </div>
                                <p class="text-center text-green-400 text-[10px] mt-4 font-mono uppercase tracking-[0.2em] animate-pulse">Target Acquired</p>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Email Validator & Leak Scanner -->
                <div>
                    <h2 class="text-xl font-bold text-red-500 mb-4 border-b border-slate-700 pb-2 flex items-center gap-2">
                        <span>📧</span> فحص الإيميل (Email Intelligence)
                    </h2>
                    <p class="text-xs text-gray-400 mb-3">فحص البريد الإلكتروني للتأكد من صلاحيته، هل هو بريد وهمي (Disposable)، واحتمالية كونه احتيالياً (Fraud Score).</p>
                    <div class="flex gap-2 mb-4">
                        <input type="email" id="phishUrlInput" placeholder="أدخل البريد الإلكتروني لفحصه..." class="flex-1 p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-red-500 outline-none font-mono text-left" dir="ltr">
                        <button onclick="checkPhishing()" class="bg-red-900/40 hover:bg-red-800 px-6 py-3 rounded-xl font-bold border border-red-800/50 transition-all text-red-400 flex items-center justify-center min-w-[140px]">
                            فحص الإيميل
                        </button>
                    </div>
                    <div id="phishResult" class="hidden p-4 bg-slate-900/80 rounded-xl border border-slate-700 text-sm mb-6"></div>
                    
                    <h3 class="font-bold text-orange-500 mb-3 text-sm flex items-center gap-2">
                        <span>🕵️</span> فحص تسريبات الإيميل وكلمة السر (Data Leaks)
                    </h3>
                    <p class="text-xs text-gray-400 mb-3">تحقق مما إذا كان بريدك الإلكتروني وكلمة السر المحددة قد تم تسريبها معاً في اختراقات سابقة للبيانات.</p>
                    <div class="bg-slate-900/50 p-4 rounded-xl border border-slate-700/50">
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                            <input type="email" id="leakEmailInput" placeholder="البريد الإلكتروني..." class="p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-orange-500 outline-none text-sm font-mono text-left" dir="ltr">
                            <input type="password" id="leakPassInput" placeholder="كلمة السر للتحقق من تسريبها مع الإيميل..." class="p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-orange-500 outline-none text-sm font-mono text-left" dir="ltr">
                        </div>
                        <button onclick="checkEmailPassLeak()" class="w-full bg-orange-900/40 hover:bg-orange-800 px-6 py-3 rounded-xl font-bold border border-orange-800/50 transition-all text-orange-400 flex items-center justify-center">
                            فحص التسريبات
                        </button>
                        <div id="leakEmailPassResult" class="hidden mt-4 p-4 bg-slate-900/80 rounded-xl border border-slate-700 text-sm"></div>
                    </div>
                </div>

                <!-- URL Scanner & Phishing Detection -->
                <div>
                    <h2 class="text-xl font-bold text-blue-500 mb-4 border-b border-slate-700 pb-2 flex items-center gap-2">
                        <span>🌐</span> فحص الروابط المشبوهة (URL/Phishing Scanner)
                    </h2>
                    <p class="text-xs text-gray-400 mb-3">فحص دقيق للروابط والمواقع لاكتشاف صفحات التصيد (Phishing) والبرمجيات الخبيثة وتصنيف الخطورة.</p>
                    <div class="flex gap-2 mb-4">
                        <input type="url" id="urlInput" placeholder="أدخل الرابط لفحصه (مثل https://example.com)..." class="flex-1 p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-blue-500 outline-none font-mono text-left" dir="ltr">
                        <button onclick="checkUrl()" class="bg-blue-900/40 hover:bg-blue-800 px-6 py-3 rounded-xl font-bold border border-blue-800/50 transition-all text-blue-400 flex items-center justify-center min-w-[140px]">
                            فحص الرابط
                        </button>
                    </div>
                    <div id="urlResult" class="hidden p-4 bg-slate-900/80 rounded-xl border border-slate-700 text-sm"></div>
                </div>

                <!-- Malware URL & File Scanner -->
                <div>
                    <h2 class="text-xl font-bold text-rose-500 mb-4 border-b border-slate-700 pb-2 flex items-center gap-2">
                        <span>🦠</span> فحص البرمجيات الخبيثة (Malware Scanner)
                    </h2>
                    <p class="text-xs text-gray-400 mb-3">ابحث عن الفيروسات والبرمجيات الخبيثة المخفية في الروابط أو الملفات.</p>
                    
                    <div class="bg-slate-900/50 p-5 rounded-xl border border-slate-700/50 space-y-4">
                        <!-- URL Scan -->
                        <div>
                            <label class="block text-xs text-gray-400 mb-2 font-bold">فحص رابط خبيث:</label>
                            <div class="flex gap-2">
                                <input type="url" id="malwareUrlInput" placeholder="أدخل الرابط لفحصه..." class="flex-1 p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-rose-500 outline-none font-mono text-left" dir="ltr">
                                <button onclick="checkMalwareUrl()" class="bg-rose-900/40 hover:bg-rose-800 px-6 py-3 rounded-xl font-bold border border-rose-800/50 transition-all text-rose-400 flex items-center justify-center min-w-[140px]">
                                    فحص الرابط
                                </button>
                            </div>
                        </div>
                        
                        <!-- Divider -->
                        <div class="flex items-center gap-3">
                            <hr class="flex-1 border-slate-700">
                            <span class="text-xs text-gray-500 font-bold uppercase">أو</span>
                            <hr class="flex-1 border-slate-700">
                        </div>
                        
                        <!-- File Scan -->
                        <div>
                            <label class="block text-xs text-gray-400 mb-2 font-bold">فحص ملف مشبوه:</label>
                            <div class="flex gap-2">
                                <input type="file" id="malwareFileInput" class="w-full text-sm text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-sm file:font-semibold file:bg-rose-900/40 file:text-rose-400 hover:file:bg-rose-800/60 border border-slate-700 p-2 rounded-xl">
                                <button onclick="checkMalwareFile()" class="bg-rose-900/40 hover:bg-rose-800 px-6 py-2 rounded-xl font-bold border border-rose-800/50 transition-all text-rose-400 flex items-center justify-center min-w-[140px]">
                                    رفع وفحص الملف
                                </button>
                            </div>
                        </div>
                    </div>
                    <div id="malwareResult" class="hidden mt-4 p-4 bg-slate-900/80 rounded-xl border border-slate-700 text-sm"></div>
                </div>

                <!-- API Usage Logs (IPQualityScore) -->
                <div>
                    <h2 class="text-xl font-bold text-teal-500 mb-4 border-b border-slate-700 pb-2 flex items-center gap-2">
                        <span>📊</span> سجلات استخدام (API Logs)
                    </h2>
                    <p class="text-xs text-gray-400 mb-3">عرض سجلات العمليات السابقة التي تم إجراؤها عبر حساب IPQualityScore الخاص بك.</p>
                    <div class="bg-slate-900/50 p-4 rounded-xl border border-slate-700/50">
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                            <div>
                                <label class="block text-[10px] text-gray-500 mb-1 uppercase tracking-widest">نوع السجل</label>
                                <select id="ipqsLogType" class="w-full p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-teal-500 outline-none text-sm text-gray-300 appearance-none cursor-pointer">
                                    <option value="proxy" selected>IP / Proxy Checks</option>
                                    <option value="email">Email Checks</option>
                                    <option value="devicetracker">Device Tracker</option>
                                    <option value="mobiletracker">Mobile Tracker</option>
                                </select>
                            </div>
                            <div>
                                <label class="block text-[10px] text-gray-500 mb-1 uppercase tracking-widest">تاريخ البداية (YYYY-MM-DD)</label>
                                <input type="date" id="ipqsLogDate" class="w-full p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-teal-500 outline-none text-sm text-gray-300" value="2024-01-01">
                            </div>
                        </div>
                        <button onclick="fetchIpqsLogs()" class="w-full bg-teal-900/40 hover:bg-teal-800 px-6 py-3 rounded-xl font-bold border border-teal-800/50 transition-all text-teal-400 flex items-center justify-center gap-2">
                            <span>جلب السجلات</span>
                        </button>
                        <div id="ipqsLogsResult" class="hidden mt-4 max-h-[300px] overflow-y-auto custom-scrollbar p-2 bg-slate-950/80 rounded-xl border border-slate-700 text-sm font-mono text-left" dir="ltr"></div>
                    </div>
                </div>

                <!-- Phone Validator & Intelligence -->
                <div>
                    <h2 class="text-xl font-bold text-yellow-500 mb-4 border-b border-slate-700 pb-2 flex items-center gap-2">
                        <span>📱</span> فحص الهاتف (Phone Intelligence)
                    </h2>
                    <p class="text-xs text-gray-400 mb-3">تحليل رقم الهاتف لاكتشاف نوع الخط ومزود الخدمة ودرجة الاحتيال المرتبطة به.</p>
                    <div class="flex flex-col md:flex-row gap-2 mb-4">
                        <input type="tel" id="phoneInput" placeholder="أدخل رقم الهاتف مع الترميز (مثل +962778...)" class="flex-1 p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-yellow-500 outline-none font-mono text-left" dir="ltr">
                        <button onclick="checkPhone()" class="bg-yellow-900/40 hover:bg-yellow-800 px-6 py-3 rounded-xl font-bold border border-yellow-800/50 transition-all text-yellow-400 flex items-center justify-center w-full md:w-auto min-w-[140px]">
                            فحص الرقم
                        </button>
                    </div>
                    <div id="phoneResult" class="hidden p-4 bg-slate-900/80 rounded-xl border border-slate-700 text-sm"></div>
                </div>

                <!-- Local LAN Monitor -->
                <div>
                    <h2 class="text-xl font-bold text-cyan-500 mb-4 border-b border-slate-700 pb-2 flex items-center gap-2">
                        <span>🌐</span> رادار الشبكة المحلية (LAN Monitor)
                    </h2>
                    <p class="text-xs text-gray-400 mb-3">اكتشف جميع الأجهزة المتصلة معك على نفس شبكة Wi-Fi محلياً لاكتشاف المتطفلين.</p>
                    <button id="btnLanScan" onclick="scanLanNetwork()" class="w-full bg-cyan-900/30 hover:bg-cyan-800 px-6 py-3 rounded-xl font-bold border border-cyan-800/50 transition-all text-cyan-400 flex items-center justify-center gap-2 mb-4">
                        <span>مسح الشبكة للبحث عن دخلاء</span>
                        <div id="lanLoader" class="hidden w-4 h-4 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin"></div>
                    </button>
                    <button id="btnLanExport" onclick="exportLanCsv()" class="w-full bg-slate-900/60 hover:bg-slate-800 px-5 py-2.5 rounded-xl font-bold border border-slate-700 transition-all text-slate-300 flex items-center justify-center gap-2 mb-3 disabled:opacity-50 disabled:cursor-not-allowed" disabled>
                        <span>تصدير النتائج CSV</span>
                    </button>
                    <div id="lanResult" class="hidden p-4 bg-slate-900/80 rounded-xl border border-slate-700 max-h-60 overflow-y-auto custom-scrollbar"></div>
                </div>
                <!-- Port Scanner Tool -->
                <div>
                    <h2 class="text-xl font-bold text-purple-400 mb-4 border-b border-slate-700 pb-2 flex items-center gap-2">
                        <span>🔍</span> فحص المنافذ المفتوحة
                    </h2>
                    <div class="flex gap-2 mb-4">
                        <input type="text" id="portIpInput" placeholder="أدخل IP الهدف للبحث عن ثغرات..." class="flex-1 p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-purple-500 outline-none font-mono text-left" dir="ltr">
                        <button id="btnPortScan" onclick="scanPorts()" class="bg-slate-800 hover:bg-slate-700 px-6 py-3 rounded-xl font-bold border border-slate-600 transition-all flex items-center justify-center min-w-[140px] text-gray-300">
                            <span id="scanLabel">فحص المنافذ 📡</span>
                            <div id="scanLoader" class="hidden w-5 h-5 border-2 border-purple-500 border-t-transparent rounded-full animate-spin"></div>
                        </button>
                    </div>
                    
                    <div id="portResult" class="hidden bg-slate-900/80 p-6 rounded-xl border border-slate-700 shadow-lg">
                        <h3 class="font-bold text-gray-300 mb-4 text-sm flex items-center gap-2">
                            نتائج الفحص للهدف: <span id="portScanTarget" class="text-purple-400 font-mono tracking-widest bg-purple-900/20 px-2 py-1 rounded"></span>
                        </h3>
                        <div id="openPortsContainer" class="flex flex-wrap gap-2 text-sm max-h-40 overflow-y-auto custom-scrollbar">
                            <!-- المنافذ برمجياً -->
                        </div>
                    </div>
                </div>

            </div>

            <div id="ghost-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-pink-400 border-b border-slate-700 pb-2 flex items-center gap-2">
                    <span>🔥</span> قنوات الشبح
                </h2>
                <p class="text-xs text-gray-400">دمج كامل بين رسائل لمرة واحدة وغرفة دردشة مشفرة ذات تدمير فوري للرسائل.</p>

                <div class="bg-slate-900/50 p-5 rounded-xl border border-slate-700/50 border-r-4 border-r-orange-500 relative overflow-hidden group">
                    <div class="absolute inset-0 bg-gradient-to-l from-orange-500/5 to-transparent pointer-events-none"></div>
                    <div class="flex items-center gap-3 mb-2 relative z-10">
                        <span class="text-orange-500 text-2xl drop-shadow-[0_0_10px_rgba(249,115,22,0.6)] animate-pulse">💣</span>
                        <h3 class="text-sm font-bold text-gray-200">الرسائل ذاتية التدمير (Burn Notes)</h3>
                    </div>
                    <p class="text-xs text-gray-400 mb-3 relative z-10">رسالة سرية لمرة واحدة، تُحذف فور قراءتها.</p>
                    <textarea id="burnNoteText" rows="3" class="w-full p-3 rounded-xl bg-slate-800 border border-slate-600 focus:ring-1 focus:ring-orange-500 outline-none text-sm mb-3 relative z-10" placeholder="اكتب رسالتك السرية هنا..."></textarea>
                    <button onclick="createBurnNote()" class="w-full bg-gradient-to-r from-orange-600 to-red-600 hover:from-orange-500 hover:to-red-500 text-white font-bold px-4 py-2 rounded-xl transition-all text-sm shadow-[0_0_15px_rgba(234,88,12,0.35)] flex items-center justify-center gap-2 relative z-10">
                        توليد رابط التدمير السري 🔥
                    </button>
                    <div id="burnNoteResult" class="hidden mt-3 p-3 bg-slate-900/80 border border-orange-800/30 rounded-xl flex flex-col md:flex-row items-center justify-between gap-2 relative z-10">
                        <input type="text" id="burnNoteLink" readonly class="w-full bg-black/50 text-orange-400 font-mono text-xs p-2 rounded-lg border border-slate-700/50 focus:outline-none" dir="ltr">
                        <button id="burnCopyBtn" onclick="copyBurnNoteLink()" class="w-full md:w-auto bg-slate-800 hover:bg-slate-700 text-xs px-4 py-2 rounded-lg text-gray-300 transition-colors whitespace-nowrap border border-slate-600 font-bold">نسخ الرابط</button>
                    </div>
                </div>

                <div>
                    <h2 class="text-xl font-bold text-pink-500 mb-4 border-b border-slate-700 pb-2 flex items-center gap-2">
                        <span>🔥</span> غرفة الـ Burn Chat (P2P مشفر)
                    </h2>
                    <p class="text-xs text-gray-400 mb-3">اتصال مشفر آمن لا يحفظ السجلات. الرسالة تُدمّر حرفياً من ذاكرة الخادم في اللحظة التي تُقرأ فيها.</p>

                    <div class="bg-gray-900/80 rounded-xl border border-slate-700 p-4">
                        <div class="flex gap-2 mb-4 bg-black p-3 rounded-lg border border-slate-800 flex-col md:flex-row">
                            <input type="text" id="burnChatId" placeholder="كود الغرفة (Room ID)..." class="flex-1 p-2 rounded bg-slate-900 border border-slate-700 focus:border-pink-500 outline-none text-center font-mono">
                            <input type="password" id="burnChatKey" placeholder="كلمة مرور الغرفة..." class="flex-1 p-2 rounded bg-slate-900 border border-slate-700 focus:border-pink-500 outline-none text-center font-mono" title="كلمة السر الخاصة بدخول الغرفة">
                            <input type="text" id="burnChatUser" placeholder="اسمك الرمزي (Ghost)" class="w-full md:w-1/4 p-2 rounded bg-slate-900 border border-slate-700 focus:border-pink-500 outline-none text-center">
                            <button onclick="joinBurnChat()" class="bg-pink-900/40 hover:bg-pink-800 text-pink-300 px-6 py-2 rounded border border-pink-800/50 transition-all font-bold">انضمام</button>
                        </div>

                        <div id="burnChatDisplay" class="h-64 bg-black rounded-lg border border-pink-900/30 mb-4 p-4 overflow-y-auto flex flex-col gap-2 shadow-inner">
                            <div class="text-center text-gray-600 text-[10px] tracking-widest uppercase mt-auto">-- Secure RAM Storage Only --</div>
                        </div>

                        <div class="flex gap-2">
                            <input type="text" id="burnChatInput" placeholder="اكتب رسالتك السرية هنا..." class="flex-1 p-3 rounded-lg bg-slate-900 border border-slate-700 focus:border-pink-500 outline-none" disabled>
                            <button id="burnChatSendBtn" onclick="sendBurnChat()" class="bg-slate-800 text-gray-500 px-8 rounded-lg font-bold transition-all border border-slate-700" disabled>إرسال</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- ===== OSINT SECTION ===== -->
            <div id="osint-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-indigo-400 border-b border-slate-700 pb-2">🕵️ OSINT Workbench</h2>

                <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
                    <div class="lg:col-span-2 bg-slate-900/60 p-4 rounded-xl border border-indigo-900/40">
                        <h3 class="text-sm font-bold text-indigo-300 mb-2">البحث الموحد (IP / Domain / URL / Email / Phone)</h3>
                        <p class="text-[11px] text-gray-500 mb-3">اكتب أي هدف وسيتم تحليله تلقائياً حسب النوع مع درجة خطورة سريعة.</p>
                        <div class="flex flex-col md:flex-row gap-2">
                            <input id="osintTargetInput" type="text" placeholder="8.8.8.8 أو example.com أو user@mail.com أو +962..." class="flex-1 p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-indigo-500 outline-none font-mono text-left" dir="ltr">
                            <button onclick="runUnifiedOsint()" class="bg-indigo-900/50 hover:bg-indigo-800 px-5 py-3 rounded-xl font-bold border border-indigo-800/50 transition-all text-indigo-300">تحليل الهدف</button>
                        </div>
                        <div id="osintRiskScore" class="hidden mt-3 p-3 rounded-xl border text-sm font-bold"></div>
                        <div id="osintUnifiedResult" class="hidden mt-3 p-3 bg-black/40 border border-slate-700 rounded-xl text-xs font-mono whitespace-pre-wrap max-h-72 overflow-y-auto" dir="ltr"></div>
                    </div>

                    <div class="bg-slate-900/60 p-4 rounded-xl border border-indigo-900/40">
                        <h3 class="text-sm font-bold text-indigo-300 mb-2">Watchlist</h3>
                        <p class="text-[11px] text-gray-500 mb-3">احفظ الأهداف لمراقبتها وتصدير تقرير سريع.</p>
                        <div class="flex gap-2 mb-2">
                            <button onclick="saveCurrentOsintTarget()" class="flex-1 py-2 bg-indigo-900/40 hover:bg-indigo-800 rounded-lg text-xs font-bold text-indigo-300 border border-indigo-800/40">إضافة الهدف الحالي</button>
                            <button onclick="exportOsintReport()" class="flex-1 py-2 bg-emerald-900/40 hover:bg-emerald-800 rounded-lg text-xs font-bold text-emerald-300 border border-emerald-800/40">تصدير JSON</button>
                        </div>
                        <div id="osintWatchlist" class="bg-black/40 border border-slate-700 rounded-lg p-2 max-h-56 overflow-y-auto text-xs text-gray-300"></div>
                    </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-cyan-900/40">
                        <h3 class="text-sm font-bold text-cyan-300 mb-2">Username Hunter</h3>
                        <p class="text-[11px] text-gray-500 mb-3">البحث عن اليوزرنيم على منصات متعددة لمعرفة وين موجود.</p>
                        <div class="flex gap-2">
                            <input id="osintUsernameInput" type="text" placeholder="username" class="flex-1 p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-cyan-500 outline-none font-mono text-left" dir="ltr">
                            <button onclick="huntUsername()" class="bg-cyan-900/50 hover:bg-cyan-800 px-5 py-3 rounded-xl font-bold border border-cyan-800/50 transition-all text-cyan-300">ابحث</button>
                        </div>
                        <div id="osintUsernameResult" class="hidden mt-3 p-3 bg-black/40 border border-slate-700 rounded-xl text-xs font-mono whitespace-pre-wrap max-h-72 overflow-y-auto" dir="ltr"></div>
                    </div>

                    <div class="bg-slate-900/60 p-4 rounded-xl border border-amber-900/40">
                        <h3 class="text-sm font-bold text-amber-300 mb-2">Hash Analyzer</h3>
                        <p class="text-[11px] text-gray-500 mb-3">تحليل مؤشرات الملفات (MD5 / SHA1 / SHA256) وتقدير السمعة.</p>
                        <div class="flex gap-2">
                            <input id="osintHashInput" type="text" placeholder="Paste hash..." class="flex-1 p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-amber-500 outline-none font-mono text-left" dir="ltr">
                            <button onclick="analyzeHashIndicator()" class="bg-amber-900/50 hover:bg-amber-800 px-5 py-3 rounded-xl font-bold border border-amber-800/50 transition-all text-amber-300">حلل</button>
                        </div>
                        <div id="osintHashResult" class="hidden mt-3 p-3 bg-black/40 border border-slate-700 rounded-xl text-xs font-mono whitespace-pre-wrap" dir="ltr"></div>
                    </div>
                </div>

                <div class="bg-slate-900/60 p-4 rounded-xl border border-rose-900/40">
                    <h3 class="text-sm font-bold text-rose-300 mb-2">Threat Intel Quick Actions</h3>
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div class="bg-black/30 border border-slate-700 rounded-lg p-3">
                            <label class="text-[10px] text-gray-500 uppercase tracking-wider">DNS Leak</label>
                            <button onclick="osintQuickDnsLeak()" class="w-full mt-2 py-2 bg-rose-900/40 hover:bg-rose-800 rounded-lg text-xs font-bold text-rose-300 border border-rose-800/40">فحص</button>
                        </div>
                        <div class="bg-black/30 border border-slate-700 rounded-lg p-3">
                            <label class="text-[10px] text-gray-500 uppercase tracking-wider">Shodan Intel (IP)</label>
                            <input id="osintShodanIp" type="text" placeholder="1.1.1.1" class="w-full mt-2 p-2 rounded bg-slate-900 border border-slate-700 outline-none text-xs font-mono text-left" dir="ltr">
                            <button onclick="osintQuickShodan()" class="w-full mt-2 py-2 bg-rose-900/40 hover:bg-rose-800 rounded-lg text-xs font-bold text-rose-300 border border-rose-800/40">فحص</button>
                        </div>
                        <div class="bg-black/30 border border-slate-700 rounded-lg p-3">
                            <label class="text-[10px] text-gray-500 uppercase tracking-wider">Malware URL</label>
                            <input id="osintMalwareUrl" type="text" placeholder="https://target.tld" class="w-full mt-2 p-2 rounded bg-slate-900 border border-slate-700 outline-none text-xs font-mono text-left" dir="ltr">
                            <button onclick="osintQuickMalwareUrl()" class="w-full mt-2 py-2 bg-rose-900/40 hover:bg-rose-800 rounded-lg text-xs font-bold text-rose-300 border border-rose-800/40">فحص</button>
                        </div>
                    </div>
                    <div id="osintThreatResult" class="hidden mt-3 p-3 bg-black/40 border border-slate-700 rounded-xl text-xs font-mono whitespace-pre-wrap max-h-64 overflow-y-auto" dir="ltr"></div>
                </div>
            </div>

            <div id="ir-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-red-400 border-b border-slate-700 pb-2">🚨 Incident Response</h2>
                <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-red-900/40 space-y-3">
                        <h3 class="text-sm font-bold text-red-300">إنشاء قضية</h3>
                        <input id="irCaseTitle" type="text" placeholder="عنوان القضية" class="w-full p-2 rounded-lg bg-slate-900 border border-slate-700 outline-none text-sm">
                        <select id="irCaseSeverity" class="w-full p-2 rounded-lg bg-slate-900 border border-slate-700 outline-none text-sm">
                            <option value="low">Low</option>
                            <option value="medium" selected>Medium</option>
                            <option value="high">High</option>
                            <option value="critical">Critical</option>
                        </select>
                        <textarea id="irCaseDesc" rows="3" placeholder="وصف سريع للحادث" class="w-full p-2 rounded-lg bg-slate-900 border border-slate-700 outline-none text-sm"></textarea>
                        <button onclick="irCreateCase()" class="w-full py-2 rounded-lg bg-red-900/50 hover:bg-red-800 text-red-300 font-bold border border-red-800/40">إنشاء</button>
                    </div>

                    <div class="lg:col-span-2 bg-slate-900/60 p-4 rounded-xl border border-red-900/40">
                        <div class="flex items-center justify-between mb-3">
                            <h3 class="text-sm font-bold text-red-300">القضايا</h3>
                            <button onclick="irLoadCases()" class="text-xs px-3 py-1 rounded bg-slate-800 border border-slate-700">تحديث</button>
                        </div>
                        <div id="irCasesList" class="space-y-2 max-h-56 overflow-y-auto"></div>
                    </div>
                </div>

                <div class="bg-slate-900/60 p-4 rounded-xl border border-red-900/40">
                    <div class="flex items-center justify-between mb-3">
                        <h3 class="text-sm font-bold text-red-300">إدارة مؤشرات القضية</h3>
                        <div id="irSelectedCase" class="text-xs text-gray-400">لم يتم اختيار قضية</div>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-4 gap-2">
                        <select id="irIocType" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                            <option value="ip">IP</option>
                            <option value="domain">Domain</option>
                            <option value="url">URL</option>
                            <option value="hash">Hash</option>
                            <option value="username">Username</option>
                            <option value="email">Email</option>
                        </select>
                        <input id="irIocValue" type="text" placeholder="IOC value" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none font-mono" dir="ltr">
                        <input id="irIocRisk" type="number" min="0" max="100" value="50" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                        <button onclick="irAddIoc()" class="p-2 rounded bg-red-900/40 border border-red-800/50 text-red-300 text-xs font-bold">إضافة IOC</button>
                    </div>
                    <div class="flex flex-wrap gap-2 mt-3">
                        <button onclick="irUpdateStatus('open')" class="px-3 py-1 text-xs rounded bg-slate-800 border border-slate-700">Open</button>
                        <button onclick="irUpdateStatus('investigating')" class="px-3 py-1 text-xs rounded bg-blue-900/30 border border-blue-800/50">Investigating</button>
                        <button onclick="irUpdateStatus('contained')" class="px-3 py-1 text-xs rounded bg-amber-900/30 border border-amber-800/50">Contained</button>
                        <button onclick="irUpdateStatus('closed')" class="px-3 py-1 text-xs rounded bg-green-900/30 border border-green-800/50">Closed</button>
                        <button onclick="irExportReport()" class="px-3 py-1 text-xs rounded bg-emerald-900/30 border border-emerald-800/50">تصدير تقرير</button>
                    </div>
                    <div id="irIocTimeline" class="mt-3 p-3 rounded-lg bg-black/40 border border-slate-700 max-h-56 overflow-y-auto text-xs"></div>
                </div>
            </div>

            <div id="maltego-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-fuchsia-400 border-b border-slate-700 pb-2">🕸️ Link Analysis (Maltego Style)</h2>
                <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-fuchsia-900/40 space-y-3">
                        <h3 class="text-sm font-bold text-fuchsia-300">إضافة كيان</h3>
                        <select id="graphEntityType" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                            <option value="ip">IP</option>
                            <option value="domain">Domain</option>
                            <option value="url">URL</option>
                            <option value="email">Email</option>
                            <option value="username">Username</option>
                            <option value="hash">Hash</option>
                        </select>
                        <input id="graphEntityValue" type="text" placeholder="قيمة الكيان" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none font-mono" dir="ltr">
                        <button onclick="graphAddEntity()" class="w-full py-2 rounded bg-fuchsia-900/40 border border-fuchsia-800/50 text-fuchsia-300 text-xs font-bold">إضافة</button>
                        <button onclick="graphAutoLink()" class="w-full py-2 rounded bg-violet-900/40 border border-violet-800/50 text-violet-300 text-xs font-bold">تحليل الروابط</button>
                    </div>
                    <div class="lg:col-span-2 bg-slate-900/60 p-4 rounded-xl border border-fuchsia-900/40">
                        <h3 class="text-sm font-bold text-fuchsia-300 mb-3">لوحة العقد والروابط</h3>
                        <div id="graphCanvas" class="relative min-h-[260px] rounded-xl border border-slate-700 bg-black/40 p-2 overflow-hidden"></div>
                        <div id="graphLinksList" class="mt-3 text-xs bg-black/40 border border-slate-700 rounded-lg p-2 max-h-40 overflow-y-auto"></div>
                    </div>
                </div>
            </div>

            <div id="hunting-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-orange-400 border-b border-slate-700 pb-2">🎯 Threat Hunting Lab</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-orange-900/40 space-y-3">
                        <h3 class="text-sm font-bold text-orange-300">Query Builder</h3>
                        <input id="huntQueryText" type="text" placeholder="ابحث عن مؤشر..." class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none font-mono" dir="ltr">
                        <select id="huntQueryType" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                            <option value="all">All</option>
                            <option value="ip">IP</option>
                            <option value="domain">Domain</option>
                            <option value="url">URL</option>
                            <option value="email">Email</option>
                            <option value="username">Username</option>
                            <option value="hash">Hash</option>
                        </select>
                        <button onclick="huntRunQuery()" class="w-full py-2 rounded bg-orange-900/40 border border-orange-800/50 text-orange-300 text-xs font-bold">Run Hunt</button>
                        <div id="huntQueryResult" class="p-2 rounded bg-black/40 border border-slate-700 max-h-48 overflow-y-auto text-xs"></div>
                    </div>
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-orange-900/40 space-y-3">
                        <h3 class="text-sm font-bold text-orange-300">Correlation Rule</h3>
                        <p class="text-[11px] text-gray-500">قاعدة: إذا Risk Avg >= Threshold فأنشئ Alert.</p>
                        <input id="huntRuleThreshold" type="number" min="0" max="100" value="70" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                        <button onclick="huntEvaluateRule()" class="w-full py-2 rounded bg-amber-900/40 border border-amber-800/50 text-amber-300 text-xs font-bold">Evaluate</button>
                        <div id="huntRuleResult" class="p-2 rounded bg-black/40 border border-slate-700 text-xs"></div>
                    </div>
                </div>
            </div>

            <div id="forensics-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-teal-400 border-b border-slate-700 pb-2">🧪 Digital Forensics</h2>
                <div class="bg-slate-900/60 p-4 rounded-xl border border-teal-900/40 space-y-3">
                    <h3 class="text-sm font-bold text-teal-300">File Triage</h3>
                    <input id="forensicsFile" type="file" class="block w-full text-sm text-slate-400 file:mr-2 file:py-2 file:px-4 file:rounded-full file:border-0 file:bg-slate-800 file:text-teal-300 border border-slate-700 p-2 rounded-xl">
                    <button onclick="forensicsTriage()" class="w-full py-2 rounded bg-teal-900/40 border border-teal-800/50 text-teal-300 text-xs font-bold">تحليل الدليل</button>
                    <div id="forensicsResult" class="p-2 rounded bg-black/40 border border-slate-700 text-xs font-mono whitespace-pre-wrap" dir="ltr"></div>
                </div>
            </div>

            <div id="brand-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-cyan-400 border-b border-slate-700 pb-2">🛡️ Brand & Social Protection</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-cyan-900/40 space-y-3">
                        <h3 class="text-sm font-bold text-cyan-300">Typosquatting Checker</h3>
                        <input id="brandDomainInput" type="text" placeholder="example.com" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none font-mono" dir="ltr">
                        <button onclick="brandCheckTypos()" class="w-full py-2 rounded bg-cyan-900/40 border border-cyan-800/50 text-cyan-300 text-xs font-bold">فحص</button>
                        <div id="brandTyposResult" class="p-2 rounded bg-black/40 border border-slate-700 max-h-44 overflow-y-auto text-xs"></div>
                    </div>
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-cyan-900/40 space-y-3">
                        <h3 class="text-sm font-bold text-cyan-300">Fake Account Detector</h3>
                        <input id="brandUserInput" type="text" placeholder="brand_username" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none font-mono" dir="ltr">
                        <button onclick="brandCheckImpersonation()" class="w-full py-2 rounded bg-cyan-900/40 border border-cyan-800/50 text-cyan-300 text-xs font-bold">تحليل</button>
                        <div id="brandUserResult" class="p-2 rounded bg-black/40 border border-slate-700 max-h-44 overflow-y-auto text-xs"></div>
                    </div>
                </div>
            </div>

            <div id="se-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-pink-400 border-b border-slate-700 pb-2">🎭 Social Engineering Defense</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-pink-900/40 space-y-3">
                        <h3 class="text-sm font-bold text-pink-300">Awareness Simulator</h3>
                        <select id="seScenarioType" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                            <option value="phishing_email">Phishing Email</option>
                            <option value="vishing_call">Vishing Call</option>
                            <option value="pretexting">Pretexting</option>
                            <option value="baiting_usb">Baiting USB</option>
                        </select>
                        <button onclick="seGenerateScenario()" class="w-full py-2 rounded bg-pink-900/40 border border-pink-800/50 text-pink-300 text-xs font-bold">Generate Scenario</button>
                        <div id="seScenarioResult" class="p-2 rounded bg-black/40 border border-slate-700 text-xs whitespace-pre-wrap"></div>
                    </div>
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-pink-900/40 space-y-3">
                        <h3 class="text-sm font-bold text-pink-300">Training Checklist</h3>
                        <label class="flex items-center gap-2 text-xs"><input type="checkbox"> Verify sender domain before clicking links</label>
                        <label class="flex items-center gap-2 text-xs"><input type="checkbox"> Never share OTP or passwords</label>
                        <label class="flex items-center gap-2 text-xs"><input type="checkbox"> Confirm urgent requests via second channel</label>
                        <label class="flex items-center gap-2 text-xs"><input type="checkbox"> Report suspicious message to SOC</label>
                        <div class="text-[11px] text-gray-500">هذا القسم توعوي دفاعي فقط وليس للاستخدام الهجومي.</div>
                    </div>
                </div>
                <div class="bg-slate-900/60 p-4 rounded-xl border border-pink-900/40 space-y-3">
                    <div class="flex items-center justify-between gap-2 flex-wrap">
                        <h3 class="text-sm font-bold text-pink-300">Information Collection Board</h3>
                        <div class="flex gap-2">
                            <button onclick="seSortIntelBoard()" class="px-3 py-1 rounded bg-pink-900/40 border border-pink-800/50 text-pink-300 text-xs font-bold">ترتيب تلقائي</button>
                            <button onclick="seExportIntelBoard()" class="px-3 py-1 rounded bg-indigo-900/40 border border-indigo-800/50 text-indigo-300 text-xs font-bold">تصدير JSON</button>
                            <button onclick="seClearIntelBoard()" class="px-3 py-1 rounded bg-red-900/40 border border-red-800/50 text-red-300 text-xs font-bold">تفريغ</button>
                        </div>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-5 gap-2">
                        <input id="seIntelSubject" type="text" placeholder="Subject (person/domain)" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none md:col-span-2" dir="ltr">
                        <input id="seIntelSource" type="text" placeholder="Source (email/chat/call)" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none" dir="ltr">
                        <select id="seIntelCategory" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                            <option value="identity">Identity</option>
                            <option value="behavior">Behavior</option>
                            <option value="infrastructure">Infrastructure</option>
                            <option value="message">Message Pattern</option>
                        </select>
                        <select id="seIntelConfidence" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                            <option value="high">High Confidence</option>
                            <option value="medium" selected>Medium Confidence</option>
                            <option value="low">Low Confidence</option>
                        </select>
                    </div>
                    <textarea id="seIntelNote" rows="3" placeholder="اكتب المعلومة أو الملاحظة الأمنية هنا..." class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none"></textarea>
                    <button onclick="seAddIntelItem()" class="w-full py-2 rounded bg-pink-900/40 border border-pink-800/50 text-pink-300 text-xs font-bold">إضافة معلومة</button>
                    <div id="seIntelBoardResult" class="p-2 rounded bg-black/40 border border-slate-700 max-h-60 overflow-y-auto text-xs"></div>
                </div>
            </div>

            <div id="advcrypto-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-emerald-400 border-b border-slate-700 pb-2">🧬 Advanced Crypto Lab</h2>
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-emerald-900/40 space-y-2">
                        <h3 class="text-sm font-bold text-emerald-300">Hidden Vault (Decoy + Secret)</h3>
                        <input id="advHvLabel" placeholder="Vault label" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs">
                        <textarea id="advHvDecoy" rows="2" placeholder="Decoy text" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs"></textarea>
                        <input id="advHvDecoyPass" type="password" placeholder="Decoy password" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs">
                        <textarea id="advHvHidden" rows="2" placeholder="Hidden text" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs"></textarea>
                        <input id="advHvHiddenPass" type="password" placeholder="Hidden password" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs">
                        <div class="flex gap-2">
                            <button onclick="advHiddenVaultCreate()" class="flex-1 py-2 rounded bg-emerald-900/40 border border-emerald-800/50 text-emerald-300 text-xs font-bold">Create</button>
                            <button onclick="advHiddenVaultList()" class="flex-1 py-2 rounded bg-slate-800 border border-slate-700 text-xs">List</button>
                        </div>
                        <div class="flex gap-2">
                            <input id="advHvOpenId" type="number" placeholder="Vault ID" class="flex-1 p-2 rounded bg-slate-900 border border-slate-700 text-xs">
                            <input id="advHvOpenPass" type="password" placeholder="Password" class="flex-1 p-2 rounded bg-slate-900 border border-slate-700 text-xs">
                            <button onclick="advHiddenVaultOpen()" class="px-3 py-2 rounded bg-cyan-900/40 border border-cyan-800/50 text-xs">Open</button>
                        </div>
                        <div id="advHvOut" class="p-2 rounded bg-black/40 border border-slate-700 text-xs whitespace-pre-wrap"></div>
                    </div>

                    <div class="bg-slate-900/60 p-4 rounded-xl border border-emerald-900/40 space-y-2">
                        <h3 class="text-sm font-bold text-emerald-300">Secret Sharing (3-of-5)</h3>
                        <textarea id="advSsSecret" rows="3" placeholder="Secret text" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs"></textarea>
                        <div class="flex gap-2">
                            <button onclick="advSecretSplit()" class="flex-1 py-2 rounded bg-emerald-900/40 border border-emerald-800/50 text-emerald-300 text-xs font-bold">Split</button>
                            <button onclick="advSecretRecover()" class="flex-1 py-2 rounded bg-cyan-900/40 border border-cyan-800/50 text-xs">Recover</button>
                        </div>
                        <textarea id="advSsShares" rows="5" placeholder="Shares (JSON array)" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs font-mono" dir="ltr"></textarea>
                        <div id="advSsOut" class="p-2 rounded bg-black/40 border border-slate-700 text-xs whitespace-pre-wrap"></div>
                    </div>

                    <div class="bg-slate-900/60 p-4 rounded-xl border border-emerald-900/40 space-y-2">
                        <h3 class="text-sm font-bold text-emerald-300">Time-Lock Message</h3>
                        <textarea id="advTlMsg" rows="2" placeholder="Message" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs"></textarea>
                        <input id="advTlPass" type="password" placeholder="Password" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs">
                        <div class="grid grid-cols-2 gap-2">
                            <input id="advTlMinutes" type="number" min="1" value="10" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs">
                            <label class="text-xs flex items-center gap-2"><input id="advTlOneTime" type="checkbox" checked> One-time read</label>
                        </div>
                        <div class="flex gap-2">
                            <button onclick="advTimeLockCreate()" class="flex-1 py-2 rounded bg-emerald-900/40 border border-emerald-800/50 text-emerald-300 text-xs font-bold">Create Token</button>
                            <button onclick="advTimeLockOpen()" class="flex-1 py-2 rounded bg-cyan-900/40 border border-cyan-800/50 text-xs">Open</button>
                        </div>
                        <input id="advTlToken" placeholder="Token" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs font-mono" dir="ltr">
                        <div id="advTlOut" class="p-2 rounded bg-black/40 border border-slate-700 text-xs whitespace-pre-wrap"></div>
                    </div>

                    <div class="bg-slate-900/60 p-4 rounded-xl border border-emerald-900/40 space-y-2">
                        <h3 class="text-sm font-bold text-emerald-300">Policy Engine</h3>
                        <textarea id="advPolicyJson" rows="5" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs font-mono" dir="ltr">{"allowed_ips":[],"allowed_countries":[],"require_otp":false,"otp_code":"123456","min_hour":0,"max_hour":23}</textarea>
                        <input id="advPolicyOtp" placeholder="OTP (if required)" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs">
                        <button onclick="advPolicyEvaluate()" class="w-full py-2 rounded bg-emerald-900/40 border border-emerald-800/50 text-emerald-300 text-xs font-bold">Evaluate</button>
                        <div id="advPolicyOut" class="p-2 rounded bg-black/40 border border-slate-700 text-xs whitespace-pre-wrap"></div>
                    </div>

                    <div class="bg-slate-900/60 p-4 rounded-xl border border-emerald-900/40 space-y-2">
                        <h3 class="text-sm font-bold text-emerald-300">Watermark Signature</h3>
                        <input id="advWmFile" type="file" class="block w-full text-sm text-slate-400 file:mr-2 file:py-2 file:px-3 file:rounded-full file:border-0 file:bg-slate-800 file:text-emerald-300 border border-slate-700 p-2 rounded-xl">
                        <input id="advWmLabel" placeholder="Asset label" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs">
                        <div class="flex gap-2">
                            <button onclick="advWatermarkSign()" class="flex-1 py-2 rounded bg-emerald-900/40 border border-emerald-800/50 text-emerald-300 text-xs font-bold">Sign</button>
                            <button onclick="advWatermarkVerify()" class="flex-1 py-2 rounded bg-cyan-900/40 border border-cyan-800/50 text-xs">Verify</button>
                        </div>
                        <input id="advWmSig" placeholder="Signature" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs font-mono" dir="ltr">
                        <div id="advWmOut" class="p-2 rounded bg-black/40 border border-slate-700 text-xs whitespace-pre-wrap"></div>
                    </div>

                    <div class="bg-slate-900/60 p-4 rounded-xl border border-emerald-900/40 space-y-2">
                        <h3 class="text-sm font-bold text-emerald-300">Key Lifecycle (Create/Rotate/Revoke)</h3>
                        <input id="advKeyName" placeholder="Key name" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs">
                        <div class="flex gap-2">
                            <button onclick="advKeyCreate()" class="flex-1 py-2 rounded bg-emerald-900/40 border border-emerald-800/50 text-emerald-300 text-xs font-bold">Create</button>
                            <button onclick="advKeyList()" class="flex-1 py-2 rounded bg-slate-800 border border-slate-700 text-xs">List</button>
                        </div>
                        <div class="flex gap-2">
                            <input id="advKeyId" type="number" placeholder="Key ID" class="flex-1 p-2 rounded bg-slate-900 border border-slate-700 text-xs">
                            <button onclick="advKeyRotate()" class="px-3 py-2 rounded bg-amber-900/40 border border-amber-800/50 text-xs">Rotate</button>
                            <button onclick="advKeyRevoke()" class="px-3 py-2 rounded bg-red-900/40 border border-red-800/50 text-xs">Revoke</button>
                        </div>
                        <textarea id="advKeyPlain" rows="2" placeholder="Plain text" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs"></textarea>
                        <div class="flex gap-2">
                            <button onclick="advKeyEncrypt()" class="flex-1 py-2 rounded bg-emerald-900/40 border border-emerald-800/50 text-xs">Encrypt</button>
                            <button onclick="advKeyDecrypt()" class="flex-1 py-2 rounded bg-cyan-900/40 border border-cyan-800/50 text-xs">Decrypt</button>
                        </div>
                        <textarea id="advKeyCipher" rows="2" placeholder="Cipher text" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs font-mono" dir="ltr"></textarea>
                        <div id="advKeyOut" class="p-2 rounded bg-black/40 border border-slate-700 text-xs whitespace-pre-wrap"></div>
                    </div>
                </div>
            </div>

            <!-- ===== QR CODE SECTION ===== -->
            <div id="qr-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-green-400 border-b border-slate-700 pb-2">🔳 QR Code مشفر</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div class="bg-slate-900/70 rounded-xl p-5 border border-green-900/40 space-y-3">
                        <h3 class="font-bold text-green-400 text-sm">توليد QR</h3>
                        <textarea id="qrText" rows="3" placeholder="النص أو الرابط..." class="w-full p-3 rounded-xl bg-slate-800 border border-slate-700 outline-none text-sm focus:ring-2 focus:ring-green-500"></textarea>
                        <input type="password" id="qrPass" placeholder="كلمة سر (اختياري للتشفير)" class="w-full p-3 rounded-xl bg-slate-800 border border-slate-700 outline-none text-sm">
                        <button onclick="generateQR()" class="w-full bg-green-900/50 hover:bg-green-800 text-green-300 font-bold p-3 rounded-xl border border-green-800/50 transition-all">توليد QR 🔳</button>
                        <div id="qrResult" class="hidden text-center">
                            <img id="qrImg" src="" class="mx-auto rounded-lg border border-green-800/40 max-w-[200px]">
                            <a id="qrDownload" download="qr.png" class="block mt-2 text-xs text-green-400 underline cursor-pointer">تنزيل الصورة</a>
                        </div>
                    </div>
                    <div class="bg-slate-900/70 rounded-xl p-5 border border-blue-900/40 space-y-3">
                        <h3 class="font-bold text-blue-400 text-sm">رفع QR للقراءة / الفك</h3>
                        <input type="file" id="qrFile" accept="image/*" class="block w-full text-sm text-slate-400 file:mr-2 file:py-2 file:px-4 file:rounded-full file:border-0 file:bg-slate-800 file:text-blue-400 border border-slate-700 p-2 rounded-xl">
                        <input type="password" id="qrDecodePass" placeholder="كلمة السر (إذا كان مشفراً)" class="w-full p-3 rounded-xl bg-slate-800 border border-slate-700 outline-none text-sm">
                        <button onclick="decodeQR()" class="w-full bg-blue-900/50 hover:bg-blue-800 text-blue-300 font-bold p-3 rounded-xl border border-blue-800/50 transition-all">قراءة QR 🔍</button>
                        <div id="qrDecodeResult" class="hidden p-3 bg-slate-800 rounded-xl border border-slate-600 text-sm font-mono text-green-300 break-all"></div>
                    </div>
                </div>
            </div>

            <!-- FAKE IDENTITY SECTION -->
            <div id="identity-section" class="hidden space-y-6">
                <div class="flex items-center justify-between border-b border-teal-900/30 pb-4 mb-2">
                    <h2 class="text-2xl font-black text-transparent bg-clip-text bg-gradient-to-r from-teal-400 to-cyan-400 flex items-center gap-3">
                        <span class="w-10 h-10 rounded-full bg-teal-500/10 flex items-center justify-center text-xl shadow-[0_0_15px_rgba(20,184,166,0.2)]">🪪</span>
                        مولد الهوية الرقمية الشامل
                    </h2>
                    <div class="flex items-center gap-2">
                        <span class="text-[10px] text-teal-500/70 font-mono uppercase tracking-tighter">Status:</span>
                        <div class="flex items-center gap-1 bg-teal-900/20 px-2 py-1 rounded-full border border-teal-500/20">
                            <div class="w-1.5 h-1.5 rounded-full bg-teal-500 animate-pulse"></div>
                            <span class="text-[9px] text-teal-400 font-bold uppercase">Encrypted</span>
                        </div>
                    </div>
                </div>

                <div class="bg-gray-900/40 backdrop-blur-md p-6 rounded-3xl border border-white/5 shadow-2xl relative overflow-hidden">
                    <div class="absolute -top-24 -right-24 w-64 h-64 bg-teal-500/5 rounded-full blur-3xl pointer-events-none"></div>
                    <div class="absolute -bottom-24 -left-24 w-64 h-64 bg-blue-500/5 rounded-full blur-3xl pointer-events-none"></div>
                    
                    <div class="relative z-10">
                        <p class="text-gray-400 text-sm mb-6 leading-relaxed max-w-2xl">توليد بيانات شخصية متكاملة تتخطى أنظمة التحقق الروتينية. جميع البيانات يتم إنتاجها بخوارزميات عشوائية تضمن تفرد كل هوية.</p>
                        
                        <div class="flex flex-col md:flex-row gap-4 mb-8">
                            <div class="flex-1 relative group">
                                <label class="absolute -top-2 right-4 px-2 bg-gray-900 text-[10px] text-teal-500 font-bold z-20">اختر الموقع الجغرافي</label>
                                <select id="identityLang" class="w-full p-4 pl-10 rounded-2xl bg-black/40 border border-teal-500/20 text-gray-200 outline-none focus:ring-2 focus:ring-teal-500/40 transition-all appearance-none cursor-pointer">
                                    <optgroup label="Arabic Locales">
                                        <option value="ar_JO" selected>الأردن (Jordan) 🇯🇴</option>
                                        <option value="ar_SA">السعودية (Saudi Arabia) 🇸🇦</option>
                                        <option value="ar_AE">الإمارات (UAE) 🇦🇪</option>
                                        <option value="ar_EG">مصر (Egypt) 🇪🇬</option>
                                    </optgroup>
                                    <optgroup label="International">
                                        <option value="en_US">United States 🇺🇸</option>
                                        <option value="en_GB">United Kingdom 🇬🇧</option>
                                        <option value="fr_FR">France 🇫🇷</option>
                                        <option value="de_DE">Germany 🇩🇪</option>
                                        <option value="es_ES">Spain 🇪🇸</option>
                                        <option value="tr_TR">Turkey 🇹🇷</option>
                                        <option value="ru_RU">Russia 🇷🇺</option>
                                        <option value="zh_CN">China 🇨🇳</option>
                                    </optgroup>
                                </select>
                                <div class="absolute left-4 top-1/2 -translate-y-1/2 text-teal-500/50 pointer-events-none">▼</div>
                            </div>
                            
                            <button onclick="generateIdentity()" class="relative group overflow-hidden bg-teal-600 hover:bg-teal-500 text-white font-black px-8 py-4 rounded-2xl transition-all shadow-[0_10px_30px_-10px_rgba(20,184,166,0.5)] active:scale-95 flex items-center justify-center gap-3">
                                <span>توليد الآن ⚡</span>
                            </button>
                        </div>
                    </div>

                    <div id="identityResultArea" class="hidden animate-in fade-in slide-in-from-bottom-4 duration-700">
                        <!-- Premium Virtual ID Card -->
                        <div class="max-w-4xl mx-auto space-y-6">
                            
                            <!-- Main Card -->
                            <div class="relative overflow-hidden rounded-[2.5rem] border border-white/10 bg-slate-900/80 backdrop-blur-3xl shadow-[0_30px_100px_rgba(0,0,0,0.5)] p-0">
                                <!-- Design Accents -->
                                <div class="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-cyan-500 to-transparent opacity-50"></div>
                                <div class="absolute -right-20 -top-20 w-64 h-64 bg-cyan-500/10 rounded-full blur-[100px]"></div>
                                <div class="absolute -left-20 -bottom-20 w-64 h-64 bg-purple-500/10 rounded-full blur-[100px]"></div>
                                
                                <div class="p-8 md:p-12">
                                    <div class="flex flex-col md:flex-row gap-10 items-center md:items-start relative z-10">
                                        <!-- Photo/Profile Icon -->
                                        <div class="w-40 h-52 bg-black/60 rounded-3xl border border-cyan-500/20 overflow-hidden relative shadow-inner group flex-shrink-0">
                                            <div class="absolute inset-0 bg-gradient-to-t from-cyan-500/10 via-transparent to-transparent"></div>
                                            <div class="w-full h-full flex items-center justify-center text-8xl opacity-40 group-hover:opacity-60 transition-opacity filter grayscale" id="idProfileIcon">👤</div>
                                            <div class="absolute bottom-4 left-1/2 -translate-x-1/2 w-[85%]">
                                                <div class="bg-cyan-500/80 backdrop-blur-md text-[8px] py-1 rounded-full text-white font-black uppercase tracking-[0.2em] text-center">IDENTITY VERIFIED</div>
                                            </div>
                                        </div>

                                        <!-- Core Profile Info -->
                                        <div class="flex-1 w-full text-center md:text-right">
                                            <div class="mb-8">
                                                <div class="flex items-center justify-center md:justify-start gap-3 mb-4">
                                                    <span id="idGender" class="bg-white/5 text-cyan-400 text-[10px] font-black px-4 py-1.5 rounded-full border border-white/10 uppercase tracking-widest backdrop-blur-sm"></span>
                                                    <span id="idZodiac" class="bg-purple-500/10 text-purple-400 text-[10px] font-black px-4 py-1.5 rounded-full border border-purple-500/20"></span>
                                                </div>
                                                <h3 id="idName" class="text-4xl md:text-5xl font-black text-white leading-tight mb-2 tracking-tight"></h3>
                                                <!-- Removed secondary name per user request so only one name shows -->
                                            </div>

                                            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                <div class="bg-white/5 backdrop-blur-sm p-4 rounded-2xl border border-white/10 hover:bg-white/10 transition-colors">
                                                    <span class="text-[10px] text-gray-400 font-bold uppercase tracking-widest block mb-1 opacity-60">National Register ID</span>
                                                    <span id="idNational" class="text-xl font-mono text-white font-black tracking-widest"></span>
                                                </div>
                                                <div class="bg-white/5 backdrop-blur-sm p-4 rounded-2xl border border-white/10 hover:bg-white/10 transition-colors">
                                                    <span class="text-[10px] text-gray-400 font-bold uppercase tracking-widest block mb-1 opacity-60">Birth Certificate Date</span>
                                                    <span id="idDob" class="text-xl font-mono text-white font-black tracking-widest"></span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    <!-- Divider & Footer Info -->
                                    <div class="mt-12 pt-8 border-t border-white/5 flex flex-wrap justify-center md:justify-between items-center gap-8 relative z-10">
                                        <div class="text-center md:text-right">
                                            <span class="text-[10px] text-gray-500 font-bold uppercase tracking-widest block mb-2">Age Equivalent</span>
                                            <span id="idAge" class="text-2xl font-black text-white"></span>
                                        </div>
                                        <div class="text-center md:text-right">
                                            <span class="text-[10px] text-gray-500 font-bold uppercase tracking-widest block mb-2">Blood Group</span>
                                            <span id="idBlood" class="text-2xl font-black text-rose-500 drop-shadow-[0_0_10px_rgba(244,63,94,0.3)]"></span>
                                        </div>
                                        <div class="text-center md:text-right">
                                            <span class="text-[10px] text-gray-500 font-bold uppercase tracking-widest block mb-2">Physical Specs</span>
                                            <span class="text-xl font-bold text-gray-200" dir="ltr"><span id="idHeight"></span> | <span id="idWeight"></span></span>
                                        </div>
                                        <div class="text-center md:text-right">
                                            <span class="text-[10px] text-gray-500 font-bold uppercase tracking-widest block mb-2">Primary Asset</span>
                                            <span id="idVehicle" class="text-lg font-bold text-gray-400 truncate max-w-[150px] inline-block"></span>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <!-- Detail Sections Grid -->
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                                
                                <!-- Contact Details Card -->
                                <div class="bg-slate-900/60 backdrop-blur-2xl rounded-[2rem] border border-white/5 p-8 shadow-xl">
                                    <div class="flex items-center gap-3 mb-8">
                                        <div class="w-10 h-10 bg-cyan-500/20 rounded-xl flex items-center justify-center text-cyan-400 shadow-[0_0_15px_rgba(6,182,212,0.2)]">📍</div>
                                        <h4 class="text-sm font-black text-white uppercase tracking-[0.2em]">Contact & Logistics</h4>
                                    </div>
                                    
                                    <div class="space-y-6">
                                        <div class="bg-white/5 p-4 rounded-2xl border border-white/5">
                                            <span class="text-[9px] text-gray-500 font-bold uppercase tracking-widest block mb-2">Registered Address</span>
                                            <p id="idAddress" class="text-sm text-gray-200 font-bold leading-relaxed"></p>
                                        </div>
                                        
                                        <div class="grid grid-cols-2 gap-4">
                                            <div class="bg-white/5 p-4 rounded-2xl border border-white/5">
                                                <span class="text-[9px] text-gray-500 font-bold uppercase tracking-widest block mb-1">Postal Code</span>
                                                <p id="idZip" class="text-lg font-mono text-cyan-400 font-black"></p>
                                            </div>
                                            <div class="bg-white/5 p-4 rounded-2xl border border-white/5">
                                                <span class="text-[9px] text-gray-500 font-bold uppercase tracking-widest block mb-1">Country Prefix</span>
                                                <p id="idCountryCode" class="text-lg font-mono text-white font-black"></p>
                                            </div>
                                        </div>
                                        
                                        <div class="bg-black/40 p-5 rounded-2xl border border-white/5">
                                            <div class="flex justify-between items-center mb-1">
                                                <span class="text-[9px] text-gray-500 font-bold uppercase tracking-widest">Mobile Secure Line</span>
                                                <span class="text-[10px] text-green-500 font-mono">ACTIVE</span>
                                            </div>
                                            <p id="idPhone" class="text-xl font-mono text-white font-black tracking-wider" dir="ltr"></p>
                                        </div>
                                        
                                        <div class="bg-cyan-500/5 p-5 rounded-2xl border border-cyan-500/10">
                                            <span class="text-[9px] text-cyan-500/60 font-bold uppercase tracking-widest block mb-1">Primary Email Node</span>
                                            <p id="idEmail" class="text-xs font-mono text-cyan-300 break-all select-all font-bold"></p>
                                        </div>
                                    </div>
                                </div>

                                <!-- Financial & Web Card -->
                                <div class="bg-slate-900/60 backdrop-blur-2xl rounded-[2rem] border border-white/5 p-8 shadow-xl">
                                    <div class="flex items-center gap-3 mb-8">
                                        <div class="w-10 h-10 bg-purple-500/20 rounded-xl flex items-center justify-center text-purple-400 shadow-[0_0_15px_rgba(168,85,247,0.2)]">💳</div>
                                        <h4 class="text-sm font-black text-white uppercase tracking-[0.2em]">Financial & Digital</h4>
                                    </div>

                                    <div class="space-y-6">
                                        <!-- Standard Horizontal Premium Card (Iteration 3: Purple Professional Absolute Final) -->
                                        <div class="w-full max-w-[380px] mx-auto mb-4 select-none rounded-[1.2rem] overflow-hidden shadow-2xl transition-transform duration-500 hover:scale-[1.02]" style="aspect-ratio:1.586/1;position:relative;">
                                            <!-- Background -->
                                            <div style="position:absolute;inset:0;background:linear-gradient(135deg,#3b1d6e,#1e1054,#2d1060);"></div>
                                            <div style="position:absolute;inset:0;background:linear-gradient(135deg,rgba(255,255,255,0.06) 0%,transparent 50%,rgba(255,255,255,0.03) 100%);pointer-events:none;"></div>
                                            <div style="position:absolute;inset:0;border:1px solid rgba(255,255,255,0.1);border-radius:1.2rem;pointer-events:none;"></div>

                                            <!-- TOP ROW: Chip + TITAN SEC -->
                                            <div style="position:absolute;top:14px;left:14px;right:14px;display:flex;align-items:center;justify-content:space-between;">
                                                <!-- Gold Chip -->
                                                <div style="display:flex;align-items:center;gap:8px;">
                                                    <div style="width:36px;height:26px;background:linear-gradient(135deg,#fef3c7,#f59e0b,#d97706);border-radius:5px;position:relative;overflow:hidden;border:1px solid rgba(252,211,77,0.4);">
                                                        <div style="position:absolute;top:0;bottom:0;left:50%;width:1px;background:rgba(0,0,0,0.15);"></div>
                                                        <div style="position:absolute;left:0;right:0;top:50%;height:1px;background:rgba(0,0,0,0.15);"></div>
                                                    </div>
                                                    <!-- Wireless bars -->
                                                    <div style="display:flex;align-items:flex-end;gap:2px;opacity:0.5;">
                                                        <div style="width:2px;height:8px;background:white;border-radius:2px;"></div>
                                                        <div style="width:2px;height:12px;background:white;border-radius:2px;"></div>
                                                        <div style="width:2px;height:16px;background:white;border-radius:2px;"></div>
                                                    </div>
                                                </div>
                                                <!-- TITAN SEC -->
                                                <span style="font-size:10px;font-weight:900;letter-spacing:0.2em;color:rgba(255,255,255,0.5);font-family:monospace;">TITAN SEC</span>
                                            </div>

                                            <!-- MIDDLE: Card Number -->
                                            <div style="position:absolute;top:50%;left:0;right:0;transform:translateY(-60%);text-align:center;">
                                                <p id="idCredit" dir="ltr" style="font-size:17px;font-family:monospace;color:white;font-weight:700;letter-spacing:0.18em;white-space:nowrap;text-shadow:0 2px 8px rgba(0,0,0,0.8);unicode-bidi:bidi-override;"></p>
                                            </div>

                                            <!-- BOTTOM ROW: 3-column grid -->
                                            <div style="position:absolute;bottom:12px;left:14px;right:14px;display:grid;grid-template-columns:auto auto 1fr;align-items:end;gap:16px;">
                                                <!-- Valid Thru -->
                                                <div style="display:flex;flex-direction:column;gap:2px;">
                                                    <span style="font-size:7px;color:rgba(255,255,255,0.5);text-transform:uppercase;letter-spacing:0.1em;font-weight:800;">Valid Thru</span>
                                                    <span id="idCcExp" style="font-size:14px;font-family:monospace;color:white;font-weight:700;"></span>
                                                </div>
                                                <!-- Cardholder & CVV -->
                                                <div style="display:flex;flex-direction:column;gap:2px;">
                                                    <span style="font-size:7px;color:rgba(255,255,255,0.5);text-transform:uppercase;letter-spacing:0.1em;font-weight:800;">CVV &nbsp; رمز الطرواسة</span>
                                                    <div style="display:flex;align-items:center;gap:10px;">
                                                        <span id="idCcCvv" style="font-size:14px;font-family:monospace;color:white;font-weight:700;"></span>
                                                        <span style="color:rgba(255,255,255,0.3);font-size:12px;">|</span>
                                                        <span id="idCardNameDisplay" style="font-size:12px;font-weight:700;color:white;text-transform:uppercase;letter-spacing:0.05em;white-space:nowrap;max-width:100px;overflow:hidden;text-overflow:ellipsis;"></span>
                                                    </div>
                                                </div>
                                                <!-- VISA Logo -->
                                                <div style="text-align:right;">
                                                    <span style="font-size:26px;font-weight:900;font-style:italic;color:white;letter-spacing:-1px;text-shadow:0 2px 8px rgba(0,0,0,0.5);">VISA</span>
                                                </div>
                                            </div>
                                        </div>
                                        <!-- Hidden IDs for JS/Copy compatibility -->
                                        <span id="idCcType" class="hidden"></span>


                                        <div class="grid grid-cols-2 gap-4">
                                            <div class="bg-white/5 p-4 rounded-2xl border border-white/5">
                                                <span class="text-[9px] text-gray-500 font-bold uppercase tracking-widest block mb-2">System Login</span>
                                                <p id="idUsername" class="text-sm font-black text-white"></p>
                                            </div>
                                            <div class="bg-white/5 p-4 rounded-2xl border border-white/5">
                                                <span class="text-[9px] text-gray-500 font-bold uppercase tracking-widest block mb-2">Auth Sequence</span>
                                                <p id="idPassword" class="text-sm font-black text-purple-400"></p>
                                            </div>
                                        </div>

                                        <div class="bg-white/2 p-4 rounded-2xl border border-white/5">
                                            <span class="text-[9px] text-gray-500 font-bold uppercase tracking-widest block mb-1">Official Web Domain</span>
                                            <a id="idWebsite" href="#" target="_blank" class="text-xs text-blue-400 font-bold hover:underline truncate block"></a>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <!-- Meta Sigature Card -->
                            <div class="bg-black/50 backdrop-blur-md rounded-[2rem] border border-white/5 p-8">
                                <h4 class="text-[10px] font-black text-gray-500 uppercase tracking-[0.4em] mb-6 flex items-center justify-center gap-4">
                                    <div class="w-2 h-[1px] bg-gray-800 flex-1"></div>
                                    DIGITAL FOOTPRINT SIGNATURE
                                    <div class="w-2 h-[1px] bg-gray-800 flex-1"></div>
                                </h4>
                                <div class="grid grid-cols-1 md:grid-cols-2 gap-8 text-[11px] font-mono">
                                    <div class="space-y-4">
                                        <div class="flex flex-col gap-1">
                                            <span class="text-gray-700 uppercase font-black text-[9px]">Geospatial Data</span>
                                            <span id="idGeo" class="text-teal-500/80 font-bold text-sm tracking-widest"></span>
                                        </div>
                                        <div class="flex flex-col gap-1">
                                            <span class="text-gray-700 uppercase font-black text-[9px]">Unique Logic Descriptor</span>
                                            <span id="idUuid" class="text-gray-500 text-xs truncate"></span>
                                        </div>
                                    </div>
                                    <div class="space-y-4">
                                        <div class="flex flex-col gap-1">
                                            <span class="text-gray-700 uppercase font-black text-[9px]">Captured User Agent String</span>
                                            <span id="idUserAgent" class="text-gray-600 text-[10px] leading-relaxed italic break-words border-l-2 border-white/5 pl-4"></span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            <button onclick="copyFullIdentity()" class="w-full py-5 bg-white shadow-2xl shadow-white/5 hover:bg-white/90 text-slate-950 font-black rounded-[1.5rem] transition-all flex items-center justify-center gap-4 group active:scale-95">
                                <span class="bg-slate-900 text-white p-2 rounded-xl group-hover:bg-cyan-600 transition-colors">📋</span>
                                <span class="uppercase tracking-widest text-sm">تصدير كامل بيانات الهوية الرقمية</span>
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- ===== EXTREME PRIVACY SECTION ===== -->
            <div id="extreme-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-teal-400 border-b border-slate-700 pb-2">🛡️ أدوات الخصوصية القصوى (Extreme Privacy)</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div class="bg-slate-900/50 p-6 rounded-2xl border border-teal-500/20">
                        <label class="block text-sm text-teal-400 mb-3 font-bold">📄 منظف ملفات PDF:</label>
                        <p class="text-[10px] text-gray-500 mb-4">إزالة الميتابيانات من ملفات PDF لحماية الخصوصية.</p>
                        <input type="file" id="pdfCleanFile" accept=".pdf" class="w-full text-xs text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-xs file:font-semibold file:bg-teal-600/10 file:text-teal-400 hover:file:bg-teal-600/20 mb-4">
                        <button onclick="cleanPdf()" class="w-full py-3 bg-teal-600 hover:bg-teal-500 rounded-xl font-bold transition-all text-sm">بدء التنظيف العميق 🧹</button>
                    </div>
                    <div class="bg-slate-900/50 p-6 rounded-2xl border border-indigo-500/20">
                        <label class="block text-sm text-indigo-400 mb-3 font-bold">🪪 بصمة المتصفح (Browser Fingerprint):</label>
                        <p class="text-[10px] text-gray-500 mb-4">توليد ملف تعريف وهمي لتجنب التتبع الرقمي.</p>
                        <div id="fingerprintDisplay" class="font-mono text-[9px] text-indigo-300 bg-black/60 p-3 rounded-lg mb-4 h-24 overflow-y-auto italic">اضغط لتوليد هوية جديدة...</div>
                        <button onclick="generateStealthFingerprint()" class="w-full py-3 bg-indigo-600 hover:bg-indigo-500 rounded-xl font-bold transition-all text-sm">توليد هوية وهمية 🔀</button>
                    </div>
                </div>
            </div>

            <!-- ===== NETWORK INTELLIGENCE SECTION ===== -->
            <div id="netintel-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-orange-400 border-b border-slate-700 pb-2">🔬 استخبارات الشبكة (TITAN Intel)</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div class="bg-slate-900/50 p-6 rounded-2xl border border-orange-500/20">
                        <label class="block text-sm text-orange-400 mb-3 font-bold">🔍 فحص Shodan (المنافذ العامة):</label>
                        <input type="text" id="shodanIp" placeholder="IP عام..." class="w-full p-3 rounded-xl bg-slate-950 border border-slate-800 text-sm focus:border-orange-500 outline-none mb-4 text-center font-mono">
                        <div id="shodanResult" class="font-mono text-[10px] text-gray-400 mb-4 h-24 overflow-y-auto"></div>
                        <button onclick="runShodanScan()" class="w-full py-3 bg-orange-600 hover:bg-orange-500 rounded-xl font-bold transition-all text-sm">جلب بيانات Shodan 📡</button>
                    </div>
                    <div class="bg-slate-900/50 p-6 rounded-2xl border border-red-500/20 text-center">
                        <label class="block text-sm text-red-400 mb-3 font-bold">🚰 فحص تسريب DNS:</label>
                        <div id="dnsLeakStatus" class="text-2xl font-black mb-1 text-white">—</div>
                        <div id="dnsLeakDetails" class="text-[9px] text-gray-500 mb-4">سيتم فحص خوادم DNS الحالية...</div>
                        <button onclick="checkDnsLeak()" class="w-full py-3 bg-red-600 hover:bg-red-500 rounded-xl font-bold transition-all text-sm">بدء الفحص السريع 🚨</button>
                    </div>
                </div>
            </div>

        </div>
    </div>

    <!-- Panic Button Removed as per User Request -->

    <script>
        // --- نظام المؤثرات الصوتية (Web Audio API) ---
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        let audioCtx;

        function initAudio() {
            if(!audioCtx) audioCtx = new AudioContext();
            if(audioCtx.state === 'suspended') audioCtx.resume();
        }

        // تشغيل نغمة (Oscillator)
        function playTone(freq, type, duration, vol=0.1) {
            if(!audioCtx) return;
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.type = type; // 'sine', 'square', 'sawtooth', 'triangle'
            osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
            gain.gain.setValueAtTime(vol, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration);
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.start();
            osc.stop(audioCtx.currentTime + duration);
        }

        const soundManager = {
            hover: () => playTone(800, 'sine', 0.05, 0.02),
            click: () => { playTone(1200, 'square', 0.05, 0.05); playTone(1600, 'sine', 0.1, 0.02); },
            terminalType: () => playTone(2000 + Math.random()*500, 'square', 0.02, 0.02),
            startupTone: () => { playTone(300, 'sine', 1, 0.1); playTone(600, 'sawtooth', 0.5, 0.05); },
            swoosh: () => { 
                if(!audioCtx) return;
                const osc = audioCtx.createOscillator();
                const gain = audioCtx.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(100, audioCtx.currentTime);
                osc.frequency.exponentialRampToValueAtTime(1200, audioCtx.currentTime + 0.8);
                gain.gain.setValueAtTime(0, audioCtx.currentTime);
                gain.gain.linearRampToValueAtTime(0.3, audioCtx.currentTime + 0.4);
                gain.gain.linearRampToValueAtTime(0.001, audioCtx.currentTime + 0.8);
                osc.connect(gain); gain.connect(audioCtx.destination);
                osc.start(); osc.stop(audioCtx.currentTime + 0.8);
            },
            success: () => { playTone(600, 'sine', 0.1, 0.05); setTimeout(()=>playTone(800, 'sine', 0.2, 0.1), 100); setTimeout(()=>playTone(1200, 'sine', 0.4, 0.15), 250); },
            error: () => { playTone(250, 'sawtooth', 0.3, 0.1); setTimeout(()=>playTone(150, 'sawtooth', 0.5, 0.15), 200); },
            alarm: () => { playTone(800, 'sawtooth', 0.4, 0.1); setTimeout(()=>playTone(600, 'square', 0.4, 0.1), 400); }
        };

        // --- نظام التحكم بجلسة الدخول (Auth Control) ---
        async function doLogout() {
            if (!await titanConfirm('هل أنت متأكد من تسجيل الخروج؟')) return;
            try {
                await fetch('/api/auth/logout', { method: 'POST' });
            } catch(e) {}
            window.location.reload();
        }

        function switchAuthTab(tab) {
            const loginTab = document.getElementById('auth-tab-login');
            const regTab = document.getElementById('auth-tab-register');
            const loginForm = document.getElementById('auth-login-form');
            const regForm = document.getElementById('auth-register-form');
            const verifyForm = document.getElementById('auth-verify-form');
            const forgotForm = document.getElementById('auth-forgot-form'); // NEW
            
            if (tab === 'login') {
                if(loginTab) {
                    loginTab.style.background = 'linear-gradient(135deg, #a855f7, #7c3aed)';
                    loginTab.style.color = 'white';
                    loginTab.style.boxShadow = '0 0 15px rgba(168, 85, 247, 0.4)';
                }
                if(regTab) {
                    regTab.style.background = 'transparent';
                    regTab.style.color = '#6b7280';
                    regTab.style.boxShadow = 'none';
                }
                if (loginForm) loginForm.style.display = 'block';
                if (regForm) regForm.style.display = 'none';
                if (verifyForm) verifyForm.style.display = 'none';
                if (forgotForm) forgotForm.style.display = 'none';
            } else if (tab === 'register') {
                if(regTab) {
                    regTab.style.background = 'linear-gradient(135deg, #7c3aed, #5b21b6)';
                    regTab.style.color = 'white';
                    regTab.style.boxShadow = '0 0 15px rgba(124, 58, 237, 0.4)';
                }
                if(loginTab) {
                    loginTab.style.background = 'transparent';
                    loginTab.style.color = '#6b7280';
                    loginTab.style.boxShadow = 'none';
                }
                if (loginForm) loginForm.style.display = 'none';
                if (regForm) regForm.style.display = 'block';
                if (verifyForm) verifyForm.style.display = 'none';
                if (forgotForm) forgotForm.style.display = 'none';
                resetTermsAgreementGate();
            } else if (tab === 'verify') {
                if (loginForm) loginForm.style.display = 'none';
                if (regForm) regForm.style.display = 'none';
                if (verifyForm) verifyForm.style.display = 'block';
                if (forgotForm) forgotForm.style.display = 'none';
                if(loginTab) { loginTab.style.background = 'transparent'; loginTab.style.color = '#6b7280'; }
                if(regTab) { regTab.style.background = 'transparent'; regTab.style.color = '#6b7280'; }
            } else if (tab === 'forgot') {
                if (loginForm) loginForm.style.display = 'none';
                if (regForm) regForm.style.display = 'none';
                if (verifyForm) verifyForm.style.display = 'none';
                if (forgotForm) forgotForm.style.display = 'block';
                if(loginTab) { loginTab.style.background = 'transparent'; loginTab.style.color = '#6b7280'; }
                if(regTab) { regTab.style.background = 'transparent'; regTab.style.color = '#6b7280'; }
            }
        }

        function updateRegisterButtonState() {
            const btn = document.getElementById('auth-reg-btn');
            const username = document.getElementById('auth-reg-user');
            const email = document.getElementById('auth-reg-email');
            const password = document.getElementById('auth-reg-pass');
            const password2 = document.getElementById('auth-reg-pass2');
            const terms = document.getElementById('auth-reg-terms');

            if (!btn || !username || !email || !password || !password2 || !terms) return;

            const hasCoreData = username.value.trim() && email.value.trim() && password.value && password2.value;
            const accepted = terms.checked;
            const canSubmit = !!hasCoreData && accepted;

            btn.disabled = !canSubmit;
            btn.style.opacity = canSubmit ? '1' : '0.55';
            btn.style.cursor = canSubmit ? 'pointer' : 'not-allowed';
            btn.style.boxShadow = canSubmit ? '0 0 20px rgba(124,58,237,0.4)' : '0 0 20px rgba(124,58,237,0.2)';
        }

        function openTermsModal() {
            const modal = document.getElementById('auth-terms-modal');
            if (modal) modal.style.display = 'flex';
        }

        function closeTermsModal() {
            const modal = document.getElementById('auth-terms-modal');
            if (modal) modal.style.display = 'none';
        }

        function handleTermsModalScroll() {
            const content = document.getElementById('auth-terms-modal-content');
            const confirmBtn = document.getElementById('auth-terms-confirm-btn');
            if (!content || !confirmBtn) return;

            const reachedBottom = (content.scrollTop + content.clientHeight) >= (content.scrollHeight - 8);
            if (reachedBottom) {
                content.dataset.bottomReached = '1';
                confirmBtn.disabled = false;
                confirmBtn.style.opacity = '1';
                confirmBtn.style.cursor = 'pointer';
                confirmBtn.style.background = 'linear-gradient(135deg,#a855f7,#7c3aed)';
                confirmBtn.style.border = '1px solid rgba(168,85,247,0.65)';
                confirmBtn.style.color = 'white';
            }
        }

        function confirmTermsRead() {
            const content = document.getElementById('auth-terms-modal-content');
            const terms = document.getElementById('auth-reg-terms');
            const termsLabel = document.getElementById('auth-reg-terms-label');
            const status = document.getElementById('auth-terms-read-state');
            const errEl = document.getElementById('auth-reg-error');
            if (!content || !terms || !termsLabel || !status) return;

            const reachedBottom = content.dataset.bottomReached === '1';
            if (!reachedBottom) {
                if (errEl) {
                    errEl.textContent = 'الرجاء قراءة الأحكام حتى آخر سطر قبل الموافقة.';
                    errEl.style.display = 'block';
                }
                return;
            }

            terms.disabled = false;
            termsLabel.style.opacity = '1';
            termsLabel.style.cursor = 'pointer';
            terms.style.cursor = 'pointer';
            status.textContent = 'الحالة: تمت قراءة الأحكام ويمكنك الآن تحديد الموافقة.';
            status.style.color = '#4ade80';
            if (errEl) errEl.style.display = 'none';
            closeTermsModal();
            updateRegisterButtonState();
        }

        function resetTermsAgreementGate() {
            const content = document.getElementById('auth-terms-modal-content');
            const confirmBtn = document.getElementById('auth-terms-confirm-btn');
            const terms = document.getElementById('auth-reg-terms');
            const termsLabel = document.getElementById('auth-reg-terms-label');
            const status = document.getElementById('auth-terms-read-state');
            const modal = document.getElementById('auth-terms-modal');

            if (content) {
                content.scrollTop = 0;
                content.dataset.bottomReached = '';
            }
            if (confirmBtn) {
                confirmBtn.disabled = true;
                confirmBtn.style.opacity = '0.65';
                confirmBtn.style.cursor = 'not-allowed';
                confirmBtn.style.background = 'rgba(124,58,237,0.25)';
                confirmBtn.style.border = '1px solid rgba(124,58,237,0.35)';
                confirmBtn.style.color = '#c4b5fd';
            }
            if (terms) {
                terms.checked = false;
                terms.disabled = true;
                terms.style.cursor = 'not-allowed';
            }
            if (termsLabel) {
                termsLabel.style.opacity = '0.55';
                termsLabel.style.cursor = 'not-allowed';
            }
            if (status) {
                status.textContent = 'الحالة: لم يتم تأكيد القراءة بعد.';
                status.style.color = '#6b7280';
            }
            if (modal) modal.style.display = 'none';
            updateRegisterButtonState();
        }

        async function doLogin() {
            const username = document.getElementById('auth-login-user').value.trim();
            const password = document.getElementById('auth-login-pass').value;
            const errEl    = document.getElementById('auth-login-error');
            const btn      = document.getElementById('auth-login-btn');

            errEl.style.display = 'none';
            if (!username || !password) { errEl.textContent = 'يرجى إدخال اسم المستخدم وكلمة السر'; errEl.style.display = 'block'; return; }

            btn.textContent = '⏳ جاري التحقق...';
            btn.disabled = true;

            try {
                const res  = await fetch('/api/auth/login', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username, password}) });
                const data = await res.json();

                if (data.success) {
                    if (data.new_device || data.geo_alert) {
                        titanAlert('⚠️ تنبيه: تم رصد دخول من جهاز أو موقع جديد. تم إرسال تنبيه إلى بريدك الإلكتروني لضمان أمان حسابك.');
                    }
                    setAdminUi(!!data.isAdmin);
                    setAiBubbleVisibility(true);
                    btn.textContent = '✅ تم الدخول بنجاح!';
                    btn.style.background = 'linear-gradient(135deg,#22c55e,#16a34a)';
                    const usernameEl = document.getElementById('header-username');
                    if (usernameEl) usernameEl.textContent = '👤 ' + data.username;
                    setTimeout(showAuthSuccess, 500);
                } else if (data.error === 'EMAIL_NOT_VERIFIED') {
                    btn.textContent = 'دخول إلى TITAN 🔐';
                    btn.disabled = false;
                    document.getElementById('auth-verify-username').value = data.username;
                    switchAuthTab('verify');
                    const vErr = document.getElementById('auth-verify-error');
                    vErr.textContent = 'حسابك غير مفعل، يرجى إدخال كود التحقق المرسل لإيميلك.';
                    vErr.style.display = 'block';
                } else if (data.error === 'ACCOUNT_LOCKED') {
                    errEl.innerHTML = `🚨 حسابك مقفل مؤقتاً!<br>بسبب محاولات فاشلة. حاول مجدداً بعد <span class="font-bold font-mono text-red-300">${data.minutes || data.minutes_remaining || "?"} دقيقة</span>.`;
                    errEl.style.background = 'rgba(239, 68, 68, 0.3)';
                    errEl.style.border = '1px solid rgba(239, 68, 68, 0.8)';
                    errEl.style.display = 'block';
                    btn.textContent = 'دخول إلى TITAN 🔐';
                    btn.disabled = false;
                } else {
                    errEl.textContent = data.error || 'بيانات الدخول غير صحيحة';
                    errEl.style.display = 'block';
                    btn.textContent = 'دخول إلى TITAN 🔐';
                    btn.disabled = false;
                }
            } catch(e) {
                errEl.textContent = 'فشل الاتصال بالخادم.';
                errEl.style.display = 'block';
                btn.textContent = 'دخول إلى TITAN 🔐';
                btn.disabled = false;
            }
        }


        async function doRegister() {
            const username  = document.getElementById('auth-reg-user').value.trim();
            const email     = document.getElementById('auth-reg-email').value.trim();
            const password  = document.getElementById('auth-reg-pass').value;
            const password2 = document.getElementById('auth-reg-pass2').value;
            const acceptedTerms = document.getElementById('auth-reg-terms').checked;
            const errEl     = document.getElementById('auth-reg-error');
            const sucEl     = document.getElementById('auth-reg-success');
            const btn       = document.getElementById('auth-reg-btn');

            errEl.style.display = 'none';
            sucEl.style.display = 'none';

            if (!username || !email || !password || !password2) { errEl.textContent = 'يرجى ملء جميع الحقول'; errEl.style.display = 'block'; return; }
            if (password !== password2) { errEl.textContent = 'كلمتا السر غير متطابقتين!'; errEl.style.display = 'block'; return; }
            if (password.length < 6) { errEl.textContent = 'كلمة السر يجب أن تكون 6 أحرف على الأقل'; errEl.style.display = 'block'; return; }
            if (!acceptedTerms) { errEl.textContent = 'يجب الموافقة على الشروط والأحكام لإكمال إنشاء الحساب.'; errEl.style.display = 'block'; return; }

            btn.textContent = '⏳ جاري إنشاء الحساب...';
            btn.disabled = true;

            try {
                const res  = await fetch('/api/auth/register', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username, password, email, accepted_terms: acceptedTerms}) });
                const data = await res.json();

                if (data.success) {
                    sucEl.textContent = '✅ ' + data.message;
                    sucEl.style.display = 'block';
                    btn.textContent = 'إنشاء حساب جديد ✨';
                    btn.disabled = false;
                    document.getElementById('auth-verify-username').value = username;

                    setTimeout(() => {
                        switchAuthTab('verify');
                    }, 1500);
                } else {
                    errEl.textContent = data.error || 'فشل إنشاء الحساب';
                    errEl.style.display = 'block';
                    btn.textContent = 'إنشاء حساب جديد ✨';
                    btn.disabled = false;
                }
            } catch(e) {
                errEl.textContent = 'فشل الاتصال بالخادم.';
                errEl.style.display = 'block';
                btn.textContent = 'إنشاء حساب جديد ✨';
                btn.disabled = false;
            }
        }

        async function doVerify() {
            const username = document.getElementById('auth-verify-username').value;
            const otp      = document.getElementById('auth-verify-otp').value.trim();
            const errEl    = document.getElementById('auth-verify-error');
            const btn      = document.getElementById('auth-verify-btn');

            errEl.style.display = 'none';
            if (!otp) { errEl.textContent = 'يرجى إدخال كود التحقق'; errEl.style.display = 'block'; return; }

            btn.textContent = '⏳ جاري التفعيل...';
            btn.disabled = true;

            try {
                const res  = await fetch('/api/auth/verify', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username, otp}) });
                const data = await res.json();

                if (data.success) {
                    if (data.auto_login) {
                        titanAlert('✅ تم تفعيل حسابك وتسجيل دخولك بنجاح!');
                        setTimeout(() => location.reload(), 1500);
                    } else {
                        titanAlert('✅ تم تفعيل حسابك بنجاح! يمكنك الآن تسجيل الدخول.');
                        switchAuthTab('login');
                        document.getElementById('auth-login-user').value = username;
                        document.getElementById('auth-login-pass').focus();
                    }
                    btn.textContent = 'تفعيل الحساب 🛡️';
                    btn.disabled = false;
                } else {
                    errEl.textContent = data.error || 'فشل التفعيل';
                    errEl.style.display = 'block';
                    btn.textContent = 'تفعيل الحساب 🛡️';
                    btn.disabled = false;
                }
            } catch(e) {
                errEl.textContent = 'فشل الاتصال بالخادم.';
                errEl.style.display = 'block';
                btn.textContent = 'تفعيل الحساب 🛡️';
                btn.disabled = false;
            }
        }

        let __hudIntervalId = null;
        function updateHUD() {
            loadDashboard();
        }

        function startHUDTicker() {
            if (__hudIntervalId) return;
            updateHUD();
            __hudIntervalId = setInterval(updateHUD, 2000);
        }

        function showAuthSuccess() {
            const overlay = document.getElementById('auth-overlay');
            overlay.style.transition = 'opacity 0.6s ease';
            overlay.style.opacity = '0';
            setTimeout(() => {
                overlay.style.display = 'none';
                overlay.style.opacity = '1';

                // إخفاء intro-overlay فوراً بدلاً من تشغيل شاشة المقدمة
                const introOverlay = document.getElementById('intro-overlay');
                if (introOverlay) {
                    introOverlay.style.display = 'none';
                }

                console.log('Transitioning to main-app...');
                const mainApp = document.getElementById('main-app');
                if (mainApp) {
                    mainApp.classList.remove('opacity-0', 'pointer-events-none');
                    mainApp.style.opacity = '1';
                    mainApp.style.pointerEvents = 'auto';
                    console.log('main-app classes removed:', mainApp.classList);
                    if (typeof introMatrixAnimId !== 'undefined') {
                        cancelAnimationFrame(introMatrixAnimId);
                    }
                    const matrixBg = document.getElementById('matrix-bg');
                    if (matrixBg) matrixBg.style.display = 'block';
                    initMatrix('matrix-bg', false);
                    startHUDTicker();
                    document.querySelectorAll('button').forEach(btn => {
                        btn.addEventListener('mouseenter', soundManager.hover);
                        btn.addEventListener('click', soundManager.click);
                    });
                }
                setAiBubbleVisibility(true);
            }, 600);
        }

        // --- نظام نبض الجلسة (Session Heartbeat) ---
        let heartbeatInterval;
        function startHeartbeat() {
            if (heartbeatInterval) clearInterval(heartbeatInterval);
            heartbeatInterval = setInterval(async () => {
                try {
                    const res = await fetch('/api/auth/heartbeat', {method: 'POST'});
                    if (res.status === 401) {
                        clearInterval(heartbeatInterval);
                        titanAlert('انتهت صلاحية جلستك (خمول تام)، تم تسجيل خروجك لأسباب أمنية.');
                        window.location.reload();
                    }
                } catch(e) {}
            }, 5 * 60 * 1000); // 5 دقائق بين كل نبضة
        }

        // تشغيل النبض تلقائياً عند التأكد من وجود جلسة
        function setAdminUi(isAdmin) {
            const adminBtn = document.getElementById('btn-admin');
            if (!adminBtn) return;
            if (isAdmin) {
                adminBtn.classList.remove('hidden');
                adminBtn.classList.add('flex');
            } else {
                adminBtn.classList.add('hidden');
                adminBtn.classList.remove('flex');
                const adminSection = document.getElementById('admin-section');
                if (adminSection) adminSection.classList.add('hidden');
            }
        }

        async function checkAuth() {
            try {
                const res = await fetch('/api/auth/status');
                const data = await res.json();
                // المستخدم طلب أن شاشة الدخول تظهر كل مرة عند فتح الموقع.
                // إذا كانت هناك جلسة فعّالة، نعمل logout صامت ثم نظهر شاشة الدخول.
                if (data.loggedIn) {
                    try {
                        await fetch('/api/auth/logout', { method: 'POST' });
                    } catch (e) {}
                }

                setAdminUi(false);
                setAiBubbleVisibility(false);
                const mainApp = document.getElementById('main-app');
                if (mainApp) {
                    mainApp.classList.add('opacity-0', 'pointer-events-none');
                    mainApp.style.opacity = '0';
                    mainApp.style.pointerEvents = 'none';
                }
                const introOverlay = document.getElementById('intro-overlay');
                if (introOverlay) introOverlay.style.display = 'none';
                const matrixBg = document.getElementById('matrix-bg');
                if (matrixBg) matrixBg.style.display = 'block';
                document.getElementById('auth-overlay').style.display = 'block';
                initMatrix('auth-matrix', true);
            } catch (e) {
                setAdminUi(false);
                setAiBubbleVisibility(false);
                const mainApp = document.getElementById('main-app');
                if (mainApp) {
                    mainApp.classList.add('opacity-0', 'pointer-events-none');
                    mainApp.style.opacity = '0';
                    mainApp.style.pointerEvents = 'none';
                }
                const introOverlay = document.getElementById('intro-overlay');
                if (introOverlay) introOverlay.style.display = 'none';
                const matrixBg = document.getElementById('matrix-bg');
                if (matrixBg) matrixBg.style.display = 'block';
                document.getElementById('auth-overlay').style.display = 'block';
                initMatrix('auth-matrix', true);
            }
        }

        // --- إدارة المقدمة الفاخرة (Premium IntroFade In) ---
        function runIntroSequence() {
            setTimeout(() => {
                const logoContainer = document.getElementById('intro-center-logo');
                logoContainer.classList.remove('opacity-0', 'translate-y-8');
                soundManager.startupTone();
                setTimeout(() => document.getElementById('start-btn').classList.add('show'), 600);
            }, 300);
        }

        // أداة لمعرفة متى المستخدم ضغط أي زر لتفعيل الصوت (لأن المتصفحات تمنع الصوت بدون تفاعل)
        window.addEventListener('click', () => { initAudio(); }, {once:true});
        function initRegisterTermsUi() {
            ['auth-reg-user', 'auth-reg-email', 'auth-reg-pass', 'auth-reg-pass2'].forEach((id) => {
                const el = document.getElementById(id);
                if (el) el.addEventListener('input', updateRegisterButtonState);
            });
            const terms = document.getElementById('auth-reg-terms');
            if (terms) terms.addEventListener('change', updateRegisterButtonState);
            resetTermsAgreementGate();
            loadOsintWatchlist();
        }
        window.onload = () => {
            initRegisterTermsUi();
            setTimeout(checkAuth, 100);
        };

        function startSystem() {
            soundManager.click();
            setTimeout(() => soundManager.swoosh(), 200); 
            
            const intro = document.getElementById('intro-overlay');
            const app = document.getElementById('main-app');
            
            intro.style.transform = 'scale(1.05)';
            intro.style.opacity = '0';
            
            setTimeout(() => {
                intro.style.display = 'none';
                if(typeof introMatrixAnimId !== 'undefined') cancelAnimationFrame(introMatrixAnimId);
                app.classList.remove('opacity-0', 'pointer-events-none');
                
                document.querySelectorAll('button').forEach(btn => {
                    btn.addEventListener('mouseenter', soundManager.hover);
                    btn.addEventListener('click', soundManager.click);
                });
                document.querySelectorAll('input, textarea').forEach(inp => inp.addEventListener('focus', soundManager.hover));
                
                startHUDTicker();
            }, 1000);
        }

        // --- وظائف الأمان الجديدة (Security Tab / JS) ---

        function loadSecurityTab() {
            loadActiveSessions();
            checkCanaryStatus();
            loadSecurityLogsInterval(); // load specific terminal UI
            loadTimeLockedFiles();
        }

        async function doPanic() {
            if (!await titanConfirm('🚨 خيار الدمار شامل! هذا سيشفر كامل بيانات القبو بمفتاح عشوائي جديد ويحذفه للأبد! لن تتمكن من استرجاع البيانات أبداً! متأكد؟')) return;
            try {
                const res = await fetch('/api/security/panic', {method:'POST'});
                const data = await res.json();
                if (data.success) {
                    titanAlert('💥 تم محو البيانات وتدمير الجلسات بنجاح. سيتم تسجيل الخروج فوراً.');
                    window.location.reload();
                } else { titanAlert(data.error); }
            } catch(e) { titanAlert('فشل الاتصال بمفرقعات الأمان 💣'); }
        }

        async function checkIntegrity() {
            const st = document.getElementById('integrity-status');
            st.innerHTML = '<span class="text-yellow-400">جاري فحص المكونات... 🔍</span>';
            try {
                const res = await fetch('/api/security/integrity');
                const data = await res.json();
                if(data.status === 'ok') {
                    st.innerHTML = '<span class="text-green-400 font-bold">✅ المكونات مطابقة للأساس (Safe)</span>';
                } else if (data.status === 'altered') {
                    st.innerHTML = '<span class="text-red-500 font-bold">🚨 تم اكتشاف تغيير في ملفات النظام!</span><br><span class="text-[10px] text-red-400">ملف app.py تم تعديله أو اختراقه.</span>';
                } else {
                    st.innerHTML = '<span class="text-yellow-500 font-bold">⚠️ الأساس (Baseline) غير موجود، الرجاء تحديثه أولاً.</span>';
                }
            } catch(e) { st.innerText = 'فشل الفحص'; }
        }

        async function resetBaseline() {
            if(!await titanConfirm('هل أنت متأكد من أن الكود الحالي نظيف وموثوق وتريد تعيينه كأساسيات رسمية للمستقبل؟')) return;
            try {
                const res = await fetch('/api/security/integrity/reset', {method:'POST'});
                const data = await res.json();
                if(data.success) { titanAlert('✅ تم تحديث أساس الفحص للملفات الحالية وتوثيقها.'); checkIntegrity(); }
            } catch(e) {}
        }

        async function loadActiveSessions() {
            const list = document.getElementById('sessions-list');
            list.innerHTML = 'جاري الجلب...';
            try {
                const res = await fetch('/api/auth/sessions');
                const data = await res.json();
                if(data.error) throw new Error();
                
                let html = '';
                data.sessions.forEach(s => {
                    html += `
                        <div class="flex justify-between items-center bg-slate-800/80 p-2 rounded border border-slate-700">
                            <div>
                                <div class="text-blue-300">${s.ip} <span class="text-gray-500">(${s.country || 'Unknown'})</span></div>
                                <div class="text-[10px] text-gray-500 truncate w-48" title="${s.user_agent}">${s.user_agent.split(' ').slice(-1)}</div>
                                <div class="text-[9px] text-gray-600">${s.created_at}</div>
                            </div>
                            <button onclick="revokeSession(${s.id})" class="text-red-400 hover:text-red-300 text-[10px] border border-red-900/40 p-1 rounded">طرد 🚪</button>
                        </div>
                    `;
                });
                list.innerHTML = html || 'لا توجد جلسات أخرى نشطة.';
            } catch(e) { list.innerHTML = 'خطأ.'; }
        }

        async function revokeSession(sessionId) {
            try {
                await fetch('/api/auth/sessions/revoke', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({session_id: sessionId})});
                loadActiveSessions();
            } catch(e) {}
        }
        
        async function revokeAllSessions() {
            if(!await titanConfirm('هذا سيخرجك من جميع الأجهزة النشطة. متأكد؟')) return;
            try {
                await fetch('/api/auth/sessions/revoke', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({all:true})});
                titanAlert('تم تسجيل الخروج من كل الأجهزة.'); 
                loadActiveSessions();
            } catch(e) {}
        }

        async function checkCanaryStatus() {
            const el = document.getElementById('canary-status');
            try {
                // Since there is no /api/canary endpoint explicitly returning logs in the backend (we added security_logs API instead),
                // We fetch logs and filter for "Canary" or we can just fetch all security logs and display canary triggers
                const res = await fetch('/api/security/logs');
                const data = await res.json();
                const logs = data.logs || [];
                const canaryLogs = logs.filter(l => l.action.toLowerCase().includes('canary') || l.action.includes('مصيدة'));
                if(canaryLogs.length === 0) {
                    el.innerHTML = '<span class="text-green-500">الفخ سليم (لم يقترب أحد). ✅</span>';
                } else {
                    let h = '';
                    canaryLogs.forEach(l => {
                        h += `<div class="text-red-400">🚨 تم التطفل من ${l.ip} <br><span class="text-gray-500 text-[10px]">${l.time}</span></div>`;
                    });
                    el.innerHTML = h;
                }
            } catch(e) {}
        }

        let mainLogsInterval;
        async function loadSecurityLogsInterval() {
            const term = document.getElementById('security-terminal');
            if(mainLogsInterval) clearInterval(mainLogsInterval);
            
            async function fetchsec() {
                try {
                    const res = await fetch('/api/security/logs');
                    const data = await res.json();
                    const logs = data.logs || [];
                    let html = '';
                    logs.forEach(l => {
                        let color = l.action.includes('فشل') || l.action.includes('🚨') ? 'text-red-400' : 'text-purple-300';
                        html += `
                            <div><span class="text-gray-500">[${l.time.split(' ')[1]}]</span> <span class="text-blue-400">${l.ip}</span> <span class="${color}">${l.action}</span> - ${l.details.substring(0,30)}</div>
                        `;
                    });
                    term.innerHTML = html;
                } catch(e) {}
            }
            fetchsec();
            mainLogsInterval = setInterval(fetchsec, 5000); // تحديث كل 5 ثواني
        }

        async function uploadTimelocked() {
            const file = document.getElementById('tl-file').files[0];
            const pass = document.getElementById('tl-pass').value;
            const unlockAt = document.getElementById('tl-unlock-at').value; // format: 2026-02-27T15:30
            const status = document.getElementById('tl-status');
            
            if(!file || !pass || !unlockAt) { status.innerHTML = "<span class='text-red-400'>أكمل جميع الحقول</span>"; return; }
            const isoTime = new Date(unlockAt).toISOString().replace('T', ' ').substring(0, 19);
            
            const form = new FormData();
            form.append('file', file);
            form.append('vault_password', pass);
            form.append('unlock_at', isoTime);
            
            status.innerHTML = "جاري التشفير والرفع... ⏳";
            try {
                const res = await fetch('/api/vault/timelocked/upload', {method:'POST', body:form});
                const data = await res.json();
                if(data.success) {
                    status.innerHTML = "<span class='text-green-400'>تم الرفع والقفل المحكم ✅</span>";
                    document.getElementById('tl-file').value = '';
                    document.getElementById('tl-pass').value = '';
                    loadTimeLockedFiles();
                } else {
                    status.innerHTML = `<span class='text-red-400'>${data.error}</span>`;
                }
            } catch(e) {}
        }
        
        async function loadTimeLockedFiles() {
            const list = document.getElementById('tl-list');
            list.innerHTML = 'جاري التحديث...';
            try {
                const res = await fetch('/api/vault/timelocked/list');
                const data = await res.json();
                if(data.error) throw new Error();
                
                let h='';
                data.files.forEach(f => {
                    if (f.locked) {
                        h+= `<div class="bg-yellow-900/20 p-2 rounded border border-yellow-800/40 opacity-70">
                                <div class="font-bold text-yellow-500">🔒 ${f.filename}</div>
                                <div class="text-gray-500 text-[10px]">مغلق، يفتح في: ${f.unlock_at}</div>
                             </div>`;
                    } else {
                        h+= `<div class="bg-green-900/20 p-2 border border-green-800/40 rounded mt-1 flex justify-between items-center">
                                <div>
                                    <div class="font-bold text-green-400">🔓 ${f.filename}</div>
                                    <div class="text-gray-500 text-[10px]">مفتوح جاهز للتحميل</div>
                                </div>
                                <button onclick="downloadTimelocked(${f.id}, '${f.filename}')" class="bg-green-700/50 px-2 py-1 rounded text-[10px]">تحميل الآن</button>
                            </div>`;
                    }
                });
                list.innerHTML = h || '<div class="text-gray-600">القبو הזمني فارغ.</div>';
            } catch(e) {}
        }
        
        async function downloadTimelocked(id, filename) {
            const pass = prompt(`أدخل كلمة سر القبو لفتح ${filename}:`);
            if(!pass) return;
            const res = await fetch('/api/vault/timelocked/download', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({file_id: id, vault_password: pass})
            });
            if (!res.ok) {
                const data = await res.json();
                titanAlert(data.error || 'فشل التنزيل'); return;
            }
            const blob = await res.blob();
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(downloadUrl);
        }

        // --- 3D Matrix Rain (Violet/Purple Theme) ---
        function initMatrix(canvasId, isPremium3D = false) {
            const canvas = document.getElementById(canvasId);
            if(!canvas) return;
            const ctx = canvas.getContext('2d');
            canvas.width = window.innerWidth; canvas.height = window.innerHeight;
            
            const chars = "∑πΩΔΦΨΓΛΞ∞∫∬∮∇∂</√∛∝∠∩∪∴∵∼≈≅≠≡≤≥⊂⊃⊕⊗⊙⊢⊣⊥⊨⊩∀∃∄∅∉∈∊∋∌∏∐".split("");
            const fontSize = isPremium3D ? 12 : 10;
            const columns = canvas.width / fontSize;
            const drops = [];
            const speeds = [];
            const depths = []; 
            
            for(let x = 0; x < columns; x++) {
                drops[x] = Math.random() * -100;
                speeds[x] = isPremium3D ? (Math.random() * 0.5 + 0.2) : (Math.random() * 1 + 0.5);
                depths[x] = Math.random(); 
            }

            let animId;
            function draw() {
                // Fade effect matching dark background (higher alpha for cleaner tails)
                ctx.fillStyle = isPremium3D ? "rgba(5, 5, 5, 0.25)" : "rgba(10, 10, 10, 0.15)"; 
                ctx.fillRect(0, 0, canvas.width, canvas.height);

                for(let i = 0; i < drops.length; i++) {
                    if (drops[i] < 0) {
                        drops[i] += speeds[i];
                        continue;
                    }
                    
                    const text = chars[Math.floor(Math.random() * chars.length)];
                    ctx.font = (fontSize * (isPremium3D ? (depths[i] * 0.5 + 0.8) : 1)) + "px monospace";
                    
                    const baseAlpha = isPremium3D ? depths[i] : 1;
                    
                    if (Math.random() > 0.98) ctx.fillStyle = `rgba(255, 255, 255, ${baseAlpha})`; 
                    else if (Math.random() > 0.9) ctx.fillStyle = `rgba(168, 85, 247, ${baseAlpha})`; // Purple
                    else if (Math.random() > 0.7) ctx.fillStyle = `rgba(139, 92, 246, ${baseAlpha})`; // Deep Violet
                    else ctx.fillStyle = `rgba(88, 28, 135, ${baseAlpha})`; // Very Deep Purple

                    ctx.fillText(text, i * fontSize, drops[i] * fontSize);
                    
                    if(drops[i] * fontSize > canvas.height && Math.random() > 0.98) {
                        drops[i] = 0;
                        speeds[i] = isPremium3D ? (Math.random() * 0.5 + 0.2) : (Math.random() * 1 + 0.5); 
                    }
                    drops[i] += speeds[i];
                }
                animId = requestAnimationFrame(draw);
            }
            draw();
            
            window.addEventListener('resize', () => { 
                canvas.width = window.innerWidth; 
                canvas.height = window.innerHeight; 
            });
            return animId; 
        }

        let introMatrixAnimId = initMatrix('intro-matrix', true);
        initMatrix('matrix-bg', false);

        // --- نظام التنبيهات الصوتية ---


        // --- التحكم بالتبويبات ---
        const ALL_TABS = ['dash','pass','vault','crypt','suite','tools','ghost','osint','ir','maltego','hunting','forensics','brand','se','advcrypto','audio','video','qr','identity','extreme','netintel','admin'];
        let _aiActiveSubTab = 'chat';
        let _prevTab = 'pass';

        function openAiSection() {
            const sec = document.getElementById('ai-section');
            if (sec) {
                sec.classList.remove('hidden');
                sec.style.left = 'auto';
                sec.style.right = '16px';
                sec.style.bottom = '84px';
                sec.style.display = 'block';
                sec.style.pointerEvents = 'auto';
            }
            showAiSubTab(_aiActiveSubTab || 'chat');
        }

        function closeAiBubble() {
            const sec = document.getElementById('ai-section');
            if (sec) {
                sec.classList.add('hidden');
                sec.style.display = 'none';
                sec.style.pointerEvents = 'none';
            }
        }

        function setAiBubbleVisibility(isVisible) {
            const launcher = document.getElementById('ai-float-launcher');
            if (!launcher) return;
            if (isVisible) {
                launcher.classList.remove('hidden');
                launcher.style.position = 'fixed';
                launcher.style.left = 'auto';
                launcher.style.right = '16px';
                launcher.style.bottom = '12px';
                launcher.style.display = 'flex';
                launcher.style.alignItems = 'center';
                launcher.style.justifyContent = 'center';
                launcher.style.visibility = 'visible';
                launcher.style.opacity = '1';
                launcher.style.pointerEvents = 'auto';
            } else {
                launcher.classList.add('hidden');
                launcher.style.display = 'none';
                launcher.style.visibility = 'hidden';
                launcher.style.opacity = '0';
                launcher.style.pointerEvents = 'none';
            }
            if (!isVisible) closeAiBubble();
        }

        function toggleAiBubble() {
            const sec = document.getElementById('ai-section');
            if (!sec) return;
            if (sec.classList.contains('hidden')) openAiSection();
            else closeAiBubble();
        }

        function scrollAiChatToBottom() {
            const box = document.getElementById('ai-chat-messages');
            if (!box) return;
            requestAnimationFrame(() => { box.scrollTop = box.scrollHeight; });
        }

        function showAiSubTab(tab) {
            const valid = ['chat', 'analysis', 'support'];
            const t = valid.includes(tab) ? tab : 'chat';
            _aiActiveSubTab = t;

            const map = {
                chat: document.getElementById('ai-sub-content-chat'),
                analysis: document.getElementById('ai-sub-content-analysis'),
                support: document.getElementById('ai-sub-content-support')
            };
            Object.keys(map).forEach(k => {
                const el = map[k];
                if (el) el.classList.toggle('hidden', k !== t);
            });

            const btnMap = {
                chat: document.getElementById('ai-subtab-chat'),
                analysis: document.getElementById('ai-subtab-analysis'),
                support: document.getElementById('ai-subtab-support')
            };
            Object.keys(btnMap).forEach(k => {
                const b = btnMap[k];
                if (!b) return;
                if (k === t) {
                    b.classList.remove('border-slate-700', 'text-gray-300', 'bg-slate-800/60');
                    b.classList.add('border-purple-700/50', 'bg-purple-900/40', 'text-purple-300');
                } else {
                    b.classList.remove('border-purple-700/50', 'bg-purple-900/40', 'text-purple-300');
                    b.classList.add('border-slate-700', 'text-gray-300', 'bg-slate-800/60');
                }
            });

            if (t === 'support' && typeof loadSupportTickets === 'function') {
                loadSupportTickets();
            }
            if (t === 'chat') {
                scrollAiChatToBottom();
            }
        }

        function normalizeArabicSearchText(value) {
            return (value || '')
                .toLowerCase()
                .replace(/[\\u064B-\\u065F\\u0670]/g, '')   // remove Arabic diacritics
                .replace(/\u0640/g, '')                    // remove tatweel
                .replace(/[أإآٱ]/g, 'ا')
                .replace(/ؤ/g, 'و')
                .replace(/ئ/g, 'ي')
                .replace(/ى/g, 'ي')
                .replace(/ة/g, 'ه')
                .replace(/\\s+/g, ' ')
                .trim();
        }

        function filterNavTabs(rawValue) {
            const query = normalizeArabicSearchText(rawValue);
            const allButtons = document.querySelectorAll('.tab-nav-modern .tab-grid button');
            let visibleCount = 0;

            allButtons.forEach(btn => {
                if (btn.classList.contains('hidden')) return;
                const label = normalizeArabicSearchText(btn.innerText || btn.textContent || '');
                const shouldShow = !query || label.includes(query);
                btn.style.display = shouldShow ? '' : 'none';
                if (shouldShow) visibleCount += 1;
            });

            document.querySelectorAll('.tab-nav-modern .tab-group').forEach(group => {
                const groupButtons = group.querySelectorAll('.tab-grid button');
                const hasVisible = Array.from(groupButtons).some(btn => btn.style.display !== 'none' && !btn.classList.contains('hidden'));
                group.style.display = hasVisible ? '' : 'none';
            });

            const empty = document.getElementById('tab-search-empty');
            if (empty) empty.classList.toggle('hidden', !(query && visibleCount === 0));
        }

        function showTab(type) {
            // Auto-lock vault silently when leaving it
            if (_prevTab === 'vault' && type !== 'vault' && currentMasterKey) {
                lockVault(true);
            }
            _prevTab = type;
            ALL_TABS.forEach(t => {
                const sec = document.getElementById(t + '-section');
                const btn = document.getElementById('btn-' + t);
                if(sec) {
                    sec.classList.toggle('hidden', t !== type);
                    if (t === type) _animateTabSection(sec);
                }
                if(btn) {
                    if(t === type) {
                        btn.classList.add('tab-active');
                        btn.classList.remove('text-gray-400');
                        btn.classList.add('bg-purple-600/90', 'text-white');
                    } else {
                        btn.classList.remove('tab-active', 'tab-active-vault', 'bg-purple-600/90', 'text-white', 'bg-yellow-600/90', 'text-slate-900');
                        btn.classList.add('text-gray-400');
                    }
                }
            });
            // Special vault styling
            const vBtn = document.getElementById('btn-vault');
            if(vBtn) {
                if(type === 'vault') {
                    vBtn.classList.remove('tab-active');
                    vBtn.classList.add('tab-active-vault');
                    vBtn.classList.add('bg-yellow-600/90', 'text-slate-900');
                    vBtn.classList.remove('text-gray-400', 'bg-purple-600/90');
                }
            }
            if(type === 'dash') {
                loadDashboard();
                if (!window.dashInterval) window.dashInterval = setInterval(loadDashboard, 1000);
            } else {
                if (window.dashInterval) { clearInterval(window.dashInterval); window.dashInterval = null; }
            }
            if(type === 'tools' && typeof fetchIpIntel === 'function') fetchIpIntel();
            if(type === 'osint' && typeof loadOsintWatchlist === 'function') loadOsintWatchlist();
            if(type === 'ir' && typeof irLoadCases === 'function') irLoadCases();
            if(type === 'se' && typeof seLoadIntelBoard === 'function') seLoadIntelBoard();
            if(type === 'admin' && typeof loadAdminSupportTickets === 'function') loadAdminSupportTickets();

            const activeBtn = document.getElementById('btn-' + type);
            if (activeBtn && typeof activeBtn.scrollIntoView === 'function') {
                activeBtn.scrollIntoView({behavior: 'smooth', inline: 'center', block: 'nearest'});
            }
        }

        function _resultGetElement(target) {
            if (!target) return null;
            return typeof target === 'string' ? document.getElementById(target) : target;
        }

        function _resultEscape(value) {
            const div = document.createElement('div');
            div.textContent = String(value ?? '');
            return div.innerHTML;
        }

        function _resultToneByScore(score) {
            const n = Number(score || 0);
            if (n >= 70) return 'danger';
            if (n >= 35) return 'warn';
            return 'safe';
        }

        function _resultRiskClass(score) {
            const tone = _resultToneByScore(score);
            if (tone === 'danger') return 'risk-danger';
            if (tone === 'warn') return 'risk-warn';
            return 'risk-safe';
        }

        function _resultApplyRiskTheme(el, riskScore) {
            if (!el || riskScore === undefined || riskScore === null) return;
            el.classList.remove('risk-safe', 'risk-warn', 'risk-danger');
            el.classList.add(_resultRiskClass(riskScore));
        }

        function _animateTabSection(sec) {
            if (!sec) return;
            sec.classList.remove('tab-section-enter');
            void sec.offsetWidth;
            sec.classList.add('tab-section-enter');
        }

        function setResultLoading(target, title, hint) {
            const el = _resultGetElement(target);
            if (!el) return;
            el.classList.remove('hidden');
            el.classList.add('result-panel', 'result-panel--loading');
            el.classList.remove('risk-safe', 'risk-warn', 'risk-danger');
            el.innerHTML = `
                <div class="result-head">
                    <div class="result-title">${_resultEscape(title || 'جاري التحليل')}</div>
                    <div class="result-badge">Live</div>
                </div>
                <div class="result-list">
                    <div class="result-skeleton"></div>
                    <div class="result-skeleton"></div>
                </div>
                ${hint ? `<div class="text-[11px] text-indigo-300 mt-2">${_resultEscape(hint)}</div>` : ''}
            `;
        }

        function setResultError(target, message) {
            const el = _resultGetElement(target);
            if (!el) return;
            el.classList.remove('hidden');
            el.classList.add('result-panel');
            el.classList.remove('result-panel--loading');
            el.classList.remove('risk-safe', 'risk-warn');
            el.classList.add('risk-danger');
            el.innerHTML = `
                <div class="result-head">
                    <div class="result-title text-red-300">Error</div>
                    <div class="result-badge" style="border-color:rgba(239,68,68,0.35);color:#fca5a5;">Failed</div>
                </div>
                <div class="result-list-item text-red-300 bg-red-900/20 border-red-800/50">${_resultEscape(message || 'حدث خطأ غير متوقع')}</div>
            `;
        }

        function setResultInfo(target, title, entries, options = {}) {
            const el = _resultGetElement(target);
            if (!el) return;
            const cols = options.cols || 2;
            const badge = options.badge || 'Updated';
            const rows = Array.isArray(entries) ? entries : [];
            el.classList.remove('hidden');
            el.classList.add('result-panel');
            el.classList.remove('result-panel--loading');
            el.classList.remove('risk-safe', 'risk-warn', 'risk-danger');
            _resultApplyRiskTheme(el, options.riskScore);
            el.innerHTML = `
                <div class="result-head">
                    <div class="result-title">${_resultEscape(title || 'النتيجة')}</div>
                    <div class="result-badge">${_resultEscape(badge)}</div>
                </div>
                <div class="result-kv-grid cols-${cols}">
                    ${rows.map((item) => `
                        <div class="result-kv-item result-tone-${_resultEscape(item.tone || 'info')}">
                            <div class="result-kv-label">${_resultEscape(item.label || 'Field')}</div>
                            <div class="result-kv-value" ${item.dir ? `dir="${_resultEscape(item.dir)}"` : ''}>${_resultEscape(item.value ?? 'N/A')}</div>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        function setResultList(target, title, rows, options = {}) {
            const el = _resultGetElement(target);
            if (!el) return;
            const badge = options.badge || 'Records';
            const emptyText = options.emptyText || 'لا توجد نتائج';
            const safeRows = Array.isArray(rows) ? rows : [];
            el.classList.remove('hidden');
            el.classList.add('result-panel');
            el.classList.remove('result-panel--loading');
            el.classList.remove('risk-safe', 'risk-warn', 'risk-danger');
            _resultApplyRiskTheme(el, options.riskScore);
            el.innerHTML = `
                <div class="result-head">
                    <div class="result-title">${_resultEscape(title || 'النتائج')}</div>
                    <div class="result-badge">${_resultEscape(badge)}</div>
                </div>
                <div class="result-list">
                    ${safeRows.length ? safeRows.map((row) => `<div class="result-list-item">${row}</div>`).join('') : `<div class="result-list-item text-gray-400">${_resultEscape(emptyText)}</div>`}
                </div>
            `;
        }

        function setResultMarkup(target, title, html, options = {}) {
            const el = _resultGetElement(target);
            if (!el) return;
            const badge = options.badge || 'Updated';
            el.classList.remove('hidden');
            el.classList.add('result-panel');
            el.classList.remove('result-panel--loading');
            el.classList.remove('risk-safe', 'risk-warn', 'risk-danger');
            _resultApplyRiskTheme(el, options.riskScore);
            el.innerHTML = `
                <div class="result-head">
                    <div class="result-title">${_resultEscape(title || 'النتيجة')}</div>
                    <div class="result-badge">${_resultEscape(badge)}</div>
                </div>
                ${html || '<div class="result-list-item text-gray-400">لا توجد نتائج.</div>'}
            `;
        }

        function enhanceResultPanels() {
            const selectors = [
                '[id$="Result"]',
                '[id$="result"]',
                '#ipDataBox',
                '#openPortsContainer',
                '#osintResult',
                '#phoneResult',
                '#urlResult',
                '#phishResult',
                '#leakEmailPassResult',
                '#ipqsLogsResult'
            ];

            document.querySelectorAll(selectors.join(',')).forEach((el) => {
                if (!el.classList.contains('result-panel') && (el.textContent || '').trim()) {
                    el.classList.add('result-panel');
                }
            });

            if (window.__titanResultObserver) return;
            window.__titanResultObserver = new MutationObserver(() => {
                document.querySelectorAll(selectors.join(',')).forEach((el) => {
                    if (!el.classList.contains('hidden') && (el.textContent || '').trim()) {
                        el.classList.add('result-panel');
                    }
                });
            });
            window.__titanResultObserver.observe(document.body, { childList: true, subtree: true, characterData: true });
        }

        const passInput = document.getElementById('passInput');
        passInput.addEventListener('input', async () => {
            const val = passInput.value;
            if(!val) { document.getElementById('pass-result').classList.add('hidden'); return; }
            const res = await fetch('/scan', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({target:val}) });
            const data = await res.json();
            document.getElementById('pass-result').classList.remove('hidden');
            document.getElementById('strength-text').innerText = data.strength;
            document.getElementById('strength-percent').innerText = ((data.score + 1) * 20) + "%";
            const bar = document.getElementById('strength-bar');
            bar.style.width = (data.score + 1) * 20 + "%";
            bar.style.backgroundColor = ['#ef4444', '#f97316', '#eab308', '#a855f7', '#22c55e'][data.score];
            const leak = document.getElementById('leak-info');
            leak.classList.remove('hidden');
            if(data.exposed_count > 0) {
                soundManager.alarm(); // صوت إنذار الاختراق
                leak.innerHTML = `🚨 متسربة في <b>${data.exposed_count}</b> خرق!`;
                leak.className = "p-4 rounded-xl border border-red-800 bg-red-900/20 text-red-400";
            } else {
                soundManager.success();
                leak.innerHTML = `✅ لم يتم العثور عليها في تسريبات معروفة.`;
                leak.className = "p-4 rounded-xl border border-green-800 bg-green-900/20 text-green-400";
            }
        });

        async function processText(action) {
            const text = document.getElementById('cryptText').value;
            const key = document.getElementById('cryptKey').value;
            if(!text || !key) return titanAlert("يرجى إدخال النص وكلمة السر!");
            const res = await fetch('/crypt-text', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text, key, action}) });
            const data = await res.json();
            if(data.error) titanAlert(data.error); else document.getElementById('cryptText').value = data.result;
        }

        async function processFile(action) {
            const file = document.getElementById('fileInput').files[0];
            const key = document.getElementById('cryptKey').value;
            if(!file || !key) return titanAlert("يرجى اختيار ملف وإدخال كلمة السر!");
            const formData = new FormData();
            formData.append('file', file);
            formData.append('key', key);
            formData.append('action', action);
            const res = await fetch('/crypt-file', { method:'POST', body: formData });
            if(res.ok) {
                soundManager.success();
                const blob = await res.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = action === 'encrypt' ? file.name + '.titan' : file.name.replace('.titan', '');
                a.click();
            } else {
                soundManager.error();
                const err = await res.json(); titanAlert(err.error);
            }
        }

        async function generatePass(mode = 'random') {
            const res = await fetch(`/generate?mode=${mode}`);
            const data = await res.json();
            document.getElementById('suggested-pass').innerText = data.suggested;
            document.getElementById('suggested-pass-container').classList.remove('hidden');
        }

        function copyPass() {
            navigator.clipboard.writeText(document.getElementById('suggested-pass').innerText);
            titanAlert("تم النسخ!");
        }
        async function checkIP() {
            let ip = document.getElementById('ipInput').value.trim();
            const resultDiv = document.getElementById('ipResult');
            const dataBox = document.getElementById('ipDataBox');
            
            resultDiv.classList.remove('hidden');
            setResultLoading(dataBox, 'IP Intelligence', 'جاري التقاط الحزم وتحليل مسار الاتصال...');
            soundManager.terminalType();

            // فحص الـ IP من جهة العميل لضمان مرور الطلب عبر أي متصفح VPN نشط
            if (!ip) {
                try {
                    const ipRes = await fetch('https://api.ipify.org?format=json');
                    const ipData = await ipRes.json();
                    if(ipData && ipData.ip) ip = ipData.ip;
                } catch (e) {
                    console.log("Fallback to backend IP detection");
                }
            }

            const res = await fetch('/api/ip', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ip}) });
            const data = await res.json();
            
            if (data.success) {
                soundManager.success();
                const proxyFlag = String(data.proxy || data.vpn || '').toLowerCase();
                const proxyDetected = proxyFlag === 'true' || proxyFlag === '1' || data.proxy === true || data.vpn === true;
                setResultInfo(dataBox, 'IP Intelligence', [
                    { label: 'IP', value: ip || data.query || 'غير معروف', tone: 'info', dir: 'ltr' },
                    { label: 'ISP', value: data.ISP || 'غير متاح', tone: 'info' },
                    { label: 'Country', value: data.country_code || 'N/A', tone: 'info' },
                    { label: 'Privacy Risk', value: proxyDetected ? 'Proxy/VPN محتمل' : 'لا يوجد Proxy واضح', tone: proxyDetected ? 'warn' : 'safe' }
                ], { badge: proxyDetected ? 'Suspicious' : 'Clean', cols: 2, riskScore: proxyDetected ? 70 : 15 });
            } else {
                soundManager.error();
                setResultError(dataBox, data.message || 'فشل جلب البيانات');
            }
        }

        async function generate2FA() {
            const res = await fetch('/api/2fa/generate');
            const data = await res.json();
            document.getElementById('tfaResult').classList.remove('hidden');
            document.getElementById('qrCodeImg').src = data.qr_code;
            document.getElementById('tfaSecret').innerText = data.secret;
            document.getElementById('tfaCodeInput').value = '';
        }

        async function verify2FA() {
            const secret = document.getElementById('tfaSecret').innerText;
            const code = document.getElementById('tfaCodeInput').value;
            if(!secret || !code) return titanAlert("الرجاء إدخال الرمز للتحقق!");
            
            const res = await fetch('/api/2fa/verify', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({secret, code})
            });
            const data = await res.json();
            if(data.valid) {
                soundManager.success();
                titanAlert("✅ الرمز صحيح! المصادقة ناجحة.");
            } else {
                soundManager.error();
                titanAlert("❌ الرمز خاطئ أو منتهي الصلاحية.");
            }
        }

        // --- منطق قبو كلمات المرور المكتوب بـ Vanilla JS ---
        let vaultData = [];
        let currentMasterKey = "";

        async function checkVaultPasswordSetup() {
            // Called when vault tab is clicked — shows setup or login panel
            try {
                const res = await fetch('/api/vault/has-password');
                const data = await res.json();
                const setupPanel = document.getElementById('vault-setup');
                const loginPanel = document.getElementById('vault-login');
                if (!data.hasVaultPassword) {
                    // First time: show setup panel
                    if (setupPanel) setupPanel.classList.remove('hidden');
                    if (loginPanel) loginPanel.classList.add('hidden');
                } else {
                    // Already has a password: show login panel
                    if (setupPanel) setupPanel.classList.add('hidden');
                    if (loginPanel) loginPanel.classList.remove('hidden');
                }
            } catch(e) { /* backend not running, just show login */ }
        }

        async function setVaultPassword() {
            const pw1 = document.getElementById('vaultSetupPass1').value;
            const pw2 = document.getElementById('vaultSetupPass2').value;
            const errEl = document.getElementById('vaultSetupError');
            errEl.classList.add('hidden');
            if (!pw1) { errEl.textContent = 'أدخل كلمة السر.'; errEl.classList.remove('hidden'); return; }
            if (pw1.length < 4) { errEl.textContent = 'كلمة السر يجب أن تكون 4 أحرف على الأقل.'; errEl.classList.remove('hidden'); return; }
            if (pw1 !== pw2) { errEl.textContent = 'كلمتا السر غير متطابقتين!'; errEl.classList.remove('hidden'); return; }
            const res = await fetch('/api/vault/set-password', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ password: pw1 })
            });
            const data = await res.json();
            if (data.error) { errEl.textContent = data.error; errEl.classList.remove('hidden'); return; }
            soundManager.success();
            // Switch to login view and pre-fill the password
            document.getElementById('vault-setup').classList.add('hidden');
            document.getElementById('vault-login').classList.remove('hidden');
            document.getElementById('vaultMasterKey').value = pw1;
            await unlockVault(); // Auto-open vault right after setup
        }

        // --- Vault Logic ---
        let vaultFailedAttempts = 0;

        function triggerVaultLockout() {
            // Full-screen red lockout overlay — same feel as burn chat blackout
            const overlay = document.createElement('div');
            overlay.id = 'vault-lockout-overlay';
            overlay.style.cssText = `
                position:fixed;inset:0;z-index:999999;
                background:radial-gradient(ellipse at center, #1a0000 0%, #000 100%);
                display:flex;flex-direction:column;align-items:center;justify-content:center;
                animation:fadeInLockout 0.4s ease;
            `;
            overlay.innerHTML = `
                <style>
                    @keyframes fadeInLockout{from{opacity:0}to{opacity:1}}
                    @keyframes redPulse{0%,100%{text-shadow:0 0 20px #ef4444,0 0 60px #ef4444;}50%{text-shadow:0 0 5px #ef4444;}}
                    @keyframes scanLine{0%{top:0}100%{top:100%}}
                    .lockout-scanline{position:absolute;left:0;width:100%;height:2px;background:rgba(239,68,68,0.4);animation:scanLine 2s linear infinite;pointer-events:none;}
                </style>
                <div class="lockout-scanline"></div>
                <div style="font-size:5rem;animation:redPulse 1.5s infinite;">🔴</div>
                <h1 style="color:#ef4444;font-size:2rem;font-weight:900;letter-spacing:0.15em;margin:1rem 0 0.5rem;text-shadow:0 0 30px #ef4444;">ACCESS DENIED</h1>
                <p style="color:#f87171;font-size:1rem;letter-spacing:0.1em;margin-bottom:0.5rem;">تجاوزت عدد محاولات الدخول المسموح بها</p>
                <p style="color:#6b7280;font-size:0.75rem;font-family:monospace;letter-spacing:0.2em;">VAULT LOCKED — SESSION TERMINATED</p>
                <div style="margin-top:2rem;width:200px;height:4px;background:#1f0000;border-radius:4px;overflow:hidden;">
                    <div id="lockout-bar" style="height:100%;width:100%;background:#ef4444;animation:none;"></div>
                </div>
                <p style="color:#4b5563;font-size:0.7rem;margin-top:0.75rem;font-family:monospace;">SYSTEM RE-ENABLING IN <span id="lockout-count">30</span>s</p>
            `;
            document.body.appendChild(overlay);

            // 30-second countdown then unlock
            let secs = 30;
            const bar = overlay.querySelector('#lockout-bar');
            const counter = overlay.querySelector('#lockout-count');
            const timer = setInterval(() => {
                secs--;
                counter.textContent = secs;
                if(bar) bar.style.width = (secs / 30 * 100) + '%';
                if(secs <= 0) {
                    clearInterval(timer);
                    overlay.remove();
                    vaultFailedAttempts = 0;
                    document.getElementById('vaultMasterKey').value = '';
                }
            }, 1000);
        }

        async function unlockVault() {
            const key = document.getElementById('vaultMasterKey').value;
            if(!key) return titanAlert("أدخل كلمة السر الرئيسية!");
            
            const res = await fetch('/api/vault/load', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ key })
            });
            const data = await res.json();
            
            if(data.error) {
                soundManager.error();
                vaultFailedAttempts++;
                const remaining = 3 - vaultFailedAttempts;
                if(vaultFailedAttempts >= 3) {
                    triggerVaultLockout();
                    vaultFailedAttempts = 0;
                } else {
                    titanAlert(`❌ كلمة السر خاطئة! تحذير: ${remaining} محاولة متبقية قبل تجميد النظام.`);
                }
            } else {
                soundManager.success();
                vaultFailedAttempts = 0;
                currentMasterKey = key;
                vaultData = data.vault || [];
                document.getElementById('vault-login').classList.add('hidden');
                document.getElementById('vault-content').classList.remove('hidden');
                renderVaultItems();
            }
        }

        function lockVault(silent = false) {
            currentMasterKey = "";
            vaultData = [];
            document.getElementById('vaultMasterKey').value = "";
            document.getElementById('vault-login').classList.remove('hidden');
            document.getElementById('vault-content').classList.add('hidden');
            document.getElementById('vaultItemsContainer').innerHTML = "";
            if(!silent) titanAlert("🔒 تم إغلاق القبو بنجاح.");
        }

        async function saveVault() {
            if(!currentMasterKey) return;
            const res = await fetch('/api/vault/save', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ key: currentMasterKey, vault: vaultData })
            });
            const data = await res.json();
            if(data.error) titanAlert("طأ في حفظ القبو: " + data.error);
        }

        function addVaultItem() {
            const title = document.getElementById('vaultItemTitle').value;
            const username = document.getElementById('vaultItemUsername').value;
            const password = document.getElementById('vaultItemPass').value;
            
            if(!title || !password) return titanAlert("يجب إدخال العنوان وكلمة السر على الأقل!");
            
            vaultData.push({ title, username, password, date: new Date().toISOString().split('T')[0] });
            
            document.getElementById('vaultItemTitle').value = "";
            document.getElementById('vaultItemUsername').value = "";
            document.getElementById('vaultItemPass').value = "";
            
            renderVaultItems();
            saveVault();
        }

        function renderVaultItems() {
            const container = document.getElementById('vaultItemsContainer');
            if(vaultData.length === 0) {
                container.innerHTML = '<p class="text-center text-gray-500 py-4">القبو فارغ حالياً.</p>';
                return;
            }
            
            container.innerHTML = vaultData.map((item, index) => `
                <div class="bg-slate-800 p-4 rounded-xl border border-slate-700 flex flex-col md:flex-row justify-between items-start md:items-center gap-4 hover:border-yellow-900/50 transition-colors">
                    <div class="flex-1">
                        <div class="flex items-center gap-2 mb-1">
                            <h4 class="font-bold text-purple-400">${item.title}</h4>
                            <span class="text-xs text-slate-500">${item.date || ''}</span>
                        </div>
                        <p class="text-sm text-gray-400">👤 ${item.username || 'بدون اسم مستخدم'}</p>
                    </div>
                    <div class="flex items-center gap-2 w-full md:w-auto">
                        <input type="password" id="vault-pass-${index}" value="${item.password}" readonly class="bg-slate-900 border border-slate-700 rounded-lg p-2 text-sm text-center w-full md:w-32 focus:outline-none">
                        <button onclick="toggleVaultPass(${index})" class="bg-blue-600/20 text-blue-500 hover:bg-blue-600 hover:text-white p-2 rounded-lg transition-colors" title="إظهار/إخفاء كلمة السر">👁️</button>
                        <button onclick="deleteVaultItem('${index}')" class="bg-red-900/20 text-red-500 hover:bg-red-600 hover:text-white p-2 rounded-lg transition-colors" title="حذف">🗑️</button>
                    </div>
                </div>
            `).join('');
        }

        function toggleVaultPass(index) {
            const input = document.getElementById(`vault-pass-${index}`);
            if(input.type === 'password') {
                input.type = 'text';
            } else {
                input.type = 'password';
            }
        }

        function deleteVaultItem(index) {
            if(confirm("هل أنت متأكد من حذف هذا السجل بشكل نهائي؟")) {
                vaultData.splice(index, 1);
                renderVaultItems();
                saveVault();
            }
        }

        async function backupVault() {
            const res = await fetch('/api/vault/backup', { method: 'POST' });
            if (res.ok) {
                const blob = await res.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = "vault_backup.titan.bak";
                a.click();
            } else {
                titanAlert("فشل تصدير النسخة!");
            }
        }

        async function restoreVault(input) {
            if (!input.files[0]) return;
            const formData = new FormData();
            formData.append('file', input.files[0]);
            const res = await fetch('/api/vault/restore', { method: 'POST', body: formData });
            if (res.ok) {
                titanAlert("تم استعادة النسخة بنجاح! يرجى إدخال كلمة السر لفتح القبو.");
                lockVault();
            } else {
                titanAlert("فشل استعادة النسخة!");
            }
        }

        async function showRecoveryMode() {
            try {
                const res = await fetch('/api/vault/recovery/questions');
                const data = await res.json();
                if(data.error) throw new Error(data.error);
                
                document.getElementById('rec-q1').innerText = data.q1;
                document.getElementById('rec-q2').innerText = data.q2;
                document.getElementById('vault-auth-mode').classList.add('hidden');
                document.getElementById('vault-recover-mode').classList.remove('hidden');
            } catch (e) {
                titanAlert(e.message);
                soundManager.error();
            }
        }

        function hideRecoveryMode() {
            document.getElementById('vault-auth-mode').classList.remove('hidden');
            document.getElementById('vault-recover-mode').classList.add('hidden');
        }

        // --- VAULT FORGOT PASSWORD JS ---
        function showVaultForgot() {
            const modal = document.getElementById('vault-forgot-modal');
            modal.style.display = 'flex';
            modal.classList.remove('hidden');
            document.getElementById('vf-step1').style.display = 'block';
            document.getElementById('vf-step2').style.display = 'none';
            document.getElementById('vf-step3').style.display = 'none';
            document.getElementById('vf-error').style.display = 'none';
        }

        function closeVaultForgot() {
            const modal = document.getElementById('vault-forgot-modal');
            modal.style.display = 'none';
            modal.classList.add('hidden');
        }

        async function doVaultForgotSend() {
            const errEl = document.getElementById('vf-error');
            const btn = document.getElementById('vf-send-btn');
            errEl.style.display = 'none';
            btn.disabled = true;
            btn.innerText = '⏳ جاري الإرسال...';
            
            try {
                const res = await fetch('/api/vault/forgot-password', { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    document.getElementById('vf-step1').style.display = 'none';
                    document.getElementById('vf-step2').style.display = 'block';
                    soundManager.success();
                } else {
                    errEl.innerText = data.error || 'حدث خطأ غير متوقع.';
                    errEl.style.display = 'block';
                    soundManager.error();
                }
            } catch(e) {
                errEl.innerText = 'فشل الاتصال بالخادم.';
                errEl.style.display = 'block';
            }
            btn.disabled = false;
            btn.innerText = 'إرسال الكود 📲';
        }

        async function doVaultForgotVerify() {
            const otp = document.getElementById('vf-otp').value.trim();
            const errEl = document.getElementById('vf-error');
            errEl.style.display = 'none';
            if (!otp || otp.length < 6) { 
                errEl.innerText = 'يرجى إدخال الكود كاملاً.'; 
                errEl.style.display = 'block'; 
                return; 
            }
            
            // Note: We verify via the reset route directly in this implementation
            document.getElementById('vf-step2').style.display = 'none';
            document.getElementById('vf-step3').style.display = 'block';
            soundManager.click();
        }

        async function doVaultForgotReset() {
            const otp = document.getElementById('vf-otp').value.trim();
            const pass1 = document.getElementById('vf-new-pass').value;
            const pass2 = document.getElementById('vf-new-pass2').value;
            const errEl = document.getElementById('vf-error');
            errEl.style.display = 'none';
            
            if (pass1 !== pass2) { 
                errEl.innerText = 'كلمتا السر غير متطابقتين.'; 
                errEl.style.display = 'block'; 
                return; 
            }
            if (pass1.length < 6) {
                errEl.innerText = 'كلمة السر يجب أن تكون 6 أحرف على الأقل.';
                errEl.style.display = 'block';
                return;
            }
            
            try {
                const res = await fetch('/api/vault/reset-password', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ otp, new_password: pass1 })
                });
                const data = await res.json();
                if (data.success) {
                    titanAlert('✅ تم إعادة تعيين كلمة سر القبو بنجاح! يمكنك الآن تسجيل الدخول.');
                    closeVaultForgot();
                    soundManager.success();
                } else {
                    errEl.innerText = data.error || 'حدث خطأ.';
                    errEl.style.display = 'block';
                    soundManager.error();
                }
            } catch(e) {
                errEl.innerText = 'فشل الاتصال بالخادم.';
                errEl.style.display = 'block';
            }
        }

        // --- ADMIN PANEL JS ---
        function showAdminTab() {
            showTab('admin');
            soundManager.swoosh();
            if (typeof loadAdminSupportTickets === 'function') loadAdminSupportTickets();
        }

        async function adminNukeSystem() {
            const confirmBox = document.getElementById('admin-confirm-reset');
            const msgEl = document.getElementById('admin-reset-msg');
            const btn = document.getElementById('admin-nuke-btn');
            
            if (!confirmBox.checked) {
                titanAlert('🚨 يجب تأكيد الموافقة أولاً بالضغط على المربع.');
                return;
            }
            
            const pass = prompt('SECURITY CHALLENGE: أدخل كلمة سر الادمن root لتأكيد المسح الشامل:');
            if (pass !== 'Facebook123@@') {
                titanAlert('❌ كلمة سر خاطئة! تم إلغاء العملية.');
                return;
            }
            
            if (!await titanConfirm('⚠️ تحذير نهائي: هل أنت متأكد من مسح جميع البيانات؟ هذا الإجراء لا يمكن التراجع عنه!')) return;
            
            btn.disabled = true;
            btn.innerText = '☢️ جاري المسح الشامل...';
            msgEl.innerText = 'Erasing core databases...';
            msgEl.className = 'mt-4 p-3 rounded-lg text-center font-mono text-sm border bg-red-900/20 text-red-400 block';
            msgEl.classList.remove('hidden');
            
            try {
                const res = await fetch('/api/admin/reset-system', { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    msgEl.innerText = 'COMPLETED: System reset successful. Logging out...';
                    soundManager.alarm();
                    setTimeout(() => window.location.reload(), 3000);
                } else {
                    btn.disabled = false;
                    btn.innerText = '🔥 تنفيذ المسح الشامل (FACTORY RESET)';
                    msgEl.innerText = 'ERROR: ' + (data.error || 'Unknown failure');
                }
            } catch(e) {
                btn.disabled = false;
                btn.innerText = '🔥 تنفيذ المسح الشامل (FACTORY RESET)';
                msgEl.innerText = 'CONNECTION LOST DURING WIPE';
            }
        }

        function _adminTicketStatusClass(status) {
            if (status === 'open') return 'bg-red-900/30 text-red-300 border border-red-800/50';
            if (status === 'in_progress') return 'bg-amber-900/30 text-amber-300 border border-amber-800/50';
            if (status === 'resolved') return 'bg-emerald-900/30 text-emerald-300 border border-emerald-800/50';
            if (status === 'closed') return 'bg-slate-800 text-slate-300 border border-slate-700';
            return 'bg-slate-800 text-slate-300 border border-slate-700';
        }

        async function loadAdminSupportTickets() {
            const box = document.getElementById('adminSupportTicketsList');
            const filter = document.getElementById('adminTicketStatusFilter');
            if (!box) return;
            const status = (filter?.value || 'all');
            setResultLoading(box, 'Admin Tickets', 'Loading admin tickets...');

            try {
                const q = status && status !== 'all' ? ('?status=' + encodeURIComponent(status)) : '';
                const res = await fetch('/api/admin/support/tickets' + q);
                const data = await res.json();
                if (!data.success) {
                    setResultError(box, data.error || 'Failed to load tickets');
                    return;
                }

                const rows = data.tickets || [];
                if (!rows.length) {
                    setResultList(box, 'Admin Tickets', [], { badge: '0', emptyText: 'لا توجد تذاكر مطابقة.' });
                    return;
                }

                setResultMarkup(
                    box,
                    'Admin Tickets',
                    rows.map(t => {
                    const st = String(t.status || 'open');
                    const statusCls = _adminTicketStatusClass(st);
                    return `
                        <div class="p-3 rounded-xl bg-black/30 border border-slate-700">
                            <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
                                <div class="text-sm font-bold text-cyan-300">#${t.id} ${_osintEscape(t.subject || '')}</div>
                                <div class="text-[10px] px-2 py-0.5 rounded ${statusCls}">${_osintEscape(st)}</div>
                            </div>
                            <div class="text-[11px] text-gray-400 mb-2">User: ${_osintEscape(t.username || 'unknown')} | ${_osintEscape(t.category || '')} | ${_osintEscape(t.priority || '')} | ${_osintEscape(t.created_at || '')}</div>
                            <div class="text-xs text-gray-300 whitespace-pre-wrap mb-3">${_osintEscape(t.details || '')}</div>
                            <div class="grid grid-cols-1 md:grid-cols-5 gap-2">
                                <select id="adminTicketStatus_${t.id}" class="md:col-span-1 bg-slate-800 border border-slate-700 text-gray-300 text-xs rounded-lg p-2 outline-none">
                                    <option value="open" ${st === 'open' ? 'selected' : ''}>Open</option>
                                    <option value="in_progress" ${st === 'in_progress' ? 'selected' : ''}>In Progress</option>
                                    <option value="resolved" ${st === 'resolved' ? 'selected' : ''}>Resolved</option>
                                    <option value="closed" ${st === 'closed' ? 'selected' : ''}>Closed</option>
                                </select>
                                <input id="adminTicketNote_${t.id}" type="text" value="${_osintEscape(t.admin_note || '')}" placeholder="Admin note..." class="md:col-span-3 bg-slate-800 border border-slate-700 text-gray-300 text-xs rounded-lg p-2 outline-none">
                                <button onclick="adminUpdateSupportTicket(${t.id})" class="md:col-span-1 bg-cyan-700 hover:bg-cyan-600 text-white text-xs font-bold rounded-lg p-2">حفظ</button>
                            </div>
                        </div>
                    `;
                }).join(''),
                    { badge: `${rows.length} Tickets` }
                );
            } catch (e) {
                setResultError(box, 'Failed to load tickets');
            }
        }

        async function adminUpdateSupportTicket(ticketId) {
            const stEl = document.getElementById('adminTicketStatus_' + ticketId);
            const noteEl = document.getElementById('adminTicketNote_' + ticketId);
            const status = stEl?.value || 'open';
            const admin_note = (noteEl?.value || '').trim();

            try {
                const res = await fetch('/api/admin/support/tickets/' + ticketId, {
                    method: 'PATCH',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ status, admin_note })
                });
                const data = await res.json();
                if (!data.success) {
                    titanAlert(data.error || 'فشل تحديث التيكت');
                    return;
                }
                titanAlert('✅ تم تحديث التيكت بنجاح');
                loadAdminSupportTickets();
            } catch (e) {
                titanAlert('فشل الاتصال بالخادم أثناء التحديث');
            }
        }

        async function executeRecovery() {
            const a1 = document.getElementById('rec-a1').value;
            const a2 = document.getElementById('rec-a2').value;
            if(!a1 || !a2) return titanAlert("الرجاء إدخال الإجابات!");
            
            try {
                const res = await fetch('/api/vault/recovery/recover', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({a1, a2})
                });
                const data = await res.json();
                if(data.error) throw new Error(data.error);
                
                document.getElementById('vaultMasterKey').value = data.recovered_key;
                soundManager.success();
                titanAlert("✅ تم استرجاع كلمة السر بنجاح! يتم فتح القبو الآن.");
                hideRecoveryMode();
                unlockVault(); // Auto-unlock with the recovered key
            } catch(e) {
                titanAlert(e.message);
                soundManager.error();
            }
        }

        function showSetupRecovery() {
            document.getElementById('setup-recovery-container').classList.toggle('hidden');
        }

        async function saveRecoverySetup() {
            const q1 = document.getElementById('setup-q1').value;
            const a1 = document.getElementById('setup-a1').value;
            const q2 = document.getElementById('setup-q2').value;
            const a2 = document.getElementById('setup-a2').value;
            
            if(!q1 || !a1 || !q2 || !a2) return titanAlert("جميع حقول أسئلة الأمان وإجاباتها مطلوبة!");
            
            try {
                const res = await fetch('/api/vault/recovery/setup', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({key: currentMasterKey, q1, a1, q2, a2})
                });
                const data = await res.json();
                if(data.error) throw new Error(data.error);
                
                titanAlert("✅ تم إعداد أسئلة استعادة كلمة السر بنجاح للمستقبل.");
                document.getElementById('setup-recovery-container').classList.add('hidden');
                soundManager.success();
            } catch (e) {
                titanAlert(e.message);
                soundManager.error();
            }
        }

        async function processMetadata() {
            const file = document.getElementById('metadataFile').files[0];
            if (!file) return;
            const formData = new FormData();
            formData.append('file', file);
            const res = await fetch('/api/metadata/remove', { method: 'POST', body: formData });
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = "clean_" + file.name;
            a.click();
            refreshLogs();
        }

        async function processPdf(action) {
            const file = document.getElementById('pdfFileInput').files[0];
            const password = document.getElementById('pdfPass').value;
            if(!file || !password) return titanAlert("الرجاء اختيار ملف PDF وإدخال كلمة سر المكونة منه!");
            
            const formData = new FormData();
            formData.append('file', file);
            formData.append('password', password);
            formData.append('action', action);
            
            try {
                const res = await fetch('/api/pdf-process', { method: 'POST', body: formData });
                if(res.ok) {
                    soundManager.success();
                    const blob = await res.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = (action === 'lock' ? 'locked_' : 'unlocked_') + file.name;
                    a.click();
                    refreshLogs();
                } else {
                    const data = await res.json();
                    throw new Error(data.error || "خطأ غير معروف (ربما كلمة السر التي أدخلتها خاطئة!)");
                }
            } catch (e) {
                titanAlert(e.message);
                soundManager.error();
            }
        }

        async function scanPorts() {
            const ip = document.getElementById('portIpInput').value.trim() || '127.0.0.1';
            const btn = document.getElementById('btnPortScan');
            const label = document.getElementById('scanLabel');
            const loader = document.getElementById('scanLoader');
            const resultBox = document.getElementById('portResult');
            const container = document.getElementById('openPortsContainer');
            
            btn.disabled = true;
            label.classList.add('hidden');
            loader.classList.remove('hidden');
            resultBox.classList.remove('hidden');
            setResultLoading(container, 'Port Scan', 'جاري التشخيص وفحص المنافذ الحساسة...');
            document.getElementById('portScanTarget').innerText = ip;
            soundManager.terminalType();
            
            try {
                const res = await fetch('/api/port-scan', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ip}) });
                const data = await res.json();
                
                if (data.error) {
                    setResultError(container, data.error);
                    soundManager.error();
                } else if (data.open_ports && data.open_ports.length > 0) {
                    soundManager.alarm();
                    setResultList(
                        container,
                        'Open Ports',
                        data.open_ports.map((p) => `<span class="text-red-300 font-mono">🚨 منفذ ${_resultEscape(p)} مفتوح</span>`),
                        { badge: `${data.open_ports.length} Open`, riskScore: 90 }
                    );
                } else {
                    soundManager.success();
                    setResultInfo(container, 'Port Scan', [
                        { label: 'Status', value: 'جميع المنافذ المفحوصة مغلقة (آمن)', tone: 'safe' },
                        { label: 'Target', value: ip, tone: 'info', dir: 'ltr' }
                    ], { badge: 'Secure', cols: 2, riskScore: 8 });
                }
            } catch (e) {
                setResultError(container, 'فشل الاتصال بالخادم.');
                soundManager.error();
            }
            
            btn.disabled = false;
            label.classList.remove('hidden');
            loader.classList.add('hidden');
            refreshLogs();
        }

        async function processExifOsint() {
            const file = document.getElementById('osintFile').files[0];
            if (!file) return;
            const formData = new FormData();
            formData.append('file', file);
            
            const resBox = document.getElementById('osintResult');
            resBox.classList.remove('hidden');
            setResultLoading(resBox, 'EXIF Intelligence', 'جاري التحليل واستخراج البيانات العميقة...');
            soundManager.terminalType();
            
            try {
                const res = await fetch('/api/osint/image', { method: 'POST', body: formData });
                const data = await res.json();
                
                if(data.error) throw new Error(data.error);

                const entries = Object.keys(data || {}).slice(0, 12).map((key) => ({
                    label: key,
                    value: data[key],
                    tone: 'info'
                }));
                if (!entries.length) {
                    setResultList(resBox, 'EXIF Intelligence', [], { badge: 'No Data', emptyText: 'لا توجد بيانات حساسة.' });
                } else {
                    setResultInfo(resBox, 'EXIF Intelligence', entries, { badge: `${entries.length} Fields`, cols: 2 });
                }
                soundManager.success();
            } catch (e) {
                setResultError(resBox, e.message);
                soundManager.error();
            }
        }


        async function checkPhishing() {
            const email = document.getElementById('phishUrlInput').value;
            if(!email || !email.includes('@')) return titanAlert("الرجاء إدخال بريد إلكتروني صحيح");
            const resBox = document.getElementById('phishResult');
            resBox.classList.remove('hidden');
            setResultLoading(resBox, 'Email Reputation', 'جاري فحص سمعة البريد الإلكتروني عبر IPQualityScore...');
            soundManager.terminalType();
            
            try {
                const res = await fetch('/api/scan/email', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({email})
                });
                const data = await res.json();
                
                if (data.error) {
                    setResultError(resBox, data.error);
                    return;
                }
                
                if (data.success) {
                    const scoreTone = _resultToneByScore(data.fraud_score);
                    setResultInfo(resBox, 'Email Reputation', [
                        { label: 'Email', value: email, tone: 'info', dir: 'ltr' },
                        { label: 'Fraud Score', value: data.fraud_score ?? 0, tone: scoreTone },
                        { label: 'Valid Email', value: data.valid ? 'YES' : 'NO', tone: data.valid ? 'safe' : 'danger' },
                        { label: 'Disposable', value: data.disposable ? 'YES (وهمي)' : 'NO', tone: data.disposable ? 'warn' : 'safe' },
                        { label: 'Spam Trap', value: data.spam_trap_score ?? 'N/A', tone: 'info' }
                    ], { badge: scoreTone === 'danger' ? 'High Risk' : (scoreTone === 'warn' ? 'Medium Risk' : 'Low Risk'), cols: 2, riskScore: Number(data.fraud_score || 0) });
                    if(data.fraud_score > 70 || data.disposable || !data.valid) soundManager.alarm(); else soundManager.success();
                } else {
                    setResultError(resBox, `خطأ من الخدمة: ${data.message}`);
                    soundManager.error();
                }
            } catch (e) {
                setResultError(resBox, 'فشل الاتصال بخادم الفحص.');
                soundManager.error();
            }
        }

        async function checkEmailPassLeak() {
            const email = document.getElementById('leakEmailInput').value;
            const password = document.getElementById('leakPassInput').value;
            if(!email || !password) return titanAlert("الرجاء إدخال البريد الإلكتروني وكلمة السر بشكل صحيح");
            
            const resBox = document.getElementById('leakEmailPassResult');
            resBox.classList.remove('hidden');
            setResultLoading(resBox, 'Credential Leak Check', 'جاري فحص التسريبات عبر IPQualityScore...');
            soundManager.terminalType();
            
            try {
                const res = await fetch('/api/scan/emailpass_leak', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({email, password})
                });
                const data = await res.json();
                
                if (data.error) {
                    setResultError(resBox, data.error);
                    return;
                }
                
                if (data.success) {
                    const isLeaked = data.leaked === true || data.leaked === "true";
                    setResultInfo(resBox, 'Credential Leak Check', [
                        { label: 'Email', value: email, tone: 'info', dir: 'ltr' },
                        { label: 'Status', value: isLeaked ? 'تم تسريب هذه البيانات معاً مسبقاً' : 'لم يثبت تسريب الإيميل مع كلمة السر', tone: isLeaked ? 'danger' : 'safe' }
                    ], { badge: isLeaked ? 'Breached' : 'Clean', cols: 2, riskScore: isLeaked ? 95 : 10 });
                    if(isLeaked) soundManager.alarm(); else soundManager.success();
                } else {
                    setResultError(resBox, `خطأ من الخدمة: ${data.message}`);
                    soundManager.error();
                }
            } catch (e) {
                setResultError(resBox, 'فشل الاتصال بخادم الفحص.');
                soundManager.error();
            }
        }

        async function fetchIpqsLogs() {
            const reqType = document.getElementById('ipqsLogType').value;
            const startDate = document.getElementById('ipqsLogDate').value;
            const resBox = document.getElementById('ipqsLogsResult');
            
            resBox.classList.remove('hidden');
            setResultLoading(resBox, 'IPQS Logs', 'جاري جلب السجلات من الخادم...');
            soundManager.terminalType();
            
            try {
                const res = await fetch('/api/scan/ipqs_logs', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({type: reqType, start_date: startDate})
                });
                const data = await res.json();
                
                if (data.success === false) {
                    setResultError(resBox, data.message || 'فشل جلب السجلات');
                    soundManager.error();
                    return;
                }
                
                const requests = data.requests || [];
                if (requests.length === 0) {
                    setResultList(resBox, 'IPQS Logs', [], { badge: '0', emptyText: 'لا توجد سجلات مطابقة في هذه الفترة.' });
                    soundManager.success();
                    return;
                }
                
                const rows = requests.map((req) => {
                    const ok = !!req.status;
                    const dateStr = new Date(req.request_date).toLocaleString('ar-EG');
                    const targetStr = _resultEscape(req.query || req.email || req.ip || req.phone || 'Unknown Target');
                    const fraud = req.fraud_score !== undefined ? _resultEscape(req.fraud_score) : 'N/A';
                    return `
                        <div class="flex flex-wrap justify-between items-start gap-2">
                            <span class="text-teal-200 font-bold font-mono" dir="ltr">${targetStr}</span>
                            <span class="text-[10px] text-slate-400">${_resultEscape(dateStr)}</span>
                        </div>
                        <div class="text-[11px] text-slate-300 mt-1">Status: <span class="${ok ? 'text-green-400' : 'text-red-400'}">${ok ? 'Success' : 'Failed'}</span> | Fraud: <span class="text-amber-300">${fraud}</span></div>
                    `;
                });
                setResultList(resBox, 'IPQS Logs', rows, { badge: `${requests.length} Records` });
                soundManager.success();
                
            } catch (e) {
                setResultError(resBox, 'فشل الاتصال بخادم السجلات.');
                soundManager.error();
            }
        }

        async function checkPhone() {
            const phone = document.getElementById('phoneInput').value;
            if(!phone) return titanAlert("الرجاء إدخال رقم الهاتف");
            const resBox = document.getElementById('phoneResult');
            resBox.classList.remove('hidden');
            setResultLoading(resBox, 'Phone Intelligence', 'جاري فحص الرقم عبر IPQualityScore...');
            soundManager.terminalType();
            
            try {
                const res = await fetch('/api/scan/phone', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({phone})
                });
                const data = await res.json();
                
                if (data.error) {
                    setResultError(resBox, data.error);
                    return;
                }
                
                if (data.success) {
                    const scoreTone = _resultToneByScore(data.fraud_score);
                    setResultInfo(resBox, 'Phone Intelligence', [
                        { label: 'Phone', value: data.formatted || phone, tone: 'info', dir: 'ltr' },
                        { label: 'Fraud Score', value: data.fraud_score ?? 0, tone: scoreTone },
                        { label: 'Valid', value: data.valid ? 'YES' : 'NO', tone: data.valid ? 'safe' : 'danger' },
                        { label: 'Active', value: data.active ? 'YES' : 'Unknown', tone: data.active ? 'safe' : 'warn' },
                        { label: 'Line Type', value: data.line_type || 'N/A', tone: 'info' },
                        { label: 'Recent Abuse', value: data.recent_abuse ? 'YES' : 'NO', tone: data.recent_abuse ? 'danger' : 'safe' },
                        { label: 'Carrier', value: data.carrier || 'N/A', tone: 'info' }
                    ], { badge: scoreTone === 'danger' ? 'High Risk' : (scoreTone === 'warn' ? 'Medium Risk' : 'Low Risk'), cols: 2, riskScore: Number(data.fraud_score || 0) });
                    if(data.fraud_score > 70 || data.recent_abuse || !data.valid) soundManager.alarm(); else soundManager.success();
                } else {
                    setResultError(resBox, `${data.message} (ملاحظة: إذا تكرر الخطأ فغالبًا الرصيد المجاني في IPQualityScore انتهى لليوم)`);
                    soundManager.error();
                }
            } catch (e) {
                setResultError(resBox, 'فشل الاتصال بخادم الفحص.');
                soundManager.error();
            }
        }

        async function checkUrl() {
            const url = document.getElementById('urlInput').value;
            if(!url || (!url.startsWith('http://') && !url.startsWith('https://'))) return titanAlert("الرجاء إدخال رابط صحيح يبدأ بـ http:// أو https://");
            const resBox = document.getElementById('urlResult');
            resBox.classList.remove('hidden');
            setResultLoading(resBox, 'URL Intelligence', 'جاري فحص الرابط عبر IPQualityScore...');
             soundManager.terminalType();
            
            try {
                const res = await fetch('/api/scan/url', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url})
                });
                const data = await res.json();
                
                if (data.error) {
                    setResultError(resBox, data.error);
                    return;
                }
                
                if (data.success) {
                    const scoreTone = _resultToneByScore(data.risk_score);
                    setResultInfo(resBox, 'URL Intelligence', [
                        { label: 'URL', value: url, tone: 'info', dir: 'ltr' },
                        { label: 'Risk Score', value: data.risk_score || 0, tone: scoreTone },
                        { label: 'Phishing', value: data.phishing ? 'YES (تصيد)' : 'NO', tone: data.phishing ? 'danger' : 'safe' },
                        { label: 'Malware', value: data.malware ? 'YES (خبيث)' : 'NO', tone: data.malware ? 'danger' : 'safe' },
                        { label: 'Suspicious', value: data.suspicious ? 'YES (مشبوه)' : 'NO', tone: data.suspicious ? 'warn' : 'safe' },
                        { label: 'Parking', value: data.parking ? 'YES' : 'NO', tone: 'info' },
                        { label: 'Domain', value: data.domain || 'N/A', tone: 'info', dir: 'ltr' },
                        { label: 'Category / Server', value: `${data.category || 'N/A'} / ${data.server || 'N/A'}`, tone: 'info' }
                    ], { badge: scoreTone === 'danger' ? 'High Risk' : (scoreTone === 'warn' ? 'Medium Risk' : 'Low Risk'), cols: 2, riskScore: Number(data.risk_score || 0) });
                    if(data.risk_score > 70 || data.phishing || data.malware || data.suspicious) soundManager.alarm(); else soundManager.success();
                } else {
                    setResultError(resBox, `خطأ من الخدمة: ${data.message}`);
                     soundManager.error();
                }
            } catch (e) {
                setResultError(resBox, 'فشل الاتصال بخادم الفحص.');
                 soundManager.error();
            }
        }

        function _osintEscape(value) {
            const div = document.createElement('div');
            div.textContent = String(value ?? '');
            return div.innerHTML;
        }

        function _osintRenderKeyValueGrid(obj, keys) {
            return `<div class="grid grid-cols-1 md:grid-cols-2 gap-2">${keys.map((k) => `
                <div class="bg-slate-900/70 border border-slate-700 rounded-lg p-2">
                    <div class="text-[10px] text-gray-500 uppercase tracking-wider">${_osintEscape(k)}</div>
                    <div class="text-xs font-mono text-indigo-200 break-all" dir="ltr">${_osintEscape(obj?.[k] ?? 'N/A')}</div>
                </div>
            `).join('')}</div>`;
        }

        function _osintRenderUnifiedResult(target, targetType, data) {
            if (!data || data.error) {
                return `<div class="text-red-400 text-sm">${_osintEscape(data?.error || 'فشل التحليل')}</div>`;
            }

            const wrappers = {
                ip: ['query', 'country_code', 'ISP', 'proxy', 'vpn', 'fraud_score'],
                email: ['valid', 'disposable', 'fraud_score', 'smtp_score', 'overall_score'],
                phone: ['formatted', 'valid', 'active', 'line_type', 'carrier', 'fraud_score'],
                url: ['domain', 'risk_score', 'phishing', 'malware', 'suspicious', 'server'],
                domain: ['domain', 'risk_score', 'phishing', 'malware', 'suspicious', 'server'],
            };
            const keys = wrappers[targetType] || Object.keys(data).slice(0, 8);

            return `
                <div class="space-y-3">
                    <div class="bg-indigo-950/20 border border-indigo-800/40 rounded-lg p-3">
                        <div class="text-[10px] text-indigo-300 uppercase tracking-widest">Target</div>
                        <div class="text-sm font-mono text-white break-all" dir="ltr">${_osintEscape(target)}</div>
                        <div class="text-[11px] text-gray-400 mt-1">Type: <span class="text-indigo-300 font-bold">${_osintEscape(targetType.toUpperCase())}</span></div>
                    </div>
                    ${_osintRenderKeyValueGrid(data, keys)}
                </div>
            `;
        }

        function _osintRenderUsernameResult(data) {
            if (!data || !data.success) {
                return `<div class="text-red-400 text-sm">${_osintEscape(data?.error || 'فشل الفحص')}</div>`;
            }
            const found = data.found || [];
            const notFound = data.not_found || [];

            return `
                <div class="space-y-3">
                    <div class="grid grid-cols-3 gap-2">
                        <div class="bg-green-900/20 border border-green-800/50 rounded-lg p-2 text-center">
                            <div class="text-[10px] text-gray-400">FOUND</div>
                            <div class="text-lg font-black text-green-400">${_osintEscape(found.length)}</div>
                        </div>
                        <div class="bg-slate-900/60 border border-slate-700 rounded-lg p-2 text-center">
                            <div class="text-[10px] text-gray-400">NOT FOUND</div>
                            <div class="text-lg font-black text-gray-300">${_osintEscape(notFound.length)}</div>
                        </div>
                        <div class="bg-indigo-900/20 border border-indigo-800/50 rounded-lg p-2 text-center">
                            <div class="text-[10px] text-gray-400">USERNAME</div>
                            <div class="text-sm font-bold text-indigo-300 font-mono" dir="ltr">${_osintEscape(data.username)}</div>
                        </div>
                    </div>
                    <div class="bg-black/40 border border-slate-700 rounded-lg p-2">
                        <div class="text-[10px] text-gray-500 uppercase mb-2">Platforms Detected</div>
                        ${found.length ? found.map((r) => `<a href="${_osintEscape(r.url)}" target="_blank" rel="noopener noreferrer" class="block mb-1 p-2 rounded bg-green-900/20 border border-green-800/40 hover:bg-green-900/35 transition-all">
                            <span class="text-green-300 font-bold">${_osintEscape(r.platform)}</span>
                            <span class="text-[11px] text-gray-300 ml-2 font-mono" dir="ltr">${_osintEscape(r.url)}</span>
                        </a>`).join('') : '<div class="text-gray-500 text-xs">لا توجد حسابات مؤكدة حالياً.</div>'}
                    </div>
                </div>
            `;
        }

        function _osintRenderHashResult(data) {
            if (!data || !data.success) {
                return `<div class="text-red-400 text-sm">${_osintEscape(data?.error || 'فشل التحليل')}</div>`;
            }
            return `
                <div class="space-y-2">
                    ${_osintRenderKeyValueGrid(data, ['hash_type', 'length', 'entropy_hint', 'reputation', 'risk_score'])}
                    <div class="bg-slate-900/60 border border-slate-700 rounded-lg p-2">
                        <div class="text-[10px] text-gray-500 uppercase tracking-wider">HASH</div>
                        <div class="text-xs font-mono text-amber-300 break-all" dir="ltr">${_osintEscape(data.hash)}</div>
                    </div>
                </div>
            `;
        }

        function _osintRenderThreatResult(title, payload) {
            return `
                <div class="space-y-2">
                    <div class="bg-rose-900/20 border border-rose-800/40 rounded-lg p-2 text-sm font-bold text-rose-300">${_osintEscape(title)}</div>
                    <div class="bg-slate-900/70 border border-slate-700 rounded-lg p-2 text-xs font-mono whitespace-pre-wrap" dir="ltr">${_osintEscape(JSON.stringify(payload, null, 2))}</div>
                </div>
            `;
        }

        function _osintDetectTargetType(target) {
            const t = (target || '').trim();
            if (!t) return 'unknown';
            const ipRegex = /^(?:[0-9]{1,3}[.]){3}[0-9]{1,3}$/;
            const emailRegex = /^[^@ ]+@[^@ ]+[.][^@ ]+$/;
            const phoneRegex = /^[+]?[0-9 -]{7,20}$/;
            const urlRegex = /^(https?:[/][/])/i;
            const domainRegex = /^(?:[a-zA-Z0-9-]+[.])+[a-zA-Z]{2,}$/;

            if (ipRegex.test(t)) return 'ip';
            if (emailRegex.test(t)) return 'email';
            if (urlRegex.test(t)) return 'url';
            if (domainRegex.test(t)) return 'domain';
            if (phoneRegex.test(t)) return 'phone';
            return 'unknown';
        }

        function _osintRenderRisk(score, label) {
            const box = document.getElementById('osintRiskScore');
            if (!box) return;
            const n = Math.max(0, Math.min(100, Number(score) || 0));
            const color = n >= 70 ? 'text-red-400 border-red-800 bg-red-900/20' : (n >= 35 ? 'text-amber-300 border-amber-800 bg-amber-900/20' : 'text-green-400 border-green-800 bg-green-900/20');
            box.className = `mt-3 p-3 rounded-xl border text-sm font-bold ${color}`;
            box.innerText = `Risk Score: ${n}/100 - ${label}`;
            box.classList.remove('hidden');
        }

        async function runUnifiedOsint() {
            const input = document.getElementById('osintTargetInput');
            const out = document.getElementById('osintUnifiedResult');
            const target = (input?.value || '').trim();
            if (!target) return titanAlert('ادخل هدف أولاً.');
            if (!out) return;

            setResultLoading(out, 'Unified OSINT', 'Running unified OSINT lookup...');
            const targetType = _osintDetectTargetType(target);
            let data = null;
            let risk = 0;
            let label = 'Low';

            try {
                if (targetType === 'ip') {
                    const res = await fetch('/api/ip', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ip: target}) });
                    data = await res.json();
                    risk = data.proxy ? 75 : 20;
                    label = data.proxy ? 'Proxy/VPN Suspected' : 'Clean IP';
                } else if (targetType === 'email') {
                    const res = await fetch('/api/scan/email', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({email: target}) });
                    data = await res.json();
                    risk = Number(data.fraud_score || 0);
                    label = risk >= 70 ? 'High Fraud Probability' : (risk >= 35 ? 'Suspicious' : 'Likely Safe');
                } else if (targetType === 'phone') {
                    const res = await fetch('/api/scan/phone', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({phone: target}) });
                    data = await res.json();
                    risk = Number(data.fraud_score || 0);
                    label = risk >= 70 ? 'High Abuse Probability' : (risk >= 35 ? 'Suspicious' : 'Likely Safe');
                } else if (targetType === 'domain' || targetType === 'url') {
                    const finalUrl = targetType === 'domain' ? `https://${target}` : target;
                    const res = await fetch('/api/scan/url', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url: finalUrl}) });
                    data = await res.json();
                    risk = Number(data.risk_score || 0);
                    label = risk >= 70 ? 'High Threat URL' : (risk >= 35 ? 'Potentially Suspicious' : 'Likely Safe URL');
                } else {
                    setResultError(out, 'نوع الهدف غير مدعوم. استخدم: IP, URL, Domain, Email, Phone');
                    return;
                }

                _osintRenderRisk(risk, label);
                setResultMarkup(out, 'Unified OSINT', _osintRenderUnifiedResult(target, targetType, data), { badge: targetType.toUpperCase() });
                soundManager.success();
            } catch (e) {
                setResultError(out, `Lookup failed: ${e.message || e}`);
                soundManager.error();
            }
        }

        async function huntUsername() {
            const username = (document.getElementById('osintUsernameInput')?.value || '').trim();
            const out = document.getElementById('osintUsernameResult');
            if (!username) return titanAlert('ادخل اسم مستخدم أولاً.');
            if (!out) return;

            setResultLoading(out, 'Username Hunt', 'Hunting username across platforms...');
            try {
                const res = await fetch('/api/osint/username', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username})
                });
                const data = await res.json();
                setResultMarkup(out, 'Username Hunt', _osintRenderUsernameResult(data), { badge: data.success ? 'Completed' : 'Failed' });
                if (data.found_count > 0) {
                    _osintRenderRisk(60, 'Public Username Footprint Detected');
                } else {
                    _osintRenderRisk(15, 'No Immediate Public Presence');
                }
            } catch (e) {
                setResultError(out, `Username scan failed: ${e.message || e}`);
            }
        }

        async function analyzeHashIndicator() {
            const hashValue = (document.getElementById('osintHashInput')?.value || '').trim();
            const out = document.getElementById('osintHashResult');
            if (!hashValue) return titanAlert('الصق قيمة Hash أولاً.');
            if (!out) return;

            setResultLoading(out, 'Hash Indicator', 'Analyzing hash indicator...');
            try {
                const res = await fetch('/api/osint/hash', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({hash: hashValue})
                });
                const data = await res.json();
                setResultMarkup(out, 'Hash Indicator', _osintRenderHashResult(data), { badge: data.success ? 'Analyzed' : 'Failed' });
                _osintRenderRisk(Number(data.risk_score || 0), data.reputation || 'Unknown');
            } catch (e) {
                setResultError(out, `Hash analyze failed: ${e.message || e}`);
            }
        }

        async function osintQuickDnsLeak() {
            const out = document.getElementById('osintThreatResult');
            if (!out) return;
            setResultLoading(out, 'Threat Intel', 'Checking DNS leak...');
            try {
                const res = await fetch('/api/intel/dns-leak');
                const data = await res.json();
                setResultMarkup(out, 'Threat Intel', _osintRenderThreatResult('DNS Leak Result', data), { badge: 'DNS' });
                _osintRenderRisk(data.leaked ? 80 : 10, data.leaked ? 'DNS Leak Detected' : 'No DNS Leak');
            } catch (e) {
                setResultError(out, `DNS check failed: ${e.message || e}`);
            }
        }

        async function osintQuickShodan() {
            const ip = (document.getElementById('osintShodanIp')?.value || '').trim();
            const out = document.getElementById('osintThreatResult');
            if (!ip) return titanAlert('ادخل IP لفحص Shodan.');
            if (!out) return;
            setResultLoading(out, 'Threat Intel', 'Running shodan intel...');
            try {
                const res = await fetch('/api/intel/shodan', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ip}) });
                const data = await res.json();
                setResultMarkup(out, 'Threat Intel', _osintRenderThreatResult('Shodan Intel', data), { badge: 'Shodan' });
                const risk = (data.vulnerabilities && data.vulnerabilities.length) ? 75 : 35;
                _osintRenderRisk(risk, (data.vulnerabilities && data.vulnerabilities.length) ? 'Exposed Services / CVEs' : 'Open Ports Observed');
            } catch (e) {
                setResultError(out, `Shodan check failed: ${e.message || e}`);
            }
        }

        async function osintQuickMalwareUrl() {
            const url = (document.getElementById('osintMalwareUrl')?.value || '').trim();
            const out = document.getElementById('osintThreatResult');
            if (!url) return titanAlert('ادخل URL للفحص.');
            if (!out) return;
            setResultLoading(out, 'Threat Intel', 'Scanning malware URL...');
            try {
                const res = await fetch('/api/scan/malware_url', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({url}) });
                const data = await res.json();
                setResultMarkup(out, 'Threat Intel', _osintRenderThreatResult('Malware URL Scan', data), { badge: 'Malware URL' });
                const rs = Number((data.result && data.result.risk_score) || data.risk_score || 0);
                _osintRenderRisk(rs, rs >= 70 ? 'Malware/Phishing Risk' : 'No High Malware Signal');
            } catch (e) {
                setResultError(out, `Malware URL scan failed: ${e.message || e}`);
            }
        }

        function loadOsintWatchlist() {
            const box = document.getElementById('osintWatchlist');
            if (!box) return;
            const list = JSON.parse(localStorage.getItem('titan_osint_watchlist') || '[]');
            if (!list.length) {
                setResultList(box, 'OSINT Watchlist', [], { badge: '0', emptyText: 'لا يوجد عناصر محفوظة بعد.' });
                return;
            }
            setResultList(
                box,
                'OSINT Watchlist',
                list.map((x, i) => `<div class="flex items-center justify-between gap-2"><span class="font-mono text-[11px] text-indigo-200" dir="ltr">${_resultEscape(x)}</span><button onclick="removeOsintWatchItem(${i})" class="text-red-400 text-[10px]">حذف</button></div>`),
                { badge: `${list.length} Targets` }
            );
        }

        function saveCurrentOsintTarget() {
            const target = (document.getElementById('osintTargetInput')?.value || '').trim();
            if (!target) return titanAlert('لا يوجد هدف لحفظه.');
            const list = JSON.parse(localStorage.getItem('titan_osint_watchlist') || '[]');
            if (!list.includes(target)) list.unshift(target);
            localStorage.setItem('titan_osint_watchlist', JSON.stringify(list.slice(0, 40)));
            loadOsintWatchlist();
            titanAlert('تمت إضافة الهدف إلى الـ Watchlist.');
        }

        function removeOsintWatchItem(idx) {
            const list = JSON.parse(localStorage.getItem('titan_osint_watchlist') || '[]');
            list.splice(idx, 1);
            localStorage.setItem('titan_osint_watchlist', JSON.stringify(list));
            loadOsintWatchlist();
        }

        function exportOsintReport() {
            const watchlist = JSON.parse(localStorage.getItem('titan_osint_watchlist') || '[]');
            const latestUnified = document.getElementById('osintUnifiedResult')?.innerText || '';
            const latestThreat = document.getElementById('osintThreatResult')?.innerText || '';
            const latestUsername = document.getElementById('osintUsernameResult')?.innerText || '';
            const latestHash = document.getElementById('osintHashResult')?.innerText || '';
            const report = {
                generated_at: new Date().toISOString(),
                watchlist,
                latest_unified_lookup: latestUnified,
                latest_threat_intel: latestThreat,
                latest_username_hunt: latestUsername,
                latest_hash_analysis: latestHash
            };
            const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'titan-osint-report.json';
            a.click();
            URL.revokeObjectURL(url);
        }

        let currentIncidentCaseId = null;
        let graphState = { nodes: [], edges: [] };

        async function irCreateCase() {
            const title = (document.getElementById('irCaseTitle')?.value || '').trim();
            const severity = document.getElementById('irCaseSeverity')?.value || 'medium';
            const description = (document.getElementById('irCaseDesc')?.value || '').trim();
            if (!title) return titanAlert('اكتب عنوان القضية أولاً.');
            const res = await fetch('/api/incidents/create', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({title, severity, description}) });
            const data = await res.json();
            if (!data.success) return titanAlert(data.error || 'فشل إنشاء القضية');
            document.getElementById('irCaseTitle').value = '';
            document.getElementById('irCaseDesc').value = '';
            irLoadCases();
        }

        async function irLoadCases() {
            const box = document.getElementById('irCasesList');
            if (!box) return;
            setResultLoading(box, 'Incident Cases', 'Loading cases...');
            const res = await fetch('/api/incidents/list');
            const data = await res.json();
            if (!data.success) { setResultError(box, 'Load failed'); return; }
            const rows = data.cases || [];
            if (!rows.length) { setResultList(box, 'Incident Cases', [], { badge: '0', emptyText: 'لا توجد قضايا حتى الآن.' }); return; }
            setResultMarkup(
                box,
                'Incident Cases',
                rows.map(c => `
                <div class="p-2 rounded-lg border ${currentIncidentCaseId===c.id ? 'border-red-500 bg-red-900/20' : 'border-slate-700 bg-black/30'}">
                    <div class="flex items-center justify-between gap-2">
                        <button onclick="irSelectCase(${c.id})" class="text-left flex-1">
                            <div class="text-sm font-bold text-gray-200">${_osintEscape(c.title)}</div>
                            <div class="text-[10px] text-gray-500">${_osintEscape(c.severity)} | ${_osintEscape(c.status)}</div>
                        </button>
                    </div>
                </div>
            `).join(''),
                { badge: `${rows.length} Cases` }
            );
        }

        async function irSelectCase(caseId) {
            currentIncidentCaseId = caseId;
            const tag = document.getElementById('irSelectedCase');
            if (tag) tag.innerText = `Case ID: ${caseId}`;
            await irLoadCases();
            await irLoadIocs();
        }

        async function irAddIoc() {
            if (!currentIncidentCaseId) return titanAlert('اختر قضية أولاً.');
            const ioc_type = document.getElementById('irIocType')?.value || 'ip';
            const ioc_value = (document.getElementById('irIocValue')?.value || '').trim();
            const risk_score = Number(document.getElementById('irIocRisk')?.value || 50);
            if (!ioc_value) return titanAlert('اكتب قيمة IOC.');
            const res = await fetch(`/api/incidents/${currentIncidentCaseId}/ioc`, {
                method: 'POST', headers: {'Content-Type':'application/json'},
                body: JSON.stringify({ioc_type, ioc_value, risk_score})
            });
            const data = await res.json();
            if (!data.success) return titanAlert(data.error || 'فشل إضافة IOC');
            document.getElementById('irIocValue').value = '';
            irLoadIocs();
        }

        async function irLoadIocs() {
            const box = document.getElementById('irIocTimeline');
            if (!box || !currentIncidentCaseId) return;
            setResultLoading(box, 'IOC Timeline', 'Loading timeline...');
            const res = await fetch(`/api/incidents/${currentIncidentCaseId}/ioc`);
            const data = await res.json();
            if (!data.success) { setResultError(box, 'Failed'); return; }
            const rows = data.iocs || [];
            if (!rows.length) {
                setResultList(box, 'IOC Timeline', [], { badge: '0', emptyText: 'لا توجد IOCs بعد.' });
                return;
            }
            setResultList(
                box,
                'IOC Timeline',
                rows.map(r => `<span class="text-red-300 font-bold">${_osintEscape(r.ioc_type)}</span> <span class="font-mono" dir="ltr">${_osintEscape(r.ioc_value)}</span> <span class="text-[10px] text-gray-500">risk=${_osintEscape(r.risk_score)} | ${_osintEscape(r.created_at)}</span>`),
                { badge: `${rows.length} IOCs` }
            );
        }

        async function irUpdateStatus(status) {
            if (!currentIncidentCaseId) return titanAlert('اختر قضية أولاً.');
            const res = await fetch(`/api/incidents/${currentIncidentCaseId}/status`, {
                method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({status})
            });
            const data = await res.json();
            if (!data.success) return titanAlert(data.error || 'فشل تحديث الحالة');
            irLoadCases();
        }

        async function irExportReport() {
            if (!currentIncidentCaseId) return titanAlert('اختر قضية أولاً.');
            const res = await fetch(`/api/incidents/${currentIncidentCaseId}/report`);
            const data = await res.json();
            if (!data.success) return titanAlert(data.error || 'فشل التصدير');
            const blob = new Blob([JSON.stringify(data.report, null, 2)], {type:'application/json'});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `incident-${currentIncidentCaseId}-report.json`;
            a.click();
            URL.revokeObjectURL(url);
        }

        function graphAddEntity() {
            const type = document.getElementById('graphEntityType')?.value || 'ip';
            const value = (document.getElementById('graphEntityValue')?.value || '').trim();
            if (!value) return titanAlert('أدخل قيمة الكيان.');
            graphState.nodes.push({ id: `n${Date.now()}${Math.floor(Math.random()*999)}`, type, value });
            document.getElementById('graphEntityValue').value = '';
            graphRender();
        }

        async function graphAutoLink() {
            if (!graphState.nodes.length) return titanAlert('أضف عقد أولاً.');
            const res = await fetch('/api/link-analyzer/build', {
                method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({nodes: graphState.nodes})
            });
            const data = await res.json();
            if (!data.success) return titanAlert(data.error || 'فشل التحليل');
            graphState = { nodes: data.nodes || [], edges: data.edges || [] };
            graphRender();
        }

        function graphRender() {
            const canvas = document.getElementById('graphCanvas');
            const links = document.getElementById('graphLinksList');
            if (!canvas || !links) return;

            const width = canvas.clientWidth || 500;
            const height = 260;
            const nodes = graphState.nodes || [];
            const edges = graphState.edges || [];

            const placed = nodes.map((n, i) => {
                const angle = (i / Math.max(nodes.length, 1)) * Math.PI * 2;
                const r = Math.min(width, height) * 0.32;
                const x = width / 2 + Math.cos(angle) * r;
                const y = height / 2 + Math.sin(angle) * r;
                return { ...n, x, y };
            });

            const byId = Object.fromEntries(placed.map(n => [n.id, n]));
            const edgeSvg = `<svg width="${width}" height="${height}" class="absolute inset-0 pointer-events-none">${edges.map(e => {
                const a = byId[e.source];
                const b = byId[e.target];
                if (!a || !b) return '';
                return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="rgba(217,70,239,0.6)" stroke-width="1.5"/>`;
            }).join('')}</svg>`;

            const nodeHtml = placed.map(n => `<div class="absolute px-2 py-1 rounded-lg border border-fuchsia-700/50 bg-fuchsia-900/20 text-[10px]" style="left:${n.x-50}px;top:${n.y-14}px;width:100px;text-align:center;"><div class="text-fuchsia-300 font-bold">${_osintEscape(n.type)}</div><div class="text-gray-200 font-mono truncate" dir="ltr">${_osintEscape(n.value)}</div></div>`).join('');
            canvas.innerHTML = edgeSvg + nodeHtml;

            links.innerHTML = edges.length ? edges.map(e => `<div class="mb-1 p-1 rounded bg-slate-900/40 border border-slate-700 text-[11px]"><span class="text-fuchsia-300">${_osintEscape(e.relation)}</span> | <span class="text-gray-300">${_osintEscape(e.source_value || e.source)} -> ${_osintEscape(e.target_value || e.target)}</span></div>`).join('') : '<div class="text-gray-500 text-xs">لا توجد روابط حتى الآن.</div>';
        }

        async function huntRunQuery() {
            const q = (document.getElementById('huntQueryText')?.value || '').trim();
            const ioc_type = document.getElementById('huntQueryType')?.value || 'all';
            const out = document.getElementById('huntQueryResult');
            if (!out) return;
            setResultLoading(out, 'Threat Hunting', 'Running hunt...');
            const res = await fetch('/api/hunt/query', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({query: q, ioc_type}) });
            const data = await res.json();
            if (!data.success) { setResultError(out, data.error || 'Failed'); return; }
            const rows = data.rows || [];
            const viewRows = rows.map(r => `<span class="text-orange-300">${_osintEscape(r.ioc_type)}</span> <span class="font-mono" dir="ltr">${_osintEscape(r.ioc_value)}</span> <span class="text-[10px] text-gray-500">case#${_osintEscape(r.case_id)} risk=${_osintEscape(r.risk_score)}</span>`);
            setResultList(out, 'Threat Hunting', viewRows, { badge: `${rows.length} Hits`, emptyText: 'No hits.' });
        }

        async function huntEvaluateRule() {
            const threshold = Number(document.getElementById('huntRuleThreshold')?.value || 70);
            const out = document.getElementById('huntRuleResult');
            if (!out) return;
            const res = await fetch('/api/hunt/rule-evaluate', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({threshold}) });
            const data = await res.json();
            if (!data.success) { setResultError(out, data.error || 'Failed'); return; }
            setResultInfo(out, 'Rule Evaluation', [
                { label: 'Average Risk', value: data.avg_risk ?? 'N/A', tone: _resultToneByScore(data.avg_risk) },
                { label: 'Threshold', value: threshold, tone: 'info' },
                { label: 'Alert', value: data.alert_created ? 'Created' : 'No Alert', tone: data.alert_created ? 'danger' : 'safe' }
            ], { badge: data.alert_created ? 'Alert' : 'Normal', cols: 3 });
        }

        async function forensicsTriage() {
            const file = document.getElementById('forensicsFile')?.files?.[0];
            const out = document.getElementById('forensicsResult');
            if (!file || !out) return titanAlert('اختر ملفاً أولاً.');
            setResultLoading(out, 'Forensics Triage', 'Analyzing evidence...');
            const form = new FormData();
            form.append('file', file);
            const res = await fetch('/api/forensics/triage', { method:'POST', body: form });
            const data = await res.json();
            setResultMarkup(out, 'Forensics Triage', `<div class="bg-slate-900/70 border border-slate-700 rounded-lg p-2 text-xs font-mono whitespace-pre-wrap" dir="ltr">${_resultEscape(JSON.stringify(data, null, 2))}</div>`, { badge: 'JSON' });
        }

        async function brandCheckTypos() {
            const domain = (document.getElementById('brandDomainInput')?.value || '').trim();
            const out = document.getElementById('brandTyposResult');
            if (!domain || !out) return titanAlert('اكتب دومين أولاً.');
            setResultLoading(out, 'Brand Protection', 'Checking similar domains...');
            const res = await fetch('/api/brand/typosquatting', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({domain}) });
            const data = await res.json();
            if (!data.success) { setResultError(out, data.error || 'Failed'); return; }
            const variants = data.similar_domains || [];
            setResultList(out, 'Brand Protection', variants.map((d) => `<span class="font-mono" dir="ltr">${_osintEscape(d)}</span>`), { badge: `${variants.length} Variants`, emptyText: 'No variants' });
        }

        async function brandCheckImpersonation() {
            const username = (document.getElementById('brandUserInput')?.value || '').trim();
            const out = document.getElementById('brandUserResult');
            if (!username || !out) return titanAlert('اكتب اسم المستخدم.');
            setResultLoading(out, 'Impersonation Check', 'Scanning impersonation footprint...');
            const res = await fetch('/api/osint/username', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({username}) });
            const data = await res.json();
            if (!data.success) { setResultError(out, data.error || 'Failed'); return; }
            const found = data.found || [];
            const rows = found.map((r) => `<a href="${_osintEscape(r.url)}" target="_blank" rel="noopener noreferrer" class="text-cyan-300">${_osintEscape(r.platform)}</a>`);
            setResultList(out, 'Impersonation Check', rows, { badge: `${found.length} Profiles`, emptyText: 'No public footprint detected.' });
        }

        async function seGenerateScenario() {
            const scenario_type = document.getElementById('seScenarioType')?.value || 'phishing_email';
            const out = document.getElementById('seScenarioResult');
            if (!out) return;
            setResultLoading(out, 'SE Simulation', 'Generating defensive scenario...');
            const res = await fetch('/api/social/simulate', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({scenario_type}) });
            const data = await res.json();
            if (!data.success) { setResultError(out, data.error || 'Failed'); return; }
            const nl = String.fromCharCode(10);
            const scenarioText = [
                data.scenario || '',
                '',
                'Red flags:',
                ...((data.red_flags || []).map((x) => `- ${x}`)),
                '',
                'Recommended response:',
                ...((data.defense_actions || []).map((x) => `- ${x}`))
            ].join(nl);
            setResultMarkup(
                out,
                'SE Simulation',
                `<div class="result-list-item text-gray-100 whitespace-pre-wrap">${_resultEscape(scenarioText)}</div>`,
                { badge: 'Generated' }
            );
        }

        function _seConfidenceScore(level) {
            if (level === 'high') return 3;
            if (level === 'medium') return 2;
            return 1;
        }

        function seLoadIntelBoard() {
            const box = document.getElementById('seIntelBoardResult');
            if (!box) return;
            const items = JSON.parse(localStorage.getItem('titan_se_intel_board') || '[]');
            if (!items.length) {
                box.innerHTML = '<div class="text-gray-500">لا توجد معلومات بعد. أضف أول ملاحظة.</div>';
                return;
            }
            box.innerHTML = items.map((it, idx) => `
                <div class="mb-2 p-2 rounded border border-slate-700 bg-slate-900/40">
                    <div class="flex items-center justify-between gap-2">
                        <div class="text-pink-300 font-bold">${_osintEscape(it.subject || 'unknown')}</div>
                        <button onclick="seDeleteIntelItem(${idx})" class="text-red-400 text-[10px]">حذف</button>
                    </div>
                    <div class="text-[10px] text-gray-400 mt-1">${_osintEscape(it.category)} | ${_osintEscape(it.confidence)} | ${_osintEscape(it.source)} | ${_osintEscape(it.created_at)}</div>
                    <div class="text-gray-200 mt-1 whitespace-pre-wrap">${_osintEscape(it.note || '')}</div>
                </div>
            `).join('');
        }

        function seAddIntelItem() {
            const subject = (document.getElementById('seIntelSubject')?.value || '').trim();
            const source = (document.getElementById('seIntelSource')?.value || '').trim();
            const category = document.getElementById('seIntelCategory')?.value || 'message';
            const confidence = document.getElementById('seIntelConfidence')?.value || 'medium';
            const note = (document.getElementById('seIntelNote')?.value || '').trim();
            if (!subject || !note) return titanAlert('اكتب Subject والملاحظة أولاً.');

            const items = JSON.parse(localStorage.getItem('titan_se_intel_board') || '[]');
            items.unshift({
                subject,
                source: source || 'unknown',
                category,
                confidence,
                note,
                score: _seConfidenceScore(confidence),
                created_at: new Date().toISOString()
            });
            localStorage.setItem('titan_se_intel_board', JSON.stringify(items.slice(0, 200)));

            document.getElementById('seIntelSubject').value = '';
            document.getElementById('seIntelSource').value = '';
            document.getElementById('seIntelNote').value = '';
            seLoadIntelBoard();
        }

        function seDeleteIntelItem(index) {
            const items = JSON.parse(localStorage.getItem('titan_se_intel_board') || '[]');
            items.splice(index, 1);
            localStorage.setItem('titan_se_intel_board', JSON.stringify(items));
            seLoadIntelBoard();
        }

        function seSortIntelBoard() {
            const items = JSON.parse(localStorage.getItem('titan_se_intel_board') || '[]');
            items.sort((a, b) => {
                if ((b.score || 0) !== (a.score || 0)) return (b.score || 0) - (a.score || 0);
                return String(b.created_at || '').localeCompare(String(a.created_at || ''));
            });
            localStorage.setItem('titan_se_intel_board', JSON.stringify(items));
            seLoadIntelBoard();
            titanAlert('تم ترتيب المعلومات حسب الثقة ثم الزمن.');
        }

        function seExportIntelBoard() {
            const items = JSON.parse(localStorage.getItem('titan_se_intel_board') || '[]');
            const payload = {
                exported_at: new Date().toISOString(),
                total_items: items.length,
                items
            };
            const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'social-intel-board.json';
            a.click();
            URL.revokeObjectURL(url);
        }

        function seClearIntelBoard() {
            if (!confirm('هل تريد حذف كل عناصر لوحة المعلومات؟')) return;
            localStorage.removeItem('titan_se_intel_board');
            seLoadIntelBoard();
        }

        async function advHiddenVaultCreate() {
            const payload = {
                label: (document.getElementById('advHvLabel')?.value || '').trim(),
                decoy_text: (document.getElementById('advHvDecoy')?.value || '').trim(),
                hidden_text: (document.getElementById('advHvHidden')?.value || '').trim(),
                decoy_pass: document.getElementById('advHvDecoyPass')?.value || '',
                hidden_pass: document.getElementById('advHvHiddenPass')?.value || ''
            };
            const out = document.getElementById('advHvOut');
            if (out) out.innerText = 'Creating...';
            const res = await fetch('/api/adv/hidden-vault/create', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
            const data = await res.json();
            if (out) out.innerText = JSON.stringify(data, null, 2);
        }

        async function advHiddenVaultList() {
            const out = document.getElementById('advHvOut');
            if (out) out.innerText = 'Loading...';
            const res = await fetch('/api/adv/hidden-vault/list');
            const data = await res.json();
            if (out) out.innerText = JSON.stringify(data, null, 2);
        }

        async function advHiddenVaultOpen() {
            const payload = {
                vault_id: Number(document.getElementById('advHvOpenId')?.value || 0),
                password: document.getElementById('advHvOpenPass')?.value || ''
            };
            const out = document.getElementById('advHvOut');
            if (out) out.innerText = 'Opening...';
            const res = await fetch('/api/adv/hidden-vault/open', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
            const data = await res.json();
            if (out) out.innerText = JSON.stringify(data, null, 2);
        }

        async function advSecretSplit() {
            const secret = (document.getElementById('advSsSecret')?.value || '').trim();
            const out = document.getElementById('advSsOut');
            if (out) out.innerText = 'Splitting...';
            const res = await fetch('/api/adv/secret-sharing/split', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({secret, n:5, k:3}) });
            const data = await res.json();
            if (data.success && document.getElementById('advSsShares')) {
                document.getElementById('advSsShares').value = JSON.stringify(data.shares, null, 2);
            }
            if (out) out.innerText = JSON.stringify(data, null, 2);
        }

        async function advSecretRecover() {
            const sharesRaw = document.getElementById('advSsShares')?.value || '[]';
            let shares = [];
            try { shares = JSON.parse(sharesRaw); } catch (e) {}
            const out = document.getElementById('advSsOut');
            if (out) out.innerText = 'Recovering...';
            const res = await fetch('/api/adv/secret-sharing/recover', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({shares}) });
            const data = await res.json();
            if (out) out.innerText = JSON.stringify(data, null, 2);
        }

        async function advTimeLockCreate() {
            const payload = {
                message: (document.getElementById('advTlMsg')?.value || '').trim(),
                password: document.getElementById('advTlPass')?.value || '',
                unlock_minutes: Number(document.getElementById('advTlMinutes')?.value || 10),
                one_time: !!document.getElementById('advTlOneTime')?.checked
            };
            const out = document.getElementById('advTlOut');
            if (out) out.innerText = 'Creating token...';
            const res = await fetch('/api/adv/timelock/create', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
            const data = await res.json();
            if (data.success && document.getElementById('advTlToken')) {
                document.getElementById('advTlToken').value = data.token || '';
            }
            if (out) out.innerText = JSON.stringify(data, null, 2);
        }

        async function advTimeLockOpen() {
            const payload = {
                token: (document.getElementById('advTlToken')?.value || '').trim(),
                password: document.getElementById('advTlPass')?.value || ''
            };
            const out = document.getElementById('advTlOut');
            if (out) out.innerText = 'Opening...';
            const res = await fetch('/api/adv/timelock/open', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
            const data = await res.json();
            if (out) out.innerText = JSON.stringify(data, null, 2);
        }

        async function advPolicyEvaluate() {
            const out = document.getElementById('advPolicyOut');
            let policy = {};
            try {
                policy = JSON.parse(document.getElementById('advPolicyJson')?.value || '{}');
            } catch (e) {
                if (out) out.innerText = 'Policy JSON غير صالح';
                return;
            }
            const payload = { policy, otp: (document.getElementById('advPolicyOtp')?.value || '').trim() };
            if (out) out.innerText = 'Evaluating...';
            const res = await fetch('/api/adv/policy/evaluate', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
            const data = await res.json();
            if (out) out.innerText = JSON.stringify(data, null, 2);
        }

        async function advWatermarkSign() {
            const file = document.getElementById('advWmFile')?.files?.[0];
            const out = document.getElementById('advWmOut');
            if (!file) { if (out) out.innerText = 'اختر ملفاً'; return; }
            const form = new FormData();
            form.append('file', file);
            form.append('label', (document.getElementById('advWmLabel')?.value || '').trim());
            if (out) out.innerText = 'Signing...';
            const res = await fetch('/api/adv/watermark/sign', { method: 'POST', body: form });
            const data = await res.json();
            if (data.success && document.getElementById('advWmSig')) {
                document.getElementById('advWmSig').value = data.signature || '';
            }
            if (out) out.innerText = JSON.stringify(data, null, 2);
        }

        async function advWatermarkVerify() {
            const file = document.getElementById('advWmFile')?.files?.[0];
            const out = document.getElementById('advWmOut');
            if (!file) { if (out) out.innerText = 'اختر ملفاً'; return; }
            const form = new FormData();
            form.append('file', file);
            form.append('signature', (document.getElementById('advWmSig')?.value || '').trim());
            form.append('label', (document.getElementById('advWmLabel')?.value || '').trim());
            if (out) out.innerText = 'Verifying...';
            const res = await fetch('/api/adv/watermark/verify', { method: 'POST', body: form });
            const data = await res.json();
            if (out) out.innerText = JSON.stringify(data, null, 2);
        }

        async function advKeyCreate() {
            const name = (document.getElementById('advKeyName')?.value || '').trim();
            const out = document.getElementById('advKeyOut');
            const res = await fetch('/api/adv/keyring/create', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({name}) });
            const data = await res.json();
            if (out) out.innerText = JSON.stringify(data, null, 2);
        }

        async function advKeyList() {
            const out = document.getElementById('advKeyOut');
            const res = await fetch('/api/adv/keyring/list');
            const data = await res.json();
            if (out) out.innerText = JSON.stringify(data, null, 2);
        }

        async function advKeyRotate() {
            const key_id = Number(document.getElementById('advKeyId')?.value || 0);
            const out = document.getElementById('advKeyOut');
            const res = await fetch('/api/adv/keyring/rotate', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({key_id}) });
            const data = await res.json();
            if (out) out.innerText = JSON.stringify(data, null, 2);
        }

        async function advKeyRevoke() {
            const key_id = Number(document.getElementById('advKeyId')?.value || 0);
            const out = document.getElementById('advKeyOut');
            const res = await fetch('/api/adv/keyring/revoke', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({key_id}) });
            const data = await res.json();
            if (out) out.innerText = JSON.stringify(data, null, 2);
        }

        async function advKeyEncrypt() {
            const key_id = Number(document.getElementById('advKeyId')?.value || 0);
            const text = document.getElementById('advKeyPlain')?.value || '';
            const out = document.getElementById('advKeyOut');
            const res = await fetch('/api/adv/keyring/encrypt', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({key_id, text}) });
            const data = await res.json();
            if (data.success && document.getElementById('advKeyCipher')) document.getElementById('advKeyCipher').value = data.cipher || '';
            if (out) out.innerText = JSON.stringify(data, null, 2);
        }

        async function advKeyDecrypt() {
            const key_id = Number(document.getElementById('advKeyId')?.value || 0);
            const cipher = document.getElementById('advKeyCipher')?.value || '';
            const out = document.getElementById('advKeyOut');
            const res = await fetch('/api/adv/keyring/decrypt', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({key_id, cipher}) });
            const data = await res.json();
            if (data.success && document.getElementById('advKeyPlain')) document.getElementById('advKeyPlain').value = data.text || '';
            if (out) out.innerText = JSON.stringify(data, null, 2);
        }

        function renderMalwareResult(data, targetName, isUrl = true) {
            const resBox = document.getElementById('malwareResult');
            
            if (data.error) {
                setResultError(resBox, data.error);
                return;
            }
            
            if (data.status === "pending") {
                 setResultLoading(resBox, 'Malware Scan', 'جاري تحليل الهدف أمنياً في الخادم... الرجاء الانتظار بضع ثوانٍ.');
                 return;
            }
             
            if (data.success && data.result) {
                const scan = data.result;
                 // Some risk score keys for malware scan could differ slightly, safely extracting
                let riskScore = scan.risk_score || 0;
                    const scoreTone = _resultToneByScore(riskScore);
                    setResultInfo(resBox, isUrl ? 'Malware URL Scan' : 'Malware File Scan', [
                        { label: isUrl ? 'URL' : 'File', value: targetName, tone: 'info', dir: 'ltr' },
                        { label: 'Risk Score', value: riskScore, tone: scoreTone },
                        { label: 'Malicious', value: scan.malicious ? 'YES (خبيث)' : 'NO', tone: scan.malicious ? 'danger' : 'safe' },
                        { label: 'Phishing', value: scan.phishing ? 'YES (تصيد)' : 'NO', tone: scan.phishing ? 'danger' : 'safe' },
                        { label: 'Suspicious', value: scan.suspicious ? 'YES (مشبوه)' : 'NO', tone: scan.suspicious ? 'warn' : 'safe' },
                        { label: 'Spam', value: scan.spam ? 'YES (مزعج)' : 'NO', tone: scan.spam ? 'danger' : 'safe' }
                    ], { badge: scoreTone === 'danger' ? 'High Risk' : (scoreTone === 'warn' ? 'Medium Risk' : 'Low Risk'), cols: 2, riskScore: Number(riskScore || 0) });
                 if(riskScore > 70 || scan.malicious || scan.phishing || scan.suspicious) soundManager.alarm(); else soundManager.success();
             } else {
                     setResultError(resBox, data.message || 'فشل عملية الفحص العميق.');
                  soundManager.error();
             }
        }

        async function checkMalwareUrl() {
            const url = document.getElementById('malwareUrlInput').value;
            if(!url || (!url.startsWith('http://') && !url.startsWith('https://'))) return titanAlert("الرجاء إدخال رابط صحيح يبدأ بـ http:// أو https://");
            const resBox = document.getElementById('malwareResult');
            resBox.classList.remove('hidden');
            setResultLoading(resBox, 'Malware Scan', 'جاري فحص الرابط للبرمجيات الخبيثة عبر IPQualityScore...');
            soundManager.terminalType();
            
            try {
                const res = await fetch('/api/scan/malware_url', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url})
                });
                const data = await res.json();
                renderMalwareResult(data, url, true);
            } catch (e) {
                 setResultError(resBox, 'فشل الاتصال بخادم الفحص.');
                 soundManager.error();
            }
        }

        async function checkMalwareFile() {
             const fileInput = document.getElementById('malwareFileInput');
             if(!fileInput.files.length) return titanAlert("الرجاء اختيار ملف للفحص");
             
             const file = fileInput.files[0];
             // Limit check (e.g. 15MB) since IPQualityScore free typically limits file size
             if (file.size > 15 * 1024 * 1024) return titanAlert("حجم الملف كبير جداً. الحد الأقصى 15 ميجابايت.");
             
            const resBox = document.getElementById('malwareResult');
            resBox.classList.remove('hidden');
            setResultLoading(resBox, 'Malware Scan', 'جاري رفع وفحص الملف للبرمجيات الخبيثة...');
            soundManager.terminalType();
            
            const formData = new FormData();
            formData.append('file', file);
            
             try {
                const res = await fetch('/api/scan/malware_file', {
                    method: 'POST', body: formData
                });
                const data = await res.json();
                renderMalwareResult(data, file.name, false);
            } catch (e) {
                 setResultError(resBox, 'فشل رفع الملف أو الاتصال بالخادم.');
                 soundManager.error();
            }
        }

        async function scanLanNetwork() {
            const loader = document.getElementById('lanLoader');
            const resBox = document.getElementById('lanResult');
            const btn = document.getElementById('btnLanScan');
            const exportBtn = document.getElementById('btnLanExport');
            
            btn.disabled = true;
            loader.classList.remove('hidden');
            resBox.classList.remove('hidden');
            if(exportBtn) exportBtn.disabled = true;
            setResultLoading(resBox, 'LAN Discovery', 'جاري إرسال حزم استكشافية للشبكة (ARP Sweep)...');
            soundManager.terminalType();
            
            try {
                const res = await fetch('/api/network/scan');
                const data = await res.json();

                if(!res.ok || !data.success) {
                    const errMsg = data && data.error ? data.error : 'تعذر تنفيذ فحص الشبكة حالياً.';
                    setResultError(resBox, errMsg);
                    soundManager.error();
                    return;
                }

                const devices = Array.isArray(data.devices) ? data.devices : [];
                window.__lanLastDevices = devices;
                const routerCount = devices.filter(d => (d.label || '').includes('التوجيه')).length;
                const unknownCount = devices.filter(d => !d.hostname || d.hostname === '').length;
                const selfCount = devices.filter(d => d.is_self).length;
                const selfIp = data.local_ip || (devices.find(d => d.is_self) || {}).ip || 'غير متاح';

                if(exportBtn && devices.length > 0) exportBtn.disabled = false;

                if(devices.length === 0) {
                    setResultList(resBox, 'LAN Discovery', [], { badge: '0 Devices', emptyText: 'لم يتم العثور على أجهزة (أو الشبكة تمنع الفحص).' });
                } else {
                    const rows = devices.map((d) => `${_resultEscape(d.icon || '💻')} <span class="font-mono text-cyan-300" dir="ltr">${_resultEscape(d.ip)}</span> | ${_resultEscape(d.label || d.type || 'Unknown')} | ${_resultEscape(d.hostname || 'Hostname غير متاح')} | MAC: <span class="font-mono" dir="ltr">${_resultEscape(d.mac || 'N/A')}</span> ${d.is_self ? '<span class="text-emerald-300">(THIS DEVICE)</span>' : ''}`);
                    setResultList(resBox, 'LAN Discovery', rows, { badge: `${devices.length} Devices`, riskScore: unknownCount > 0 ? 35 : 10 });
                }
                soundManager.success();
            } catch(e) {
                setResultError(resBox, 'فشل في جلب أجهزة الشبكة.');
                soundManager.error();
            } finally {
                loader.classList.add('hidden');
                btn.disabled = false;
            }
        }

        function exportLanCsv() {
            const devices = Array.isArray(window.__lanLastDevices) ? window.__lanLastDevices : [];
            if(!devices.length) {
                titanAlert('لا توجد نتائج متاحة للتصدير. نفّذ فحص الشبكة أولاً.');
                return;
            }

            const header = ['ip', 'mac', 'hostname', 'label', 'type', 'is_self'];
            const rows = devices.map(d => [
                d.ip || '',
                d.mac || '',
                d.hostname || '',
                d.label || '',
                d.type || '',
                d.is_self ? 'yes' : 'no'
            ]);

            const escapeCsv = (value) => {
                const text = String(value ?? '');
                if(/[",\\n\\r]/.test(text)) {
                    return `"${text.replace(/"/g, '""')}"`;
                }
                return text;
            };

            const csv = [header, ...rows].map(row => row.map(escapeCsv).join(',')).join('\\r\\n');
            const bom = '\uFEFF';
            const blob = new Blob([bom + csv], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement('a');
            const ts = new Date().toISOString().replace(/[:.]/g, '-');
            link.href = URL.createObjectURL(blob);
            link.download = `titan-lan-scan-${ts}.csv`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(link.href);
            soundManager.success();
        }

        async function createBurnNote() {
            const text = document.getElementById('burnNoteText').value;
            if(!text) return titanAlert("يرجى كتابة رسالة الصندوق قبل التوليد!");
            
            try {
                const res = await fetch('/api/burn-note/create', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({text})
                });
                const data = await res.json();
                if(data.error) throw new Error(data.error);
                
                document.getElementById('burnNoteResult').classList.remove('hidden');
                document.getElementById('burnNoteLink').value = data.link;
                document.getElementById('burnNoteText').value = "";
                soundManager.success();
                refreshLogs();
            } catch (e) {
                titanAlert("خطأ: " + e.message);
                soundManager.error();
            }
        }

        function copyBurnNoteLink() {
            const link = document.getElementById('burnNoteLink');
            link.select();
            document.execCommand('copy');
            
            const btn = document.getElementById('burnCopyBtn');
            const orgText = btn.innerText;
            btn.innerText = '✅ تم النسخ';
            btn.classList.add('text-orange-400', 'border-orange-500', 'bg-orange-900/30');
            soundManager.click();
            
            setTimeout(() => {
                btn.innerText = orgText;
                btn.classList.remove('text-orange-400', 'border-orange-500', 'bg-orange-900/30');
            }, 2000);
        }

        async function showStego(mode) {
            if (mode === 'encode') {
                const text = prompt("أدخل النص الذي تريد إخفاءه داخل الصورة:");
                if (!text) return;
                const fileInput = document.createElement('input');
                fileInput.type = 'file';
                fileInput.accept = 'image/*';
                fileInput.onchange = async () => {
                    const formData = new FormData();
                    formData.append('file', fileInput.files[0]);
                    formData.append('text', text);
                    const res = await fetch('/api/steganography/encode', { method: 'POST', body: formData });
                    if(res.ok) {
                        const blob = await res.blob();
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url; a.download = "stego_img.png"; a.click();
                        refreshLogs();
                    } else { 
                        const errData = await res.json();
                        titanAlert("خطأ في تشفير الصورة: " + (errData.error || "خطأ غير معروف")); 
                    }
                };
                fileInput.click();
            } else {
                const fileInput = document.createElement('input');
                fileInput.type = 'file';
                fileInput.accept = 'image/*';
                fileInput.onchange = async () => {
                    const formData = new FormData();
                    formData.append('file', fileInput.files[0]);
                    const res = await fetch('/api/steganography/decode', { method: 'POST', body: formData });
                    const data = await res.json();
                    titanAlert("النص المستخرج: " + (data.result || "لا توجد بيانات"));
                    refreshLogs();
                };
                fileInput.click();
            }
        }

        async function toggleUsbGuardian(action) {
            try {
                const res = await fetch('/api/defense/usb', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({action})
                });
                const data = await res.json();
                
                const badge = document.getElementById('usbStatusBadge');
                if(data.status === 'active') {
                    badge.innerText = 'يراقب 🛡️';
                    badge.className = 'text-[9px] px-2 py-0.5 rounded-full bg-teal-900/50 text-teal-300 border border-teal-500/50 animate-pulse';
                    soundManager.success();
                } else {
                    badge.innerText = 'متوقف';
                    badge.className = 'text-[9px] px-2 py-0.5 rounded-full bg-slate-800 text-gray-400 border border-slate-700';
                    soundManager.click();
                }
                refreshLogs();
            } catch(e) {
                soundManager.error();
            }
        }

        async function toggleFim(action) {
            const target = document.getElementById('fimTargetPath').value;
            if(action === 'start' && !target) return titanAlert("الرجاء إدخال مسار الملف للمراقبة");
            
            try {
                const res = await fetch('/api/defense/fim', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({action, target})
                });
                const data = await res.json();
                if(data.error) throw new Error(data.error);
                
                const badge = document.getElementById('fimStatusBadge');
                if(data.status === 'active') {
                    badge.innerText = 'يراقب ⚖️';
                    badge.className = 'text-[9px] px-2 py-0.5 rounded-full bg-orange-900/50 text-orange-300 border border-orange-500/50 animate-pulse';
                    soundManager.success();
                } else {
                    badge.innerText = 'متوقف';
                    badge.className = 'text-[9px] px-2 py-0.5 rounded-full bg-slate-800 text-gray-400 border border-slate-700';
                    soundManager.click();
                }
                refreshLogs();
            } catch(e) {
                titanAlert("خطأ: " + e.message);
                soundManager.error();
            }
        }

        /* --- Burn Chat Logic (E2E Encrypted) --- */
        let burnChatTimer = null;
        let currentRoomId = null;
        let currentUser = null;

        // Custom E2E Encryption (XOR + Base64 Safe) with Signature
        function e2eEncrypt(str, key) {
            let encodedStr = encodeURIComponent(str + "||TITAN_OK||"); // Append verification signature
            let res = "";
            for(let i=0; i<encodedStr.length; i++) {
                res += String.fromCharCode(encodedStr.charCodeAt(i) ^ key.charCodeAt(i % key.length));
            }
            return btoa(res);
        }
        
        function e2eDecrypt(b64, key) {
            let res = "";
            try {
                let decodedStr = atob(b64);
                for(let i=0; i<decodedStr.length; i++) {
                    res += String.fromCharCode(decodedStr.charCodeAt(i) ^ key.charCodeAt(i % key.length));
                }
                
                // Try decoding URI component
                let plaintext = decodeURIComponent(res);
                if(plaintext.endsWith("||TITAN_OK||")) {
                    return { success: true, text: plaintext.substring(0, plaintext.length - 12) };
                }
                return { success: false, text: res }; // Valid URI encoding, but bad signature
            } catch(e) {
                // Invalid URI encoding (XOR caused bad bytes)
                return { success: false, text: res || "GARBLED_DATA" };
            }
        }

        function joinBurnChat() {
            const roomId = document.getElementById('burnChatId').value.trim();
            const user = document.getElementById('burnChatUser').value.trim() || 'Anonymous';
            
            if(!roomId) return titanAlert("الرجاء إدخال رقم الغرفة للاتصال المشفر!");
            
            currentRoomId = roomId;
            currentUser = user;
            
            document.getElementById('burnChatInput').disabled = false;
            document.getElementById('burnChatSendBtn').disabled = false;
            document.getElementById('burnChatSendBtn').className = "bg-pink-600 hover:bg-pink-500 text-white px-8 rounded-lg font-bold transition-all border border-pink-500/50 shadow-[0_0_15px_rgba(236,72,153,0.3)] flex-shrink-0";
            document.getElementById('burnChatDisplay').innerHTML = '<div class="text-center text-pink-500 font-bold tracking-widest text-xs uppercase mt-auto mb-2 animate-pulse">-- 🔒 تم الاتصال بنفق مشفر (End-to-End) --</div><div class="text-center text-gray-500 tracking-widest text-[10px] uppercase">يتم تشفير/فك تشفير الرسائل محلياً داخل متصفحك فقط</div>';
            
            soundManager.success();
            
            if(burnChatTimer) clearInterval(burnChatTimer);
            burnChatTimer = setInterval(pollBurnChat, 2000);
        }

        async function sendBurnChat() {
            const input = document.getElementById('burnChatInput');
            const msg = input.value.trim();
            if(!msg || !currentRoomId) return;
            
            // PROMPT SENDER FOR DECRYPTION KEY
            const encryptKey = prompt("🔐 أدخل مفتاح التشفير الخاص بهذه الرسالة (يجب أن يعرفه الطرف الآخر لفك التشفير):");
            if (!encryptKey) return; // Cancelled
            
            input.value = '';
            
            // Show local preview
            const display = document.getElementById('burnChatDisplay');
            display.innerHTML += `
                <div class="flex justify-start mt-4">
                    <div class="bg-indigo-900/40 border border-indigo-700/50 text-indigo-200 px-4 py-3 rounded-lg text-sm max-w-[85%] break-y relative">
                        <span class="text-[10px] text-indigo-400 font-bold mb-1 block">أنت (${currentUser}) <span class="text-indigo-600 bg-indigo-950 px-1 rounded ml-2">🔒 مُشفّر</span></span>
                        <div class="text-[8px] font-mono text-indigo-700/50 overflow-hidden text-ellipsis whitespace-nowrap mb-2 italic" title="Ciphertext">Encrypted payload sent...</div>
                        <div class="text-indigo-100 font-bold text-[15px]">${msg}</div>
                    </div>
                </div>
            `;
            display.scrollTop = display.scrollHeight;
            soundManager.terminalType();
            
            // Encrypt and Send
            const encryptedMsg = e2eEncrypt(msg, encryptKey);
            try {
                await fetch('/api/chat/send', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({room_id: currentRoomId, sender: currentUser, msg: encryptedMsg})
                });
            } catch(e) {
                console.error("Encryption Transmission Failed:", e);
            }
        }

        async function pollBurnChat() {
            if(!currentRoomId) return;
            
            try {
                const res = await fetch(`/api/chat/receive?room_id=${currentRoomId}&requester=${currentUser}`);
                const data = await res.json();
                
                if(data.messages && data.messages.length > 0) {
                    const display = document.getElementById('burnChatDisplay');
                    data.messages.forEach(m => {
                        // Generate a unique ID for this message block
                        const msgId = 'msg-' + Math.random().toString(36).substr(2, 9);
                        
                        display.innerHTML += `
                            <div class="flex justify-end mt-4 mb-2">
                                <div id="${msgId}" class="bg-pink-900/40 border border-pink-700/50 text-pink-200 px-5 py-4 rounded-lg text-sm max-w-[85%] break-y relative group shadow-[0_4px_20px_rgba(236,72,153,0.15)] transition-all">
                                    <div class="flex justify-between items-center mb-2 border-b border-pink-800/50 pb-2">
                                        <span class="text-xs text-pink-400 font-black">${m.sender}</span>
                                        <span class="text-[9px] text-gray-500 ml-3 uppercase bg-black/50 border border-slate-700 px-2 py-0.5 rounded">🔒 مشفر (Ciphertext)</span>
                                    </div>
                                    <!-- Ciphertext -->
                                    <div class="mb-3 p-2 bg-black/80 rounded border border-pink-900/50">
                                        <div class="text-[10px] font-mono text-pink-700 break-all select-all">${m.msg}</div>
                                    </div>
                                    
                                    <!-- Action Button & Output Area -->
                                    <div id="${msgId}-action-area" class="flex flex-col gap-2">
                                        <button onclick="decryptManual('${msgId}', '${m.msg}')" class="w-full bg-pink-800/30 hover:bg-pink-700/40 border border-pink-700/50 text-pink-300 text-[10px] font-bold py-2 rounded transition-all">
                                            فك التشفير الآن 🔓
                                        </button>
                                    </div>
                                    <div class="absolute -left-4 -top-4 text-2xl opacity-0 group-hover:opacity-100 transition-opacity drop-shadow-xl" title="Burned from Server Memory">🔥</div>
                                </div>
                            </div>
                        `;
                    });
                    display.scrollTop = display.scrollHeight;
                    soundManager.alarm(); 
                }
            } catch(e) {
                console.error(e);
            }
        }

        function decryptManual(msgId, cipherData) {
            const key = prompt("⚠️ أدخل مفتاح فك التشفير السري الخاص بهذه الرسالة:");
            if(!key) return; // User cancelled the prompt
            
            const actionArea = document.getElementById(msgId + '-action-area');
            const result = e2eDecrypt(cipherData, key);
            
            if(!result.success) {
                // Show Garbled Text Result
                actionArea.innerHTML = `
                    <div class="text-[9px] text-red-400 mb-1">❌ محاولة فك تشفير فاشلة (نص مخربط):</div>
                    <div class="text-red-300 font-mono text-sm leading-relaxed bg-red-900/20 p-3 rounded border border-red-800/50 break-all select-all">${result.text.substring(0, 100)}...</div>
                `;
                
                // Update badge to red
                const badge = document.querySelector(`#${msgId} span`);
                if(badge) {
                    badge.className = "text-[9px] text-red-500 ml-3 uppercase bg-red-900/30 border border-red-800/50 px-2 py-0.5 rounded animate-pulse";
                    badge.innerText = "❌ مفتاح خاطئ";
                }
                
                // Alert slightly, then enforce FULL SYSTEM LOCKDOWN after 3 seconds
                soundManager.error();
                setTimeout(() => {
                    clearInterval(burnChatTimer);
                    burnChatTimer = null;
                    
                    // Completely destroy the page UI
                    document.body.innerHTML = `
                        <div class="h-screen w-screen bg-black flex flex-col items-center justify-center text-center p-8 fixed top-0 left-0 z-50">
                            <div class="text-9xl mb-8 animate-bounce">💀</div>
                            <h1 class="text-red-600 font-black text-6xl mb-4 tracking-widest animate-pulse">SYSTEM LOCKED</h1>
                            <h2 class="text-red-500 font-bold text-2xl mb-8">SECURE COMM COMPROMISED</h2>
                            <p class="text-red-400 text-lg max-w-2xl mx-auto mb-10 leading-relaxed border border-red-900/50 bg-red-950/30 p-6 rounded-xl">
                                تم إدخال مفتاح تشفير عالي السرية بشكل خاطئ. للحماية القصوى من محاولات التخمين والاختراق، تم تفعيل بروتوكول التدمير الذاتي وتجميد واجهة النظام بالكامل.
                            </p>
                            <div class="text-gray-600 font-mono text-xs opacity-50 mb-10">
                                ERASING SESSION CACHE... [DONE]<br>
                                WIPING LOCAL TOKENS... [DONE]<br>
                                CONNECTION TERMINATED PERMANENTLY
                            </div>
                            <div class="text-red-500 font-black text-xl animate-pulse border-t border-b border-red-900/50 py-4 w-full max-w-md">
                                يُرجى إغلاق المتصفح أو علامة التبويب فوراً.
                            </div>
                        </div>
                    `;
                    soundManager.alarm();
                }, 2500);
                return;
            }
            
            // Success: Replace the button area with the decrypted result
            actionArea.innerHTML = `
                <div class="text-[9px] text-green-400 mb-1">تم فك التشفير محلياً بنجاح باستخدام المفتاح المقدم:</div>
                <div class="text-white font-bold text-lg leading-relaxed bg-green-900/20 p-3 rounded border border-green-800/30">${result.text}</div>
            `;
            
            // Update the badge
            const badge = document.querySelector(`#${msgId} span.text-gray-500`) || document.querySelector(`#${msgId} span`);
            if(badge) {
                badge.className = "text-[9px] text-green-400 ml-3 uppercase bg-green-900/30 border border-green-800/50 px-2 py-0.5 rounded animate-pulse";
                badge.innerText = "🔓 فُك تشفيره";
            }
            
            // Highlight the box temporarily
            const box = document.getElementById(msgId);
            box.classList.add('ring-2', 'ring-green-500/50');
            setTimeout(() => box.classList.remove('ring-2', 'ring-green-500/50'), 1000);
            
            soundManager.success();
        }
        
        /* -------------------------- */

        async function refreshLogs() {
            const res = await fetch('/api/audit-logs');
            const data = await res.json();
            const container = document.getElementById('auditContainer');
            if(!container) return;
            container.innerHTML = data.map(log => `
                <div class="flex justify-between border-b border-white/5 py-1">
                    <span class="text-purple-500">[${log.time}]</span>
                    <span class="text-gray-300 mx-2">${log.action}</span>
                    <span class="text-gray-500 text-[9px] truncate ml-auto">${log.details}</span>
                </div>
            `).join('');
        }
        
        // Initial setup
        enhanceResultPanels();
        showTab('pass');
        refreshLogs();

        // ===========================
        // ===== AUTH SYSTEM JS  =====
        // ===========================
        
        // --- Forgot Password Functions ---
        async function doForgotSend() {
            const username = document.getElementById('forgot-username').value.trim();
            const errEl = document.getElementById('forgot-step1-error');
            const btn = document.getElementById('forgot-send-btn');
            errEl.style.display = 'none';
            if (!username) { errEl.textContent = 'يرجى إدخال اسم المستخدم.'; errEl.style.display = 'block'; return; }
            btn.disabled = true;
            btn.textContent = '⏳ جاري الإرسال...';
            try {
                const res = await fetch('/api/auth/forgot-password/send', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username})
                });
                const data = await res.json();
                if (data.success) {
                    document.getElementById('forgot-step1').style.display = 'none';
                    document.getElementById('forgot-step2').style.display = 'block';
                } else {
                    errEl.textContent = data.error || 'حدث خطأ، تأكد من اسم المستخدم.';
                    errEl.style.display = 'block';
                }
            } catch(e) {
                errEl.textContent = 'فشل الاتصال بالخادم.';
                errEl.style.display = 'block';
            }
            btn.disabled = false;
            btn.textContent = '📧 إرسال كود التحقق';
        }

        async function doForgotVerify() {
            const username = document.getElementById('forgot-username').value.trim();
            const otp = document.getElementById('forgot-otp').value.trim();
            const errEl = document.getElementById('forgot-step2-error');
            errEl.style.display = 'none';
            if (!otp) { errEl.textContent = 'أدخل كود التحقق.'; errEl.style.display = 'block'; return; }
            try {
                const res = await fetch('/api/auth/forgot-password/verify', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username, otp})
                });
                const data = await res.json();
                if (data.success) {
                    document.getElementById('forgot-step2').style.display = 'none';
                    document.getElementById('forgot-step3').style.display = 'block';
                } else {
                    errEl.textContent = data.error || 'الكود غير صحيح أو منتهي الصلاحية.';
                    errEl.style.display = 'block';
                }
            } catch(e) {
                errEl.textContent = 'فشل الاتصال بالخادم.';
                errEl.style.display = 'block';
            }
        }

        async function doForgotReset() {
            const username = document.getElementById('forgot-username').value.trim();
            const otp = document.getElementById('forgot-otp').value.trim();
            const newpass = document.getElementById('forgot-newpass').value;
            const newpass2 = document.getElementById('forgot-newpass2').value;
            const errEl = document.getElementById('forgot-step3-error');
            errEl.style.display = 'none';
            if (!newpass || newpass.length < 6) { errEl.textContent = 'كلمة السر يجب أن تكون 6 أحرف على الأقل.'; errEl.style.display = 'block'; return; }
            if (newpass !== newpass2) { errEl.textContent = 'كلمتا السر غير متطابقتين.'; errEl.style.display = 'block'; return; }
            try {
                const res = await fetch('/api/auth/forgot-password/reset', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username, otp, new_password: newpass})
                });
                const data = await res.json();
                if (data.success) {
                    titanAlert('✅ تم تغيير كلمة السر بنجاح! يمكنك الآن تسجيل الدخول.');
                    switchAuthTab('login');
                    // Reset all forgot steps
                    document.getElementById('forgot-step1').style.display = 'block';
                    document.getElementById('forgot-step2').style.display = 'none';
                    document.getElementById('forgot-step3').style.display = 'none';
                    document.getElementById('forgot-username').value = '';
                    document.getElementById('forgot-otp').value = '';
                    document.getElementById('forgot-newpass').value = '';
                    document.getElementById('forgot-newpass2').value = '';
                } else {
                    errEl.textContent = data.error || 'فشل تغيير كلمة السر.';
                    errEl.style.display = 'block';
                }
            } catch(e) {
                errEl.textContent = 'فشل الاتصال بالخادم.';
                errEl.style.display = 'block';
            }
        }

        function initAuthMatrix() {

            const canvas = document.getElementById('auth-matrix');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            const chars = "01アイウエオカキクケコサシスセソTITAN".split("");
            const fontSize = 11;
            const cols = Math.floor(canvas.width / fontSize);
            const drops = Array.from({length: cols}, () => Math.random() * -100);
            function drawAuthMatrix() {
                ctx.fillStyle = "rgba(5,5,16,0.18)";
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                for (let i = 0; i < drops.length; i++) {
                    const ch = chars[Math.floor(Math.random() * chars.length)];
                    const alpha = Math.random() > 0.85 ? 0.9 : 0.35;
                    ctx.fillStyle = Math.random() > 0.7 ? `rgba(168,85,247,${alpha})` : `rgba(88,28,135,${alpha})`;
                    ctx.font = fontSize + "px monospace";
                    ctx.fillText(ch, i * fontSize, drops[i] * fontSize);
                    if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) drops[i] = 0;
                    drops[i] += 0.4;
                }
                requestAnimationFrame(drawAuthMatrix);
            }
            drawAuthMatrix();
            window.addEventListener('resize', () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; });
        }

        // Enter key support for auth forms
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const overlay = document.getElementById('auth-overlay');
                if (!overlay || overlay.style.display === 'none') return;
                const loginForm = document.getElementById('auth-login-form');
                if (loginForm && loginForm.style.display !== 'none') doLogin();
                else doRegister();
            }
        });

        // Run auth check on page load
        window.addEventListener('load', () => {
            setTimeout(checkAuth, 150);
        });



        // ===== Phase 6 JS =====
        function updateDashMetricCard(cardId, valueElId, rawValue, warnThreshold, dangerThreshold) {
            const card = document.getElementById(cardId);
            const valueEl = document.getElementById(valueElId);
            if (!card || !valueEl) return;

            const val = Number(rawValue || 0);
            const level = val >= dangerThreshold ? 'danger' : (val >= warnThreshold ? 'warn' : 'ok');

            card.classList.remove('border-red-700/70', 'border-yellow-700/70', 'border-green-700/70', 'bg-red-950/25', 'bg-yellow-950/20', 'bg-green-950/20');
            valueEl.classList.remove('text-red-400', 'text-yellow-400', 'text-green-400');

            if (level === 'danger') {
                card.classList.add('border-red-700/70', 'bg-red-950/25');
                valueEl.classList.add('text-red-400');
            } else if (level === 'warn') {
                card.classList.add('border-yellow-700/70', 'bg-yellow-950/20');
                valueEl.classList.add('text-yellow-400');
            } else {
                card.classList.add('border-green-700/70', 'bg-green-950/20');
                valueEl.classList.add('text-green-400');
            }
        }

        function pulseDashIndicator(ok = true) {
            const pulse = document.getElementById('dashPulse');
            if (!pulse) return;
            pulse.classList.remove('bg-gray-600', 'bg-red-500', 'bg-emerald-400', 'animate-pulse', 'opacity-60');
            if (ok) {
                pulse.classList.add('bg-emerald-400', 'animate-pulse');
                setTimeout(() => {
                    pulse.classList.remove('animate-pulse');
                    pulse.classList.add('opacity-60');
                }, 450);
            } else {
                pulse.classList.add('bg-red-500', 'opacity-60');
            }
        }

        async function loadDashboard() {
            if (window.__dashInFlight) return;
            window.__dashInFlight = true;
            try {
                const res = await fetch(`/api/dashboard/stats?_=${Date.now()}`, {
                    cache: 'no-store',
                    headers: {
                        'Cache-Control': 'no-cache'
                    }
                });
                if (!res.ok) throw new Error('dashboard request failed');
                const d = await res.json();
                if(d.error) throw new Error(d.error);
                const cpu = Number(d.cpu_percent || 0);
                const ram = Number(d.ram_percent || 0);
                const diskIo = Number(d.disk_io_kbps || 0);

                document.getElementById('dashCpu').innerText  = cpu.toFixed(1) + '%';
                document.getElementById('dashRam').innerText  = ram.toFixed(1) + '%';
                document.getElementById('dashDisk').innerText = diskIo.toFixed(2);

                updateDashMetricCard('dashCpuCard', 'dashCpu', cpu, 60, 85);
                updateDashMetricCard('dashRamCard', 'dashRam', ram, 65, 88);
                updateDashMetricCard('dashDiskCard', 'dashDisk', diskIo, 512, 2048);
                document.getElementById('dashBurn').innerText = d.burn_notes;
                document.getElementById('dashLocalIp').innerText = d.local_ip;
                document.getElementById('dashPubIp').innerText  = d.public_ip;
                document.getElementById('dashSent').innerText   = Number(d.net_up_kbps || 0).toFixed(2);
                document.getElementById('dashRecv').innerText   = Number(d.net_down_kbps || 0).toFixed(2);
                const sentTotalEl = document.getElementById('dashSentTotal');
                const recvTotalEl = document.getElementById('dashRecvTotal');
                if (sentTotalEl) sentTotalEl.innerText = Number(d.net_sent_mb || 0).toFixed(2);
                if (recvTotalEl) recvTotalEl.innerText = Number(d.net_recv_mb || 0).toFixed(2);
                const updatedAtEl = document.getElementById('dashUpdatedAt');
                if (updatedAtEl) updatedAtEl.innerText = d.measured_at || new Date().toLocaleTimeString();
                pulseDashIndicator(true);
                const logsEl = document.getElementById('dashLogs');
                if(d.recent_logs && d.recent_logs.length) {
                    logsEl.innerHTML = d.recent_logs.map(l =>
                        `<div class="text-purple-400">[${l.time.split(' ')[1]}] <span class="text-gray-300">${l.action}</span></div>`
                    ).join('');
                } else { logsEl.innerHTML = '<div class="text-gray-600">لا يوجد نشاط</div>'; }
            } catch(e) {
                const updatedAtEl = document.getElementById('dashUpdatedAt');
                if (updatedAtEl) updatedAtEl.innerText = 'فشل الاتصال';
                pulseDashIndicator(false);
                console.error('Dashboard update failed:', e);
            } finally {
                window.__dashInFlight = false;
            }
        }


        // ===== TITAN Notification System =====
        function titanAlert(msg, type='info') {
            const existing = document.getElementById('titan-toast');
            if(existing) existing.remove();
            const colors = {info:'#3b82f6', success:'#22c55e', error:'#ef4444', warning:'#f59e0b'};
            const color = colors[type] || colors.info;
            const toast = document.createElement('div');
            toast.id = 'titan-toast';
            toast.style.cssText = `
                position:fixed; top:24px; left:50%; transform:translateX(-50%);
                background:#0f172a; border:1px solid ${color}; border-radius:14px;
                padding:16px 28px; z-index:99999; min-width:320px; max-width:500px;
                box-shadow:0 0 30px ${color}44; text-align:center; font-family:monospace;
                animation: fadeInDown 0.3s ease;
            `;
            toast.innerHTML = `
                <div style="color:${color};font-size:11px;font-weight:900;letter-spacing:3px;margin-bottom:8px;">
                    &#9632; TITAN SEC &#9632;
                </div>
                <div style="color:#e2e8f0;font-size:14px;line-height:1.6;">${msg}</div>
                <button onclick="document.getElementById('titan-toast').remove()"
                    style="margin-top:12px;padding:4px 20px;background:${color}22;border:1px solid ${color}55;
                    color:${color};border-radius:8px;cursor:pointer;font-size:12px;font-family:monospace;">
                    OK
                </button>`;
            document.body.appendChild(toast);
            setTimeout(() => toast?.remove(), 4000);
        }

        function titanConfirm(msg) {
            return new Promise(resolve => {
                const existing = document.getElementById('titan-confirm');
                if(existing) existing.remove();
                const overlay = document.createElement('div');
                overlay.id = 'titan-confirm';
                overlay.style.cssText = `
                    position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:99999;
                    display:flex;align-items:center;justify-content:center;`;
                overlay.innerHTML = `
                    <div style="background:#0f172a;border:1px solid #ef444488;border-radius:16px;
                        padding:28px 36px;min-width:320px;max-width:460px;text-align:center;font-family:monospace;
                        box-shadow:0 0 40px #ef444422;">
                        <div style="color:#ef4444;font-size:11px;font-weight:900;letter-spacing:3px;margin-bottom:12px;">
                            &#9632; TITAN SEC &#9632;
                        </div>
                        <div style="color:#e2e8f0;font-size:14px;line-height:1.6;margin-bottom:20px;">${msg}</div>
                        <div style="display:flex;gap:12px;justify-content:center;">
                            <button id="tc-yes" style="padding:8px 24px;background:#ef4444;border:none;color:white;
                                border-radius:8px;cursor:pointer;font-weight:bold;font-family:monospace;">تأكيد</button>
                            <button id="tc-no" style="padding:8px 24px;background:#1e293b;border:1px solid #334155;
                                color:#94a3b8;border-radius:8px;cursor:pointer;font-family:monospace;">إلغاء</button>
                        </div>
                    </div>`;
                document.body.appendChild(overlay);
                overlay.querySelector('#tc-yes').onclick = () => { overlay.remove(); resolve(true); };
                overlay.querySelector('#tc-no').onclick = () => { overlay.remove(); resolve(false); };
            });
        }

        const style = document.createElement('style');
        style.textContent = '@keyframes fadeInDown{from{opacity:0;transform:translateX(-50%) translateY(-20px)}to{opacity:1;transform:translateX(-50%) translateY(0)}}';
        document.head.appendChild(style);
        // ===== END TITAN Notifications =====
        // =====================================================================
        // === AI Functions ===
        // =====================================================================

        let aiPendingFiles = [];

        function _aiFmtBytes(n) {
            if (n < 1024) return n + ' B';
            if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
            return (n / (1024 * 1024)).toFixed(1) + ' MB';
        }

        function renderAiPendingFiles() {
            const list = document.getElementById('ai-attach-list');
            if (!list) return;
            if (!aiPendingFiles.length) {
                list.classList.add('hidden');
                list.innerHTML = '';
                return;
            }
            list.classList.remove('hidden');
            list.innerHTML = aiPendingFiles.map((f, i) => `
                <span class="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg bg-slate-800 border border-slate-700 text-gray-300">
                    <span>📎 ${_osintEscape(f.name)} (${_aiFmtBytes(f.size)})</span>
                    <button type="button" onclick="removeAiPendingFile(${i})" class="text-red-300 hover:text-red-200">✕</button>
                </span>
            `).join('');
        }

        function removeAiPendingFile(index) {
            aiPendingFiles.splice(index, 1);
            renderAiPendingFiles();
        }

        function onAiFilesSelected(ev) {
            const input = ev.target;
            const selected = Array.from(input.files || []);
            const maxFiles = 5;
            const maxPerFile = 8 * 1024 * 1024;
            for (const f of selected) {
                if (aiPendingFiles.length >= maxFiles) {
                    titanAlert('الحد الأقصى للمرفقات هو 5 ملفات', 'warning');
                    break;
                }
                if (f.size > maxPerFile) {
                    titanAlert(`الملف كبير جداً: ${f.name} (الحد 8MB لكل ملف)`, 'warning');
                    continue;
                }
                const exists = aiPendingFiles.some(x => x.name === f.name && x.size === f.size && x.lastModified === f.lastModified);
                if (!exists) aiPendingFiles.push(f);
            }
            input.value = '';
            renderAiPendingFiles();
        }

        document.addEventListener('DOMContentLoaded', function() {
            var aiLauncher = document.getElementById('ai-float-launcher');
            var aiPanel = document.getElementById('ai-section');

            if (aiPanel) {
                if (aiPanel.parentElement !== document.body) {
                    document.body.appendChild(aiPanel);
                }
                aiPanel.style.position = 'fixed';
                aiPanel.style.left = 'auto';
                aiPanel.style.right = '16px';
                aiPanel.style.bottom = '84px';
                aiPanel.style.zIndex = '2147483646';
                aiPanel.style.width = 'min(92vw,34rem)';
                aiPanel.style.maxHeight = '78vh';
                aiPanel.style.display = 'none';
                aiPanel.style.pointerEvents = 'none';
            }

            if (aiLauncher) {
                if (aiLauncher.parentElement !== document.body) {
                    document.body.appendChild(aiLauncher);
                }
                aiLauncher.style.position = 'fixed';
                aiLauncher.style.left = 'auto';
                aiLauncher.style.right = '16px';
                aiLauncher.style.bottom = '12px';
                aiLauncher.style.zIndex = '2147483647';
            }
            closeAiBubble();
            setAiBubbleVisibility(false);

            var aiInput = document.getElementById('ai-chat-input');
            if (aiInput) {
                aiInput.addEventListener('keydown', function(e) {
                    if (e.key === 'Enter') sendAiMessage();
                });
            }
            var aiFileInput = document.getElementById('ai-file-input');
            if (aiFileInput) {
                aiFileInput.addEventListener('change', onAiFilesSelected);
            }
        });

        async function sendAiMessage() {
            var input = document.getElementById('ai-chat-input');
            var messages = document.getElementById('ai-chat-messages');
            var flow = document.getElementById('ai-chat-flow') || messages;
            var btn = document.getElementById('ai-send-btn');
            var modelEl = document.getElementById('ai-model-select');
            var model = modelEl ? modelEl.value : 'titan_ultimate';
            var msg = input.value.trim();
            const hasFiles = aiPendingFiles.length > 0;
            if (!msg && !hasFiles) return;

            var userDiv = document.createElement('div');
            userDiv.className = 'flex justify-end items-end gap-2';
            const attachPreview = hasFiles
                ? `<div class="mt-2 flex flex-wrap gap-1">${aiPendingFiles.map(f => `<span class="text-[10px] px-2 py-0.5 rounded bg-purple-900/30 border border-purple-700/40">📎 ${_osintEscape(f.name)}</span>`).join('')}</div>`
                : '';
            userDiv.innerHTML = '<div class="bg-purple-700/70 text-white px-4 py-3 rounded-2xl rounded-br-md max-w-[80%] text-sm shadow-lg border border-purple-600/40">' +
                (msg ? _osintEscape(msg).replace(/\\n/g, '<br>') : '<span class="text-purple-100/80">(مرفقات بدون نص)</span>') +
                attachPreview +
                '</div><div class="w-7 h-7 rounded-full bg-purple-800/40 border border-purple-700/50 flex items-center justify-center text-xs">👤</div>';
            flow.appendChild(userDiv);
            input.value = '';
            btn.disabled = true;
            btn.textContent = '...';
            messages.scrollTop = messages.scrollHeight;

            var replyDiv = document.createElement('div');
            replyDiv.className = 'flex justify-start items-end gap-2';
            var botAvatar = document.createElement('div');
            botAvatar.className = 'w-7 h-7 rounded-full bg-purple-900/50 border border-purple-700/40 flex items-center justify-center text-xs';
            botAvatar.textContent = '🤖';
            var replyInner = document.createElement('div');
            replyInner.className = 'bg-slate-800 text-gray-300 px-4 py-3 rounded-2xl rounded-bl-md max-w-[80%] text-sm shadow-lg border border-slate-700/60';
            replyInner.textContent = '...';
            replyDiv.appendChild(botAvatar);
            replyDiv.appendChild(replyInner);
            flow.appendChild(replyDiv);
            messages.scrollTop = messages.scrollHeight;

            try {
                let res;
                if (hasFiles) {
                    const fd = new FormData();
                    fd.append('message', msg);
                    fd.append('model', model);
                    aiPendingFiles.forEach(f => fd.append('files', f, f.name));
                    res = await fetch('/api/ai/chat', {
                        method: 'POST',
                        body: fd
                    });
                } else {
                    res = await fetch('/api/ai/chat', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({message: msg, model: model})
                    });
                }
                var data = await res.json();
                if (data.reply) {
                    replyInner.textContent = data.reply;
                } else {
                    replyInner.textContent = data.error || 'حدث خطأ';
                }
            } catch(e) {
                replyInner.textContent = 'فشل الاتصال';
            }
            aiPendingFiles = [];
            renderAiPendingFiles();
            btn.disabled = false;
            btn.textContent = 'إرسال';
            messages.scrollTop = messages.scrollHeight;
        }

        async function createSupportTicket() {
            const subject = (document.getElementById('supportTicketSubject')?.value || '').trim();
            const details = (document.getElementById('supportTicketDetails')?.value || '').trim();
            const category = document.getElementById('supportTicketCategory')?.value || 'technical';
            const priority = document.getElementById('supportTicketPriority')?.value || 'normal';
            if (!subject || !details) {
                return titanAlert('يرجى إدخال عنوان المشكلة والتفاصيل');
            }
            const res = await fetch('/api/support/tickets', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({subject, details, category, priority})
            });
            const data = await res.json();
            if (!data.success) {
                return titanAlert(data.error || 'فشل إنشاء التيكت');
            }
            document.getElementById('supportTicketSubject').value = '';
            document.getElementById('supportTicketDetails').value = '';
            titanAlert('✅ تم إنشاء تيكت الدعم بنجاح');
            loadSupportTickets();
        }

        function _supportStatusBadgeClass(status) {
            if (status === 'open') return 'bg-red-900/30 text-red-300 border border-red-800/50';
            if (status === 'in_progress') return 'bg-amber-900/30 text-amber-300 border border-amber-800/50';
            if (status === 'resolved') return 'bg-emerald-900/30 text-emerald-300 border border-emerald-800/50';
            if (status === 'closed') return 'bg-slate-800 text-slate-300 border border-slate-700';
            return 'bg-slate-800 text-slate-300 border border-slate-700';
        }

        function _supportPriorityBadgeClass(priority) {
            if (priority === 'urgent') return 'bg-rose-900/30 text-rose-300 border border-rose-800/50';
            if (priority === 'high') return 'bg-orange-900/30 text-orange-300 border border-orange-800/50';
            if (priority === 'normal') return 'bg-cyan-900/30 text-cyan-300 border border-cyan-800/50';
            if (priority === 'low') return 'bg-slate-800 text-slate-300 border border-slate-700';
            return 'bg-slate-800 text-slate-300 border border-slate-700';
        }

        async function loadSupportTickets() {
            const box = document.getElementById('supportTicketsList');
            if (!box) return;
            setResultLoading(box, 'My Support Tickets', 'Loading tickets...');
            const res = await fetch('/api/support/tickets');
            const data = await res.json();
            if (!data.success) {
                setResultError(box, 'Failed to load tickets');
                return;
            }
            const rows = data.tickets || [];
            if (!rows.length) {
                setResultList(box, 'My Support Tickets', [], { badge: '0', emptyText: 'لا توجد تذاكر حالياً.' });
                return;
            }

            const storageKey = 'titanSupportSeenStates';
            let seenStates = {};
            try {
                seenStates = JSON.parse(localStorage.getItem(storageKey) || '{}') || {};
            } catch (e) {
                seenStates = {};
            }
            const hadHistory = Object.keys(seenStates).length > 0;
            let updatesCount = 0;
            const nextSeenStates = {};

            setResultMarkup(
                box,
                'My Support Tickets',
                rows.map(t => {
                const status = String(t.status || 'open');
                const priority = String(t.priority || 'normal');
                const signature = `${t.updated_at || ''}|${status}|${t.admin_note || ''}`;
                const prevSig = seenStates[String(t.id)];
                const hasUpdate = !!(prevSig && prevSig !== signature);
                if (hasUpdate) updatesCount++;
                nextSeenStates[String(t.id)] = signature;
                return `
                <div class="p-2 rounded-lg border ${status === 'open' ? 'border-cyan-800/50 bg-cyan-900/10' : 'border-slate-700 bg-black/30'} ${hasUpdate ? 'ring-1 ring-amber-500/50' : ''}">
                    <div class="flex items-center justify-between gap-2 mb-1">
                        <div class="text-xs font-bold text-cyan-300">#${t.id} ${_osintEscape(t.subject)}</div>
                        <div class="flex items-center gap-1.5">
                            ${hasUpdate ? '<span class="text-[10px] px-2 py-0.5 rounded bg-amber-900/30 text-amber-300 border border-amber-800/50">🔔 تحديث جديد</span>' : ''}
                            <div class="text-[10px] px-2 py-0.5 rounded ${_supportStatusBadgeClass(status)}">${_osintEscape(status)}</div>
                            <div class="text-[10px] px-2 py-0.5 rounded ${_supportPriorityBadgeClass(priority)}">${_osintEscape(priority)}</div>
                        </div>
                    </div>
                    <div class="text-[10px] text-gray-400 mb-1">${_osintEscape(t.category)} | Created: ${_osintEscape(t.created_at)} | Updated: ${_osintEscape(t.updated_at || t.created_at)}</div>
                    <div class="text-xs text-gray-300 whitespace-pre-wrap">${_osintEscape(t.details)}</div>
                    ${t.admin_note ? `<div class="mt-1 text-[11px] text-emerald-300 border-t border-slate-700 pt-1">🛠️ Admin note: ${_osintEscape(t.admin_note)}</div>` : ''}
                </div>
            `;
            }).join(''),
                { badge: `${rows.length} Tickets` }
            );

            try {
                localStorage.setItem(storageKey, JSON.stringify(nextSeenStates));
            } catch (e) {}

            if (hadHistory && updatesCount > 0) {
                titanAlert(`🔔 لديك ${updatesCount} تحديث جديد على تذاكر الدعم`, 'success');
            }
        }

        async function analyzePassword() {
            const pass = document.getElementById('ai-pass-input').value;
            const result = document.getElementById('ai-pass-result');
            if (!pass) return titanAlert('أدخل كلمة السر للتحليل');
            result.classList.remove('hidden');
            result.textContent = 'جاري التحليل... قد يستغرق 30-60 ثانية ⏳';
            try {
                const res = await fetch('/api/ai/analyze', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({type: 'password', content: pass})
                });
                const data = await res.json();
                result.textContent = data.analysis || data.error || 'فشل التحليل';
            } catch(e) {
                result.textContent = 'فشل الاتصال - حاول مرة أخرى';
            }
        }

        async function analyzeSecurity() {
            const secVal = document.getElementById('ai-security-input').value;
            const result = document.getElementById('ai-security-result');
            if (!secVal) return titanAlert('أدخل البيانات للتحليل');
            result.classList.remove('hidden');
            result.textContent = 'جاري التحليل الأمني... قد يستغرق 30-60 ثانية ⏳';
            try {
                const res = await fetch('/api/ai/analyze', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({type: 'security', content: secVal})
                });
                const data = await res.json();
                result.textContent = data.analysis || data.error || 'فشل التحليل';
            } catch(e) {
                result.textContent = 'فشل الاتصال - حاول مرة أخرى';
            }
        }


        async function generateQR() {
            const text = document.getElementById('qrText').value.trim();
            const pass = document.getElementById('qrPass').value;
            if(!text) { titanAlert('أدخل النص'); return; }
            const res = await fetch('/api/qr/generate', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({text, password: pass})
            });
            const d = await res.json();
            if(d.error) { titanAlert(d.error); return; }
            const src = 'data:image/png;base64,' + d.qr;
            document.getElementById('qrImg').src = src;
            document.getElementById('qrDownload').href = src;
            document.getElementById('qrResult').classList.remove('hidden');
        }

        async function decodeQR() {
            const file = document.getElementById('qrFile').files[0];
            const pass = document.getElementById('qrDecodePass').value;
            if(!file) { titanAlert('اختر صورة'); return; }
            const form = new FormData();
            form.append('file', file);
            form.append('password', pass);
            const res = await fetch('/api/qr/decode', {method:'POST', body:form});
            const d = await res.json();
            const el = document.getElementById('qrDecodeResult');
            el.classList.remove('hidden');
            el.innerText = d.error ? '❌ ' + d.error : '✅ ' + d.text;
            el.className = el.className + (d.error ? ' text-red-400' : ' text-green-300');
        }

        async function generateIdentity() {
            const lang = document.getElementById('identityLang').value;
            const resArea = document.getElementById('identityResultArea');
            
            // Helper: safely set innerText only if element exists
            function setEl(id, value) {
                const el = document.getElementById(id);
                if (el) el.innerText = value || '';
            }
            
            try {
                // Dim area while loading
                if(!resArea.classList.contains('hidden')) {
                    resArea.style.opacity = '0.5';
                }
                
                const res = await fetch(`/api/fake-identity?lang=${lang}`);
                const data = await res.json();
                
                if (data.error) throw new Error(data.error);
                
                // Populate data safely
                setEl('idName', data.name);
                setEl('idCardNameDisplay', data.name);
                setEl('idGender', data.gender);
                setEl('idMotherName', data.mother_name);
                setEl('idNational', data.national_id);
                setEl('idDob', data.birthdate);
                setEl('idAge', data.age);
                setEl('idZodiac', data.zodiac);

                setEl('idAddress', data.address);
                setEl('idZip', data.zip_code);
                setEl('idGeo', data.geo);
                setEl('idCountryCode', data.country_code);

                setEl('idPhone', data.phone);
                setEl('idEmail', data.email);
                setEl('idCompany', data.company);
                setEl('idJob', data.job);

                setEl('idHeight', data.height);
                setEl('idWeight', data.weight);
                setEl('idBlood', data.blood_type);
                setEl('idColor', data.color);
                setEl('idVehicle', data.vehicle);

                setEl('idCcType', data.cc_type ? data.cc_type.toUpperCase() : '');
                setEl('idCredit', data.credit_card ? (data.credit_card.match(/.{1,4}/g) || []).join(' ') : '');
                setEl('idCcExp', data.cc_expire);
                setEl('idCcCvv', data.cc_cvv);

                setEl('idUsername', data.username);
                setEl('idPassword', data.password);
                
                const websiteEl = document.getElementById('idWebsite');
                if (websiteEl) { websiteEl.innerText = data.website; websiteEl.href = data.website; }
                setEl('idUserAgent', data.user_agent);
                setEl('idUuid', data.uuid);
                
                // Show area and restore opacity
                resArea.classList.remove('hidden');
                resArea.style.opacity = '1';
                
                soundManager.terminalType();
                soundManager.success();
            } catch (err) {
                titanAlert("تعذر توليد الهوية: " + err.message);
                soundManager.error();
                resArea.style.opacity = '1';
            }
        }

        function copyFullIdentity() {
            const getVal = (id) => {
                const el = document.getElementById(id);
                return el ? el.innerText : 'غير متوفر';
            };
            const langEl = document.getElementById('identityLang');
            const langText = langEl && langEl.options[langEl.selectedIndex] ? langEl.options[langEl.selectedIndex].text : '';
            
            const dataToCopy = `
=== هوية وهمية مقترحة (${langText}) ===
الاسم الكامل: ${getVal('idName')}
الجنس: ${getVal('idGender')}
اسم الأم: ${getVal('idMotherName')}
تاريخ الميلاد: ${getVal('idDob')} (${getVal('idAge')} سنة - ${getVal('idZodiac')})
الرقم الوطني: ${getVal('idNational')}

[معلومات الاتصال والموقع]
العنوان: ${getVal('idAddress')}
الرمز البريدي: ${getVal('idZip')}
الإحداثيات: ${getVal('idGeo')}
رقم الهاتف: ${getVal('idPhone')}
البريد الإلكتروني: ${getVal('idEmail')}

[العمل والخصائص الجسدية]
الشركة: ${getVal('idCompany')}
الوظيفة: ${getVal('idJob')}
الطول/الوزن: ${getVal('idHeight')} / ${getVal('idWeight')}
فصيلة الدم: ${getVal('idBlood')}
اللون المفضل: ${getVal('idColor')}
السيارة: ${getVal('idVehicle')}

[بيانات البطاقة الائتمانية]
النوع: ${getVal('idCcType')}
رقم البطاقة: ${getVal('idCredit')}
تاريخ الانتهاء: ${getVal('idCcExp')}
CVV: ${getVal('idCcCvv')}

[بيانات رقمية]
اسم المستخدم: ${getVal('idUsername')}
كلمة المرور: ${getVal('idPassword')}
موقع الويب: ${getVal('idWebsite')}
User Agent: ${getVal('idUserAgent')}
UUID: ${getVal('idUuid')}
===============================
            `.trim();
            
            let btn = null;
            if (window.event && window.event.currentTarget) {
                btn = window.event.currentTarget;
            } else if (window.event && window.event.srcElement) {
                btn = window.event.srcElement.closest('button');
            }
            
            let displaySpan = btn;
            if (btn) {
                const spans = btn.querySelectorAll('span');
                if (spans.length > 0) {
                    displaySpan = spans.length > 1 && spans[1].innerText.length > spans[0].innerText.length ? spans[1] : spans[0];
                }
            }
            
            const oldText = displaySpan ? displaySpan.innerText : '';
            
            navigator.clipboard.writeText(dataToCopy).then(() => {
                if (typeof soundManager !== 'undefined' && soundManager.click) {
                    soundManager.click();
                }
                if (displaySpan) {
                    displaySpan.innerText = "تم النسخ بنجاح ✔️";
                    setTimeout(() => displaySpan.innerText = oldText, 2000);
                }
            });
        }

        // --- وظائف الأدوات الجديدة المتقدمة ---
        let _audioRecorder = null;
        let _audioStream = null;
        let _audioChunks = [];
        let _recordedAudioBlob = null;

        async function startAudioRecording() {
            try {
                _audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                _audioChunks = [];
                _audioRecorder = new MediaRecorder(_audioStream);
                _audioRecorder.ondataavailable = (e) => {
                    if (e.data && e.data.size > 0) _audioChunks.push(e.data);
                };
                _audioRecorder.onstop = () => {
                    const mime = _audioRecorder.mimeType || 'audio/webm';
                    _recordedAudioBlob = new Blob(_audioChunks, { type: mime });
                    const preview = document.getElementById('audioRecordedPreview');
                    const status = document.getElementById('audioRecStatus');
                    preview.src = URL.createObjectURL(_recordedAudioBlob);
                    preview.classList.remove('hidden');
                    status.innerText = 'تم حفظ التسجيل محلياً وجاهز للإخفاء.';
                };
                _audioRecorder.start();
                document.getElementById('audioRecStartBtn').disabled = true;
                document.getElementById('audioRecStopBtn').disabled = false;
                document.getElementById('audioRecStatus').innerText = 'جاري التسجيل... تحدث الآن.';
            } catch (e) {
                titanAlert('تعذر الوصول للميكروفون. تأكد من السماح بالصلاحية.');
            }
        }

        function stopAudioRecording() {
            if (_audioRecorder && _audioRecorder.state !== 'inactive') {
                _audioRecorder.stop();
            }
            if (_audioStream) {
                _audioStream.getTracks().forEach(t => t.stop());
                _audioStream = null;
            }
            document.getElementById('audioRecStartBtn').disabled = false;
            document.getElementById('audioRecStopBtn').disabled = true;
        }

        function _arrayBufferToBase64(buffer) {
            let binary = '';
            const bytes = new Uint8Array(buffer);
            const chunkSize = 0x8000;
            for (let i = 0; i < bytes.length; i += chunkSize) {
                const chunk = bytes.subarray(i, i + chunkSize);
                binary += String.fromCharCode.apply(null, chunk);
            }
            return btoa(binary);
        }

        async function _encryptAudioSecretInBrowser(text, passphrase) {
            const encoder = new TextEncoder();
            const salt = crypto.getRandomValues(new Uint8Array(16));
            const iv = crypto.getRandomValues(new Uint8Array(12));
            const keyMaterial = await crypto.subtle.importKey(
                'raw',
                encoder.encode(passphrase),
                'PBKDF2',
                false,
                ['deriveKey']
            );
            const key = await crypto.subtle.deriveKey(
                { name: 'PBKDF2', salt, iterations: 120000, hash: 'SHA-256' },
                keyMaterial,
                { name: 'AES-GCM', length: 256 },
                false,
                ['encrypt']
            );
            const cipherBuf = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, encoder.encode(text));
            return `ENC_AUDIO_V1:${_arrayBufferToBase64(salt)}:${_arrayBufferToBase64(iv)}:${_arrayBufferToBase64(cipherBuf)}`;
        }

        async function _decryptAudioSecretInBrowser(payload, passphrase) {
            if (!payload.startsWith('ENC_AUDIO_V1:')) return payload;
            const parts = payload.split(':');
            if (parts.length !== 4) throw new Error('صيغة النص المشفر داخل الصوت غير صالحة.');
            const [, saltB64, ivB64, cipherB64] = parts;
            const toBytes = (b64) => Uint8Array.from(atob(b64), c => c.charCodeAt(0));
            const salt = toBytes(saltB64);
            const iv = toBytes(ivB64);
            const cipherBytes = toBytes(cipherB64);

            const encoder = new TextEncoder();
            const keyMaterial = await crypto.subtle.importKey(
                'raw',
                encoder.encode(passphrase),
                'PBKDF2',
                false,
                ['deriveKey']
            );
            const key = await crypto.subtle.deriveKey(
                { name: 'PBKDF2', salt, iterations: 120000, hash: 'SHA-256' },
                keyMaterial,
                { name: 'AES-GCM', length: 256 },
                false,
                ['decrypt']
            );
            const plainBuf = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, cipherBytes);
            return new TextDecoder().decode(plainBuf);
        }
        
        async function processAudio(action) {
            const formData = new FormData();
            if (action === 'encode') {
                const fileEl = document.getElementById('audioFileEncrypt');
                const file = fileEl.files[0];
                const text = document.getElementById('audioSecretText').value.trim();
                const passphrase = document.getElementById('audioSecretPass').value.trim();
                
                if (!text) {
                    return titanAlert('يرجى كتابة النص السري المراد إخفاؤه.');
                }

                const sourceBlob = file || _recordedAudioBlob;
                if (!sourceBlob) {
                    return titanAlert('اختر ملف صوتي أو سجّل صوتاً أولاً.');
                }

                let finalSecret = text;
                if (passphrase) {
                    finalSecret = await _encryptAudioSecretInBrowser(text, passphrase);
                }
                
                console.log('جاري المعالجة...');

                const extGuess = file ? file.name.split('.').pop() : 'webm';
                const uploadName = file ? file.name : `recorded_audio.${extGuess || 'webm'}`;
                formData.append('file', sourceBlob, uploadName);
                formData.append('text', finalSecret);
                
                try {
                    const response = await fetch('/api/audio/stego/encode', { method:'POST', body:formData });
                    if (!response.ok) {
                        const err = await response.json();
                        throw new Error(err.error || 'عذراً، فشلت عملية التشفير.');
                    }
                    
                    const blob = await response.blob();
                    const downloadUrl = window.URL.createObjectURL(blob);
                    const downloadAnchor = document.createElement('a');
                    downloadAnchor.href = downloadUrl;
                    downloadAnchor.download = "TITAN_SECURE_" + uploadName;
                    document.body.appendChild(downloadAnchor);
                    downloadAnchor.click();
                    
                    titanAlert(passphrase ? 'تم تشفير النص ثم إخفاؤه داخل الصوت ✅' : 'تم إخفاء النص داخل الصوت ✅');
                    
                    setTimeout(() => {
                        document.body.removeChild(downloadAnchor);
                        window.URL.revokeObjectURL(downloadUrl);
                    }, 500);
                } catch (error) {
                    titanAlert('خطأ: ' + error.message);
                }
            } else {
                const file = document.getElementById('audioFileDecrypt').files[0];
                const decodePass = document.getElementById('audioDecodePass').value.trim();
                if (!file) return titanAlert('يرجى اختيار الملف المراد فحصه.');
                
                console.log('جاري التحليل...');
                formData.append('file', file);
                
                try {
                    const res = await fetch('/api/audio/stego/decode', { method:'POST', body:formData });
                    const data = await res.json();
                    
                    if (data.error) {
                        titanAlert('تنبيه: ' + data.error);
                    } else if (data.success && data.hidden_data) {
                        let shownText = data.hidden_data;
                        if (shownText.startsWith('ENC_AUDIO_V1:')) {
                            if (!decodePass) {
                                shownText = 'تم العثور على نص مشفر. أدخل كلمة السر لفك التشفير.';
                            } else {
                                try {
                                    shownText = await _decryptAudioSecretInBrowser(shownText, decodePass);
                                } catch (e) {
                                    shownText = 'فشل فك التشفير: كلمة السر غير صحيحة أو البيانات تالفة.';
                                }
                            }
                        }
                        document.getElementById('audioDecodedResult').innerText = shownText;
                        titanAlert('✅ تم العثور على نص مخفي!');
                    } else {
                        titanAlert('لم يتم العثور على بيانات مخفية.');
                    }
                } catch (error) {
                    titanAlert('خطأ في الاتصال بالخادم.');
                }
            }
        }

        async function _encryptVideoSecretInBrowser(text, passphrase) {
            const encoder = new TextEncoder();
            const salt = crypto.getRandomValues(new Uint8Array(16));
            const iv = crypto.getRandomValues(new Uint8Array(12));
            const keyMaterial = await crypto.subtle.importKey(
                'raw',
                encoder.encode(passphrase),
                'PBKDF2',
                false,
                ['deriveKey']
            );
            const key = await crypto.subtle.deriveKey(
                { name: 'PBKDF2', salt, iterations: 120000, hash: 'SHA-256' },
                keyMaterial,
                { name: 'AES-GCM', length: 256 },
                false,
                ['encrypt']
            );
            const cipherBuf = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, encoder.encode(text));
            return `ENC_VIDEO_V1:${_arrayBufferToBase64(salt)}:${_arrayBufferToBase64(iv)}:${_arrayBufferToBase64(cipherBuf)}`;
        }

        async function _decryptVideoSecretInBrowser(payload, passphrase) {
            if (!payload.startsWith('ENC_VIDEO_V1:')) return payload;
            const parts = payload.split(':');
            if (parts.length !== 4) throw new Error('صيغة النص المشفر داخل الفيديو غير صالحة.');
            const [, saltB64, ivB64, cipherB64] = parts;
            const toBytes = (b64) => Uint8Array.from(atob(b64), c => c.charCodeAt(0));

            const salt = toBytes(saltB64);
            const iv = toBytes(ivB64);
            const cipherBytes = toBytes(cipherB64);
            const encoder = new TextEncoder();

            const keyMaterial = await crypto.subtle.importKey(
                'raw',
                encoder.encode(passphrase),
                'PBKDF2',
                false,
                ['deriveKey']
            );
            const key = await crypto.subtle.deriveKey(
                { name: 'PBKDF2', salt, iterations: 120000, hash: 'SHA-256' },
                keyMaterial,
                { name: 'AES-GCM', length: 256 },
                false,
                ['decrypt']
            );
            const plainBuf = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, cipherBytes);
            return new TextDecoder().decode(plainBuf);
        }

        async function scanVideoClip() {
            const file = document.getElementById('videoScanFile').files[0];
            if (!file) return titanAlert('اختر فيديو أولاً لفحصه.');

            const formData = new FormData();
            formData.append('file', file);

            const box = document.getElementById('videoScanResult');
            box.classList.remove('hidden');
            box.innerText = 'جاري فحص الفيديو...';

            try {
                const res = await fetch('/api/video/scan', { method: 'POST', body: formData });
                const data = await res.json();
                if (!res.ok || data.error) throw new Error(data.error || 'فشل فحص الفيديو');

                const lines = [
                    `الاسم: ${data.filename || file.name}`,
                    `الدقة: ${data.width}x${data.height}`,
                    `عدد الإطارات: ${data.frame_count}`,
                    `FPS: ${data.fps}`,
                    `المدة (ثانية): ${data.duration_seconds}`,
                    `السعة التقريبية للنص (بايت): ${data.estimated_capacity_bytes}`,
                    `تم رصد بيانات مخفية سابقاً: ${data.has_hidden_payload ? 'نعم' : 'لا'}`
                ];
                box.innerText = lines.join('\\n');
                soundManager.success();
            } catch (e) {
                box.innerText = 'خطأ: ' + e.message;
                soundManager.error();
            }
        }

        async function processVideo(action) {
            const formData = new FormData();
            if (action === 'encode') {
                const file = document.getElementById('videoFileEncrypt').files[0];
                const text = document.getElementById('videoSecretText').value.trim();
                const passphrase = document.getElementById('videoSecretPass').value.trim();

                if (!file) return titanAlert('يرجى اختيار ملف فيديو.');
                if (!text) return titanAlert('يرجى كتابة النص المراد إخفاؤه.');

                let finalSecret = text;
                if (passphrase) {
                    finalSecret = await _encryptVideoSecretInBrowser(text, passphrase);
                }

                formData.append('file', file);
                formData.append('text', finalSecret);

                try {
                    const response = await fetch('/api/video/stego/encode', { method: 'POST', body: formData });
                    if (!response.ok) {
                        const err = await response.json();
                        throw new Error(err.error || 'فشلت عملية الإخفاء داخل الفيديو');
                    }

                    const blob = await response.blob();
                    const downloadUrl = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = downloadUrl;
                    a.download = 'TITAN_STEGO_' + file.name.replace(/\\.[^/.]+$/, '') + '.mp4';
                    document.body.appendChild(a);
                    a.click();
                    setTimeout(() => {
                        document.body.removeChild(a);
                        window.URL.revokeObjectURL(downloadUrl);
                    }, 500);

                    titanAlert(passphrase ? 'تم تشفير النص ثم إخفاؤه داخل الفيديو ✅' : 'تم إخفاء النص داخل الفيديو ✅');
                    soundManager.success();
                    refreshLogs();
                } catch (e) {
                    titanAlert('خطأ: ' + e.message);
                    soundManager.error();
                }
            } else {
                const file = document.getElementById('videoFileDecrypt').files[0];
                const decodePass = document.getElementById('videoDecodePass').value.trim();
                if (!file) return titanAlert('يرجى اختيار ملف فيديو للتحليل.');

                formData.append('file', file);

                try {
                    const res = await fetch('/api/video/stego/decode', { method: 'POST', body: formData });
                    const data = await res.json();

                    if (data.error) {
                        titanAlert('تنبيه: ' + data.error);
                        return;
                    }

                    if (data.success && data.hidden_data) {
                        let shownText = data.hidden_data;
                        if (shownText.startsWith('ENC_VIDEO_V1:')) {
                            if (!decodePass) {
                                shownText = 'تم العثور على نص مشفر. أدخل كلمة السر لفك التشفير.';
                            } else {
                                try {
                                    shownText = await _decryptVideoSecretInBrowser(shownText, decodePass);
                                } catch (e) {
                                    shownText = 'فشل فك التشفير: كلمة السر غير صحيحة أو البيانات تالفة.';
                                }
                            }
                        }

                        document.getElementById('videoDecodedResult').innerText = shownText;
                        titanAlert('✅ تم استخراج النص من الفيديو');
                        soundManager.success();
                        refreshLogs();
                    } else {
                        document.getElementById('videoDecodedResult').innerText = 'لا توجد بيانات مخفية.';
                        titanAlert('لم يتم العثور على بيانات مخفية داخل الفيديو.');
                    }
                } catch (e) {
                    titanAlert('خطأ في الاتصال بالخادم.');
                    soundManager.error();
                }
            }
        }

        async function processVideoFile(action) {
            const file = document.getElementById('videoFileCrypt').files[0];
            const key = document.getElementById('videoFileCryptPass').value.trim();
            if (!file) return titanAlert('يرجى اختيار ملف فيديو أو ملف مشفر.');
            if (!key) return titanAlert('يرجى إدخال كلمة السر أولاً.');

            const formData = new FormData();
            formData.append('file', file);
            formData.append('key', key);

            const endpoint = action === 'encrypt' ? '/api/video/file/encrypt' : '/api/video/file/decrypt';

            try {
                const res = await fetch(endpoint, { method: 'POST', body: formData });
                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.error || 'فشل عملية تشفير/فك الفيديو');
                }

                const blob = await res.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                const cleanBase = file.name.replace(/\\.titan$/i, '').replace(/\\.[^/.]+$/, '');
                a.href = url;
                a.download = action === 'encrypt' ? (cleanBase + '.mp4.titan') : (cleanBase + '_decrypted.mp4');
                document.body.appendChild(a);
                a.click();
                setTimeout(() => {
                    document.body.removeChild(a);
                    window.URL.revokeObjectURL(url);
                }, 500);

                titanAlert(action === 'encrypt' ? '✅ تم تشفير ملف الفيديو بالكامل' : '✅ تم فك تشفير ملف الفيديو بنجاح');
                soundManager.success();
                refreshLogs();
            } catch (e) {
                titanAlert('خطأ: ' + e.message);
                soundManager.error();
            }
        }

        async function cleanPdf() {
            const file = document.getElementById('pdfCleanFile').files[0];
            if (!file) return Swal.fire({ icon:'error', title:'خطأ', text:'يرجى اختيار ملف PDF.' });
            const formData = new FormData();
            formData.append('file', file);
            
            try {
                const res = await fetch('/api/pdf/clean', { method:'POST', body:formData });
                if (!res.ok) throw new Error('فشل التنظيف');
                const blob = await res.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = "clean_" + file.name;
                document.body.appendChild(a);
                a.click();

                titanAlert('تم التنظيف بنجاح، تم تحميل الملف النظيف.');
            } catch (e) { titanAlert('خطأ: ' + e.message); }
        }

        function generateStealthFingerprint() {
            const prints = [
                { os: "Linux x86_64", browser: "Tor Browser/11.5.1", gl: "Intel Open Source Technology Center", screen: "1366x768", fonts: ["Arimo", "Tinos"] },
                { os: "Windows 10.0", browser: "Hardened Firefox/98.0", gl: "Microsoft Basic Render", screen: "1920x1080", fonts: ["Arial", "Courier"] },
                { os: "macOS 12.0", browser: "Safari/15.0 (Stealth)", gl: "Apple M1 GPU", screen: "1440x900", fonts: ["Helvetica", "Menlo"] }
            ];
            const p = prints[Math.floor(Math.random()*prints.length)];
            document.getElementById('fingerprintDisplay').innerText = JSON.stringify(p, null, 2);

        }

        async function runShodanScan() {
            const ip = document.getElementById('shodanIp').value;
            if (!ip) return;
            const res = await fetch('/api/intel/shodan', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ip}) });
            const data = await res.json();
            document.getElementById('shodanResult').innerText = JSON.stringify(data, null, 2);

        }

        async function checkDnsLeak() {
            const res = await fetch('/api/intel/dns-leak');
            const data = await res.json();
            document.getElementById('dnsLeakStatus').innerText = data.leaked ? "⚠️ تسريب!" : "✅ آمن";
            document.getElementById('dnsLeakStatus').className = data.leaked ? "text-2xl font-black mb-1 text-red-500" : "text-2xl font-black mb-1 text-green-500";

        }

        function panicWipe() {
            if (confirm('تدمير الجلسة؟ سيتم تسجيل الخروج فوراً ومسح كافة البيانات المؤقتة!')) {
                doLogout();
            }
        }
    </script>
</body>
</html>
"""

# --- المسارات (Routes) ---

@app.route('/tailwind.css')
def tailwind_css():
    """Serve Tailwind CSS from disk, with a safe minimal fallback in production."""
    css_path = os.path.join(app.root_path, 'static', 'css', 'tailwind.css')
    try:
        with open(css_path, 'r', encoding='utf-8') as f:
            css = f.read()
        return Response(css, mimetype='text/css')
    except Exception:
        fallback_css = """
/* TITAN emergency CSS fallback */
html,body{margin:0;padding:0;font-family:'Tajawal',sans-serif;background:#070b19;color:#fff}
.hidden{display:none !important}
.container{width:100%;max-width:64rem;margin-left:auto;margin-right:auto}
.glass{background:rgba(10,15,30,.85);border:1px solid rgba(168,85,247,.2);border-radius:1rem}
.tab-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:.45rem}
button,input,textarea,select{font:inherit}
"""
        return Response(fallback_css, mimetype='text/css')

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/scan', methods=['POST'])
def scan():
    target = request.json.get('target', '')
    label, score = get_strength_details(target)
    count = check_hibp_leak(target)
    return jsonify({"strength": label, "score": score, "exposed_count": count})

@app.route('/generate', methods=['GET'])
def generate():
    mode = request.args.get('mode', 'random')
    if mode == 'passphrase':
        return jsonify({"suggested": generate_readable_passphrase()})
    return jsonify({"suggested": generate_strong_password()})

@app.route('/api/metadata/remove', methods=['POST'])
def metadata_remove_route():
    file = request.files['file']
    filename = file.filename or 'image.png'
    try:
        processed_data = remove_image_metadata(file.read())
        add_audit_log("إزالة ميتابيانات", f"الملف: {filename}")
        return send_file(
            io.BytesIO(processed_data),
            mimetype='image/png',
            as_attachment=True,
            download_name="clean_" + filename
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/steganography/encode', methods=['POST'])
def stego_encode_route():
    file = request.files['file']
    filename = file.filename or 'image.png'
    text = request.form['text']
    try:
        processed_data = lsb_encode(file.read(), text)
        add_audit_log("تشفير إخفاء (Stego)", f"إخفاء نص في {filename}")
        return send_file(
            io.BytesIO(processed_data),
            mimetype='image/png',
            as_attachment=True,
            download_name="stego_" + filename
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/steganography/decode', methods=['POST'])
def stego_decode_route():
    file = request.files['file']
    filename = file.filename or 'image.png'
    try:
        decoded_text = lsb_decode(file.read())
        add_audit_log("فك إخفاء (Stego)", f"محاولة استخراج نص من {filename}")
        return jsonify({"result": decoded_text})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/audio/stego/encode', methods=['POST'])
def audio_stego_encode_route():
    if 'file' not in request.files or 'text' not in request.form:
        return jsonify({"error": "الملف والنص مطلوبان"}), 400
    file = request.files['file']
    filename = file.filename or 'audio.wav'
    text = request.form['text']
    try:
        file_bytes = file.read()
        processed_data = wave_lsb_encode(file_bytes, text, filename)
        add_audit_log("إخفاء صوتي (Audio Stego)", f"إخفاء نص في {filename}")
        return send_file(
            io.BytesIO(processed_data),
            mimetype='audio/wav' if filename.lower().endswith('.wav') else 'audio/mpeg',
            as_attachment=True,
            download_name="TITAN_SECURE_" + filename
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/audio/stego/decode', methods=['POST'])
def audio_stego_decode_route():
    if 'file' not in request.files:
        return jsonify({"error": "يرجى اختيار ملف"}), 400
    file = request.files['file']
    filename = file.filename or 'audio.wav'
    try:
        file_bytes = file.read()
        hidden_data = wave_lsb_decode(file_bytes, filename)
        add_audit_log("استخراج صوتي (Audio Stego)", f"محاولة استخراج من {filename}")
        if "لم يتم العثور" in hidden_data or "خطأ" in hidden_data:
             return jsonify({"success": True, "hidden_data": None, "error": hidden_data})
        return jsonify({"success": True, "hidden_data": hidden_data})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/video/scan', methods=['POST'])
def video_scan_route():
    if 'file' not in request.files:
        return jsonify({"error": "يرجى اختيار ملف فيديو"}), 400
    file = request.files['file']
    filename = file.filename or 'video.mp4'
    try:
        result = scan_video_clip(file.read(), filename)
        if not result.get('success'):
            return jsonify({"error": result.get('error', 'فشل الفحص')}) , 400
        add_audit_log("فحص فيديو", f"تحليل خصائص {filename}")
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/video/stego/encode', methods=['POST'])
def video_stego_encode_route():
    if 'file' not in request.files or 'text' not in request.form:
        return jsonify({"error": "الملف والنص مطلوبان"}), 400
    file = request.files['file']
    filename = file.filename or 'video.mp4'
    text = request.form['text']
    try:
        processed_data = video_lsb_encode(file.read(), text)
        add_audit_log("إخفاء داخل فيديو", f"إخفاء نص في {filename}")
        return send_file(
            io.BytesIO(processed_data),
            mimetype='video/mp4',
            as_attachment=True,
            download_name='TITAN_STEGO_' + filename.rsplit('.', 1)[0] + '.mp4'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/video/stego/decode', methods=['POST'])
def video_stego_decode_route():
    if 'file' not in request.files:
        return jsonify({"error": "يرجى اختيار ملف فيديو"}), 400
    file = request.files['file']
    filename = file.filename or 'video.mp4'
    try:
        hidden_data = video_lsb_decode(file.read())
        add_audit_log("استخراج من فيديو", f"محاولة استخراج نص من {filename}")
        if "لم يتم العثور" in hidden_data or "تعذر" in hidden_data:
            return jsonify({"success": True, "hidden_data": None, "error": hidden_data})
        return jsonify({"success": True, "hidden_data": hidden_data})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/video/file/encrypt', methods=['POST'])
def video_file_encrypt_route():
    if 'file' not in request.files:
        return jsonify({"error": "يرجى اختيار ملف فيديو"}), 400
    key = (request.form.get('key') or '').strip()
    if not key:
        return jsonify({"error": "كلمة السر مطلوبة"}), 400

    file = request.files['file']
    filename = file.filename or 'video.mp4'

    try:
        encrypted = encrypt_data(file.read(), key)
        add_audit_log("تشفير ملف فيديو", f"تشفير كامل للملف: {filename}")
        return send_file(
            io.BytesIO(encrypted),
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=filename + '.titan'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/video/file/decrypt', methods=['POST'])
def video_file_decrypt_route():
    if 'file' not in request.files:
        return jsonify({"error": "يرجى اختيار ملف مشفر"}), 400
    key = (request.form.get('key') or '').strip()
    if not key:
        return jsonify({"error": "كلمة السر مطلوبة"}), 400

    file = request.files['file']
    filename = file.filename or 'video.mp4.titan'

    try:
        decrypted = decrypt_data(file.read(), key)
        out_name = filename[:-6] if filename.lower().endswith('.titan') else ('decrypted_' + filename)
        add_audit_log("فك تشفير ملف فيديو", f"فك كامل للملف: {filename}")
        return send_file(
            io.BytesIO(decrypted),
            mimetype='video/mp4',
            as_attachment=True,
            download_name=out_name
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/audit-logs', methods=['GET'])
def get_audit_logs():
    return jsonify(AUDIT_LOGS)

@app.route('/crypt-text', methods=['POST'])
def crypt_text_route():
    data = request.json
    text, key, action = data['text'], data['key'], data['action']
    try:
        if action == 'encrypt':
            result = encrypt_data(text.encode(), key).decode('latin1') # استخدام latin1 لنقل bytes كنص
            return jsonify({"result": base64.b64encode(result.encode('latin1')).decode()})
        else:
            encrypted_bytes = base64.b64decode(text)
            result = decrypt_data(encrypted_bytes, key).decode()
            return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/crypt-file', methods=['POST'])
def crypt_file_route():
    file = request.files['file']
    filename = file.filename or 'file.bin'
    key = request.form['key']
    action = request.form['action']
    try:
        file_data = file.read()
        if action == 'encrypt':
            processed_data = encrypt_data(file_data, key)
        else:
            processed_data = decrypt_data(file_data, key)
        
        return send_file(
            io.BytesIO(processed_data),
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=filename + ('.titan' if action == 'encrypt' else '')
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/ip', methods=['POST'])
def ip_check():
    data = request.json or {}
    ip = str(data.get('ip', "") or "").strip()
    if not ip:
        if request.headers.getlist("X-Forwarded-For"):
            ip = request.headers.getlist("X-Forwarded-For")[0]
        else:
            ip = str(request.remote_addr or "")
        if ip == "127.0.0.1": 
            ip = ""
            
    info = get_ip_intelligence_data(ip)
    return jsonify(info)

@app.route('/api/scan/phone', methods=['POST'])
def scan_phone_route():
    data = request.json or {}
    phone = data.get('phone', '')
    res = check_phone_intelligence(phone)
    add_audit_log("فحص رقم هاتف (IPQualityScore)", f"تم فحص الرقم: {phone}")
    return jsonify(res)

@app.route('/api/scan/url', methods=['POST'])
def scan_url_route():
    data = request.json or {}
    url = data.get('url', '')
    res = check_url_intelligence(url)
    add_audit_log("فحص رابط مشبوه (IPQualityScore)", f"تم فحص الموثوقية: {url[:30]}...")
    return jsonify(res)

@app.route('/api/scan/malware_url', methods=['POST'])
def scan_malware_url_route():
    data = request.json or {}
    url = data.get('url', '')
    res = scan_malware_url(url)
    add_audit_log("فحص URL خبيث (Malware)", f"تم فحص: {url[:30]}...")
    return jsonify(res)

@app.route('/api/scan/malware_file', methods=['POST'])
def scan_malware_file_route():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "لم يتم تقديم أي ملف"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "message": "لم يتم اختيار ملف"}), 400

    filename = file.filename or 'uploaded.bin'
    temp_path = os.path.join(tempfile.gettempdir(), secure_filename(filename))
    file.save(temp_path)
    
    try:
        res = scan_malware_file(temp_path)
        add_audit_log("فحص ملف خبيث (Malware)", f"اسم الملف: {filename}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
    return jsonify(res)

@app.route('/api/scan/emailpass_leak', methods=['POST'])
def scan_emailpass_leak_route():
    data = request.json or {}
    email = data.get('email', '')
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({"success": False, "message": "الرجاء توفير الإيميل وكلمة السر"}), 400
        
    res = check_leaked_emailpass(email, password)
    add_audit_log("فحص تسريب (IPQualityScore)", f"تم الفحص لـ: {email}")
    return jsonify(res)

@app.route('/api/scan/ipqs_logs', methods=['POST'])
def scan_ipqs_logs_route():
    data = request.json or {}
    req_type = data.get('type', 'proxy')
    start_date = data.get('start_date', '2024-01-01')
    
    res = get_ipqs_requests_list(req_type, start_date)
    add_audit_log("سجلات API (IPQualityScore)", f"استعلام عن: {req_type} منذ {start_date}")
    return jsonify(res)

@app.route('/api/2fa/generate', methods=['GET'])
def generate_2fa():
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name="TITAN User", issuer_name="TITAN Security")
    
    img = qrcode.make(provisioning_uri)
    buffered = io.BytesIO()
    img.save(buffered, "PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    
    return jsonify({
        "secret": secret,
        "qr_code": f"data:image/png;base64,{img_str}"
    })

@app.route('/api/2fa/verify', methods=['POST'])
def verify_2fa():
    data = request.json or {}
    secret = data.get('secret')
    code = data.get('code')
    
    if not secret or not code:
        return jsonify({"valid": False})
        
    totp = pyotp.TOTP(secret)
    is_valid = totp.verify(code)
    return jsonify({"valid": is_valid})

# --- مسارات القبو المشفر (Per-User) ---

def _get_logged_in_user_id():
    """Returns (user_id, None) if logged in, else (None, error_response)."""
    user_id = session.get('user_id')
    if user_id is None:
        return None, (jsonify({"error": "غير مصرح. يجب تسجيل الدخول أولاً."}), 401)
    try:
        return int(user_id), None
    except Exception:
        return None, (jsonify({"error": "جلسة غير صالحة. يرجى تسجيل الدخول مجدداً."}), 401)

@app.route('/api/vault/has-password', methods=['GET'])
def vault_has_password():
    """Check if the logged-in user has a vault password set."""
    user_id, err = _get_logged_in_user_id()
    if err: return err
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT vault_password_hash FROM users WHERE id = %s", (user_id,))
        row = c.fetchone()
        has_pw = bool(row and row[0])
        return jsonify({"hasVaultPassword": has_pw})
    except Exception as e:
        print(f"[TITAN] Vault has-password error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/vault/set-password', methods=['POST'])
def vault_set_password():
    """First-time vault password setup for the logged-in user."""
    user_id, err = _get_logged_in_user_id()
    if err: return err
    data = request.json or {}
    password = data.get('password', '').strip()
    if len(password) < 4:
        return jsonify({"error": "كلمة سر القبو يجب أن تكون 4 أحرف على الأقل"}), 400
    pw_hash = hash_password(password)
    import os
    db_url = os.environ.get('DATABASE_URL', '')
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    c = conn.cursor()
    # Check if already set
    c.execute("SELECT vault_password_hash FROM users WHERE id = %s", (user_id,))
    row = c.fetchone()
    if row and row[0]:
        conn.close()
        return jsonify({"error": "كلمة سر القبو محددة مسبقاً. استخدمها للدخول."}), 409
    c.execute("UPDATE users SET vault_password_hash = %s WHERE id = %s", (pw_hash, user_id))
    conn.commit()
    conn.close()
    add_audit_log("تعيين كلمة سر القبو 🔐", f"المستخدم #{user_id} عيّن كلمة سر قبو جديدة")
    return jsonify({"success": True})

@app.route('/api/vault/load', methods=['POST'])
def load_vault():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    data = request.json or {}
    key = data.get('key')
    if not key: return jsonify({"error": "Missing key"}), 400

    # Verify the vault password against the stored hash
    import os
    db_url = os.environ.get('DATABASE_URL', '')
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    c = conn.cursor()
    c.execute("SELECT vault_password_hash FROM users WHERE id = %s", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row or not row[0]:
        return jsonify({"error": "لم تقم بتعيين كلمة سر للقبو بعد."}), 403
    if not verify_password(key, row[0]):
        add_audit_log("فشل فتح القبو 🚨", f"كلمة سر خاطئة للمستخدم #{user_id}")
        return jsonify({"error": "كلمة السر الرئيسية غير صحيحة."}), 401

    vault_file = get_vault_file(int(user_id))
    if not os.path.exists(vault_file):
        add_audit_log("فتح القبو ✅", f"قبو جديد للمستخدم #{user_id}")
        return jsonify({"vault": []})  # قبو جديد

    try:
        with open(vault_file, 'rb') as f:
            encrypted_data = f.read()
        decrypted_bytes = decrypt_data(encrypted_data, key)
        vault_data = json.loads(decrypted_bytes.decode('utf-8'))
        add_audit_log("فتح القبو ✅", f"تم الوصول لقبو المستخدم #{user_id}")
        return jsonify({"vault": vault_data})
    except Exception:
        add_audit_log("فشل فتح القبو 🚨", f"خطأ في فك التشفير للمستخدم #{user_id}")
        return jsonify({"error": "كلمة السر الرئيسية غير صحيحة أو الملف معطوب."}), 401

@app.route('/api/vault/save', methods=['POST'])
def save_vault():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    data = request.json or {}
    key = data.get('key')
    vault_list = data.get('vault', [])
    if not key: return jsonify({"error": "Missing key"}), 400

    # Re-verify password before saving
    import os
    db_url = os.environ.get('DATABASE_URL', '')
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    c = conn.cursor()
    c.execute("SELECT vault_password_hash FROM users WHERE id = %s", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row or not row[0] or not verify_password(key, row[0]):
        return jsonify({"error": "كلمة السر غير صحيحة. لا يمكن الحفظ."}), 401

    try:
        json_str = json.dumps(vault_list).encode('utf-8')
        encrypted_data = encrypt_data(json_str, key)
        vault_file = get_vault_file(int(user_id))
        with open(vault_file, 'wb') as f:
            f.write(encrypted_data)
        add_audit_log("حفظ القبو 💾", f"تم تحديث {len(vault_list)} عنصر للمستخدم #{user_id}")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/vault/backup', methods=['POST'])
def backup_vault():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    vault_file = get_vault_file(int(user_id))
    if not os.path.exists(vault_file):
        return jsonify({"error": "لا يوجد قبو لتصديره!"}), 400
    try:
        with open(vault_file, 'rb') as f:
            data = f.read()
        add_audit_log("تصدير النسخة الاحتياطية 📦", f"المستخدم #{user_id}")
        return send_file(
            io.BytesIO(data),
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=f"vault_backup_user{user_id}.titan.bak"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/vault/restore', methods=['POST'])
def restore_vault():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    file = request.files['file']
    try:
        data = file.read()
        vault_file = get_vault_file(int(user_id))
        with open(vault_file, 'wb') as f:
            f.write(data)
        add_audit_log("استعادة النسخة الاحتياطية 🔄", f"تم استعادة قبو المستخدم #{user_id}")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/vault/recovery/setup', methods=['POST'])
def setup_recovery():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    data = request.json or {}
    key = data.get('key', '')
    q1 = data.get('q1', '')
    a1 = data.get('a1', '')
    q2 = data.get('q2', '')
    a2 = data.get('a2', '')

    if not all([key, q1, a1, q2, a2]):
        return jsonify({"error": "جميع الحقول مطلوبة"}), 400

    recovery_pass = a1.strip().lower() + "|" + a2.strip().lower()
    encrypted_key = encrypt_data(key.encode('utf-8'), recovery_pass)
    recovery_file = get_vault_recovery_file(int(user_id))

    with open(recovery_file, 'w', encoding='utf-8') as f:
        json.dump({
            "q1": q1,
            "q2": q2,
            "encrypted_key": base64.b64encode(encrypted_key).decode('utf-8')
        }, f, ensure_ascii=False)

    add_audit_log("إعداد استعادة القبو 🔑", f"المستخدم #{user_id} عيّن أسئلة الأمان")
    return jsonify({"success": True})

@app.route('/api/vault/recovery/questions', methods=['GET'])
def get_recovery_questions():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    recovery_file = get_vault_recovery_file(int(user_id))
    if not os.path.exists(recovery_file):
        return jsonify({"error": "لم تقم بإعداد أسئلة الأمان مسبقاً لاستعادة هذا القبو."}), 400
    with open(recovery_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify({"q1": data["q1"], "q2": data["q2"]})

@app.route('/api/vault/recovery/recover', methods=['POST'])
def recover_vault_key():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    data = request.json or {}
    a1 = data.get('a1', '')
    a2 = data.get('a2', '')
    recovery_file = get_vault_recovery_file(int(user_id))
    if not os.path.exists(recovery_file):
        return jsonify({"error": "لم يتم إعداد أسئلة الأمان"}), 400

    with open(recovery_file, 'r', encoding='utf-8') as f:
        r_data = json.load(f)

    recovery_pass = a1.strip().lower() + "|" + a2.strip().lower()
    try:
        encrypted_key_bytes = base64.b64decode(r_data["encrypted_key"])
        decrypted_key = decrypt_data(encrypted_key_bytes, recovery_pass)
        add_audit_log("استعادة القبو ✅", f"المستخدم #{user_id} استعاد كلمة سر القبو")
        return jsonify({"recovered_key": decrypted_key.decode('utf-8')})
    except Exception:
        add_audit_log("محاولة استعادة فاشلة 🚨", f"إجابات خاطئة للمستخدم #{user_id}")
        return jsonify({"error": "الإجابات التي أدخلتها غير صحيحة"}), 401

@app.route('/api/vault/forgot-password', methods=['POST'])
def vault_forgot_password():
    """إرسال كود استعادة القبو للمستخدم المسجل دخوله"""
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    
    user_id = int(session['user_id'])
    username = str(session.get('username', ''))
    
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT email FROM users WHERE id = %s", (user_id,))
        row = c.fetchone()
        
        if not row or not row[0]:
            return jsonify({"error": "لا يوجد بريد إلكتروني مسجّل لحسابك. تواصل مع الإدارة."}), 400
        
        email = row[0]
        otp = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
        
        c.execute("UPDATE users SET vault_otp_code = %s WHERE id = %s", (otp, user_id))
        conn.commit()
        
        send_otp_email(email, otp)
        add_audit_log("طلب استعادة القبو 🔐", f"تم إرسال كود استعادة للمستخدم: {username}", username=username)
        return jsonify({"success": True, "message": "تم إرسال كود الاستعادة إلى بريدك الإلكتروني."})
    except Exception as e:
        print(f"[TITAN] Vault forgot password error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/vault/reset-password', methods=['POST'])
def vault_reset_password():
    """إعادة تعيين كلمة سر القبو باستخدام الكود"""
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
        
    data = request.json or {}
    otp = data.get('otp', '').strip()
    new_password = data.get('new_password', '').strip()
    
    if not otp or not new_password:
        return jsonify({"error": "البيانات ناقصة"}), 400
    if len(new_password) < 4:
        return jsonify({"error": "كلمة سر القبو قصيرة جداً"}), 400
        
    user_id = session['user_id']
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT vault_otp_code FROM users WHERE id = %s", (user_id,))
        row = c.fetchone()
        
        if not row or row[0] != otp:
            return jsonify({"error": "كود التحقق غير صحيح"}), 401
            
        new_hash = hash_password(new_password)
        c.execute("UPDATE users SET vault_password_hash = %s, vault_otp_code = NULL WHERE id = %s", (new_hash, user_id))
        conn.commit()
        
        add_audit_log("إعادة تعيين القبو ✅", f"تم تعيين كلمة سر قبو جديدة للمستخدم #{user_id}")
        return jsonify({"success": True, "message": "تم إعادة تعيين كلمة سر القبو بنجاح!"})
    except Exception as e:
        print(f"[TITAN] Vault reset password error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

# --- Admin Routes ---

@app.route('/api/admin/reset-system', methods=['POST'])
def admin_reset_system():
    """تصفير السيرفر بالكامل (حذف جميع البيانات باستثناء الأدمن)"""
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
        
    user_id = session['user_id']
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT is_admin FROM users WHERE id = %s", (user_id,))
        row = c.fetchone()
        
        if not row or not row[0]:
            return jsonify({"error": "صلاحيات غير كافية. هذه العملية تتطلب حساب Root."}), 403
            
        # حذف كل شيء باستثناء الأدمن
        # 1. حذف الجلسات
        c.execute("DELETE FROM active_sessions WHERE user_id != %s", (user_id,))
        # 2. حذف القبو الزمني
        c.execute("DELETE FROM vault_timelocked")
        # 3. حذف سجلات الأمان
        c.execute("DELETE FROM security_logs")
        # 4. حذف جميع المستخدمين باستثناء الحالي (الأدمن)
        c.execute("DELETE FROM users WHERE id != %s", (user_id,))
        
        conn.commit()
        
        # حذف ملفات القبو الفيزيائية
        vault_dir = 'vaults'
        if os.path.exists(vault_dir):
            import shutil
            for filename in os.listdir(vault_dir):
                 file_path = os.path.join(vault_dir, filename)
                 try:
                     if os.path.isfile(file_path): os.unlink(file_path)
                 except: pass

        add_audit_log("تصفير النظام ⚠️", "تم إجراء عملية تصفير شاملة للنظام من قبل المسؤول")
        return jsonify({"success": True, "message": "تم تصفير النظام بنجاح! تم حذف جميع المستخدمين والبيانات."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/admin/support/tickets', methods=['GET'])
def admin_support_tickets_list():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401

    user_id = session['user_id']
    status_filter = (request.args.get('status') or 'all').strip().lower()
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()

        c.execute("SELECT is_admin FROM users WHERE id = %s", (user_id,))
        row = c.fetchone()
        if not row or not row[0]:
            return jsonify({"success": False, "error": "صلاحيات غير كافية"}), 403

        base_query = (
            "SELECT st.id, COALESCE(u.username, ''), st.subject, st.category, st.priority, st.details, "
            "st.status, st.admin_note, st.created_at, st.updated_at "
            "FROM support_tickets st LEFT JOIN users u ON u.id = st.user_id"
        )
        params = []
        if status_filter in ('open', 'in_progress', 'resolved', 'closed'):
            base_query += " WHERE st.status = %s"
            params.append(status_filter)
        base_query += " ORDER BY st.id DESC LIMIT 300"

        c.execute(base_query, tuple(params))
        rows = c.fetchall()
        tickets = [
            {
                "id": r[0],
                "username": r[1],
                "subject": r[2],
                "category": r[3],
                "priority": r[4],
                "details": r[5],
                "status": r[6],
                "admin_note": r[7],
                "created_at": r[8],
                "updated_at": r[9]
            }
            for r in rows
        ]
        return jsonify({"success": True, "tickets": tickets})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/admin/support/tickets/<int:ticket_id>', methods=['PATCH'])
def admin_support_tickets_update(ticket_id):
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401

    user_id = session['user_id']
    data = request.json or {}
    status = (data.get('status') or '').strip().lower()
    admin_note = (data.get('admin_note') or '').strip()
    if status not in ('open', 'in_progress', 'resolved', 'closed'):
        return jsonify({"success": False, "error": "status غير صالح"}), 400

    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()

        c.execute("SELECT is_admin FROM users WHERE id = %s", (user_id,))
        row = c.fetchone()
        if not row or not row[0]:
            return jsonify({"success": False, "error": "صلاحيات غير كافية"}), 403

        now = datetime.datetime.now().isoformat()
        c.execute(
            "UPDATE support_tickets SET status=%s, admin_note=%s, updated_at=%s WHERE id=%s RETURNING id",
            (status, admin_note, now, ticket_id)
        )
        updated = c.fetchone()
        if not updated:
            conn.rollback()
            return jsonify({"success": False, "error": "التذكرة غير موجودة"}), 404

        conn.commit()
        add_audit_log("Support Ticket Admin", f"ticket#{ticket_id} => {status}", username=session.get('username', ''))
        return jsonify({"success": True, "ticket_id": ticket_id, "status": status})
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


# --- مسارات الإضافات الجديدة المتقدمة ---



@app.route('/api/pdf-process', methods=['POST'])
def pdf_process_route():
    try:
        file = request.files['file']
        password = request.form['password']
        action = request.form.get('action', 'lock')
        
        reader = PdfReader(file.stream)
        writer = PdfWriter()
        
        if action == 'lock':
            for page in reader.pages:
                writer.add_page(page)
            writer.encrypt(password)
            add_audit_log("حماية PDF 🔒", f"تم تشفير الملف بكلمة سر ({file.filename})")
        else:
            if reader.is_encrypted:
                reader.decrypt(password)
            for page in reader.pages:
                writer.add_page(page)
            add_audit_log("فك حماية PDF 🔓", f"تم فتح الملف ({file.filename})")
            
        out_stream = io.BytesIO()
        writer.write(out_stream)
        out_stream.seek(0)
        
        dl_name = f"locked_{file.filename}" if action == 'lock' else f"unlocked_{file.filename}"
        return send_file(
            out_stream, 
            mimetype='application/pdf', 
            as_attachment=True, 
            download_name=dl_name
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/port-scan', methods=['POST'])
def port_scan_route():
    ip = request.json.get('ip', '127.0.0.1')
    common_ports = [21, 22, 23, 25, 53, 80, 110, 143, 443, 3306, 3389, 8080]
    open_ports = []
    
    def scan_port(port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex((ip, port))
        sock.close()
        return port if result == 0 else None
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(common_ports)) as executor:
        results = executor.map(scan_port, common_ports)
        for r in results:
            if r is not None:
                open_ports.append(r)
                
    add_audit_log("فحص منافذ 📡", f"{ip} - عُثر على {len(open_ports)} منفذ مفتوح")
    return jsonify({"open_ports": open_ports})

@app.route('/api/burn-note/create', methods=['POST'])
def create_burn_note():
    text = request.json.get('text')
    if not text:
        return jsonify({"error": "نص فارغ"}), 400
    
    note_id = str(uuid.uuid4())
    BURN_NOTES[note_id] = text
    add_audit_log("رسالة تدمير ذاتي 🔥", f"تم توليد رابط رسالة جديدة")
    
    # Generate full access URL
    url = f"{request.host_url}burn/{note_id}"
    return jsonify({"link": url})

@app.route('/burn/<note_id>', methods=['GET'])
def view_burn_note(note_id):
    if note_id in BURN_NOTES:
        # قرأناها ودمّرناها فوراً من المتغير (RAM)
        text = BURN_NOTES.pop(note_id) 
        add_audit_log("رسالة مدمرة 💣", f"تم فتح الرسالة وتدميرها للأبد")
        
        return f'''
        <!DOCTYPE html>
        <html lang="ar" dir="rtl">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>رسالة مدمرة | TITAN</title>
            <style>
                body {{ background: #050505; color: #fff; font-family: 'Segoe UI', Tahoma, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; background-image: radial-gradient(circle at center, #2e0909 0%, #050505 100%); user-select: none; -webkit-user-select: none; }}
                body::selection {{ background: transparent; color: transparent; }}
                .container {{ background: #0a0a0a; border: 1px solid #ef4444; border-radius: 12px; padding: 40px; box-shadow: 0 0 50px rgba(239, 68, 68, 0.2); max-width: 600px; text-align: center; position: relative; overflow: hidden; width: 90%; transition: filter 0.2s, opacity 0.2s; }}
                .container::before {{ content:""; position:absolute; top:0; left:0; right:0; height:4px; background:linear-gradient(90deg, #ef4444, #f97316); }}
                h1 {{ color: #ef4444; margin-bottom: 5px; font-weight: 900; letter-spacing: -1px; text-shadow: 0 0 20px rgba(239,68,68,0.5); pointer-events: none; }}
                .subtitle {{ color: #9ca3af; font-size: 14px; margin-bottom: 30px; line-height: 1.6; pointer-events: none; }}
                .warning {{ margin-top: 30px; font-size: 14px; color: #ef4444; opacity: 0.9; font-weight: bold; letter-spacing: 1px; pointer-events: none; }}
                @keyframes pulse-icon {{ 0%, 100% {{ transform: scale(1); }} 50% {{ transform: scale(1.1); filter: drop-shadow(0 0 15px #ef4444); }} }}

                /* === ANTI-CAMERA CSS ANIMATION ===
                   Rapidly cycles the text between two color states at ~8Hz.
                   Human eye (persistence ~100ms) sees the ON state clearly.
                   Camera integrating over 1/30s captures both states merged
                   creating color fringing + temporal blur that obscures the text. */
                @keyframes antiCam {{
                    0%   {{ color: #ff5555; text-shadow: 0 0 8px rgba(255,85,85,0.7); }}
                    49%  {{ color: #ff5555; text-shadow: 0 0 8px rgba(255,85,85,0.7); }}
                    50%  {{ color: #0a0a0a; text-shadow: none; }}
                    99%  {{ color: #0a0a0a; text-shadow: none; }}
                    100% {{ color: #ff5555; text-shadow: 0 0 8px rgba(255,85,85,0.7); }}
                }}
                .secure-text {{
                    background: #000;
                    padding: 24px 20px;
                    border-radius: 8px;
                    border: 1px dashed #ef4444;
                    text-align: right;
                    direction: rtl;
                    font-size: 20px;
                    line-height: 1.9;
                    word-wrap: break-word;
                    white-space: pre-wrap;
                    font-family: 'Segoe UI', Tahoma, 'Arial', monospace;
                    font-weight: bold;
                    pointer-events: none;
                    animation: antiCam 0.125s steps(1) infinite;
                    margin-bottom: 10px;
                }}
            </style>
        </head>
        <body oncontextmenu="return false;" onkeydown="return disableCopyKeys(event);">
            <div class="container" id="secureContainer">
                <div style="font-size: 60px; margin-bottom: 20px; animation: pulse-icon 2s infinite;">💣</div>
                <h1>هذه الرسالة دُمّرت للتو!</h1>
                <p class="subtitle" id="topSubtitle">لقد تم مسح هذه الرسالة نهائياً من الذاكرة الحية للخادم بمجرد فتحك لها.<br>لن يمكنك أنت أو غيرك قراءة محتواها مرة أخرى، قم بنسخها الآن إذا احتجت لذلك.</p>
                <!-- Full Arabic text - browser handles letter joining natively -->
                <div class="secure-text" id="secureText">{text}</div>
                <p style="color:#6b7280; font-size:10px; margin:0 0 10px 0; letter-spacing:1px;">🔒 CAMERA-RESISTANT DISPLAY</p>
                <div class="warning" id="timerWarning">⚠️ تدمير ذاتي إضافي للشاشة خلال <span id="countdown">10</span> ثواني...</div>
            </div>
            
            <script>
                let timeLeft = 10;
                const countdownEl = document.getElementById('countdown');
                const warningBox = document.getElementById('timerWarning');
                const topSubs = document.getElementById('topSubtitle');
                const secureTextEl = document.getElementById('secureText');
                let destroyed = false;

                const timer = setInterval(() => {{
                    timeLeft--;
                    countdownEl.innerText = timeLeft;
                    
                    if (timeLeft <= 3) {{
                        countdownEl.style.fontSize = '24px';
                        countdownEl.parentElement.style.textShadow = '0 0 10px red';
                    }}
                    
                    if(timeLeft <= 0) {{
                        clearInterval(timer);
                        // Stop the CSS animation and replace text with destroyed message
                        secureTextEl.style.animation = 'none';
                        secureTextEl.style.color = '#ef4444';
                        secureTextEl.style.textAlign = 'center';
                        secureTextEl.textContent = '💥 تم تدمير الرسالة نهائياً';
                        warningBox.innerText = 'SECURE BURN COMPLETE // SYSTEM LOGGED';
                        topSubs.innerText = 'تم التخلص من الرسالة بالكامل من الشاشة.';
                    }}
                }}, 1000);

                // Anti-Copy and Anti-Screenshot Scripts
                function disableCopyKeys(e) {{
                    if(e.ctrlKey && (e.key === 'c' || e.key === 'p' || e.key === 's')) return false;
                    if(e.key === 'PrintScreen') {{
                        navigator.clipboard.writeText('محاولة التقاط شاشة مرفوضة.');
                        return false;
                    }}
                }}
                
                document.addEventListener('keyup', (e) => {{
                    if(e.key === 'PrintScreen') navigator.clipboard.writeText('محاولة التقاط شاشة مرفوضة.');
                }});
                
                // Hide content when window loses focus to prevent screenshots/recording
                const secContainer = document.getElementById('secureContainer');
                window.addEventListener('blur', () => {{
                    secContainer.style.filter = 'blur(30px)';
                    secContainer.style.opacity = '0';
                }});
                window.addEventListener('focus', () => {{
                    secContainer.style.filter = 'none';
                    secContainer.style.opacity = '1';
                }});
            </script>
        </body>
        </html>
        '''
    else:
        return f'''
        <!DOCTYPE html>
        <html lang="ar" dir="rtl">
        <head><meta charset="UTF-8"><title>الرسالة غير موجودة</title></head>
        <body style="background:#050505; color:#ef4444; font-family:sans-serif; text-align:center; padding-top:100px;">
            <div style="font-size: 60px; margin-bottom:20px;">🕳️</div>
            <h2>الرسالة غير متوفرة!</h2>
            <p style="color:#9ca3af;">الرابط غير صالح، أو أن الرسالة تم الإطلاع عليها وتدميرها مسبقاً.</p>
        </body>
        </html>
        ''', 404

# --- مسارات الإضافات للحزمة الثالثة المتقدمة (Audio & Privacy) ---

@app.route('/api/audio/stego/encode', methods=['POST'])
def audio_stego_encode():
    file = request.files['file']
    filename = file.filename or 'audio.wav'
    text = request.form['text']
    try:
        processed_data = wave_lsb_encode(file.read(), text, filename)
        add_audit_log("إخفاء في الصوت 🎵", f"تم إخفاء بيانات في {filename}")
        mimetype = 'audio/mpeg' if filename.lower().endswith('.mp3') else 'audio/wav'
        return send_file(
            io.BytesIO(processed_data),
            mimetype=mimetype,
            as_attachment=True,
            download_name="stego_" + filename
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/audio/stego/decode', methods=['POST'])
def audio_stego_decode():
    file = request.files['file']
    filename = file.filename or 'audio.wav'
    try:
        decoded_text = wave_lsb_decode(file.read(), filename)
        add_audit_log("استخراج من الصوت 🎵", f"محاولة فك تشفير {filename}")
        return jsonify({"success": True, "hidden_data": decoded_text})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/pdf/clean', methods=['POST'])
def pdf_clean_route():
    file = request.files['file']
    filename = file.filename or 'file.pdf'
    try:
        processed_data = clean_pdf_metadata(file.read())
        add_audit_log("تنظيف PDF 🧹", f"إزالة ميتابيانات {filename}")
        return send_file(
            io.BytesIO(processed_data),
            mimetype='application/pdf',
            as_attachment=True,
            download_name="clean_" + filename
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/intel/dns-leak', methods=['GET'])
def dns_leak_route():
    return jsonify(get_dns_leak_info())

@app.route('/api/intel/shodan', methods=['POST'])
def shodan_intel_route():
    ip = request.json.get('ip', '')
    return jsonify(get_shodan_intel(ip))

# --- مسارات الإضافات للحزمة الثانية المتقدمة ---

@app.route('/api/osint/image', methods=['POST'])
def osint_image_route():
    try:
        file = request.files['file']
        data = extract_exif_data(file.read())
        add_audit_log("استخبارات صور (OSINT)", f"تم استخراج بيانات من {file.filename}")
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/scan/email', methods=['POST'])
def scan_email_route():
    email = request.json.get('email', '')
    res = check_email_intelligence(email)
    add_audit_log("فحص إيميل (IPQualityScore)", f"تم فحص البريد: {email}")
    return jsonify(res)


@app.route('/api/osint/username', methods=['POST'])
def osint_username_route():
    data = request.json or {}
    username = data.get('username', '').strip()
    result = check_username_presence(username)
    if not result.get('success'):
        return jsonify(result), 400
    add_audit_log("Username Hunter (OSINT)", f"فحص اليوزرنيم: {username}")
    return jsonify(result)


@app.route('/api/osint/hash', methods=['POST'])
def osint_hash_route():
    data = request.json or {}
    hash_value = data.get('hash', '').strip()
    result = analyze_hash_indicator(hash_value)
    if not result.get('success'):
        return jsonify(result), 400
    add_audit_log("Hash Analyzer (OSINT)", f"تحليل Hash بطول {len(hash_value)}")
    return jsonify(result)


@app.route('/api/incidents/create', methods=['POST'])
def ir_create_case_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    data = request.json or {}
    title = data.get('title', '').strip()
    severity = (data.get('severity') or 'medium').strip().lower()
    description = data.get('description', '').strip()
    if not title:
        return jsonify({"success": False, "error": "عنوان القضية مطلوب"}), 400
    if severity not in ('low', 'medium', 'high', 'critical'):
        severity = 'medium'
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO incident_cases (user_id, title, severity, status, description, created_at, updated_at)
            VALUES (%s,%s,%s,'open',%s,%s,%s) RETURNING id
        """, (user_id, title, severity, description, now, now))
        row = c.fetchone()
        if not row:
            conn.rollback()
            return jsonify({"success": False, "error": "فشل إنشاء القضية"}), 500
        case_id = row[0]
        conn.commit()
        add_audit_log("Incident Created", f"case#{case_id} {title}", username=session.get('username', ''))
        return jsonify({"success": True, "case_id": case_id})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/incidents/list', methods=['GET'])
def ir_list_cases_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT id, title, severity, status, description, created_at, updated_at FROM incident_cases WHERE user_id=%s ORDER BY id DESC", (user_id,))
        rows = c.fetchall()
        cases = [
            {
                "id": r[0], "title": r[1], "severity": r[2], "status": r[3],
                "description": r[4], "created_at": r[5], "updated_at": r[6]
            }
            for r in rows
        ]
        return jsonify({"success": True, "cases": cases})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/incidents/<int:case_id>/status', methods=['POST'])
def ir_update_case_status_route(case_id: int):
    user_id, err = _get_logged_in_user_id()
    if err: return err
    status = (request.json or {}).get('status', 'open').strip().lower()
    if status not in ('open', 'investigating', 'contained', 'closed'):
        return jsonify({"success": False, "error": "Status غير صالح"}), 400
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("UPDATE incident_cases SET status=%s, updated_at=%s WHERE id=%s AND user_id=%s", (status, now, case_id, user_id))
        conn.commit()
        add_audit_log("Incident Status", f"case#{case_id} -> {status}", username=session.get('username', ''))
        return jsonify({"success": True})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/incidents/<int:case_id>/ioc', methods=['POST'])
def ir_add_ioc_route(case_id: int):
    user_id, err = _get_logged_in_user_id()
    if err: return err
    data = request.json or {}
    ioc_type = data.get('ioc_type', '').strip().lower()
    ioc_value = data.get('ioc_value', '').strip()
    risk_score = int(data.get('risk_score', 0) or 0)
    if not ioc_type or not ioc_value:
        return jsonify({"success": False, "error": "ioc_type و ioc_value مطلوبان"}), 400
    risk_score = max(0, min(100, risk_score))
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT id FROM incident_cases WHERE id=%s AND user_id=%s", (case_id, user_id))
        if not c.fetchone():
            return jsonify({"success": False, "error": "القضية غير موجودة"}), 404
        c.execute("INSERT INTO incident_iocs (case_id, ioc_type, ioc_value, risk_score, created_at) VALUES (%s,%s,%s,%s,%s)",
                  (case_id, ioc_type, ioc_value, risk_score, now))
        conn.commit()
        add_audit_log("IOC Added", f"case#{case_id} {ioc_type}:{ioc_value}", username=session.get('username', ''))
        return jsonify({"success": True})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/incidents/<int:case_id>/ioc', methods=['GET'])
def ir_list_iocs_route(case_id: int):
    user_id, err = _get_logged_in_user_id()
    if err: return err
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT id FROM incident_cases WHERE id=%s AND user_id=%s", (case_id, user_id))
        if not c.fetchone():
            return jsonify({"success": False, "error": "القضية غير موجودة"}), 404
        c.execute("SELECT id, ioc_type, ioc_value, risk_score, created_at FROM incident_iocs WHERE case_id=%s ORDER BY id DESC", (case_id,))
        rows = c.fetchall()
        iocs = [{"id": r[0], "ioc_type": r[1], "ioc_value": r[2], "risk_score": r[3], "created_at": r[4]} for r in rows]
        return jsonify({"success": True, "iocs": iocs})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/incidents/<int:case_id>/report', methods=['GET'])
def ir_case_report_route(case_id: int):
    user_id, err = _get_logged_in_user_id()
    if err: return err
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT id, title, severity, status, description, created_at, updated_at FROM incident_cases WHERE id=%s AND user_id=%s", (case_id, user_id))
        case_row = c.fetchone()
        if not case_row:
            return jsonify({"success": False, "error": "القضية غير موجودة"}), 404
        c.execute("SELECT ioc_type, ioc_value, risk_score, created_at FROM incident_iocs WHERE case_id=%s ORDER BY id DESC", (case_id,))
        iocs = c.fetchall()
        report = {
            "case": {
                "id": case_row[0], "title": case_row[1], "severity": case_row[2], "status": case_row[3],
                "description": case_row[4], "created_at": case_row[5], "updated_at": case_row[6]
            },
            "iocs": [
                {"ioc_type": r[0], "ioc_value": r[1], "risk_score": r[2], "created_at": r[3]} for r in iocs
            ],
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        return jsonify({"success": True, "report": report})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/link-analyzer/build', methods=['POST'])
def link_analyzer_build_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    nodes = (request.json or {}).get('nodes', [])
    graph = build_link_analysis_graph(nodes)
    add_audit_log("Link Analysis", f"nodes={len(graph['nodes'])} edges={len(graph['edges'])}", username=session.get('username', ''))
    return jsonify({"success": True, "nodes": graph['nodes'], "edges": graph['edges']})


@app.route('/api/hunt/query', methods=['POST'])
def hunt_query_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    data = request.json or {}
    query = (data.get('query') or '').strip().lower()
    ioc_type = (data.get('ioc_type') or 'all').strip().lower()
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        sql = """
            SELECT ii.case_id, ii.ioc_type, ii.ioc_value, ii.risk_score, ii.created_at
            FROM incident_iocs ii
            JOIN incident_cases ic ON ic.id = ii.case_id
            WHERE ic.user_id = %s
        """
        params: list[object] = [user_id]
        if ioc_type != 'all':
            sql += " AND ii.ioc_type = %s"
            params.append(ioc_type)
        if query:
            sql += " AND LOWER(ii.ioc_value) LIKE %s"
            params.append(f"%{query}%")
        sql += " ORDER BY ii.id DESC LIMIT 200"
        c.execute(sql, tuple(params))
        rows = c.fetchall()
        out = [{"case_id": r[0], "ioc_type": r[1], "ioc_value": r[2], "risk_score": r[3], "created_at": r[4]} for r in rows]
        return jsonify({"success": True, "rows": out})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/hunt/rule-evaluate', methods=['POST'])
def hunt_rule_evaluate_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    threshold = int((request.json or {}).get('threshold', 70) or 70)
    threshold = max(0, min(100, threshold))
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("""
            SELECT AVG(ii.risk_score)
            FROM incident_iocs ii
            JOIN incident_cases ic ON ic.id = ii.case_id
            WHERE ic.user_id = %s
        """, (user_id,))
        row = c.fetchone()
        avg_risk = float((row[0] if row else 0) or 0)
        alert_created = avg_risk >= threshold
        if alert_created:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("INSERT INTO hunting_alerts (user_id, title, details, severity, created_at) VALUES (%s,%s,%s,%s,%s)",
                      (user_id, 'Hunting Rule Triggered', f'Avg risk {avg_risk:.2f} >= {threshold}', 'high', now))
            conn.commit()
        return jsonify({"success": True, "avg_risk": round(avg_risk, 2), "threshold": threshold, "alert_created": alert_created})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/forensics/triage', methods=['POST'])
def forensics_triage_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "يرجى اختيار ملف"}), 400
    file = request.files['file']
    raw = file.read()
    result = {
        "success": True,
        "filename": file.filename,
        "size_bytes": len(raw),
        "md5": hashlib.md5(raw).hexdigest(),
        "sha1": hashlib.sha1(raw).hexdigest(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "entropy_hint": round(len(set(raw)) / 256 * 8, 3) if raw else 0,
        "triaged_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    add_audit_log("Forensics Triage", f"{file.filename} ({len(raw)} bytes)", username=session.get('username', ''))
    return jsonify(result)


@app.route('/api/brand/typosquatting', methods=['POST'])
def brand_typosquatting_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    domain = (request.json or {}).get('domain', '').strip().lower()
    if not domain or '.' not in domain:
        return jsonify({"success": False, "error": "يرجى إدخال domain صالح"}), 400
    variants = generate_typosquatting_variants(domain)
    add_audit_log("Brand Typosquatting", f"{domain} -> {len(variants)} variants", username=session.get('username', ''))
    return jsonify({"success": True, "domain": domain, "similar_domains": variants})


@app.route('/api/social/simulate', methods=['POST'])
def social_simulate_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    scenario_type = (request.json or {}).get('scenario_type', 'phishing_email')
    payload = create_social_defense_scenario(scenario_type)
    add_audit_log("Social Engineering Drill", f"scenario={scenario_type}", username=session.get('username', ''))
    return jsonify({"success": True, **payload})

@app.route('/api/network/scan', methods=['GET'])
def scan_network_route():
    result = scan_local_network()
    add_audit_log("رادار الشبكة المحلية", f"تم العثور على {result.get('count', 0)} جهاز متصل")
    return jsonify(result)

# --- مسارات الإضافات للحزمة الرابعة المتقدمة (Phase 4: Defense & Comms) ---

# 1. USB Guardian
USB_MONITOR_ACTIVE = False
USB_MONITOR_THREAD = None
LAST_DRIVES = set()

def get_current_drives():
    drives = set()
    try:
        for p in psutil.disk_partitions():
            if 'removable' in p.opts.lower() or p.fstype == '':
                drives.add(p.device)
    except:
        pass
    return drives

def usb_monitor_listener():
    global USB_MONITOR_ACTIVE, LAST_DRIVES
    import time
    LAST_DRIVES = get_current_drives()
    
    suspicious_files = ['autorun.inf']
    suspicious_exts = ['.vbs', '.bat', '.ps1', '.exe', '.cmd']
    
    while USB_MONITOR_ACTIVE:
        current_drives = get_current_drives()
        new_drives = current_drives - LAST_DRIVES
        
        for drive in new_drives:
            with app.app_context():
                add_audit_log("🛡️ حارس منافذ USB", f"تم رصد توصيل قرص جديد: {drive}")
            
            # Simple root scan for threats
            try:
                if os.path.exists(drive):
                    for f in os.listdir(drive):
                        f_lower = f.lower()
                        if f_lower in suspicious_files or any(f_lower.endswith(ext) for ext in suspicious_exts):
                            with app.app_context():
                                add_audit_log("🚨 تهديد USB محتمل", f"عُثر على ملف تشغيل تلقائي أو تنفيذي مشبوه في {drive}: {f}")
            except Exception:
                pass
                
        LAST_DRIVES = current_drives
        time.sleep(3)

@app.route('/api/defense/usb', methods=['POST'])
def toggle_usb_guardian():
    global USB_MONITOR_ACTIVE, USB_MONITOR_THREAD
    action = request.json.get('action')
    if action == 'start':
        if not USB_MONITOR_ACTIVE:
            USB_MONITOR_ACTIVE = True
            USB_MONITOR_THREAD = threading.Thread(target=usb_monitor_listener, daemon=True)
            USB_MONITOR_THREAD.start()
            add_audit_log("تفعيل حارس USB", "تم تفعيل المراقبة الفورية لمنافذ USB")
        return jsonify({"status": "active"})
    else:
        USB_MONITOR_ACTIVE = False
        add_audit_log("إيقاف حارس USB", "تم إيقاف المراقبة")
        return jsonify({"status": "inactive"})

# 2. File Integrity Monitor (FIM)
FIM_ACTIVE = False
FIM_THREAD = None
FIM_TARGET_FILE = ""
FIM_TARGET_HASH = ""

def fim_listener():
    global FIM_ACTIVE, FIM_TARGET_FILE, FIM_TARGET_HASH
    import time
    while FIM_ACTIVE:
        if FIM_TARGET_FILE and os.path.exists(FIM_TARGET_FILE):
            try:
                with open(FIM_TARGET_FILE, 'rb') as f:
                    current_hash = hashlib.sha256(f.read()).hexdigest()
                if current_hash != FIM_TARGET_HASH:
                    with app.app_context():
                        add_audit_log("⚠️ اختراق تكامل الملفات (FIM)", f"تم رصد تغيير في الملف المراقب: {FIM_TARGET_FILE}")
                    FIM_TARGET_HASH = current_hash # Update to prevent spam
            except Exception:
                pass
        time.sleep(5)

@app.route('/api/defense/fim', methods=['POST'])
def toggle_fim():
    global FIM_ACTIVE, FIM_THREAD, FIM_TARGET_FILE, FIM_TARGET_HASH
    data = request.json or {}
    action = data.get('action')
    
    if action == 'start':
        target = data.get('target', '')
        if not os.path.exists(target):
            return jsonify({"error": "الملف غير موجود!"}), 400
        
        try:
            with open(target, 'rb') as f:
                FIM_TARGET_HASH = hashlib.sha256(f.read()).hexdigest()
            FIM_TARGET_FILE = target
            FIM_ACTIVE = True
            FIM_THREAD = threading.Thread(target=fim_listener, daemon=True)
            FIM_THREAD.start()
            add_audit_log("تفعيل مراقب التكامل (FIM)", f"بدأت مراقبة الملف: {os.path.basename(target)}")
            return jsonify({"status": "active"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        FIM_ACTIVE = False
        add_audit_log("إيقاف مراقب التكامل", "تم إيقاف المراقبة")
        return jsonify({"status": "inactive"})

# 3. Secure Comms: P2P Burn Chat
# In-memory only storage. Structure: { "room_id": [ {"sender": "A", "msg": "hello", "timestamp": ...} ] }
BURN_CHAT_ROOMS = {}

@app.route('/api/chat/send', methods=['POST'])
def chat_send():
    data = request.json or {}
    room_id = data.get('room_id')
    sender = data.get('sender', 'Anonymous')
    msg = data.get('msg', '')
    
    if not room_id or not msg:
        return jsonify({"error": "بيانات مفقودة"}), 400
        
    if room_id not in BURN_CHAT_ROOMS:
        BURN_CHAT_ROOMS[room_id] = []
        
    BURN_CHAT_ROOMS[room_id].append({"sender": sender, "msg": msg})
    return jsonify({"success": True})

@app.route('/api/chat/receive', methods=['GET'])
def chat_receive():
    room_id = request.args.get('room_id')
    requester = request.args.get('requester', '')
    
    if not room_id or room_id not in BURN_CHAT_ROOMS:
        return jsonify({"messages": []})
        
    messages = BURN_CHAT_ROOMS[room_id]
    to_deliver = []
    remaining = []
    
    # Only deliver messages NOT sent by the requester, and burn them after reading
    for m in messages:
        if m['sender'] != requester:
            to_deliver.append(m)
        else:
            remaining.append(m)
            
    BURN_CHAT_ROOMS[room_id] = remaining
    
    if to_deliver:
        add_audit_log("Burn Chat 🔥", f"تم قراءة وتدمير {len(to_deliver)} رسالة سرية في الغرفة [{room_id}]")
        
    return jsonify({"messages": to_deliver})


# =====================================================================
# === الميزات الجديدة – Phase 6 ===
# =====================================================================

# --- QR Code مشفر ---
@app.route('/api/qr/generate', methods=['POST'])
def qr_generate():
    try:
        data = request.json or {}
        text = data.get('text', '')
        password = data.get('password', '')
        if not text: return jsonify({'error': 'النص مطلوب'}), 400

        # تشفير النص إذا وُجدت كلمة سر
        if password:
            salt = os.urandom(16)
            key = derive_key(password, salt)
            f = Fernet(key)
            payload = base64.urlsafe_b64encode(salt + f.encrypt(text.encode())).decode()
            payload = 'ENC:' + payload
        else:
            payload = text

        # توليد QR
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buf = io.BytesIO()
        img.save(buf, 'PNG')
        img_b64 = base64.b64encode(buf.getvalue()).decode()
        add_audit_log("QR Code 🔳", f"تم توليد QR {'مشفر' if password else 'عادي'}")
        return jsonify({'qr': img_b64, 'encrypted': bool(password)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/qr/decode', methods=['POST'])
def qr_decode():
    try:
        password = request.form.get('password', '')
        file = request.files.get('file')
        if not file: return jsonify({'error': 'الصورة مطلوبة'}), 400

        from PIL import Image as PILImage # type: ignore
        _pyzbar = None
        try:
            from pyzbar import pyzbar as _pyzbar
            _use_pyzbar = True
        except ImportError:
            _use_pyzbar = False
        img = PILImage.open(file.stream)
        if _use_pyzbar and _pyzbar is not None:
            decoded = _pyzbar.decode(img)
        else:
            # fallback: use qrcode detector via PIL color scan
            import importlib
            cv2 = importlib.import_module('cv2')
            np = importlib.import_module('numpy')
            img_np = np.array(img.convert('RGB'))
            detector = cv2.QRCodeDetector()
            val, _, _ = detector.detectAndDecode(img_np)
            decoded = [type('obj', (object,), {'data': val.encode()})() ] if val else []
        if not decoded: return jsonify({'error': 'لم يتم التعرف على QR في الصورة'}), 400

        first_decoded = decoded[0]
        raw_payload = getattr(first_decoded, 'data', b'')
        payload = raw_payload.decode('utf-8') if isinstance(raw_payload, (bytes, bytearray)) else str(raw_payload)
        if payload.startswith('ENC:') and password:
            raw = base64.urlsafe_b64decode(payload[4:])
            salt = raw[:16] # type: ignore
            enc = raw[16:] # type: ignore
            key = derive_key(password, salt)
            f = Fernet(key)
            text = f.decrypt(enc).decode('utf-8')
        else:
            text = payload
        return jsonify({'text': text})
    except Exception as e:
        error_msg = str(e)
        if "InvalidToken" in str(type(e)) or not error_msg:
            error_msg = "كلمة السر خاطئة أو رمز QR تالف"
        return jsonify({'error': error_msg}), 400


# --- Packet Sniffer ---
@app.route('/api/network/sniff', methods=['GET'])
def packet_sniff():
    try:
        import socket as _socket
        duration = int(request.args.get('duration', 4))
        packets_info = []
        stop_event = threading.Event()

        # Simple raw socket sniffer (works without scapy on Windows with admin)
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_RAW, _socket.IPPROTO_IP)
            local_ip = _socket.gethostbyname(_socket.gethostname())
            s.bind((local_ip, 0))
            s.setsockopt(_socket.IPPROTO_IP, _socket.IP_HDRINCL, 1)
            # Windows: enable promiscuous
            try: s.ioctl(_socket.SIO_RCVALL, _socket.RCVALL_ON) # type: ignore
            except Exception: pass
            s.settimeout(0.5)

            import time
            start = time.time()
            while time.time() - start < duration and len(packets_info) < 30:
                try:
                    raw, addr = s.recvfrom(65535)
                    # Parse IP header (first 20 bytes)
                    ip_header = raw[:20] # type: ignore
                    iph = ip_header
                    proto = iph[9]
                    src_ip = '.'.join(str(b) for b in iph[12:16])
                    dst_ip = '.'.join(str(b) for b in iph[16:20])
                    proto_name = {1: 'ICMP', 6: 'TCP', 17: 'UDP'}.get(proto, f'IP({proto})')
                    packets_info.append({
                        'src': src_ip, 'dst': dst_ip,
                        'proto': proto_name, 'size': len(raw)
                    })
                except _socket.timeout:
                    continue
            try: s.ioctl(_socket.SIO_RCVALL, _socket.RCVALL_OFF) # type: ignore
            except Exception: pass
            s.close()
            add_audit_log("Packet Sniffer 📡", f"تم التقاط {len(packets_info)} حزمة")
        except PermissionError:
            return jsonify({'error': 'يحتاج صلاحية Administrator – شغّل البرنامج كمسؤول', 'packets': []}), 403
        return jsonify({'packets': packets_info})
    except Exception as e:
        return jsonify({'error': str(e), 'packets': []}), 500

# --- تحسين الهوية الوهمية ---
@app.route('/api/fake-identity', methods=['GET'])
def fake_identity_route():
    try:
        from faker import Faker  # type: ignore
        import datetime

        lang = request.args.get('lang', 'ar_SA')

        # قائمة اللغات المدعومة
        SUPPORTED_LANGS = {
            'en_US': 'en_US', 'en_GB': 'en_GB',
            'ar_SA': 'ar_SA', 'ar_AA': 'ar_AA',
            'ar_JO': 'ar_AA',  # Faker لا يدعم ar_JO بشكل رسمي — نستخدم ar_AA كبديل
            'fr_FR': 'fr_FR', 'de_DE': 'de_DE', 'es_ES': 'es_ES',
            'tr_TR': 'tr_TR', 'ru_RU': 'ru_RU', 'zh_CN': 'zh_CN',
        }
        faker_lang = SUPPORTED_LANGS.get(lang, 'ar_AA')
        
        try:
            fake = Faker(faker_lang)
        except Exception:
            fake = Faker('ar_AA')
        
        fake_en = Faker('en_US')

        username_base = fake_en.user_name()
        password_fake = fake_en.password(length=12, special_chars=True)
        dob = fake_en.date_of_birth(minimum_age=18, maximum_age=60)
        age = (datetime.date.today() - dob).days // 365

        zodiac_signs = [(120,"الجدي"), (219,"الدلو"), (320,"الحوت"), (420,"الحمل"), (521,"الثور"), (621,"الجوزاء"), (722,"السرطان"), (822,"الأسد"), (922,"العذراء"), (1022,"الميزان"), (1121,"العقرب"), (1221,"القوس"), (1231,"الجدي")]
        day_of_year = dob.month * 100 + dob.day
        zodiac = next(z for d, z in zodiac_signs if day_of_year <= d)

        # --- 1. تحديد الجنس أولاً بشكل صريح ---
        gender_code = random.choice(['male', 'female'])
        gender = 'ذكر / Male' if gender_code == 'male' else 'أنثى / Female'

        # --- 2. توليد الاسم والبيانات حسب اللغة والجنس ---
        if lang == 'ar_JO':
            # رقم وطني أردني: 10 أرقام يبدأ بـ 2
            national_id = '2' + ''.join([str(random.randint(0,9)) for _ in range(9)])
            country_code = '+962'
            city_options = ["عمّان", "الزرقاء", "إربد", "العقبة", "المفرق", "الكرك", "معان", "جرش", "السلط", "مادبا", "عجلون"]
            address_str = f"{random.choice(city_options)}، الأردن، شارع {fake_en.street_name()}"
            zip_code = str(random.randint(10000, 99999))
            
            # قوائم أسماء أردنية محسنة
            male_first = ["محمد", "أحمد", "خالد", "عمر", "يوسف", "علي", "حسن", "ماجد", "فيصل", "سامي", "ليث", "زيد", "يزن", "حمزة", "عبد الله"]
            female_first = ["فاطمة", "مريم", "سارة", "نور", "لينا", "رنا", "دانا", "هند", "أمل", "لمى", "رهف", "تالا", "جنى", "سلمى", "ليان"]
            last_names = ["العبدلي", "الخطيب", "القضاة", "الزيود", "الشرايري", "الطراونة", "البطاينة", "الحجاوي", "العساف", "المجالي", "العدوان", "الفايز", "الروسان", "الخصاونة", "العبادي"]
            
            first_name = random.choice(male_first if gender_code == 'male' else female_first)
            last_name = random.choice(last_names)
            full_name = f"{first_name} {last_name}"
            
            mother_first = random.choice(female_first)
            mother_name = f"{mother_first} {random.choice(last_names)}"
            phone = f"+962 7{random.choice(['7','8','9'])}{random.randint(0,9)} {random.randint(100,999)} {random.randint(1000,9999)}"
            
            try: company = fake.company()
            except Exception: company = fake_en.company()
            try: job = fake.job()
            except Exception: job = fake_en.job()
            
        else:
            national_id = ''.join([str(random.randint(0,9)) for _ in range(10)])
            try: country_code = fake.country_calling_code()
            except Exception: country_code = fake_en.country_calling_code()
            try: address_str = fake.address().replace('\n', '، ')
            except Exception: address_str = fake_en.address().replace('\n', '، ')
            try: zip_code = fake.postcode()
            except Exception: zip_code = fake_en.postcode()
            
            # توليد الاسم بناءً على الجنس المحدد لكل اللغات
            try:
                if gender_code == 'male':
                    full_name = fake.name_male()
                else:
                    full_name = fake.name_female()
            except Exception:
                # Fallback to English but keep gender
                if gender_code == 'male':
                    full_name = fake_en.name_male()
                else:
                    full_name = fake_en.name_female()

            try:
                mother_name = fake.first_name_female() + ' ' + fake.last_name()
            except Exception:
                mother_name = fake_en.first_name_female() + ' ' + fake_en.last_name()
                
            try: phone = fake.phone_number()
            except Exception: phone = fake_en.phone_number()
            try: company = fake.company()
            except Exception: company = fake_en.company()
            try: job = fake.job()
            except Exception: job = fake_en.job()

        # color_name قد يفشل مع بعض اللغات
        try:
            color = fake.color_name()
        except Exception:
            color = fake_en.color_name()

        return jsonify({
            'name': full_name,
            'gender': gender,
            'mother_name': mother_name,
            'birthdate': dob.strftime('%Y-%m-%d'),
            'age': age,
            'zodiac': zodiac,
            'national_id': national_id,

            'address': address_str,
            'zip_code': zip_code,
            'geo': f"{fake_en.latitude()}, {fake_en.longitude()}",
            'country_code': country_code,

            'phone': phone,
            'email': fake_en.email(),
            'company': company,
            'job': job,

            'height': f"{random.randint(150, 195)} cm",
            'weight': f"{random.randint(50, 100)} kg",
            'blood_type': random.choice(["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]),
            'color': color,
            'vehicle': fake_en.word().title() + ' ' + str(random.randint(2000, 2024)),

            'cc_type': fake_en.credit_card_provider(),
            'credit_card': fake_en.credit_card_number(card_type='visa' if random.random() > 0.5 else 'mastercard'),
            'cc_expire': fake_en.credit_card_expire(),
            'cc_cvv': fake_en.credit_card_security_code(),

            'username': username_base,
            'password': password_fake,
            'website': f'https://www.{fake_en.domain_name()}',
            'user_agent': fake_en.user_agent(),
            'uuid': fake_en.uuid4(),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- Dashboard / System Stats ---
@app.route('/api/dashboard/stats', methods=['GET'])
def dashboard_stats():
    global _dash_prev_net, _dash_prev_ts, _dash_prev_disk_io, _dash_prev_disk_io_ts, _dash_cpu_primed
    try:
        if not _dash_cpu_primed:
            psutil.cpu_percent(interval=None)
            _dash_cpu_primed = True
        cpu = psutil.cpu_percent(interval=0.2)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        net = psutil.net_io_counters()
        disk_io = psutil.disk_io_counters()
        local_ip = _dash_local_ip()
        public_ip = _dash_public_ip_cached()

        now_ts = time.time()
        up_kbps = 0.0
        down_kbps = 0.0
        disk_io_kbps = 0.0
        with _dash_metrics_lock:
            if _dash_prev_net is not None and _dash_prev_ts > 0:
                dt = max(now_ts - _dash_prev_ts, 1e-6)
                up_kbps = ((net.bytes_sent - _dash_prev_net.bytes_sent) / 1024.0) / dt
                down_kbps = ((net.bytes_recv - _dash_prev_net.bytes_recv) / 1024.0) / dt
            _dash_prev_net = net
            _dash_prev_ts = now_ts

            if disk_io is not None and _dash_prev_disk_io is not None and _dash_prev_disk_io_ts > 0:
                dt_disk = max(now_ts - _dash_prev_disk_io_ts, 1e-6)
                total_delta = (disk_io.read_bytes - _dash_prev_disk_io.read_bytes) + (disk_io.write_bytes - _dash_prev_disk_io.write_bytes)
                disk_io_kbps = (total_delta / 1024.0) / dt_disk
            if disk_io is not None:
                _dash_prev_disk_io = disk_io
                _dash_prev_disk_io_ts = now_ts

        up_kbps = max(up_kbps, 0.0)
        down_kbps = max(down_kbps, 0.0)
        disk_io_kbps = max(disk_io_kbps, 0.0)

        response = jsonify({
            'cpu_percent': cpu,
            'ram_used_gb': round(mem.used / 1024**3, 2),
            'ram_total_gb': round(mem.total / 1024**3, 2),
            'ram_percent': mem.percent,
            'disk_used_gb': round(disk.used / 1024**3, 2),
            'disk_total_gb': round(disk.total / 1024**3, 2),
            'disk_percent': disk.percent,
            'disk_io_kbps': round(disk_io_kbps, 2),
            'net_sent_mb': round(net.bytes_sent / 1024**2, 2),
            'net_recv_mb': round(net.bytes_recv / 1024**2, 2),
            'net_up_kbps': round(up_kbps, 2),
            'net_down_kbps': round(down_kbps, 2),
            'local_ip': local_ip,
            'public_ip': public_ip,
            'vault_items': 0,
            'burn_notes': len(BURN_NOTES),
            'audit_count': len(AUDIT_LOGS),
            'recent_logs': AUDIT_LOGS[:5], # type: ignore
            'measured_at': datetime.datetime.now().strftime('%H:%M:%S'),
        })
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        err = jsonify({'error': str(e)})
        err.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        err.headers['Pragma'] = 'no-cache'
        err.headers['Expires'] = '0'
        return err, 500



# =====================================================================
# === Authentication Routes ===
# =====================================================================

def _get_login_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()


def _get_country(ip):
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=countryCode", timeout=4)
        return r.json().get('countryCode', '')
    except Exception:
        return ''


@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    email = data.get('email', '').strip()
    accepted_terms = bool(data.get('accepted_terms', False))

    if not username or not password or not email:
        return jsonify({"error": "اسم المستخدم وكلمة السر والإيميل مطلوبان"}), 400
    if len(username) < 3:
        return jsonify({"error": "اسم المستخدم يجب أن يكون 3 أحرف على الأقل"}), 400
    if len(password) < 6:
        return jsonify({"error": "كلمة السر يجب أن تكون 6 أحرف على الأقل"}), 400
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({"error": "البريد الإلكتروني غير صالح"}), 400
    if not accepted_terms:
        return jsonify({"error": "يجب الموافقة على الشروط والأحكام أولاً"}), 400

    pw_hash = hash_password(password)
    otp_code = "".join(random.choices(string.digits, k=6))
    created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ip = _get_login_ip()

    conn = None
    max_retries = 3
    retry_count = 0
    while retry_count < max_retries:
        try:
            conn = get_db_conn()
            c = conn.cursor()
            
            # --- فحص منع تكرار الإيميل (Duplicate Email Check) ---
            c.execute("SELECT id FROM users WHERE email = %s", (email,))
            if c.fetchone():
                return jsonify({"error": "البريد الإلكتروني مسجل مسبقاً بحساب آخر"}), 409
                
            # Perform insertion
            c.execute("INSERT INTO users (username, password_hash, email, otp_code, is_verified, created_at) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                      (username, pw_hash, email, otp_code, 0, created_at))
            c.fetchone()
            
            conn.commit()
            
            # Email and Audit
            add_audit_log("تسجيل مستخدم جديد", f"تم إنشاء حساب: {username}", ip=ip, username=username)
            send_otp_email(email, otp_code)
            
            return jsonify({"success": True, "message": "تم إنشاء الحساب! يرجى التحقق من بريدك الإلكتروني.",
                            "username": username})
        except psycopg2.errors.UniqueViolation:
            if conn: conn.rollback()
            return jsonify({"error": "اسم المستخدم أو البريد الإلكتروني مسجل مسبقاً، اختر اسماً آخر"}), 409
        except Exception as e:
            import traceback
            if conn: conn.rollback()
            print(f"[TITAN] Register error: {e}")
            print(traceback.format_exc())
            return jsonify({"error": "فشل إنشاء الحساب، حاول مجدداً"}), 500
        finally:
            if conn:
                conn.close()
    
    return jsonify({"error": "قاعدة البيانات مشغولة حالياً، يرجى المحاولة لاحقاً"}), 503

@app.route('/api/auth/verify', methods=['POST'])
def auth_verify():
    data = request.json or {}
    username = data.get('username', '').strip()
    otp = data.get('otp', '').strip()

    if not username or not otp:
        return jsonify({"error": "اسم المستخدم وكود التحقق مطلوبان"}), 400

    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT otp_code FROM users WHERE username = %s", (username,))
        row = c.fetchone()
        
        if row and row[0] == otp:
            c.execute("UPDATE users SET is_verified = 1, otp_code = NULL WHERE username = %s", (username,))
            conn.commit()
            # تسجيل دخول تلقائي بعد التحقق
            c.execute("SELECT id FROM users WHERE username = %s", (username,))
            user_row = c.fetchone()
            if user_row:
                session.permanent = True
                session['user_id'] = user_row[0]
                session['username'] = username
            add_audit_log("تفعيل الحساب ✅", f"تم تفعيل حساب المستخدم: {username}")
            return jsonify({"success": True, "message": "تم تفعيل الحساب بنجاح!", "auto_login": True})
        else:
            return jsonify({"error": "كود التحقق غير صحيح"}), 401
    except Exception as e:
        print(f"[TITAN] Verify error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    ip = _get_login_ip()
    ua = request.headers.get('User-Agent', '')[:255]

    if not username or not password:
        return jsonify({"error": "اسم المستخدم وكلمة السر مطلوبان"}), 400

    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT id, password_hash, is_verified, email, failed_attempts, lockout_until, last_user_agent, last_country FROM users WHERE username = %s", (username,))
        row = c.fetchone()

        if not row:
            add_audit_log("محاولة دخول فاشلة", f"مستخدم غير موجود: {username}", ip=ip)
            return jsonify({"error": "اسم المستخدم أو كلمة السر غير صحيحة"}), 401

        user_id, pw_hash, is_verified, email, failed_attempts, lockout_until, last_ua, last_country = row

        # --- فحص الحظر (Account Lockout) ---
        if lockout_until:
            lo_dt = datetime.datetime.fromisoformat(lockout_until)
            if datetime.datetime.now() < lo_dt:
                remaining = int((lo_dt - datetime.datetime.now()).total_seconds() // 60) + 1
                return jsonify({"error": "ACCOUNT_LOCKED",
                                "message": f"الحساب مقفل. حاول مجدداً بعد {remaining} دقيقة.",
                                "minutes": remaining}), 429

        if not verify_password(password, pw_hash):
            failed_attempts = (failed_attempts or 0) + 1
            lockout = None
            if failed_attempts >= 3:
                lockout = (datetime.datetime.now() + datetime.timedelta(minutes=30)).isoformat()
                add_audit_log("قفل الحساب", f"تم قفل حساب: {username} بعد 3 محاولات فاشلة", ip=ip, username=username)
            c.execute("UPDATE users SET failed_attempts=%s, lockout_until=%s WHERE id=%s", (failed_attempts, lockout, user_id))
            conn.commit()
            add_audit_log("محاولة دخول فاشلة", f"كلمة سر خاطئة لـ: {username} (محاولة {failed_attempts}/3)", ip=ip, username=username)
            remaining_attempts = max(0, 3 - failed_attempts)
            return jsonify({"error": "اسم المستخدم أو كلمة السر غير صحيحة",
                            "remaining_attempts": remaining_attempts}), 401

        if not is_verified:
            return jsonify({"error": "EMAIL_NOT_VERIFIED", "message": "يرجى تفعيل حسابك أولاً", "username": username}), 403

        # --- نجح الدخول: تصفير المحاولات الفاشلة ---
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        current_country = _get_country(ip)
        c.execute("UPDATE users SET failed_attempts=0, lockout_until=NULL, last_user_agent=%s, last_login_ip=%s, last_login_at=%s, last_country=%s WHERE id=%s",
                  (ua, ip, now_str, current_country, user_id))

        # --- إنشاء رمز جلسة (Session Token) ---
        session_token = secrets.token_hex(32)
        c.execute("INSERT INTO active_sessions (user_id, token, user_agent, ip, country, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                  (user_id, session_token, ua, ip, current_country, now_str))
        conn.commit()

        session['user_id'] = user_id
        session['username'] = username
        session['token'] = session_token
        session.permanent = True

        # --- تنبيهات الأمان (في الخلفية) ---
        add_audit_log("تسجيل دخول", f"دخول ناجح: {username}", ip=ip, username=username)
        send_login_alert_email(username, ip, ua)

        is_new_device = last_ua and ua != last_ua
        if is_new_device and email:
            send_new_device_alert(username, ip, ua, email)

        if last_country and current_country and current_country != last_country and email:
            send_geo_fence_alert(username, ip, last_country, current_country, email)

        c.execute("SELECT is_admin FROM users WHERE id = %s", (user_id,))
        admin_row = c.fetchone()
        is_admin_flag = bool(admin_row and admin_row[0])

        return jsonify({"success": True, "username": username,
                        "isAdmin": is_admin_flag,
                        "new_device": bool(is_new_device),
                        "geo_alert": bool(last_country and current_country and current_country != last_country)})
    except Exception as e:
        print(f"[TITAN] Login error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    username = session.get('username', 'Unknown')
    token = session.get('token')
    if token:
        conn = None
        try:
            conn = get_db_conn()
            _cur = conn.cursor()
            _cur.execute("DELETE FROM active_sessions WHERE token=%s", (token,))
            conn.commit()
        except Exception as e:
            print(f"[TITAN] Logout error: {e}")
        finally:
            if conn:
                conn.close()
    session.clear()
    add_audit_log("تسجيل خروج", f"خروج: {username}")
    return jsonify({"success": True})

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    if 'user_id' in session:
        user_id = session['user_id']
        conn = get_db_conn()
        _cur = conn.cursor()
        _cur.execute("SELECT is_admin FROM users WHERE id = %s", (user_id,))
        res = _cur.fetchone()
        is_admin_flag = bool(res[0]) if res else False
        conn.close()
        return jsonify({"loggedIn": True, "username": session.get('username', ''), "isAdmin": is_admin_flag})
    return jsonify({"loggedIn": False})

@app.route('/api/auth/heartbeat', methods=['POST'])
def auth_heartbeat():
    """يُجدد الجلسة – يُستدعى من الواجهة كل 5 دقائق"""
    if 'user_id' not in session:
        return jsonify({"loggedIn": False}), 401
    session.modified = True
    return jsonify({"loggedIn": True})

# --- نسيت كلمة السر (Forgot Password) ---
# تخزين مؤقت للأكواد: {username: {otp, expires_at}}
_FORGOT_OTP_STORE = {}

@app.route('/api/auth/forgot-password/send', methods=['POST'])
def forgot_password_send():
    """إرسال كود التحقق على إيميل المستخدم"""
    data = request.json or {}
    username = data.get('username', '').strip()
    if not username:
        return jsonify({"error": "اسم المستخدم مطلوب"}), 400
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT id, email, is_verified FROM users WHERE username = %s", (username,))
        row = c.fetchone()
        if not row:
            # نعطي نفس الرد حتى لا نكشف وجود المستخدمين
            return jsonify({"success": True, "message": "إذا كان الحساب موجوداً سيصل الكود."}), 200
        user_id, email, is_verified = row
        if not email:
            return jsonify({"error": "لا يوجد بريد إلكتروني مسجّل لهذا الحساب."}), 400
        # توليد كود 6 أرقام
        otp = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
        expires_at = datetime.datetime.now() + datetime.timedelta(minutes=10)
        _FORGOT_OTP_STORE[username] = {"otp": otp, "expires_at": expires_at}
        # إرسال الكود
        msg = MIMEText(f"""
مرحباً {username}،

طُلب استعادة كلمة السر لحسابك في TITAN.

كود التحقق الخاص بك هو: {otp}

هذا الكود صالح لمدة 10 دقائق فقط.

إذا لم تطلب ذلك، تجاهل هذا البريد.
— فريق TITAN Security
""", 'plain', 'utf-8')
        try:
            _resend_send(email, "TITAN - كود استعادة كلمة السر", f"""
مرحباً {username}،

طُلب استعادة كلمة السر لحسابك في TITAN.

كود التحقق الخاص بك هو: {otp}

هذا الكود صالح لمدة 10 دقائق فقط.

إذا لم تطلب ذلك، تجاهل هذا البريد.
— فريق TITAN Security
""")
        except Exception as e:
            print(f"[TITAN] Forgot password email error: {e}")
            return jsonify({"error": "فشل إرسال البريد الإلكتروني."}), 500
        add_audit_log("طلب استعادة كلمة السر", f"تم إرسال كود لـ: {username}", username=username)
        return jsonify({"success": True})
    except Exception as e:
        print(f"[TITAN] Forgot password send error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/auth/forgot-password/verify', methods=['POST'])
def forgot_password_verify():
    """التحقق من كود إعادة تعيين كلمة السر"""
    data = request.json or {}
    username = data.get('username', '').strip()
    otp = data.get('otp', '').strip()
    if not username or not otp:
        return jsonify({"error": "البيانات ناقصة"}), 400
    stored = _FORGOT_OTP_STORE.get(username)
    if not stored:
        return jsonify({"error": "لم يتم إرسال كود. يرجى طلب كود جديد."}), 400
    if datetime.datetime.now() > stored["expires_at"]:
        del _FORGOT_OTP_STORE[username]
        return jsonify({"error": "انتهت صلاحية الكود. يرجى طلب كود جديد."}), 400
    if otp != stored["otp"]:
        return jsonify({"error": "الكود غير صحيح."}), 400
    return jsonify({"success": True})

@app.route('/api/auth/forgot-password/reset', methods=['POST'])
def forgot_password_reset():
    """إعادة تعيين كلمة السر بعد التحقق من الكود"""
    data = request.json or {}
    username = data.get('username', '').strip()
    otp = data.get('otp', '').strip()
    new_password = data.get('new_password', '')
    if not username or not otp or not new_password:
        return jsonify({"error": "البيانات ناقصة"}), 400
    if len(new_password) < 6:
        return jsonify({"error": "كلمة السر قصيرة جداً (6 أحرف على الأقل)"}), 400
    stored = _FORGOT_OTP_STORE.get(username)
    if not stored:
        return jsonify({"error": "يرجى إعادة طلب كود التحقق."}), 400
    if datetime.datetime.now() > stored["expires_at"]:
        del _FORGOT_OTP_STORE[username]
        return jsonify({"error": "انتهت صلاحية الكود."}), 400
    if otp != stored["otp"]:
        return jsonify({"error": "الكود غير صحيح."}), 400
    conn = None
    try:
        conn = get_db_conn()
        new_hash = hash_password(new_password)
        _cur = conn.cursor()
        _cur.execute("UPDATE users SET password_hash=%s, failed_attempts=0, lockout_until=NULL WHERE username=%s",
                     (new_hash, username))
        conn.commit()
        del _FORGOT_OTP_STORE[username]
        add_audit_log("تغيير كلمة السر ✅", f"تم تغيير كلمة سر: {username}", username=username)
        return jsonify({"success": True})
    except Exception as e:
        print(f"[TITAN] Forgot password reset error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/auth/sessions', methods=['GET'])
def auth_sessions():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT id, user_agent, ip, country, created_at FROM active_sessions WHERE user_id=%s ORDER BY created_at DESC", (session['user_id'],))
        rows = c.fetchall()
        sessions = [{"id": r[0], "user_agent": r[1][:80], "ip": r[2], "country": r[3], "created_at": r[4]} for r in rows]
        return jsonify({"sessions": sessions})
    except Exception as e:
        print(f"[TITAN] Session list error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/auth/sessions/revoke', methods=['POST'])
def auth_sessions_revoke():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    data = request.json or {}
    revoke_all = data.get('all', False)
    session_id = data.get('session_id')
    conn = None
    try:
        conn = get_db_conn()
        if revoke_all:
            _cur = conn.cursor()
            _cur.execute("DELETE FROM active_sessions WHERE user_id=%s", (session['user_id'],))
            session.clear()
        elif session_id:
            _cur = conn.cursor()
            _cur.execute("DELETE FROM active_sessions WHERE id=%s AND user_id=%s", (session_id, session['user_id']))
        conn.commit()
        add_audit_log("إلغاء جلسات", f"أُلغيت الجلسات لـ: {session.get('username','')}", username=session.get('username',''))
        return jsonify({"success": True})
    except Exception as e:
        print(f"[TITAN] Session revoke error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()


# =====================================================================
# === New Security Feature Routes ===
# =====================================================================

# --- Canary Honeypot ---
@app.route('/passwords.txt', methods=['GET'])
def canary_trap():
    """ملف شرك يُنبّه عند أي وصول"""
    ip = _get_login_ip()
    ua = request.headers.get('User-Agent', '')
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = None
    try:
        conn = get_db_conn()
        _cur = conn.cursor()
        _cur.execute("INSERT INTO canary_log (time, ip, user_agent) VALUES (%s,%s,%s)", (now, ip, ua[:255]))
        conn.commit()
    except Exception as e:
        print(f"[TITAN] Canary DB error: {e}")
    finally:
        if conn:
            conn.close()
    add_audit_log("CANARY TRIGGERED!", f"وصول للملف الشرك من IP: {ip}", ip=ip)
    send_canary_alert(ip, ua)
    # نُعيد محتوى وهمي
    return "Access Denied", 403

@app.route('/api/canary/status', methods=['GET'])
def canary_status():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT time, ip, user_agent FROM canary_log ORDER BY id DESC LIMIT 10")
        rows = c.fetchall()
        return jsonify({"accesses": [{"time": r[0], "ip": r[1], "ua": r[2][:60]} for r in rows]})
    except Exception as e:
        print(f"[TITAN] Canary status error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

# --- System Integrity Check ---
@app.route('/api/security/integrity', methods=['GET'])
def security_integrity():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    app_path = os.path.abspath(__file__)
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT hash, set_at FROM integrity_baseline WHERE file_path=%s", (app_path,))
        row = c.fetchone()
        if not row:
            return jsonify({"status": "unknown", "message": "لا يوجد baseline محفوظ"})
        stored_hash, set_at = row
        with open(app_path, 'rb') as f:
            current_hash = hashlib.sha256(f.read()).hexdigest()
        intact = (current_hash == stored_hash)
        if not intact:
            add_audit_log("INTEGRITY BREACH!", "تم اكتشاف تغيير في ملف app.py!")
        return jsonify({
            "status": "ok" if intact else "BREACH",
            "intact": intact,
            "baseline_set": set_at,
            "message": "سلامة النظام مؤكدة ✅" if intact else "تحذير: تم اكتشاف تعديل في ملف النظام! 🚨"
        })
    except Exception as e:
        print(f"[TITAN] Integrity check error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/security/integrity/reset', methods=['POST'])
def security_integrity_reset():
    """إعادة تعيين baseline بعد تحديث مقصود"""
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    app_path = os.path.abspath(__file__)
    conn = None
    try:
        with open(app_path, 'rb') as f:
            new_hash = hashlib.sha256(f.read()).hexdigest()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db_conn()
        _cur = conn.cursor()
        _cur.execute("DELETE FROM integrity_baseline WHERE file_path=%s", (app_path,))
        _cur = conn.cursor()
        _cur.execute("INSERT INTO integrity_baseline (file_path, hash, set_at) VALUES (%s,%s,%s)", (app_path, new_hash, now))
        conn.commit()
        add_audit_log("Integrity Baseline Reset", f"تم إعادة تعيين baseline بواسطة: {session.get('username','')}")
        return jsonify({"success": True, "message": "تم تحديث baseline بنجاح"})
    except Exception as e:
        print(f"[TITAN] Integrity reset error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

# --- Panic Button (Nuke Option) ---
@app.route('/api/security/panic', methods=['POST'])
def security_panic():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    user_id = session['user_id']
    username = session.get('username', '')
    conn = None
    try:
        vault_file = get_vault_file(user_id)
        nuked = False
        if os.path.exists(vault_file):
            # نُشفّر الملف بمفتاح عشوائي ونحذف المفتاح فوراً
            random_key = Fernet.generate_key()
            f_obj = Fernet(random_key)
            with open(vault_file, 'rb') as vf:
                data = vf.read()
            with open(vault_file, 'wb') as vf:
                vf.write(f_obj.encrypt(data))
            del random_key, f_obj  # حذف المفتاح من الذاكرة
            nuked = True

        # مسح القبو الزمني للمستخدم
        conn = get_db_conn()
        _cur = conn.cursor()
        _cur.execute("DELETE FROM vault_timelocked WHERE user_id=%s", (user_id,))
        _cur = conn.cursor()
        _cur.execute("DELETE FROM active_sessions WHERE user_id=%s", (user_id,))
        conn.commit()

        session.clear()
        add_audit_log("PANIC BUTTON PRESSED", f"تم تفعيل زر الطوارئ بواسطة: {username}", username=username)
        _send_email_async("TITAN",
                          f"تم تفعيل زر الانتحار بواسطة المستخدم: {username}\nجميع بيانات القبو مشفرة ومكتاح محذوف.")
        return jsonify({"success": True, "nuked": nuked, "message": "تم تدمير البيانات بشكل آمن. تم تسجيل الخروج."})
    except Exception as e:
        print(f"[TITAN] Panic error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

# --- Security Logs API ---
@app.route('/api/security/logs', methods=['GET'])
def security_logs_api():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    limit = min(int(request.args.get('limit', 50)), 200)
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT time, action, details, ip, username FROM security_logs ORDER BY id DESC LIMIT %s", (limit,))
        rows = c.fetchall()
        logs = [{"time": r[0], "action": r[1], "details": r[2], "ip": r[3], "username": r[4]} for r in rows]
        return jsonify({"logs": logs})
    except Exception as e:
        print(f"[TITAN] Security logs error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

# --- Time-Locked Vault ---
@app.route('/api/vault/timelocked/upload', methods=['POST'])
def vault_timelocked_upload():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    vault_pass = request.form.get('vault_password', '')
    unlock_at = request.form.get('unlock_at', '')
    file = request.files.get('file')
    if not file or not vault_pass or not unlock_at:
        return jsonify({"error": "الملف وكلمة السر وتاريخ الفتح مطلوبة"}), 400
    try:
        datetime.datetime.fromisoformat(unlock_at)
    except ValueError:
        return jsonify({"error": "تنسيق التاريخ غير صالح"}), 400
    conn = None
    try:
        raw = file.read()
        enc = encrypt_data(raw, vault_pass)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("INSERT INTO vault_timelocked (user_id, filename, enc_data, unlock_at, created_at) VALUES (%s,%s,%s,%s,%s)",
                  (session['user_id'], secure_filename(file.filename or 'file.bin'), enc, unlock_at, now))
        conn.commit()
        add_audit_log("رفع ملف زمني", f"ملف: {file.filename} يُفتح في: {unlock_at}", username=session.get('username',''))
        return jsonify({"success": True, "message": f"تم تشفير الملف. يمكن فتحه بعد: {unlock_at}"})
    except Exception as e:
        print(f"[TITAN] Vault upload error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/vault/timelocked/list', methods=['GET'])
def vault_timelocked_list():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT id, filename, unlock_at, created_at FROM vault_timelocked WHERE user_id=%s ORDER BY unlock_at", (session['user_id'],))
        rows = c.fetchall()
        now = datetime.datetime.now()
        files = []
        for r in rows:
            unlock_dt = datetime.datetime.fromisoformat(r[2])
            locked = now < unlock_dt
            seconds_left = max(0, int((unlock_dt - now).total_seconds()))
            files.append({"id": r[0], "filename": r[1], "unlock_at": r[2], "created_at": r[3], "locked": locked, "seconds_left": seconds_left})
        return jsonify({"files": files})
    except Exception as e:
        print(f"[TITAN] Vault list error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/vault/timelocked/download', methods=['POST'])
def vault_timelocked_download():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    data = request.json or {}
    file_id = data.get('id')
    vault_pass = data.get('vault_password', '')
    if not file_id or not vault_pass:
        return jsonify({"error": "البيانات ناقصة"}), 400
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT filename, enc_data, unlock_at FROM vault_timelocked WHERE id=%s AND user_id=%s", (file_id, session['user_id']))
        row = c.fetchone()
        if not row:
            return jsonify({"error": "الملف غير موجود"}), 404
        filename, enc_data, unlock_at = row
        unlock_dt = datetime.datetime.fromisoformat(unlock_at)
        if datetime.datetime.now() < unlock_dt:
            seconds_left = int((unlock_dt - datetime.datetime.now()).total_seconds())
            return jsonify({"error": "TIME_LOCKED", "seconds_left": seconds_left,
                            "message": f"الملف مقفل. يُفتح في: {unlock_at}"}), 403
        decrypted = decrypt_data(enc_data, vault_pass)
        buf = io.BytesIO(decrypted)
        buf.seek(0)
        add_audit_log("تحميل ملف زمني", f"تم تحميل: {filename}", username=session.get('username',''))
        return send_file(buf, as_attachment=True, download_name=filename)
    except ValueError:
        return jsonify({"error": "كلمة السر خاطئة أو الملف معطوب"}), 401
    except Exception as e:
        print(f"[TITAN] Vault download error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()





# =====================================================================
# === Advanced Crypto Lab Routes ===
# =====================================================================

@app.route('/api/adv/hidden-vault/create', methods=['POST'])
def adv_hidden_vault_create():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    data = request.json or {}
    label = (data.get('label') or '').strip() or 'vault'
    decoy_text = (data.get('decoy_text') or '').strip()
    hidden_text = (data.get('hidden_text') or '').strip()
    decoy_pass = data.get('decoy_pass') or ''
    hidden_pass = data.get('hidden_pass') or ''
    if not decoy_text or not hidden_text or not decoy_pass or not hidden_pass:
        return jsonify({"success": False, "error": "All fields are required"}), 400
    try:
        container = {
            "version": 1,
            "decoy": base64.b64encode(encrypt_data(decoy_text.encode('utf-8'), decoy_pass)).decode('ascii'),
            "hidden": base64.b64encode(encrypt_data(hidden_text.encode('utf-8'), hidden_pass)).decode('ascii')
        }
        conn = get_db_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO advanced_hidden_vaults (user_id, label, container_json, created_at) VALUES (%s, %s, %s, %s) RETURNING id",
            (user_id, label, json.dumps(container), datetime.datetime.now().isoformat())
        )
        row = c.fetchone()
        conn.commit()
        conn.close()
        add_audit_log("ADV Hidden Vault", f"created id={row[0] if row else '?'}", username=session.get('username', ''))
        return jsonify({"success": True, "vault_id": row[0] if row else None})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/adv/hidden-vault/list', methods=['GET'])
def adv_hidden_vault_list():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT id, label, created_at FROM advanced_hidden_vaults WHERE user_id=%s ORDER BY id DESC LIMIT 100", (user_id,))
    rows = c.fetchall()
    conn.close()
    return jsonify({"success": True, "vaults": [{"id": r[0], "label": r[1], "created_at": r[2]} for r in rows]})


@app.route('/api/adv/hidden-vault/open', methods=['POST'])
def adv_hidden_vault_open():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    data = request.json or {}
    vault_id = int(data.get('vault_id') or 0)
    password = data.get('password') or ''
    if not vault_id or not password:
        return jsonify({"success": False, "error": "vault_id/password required"}), 400
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT container_json FROM advanced_hidden_vaults WHERE id=%s AND user_id=%s", (vault_id, user_id))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({"success": False, "error": "Vault not found"}), 404
    container = json.loads(row[0])
    for name in ('decoy', 'hidden'):
        try:
            encrypted = base64.b64decode(container[name])
            plain = decrypt_data(encrypted, password).decode('utf-8')
            return jsonify({"success": True, "compartment": name, "text": plain})
        except Exception:
            pass
    return jsonify({"success": False, "error": "Wrong password"}), 401


@app.route('/api/adv/secret-sharing/split', methods=['POST'])
def adv_secret_split():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    data = request.json or {}
    secret = (data.get('secret') or '').strip()
    n = int(data.get('n') or 5)
    k = int(data.get('k') or 3)
    if not secret:
        return jsonify({"success": False, "error": "secret required"}), 400
    shares = split_secret_shares(secret, n=n, k=k)
    add_audit_log("ADV Secret Sharing", f"split n={n} k={k}", username=session.get('username', ''))
    return jsonify({"success": True, "shares": shares})


@app.route('/api/adv/secret-sharing/recover', methods=['POST'])
def adv_secret_recover():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    data = request.json or {}
    shares = data.get('shares') or []
    if not isinstance(shares, list):
        return jsonify({"success": False, "error": "shares must be array"}), 400
    try:
        secret = recover_secret_shares(shares)
        add_audit_log("ADV Secret Sharing", "recover", username=session.get('username', ''))
        return jsonify({"success": True, "secret": secret})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route('/api/adv/timelock/create', methods=['POST'])
def adv_timelock_create():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    data = request.json or {}
    message = (data.get('message') or '').strip()
    password = data.get('password') or ''
    unlock_minutes = max(1, int(data.get('unlock_minutes') or 10))
    one_time = 1 if data.get('one_time', True) else 0
    if not message or not password:
        return jsonify({"success": False, "error": "message/password required"}), 400
    token = secrets.token_urlsafe(24)
    unlock_at = (datetime.datetime.now() + datetime.timedelta(minutes=unlock_minutes)).isoformat()
    enc_payload = encrypt_data(message.encode('utf-8'), password)
    conn = get_db_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO advanced_timelock_messages (user_id, token, enc_payload, unlock_at, one_time_read, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
        (user_id, token, psycopg2.Binary(enc_payload), unlock_at, one_time, datetime.datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "token": token, "unlock_at": unlock_at})


@app.route('/api/adv/timelock/open', methods=['POST'])
def adv_timelock_open():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    data = request.json or {}
    token = (data.get('token') or '').strip()
    password = data.get('password') or ''
    if not token or not password:
        return jsonify({"success": False, "error": "token/password required"}), 400
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT id, enc_payload, unlock_at, one_time_read, is_used FROM advanced_timelock_messages WHERE token=%s AND user_id=%s", (token, user_id))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "token not found"}), 404
    msg_id, enc_payload, unlock_at, one_time_read, is_used = row
    if int(is_used or 0) == 1:
        conn.close()
        return jsonify({"success": False, "error": "token already consumed"}), 410
    if datetime.datetime.now() < datetime.datetime.fromisoformat(unlock_at):
        conn.close()
        return jsonify({"success": False, "error": "still locked", "unlock_at": unlock_at}), 403
    try:
        plain = decrypt_data(bytes(enc_payload), password).decode('utf-8')
    except Exception:
        conn.close()
        return jsonify({"success": False, "error": "wrong password"}), 401
    if int(one_time_read or 0) == 1:
        c.execute("UPDATE advanced_timelock_messages SET is_used=1 WHERE id=%s", (msg_id,))
        conn.commit()
    conn.close()
    return jsonify({"success": True, "message": plain, "one_time": bool(one_time_read)})


@app.route('/api/adv/policy/evaluate', methods=['POST'])
def adv_policy_evaluate():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    data = request.json or {}
    policy = data.get('policy') or {}
    otp = (data.get('otp') or '').strip()
    context = {
        "ip": request.remote_addr,
        "country": _get_country(request.remote_addr or ''),
        "otp": otp
    }
    result = evaluate_advanced_policy(policy, context)
    return jsonify({"success": True, "context": context, **result})


@app.route('/api/adv/watermark/sign', methods=['POST'])
def adv_watermark_sign():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    file = request.files.get('file')
    label = (request.form.get('label') or '').strip() or 'asset'
    if not file:
        return jsonify({"success": False, "error": "file required"}), 400
    data = file.read()
    wm = create_watermark_signature(data, label, user_id)
    return jsonify({"success": True, "label": label, **wm})


@app.route('/api/adv/watermark/verify', methods=['POST'])
def adv_watermark_verify():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    file = request.files.get('file')
    signature = (request.form.get('signature') or '').strip()
    label = (request.form.get('label') or '').strip() or 'asset'
    if not file or not signature:
        return jsonify({"success": False, "error": "file/signature required"}), 400
    data = file.read()
    file_hash = hashlib.sha256(data).hexdigest()
    raw_secret = app.secret_key or 'titan'
    secret = raw_secret if isinstance(raw_secret, (bytes, bytearray)) else str(raw_secret).encode('utf-8')
    expected = hashlib.sha256(secret + f"{user_id}|{label}|{file_hash}".encode('utf-8')).hexdigest()
    valid = signature == expected
    return jsonify({"success": True, "valid": valid, "file_hash": file_hash, "label": label})


@app.route('/api/adv/keyring/create', methods=['POST'])
def adv_keyring_create():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    data = request.json or {}
    key_name = (data.get('name') or '').strip() or f"key-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    key_material = Fernet.generate_key().decode('ascii')
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("INSERT INTO advanced_keyring (user_id, key_name, key_material, status, created_at) VALUES (%s,%s,%s,'active',%s) RETURNING id",
              (user_id, key_name, key_material, datetime.datetime.now().isoformat()))
    row = c.fetchone()
    conn.commit()
    conn.close()
    return jsonify({"success": True, "key_id": row[0] if row else None, "key_name": key_name})


@app.route('/api/adv/keyring/list', methods=['GET'])
def adv_keyring_list():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT id, key_name, status, rotated_from, created_at FROM advanced_keyring WHERE user_id=%s ORDER BY id DESC", (user_id,))
    rows = c.fetchall()
    conn.close()
    return jsonify({"success": True, "keys": [{"id": r[0], "name": r[1], "status": r[2], "rotated_from": r[3], "created_at": r[4]} for r in rows]})


@app.route('/api/adv/keyring/rotate', methods=['POST'])
def adv_keyring_rotate():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    key_id = int((request.json or {}).get('key_id') or 0)
    if not key_id:
        return jsonify({"success": False, "error": "key_id required"}), 400
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT id, key_name FROM advanced_keyring WHERE id=%s AND user_id=%s", (key_id, user_id))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "key not found"}), 404
    c.execute("UPDATE advanced_keyring SET status='rotated' WHERE id=%s", (key_id,))
    new_key = Fernet.generate_key().decode('ascii')
    c.execute("INSERT INTO advanced_keyring (user_id, key_name, key_material, status, rotated_from, created_at) VALUES (%s,%s,%s,'active',%s,%s) RETURNING id",
              (user_id, f"{row[1]}-rotated", new_key, key_id, datetime.datetime.now().isoformat()))
    new_row = c.fetchone()
    conn.commit()
    conn.close()
    return jsonify({"success": True, "new_key_id": new_row[0] if new_row else None})


@app.route('/api/adv/keyring/revoke', methods=['POST'])
def adv_keyring_revoke():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    key_id = int((request.json or {}).get('key_id') or 0)
    if not key_id:
        return jsonify({"success": False, "error": "key_id required"}), 400
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("UPDATE advanced_keyring SET status='revoked' WHERE id=%s AND user_id=%s", (key_id, user_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


def _adv_get_key_material(user_id: int, key_id: int) -> str | None:
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT key_material, status FROM advanced_keyring WHERE id=%s AND user_id=%s", (key_id, user_id))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    if row[1] != 'active':
        return None
    return row[0]


@app.route('/api/adv/keyring/encrypt', methods=['POST'])
def adv_keyring_encrypt():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    data = request.json or {}
    key_id = int(data.get('key_id') or 0)
    text = data.get('text') or ''
    if not key_id or text == '':
        return jsonify({"success": False, "error": "key_id/text required"}), 400
    key_material = _adv_get_key_material(user_id, key_id)
    if not key_material:
        return jsonify({"success": False, "error": "active key not found"}), 404
    cipher = Fernet(key_material.encode('ascii')).encrypt(text.encode('utf-8')).decode('ascii')
    return jsonify({"success": True, "cipher": cipher})


@app.route('/api/adv/keyring/decrypt', methods=['POST'])
def adv_keyring_decrypt():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    data = request.json or {}
    key_id = int(data.get('key_id') or 0)
    cipher = data.get('cipher') or ''
    if not key_id or not cipher:
        return jsonify({"success": False, "error": "key_id/cipher required"}), 400
    key_material = _adv_get_key_material(user_id, key_id)
    if not key_material:
        return jsonify({"success": False, "error": "active key not found"}), 404
    try:
        text = Fernet(key_material.encode('ascii')).decrypt(cipher.encode('ascii')).decode('utf-8')
        return jsonify({"success": True, "text": text})
    except Exception:
        return jsonify({"success": False, "error": "decrypt failed"}), 400


# =====================================================================
# === AI Routes (Ollama) ===
# =====================================================================

@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401

    is_multipart = (request.content_type or '').lower().startswith('multipart/form-data')
    message = ''
    model = 'titan_ultimate'
    files = []
    if is_multipart:
        message = (request.form.get('message') or '').strip()
        model = (request.form.get('model') or 'titan_ultimate').strip()
        files = request.files.getlist('files')
    else:
        data = request.get_json(silent=True) or {}
        message = (data.get('message') or '').strip()
        model = (data.get('model') or 'titan_ultimate').strip()

    if not message and not files:
        return jsonify({"error": "الرسالة أو المرفقات مطلوبة"}), 400
    if not DO_AI_KEY:
        return jsonify({"error": "DO_AI_KEY غير مضبوط"}), 500

    try:
        attachment_chunks = []
        skipped = []
        max_files = 5
        max_file_size = 8 * 1024 * 1024

        if files:
            for idx, f in enumerate(files[:max_files], start=1):
                filename = secure_filename(f.filename or f"file_{idx}")
                content_type = (f.mimetype or 'application/octet-stream').lower()
                raw = f.read() or b''
                if not raw:
                    skipped.append(f"{filename}: empty")
                    continue
                if len(raw) > max_file_size:
                    skipped.append(f"{filename}: too large")
                    continue

                lower_name = filename.lower()
                try:
                    if content_type.startswith('image/') or lower_name.endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp')):
                        w = h = None
                        try:
                            img = Image.open(io.BytesIO(raw))
                            w, h = img.size
                        except Exception:
                            pass
                        dims = f"{w}x{h}" if w and h else "unknown-size"
                        ocr_text, ocr_err = extract_image_ocr_text(raw, max_chars=5000)
                        if ocr_text:
                            attachment_chunks.append(
                                f"[Attachment {idx}] IMAGE: name={filename}, mime={content_type}, size={len(raw)} bytes, dimensions={dims}\n"
                                f"OCR_TEXT:\n{ocr_text}"
                            )
                        else:
                            attachment_chunks.append(
                                f"[Attachment {idx}] IMAGE: name={filename}, mime={content_type}, size={len(raw)} bytes, dimensions={dims}, "
                                f"ocr_status={ocr_err or 'unavailable'}"
                            )
                    elif content_type == 'application/pdf' or lower_name.endswith('.pdf'):
                        reader = PdfReader(io.BytesIO(raw))
                        pages = reader.pages[:5]
                        extracted = []
                        for p in pages:
                            txt = (p.extract_text() or '').strip()
                            if txt:
                                extracted.append(txt[:1800])
                        joined = "\n\n".join(extracted).strip()
                        if not joined:
                            joined = "(No extractable text found in PDF)"
                        attachment_chunks.append(
                            f"[Attachment {idx}] PDF: name={filename}, pages_read={len(pages)}\n{joined}"
                        )
                    elif content_type.startswith('text/') or lower_name.endswith(('.txt', '.md', '.csv', '.json', '.log', '.xml', '.html', '.css', '.js', '.py', '.yaml', '.yml', '.ini', '.conf')):
                        text = raw.decode('utf-8', errors='ignore').strip()
                        if not text:
                            text = "(Empty text file)"
                        attachment_chunks.append(
                            f"[Attachment {idx}] TEXT: name={filename}\n{text[:6000]}"
                        )
                    else:
                        attachment_chunks.append(
                            f"[Attachment {idx}] FILE: name={filename}, mime={content_type}, size={len(raw)} bytes"
                        )
                except Exception as ex:
                    skipped.append(f"{filename}: {str(ex)[:80]}")

        prompt_parts = []
        if message:
            prompt_parts.append(message)
        if attachment_chunks:
            prompt_parts.append("\n\n=== ATTACHMENTS CONTEXT ===\n" + "\n\n".join(attachment_chunks))
            prompt_parts.append("\nPlease analyze the attachments context and answer in Arabic with practical security guidance.")
        if skipped:
            prompt_parts.append("\n\nSkipped attachments: " + ", ".join(skipped))

        final_prompt = "\n".join(prompt_parts).strip()
        reply = _call_do_ai(final_prompt)
        add_audit_log("AI Chat 🤖", f"AI: {message[:50]} | files={len(files)} | model={model}", username=session.get('username', ''))
        return jsonify({"success": True, "reply": reply})
    except Exception as e:
        print(f"[TITAN AI] Error: {e}")
        return jsonify({"error": f"فشل الاتصال بـ TITAN AI: {str(e)}"}), 500


@app.route('/api/ai/analyze', methods=['POST'])
def ai_analyze():
    """تحليل أمني بالذكاء الاصطناعي"""
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    data = request.json or {}
    analyze_type = data.get('type', 'security')
    content_to_analyze = data.get('content', '')
    if not content_to_analyze:
        return jsonify({"error": "المحتوى مطلوب"}), 400

    prompts = {
        'password': f"حلل كلمة السر هذه أمنياً بالعربية: مستوى الأمان، نقاط الضعف، اقتراحات للتحسين. كلمة السر: {content_to_analyze}",
        'ip': f"حلل بيانات IP هذه أمنياً بالعربية وأعطني تقييم وتوصيات: {content_to_analyze}",
        'security': f"حلل هذه البيانات الأمنية بالعربية وأعطني تقييماً شاملاً وتوصيات عملية: {content_to_analyze}"
    }

    prompt = prompts.get(analyze_type, prompts['security'])
    if not DO_AI_KEY:
        return jsonify({"error": "DO_AI_KEY غير مضبوط"}), 500
    try:
        analysis = _call_do_ai(prompt)
        add_audit_log("AI تحليل 🤖", f"تحليل {analyze_type}", username=session.get('username', ''))
        return jsonify({"success": True, "analysis": analysis})
    except Exception as e:
        print(f"[TITAN AI] Analyze error: {e}")
        return jsonify({"error": f"فشل التحليل: {str(e)}"}), 500


@app.route('/api/ai/models', methods=['GET'])
def ai_models():
    return jsonify({"models": ["TITAN-SEC AI (DigitalOcean)"], "success": True})


@app.route('/api/support/tickets', methods=['GET', 'POST'])
def support_tickets_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    assert user_id is not None
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        if request.method == 'POST':
            data = request.json or {}
            subject = (data.get('subject') or '').strip()
            details = (data.get('details') or '').strip()
            category = (data.get('category') or 'technical').strip().lower()
            priority = (data.get('priority') or 'normal').strip().lower()
            if not subject or not details:
                return jsonify({"success": False, "error": "subject/details required"}), 400
            if category not in ('technical', 'billing', 'account', 'security'):
                category = 'technical'
            if priority not in ('low', 'normal', 'high', 'urgent'):
                priority = 'normal'
            now = datetime.datetime.now().isoformat()
            c.execute(
                "INSERT INTO support_tickets (user_id, subject, category, priority, details, status, admin_note, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,'open','',%s,%s) RETURNING id",
                (user_id, subject, category, priority, details, now, now)
            )
            row = c.fetchone()
            conn.commit()
            add_audit_log("Support Ticket", f"created ticket#{row[0] if row else '?'}", username=session.get('username', ''))
            return jsonify({"success": True, "ticket_id": row[0] if row else None})

        c.execute(
            "SELECT id, subject, category, priority, details, status, admin_note, created_at, updated_at FROM support_tickets WHERE user_id=%s ORDER BY id DESC LIMIT 100",
            (user_id,)
        )
        rows = c.fetchall()
        tickets = [
            {
                "id": r[0], "subject": r[1], "category": r[2], "priority": r[3], "details": r[4],
                "status": r[5], "admin_note": r[6], "created_at": r[7], "updated_at": r[8]
            }
            for r in rows
        ]
        return jsonify({"success": True, "tickets": tickets})
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


# --- تهيئة قاعدة البيانات عند بدء التطبيق ---
try:
    init_db()
    print("[TITAN] Database initialized successfully.")
except Exception as _e:
    print(f"[TITAN] init_db error: {_e}")

if __name__ == "__main__":
    port = int(__import__("os").environ.get("PORT", 5000))
    __import__("__main__").app.run(host="0.0.0.0", port=port, debug=False)
