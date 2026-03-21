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

# --- Appwrite SDK ---
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.services.users import Users
from appwrite.services.storage import Storage
from appwrite.id import ID
from appwrite.query import Query

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
TESTMAIL_API_KEY = os.environ.get('TESTMAIL_API_KEY', '')
TESTMAIL_NAMESPACE = os.environ.get('TESTMAIL_NAMESPACE', '')
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'abdallahalqam4040@gmail.com')


def get_appwrite_client():
    client = Client()
    client.set_endpoint(APPWRITE_ENDPOINT)
    client.set_project(APPWRITE_PROJECT_ID)
    client.set_key(APPWRITE_API_KEY)
    return client


def get_db():
    return Databases(get_appwrite_client())


def get_users_service():
    return Users(get_appwrite_client())


# =====================================================================
# === Testmail Email Functions ===
# =====================================================================

def _testmail_send(to_email, subject, body):
    """إرسال إيميل عبر Testmail API"""
    # Testmail يستقبل الإيميلات على namespace.tag@inbox.testmail.app
    # لإرسال إيميل حقيقي نستخدم Testmail SMTP
    try:
        data = _json.dumps({
            "apikey": TESTMAIL_API_KEY,
            "namespace": TESTMAIL_NAMESPACE,
            "subject": subject,
            "text": body,
            "to": to_email,
        }).encode('utf-8')
        req = urllib.request.Request(
            "https://api.testmail.app/api/json",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = _json.loads(resp.read().decode())
            return result.get('result') == 'success'
    except Exception as e:
        print(f"[Testmail] Error: {e}")
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

def aw_create(collection_id, data, doc_id=None):
    db = get_db()
    return db.create_document(
        database_id=APPWRITE_DB_ID,
        collection_id=collection_id,
        document_id=doc_id or ID.unique(),
        data=data
    )


def aw_get(collection_id, doc_id):
    db = get_db()
    try:
        return db.get_document(APPWRITE_DB_ID, collection_id, doc_id)
    except Exception:
        return None


def aw_list(collection_id, queries=None):
    db = get_db()
    try:
        result = db.list_documents(APPWRITE_DB_ID, collection_id, queries=queries or [])
        return result.get('documents', [])
    except Exception:
        return []


def aw_update(collection_id, doc_id, data):
    db = get_db()
    return db.update_document(APPWRITE_DB_ID, collection_id, doc_id, data)


def aw_delete(collection_id, doc_id):
    db = get_db()
    try:
        db.delete_document(APPWRITE_DB_ID, collection_id, doc_id)
        return True
    except Exception:
        return False


def find_user_by_username(username):
    docs = aw_list(COL_USERS, [Query.equal('username', username)])
    return docs[0] if docs else None


def find_user_by_email(email):
    docs = aw_list(COL_USERS, [Query.equal('email', email)])
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
        try:
            db.get_collection(APPWRITE_DB_ID, col_id)
            print(f"[TITAN] Collection {col_id} already exists.")
        except Exception:
            try:
                db.create_collection(
                    database_id=APPWRITE_DB_ID,
                    collection_id=col_id,
                    name=col_id,
                    document_security=False
                )
                print(f"[TITAN] Created collection: {col_id}")
                for attr in attributes:
                    try:
                        attr_type = attr.get("type")
                        if attr_type == "string":
                            db.create_string_attribute(
                                APPWRITE_DB_ID, col_id,
                                key=attr["key"],
                                size=attr.get("size", 255),
                                required=attr.get("required", False),
                                default=attr.get("default", None)
                            )
                        elif attr_type == "boolean":
                            db.create_boolean_attribute(
                                APPWRITE_DB_ID, col_id,
                                key=attr["key"],
                                required=attr.get("required", False),
                                default=attr.get("default", False)
                            )
                        elif attr_type == "integer":
                            db.create_integer_attribute(
                                APPWRITE_DB_ID, col_id,
                                key=attr["key"],
                                required=attr.get("required", False),
                                default=attr.get("default", 0)
                            )
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
        existing = aw_list(COL_INTEGRITY, [Query.equal('file_path', app_path)])
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
            sessions = aw_list(COL_ACTIVE_SESSIONS, [Query.equal('token', token)])
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
        codes = aw_list(COL_BACKUP_CODES, [
            Query.equal('user_id', user_id),
            Query.equal('code_hash', code_hash),
            Query.equal('used', False)
        ])
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
        existing = aw_list(COL_BACKUP_CODES, [Query.equal('user_id', user_id)])
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
        docs = aw_list(COL_VAULT_TIMELOCKED, [Query.equal('user_id', session['user_id'])])
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
        docs = aw_list(COL_INTEGRITY, [Query.equal('file_path', app_path)])
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
        existing = aw_list(COL_INTEGRITY, [Query.equal('file_path', app_path)])
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
        tl_docs = aw_list(COL_VAULT_TIMELOCKED, [Query.equal('user_id', user_id)])
        for doc in tl_docs:
            aw_delete(COL_VAULT_TIMELOCKED, doc['$id'])
        sessions = aw_list(COL_ACTIVE_SESSIONS, [Query.equal('user_id', user_id)])
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
        docs = aw_list(COL_SECURITY_LOGS, [Query.limit(limit), Query.order_desc('$createdAt')])
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
        users = aw_list(COL_USERS, [Query.limit(100)])
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

@app.route('/')
def index():
    try:
        template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', 'index.html')
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"[TITAN] Template error: {e}")
        return '''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head><meta charset="UTF-8"><title>TITAN SEC</title>
<style>body{background:#050505;color:#a855f7;font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center;}</style>
</head>
<body>
<div>
<div style="font-size:5rem;font-weight:900;">TITAN</div>
<div style="color:#a855f7;font-size:0.75rem;letter-spacing:0.5em;">SEC</div>
<p style="color:#9ca3af;margin-top:1rem;">جاري التحميل...</p>
</div>
</body></html>'''


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
