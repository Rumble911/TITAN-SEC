import os
import re
import secrets
import string
import hashlib
import base64
import io
import json
import pyotp  # type: ignore
import qrcode  # type: ignore
import datetime
import time
import tempfile
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, render_template_string, send_file, session  # type: ignore
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
import urllib.request
import json as _json

# --- Appwrite REST API (no SDK needed) ---

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.secret_key = os.environ.get('SECRET_KEY', 'CHANGE_THIS_IN_PRODUCTION')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_NAME'] = 'titan_session'
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(hours=12)

# --- Appwrite Config ---
APPWRITE_ENDPOINT = os.environ.get('APPWRITE_ENDPOINT', 'https://fra.cloud.appwrite.io/v1')
APPWRITE_PROJECT_ID = os.environ.get('APPWRITE_PROJECT_ID', '')
APPWRITE_API_KEY = os.environ.get('APPWRITE_API_KEY', '')
APPWRITE_DB_ID = os.environ.get('APPWRITE_DB_ID', 'TITAN-DBB1')

# Collection IDs (سنعرّفها كـ constants)
COL_USERS = 'users'
COL_SECURITY_LOGS = 'security_logs'
COL_ACTIVE_SESSIONS = 'active_sessions'
COL_BACKUP_CODES = 'backup_codes'
COL_VAULT_TIMELOCKED = 'vault_timelocked'
COL_INTEGRITY = 'integrity_baseline'
COL_PASSWORDS = 'passwords'

# --- Testmail Config ---
BREVO_SMTP_SERVER = 'smtp-relay.brevo.com'
BREVO_SMTP_PORT = 587
BREVO_SMTP_LOGIN = os.environ.get('BREVO_SMTP_LOGIN', '')
BREVO_SMTP_KEY = os.environ.get('BREVO_SMTP_KEY', '')
SENDER_EMAIL = 'noreply@titan-cyber.me'
SENDER_NAME = 'TITAN SEC'
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'abdallahalqam4040@gmail.com')


def _aw_headers():
    return {
        "Content-Type": "application/json",
        "X-Appwrite-Project": APPWRITE_PROJECT_ID,
        "X-Appwrite-Key": APPWRITE_API_KEY,
    }


def _aw_url(path):
    return f"{APPWRITE_ENDPOINT}{path}"


# =====================================================================
# === Testmail Email Functions ===
# =====================================================================

def _testmail_send(to_email, subject, body):
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


def _send_email_async(subject, body, to=None):
    target = to or ADMIN_EMAIL
    def _worker():
        try:
            _testmail_send(target, subject, body)
        except Exception as e:
            print(f"[TITAN Email] {e}")
    threading.Thread(target=_worker, daemon=True).start()


def send_otp_email(target_email, otp_code):
    body = f"""مرحباً بك في TITAN SEC.
كود التحقق الخاص بك هو: {otp_code}
يرجى إدخاله في الموقع لإتمام عملية التسجيل.

هذا الكود صالح لمدة 10 دقائق فقط."""
    return _testmail_send(target_email, "كود التحقق الخاص بك - TITAN", body)


def send_login_alert_email(username, ip, user_agent):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = f"""TITAN Security Alert - Login Notification

تم تسجيل دخول الى النظام:
- المستخدم: {username}
- عنوان IP: {ip}
- المتصفح: {user_agent[:120]}
- الوقت: {now}
"""
    _send_email_async(f"TITAN - دخول جديد: {username}", body)


def send_new_device_alert(username, ip, user_agent, email):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = f"""TITAN - تنبيه دخول من جهاز جديد

مرحبا {username}،
رصد دخول من متصفح/جهاز جديد:
- IP: {ip}
- المتصفح: {user_agent[:120]}
- الوقت: {now}

اذا لم تكن انت، غير كلمة السر فورا.
"""
    _send_email_async(f"TITAN - جهاز جديد: {username}", body, to=email)
    _send_email_async(f"TITAN ADMIN - جهاز جديد لـ {username}", body)


def send_geo_fence_alert(username, ip, old_country, new_country, email):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = f"""TITAN - تنبيه دخول مشبوه!

مرحبا {username}،
دخول من دولة مختلفة:
- الدولة المعتادة: {old_country}
- الدولة الجديدة: {new_country}
- IP: {ip}
- الوقت: {now}
"""
    _send_email_async(f"TITAN - دخول مشبوه لـ {username}", body, to=email)
    _send_email_async(f"TITAN ADMIN - دخول مشبوه لـ {username}", body)


def send_canary_alert(ip, user_agent):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = f"""TITAN HONEYPOT TRIGGERED!

شخص حاول الوصول لملف passwords.txt السري!
- IP: {ip}
- المتصفح: {user_agent[:150]}
- الوقت: {now}
"""
    _send_email_async("TITAN HONEYPOT - تنبيه تجسس!", body)


# =====================================================================
# === Appwrite DB Helpers ===
# =====================================================================

def _unique_id():
    return secrets.token_hex(10)


def aw_create(collection_id, data, doc_id=None):
    doc_id = doc_id or _unique_id()
    url = _aw_url(f"/databases/{APPWRITE_DB_ID}/collections/{collection_id}/documents")
    payload = {"documentId": doc_id, "data": data}
    r = requests.post(url, headers=_aw_headers(), json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def aw_get(collection_id, doc_id):
    url = _aw_url(f"/databases/{APPWRITE_DB_ID}/collections/{collection_id}/documents/{doc_id}")
    try:
        r = requests.get(url, headers=_aw_headers(), timeout=10)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def aw_list(collection_id, queries=None):
    url = _aw_url(f"/databases/{APPWRITE_DB_ID}/collections/{collection_id}/documents")
    params = {}
    if queries:
        params['queries[]'] = queries
    try:
        r = requests.get(url, headers=_aw_headers(), params=params, timeout=10)
        r.raise_for_status()
        return r.json().get('documents', [])
    except Exception:
        return []


def aw_update(collection_id, doc_id, data):
    url = _aw_url(f"/databases/{APPWRITE_DB_ID}/collections/{collection_id}/documents/{doc_id}")
    payload = {"data": data}
    r = requests.patch(url, headers=_aw_headers(), json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def aw_delete(collection_id, doc_id):
    url = _aw_url(f"/databases/{APPWRITE_DB_ID}/collections/{collection_id}/documents/{doc_id}")
    try:
        r = requests.delete(url, headers=_aw_headers(), timeout=10)
        return r.status_code in [200, 204]
    except Exception:
        return False


def aw_list_query(collection_id, field, value):
    """List documents filtered by field=value using Appwrite REST query"""
    url = _aw_url(f"/databases/{APPWRITE_DB_ID}/collections/{collection_id}/documents")
    query = f'equal("{field}", ["{value}"])'
    try:
        r = requests.get(url, headers=_aw_headers(),
                         params={"queries[]": query}, timeout=10)
        r.raise_for_status()
        return r.json().get('documents', [])
    except Exception as e:
        print(f"[TITAN] aw_list_query error: {e}")
        return []


def find_user_by_username(username):
    docs = aw_list_query(COL_USERS, 'username', username)
    return docs[0] if docs else None


def find_user_by_email(email):
    docs = aw_list_query(COL_USERS, 'email', email)
    return docs[0] if docs else None


def find_user_by_id(user_id):
    return aw_get(COL_USERS, user_id)


# =====================================================================
# === Security / Audit Logs ===
# =====================================================================

AUDIT_LOGS = []
BURN_NOTES = {}


def add_audit_log(action, details="", ip="", username=""):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    event = {"time": now, "action": action, "details": details, "ip": ip, "username": username}
    AUDIT_LOGS.insert(0, event)
    if len(AUDIT_LOGS) > 200:
        AUDIT_LOGS.pop()
    try:
        aw_create(COL_SECURITY_LOGS, {
            "time": now,
            "action": action,
            "details": details[:500] if details else "",
            "ip": ip,
            "username": username
        })
    except Exception as e:
        print(f"[TITAN] Audit log error: {e}")


# =====================================================================
# === Password Hashing ===
# =====================================================================

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


# =====================================================================
# === Encryption / Decryption ===
# =====================================================================

def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def derive_raw_key(password: str, salt: bytes) -> bytes:
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
    return salt + encrypted_data


def decrypt_data(encrypted_content: bytes, password: str) -> bytes:
    try:
        salt = encrypted_content[:16]
        data = encrypted_content[16:]
        key = derive_key(password, salt)
        f = Fernet(key)
        return f.decrypt(data)
    except Exception:
        raise ValueError("كلمة السر خاطئة أو الملف معطوب")


# =====================================================================
# === Vault File Helpers (Appwrite Storage) ===
# =====================================================================

def get_vault_file(user_id: str) -> str:
    return f'vault_user_{user_id}.titan'


def get_vault_recovery_file(user_id: str) -> str:
    return f'vault_recovery_user_{user_id}.json'


def _get_logged_in_user_id():
    if 'user_id' not in session:
        return None, (jsonify({"error": "غير مصرح"}), 401)
    return session['user_id'], None


# =====================================================================
# === Init DB (Create Collections if not exist) ===
# =====================================================================

def init_db():
    """Create Appwrite collections if they don't exist, and create root user"""
    db = get_db()

    collections_needed = [
        (COL_USERS, [
            {"key": "username", "type": "string", "size": 100, "required": True},
            {"key": "password_hash", "type": "string", "size": 200, "required": True},
            {"key": "email", "type": "string", "size": 200, "required": False},
            {"key": "is_verified", "type": "boolean", "required": False, "default": False},
            {"key": "otp_code", "type": "string", "size": 20, "required": False},
            {"key": "vault_password_hash", "type": "string", "size": 200, "required": False},
            {"key": "created_at", "type": "string", "size": 50, "required": True},
            {"key": "is_admin", "type": "boolean", "required": False, "default": False},
            {"key": "failed_attempts", "type": "integer", "required": False, "default": 0},
            {"key": "lockout_until", "type": "string", "size": 50, "required": False},
            {"key": "last_user_agent", "type": "string", "size": 300, "required": False},
            {"key": "last_login_ip", "type": "string", "size": 100, "required": False},
            {"key": "last_login_at", "type": "string", "size": 50, "required": False},
            {"key": "last_country", "type": "string", "size": 10, "required": False},
            {"key": "vault_otp_code", "type": "string", "size": 20, "required": False},
        ]),
        (COL_SECURITY_LOGS, [
            {"key": "time", "type": "string", "size": 50, "required": True},
            {"key": "action", "type": "string", "size": 200, "required": True},
            {"key": "details", "type": "string", "size": 500, "required": False},
            {"key": "ip", "type": "string", "size": 100, "required": False},
            {"key": "username", "type": "string", "size": 100, "required": False},
        ]),
        (COL_ACTIVE_SESSIONS, [
            {"key": "user_id", "type": "string", "size": 100, "required": True},
            {"key": "token", "type": "string", "size": 100, "required": True},
            {"key": "user_agent", "type": "string", "size": 300, "required": False},
            {"key": "ip", "type": "string", "size": 100, "required": False},
            {"key": "country", "type": "string", "size": 10, "required": False},
            {"key": "created_at", "type": "string", "size": 50, "required": False},
        ]),
        (COL_BACKUP_CODES, [
            {"key": "user_id", "type": "string", "size": 100, "required": True},
            {"key": "code_hash", "type": "string", "size": 100, "required": True},
            {"key": "used", "type": "boolean", "required": False, "default": False},
        ]),
        (COL_VAULT_TIMELOCKED, [
            {"key": "user_id", "type": "string", "size": 100, "required": True},
            {"key": "filename", "type": "string", "size": 200, "required": True},
            {"key": "enc_data", "type": "string", "size": 10000000, "required": True},
            {"key": "unlock_at", "type": "string", "size": 50, "required": True},
            {"key": "created_at", "type": "string", "size": 50, "required": True},
        ]),
        (COL_INTEGRITY, [
            {"key": "file_path", "type": "string", "size": 500, "required": True},
            {"key": "hash", "type": "string", "size": 100, "required": True},
            {"key": "set_at", "type": "string", "size": 50, "required": True},
        ]),
        (COL_PASSWORDS, [
            {"key": "user_id", "type": "string", "size": 100, "required": True},
            {"key": "site", "type": "string", "size": 200, "required": True},
            {"key": "username_field", "type": "string", "size": 200, "required": False},
            {"key": "enc_password", "type": "string", "size": 5000, "required": True},
            {"key": "notes", "type": "string", "size": 1000, "required": False},
            {"key": "created_at", "type": "string", "size": 50, "required": False},
        ]),
    ]

    for col_id, attributes in collections_needed:
        check_url = _aw_url(f"/databases/{APPWRITE_DB_ID}/collections/{col_id}")
        r = requests.get(check_url, headers=_aw_headers(), timeout=10)
        if r.status_code == 200:
            print(f"[TITAN] Collection {col_id} already exists.")
            continue
        try:
            create_url = _aw_url(f"/databases/{APPWRITE_DB_ID}/collections")
            r = requests.post(create_url, headers=_aw_headers(), json={
                "collectionId": col_id, "name": col_id, "documentSecurity": False
            }, timeout=10)
            r.raise_for_status()
            print(f"[TITAN] Created collection: {col_id}")
            time.sleep(1)
            for attr in attributes:
                try:
                    attr_type = attr.get("type")
                    attr_url = _aw_url(f"/databases/{APPWRITE_DB_ID}/collections/{col_id}/attributes/{attr_type}")
                    payload = {"key": attr["key"], "required": attr.get("required", False)}
                    if attr_type == "string":
                        payload["size"] = attr.get("size", 255)
                        if attr.get("default") is not None:
                            payload["default"] = attr["default"]
                    elif attr_type in ("boolean", "integer"):
                        if attr.get("default") is not None:
                            payload["default"] = attr["default"]
                    requests.post(attr_url, headers=_aw_headers(), json=payload, timeout=10)
                    time.sleep(0.3)
                except Exception as ae:
                    print(f"[TITAN] Attr error {col_id}.{attr['key']}: {ae}")
        except Exception as ce:
            print(f"[TITAN] Collection create error {col_id}: {ce}")

    # Root user
    time.sleep(2)
    try:
        root = find_user_by_username('root')
        if not root:
            aw_create(COL_USERS, {
                "username": "root",
                "password_hash": hash_password('Facebook123@@'),
                "is_verified": True,
                "is_admin": True,
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "failed_attempts": 0,
            })
            print("[TITAN] Root user created.")
    except Exception as e:
        print(f"[TITAN] Root user error: {e}")

    _create_canary_file()
    _ensure_integrity_baseline()


def _create_canary_file():
    canary_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'passwords.txt')
    if not os.path.exists(canary_path):
        with open(canary_path, 'w', encoding='utf-8') as f:
            f.write("# TITAN System Credentials - DO NOT SHARE\n")
            f.write("admin:T1TAN_S3CR3T_2025!\n")
            f.write("root:P@ssw0rd123\n")
            f.write("dbuser:sql_vault_key_9x\n")


def _ensure_integrity_baseline():
    app_path = os.path.abspath(__file__)
    try:
        existing = aw_list_query(COL_INTEGRITY, "file_path", app_path)
        if not existing:
            with open(app_path, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
            aw_create(COL_INTEGRITY, {
                "file_path": app_path,
                "hash": file_hash,
                "set_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
    except Exception as e:
        print(f"[TITAN] Integrity baseline error: {e}")


# =====================================================================
# === Image & Steganography Functions (unchanged) ===
# =====================================================================

def remove_image_metadata(img_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(img_bytes))
    data = list(img.getdata())
    img_no_meta = Image.new(img.mode, img.size)
    img_no_meta.putdata(data)
    out = io.BytesIO()
    fmt = img.format if img.format else "PNG"
    img_no_meta.save(out, format=fmt)
    return out.getvalue()


def lsb_encode(img_bytes: bytes, secret_data: str) -> bytes:
    img = Image.open(io.BytesIO(img_bytes)).convert('RGBA')
    width, height = img.size
    binary_data = ''.join([format(b, "08b") for b in secret_data.encode('utf-8')]) + '1111111111111110'
    if len(binary_data) > width * height * 3:
        raise ValueError("البيانات كبيرة جداً بالنسبة لهذه الصورة!")
    pixels = img.load()
    data_idx = 0
    for y in range(height):
        for x in range(width):
            if data_idx < len(binary_data):
                r, g, b, a = pixels[x, y]
                r = (r & ~1) | int(binary_data[data_idx])
                data_idx += 1
                if data_idx < len(binary_data):
                    g = (g & ~1) | int(binary_data[data_idx])
                    data_idx += 1
                if data_idx < len(binary_data):
                    b = (b & ~1) | int(binary_data[data_idx])
                    data_idx += 1
                pixels[x, y] = (r, g, b, a)
            else:
                break
        if data_idx >= len(binary_data):
            break
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def lsb_decode(img_bytes: bytes) -> str:
    img = Image.open(io.BytesIO(img_bytes)).convert('RGBA')
    width, height = img.size
    pixels = img.load()
    bits: list = []
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            bits.append(r & 1)
            bits.append(g & 1)
            bits.append(b & 1)
    END_MARKER = [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0]
    for i in range(len(bits) - 15):
        if bits[i:i+16] == END_MARKER:
            data_bits = bits[:i]
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
                    return "فشل استخراج النص."
    return "لم يتم العثور على بيانات مخفية في هذه الصورة!"


def extract_exif_data(img_bytes: bytes) -> dict:
    tags = exifread.process_file(io.BytesIO(img_bytes), details=False)
    extracted = {}
    important_tags = ['Image Make', 'Image Model', 'Image DateTime', 'Image Software', 'GPS GPSLatitude', 'GPS GPSLongitude']
    for tag in tags.keys():
        if any(imp in tag for imp in important_tags):
            extracted[tag] = str(tags[tag])
    return extracted if extracted else {"Info": "لا توجد أي بيانات وصفية مخفية (EXIF) في هذه الصورة."}


# =====================================================================
# === IPQualityScore Functions (unchanged) ===
# =====================================================================

def check_email_intelligence(email: str) -> dict:
    API_KEY = os.environ.get('IPQS_API_KEY', '1ZFJTNYsuxNXvJwdiETskE0DqpHJDIc4')
    url = f'https://ipqualityscore.com/api/json/email/{API_KEY}/{email}'
    try:
        response = requests.get(url, params={'timeout': 7, 'fast': 'false', 'abuse_strictness': 0}, timeout=10)
        return response.json()
    except Exception as e:
        return {"success": False, "message": str(e)}


def check_phone_intelligence(phone: str) -> dict:
    API_KEY = os.environ.get('IPQS_API_KEY', '1ZFJTNYsuxNXvJwdiETskE0DqpHJDIc4')
    phone_clean = urllib.parse.quote(phone.strip())
    url = f'https://www.ipqualityscore.com/api/json/phone/{API_KEY}/{phone_clean}'
    try:
        response = requests.get(url, timeout=10)
        return response.json()
    except Exception as e:
        return {"success": False, "message": str(e)}


def check_url_intelligence(target_url: str) -> dict:
    API_KEY = os.environ.get('IPQS_API_KEY', '1ZFJTNYsuxNXvJwdiETskE0DqpHJDIc4')
    url_clean = urllib.parse.quote(target_url.strip(), safe='')
    url = f'https://www.ipqualityscore.com/api/json/url/{API_KEY}/{url_clean}'
    try:
        response = requests.get(url, params={'fast': 'true', 'strictness': 0}, timeout=10)
        return response.json()
    except Exception as e:
        return {"success": False, "message": str(e)}


def check_leaked_emailpass(email: str, password: str) -> dict:
    API_KEY = os.environ.get('IPQS_API_KEY', '1ZFJTNYsuxNXvJwdiETskE0DqpHJDIc4')
    url = f"https://www.ipqualityscore.com/api/json/leaked/emailpass/{API_KEY}"
    try:
        response = requests.post(url, json={"email": email, "password": password}, timeout=10)
        return response.json()
    except Exception as e:
        return {"success": False, "message": str(e)}


def get_ipqs_requests_list(req_type: str, start_date: str) -> dict:
    API_KEY = os.environ.get('IPQS_API_KEY', '1ZFJTNYsuxNXvJwdiETskE0DqpHJDIc4')
    url = f'https://www.ipqualityscore.com/api/json/requests/{API_KEY}/list'
    try:
        response = requests.get(url, params={'type': req_type, 'start_date': start_date}, timeout=10)
        return response.json()
    except Exception as e:
        return {"success": False, "message": str(e)}


# =====================================================================
# === Audio Steganography ===
# =====================================================================

def wave_lsb_encode(audio_bytes: bytes, secret_text: str, filename: str) -> bytes:
    if filename.lower().endswith('.mp3'):
        return audio_bytes
    try:
        with wave.open(io.BytesIO(audio_bytes)) as wf:
            params = wf.getparams()
            frames = bytearray(wf.readframes(wf.getnframes()))
        binary_secret = ''.join(format(b, '08b') for b in secret_text.encode('utf-8')) + '1111111111111110'
        if len(binary_secret) > len(frames):
            raise ValueError("النص كبير جداً بالنسبة لهذا الملف الصوتي!")
        for i, bit in enumerate(binary_secret):
            frames[i] = (frames[i] & ~1) | int(bit)
        out = io.BytesIO()
        with wave.open(out, 'wb') as wf_out:
            wf_out.setparams(params)
            wf_out.writeframes(bytes(frames))
        return out.getvalue()
    except Exception as e:
        raise ValueError(f"خطأ في معالجة الملف الصوتي: {str(e)}")


def wave_lsb_decode(audio_bytes: bytes, filename: str) -> str:
    if filename.lower().endswith('.mp3'):
        return "فك التشفير الصوتي غير مدعوم لملفات MP3 حالياً"
    try:
        with wave.open(io.BytesIO(audio_bytes)) as wf:
            frames = bytearray(wf.readframes(wf.getnframes()))
        bits = [frames[i] & 1 for i in range(len(frames))]
        END_MARKER = [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0]
        for i in range(len(bits) - 15):
            if bits[i:i+16] == END_MARKER:
                data_bits = bits[:i]
                num_bytes = len(data_bits) // 8
                if num_bytes == 0:
                    return "لا توجد بيانات مخفية في هذا الملف!"
                byte_data = bytes([int(''.join(str(b) for b in data_bits[j*8:(j+1)*8]), 2) for j in range(num_bytes)])
                return byte_data.decode('utf-8', errors='replace')
        return "لم يتم العثور على بيانات مخفية!"
    except Exception as e:
        raise ValueError(f"خطأ في فك تشفير الملف الصوتي: {str(e)}")


def clean_pdf_metadata(pdf_bytes: bytes) -> bytes:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_metadata({})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# =====================================================================
# === Network Functions ===
# =====================================================================

def get_dns_leak_info() -> dict:
    try:
        result = requests.get('https://api.ipify.org?format=json', timeout=5)
        ip = result.json().get('ip', 'N/A')
        geo = requests.get(f'http://ip-api.com/json/{ip}', timeout=5).json()
        return {
            'public_ip': ip,
            'country': geo.get('country', 'N/A'),
            'isp': geo.get('isp', 'N/A'),
            'city': geo.get('city', 'N/A'),
        }
    except Exception as e:
        return {'error': str(e)}


def get_shodan_intel(ip: str) -> dict:
    try:
        r = requests.get(f'https://internetdb.shodan.io/{ip}', timeout=7)
        return r.json()
    except Exception as e:
        return {'error': str(e)}


def scan_local_network() -> list:
    devices = []
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
        base_ip = '.'.join(local_ip.split('.')[:3])
        def check_host(i):
            target = f"{base_ip}.{i}"
            try:
                socket.setdefaulttimeout(0.1)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex((target, 80))
                sock.close()
                if result == 0:
                    try:
                        hostname = socket.gethostbyaddr(target)[0]
                    except Exception:
                        hostname = target
                    return {"ip": target, "hostname": hostname}
            except Exception:
                pass
            return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            results = list(executor.map(check_host, range(1, 255)))
        devices = [r for r in results if r]
    except Exception:
        pass
    return devices


# =====================================================================
# === Auth Routes ===
# =====================================================================

def _get_login_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()


def _get_country(ip):
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=countryCode", timeout=4)
        return r.json().get('countryCode', '')
    except Exception:
        return ''


_FORGOT_OTP_STORE = {}


@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    email = data.get('email', '').strip()

    if not username or not password or not email:
        return jsonify({"error": "اسم المستخدم وكلمة السر والإيميل مطلوبان"}), 400
    if len(username) < 3:
        return jsonify({"error": "اسم المستخدم يجب أن يكون 3 أحرف على الأقل"}), 400
    if len(password) < 6:
        return jsonify({"error": "كلمة السر يجب أن تكون 6 أحرف على الأقل"}), 400
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({"error": "البريد الإلكتروني غير صالح"}), 400

    ip = _get_login_ip()

    try:
        if find_user_by_username(username):
            return jsonify({"error": "اسم المستخدم مسجل مسبقاً"}), 409
        if find_user_by_email(email):
            return jsonify({"error": "البريد الإلكتروني مسجل مسبقاً بحساب آخر"}), 409

        pw_hash = hash_password(password)
        otp_code = "".join(random.choices(string.digits, k=6))
        created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        user_doc = aw_create(COL_USERS, {
            "username": username,
            "password_hash": pw_hash,
            "email": email,
            "otp_code": otp_code,
            "is_verified": False,
            "is_admin": False,
            "created_at": created_at,
            "failed_attempts": 0,
        })
        user_id = user_doc['$id']

        codes = [''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8)) for _ in range(8)]
        for code in codes:
            aw_create(COL_BACKUP_CODES, {
                "user_id": user_id,
                "code_hash": hashlib.sha256(code.encode()).hexdigest(),
                "used": False
            })

        add_audit_log("تسجيل مستخدم جديد", f"تم إنشاء حساب: {username}", ip=ip, username=username)
        send_otp_email(email, otp_code)

        return jsonify({
            "success": True,
            "message": "تم إنشاء الحساب! يرجى التحقق من بريدك الإلكتروني.",
            "username": username,
            "backup_codes": codes
        })
    except Exception as e:
        print(f"[TITAN] Register error: {e}")
        return jsonify({"error": "فشل إنشاء الحساب، حاول مجدداً"}), 500


@app.route('/api/auth/verify', methods=['POST'])
def auth_verify():
    data = request.json or {}
    username = data.get('username', '').strip()
    otp = data.get('otp', '').strip()

    if not username or not otp:
        return jsonify({"error": "اسم المستخدم وكود التحقق مطلوبان"}), 400

    try:
        user = find_user_by_username(username)
        if not user:
            return jsonify({"error": "المستخدم غير موجود"}), 404

        if user.get('otp_code') == otp:
            aw_update(COL_USERS, user['$id'], {"is_verified": True, "otp_code": None})
            session.permanent = True
            session['user_id'] = user['$id']
            session['username'] = username
            add_audit_log("تفعيل الحساب ✅", f"تم تفعيل حساب المستخدم: {username}")
            return jsonify({"success": True, "message": "تم تفعيل الحساب بنجاح!", "auto_login": True})
        else:
            return jsonify({"error": "كود التحقق غير صحيح"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    ip = _get_login_ip()
    ua = request.headers.get('User-Agent', '')[:255]

    if not username or not password:
        return jsonify({"error": "اسم المستخدم وكلمة السر مطلوبان"}), 400

    try:
        user = find_user_by_username(username)
        if not user:
            add_audit_log("محاولة دخول فاشلة", f"مستخدم غير موجود: {username}", ip=ip)
            return jsonify({"error": "اسم المستخدم أو كلمة السر غير صحيحة"}), 401

        user_id = user['$id']
        pw_hash = user.get('password_hash', '')
        is_verified = user.get('is_verified', False)
        email = user.get('email', '')
        failed_attempts = user.get('failed_attempts', 0) or 0
        lockout_until = user.get('lockout_until')
        last_ua = user.get('last_user_agent', '')
        last_country = user.get('last_country', '')

        if lockout_until:
            try:
                lo_dt = datetime.datetime.fromisoformat(lockout_until)
                if datetime.datetime.now() < lo_dt:
                    remaining = int((lo_dt - datetime.datetime.now()).total_seconds() // 60) + 1
                    return jsonify({"error": "ACCOUNT_LOCKED",
                                    "message": f"الحساب مقفل. حاول مجدداً بعد {remaining} دقيقة.",
                                    "minutes": remaining}), 429
            except Exception:
                pass

        if not verify_password(password, pw_hash):
            failed_attempts += 1
            lockout = None
            if failed_attempts >= 3:
                lockout = (datetime.datetime.now() + datetime.timedelta(minutes=30)).isoformat()
                add_audit_log("قفل الحساب", f"تم قفل حساب: {username}", ip=ip, username=username)
            aw_update(COL_USERS, user_id, {"failed_attempts": failed_attempts, "lockout_until": lockout})
            add_audit_log("محاولة دخول فاشلة", f"كلمة سر خاطئة لـ: {username}", ip=ip, username=username)
            return jsonify({"error": "اسم المستخدم أو كلمة السر غير صحيحة",
                            "remaining_attempts": max(0, 3 - failed_attempts)}), 401

        if not is_verified:
            return jsonify({"error": "EMAIL_NOT_VERIFIED", "message": "يرجى تفعيل حسابك أولاً", "username": username}), 403

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        current_country = _get_country(ip)
        session_token = secrets.token_hex(32)

        aw_update(COL_USERS, user_id, {
            "failed_attempts": 0,
            "lockout_until": None,
            "last_user_agent": ua,
            "last_login_ip": ip,
            "last_login_at": now_str,
            "last_country": current_country
        })

        aw_create(COL_ACTIVE_SESSIONS, {
            "user_id": user_id,
            "token": session_token,
            "user_agent": ua,
            "ip": ip,
            "country": current_country,
            "created_at": now_str
        })

        session['user_id'] = user_id
        session['username'] = username
        session['token'] = session_token
        session.permanent = True

        add_audit_log("تسجيل دخول", f"دخول ناجح: {username}", ip=ip, username=username)
        send_login_alert_email(username, ip, ua)

        if last_ua and ua != last_ua and email:
            send_new_device_alert(username, ip, ua, email)
        if last_country and current_country and current_country != last_country and email:
            send_geo_fence_alert(username, ip, last_country, current_country, email)

        is_admin_flag = bool(user.get('is_admin', False))
        return jsonify({"success": True, "username": username, "isAdmin": is_admin_flag})
    except Exception as e:
        print(f"[TITAN] Login error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    username = session.get('username', 'Unknown')
    token = session.get('token')
    if token:
        try:
            sessions = aw_list_query(COL_ACTIVE_SESSIONS, "token", token)
            for s in sessions:
                aw_delete(COL_ACTIVE_SESSIONS, s['$id'])
        except Exception:
            pass
    session.clear()
    add_audit_log("تسجيل خروج", f"خروج: {username}")
    return jsonify({"success": True})


@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    if 'user_id' in session:
        user = find_user_by_id(session['user_id'])
        is_admin_flag = bool(user.get('is_admin', False)) if user else False
        return jsonify({"loggedIn": True, "username": session.get('username', ''), "isAdmin": is_admin_flag})
    return jsonify({"loggedIn": False})


@app.route('/api/auth/heartbeat', methods=['POST'])
def auth_heartbeat():
    if 'user_id' not in session:
        return jsonify({"loggedIn": False}), 401
    session.modified = True
    return jsonify({"loggedIn": True})


@app.route('/api/auth/forgot-password/send', methods=['POST'])
def forgot_password_send():
    data = request.json or {}
    username = data.get('username', '').strip()
    if not username:
        return jsonify({"error": "اسم المستخدم مطلوب"}), 400
    try:
        user = find_user_by_username(username)
        if not user:
            return jsonify({"success": True, "message": "إذا كان الحساب موجوداً سيصل الكود."}), 200
        email = user.get('email')
        if not email:
            return jsonify({"error": "لا يوجد بريد إلكتروني مسجّل لهذا الحساب."}), 400
        otp = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
        expires_at = datetime.datetime.now() + datetime.timedelta(minutes=10)
        _FORGOT_OTP_STORE[username] = {"otp": otp, "expires_at": expires_at}
        body = f"""مرحباً {username}،

طُلب استعادة كلمة السر لحسابك في TITAN.

كود التحقق الخاص بك هو: {otp}

هذا الكود صالح لمدة 10 دقائق فقط.

إذا لم تطلب ذلك، تجاهل هذا البريد.
— فريق TITAN Security"""
        _testmail_send(email, "TITAN - كود استعادة كلمة السر", body)
        add_audit_log("طلب استعادة كلمة السر", f"تم إرسال كود لـ: {username}", username=username)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/auth/forgot-password/verify', methods=['POST'])
def forgot_password_verify():
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
        return jsonify({"error": "انتهت صلاحية الكود."}), 400
    if otp != stored["otp"]:
        return jsonify({"error": "الكود غير صحيح."}), 400
    return jsonify({"success": True})


@app.route('/api/auth/forgot-password/reset', methods=['POST'])
def forgot_password_reset():
    data = request.json or {}
    username = data.get('username', '').strip()
    otp = data.get('otp', '').strip()
    new_password = data.get('new_password', '')
    if not username or not otp or not new_password:
        return jsonify({"error": "البيانات ناقصة"}), 400
    if len(new_password) < 6:
        return jsonify({"error": "كلمة السر قصيرة جداً"}), 400
    stored = _FORGOT_OTP_STORE.get(username)
    if not stored or datetime.datetime.now() > stored["expires_at"]:
        return jsonify({"error": "يرجى إعادة طلب كود التحقق."}), 400
    if otp != stored["otp"]:
        return jsonify({"error": "الكود غير صحيح."}), 400
    try:
        user = find_user_by_username(username)
        if not user:
            return jsonify({"error": "المستخدم غير موجود"}), 404
        aw_update(COL_USERS, user['$id'], {
            "password_hash": hash_password(new_password),
            "failed_attempts": 0,
            "lockout_until": None
        })
        del _FORGOT_OTP_STORE[username]
        add_audit_log("تغيير كلمة السر ✅", f"تم تغيير كلمة سر: {username}", username=username)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/auth/backup-login', methods=['POST'])
def auth_backup_login():
    data = request.json or {}
    username = data.get('username', '').strip()
    code = data.get('code', '').strip().upper()
    if not username or not code:
        return jsonify({"error": "البيانات ناقصة"}), 400
    try:
        user = find_user_by_username(username)
        if not user or not user.get('is_verified'):
            return jsonify({"error": "المستخدم غير موجود أو غير مفعّل"}), 404
        user_id = user['$id']
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        # Find backup code matching user_id and code_hash
        all_codes = aw_list_query(COL_BACKUP_CODES, "user_id", user_id)
        codes = [c for c in all_codes if c.get('code_hash') == code_hash and not c.get('used', True)]
        if not codes:
            return jsonify({"error": "الكود غير صحيح أو مستخدم مسبقاً"}), 401
        aw_update(COL_BACKUP_CODES, codes[0]['$id'], {"used": True})
        session['user_id'] = user_id
        session['username'] = username
        session.permanent = True
        add_audit_log("دخول بكود طوارئ", f"استخدام كود طوارئ: {username}", ip=_get_login_ip(), username=username)
        return jsonify({"success": True, "username": username})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/auth/backup-codes/regenerate', methods=['POST'])
def auth_regenerate_backup_codes():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح لك"}), 401
    user_id = session['user_id']
    username = session['username']
    try:
        existing = aw_list_query(COL_BACKUP_CODES, "user_id", user_id)
        for doc in existing:
            aw_delete(COL_BACKUP_CODES, doc['$id'])
        codes = [''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8)) for _ in range(8)]
        for code in codes:
            aw_create(COL_BACKUP_CODES, {
                "user_id": user_id,
                "code_hash": hashlib.sha256(code.encode()).hexdigest(),
                "used": False
            })
        add_audit_log("توليد أكواد طوارئ جديدة", f"تم توليد أكواد جديدة لـ: {username}", username=username)
        return jsonify({"success": True, "backup_codes": codes})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =====================================================================
# === Vault Routes ===
# =====================================================================

@app.route('/api/vault/setup-password', methods=['POST'])
def setup_vault_password():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    data = request.json or {}
    password = data.get('password', '').strip()
    if len(password) < 4:
        return jsonify({"error": "كلمة سر القبو يجب أن تكون 4 أحرف على الأقل"}), 400
    user = find_user_by_id(user_id)
    if not user:
        return jsonify({"error": "المستخدم غير موجود"}), 404
    if user.get('vault_password_hash'):
        return jsonify({"error": "كلمة سر القبو محددة مسبقاً."}), 409
    aw_update(COL_USERS, user_id, {"vault_password_hash": hash_password(password)})
    add_audit_log("تعيين كلمة سر القبو 🔐", f"المستخدم {session.get('username')} عيّن كلمة سر قبو")
    return jsonify({"success": True})


@app.route('/api/vault/check-password', methods=['GET'])
def check_vault_password():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    user = find_user_by_id(user_id)
    has_password = bool(user and user.get('vault_password_hash'))
    return jsonify({"hasPassword": has_password})


@app.route('/api/vault/load', methods=['POST'])
def load_vault():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    data = request.json or {}
    key = data.get('key')
    if not key: return jsonify({"error": "Missing key"}), 400
    user = find_user_by_id(user_id)
    if not user or not user.get('vault_password_hash'):
        return jsonify({"error": "لم تقم بتعيين كلمة سر للقبو بعد."}), 403
    if not verify_password(key, user['vault_password_hash']):
        add_audit_log("فشل فتح القبو 🚨", f"كلمة سر خاطئة للمستخدم {session.get('username')}")
        return jsonify({"error": "كلمة السر الرئيسية غير صحيحة."}), 401
    vault_file = get_vault_file(user_id)
    if not os.path.exists(vault_file):
        add_audit_log("فتح القبو ✅", f"قبو جديد للمستخدم {session.get('username')}")
        return jsonify({"vault": []})
    try:
        with open(vault_file, 'rb') as f:
            encrypted_data = f.read()
        decrypted_bytes = decrypt_data(encrypted_data, key)
        vault_data = json.loads(decrypted_bytes.decode('utf-8'))
        add_audit_log("فتح القبو ✅", f"تم الوصول لقبو المستخدم {session.get('username')}")
        return jsonify({"vault": vault_data})
    except Exception:
        return jsonify({"error": "كلمة السر الرئيسية غير صحيحة أو الملف معطوب."}), 401


@app.route('/api/vault/save', methods=['POST'])
def save_vault():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    data = request.json or {}
    key = data.get('key')
    vault_list = data.get('vault', [])
    if not key: return jsonify({"error": "Missing key"}), 400
    user = find_user_by_id(user_id)
    if not user or not user.get('vault_password_hash') or not verify_password(key, user['vault_password_hash']):
        return jsonify({"error": "كلمة السر غير صحيحة."}), 401
    try:
        json_str = json.dumps(vault_list).encode('utf-8')
        encrypted_data = encrypt_data(json_str, key)
        vault_file = get_vault_file(user_id)
        with open(vault_file, 'wb') as f:
            f.write(encrypted_data)
        add_audit_log("حفظ القبو 💾", f"تم تحديث {len(vault_list)} عنصر للمستخدم {session.get('username')}")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/vault/backup', methods=['POST'])
def backup_vault():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    vault_file = get_vault_file(user_id)
    if not os.path.exists(vault_file):
        return jsonify({"error": "لا يوجد قبو لتصديره!"}), 400
    try:
        with open(vault_file, 'rb') as f:
            data = f.read()
        add_audit_log("تصدير النسخة الاحتياطية 📦", f"المستخدم {session.get('username')}")
        return send_file(io.BytesIO(data), mimetype='application/octet-stream', as_attachment=True,
                         download_name=f"vault_backup_user{user_id}.titan.bak")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/vault/restore', methods=['POST'])
def restore_vault():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    file = request.files['file']
    try:
        data = file.read()
        vault_file = get_vault_file(user_id)
        with open(vault_file, 'wb') as f:
            f.write(data)
        add_audit_log("استعادة النسخة الاحتياطية 🔄", f"تم استعادة قبو المستخدم {session.get('username')}")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/vault/recovery/setup', methods=['POST'])
def setup_recovery():
    user_id, err = _get_logged_in_user_id()
    if err: return err
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
    recovery_file = get_vault_recovery_file(user_id)
    with open(recovery_file, 'w', encoding='utf-8') as f:
        json.dump({"q1": q1, "q2": q2, "encrypted_key": base64.b64encode(encrypted_key).decode('utf-8')}, f, ensure_ascii=False)
    add_audit_log("إعداد استعادة القبو 🔑", f"المستخدم {session.get('username')} عيّن أسئلة الأمان")
    return jsonify({"success": True})


@app.route('/api/vault/recovery/questions', methods=['GET'])
def get_recovery_questions():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    recovery_file = get_vault_recovery_file(user_id)
    if not os.path.exists(recovery_file):
        return jsonify({"error": "لم تقم بإعداد أسئلة الأمان مسبقاً."}), 400
    with open(recovery_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify({"q1": data["q1"], "q2": data["q2"]})


@app.route('/api/vault/recovery/recover', methods=['POST'])
def recover_vault_key():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    data = request.json or {}
    a1 = data.get('a1', '')
    a2 = data.get('a2', '')
    recovery_file = get_vault_recovery_file(user_id)
    if not os.path.exists(recovery_file):
        return jsonify({"error": "لم يتم إعداد أسئلة الأمان"}), 400
    with open(recovery_file, 'r', encoding='utf-8') as f:
        r_data = json.load(f)
    recovery_pass = a1.strip().lower() + "|" + a2.strip().lower()
    try:
        encrypted_key_bytes = base64.b64decode(r_data["encrypted_key"])
        decrypted_key = decrypt_data(encrypted_key_bytes, recovery_pass)
        add_audit_log("استعادة القبو ✅", f"المستخدم {session.get('username')} استعاد كلمة سر القبو")
        return jsonify({"recovered_key": decrypted_key.decode('utf-8')})
    except Exception:
        add_audit_log("محاولة استعادة فاشلة 🚨", f"إجابات خاطئة للمستخدم {session.get('username')}")
        return jsonify({"error": "الإجابات التي أدخلتها غير صحيحة"}), 401


@app.route('/api/vault/forgot-password', methods=['POST'])
def vault_forgot_password():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    user_id = session['user_id']
    username = session.get('username')
    try:
        user = find_user_by_id(user_id)
        if not user or not user.get('email'):
            return jsonify({"error": "لا يوجد بريد إلكتروني مسجّل."}), 400
        otp = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
        aw_update(COL_USERS, user_id, {"vault_otp_code": otp})
        body = f"""مرحباً {username}،

كود استعادة قبو TITAN الخاص بك: {otp}

هذا الكود للاستخدام مرة واحدة فقط.
— فريق TITAN Security"""
        _testmail_send(user['email'], "TITAN - كود استعادة القبو", body)
        return jsonify({"success": True, "message": "تم إرسال كود الاستعادة على بريدك."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =====================================================================
# === Time-Locked Vault ===
# =====================================================================

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
    try:
        raw = file.read()
        enc = encrypt_data(raw, vault_pass)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        aw_create(COL_VAULT_TIMELOCKED, {
            "user_id": session['user_id'],
            "filename": secure_filename(file.filename or 'file.bin'),
            "enc_data": base64.b64encode(enc).decode('utf-8'),
            "unlock_at": unlock_at,
            "created_at": now
        })
        add_audit_log("رفع ملف زمني", f"ملف: {file.filename} يُفتح في: {unlock_at}", username=session.get('username', ''))
        return jsonify({"success": True, "message": f"تم تشفير الملف. يمكن فتحه بعد: {unlock_at}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/vault/timelocked/list', methods=['GET'])
def vault_timelocked_list():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    try:
        docs = aw_list_query(COL_VAULT_TIMELOCKED, 'user_id', session['user_id'])
        now = datetime.datetime.now()
        files = []
        for r in docs:
            unlock_dt = datetime.datetime.fromisoformat(r['unlock_at'])
            locked = now < unlock_dt
            seconds_left = max(0, int((unlock_dt - now).total_seconds()))
            files.append({"id": r['$id'], "filename": r['filename'], "unlock_at": r['unlock_at'],
                          "created_at": r['created_at'], "locked": locked, "seconds_left": seconds_left})
        return jsonify({"files": files})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/vault/timelocked/download', methods=['POST'])
def vault_timelocked_download():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    data = request.json or {}
    file_id = data.get('id')
    vault_pass = data.get('vault_password', '')
    if not file_id or not vault_pass:
        return jsonify({"error": "البيانات ناقصة"}), 400
    try:
        doc = aw_get(COL_VAULT_TIMELOCKED, file_id)
        if not doc or doc.get('user_id') != session['user_id']:
            return jsonify({"error": "الملف غير موجود"}), 404
        unlock_dt = datetime.datetime.fromisoformat(doc['unlock_at'])
        if datetime.datetime.now() < unlock_dt:
            seconds_left = int((unlock_dt - datetime.datetime.now()).total_seconds())
            return jsonify({"error": "TIME_LOCKED", "seconds_left": seconds_left,
                            "message": f"الملف مقفل. يُفتح في: {doc['unlock_at']}"}), 403
        enc_data = base64.b64decode(doc['enc_data'])
        decrypted = decrypt_data(enc_data, vault_pass)
        buf = io.BytesIO(decrypted)
        buf.seek(0)
        add_audit_log("تحميل ملف زمني", f"تم تحميل: {doc['filename']}", username=session.get('username', ''))
        return send_file(buf, as_attachment=True, download_name=doc['filename'])
    except ValueError:
        return jsonify({"error": "كلمة السر خاطئة أو الملف معطوب"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =====================================================================
# === Security Routes ===
# =====================================================================

@app.route('/api/security/integrity/check', methods=['GET'])
def security_integrity_check():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    app_path = os.path.abspath(__file__)
    try:
        with open(app_path, 'rb') as f:
            current_hash = hashlib.sha256(f.read()).hexdigest()
        docs = aw_list_query(COL_INTEGRITY, "file_path", app_path)
        if not docs:
            return jsonify({"intact": True, "message": "لا يوجد baseline محفوظ بعد."})
        stored_hash = docs[0]['hash']
        intact = current_hash == stored_hash
        return jsonify({
            "intact": intact,
            "stored_hash": stored_hash,
            "current_hash": current_hash,
            "message": "سلامة النظام مؤكدة ✅" if intact else "تحذير: تم اكتشاف تعديل في ملف النظام! 🚨"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/security/integrity/reset', methods=['POST'])
def security_integrity_reset():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    app_path = os.path.abspath(__file__)
    try:
        with open(app_path, 'rb') as f:
            new_hash = hashlib.sha256(f.read()).hexdigest()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        existing = aw_list_query(COL_INTEGRITY, "file_path", app_path)
        for doc in existing:
            aw_delete(COL_INTEGRITY, doc['$id'])
        aw_create(COL_INTEGRITY, {"file_path": app_path, "hash": new_hash, "set_at": now})
        add_audit_log("Integrity Baseline Reset", f"تم إعادة تعيين baseline بواسطة: {session.get('username', '')}")
        return jsonify({"success": True, "message": "تم تحديث baseline بنجاح"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/security/panic', methods=['POST'])
def security_panic():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    user_id = session['user_id']
    username = session.get('username', '')
    try:
        vault_file = get_vault_file(user_id)
        nuked = False
        if os.path.exists(vault_file):
            random_key = Fernet.generate_key()
            f_obj = Fernet(random_key)
            with open(vault_file, 'rb') as vf:
                data = vf.read()
            with open(vault_file, 'wb') as vf:
                vf.write(f_obj.encrypt(data))
            del random_key, f_obj
            nuked = True
        tl_docs = aw_list_query(COL_VAULT_TIMELOCKED, "user_id", user_id)
        for doc in tl_docs:
            aw_delete(COL_VAULT_TIMELOCKED, doc['$id'])
        sessions = aw_list_query(COL_ACTIVE_SESSIONS, "user_id", user_id)
        for s in sessions:
            aw_delete(COL_ACTIVE_SESSIONS, s['$id'])
        session.clear()
        add_audit_log("PANIC BUTTON PRESSED", f"تم تفعيل زر الطوارئ بواسطة: {username}", username=username)
        _send_email_async("TITAN PANIC – تم تفعيل زر الانتحار!",
                          f"تم تفعيل زر الانتحار بواسطة المستخدم: {username}")
        return jsonify({"success": True, "nuked": nuked, "message": "تم تدمير البيانات بشكل آمن."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/security/logs', methods=['GET'])
def security_logs_api():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    limit = min(int(request.args.get('limit', 50)), 200)
    try:
        url = _aw_url(f"/databases/{APPWRITE_DB_ID}/collections/{COL_SECURITY_LOGS}/documents")
        r = requests.get(url, headers=_aw_headers(),
                         params={"queries[]": [f'limit({limit})', 'orderDesc("$createdAt")']}, timeout=10)
        r.raise_for_status()
        docs = r.json().get('documents', [])
        logs = [{"time": d.get('time'), "action": d.get('action'), "details": d.get('details'),
                 "ip": d.get('ip'), "username": d.get('username')} for d in docs]
        return jsonify({"logs": logs})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =====================================================================
# === Admin Routes ===
# =====================================================================

@app.route('/api/admin/users', methods=['GET'])
def admin_users():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    user = find_user_by_id(session['user_id'])
    if not user or not user.get('is_admin'):
        return jsonify({"error": "ليس لديك صلاحية"}), 403
    try:
        users = aw_list(COL_USERS)
        result = []
        for u in users:
            result.append({
                "id": u['$id'],
                "username": u.get('username'),
                "email": u.get('email'),
                "is_verified": u.get('is_verified'),
                "is_admin": u.get('is_admin'),
                "created_at": u.get('created_at'),
                "last_login_at": u.get('last_login_at'),
                "last_login_ip": u.get('last_login_ip'),
            })
        return jsonify({"users": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/delete-user', methods=['POST'])
def admin_delete_user():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    admin = find_user_by_id(session['user_id'])
    if not admin or not admin.get('is_admin'):
        return jsonify({"error": "ليس لديك صلاحية"}), 403
    data = request.json or {}
    target_id = data.get('user_id')
    if not target_id:
        return jsonify({"error": "user_id مطلوب"}), 400
    try:
        aw_delete(COL_USERS, target_id)
        add_audit_log("حذف مستخدم", f"تم حذف المستخدم: {target_id}", username=session.get('username'))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/wipe', methods=['POST'])
def admin_wipe():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401
    admin = find_user_by_id(session['user_id'])
    if not admin or not admin.get('is_admin'):
        return jsonify({"error": "ليس لديك صلاحية"}), 403
    add_audit_log("SYSTEM WIPE", f"تم تفعيل إعادة ضبط المصنع بواسطة: {session.get('username')}")
    return jsonify({"success": True, "message": "تم تسجيل طلب المسح."})


# =====================================================================
# === Encryption / Tools Routes ===
# =====================================================================

@app.route('/api/encrypt', methods=['POST'])
def encrypt_route():
    data = request.json or {}
    text = data.get('text', '')
    password = data.get('password', '')
    if not text or not password:
        return jsonify({"error": "النص وكلمة السر مطلوبان"}), 400
    try:
        encrypted = encrypt_data(text.encode('utf-8'), password)
        result = base64.b64encode(encrypted).decode('utf-8')
        add_audit_log("تشفير نص", f"تم تشفير {len(text)} حرف")
        return jsonify({"encrypted": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/decrypt', methods=['POST'])
def decrypt_route():
    data = request.json or {}
    encrypted_b64 = data.get('encrypted', '')
    password = data.get('password', '')
    if not encrypted_b64 or not password:
        return jsonify({"error": "البيانات المشفرة وكلمة السر مطلوبتان"}), 400
    try:
        encrypted_bytes = base64.b64decode(encrypted_b64)
        decrypted = decrypt_data(encrypted_bytes, password)
        add_audit_log("فك تشفير نص", "تم فك تشفير بيانات")
        return jsonify({"decrypted": decrypted.decode('utf-8')})
    except ValueError as e:
        return jsonify({"error": str(e)}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/generate-password', methods=['POST'])
def generate_password():
    data = request.json or {}
    length = min(int(data.get('length', 16)), 128)
    use_upper = data.get('uppercase', True)
    use_lower = data.get('lowercase', True)
    use_digits = data.get('digits', True)
    use_symbols = data.get('symbols', True)
    chars = ''
    if use_upper: chars += string.ascii_uppercase
    if use_lower: chars += string.ascii_lowercase
    if use_digits: chars += string.digits
    if use_symbols: chars += string.punctuation
    if not chars: chars = string.ascii_letters + string.digits
    password = ''.join(secrets.choice(chars) for _ in range(length))
    return jsonify({"password": password})


@app.route('/api/hash', methods=['POST'])
def hash_route():
    data = request.json or {}
    text = data.get('text', '')
    algorithm = data.get('algorithm', 'sha256').lower()
    if not text:
        return jsonify({"error": "النص مطلوب"}), 400
    algos = {
        'md5': hashlib.md5,
        'sha1': hashlib.sha1,
        'sha256': hashlib.sha256,
        'sha512': hashlib.sha512,
    }
    if algorithm not in algos:
        return jsonify({"error": f"خوارزمية غير مدعومة: {algorithm}"}), 400
    result = algos[algorithm](text.encode()).hexdigest()
    add_audit_log(f"تحويل Hash ({algorithm.upper()})", f"تم حساب {algorithm} لـ {len(text)} حرف")
    return jsonify({"hash": result, "algorithm": algorithm})


@app.route('/api/rsa/generate', methods=['POST'])
def rsa_generate():
    try:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
        add_audit_log("توليد مفاتيح RSA 🔑", "تم توليد زوج مفاتيح RSA-2048")
        return jsonify({"private_key": private_pem, "public_key": public_pem})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/base64/encode', methods=['POST'])
def base64_encode():
    data = request.json or {}
    text = data.get('text', '')
    result = base64.b64encode(text.encode('utf-8')).decode('utf-8')
    return jsonify({"result": result})


@app.route('/api/base64/decode', methods=['POST'])
def base64_decode():
    data = request.json or {}
    text = data.get('text', '')
    try:
        result = base64.b64decode(text).decode('utf-8')
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# =====================================================================
# === Burn Notes ===
# =====================================================================

@app.route('/api/burn-note/create', methods=['POST'])
def create_burn_note():
    data = request.json or {}
    message = data.get('message', '')
    if not message:
        return jsonify({"error": "الرسالة مطلوبة"}), 400
    note_id = secrets.token_urlsafe(16)
    BURN_NOTES[note_id] = message
    add_audit_log("إنشاء رسالة مدمرة 🔥", f"تم إنشاء رسالة ذاتية التدمير")
    return jsonify({"id": note_id, "url": f"/burn/{note_id}"})


@app.route('/burn/<note_id>', methods=['GET'])
def view_burn_note(note_id):
    note = BURN_NOTES.pop(note_id, None)
    if note:
        add_audit_log("قراءة رسالة مدمرة 🔥", f"تم قراءة وتدمير الرسالة")
        return render_template_string(f'''
        <!DOCTYPE html><html lang="ar" dir="rtl">
        <head><meta charset="UTF-8"><title>TITAN - رسالة مدمرة</title>
        <style>body{{background:#050505;color:#22c55e;font-family:monospace;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:20px;box-sizing:border-box;}}
        .box{{background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3);border-radius:12px;padding:2rem;max-width:600px;width:100%;}}
        h2{{color:#22c55e;}}p{{color:#9ca3af;font-size:0.8rem;}}pre{{white-space:pre-wrap;word-break:break-all;color:#e2e8f0;background:rgba(0,0,0,0.5);padding:1rem;border-radius:8px;border:1px solid rgba(34,197,94,0.2);}}
        </style></head>
        <body><div class="box"><h2>🔥 رسالة مدمرة</h2><pre>{note}</pre><p>⚠️ تم تدمير هذه الرسالة الآن. لن تظهر مرة أخرى.</p></div></body></html>
        ''')
    else:
        return '''<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>غير موجودة</title></head>
        <body style="background:#050505;color:#ef4444;font-family:sans-serif;text-align:center;padding-top:100px;">
        <div style="font-size:60px;margin-bottom:20px;">🕳️</div>
        <h2>الرسالة غير متوفرة!</h2>
        <p style="color:#9ca3af;">الرابط غير صالح، أو أن الرسالة تم الإطلاع عليها وتدميرها مسبقاً.</p>
        </body></html>''', 404


# =====================================================================
# === Image / Steganography Routes ===
# =====================================================================

@app.route('/api/image/remove-metadata', methods=['POST'])
def remove_metadata_route():
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "الملف مطلوب"}), 400
    try:
        result = remove_image_metadata(file.read())
        add_audit_log("إزالة ميتابيانات صورة 🖼️", f"تم تنظيف {file.filename}")
        return send_file(io.BytesIO(result), mimetype='image/png', as_attachment=True,
                         download_name=f"clean_{file.filename}")
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/image/steganography/encode', methods=['POST'])
def stego_encode():
    file = request.files.get('file')
    secret = request.form.get('secret', '')
    if not file or not secret:
        return jsonify({"error": "الصورة والنص المخفي مطلوبان"}), 400
    try:
        result = lsb_encode(file.read(), secret)
        add_audit_log("إخفاء في صورة 🖼️", f"تم إخفاء بيانات في {file.filename}")
        return send_file(io.BytesIO(result), mimetype='image/png', as_attachment=True,
                         download_name=f"stego_{file.filename}.png")
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/image/steganography/decode', methods=['POST'])
def stego_decode():
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "الصورة مطلوبة"}), 400
    try:
        result = lsb_decode(file.read())
        add_audit_log("استخراج من صورة 🖼️", f"تم استخراج بيانات من {file.filename}")
        return jsonify({"hidden_data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/osint/image', methods=['POST'])
def osint_image_route():
    try:
        file = request.files['file']
        data = extract_exif_data(file.read())
        add_audit_log("استخبارات صور (OSINT)", f"تم استخراج بيانات من {file.filename}")
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# =====================================================================
# === Audio Routes ===
# =====================================================================

@app.route('/api/audio/stego/encode', methods=['POST'])
def audio_stego_encode():
    file = request.files['file']
    text = request.form['text']
    try:
        processed_data = wave_lsb_encode(file.read(), text, file.filename)
        add_audit_log("إخفاء في الصوت 🎵", f"تم إخفاء بيانات في {file.filename}")
        mimetype = 'audio/mpeg' if file.filename.lower().endswith('.mp3') else 'audio/wav'
        return send_file(io.BytesIO(processed_data), mimetype=mimetype, as_attachment=True,
                         download_name="stego_" + file.filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/audio/stego/decode', methods=['POST'])
def audio_stego_decode():
    file = request.files['file']
    try:
        decoded_text = wave_lsb_decode(file.read(), file.filename)
        add_audit_log("استخراج من الصوت 🎵", f"محاولة فك تشفير {file.filename}")
        return jsonify({"success": True, "hidden_data": decoded_text})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# =====================================================================
# === PDF Routes ===
# =====================================================================

@app.route('/api/pdf/clean', methods=['POST'])
def pdf_clean_route():
    file = request.files['file']
    try:
        processed_data = clean_pdf_metadata(file.read())
        add_audit_log("تنظيف PDF 🧹", f"إزالة ميتابيانات {file.filename}")
        return send_file(io.BytesIO(processed_data), mimetype='application/pdf', as_attachment=True,
                         download_name="clean_" + file.filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# =====================================================================
# === Network / Intelligence Routes ===
# =====================================================================

@app.route('/api/intel/dns-leak', methods=['GET'])
def dns_leak_route():
    return jsonify(get_dns_leak_info())


@app.route('/api/intel/shodan', methods=['POST'])
def shodan_intel_route():
    ip = request.json.get('ip', '')
    return jsonify(get_shodan_intel(ip))


@app.route('/api/network/scan', methods=['GET'])
def scan_network_route():
    devices = scan_local_network()
    add_audit_log("رادار الشبكة المحلية", f"تم العثور على {len(devices)} جهاز متصل")
    return jsonify(devices)


@app.route('/api/port-scan', methods=['POST'])
def port_scan():
    data = request.json or {}
    target_ip = data.get('ip', '127.0.0.1')
    open_ports = []
    common_ports = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 3306, 3389, 5432, 6379, 8080, 8443, 27017]
    def check_port(port):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((target_ip, port))
            sock.close()
            return port if result == 0 else None
        except Exception:
            return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(check_port, common_ports))
    open_ports = [p for p in results if p]
    add_audit_log("فحص المنافذ", f"فحص {target_ip} - {len(open_ports)} منافذ مفتوحة")
    return jsonify({"open_ports": open_ports, "target": target_ip})


@app.route('/api/scan/email', methods=['POST'])
def scan_email_route():
    email = request.json.get('email', '')
    res = check_email_intelligence(email)
    add_audit_log("فحص إيميل (IPQualityScore)", f"تم فحص البريد: {email}")
    return jsonify(res)


@app.route('/api/scan/phone', methods=['POST'])
def scan_phone_route():
    phone = request.json.get('phone', '')
    res = check_phone_intelligence(phone)
    add_audit_log("فحص رقم هاتف", f"تم فحص: {phone}")
    return jsonify(res)


@app.route('/api/scan/url', methods=['POST'])
def scan_url_route():
    url = request.json.get('url', '')
    res = check_url_intelligence(url)
    add_audit_log("فحص رابط", f"تم فحص: {url[:100]}")
    return jsonify(res)


@app.route('/api/scan/leaked', methods=['POST'])
def scan_leaked_route():
    data = request.json or {}
    email = data.get('email', '')
    password = data.get('password', '')
    res = check_leaked_emailpass(email, password)
    add_audit_log("فحص تسريب بيانات", f"تم فحص تسريب لـ: {email}")
    return jsonify(res)


@app.route('/api/network/sniff', methods=['GET'])
def packet_sniff():
    try:
        import socket as _socket
        duration = int(request.args.get('duration', 4))
        packets_info = []
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_RAW, _socket.IPPROTO_IP)
            local_ip = _socket.gethostbyname(_socket.gethostname())
            s.bind((local_ip, 0))
            s.setsockopt(_socket.IPPROTO_IP, _socket.IP_HDRINCL, 1)
            try: s.ioctl(_socket.SIO_RCVALL, _socket.RCVALL_ON)
            except Exception: pass
            s.settimeout(0.5)
            start = time.time()
            while time.time() - start < duration and len(packets_info) < 30:
                try:
                    raw, addr = s.recvfrom(65535)
                    iph = raw[:20]
                    proto = iph[9]
                    src_ip = '.'.join(str(b) for b in iph[12:16])
                    dst_ip = '.'.join(str(b) for b in iph[16:20])
                    proto_name = {1: 'ICMP', 6: 'TCP', 17: 'UDP'}.get(proto, f'IP({proto})')
                    packets_info.append({'src': src_ip, 'dst': dst_ip, 'proto': proto_name, 'size': len(raw)})
                except _socket.timeout:
                    continue
            try: s.ioctl(_socket.SIO_RCVALL, _socket.RCVALL_OFF)
            except Exception: pass
            s.close()
            add_audit_log("Packet Sniffer 📡", f"تم التقاط {len(packets_info)} حزمة")
        except PermissionError:
            return jsonify({'error': 'يحتاج صلاحية Administrator', 'packets': []}), 403
        return jsonify({'packets': packets_info})
    except Exception as e:
        return jsonify({'error': str(e), 'packets': []}), 500


# =====================================================================
# === QR Code Routes ===
# =====================================================================

@app.route('/api/qr/generate', methods=['POST'])
def qr_generate():
    try:
        data = request.json or {}
        text = data.get('text', '')
        password = data.get('password', '')
        if not text: return jsonify({'error': 'النص مطلوب'}), 400
        if password:
            salt = os.urandom(16)
            key = derive_key(password, salt)
            f = Fernet(key)
            payload = base64.urlsafe_b64encode(salt + f.encrypt(text.encode())).decode()
            payload = 'ENC:' + payload
        else:
            payload = text
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
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
        from PIL import Image as PILImage
        try:
            from pyzbar import pyzbar as _pyzbar
            _use_pyzbar = True
        except ImportError:
            _use_pyzbar = False
        img = PILImage.open(file)
        if _use_pyzbar:
            decoded = _pyzbar.decode(img)
        else:
            import cv2, numpy as np
            img_np = np.array(img.convert('RGB'))
            detector = cv2.QRCodeDetector()
            val, _, _ = detector.detectAndDecode(img_np)
            decoded = [type('obj', (object,), {'data': val.encode()})() ] if val else []
        if not decoded: return jsonify({'error': 'لم يتم التعرف على QR في الصورة'}), 400
        payload = decoded[0].data.decode('utf-8')
        if payload.startswith('ENC:') and password:
            raw = base64.urlsafe_b64decode(payload[4:])
            salt = raw[:16]
            enc = raw[16:]
            key = derive_key(password, salt)
            f = Fernet(key)
            text = f.decrypt(enc).decode('utf-8')
        else:
            text = payload
        return jsonify({'text': text})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


# =====================================================================
# === Fake Identity ===
# =====================================================================

@app.route('/api/fake-identity', methods=['GET'])
def fake_identity_route():
    try:
        from faker import Faker
        lang = request.args.get('lang', 'ar_SA')
        SUPPORTED_LANGS = {'ar': 'ar_SA', 'en': 'en_US', 'fr': 'fr_FR', 'de': 'de_DE', 'es': 'es_ES'}
        faker_locale = SUPPORTED_LANGS.get(lang, lang)
        try:
            fake = Faker(faker_locale)
        except Exception:
            fake = Faker('en_US')
        fake_en = Faker('en_US')
        name = fake.name()
        username_base = fake_en.user_name()
        password_fake = fake_en.password(length=12, special_chars=True, digits=True, upper_case=True)
        dob = fake.date_of_birth(minimum_age=18, maximum_age=65)
        age = (datetime.date.today() - dob).days // 365
        country_code = fake_en.country_code()
        try:
            address_str = fake.address()
        except Exception:
            address_str = fake_en.address()
        try:
            zip_code = fake.postcode()
        except Exception:
            zip_code = fake_en.postcode()
        try:
            phone = fake.phone_number()
        except Exception:
            phone = fake_en.phone_number()
        company = fake_en.company()
        job = fake_en.job()
        colors = ["أشقر", "أسمر", "بني فاتح", "رمادي", "أسود"]
        color = random.choice(colors)
        id_num = ''.join([str(random.randint(0,9)) for _ in range(10)])
        national_id = f"{country_code}-{id_num}"
        return jsonify({
            'name': name, 'username': username_base, 'password': password_fake,
            'dob': str(dob), 'age': age, 'gender': random.choice(["ذكر", "أنثى"]),
            'national_id': national_id, 'address': address_str, 'zip_code': zip_code,
            'geo': f"{fake_en.latitude()}, {fake_en.longitude()}", 'country_code': country_code,
            'phone': phone, 'email': fake_en.email(), 'company': company, 'job': job,
            'height': f"{random.randint(150, 195)} cm", 'weight': f"{random.randint(50, 100)} kg",
            'blood_type': random.choice(["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]),
            'color': color, 'vehicle': fake_en.word().title() + ' ' + str(random.randint(2000, 2024)),
            'cc_type': fake_en.credit_card_provider(),
            'credit_card': fake_en.credit_card_number(card_type='visa' if random.random() > 0.5 else 'mastercard'),
            'cc_expire': fake_en.credit_card_expire(), 'cc_cvv': fake_en.credit_card_security_code(),
            'website': f'https://www.{fake_en.domain_name()}', 'user_agent': fake_en.user_agent(),
            'uuid': fake_en.uuid4(),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =====================================================================
# === Dashboard Stats ===
# =====================================================================

@app.route('/api/dashboard/stats', methods=['GET'])
def dashboard_stats():
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        net = psutil.net_io_counters()
        local_ip = socket.gethostbyname(socket.gethostname())
        try:
            pub_ip_data = requests.get('https://api.ipify.org?format=json', timeout=3).json()
            public_ip = pub_ip_data.get('ip', 'غير متاح')
        except Exception:
            public_ip = 'غير متاح'
        return jsonify({
            'cpu_percent': cpu, 'ram_used_gb': round(mem.used / 1024**3, 2),
            'ram_total_gb': round(mem.total / 1024**3, 2), 'ram_percent': mem.percent,
            'disk_used_gb': round(disk.used / 1024**3, 2), 'disk_total_gb': round(disk.total / 1024**3, 2),
            'disk_percent': disk.percent, 'net_sent_mb': round(net.bytes_sent / 1024**2, 2),
            'net_recv_mb': round(net.bytes_recv / 1024**2, 2), 'local_ip': local_ip,
            'public_ip': public_ip, 'vault_items': 0, 'burn_notes': len(BURN_NOTES),
            'audit_count': len(AUDIT_LOGS), 'recent_logs': AUDIT_LOGS[:5],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =====================================================================
# === Canary Honeypot ===
# =====================================================================

@app.route('/passwords.txt', methods=['GET'])
def canary_honeypot():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '')
    ua = request.headers.get('User-Agent', '')
    send_canary_alert(ip, ua)
    add_audit_log("🍯 HONEYPOT TRIGGERED", f"IP: {ip}", ip=ip)
    return "# TITAN System Credentials\nadmin:T1TAN_S3CR3T_2025!\nroot:P@ssw0rd123\n", 200, {'Content-Type': 'text/plain'}


# =====================================================================
# === USB & FIM Defense ===
# =====================================================================

USB_MONITOR_ACTIVE = False
USB_MONITOR_THREAD = None
LAST_DRIVES = set()


def get_current_drives():
    drives = set()
    try:
        for p in psutil.disk_partitions():
            if 'removable' in p.opts.lower() or p.fstype == '':
                drives.add(p.device)
    except Exception:
        pass
    return drives


def usb_monitor_listener():
    global USB_MONITOR_ACTIVE, LAST_DRIVES
    LAST_DRIVES = get_current_drives()
    suspicious_files = ['autorun.inf']
    suspicious_exts = ['.vbs', '.bat', '.ps1', '.exe', '.cmd']
    while USB_MONITOR_ACTIVE:
        current_drives = get_current_drives()
        new_drives = current_drives - LAST_DRIVES
        for drive in new_drives:
            with app.app_context():
                add_audit_log("🛡️ حارس منافذ USB", f"تم رصد توصيل قرص جديد: {drive}")
            try:
                if os.path.exists(drive):
                    for f in os.listdir(drive):
                        f_lower = f.lower()
                        if f_lower in suspicious_files or any(f_lower.endswith(ext) for ext in suspicious_exts):
                            with app.app_context():
                                add_audit_log("🚨 تهديد USB محتمل", f"ملف مشبوه في {drive}: {f}")
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
            add_audit_log("تفعيل حارس USB", "تم تفعيل المراقبة الفورية")
        return jsonify({"status": "active"})
    else:
        USB_MONITOR_ACTIVE = False
        add_audit_log("إيقاف حارس USB", "تم إيقاف المراقبة")
        return jsonify({"status": "inactive"})


FIM_ACTIVE = False
FIM_THREAD = None
FIM_TARGET_FILE = ""
FIM_TARGET_HASH = ""


def fim_listener():
    global FIM_ACTIVE, FIM_TARGET_FILE, FIM_TARGET_HASH
    while FIM_ACTIVE:
        if FIM_TARGET_FILE and os.path.exists(FIM_TARGET_FILE):
            try:
                with open(FIM_TARGET_FILE, 'rb') as f:
                    current_hash = hashlib.sha256(f.read()).hexdigest()
                if current_hash != FIM_TARGET_HASH:
                    with app.app_context():
                        add_audit_log("⚠️ اختراق تكامل الملفات (FIM)", f"تغيير في: {FIM_TARGET_FILE}")
                    FIM_TARGET_HASH = current_hash
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
            add_audit_log("تفعيل مراقب التكامل (FIM)", f"بدأت مراقبة: {os.path.basename(target)}")
            return jsonify({"status": "active"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        FIM_ACTIVE = False
        add_audit_log("إيقاف مراقب التكامل", "تم إيقاف المراقبة")
        return jsonify({"status": "inactive"})


# =====================================================================
# === Burn Chat ===
# =====================================================================

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
    to_deliver = [m for m in messages if m['sender'] != requester]
    remaining = [m for m in messages if m['sender'] == requester]
    BURN_CHAT_ROOMS[room_id] = remaining
    if to_deliver:
        add_audit_log("Burn Chat 🔥", f"تم قراءة وتدمير {len(to_deliver)} رسالة في [{room_id}]")
    return jsonify({"messages": to_deliver})


# =====================================================================
# === Main Page ===
# =====================================================================

# نستبقي HTML الأصلي من app.py الأصلي
# هنا سيُعرض نفس الـ HTML الموجود في الكود الأصلي
# لأن الـ HTML كبير جداً (6000+ سطر)، نستخدم نفس الـ template من الكود الأصلي

HTML_TEMPLATE = """

<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TITAN | التشفير والأمن السيبراني</title>
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIj48cmVjdCB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgcng9IjE4IiBmaWxsPSIjMGQwZDFhIi8+PHRleHQgeD0iNTAiIHk9IjY4IiBmb250LWZhbWlseT0iQXJpYWwgQmxhY2ssc2Fucy1zZXJpZiIgZm9udC1zaXplPSI1NCIgZm9udC13ZWlnaHQ9IjkwMCIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZmlsbD0idXJsKCNnKSI+VEFOPC90ZXh0PjxkZWZzPjxsaW5lYXJHcmFkaWVudCBpZD0iZyIgeDE9IjAlIiB5MT0iMCUiIHgyPSIxMDAlIiB5Mj0iMTAwJSI+PHN0b3Agb2Zmc2V0PSIwJSIgc3RvcC1jb2xvcj0iI2MwODRmYyIvPjxzdG9wIG9mZnNldD0iMTAwJSIgc3RvcC1jb2xvcj0iIzdjM2FlZCIvPjwvbGluZWFyR3JhZGllbnQ+PC9kZWZzPjwvc3ZnPg==">
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
                    <div style="margin-bottom:1.5rem;">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                            <label style="display:block;color:#9ca3af;font-size:0.78rem;letter-spacing:0.05em;">كلمة السر</label>
                            <div>
                                <a href="#" onclick="switchAuthTab('backup'); return false;" style="color:#22c55e;font-size:0.75rem;text-decoration:none;transition:color 0.2s;margin-left:10px;" onmouseover="this.style.color='#4ade80'" onmouseout="this.style.color='#22c55e'">دخول بكود طوارئ</a>
                                <a href="#" onclick="switchAuthTab('forgot'); return false;" style="color:#a855f7;font-size:0.75rem;text-decoration:none;transition:color 0.2s;" onmouseover="this.style.color='#e9d5ff'" onmouseout="this.style.color='#a855f7'">نسيت كلمة السر؟</a>
                            </div>
                        </div>
                        <input id="auth-login-pass" type="password" placeholder="كلمة السر..." autocomplete="current-password" style="width:100%;box-sizing:border-box;padding:0.85rem 1rem;background:rgba(15,15,40,0.9);border:1px solid rgba(139,92,246,0.3);border-radius:12px;color:white;font-size:0.95rem;outline:none;transition:border-color 0.2s;font-family:Tajawal,sans-serif;" onfocus="this.style.borderColor='#a855f7'" onblur="this.style.borderColor='rgba(139,92,246,0.3)'">
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
                    <div id="auth-reg-error" style="display:none;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.4);border-radius:10px;padding:0.7rem 1rem;color:#f87171;font-size:0.82rem;margin-bottom:1rem;text-align:center;"></div>
                    <div id="auth-reg-success" style="display:none;background:rgba(34,197,94,0.15);border:1px solid rgba(34,197,94,0.4);border-radius:10px;padding:0.7rem 1rem;color:#4ade80;font-size:0.82rem;margin-bottom:1rem;text-align:center;"></div>
                    <button onclick="doRegister()" style="width:100%;padding:0.9rem;background:linear-gradient(135deg,#7c3aed,#5b21b6);border:none;border-radius:12px;color:white;font-size:1rem;font-weight:700;cursor:pointer;transition:all 0.2s;box-shadow:0 0 20px rgba(124,58,237,0.4);font-family:Tajawal,sans-serif;" onmouseover="this.style.boxShadow='0 0 35px rgba(124,58,237,0.7)'" onmouseout="this.style.boxShadow='0 0 20px rgba(124,58,237,0.4)'" id="auth-reg-btn">
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

                <!-- Backup Login Form -->
                <div id="auth-backup-form" style="display:none;">
                    <div style="text-align:center;margin-bottom:1.5rem;">
                        <div style="font-size:2.5rem;margin-bottom:0.5rem;">🔑</div>
                        <h3 style="color:#22c55e;font-weight:700;">الدخول بكود الطوارئ</h3>
                        <p style="color:#9ca3af;font-size:0.8rem;margin-top:0.5rem;">أدخل اسم المستخدم وكود الطوارئ لمرة واحدة.</p>
                    </div>
                    <div style="margin-bottom:1rem;">
                        <label style="display:block;color:#9ca3af;font-size:0.78rem;margin-bottom:6px;">اسم المستخدم</label>
                        <input id="auth-backup-user" type="text" placeholder="اسم المستخدم..." style="width:100%;box-sizing:border-box;padding:0.85rem 1rem;background:rgba(15,15,40,0.9);border:1px solid rgba(34,197,94,0.3);border-radius:12px;color:white;font-size:0.95rem;outline:none;font-family:Tajawal,sans-serif;" onfocus="this.style.borderColor='#22c55e'" onblur="this.style.borderColor='rgba(34,197,94,0.3)'">
                    </div>
                    <div style="margin-bottom:1.5rem;">
                        <label style="display:block;color:#9ca3af;font-size:0.78rem;margin-bottom:6px;">كود الطوارئ</label>
                        <input id="auth-backup-code" type="text" placeholder="XXXXXXXX" style="width:100%;box-sizing:border-box;padding:1rem;background:rgba(15,15,40,0.9);border:1px solid rgba(34,197,94,0.3);border-radius:12px;color:white;font-size:1.8rem;outline:none;font-family:monospace;text-align:center;letter-spacing:0.5em;" onfocus="this.style.borderColor='#22c55e'" onblur="this.style.borderColor='rgba(34,197,94,0.3)'">
                    </div>
                    <div id="auth-backup-error" style="display:none;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.4);border-radius:10px;padding:0.7rem 1rem;color:#f87171;font-size:0.82rem;margin-bottom:1rem;text-align:center;"></div>
                    <button onclick="doBackupLogin()" style="width:100%;padding:0.9rem;background:linear-gradient(135deg,#22c55e,#16a34a);border:none;border-radius:12px;color:white;font-size:1rem;font-weight:700;cursor:pointer;font-family:Tajawal,sans-serif;box-shadow:0 0 20px rgba(34,197,94,0.4);">
                        دخول بالكود 🛡️
                    </button>
                    <button onclick="switchAuthTab('login')" style="width:100%;margin-top:0.75rem;background:transparent;border:none;color:#9ca3af;font-size:0.85rem;cursor:pointer;text-decoration:underline;">إلغاء والعودة</button>
                </div>

                <!-- Footer -->
                <div style="text-align:center;margin-top:1.5rem;color:#374151;font-size:0.72rem;letter-spacing:0.05em;">
                    🛡️ TITAN SECURITY PROTOCOL — ALL DATA ENCRYPTED
                </div>
            </div>
        </div>

        <style>
            @keyframes orbFloat { 0%{transform:translate(0,0) scale(1);} 100%{transform:translate(3%,5%) scale(1.08);} }
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
        <div class="container mx-auto px-4 py-12 max-w-3xl relative z-10">
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
            <div class="mb-8 flex flex-wrap justify-center gap-2 p-2 bg-slate-900/40 rounded-xl border border-slate-700/50">
                <button onclick="showTab('dash')" id="btn-dash" class="px-3 py-1.5 rounded-lg hover:bg-purple-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-purple-500/30"><span>📊</span> الإحصائيات</button>
                <button onclick="showTab('pass')" id="btn-pass" class="px-3 py-1.5 rounded-lg hover:bg-purple-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-purple-500/30"><span>🔑</span> كلمات السر</button>
                <button onclick="showTab('vault'); checkVaultPasswordSetup();" id="btn-vault" class="px-3 py-1.5 rounded-lg hover:bg-yellow-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-yellow-500/30"><span>🗄️</span> القبو</button>
                <button onclick="showTab('crypt')" id="btn-crypt" class="px-3 py-1.5 rounded-lg hover:bg-blue-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-blue-500/30"><span>🔐</span> التشفير</button>
                <button onclick="showTab('suite')" id="btn-suite" class="px-3 py-1.5 rounded-lg hover:bg-purple-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-purple-500/30"><span>🛠️</span> الأدوات الذكية</button>
                <button onclick="showTab('tools')" id="btn-tools" class="px-3 py-1.5 rounded-lg hover:bg-purple-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-purple-500/30"><span>🌐</span> تتبع IP</button>
                <button onclick="showTab('audio')" id="btn-audio" class="px-3 py-1.5 rounded-lg hover:bg-orange-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-orange-500/30"><span>🎵</span> إخفاء صوتي</button>
                <button onclick="showTab('qr')" id="btn-qr" class="px-3 py-1.5 rounded-lg hover:bg-green-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-green-500/30"><span>🔳</span> QR آمن</button>
                <button onclick="showTab('identity')" id="btn-identity" class="px-3 py-1.5 rounded-lg hover:bg-cyan-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-cyan-500/30"><span>🪪</span> هوية وهمية</button>
                <button onclick="showAdminTab()" id="btn-admin" class="hidden px-3 py-1.5 rounded-lg text-xs font-bold text-white transition-all items-center gap-1.5 border border-red-600/40 hover:bg-red-600/20 bg-red-600/10"><span>👑</span> لوحة الإدارة</button>
            </div>

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
            </div>

            <div id="security-section" class="hidden"></div> <!-- Security section completely removed per user request -->


            <!-- Backup Codes Modal -->
            <div id="backup-codes-modal" style="display:none;position:fixed;inset:0;z-index:999999;background:rgba(0,0,0,0.85);align-items:center;justify-content:center;">
                <div style="background:#0a0a1e;border:1px solid rgba(34,197,94,0.4);border-radius:20px;padding:2rem;max-width:420px;width:90%;box-shadow:0 0 60px rgba(34,197,94,0.2);">
                    <div style="text-align:center;margin-bottom:1.5rem;">
                        <div style="font-size:2rem">🔑</div>
                        <h3 style="color:#4ade80;font-weight:700;margin:0.5rem 0;">أكواد الطوارئ الخاصة بك</h3>
                        <p style="color:#6b7280;font-size:0.75rem;">احفظ هذه الأكواد في مكان آمن. كل كود يُستخدم مرة واحدة فقط.</p>
                    </div>
                    <div id="backup-codes-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;margin-bottom:1.5rem;"></div>
                    <div style="background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:10px;padding:0.75rem;margin-bottom:1rem;color:#f87171;font-size:0.75rem;text-align:center;">
                        ⚠️ هذه الأكواد لن تظهر مرة أخرى! اكتبها الآن على ورقة.
                    </div>
                    <button onclick="closeBackupModal()" style="width:100%;padding:0.75rem;background:linear-gradient(135deg,#16a34a,#15803d);border:none;border-radius:12px;color:white;font-weight:700;cursor:pointer;font-size:0.9rem;">فهمت، حفظتها ✅</button>
                </div>
            </div>

            <!-- ===== DASHBOARD SECTION ===== -->

            <div id="dash-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-purple-400 border-b border-slate-700 pb-2">📊 لوحة التحكم – معلومات النظام</h2>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3" id="dashCards">
                    <div class="bg-slate-900 rounded-xl p-4 border border-purple-800/40 text-center">
                        <div class="text-3xl font-black text-purple-400" id="dashCpu">—</div>
                        <div class="text-xs text-gray-500 mt-1">CPU %</div>
                    </div>
                    <div class="bg-slate-900 rounded-xl p-4 border border-blue-800/40 text-center">
                        <div class="text-3xl font-black text-blue-400" id="dashRam">—</div>
                        <div class="text-xs text-gray-500 mt-1">RAM %</div>
                    </div>
                    <div class="bg-slate-900 rounded-xl p-4 border border-green-800/40 text-center">
                        <div class="text-3xl font-black text-green-400" id="dashDisk">—</div>
                        <div class="text-xs text-gray-500 mt-1">Disk %</div>
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
                            <div class="flex justify-between"><span class="text-gray-500">صادر (MB)</span><span class="text-purple-400" id="dashSent">—</span></div>
                            <div class="flex justify-between"><span class="text-gray-500">وارد (MB)</span><span class="text-purple-400" id="dashRecv">—</span></div>
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
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div class="bg-slate-900/50 p-6 rounded-2xl border border-blue-500/20">
                            <label class="block text-sm text-blue-400 mb-3 font-bold">🛠️ تشفير (إخفاء):</label>
                            <input type="file" id="audioFileEncrypt" accept=".wav, .mp3" class="hidden" onchange="document.getElementById('audioEncryptName').innerText = this.files[0].name">
                            <label for="audioFileEncrypt" class="w-full text-xs text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-xs file:font-semibold file:bg-blue-600/10 file:text-blue-400 hover:file:bg-blue-600/20 mb-4 cursor-pointer flex items-center justify-center p-2 rounded-xl border border-blue-600/30">
                                <span id="audioEncryptName" class="truncate">اختر ملف صوتي (.wav, .mp3)</span>
                            </label>
                            <textarea id="audioSecretText" placeholder="أدخل النص السري هنا..." class="w-full h-24 p-3 rounded-xl bg-slate-950 border border-slate-800 text-sm focus:border-blue-500 outline-none mb-4"></textarea>
                            <button onclick="processAudio('encode')" class="w-full py-3 bg-blue-600 hover:bg-blue-500 rounded-xl font-bold transition-all shadow-lg shadow-blue-900/20">حفظ النص في الملف 💾</button>
                        </div>
                        <div class="bg-slate-900/50 p-6 rounded-2xl border border-purple-500/20">
                            <label class="block text-sm text-purple-400 mb-3 font-bold">🔍 فك التشفير (استخراج):</label>
                            <input type="file" id="audioFileDecrypt" accept=".wav, .mp3" class="hidden" onchange="document.getElementById('audioDecryptName').innerText = this.files[0].name">
                            <label for="audioFileDecrypt" class="w-full text-xs text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-xs file:font-semibold file:bg-purple-600/10 file:text-purple-400 hover:file:bg-purple-600/20 mb-4 cursor-pointer flex items-center justify-center p-2 rounded-xl border border-purple-600/30">
                                <span id="audioDecryptName" class="truncate">اختر ملف صوتي (.wav, .mp3)</span>
                            </label>
                            <div id="audioDecodedResult" class="w-full h-24 p-3 rounded-xl bg-slate-950 border border-slate-800 text-sm overflow-y-auto mb-4 text-gray-400 font-mono italic">سيظهر النص المستخرج هنا...</div>
                            <button onclick="processAudio('decode')" class="w-full py-3 bg-purple-600 hover:bg-purple-500 rounded-xl font-bold transition-all shadow-lg shadow-purple-900/20">استخراج النص السري 🔑</button>
                        </div>
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


                    <!-- 1. Burn Notes -->
                    <div class="bg-slate-900/50 p-5 rounded-xl border border-slate-700/50 border-r-4 border-r-orange-500 relative overflow-hidden group">
                        <div class="absolute inset-0 bg-gradient-to-l from-orange-500/5 to-transparent pointer-events-none"></div>
                        <div class="flex items-center gap-3 mb-2 relative z-10">
                            <span class="text-orange-500 text-2xl drop-shadow-[0_0_10px_rgba(249,115,22,0.6)] animate-pulse">💣</span>
                            <h3 class="text-sm font-bold text-gray-200">الرسائل ذاتية التدمير (Burn Notes)</h3>
                        </div>
                        <p class="text-xs text-gray-400 mb-3 relative z-10">رسالة سرية لمرة واحدة — تُحذف فور قراءتها.</p>
                        <textarea id="burnNoteText" rows="3" class="w-full p-3 rounded-xl bg-slate-800 border border-slate-600 focus:ring-1 focus:ring-orange-500 outline-none text-sm mb-3 relative z-10" placeholder="اكتب رسالتك السرية هنا..."></textarea>
                        <button onclick="createBurnNote()" class="w-full bg-gradient-to-r from-orange-600 to-red-600 hover:from-orange-500 hover:to-red-500 text-white font-bold px-4 py-2 rounded-xl transition-all text-sm shadow-[0_0_15px_rgba(234,88,12,0.35)] flex items-center justify-center gap-2 relative z-10">
                            توليد رابط التدمير السري 🔥
                        </button>
                        <div id="burnNoteResult" class="hidden mt-3 p-3 bg-slate-900/80 border border-orange-800/30 rounded-xl flex flex-col md:flex-row items-center justify-between gap-2 relative z-10">
                            <input type="text" id="burnNoteLink" readonly class="w-full bg-black/50 text-orange-400 font-mono text-xs p-2 rounded-lg border border-slate-700/50 focus:outline-none" dir="ltr">
                            <button id="burnCopyBtn" onclick="copyBurnNoteLink()" class="w-full md:w-auto bg-slate-800 hover:bg-slate-700 text-xs px-4 py-2 rounded-lg text-gray-300 transition-colors whitespace-nowrap border border-slate-600 font-bold">نسخ الرابط</button>
                        </div>
                    </div>

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

                <!-- Phase 4 Secure Comms: Burn Chat -->
                <div class="col-span-1 md:col-span-2">
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
            const backupForm = document.getElementById('auth-backup-form'); // NEW
            
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
                if (backupForm) backupForm.style.display = 'none';
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
                if (backupForm) backupForm.style.display = 'none';
            } else if (tab === 'verify') {
                if (loginForm) loginForm.style.display = 'none';
                if (regForm) regForm.style.display = 'none';
                if (verifyForm) verifyForm.style.display = 'block';
                if (forgotForm) forgotForm.style.display = 'none';
                if (backupForm) backupForm.style.display = 'none';
                if(loginTab) { loginTab.style.background = 'transparent'; loginTab.style.color = '#6b7280'; }
                if(regTab) { regTab.style.background = 'transparent'; regTab.style.color = '#6b7280'; }
            } else if (tab === 'forgot') {
                if (loginForm) loginForm.style.display = 'none';
                if (regForm) regForm.style.display = 'none';
                if (verifyForm) verifyForm.style.display = 'none';
                if (forgotForm) forgotForm.style.display = 'block';
                if (backupForm) backupForm.style.display = 'none';
                if(loginTab) { loginTab.style.background = 'transparent'; loginTab.style.color = '#6b7280'; }
                if(regTab) { regTab.style.background = 'transparent'; regTab.style.color = '#6b7280'; }
            } else if (tab === 'backup') {
                if (loginForm) loginForm.style.display = 'none';
                if (regForm) regForm.style.display = 'none';
                if (verifyForm) verifyForm.style.display = 'none';
                if (forgotForm) forgotForm.style.display = 'none';
                if (backupForm) backupForm.style.display = 'block';
                if(loginTab) { loginTab.style.background = 'transparent'; loginTab.style.color = '#6b7280'; }
                if(regTab) { regTab.style.background = 'transparent'; regTab.style.color = '#6b7280'; }
            }
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
            const errEl     = document.getElementById('auth-reg-error');
            const sucEl     = document.getElementById('auth-reg-success');
            const btn       = document.getElementById('auth-reg-btn');

            errEl.style.display = 'none';
            sucEl.style.display = 'none';

            if (!username || !email || !password || !password2) { errEl.textContent = 'يرجى ملء جميع الحقول'; errEl.style.display = 'block'; return; }
            if (password !== password2) { errEl.textContent = 'كلمتا السر غير متطابقتين!'; errEl.style.display = 'block'; return; }
            if (password.length < 6) { errEl.textContent = 'كلمة السر يجب أن تكون 6 أحرف على الأقل'; errEl.style.display = 'block'; return; }

            btn.textContent = '⏳ جاري إنشاء الحساب...';
            btn.disabled = true;

            try {
                const res  = await fetch('/api/auth/register', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username, password, email}) });
                const data = await res.json();

                if (data.success) {
                    sucEl.textContent = '✅ ' + data.message;
                    sucEl.style.display = 'block';
                    btn.textContent = 'إنشاء حساب جديد ✨';
                    btn.disabled = false;
                    document.getElementById('auth-verify-username').value = username;
                    
                    // Show Backup Codes ONLY ONCE
                    if (data.backup_codes && data.backup_codes.length > 0) {
                        const grid = document.getElementById('backup-codes-grid');
                        grid.innerHTML = '';
                        data.backup_codes.forEach(code => {
                            const d = document.createElement('div');
                            d.className = 'bg-black/50 border border-green-800/40 p-2 rounded text-center text-sm font-mono text-green-300 tracking-wider font-bold';
                            d.textContent = code;
                            grid.appendChild(d);
                        });
                        document.getElementById('backup-codes-modal').style.display = 'flex';
                    }

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
        
        function closeBackupModal() {
            document.getElementById('backup-codes-modal').style.display = 'none';
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
                    initMatrix('matrix-bg', false);
                    setInterval(updateHUD, 2000);
                    document.querySelectorAll('button').forEach(btn => {
                        btn.addEventListener('mouseenter', soundManager.hover);
                        btn.addEventListener('click', soundManager.click);
                    });
                }
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
        async function checkAuth() {
            try {
                const res = await fetch('/api/auth/status');
                const data = await res.json();
                if (data.loggedIn) {
                    console.log('User is logged in:', data.username);
                    // إخفاء auth overlay
                    document.getElementById('auth-overlay').style.display = 'none';
                    document.getElementById('header-username').innerText = '👤 ' + data.username;

                    // إخفاء intro-overlay فوراً حتى لا يضطر المستخدم للضغط على زر البصمة
                    const introOverlay = document.getElementById('intro-overlay');
                    if (introOverlay) {
                        introOverlay.style.display = 'none';
                    }

                    // إظهار التطبيق الرئيسي مباشرة
                    const mainApp = document.getElementById('main-app');
                    if (mainApp) {
                        mainApp.classList.remove('opacity-0', 'pointer-events-none');
                        mainApp.style.opacity = '1';
                        mainApp.style.pointerEvents = 'auto';
                        console.log('mainApp shown via checkAuth');
                    }

                    if (data.isAdmin) {
                        const adminBtn = document.getElementById('btn-admin');
                        if (adminBtn) {
                            adminBtn.classList.remove('hidden');
                            adminBtn.classList.add('flex');
                        }
                    }

                    // تهيئة التطبيق
                    if (typeof introMatrixAnimId !== 'undefined') {
                        cancelAnimationFrame(introMatrixAnimId);
                    }
                    initMatrix('matrix-bg', false);
                    setInterval(updateHUD, 2000);
                    document.querySelectorAll('button').forEach(btn => {
                        btn.addEventListener('mouseenter', soundManager.hover);
                        btn.addEventListener('click', soundManager.click);
                    });
                } else {
                    document.getElementById('auth-overlay').style.display = 'block';
                    initMatrix('auth-matrix', true);
                }
            } catch (e) {
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
        window.onload = () => { setTimeout(checkAuth, 100); };

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
                
                setInterval(updateHUD, 2000);
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

        async function doBackupLogin() {
            const username = document.getElementById('auth-backup-user').value.trim();
            const code = document.getElementById('auth-backup-code').value.trim();
            const msg = document.getElementById('auth-backup-error');
            
            if (!username || !code) { 
                msg.innerText = "يرجى إدخال اسم المستخدم وكود الطوارئ"; 
                msg.style.display = 'block'; 
                return; 
            }
            if(code.length !== 8) { 
                msg.innerText = "الكود يجب أن يكون 8 حروف تماماً"; 
                msg.style.display = 'block'; 
                return; 
            }
            
            msg.style.display = 'none';

            try {
                const res = await fetch('/api/auth/backup-login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({code, username})});
                const data = await res.json();
                if (data.success) {
                    msg.innerText = "✅ تم الدخول بالكود بنجاح! جاري توجيهك...";
                    msg.className = "mt-4 p-2 rounded bg-green-900/40 text-green-300 border border-green-800/50 text-xs text-center";
                    msg.style.display = 'block';
                    setTimeout(() => window.location.reload(), 1000);
                } else {
                    msg.innerText = data.error || "❌ الكود غير صحيح أو مستخدم مسبقاً.";
                    msg.className = "mt-4 p-2 rounded bg-red-900/40 text-red-300 border border-red-800/50 text-xs text-center";
                    msg.style.display = 'block';
                }
            } catch(e) {
                msg.innerText = "فشل الاتصال بالخادم";
                msg.style.display = 'block';
            }
        }

        async function regenerateBackupCodes() {
            if(!await titanConfirm('هل أنت متأكد؟ سيؤدي ذلك إلى إلغاء جميع أكواد الطوارئ القديمة وتوليد 8 أكواد جديدة.')) return;
            
            try {
                const res = await fetch('/api/auth/backup-codes/regenerate', {method:'POST'});
                const data = await res.json();
                if(data.success && data.backup_codes) {
                    const grid = document.getElementById('backup-codes-grid');
                    grid.innerHTML = '';
                    data.backup_codes.forEach(code => {
                        const d = document.createElement('div');
                        d.className = 'bg-black/50 border border-green-800/40 p-2 rounded text-center text-sm font-mono text-green-300 tracking-wider font-bold';
                        d.textContent = code;
                        grid.appendChild(d);
                    });
                    document.getElementById('backup-codes-modal').style.display = 'flex';
                    soundManager.success();
                } else {
                    titanAlert(data.error || 'فشل توليد الأكواد');
                }
            } catch(e) {
                titanAlert('فشل الاتصال بالخادم');
            }
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
        const ALL_TABS = ['dash','pass','vault','crypt','suite','tools','qr','identity','audio','extreme','netintel'];
        let _prevTab = 'pass';
        function showTab(type) {
            // Auto-lock vault silently when leaving it
            if (_prevTab === 'vault' && type !== 'vault' && currentMasterKey) {
                lockVault(true);
            }
            _prevTab = type;
            ALL_TABS.forEach(t => {
                const sec = document.getElementById(t + '-section');
                const btn = document.getElementById('btn-' + t);
                if(sec) sec.classList.toggle('hidden', t !== type);
                if(btn) {
                    if(t === type) {
                        btn.classList.remove('text-gray-400');
                        btn.classList.add('bg-purple-600/90', 'text-white');
                    } else {
                        btn.classList.remove('bg-purple-600/90', 'text-white', 'bg-yellow-600/90', 'text-slate-900');
                        btn.classList.add('text-gray-400');
                    }
                }
            });
            // Special vault styling
            const vBtn = document.getElementById('btn-vault');
            if(vBtn) {
                if(type === 'vault') {
                    vBtn.classList.add('bg-yellow-600/90', 'text-slate-900');
                    vBtn.classList.remove('text-gray-400', 'bg-purple-600/90');
                }
            }
            if(type === 'dash') {
                loadDashboard();
                if (!window.dashInterval) window.dashInterval = setInterval(loadDashboard, 3000);
            } else {
                if (window.dashInterval) { clearInterval(window.dashInterval); window.dashInterval = null; }
            }
            if(type === 'tools' && typeof fetchIpIntel === 'function') fetchIpIntel();
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
            dataBox.innerHTML = '<div class="p-4 text-center"><span class="text-purple-400 animate-pulse text-sm font-mono tracking-wider">جاري التقاط الحزم وتحليل مسار الاتصال...</span></div>';
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
                dataBox.innerHTML = `
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-y-5 gap-x-6">
                        <div class="bg-slate-800/60 p-4 rounded-xl border border-slate-700/50 hover:border-purple-500/50 transition-colors">
                            <div class="text-slate-400 text-[10px] uppercase mb-1 flex items-center gap-2 tracking-wider"><span class="w-1.5 h-1.5 rounded-full bg-purple-500 shadow-[0_0_5px_#a855f7]"></span>العنوان (IP)</div> 
                            <div class="font-mono text-xl text-purple-400 font-bold text-shadow-sm">${ip || data.query || 'غير معروف'}</div>
                        </div>
                        <div class="bg-slate-800/60 p-4 rounded-xl border border-slate-700/50 hover:border-purple-500/50 transition-colors">
                            <div class="text-slate-400 text-[10px] uppercase mb-1 flex items-center gap-2 tracking-wider"><span class="w-1.5 h-1.5 rounded-full bg-yellow-500 shadow-[0_0_5px_#eab308]"></span>مزود الخدمة (ISP) - البلد</div> 
                            <div class="font-semibold text-gray-200">${data.ISP} <span class="text-gray-500 text-xs">(${data.country_code})</span></div>
                        </div>
                    </div>
                `;
            } else {
                soundManager.error();
                dataBox.innerHTML = `<div class="text-red-400 font-bold bg-red-900/20 p-4 rounded-lg">خطأ: ${data.message || 'فشل جلب البيانات'}</div>`;
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
            container.innerHTML = '<span class="text-gray-500 font-mono animate-pulse text-xs">جاري التشخيص وفحص المنافذ الحساسة...</span>';
            document.getElementById('portScanTarget').innerText = ip;
            soundManager.terminalType();
            
            try {
                const res = await fetch('/api/port-scan', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ip}) });
                const data = await res.json();
                
                if (data.error) {
                    container.innerHTML = `<span class="text-red-400 bg-red-900/20 px-3 py-2 rounded">خطأ: ${data.error}</span>`;
                    soundManager.error();
                } else if (data.open_ports && data.open_ports.length > 0) {
                    soundManager.alarm();
                    container.innerHTML = data.open_ports.map(p => `
                        <div class="px-4 py-2 bg-red-900/40 border border-red-500/50 rounded-xl text-red-400 font-mono shadow-[0_0_10px_rgba(239,68,68,0.2)] flex items-center gap-2">
                            <span class="w-2 h-2 rounded-full bg-red-500 shadow-[0_0_8px_#ef4444] animate-pulse"></span> منفذ ${p} مفتوح
                        </div>
                    `).join('');
                } else {
                    soundManager.success();
                    container.innerHTML = `<div class="bg-green-900/20 text-green-400 font-bold px-4 py-3 rounded-xl border border-green-800/50 w-full text-center flex items-center justify-center gap-2">✅ جميع المنافذ المفحوصة مغلقة (آمن)</div>`;
                }
            } catch (e) {
                container.innerHTML = `<span class="text-red-400">فشل الاتصال بالخادم.</span>`;
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
            resBox.innerHTML = '<span class="text-blue-500 animate-pulse">جاري التحليل واستخراج البيانات العميقة...</span>';
            soundManager.terminalType();
            
            try {
                const res = await fetch('/api/osint/image', { method: 'POST', body: formData });
                const data = await res.json();
                
                if(data.error) throw new Error(data.error);
                
                let html = '';
                for(let key in data) {
                    html += `<span class="text-purple-400">${key}:</span> <span class="text-gray-300">${data[key]}</span>\n`;
                }
                resBox.innerHTML = html || 'لا توجد بيانات حساسة.';
                soundManager.success();
            } catch (e) {
                resBox.innerHTML = `<span class="text-red-400">خطأ: ${e.message}</span>`;
                soundManager.error();
            }
        }


        async function checkPhishing() {
            const email = document.getElementById('phishUrlInput').value;
            if(!email || !email.includes('@')) return titanAlert("الرجاء إدخال بريد إلكتروني صحيح");
            const resBox = document.getElementById('phishResult');
            resBox.classList.remove('hidden');
            resBox.innerHTML = '<span class="text-orange-400 animate-pulse text-xs font-mono">جاري فحص سمعة البريد الإلكتروني عبر IPQualityScore...</span>';
            soundManager.terminalType();
            
            try {
                const res = await fetch('/api/scan/email', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({email})
                });
                const data = await res.json();
                
                if (data.error) {
                    resBox.innerHTML = `<span class="text-red-400">خطأ: ${data.error}</span>`;
                    return;
                }
                
                if (data.success) {
                    const riskColor = data.fraud_score > 70 ? 'text-red-500' : (data.fraud_score > 30 ? 'text-orange-400' : 'text-green-500');
                    resBox.innerHTML = `
                        <div class="flex justify-between items-center mb-3 border-b border-slate-700 pb-2">
                            <span class="font-bold text-gray-300 font-mono tracking-wider">${email}</span>
                            <span class="font-black ${riskColor} bg-slate-900 px-2 py-1 rounded">Fraud Score: ${data.fraud_score}</span>
                        </div>
                        <div class="grid grid-cols-2 gap-3 mb-2">
                            <div class="bg-slate-950 p-3 rounded-lg border border-slate-700/50 text-center">
                                <span class="text-[10px] text-gray-400 block mb-1 uppercase tracking-widest">Valid Email</span>
                                <span class="font-bold font-mono ${data.valid ? 'text-green-400' : 'text-red-400'}">${data.valid ? 'YES' : 'NO'}</span>
                            </div>
                            <div class="bg-slate-950 p-3 rounded-lg border border-slate-700/50 text-center">
                                <span class="text-[10px] text-gray-400 block mb-1 uppercase tracking-widest">Disposable</span>
                                <span class="font-bold font-mono ${data.disposable ? 'text-red-400' : 'text-green-400'}">${data.disposable ? 'YES (وهمي)' : 'NO'}</span>
                            </div>
                        </div>
                        <div class="grid grid-cols-2 gap-3">
                            <div class="bg-slate-950 p-3 rounded-lg border border-slate-700/50 text-center">
                                <span class="text-[10px] text-gray-400 block mb-1 uppercase tracking-widest">Spam Trap Score</span>
                                <span class="font-bold text-gray-200">${data.spam_trap_score}</span>
                            </div>
                        </div>
                    `;
                    if(data.fraud_score > 70 || data.disposable || !data.valid) soundManager.alarm(); else soundManager.success();
                } else {
                    resBox.innerHTML = `<span class="text-red-400">خطأ من الخدمة: ${data.message}</span>`;
                    soundManager.error();
                }
            } catch (e) {
                resBox.innerHTML = `<span class="text-red-400">فشل الاتصال بخادم الفحص.</span>`;
                soundManager.error();
            }
        }

        async function checkEmailPassLeak() {
            const email = document.getElementById('leakEmailInput').value;
            const password = document.getElementById('leakPassInput').value;
            if(!email || !password) return titanAlert("الرجاء إدخال البريد الإلكتروني وكلمة السر بشكل صحيح");
            
            const resBox = document.getElementById('leakEmailPassResult');
            resBox.classList.remove('hidden');
            resBox.innerHTML = '<span class="text-orange-400 animate-pulse text-xs font-mono">جاري فحص التسريبات عبر IPQualityScore...</span>';
            soundManager.terminalType();
            
            try {
                const res = await fetch('/api/scan/emailpass_leak', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({email, password})
                });
                const data = await res.json();
                
                if (data.error) {
                    resBox.innerHTML = `<span class="text-red-400">خطأ: ${data.error}</span>`;
                    return;
                }
                
                if (data.success) {
                    const isLeaked = data.leaked === true || data.leaked === "true";
                    resBox.innerHTML = `
                        <div class="flex justify-between items-center mb-3 border-b border-slate-700 pb-2">
                            <span class="font-bold text-gray-300 font-mono tracking-wider">${email}</span>
                        </div>
                        <div class="bg-slate-950 p-4 rounded-lg border ${isLeaked ? 'border-red-500/50' : 'border-green-500/50'} text-center">
                            <span class="text-xs text-gray-400 block mb-2 font-bold uppercase tracking-widest">حالة التسريب لهذه البيانات معاً</span>
                            <div class="text-lg font-bold font-mono ${isLeaked ? 'text-red-500' : 'text-green-400'}">
                                ${isLeaked ? '🚨 تم تسريب هذه البيانات معاً مسبقاً! (خطر)' : '✅ لم يثبت تسريب الإيميل مع كلمة السر (آمن نسبياً)'}
                            </div>
                        </div>
                    `;
                    if(isLeaked) soundManager.alarm(); else soundManager.success();
                } else {
                    resBox.innerHTML = `<span class="text-red-400">خطأ من الخدمة: ${data.message}</span>`;
                    soundManager.error();
                }
            } catch (e) {
                resBox.innerHTML = `<span class="text-red-400">فشل الاتصال بخادم الفحص.</span>`;
                soundManager.error();
            }
        }

        async function fetchIpqsLogs() {
            const reqType = document.getElementById('ipqsLogType').value;
            const startDate = document.getElementById('ipqsLogDate').value;
            const resBox = document.getElementById('ipqsLogsResult');
            
            resBox.classList.remove('hidden');
            resBox.innerHTML = '<span class="text-teal-400 animate-pulse">جاري جلب السجلات من الخادم...</span>';
            soundManager.terminalType();
            
            try {
                const res = await fetch('/api/scan/ipqs_logs', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({type: reqType, start_date: startDate})
                });
                const data = await res.json();
                
                if (data.success === false) {
                    resBox.innerHTML = `<span class="text-red-400">خطأ: ${data.message || 'فشل جلب السجلات'}</span>`;
                    soundManager.error();
                    return;
                }
                
                const requests = data.requests || [];
                if (requests.length === 0) {
                    resBox.innerHTML = '<span class="text-gray-400 italic">لا توجد سجلات مطابقة في هذه الفترة.</span>';
                    soundManager.success();
                    return;
                }
                
                let html = '<div class="space-y-2">';
                requests.forEach(req => {
                    const statusStr = req.status ? '<span class="text-green-400">Success</span>' : '<span class="text-red-400">Failed</span>';
                    const fraudStr = req.fraud_score !== undefined ? `Fraud: <span class="text-yellow-400">${req.fraud_score}</span>` : '';
                    const dateStr = new Date(req.request_date).toLocaleString('ar-EG');
                    
                    // target represents what was scanned (ip, email, query, etc)
                    const targetStr = req.query || req.email || req.ip || req.phone || 'Unknown Target';
                    
                    html += `
                        <div class="bg-slate-900 p-2 rounded border border-slate-700/50 hover:border-teal-500/30 transition-colors flex flex-col gap-1">
                            <div class="flex justify-between items-start">
                                <span class="text-teal-300 font-bold">${targetStr}</span>
                                <span class="text-[10px] text-gray-500">${dateStr}</span>
                            </div>
                            <div class="flex justify-between items-center text-xs text-gray-400 mt-1">
                                <span>Status: ${statusStr}</span>
                                <span>${fraudStr}</span>
                            </div>
                        </div>
                    `;
                });
                html += '</div>';
                
                resBox.innerHTML = html;
                soundManager.success();
                
            } catch (e) {
                resBox.innerHTML = `<span class="text-red-400">فشل الاتصال بخادم السجلات.</span>`;
                soundManager.error();
            }
        }

        async function checkPhone() {
            const phone = document.getElementById('phoneInput').value;
            if(!phone) return titanAlert("الرجاء إدخال رقم الهاتف");
            const resBox = document.getElementById('phoneResult');
            resBox.classList.remove('hidden');
            resBox.innerHTML = '<span class="text-yellow-400 animate-pulse text-xs font-mono">جاري فحص الرقم عبر IPQualityScore...</span>';
            soundManager.terminalType();
            
            try {
                const res = await fetch('/api/scan/phone', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({phone})
                });
                const data = await res.json();
                
                if (data.error) {
                    resBox.innerHTML = `<span class="text-red-400">خطأ: ${data.error}</span>`;
                    return;
                }
                
                if (data.success) {
                    const riskColor = data.fraud_score > 70 ? 'text-red-500' : (data.fraud_score > 30 ? 'text-orange-400' : 'text-green-500');
                    resBox.innerHTML = `
                        <div class="flex justify-between items-center mb-3 border-b border-slate-700 pb-2">
                            <span class="font-bold text-gray-300 font-mono tracking-wider" dir="ltr">${data.formatted || phone}</span>
                            <span class="font-black ${riskColor} bg-slate-900 px-2 py-1 rounded">Fraud Score: ${data.fraud_score}</span>
                        </div>
                        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-2">
                            <div class="bg-slate-950 p-3 rounded-lg border border-slate-700/50 text-center">
                                <span class="text-[10px] text-gray-400 block mb-1 uppercase tracking-widest">Valid</span>
                                <span class="font-bold font-mono ${data.valid ? 'text-green-400' : 'text-red-400'}">${data.valid ? 'YES' : 'NO'}</span>
                            </div>
                            <div class="bg-slate-950 p-3 rounded-lg border border-slate-700/50 text-center">
                                <span class="text-[10px] text-gray-400 block mb-1 uppercase tracking-widest">Active</span>
                                <span class="font-bold font-mono ${data.active ? 'text-green-400' : 'text-orange-400'}">${data.active ? 'YES' : 'Unknown'}</span>
                            </div>
                            <div class="bg-slate-950 p-3 rounded-lg border border-slate-700/50 text-center">
                                <span class="text-[10px] text-gray-400 block mb-1 uppercase tracking-widest">Line Type</span>
                                <span class="font-bold font-mono text-gray-200">${data.line_type || 'N/A'}</span>
                            </div>
                            <div class="bg-slate-950 p-3 rounded-lg border border-slate-700/50 text-center">
                                <span class="text-[10px] text-gray-400 block mb-1 uppercase tracking-widest">Recent Abuse</span>
                                <span class="font-bold font-mono ${data.recent_abuse ? 'text-red-400' : 'text-green-400'}">${data.recent_abuse ? 'YES' : 'NO'}</span>
                            </div>
                        </div>
                        <div class="grid grid-cols-1 gap-3">
                            <div class="bg-slate-950 p-3 rounded-lg border border-slate-700/50 text-center">
                                <span class="text-[10px] text-gray-400 block mb-1 uppercase tracking-widest">Carrier</span>
                                <span class="font-bold text-gray-200">${data.carrier || 'N/A'}</span>
                            </div>
                        </div>
                    `;
                    if(data.fraud_score > 70 || data.recent_abuse || !data.valid) soundManager.alarm(); else soundManager.success();
                } else {
                    resBox.innerHTML = `<span class="text-red-400">خطأ من الخدمة: ${data.message} <br> <span class="text-xs text-gray-500 mt-2 block">(ملاحظة النظام: إذا كان الخطأ يتكرر لجميع الأرقام، فهذا يعني أن رصيد حسابك المجاني في IPQualityScore قد انتهى لليوم)</span></span>`;
                    soundManager.error();
                }
            } catch (e) {
                resBox.innerHTML = `<span class="text-red-400">فشل الاتصال بخادم الفحص.</span>`;
                soundManager.error();
            }
        }

        async function checkUrl() {
            const url = document.getElementById('urlInput').value;
            if(!url || (!url.startsWith('http://') && !url.startsWith('https://'))) return titanAlert("الرجاء إدخال رابط صحيح يبدأ بـ http:// أو https://");
            const resBox = document.getElementById('urlResult');
            resBox.classList.remove('hidden');
            resBox.innerHTML = '<span class="text-blue-400 animate-pulse text-xs font-mono">جاري فحص الرابط عبر IPQualityScore...</span>';
             soundManager.terminalType();
            
            try {
                const res = await fetch('/api/scan/url', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url})
                });
                const data = await res.json();
                
                if (data.error) {
                    resBox.innerHTML = `<span class="text-red-400">خطأ: ${data.error}</span>`;
                    return;
                }
                
                if (data.success) {
                    const riskColor = data.risk_score > 70 ? 'text-red-500' : (data.risk_score > 30 ? 'text-orange-400' : 'text-green-500');
                    resBox.innerHTML = `
                        <div class="flex justify-between items-center mb-3 border-b border-slate-700 pb-2 flex-wrap gap-2">
                            <span class="font-bold text-gray-300 font-mono tracking-wider break-all text-xs" dir="ltr">${url}</span>
                            <span class="font-black ${riskColor} bg-slate-900 px-2 py-1 rounded">Risk Score: ${data.risk_score || 0}</span>
                        </div>
                        <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-2">
                            <div class="bg-slate-950 p-3 rounded-lg border border-slate-700/50 text-center">
                                <span class="text-[10px] text-gray-400 block mb-1 uppercase tracking-widest">Phishing</span>
                                <span class="font-bold font-mono ${data.phishing ? 'text-red-400' : 'text-green-400'}">${data.phishing ? 'YES (تصيد)' : 'NO'}</span>
                            </div>
                            <div class="bg-slate-950 p-3 rounded-lg border border-slate-700/50 text-center">
                                <span class="text-[10px] text-gray-400 block mb-1 uppercase tracking-widest">Malware</span>
                                <span class="font-bold font-mono ${data.malware ? 'text-red-400' : 'text-green-400'}">${data.malware ? 'YES (خبيث)' : 'NO'}</span>
                            </div>
                            <div class="bg-slate-950 p-3 rounded-lg border border-slate-700/50 text-center">
                                <span class="text-[10px] text-gray-400 block mb-1 uppercase tracking-widest">Suspicious</span>
                                <span class="font-bold font-mono ${data.suspicious ? 'text-orange-400' : 'text-green-400'}">${data.suspicious ? 'YES (مشبوه)' : 'NO'}</span>
                            </div>
                            <div class="bg-slate-950 p-3 rounded-lg border border-slate-700/50 text-center">
                                <span class="text-[10px] text-gray-400 block mb-1 uppercase tracking-widest">Parking</span>
                                <span class="font-bold font-mono text-gray-200">${data.parking ? 'YES' : 'NO'}</span>
                            </div>
                        </div>
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                            <div class="bg-slate-950 p-3 rounded-lg border border-slate-700/50">
                                <span class="text-[10px] text-gray-400 block mb-1 uppercase tracking-widest">Domain Name</span>
                                <span class="font-bold text-gray-200 text-xs">${data.domain || 'N/A'}</span>
                            </div>
                            <div class="bg-slate-950 p-3 rounded-lg border border-slate-700/50">
                                <span class="text-[10px] text-gray-400 block mb-1 uppercase tracking-widest">Category / Server</span>
                                <span class="font-bold text-gray-200 text-xs">${data.category || 'N/A'} / ${data.server || 'N/A'}</span>
                            </div>
                        </div>
                    `;
                    if(data.risk_score > 70 || data.phishing || data.malware || data.suspicious) soundManager.alarm(); else soundManager.success();
                } else {
                    resBox.innerHTML = `<span class="text-red-400">خطأ من الخدمة: ${data.message}</span>`;
                     soundManager.error();
                }
            } catch (e) {
                resBox.innerHTML = `<span class="text-red-400">فشل الاتصال بخادم الفحص.</span>`;
                 soundManager.error();
            }
        }

        function renderMalwareResult(data, targetName, isUrl = true) {
            const resBox = document.getElementById('malwareResult');
            
            if (data.error) {
                resBox.innerHTML = `<span class="text-red-400">خطأ: ${data.error}</span>`;
                return;
            }
            
            if (data.status === "pending") {
                 resBox.innerHTML = `<span class="text-yellow-400 animate-pulse font-mono tracking-widest whitespace-pre-wrap"><br/>⚠️ جاري تحليل الهدف أمنياً في الخادم... الرجاء الانتظار بضع ثوانٍ.</span>`;
                 return;
            }
             
            if (data.success && data.result) {
                const scan = data.result;
                 // Some risk score keys for malware scan could differ slightly, safely extracting
                let riskScore = scan.risk_score || 0;
                let riskColor = riskScore > 70 ? 'text-red-500' : (riskScore > 30 ? 'text-orange-400' : 'text-green-500');
                
               resBox.innerHTML = `
                    <div class="flex justify-between items-center mb-3 border-b border-slate-700 pb-2 flex-wrap gap-2">
                        <span class="font-bold text-gray-300 font-mono tracking-wider break-all text-xs" dir="ltr">${targetName}</span>
                         <span class="font-black ${riskColor} bg-slate-900 px-2 py-1 rounded">Risk Score: ${riskScore}</span>
                    </div>
                    <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-2">
                        <div class="bg-slate-950 p-3 rounded-lg border border-slate-700/50 text-center">
                            <span class="text-[10px] text-gray-400 block mb-1 uppercase tracking-widest">Malicious</span>
                             <span class="font-bold font-mono ${scan.malicious ? 'text-red-400' : 'text-green-400'}">${scan.malicious ? 'YES (خبيث)' : 'NO'}</span>
                        </div>
                        <div class="bg-slate-950 p-3 rounded-lg border border-slate-700/50 text-center">
                            <span class="text-[10px] text-gray-400 block mb-1 uppercase tracking-widest">Phishing</span>
                            <span class="font-bold font-mono ${scan.phishing ? 'text-red-400' : 'text-green-400'}">${scan.phishing ? 'YES (تصيد)' : 'NO'}</span>
                        </div>
                         <div class="bg-slate-950 p-3 rounded-lg border border-slate-700/50 text-center">
                            <span class="text-[10px] text-gray-400 block mb-1 uppercase tracking-widest">Suspicious</span>
                            <span class="font-bold font-mono ${scan.suspicious ? 'text-orange-400' : 'text-green-400'}">${scan.suspicious ? 'YES (مشبوه)' : 'NO'}</span>
                        </div>
                        <div class="bg-slate-950 p-3 rounded-lg border border-slate-700/50 text-center">
                            <span class="text-[10px] text-gray-400 block mb-1 uppercase tracking-widest">Spam</span>
                            <span class="font-bold font-mono ${scan.spam ? 'text-red-400' : 'text-green-400'}">${scan.spam ? 'YES (مزعج)' : 'NO'}</span>
                        </div>
                    </div>
                `;
                 if(riskScore > 70 || scan.malicious || scan.phishing || scan.suspicious) soundManager.alarm(); else soundManager.success();
             } else {
                 resBox.innerHTML = `<span class="text-red-400">خطأ من الخدمة: ${data.message || 'فشل عملية الفحص العميق.'}</span>`;
                  soundManager.error();
             }
        }

        async function checkMalwareUrl() {
            const url = document.getElementById('malwareUrlInput').value;
            if(!url || (!url.startsWith('http://') && !url.startsWith('https://'))) return titanAlert("الرجاء إدخال رابط صحيح يبدأ بـ http:// أو https://");
            const resBox = document.getElementById('malwareResult');
            resBox.classList.remove('hidden');
            resBox.innerHTML = '<span class="text-rose-400 animate-pulse text-xs font-mono">جاري فحص الرابط للبرمجيات الخبيثة عبر IPQualityScore...</span>';
            soundManager.terminalType();
            
            try {
                const res = await fetch('/api/scan/malware_url', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url})
                });
                const data = await res.json();
                renderMalwareResult(data, url, true);
            } catch (e) {
                 resBox.innerHTML = `<span class="text-red-400">فشل الاتصال بخادم الفحص.</span>`;
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
            resBox.innerHTML = '<span class="text-rose-400 animate-pulse text-xs font-mono">جاري رفع وفحص الملف للبرمجيات الخبيثة...</span>';
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
                 resBox.innerHTML = `<span class="text-red-400">فشل رفع الملف أو الاتصال بالخادم.</span>`;
                 soundManager.error();
            }
        }

        async function scanLanNetwork() {
            const loader = document.getElementById('lanLoader');
            const resBox = document.getElementById('lanResult');
            const btn = document.getElementById('btnLanScan');
            
            btn.disabled = true;
            loader.classList.remove('hidden');
            resBox.classList.remove('hidden');
            resBox.innerHTML = '<span class="text-cyan-500 animate-pulse text-xs font-mono">جاري إرسال حزم استكشافية للشبكة (ARP Sweep)...</span>';
            soundManager.terminalType();
            
            try {
                const res = await fetch('/api/network/scan');
                const data = await res.json();
                
                if(data.length === 0) {
                    resBox.innerHTML = '<span class="text-gray-400">لم يتم العثور على أجهزة (أو الشبكة تمنع الفحص).</span>';
                } else if(data[0].error) {
                    resBox.innerHTML = `<span class="text-red-400">${data[0].error}</span>`;
                } else {
                    resBox.innerHTML = data.map(d => `
                        <div class="flex justify-between items-center p-3 border-b border-slate-800 hover:bg-slate-800/60 transition-colors rounded-lg mb-1">
                            <div class="flex items-center gap-3">
                                <span class="text-xl bg-slate-950 p-2 rounded-lg border border-slate-700">${d.icon || '💻'}</span>
                                <div class="flex flex-col">
                                    <span class="text-cyan-400 font-bold font-mono text-sm tracking-wider">${d.ip}</span>
                                    <span class="text-gray-500 text-[10px] uppercase font-bold">${d.label || d.type || 'Unknown'}</span>
                                </div>
                            </div>
                            <div class="text-right flex flex-col items-end">
                                <span class="text-gray-400 font-mono text-[10px] tracking-widest">${d.mac}</span>
                                <span class="text-[9px] text-teal-600 bg-teal-900/20 px-1 rounded mt-1">ACTIVE</span>
                            </div>
                        </div>
                    `).join('');
                }
                soundManager.success();
            } catch(e) {
                resBox.innerHTML = `<span class="text-red-400">فشل في جلب أجهزة الشبكة.</span>`;
                soundManager.error();
            }
            loader.classList.add('hidden');
            btn.disabled = false;
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
        async function loadDashboard() {
            try {
                const res = await fetch('/api/dashboard/stats');
                const d = await res.json();
                if(d.error) return;
                document.getElementById('dashCpu').innerText  = d.cpu_percent + '%';
                document.getElementById('dashRam').innerText  = d.ram_percent + '%';
                document.getElementById('dashDisk').innerText = d.disk_percent + '%';
                document.getElementById('dashBurn').innerText = d.burn_notes;
                document.getElementById('dashLocalIp').innerText = d.local_ip;
                document.getElementById('dashPubIp').innerText  = d.public_ip;
                document.getElementById('dashSent').innerText   = d.net_sent_mb;
                document.getElementById('dashRecv').innerText   = d.net_recv_mb;
                const logsEl = document.getElementById('dashLogs');
                if(d.recent_logs && d.recent_logs.length) {
                    logsEl.innerHTML = d.recent_logs.map(l =>
                        `<div class="text-purple-400">[${l.time.split(' ')[1]}] <span class="text-gray-300">${l.action}</span></div>`
                    ).join('');
                } else { logsEl.innerHTML = '<div class="text-gray-600">لا يوجد نشاط</div>'; }
            } catch(e) {}
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
        
        async function processAudio(action) {
            const formData = new FormData();
            if (action === 'encode') {
                const fileEl = document.getElementById('audioFileEncrypt');
                const file = fileEl.files[0];
                const text = document.getElementById('audioSecretText').value.trim();
                
                if (!file || !text) {
                    return titanAlert('يرجى اختيار ملف صوتي وكتابة النص السري المراد إخفاؤه.');
                }
                
                console.log('جاري المعالجة...');
                
                formData.append('file', file);
                formData.append('text', text);
                
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
                    downloadAnchor.download = "TITAN_SECURE_" + file.name;
                    document.body.appendChild(downloadAnchor);
                    downloadAnchor.click();
                    
                    titanAlert('تم التشفير والتحميل تلقائياً ✅');
                    
                    setTimeout(() => {
                        document.body.removeChild(downloadAnchor);
                        window.URL.revokeObjectURL(downloadUrl);
                    }, 500);
                } catch (error) {
                    titanAlert('خطأ: ' + error.message);
                }
            } else {
                const file = document.getElementById('audioFileDecrypt').files[0];
                if (!file) return titanAlert('يرجى اختيار الملف المراد فحصه.');
                
                console.log('جاري التحليل...');
                formData.append('file', file);
                
                try {
                    const res = await fetch('/api/audio/stego/decode', { method:'POST', body:formData });
                    const data = await res.json();
                    
                    if (data.error) {
                        titanAlert('تنبيه: ' + data.error);
                    } else if (data.success && data.hidden_data) {
                        document.getElementById('audioDecodedResult').innerText = data.hidden_data;
                        titanAlert('✅ تم العثور على نص مخفي!');
                    } else {
                        titanAlert('لم يتم العثور على بيانات مخفية.');
                    }
                } catch (error) {
                    titanAlert('خطأ في الاتصال بالخادم.');
                }
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

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


# =====================================================================
# === Init & Run ===
# =====================================================================

try:
    init_db()
    print("[TITAN] Appwrite initialized successfully.")
except Exception as _e:
    print(f"[TITAN] init_db error: {_e}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
