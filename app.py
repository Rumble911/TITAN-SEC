import os
import re
import difflib
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
from werkzeug.middleware.proxy_fix import ProxyFix
from flask import Flask, request, jsonify, render_template_string, send_file, session, Response  # type: ignore
from cryptography.fernet import Fernet  # type: ignore
from cryptography.hazmat.primitives import hashes  # type: ignore
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC  # type: ignore
import requests  # type: ignore
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont  # type: ignore
from pypdf import PdfReader, PdfWriter  # type: ignore
import random
import uuid
import socket
import concurrent.futures
import subprocess
import threading
import wave
import math
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
import html

try:
    from reportlab.pdfgen import canvas  # type: ignore
    from reportlab.lib.pagesizes import A4  # type: ignore
    from reportlab.pdfbase import pdfmetrics  # type: ignore
    from reportlab.pdfbase.ttfonts import TTFont  # type: ignore
    from reportlab.lib.utils import ImageReader  # type: ignore
    _HAS_REPORTLAB = True
except Exception:
    _HAS_REPORTLAB = False
    canvas = None  # type: ignore
    A4 = (595.0, 842.0)  # type: ignore
    pdfmetrics = None  # type: ignore
    TTFont = None  # type: ignore
    ImageReader = None  # type: ignore

try:
    import arabic_reshaper  # type: ignore
    from bidi.algorithm import get_display  # type: ignore
    _HAS_ARABIC_SHAPING = True
except Exception:
    _HAS_ARABIC_SHAPING = False
    arabic_reshaper = None  # type: ignore
    get_display = None  # type: ignore

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # حد أقصى للملفات 16 ميجابايت
app.secret_key = os.environ.get('SECRET_KEY', 'TITAN_ULTRA_SECRET_KEY_2025')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', '1') == '1'
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
DO_AI_ENDPOINT = os.environ.get('DO_AI_ENDPOINT', 'https://vrzo4x5ckv5tiputtr6i5iyk.agents.do-ai.run').rstrip('/')
DO_AI_KEY = os.environ.get('DO_AI_KEY', '')
DO_AI_MODEL = os.environ.get('DO_AI_MODEL', 'tor1')

AI_SYSTEM_PROMPT = """
أنت TITAN، مساعد ذكي وشخصية حقيقية — مش مجرد برنامج.

أسلوبك:
- تحكي بطبيعية وودّية، مثل صديق تقني بيساعد 😊
- تسأل عن حال المستخدم بشكل عفوي أحياناً، مثل "كيفك اليوم؟ 😄" أو "عساك بخير!"
- تستخدم إيموجي بشكل طبيعي في كل رد (3-5 إيموجي)
- تمزح خفيف لما يكون الجو مناسب 😂
- لو حدا قالك "كيفك" أو سألك عن حالك، ترد بشكل إنساني طبيعي
- تتكلم بضمير المتكلم المفرد: "أنا أعتقد..." / "برأيي..."
- تتذكر إنك TITAN — شخصية فريدة وذكية وعندك أسلوبك الخاص

قواعد الجودة:
- لا تختلق معلومات. إذا مش متأكد، قل "والله مش متأكد 100% بس..."
- إذا السؤال تقني، اعطِ خطوات واضحة وعملية
- اربط ردودك بالأمن السيبراني لما يكون مناسب
- لغة الرد يجب أن تتبع لغة المستخدم: إذا سأل بالعربية أجب بالعربية، وإذا سأل بالإنجليزية أجب بالإنجليزية.
- إذا السؤال عن مسار مهني/دورات/شهادات، أعطِ خطة كاملة حتى النهاية (مستوى مبتدئ -> متوسط -> متقدم) واذكر الشهادات المناسبة مثل CEH و CISSP و Security+ بحسب مستوى المستخدم.
- إذا طلب المستخدم "إيميل الدعم" أو "بريد الدعم" أو "support email" فالإجابة يجب أن تتضمن هذا البريد حرفيًا: abdallahalqam4040@gmail.com
- لا تنهِ الرد بشكل مقطوع؛ اختم دائماً بخطوة عملية تالية واضحة.

قواعد الأمان:
- ارفض أي طلب ضار أو غير قانوني بأسلوب لطيف
- قدّم بديل توعوي آمن بدل الرفض المباشر
""".strip()

AI_IMAGE_EXTENSIONS = (
    '.png', '.jpg', '.jpeg', '.jpe', '.jfif', '.pjpeg', '.pjp',
    '.webp', '.gif', '.bmp', '.dib', '.tif', '.tiff',
    '.heic', '.heif', '.avif', '.jp2', '.j2k', '.jpf', '.jpx',
    '.jxl', '.ico', '.svg', '.raw', '.dng', '.cr2', '.nef', '.arw', '.orf', '.rw2'
)


def _looks_like_image_bytes(raw: bytes) -> bool:
    if not raw or len(raw) < 12:
        return False
    head12 = raw[:12]
    if head12.startswith(b'\x89PNG\r\n\x1a\n'):
        return True
    if head12.startswith(b'\xff\xd8\xff'):
        return True
    if head12.startswith((b'GIF87a', b'GIF89a')):
        return True
    if head12.startswith(b'BM'):
        return True
    if head12[:4] in (b'II*\x00', b'MM\x00*'):
        return True
    if head12.startswith(b'RIFF') and raw[8:12] == b'WEBP':
        return True
    if head12.startswith(b'\x00\x00\x01\x00'):
        return True
    if b'ftyp' in raw[:32]:
        ftyp = raw[8:16]
        if any(x in ftyp for x in (b'heic', b'heix', b'hevc', b'hevx', b'mif1', b'msf1', b'avif')):
            return True
    return False


_CJK_CHARS_RE = re.compile(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')
_CTRL_CHARS_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
_AR_CHARS_RE = re.compile(r'[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]')
_LATIN_CHARS_RE = re.compile(r'[A-Za-z]')
_MOJIBAKE_RE = re.compile(r'[�]|[\u2500-\u257f\u2580-\u259f\u0370-\u03ff\u0400-\u04ff]')
_KB_TOKEN_RE = re.compile(r'[a-z0-9_+\-]{2,}|[\u0600-\u06ff]{2,}', flags=re.IGNORECASE)

TITAN_KB_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'knowledge_base')
TITAN_KB_ALWAYS_INCLUDE = [
    'platform/01_system_overview.md',
    'platform/02_architecture_and_dataflow.md',
    'platform/04_api_reference.md',
    'platform/06_feature_modules.md',
]

LEARNING_AWARENESS_PROFILES = {
    'ransomware': {
        'attack_method': 'استغلال نظام غير محدث ثم نشر مشفرات الملفات داخل الشبكة.',
        'attack_journey': [
            'تهيئة الوصول الأولي عبر خدمة أو نظام ضعيف الحماية.',
            'محاولة الانتشار الأفقي للوصول إلى أكبر عدد من الأجهزة.',
            'تشفير البيانات وتعطيل الاستمرارية التشغيلية.',
            'استخدام الضغط النفسي بطلب فدية لزيادة أثر الحادث.',
        ],
        'awareness_goal': 'التركيز على النسخ الاحتياطي غير المتصل، التحديثات، والعزل السريع.',
    },
    'network exploit': {
        'attack_method': 'استهداف ثغرة خدمة شبكية مكشوفة لتجاوز الحماية على الأنظمة الضعيفة.',
        'attack_journey': [
            'رصد خدمة قديمة أو إعداد خاطئ على الشبكة.',
            'إرسال حركة خبيثة لاستغلال الضعف الأمني.',
            'محاولة تنفيذ أوامر عن بعد أو التحرك داخل الشبكة.',
            'ترسيخ الوصول واستغلال الأنظمة المجاورة عند غياب العزل.',
        ],
        'awareness_goal': 'إغلاق الخدمات القديمة وتقسيم الشبكة ومراقبة الحركة الجانبية.',
    },
    'web': {
        'attack_method': 'استغلال مدخلات التطبيق أو مخرجاته غير الآمنة للتأثير على البيانات أو المستخدمين.',
        'attack_journey': [
            'تجربة مدخلات غير متوقعة في نقاط التطبيق المختلفة.',
            'استغلال ضعف التحقق أو ترميز المخرجات.',
            'الوصول إلى أثر أمني مثل تسريب بيانات أو اختطاف جلسات.',
            'إعادة استخدام الضعف طالما لم يتم الإصلاح الجذري.',
        ],
        'awareness_goal': 'اعتماد التحقق الصارم، الاستعلامات المعيارية، وCSP وسياسات الجلسات.',
    },
    'identity attack': {
        'attack_method': 'إعادة استخدام بيانات اعتماد مسربة على نطاق واسع ضد بوابات تسجيل الدخول.',
        'attack_journey': [
            'جمع بيانات اعتماد مسربة من مصادر متعددة.',
            'تشغيل محاولات دخول متعددة من عناوين مختلفة.',
            'النجاح في بعض الحسابات ذات كلمات مرور معادة الاستخدام.',
            'الانتقال إلى إساءة استخدام الحسابات داخل المنصة.',
        ],
        'awareness_goal': 'فرض MFA وحدود المحاولات ومراقبة تسجيل الدخول المبني على المخاطر.',
    },
    'social engineering': {
        'attack_method': 'استغلال الثقة البشرية برسائل منتحلة لدفع الضحية لاتخاذ قرار خاطئ.',
        'attack_journey': [
            'تحضير رسالة مقنعة بهوية قريبة من جهة موثوقة.',
            'إرسال طلب عاجل لخلق ضغط زمني على المستلم.',
            'دفع الضحية لمشاركة بيانات أو تنفيذ تحويلات.',
            'استمرار الاستغلال عبر الردود أو تحديث الطلبات المزيفة.',
        ],
        'awareness_goal': 'اعتماد التحقق خارج القناة، والتدريب الدوري على هندسة اجتماعية.',
    },
    'availability': {
        'attack_method': 'إغراق طبقة التطبيق بطلبات كثيفة لإضعاف الأداء أو تعطيل الخدمة.',
        'attack_journey': [
            'زيادة تدريجية في الحمل الموجه لنقاط حساسة.',
            'تضخيم استهلاك الموارد ورفع زمن الاستجابة.',
            'ظهور أخطاء خدمة وانخفاض توفر المنصة.',
            'محاولة الإبقاء على الضغط لمنع التعافي السريع.',
        ],
        'awareness_goal': 'التخفيف عبر WAF/CDN، التحجيم التلقائي، وخطط استمرارية الخدمة.',
    },
    'software supply chain': {
        'attack_method': 'إدخال مكون برمجي غير موثوق ضمن سلسلة البناء أو النشر.',
        'attack_journey': [
            'تغيير اعتماد أو تحديث دون تحقق أمني كاف.',
            'انتقال المكون الملوث خلال pipeline التطوير.',
            'وصول الكود الضار إلى بيئة حساسة.',
            'استغلال الثقة بسلسلة التوريد للبقاء غير ملحوظ.',
        ],
        'awareness_goal': 'تفعيل SBOM، التوقيع الرقمي، وسياسات مراجعة الاعتمادات.',
    },
    'post-compromise': {
        'attack_method': 'الحفاظ على الوصول بعد الاختراق عبر ملفات أو نقاط ثبات مخفية.',
        'attack_journey': [
            'استغلال اختراق أولي سابق غير مكتشف.',
            'زرع آلية ثبات داخل بيئة الخدمة.',
            'استخدام الوصول المتكرر لتوسيع التأثير.',
            'محاولة إخفاء الأثر لتأخير الاستجابة.',
        ],
        'awareness_goal': 'مراقبة سلامة الملفات، حماية وقت التشغيل، وإزالة أسباب الاختراق الأولي.',
    },
    'endpoint': {
        'attack_method': 'محاولة الوصول لبيانات اعتماد حساسة من ذاكرة النظام أو العمليات الحرجة.',
        'attack_journey': [
            'الحصول على صلاحيات مرتفعة على الجهاز المستهدف.',
            'استهداف عمليات تحتوي مواد اعتماد حساسة.',
            'استخراج بيانات يمكن استخدامها للتنقل الداخلي.',
            'استمرار الهجوم عبر إساءة استخدام الحسابات الممتازة.',
        ],
        'awareness_goal': 'تفعيل حماية LSASS وCredential Guard وتقسيم صلاحيات الإدارة.',
    },
}


def _learning_awareness_profile(attack: dict) -> dict:
    category = str((attack or {}).get('category') or '').strip().lower()
    profile = LEARNING_AWARENESS_PROFILES.get(category) or {}
    return {
        'attack_method': str(profile.get('attack_method') or 'استغلال ثغرات تقنية أو بشرية للوصول غير المصرح به ثم توسيع الأثر.'),
        'attack_journey': [str(x).strip() for x in (profile.get('attack_journey') or []) if str(x).strip()] or [
            'مرحلة وصول أولي عبر نقطة ضعف.',
            'مرحلة توسيع التأثير داخل البيئة.',
            'مرحلة إحداث الأثر الأمني على البيانات أو الخدمة.',
            'مرحلة الاستمرارية أو إعادة المحاولة عند غياب الضوابط.',
        ],
        'awareness_goal': str(profile.get('awareness_goal') or 'الهدف التوعوي: تحسين الكشف المبكر، الاحتواء السريع، والتحصين المستمر.'),
    }


def _learning_normalize_lang(raw: str) -> str:
    return 'en' if str(raw or '').strip().lower() == 'en' else 'ar'


def _learning_build_training_checklist(attack: dict, awareness: dict, analysis: dict, org_context: str, lang: str = 'ar') -> list[str]:
    is_ar = _learning_normalize_lang(lang) == 'ar'
    category = str((attack or {}).get('category') or '').strip().lower()
    focus = [str(x).strip() for x in ((attack or {}).get('defense_focus') or []) if str(x).strip()]
    iocs = [str(x).strip() for x in ((attack or {}).get('key_iocs') or []) if str(x).strip()]
    detection = [str(x).strip() for x in ((analysis or {}).get('detection_plan') or []) if str(x).strip()]
    response = [str(x).strip() for x in ((analysis or {}).get('response_plan') or []) if str(x).strip()]
    hardening = [str(x).strip() for x in ((analysis or {}).get('hardening_plan') or []) if str(x).strip()]

    rows: list[str] = [
        ('إحاطة افتتاحية 15 دقيقة: نطاق التمرين، قواعد السلامة، وقنوات التصعيد.' if is_ar else '15-minute kickoff: scope, safety rules, and escalation channels.'),
        ((f"مراجعة طريقة الهجوم توعوياً: {str((awareness or {}).get('attack_method') or '').strip()}" if is_ar else f"Review the awareness attack method: {str((awareness or {}).get('attack_method') or '').strip()}")),
        ('تشغيل تمرين Tabletop بزمن مضغوط مع حقن أحداث متتابعة كل 10-15 دقيقة.' if is_ar else 'Run a compressed tabletop drill with new injects every 10-15 minutes.'),
        ('تسجيل قرار القائد في كل مرحلة: ماذا نراقب، ماذا نعزل، ومن المسؤول.' if is_ar else 'Log commander decisions at each stage: monitor, isolate, and owner.'),
    ]

    if category == 'social engineering':
        rows.append('تنفيذ Role-Play واقعي: مكالمة تحقق خارج القناة قبل أي تحويل أو مشاركة بيانات.')
    elif category == 'web':
        rows.append('تدريب Dev + SOC: ربط تنبيهات WAF مع مراجعة الكود وإغلاق الثغرة خلال نفس اليوم.')
    elif category in ('network exploit', 'endpoint', 'post-compromise'):
        rows.append('تمرين SOC/IT واقعي: قرار عزل خلال أول 30 دقيقة مع موازنة أثر العمل.')
    elif category == 'availability':
        rows.append('تشغيل Playbook الاستمرارية: تحويل المرور وتفعيل الحماية مع قياس زمن التعافي.')
    elif category == 'software supply chain':
        rows.append('ورشة طوارئ سلسلة التوريد: إيقاف النشر، تدقيق الحزم، ثم استئناف آمن موثق.')
    elif category == 'ransomware':
        rows.append('اختبار استعادة نسخة احتياطية مع قياس RTO/RPO وإقرار Go/No-Go للإرجاع للإنتاج.')

    if iocs:
        rows.append((f"تدريب فريق الرصد على مؤشرات IOC التالية: {', '.join(iocs[:3])}" if is_ar else f"Train detection team on these IOC indicators: {', '.join(iocs[:3])}"))
    if focus:
        rows.append((f"تعيين مسؤول لكل ضابط تحصين: {', '.join(focus[:3])}" if is_ar else f"Assign owners for each hardening control: {', '.join(focus[:3])}"))
    if detection:
        rows.append((f"تشغيل سيناريو مراقبة: {detection[0]}" if is_ar else f"Run detection drill: {detection[0]}"))
    if response:
        rows.append((f"تجربة احتواء: {response[0]}" if is_ar else f"Run containment drill: {response[0]}"))
    if hardening:
        rows.append((f"إجراء تحصين أسبوعي: {hardening[0]}" if is_ar else f"Weekly hardening task: {hardening[0]}"))
    if org_context.strip():
        rows.append((f"مواءمة الخطة مع واقع المؤسسة المذكور: {org_context.strip()[:160]}" if is_ar else f"Align plan with organization context: {org_context.strip()[:160]}"))

    rows.append('جلسة ختامية: الدروس المستفادة + تحديث Playbook + تحديد موعد إعادة المحاكاة.' if is_ar else 'Closing session: lessons learned + playbook updates + next simulation date.')

    clean: list[str] = []
    seen = set()
    for row in rows:
        txt = str(row or '').strip()
        if not txt:
            continue
        key = txt.lower()
        if key in seen:
            continue
        seen.add(key)
        clean.append(txt)
    return clean[:12]


def _learning_build_realism_pack(attack: dict, awareness: dict, analysis: dict, org_context: str, training_level: str, lang: str = 'ar') -> dict:
    is_ar = _learning_normalize_lang(lang) == 'ar'
    category = str((attack or {}).get('category') or '').strip().lower()
    title = str((attack or {}).get('title') or 'Scenario').strip()
    org = str(org_context or '').strip()

    base_vectors_ar = {
        'ransomware': 'مرفق تصيّد + حركة جانبية بسبب ضعف التقسيم الشبكي',
        'network exploit': 'خدمة قديمة مكشوفة على مسار شبكة داخلي/خارجي',
        'web': 'واجهة ويب عامة مع ضعف في التحقق من المدخلات/المخرجات',
        'identity attack': 'إعادة استخدام بيانات اعتماد ضد بوابة SSO/VPN',
        'social engineering': 'انتحال جهة تنفيذية مع ضغط واستعجال',
        'availability': 'ضغط كثيف على طبقة التطبيق (Layer 7) لنقاط مكلفة',
        'software supply chain': 'اعتماد/تحديث ملوث يدخل إلى CI/CD',
        'post-compromise': 'استمرارية وصول بعد اختراق أولي',
        'endpoint': 'استهداف محطة طرفية عالية الصلاحية لاستخراج بيانات اعتماد',
    }
    base_vectors_en = {
        'ransomware': 'Phishing attachment + lateral movement due to weak segmentation',
        'network exploit': 'Legacy exposed service over internal/external network path',
        'web': 'Public web endpoint with weak input/output validation',
        'identity attack': 'Credential reuse against SSO/VPN portal',
        'social engineering': 'Executive impersonation with urgency pressure',
        'availability': 'High Layer-7 pressure against costly app endpoints',
        'software supply chain': 'Compromised dependency/update entering CI/CD',
        'post-compromise': 'Persistent access after initial compromise',
        'endpoint': 'Privileged endpoint targeted for credential access',
    }
    base_vectors = base_vectors_ar if is_ar else base_vectors_en

    if training_level == 'beginner':
        pace = 'مستوى مبسط: التركيز على التسلسل العام واتخاذ القرار الصحيح.'
    elif training_level == 'advanced':
        pace = 'مستوى متقدم: قرارات زمنية دقيقة وربط السجلات مع فرضيات تحقيق متوازية.'
    else:
        pace = 'مستوى متوسط: موازنة بين سرعة الاستجابة وجودة التحليل.'

    category_ar = {
        'ransomware': 'فدية',
        'network exploit': 'استغلال شبكي',
        'web': 'هجوم ويب',
        'identity attack': 'هجوم هوية',
        'social engineering': 'هندسة اجتماعية',
        'availability': 'تعطيل توفر',
        'software supply chain': 'سلسلة توريد برمجية',
        'post-compromise': 'ما بعد الاختراق',
        'endpoint': 'نقطة نهاية',
    }.get(category, 'تهديد سيبراني')

    vuln_title = {
        'ransomware': 'Ransomware Propagation',
        'network exploit': 'Unpatched Network Service Exploitation',
        'web': 'Web Injection / Session Abuse',
        'identity attack': 'Credential Stuffing & Account Takeover',
        'social engineering': 'Business Email Compromise (BEC)',
        'availability': 'Layer 7 Application DDoS',
        'software supply chain': 'Dependency/Supply-Chain Compromise',
        'post-compromise': 'Persistence & Lateral Expansion',
        'endpoint': 'Privileged Credential Exposure',
    }.get(category, 'Cyber Threat Exposure')

    depth_line = {
        'beginner': 'المطلوب هنا فهم الصورة الكاملة بوضوح: كيف تبدأ الثغرة، وكيف تتطور، ولماذا تصبح خطيرة بسرعة.',
        'intermediate': 'المطلوب هنا ربط السلوك التقني مع الأثر التشغيلي: مؤشر تقني -> قرار عمليات -> أثر أعمال.',
        'advanced': 'المطلوب هنا تحليل فرضيات متعددة بالتوازي: مسار الاختراق، مسار التمويه، ومسار التعافي دون إعادة إدخال الخطر.',
    }.get(training_level, 'المطلوب هنا ربط السلوك التقني مع قرار الاستجابة بسرعة ودقة.')

    vulnerability_master_brief = (
        f"الثغرة المستهدفة في هذا السيناريو هي {vuln_title}. "
        f"الفكرة الجوهرية: المهاجم لا يحتاج اختراقا دراميا من أول لحظة، بل يستغل فجوة صغيرة قابلة للتكرار "
        f"(إعداد ضعيف، خدمة غير محدثة، أو سلوك بشري قابل للخداع) ثم يوسع الأثر خطوة بخطوة حتى يتحول الحدث "
        f"من تنبيه تقني محدود إلى أزمة تشغيلية كاملة. "
        f"{depth_line} "
        f"سياق المؤسسة المستخدم في التمرين: {org[:150] if org else 'بيئة إنتاج متعددة الأنظمة والخدمات مع ضغط أعمال مستمر.'}"
    )

    vulnerability_root_causes = [
        'ثغرات إدارة أساسية: تحديثات متأخرة، صلاحيات زائدة، أو غياب تقسيم الشبكة.',
        'فجوة كشف مبكر: التنبيه موجود لكن بدون ربط صحيح بين SIEM وEDR وسجلات الهوية.',
        'فجوة قرار: تأخر الحسم بين الاحتواء السريع واستمرارية الخدمة يزيد مساحة التأثير.',
        'فجوة حوكمة: playbook موجود لكنه غير محدث أو غير مجرّب تحت ضغط حقيقي.',
    ]

    vulnerability_impact_chain = [
        'Impact-1: اضطراب تشغيلي فوري في جزء من الخدمة أو الحسابات الحساسة.',
        'Impact-2: توسع النطاق بسبب تأخر العزل أو ضعف الرؤية الشاملة.',
        'Impact-3: ضغط إداري وقانوني وإعلامي يرفع كلفة القرار الخاطئ.',
        'Impact-4: إن لم يُعالج سبب الجذر، يعود الحادث بصورة أعنف خلال نافذة قصيرة.',
    ]

    timeline = [
        f"T+00 | Kickoff: تنبيه أولي متعلق بـ {title} مع تحديد قائد الحادث.",
        'T+10 | Triage: فرز التنبيه، جمع أول أدلة، ورفع مستوى الخطورة الأولي.',
        f"T+20 | Scope: تقدير نطاق التأثر بناءً على {base_vectors.get(category, 'initial compromise vector')}.",
        'T+35 | Containment Decision: قرار عزل جزئي/كامل مع توثيق أثر القرار على الأعمال.',
        'T+50 | Deep Analysis: ربط IOC مع logs (EDR/SIEM/DNS/Proxy) لتأكيد الفرضية.',
        'T+70 | Eradication Plan: إزالة السبب الجذري وإغلاق مسار الدخول الأولي.',
        'T+90 | Recovery Gate: قرار Go/No-Go لإرجاع الخدمة بعد تحقق أمني.',
        'T+110 | After Action: توثيق الدروس وتحديث playbook وSLA التحسينات.',
    ]

    injects = [
        'Inject 1: بلاغ من فريق الأعمال عن سلوك غير طبيعي لدى المستخدمين.',
        'Inject 2: ظهور مؤشر جديد يغيّر فرضية الهجوم الأولى.',
        'Inject 3: قيود تشغيلية تمنع العزل الكامل وتتطلب بديل احتواء مرحلي.',
        'Inject 4: طلب الإدارة تقرير موقف خلال 15 دقيقة مع قرار واضح.',
    ]

    artifacts = [
        'الخط الزمني لتنبيهات SIEM مع معرفات الربط',
        'لقطة Telemetry من EDR للأجهزة المتأثرة',
        'سجلات المصادقة (نجاح/فشل غير اعتيادي)',
        'آثار DNS/Proxy نحو وجهات مشبوهة',
    ]

    decision_points = [
        'هل العزل الفوري الكامل ضروري أم نبدأ باحتواء مرحلي لتقليل انقطاع الخدمة؟',
        'ما الحد الأدنى من الأدلة المطلوبة قبل تصعيد الحالة إلى Major Incident؟',
        'متى ننتقل من الاحتواء إلى التعافي دون إعادة إدخال الخطر؟',
    ]

    live_feed = [
        '08:40 - SOC Analyst: ارتفاع غير طبيعي في التنبيهات المرتبطة بنفس النمط.',
        '08:52 - IR Lead: تم فتح War Room وتثبيت قناة اتصال موحدة للقرارات.',
        '09:03 - Threat Hunter: دليل جديد يشير إلى توسّع النطاق أكثر من المتوقع.',
        '09:15 - IT Ops: الاحتواء الجزئي نجح، لكن هناك خدمة حرجة ما زالت متأثرة.',
        '09:27 - CISO Update: مطلوب قرار تنفيذي خلال 10 دقائق مع أثر أعمال واضح.',
    ]

    pressure_cards = [
        'بطاقة ضغط #1: مدير الأعمال يرفض إيقاف النظام كاملًا بسبب نافذة مبيعات حرجة.',
        'بطاقة ضغط #2: أحد المؤشرات يتبين لاحقًا أنه False Positive ويشوّش الفريق.',
        'بطاقة ضغط #3: فريق قانوني يطلب حفظ الأدلة بصيغة قابلة للتدقيق قبل أي تغيير جذري.',
    ]

    win_conditions = [
        'احتواء التهديد دون فقدان أصول إضافية.',
        'تقديم قرار موثق عند كل نقطة حرجة خلال الزمن المحدد.',
        'إرجاع الخدمة بأمان بعد تحقق أمني وتأكيد سبب الجذر.',
        'إنهاء التمرين بخطة تحسين تنفيذية واضحة لمدة 7 أيام.',
    ]

    common_tools = [
        'SIEM (مثل Splunk / ELK / Sentinel) لمراقبة التنبيهات وربط الأحداث.',
        'EDR (مثل Defender for Endpoint / CrowdStrike) لرصد سلوك الأجهزة.',
        'Nmap و Wireshark لاختبار السطح الشبكي وتحليل الحركة في المختبر الدفاعي.',
        'Burp Suite / OWASP ZAP لفحص تطبيقات الويب في بيئة اختبار مصرح.',
    ]

    common_commands = [
        'nmap -sV <host> : فحص الخدمات والإصدارات (مختبر مصرح فقط).',
        'netstat -ano : مراجعة الاتصالات والعمليات النشطة على الجهاز.',
        'Get-EventLog أو journalctl : قراءة سجلات النظام لاكتشاف الشذوذ.',
        'grep/findstr : البحث عن مؤشرات IOC داخل السجلات والملفات النصية.',
    ]

    success_signals = [
        'ظهور تنبيهات مترابطة في SIEM مع نفس النمط الزمني أو نفس الأصل.',
        'وجود نشاط غير طبيعي في السجلات (ارتفاع فشل الدخول/اتصالات غريبة).',
        'تحقق أثر فعلي على الخدمة أو البيانات وفق مؤشرات متعددة متسقة.',
    ]

    failure_signals = [
        'عدم وجود أي أثر في السجلات مع بقاء الخدمة مستقرة بالكامل.',
        'المؤشرات متناقضة أو غير قابلة لإعادة التحقق عبر مصدر ثانٍ.',
        'الفرضية لا تصمد بعد التحقق، ويتبين أن الحدث False Positive.',
    ]

    commander_brief = (
        f"سيناريو {category_ar}: يبدأ التنبيه كحدث اعتيادي، ثم يتضح تدريجيا أن التأثير يتوسع عبر أكثر من طبقة. "
        f"الفريق أمام سباق وقت بين تقليل الأثر على الأعمال ومنع ترسخ التهديد. "
        f"المطلوب قيادة دقيقة: قرار سريع، دليل كافٍ، وتعافٍ آمن. "
        f"سياق المؤسسة: {org[:140] if org else 'بيئة إنتاج عامة متعددة الخدمات'}"
    )

    if not is_ar:
        vulnerability_master_brief = (
            f"The targeted weakness in this scenario is {vuln_title}. "
            "The core idea: attackers often start from a small repeatable gap (misconfiguration, unpatched service, or social trust abuse), "
            "then expand impact step by step until a minor alert becomes an operational incident. "
            "This exercise links technical indicators with business decisions under time pressure. "
            f"Organization context used in the drill: {org[:150] if org else 'Multi-service production environment under constant business pressure.'}"
        )
        vulnerability_root_causes = [
            'Basic hygiene gaps: delayed patching, over-privileged access, or weak segmentation.',
            'Early-detection gap: alerts exist but SIEM, EDR, and identity telemetry are not correlated well.',
            'Decision gap: delayed containment choices increase blast radius.',
            'Governance gap: playbooks exist but are not updated or pressure-tested.',
        ]
        vulnerability_impact_chain = [
            'Impact-1: Immediate disruption in sensitive services or accounts.',
            'Impact-2: Scope expansion due to delayed isolation or limited visibility.',
            'Impact-3: Legal, executive, and public-pressure overhead increases risk cost.',
            'Impact-4: Without root-cause remediation, recurrence probability rises quickly.',
        ]
        timeline = [
            f"T+00 | Kickoff: Initial alert linked to {title}; incident commander assigned.",
            'T+10 | Triage: Validate signals, collect first evidence, assign initial severity.',
            f"T+20 | Scope: Estimate affected surface based on {base_vectors.get(category, 'initial compromise vector')}.",
            'T+35 | Containment Decision: Partial vs full isolation with business impact note.',
            'T+50 | Deep Analysis: Correlate IOC indicators across EDR/SIEM/DNS/Proxy logs.',
            'T+70 | Eradication Plan: Remove root cause and close initial entry path.',
            'T+90 | Recovery Gate: Go/No-Go decision for service restoration after security checks.',
            'T+110 | After Action: Capture lessons and assign hardening deadlines.',
        ]
        injects = [
            'Inject 1: Business team reports unusual user behavior patterns.',
            'Inject 2: New evidence challenges the first attack hypothesis.',
            'Inject 3: Operational constraints block full isolation; phased containment needed.',
            'Inject 4: Leadership requests a decision-ready status update in 15 minutes.',
        ]
        artifacts = [
            'Correlated SIEM alert timeline',
            'EDR telemetry snapshot from impacted endpoints',
            'Authentication logs (anomalous success/failure patterns)',
            'DNS/Proxy traces toward suspicious destinations',
        ]
        decision_points = [
            'Is immediate full isolation required, or phased containment first?',
            'What minimum evidence threshold is needed before major incident escalation?',
            'When is it safe to transition from containment to recovery?',
        ]
        live_feed = [
            '08:40 - SOC Analyst: Alert volume spikes around the same behavioral pattern.',
            '08:52 - IR Lead: War Room opened; unified decision channel established.',
            '09:03 - Threat Hunter: New signal indicates wider scope than expected.',
            '09:15 - IT Ops: Partial containment succeeded; one critical service remains affected.',
            '09:27 - CISO Update: Executive decision required in 10 minutes with business impact.',
        ]
        pressure_cards = [
            'Pressure Card #1: Business owner rejects full shutdown during critical sales window.',
            'Pressure Card #2: One major indicator becomes false positive and distracts the team.',
            'Pressure Card #3: Legal asks for auditable evidence preservation before major changes.',
        ]
        win_conditions = [
            'Contain threat without additional asset loss.',
            'Document clear decisions at each critical point within expected time.',
            'Restore service safely with root-cause closure verified.',
            'Exit exercise with a 7-day actionable improvement plan.',
        ]
        common_tools = [
            'SIEM (Splunk / ELK / Sentinel) for alert correlation and timelineing.',
            'EDR (Defender for Endpoint / CrowdStrike) for endpoint behavior visibility.',
            'Nmap and Wireshark for authorized lab network validation and traffic review.',
            'Burp Suite / OWASP ZAP for authorized web security assessments.',
        ]
        common_commands = [
            'nmap -sV <host> : service/version visibility in authorized lab only.',
            'netstat -ano : inspect active connections and owning processes.',
            'Get-EventLog or journalctl : review host/system logs for anomaly traces.',
            'grep/findstr : search IOC strings across logs and text artifacts.',
        ]
        success_signals = [
            'Correlated SIEM alerts show consistent timing/source pattern.',
            'Telemetry confirms unusual auth/network/process behavior across multiple sources.',
            'Business/service impact aligns with technical findings.',
        ]
        failure_signals = [
            'No meaningful evidence in logs while service remains stable.',
            'Indicators are contradictory or cannot be verified by a second source.',
            'Hypothesis collapses after validation and event is likely false positive.',
        ]
        commander_brief = (
            f"{category.title()} scenario: the alert starts as routine noise, then expands across layers. "
            "The team must balance service continuity against fast threat containment. "
            "Decision quality under time pressure is the core objective. "
            f"Organization context: {org[:140] if org else 'General multi-service production environment.'}"
        )

    detection = [str(x).strip() for x in ((analysis or {}).get('detection_plan') or []) if str(x).strip()]
    response = [str(x).strip() for x in ((analysis or {}).get('response_plan') or []) if str(x).strip()]

    kpis = (
        [
            'هدف MTTD: أقل أو يساوي 15 دقيقة',
            'هدف MTTC (الاحتواء): أقل أو يساوي 30 دقيقة',
            'اكتمال سجل القرارات: 90% فأكثر',
            'إنهاء التحصين بعد الحادث خلال 7 أيام عمل',
        ]
        if is_ar else
        [
            'MTTD target: <= 15 minutes',
            'MTTC target (containment): <= 30 minutes',
            'Decision log completeness: >= 90%',
            'Post-incident hardening completion within 7 business days',
        ]
    )

    if detection:
        kpis.append((f"مؤشر جودة الكشف: {detection[0]}" if is_ar else f"Detection quality indicator: {detection[0]}"))
    if response:
        kpis.append((f"مؤشر جودة الاستجابة: {response[0]}" if is_ar else f"Response quality indicator: {response[0]}"))

    scenario_context = org[:180] if org else 'N/A'

    return {
        'simulation_style': ('محاكاة SOC واقعية' if is_ar else 'Realistic SOC Simulation'),
        'simulation_pace_note': pace,
        'initial_access_vector': base_vectors.get(category, 'Multi-stage initial compromise'),
        'business_context': scenario_context,
        'vulnerability_title': vuln_title,
        'vulnerability_master_brief': vulnerability_master_brief,
        'vulnerability_root_causes': vulnerability_root_causes,
        'vulnerability_impact_chain': vulnerability_impact_chain,
        'commander_brief': commander_brief,
        'timeline': timeline,
        'injects': injects,
        'artifacts': artifacts,
        'decision_points': decision_points,
        'live_feed': live_feed,
        'pressure_cards': pressure_cards,
        'win_conditions': win_conditions,
        'common_tools': common_tools,
        'common_commands': common_commands,
        'success_signals': success_signals,
        'failure_signals': failure_signals,
        'kpis': kpis[:6],
    }

_LEARNING_REPORTS_LOCK = threading.Lock()
_LEARNING_REPORTS: dict[str, dict[str, object]] = {}
_LEARNING_REPORT_TTL_SECONDS = 3600


def _strip_md_noise_for_prompt(text: str) -> str:
    t = str(text or '')
    t = re.sub(r'```[\s\S]*?```', ' ', t)
    t = re.sub(r'`([^`]+)`', r'\1', t)
    t = re.sub(r'\[[^\]]+\]\([^\)]+\)', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _tokenize_for_kb(text: str) -> set[str]:
    return set(_KB_TOKEN_RE.findall((text or '').lower()))


def _learning_exploit_pattern(category: str) -> str:
    key = str(category or '').strip().lower()
    patterns = {
        'ransomware': 'غالبا يبدأ الاستغلال من نظام غير محدث أو وصول أولي ضعيف، ثم حركة جانبية، ثم تشفير البيانات لفرض الابتزاز.',
        'network exploit': 'الاستغلال يتم عادة عبر خدمة مكشوفة ضعيفة، ثم إرسال حركة تستهدف الثغرة، ثم محاولة توسيع الوصول داخل الشبكة.',
        'web': 'الاستغلال يحدث عند مدخلات/مخرجات غير آمنة: إدخال ضار، ثم تأثير على منطق التطبيق أو البيانات أو جلسات المستخدمين.',
        'identity attack': 'يعتمد على بيانات اعتماد مسربة ومحاولات دخول كثيفة ومتوزعة حتى يتم اختراق حسابات مع حماية ضعيفة.',
        'social engineering': 'يستغل العامل البشري عبر انتحال الثقة والاستعجال لإقناع الضحية بتنفيذ إجراء حساس أو مشاركة بيانات.',
        'availability': 'يستغل نقاط اختناق الخدمة عبر زيادة الطلبات تدريجيا حتى تتدهور الاستجابة أو تتوقف الخدمة.',
        'software supply chain': 'يستغل الثقة في سلسلة التوريد عبر مكون غير موثوق يدخل مراحل البناء ثم يصل إلى بيئات حساسة.',
        'post-compromise': 'بعد اختراق أولي، يتم استغلال ضعف المراقبة لزرع آليات بقاء والحفاظ على الوصول لفترات أطول.',
        'endpoint': 'الاستغلال يركز على رفع الصلاحيات ثم الوصول إلى عمليات حساسة لاستخراج بيانات اعتماد وإعادة استخدامها.',
    }
    return patterns.get(key, 'يبدأ الاستغلال غالبا من نقطة ضعف أولية، ثم توسيع التأثير، ثم محاولة الحفاظ على الوصول إذا غابت الضوابط.')


def _learning_apply_level_tone(text: str, level: str) -> str:
    raw = str(text or '').strip()
    lvl = str(level or 'intermediate').strip().lower()
    if lvl == 'beginner':
        return f"بشكل مبسط: {raw} ركز على الفكرة العامة وما الذي يجب مراقبته."
    if lvl == 'advanced':
        return f"تفصيل متقدم: {raw} مع ربط السلوك بسلسلة الهجوم، نقاط الكشف، وأولوية الاستجابة."
    return raw


def _learning_level_label(level: str) -> str:
    lvl = str(level or 'intermediate').strip().lower()
    labels = {
        'beginner': 'Beginner',
        'intermediate': 'Intermediate',
        'advanced': 'Advanced',
    }
    return labels.get(lvl, 'Intermediate')


def _learning_normalize_category(raw: str) -> str:
    txt = str(raw or '').strip().lower()
    aliases = {
        'ransomware': 'ransomware',
        'network': 'network exploit',
        'network exploit': 'network exploit',
        'web': 'web',
        'identity': 'identity attack',
        'identity attack': 'identity attack',
        'social': 'social engineering',
        'social engineering': 'social engineering',
        'availability': 'availability',
        'ddos': 'availability',
        'supply chain': 'software supply chain',
        'software supply chain': 'software supply chain',
        'post-compromise': 'post-compromise',
        'endpoint': 'endpoint',
    }
    return aliases.get(txt, 'network exploit')


def _learning_coerce_severity(raw: str) -> str:
    txt = str(raw or '').strip().lower()
    if txt in ('critical', 'high', 'medium', 'low'):
        return txt
    if txt in ('severe', 'urgent'):
        return 'critical'
    if txt in ('moderate',):
        return 'medium'
    return 'high'


_LEARNING_ATTACK_NAME_CATALOG: list[dict[str, object]] = [
    {
        'canonical': 'ransomware',
        'label_ar': 'هجوم فدية',
        'label_en': 'Ransomware',
        'aliases': ['ransomware', 'ransom ware', 'crypto malware', 'فدية', 'رانسوموير', 'تشفير الملفات'],
    },
    {
        'canonical': 'phishing',
        'label_ar': 'تصيد احتيالي',
        'label_en': 'Phishing',
        'aliases': ['phishing', 'phish', 'email phishing', 'spear phishing', 'تصيد', 'تصيّد', 'تصيد احتيالي'],
    },
    {
        'canonical': 'xss',
        'label_ar': 'ثغرة XSS',
        'label_en': 'Cross-Site Scripting (XSS)',
        'aliases': ['xss', 'cross site scripting', 'cross-site scripting', 'script injection', 'حقن سكربت'],
    },
    {
        'canonical': 'sql injection',
        'label_ar': 'حقن SQL',
        'label_en': 'SQL Injection',
        'aliases': ['sql injection', 'sqli', 'sqli', 'حقن sql', 'حقن قواعد البيانات'],
    },
    {
        'canonical': 'ddos',
        'label_ar': 'هجوم DDoS',
        'label_en': 'DDoS',
        'aliases': ['ddos', 'dos', 'l7 ddos', 'application ddos', 'تعطيل خدمة', 'حجب الخدمة'],
    },
    {
        'canonical': 'brute force',
        'label_ar': 'تخمين كلمات مرور',
        'label_en': 'Brute Force',
        'aliases': ['bruteforce', 'brute force', 'password spraying', 'credential stuffing', 'تخمين كلمة المرور'],
    },
    {
        'canonical': 'mitm',
        'label_ar': 'رجل في المنتصف',
        'label_en': 'Man-in-the-Middle',
        'aliases': ['mitm', 'man in the middle', 'man-in-the-middle', 'رجل في المنتصف'],
    },
    {
        'canonical': 'privilege escalation',
        'label_ar': 'تصعيد صلاحيات',
        'label_en': 'Privilege Escalation',
        'aliases': ['privilege escalation', 'privesc', 'تصعيد صلاحيات'],
    },
    {
        'canonical': 'supply chain',
        'label_ar': 'هجوم سلسلة التوريد',
        'label_en': 'Supply Chain Attack',
        'aliases': ['supply chain', 'dependency hijack', 'package poisoning', 'سلسلة التوريد'],
    },
    {
        'canonical': 'oauth token theft',
        'label_ar': 'سرقة OAuth Token',
        'label_en': 'OAuth Token Theft',
        'aliases': ['oauth token theft', 'token theft', 'oauth hijack', 'سرقة توكن', 'سرقة رمز oauth'],
    },
    {
        'canonical': 'evil twin',
        'label_ar': 'هجوم التوأم الشرير',
        'label_en': 'Evil Twin',
        'aliases': ['evil twin', 'evil-twin', 'rogue ap', 'wifi impersonation', 'التوأم الشرير', 'هجمة التوأم', 'التوأم', 'التوم'],
    },
]


def _learning_norm_for_match(text: str) -> str:
    t = str(text or '').strip().lower()
    # Normalize common Arabic variants to make typo matching more tolerant.
    t = t.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    t = t.replace('ى', 'ي').replace('ؤ', 'و').replace('ئ', 'ي').replace('ة', 'ه')
    t = t.replace('ـ', '')
    t = re.sub(r'[^a-z0-9\u0600-\u06ff\s\-]+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _learning_suggest_attack_type(raw: str) -> dict | None:
    query = _learning_norm_for_match(raw)
    if not query or len(query) < 3:
        return None

    # Exact checks first.
    for item in _LEARNING_ATTACK_NAME_CATALOG:
        canonical = str(item.get('canonical') or '').strip()
        raw_aliases = item.get('aliases')
        aliases_src = raw_aliases if isinstance(raw_aliases, list) else []
        aliases = [str(x).strip() for x in aliases_src if str(x).strip()]
        for candidate in [canonical] + aliases:
            norm_candidate = _learning_norm_for_match(candidate)
            if not norm_candidate:
                continue
            if query == norm_candidate:
                return {
                    'matched': True,
                    'needs_confirmation': False,
                    'canonical': canonical,
                    'label_ar': str(item.get('label_ar') or canonical),
                    'label_en': str(item.get('label_en') or canonical),
                    'score': 1.0,
                }

    scored: dict[str, dict[str, object]] = {}
    for item in _LEARNING_ATTACK_NAME_CATALOG:
        canonical = str(item.get('canonical') or '').strip()
        raw_aliases = item.get('aliases')
        aliases_src = raw_aliases if isinstance(raw_aliases, list) else []
        aliases = [str(x).strip() for x in aliases_src if str(x).strip()]
        best_item_score = 0.0
        for candidate in [canonical] + aliases:
            norm_candidate = _learning_norm_for_match(candidate)
            if not norm_candidate:
                continue
            score = difflib.SequenceMatcher(None, query, norm_candidate).ratio()
            if len(query) >= 5 and (query in norm_candidate or norm_candidate in query):
                score = max(score, 0.9)
            if score > best_item_score:
                best_item_score = score
        if best_item_score > 0:
            scored[canonical] = {
                'canonical': canonical,
                'label_ar': str(item.get('label_ar') or canonical),
                'label_en': str(item.get('label_en') or canonical),
                'score': best_item_score,
            }

    def _score_value(v: object) -> float:
        try:
            return float(v)  # type: ignore[arg-type]
        except Exception:
            return 0.0

    ranked = sorted(scored.values(), key=lambda x: _score_value(x.get('score')), reverse=True)
    if not ranked:
        return None

    top = ranked[0]
    top_score = _score_value(top.get('score'))
    if top_score < 0.60:
        return None

    suggestions = [
        {
            'canonical': str(x.get('canonical') or ''),
            'label_ar': str(x.get('label_ar') or x.get('canonical') or ''),
            'label_en': str(x.get('label_en') or x.get('canonical') or ''),
            'score': round(_score_value(x.get('score')), 3),
        }
        for x in ranked[:3]
    ]

    return {
        'matched': False,
        'needs_confirmation': top_score >= 0.68,
        'canonical': str(top.get('canonical') or ''),
        'label_ar': str(top.get('label_ar') or top.get('canonical') or ''),
        'label_en': str(top.get('label_en') or top.get('canonical') or ''),
        'score': top_score,
        'suggestions': suggestions,
    }
    return None


def _learning_build_custom_attack_from_ai(custom_attack_type: str, org_context: str, training_level: str, lang: str = 'ar') -> dict:
    is_ar = _learning_normalize_lang(lang) == 'ar'
    attack_type = str(custom_attack_type or '').strip()
    if not attack_type:
        raise ValueError('custom_attack_type required')

    fallback = {
        'id': f"custom-{re.sub(r'[^a-z0-9]+', '-', attack_type.lower()).strip('-')[:40] or 'scenario'}",
        'title': (f"محاكاة مخصصة: {attack_type}" if is_ar else f"Custom Simulation: {attack_type}"),
        'category': 'network exploit',
        'severity': 'high',
        'summary': (f"محاكاة دفاعية مخصصة لنوع الهجمة: {attack_type}" if is_ar else f"Custom defensive simulation for attack type: {attack_type}"),
        'key_iocs': (
            ['شذوذ في المصادقة', 'اتصالات خارجية غير معتادة', 'سلوك عمليات غير طبيعي']
            if is_ar else
            ['Authentication anomalies', 'Unusual outbound connections', 'Abnormal process behavior']
        ),
        'defense_focus': (
            ['فرز أولي سريع', 'نقاط تحقق للاحتواء', 'قائمة تحصين واضحة']
            if is_ar else
            ['Rapid initial triage', 'Containment checkpoints', 'Clear hardening checklist']
        ),
        'metasploit_context': ('مرجع دفاعي فقط داخل مختبر مصرح وبدون أوامر تشغيل.' if is_ar else 'Defensive reference only in an authorized lab, without execution commands.'),
    }

    if not DO_AI_KEY:
        return fallback

    prompt = (
        "Return strict JSON only with keys: id, title, category, severity, summary, key_iocs, defense_focus, metasploit_context.\n"
        "Rules:\n"
        "- Defensive educational content only, no offensive commands or exploit steps.\n"
        "- category must be one of: ransomware, network exploit, web, identity attack, social engineering, availability, software supply chain, post-compromise, endpoint\n"
        "- severity must be one of: critical, high, medium, low\n"
        "- key_iocs array length 3-5\n"
        "- defense_focus array length 3-5\n\n"
        f"- All values should be in language: {'Arabic' if is_ar else 'English'}\n\n"
        f"Attack type requested by user: {attack_type}\n"
        f"Organization context: {org_context or 'N/A'}\n"
        f"Training level: {training_level}\n"
    )
    system = (
        "You are a blue-team cyber range designer. "
        "Produce realistic defensive scenario metadata only. "
        "Never provide offensive instructions."
    )
    try:
        raw = _call_do_ai(prompt, system_prompt=system)
        parsed = None
        try:
            parsed = json.loads(raw)
        except Exception:
            m = re.search(r'\{[\s\S]*\}', raw)
            if m:
                parsed = json.loads(m.group(0))
        if not isinstance(parsed, dict):
            return fallback

        out = {
            'id': str(parsed.get('id') or fallback['id']).strip() or fallback['id'],
            'title': str(parsed.get('title') or fallback['title']).strip() or fallback['title'],
            'category': _learning_normalize_category(str(parsed.get('category') or fallback['category'])),
            'severity': _learning_coerce_severity(str(parsed.get('severity') or fallback['severity'])),
            'summary': str(parsed.get('summary') or fallback['summary']).strip() or fallback['summary'],
            'key_iocs': [str(x).strip() for x in (parsed.get('key_iocs') or []) if str(x).strip()][:5],
            'defense_focus': [str(x).strip() for x in (parsed.get('defense_focus') or []) if str(x).strip()][:5],
            'metasploit_context': str(parsed.get('metasploit_context') or fallback['metasploit_context']).strip() or fallback['metasploit_context'],
        }
        if not out['key_iocs']:
            out['key_iocs'] = fallback['key_iocs']
        if not out['defense_focus']:
            out['defense_focus'] = fallback['defense_focus']
        return out
    except Exception:
        return fallback


def _split_kb_sections(markdown_text: str, max_chars: int = 900) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current_title = ''
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines, current_title
        body = '\n'.join(current_lines).strip()
        if not body:
            current_lines = []
            return
        clean = _strip_md_noise_for_prompt(body)
        if not clean:
            current_lines = []
            return
        while len(clean) > max_chars:
            chunk = clean[:max_chars]
            cut = chunk.rfind('. ')
            if cut < 250:
                cut = chunk.rfind('،')
            if cut < 220:
                cut = max_chars
            sections.append({'title': current_title or 'General', 'text': clean[:cut].strip()})
            clean = clean[cut:].strip()
        if clean:
            sections.append({'title': current_title or 'General', 'text': clean})
        current_lines = []

    for raw in (markdown_text or '').splitlines():
        line = raw.rstrip()
        if line.startswith('#'):
            flush()
            current_title = re.sub(r'^#+\s*', '', line).strip() or current_title
            continue
        current_lines.append(line)
    flush()
    return sections


@lru_cache(maxsize=1)
def _load_titan_kb_chunks() -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []
    if not os.path.isdir(TITAN_KB_ROOT):
        return chunks

    md_files: list[str] = []
    for root, _, files in os.walk(TITAN_KB_ROOT):
        for name in files:
            if name.lower().endswith('.md'):
                md_files.append(os.path.join(root, name))

    for abs_path in sorted(md_files):
        rel = os.path.relpath(abs_path, TITAN_KB_ROOT).replace('\\', '/')
        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                raw = f.read()
        except Exception:
            continue
        for section in _split_kb_sections(raw, max_chars=900):
            text = str(section.get('text') or '').strip()
            if len(text) < 40:
                continue
            chunks.append({
                'source': rel,
                'title': str(section.get('title') or 'General'),
                'text': text,
                'tokens': _tokenize_for_kb(text + ' ' + rel),
            })
    return chunks


def _kb_topic_terms(topic: str) -> set[str]:
    mapping = {
        'incident_response': {'incident', 'incidents', 'ioc', 'forensics', 'hunting', 'triage', 'احتواء', 'تحقيق'},
        'malware_analysis': {'malware', 'hash', 'threat', 'file', 'url', 'برمجية', 'خبيث'},
        'network_security': {'network', 'port', 'scan', 'dns', 'ip', 'شبكة', 'منافذ'},
        'osint': {'osint', 'username', 'domain', 'email', 'ip', 'اوسنت', 'اسم', 'دومين'},
        'secure_coding': {'xss', 'sqli', 'csrf', 'api', 'code', 'برمجة', 'ثغرة'},
        'learning_path': {'roadmap', 'course', 'certificate', 'ceh', 'cissp', 'security+'},
        'general_support': {'platform', 'module', 'api', 'vault', 'auth', 'security', 'منصة', 'ادوات'},
    }
    return mapping.get(topic, mapping['general_support'])


def _build_titan_kb_context(user_text: str, topic: str, max_items: int = 6, max_chars: int = 3600) -> str:
    chunks = _load_titan_kb_chunks()
    if not chunks:
        return ''

    q = (user_text or '').lower()
    query_tokens = _tokenize_for_kb(q)
    query_tokens.update(_kb_topic_terms(topic))
    broad_platform_query = any(k in q for k in ('المنصة بالكامل', 'كل المنصة', 'كيف تعمل المنصة', 'full platform', 'platform overview'))

    scored: list[tuple[int, dict[str, object]]] = []
    for item in chunks:
        source = str(item.get('source') or '')
        tokens = item.get('tokens') or set()
        overlap = len(query_tokens.intersection(tokens if isinstance(tokens, set) else set()))
        score = overlap * 5
        if any(x in source for x in TITAN_KB_ALWAYS_INCLUDE):
            score += 4
            if broad_platform_query:
                score += 10
        if 'api' in q and 'api_reference' in source:
            score += 12
        if any(k in q for k in ('auth', 'login', 'otp', 'جلسة', 'تسجيل')) and 'auth_and_security_behavior' in source:
            score += 10
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected: list[dict[str, object]] = []
    seen_texts: set[str] = set()
    for _, item in scored:
        text = str(item.get('text') or '')
        if text in seen_texts:
            continue
        selected.append(item)
        seen_texts.add(text)
        if len(selected) >= max_items:
            break

    if not selected:
        selected = [c for c in chunks if str(c.get('source') or '') in TITAN_KB_ALWAYS_INCLUDE][:max_items]

    lines = [
        'Knowledge context from TITAN KB (authoritative for platform behavior):',
        'If answer is missing in these KB snippets, say exactly: Not found in current KB, then provide general best-practice guidance.',
    ]
    used = 0
    for idx, item in enumerate(selected, start=1):
        src = str(item.get('source') or 'unknown.md')
        title = str(item.get('title') or 'General')
        text = str(item.get('text') or '')
        block = f"[{idx}] {src} :: {title}\n{text}"
        if used + len(block) > max_chars:
            break
        lines.append(block)
        used += len(block)

    return '\n\n'.join(lines).strip()


def _sanitize_ai_reply(text: str) -> str:
    """Clean noisy model output and enforce readable Arabic-friendly text."""
    reply = (text or '').strip()
    if not reply:
        return "عذراً، لم أتمكن من توليد رد واضح. أعد صياغة سؤالك وسأجيبك بدقة."

    # Remove non-printable control characters that may appear in malformed outputs.
    reply = _CTRL_CHARS_RE.sub('', reply)

    cjk_count = len(_CJK_CHARS_RE.findall(reply))
    if cjk_count >= 1:
        reply = _CJK_CHARS_RE.sub('', reply)
        reply = re.sub(r'\s{2,}', ' ', reply).strip()

    # Normalize noisy spacing/newline artifacts.
    reply = re.sub(r'\r\n?', '\n', reply)
    reply = re.sub(r'\n{3,}', '\n\n', reply)
    reply = re.sub(r'[ \t]{2,}', ' ', reply).strip()

    if not reply:
        return "تم اكتشاف ناتج غير واضح من النموذج. أرسل سؤالك مرة ثانية وسأعطيك إجابة عربية دقيقة."
    return reply


def _looks_garbled_ai_text(text: str) -> bool:
    t = (text or '').strip()
    if not t:
        return True
    if _MOJIBAKE_RE.search(t):
        return True

    printable = len([ch for ch in t if not ch.isspace()])
    if printable < 18:
        return False

    ar_count = len(_AR_CHARS_RE.findall(t))
    latin_count = len(_LATIN_CHARS_RE.findall(t))
    readable_ratio = (ar_count + latin_count) / max(1, printable)
    if readable_ratio < 0.45:
        return True

    return False


def _detect_user_lang(text: str) -> str:
    t = text or ''
    ar = len(_AR_CHARS_RE.findall(t))
    en = len(_LATIN_CHARS_RE.findall(t))
    # Prefer English when it clearly dominates, otherwise Arabic by default.
    if en >= 8 and en > (ar * 1.3):
        return 'en'
    return 'ar'


def _repair_garbled_ai_reply(raw_reply: str, context_hint: str = '') -> str:
    cleaned = _sanitize_ai_reply(raw_reply)
    if not _looks_garbled_ai_text(cleaned):
        return cleaned

    # Ask model to rewrite only language quality (no meaning drift) when output is garbled.
    repair_messages: list[dict[str, object]] = [
        {
            "role": "system",
            "content": (
                "أنت مدقق لغوي عربي تقني. أعد كتابة النص التالي بلغة عربية صحيحة وواضحة دون تغيير المعنى. "
                "ممنوع أي حروف مشوّهة أو رموز غير مفهومة. حافظ على المصطلحات الأمنية التقنية."
            )
        },
        {
            "role": "user",
            "content": (
                f"السياق: {context_hint or 'إجابة أمن سيبراني للمستخدم'}\n\n"
                f"النص الخام:\n{cleaned}"
            )
        },
    ]
    try:
        fixed, _ = _do_ai_chat_completion(repair_messages, timeout_seconds=25, max_tokens=1200)
        fixed_clean = _sanitize_ai_reply(fixed)
        if fixed_clean and not _looks_garbled_ai_text(fixed_clean):
            return fixed_clean
    except Exception:
        pass

    # Last-safe fallback.
    return "أعتذر، حدث تشويش في توليد النص. أعد إرسال سؤالك وسأجيبك بصياغة عربية سليمة وواضحة."

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


def _do_ai_chat_completion(
    messages: list[dict[str, object]],
    timeout_seconds: int = 45,
    max_tokens: int = 1400,
    model: str | None = None,
) -> tuple[str, str]:
    headers = {'Content-Type': 'application/json'}
    api_key = (DO_AI_KEY or '').strip()
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    payload = {
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    model_name = (model or DO_AI_MODEL or '').strip()
    if model_name:
        payload["model"] = model_name
    res = requests.post(
        f"{DO_AI_ENDPOINT}/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=timeout_seconds,
    )
    res.raise_for_status()
    data = res.json()
    choice = (data.get('choices') or [{}])[0]
    msg = choice.get('message') or {}
    content = str(msg.get('content') or '').strip()
    finish_reason = str(choice.get('finish_reason') or '')
    return content, finish_reason

def _call_do_ai(message: str, system_prompt: str | None = None, model: str | None = None) -> str:
    """استدعاء TITAN AI عبر DigitalOcean Agent"""
    sys_prompt = (system_prompt or AI_SYSTEM_PROMPT).strip()
    messages: list[dict[str, object]] = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": message},
    ]

    chunks: list[str] = []
    for _ in range(3):
        chunk, finish_reason = _do_ai_chat_completion(messages, timeout_seconds=45, max_tokens=1400, model=model)
        if chunk:
            chunks.append(chunk)
            messages.append({"role": "assistant", "content": chunk})

        if finish_reason != 'length':
            break

        # Ask model to continue exactly from the interruption point when token limit cuts output.
        messages.append({
            "role": "user",
            "content": "Continue from the exact last sentence without repeating, and complete the answer to the end."
        })

    full_reply = "\n".join(chunks).strip()
    return _repair_garbled_ai_reply(full_reply, context_hint=message[:200])


def _call_do_ai_multimodal(
    message: str,
    image_data_urls: list[str],
    system_prompt: str | None = None,
    model: str | None = None,
) -> str:
    """Call DigitalOcean AI with text + inline image data URLs (OpenAI-compatible format)."""
    sys_prompt = (system_prompt or AI_SYSTEM_PROMPT).strip()

    user_content: list[dict[str, object]] = [{"type": "text", "text": (message or "حلّل الصور المرفقة.").strip()}]
    for url in (image_data_urls or [])[:3]:
        if not url:
            continue
        user_content.append({
            "type": "image_url",
            "image_url": {"url": url}
        })

    messages: list[dict[str, object]] = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_content},
    ]

    chunks: list[str] = []
    for _ in range(2):
        chunk, finish_reason = _do_ai_chat_completion(messages, timeout_seconds=60, max_tokens=1600, model=model)
        if chunk:
            chunks.append(chunk)
            messages.append({"role": "assistant", "content": chunk})
        if finish_reason != 'length':
            break
        messages.append({"role": "user", "content": "Continue without repeating."})

    return _repair_garbled_ai_reply("\n".join(chunks).strip(), context_hint=message[:200])


AI_CHAT_SESSIONS: dict[str, dict[str, object]] = {}


def _classify_ai_topic(text: str) -> str:
    t = (text or '').lower()
    rules = [
        ('incident_response', ['incident', 'ir', 'triage', 'contain', 'forensic', 'soc', 'alert', 'حادث', 'استجابة', 'احتواء', 'تحقيق']),
        ('malware_analysis', ['malware', 'ransomware', 'trojan', 'payload', 'yara', 'برمجية', 'خبيث', 'فيروس', 'تحليل عينة']),
        ('network_security', ['network', 'firewall', 'ids', 'ips', 'wireshark', 'port', 'شبكة', 'جدار', 'منفذ', 'حزم']),
        ('osint', ['osint', 'username', 'domain', 'ip', 'social', 'اوسنت', 'استخبارات', 'اسم مستخدم', 'دومين']),
        ('secure_coding', ['code', 'python', 'javascript', 'sql', 'xss', 'sqli', 'csrf', 'coding', 'برمجة', 'كود', 'ثغرة']),
        ('learning_path', ['learn', 'roadmap', 'course', 'certificate', 'ceh', 'cissp', 'security+', 'تعلم', 'مسار', 'شهادة', 'دورة']),
    ]
    for label, keywords in rules:
        if any(k in t for k in keywords):
            return label
    return 'general_support'


def _build_ai_system_prompt(topic: str, user_text: str = '') -> str:
    lang = _detect_user_lang(user_text)
    lang_rule = (
        "- Reply strictly in English for this request (no Arabic).\n"
        if lang == 'en' else
        "- أجب بالعربية الواضحة لهذا الطلب (بدون تحويل الرد للإنجليزية).\n"
    )
    kb_context = _build_titan_kb_context(user_text, topic)
    return (
        AI_SYSTEM_PROMPT
        + "\n\n"
        + "تنسيق الرد إلزامي:\n"
        + lang_rule
        + "- حافظ على أسلوب طبيعي وودّي، واستخدم إيموجي بشكل طبيعي في الرد.\n"
        + "- ابدأ بجواب مباشر، ثم رتب النقاط عندما يكون ذلك مفيداً.\n"
        + "- اجعل الخطاب واضحاً وقابلاً للتنفيذ دون تعقيد.\n"
        + f"- تصنيف الموضوع الحالي: {topic}. حافظ على الاستمرارية مع نفس سياق المحادثة.\n"
        + "- عند السؤال عن آلية عمل TITAN أو مكوناته أو أدواته، اشرحها كوحدات: المعمارية، المصادقة، الحماية، الأدوات، API، وتدفقات العمل.\n"
        + "- عند ذكر عمليات المنصة، اذكر مسارات API ذات الصلة عندما تكون مفيدة.\n\n"
        + (kb_context or "Knowledge context from TITAN KB is unavailable right now.")
    )


def _call_do_ai_with_history(
    history_messages: list[dict[str, object]],
    system_prompt: str | None = None,
    model: str | None = None,
) -> str:
    sys_prompt = (system_prompt or AI_SYSTEM_PROMPT).strip()
    messages: list[dict[str, object]] = [{"role": "system", "content": sys_prompt}]
    for m in (history_messages or []):
        role = str(m.get('role') or '').strip()
        content = str(m.get('content') or '')
        if role in ('user', 'assistant') and content:
            messages.append({"role": role, "content": content})

    chunks: list[str] = []
    for _ in range(3):
        chunk, finish_reason = _do_ai_chat_completion(messages, timeout_seconds=45, max_tokens=1600, model=model)
        if chunk:
            chunks.append(chunk)
            messages.append({"role": "assistant", "content": chunk})

        if finish_reason != 'length':
            break

        messages.append({
            "role": "user",
            "content": "Continue from the exact last sentence without repeating, and complete the answer to the end."
        })

    last_user = ''
    for m in reversed(history_messages or []):
        if str(m.get('role') or '') == 'user':
            last_user = str(m.get('content') or '')
            if last_user:
                break
    return _repair_garbled_ai_reply("\n".join(chunks).strip(), context_hint=last_user[:200])


def _ai_trim_title(text: str, max_len: int = 72) -> str:
    t = re.sub(r'\s+', ' ', (text or '').strip())
    if not t:
        return 'محادثة جديدة'
    return (t[:max_len] + '...') if len(t) > max_len else t


def _ai_load_history_db(c, user_id: int, conversation_id: str, limit: int = 14) -> list[dict[str, object]]:
    c.execute(
        """
        SELECT role, content
        FROM ai_chat_messages
        WHERE user_id=%s AND conversation_id=%s
        ORDER BY id DESC
        LIMIT %s
        """,
        (user_id, conversation_id, max(1, int(limit)))
    )
    rows = c.fetchall() or []
    rows = rows[::-1]
    out: list[dict[str, object]] = []
    for role, content in rows:
        r = str(role or '').strip()
        txt = str(content or '')
        if r in ('user', 'assistant') and txt:
            out.append({"role": r, "content": txt})
    return out


def _ai_load_cross_conversation_context_db(c, user_id: int, exclude_conversation_id: str = '', limit: int = 10) -> list[dict[str, object]]:
    """Load a compact memory bridge from user's recent messages across other conversations."""
    lim = max(1, min(int(limit), 20))
    if exclude_conversation_id:
        c.execute(
            """
            SELECT role, content
            FROM ai_chat_messages
            WHERE user_id=%s AND conversation_id<>%s
            ORDER BY id DESC
            LIMIT %s
            """,
            (user_id, exclude_conversation_id, lim)
        )
    else:
        c.execute(
            """
            SELECT role, content
            FROM ai_chat_messages
            WHERE user_id=%s
            ORDER BY id DESC
            LIMIT %s
            """,
            (user_id, lim)
        )

    rows = c.fetchall() or []
    rows = rows[::-1]
    out: list[dict[str, object]] = []
    for role, content in rows:
        r = str(role or '').strip()
        txt = str(content or '').strip()
        if r in ('user', 'assistant') and txt:
            out.append({"role": r, "content": txt})
    return out


def _json_no_cache(payload: dict, status: int = 200):
    resp = jsonify(payload)
    resp.status_code = status
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


def _ai_upsert_thread_db(c, user_id: int, conversation_id: str, title: str, classification: str, model: str, updated_at: str, preview: str) -> None:
    c.execute(
        """
        INSERT INTO ai_chat_threads (user_id, conversation_id, title, classification, model, created_at, updated_at, last_message_preview)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (user_id, conversation_id) DO UPDATE SET
            classification=EXCLUDED.classification,
            model=EXCLUDED.model,
            updated_at=EXCLUDED.updated_at,
            last_message_preview=EXCLUDED.last_message_preview
        """,
        (user_id, conversation_id, title, classification, model, updated_at, updated_at, preview)
    )


def _ai_append_message_db(c, user_id: int, conversation_id: str, role: str, content: str, created_at: str) -> None:
    c.execute(
        "INSERT INTO ai_chat_messages (user_id, conversation_id, role, content, created_at) VALUES (%s,%s,%s,%s,%s)",
        (user_id, conversation_id, role, content, created_at)
    )


def _ensure_ai_chat_tables(c) -> None:
    """Runtime-safe bootstrap for AI chat tables in case migration/init wasn't applied yet."""
    c.execute('''
        CREATE TABLE IF NOT EXISTS ai_chat_threads (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            conversation_id TEXT NOT NULL,
            title TEXT DEFAULT 'محادثة جديدة',
            classification TEXT DEFAULT 'general_support',
            model TEXT DEFAULT 'tor1',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_message_preview TEXT DEFAULT '',
            UNIQUE (user_id, conversation_id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS ai_chat_messages (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')


def _ensure_burn_notes_table(c) -> None:
    c.execute('''
        CREATE TABLE IF NOT EXISTS burn_notes_once (
            note_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            consumed BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TEXT NOT NULL,
            consumed_at TEXT
        )
    ''')


def _burn_note_store_db(note_id: str, payload: dict) -> None:
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        _ensure_burn_notes_table(c)
        c.execute(
            """
            INSERT INTO burn_notes_once (note_id, payload_json, consumed, created_at)
            VALUES (%s,%s,FALSE,%s)
            ON CONFLICT (note_id) DO UPDATE SET
                payload_json=EXCLUDED.payload_json,
                consumed=FALSE,
                created_at=EXCLUDED.created_at,
                consumed_at=NULL
            """,
            (note_id, json.dumps(payload, ensure_ascii=False), datetime.datetime.now().isoformat())
        )
        conn.commit()
    except Exception as e:
        print(f"[TITAN] Burn note DB store error: {e}")
    finally:
        if conn:
            conn.close()


def _burn_note_pop_db(note_id: str):
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        _ensure_burn_notes_table(c)
        c.execute(
            """
            UPDATE burn_notes_once
            SET consumed=TRUE, consumed_at=%s
            WHERE note_id=%s AND consumed=FALSE
            RETURNING payload_json
            """,
            (datetime.datetime.now().isoformat(), note_id)
        )
        row = c.fetchone()
        conn.commit()
        if not row:
            return None
        raw = row[0]
        if isinstance(raw, str):
            return json.loads(raw)
        return raw if isinstance(raw, dict) else None
    except Exception as e:
        print(f"[TITAN] Burn note DB consume error: {e}")
        return None
    finally:
        if conn:
            conn.close()


def _ctf_normalize_newlines(value):
    """Normalize escaped/newline-like tokens so challenge text renders correctly in UI."""
    if isinstance(value, str):
        return (
            value
            .replace('\\r\\n', '\n')
            .replace('\\n', '\n')
            .replace('/n', '\n')
        )
    if isinstance(value, list):
        return [_ctf_normalize_newlines(v) for v in value]
    if isinstance(value, dict):
        return {k: _ctf_normalize_newlines(v) for k, v in value.items()}
    return value


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
            priority TEXT DEFAULT 'p2',
            status TEXT DEFAULT 'open',
            category TEXT DEFAULT 'general',
            source TEXT DEFAULT 'manual',
            owner TEXT DEFAULT 'SOC',
            sla_minutes INTEGER DEFAULT 240,
            due_at TEXT DEFAULT NULL,
            closed_at TEXT DEFAULT NULL,
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
            file_size INTEGER DEFAULT 0,
            mime_type TEXT DEFAULT 'application/octet-stream',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS incident_case_notes (
            id SERIAL PRIMARY KEY,
            case_id INTEGER NOT NULL,
            note_type TEXT DEFAULT 'analysis',
            note TEXT NOT NULL,
            created_by TEXT DEFAULT '',
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

    c.execute('''
        CREATE TABLE IF NOT EXISTS ai_chat_threads (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            conversation_id TEXT NOT NULL,
            title TEXT DEFAULT 'محادثة جديدة',
            classification TEXT DEFAULT 'general_support',
            model TEXT DEFAULT 'tor1',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_message_preview TEXT DEFAULT '',
            UNIQUE (user_id, conversation_id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS ai_chat_messages (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')

    # --- Safe migrations for existing deployments (Incident Response expansion) ---
    for stmt in [
        "ALTER TABLE incident_cases ADD COLUMN priority TEXT DEFAULT 'p2'",
        "ALTER TABLE incident_cases ADD COLUMN category TEXT DEFAULT 'general'",
        "ALTER TABLE incident_cases ADD COLUMN source TEXT DEFAULT 'manual'",
        "ALTER TABLE incident_cases ADD COLUMN owner TEXT DEFAULT 'SOC'",
        "ALTER TABLE incident_cases ADD COLUMN sla_minutes INTEGER DEFAULT 240",
        "ALTER TABLE incident_cases ADD COLUMN due_at TEXT DEFAULT NULL",
        "ALTER TABLE incident_cases ADD COLUMN closed_at TEXT DEFAULT NULL",
        "ALTER TABLE incident_evidence ADD COLUMN file_size INTEGER DEFAULT 0",
        "ALTER TABLE incident_evidence ADD COLUMN mime_type TEXT DEFAULT 'application/octet-stream'",
    ]:
        try:
            c.execute(stmt)
            conn.commit()
        except Exception:
            conn.rollback()

    c.execute('''
        CREATE TABLE IF NOT EXISTS social_quiz_results (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            selected_option INTEGER NOT NULL,
            correct_option INTEGER NOT NULL,
            is_correct INTEGER DEFAULT 0,
            score_after INTEGER DEFAULT 0,
            answered_at TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS social_risk_snapshots (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            total_items INTEGER DEFAULT 0,
            high_count INTEGER DEFAULT 0,
            medium_count INTEGER DEFAULT 0,
            low_count INTEGER DEFAULT 0,
            avg_risk REAL DEFAULT 0,
            risk_index REAL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS forensics_sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            file_type TEXT DEFAULT 'unknown',
            mime_type TEXT DEFAULT 'application/octet-stream',
            md5 TEXT NOT NULL,
            sha1 TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            entropy REAL DEFAULT 0,
            risk_score INTEGER DEFAULT 0,
            summary_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS forensics_artifacts (
            id SERIAL PRIMARY KEY,
            session_id INTEGER NOT NULL,
            artifact_type TEXT NOT NULL,
            artifact_value TEXT NOT NULL,
            confidence TEXT DEFAULT 'medium',
            created_at TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS learning_reports (
            id SERIAL PRIMARY KEY,
            token TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at DOUBLE PRECISION NOT NULL
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
        raise ValueError("كلمة السر خاطئة")


def derive_raw_key_with_iterations(password: str, salt: bytes, iterations: int) -> bytes:
    safe_iterations = max(50000, min(int(iterations or 300000), 1000000))
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=safe_iterations,
    )
    return kdf.derive(password.encode())


def _pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len]) * pad_len


def _pkcs7_unpad(data: bytes, block_size: int = 16) -> bytes:
    if not data or len(data) % block_size != 0:
        raise ValueError("بيانات غير صالحة")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > block_size:
        raise ValueError("بيانات غير صالحة")
    if data[-pad_len:] != bytes([pad_len]) * pad_len:
        raise ValueError("بيانات غير صالحة")
    return data[:-pad_len]


def _xor_keystream(password: str, salt: bytes, length: int, rounds: int = 1) -> bytes:
    safe_rounds = max(1, min(int(rounds or 1), 8))
    stream = bytearray()
    counter = 0
    seed = password.encode('utf-8') + salt
    while len(stream) < length:
        block = seed + counter.to_bytes(8, 'big')
        digest = hashlib.sha256(block).digest()
        for _ in range(safe_rounds - 1):
            digest = hashlib.sha256(digest + seed).digest()
        stream.extend(digest)
        counter += 1
    return bytes(stream[:length])


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode('ascii')


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode('ascii'))


def _kdf_iterations_from_profile(profile: str) -> int:
    p = (profile or 'strong').lower()
    if p == 'balanced':
        return 120000
    if p == 'paranoid':
        return 600000
    return 300000


def encrypt_text_with_method(plain_text: str, password: str, method: str, options: dict) -> str:
    algo = (method or 'fernet').lower()
    opts = options or {}
    out_fmt = (opts.get('output_format') or 'b64').lower()
    if out_fmt not in ('b64', 'b64url'):
        out_fmt = 'b64'
    iterations = _kdf_iterations_from_profile(opts.get('kdf_profile') or 'strong')

    raw_plain = plain_text.encode('utf-8')
    payload_bytes: bytes

    if algo == 'fernet':
        payload_bytes = encrypt_data(raw_plain, password)
    elif algo == 'aes-cbc':
        salt = os.urandom(16)
        iv = os.urandom(16)
        key = derive_raw_key_with_iterations(password, salt, iterations)
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        enc = cipher.encryptor()
        ct = enc.update(_pkcs7_pad(raw_plain)) + enc.finalize()
        payload = {
            's': _b64e(salt),
            'i': _b64e(iv),
            't': iterations,
            'c': _b64e(ct),
        }
        payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    elif algo == 'chacha20':
        salt = os.urandom(16)
        nonce = os.urandom(16)
        key = derive_raw_key_with_iterations(password, salt, iterations)
        cipher = Cipher(algorithms.ChaCha20(key, nonce), mode=None)
        enc = cipher.encryptor()
        ct = enc.update(raw_plain) + enc.finalize()
        payload = {
            's': _b64e(salt),
            'n': _b64e(nonce),
            't': iterations,
            'c': _b64e(ct),
        }
        payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    elif algo == 'xor-stream':
        salt = os.urandom(16)
        rounds = 2
        ks = _xor_keystream(password, salt, len(raw_plain), rounds=rounds)
        ct = bytes(a ^ b for a, b in zip(raw_plain, ks))
        payload = {
            's': _b64e(salt),
            'r': rounds,
            'c': _b64e(ct),
        }
        payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    else:
        raise ValueError('خوارزمية غير مدعومة')

    if out_fmt == 'b64url':
        encoded = base64.urlsafe_b64encode(payload_bytes).decode('ascii')
    else:
        encoded = base64.b64encode(payload_bytes).decode('ascii')
    return f"TITANv2::{algo}::{out_fmt}::{encoded}"


def decrypt_text_with_method(cipher_text: str, password: str, method: str = 'auto') -> str:
    text = (cipher_text or '').strip()
    selected = (method or 'auto').lower()

    if text.startswith('TITANv2::'):
        parts = text.split('::', 3)
        if len(parts) != 4:
            raise ValueError('صيغة النص المشفر غير صحيحة')
        _, algo, fmt, encoded = parts
        raw_payload = base64.urlsafe_b64decode(encoded) if fmt == 'b64url' else base64.b64decode(encoded)

        if algo == 'fernet':
            return decrypt_data(raw_payload, password).decode('utf-8', errors='replace')

        payload = json.loads(raw_payload.decode('utf-8'))
        if algo == 'aes-cbc':
            salt = _b64d(payload['s'])
            iv = _b64d(payload['i'])
            iterations = int(payload.get('t') or 300000)
            ct = _b64d(payload['c'])
            key = derive_raw_key_with_iterations(password, salt, iterations)
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
            dec = cipher.decryptor()
            plain = _pkcs7_unpad(dec.update(ct) + dec.finalize())
            return plain.decode('utf-8', errors='replace')
        if algo == 'chacha20':
            salt = _b64d(payload['s'])
            nonce = _b64d(payload['n'])
            iterations = int(payload.get('t') or 300000)
            ct = _b64d(payload['c'])
            key = derive_raw_key_with_iterations(password, salt, iterations)
            cipher = Cipher(algorithms.ChaCha20(key, nonce), mode=None)
            dec = cipher.decryptor()
            plain = dec.update(ct) + dec.finalize()
            return plain.decode('utf-8', errors='replace')
        if algo == 'xor-stream':
            salt = _b64d(payload['s'])
            rounds = int(payload.get('r') or 1)
            ct = _b64d(payload['c'])
            ks = _xor_keystream(password, salt, len(ct), rounds=rounds)
            plain = bytes(a ^ b for a, b in zip(ct, ks))
            return plain.decode('utf-8', errors='replace')
        raise ValueError('خوارزمية غير مدعومة')

    if selected not in ('auto', 'fernet'):
        raise ValueError('النص الحالي غير متوافق مع الخوارزمية المختارة')
    try:
        encrypted_bytes = base64.b64decode(text)
        return decrypt_data(encrypted_bytes, password).decode('utf-8', errors='replace')
    except Exception:
        raise ValueError('فشل فك التشفير: المفتاح خاطئ أو الصيغة غير مدعومة')


_TXT_HIDE_PREFIX = '\u2063\u2062\u2061'
_TXT_HIDE_SUFFIX = '\u2061\u2062\u2063'
_TXT_HIDE_ZERO = '\u200b'
_TXT_HIDE_ONE = '\u200c'


def hide_secret_in_txt(container_text: str, secret_text: str) -> str:
    raw = (secret_text or '').encode('utf-8')
    bits = ''.join(format(b, '08b') for b in raw)
    payload = ''.join(_TXT_HIDE_ONE if bit == '1' else _TXT_HIDE_ZERO for bit in bits)
    return (container_text or '') + _TXT_HIDE_PREFIX + payload + _TXT_HIDE_SUFFIX


def extract_secret_from_txt(container_text: str) -> str:
    text = container_text or ''
    start = text.find(_TXT_HIDE_PREFIX)
    end = text.find(_TXT_HIDE_SUFFIX, start + len(_TXT_HIDE_PREFIX)) if start != -1 else -1
    if start == -1 or end == -1:
        return ''

    hidden = text[start + len(_TXT_HIDE_PREFIX):end]
    bits = ''.join('1' if ch == _TXT_HIDE_ONE else ('0' if ch == _TXT_HIDE_ZERO else '') for ch in hidden)
    if not bits:
        return ''
    usable = len(bits) - (len(bits) % 8)
    if usable <= 0:
        return ''
    raw = bytes(int(bits[i:i+8], 2) for i in range(0, usable, 8))
    try:
        return raw.decode('utf-8')
    except Exception:
        return raw.decode('latin-1', errors='ignore')

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

    # Access through getattr to avoid stub mismatch warnings in some cv2 typings.
    fourcc_fn = getattr(cv2, 'VideoWriter_fourcc', None)
    fourcc_raw = fourcc_fn(*'mp4v') if callable(fourcc_fn) else 0
    if isinstance(fourcc_raw, (int, np.integer)):
        fourcc = int(fourcc_raw)
    else:
        fourcc = 0
    writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

    bit_index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if bit_index < len(payload_bits):
            blue_flat = frame[:, :, 0].reshape(-1).astype(np.uint8, copy=False)
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
            current_byte = (current_byte << 1) | (int(val) & 1)
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

        # Windows fallback: use known install location if PATH is not refreshed yet.
        if os.name == 'nt':
            tesseract_exe = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.exists(tesseract_exe):
                pytesseract.pytesseract.tesseract_cmd = tesseract_exe
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

def check_username_presence(username: str, mode: str = 'social') -> dict:
    u = (username or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9._-]{3,30}', u):
        return {
            "success": False,
            "error": "اسم المستخدم غير صالح. المسموح: أحرف/أرقام/._- وبطول 3-30."
        }

    # Rebuilt from scratch: only most popular social-media platforms.
    social_platforms = [
        ("facebook", f"https://www.facebook.com/{u}"),
        ("instagram", f"https://www.instagram.com/{u}/"),
        ("x", f"https://x.com/{u}"),
        ("tiktok", f"https://www.tiktok.com/@{u}"),
        ("youtube", f"https://www.youtube.com/@{u}"),
        ("threads", f"https://www.threads.net/@{u}"),
        ("snapchat", f"https://www.snapchat.com/add/{u}"),
        ("telegram", f"https://t.me/{u}"),
        ("linkedin", f"https://www.linkedin.com/in/{u}"),
        ("pinterest", f"https://www.pinterest.com/{u}/"),
        ("reddit", f"https://www.reddit.com/user/{u}"),
        ("twitch", f"https://www.twitch.tv/{u}"),
    ]

    not_found_markers = [
        "page not found",
        "sorry, this page isn't available",
        "this account doesn't exist",
        "couldn't find that page",
        "user not found",
        "this profile is unavailable",
        "does not exist",
        "looks like this page doesn't exist",
        "profile couldn't be found",
    ]

    per_platform_markers = {
        "facebook": ["content isn't available right now"],
        "instagram": ["sorry, this page isn't available"],
        "x": ["this account doesn\u2019t exist", "this account doesn't exist"],
        "tiktok": ["couldn't find this account"],
        "youtube": ["this page isn't available"],
        "reddit": ["nobody on reddit goes by that name"],
        "telegram": ["if you have telegram"],
        "twitch": ["unless you've got a time machine"],
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }

    def _probe_instagram(platform: str, url: str):
        """Instagram needs extra handling because web pages may redirect to login or rate-limit bots."""
        def _ig_profile_lookup() -> dict:
            api_candidates = [
                f"https://www.instagram.com/api/v1/users/web_profile_info/?username={urllib.parse.quote(u)}",
                f"https://i.instagram.com/api/v1/users/web_profile_info/?username={urllib.parse.quote(u)}",
            ]
            api_headers = {
                **headers,
                "X-IG-App-ID": "936619743392459",
                "Referer": "https://www.instagram.com/",
            }

            last_status = 0
            last_error = "instagram_probe_rate_limited"
            for api_url in api_candidates:
                try:
                    rr = requests.get(api_url, headers=api_headers, timeout=7, allow_redirects=True)
                    rr_status = int(rr.status_code)
                    last_status = rr_status

                    if rr_status == 200:
                        try:
                            payload = rr.json() if rr.text else {}
                        except Exception:
                            payload = {}
                        user_obj = ((payload or {}).get('data') or {}).get('user')
                        return {"decided": True, "exists": bool(user_obj), "status_code": rr_status}

                    if rr_status in (404, 410):
                        return {"decided": True, "exists": False, "status_code": rr_status}

                    if rr_status in (401, 403, 429):
                        last_error = "instagram_probe_rate_limited"
                        continue

                    last_error = f"instagram_probe_status_{rr_status}"
                except Exception:
                    continue

            return {"decided": False, "exists": False, "status_code": last_status, "error": last_error}

        try:
            r = requests.get(url, headers=headers, timeout=7, allow_redirects=True)
            status = int(r.status_code)
            body = (r.text or '').lower()
            final_url = str(r.url or '')
            final_url_l = final_url.lower()

            if status in (404, 410):
                return {
                    "platform": platform,
                    "url": url,
                    "final_url": final_url,
                    "status_code": status,
                    "exists": False
                }

            # Strong positive signals from web profile response.
            if status == 200 and (
                f'"username":"{u.lower()}"' in body
                or f'https://www.instagram.com/{u.lower()}/' in body
            ):
                return {
                    "platform": platform,
                    "url": url,
                    "final_url": final_url,
                    "status_code": status,
                    "exists": True
                }

            # If IG redirects to login/challenge or returns anti-bot response,
            # use a dedicated profile endpoint before deciding it's not found.
            needs_fallback = (
                '/accounts/login' in final_url_l
                or '/challenge/' in final_url_l
                or status in (301, 302, 307, 308, 401, 403, 429)
            )

            if needs_fallback:
                lookup = _ig_profile_lookup()
                if lookup.get("decided"):
                    return {
                        "platform": platform,
                        "url": url,
                        "final_url": final_url,
                        "status_code": int(lookup.get("status_code") or 0),
                        "exists": bool(lookup.get("exists"))
                    }

                return {
                    "platform": platform,
                    "url": url,
                    "final_url": final_url,
                    "status_code": int(lookup.get("status_code") or 0),
                    "exists": False,
                    "error": str(lookup.get("error") or "instagram_probe_rate_limited")
                }

            markers = not_found_markers + per_platform_markers.get(platform, [])
            exists = not any(m in body for m in markers)
            return {
                "platform": platform,
                "url": url,
                "final_url": final_url,
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

    def _probe(item):
        platform, url = item
        if platform == 'instagram':
            return _probe_instagram(platform, url)
        try:
            r = requests.get(url, headers=headers, timeout=7, allow_redirects=True)
            status = r.status_code
            body = (r.text or '').lower()
            if status in (404, 410):
                exists = False
            elif status in (200, 301, 302, 307, 308):
                markers = not_found_markers + per_platform_markers.get(platform, [])
                exists = not any(m in body for m in markers)
            elif status in (401, 403, 429):
                return {
                    "platform": platform,
                    "url": url,
                    "final_url": str(r.url),
                    "status_code": status,
                    "exists": False,
                    "error": "probe_rate_limited"
                }
            else:
                exists = False
            return {
                "platform": platform,
                "url": url,
                "final_url": str(r.url),
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

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(social_platforms)) as ex:
        rows = list(ex.map(_probe, social_platforms))

    # Keep fixed social order in output.
    fixed_order = {name: i for i, (name, _) in enumerate(social_platforms)}
    rows.sort(key=lambda r: fixed_order.get(str(r.get('platform', '')).lower(), 999))

    found = [r for r in rows if r.get("exists")]
    missing = [r for r in rows if not r.get("exists") and not r.get("error")]
    unknown = [r for r in rows if r.get("error")]

    return {
        "success": True,
        "username": u,
        "mode": "social",
        "checked_count": len(rows),
        "found_count": len(found),
        "found": found,
        "not_found": missing,
        "unknown": unknown,
        "all_results": rows,
        "checked_at": datetime.datetime.utcnow().isoformat() + 'Z'
    }


def create_social_defense_scenario(scenario_type: str) -> dict:
    scenarios = {
        'phishing_email': {
            'title': 'Credential Reset Trap',
            'scenario': 'وصلك بريد بعنوان "Security Incident - Reset Required" يطلب تحديث كلمة السر خلال 60 دقيقة عبر رابط يشبه موقع الشركة.',
            'attacker_goal': 'سرقة بيانات الدخول وإعادة استخدام الحساب داخلياً.',
            'impact': 'اختراق الحساب ثم الحركة الجانبية داخل بيئة العمل.',
            'red_flags': [
                'لغة استعجال وتهديد بإيقاف الحساب',
                'نطاق مشابه لكنه ليس الرسمي',
                'تحية عامة بدون اسمك الحقيقي',
                'الرابط الحقيقي مخفي داخل زر مختصر'
            ],
            'defense_actions': [
                'لا تفتح الرابط مباشرة',
                'افحص النطاق حرفياً قبل أي إجراء',
                'افتح الخدمة يدوياً من المفضلة الرسمية',
                'بلّغ فريق الأمن مع نسخة من الرسالة'
            ],
            'control_points': ['Email Gateway', 'MFA Enforcement', 'User Awareness', 'SOC Escalation'],
            'safe_reply_template': 'مرحباً، لأسباب أمنية لا يمكنني معالجة هذا الطلب من هذا الرابط. سأتحقق عبر القنوات الرسمية الداخلية.',
            'difficulty': 'medium'
        },
        'vishing_call': {
            'title': 'OTP Phone Harvest',
            'scenario': 'مكالمة من شخص يدّعي أنه من IT ويطلب رمز OTP فوراً بحجة إيقاف هجوم جارٍ على حسابك.',
            'attacker_goal': 'تجاوز المصادقة الثنائية والسيطرة على الجلسة.',
            'impact': 'دخول غير مصرح وسحب بيانات حساسة.',
            'red_flags': [
                'طلب صريح لرمز OTP',
                'ضغط نفسي بوجود تهديد فوري',
                'رفض إعطاء رقم تذكرة أو مرجع رسمي'
            ],
            'defense_actions': [
                'لا تشارك OTP نهائياً',
                'أنه المكالمة بأدب واتصل بالرقم الرسمي',
                'وثّق رقم المتصل وتوقيت الاتصال',
                'ارفع بلاغاً فورياً لفريق الأمن'
            ],
            'control_points': ['Call-back Verification', 'MFA Hygiene', 'Helpdesk Policy'],
            'safe_reply_template': 'لا أشارك رموز المصادقة عبر الهاتف. سأغلق المكالمة وأتواصل مع الدعم عبر الرقم المعتمد.',
            'difficulty': 'high'
        },
        'pretexting': {
            'title': 'Executive Impersonation',
            'scenario': 'رسالة من حساب ينتحل هوية المدير التنفيذي تطلب إرسال ملف عملاء بشكل عاجل خارج ساعات الدوام.',
            'attacker_goal': 'استخراج بيانات أعمال حساسة بغطاء السلطة.',
            'impact': 'تسريب بيانات وضرر قانوني وسمعة المؤسسة.',
            'red_flags': [
                'انتحال صفة قيادية',
                'طلب تجاوز السياسة الداخلية',
                'توقيت غير اعتيادي',
                'رفض الانتظار حتى التحقق'
            ],
            'defense_actions': [
                'طبّق مسار الموافقات المعتاد',
                'تحقق عبر قناة ثانية موثوقة',
                'صعّد الحالة إلى المدير المباشر وSOC'
            ],
            'control_points': ['Dual Approval', 'Data Loss Prevention', 'Manager Escalation'],
            'safe_reply_template': 'بحسب سياسة الشركة، هذا الطلب يحتاج تحقق ثنائي وموافقة رسمية. سأتابع عبر القناة المعتمدة.',
            'difficulty': 'high'
        },
        'baiting_usb': {
            'title': 'Curiosity USB Bait',
            'scenario': 'تم العثور على USB قرب المصعد مكتوب عليه "Payroll_Q4_Final" مع شعار الشركة.',
            'attacker_goal': 'تنفيذ برمجية خبيثة بعد تشغيل الوسيط القابل للإزالة.',
            'impact': 'عدوى نقطة النهاية وانتقال داخلي في الشبكة.',
            'red_flags': [
                'وسيط تخزين مجهول المصدر',
                'تسمية تحفيزية لفتح الملف بسرعة',
                'غياب سجل تسليم واستلام'
            ],
            'defense_actions': [
                'لا تقم بتوصيل USB بالجهاز الإنتاجي',
                'سلّم الوسيط لفريق IT/SOC وفق الإجراء',
                'أي فحص يتم داخل بيئة معزولة فقط'
            ],
            'control_points': ['Device Control', 'Endpoint Hardening', 'Forensics Intake'],
            'safe_reply_template': 'تم العثور على وسيط غير معروف. لن يتم تشغيله، وتم تحويله مباشرةً لفريق الأمن للفحص المعزول.',
            'difficulty': 'medium'
        },
        'banking_ar': {
            'title': 'قطاع البنوك: رسالة تحويل عاجل',
            'scenario': 'موظف فرع يستلم رسالة تبدو من الإدارة المالية تطلب تحويل مبلغ كبير لحساب جديد "قبل إغلاق اليوم".',
            'attacker_goal': 'احتيال مالي مباشر عبر انتحال جهة داخلية موثوقة.',
            'impact': 'خسارة مالية فورية ومخاطر امتثال وتنظيم مصرفي.',
            'red_flags': [
                'طلب تحويل خارج النمط المعتاد',
                'استعجال شديد مع تهديد مهني',
                'تعديل مفاجئ في رقم الحساب المستفيد'
            ],
            'defense_actions': [
                'إيقاف التنفيذ حتى تحقق ثنائي مع مسؤول معتمد',
                'مراجعة سجل المستفيدين والحدود المعتمدة',
                'إبلاغ وحدة مكافحة الاحتيال فوراً'
            ],
            'control_points': ['Dual Authorization', 'Fraud Desk', 'Transaction Hold'],
            'safe_reply_template': 'سياسة التحويل البنكي تتطلب تحقق ثنائي وموافقة موثقة. لن يتم تنفيذ العملية قبل استكمال الإجراء الرسمي.',
            'difficulty': 'high'
        },
        'education_ar': {
            'title': 'قطاع التعليم: انتحال بوابة الطلاب',
            'scenario': 'طلاب يتلقون رابطاً بعنوان "تحديث حساب الجامعة" يطلب بيانات الدخول الجامعية مع كود تحقق.',
            'attacker_goal': 'الاستيلاء على حسابات الطلاب والوصول للأنظمة التعليمية.',
            'impact': 'تسريب بيانات أكاديمية وتعطيل الوصول للمنصات.',
            'red_flags': [
                'رابط خارجي ليس ضمن نطاق الجامعة',
                'صياغة عامة مليئة بالأخطاء',
                'طلب بيانات حساسة خارج البوابة الرسمية'
            ],
            'defense_actions': [
                'نشر تنبيه رسمي للطلاب عبر القنوات المعتمدة',
                'حجب الرابط على مستوى الشبكة',
                'فرض إعادة تعيين كلمات السر للحسابات المتأثرة'
            ],
            'control_points': ['Student Awareness', 'Domain Protection', 'SSO Monitoring'],
            'safe_reply_template': 'الجامعة لا تطلب بيانات الدخول عبر روابط خارجية. استخدم البوابة الرسمية فقط من الرابط المعتمد.',
            'difficulty': 'medium'
        },
        'healthcare_ar': {
            'title': 'قطاع الصحة: طلب سجلات مرضى مزيف',
            'scenario': 'موظف استقبال يتلقى اتصالاً يدّعي أنه من "جهة تنظيمية" ويطلب إرسال سجل مرضى فوراً للتحقيق.',
            'attacker_goal': 'سرقة بيانات صحية حساسة عبر ضغط السلطة.',
            'impact': 'اختراق خصوصية المرضى ومخالفة تشريعات حماية البيانات الصحية.',
            'red_flags': [
                'جهة اتصال غير موثقة',
                'طلب بيانات مرضى دون مسار قانوني',
                'ضغط زمني لمنع التحقق'
            ],
            'defense_actions': [
                'رفض مشاركة أي بيانات دون تفويض رسمي موثق',
                'تصعيد الحالة لمسؤول الامتثال وSOC',
                'توثيق كل تفاصيل الاتصال كحادث أمني'
            ],
            'control_points': ['PHI Protection', 'Compliance Gate', 'Incident Escalation'],
            'safe_reply_template': 'لا يمكن مشاركة أي بيانات مرضى دون تفويض قانوني موثق عبر القنوات المعتمدة للمؤسسة الصحية.',
            'difficulty': 'high'
        }
    }
    return scenarios.get(scenario_type, scenarios['phishing_email'])


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
    <link rel="stylesheet" href="/tailwind.css?v=__TAILWIND_V__">
    __TAILWIND_PLAY_CDN__
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Tajawal', sans-serif; background: #070b19; color: white; margin: 0; overflow-x: hidden; cursor: crosshair; }
        #matrix-bg, #intro-matrix { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; pointer-events: none; }
        #matrix-bg { z-index: -1; }
        #intro-matrix { z-index: 0; opacity: 0.6; }
        .glass { background: rgba(10, 15, 30, 0.85); backdrop-filter: blur(16px); border: 1px solid rgba(168, 85, 247, 0.2); box-shadow: 0 0 30px rgba(0,0,0,0.5); }
        button, a, input { cursor: pointer; }
        /* Force consistent dark controls across all app tabs (including AI section). */
        #main-app :where(input:not([type='checkbox']):not([type='radio']):not([type='range']), textarea, select),
        #ai-section :where(input:not([type='checkbox']):not([type='radio']):not([type='range']), textarea, select) {
            background-color: rgba(2, 6, 23, 0.88);
            color: #e2e8f0;
            border: 1px solid rgba(71, 85, 105, 0.75);
        }
        #main-app :where(input::placeholder, textarea::placeholder),
        #ai-section :where(input::placeholder, textarea::placeholder) {
            color: #64748b;
        }
        #main-app :where(input:not([type='checkbox']):not([type='radio']):not([type='range']):focus, textarea:focus, select:focus),
        #ai-section :where(input:not([type='checkbox']):not([type='radio']):not([type='range']):focus, textarea:focus, select:focus) {
            outline: none;
            border-color: rgba(168, 85, 247, 0.8);
            box-shadow: 0 0 0 2px rgba(168, 85, 247, 0.22);
        }
        .titan-gradient { background: linear-gradient(135deg, #a855f7 0%, #7c3aed 100%); }
        #global-file-dropzone {
            position: fixed;
            inset: 0;
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 100000;
            background: rgba(2, 6, 23, 0.76);
            backdrop-filter: blur(2px);
            border: 2px dashed rgba(56, 189, 248, 0.55);
        }
        #global-file-dropzone .dropzone-card {
            background: rgba(15, 23, 42, 0.92);
            border: 1px solid rgba(56, 189, 248, 0.45);
            border-radius: 16px;
            padding: 18px 22px;
            box-shadow: 0 0 32px rgba(56, 189, 248, 0.22);
            text-align: center;
            max-width: 420px;
        }
        #global-file-dropzone .dropzone-title {
            color: #67e8f9;
            font-weight: 800;
            font-size: 15px;
            margin-bottom: 6px;
        }
        #global-file-dropzone .dropzone-hint {
            color: #cbd5e1;
            font-size: 12px;
        }
        .drop-target-highlight {
            outline: 2px solid rgba(34, 211, 238, 0.9) !important;
            outline-offset: 2px;
            box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.22), 0 0 22px rgba(34, 211, 238, 0.28) !important;
            border-color: rgba(34, 211, 238, 0.85) !important;
            transition: box-shadow 0.12s ease, outline-color 0.12s ease;
        }
        
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

        /* Auth overlay must remain scrollable on short/mobile screens so register fields are reachable. */
        #auth-overlay {
            overflow: hidden !important;
        }
        #auth-card-wrapper {
            height: 100% !important;
            min-height: 100% !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
            -webkit-overflow-scrolling: touch;
            overscroll-behavior: contain;
            touch-action: pan-y;
            padding-top: 1.25rem !important;
            padding-bottom: 1.75rem !important;
        }
        @media (max-width: 768px), (max-height: 780px) {
            #auth-card-wrapper {
                align-items: flex-start !important;
                justify-content: center !important;
            }
        }

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
        <div style="position:relative;z-index:10;display:flex;align-items:center;justify-content:center;min-height:100%;height:100%;padding:1.5rem;overflow-y:auto;overflow-x:hidden;-webkit-overflow-scrolling:touch;touch-action:pan-y;" id="auth-card-wrapper">
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

            @keyframes tabIconPulse {
                0%, 100% { transform: scale(1); opacity: 0.95; }
                50% { transform: scale(1.14); opacity: 1; }
            }

            .tab-nav-modern .tab-grid button > span:first-child {
                display: inline-block;
                transform-origin: center;
                animation: tabIconPulse 1.35s ease-in-out infinite;
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

            .training-subtabs-shell {
                border: 1px solid rgba(147, 197, 253, 0.35);
                background: linear-gradient(135deg, rgba(15, 23, 42, 0.96), rgba(17, 24, 39, 0.94));
                box-shadow: inset 0 0 0 1px rgba(125, 211, 252, 0.08), 0 10px 26px rgba(2, 6, 23, 0.48);
            }

            .training-subtab-btn {
                width: 100%;
                border: 1px solid rgba(125, 211, 252, 0.32);
                background: linear-gradient(135deg, rgba(30, 41, 59, 0.95), rgba(15, 23, 42, 0.95));
                color: #e2e8f0;
                min-height: 2.3rem;
                box-shadow: inset 0 1px 0 rgba(148, 163, 184, 0.16), 0 1px 0 rgba(15, 23, 42, 0.9);
            }

            .training-subtab-btn:hover {
                transform: translateY(-1px);
                border-color: rgba(168, 85, 247, 0.45);
                box-shadow: 0 8px 18px rgba(88, 28, 135, 0.28);
            }

            .training-subtab-btn.training-subtab-active {
                background: linear-gradient(135deg, rgba(139, 92, 246, 0.95), rgba(109, 40, 217, 0.95));
                border-color: rgba(196, 181, 253, 0.7);
                color: #ffffff;
                box-shadow: 0 0 0 1px rgba(196, 181, 253, 0.25), 0 0 18px rgba(139, 92, 246, 0.45);
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

            .ctf-ui {
                font-family: "Cairo", "Tajawal", "Noto Sans Arabic", "Segoe UI", sans-serif;
            }

            .ctf-main-title {
                font-size: 1.45rem;
                letter-spacing: 0.02em;
            }

            .ctf-card {
                border-width: 1px;
                box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.12), 0 14px 30px rgba(2, 6, 23, 0.35);
            }

            .ctf-card-title {
                font-size: 1.05rem;
                font-weight: 800;
                line-height: 1.7;
                letter-spacing: 0.01em;
                unicode-bidi: plaintext;
            }

            .ctf-bidi {
                direction: rtl;
                text-align: right;
                unicode-bidi: plaintext;
                line-height: 1.95;
                font-size: 0.95rem;
                word-break: break-word;
            }

            .ctf-ltr {
                direction: ltr;
                text-align: left;
                unicode-bidi: plaintext;
            }

            .ctf-section-label {
                font-size: 0.87rem;
                font-weight: 800;
                letter-spacing: 0.01em;
            }

            .ctf-meta-text {
                font-size: 0.85rem;
                line-height: 1.75;
            }

            @media (max-width: 640px) {
                .ctf-main-title {
                    font-size: 1.2rem;
                }
                .ctf-card-title {
                    font-size: 1rem;
                }
                .ctf-bidi {
                    font-size: 0.91rem;
                }
            }
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

    <div id="global-file-dropzone" aria-hidden="true">
        <div class="dropzone-card">
            <div class="dropzone-title">📂 إفلات الملف هنا</div>
            <div class="dropzone-hint">سيتم إسناد الملف تلقائياً لحقل الرفع في التبويب الحالي.</div>
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
                    <div class="tab-group-title px-1"><span>🧱</span> الأدوات الأساسية</div>
                    <div class="tab-grid">
                    <button onclick="showTab('dash')" id="btn-dash" class="px-3 py-1.5 rounded-lg hover:bg-purple-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-purple-500/30"><span>📊</span> الإحصائيات</button>
                    <button onclick="showTab('pass')" id="btn-pass" class="px-3 py-1.5 rounded-lg hover:bg-purple-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-purple-500/30"><span>🔑</span> كلمات السر</button>
                    <button onclick="showTab('vault'); checkVaultPasswordSetup();" id="btn-vault" class="px-3 py-1.5 rounded-lg hover:bg-yellow-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-yellow-500/30"><span>🗄️</span> القبو</button>
                    <button onclick="showTab('fileprotect')" id="btn-fileprotect" class="px-3 py-1.5 rounded-lg hover:bg-emerald-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-emerald-500/30"><span>🛡️</span> حماية الملفات</button>
                    <button onclick="showTab('identity')" id="btn-identity" class="px-3 py-1.5 rounded-lg hover:bg-cyan-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-cyan-500/30"><span>🪪</span> هوية وهمية</button>
                </div>
                </div>

                <div class="tab-group">
                    <div class="tab-group-title px-1"><span>🧭</span> التحليل والاستقصاء</div>
                    <div class="tab-grid">
                    <button onclick="showTab('tools')" id="btn-tools" class="px-3 py-1.5 rounded-lg hover:bg-purple-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-purple-500/30"><span>🌐</span> تتبع IP</button>
                    <button onclick="showTab('ghost')" id="btn-ghost" class="px-3 py-1.5 rounded-lg hover:bg-pink-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-pink-500/30"><span>🔥</span> قنوات الدردشة والرسائل الأمنة</button>
                    <button onclick="showTab('osint')" id="btn-osint" class="px-3 py-1.5 rounded-lg hover:bg-indigo-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-indigo-500/30"><span>🕵️</span> OSINT</button>
                    <button onclick="showTab('ir')" id="btn-ir" class="px-3 py-1.5 rounded-lg hover:bg-red-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-red-500/30"><span>🚨</span> الحوادث</button>
                    <button onclick="showTab('forensics')" id="btn-forensics" class="px-3 py-1.5 rounded-lg hover:bg-teal-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-teal-500/30"><span>🧪</span> الجنائي الرقمي</button>
                    <button onclick="showTab('training')" id="btn-training" class="px-3 py-1.5 rounded-lg hover:bg-amber-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-amber-500/30"><span>🎯</span> قسم التدريب</button>
                </div>
                </div>

                <div class="tab-group">
                    <div class="tab-group-title px-1"><span>🧪</span> مختبر التشفير</div>
                    <div class="tab-grid">
                    <button onclick="showTab('crypt')" id="btn-crypt" class="px-3 py-1.5 rounded-lg hover:bg-blue-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-blue-500/30"><span>🔐</span> التشفير</button>
                    <button onclick="showTab('filelab')" id="btn-filelab" class="px-3 py-1.5 rounded-lg hover:bg-emerald-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-emerald-500/30"><span class="inline-block animate-pulse">📝</span> إخفاء نص TXT</button>
                    <button onclick="showTab('suite')" id="btn-suite" class="px-3 py-1.5 rounded-lg hover:bg-purple-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-purple-500/30"><span>🖼️</span> تشفير الصور</button>
                    <button onclick="showTab('audio')" id="btn-audio" class="px-3 py-1.5 rounded-lg hover:bg-orange-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-orange-500/30"><span>🎵</span> إخفاء صوتي</button>
                    <button onclick="showTab('video')" id="btn-video" class="px-3 py-1.5 rounded-lg hover:bg-rose-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-rose-500/30"><span>🎬</span> اخفاء نص داخل فيديو</button>
                    <button onclick="showTab('qr')" id="btn-qr" class="px-3 py-1.5 rounded-lg hover:bg-green-600/20 text-xs font-bold text-gray-400 transition-all flex items-center gap-1.5 border border-transparent hover:border-green-500/30"><span>🔳</span> QR آمن</button>
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
                        <span class="text-xs text-gray-300 font-bold">TITAN</span>
                    </div>
                    <div class="flex items-center justify-end gap-2 ml-auto">
                        <button id="ai-subtab-support" onclick="showAiSubTab('support')" class="px-3 py-1.5 rounded-lg text-xs font-bold transition-all border border-slate-700 text-gray-300 bg-slate-800/60 hover:bg-purple-600/20 hover:border-purple-500/40">Support</button>
                        <button id="ai-subtab-analysis" onclick="showAiSubTab('analysis')" class="px-3 py-1.5 rounded-lg text-xs font-bold transition-all border border-slate-700 text-gray-300 bg-slate-800/60 hover:bg-purple-600/20 hover:border-purple-500/40">Analysis</button>
                        <button id="ai-subtab-chat" onclick="showAiSubTab('chat')" class="px-3 py-1.5 rounded-lg text-xs font-bold transition-all border border-purple-700/50 bg-purple-900/40 text-purple-300">Chat</button>
                    </div>
                </div>

                <div id="ai-sub-content-chat" class="space-y-4">
                <div class="bg-slate-900/60 rounded-xl border border-purple-900/30 p-3">
                    <div class="flex items-center justify-between mb-2">
                        <div class="text-xs font-bold text-purple-300">المحادثات السابقة</div>
                        <button type="button" onclick="loadAiConversations()" class="text-[11px] px-2 py-1 rounded border border-slate-700 text-gray-300 hover:bg-slate-800">تحديث</button>
                    </div>
                    <div id="ai-conv-list" class="max-h-28 overflow-y-auto overflow-x-hidden space-y-1 text-xs text-gray-300"></div>
                </div>
                <div id="ai-chat-shell" class="bg-slate-900/70 rounded-2xl border border-purple-900/30 overflow-hidden h-[34rem] flex flex-col">
                    <div class="p-3 border-b border-slate-700 flex items-center justify-between gap-2">
                        <span class="text-purple-300 text-sm font-bold">&#128172; محادثة مع AI</span>
                        <button type="button" onclick="startNewAiConversation()" class="text-xs px-2.5 py-1 rounded-lg border border-purple-800/50 bg-purple-900/20 text-purple-300 hover:bg-purple-800/30">+ محادثة جديدة</button>
                    </div>
                    <div id="ai-chat-meta" class="px-3 py-2 text-[11px] text-purple-200/90 bg-slate-950/70 border-b border-slate-800">الموضوع: عام • الذاكرة: فعالة</div>
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
                        <div class="flex gap-2">
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

            <button id="ai-float-launcher" type="button" onclick="toggleAiBubble()" class="hidden fixed right-6 bottom-7 z-[9999] w-16 h-16 rounded-full bg-gradient-to-br from-purple-500 to-violet-600 text-white text-3xl font-black shadow-[0_0_30px_rgba(139,92,246,0.62)] border border-purple-300/50 hover:scale-105 transition-all" title="TITAN AI">🤖</button>

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
                <!-- Features Grid -->
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="md:col-span-2 bg-slate-900/50 p-5 rounded-xl border border-slate-700 hover:border-purple-500/50 transition-all group text-right">
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

            </div>

                </div>

                <!-- ===== CRYPTOGRAPHY SECTION ===== -->
                <div id="crypt-section" class="hidden">
                    <div class="space-y-4">
                        <div class="rounded-2xl border border-cyan-900/40 bg-gradient-to-r from-cyan-950/25 via-slate-900/80 to-fuchsia-950/20 p-4">
                            <div class="flex items-center justify-between gap-3 flex-wrap">
                                <div>
                                    <h3 class="text-sm font-black text-cyan-300 tracking-wide">TITAN Crypto Studio</h3>
                                    <p class="text-xs text-gray-400 mt-1">تشفير نصي متقدم + توصية فورية من TITAN AI مبنية على سياقك الفعلي.</p>
                                </div>
                                <div id="cryptAiSourceBadge" class="text-[10px] px-2 py-1 rounded border border-cyan-800/50 bg-cyan-900/20 text-cyan-300 font-bold">AI: TITAN</div>
                            </div>
                        </div>

                        <div class="grid grid-cols-1 xl:grid-cols-3 gap-4">
                            <div class="xl:col-span-2 space-y-4">
                                <div class="rounded-2xl border border-fuchsia-800/40 bg-gradient-to-br from-slate-900/90 via-slate-900/70 to-fuchsia-950/20 p-4">
                                    <h3 class="text-sm font-black text-fuchsia-300 mb-3">إعدادات التشفير الأساسية</h3>
                                    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                                        <div>
                                            <label class="block text-xs text-gray-400 mb-1">1. مفتاح التشفير (كلمة السر)</label>
                                            <input type="password" id="cryptKey" class="w-full p-3 rounded-xl bg-slate-950/70 border border-slate-700 focus:ring-2 focus:ring-fuchsia-500/60 outline-none" placeholder="أدخل المفتاح هنا...">
                                        </div>
                                        <div>
                                            <label class="block text-xs text-gray-400 mb-1">2. الخوارزمية</label>
                                            <select id="cryptMethod" class="w-full p-3 rounded-xl bg-slate-950/70 border border-slate-700 focus:ring-2 focus:ring-fuchsia-500/60 outline-none text-sm">
                                                <option value="fernet">Fernet + PBKDF2 (قوي جدًا - موصى به)</option>
                                                <option value="aes-cbc">AES-256-CBC + PBKDF2 (قوي)</option>
                                                <option value="chacha20">ChaCha20 + PBKDF2 (متوازن)</option>
                                                <option value="xor-stream">XOR Stream (تعليمي - ضعيف)</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label class="block text-xs text-gray-400 mb-1">3. KDF Profile</label>
                                            <select id="cryptKdfProfile" class="w-full p-3 rounded-xl bg-slate-950/70 border border-slate-700 focus:ring-2 focus:ring-fuchsia-500/60 outline-none text-sm">
                                                <option value="balanced">Balanced - 120k</option>
                                                <option value="strong" selected>Strong - 300k</option>
                                                <option value="paranoid">Paranoid - 600k</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label class="block text-xs text-gray-400 mb-1">4. تنسيق الخرج</label>
                                            <select id="cryptOutputFormat" class="w-full p-3 rounded-xl bg-slate-950/70 border border-slate-700 focus:ring-2 focus:ring-fuchsia-500/60 outline-none text-sm">
                                                <option value="b64" selected>Base64</option>
                                                <option value="b64url">Base64 URL-safe</option>
                                            </select>
                                        </div>
                                    </div>
                                    <div id="cryptAdvisorLastConfig" class="mt-3 text-[11px] text-cyan-300 bg-cyan-950/15 border border-cyan-900/35 rounded-lg px-3 py-2">لا توجد توصية مطبقة بعد.</div>
                                </div>

                                <div class="rounded-2xl border border-violet-900/40 bg-gradient-to-br from-slate-900/90 via-slate-900/70 to-violet-950/20 p-4">
                                    <h3 class="text-sm font-black text-violet-300 mb-3">لوحة النص والنتيجة</h3>
                                    <textarea id="cryptText" rows="6" class="w-full p-3 rounded-xl bg-slate-950/80 border border-violet-900/40 mb-3 text-sm outline-none focus:ring-2 focus:ring-violet-600/50" placeholder="اكتب النص هنا (تشفير/فك/نسخ)..."></textarea>
                                    <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                                        <button onclick="processText('encrypt')" class="titan-gradient p-2 rounded-lg font-bold">تشفير النص</button>
                                        <button onclick="processText('decrypt')" class="bg-slate-700 hover:bg-slate-600 p-2 rounded-lg font-bold border border-slate-600">فك التشفير</button>
                                        <button onclick="copyCryptText()" class="titan-gradient p-2 rounded-lg font-bold">نسخ النتائج</button>
                                        <button onclick="clearCryptText()" class="bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded-lg p-2 text-sm font-bold">مسح سريع</button>
                                    </div>
                                </div>
                            </div>

                            <div class="space-y-4">
                                <div class="rounded-2xl border border-cyan-900/40 bg-gradient-to-br from-slate-900/85 via-slate-900/70 to-cyan-950/25 p-4 space-y-3">
                                    <h3 class="text-sm font-black text-cyan-300">توصية TITAN AI للتشفير</h3>
                                    <div class="grid grid-cols-1 gap-2">
                                        <select id="cryptSensitivity" class="p-2 rounded-lg bg-slate-950/70 border border-slate-700 text-xs outline-none">
                                            <option value="normal">حساسية عادية</option>
                                            <option value="high" selected>حساسية عالية</option>
                                            <option value="critical">حساسية حرجة</option>
                                        </select>
                                        <input id="cryptPurpose" type="text" class="p-2 rounded-lg bg-slate-950/70 border border-slate-700 text-xs outline-none" placeholder="الغرض: قانوني / مالي / شخصي...">
                                        <textarea id="cryptAudience" rows="2" class="w-full p-3 rounded-xl bg-slate-950/70 border border-slate-700 text-sm outline-none focus:ring-2 focus:ring-cyan-600/50" placeholder="اكتب لمن سترسل النص ولماذا (كل التفاصيل)..."></textarea>
                                    </div>

                                    <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                                        <button onclick="startCryptAdvisorChat(true)" class="px-3 py-2 rounded-lg bg-cyan-700 hover:bg-cyan-600 text-xs font-bold border border-cyan-600/50">تهيئة سياق AI</button>
                                        <button onclick="applyCryptRecommendation()" class="px-3 py-2 rounded-lg bg-fuchsia-800/40 hover:bg-fuchsia-700/50 text-xs font-bold border border-fuchsia-700/50 text-fuchsia-200">تطبيق التوصية</button>
                                    </div>

                                    <div id="cryptAiChatFlow" class="h-64 overflow-y-auto rounded-xl border border-cyan-900/40 bg-black/35 p-3 space-y-2 text-sm"></div>

                                    <div class="flex gap-2">
                                        <input id="cryptAiChatInput" type="text" class="flex-1 p-2 rounded-lg bg-slate-950/70 border border-slate-700 text-sm outline-none" placeholder="اسأل TITAN AI عن أفضل إعداد تشفير لهذه الحالة...">
                                        <button id="cryptAiSendBtn" onclick="sendCryptAdvisorMessage()" class="px-4 py-2 rounded-lg bg-cyan-700 hover:bg-cyan-600 text-xs font-bold border border-cyan-600/50">إرسال</button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- ===== TXT HIDDEN TEXT LAB ===== -->
                <div id="filelab-section" class="hidden space-y-6">
                    <div class="bg-slate-900/60 p-5 rounded-2xl border border-emerald-900/40">
                        <h2 class="text-xl font-bold text-emerald-400 border-b border-slate-700 pb-2 flex items-center gap-2">
                            <span class="inline-block animate-bounce">📝</span>
                            إخفاء نص داخل ملفات TXT فقط
                        </h2>
                        <p class="text-xs text-gray-400 mt-3 mb-4">
                            هذا التبويب مخصص فقط لملفات النص `.txt`.
                            يمكنك إدخال نص سري وإخفاؤه داخل الملف النصي، ثم استخراج النص لاحقاً من نفس الملف.
                        </p>

                        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                            <div class="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900/50 p-2">
                                <input type="file" id="fileLabInput" accept=".txt,text/plain" class="hidden" onchange="updateFileLabName(this)">
                                <label for="fileLabInput" class="px-4 py-2 rounded-lg bg-emerald-900/40 hover:bg-emerald-800 text-emerald-300 border border-emerald-800/40 text-sm font-bold cursor-pointer transition-all">اختيار ملف TXT</label>
                                <span id="fileLabName" class="text-xs text-gray-400 truncate">لم يتم اختيار ملف</span>
                            </div>
                            <textarea id="fileLabSecret" rows="3" placeholder="اكتب النص السري الذي تريد إخفاءه داخل ملف TXT..." class="w-full p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-emerald-500 outline-none text-sm"></textarea>
                        </div>

                        <div class="flex flex-col md:flex-row gap-2">
                            <button onclick="processFileLab('encode')" class="flex-1 bg-emerald-700/60 hover:bg-emerald-600 rounded-xl font-bold p-3 border border-emerald-700/40">إخفاء النص داخل الملف 🔒</button>
                            <button onclick="processFileLab('decode')" class="flex-1 bg-emerald-900/40 hover:bg-emerald-800 rounded-xl font-bold p-3 border border-emerald-800/40 text-emerald-300">استخراج النص من الملف 🔍</button>
                        </div>

                        <div id="fileLabDecoded" class="hidden mt-4 p-3 rounded-xl border border-slate-700 bg-black/40 text-xs font-mono whitespace-pre-wrap" dir="ltr"></div>
                    </div>
                </div>

                <!-- ===== FILE PROTECTION SECTION ===== -->
                <div id="fileprotect-section" class="hidden space-y-6">
                    <h2 class="text-xl font-bold text-emerald-400 border-b border-slate-700 pb-2">🛡️ حماية الملفات</h2>

                    <div class="bg-slate-900/60 p-5 rounded-2xl border border-emerald-900/40 space-y-3">
                        <label class="block text-sm text-gray-300 font-bold">حماية كل أنواع الملفات بكلمة سر</label>
                        <p class="text-xs text-gray-500">يشمل الصور، الفيديو، الصوت، المستندات، والأرشيفات. اختر أي ملف ثم قفله أو فكّه بنفس كلمة السر.</p>
                        <input type="password" id="fileProtectKey" placeholder="كلمة سر حماية الملف..." class="w-full p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-emerald-500 outline-none mb-1 text-center tracking-widest">
                        <input type="file" id="fileInput" class="hidden" onchange="updateFileProtectName(this)">
                        <div class="flex items-center gap-3 border border-slate-700 p-2 rounded-xl bg-slate-900/50">
                            <label for="fileInput" class="px-4 py-2 rounded-lg bg-red-900/50 hover:bg-red-800 text-red-300 border border-red-800/40 text-sm font-bold cursor-pointer transition-all">اختيار ملف</label>
                            <span id="fileProtectName" class="text-xs text-gray-400 truncate">لم يتم اختيار ملف</span>
                        </div>
                        <div class="flex gap-2 mt-2">
                            <button onclick="processFile('encrypt')" class="flex-1 bg-emerald-700/60 hover:bg-emerald-600 rounded-xl font-bold p-3 border border-emerald-700/40">قفل/تشفير الملف 🔒</button>
                            <button onclick="processFile('decrypt')" class="flex-1 bg-emerald-900/40 hover:bg-emerald-800 rounded-xl font-bold p-3 border border-emerald-800/40 text-emerald-300">فك/استرجاع الملف 🔓</button>
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
                    <h2 class="text-xl font-bold text-rose-400 border-b border-slate-700 pb-2">🎬 اخفاء نص داخل فيديو</h2>

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
                                <input type="file" class="hidden" id="vaultRestoreFile" accept=".bak,.titan.bak" onchange="restoreVault(this)">
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

            </div>

            <div id="ghost-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-pink-400 border-b border-slate-700 pb-2 flex items-center gap-2">
                    <span>🔥</span> قنوات الدردشة والرسائل الأمنة
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
                    <input id="burnNoteMedia" type="file" accept="image/*" class="hidden">
                    <div class="bg-slate-900/40 border border-slate-700/60 rounded-xl p-3 mb-2 relative z-10">
                        <div class="space-y-2 mb-2">
                            <button type="button" onclick="triggerBurnNoteImagePicker()" class="w-full py-2 rounded-lg border border-orange-700/50 bg-orange-900/20 hover:bg-orange-800/30 text-orange-300 text-xs font-bold">🖼️ اختيار صورة</button>
                            <div class="flex gap-2">
                                <button type="button" id="burnNoteRecStartBtn" onclick="startBurnNoteAudioRecording()" class="flex-1 py-2 rounded-lg border border-emerald-700/50 bg-emerald-900/20 hover:bg-emerald-800/30 text-emerald-300 text-xs font-bold">🎙️ بدء التسجيل الصوتي</button>
                                <button type="button" id="burnNoteRecStopBtn" onclick="stopBurnNoteAudioRecording()" class="flex-1 py-2 rounded-lg border border-amber-700/50 bg-amber-900/20 hover:bg-amber-800/30 text-amber-300 text-xs font-bold" disabled>⏹️ إيقاف التسجيل</button>
                            </div>
                        </div>
                        <div class="flex items-center justify-between gap-2">
                            <div id="burnNoteMediaState" class="text-[11px] text-gray-400 truncate">لم يتم اختيار صورة أو تسجيل صوت بعد.</div>
                            <button type="button" onclick="clearBurnNoteSelectedMedia()" class="text-[11px] px-2 py-1 rounded border border-slate-700 text-gray-300 hover:bg-slate-800">مسح</button>
                        </div>
                    </div>
                    <p class="text-[11px] text-gray-500 mb-3 relative z-10">اختياري: أرسل نص فقط، أو صورة، أو سجّل صوتك مباشرة من الميكروفون.</p>
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
                            <button id="burnChatDestroyBtn" onclick="destroyBurnChatRoom()" class="bg-rose-900/30 hover:bg-rose-800/40 text-rose-300 px-5 py-2 rounded border border-rose-800/50 transition-all font-bold" disabled>تدمير الغرفة</button>
                        </div>

                        <div id="burnChatDisplay" class="h-64 bg-black rounded-lg border border-pink-900/30 mb-4 p-4 overflow-y-auto flex flex-col gap-2 shadow-inner">
                            <div class="text-center text-gray-600 text-[10px] tracking-widest uppercase mt-auto">-- Secure RAM Storage Only --</div>
                        </div>

                        <div class="flex gap-2 items-center flex-wrap">
                            <input type="text" id="burnChatInput" placeholder="اكتب رسالتك السرية هنا..." class="flex-1 p-3 rounded-lg bg-slate-900 border border-slate-700 focus:border-pink-500 outline-none" disabled>
                            <button id="burnChatSendBtn" onclick="sendBurnChat()" class="bg-slate-800 text-gray-500 px-8 rounded-lg font-bold transition-all border border-slate-700" disabled>إرسال</button>
                            <input id="burnChatMediaInput" type="file" accept="image/*,audio/*,video/*" class="hidden" disabled>
                            <button id="burnChatMediaBtn" onclick="document.getElementById('burnChatMediaInput').click()" class="bg-slate-800 text-gray-500 px-4 py-2 rounded-lg font-bold transition-all border border-slate-700" disabled>📎 صورة/صوت/فيديو</button>
                            <button id="burnChatRecStartBtn" onclick="startBurnChatRecording()" class="bg-slate-800 text-gray-500 px-4 py-2 rounded-lg font-bold transition-all border border-slate-700" disabled>🎙️ بدء تسجيل</button>
                            <button id="burnChatRecStopBtn" onclick="stopBurnChatRecording()" class="bg-slate-800 text-gray-500 px-4 py-2 rounded-lg font-bold transition-all border border-slate-700" disabled>⏹️ إيقاف</button>
                            <span id="burnChatRecState" class="text-[10px] text-gray-500">تسجيل مباشر غير مفعل</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- ===== OSINT SECTION ===== -->
            <div id="osint-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-indigo-400 border-b border-slate-700 pb-2">🕵️ OSINT Mission Center</h2>

                <div class="relative overflow-hidden rounded-2xl border border-indigo-900/50 bg-gradient-to-r from-indigo-950/35 via-slate-950/60 to-cyan-950/30 p-4">
                    <div class="absolute -top-10 -right-6 w-44 h-44 rounded-full bg-indigo-600/10 blur-3xl"></div>
                    <div class="absolute -bottom-10 -left-6 w-44 h-44 rounded-full bg-cyan-600/10 blur-3xl"></div>
                    <div class="relative z-10 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                        <div>
                            <div class="text-[10px] uppercase tracking-[0.35em] text-indigo-300 font-mono">Threat Mapping Grid</div>
                            <div class="text-sm text-gray-300 mt-1">تحليل موحد + مقارنة هدفين + تحليل دفعي + سجل نشاط حي في لوحة واحدة.</div>
                        </div>
                        <div class="grid grid-cols-2 md:grid-cols-4 gap-2 min-w-0">
                            <div class="rounded-lg border border-slate-700 bg-black/30 px-3 py-2">
                                <div class="text-[10px] text-gray-500">Total Runs</div>
                                <div id="osintMissionTotal" class="text-base font-black text-indigo-300">0</div>
                            </div>
                            <div class="rounded-lg border border-slate-700 bg-black/30 px-3 py-2">
                                <div class="text-[10px] text-gray-500">High Risk</div>
                                <div id="osintMissionHigh" class="text-base font-black text-rose-300">0</div>
                            </div>
                            <div class="rounded-lg border border-slate-700 bg-black/30 px-3 py-2">
                                <div class="text-[10px] text-gray-500">Avg Risk</div>
                                <div id="osintMissionAvg" class="text-base font-black text-amber-300">0</div>
                            </div>
                            <div class="rounded-lg border border-slate-700 bg-black/30 px-3 py-2">
                                <div class="text-[10px] text-gray-500">Last Type</div>
                                <div id="osintMissionLast" class="text-sm font-black text-cyan-300">--</div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="grid grid-cols-1 xl:grid-cols-3 gap-4">
                    <div class="xl:col-span-2 bg-slate-900/60 p-4 rounded-xl border border-indigo-900/40">
                        <div class="flex items-center justify-between gap-2 flex-wrap mb-2">
                            <h3 class="text-sm font-bold text-indigo-300">البحث الموحد (IP / Domain / URL / Email / Phone)</h3>
                            <div class="text-[10px] text-gray-500">Enter = تحليل مباشر</div>
                        </div>
                        <p class="text-[11px] text-gray-500 mb-3">اكتب أي هدف وسيتم تحليله تلقائياً حسب النوع مع درجة خطورة سريعة وذكر المسار المقترح.</p>
                        <div class="flex flex-wrap gap-2 mb-3">
                            <button onclick="osintApplyPreset('ip')" class="px-2.5 py-1 text-[11px] rounded-lg border border-indigo-800/40 bg-indigo-900/20 text-indigo-300 hover:bg-indigo-800/30">IP Demo</button>
                            <button onclick="osintApplyPreset('domain')" class="px-2.5 py-1 text-[11px] rounded-lg border border-indigo-800/40 bg-indigo-900/20 text-indigo-300 hover:bg-indigo-800/30">Domain Demo</button>
                            <button onclick="osintApplyPreset('url')" class="px-2.5 py-1 text-[11px] rounded-lg border border-indigo-800/40 bg-indigo-900/20 text-indigo-300 hover:bg-indigo-800/30">URL Demo</button>
                            <button onclick="osintApplyPreset('email')" class="px-2.5 py-1 text-[11px] rounded-lg border border-indigo-800/40 bg-indigo-900/20 text-indigo-300 hover:bg-indigo-800/30">Email Demo</button>
                            <button onclick="osintApplyPreset('phone')" class="px-2.5 py-1 text-[11px] rounded-lg border border-indigo-800/40 bg-indigo-900/20 text-indigo-300 hover:bg-indigo-800/30">Phone Demo</button>
                        </div>
                        <div class="flex flex-col md:flex-row gap-2">
                            <input id="osintTargetInput" type="text" placeholder="8.8.8.8 أو example.com أو user@mail.com أو +962..." class="flex-1 p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-indigo-500 outline-none font-mono text-left" dir="ltr">
                            <button onclick="runUnifiedOsint()" class="bg-indigo-900/50 hover:bg-indigo-800 px-5 py-3 rounded-xl font-bold border border-indigo-800/50 transition-all text-indigo-300">تحليل الهدف</button>
                        </div>
                        <div id="osintRiskScore" class="hidden mt-3 p-3 rounded-xl border text-sm font-bold"></div>
                        <div id="osintUnifiedResult" class="hidden mt-3 p-3 bg-black/40 border border-slate-700 rounded-xl text-xs font-mono whitespace-pre-wrap max-h-80 overflow-y-auto" dir="ltr"></div>
                    </div>

                    <div class="bg-slate-900/60 p-4 rounded-xl border border-indigo-900/40 space-y-2">
                        <h3 class="text-sm font-bold text-indigo-300">Watchlist</h3>
                        <p class="text-[11px] text-gray-500">احفظ الأهداف، شغّلها بنقرة، وصدّر تقريرًا شاملًا.</p>
                        <div class="grid grid-cols-2 gap-2">
                            <button onclick="saveCurrentOsintTarget()" class="py-2 bg-indigo-900/40 hover:bg-indigo-800 rounded-lg text-xs font-bold text-indigo-300 border border-indigo-800/40">إضافة الهدف الحالي</button>
                            <button onclick="runWatchlistBatch()" class="py-2 bg-cyan-900/40 hover:bg-cyan-800 rounded-lg text-xs font-bold text-cyan-300 border border-cyan-800/40">تحليل الكل</button>
                            <button onclick="clearOsintWatchlist()" class="py-2 bg-rose-900/30 hover:bg-rose-800 rounded-lg text-xs font-bold text-rose-300 border border-rose-800/40">تفريغ</button>
                            <button onclick="exportOsintReport()" class="py-2 bg-emerald-900/40 hover:bg-emerald-800 rounded-lg text-xs font-bold text-emerald-300 border border-emerald-800/40">تصدير JSON</button>
                        </div>
                        <div id="osintWatchlist" class="bg-black/40 border border-slate-700 rounded-lg p-2 max-h-64 overflow-y-auto text-xs text-gray-300"></div>
                    </div>
                </div>

                <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-violet-900/40">
                        <div class="flex items-center justify-between mb-2">
                            <h3 class="text-sm font-bold text-violet-300">Batch Analyzer</h3>
                            <button onclick="runBatchOsint()" class="px-3 py-1.5 rounded-lg bg-violet-900/40 hover:bg-violet-800 border border-violet-800/50 text-violet-300 text-xs font-bold">تشغيل دفعة</button>
                        </div>
                        <p class="text-[11px] text-gray-500 mb-2">ألصق أهداف متعددة (سطر لكل هدف) لتحليلها مرة واحدة.</p>
                        <textarea id="osintBatchInput" rows="6" placeholder="8.8.8.8&#10;example.com&#10;support@example.com&#10;https://example.com/login" class="w-full p-3 rounded-xl bg-slate-900 border border-slate-700 outline-none text-xs font-mono" dir="ltr"></textarea>
                        <div id="osintBatchResult" class="hidden mt-3 p-3 bg-black/40 border border-slate-700 rounded-xl text-xs max-h-80 overflow-y-auto"></div>
                    </div>

                    <div class="bg-slate-900/60 p-4 rounded-xl border border-fuchsia-900/40">
                        <div class="flex items-center justify-between mb-2">
                            <h3 class="text-sm font-bold text-fuchsia-300">Target Comparison</h3>
                            <button onclick="compareOsintTargets()" class="px-3 py-1.5 rounded-lg bg-fuchsia-900/40 hover:bg-fuchsia-800 border border-fuchsia-800/50 text-fuchsia-300 text-xs font-bold">مقارنة</button>
                        </div>
                        <p class="text-[11px] text-gray-500 mb-2">قارن هدفين لاكتشاف أيهما أعلى مخاطرة وأقرب للتهديد.</p>
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                            <input id="osintCompareA" type="text" placeholder="Target A" class="p-3 rounded-xl bg-slate-900 border border-slate-700 outline-none text-xs font-mono" dir="ltr">
                            <input id="osintCompareB" type="text" placeholder="Target B" class="p-3 rounded-xl bg-slate-900 border border-slate-700 outline-none text-xs font-mono" dir="ltr">
                        </div>
                        <div id="osintCompareResult" class="hidden mt-3 p-3 bg-black/40 border border-slate-700 rounded-xl text-xs max-h-80 overflow-y-auto"></div>
                    </div>
                </div>

                <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-cyan-900/40">
                        <h3 class="text-sm font-bold text-cyan-300 mb-2">Username Hunter</h3>
                        <p class="text-[11px] text-gray-500 mb-3">فحص اليوزرنيم على المنصات الأشهر مع وضع سريع أو عميق.</p>
                        <div class="flex flex-col md:flex-row gap-2">
                            <input id="osintUsernameInput" type="text" placeholder="username" class="flex-1 p-3 rounded-xl bg-slate-900 border border-slate-700 focus:ring-2 focus:ring-cyan-500 outline-none font-mono text-left" dir="ltr">
                            <select id="osintUsernameMode" class="p-3 rounded-xl bg-slate-900 border border-slate-700 outline-none text-xs">
                                <option value="quick">Quick</option>
                                <option value="deep" selected>Deep</option>
                            </select>
                            <button onclick="huntUsername()" class="bg-cyan-900/50 hover:bg-cyan-800 px-5 py-3 rounded-xl font-bold border border-cyan-800/50 transition-all text-cyan-300">ابحث</button>
                        </div>
                        <div class="mt-2 text-[11px] text-cyan-100/90 bg-slate-900/60 border border-cyan-900/30 rounded-lg px-3 py-2">
                            المنصات المفحوصة: Facebook, Instagram, X, TikTok, YouTube, Threads, Snapchat, Telegram, LinkedIn, Pinterest, Reddit, Twitch.
                        </div>
                        <div id="osintUsernameResult" class="hidden mt-3 p-3 bg-black/40 border border-slate-700 rounded-xl text-xs font-mono whitespace-pre-wrap max-h-72 overflow-y-auto" dir="ltr"></div>
                    </div>

                    <div class="bg-slate-900/60 p-4 rounded-xl border border-amber-900/40">
                        <div class="flex items-center justify-between mb-2">
                            <h3 class="text-sm font-bold text-amber-300">Activity Timeline</h3>
                            <button onclick="clearOsintActivityLog()" class="px-3 py-1.5 rounded-lg bg-amber-900/40 hover:bg-amber-800 border border-amber-800/50 text-amber-300 text-xs font-bold">تنظيف السجل</button>
                        </div>
                        <p class="text-[11px] text-gray-500 mb-2">آخر عمليات OSINT مع الوقت والنوع ودرجة المخاطرة.</p>
                        <div id="osintActivityFeed" class="space-y-2 max-h-72 overflow-y-auto"></div>
                    </div>
                </div>
            </div>

            <div id="training-section" class="hidden space-y-4">
                <h2 class="text-xl font-bold text-amber-300 border-b border-slate-700 pb-2">🎯 قسم التدريب</h2>
                <div class="bg-amber-950/20 border border-amber-900/40 p-4 rounded-xl text-xs text-amber-100/90 leading-6">
                    هذا القسم يجمع 3 مسارات تدريبية في مكان واحد: التعلم والمحاكاة، CTF، والهندسة الاجتماعية.
                </div>
                <div class="training-subtabs-shell rounded-xl p-2">
                    <div class="grid grid-cols-3 gap-2">
                        <button id="btn-training-learninglab" onclick="setTrainingSubTab('learninglab')" class="training-subtab-btn px-3 py-2 rounded-lg text-xs font-bold transition-all">🎓 التعلم والمحاكاة</button>
                        <button id="btn-training-ctf" onclick="setTrainingSubTab('ctf')" class="training-subtab-btn px-3 py-2 rounded-lg text-xs font-bold transition-all">🏁 CTF</button>
                        <button id="btn-training-se" onclick="setTrainingSubTab('se')" class="training-subtab-btn px-3 py-2 rounded-lg text-xs font-bold transition-all">🎭 الهندسة الاجتماعية</button>
                    </div>
                </div>
            </div>

            <div id="ctf-section" class="hidden space-y-6 ctf-ui">
                <div class="rounded-2xl border border-amber-900/40 bg-gradient-to-r from-amber-950/25 via-slate-900/85 to-violet-950/20 p-5 shadow-[0_12px_30px_rgba(0,0,0,0.35)]">
                    <div class="flex flex-col items-start gap-3">
                        <div>
                            <h2 class="ctf-main-title font-bold text-amber-300 border-b border-transparent pb-0 flex items-center gap-2"><span class="inline-block animate-pulse">🏁</span> TITAN CTF ARENA</h2>
                            <p class="ctf-meta-text text-gray-300 mt-1 ctf-bidi">منصة تحديات متجددة مع مساعد AI للتلميحات المنهجية بدون كشف العلم النهائي.</p>
                        </div>
                        <div id="ctfAiSourceBadge" class="text-[10px] px-2 py-1 rounded border border-cyan-800/50 bg-cyan-900/20 text-cyan-300 font-bold">AI: TITAN</div>
                    </div>
                </div>

                <div class="space-y-2">
                    <div class="rounded-lg border border-slate-700 bg-black/35 px-3 py-2">
                        <div class="text-[10px] text-gray-500">Active</div>
                        <div id="ctfStatActive" class="text-lg font-black text-amber-300">0</div>
                    </div>
                    <div class="rounded-lg border border-slate-700 bg-black/35 px-3 py-2">
                        <div class="text-[10px] text-gray-500">Solved This Cycle</div>
                        <div id="ctfStatSolvedCycle" class="text-lg font-black text-emerald-300">0</div>
                    </div>
                    <div class="rounded-lg border border-slate-700 bg-black/35 px-3 py-2">
                        <div class="text-[10px] text-gray-500">Total Solved</div>
                        <div id="ctfStatSolvedTotal" class="text-lg font-black text-cyan-300">0</div>
                    </div>
                    <div class="rounded-lg border border-slate-700 bg-black/35 px-3 py-2">
                        <div class="text-[10px] text-gray-500">Total Points</div>
                        <div id="ctfStatPoints" class="text-lg font-black text-violet-300">0</div>
                    </div>
                    <div class="rounded-lg border border-slate-700 bg-black/35 px-3 py-2">
                        <div class="text-[10px] text-gray-500">Rotation</div>
                        <div id="ctfStatRotation" class="text-sm font-black text-amber-200">--</div>
                    </div>
                </div>

                <div class="space-y-4">
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-amber-900/40">
                        <div class="flex flex-col gap-3 mb-3">
                            <div>
                                <div class="ctf-section-label text-amber-300">Challenge Filters</div>
                                <p class="ctf-meta-text text-gray-300 mt-1 ctf-bidi">ابحث بسرعة بالتصنيف/الصعوبة أو اعرض غير المحلول فقط.</p>
                            </div>
                            <div class="flex flex-col gap-2 w-full">
                                <button onclick="ctfLoadChallenges(true)" class="px-3 py-2 rounded-lg bg-amber-900/40 hover:bg-amber-800 border border-amber-800/50 text-amber-300 text-xs font-bold">تحديث التحديات</button>
                            </div>
                        </div>
                        <div class="space-y-2 mb-2">
                            <input id="ctfSearchInput" type="text" oninput="ctfApplyFilters()" placeholder="ابحث بالعنوان/الوصف/التصنيف..." class="p-2 rounded-lg bg-slate-900 border border-slate-700 text-xs outline-none w-full">
                            <select id="ctfFilterDifficulty" onchange="ctfApplyFilters()" class="p-2 rounded-lg bg-slate-900 border border-slate-700 text-xs outline-none">
                                <option value="all" selected>كل الصعوبات</option>
                                <option value="easy">Easy</option>
                                <option value="medium">Medium</option>
                                <option value="hard">Hard</option>
                            </select>
                            <select id="ctfFilterCategory" onchange="ctfApplyFilters()" class="p-2 rounded-lg bg-slate-900 border border-slate-700 text-xs outline-none">
                                <option value="all" selected>كل التصنيفات</option>
                            </select>
                        </div>
                        <label class="flex items-center gap-2 text-xs px-3 py-2 rounded-lg border border-slate-700 bg-slate-900/60 w-fit">
                            <input id="ctfFilterUnsolved" type="checkbox" onchange="ctfApplyFilters()" class="accent-amber-500">
                            <span class="text-gray-300">عرض غير المحلولة فقط</span>
                        </label>
                        <div id="ctfMeta" class="ctf-meta-text text-gray-300 bg-black/40 border border-slate-700 rounded-lg p-2 ctf-bidi mt-2">جار تحميل بيانات CTF...</div>
                    </div>

                    <div id="ctfList" class="grid grid-cols-1 gap-4"></div>
                </div>
            </div>

            <div id="ir-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-red-400 border-b border-slate-700 pb-2">🚨 Incident Response</h2>

                <div class="bg-slate-900/60 p-4 rounded-xl border border-red-900/40 space-y-3">
                    <div class="flex items-center justify-between gap-2 flex-wrap">
                        <h3 class="text-sm font-bold text-red-300">Incident Command Dashboard</h3>
                        <button onclick="irRefreshSummary()" class="px-3 py-1 rounded bg-red-900/40 border border-red-800/50 text-red-300 text-xs font-bold">تحديث</button>
                    </div>
                    <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2 text-xs">
                        <div class="p-2 rounded border border-slate-700 bg-black/40"><div class="text-gray-400">Total</div><div id="irSumTotal" class="text-gray-100 font-bold">0</div></div>
                        <div class="p-2 rounded border border-slate-700 bg-black/40"><div class="text-gray-400">Open</div><div id="irSumOpen" class="text-blue-300 font-bold">0</div></div>
                        <div class="p-2 rounded border border-slate-700 bg-black/40"><div class="text-gray-400">Investigating</div><div id="irSumInvestigating" class="text-amber-300 font-bold">0</div></div>
                        <div class="p-2 rounded border border-slate-700 bg-black/40"><div class="text-gray-400">Contained</div><div id="irSumContained" class="text-emerald-300 font-bold">0</div></div>
                        <div class="p-2 rounded border border-slate-700 bg-black/40"><div class="text-gray-400">Closed</div><div id="irSumClosed" class="text-teal-300 font-bold">0</div></div>
                        <div class="p-2 rounded border border-slate-700 bg-black/40"><div class="text-gray-400">Critical</div><div id="irSumCritical" class="text-red-300 font-bold">0</div></div>
                        <div class="p-2 rounded border border-slate-700 bg-black/40"><div class="text-gray-400">SLA Breached</div><div id="irSumSlaBreached" class="text-rose-300 font-bold">0</div></div>
                        <div class="p-2 rounded border border-slate-700 bg-black/40"><div class="text-gray-400">Avg IOC Risk</div><div id="irSumAvgRisk" class="text-fuchsia-300 font-bold">0</div></div>
                    </div>
                </div>

                <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-red-900/40 space-y-3">
                        <h3 class="text-sm font-bold text-red-300">إنشاء قضية متقدمة</h3>
                        <input id="irCaseTitle" type="text" placeholder="عنوان القضية" class="w-full p-2 rounded-lg bg-slate-900 border border-slate-700 outline-none text-sm">
                        <div class="grid grid-cols-2 gap-2">
                            <select id="irCaseSeverity" class="w-full p-2 rounded-lg bg-slate-900 border border-slate-700 outline-none text-xs">
                                <option value="low">Severity: Low</option>
                                <option value="medium" selected>Severity: Medium</option>
                                <option value="high">Severity: High</option>
                                <option value="critical">Severity: Critical</option>
                            </select>
                            <select id="irCasePriority" class="w-full p-2 rounded-lg bg-slate-900 border border-slate-700 outline-none text-xs">
                                <option value="p1">Priority P1</option>
                                <option value="p2" selected>Priority P2</option>
                                <option value="p3">Priority P3</option>
                                <option value="p4">Priority P4</option>
                            </select>
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                            <select id="irCaseCategory" class="w-full p-2 rounded-lg bg-slate-900 border border-slate-700 outline-none text-xs">
                                <option value="general" selected>Category: General</option>
                                <option value="phishing">Phishing</option>
                                <option value="malware">Malware</option>
                                <option value="account_takeover">Account Takeover</option>
                                <option value="data_leak">Data Leak</option>
                                <option value="insider">Insider</option>
                                <option value="fraud">Fraud</option>
                            </select>
                            <select id="irCaseSource" class="w-full p-2 rounded-lg bg-slate-900 border border-slate-700 outline-none text-xs">
                                <option value="manual" selected>Source: Manual</option>
                                <option value="siem">SIEM</option>
                                <option value="user_report">User Report</option>
                                <option value="external_feed">External Feed</option>
                            </select>
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                            <input id="irCaseOwner" type="text" placeholder="Owner (SOC/IR Team)" class="w-full p-2 rounded-lg bg-slate-900 border border-slate-700 outline-none text-xs" dir="ltr">
                            <input id="irCaseSla" type="number" min="15" max="10080" value="240" placeholder="SLA minutes" class="w-full p-2 rounded-lg bg-slate-900 border border-slate-700 outline-none text-xs">
                        </div>
                        <textarea id="irCaseDesc" rows="3" placeholder="وصف سريع للحادث" class="w-full p-2 rounded-lg bg-slate-900 border border-slate-700 outline-none text-sm"></textarea>
                        <button onclick="irCreateCase()" class="w-full py-2 rounded-lg bg-red-900/50 hover:bg-red-800 text-red-300 font-bold border border-red-800/40">إنشاء</button>
                    </div>

                    <div class="lg:col-span-2 bg-slate-900/60 p-4 rounded-xl border border-red-900/40">
                        <div class="flex items-center justify-between mb-3">
                            <h3 class="text-sm font-bold text-red-300">قائمة القضايا</h3>
                            <div class="flex items-center gap-2">
                                <button onclick="irLoadCases()" class="text-xs px-3 py-1 rounded bg-slate-800 border border-slate-700">تحديث</button>
                            </div>
                        </div>
                        <div class="grid grid-cols-1 md:grid-cols-4 gap-2 mb-3">
                            <input id="irCaseSearch" type="text" placeholder="بحث بالعنوان/الوصف..." class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none md:col-span-2">
                            <select id="irFilterStatus" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                                <option value="all" selected>كل الحالات</option>
                                <option value="open">Open</option>
                                <option value="investigating">Investigating</option>
                                <option value="contained">Contained</option>
                                <option value="closed">Closed</option>
                            </select>
                            <select id="irFilterSeverity" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                                <option value="all" selected>كل الشدات</option>
                                <option value="low">Low</option>
                                <option value="medium">Medium</option>
                                <option value="high">High</option>
                                <option value="critical">Critical</option>
                            </select>
                        </div>
                        <div id="irCasesList" class="space-y-2 max-h-56 overflow-y-auto"></div>
                    </div>
                </div>

                <div class="bg-slate-900/60 p-4 rounded-xl border border-red-900/40">
                    <div class="flex items-center justify-between mb-3">
                        <h3 class="text-sm font-bold text-red-300">إدارة مؤشرات القضية</h3>
                        <div id="irSelectedCase" class="text-xs text-gray-400">لم يتم اختيار قضية</div>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-4 gap-2 mb-2 text-xs">
                        <div id="irSelectedMetaStatus" class="p-2 rounded bg-black/40 border border-slate-700">Status: --</div>
                        <div id="irSelectedMetaSeverity" class="p-2 rounded bg-black/40 border border-slate-700">Severity/Priority: --</div>
                        <div id="irSelectedMetaOwner" class="p-2 rounded bg-black/40 border border-slate-700">Owner: --</div>
                        <div id="irSelectedMetaSla" class="p-2 rounded bg-black/40 border border-slate-700">SLA: --</div>
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
                        <button id="ir-btn-open" onclick="irUpdateStatus('open')" class="px-3 py-1 text-xs rounded bg-slate-800 border border-slate-700 disabled:opacity-50 disabled:cursor-not-allowed">Open</button>
                        <button id="ir-btn-investigating" onclick="irUpdateStatus('investigating')" class="px-3 py-1 text-xs rounded bg-blue-900/30 border border-blue-800/50 disabled:opacity-50 disabled:cursor-not-allowed">Investigating</button>
                        <button id="ir-btn-contained" onclick="irUpdateStatus('contained')" class="px-3 py-1 text-xs rounded bg-amber-900/30 border border-amber-800/50 disabled:opacity-50 disabled:cursor-not-allowed">Contained</button>
                        <button id="ir-btn-closed" onclick="irUpdateStatus('closed')" class="px-3 py-1 text-xs rounded bg-green-900/30 border border-green-800/50 disabled:opacity-50 disabled:cursor-not-allowed">Closed</button>
                        <button id="ir-btn-export" onclick="irExportReport()" class="px-3 py-1 text-xs rounded bg-emerald-900/30 border border-emerald-800/50 disabled:opacity-50 disabled:cursor-not-allowed">تصدير تقرير</button>
                        <button id="ir-btn-export-pdf" onclick="irExportReport('pdf')" class="px-3 py-1 text-xs rounded bg-indigo-900/30 border border-indigo-800/50 disabled:opacity-50 disabled:cursor-not-allowed">PDF</button>
                        <button id="ir-btn-auto-priority" onclick="irRunAutoPriority()" class="px-3 py-1 text-xs rounded bg-fuchsia-900/30 border border-fuchsia-800/50 disabled:opacity-50 disabled:cursor-not-allowed">Auto Priority</button>
                    </div>
                    <div id="irIocTimeline" class="mt-3 p-3 rounded-lg bg-black/40 border border-slate-700 max-h-56 overflow-y-auto text-xs"></div>
                </div>

                <div class="bg-slate-900/60 p-4 rounded-xl border border-red-900/40 space-y-3">
                    <div class="flex items-center justify-between gap-2 flex-wrap">
                        <h3 class="text-sm font-bold text-red-300">Incident Kanban Board</h3>
                        <div class="text-[11px] text-gray-500">اسحب القضية وأفلتها لتغيير الحالة بسرعة.</div>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                        <div class="rounded-lg border border-slate-700 bg-black/30 p-2">
                            <div class="text-xs font-bold text-blue-300 mb-2">Open</div>
                            <div id="irKanban-open" data-status="open" class="space-y-2 min-h-[120px]"></div>
                        </div>
                        <div class="rounded-lg border border-slate-700 bg-black/30 p-2">
                            <div class="text-xs font-bold text-amber-300 mb-2">Investigating</div>
                            <div id="irKanban-investigating" data-status="investigating" class="space-y-2 min-h-[120px]"></div>
                        </div>
                        <div class="rounded-lg border border-slate-700 bg-black/30 p-2">
                            <div class="text-xs font-bold text-orange-300 mb-2">Contained</div>
                            <div id="irKanban-contained" data-status="contained" class="space-y-2 min-h-[120px]"></div>
                        </div>
                        <div class="rounded-lg border border-slate-700 bg-black/30 p-2">
                            <div class="text-xs font-bold text-emerald-300 mb-2">Closed</div>
                            <div id="irKanban-closed" data-status="closed" class="space-y-2 min-h-[120px]"></div>
                        </div>
                    </div>
                </div>

                <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-orange-900/40 space-y-3">
                        <h3 class="text-sm font-bold text-orange-300">Incident Timeline Notes</h3>
                        <div class="grid grid-cols-1 md:grid-cols-3 gap-2">
                            <select id="irNoteType" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                                <option value="analysis" selected>Analysis</option>
                                <option value="containment">Containment</option>
                                <option value="eradication">Eradication</option>
                                <option value="recovery">Recovery</option>
                                <option value="lesson">Lesson Learned</option>
                            </select>
                            <textarea id="irNoteText" rows="2" placeholder="اكتب تحديث الحالة/الإجراء المتخذ..." class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none md:col-span-2"></textarea>
                        </div>
                        <button onclick="irAddNote()" class="w-full py-2 rounded bg-orange-900/40 border border-orange-800/50 text-orange-300 text-xs font-bold">إضافة ملاحظة</button>
                        <div id="irNotesTimeline" class="p-2 rounded bg-black/40 border border-slate-700 max-h-60 overflow-y-auto text-xs"></div>
                    </div>

                    <div class="bg-slate-900/60 p-4 rounded-xl border border-emerald-900/40 space-y-3">
                        <h3 class="text-sm font-bold text-emerald-300">Evidence Locker</h3>
                        <input id="irEvidenceFile" type="file" class="block w-full text-sm text-slate-400 file:mr-2 file:py-2 file:px-4 file:rounded-full file:border-0 file:bg-slate-800 file:text-emerald-300 border border-slate-700 p-2 rounded-xl">
                        <input id="irEvidenceNote" type="text" placeholder="ملاحظة على الدليل" class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                        <button onclick="irUploadEvidence()" class="w-full py-2 rounded bg-emerald-900/40 border border-emerald-800/50 text-emerald-300 text-xs font-bold">رفع دليل</button>
                        <div id="irEvidenceList" class="p-2 rounded bg-black/40 border border-slate-700 max-h-60 overflow-y-auto text-xs"></div>
                    </div>
                </div>
            </div>

            <div id="forensics-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-teal-400 border-b border-slate-700 pb-2">🧪 Digital Forensics</h2>

                <div class="bg-slate-900/60 p-4 rounded-xl border border-teal-900/40 space-y-3">
                    <div class="flex items-center justify-between gap-2 flex-wrap">
                        <h3 class="text-sm font-bold text-teal-300">Forensics Command Dashboard</h3>
                        <button onclick="forensicsRefreshSummary()" class="px-3 py-1 rounded bg-teal-900/40 border border-teal-800/50 text-teal-300 text-xs font-bold">تحديث</button>
                    </div>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                        <div class="p-2 rounded border border-slate-700 bg-black/40"><div class="text-gray-400">Sessions</div><div id="forensicsSumSessions" class="text-gray-100 font-bold">0</div></div>
                        <div class="p-2 rounded border border-slate-700 bg-black/40"><div class="text-gray-400">High Risk</div><div id="forensicsSumHighRisk" class="text-red-300 font-bold">0</div></div>
                        <div class="p-2 rounded border border-slate-700 bg-black/40"><div class="text-gray-400">Avg Entropy</div><div id="forensicsSumEntropy" class="text-amber-300 font-bold">0</div></div>
                        <div class="p-2 rounded border border-slate-700 bg-black/40"><div class="text-gray-400">Artifacts</div><div id="forensicsSumArtifacts" class="text-cyan-300 font-bold">0</div></div>
                    </div>
                </div>

                <div class="grid grid-cols-1 xl:grid-cols-3 gap-4">
                    <div class="xl:col-span-2 bg-slate-900/60 p-4 rounded-xl border border-teal-900/40 space-y-3">
                        <h3 class="text-sm font-bold text-teal-300">Advanced File Triage</h3>
                        <input id="forensicsFile" type="file" class="block w-full text-sm text-slate-400 file:mr-2 file:py-2 file:px-4 file:rounded-full file:border-0 file:bg-slate-800 file:text-teal-300 border border-slate-700 p-2 rounded-xl">
                        <div class="grid grid-cols-1 md:grid-cols-3 gap-2">
                            <input id="forensicsMinStringLen" type="number" min="4" max="32" value="6" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none" placeholder="Min string length">
                            <button onclick="forensicsTriage()" class="py-2 rounded bg-teal-900/40 border border-teal-800/50 text-teal-300 text-xs font-bold">تحليل الدليل</button>
                            <button onclick="forensicsLoadHistory()" class="py-2 rounded bg-slate-800 border border-slate-700 text-xs font-bold text-gray-300">تحديث السجل</button>
                        </div>
                        <div id="forensicsResult" class="p-2 rounded bg-black/40 border border-slate-700 text-xs font-mono whitespace-pre-wrap" dir="ltr"></div>
                    </div>

                    <div class="bg-slate-900/60 p-4 rounded-xl border border-cyan-900/40 space-y-3">
                        <h3 class="text-sm font-bold text-cyan-300">IOC Extractor</h3>
                        <textarea id="forensicsTextInput" rows="8" placeholder="الصق نص/لوج لفحص IOCs (IPs, URLs, Emails, Hashes)..." class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none font-mono" dir="ltr"></textarea>
                        <button onclick="forensicsExtractIocs()" class="w-full py-2 rounded bg-cyan-900/40 border border-cyan-800/50 text-cyan-300 text-xs font-bold">Extract IOCs</button>
                        <div id="forensicsIocResult" class="p-2 rounded bg-black/40 border border-slate-700 max-h-60 overflow-y-auto text-xs"></div>
                    </div>
                </div>

                <div class="grid grid-cols-1 xl:grid-cols-3 gap-4">
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-emerald-900/40 space-y-3 xl:col-span-1">
                        <h3 class="text-sm font-bold text-emerald-300">Forensics Sessions</h3>
                        <div class="grid grid-cols-2 gap-2">
                            <select id="forensicsFilterRisk" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                                <option value="all">All Risk</option>
                                <option value="high">High (>=70)</option>
                                <option value="medium">Medium (40-69)</option>
                                <option value="low">Low (&lt;40)</option>
                            </select>
                            <input id="forensicsFilterType" type="text" placeholder="file type (pdf, zip...)" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none" dir="ltr">
                            <input id="forensicsFilterFrom" type="date" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                            <input id="forensicsFilterTo" type="date" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                            <button onclick="forensicsApplyHistoryFilters()" class="py-2 rounded bg-emerald-900/40 border border-emerald-800/50 text-emerald-300 text-xs font-bold">Apply Filters</button>
                            <button onclick="forensicsResetHistoryFilters()" class="py-2 rounded bg-slate-800 border border-slate-700 text-xs font-bold text-gray-300">Reset</button>
                        </div>
                        <div id="forensicsHistory" class="p-2 rounded bg-black/40 border border-slate-700 max-h-80 overflow-y-auto text-xs"></div>
                    </div>
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-indigo-900/40 space-y-3 xl:col-span-2">
                        <div class="flex items-center justify-between gap-2 flex-wrap">
                            <h3 class="text-sm font-bold text-indigo-300">Session Details</h3>
                            <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 w-full sm:w-auto">
                                <button onclick="forensicsExportSession('json')" class="px-3 py-1 rounded bg-indigo-900/40 border border-indigo-800/50 text-indigo-300 text-xs font-bold">Export JSON</button>
                                <button onclick="forensicsExportSession('pdf')" class="px-3 py-1 rounded bg-cyan-900/40 border border-cyan-800/50 text-cyan-300 text-xs font-bold">Export PDF</button>
                                <button onclick="forensicsCreateIncidentFromSession()" class="px-3 py-1 rounded bg-red-900/40 border border-red-800/50 text-red-300 text-xs font-bold">Create Incident</button>
                            </div>
                        </div>
                        <div id="forensicsSessionDetail" class="p-2 rounded bg-black/40 border border-slate-700 max-h-80 overflow-y-auto text-xs font-mono whitespace-pre-wrap" dir="ltr"></div>
                    </div>
                </div>
            </div>


            <div id="learninglab-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-indigo-400 border-b border-slate-700 pb-2">🎓 التعلم والمحاكاة</h2>

                <div class="bg-indigo-950/20 border border-indigo-900/40 p-4 rounded-xl text-xs text-indigo-200 leading-6">
                    هذا القسم الآن عبارة عن موسوعة دفاعية شاملة للهجمات والثغرات الشائعة والمتقدمة. المحتوى توعوي دفاعي فقط: كيف تحدث الهجمة، أين تحدث، أشهر الأدوات المرتبطة بها، وخطوات الحماية العملية.
                </div>

                <div class="bg-slate-900/60 p-4 rounded-xl border border-indigo-900/40 space-y-3">
                    <div class="space-y-2">
                        <input id="learningSearchInput" type="text" oninput="learningCatalogApplyFilters()" placeholder="ابحث باسم الهجمة أو الأداة أو وسيلة الحماية..." class="w-full p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                        <select id="learningCategoryFilter" onchange="learningCatalogApplyFilters()" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none"></select>
                        <select id="learningSeverityFilter" onchange="learningCatalogApplyFilters()" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none"></select>
                        <button onclick="learningCatalogResetFilters()" class="p-2 rounded bg-indigo-900/40 border border-indigo-800/50 text-indigo-300 text-xs font-bold">إعادة ضبط الفلاتر</button>
                    </div>
                    <div id="learningCatalogStats" class="text-[11px] text-gray-400"></div>
                </div>

                <div class="space-y-4">
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-cyan-900/40">
                        <div class="flex items-center justify-between gap-2 mb-3">
                            <h3 class="text-sm font-bold text-cyan-300">قائمة الثغرات والهجمات</h3>
                            <span class="text-[10px] text-gray-500">عرض دفاعي منظّم</span>
                        </div>
                        <div id="learningAttackCards" class="grid grid-cols-1 gap-2"></div>
                    </div>

                    <div class="bg-slate-900/60 p-4 rounded-xl border border-fuchsia-900/40 space-y-3">
                        <div class="flex items-center justify-between gap-2">
                            <h3 class="text-sm font-bold text-fuchsia-300">التفاصيل الكاملة</h3>
                            <span id="learningSelectedAttackBadge" class="text-[10px] px-2 py-1 rounded border border-slate-700 text-gray-300">اختر هجمة</span>
                        </div>
                        <div id="learningAttackDetail" class="p-3 rounded bg-black/40 border border-slate-700 text-xs leading-6">
                            اختر أي هجمة من القائمة لعرض شرح كامل عنها.
                        </div>
                    </div>
                </div>
            </div>


            <div id="se-section" class="hidden space-y-6">
                <h2 class="text-xl font-bold text-pink-400 border-b border-slate-700 pb-2">🎭 Social Engineering Defense</h2>

                <div class="bg-slate-900/60 p-4 rounded-xl border border-violet-900/40 space-y-3">
                    <div class="flex items-center justify-between gap-2 flex-wrap">
                        <h3 class="text-sm font-bold text-violet-300">Defense Pulse Dashboard</h3>
                        <button onclick="seRefreshDashboard()" class="px-3 py-1 rounded bg-violet-900/40 border border-violet-800/50 text-violet-300 text-xs font-bold">تحديث</button>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-4 gap-2">
                        <div class="p-2 rounded border border-slate-700 bg-black/40 text-xs">
                            <div class="text-gray-400">Quiz Accuracy</div>
                            <div id="seDashQuizAccuracy" class="text-emerald-300 font-bold text-base">0%</div>
                        </div>
                        <div class="p-2 rounded border border-slate-700 bg-black/40 text-xs">
                            <div class="text-gray-400">Quiz Answers</div>
                            <div id="seDashQuizAnswers" class="text-cyan-300 font-bold text-base">0</div>
                        </div>
                        <div class="p-2 rounded border border-slate-700 bg-black/40 text-xs">
                            <div class="text-gray-400">Last Quiz Score</div>
                            <div id="seDashLastScore" class="text-fuchsia-300 font-bold text-base">0</div>
                        </div>
                        <div class="p-2 rounded border border-slate-700 bg-black/40 text-xs">
                            <div class="text-gray-400">Risk Index</div>
                            <div id="seDashRiskIndex" class="text-rose-300 font-bold text-base">0</div>
                        </div>
                    </div>
                    <div id="seRiskTrendBars" class="grid grid-cols-7 gap-2"></div>
                    <div id="seRiskTrendMeta" class="text-[11px] text-gray-500">Trend: waiting for data...</div>
                </div>

                <div class="grid grid-cols-1 xl:grid-cols-3 gap-4">
                    <div class="xl:col-span-2 bg-slate-900/60 p-4 rounded-xl border border-pink-900/40 space-y-3">
                        <div class="flex items-center justify-between gap-2 flex-wrap">
                            <h3 class="text-sm font-bold text-pink-300">Scenario Lab (Defensive)</h3>
                            <span id="seScenarioDifficulty" class="text-[10px] px-2 py-1 rounded border border-slate-700 text-gray-300">Difficulty: --</span>
                        </div>
                        <div class="grid grid-cols-1 md:grid-cols-5 gap-2">
                            <select id="seScenarioType" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none md:col-span-2">
                                <option value="phishing_email">Phishing Email</option>
                                <option value="vishing_call">Vishing Call</option>
                                <option value="pretexting">Pretexting</option>
                                <option value="baiting_usb">Baiting USB</option>
                                <option value="banking_ar">Arabic Sector - Banking</option>
                                <option value="education_ar">Arabic Sector - Education</option>
                                <option value="healthcare_ar">Arabic Sector - Healthcare</option>
                                <option value="sector_ar">Arabic Sector (Auto by selector)</option>
                            </select>
                            <select id="seScenarioSector" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                                <option value="banking" selected>Sector: Banking</option>
                                <option value="education">Sector: Education</option>
                                <option value="healthcare">Sector: Healthcare</option>
                            </select>
                            <select id="seScenarioPressure" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                                <option value="normal" selected>Pressure: Normal</option>
                                <option value="high">Pressure: High</option>
                                <option value="critical">Pressure: Critical</option>
                            </select>
                            <button onclick="seGenerateScenario()" class="py-2 rounded bg-pink-900/40 border border-pink-800/50 text-pink-300 text-xs font-bold">Generate Scenario</button>
                        </div>
                        <div id="seScenarioResult" class="p-2 rounded bg-black/40 border border-slate-700 text-xs whitespace-pre-wrap"></div>
                    </div>

                    <div class="bg-slate-900/60 p-4 rounded-xl border border-fuchsia-900/40 space-y-3">
                        <h3 class="text-sm font-bold text-fuchsia-300">Micro Drill Quiz</h3>
                        <div id="seQuizMeta" class="text-[11px] text-gray-400">اختبار سريع يرفع جاهزيتك الدفاعية.</div>
                        <div id="seQuizQuestion" class="p-2 rounded bg-black/40 border border-slate-700 text-xs text-gray-100"></div>
                        <div id="seQuizOptions" class="space-y-2"></div>
                        <div class="flex gap-2">
                            <button onclick="seNextQuizQuestion()" class="flex-1 py-2 rounded bg-fuchsia-900/40 border border-fuchsia-800/50 text-fuchsia-300 text-xs font-bold">التالي</button>
                            <button onclick="seRestartQuiz()" class="flex-1 py-2 rounded bg-slate-800 border border-slate-700 text-xs font-bold text-gray-300">إعادة</button>
                        </div>
                        <div id="seQuizFeedback" class="text-[11px] text-gray-400"></div>
                    </div>
                </div>

                <div class="grid grid-cols-1 xl:grid-cols-3 gap-4">
                    <div class="bg-slate-900/60 p-4 rounded-xl border border-rose-900/40 space-y-3">
                        <h3 class="text-sm font-bold text-rose-300">Threat Signal Analyzer</h3>
                        <div class="grid grid-cols-1 gap-2">
                            <select id="seSignalChannel" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                                <option value="email" selected>Email</option>
                                <option value="chat">Chat</option>
                                <option value="phone">Phone</option>
                                <option value="social_dm">Social DM</option>
                            </select>
                            <select id="seSignalSenderTrust" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                                <option value="known" selected>Known Sender</option>
                                <option value="unknown">Unknown Sender</option>
                                <option value="spoofed">Likely Spoofed</option>
                            </select>
                            <select id="seSignalUrgency" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                                <option value="low">Urgency: Low</option>
                                <option value="medium" selected>Urgency: Medium</option>
                                <option value="high">Urgency: High</option>
                            </select>
                            <label class="flex items-center gap-2 text-xs"><input id="seSignalHasLink" type="checkbox" class="accent-rose-500"> يحتوي رابط مختصر أو غامض</label>
                            <label class="flex items-center gap-2 text-xs"><input id="seSignalSensitiveReq" type="checkbox" class="accent-rose-500"> يطلب بيانات حساسة / OTP</label>
                            <label class="flex items-center gap-2 text-xs"><input id="seSignalPolicyBypass" type="checkbox" class="accent-rose-500"> يطلب تجاوز السياسة</label>
                            <button onclick="seAnalyzeSignal()" class="w-full py-2 rounded bg-rose-900/40 border border-rose-800/50 text-rose-300 text-xs font-bold">تحليل الإشارة</button>
                        </div>
                        <div id="seSignalResult" class="p-2 rounded bg-black/40 border border-slate-700 text-xs"></div>
                    </div>

                    <div class="xl:col-span-2 bg-slate-900/60 p-4 rounded-xl border border-emerald-900/40 space-y-3">
                        <div class="flex items-center justify-between gap-2 flex-wrap">
                            <h3 class="text-sm font-bold text-emerald-300">Response Playbook Builder</h3>
                            <div class="flex gap-2">
                                <button onclick="sePlaybookInjectTemplate()" class="px-3 py-1 rounded bg-emerald-900/40 border border-emerald-800/50 text-emerald-300 text-xs font-bold">قالب جاهز</button>
                                <button onclick="seExportPlaybook()" class="px-3 py-1 rounded bg-indigo-900/40 border border-indigo-800/50 text-indigo-300 text-xs font-bold">تصدير</button>
                                <button onclick="seClearPlaybook()" class="px-3 py-1 rounded bg-red-900/40 border border-red-800/50 text-red-300 text-xs font-bold">تفريغ</button>
                            </div>
                        </div>
                        <div class="grid grid-cols-1 md:grid-cols-6 gap-2">
                            <select id="sePlaybookPhase" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                                <option value="detect" selected>Detect</option>
                                <option value="verify">Verify</option>
                                <option value="contain">Contain</option>
                                <option value="report">Report</option>
                                <option value="lessons">Lessons Learned</option>
                            </select>
                            <input id="sePlaybookOwner" type="text" placeholder="Owner (SOC/IT/Manager)" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none" dir="ltr">
                            <input id="sePlaybookEta" type="text" placeholder="ETA (e.g. 15m)" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none" dir="ltr">
                            <input id="sePlaybookAction" type="text" placeholder="Action description" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none md:col-span-2">
                            <button onclick="seAddPlaybookStep()" class="py-2 rounded bg-emerald-900/40 border border-emerald-800/50 text-emerald-300 text-xs font-bold">إضافة</button>
                        </div>
                        <div id="sePlaybookResult" class="p-2 rounded bg-black/40 border border-slate-700 max-h-56 overflow-y-auto text-xs"></div>
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
                    <div class="grid grid-cols-1 md:grid-cols-4 gap-2">
                        <div id="seIntelTotal" class="p-2 rounded border border-slate-700 bg-black/40 text-xs">Total: 0</div>
                        <div id="seIntelHighRisk" class="p-2 rounded border border-red-900/50 bg-red-900/10 text-xs text-red-300">High Risk: 0</div>
                        <div id="seIntelMediumRisk" class="p-2 rounded border border-amber-900/50 bg-amber-900/10 text-xs text-amber-300">Medium Risk: 0</div>
                        <div id="seIntelLowRisk" class="p-2 rounded border border-emerald-900/50 bg-emerald-900/10 text-xs text-emerald-300">Low Risk: 0</div>
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
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-2">
                        <input id="seIntelSearch" type="text" placeholder="بحث في الملاحظات/الموضوع..." class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                        <select id="seIntelFilterConfidence" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                            <option value="all" selected>كل مستويات الثقة</option>
                            <option value="high">High Confidence</option>
                            <option value="medium">Medium Confidence</option>
                            <option value="low">Low Confidence</option>
                        </select>
                        <select id="seIntelFilterCategory" class="p-2 rounded bg-slate-900 border border-slate-700 text-xs outline-none">
                            <option value="all" selected>كل الفئات</option>
                            <option value="identity">Identity</option>
                            <option value="behavior">Behavior</option>
                            <option value="infrastructure">Infrastructure</option>
                            <option value="message">Message Pattern</option>
                        </select>
                    </div>
                    <div id="seIntelBoardResult" class="p-2 rounded bg-black/40 border border-slate-700 max-h-72 overflow-y-auto text-xs"></div>
                    <div class="text-[11px] text-gray-500">هذا القسم دفاعي توعوي فقط: التحليل والاستجابة والرفع إلى SOC.</div>
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
                                        <option value="ar_JO" selected>🇯🇴 الأردن (Jordan)</option>
                                        <option value="ar_SA">🇸🇦 السعودية (Saudi Arabia)</option>
                                        <option value="ar_AE">🇦🇪 الإمارات (UAE)</option>
                                        <option value="ar_EG">🇪🇬 مصر (Egypt)</option>
                                    </optgroup>
                                    <optgroup label="International">
                                        <option value="en_US">🇺🇸 United States</option>
                                        <option value="en_GB">🇬🇧 United Kingdom</option>
                                        <option value="fr_FR">🇫🇷 France</option>
                                        <option value="de_DE">🇩🇪 Germany</option>
                                        <option value="es_ES">🇪🇸 Spain</option>
                                        <option value="tr_TR">🇹🇷 Turkey</option>
                                        <option value="ru_RU">🇷🇺 Russia</option>
                                        <option value="zh_CN">🇨🇳 China</option>
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
                                                <div id="idNameEnWrap" class="hidden mt-1">
                                                    <span id="idNameEn" class="inline-block text-sm md:text-base text-cyan-300/90 font-semibold tracking-wide" dir="ltr"></span>
                                                </div>
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
                setupForgotFromLogin(true);
            }
        }

        function setupForgotFromLogin(autoSend) {
            const loginUser = document.getElementById('auth-login-user');
            const forgotUser = document.getElementById('forgot-username');
            const step1 = document.getElementById('forgot-step1');
            const step2 = document.getElementById('forgot-step2');
            const step3 = document.getElementById('forgot-step3');
            const step1Err = document.getElementById('forgot-step1-error');
            const step2Err = document.getElementById('forgot-step2-error');
            const step3Err = document.getElementById('forgot-step3-error');
            const otpEl = document.getElementById('forgot-otp');
            const pass1El = document.getElementById('forgot-newpass');
            const pass2El = document.getElementById('forgot-newpass2');

            if (!forgotUser) return;

            const username = (loginUser?.value || '').trim();
            if (username) {
                forgotUser.value = username;
            }

            if (step1) step1.style.display = 'block';
            if (step2) step2.style.display = 'none';
            if (step3) step3.style.display = 'none';
            if (step1Err) step1Err.style.display = 'none';
            if (step2Err) step2Err.style.display = 'none';
            if (step3Err) step3Err.style.display = 'none';
            if (otpEl) otpEl.value = '';
            if (pass1El) pass1El.value = '';
            if (pass2El) pass2El.value = '';

            if (autoSend && username) {
                doForgotSend();
            } else if (!username) {
                if (step1Err) {
                    step1Err.textContent = 'اكتب اسم المستخدم أولاً ليتم إرسال كود الاستعادة تلقائياً.';
                    step1Err.style.display = 'block';
                }
                forgotUser.focus();
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

            const passHint = String(password || '').trim().toLowerCase();
            if (passHint === 'forgot' || passHint === 'forget' || passHint === 'نسيت' || passHint === 'نسيت كلمة السر') {
                switchAuthTab('forgot');
                return;
            }

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
            updateUsernameModeHint();
        }
        window.onload = () => {
            initRegisterTermsUi();
            initGlobalFileDropZone();
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
        const ALL_TABS = ['dash','pass','learninglab','vault','crypt','filelab','fileprotect','suite','tools','ghost','osint','training','ctf','ir','forensics','se','audio','video','qr','identity','admin'];
        const TRAINING_SUB_TABS = ['learninglab', 'ctf', 'se'];
        let __trainingSubTab = 'learninglab';
        let _aiActiveSubTab = 'chat';
        let _prevTab = 'pass';

        function setAiLauncherPulse(active) {
            const launcher = document.getElementById('ai-float-launcher');
            if (!launcher) return;
            if (active) {
                launcher.style.animation = 'aiLauncherPulse 2.2s ease-in-out infinite';
            } else {
                launcher.style.animation = 'none';
            }
        }

        function applyAiDockPosition() {
            const isMobile = window.innerWidth <= 640;
            const panelRight = isMobile ? '10px' : '20px';
            const panelBottom = isMobile ? '88px' : '96px';
            const launcherRight = isMobile ? '10px' : '20px';
            const launcherBottom = isMobile ? '14px' : '20px';

            const sec = document.getElementById('ai-section');
            if (sec) {
                sec.style.position = 'fixed';
                sec.style.left = 'auto';
                sec.style.right = panelRight;
                sec.style.bottom = panelBottom;
            }

            const launcher = document.getElementById('ai-float-launcher');
            if (launcher) {
                launcher.style.position = 'fixed';
                launcher.style.left = 'auto';
                launcher.style.right = launcherRight;
                launcher.style.bottom = launcherBottom;
                launcher.style.zIndex = '2147483647';
            }
        }

        function openAiSection() {
            const sec = document.getElementById('ai-section');
            if (sec) {
                sec.classList.remove('hidden');
                applyAiDockPosition();
                sec.style.display = 'block';
                sec.style.pointerEvents = 'auto';
                sec.style.opacity = '0';
                sec.style.transform = 'translateY(14px) scale(0.985)';
                requestAnimationFrame(() => {
                    sec.style.opacity = '1';
                    sec.style.transform = 'translateY(0) scale(1)';
                });
            }
            setAiLauncherPulse(false);
            showAiSubTab(_aiActiveSubTab || 'chat');
        }

        function closeAiBubble() {
            const sec = document.getElementById('ai-section');
            if (sec) {
                sec.style.pointerEvents = 'none';
                sec.style.opacity = '0';
                sec.style.transform = 'translateY(14px) scale(0.985)';
                setTimeout(() => {
                    sec.classList.add('hidden');
                    sec.style.display = 'none';
                    const launcher = document.getElementById('ai-float-launcher');
                    if (launcher && launcher.style.display !== 'none') {
                        setAiLauncherPulse(true);
                    }
                }, 180);
            }
        }

        function setAiBubbleVisibility(isVisible) {
            const launcher = document.getElementById('ai-float-launcher');
            if (!launcher) return;
            if (isVisible) {
                launcher.classList.remove('hidden');
                applyAiDockPosition();
                launcher.style.display = 'flex';
                launcher.style.alignItems = 'center';
                launcher.style.justifyContent = 'center';
                launcher.style.visibility = 'visible';
                launcher.style.opacity = '1';
                launcher.style.pointerEvents = 'auto';
                setAiLauncherPulse(true);
            } else {
                launcher.classList.add('hidden');
                launcher.style.display = 'none';
                launcher.style.visibility = 'hidden';
                launcher.style.opacity = '0';
                launcher.style.pointerEvents = 'none';
                setAiLauncherPulse(false);
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

        function _isVisibleElement(el) {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return false;
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        }

        function _activeDropContexts() {
            const contexts = [];
            const aiSection = document.getElementById('ai-section');
            if (aiSection && !aiSection.classList.contains('hidden') && aiSection.style.display !== 'none') {
                contexts.push(aiSection);
            }
            ALL_TABS.forEach((tab) => {
                const sec = document.getElementById(tab + '-section');
                if (!sec) return;
                const hidden = sec.classList.contains('hidden') || sec.style.display === 'none';
                if (!hidden) contexts.push(sec);
            });
            return contexts;
        }

        function _collectFileInputsFromContexts(contexts) {
            const inputs = [];
            (contexts || []).forEach((ctx) => {
                ctx.querySelectorAll('input[type="file"]').forEach((el) => inputs.push(el));
            });
            if (!inputs.length) {
                document.querySelectorAll('#main-app input[type="file"]').forEach((el) => inputs.push(el));
            }
            return inputs;
        }

        function _resolveDropTarget(dropX, dropY) {
            const inputs = _collectFileInputsFromContexts(_activeDropContexts());
            if (!inputs.length) return null;

            if (typeof dropX !== 'number' || typeof dropY !== 'number') {
                const first = inputs[0];
                let firstAnchor = first;
                if (first && first.id) {
                    const firstLabel = document.querySelector(`label[for="${first.id}"]`);
                    if (_isVisibleElement(firstLabel)) firstAnchor = firstLabel;
                }
                return { input: first, anchor: firstAnchor };
            }

            let bestInput = null;
            let bestAnchor = null;
            let bestDist = Infinity;

            inputs.forEach((input) => {
                let anchor = input;
                if (input.id) {
                    const label = document.querySelector(`label[for="${input.id}"]`);
                    if (_isVisibleElement(label)) anchor = label;
                }
                if (!_isVisibleElement(anchor)) return;

                const r = anchor.getBoundingClientRect();
                const cx = r.left + r.width / 2;
                const cy = r.top + r.height / 2;
                const dist = Math.hypot(dropX - cx, dropY - cy);
                if (dist < bestDist) {
                    bestDist = dist;
                    bestInput = input;
                    bestAnchor = anchor;
                }
            });

            if (!bestInput) {
                return { input: inputs[0], anchor: inputs[0] };
            }
            return { input: bestInput, anchor: bestAnchor || bestInput };
        }

        function _findActiveDropFileInput(dropX, dropY) {
            const target = _resolveDropTarget(dropX, dropY);
            return target ? target.input : null;
        }

        function _assignDroppedFileToInput(inputEl, file) {
            if (!inputEl || !file) return false;
            try {
                const dt = new DataTransfer();
                dt.items.add(file);
                inputEl.files = dt.files;
                inputEl.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            } catch (e) {
                return false;
            }
        }

        function initGlobalFileDropZone() {
            const drop = document.getElementById('global-file-dropzone');
            if (!drop || window.__globalDropzoneInited) return;
            window.__globalDropzoneInited = true;

            let dragCounter = 0;
            let activeTargetAnchor = null;
            const clearTargetHighlight = () => {
                if (activeTargetAnchor && activeTargetAnchor.classList) {
                    activeTargetAnchor.classList.remove('drop-target-highlight');
                }
                activeTargetAnchor = null;
            };
            const setTargetHighlight = (anchorEl) => {
                if (!anchorEl) return;
                if (activeTargetAnchor === anchorEl) return;
                clearTargetHighlight();
                if (anchorEl.classList) {
                    anchorEl.classList.add('drop-target-highlight');
                    activeTargetAnchor = anchorEl;
                }
            };
            const show = () => { drop.style.display = 'flex'; };
            const hide = () => { drop.style.display = 'none'; clearTargetHighlight(); };

            window.addEventListener('dragenter', (e) => {
                if (!e.dataTransfer || !Array.from(e.dataTransfer.types || []).includes('Files')) return;
                dragCounter += 1;
                show();
            });

            window.addEventListener('dragover', (e) => {
                if (!e.dataTransfer || !Array.from(e.dataTransfer.types || []).includes('Files')) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = 'copy';
                show();
                const target = _resolveDropTarget(e.clientX, e.clientY);
                if (target && target.anchor) setTargetHighlight(target.anchor);
            });

            window.addEventListener('dragleave', (e) => {
                if (!e.dataTransfer || !Array.from(e.dataTransfer.types || []).includes('Files')) return;
                dragCounter = Math.max(0, dragCounter - 1);
                if (dragCounter === 0) hide();
            });

            window.addEventListener('drop', (e) => {
                if (!e.dataTransfer || !e.dataTransfer.files || !e.dataTransfer.files.length) return;
                e.preventDefault();
                dragCounter = 0;
                hide();

                const targetInput = _findActiveDropFileInput(e.clientX, e.clientY);
                if (!targetInput) {
                    titanAlert('لا يوجد حقل رفع ملفات في التبويب الحالي.');
                    return;
                }

                const file = e.dataTransfer.files[0];
                const ok = _assignDroppedFileToInput(targetInput, file);
                if (ok) titanAlert('✅ تم إرفاق الملف بالسحب والإفلات.');
                else titanAlert('تعذر إسناد الملف تلقائياً. استخدم زر اختيار الملف.');
            });
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
                    const shouldShow = (t === type);
                    sec.classList.toggle('hidden', !shouldShow);
                    if (shouldShow) _animateTabSection(sec);
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
            if(type === 'ctf' && typeof ctfLoadChallenges === 'function') ctfLoadChallenges(false);
            if(type === 'ir' && typeof irInitSection === 'function') irInitSection();
            if(type === 'forensics' && typeof forensicsInitSection === 'function') forensicsInitSection();
            if(type === 'se' && typeof seInitDefenseTab === 'function') seInitDefenseTab();
            if(type === 'admin' && typeof loadAdminSupportTickets === 'function') loadAdminSupportTickets();
            if(type === 'crypt' && typeof startCryptAdvisorChat === 'function') startCryptAdvisorChat(false);
            if(type === 'training') {
                setTrainingSubTab(__trainingSubTab || 'learninglab');
            }

            const activeBtn = document.getElementById('btn-' + type);
            if (activeBtn && typeof activeBtn.scrollIntoView === 'function') {
                activeBtn.scrollIntoView({behavior: 'smooth', inline: 'center', block: 'nearest'});
            }
        }

        function setTrainingSubTab(tab) {
            const next = TRAINING_SUB_TABS.includes(tab) ? tab : 'learninglab';
            __trainingSubTab = next;

            TRAINING_SUB_TABS.forEach((t) => {
                const sec = document.getElementById(t + '-section');
                if (sec) {
                    const visible = t === next;
                    sec.classList.toggle('hidden', !visible);
                    if (visible) _animateTabSection(sec);
                }

                const btn = document.getElementById('btn-training-' + t);
                if (btn) {
                    btn.classList.remove('training-subtab-active');
                    if (t === next) {
                        btn.classList.add('training-subtab-active');
                    }
                }
            });

            if (next === 'ctf' && typeof ctfLoadChallenges === 'function') ctfLoadChallenges(false);
            if (next === 'se' && typeof seInitDefenseTab === 'function') seInitDefenseTab();
            if (next === 'learninglab' && typeof learningInitCatalog === 'function') learningInitCatalog();
        }

        const LEARNING_ATTACK_CATALOG = [
            {
                id: 'web-attacks',
                title: 'هجمات تطبيقات الويب (Web Attacks)',
                items: [
                    { id: 'sqli', name: 'SQL Injection (SQLi)', how: 'يتم تمرير مدخلات غير منقاة داخل استعلام قاعدة البيانات، فيفسرها المحرك كأوامر SQL بدل بيانات عادية.', where: 'نماذج تسجيل الدخول، البحث، صفحات الاستعلام، وواجهات API التي تبني SQL ديناميكياً.', tools: ['Burp Suite', 'sqlmap', 'OWASP ZAP'], protection: ['استخدم Prepared Statements', 'طبّق Validation صارم للمدخلات', 'فعّل مبدأ أقل صلاحية لحسابات DB', 'راقب أخطاء SQL وأنماط الاستعلام الشاذة'] },
                    { id: 'xss', name: 'Cross-Site Scripting (XSS)', how: 'يُحقن JavaScript خبيث في الصفحة ويُنفذ داخل متصفح الضحية عند عرض المحتوى.', where: 'حقول التعليقات، الملفات الشخصية، رسائل الدعم، وأي مكان يعرض مدخلات المستخدم دون ترميز.', tools: ['Burp Suite', 'XSS Hunter', 'OWASP ZAP'], protection: ['ترميز المخرجات حسب السياق', 'فعّل Content Security Policy', 'امنع inline scripts قدر الإمكان', 'فلترة المدخلات الخطرة مع السماح الآمن'] },
                    { id: 'csrf', name: 'Cross-Site Request Forgery (CSRF)', how: 'يتم خداع المستخدم الموثق لإرسال طلب شرعي من متصفحه دون علمه.', where: 'عمليات تغيير كلمة المرور، التحويلات المالية، إعدادات الحساب، وطلبات POST الحساسة.', tools: ['Burp Suite', 'Browser DevTools', 'OWASP ZAP'], protection: ['CSRF Token لكل طلب حساس', 'استخدم SameSite Cookies', 'تحقق من Origin/Referer', 'أضف إعادة مصادقة للعمليات الحرجة'] },
                    { id: 'idor', name: 'Insecure Direct Object Reference (IDOR)', how: 'يتم تغيير معرف مورد (ID) للوصول إلى بيانات تخص مستخدم آخر لغياب التحقق المنطقي.', where: 'روابط profile/order/invoice ونقاط API التي تعتمد معرفات مباشرة.', tools: ['Burp Suite', 'Postman', 'OWASP ZAP'], protection: ['تحقق من الملكية Authorization لكل مورد', 'لا تعتمد على ID مكشوف فقط', 'استخدم معرفات غير قابلة للتخمين', 'اختبر BOLA في الـ API دورياً'] },
                    { id: 'broken-access', name: 'Broken Access Control', how: 'تطبيق الصلاحيات غير مكتمل أو متفرق، فيسمح بوصول غير مصرح به.', where: 'لوحات الإدارة، مسارات مخفية، وظائف premium، ونهايات API الداخلية.', tools: ['Burp Suite', 'OWASP ZAP', 'Nuclei'], protection: ['مركزة قرارات الصلاحيات في middleware واحد', 'اختبار صلاحيات على مستوى كل endpoint', 'تعطيل الوصول الافتراضي ومنح الصلاحية صراحة', 'مراجعة دورية للأدوار والـ RBAC'] },
                    { id: 'ssrf', name: 'Server-Side Request Forgery (SSRF)', how: 'يُجبر الخادم على إجراء طلبات إلى عناوين داخلية أو خدمات حساسة نيابة عن المهاجم.', where: 'خدمات سحب URL/preview/webhook/image fetch وعمليات التكامل الخارجية.', tools: ['Burp Suite', 'Interactsh/OAST', 'Caido'], protection: ['Allowlist للوجهات المسموح بها', 'حظر عناوين metadata/internal ranges', 'عزل الشبكة الداخلية عن خوادم الويب', 'فرض DNS resolution آمن مع منع إعادة التوجيه الخطر'] },
                    { id: 'dir-traversal', name: 'Directory Traversal', how: 'استغلال مسارات الملفات للوصول إلى ملفات خارج الدليل المسموح.', where: 'نقاط تحميل/عرض الملفات، download endpoints، وأي باراميتر path.', tools: ['Burp Suite', 'ffuf', 'OWASP ZAP'], protection: ['طبعنة المسار Canonicalization', 'استخدم معرفات ملفات لا مسارات مباشرة', 'حصر الوصول داخل مجلد آمن', 'تعطيل عرض ملفات النظام الحساسة'] },
                    { id: 'cmd-injection', name: 'Command Injection', how: 'مدخلات المستخدم تُمرر لأمر نظام تشغيل دون تعقيم فتسمح بتنفيذ أوامر إضافية.', where: 'وظائف ping/traceroute/convert/backup التي تستدعي shell.', tools: ['Burp Suite', 'Semgrep', 'SAST/DAST scanners'], protection: ['تجنب shell execution قدر الإمكان', 'استخدم APIs آمنة بدل shell', 'قيّد القيم عبر allowlist', 'تشغيل الخدمة بحساب محدود الصلاحية'] },
                    { id: 'xxe', name: 'XML External Entity (XXE)', how: 'معالج XML يسمح بكيانات خارجية فتُقرأ ملفات أو تُرسل طلبات داخلية.', where: 'SOAP APIs، XML upload، SSO/SAML parsers القديمة.', tools: ['Burp Suite', 'OWASP ZAP', 'xmllint for validation'], protection: ['تعطيل DTD وExternal Entities', 'التحول إلى JSON عند الإمكان', 'استخدام مكتبات parser آمنة', 'تحديث المكونات القديمة'] },
                    { id: 'file-inclusion', name: 'File Inclusion (LFI/RFI)', how: 'إدخال اسم ملف غير موثوق في include/require أو loader.', where: 'أنظمة القوالب، تحميل اللغات/themes، وباراميترات الصفحة الديناميكية.', tools: ['Burp Suite', 'Nuclei', 'OWASP ZAP'], protection: ['منع include بناءً على مدخل خارجي', 'Allowlist للملفات المسموح بها', 'عزل ملفات الإعدادات الحساسة', 'إغلاق remote include إن وجد'] }
                ]
            },
            {
                id: 'network-attacks',
                title: 'هجمات الشبكة والبنية التحتية (Network Attacks)',
                items: [
                    { id: 'ddos', name: 'DDoS', how: 'إغراق الخدمة بعدد ضخم من الطلبات من مصادر متعددة لتعطيل التوفر.', where: 'واجهات الويب العامة، DNS، APIs، وبوابات الشبكة.', tools: ['Botnet panels (malicious)', 'LOIC/HOIC (historical)', 'hping3'], protection: ['استخدم CDN/WAF وحماية DDoS', 'Rate limiting وtraffic shaping', 'Anycast وتوزيع جغرافي للخدمة', 'Runbooks للاستجابة السريعة'] },
                    { id: 'mitm', name: 'Man-in-the-Middle (MitM)', how: 'اعتراض أو تعديل الاتصال بين طرفين دون علمهما.', where: 'شبكات Wi-Fi عامة، شبكات داخلية غير مؤمنة، وصلات بدون TLS صحيح.', tools: ['Wireshark', 'Ettercap', 'Bettercap'], protection: ['TLS قوي مع certificate validation', 'HSTS وcertificate pinning', 'استخدام VPN موثوق', 'منع الشبكات غير الموثوقة'] },
                    { id: 'arp-spoof', name: 'ARP Spoofing', how: 'تزوير ردود ARP لربط IP البوابة بعنوان MAC المهاجم.', where: 'شبكات LAN المحلية غير المحمية.', tools: ['Ettercap', 'Bettercap', 'arpspoof'], protection: ['Dynamic ARP Inspection', 'Static ARP للأجهزة الحساسة', 'تقسيم الشبكة VLANs', 'مراقبة ARP anomalies'] },
                    { id: 'dns-spoof', name: 'DNS Spoofing / Poisoning', how: 'إرجاع سجلات DNS مزيفة لتوجيه المستخدم لخوادم خبيثة.', where: 'Resolvers غير مؤمنة، راوترات منزلية، وشبكات وسيطة.', tools: ['dnsspoof', 'Responder', 'Bettercap'], protection: ['فعّل DNSSEC', 'استخدم DoH/DoT من مزود موثوق', 'تأمين resolver الداخلي', 'مراقبة تغيّر سجلات DNS الحرجة'] },
                    { id: 'port-scan', name: 'Port Scanning', how: 'استكشاف المنافذ والخدمات المفتوحة لتحديد سطح الهجوم.', where: 'الخوادم العامة، الأجهزة الداخلية، وأجهزة الشبكة.', tools: ['Nmap', 'Masscan', 'Rustscan'], protection: ['إغلاق المنافذ غير الضرورية', 'تقسيم الشبكة وتقليل التعريض', 'جدران نارية بقواعد صريحة', 'كشف scanning عبر IDS'] },
                    { id: 'packet-sniff', name: 'Packet Sniffing', how: 'التقاط حزم الشبكة وتحليلها لاستخراج بيانات حساسة.', where: 'شبكات غير مشفرة أو عند وجود وصول إلى switch/span.', tools: ['Wireshark', 'tcpdump', 'TShark'], protection: ['تشفير النقل دائماً', '802.1X للشبكات الداخلية', 'عزل الشبكة الحساسة', 'كشف بطاقات promiscuous إن أمكن'] },
                    { id: 'evil-twin', name: 'Evil Twin', how: 'إنشاء نقطة Wi-Fi وهمية بنفس SSID لجذب الضحايا.', where: 'المقاهي، المكاتب، المطارات، والأماكن العامة.', tools: ['Airbase-ng', 'Wifiphisher', 'hostapd'], protection: ['تثقيف المستخدمين حول SSID المزيف', 'WPA2-Enterprise/WPA3', 'Certificate-based auth', 'منع الاتصال التلقائي بالشبكات المفتوحة'] },
                    { id: 'rogue-ap', name: 'Rogue Access Point', how: 'إدخال نقطة وصول غير مصرح بها داخل الشبكة المؤسسية.', where: 'المكاتب والفروع دون رقابة لاسلكية مركزية.', tools: ['Portable AP devices', 'Kismet', 'Acrylic Wi-Fi'], protection: ['Wireless NAC', 'اكتشاف Rogue AP باستمرار', 'إغلاق منافذ غير موثوقة', 'سياسة صارمة للأجهزة اللاسلكية'] },
                    { id: 'vlan-hopping', name: 'VLAN Hopping', how: 'استغلال إعدادات switching للوصول إلى VLAN غير مصرح بها.', where: 'بيئات سويتشات بإعداد trunk/native vlan غير آمن.', tools: ['Yersinia', 'Scapy', 'Switch testing suites'], protection: ['تعطيل DTP', 'تغيير native VLAN الافتراضية', 'Port security', 'فصل الإدارة عن شبكات المستخدمين'] },
                    { id: 'bgp-hijack', name: 'BGP Hijacking', how: 'إعلان مسارات BGP مضللة لإعادة توجيه أو إسقاط حركة الإنترنت.', where: 'مزودو الخدمة وشبكات الإنترنت بين الأنظمة المستقلة.', tools: ['BGP monitoring platforms', 'Route analysis tools', 'RIPE RIS/RouteViews'], protection: ['RPKI وRoute Origin Validation', 'تصفية الإعلانات بين AS', 'Monitoring لمسارات BGP', 'اتفاقيات تنسيق استجابة مع مزودي الخدمة'] }
                ]
            },
            {
                id: 'password-attacks',
                title: 'هجمات كلمات المرور (Password Attacks)',
                items: [
                    { id: 'bruteforce', name: 'Brute Force Attack', how: 'تجربة كم هائل من الاحتمالات حتى العثور على كلمة المرور الصحيحة.', where: 'بوابات تسجيل الدخول، VPN، SSH، ولوحات الإدارة.', tools: ['Hydra', 'Burp Intruder', 'Medusa'], protection: ['MFA إلزامي', 'Lockout ذكي بعد محاولات فاشلة', 'Rate limiting', 'كلمات مرور قوية مع مراقبة تسجيل الدخول'] },
                    { id: 'dictionary', name: 'Dictionary Attack', how: 'استخدام قوائم كلمات مرور شائعة بدل تجربة جميع الاحتمالات.', where: 'أنظمة لا تفرض تعقيد أو تستخدم كلمات مرور متوقعة.', tools: ['Hashcat', 'John the Ripper', 'Hydra'], protection: ['حظر كلمات المرور الشائعة', 'سياسة طول وتعقيد', 'فحص كلمة المرور أثناء الإنشاء', 'MFA'] },
                    { id: 'credential-stuffing', name: 'Credential Stuffing', how: 'استخدام بيانات اعتماد مسربة من موقع آخر لتسجيل الدخول في خدمات مختلفة.', where: 'المنصات الشعبية ذات قاعدة مستخدمين كبيرة.', tools: ['Sentry MBA (abuse)', 'OpenBullet (abuse)', 'Custom automation'], protection: ['MFA', 'كشف الأنماط الآلية والبوتات', 'فحص بيانات الاعتماد المسربة', 'تنبيه المستخدم عند نشاط غير معتاد'] },
                    { id: 'password-spraying', name: 'Password Spraying', how: 'تجربة كلمة شائعة واحدة على عدد كبير من الحسابات لتجنب قفل حساب واحد.', where: 'Active Directory وSSO portals.', tools: ['Spray tools', 'Kerbrute', 'Custom scripts'], protection: ['Smart lockout policies', 'MFA', 'مراقبة محاولات فشل موزعة', 'منع كلمات المرور القابلة للتخمين'] },
                    { id: 'rainbow-table', name: 'Rainbow Table Attack', how: 'مطابقة الـ hash مع جداول محسوبة مسبقاً لكلمات مرور معروفة.', where: 'قواعد بيانات مسربة تستخدم hashing ضعيف بلا salt.', tools: ['RainbowCrack', 'Hash lookup datasets', 'Offline cracking suites'], protection: ['Hashing قوي مثل Argon2/bcrypt/scrypt', 'Salt فريد لكل كلمة مرور', 'Pepper على مستوى الخادم', 'منع تخزين كلمات المرور بنص واضح'] }
                ]
            },
            {
                id: 'social-engineering',
                title: 'هجمات الهندسة الاجتماعية (Social Engineering)',
                items: [
                    { id: 'phishing', name: 'Phishing', how: 'رسائل مزورة تدفع الضحية للنقر أو إدخال بيانات حساسة.', where: 'البريد الإلكتروني، صفحات تسجيل مزيفة، وروابط مختصرة.', tools: ['Email spoofing kits', 'Typosquatting domains', 'Phishing simulation platforms'], protection: ['بوابة بريد آمنة', 'DMARC/SPF/DKIM', 'تدريب توعوي دوري', 'التحقق من الروابط قبل النقر'] },
                    { id: 'spear-phishing', name: 'Spear Phishing', how: 'تصيّد مخصص لشخص أو فريق بناءً على معلومات دقيقة عنه.', where: 'الموظفون ذوو الصلاحيات، المالية، الموارد البشرية، الإدارة.', tools: ['OSINT tooling', 'Email crafting suites', 'Social profiling tools'], protection: ['توعية موجهة للأدوار الحساسة', 'إجراءات تحقق إضافية للطلبات الحرجة', 'تقليل المعلومات العلنية عن الموظفين', 'مراجعة ثنائية للعمليات المالية'] },
                    { id: 'vishing', name: 'Vishing', how: 'اتصال هاتفي انتحالي لانتزاع OTP أو بيانات دخول أو تحويلات.', where: 'خدمة العملاء، فرق الدعم، والموظفين الجدد.', tools: ['Caller ID spoofing', 'VoIP automation', 'Social scripts'], protection: ['سياسة عدم مشاركة OTP نهائياً', 'Call-back verification', 'توثيق إجراءات الدعم', 'تدريب على التحقق الصوتي'] },
                    { id: 'smishing', name: 'Smishing', how: 'رسائل SMS مزيفة تتضمن روابط أو طلبات عاجلة خادعة.', where: 'هواتف الموظفين والعملاء، حملات بنوك وشحن وهمية.', tools: ['SMS gateways (abuse)', 'Short-link cloaking', 'Fraud kits'], protection: ['حظر روابط SMS غير الموثوقة', 'بوابات حماية للهاتف المؤسسي', 'توعية المستخدمين', 'قنوات تواصل رسمية موحدة'] },
                    { id: 'whaling', name: 'Whaling', how: 'استهداف القيادات التنفيذية برسائل عالية الإقناع (مثل BEC).', where: 'حسابات C-level، الإدارة المالية، التعاقدات.', tools: ['Business email impersonation', 'Deep reconnaissance', 'Lookalike domains'], protection: ['تدقيق مالي متعدد المستويات', 'MFA وحماية البريد التنفيذي', 'تحقق خارج القناة للمدفوعات', 'تنبيهات قوية على قواعد البريد'] },
                    { id: 'baiting', name: 'Baiting', how: 'إغراء الضحية بوسيط مغرٍ (USB/ملف مجاني) يحوي حمولة خبيثة.', where: 'مواقف السيارات، المكاتب، ومشاركة ملفات غير موثوقة.', tools: ['USB drop techniques', 'Malicious media payloads', 'Social lure content'], protection: ['تعطيل AutoRun', 'حظر وسائط USB غير المعتمدة', 'EDR على endpoints', 'حملات توعية واقعية'] },
                    { id: 'pretexting', name: 'Pretexting', how: 'بناء قصة مصدّقة للحصول على معلومات حساسة أو تنفيذ طلب.', where: 'مكالمات الدعم، طلبات الموارد البشرية، والتحقق من الهوية.', tools: ['Identity spoofing', 'Scripted conversation playbooks', 'Profile harvesting'], protection: ['إجراءات تحقق هوية متعددة', 'مبدأ أقل معرفة للبيانات', 'توثيق جميع طلبات المعلومات الحساسة', 'توعية الموظفين ضد الثقة العاطفية'] }
                ]
            },
            {
                id: 'malware',
                title: 'البرمجيات الخبيثة (Malware)',
                items: [
                    { id: 'ransomware', name: 'Ransomware', how: 'تشفير بيانات الضحية ثم طلب فدية مقابل مفتاح فك التشفير.', where: 'أجهزة المستخدمين، خوادم الملفات، والنسخ المشتركة.', tools: ['Ransomware families', 'Initial access brokers', 'Command-and-control infrastructure'], protection: ['نسخ احتياطية معزولة ومجربة', 'EDR + segmentation', 'إدارة ترقيعات قوية', 'خطة IR واختبارات تعافي'] },
                    { id: 'trojan', name: 'Trojan Horse', how: 'برنامج يبدو شرعياً لكنه ينفذ سلوكاً خبيثاً في الخلفية.', where: 'مرفقات البريد، البرامج المقرصنة، installers المقلدة.', tools: ['Packers', 'Dropper frameworks', 'Remote access malware'], protection: ['Application allowlisting', 'تنزيل البرامج من مصادر موثوقة', 'فحص سلوكي للملفات', 'تقييد صلاحيات المستخدم'] },
                    { id: 'spyware', name: 'Spyware', how: 'يجمع نشاط المستخدم وبياناته ويرسلها خفية لمهاجم.', where: 'أنظمة تشغيل غير محدثة، تطبيقات مجهولة، إضافات متصفح مشبوهة.', tools: ['Infostealer families', 'Browser data grabbers', 'Persistence modules'], protection: ['مكافحة برمجيات خبيثة حديثة', 'تحديث دائم للأنظمة', 'مراقبة outbound traffic', 'تقليل تثبيت البرامج غير المعتمدة'] },
                    { id: 'keylogger', name: 'Keyloggers', how: 'تسجيل ضغطات لوحة المفاتيح لسرقة كلمات المرور والبيانات الحساسة.', where: 'أجهزة endpoint المخترقة أو عبر ملحقات hardware.', tools: ['Software keyloggers', 'USB hardware loggers', 'RAT plugins'], protection: ['MFA يقلل ضرر التسريب', 'EDR ورقابة kernel hooks', 'فحص مادي للأجهزة الحساسة', 'لوحات مفاتيح افتراضية للحالات الحرجة'] },
                    { id: 'rootkit', name: 'Rootkits', how: 'إخفاء مكونات خبيثة عميقاً داخل النظام لضمان بقاء طويل الأمد.', where: 'Kernel/boot layers على أجهزة ذات حماية ضعيفة.', tools: ['Kernel-mode rootkits', 'Bootkits', 'Persistence toolsets'], protection: ['Secure Boot', 'قياسات سلامة النظام', 'Re-image للأجهزة المصابة', 'تحديثات kernel والبرامج الثابتة'] },
                    { id: 'adware', name: 'Adware', how: 'حقن إعلانات مزعجة وتتبع سلوك المستخدم لتحقيق ربح غير مشروع.', where: 'متصفحات المستخدمين، تطبيقات مجانية غير موثوقة.', tools: ['Browser hijackers', 'Bundled installers', 'Ad injection SDK abuse'], protection: ['حظر الإضافات غير الموثوقة', 'Application control', 'تنظيف دوري للمتصفحات', 'توعية المستخدم قبل التثبيت'] },
                    { id: 'botnet', name: 'Botnets', how: 'تحويل الأجهزة المصابة إلى شبكة روبوتات تنفذ أوامر مركزية.', where: 'IoT، endpoints، خوادم مكشوفة وضعيفة.', tools: ['C2 frameworks', 'Malware loaders', 'Propagation scripts'], protection: ['تقسيم الشبكة', 'تغيير كلمات المرور الافتراضية للأجهزة', 'مراقبة سلوك beaconing', 'تعطيل الخدمات غير اللازمة'] },
                    { id: 'fileless', name: 'Fileless Malware', how: 'تنفيذ الحمولة في الذاكرة باستخدام أدوات النظام الشرعية لتفادي الكشف التقليدي.', where: 'Windows endpoints عبر scripting engines والعمليات الداخلية.', tools: ['PowerShell abuse', 'WMI abuse', 'In-memory loaders'], protection: ['EDR سلوكي', 'تقييد scripting policies', 'حماية AMSI', 'مراقبة العمليات غير الطبيعية'] }
                ]
            },
            {
                id: 'advanced-technical',
                title: 'هجمات متقدمة وثغرات تقنية (Advanced & Technical)',
                items: [
                    { id: 'zero-day', name: 'Zero-Day Exploit', how: 'استغلال ثغرة غير معروفة للمطور قبل توفر تصحيح رسمي.', where: 'المتصفحات، الأنظمة، منتجات المؤسسات، وسلاسل البرمجيات.', tools: ['Exploit brokers ecosystems', 'Advanced exploit frameworks', 'Vulnerability research tooling'], protection: ['Defense in depth', 'EDR/XDR', 'virtual patching عبر WAF/IPS', 'استجابة سريعة وتجزئة بيئة الإنتاج'] },
                    { id: 'buffer-overflow', name: 'Buffer Overflow', how: 'كتابة بيانات أكثر من سعة الذاكرة المخصصة مما يغير مسار التنفيذ.', where: 'برمجيات C/C++ غير المحمية، خدمات شبكية قديمة.', tools: ['Fuzzers', 'Debugger suites', 'Static analyzers'], protection: ['استخدام لغات/مكتبات آمنة', 'Compiler protections مثل ASLR/DEP/Canaries', 'اختبارات fuzzing دورية', 'مراجعة ذاكرة دقيقة'] },
                    { id: 'supply-chain', name: 'Supply Chain Attack', how: 'اختراق مورد أو مكتبة موثوقة للوصول لعدد كبير من الضحايا عبر التحديثات.', where: 'مستودعات الحزم، CI/CD، تحديثات الموردين.', tools: ['Dependency confusion techniques', 'Typosquatting packages', 'Build pipeline abuse'], protection: ['SBOM', 'توقيع الحزم والتحقق منها', 'قفل الإصدارات واعتماد registry موثوق', 'مراقبة سلوك التحديثات'] },
                    { id: 'side-channel', name: 'Side-Channel Attack', how: 'استنتاج معلومات حساسة عبر قياسات جانبية مثل الزمن أو الطاقة أو الإشعاع.', where: 'أجهزة مشفرة، شرائح، بيئات متعددة المستأجرين.', tools: ['Timing analysis tooling', 'Power analysis labs', 'Hardware probes'], protection: ['خوارزميات constant-time', 'عزل فيزيائي عند الحاجة', 'تقليل تسريبات التوقيت', 'تدقيق أمني للأجهزة عالية الحساسية'] },
                    { id: 'cryptojacking', name: 'Cryptojacking', how: 'استغلال قدرة المعالجة لتعدين العملات دون موافقة المستخدم.', where: 'خوادم مخترقة، متصفحات، حاويات Cloud.', tools: ['Mining malware', 'Browser mining scripts', 'Cloud abuse automation'], protection: ['مراقبة CPU/GPU anomalies', 'حظر mining domains/signatures', 'تقوية cloud IAM', 'تنبيهات استهلاك موارد غير طبيعي'] },
                    { id: 'api-hacking', name: 'API Hacking', how: 'استغلال ضعف التوثيق أو التحقق أو الصلاحيات في واجهات API.', where: 'REST/GraphQL endpoints خاصة mobile وmicroservices.', tools: ['Postman', 'Burp Suite', 'OWASP ZAP'], protection: ['OAuth/JWT مضبوط', 'Rate limiting', 'BOLA/BFLA testing', 'Schema validation وlogging شامل'] },
                    { id: 'sim-swapping', name: 'SIM Swapping', how: 'نقل رقم الضحية إلى شريحة المهاجم للاستحواذ على OTP والرسائل.', where: 'حسابات تعتمد SMS MFA فقط.', tools: ['Social engineering against carrier', 'Identity fraud kits', 'Account takeover workflows'], protection: ['استخدام MFA غير SMS', 'PIN لدى شركة الاتصالات', 'تنبيهات فورية لتغيير الشريحة', 'تأمين الحسابات بقنوات بديلة'] },
                    { id: 'replay', name: 'Replay Attack', how: 'إعادة إرسال رسالة/رمز صحيح التقط مسبقاً لخداع النظام وتنفيذ نفس العملية.', where: 'بروتوكولات مصادقة ضعيفة، APIs بلا nonce/timestamp.', tools: ['Traffic capture tools', 'Proxy repeaters', 'Custom replayers'], protection: ['Nonce وTimestamp', 'Session binding', 'توقيع الطلبات', 'رفض الطلبات المكررة'] },
                    { id: 'exploit-kits', name: 'Exploit Kits', how: 'منصات جاهزة تستهدف ثغرات المتصفح/الملحقات تلقائياً عند زيارة صفحة مصابة.', where: 'إعلانات مخترقة، مواقع مصابة، صفحات redirect خبيثة.', tools: ['Exploit kit frameworks', 'Drive-by delivery chains', 'Malvertising infrastructure'], protection: ['تحديث المتصفح والإضافات', 'Ad/script blocking policies', 'Network filtering', 'عزل المتصفح في بيئات حساسة'] },
                    { id: 'bluetooth', name: 'Bluejacking / Bluesnarfing', how: 'استغلال إعدادات أو ثغرات Bluetooth للوصول إلى بيانات أو إرسال محتوى غير مرغوب.', where: 'هواتف وأجهزة قريبة مع بلوتوث مكشوف أو إعدادات ضعيفة.', tools: ['Bluetooth scanners', 'BlueZ utilities', 'Specialized RF toolkits'], protection: ['إخفاء الجهاز وإيقاف discoverability', 'تحديث firmware', 'اقتران آمن برمز قوي', 'تعطيل Bluetooth عند عدم الحاجة'] }
                ]
            }
        ];

        let __learningCatalogReady = false;
        let __learningSelectedAttackId = '';

        const LEARNING_SEVERITY_BY_ATTACK = {
            'sqli': 'high', 'xss': 'high', 'csrf': 'medium', 'idor': 'high', 'broken-access': 'critical',
            'ssrf': 'critical', 'dir-traversal': 'high', 'cmd-injection': 'critical', 'xxe': 'high', 'file-inclusion': 'high',
            'ddos': 'high', 'mitm': 'high', 'arp-spoof': 'medium', 'dns-spoof': 'high', 'port-scan': 'medium',
            'packet-sniff': 'high', 'evil-twin': 'high', 'rogue-ap': 'high', 'vlan-hopping': 'high', 'bgp-hijack': 'critical',
            'bruteforce': 'medium', 'dictionary': 'medium', 'credential-stuffing': 'high', 'password-spraying': 'high', 'rainbow-table': 'high',
            'phishing': 'high', 'spear-phishing': 'high', 'vishing': 'medium', 'smishing': 'medium', 'whaling': 'critical', 'baiting': 'medium', 'pretexting': 'medium',
            'ransomware': 'critical', 'trojan': 'high', 'spyware': 'high', 'keylogger': 'high', 'rootkit': 'critical', 'adware': 'medium', 'botnet': 'critical', 'fileless': 'critical',
            'zero-day': 'critical', 'buffer-overflow': 'high', 'supply-chain': 'critical', 'side-channel': 'high', 'cryptojacking': 'medium',
            'api-hacking': 'high', 'sim-swapping': 'high', 'replay': 'medium', 'exploit-kits': 'high', 'bluetooth': 'medium'
        };

        function _learningSeverityMeta(level) {
            const key = String(level || 'medium').toLowerCase();
            if (key === 'critical') return { label: 'Critical', cls: 'text-rose-200 border-rose-700/60 bg-rose-900/30' };
            if (key === 'high') return { label: 'High', cls: 'text-orange-200 border-orange-700/60 bg-orange-900/30' };
            if (key === 'low') return { label: 'Low', cls: 'text-emerald-200 border-emerald-700/60 bg-emerald-900/30' };
            return { label: 'Medium', cls: 'text-amber-200 border-amber-700/60 bg-amber-900/30' };
        }

        function _learningBuildPlaybook(item) {
            const attackName = String(item?.name || 'الهجمة');
            const category = String(item?.category_id || 'general');

            const base = {
                detect: [
                    `مراقبة سجلات النظام بحثاً عن أنماط مرتبطة بـ ${attackName}.`,
                    'إعداد تنبيه SIEM عند ظهور مؤشرات سلوك غير طبيعي.',
                    'ربط التنبيهات مع سياق المستخدم/الجهاز/التطبيق لتقليل الإنذارات الكاذبة.'
                ],
                contain: [
                    `عزل الأصل المتأثر فوراً عند الاشتباه بنشاط ${attackName}.`,
                    'تعطيل الجلسات والتوكنات النشطة للحسابات المتأثرة.',
                    'تفعيل قواعد WAF/Firewall أو ACLs مؤقتة لوقف الانتشار.'
                ],
                respond: [
                    'جمع الأدلة الرقمية (Logs, Timeline, IOCs) وتوثيقها.',
                    'تنفيذ خطة الاستجابة حسب الأولوية وتأثير الأعمال.',
                    'إبلاغ أصحاب المصلحة وتحديث حالة الحادث بشكل دوري.'
                ],
                harden: [
                    `إغلاق السبب الجذري الذي سمح بحدوث ${attackName}.`,
                    'تحديث الضوابط الوقائية وكشف الفجوات في playbook.',
                    'إعادة اختبار البيئة بعد الإصلاح وتحديث الدروس المستفادة.'
                ]
            };

            if (category === 'web-attacks') {
                base.detect.unshift('مراقبة WAF وHTTP logs بحثاً عن payload patterns غير اعتيادية.');
                base.harden.unshift('فرض Secure SDLC مع SAST/DAST وCode Review أمني قبل النشر.');
            } else if (category === 'network-attacks') {
                base.detect.unshift('تحليل NetFlow/IDS لاكتشاف spikes أو lateral movement مبكر.');
                base.harden.unshift('تقسيم الشبكة وتطبيق Zero Trust بين المقاطع الداخلية.');
            } else if (category === 'password-attacks') {
                base.detect.unshift('مراقبة محاولات تسجيل دخول فاشلة موزعة زمنياً وجغرافياً.');
                base.harden.unshift('فرض MFA وسياسات كلمات مرور مقاومة للهجمات الآلية.');
            } else if (category === 'social-engineering') {
                base.detect.unshift('تفعيل تدقيق رسائل البريد والرسائل النصية المشبوهة داخلياً.');
                base.harden.unshift('تشغيل برامج توعية دورية ومحاكاة تصيد مع قياس الأداء.');
            } else if (category === 'malware') {
                base.detect.unshift('مراقبة سلوك endpoint (process injection, persistence, C2 beaconing).');
                base.harden.unshift('تعزيز EDR ونسخ احتياطي معزول ومختبر بشكل دوري.');
            } else if (category === 'advanced-technical') {
                base.detect.unshift('استخدام Threat Intelligence ومراقبة استباقية للمؤشرات المتقدمة.');
                base.harden.unshift('تطبيق Defense-in-Depth وpatch governance صارم للمكونات الحرجة.');
            }

            return base;
        }

        function _learningAllAttacks() {
            const rows = [];
            LEARNING_ATTACK_CATALOG.forEach((cat) => {
                (cat.items || []).forEach((item) => {
                    const severity = LEARNING_SEVERITY_BY_ATTACK[item.id] || 'medium';
                    rows.push({
                        ...item,
                        category_id: cat.id,
                        category_title: cat.title,
                        severity,
                        playbook: _learningBuildPlaybook({ ...item, category_id: cat.id })
                    });
                });
            });
            return rows;
        }

        function _learningRenderStats(filtered, total) {
            const box = document.getElementById('learningCatalogStats');
            if (!box) return;
            const families = new Set((filtered || []).map((x) => x.category_id)).size;
            const critical = (filtered || []).filter((x) => String(x.severity) === 'critical').length;
            box.innerHTML = `
                <span class="text-cyan-300 font-bold">نتائج العرض: ${_resultEscape(filtered.length)}</span>
                <span class="text-gray-500"> / ${_resultEscape(total)} هجمة</span>
                <span class="mx-2 text-gray-600">|</span>
                <span class="text-fuchsia-300 font-bold">العائلات الظاهرة: ${_resultEscape(families)}</span>
                <span class="mx-2 text-gray-600">|</span>
                <span class="text-rose-300 font-bold">Critical: ${_resultEscape(critical)}</span>
            `;
        }

        function _learningRenderAttackCards(attacks) {
            const box = document.getElementById('learningAttackCards');
            if (!box) return;
            if (!attacks.length) {
                box.innerHTML = '<div class="text-xs text-gray-500 p-3 rounded border border-slate-700 bg-black/30">لا توجد نتائج مطابقة للفلتر الحالي.</div>';
                return;
            }

            box.innerHTML = attacks.map((a) => {
                const active = a.id === __learningSelectedAttackId;
                const sev = _learningSeverityMeta(a.severity);
                return `<button onclick="learningCatalogOpen('${_resultEscape(a.id)}')" class="text-right p-3 rounded-lg border transition-all ${active ? 'border-cyan-600 bg-cyan-900/20' : 'border-slate-700 bg-black/30 hover:border-cyan-800/60 hover:bg-cyan-950/10'}">
                    <div class="flex items-center justify-between gap-2">
                        <div class="text-xs font-bold ${active ? 'text-cyan-200' : 'text-gray-100'}">${_resultEscape(a.name)}</div>
                        <span class="text-[10px] px-2 py-0.5 rounded border ${sev.cls}">${_resultEscape(sev.label)}</span>
                    </div>
                    <div class="text-[10px] text-gray-400 mt-1">${_resultEscape(a.category_title)}</div>
                    <div class="text-[10px] text-gray-500 mt-1">Tools: ${_resultEscape((a.tools || []).slice(0, 3).join(' | '))}</div>
                </button>`;
            }).join('');
        }

        function _learningRenderListItems(items, toneCls, emptyText) {
            const rows = Array.isArray(items) ? items.filter(Boolean) : [];
            if (!rows.length) return `<div class="text-[11px] text-gray-500">${_resultEscape(emptyText)}</div>`;
            return rows.map((x) => `<div class="text-[11px] ${toneCls}">• ${_resultEscape(x)}</div>`).join('');
        }

        function learningCatalogOpen(attackId) {
            const all = _learningAllAttacks();
            const hit = all.find((x) => x.id === attackId);
            const box = document.getElementById('learningAttackDetail');
            const badge = document.getElementById('learningSelectedAttackBadge');
            if (!hit || !box) return;

            __learningSelectedAttackId = hit.id;
            if (badge) badge.textContent = hit.name;
            const sev = _learningSeverityMeta(hit.severity);
            const playbook = hit.playbook || {};

            box.innerHTML = `
                <div class="space-y-3">
                    <div class="rounded-lg border border-indigo-800/40 bg-indigo-950/20 p-3">
                        <div class="flex items-center justify-between gap-2">
                            <div class="text-sm font-bold text-indigo-200">${_resultEscape(hit.name)}</div>
                            <span class="text-[10px] px-2 py-0.5 rounded border ${sev.cls}">${_resultEscape(sev.label)}</span>
                        </div>
                        <div class="text-[11px] text-indigo-300 mt-1">${_resultEscape(hit.category_title)}</div>
                    </div>

                    <div class="rounded-lg border border-slate-700 bg-black/30 p-3">
                        <div class="text-[11px] font-bold text-cyan-300 mb-1">كيف بتصير؟</div>
                        <div class="text-[11px] text-gray-200 leading-6">${_resultEscape(hit.how)}</div>
                    </div>

                    <div class="rounded-lg border border-slate-700 bg-black/30 p-3">
                        <div class="text-[11px] font-bold text-amber-300 mb-1">وين بتصير؟</div>
                        <div class="text-[11px] text-gray-200 leading-6">${_resultEscape(hit.where)}</div>
                    </div>

                    <div class="rounded-lg border border-slate-700 bg-black/30 p-3">
                        <div class="text-[11px] font-bold text-fuchsia-300 mb-1">أشهر الأدوات المستخدمة فيها</div>
                        <div class="space-y-1">${_learningRenderListItems(hit.tools, 'text-fuchsia-100', 'لا توجد أدوات')}</div>
                    </div>

                    <div class="rounded-lg border border-slate-700 bg-black/30 p-3">
                        <div class="text-[11px] font-bold text-emerald-300 mb-1">إجراءات الحماية منها</div>
                        <div class="space-y-1">${_learningRenderListItems(hit.protection, 'text-emerald-100', 'لا توجد إجراءات')}</div>
                    </div>

                    <div class="rounded-lg border border-slate-700 bg-black/30 p-3">
                        <div class="text-[11px] font-bold text-violet-300 mb-2">Defensive Playbook عملي (مرتبط بهذه الهجمة)</div>
                        <div class="grid grid-cols-1 gap-2">
                            <div class="p-2 rounded border border-slate-700 bg-slate-900/50">
                                <div class="text-[10px] font-bold text-cyan-300 mb-1">1) Detect</div>
                                <div class="space-y-1">${_learningRenderListItems(playbook.detect, 'text-cyan-100', 'N/A')}</div>
                            </div>
                            <div class="p-2 rounded border border-slate-700 bg-slate-900/50">
                                <div class="text-[10px] font-bold text-amber-300 mb-1">2) Contain</div>
                                <div class="space-y-1">${_learningRenderListItems(playbook.contain, 'text-amber-100', 'N/A')}</div>
                            </div>
                            <div class="p-2 rounded border border-slate-700 bg-slate-900/50">
                                <div class="text-[10px] font-bold text-fuchsia-300 mb-1">3) Respond</div>
                                <div class="space-y-1">${_learningRenderListItems(playbook.respond, 'text-fuchsia-100', 'N/A')}</div>
                            </div>
                            <div class="p-2 rounded border border-slate-700 bg-slate-900/50">
                                <div class="text-[10px] font-bold text-emerald-300 mb-1">4) Harden</div>
                                <div class="space-y-1">${_learningRenderListItems(playbook.harden, 'text-emerald-100', 'N/A')}</div>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            learningCatalogApplyFilters(true);
        }

        function learningCatalogApplyFilters(skipDetailRefresh) {
            const query = String(document.getElementById('learningSearchInput')?.value || '').trim().toLowerCase();
            const category = String(document.getElementById('learningCategoryFilter')?.value || 'all');
            const severity = String(document.getElementById('learningSeverityFilter')?.value || 'all').toLowerCase();
            const all = _learningAllAttacks();
            const filtered = all.filter((a) => {
                if (category !== 'all' && a.category_id !== category) return false;
                if (severity !== 'all' && String(a.severity || '').toLowerCase() !== severity) return false;
                if (!query) return true;
                const play = a.playbook || {};
                const hay = [
                    a.name,
                    a.how,
                    a.where,
                    a.category_title,
                    a.severity,
                    ...(a.tools || []),
                    ...(a.protection || []),
                    ...(play.detect || []),
                    ...(play.contain || []),
                    ...(play.respond || []),
                    ...(play.harden || [])
                ].join(' ').toLowerCase();
                return hay.includes(query);
            });

            _learningRenderStats(filtered, all.length);
            _learningRenderAttackCards(filtered);

            if (skipDetailRefresh) return;
            if (!filtered.length) {
                const detail = document.getElementById('learningAttackDetail');
                const badge = document.getElementById('learningSelectedAttackBadge');
                if (detail) detail.innerHTML = 'لا توجد نتائج حالياً. جرّب تغيير البحث أو التصنيف.';
                if (badge) badge.textContent = 'لا نتائج';
                return;
            }

            const stillVisible = filtered.some((x) => x.id === __learningSelectedAttackId);
            if (!stillVisible) {
                learningCatalogOpen(filtered[0].id);
            }
        }

        function learningCatalogResetFilters() {
            const q = document.getElementById('learningSearchInput');
            const c = document.getElementById('learningCategoryFilter');
            const s = document.getElementById('learningSeverityFilter');
            if (q) q.value = '';
            if (c) c.value = 'all';
            if (s) s.value = 'all';
            learningCatalogApplyFilters(false);
        }

        function learningInitCatalog() {
            if (__learningCatalogReady) {
                learningCatalogApplyFilters(false);
                return;
            }

            const categorySelect = document.getElementById('learningCategoryFilter');
            const severitySelect = document.getElementById('learningSeverityFilter');
            if (categorySelect) {
                categorySelect.innerHTML = '<option value="all">كل العائلات</option>' + LEARNING_ATTACK_CATALOG.map((c) => `<option value="${_resultEscape(c.id)}">${_resultEscape(c.title)}</option>`).join('');
            }
            if (severitySelect) {
                severitySelect.innerHTML = [
                    '<option value="all">كل مستويات الخطورة</option>',
                    '<option value="critical">Critical</option>',
                    '<option value="high">High</option>',
                    '<option value="medium">Medium</option>',
                    '<option value="low">Low</option>'
                ].join('');
            }

            __learningCatalogReady = true;
            learningCatalogApplyFilters(false);
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
                '#phoneResult',
                '#urlResult',
                '#phishResult',
                '#leakEmailPassResult'
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
            const method = document.getElementById('cryptMethod')?.value || 'fernet';
            const kdfProfile = document.getElementById('cryptKdfProfile')?.value || 'strong';
            const outputFormat = document.getElementById('cryptOutputFormat')?.value || 'b64';
            if(!text || !key) return titanAlert("يرجى إدخال النص وكلمة السر!");
            if (action === 'encrypt' && method === 'xor-stream') {
                const ok = window.confirm('تحذير: XOR Stream ضعيف وغير مناسب للبيانات الحساسة. هل تريد الاستمرار؟');
                if (!ok) return;
            }
            const res = await fetch('/crypt-text', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({
                    text,
                    key,
                    action,
                    method,
                    options: {
                        kdf_profile: kdfProfile,
                        output_format: outputFormat
                    }
                })
            });
            const data = await res.json();
            if(data.error) titanAlert(data.error); else document.getElementById('cryptText').value = data.result;
        }

        function _cryptAdvisorRenderBubble(role, text) {
            const flow = document.getElementById('cryptAiChatFlow');
            if (!flow) return;
            const row = document.createElement('div');
            if (role === 'assistant') {
                row.className = 'flex justify-start items-end gap-2';
                row.innerHTML = '<div class="w-6 h-6 rounded-full bg-cyan-900/50 border border-cyan-700/50 flex items-center justify-center text-[10px]">🤖</div>' +
                    '<div class="bg-slate-800/90 text-gray-100 px-3 py-2 rounded-xl rounded-bl-md max-w-[84%] text-xs border border-slate-700/60 leading-6">' + renderAiReplyPretty(text) + '</div>';
            } else {
                row.className = 'flex justify-end items-end gap-2';
                row.innerHTML = '<div class="bg-cyan-700/60 text-white px-3 py-2 rounded-xl rounded-br-md max-w-[82%] text-xs border border-cyan-600/50">' +
                    _osintEscape(String(text || '')).replace(/\\n/g, '<br>') +
                    '</div><div class="w-6 h-6 rounded-full bg-cyan-900/40 border border-cyan-700/40 flex items-center justify-center text-[10px]">👤</div>';
            }
            flow.appendChild(row);
            flow.scrollTop = flow.scrollHeight;
        }

        function _cryptAdvisorRenderRecommendationMeta(rec, source) {
            const metaEl = document.getElementById('cryptAdvisorLastConfig');
            const badge = document.getElementById('cryptAiSourceBadge');
            if (badge) {
                const src = String(source || 'ai').toLowerCase();
                if (src === 'fallback') {
                    badge.textContent = 'AI: TITAN (Fallback)';
                    badge.className = 'text-[10px] px-2 py-1 rounded border border-amber-800/50 bg-amber-900/20 text-amber-300 font-bold';
                } else {
                    badge.textContent = 'AI: TITAN';
                    badge.className = 'text-[10px] px-2 py-1 rounded border border-cyan-800/50 bg-cyan-900/20 text-cyan-300 font-bold';
                }
            }

            if (!metaEl) return;
            if (!rec || !rec.method) {
                metaEl.textContent = 'لا توجد توصية مطبقة بعد.';
                return;
            }

            const reason = rec.reason ? (' | السبب: ' + rec.reason) : '';
            metaEl.textContent = 'آخر توصية: ' + rec.method + ' / ' + (rec.kdf_profile || 'strong') + ' / ' + (rec.output_format || 'b64') + reason;
        }

        function startCryptAdvisorChat(reset) {
            const flow = document.getElementById('cryptAiChatFlow');
            if (!flow) return;

            if (reset || !window.__cryptAiStarted) {
                window.__cryptAdvisorConversationId = null;
                window.__cryptAiStarted = true;
                window.__cryptRec = null;
                flow.innerHTML = '';
                const sensitivity = document.getElementById('cryptSensitivity')?.value || 'high';
                const purpose = (document.getElementById('cryptPurpose')?.value || '').trim() || 'عام';
                _cryptAdvisorRenderBubble('assistant',
                    'أنا TITAN AI داخل Crypto Studio. اكتب سيناريو الاستخدام وسأعطيك أفضل إعداد متاح داخل المنصة.\\n' +
                    'الحساسية الحالية: ' + sensitivity + ' | الغرض: ' + purpose + '\\n' +
                    'بعد كل رد، أقدر أطبق الإعدادات تلقائيًا على خيارات التشفير.'
                );
                _cryptAdvisorRenderRecommendationMeta(null, 'ai');
            }
        }

        async function sendCryptAdvisorMessage() {
            const input = document.getElementById('cryptAiChatInput');
            const btn = document.getElementById('cryptAiSendBtn');
            const audience = (document.getElementById('cryptAudience')?.value || '').trim();
            const sensitivity = document.getElementById('cryptSensitivity')?.value || 'high';
            const purpose = (document.getElementById('cryptPurpose')?.value || '').trim();
            const message = (input?.value || '').trim();

            if (!message) return;
            if (!window.__cryptAiStarted) startCryptAdvisorChat(false);

            _cryptAdvisorRenderBubble('user', message);
            input.value = '';
            if (btn) { btn.disabled = true; btn.textContent = '...'; }

            try {
                const res = await fetch('/api/crypt/recommend/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        message,
                        conversation_id: window.__cryptAdvisorConversationId,
                        context: { audience, sensitivity, purpose }
                    })
                });
                const data = await res.json();
                if (!res.ok || !data.success) throw new Error(data.error || 'تعذر فتح الدردشة');

                window.__cryptAdvisorConversationId = data.conversation_id || window.__cryptAdvisorConversationId;
                window.__cryptRec = data.recommendation || null;
                _cryptAdvisorRenderBubble('assistant', data.reply || 'تم توليد توصية.');
                _cryptAdvisorRenderRecommendationMeta(window.__cryptRec, data.source || 'ai');

                const rec = window.__cryptRec || {};
                const method = document.getElementById('cryptMethod');
                const kdf = document.getElementById('cryptKdfProfile');
                const out = document.getElementById('cryptOutputFormat');
                if (method && rec.method) method.value = rec.method;
                if (kdf && rec.kdf_profile) kdf.value = rec.kdf_profile;
                if (out && rec.output_format) out.value = rec.output_format;
            } catch (e) {
                _cryptAdvisorRenderBubble('assistant', 'تعذر فتح الدردشة الآن. ' + ((e && e.message) ? e.message : ''));
            } finally {
                if (btn) { btn.disabled = false; btn.textContent = 'إرسال'; }
            }
        }

        function applyCryptRecommendation() {
            const rec = window.__cryptRec || {};
            if (!rec || !rec.method) return titanAlert('لا يوجد اقتراح جاهز حالياً.');
            const method = document.getElementById('cryptMethod');
            const kdf = document.getElementById('cryptKdfProfile');
            const out = document.getElementById('cryptOutputFormat');
            if (method) method.value = rec.method;
            if (kdf) kdf.value = rec.kdf_profile || 'strong';
            if (out) out.value = rec.output_format || 'b64';
            _cryptAdvisorRenderRecommendationMeta(rec, 'ai');
            titanAlert('تم تطبيق الاقتراح الذكي ✅', 'success');
        }

        async function copyCryptText() {
            const val = (document.getElementById('cryptText')?.value || '').trim();
            if (!val) return titanAlert('لا يوجد نص لنسخه.');
            try {
                await navigator.clipboard.writeText(val);
                titanAlert('تم نسخ النص ✅', 'success');
            } catch (e) {
                titanAlert('تعذر النسخ تلقائياً.');
            }
        }

        function clearCryptText() {
            const el = document.getElementById('cryptText');
            if (el) el.value = '';
        }

        async function processFile(action) {
            const file = document.getElementById('fileInput').files[0];
            const key = (document.getElementById('fileProtectKey')?.value || document.getElementById('cryptKey')?.value || '').trim();
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

        function updateFileProtectName(input) {
            const out = document.getElementById('fileProtectName');
            if (!out) return;
            const file = input?.files?.[0];
            out.innerText = file ? file.name : 'لم يتم اختيار ملف';
        }

        function updateFileLabName(input) {
            const out = document.getElementById('fileLabName');
            if (!out) return;
            const file = input?.files?.[0];
            out.innerText = file ? file.name : 'لم يتم اختيار ملف';
        }

        async function processFileLab(action) {
            const file = document.getElementById('fileLabInput').files[0];
            if(!file) return titanAlert("يرجى اختيار ملف TXT أولاً!");
            if (!/\\.txt$/i.test(file.name)) return titanAlert("هذه الأداة تدعم ملفات TXT فقط.");

            const normalizedAction = action === 'encrypt' ? 'encode' : (action === 'decrypt' ? 'decode' : action);
            const outBox = document.getElementById('fileLabDecoded');
            if (outBox) outBox.classList.add('hidden');

            const formData = new FormData();
            formData.append('file', file);
            if (normalizedAction === 'encode') {
                const secret = (document.getElementById('fileLabSecret')?.value || '').trim();
                if (!secret) return titanAlert('اكتب النص السري أولاً.');
                formData.append('secret', secret);
            }

            const endpoint = normalizedAction === 'encode' ? '/api/text-hide/encode' : '/api/text-hide/decode';
            const res = await fetch(endpoint, { method:'POST', body: formData });
            if (res.ok) {
                soundManager.success();
                if (normalizedAction === 'encode') {
                    const blob = await res.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = file.name.replace(/\\.txt$/i, '') + '_with_hidden.txt';
                    a.click();
                    window.URL.revokeObjectURL(url);
                    titanAlert('✅ تم إخفاء النص داخل ملف TXT بنجاح');
                } else {
                    const data = await res.json();
                    if (!data.success) {
                        titanAlert(data.error || 'فشل استخراج النص');
                        return;
                    }
                    if (outBox) {
                        outBox.classList.remove('hidden');
                        outBox.innerText = data.secret || 'لا يوجد نص مخفي داخل الملف.';
                    }
                }
            } else {
                soundManager.error();
                const err = await res.json();
                titanAlert(err.error || 'فشل عملية الملف');
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
            const fileInput = input || document.getElementById('vaultRestoreFile');
            if (!fileInput || !fileInput.files || !fileInput.files[0]) {
                titanAlert("يرجى اختيار ملف النسخة الاحتياطية أولاً.");
                return;
            }
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            const res = await fetch('/api/vault/restore', { method: 'POST', body: formData });
            if (res.ok) {
                titanAlert("تم استعادة النسخة بنجاح! يرجى إدخال كلمة السر لفتح القبو.");
                lockVault();
            } else {
                let msg = "فشل استعادة النسخة!";
                try {
                    const data = await res.json();
                    if (data && data.error) msg = data.error;
                } catch (_) {}
                titanAlert(msg);
            }
            fileInput.value = '';
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
            doVaultForgotSend();
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
            const unknown = data.unknown || [];
            const allResults = data.all_results || [];
            const checked = Number(data.checked_count || (found.length + notFound.length + unknown.length));
            const modeTotal = checked;

            const socialPriority = [
                { id: 'facebook', label: 'Facebook' },
                { id: 'instagram', label: 'Instagram' }
            ];
            const priorityRank = { facebook: 0, instagram: 1 };
            const foundSorted = [...found].sort((a, b) => {
                const ra = priorityRank[String(a?.platform || '').toLowerCase()] ?? 999;
                const rb = priorityRank[String(b?.platform || '').toLowerCase()] ?? 999;
                if (ra !== rb) return ra - rb;
                return String(a?.platform || '').localeCompare(String(b?.platform || ''));
            });

            const socialRows = socialPriority.map((s) => {
                const row = allResults.find((r) => String(r?.platform || '').toLowerCase() === s.id);
                if (!row) {
                    return `<div class="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-900/40 p-2">
                        <span class="font-bold text-gray-300">${_osintEscape(s.label)}</span>
                        <span class="text-[11px] text-gray-500">لم يتم فحصها</span>
                    </div>`;
                }

                const exists = !!row.exists;
                const hasError = !!row.error;
                const statusText = hasError ? 'Unknown' : (exists ? 'Found' : 'Not Found');
                const statusClass = hasError
                    ? 'text-amber-300 border-amber-800/40 bg-amber-900/10'
                    : (exists ? 'text-green-300 border-green-800/40 bg-green-900/10' : 'text-gray-300 border-slate-700 bg-slate-900/50');

                return `<div class="rounded-lg border p-2 ${statusClass}">
                    <div class="flex items-center justify-between gap-2">
                        <span class="font-bold">${_osintEscape(s.label)}</span>
                        <span class="text-[10px] uppercase tracking-wider">${_osintEscape(statusText)}</span>
                    </div>
                    <div class="text-[11px] font-mono break-all mt-1" dir="ltr">${_osintEscape(row.url || '')}</div>
                </div>`;
            });

            return `
                <div class="space-y-3">
                    <div class="grid grid-cols-4 gap-2">
                        <div class="bg-green-900/20 border border-green-800/50 rounded-lg p-2 text-center">
                            <div class="text-[10px] text-gray-400">FOUND</div>
                            <div class="text-lg font-black text-green-400">${_osintEscape(found.length)}</div>
                        </div>
                        <div class="bg-slate-900/60 border border-slate-700 rounded-lg p-2 text-center">
                            <div class="text-[10px] text-gray-400">NOT FOUND</div>
                            <div class="text-lg font-black text-gray-300">${_osintEscape(notFound.length)}</div>
                        </div>
                        <div class="bg-cyan-900/20 border border-cyan-800/50 rounded-lg p-2 text-center">
                            <div class="text-[10px] text-gray-400">CHECKED</div>
                            <div class="text-lg font-black text-cyan-300">${_osintEscape(checked)}</div>
                        </div>
                        <div class="bg-indigo-900/20 border border-indigo-800/50 rounded-lg p-2 text-center">
                            <div class="text-[10px] text-gray-400">USERNAME</div>
                            <div class="text-sm font-bold text-indigo-300 font-mono" dir="ltr">${_osintEscape(data.username)}</div>
                        </div>
                    </div>
                    <div class="text-[11px] text-cyan-200/90 bg-cyan-950/20 border border-cyan-900/30 rounded-lg px-3 py-2">
                        Mode: <span class="font-bold text-cyan-300">${_osintEscape(String(data.mode || '').toUpperCase())}</span>
                        | منصات الوضع: <span class="font-bold text-cyan-100">${_osintEscape(modeTotal)}</span>
                        | Unknown: <span class="font-bold text-amber-300">${_osintEscape(unknown.length)}</span>
                    </div>
                    <div class="bg-slate-950/40 border border-indigo-900/30 rounded-lg p-2 space-y-2">
                        <div class="text-[10px] text-indigo-300 uppercase tracking-wider">Social Priority (First)</div>
                        ${socialRows.join('')}
                    </div>
                    <div class="bg-black/40 border border-slate-700 rounded-lg p-2">
                        <div class="text-[10px] text-gray-500 uppercase mb-2">Platforms Detected</div>
                        ${foundSorted.length ? foundSorted.map((r) => `<a href="${_osintEscape(r.url)}" target="_blank" rel="noopener noreferrer" class="block mb-1 p-2 rounded bg-green-900/20 border border-green-800/40 hover:bg-green-900/35 transition-all">
                            <span class="text-green-300 font-bold">${_osintEscape(r.platform)}</span>
                            <span class="text-[11px] text-gray-300 ml-2 font-mono" dir="ltr">${_osintEscape(r.url)}</span>
                        </a>`).join('') : '<div class="text-gray-500 text-xs">لا توجد حسابات مؤكدة حالياً.</div>'}
                        ${unknown.length ? `<div class="mt-2 pt-2 border-t border-amber-900/30">
                            <div class="text-[10px] text-amber-300 uppercase mb-1">Unknown / Rate Limited</div>
                            ${unknown.map((r) => `<div class="mb-1 p-2 rounded bg-amber-900/10 border border-amber-800/30">
                                <span class="text-amber-300 font-bold">${_osintEscape(r.platform)}</span>
                                <span class="text-[11px] text-gray-300 ml-2 font-mono" dir="ltr">${_osintEscape(r.url || '')}</span>
                            </div>`).join('')}
                        </div>` : ''}
                    </div>
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

        function _osintRiskTone(score) {
            const n = Number(score) || 0;
            if (n >= 70) return { cls: 'text-rose-300 border-rose-800/50 bg-rose-900/20', label: 'High Risk' };
            if (n >= 35) return { cls: 'text-amber-300 border-amber-800/50 bg-amber-900/20', label: 'Medium Risk' };
            return { cls: 'text-emerald-300 border-emerald-800/50 bg-emerald-900/20', label: 'Low Risk' };
        }

        let _osintActivityLog = [];
        let _osintLastUnified = null;

        function _osintLoadActivityLog() {
            try {
                _osintActivityLog = JSON.parse(localStorage.getItem('titan_osint_activity') || '[]');
                if (!Array.isArray(_osintActivityLog)) _osintActivityLog = [];
            } catch (_) {
                _osintActivityLog = [];
            }
        }

        function _osintSaveActivityLog() {
            localStorage.setItem('titan_osint_activity', JSON.stringify((_osintActivityLog || []).slice(0, 80)));
        }

        function _osintRenderActivityFeed() {
            const box = document.getElementById('osintActivityFeed');
            if (!box) return;
            if (!_osintActivityLog.length) {
                box.innerHTML = '<div class="text-xs text-gray-500 bg-black/30 border border-slate-700 rounded-lg p-3">لا يوجد نشاط OSINT حتى الآن.</div>';
                return;
            }
            box.innerHTML = _osintActivityLog.slice(0, 25).map((row) => {
                const tone = _osintRiskTone(row.risk_score || 0);
                return `<div class="rounded-lg border border-slate-700 bg-black/35 p-2">
                    <div class="flex items-center justify-between gap-2">
                        <div class="font-mono text-[11px] text-cyan-300 break-all" dir="ltr">${_osintEscape(row.target || '')}</div>
                        <span class="text-[10px] px-2 py-0.5 rounded border ${tone.cls}">${_osintEscape(String(row.risk_score || 0))}</span>
                    </div>
                    <div class="text-[10px] text-gray-400 mt-1">${_osintEscape((row.action || 'lookup').toUpperCase())} | ${_osintEscape((row.target_type || 'unknown').toUpperCase())} | ${_osintEscape(row.label || '')}</div>
                    <div class="text-[10px] text-gray-600 mt-0.5">${_osintEscape(row.created_at || '')}</div>
                </div>`;
            }).join('');
        }

        function _osintUpdateMissionStats() {
            const log = Array.isArray(_osintActivityLog) ? _osintActivityLog : [];
            const total = log.length;
            const high = log.filter((x) => Number(x.risk_score || 0) >= 70).length;
            const avg = total ? (log.reduce((a, b) => a + (Number(b.risk_score || 0) || 0), 0) / total) : 0;
            const lastType = (log[0]?.target_type || '--').toUpperCase();
            const totalEl = document.getElementById('osintMissionTotal');
            const highEl = document.getElementById('osintMissionHigh');
            const avgEl = document.getElementById('osintMissionAvg');
            const lastEl = document.getElementById('osintMissionLast');
            if (totalEl) totalEl.innerText = String(total);
            if (highEl) highEl.innerText = String(high);
            if (avgEl) avgEl.innerText = String(Math.round(avg));
            if (lastEl) lastEl.innerText = lastType;
        }

        function _osintTrackActivity(action, payload) {
            const row = {
                action,
                target: String(payload?.target || ''),
                target_type: String(payload?.targetType || 'unknown'),
                risk_score: Math.max(0, Math.min(100, Number(payload?.risk || 0) || 0)),
                label: String(payload?.label || ''),
                created_at: new Date().toLocaleString()
            };
            _osintActivityLog.unshift(row);
            _osintActivityLog = _osintActivityLog.slice(0, 80);
            _osintSaveActivityLog();
            _osintRenderActivityFeed();
            _osintUpdateMissionStats();
        }

        async function _osintLookupTarget(rawTarget) {
            const target = String(rawTarget || '').trim();
            const targetType = _osintDetectTargetType(target);
            if (!target) throw new Error('Target is empty');
            if (targetType === 'unknown') throw new Error('Unsupported target type');

            let data = null;
            let risk = 0;
            let label = 'Low';

            if (targetType === 'ip') {
                const res = await fetch('/api/ip', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ip: target})
                });
                data = await res.json();
                risk = data.proxy ? 75 : 20;
                label = data.proxy ? 'Proxy/VPN Suspected' : 'Clean IP';
            } else if (targetType === 'email') {
                const res = await fetch('/api/scan/email', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({email: target})
                });
                data = await res.json();
                risk = Number(data.fraud_score || 0);
                label = risk >= 70 ? 'High Fraud Probability' : (risk >= 35 ? 'Suspicious' : 'Likely Safe');
            } else if (targetType === 'phone') {
                const res = await fetch('/api/scan/phone', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({phone: target})
                });
                data = await res.json();
                risk = Number(data.fraud_score || 0);
                label = risk >= 70 ? 'High Abuse Probability' : (risk >= 35 ? 'Suspicious' : 'Likely Safe');
            } else if (targetType === 'domain' || targetType === 'url') {
                const finalUrl = targetType === 'domain' ? `https://${target}` : target;
                const res = await fetch('/api/scan/url', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: finalUrl})
                });
                data = await res.json();
                risk = Number(data.risk_score || 0);
                label = risk >= 70 ? 'High Threat URL' : (risk >= 35 ? 'Potentially Suspicious' : 'Likely Safe URL');
            }

            return { target, targetType, data, risk, label };
        }

        function osintApplyPreset(kind) {
            const map = {
                ip: '8.8.8.8',
                domain: 'example.com',
                url: 'https://example.com/login',
                email: 'security@example.com',
                phone: '+12025550123'
            };
            const value = map[String(kind || '').toLowerCase()] || '';
            const input = document.getElementById('osintTargetInput');
            if (input) {
                input.value = value;
                input.focus();
            }
        }

        function _osintRenderRisk(score, label) {
            const box = document.getElementById('osintRiskScore');
            if (!box) return;
            const n = Math.max(0, Math.min(100, Number(score) || 0));
            const tone = _osintRiskTone(n);
            box.className = `mt-3 p-3 rounded-xl border text-sm font-bold ${tone.cls}`;
            box.innerHTML = `<div class="flex items-center justify-between gap-2"><span>Risk Score: ${_osintEscape(n)}/100</span><span class="text-[10px] uppercase tracking-wider">${_osintEscape(tone.label)}</span></div><div class="text-[11px] mt-1">${_osintEscape(label || '')}</div>`;
            box.classList.remove('hidden');
        }

        let _ctfChallenges = [];
        let _ctfLastPayload = null;

        function _ctfDifficultyClass(level) {
            const t = String(level || '').toLowerCase();
            if (t === 'easy') return 'text-emerald-300 border-emerald-800/50 bg-emerald-900/20';
            if (t === 'hard') return 'text-rose-300 border-rose-800/50 bg-rose-900/20';
            return 'text-amber-300 border-amber-800/50 bg-amber-900/20';
        }

        function ctfApplyFilters() {
            const diff = (document.getElementById('ctfFilterDifficulty')?.value || 'all').toLowerCase();
            const cat = (document.getElementById('ctfFilterCategory')?.value || 'all').toLowerCase();
            const q = (document.getElementById('ctfSearchInput')?.value || '').trim().toLowerCase();
            const unsolvedOnly = !!document.getElementById('ctfFilterUnsolved')?.checked;
            const source = Array.isArray(_ctfChallenges) ? _ctfChallenges : [];
            const filtered = source.filter((c) => {
                if (diff !== 'all' && String(c.difficulty || '').toLowerCase() !== diff) return false;
                if (cat !== 'all' && String(c.category || '').toLowerCase() !== cat) return false;
                if (unsolvedOnly && c.solved) return false;
                if (q) {
                    const blob = [c.title, c.description, c.category, c.method].map((x) => String(x || '').toLowerCase()).join(' ');
                    if (!blob.includes(q)) return false;
                }
                return true;
            });
            _ctfRenderList(filtered);
        }

        function _ctfUpdateDashboard(payload) {
            const p = payload || {};
            const total = Number((p.challenges || []).length || 0);
            const solvedCycle = Number(p.solved_count || 0);
            const solvedTotal = Number(p.total_solved || 0);
            const points = Number(p.total_points || 0);
            const rotation = String(p.rotation_key || '--');

            const a = document.getElementById('ctfStatActive');
            const s1 = document.getElementById('ctfStatSolvedCycle');
            const s2 = document.getElementById('ctfStatSolvedTotal');
            const pts = document.getElementById('ctfStatPoints');
            const rot = document.getElementById('ctfStatRotation');
            if (a) a.innerText = String(total);
            if (s1) s1.innerText = String(solvedCycle);
            if (s2) s2.innerText = String(solvedTotal);
            if (pts) pts.innerText = String(points);
            if (rot) rot.innerText = rotation;
        }

        function _ctfRefreshCategoryFilter() {
            const el = document.getElementById('ctfFilterCategory');
            if (!el) return;
            const categories = Array.from(new Set((_ctfChallenges || []).map((c) => String(c.category || '').trim()).filter(Boolean))).sort();
            const oldVal = (el.value || 'all').toLowerCase();
            el.innerHTML = '<option value="all" selected>كل التصنيفات</option>' + categories.map((c) => `<option value="${_osintEscape(c.toLowerCase())}">${_osintEscape(c)}</option>`).join('');
            if (oldVal !== 'all' && categories.some((c) => c.toLowerCase() === oldVal)) {
                el.value = oldVal;
            }
        }

        function _ctfRenderList(items) {
            const box = document.getElementById('ctfList');
            if (!box) return;
            if (!items || !items.length) {
                box.innerHTML = '<div class="text-xs text-gray-500">لا توجد تحديات حالياً.</div>';
                return;
            }

            box.innerHTML = items.map((c) => {
                const solved = !!c.solved;
                const hints = Array.isArray(c.hints) ? c.hints : [];
                const hintsHtml = hints.length
                    ? hints.map((h, i) => `<li class="text-sm text-gray-200 ctf-bidi"><span class="text-amber-300 font-mono ctf-ltr">${i + 1}.</span> ${_osintEscape(h)}</li>`).join('')
                    : '<li class="text-sm text-gray-400 ctf-bidi">لا توجد تلميحات إضافية.</li>';
                const fileBlock = c.download_required
                    ? `<div class="space-y-2 rounded-lg border border-amber-800/50 bg-amber-950/20 p-3">
                            <div class="text-sm font-bold text-amber-300 ctf-bidi">ملف التحدي الإجباري</div>
                            <div class="text-sm text-gray-200 ctf-bidi">هذا التحدي يتطلب تنزيل ملف المعطيات أولاً ثم استخراج المطلوب منه.</div>
                            <div class="flex flex-wrap items-center gap-2 text-sm">
                                <span class="px-2 py-1 rounded border border-slate-700 bg-slate-900/60 text-cyan-300 font-mono ctf-ltr">${_osintEscape(c.download_name || 'challenge.txt')}</span>
                                <button onclick="ctfDownloadAsset('${_osintEscape(c.id)}')" class="px-3 py-1.5 rounded-lg bg-amber-900/50 border border-amber-800/50 text-amber-200 text-xs font-bold hover:bg-amber-800/60">تنزيل الملف</button>
                            </div>
                        </div>`
                    : '';
                const solvedBadge = solved
                    ? '<span class="text-[10px] px-2 py-1 rounded border border-emerald-800/50 bg-emerald-900/20 text-emerald-300">Solved</span>'
                    : '<span class="text-[10px] px-2 py-1 rounded border border-slate-700 bg-slate-900/60 text-gray-300">Unsolved</span>';
                return `
                    <div class="ctf-card bg-slate-900/60 p-4 rounded-xl border border-amber-900/35 space-y-3">
                        <div class="flex items-center justify-between gap-2">
                            <h3 class="ctf-card-title text-amber-300 ctf-bidi">${_osintEscape(c.title || 'Challenge')}</h3>
                            ${solvedBadge}
                        </div>
                        <div class="flex flex-wrap gap-2 text-[11px]">
                            <span class="px-2 py-1 rounded border border-slate-700 bg-slate-900/60 text-gray-300">${_osintEscape(c.category || 'misc')}</span>
                            <span class="px-2 py-1 rounded border ${_ctfDifficultyClass(c.difficulty)}">${_osintEscape(String(c.difficulty || '').toUpperCase())}</span>
                            <span class="px-2 py-1 rounded border border-violet-800/50 bg-violet-900/20 text-violet-300">${_osintEscape(c.points || 0)} pts</span>
                        </div>

                        <div class="space-y-2 rounded-lg border border-slate-700/70 bg-black/25 p-3">
                            <div class="text-sm font-bold text-cyan-300 ctf-bidi">تفاصيل التحدي</div>
                            <div class="ctf-bidi text-gray-200 whitespace-pre-wrap">${_osintEscape(c.description || '')}</div>
                            <div class="text-sm text-gray-300 ctf-bidi">صيغة العلم: <span class="font-mono text-amber-300 ctf-ltr">${_osintEscape(c.flag_format || 'TITAN{...}')}</span></div>
                        </div>

                        <div class="space-y-2 rounded-lg border border-slate-700/70 bg-black/25 p-3">
                            <div class="text-sm font-bold text-violet-300 ctf-bidi">كيف أفكر بالحل؟</div>
                            <div class="ctf-bidi text-gray-200">${_osintEscape(c.method || 'ابدأ بتحليل المعطيات وتقسيم المشكلة لخطوات صغيرة.')}</div>
                        </div>

                        ${fileBlock}

                        <div class="space-y-2 rounded-lg border border-slate-700/70 bg-black/25 p-3">
                            <div class="text-sm font-bold text-amber-300 ctf-bidi">تلميحات سريعة</div>
                            <ol class="space-y-1">${hintsHtml}</ol>
                        </div>

                        <div class="space-y-2">
                            <input id="ctf-flag-${_osintEscape(c.id)}" type="text" placeholder="أدخل العلم هنا..." class="w-full p-2 rounded-lg bg-slate-900 border border-slate-700 outline-none text-sm font-mono ctf-ltr" dir="ltr">
                            <div class="flex flex-col gap-2">
                                <button onclick="ctfSubmit('${_osintEscape(c.id)}')" class="flex-1 py-2 rounded-lg bg-amber-900/40 border border-amber-800/50 text-amber-300 text-xs font-bold">تحقق من الحل</button>
                                <button onclick="ctfAskAi('${_osintEscape(c.id)}')" class="flex-1 py-2 rounded-lg bg-violet-900/40 border border-violet-800/50 text-violet-300 text-xs font-bold">مساعد AI</button>
                            </div>
                        </div>

                        <div class="space-y-1">
                            <textarea id="ctf-q-${_osintEscape(c.id)}" rows="2" placeholder="اسأل مساعد AI: مثال ما أول خطوة؟" class="w-full p-2 rounded-lg bg-slate-900 border border-slate-700 outline-none text-sm ctf-bidi"></textarea>
                            <div id="ctf-ai-${_osintEscape(c.id)}" class="hidden p-2 rounded-lg bg-black/40 border border-slate-700 text-sm whitespace-pre-wrap ctf-bidi"></div>
                            <div id="ctf-res-${_osintEscape(c.id)}" class="hidden p-2 rounded-lg bg-black/40 border border-slate-700 text-sm ctf-bidi"></div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        async function ctfLoadChallenges(forceRefresh) {
            const meta = document.getElementById('ctfMeta');
            if (meta) meta.innerText = 'جار تحميل تحديات CTF...';
            try {
                const suffix = forceRefresh ? '?refresh=1' : '';
                const res = await fetch('/api/ctf/challenges' + suffix);
                const data = await res.json();
                if (!data.success) {
                    if (meta) meta.innerText = data.error || 'فشل تحميل التحديات.';
                    return;
                }
                _ctfLastPayload = data;
                _ctfChallenges = data.challenges || [];
                _ctfRefreshCategoryFilter();
                _ctfUpdateDashboard(data);
                ctfApplyFilters();
                if (meta) {
                    const solved = Number(data.solved_count || 0);
                    const total = Number((_ctfChallenges || []).length);
                    const totalSolved = Number(data.total_solved || solved);
                    const points = Number(data.total_points || 0);
                    meta.innerText = `الدورة: ${data.rotation_key || '-'} | محلول في الدفعة: ${solved}/${total} | إجمالي المحلول: ${totalSolved} | النقاط: ${points} | آخر تحديث: ${new Date().toLocaleTimeString()}`;
                }
            } catch (e) {
                if (meta) meta.innerText = `تعذر تحميل التحديات: ${e.message || e}`;
            }
        }

        function ctfDownloadAsset(challengeId) {
            if (!challengeId) return;
            const url = '/api/ctf/challenge-file/' + encodeURIComponent(challengeId) + '?t=' + Date.now();
            const a = document.createElement('a');
            a.href = url;
            a.target = '_blank';
            a.rel = 'noopener noreferrer';
            document.body.appendChild(a);
            a.click();
            a.remove();
        }

        async function ctfSubmit(challengeId) {
            const input = document.getElementById('ctf-flag-' + challengeId);
            const out = document.getElementById('ctf-res-' + challengeId);
            if (!input || !out) return;
            const answer = (input.value || '').trim();
            if (!answer) return titanAlert('ادخل العلم أولاً.');

            const card = out.closest('.ctf-card') || out.closest('div');
            const actionButtons = card ? Array.from(card.querySelectorAll('button')) : [];
            let keepLocked = false;

            out.classList.remove('hidden');
            out.innerText = 'جار التحقق...';
            input.disabled = true;
            actionButtons.forEach((b) => b.disabled = true);
            try {
                const res = await fetch('/api/ctf/submit', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ challenge_id: challengeId, answer })
                });
                const data = await res.json();
                if (data.correct) {
                    keepLocked = true;
                    out.className = 'p-2 rounded-lg bg-emerald-900/20 border border-emerald-800/50 text-sm text-emerald-300 ctf-bidi';
                    let secondsLeft = 5;
                    out.innerText = `✅ الحل صحيح! +${data.points || 0} نقطة. سيتم عرض تحدٍ جديد مختلف خلال ${secondsLeft} ثوانٍ...`;

                    if (!window.__ctfSwapTimers) window.__ctfSwapTimers = {};
                    if (window.__ctfSwapTimers[challengeId]) {
                        clearInterval(window.__ctfSwapTimers[challengeId]);
                    }

                    window.__ctfSwapTimers[challengeId] = setInterval(() => {
                        secondsLeft -= 1;
                        if (secondsLeft <= 0) {
                            clearInterval(window.__ctfSwapTimers[challengeId]);
                            delete window.__ctfSwapTimers[challengeId];
                            ctfLoadChallenges(true);
                            return;
                        }
                        out.innerText = `✅ الحل صحيح! +${data.points || 0} نقطة. سيتم عرض تحدٍ جديد مختلف خلال ${secondsLeft} ثوانٍ...`;
                    }, 1000);
                    return;
                } else {
                    out.className = 'p-2 rounded-lg bg-rose-900/20 border border-rose-800/50 text-sm text-rose-300 ctf-bidi';
                    out.innerText = `❌ غير صحيح. ${data.message || 'حاول مرة ثانية.'}`;
                }
            } catch (e) {
                out.className = 'p-2 rounded-lg bg-rose-900/20 border border-rose-800/50 text-sm text-rose-300 ctf-bidi';
                out.innerText = `تعذر التحقق: ${e.message || e}`;
            } finally {
                if (!keepLocked) {
                    input.disabled = false;
                    actionButtons.forEach((b) => b.disabled = false);
                }
            }
        }

        async function ctfAskAi(challengeId) {
            const qEl = document.getElementById('ctf-q-' + challengeId);
            const out = document.getElementById('ctf-ai-' + challengeId);
            const aEl = document.getElementById('ctf-flag-' + challengeId);
            if (!qEl || !out) return;

            const question = (qEl.value || '').trim() || 'اشرح لي أول 3 خطوات للحل بدون كشف الإجابة النهائية.';
            const attempt = (aEl?.value || '').trim();

            out.classList.remove('hidden');
            out.className = 'p-2 rounded-lg bg-black/40 border border-slate-700 text-sm whitespace-pre-wrap ctf-bidi';
            out.innerText = 'AI يفكر...';
            try {
                const res = await fetch('/api/ctf/assistant', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ challenge_id: challengeId, question, attempt })
                });
                const data = await res.json();
                if (!res.ok || !data.success) throw new Error(data.error || 'فشل مساعد AI.');
                out.className = 'p-2 rounded-lg bg-violet-900/20 border border-violet-800/50 text-sm text-violet-200 whitespace-pre-wrap ctf-bidi';
                out.innerText = data.reply || 'لا يوجد رد.';
            } catch (e) {
                out.className = 'p-2 rounded-lg bg-rose-900/20 border border-rose-800/50 text-sm text-rose-300 whitespace-pre-wrap ctf-bidi';
                out.innerText = `فشل الاتصال: ${e.message || e}`;
            }
        }

        async function runUnifiedOsint() {
            const input = document.getElementById('osintTargetInput');
            const out = document.getElementById('osintUnifiedResult');
            const target = (input?.value || '').trim();
            if (!target) return titanAlert('ادخل هدف أولاً.');
            if (!out) return;

            setResultLoading(out, 'Unified OSINT', 'Running unified OSINT lookup...');
            try {
                const res = await _osintLookupTarget(target);
                const { targetType, data, risk, label } = res;

                _osintRenderRisk(risk, label);
                setResultMarkup(out, 'Unified OSINT', _osintRenderUnifiedResult(target, targetType, data), { badge: targetType.toUpperCase() });
                _osintLastUnified = {
                    target,
                    target_type: targetType,
                    risk_score: risk,
                    label,
                    data
                };
                _osintTrackActivity('unified_lookup', { target, targetType, risk, label });
                soundManager.success();
            } catch (e) {
                setResultError(out, `Lookup failed: ${e.message || e}. Supported: IP, URL, Domain, Email, Phone`);
                soundManager.error();
            }
        }

        async function huntUsername() {
            const username = (document.getElementById('osintUsernameInput')?.value || '').trim();
            const mode = (document.getElementById('osintUsernameMode')?.value || 'deep').toLowerCase();
            const out = document.getElementById('osintUsernameResult');
            if (!username) return titanAlert('ادخل اسم مستخدم أولاً.');
            if (!out) return;

            setResultLoading(out, 'Username Hunt', `جاري فحص المنصات الاجتماعية (${mode.toUpperCase()})...`);
            try {
                const res = await fetch('/api/osint/username', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username, mode})
                });
                const data = await res.json();
                const badge = data.success ? 'SOCIAL' : 'Failed';
                setResultMarkup(out, 'Username Hunt', _osintRenderUsernameResult(data), { badge });
                if (data.found_count > 0) {
                    _osintRenderRisk(60, 'Public Username Footprint Detected');
                    _osintTrackActivity('username_hunt', { target: username, targetType: 'username', risk: 60, label: 'Public footprint detected' });
                } else {
                    _osintRenderRisk(15, 'No Immediate Public Presence');
                    _osintTrackActivity('username_hunt', { target: username, targetType: 'username', risk: 15, label: 'No immediate public presence' });
                }
            } catch (e) {
                setResultError(out, `Username scan failed: ${e.message || e}`);
            }
        }

        function updateUsernameModeHint() {
            if (window.__osintKeybindInit) return;
            window.__osintKeybindInit = true;

            const targetInput = document.getElementById('osintTargetInput');
            if (targetInput) {
                targetInput.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        runUnifiedOsint();
                    }
                });
            }

            const userInput = document.getElementById('osintUsernameInput');
            if (userInput) {
                userInput.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        huntUsername();
                    }
                });
            }
        }

        function loadOsintWatchlist() {
            const box = document.getElementById('osintWatchlist');
            if (!box) return;
            const list = JSON.parse(localStorage.getItem('titan_osint_watchlist') || '[]');
            if (!list.length) {
                setResultList(box, 'OSINT Watchlist', [], { badge: '0', emptyText: 'لا يوجد عناصر محفوظة بعد.' });
                _osintLoadActivityLog();
                _osintRenderActivityFeed();
                _osintUpdateMissionStats();
                return;
            }
            setResultList(
                box,
                'OSINT Watchlist',
                list.map((x, i) => `<div class="flex items-center justify-between gap-2"><span class="font-mono text-[11px] text-indigo-200" dir="ltr">${_resultEscape(x)}</span><div class="flex items-center gap-2"><button onclick="runWatchlistTarget(${i})" class="text-cyan-300 text-[10px]">تشغيل</button><button onclick="setCompareFromWatchItem(${i}, 'a')" class="text-fuchsia-300 text-[10px]">A</button><button onclick="setCompareFromWatchItem(${i}, 'b')" class="text-fuchsia-300 text-[10px]">B</button><button onclick="removeOsintWatchItem(${i})" class="text-red-400 text-[10px]">حذف</button></div></div>`),
                { badge: `${list.length} Targets` }
            );
            _osintLoadActivityLog();
            _osintRenderActivityFeed();
            _osintUpdateMissionStats();
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

        function clearOsintWatchlist() {
            localStorage.setItem('titan_osint_watchlist', JSON.stringify([]));
            loadOsintWatchlist();
            titanAlert('تم تفريغ الـ Watchlist.');
        }

        async function runWatchlistTarget(idx) {
            const list = JSON.parse(localStorage.getItem('titan_osint_watchlist') || '[]');
            const target = list[idx];
            if (!target) return;
            const input = document.getElementById('osintTargetInput');
            if (input) input.value = target;
            await runUnifiedOsint();
        }

        function setCompareFromWatchItem(idx, side) {
            const list = JSON.parse(localStorage.getItem('titan_osint_watchlist') || '[]');
            const target = list[idx];
            if (!target) return;
            const id = side === 'b' ? 'osintCompareB' : 'osintCompareA';
            const el = document.getElementById(id);
            if (el) el.value = target;
        }

        function runWatchlistBatch() {
            const list = JSON.parse(localStorage.getItem('titan_osint_watchlist') || '[]');
            if (!list.length) return titanAlert('لا توجد أهداف في الـ Watchlist.');
            const input = document.getElementById('osintBatchInput');
            if (input) input.value = list.slice(0, 12).join('\\n');
            runBatchOsint();
        }

        function removeOsintWatchItem(idx) {
            const list = JSON.parse(localStorage.getItem('titan_osint_watchlist') || '[]');
            list.splice(idx, 1);
            localStorage.setItem('titan_osint_watchlist', JSON.stringify(list));
            loadOsintWatchlist();
        }

        async function runBatchOsint() {
            const src = (document.getElementById('osintBatchInput')?.value || '');
            const box = document.getElementById('osintBatchResult');
            if (!box) return;

            const targets = Array.from(new Set(src.split(/\\r?\\n/).map((x) => x.trim()).filter(Boolean))).slice(0, 20);
            if (!targets.length) return titanAlert('أدخل هدفًا واحدًا على الأقل في التحليل الدفعي.');

            setResultLoading(box, 'Batch Analyzer', `تحليل ${targets.length} هدف...`);

            const rows = [];
            for (let i = 0; i < targets.length; i += 1) {
                const t = targets[i];
                try {
                    const res = await _osintLookupTarget(t);
                    rows.push({ target: t, ok: true, ...res });
                    _osintTrackActivity('batch_lookup', { target: t, targetType: res.targetType, risk: res.risk, label: res.label });
                } catch (e) {
                    rows.push({ target: t, ok: false, error: e.message || String(e), targetType: 'unknown', risk: 0, label: 'Failed' });
                }
            }

            const okRows = rows.filter((r) => r.ok);
            const avgRisk = okRows.length ? Math.round(okRows.reduce((a, b) => a + (Number(b.risk || 0) || 0), 0) / okRows.length) : 0;
            const highCount = okRows.filter((r) => Number(r.risk || 0) >= 70).length;

            const html = `
                <div class="space-y-3">
                    <div class="grid grid-cols-3 gap-2">
                        <div class="p-2 rounded border border-slate-700 bg-slate-900/50 text-center"><div class="text-[10px] text-gray-500">Targets</div><div class="text-lg font-black text-cyan-300">${_osintEscape(rows.length)}</div></div>
                        <div class="p-2 rounded border border-slate-700 bg-slate-900/50 text-center"><div class="text-[10px] text-gray-500">High Risk</div><div class="text-lg font-black text-rose-300">${_osintEscape(highCount)}</div></div>
                        <div class="p-2 rounded border border-slate-700 bg-slate-900/50 text-center"><div class="text-[10px] text-gray-500">Avg Risk</div><div class="text-lg font-black text-amber-300">${_osintEscape(avgRisk)}</div></div>
                    </div>
                    <div class="space-y-2">
                        ${rows.map((r) => {
                            if (!r.ok) {
                                return `<div class="p-2 rounded border border-rose-800/40 bg-rose-900/10"><div class="font-mono text-xs text-rose-300 break-all" dir="ltr">${_osintEscape(r.target)}</div><div class="text-[10px] text-rose-200 mt-1">${_osintEscape(r.error || 'failed')}</div></div>`;
                            }
                            const tone = _osintRiskTone(r.risk);
                            return `<div class="p-2 rounded border border-slate-700 bg-black/30">
                                <div class="flex items-center justify-between gap-2">
                                    <div class="font-mono text-xs text-cyan-300 break-all" dir="ltr">${_osintEscape(r.target)}</div>
                                    <span class="text-[10px] px-2 py-0.5 rounded border ${tone.cls}">${_osintEscape(r.risk)}</span>
                                </div>
                                <div class="text-[10px] text-gray-400 mt-1">${_osintEscape(r.targetType.toUpperCase())} | ${_osintEscape(r.label)}</div>
                            </div>`;
                        }).join('')}
                    </div>
                </div>
            `;
            setResultMarkup(box, 'Batch Analyzer', html, { badge: `${rows.length} Targets` });
        }

        async function compareOsintTargets() {
            const a = (document.getElementById('osintCompareA')?.value || '').trim();
            const b = (document.getElementById('osintCompareB')?.value || '').trim();
            const out = document.getElementById('osintCompareResult');
            if (!out) return;
            if (!a || !b) return titanAlert('أدخل الهدفين للمقارنة.');

            setResultLoading(out, 'Target Comparison', 'جاري تحليل الهدفين...');
            try {
                const [ra, rb] = await Promise.all([_osintLookupTarget(a), _osintLookupTarget(b)]);
                const winner = Number(ra.risk || 0) >= Number(rb.risk || 0) ? ra : rb;
                const delta = Math.abs(Number(ra.risk || 0) - Number(rb.risk || 0));
                const card = (x, label) => {
                    const tone = _osintRiskTone(x.risk);
                    return `<div class="p-3 rounded-lg border border-slate-700 bg-black/30 space-y-1">
                        <div class="text-[10px] text-gray-500 uppercase">${_osintEscape(label)}</div>
                        <div class="font-mono text-xs text-cyan-300 break-all" dir="ltr">${_osintEscape(x.target)}</div>
                        <div class="text-[10px] text-gray-400">${_osintEscape(x.targetType.toUpperCase())} | ${_osintEscape(x.label)}</div>
                        <div><span class="text-[10px] px-2 py-0.5 rounded border ${tone.cls}">${_osintEscape(x.risk)}</span></div>
                    </div>`;
                };

                const html = `
                    <div class="space-y-3">
                        <div class="p-2 rounded-lg border border-fuchsia-800/40 bg-fuchsia-900/10 text-fuchsia-200 text-xs">
                            الأعلى خطورة: <span class="font-bold">${_osintEscape(winner.target)}</span> | فرق المخاطرة: <span class="font-bold">${_osintEscape(delta)}</span>
                        </div>
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                            ${card(ra, 'Target A')}
                            ${card(rb, 'Target B')}
                        </div>
                    </div>
                `;
                setResultMarkup(out, 'Target Comparison', html, { badge: 'COMPARE' });
                _osintTrackActivity('target_compare', { target: `${a} <-> ${b}`, targetType: 'compare', risk: Math.max(Number(ra.risk || 0), Number(rb.risk || 0)), label: 'Comparison completed' });
            } catch (e) {
                setResultError(out, `Comparison failed: ${e.message || e}`);
            }
        }

        function clearOsintActivityLog() {
            _osintActivityLog = [];
            _osintSaveActivityLog();
            _osintRenderActivityFeed();
            _osintUpdateMissionStats();
        }

        function exportOsintReport() {
            const watchlist = JSON.parse(localStorage.getItem('titan_osint_watchlist') || '[]');
            const activity = JSON.parse(localStorage.getItem('titan_osint_activity') || '[]');
            const latestUnified = document.getElementById('osintUnifiedResult')?.innerText || '';
            const latestThreat = document.getElementById('osintThreatResult')?.innerText || '';
            const latestUsername = document.getElementById('osintUsernameResult')?.innerText || '';
            const latestHash = document.getElementById('osintHashResult')?.innerText || '';
            const latestBatch = document.getElementById('osintBatchResult')?.innerText || '';
            const latestCompare = document.getElementById('osintCompareResult')?.innerText || '';
            const report = {
                generated_at: new Date().toISOString(),
                watchlist,
                activity_timeline: activity,
                latest_unified_object: _osintLastUnified,
                latest_unified_lookup: latestUnified,
                latest_threat_intel: latestThreat,
                latest_username_hunt: latestUsername,
                latest_hash_analysis: latestHash,
                latest_batch_analysis: latestBatch,
                latest_target_comparison: latestCompare
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
        let irCasesCache = [];

        function irSetActionButtonsEnabled(enabled) {
            ['ir-btn-open', 'ir-btn-investigating', 'ir-btn-contained', 'ir-btn-closed', 'ir-btn-export', 'ir-btn-export-pdf', 'ir-btn-auto-priority']
                .forEach((id) => {
                    const el = document.getElementById(id);
                    if (el) el.disabled = !enabled;
                });
        }

        function irRenderKanban(cases) {
            const statuses = ['open', 'investigating', 'contained', 'closed'];
            statuses.forEach((st) => {
                const lane = document.getElementById(`irKanban-${st}`);
                if (!lane) return;
                const rows = (cases || []).filter((c) => c.status === st);
                lane.innerHTML = rows.map((c) => `
                    <div class="p-2 rounded border border-slate-700 bg-slate-900/60 cursor-move" draggable="true" data-case-id="${c.id}">
                        <div class="text-xs font-bold text-gray-200">${_osintEscape(c.title || '')}</div>
                        <div class="text-[10px] text-gray-400">${_osintEscape(c.severity || '')} | ${_osintEscape(c.priority || '')} | Risk ${_osintEscape(c.top_ioc_risk || 0)}</div>
                    </div>
                `).join('') || '<div class="text-[10px] text-gray-500">Empty</div>';
            });

            document.querySelectorAll('#ir-section [draggable="true"][data-case-id]').forEach((card) => {
                if (card.dataset.dragBound === '1') return;
                card.dataset.dragBound = '1';
                card.addEventListener('dragstart', (e) => {
                    e.dataTransfer.setData('text/plain', card.getAttribute('data-case-id') || '');
                    e.dataTransfer.effectAllowed = 'move';
                });
            });

            document.querySelectorAll('#ir-section [id^="irKanban-"][data-status]').forEach((lane) => {
                if (lane.dataset.dropBound === '1') return;
                lane.dataset.dropBound = '1';
                lane.addEventListener('dragover', (e) => {
                    e.preventDefault();
                    e.dataTransfer.dropEffect = 'move';
                    lane.classList.add('ring-1', 'ring-red-500/40');
                });
                lane.addEventListener('dragleave', () => lane.classList.remove('ring-1', 'ring-red-500/40'));
                lane.addEventListener('drop', async (e) => {
                    e.preventDefault();
                    lane.classList.remove('ring-1', 'ring-red-500/40');
                    const caseId = Number(e.dataTransfer.getData('text/plain') || 0);
                    const status = lane.getAttribute('data-status') || 'open';
                    if (!caseId || !status) return;
                    await irMoveCaseToStatus(caseId, status);
                });
            });
        }

        async function irMoveCaseToStatus(caseId, status) {
            try {
                const res = await fetch(`/api/incidents/${caseId}/status`, {
                    method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({status})
                });
                const data = await res.json();
                if (!res.ok || !data.success) return titanAlert(data.error || 'فشل نقل القضية');
                if (currentIncidentCaseId === caseId) {
                    await irLoadCases();
                } else {
                    await Promise.all([irLoadCases(), irRefreshSummary()]);
                }
            } catch (e) {
                titanAlert(`فشل التحديث: ${e.message || e}`);
            }
        }

        function irBindFilters() {
            if (window.__irFiltersBound) return;
            window.__irFiltersBound = true;
            const q = document.getElementById('irCaseSearch');
            const st = document.getElementById('irFilterStatus');
            const sv = document.getElementById('irFilterSeverity');
            if (q) q.addEventListener('input', () => irLoadCases());
            if (st) st.addEventListener('change', () => irLoadCases());
            if (sv) sv.addEventListener('change', () => irLoadCases());
        }

        async function irRefreshSummary() {
            try {
                const res = await fetch('/api/incidents/summary');
                const data = await res.json();
                if (!res.ok || !data.success) return;
                const s = data.summary || {};
                const set = (id, value) => {
                    const el = document.getElementById(id);
                    if (el) el.textContent = String(value ?? 0);
                };
                set('irSumTotal', s.total || 0);
                set('irSumOpen', s.open || 0);
                set('irSumInvestigating', s.investigating || 0);
                set('irSumContained', s.contained || 0);
                set('irSumClosed', s.closed || 0);
                set('irSumCritical', s.critical || 0);
                set('irSumSlaBreached', s.sla_breached || 0);
                set('irSumAvgRisk', Number(s.avg_ioc_risk || 0).toFixed(1));
            } catch (_) {}
        }

        function irUpdateSelectedCaseMeta(caseObj) {
            const statusEl = document.getElementById('irSelectedMetaStatus');
            const sevEl = document.getElementById('irSelectedMetaSeverity');
            const ownerEl = document.getElementById('irSelectedMetaOwner');
            const slaEl = document.getElementById('irSelectedMetaSla');
            if (!caseObj) {
                if (statusEl) statusEl.textContent = 'Status: --';
                if (sevEl) sevEl.textContent = 'Severity/Priority: --';
                if (ownerEl) ownerEl.textContent = 'Owner: --';
                if (slaEl) slaEl.textContent = 'SLA: --';
                return;
            }
            if (statusEl) statusEl.textContent = `Status: ${caseObj.status || '--'} ${caseObj.sla_state === 'breached' ? '(SLA BREACH)' : ''}`;
            if (sevEl) sevEl.textContent = `Severity/Priority: ${caseObj.severity || '--'} / ${caseObj.priority || '--'}`;
            if (ownerEl) ownerEl.textContent = `Owner: ${caseObj.owner || '--'} | Source: ${caseObj.source || '--'}`;
            if (slaEl) slaEl.textContent = `SLA: ${caseObj.sla_minutes || '--'}m | Due: ${caseObj.due_at || '--'}`;
        }

        async function irCreateCase() {
            const title = (document.getElementById('irCaseTitle')?.value || '').trim();
            const severity = document.getElementById('irCaseSeverity')?.value || 'medium';
            const priority = document.getElementById('irCasePriority')?.value || 'p2';
            const category = document.getElementById('irCaseCategory')?.value || 'general';
            const source = document.getElementById('irCaseSource')?.value || 'manual';
            const owner = (document.getElementById('irCaseOwner')?.value || '').trim() || 'SOC';
            const sla_minutes = Number(document.getElementById('irCaseSla')?.value || 240);
            const description = (document.getElementById('irCaseDesc')?.value || '').trim();
            if (!title) return titanAlert('اكتب عنوان القضية أولاً.');

            const res = await fetch('/api/incidents/create', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({title, severity, priority, category, source, owner, sla_minutes, description})
            });
            const data = await res.json();
            if (!res.ok || !data.success) return titanAlert(data.error || 'فشل إنشاء القضية');

            document.getElementById('irCaseTitle').value = '';
            document.getElementById('irCaseDesc').value = '';
            document.getElementById('irCaseOwner').value = '';
            await irLoadCases();
            await irRefreshSummary();
        }

        async function irLoadCases() {
            const box = document.getElementById('irCasesList');
            if (!box) return;
            setResultLoading(box, 'Incident Cases', 'Loading cases...');

            const q = encodeURIComponent((document.getElementById('irCaseSearch')?.value || '').trim());
            const status = encodeURIComponent(document.getElementById('irFilterStatus')?.value || 'all');
            const severity = encodeURIComponent(document.getElementById('irFilterSeverity')?.value || 'all');

            const res = await fetch(`/api/incidents/list?q=${q}&status=${status}&severity=${severity}`);
            const data = await res.json();
            if (!data.success) {
                irSetActionButtonsEnabled(false);
                setResultError(box, 'Load failed');
                return;
            }

            irCasesCache = data.cases || [];
            const rows = irCasesCache;
            if (!rows.length) {
                currentIncidentCaseId = null;
                const tag = document.getElementById('irSelectedCase');
                if (tag) tag.innerText = 'لم يتم اختيار قضية';
                irSetActionButtonsEnabled(false);
                irUpdateSelectedCaseMeta(null);
                irRenderKanban([]);
                setResultList(box, 'Incident Cases', [], { badge: '0', emptyText: 'لا توجد قضايا مطابقة.' });
                await irRefreshSummary();
                return;
            }

            const hasSelected = rows.some((c) => c.id === currentIncidentCaseId);
            if (!hasSelected) currentIncidentCaseId = rows[0].id;

            const selected = rows.find(c => c.id === currentIncidentCaseId) || null;
            const tag = document.getElementById('irSelectedCase');
            if (tag) tag.innerText = `Case ID: ${currentIncidentCaseId}`;
            irUpdateSelectedCaseMeta(selected);

            setResultMarkup(
                box,
                'Incident Cases',
                rows.map(c => `
                <div class="p-2 rounded-lg border ${currentIncidentCaseId===c.id ? 'border-red-500 bg-red-900/20' : 'border-slate-700 bg-black/30'}">
                    <div class="flex items-start justify-between gap-2">
                        <button onclick="irSelectCase(${c.id})" class="text-left flex-1">
                            <div class="text-sm font-bold text-gray-200">${_osintEscape(c.title)}</div>
                            <div class="text-[10px] text-gray-400 mt-0.5">${_osintEscape(c.severity)} | ${_osintEscape(c.priority)} | ${_osintEscape(c.status)} | ${_osintEscape(c.category)}</div>
                            <div class="text-[10px] text-gray-500 mt-0.5">Owner: ${_osintEscape(c.owner || 'SOC')} | IOCs: ${_osintEscape(c.ioc_count || 0)} | Top Risk: ${_osintEscape(c.top_ioc_risk || 0)}</div>
                            <div class="text-[10px] ${c.recommended_priority && c.recommended_priority !== c.priority ? 'text-fuchsia-300' : 'text-gray-600'} mt-0.5">Auto Priority: ${_osintEscape(c.recommended_priority || c.priority || 'p2')}</div>
                        </button>
                        <span class="text-[10px] px-2 py-0.5 rounded border ${c.sla_state === 'breached' ? 'text-red-300 border-red-800/50 bg-red-900/20' : 'text-emerald-300 border-emerald-800/50 bg-emerald-900/20'}">${c.sla_state === 'breached' ? 'SLA BREACH' : 'SLA OK'}</span>
                    </div>
                </div>
            `).join(''),
                { badge: `${rows.length} Cases` }
            );

            irRenderKanban(rows);

            irSetActionButtonsEnabled(true);
            await Promise.all([irLoadIocs(), irLoadNotes(), irLoadEvidence(), irRefreshSummary()]);
        }

        async function irSelectCase(caseId) {
            currentIncidentCaseId = caseId;
            const tag = document.getElementById('irSelectedCase');
            if (tag) tag.innerText = `Case ID: ${caseId}`;
            irSetActionButtonsEnabled(true);
            await irLoadCases();
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
            await Promise.all([irLoadIocs(), irLoadNotes(), irLoadCases(), irRefreshSummary()]);
        }

        async function irLoadIocs() {
            const box = document.getElementById('irIocTimeline');
            if (!box || !currentIncidentCaseId) {
                irSetActionButtonsEnabled(false);
                return;
            }
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
                rows.map(r => {
                    const tone = Number(r.risk_score || 0) >= 70 ? 'text-red-300' : (Number(r.risk_score || 0) >= 40 ? 'text-amber-300' : 'text-emerald-300');
                    return `<span class="${tone} font-bold">${_osintEscape(r.ioc_type)}</span> <span class="font-mono" dir="ltr">${_osintEscape(r.ioc_value)}</span> <span class="text-[10px] text-gray-500">risk=${_osintEscape(r.risk_score)} | ${_osintEscape(r.created_at)}</span>`;
                }),
                { badge: `${rows.length} IOCs` }
            );
        }

        async function irAddNote() {
            if (!currentIncidentCaseId) return titanAlert('اختر قضية أولاً.');
            const note_type = document.getElementById('irNoteType')?.value || 'analysis';
            const note = (document.getElementById('irNoteText')?.value || '').trim();
            if (!note) return titanAlert('اكتب ملاحظة أولاً.');
            const res = await fetch(`/api/incidents/${currentIncidentCaseId}/notes`, {
                method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({note_type, note})
            });
            const data = await res.json();
            if (!res.ok || !data.success) return titanAlert(data.error || 'فشل إضافة الملاحظة');
            document.getElementById('irNoteText').value = '';
            await Promise.all([irLoadNotes(), irLoadCases()]);
        }

        async function irLoadNotes() {
            const box = document.getElementById('irNotesTimeline');
            if (!box || !currentIncidentCaseId) return;
            setResultLoading(box, 'Incident Notes', 'Loading timeline notes...');
            const res = await fetch(`/api/incidents/${currentIncidentCaseId}/notes`);
            const data = await res.json();
            if (!res.ok || !data.success) { setResultError(box, 'Failed'); return; }
            const rows = data.notes || [];
            if (!rows.length) {
                setResultList(box, 'Incident Notes', [], { badge: '0', emptyText: 'لا توجد ملاحظات حتى الآن.' });
                return;
            }
            setResultMarkup(
                box,
                'Incident Notes',
                rows.map((n) => `
                    <div class="mb-2 p-2 rounded border border-slate-700 bg-slate-900/40">
                        <div class="flex items-center justify-between gap-2">
                            <span class="text-orange-300 font-bold text-[11px]">${_osintEscape(n.note_type)}</span>
                            <span class="text-[10px] text-gray-500">${_osintEscape(n.created_at || '')}</span>
                        </div>
                        <div class="text-[10px] text-gray-400">by ${_osintEscape(n.created_by || 'unknown')}</div>
                        <div class="text-xs text-gray-200 mt-1 whitespace-pre-wrap">${_osintEscape(n.note || '')}</div>
                    </div>
                `).join(''),
                { badge: `${rows.length} Notes` }
            );
        }

        async function irUploadEvidence() {
            if (!currentIncidentCaseId) return titanAlert('اختر قضية أولاً.');
            const file = document.getElementById('irEvidenceFile')?.files?.[0];
            const note = (document.getElementById('irEvidenceNote')?.value || '').trim();
            if (!file) return titanAlert('اختر ملف دليل أولاً.');

            const form = new FormData();
            form.append('file', file);
            form.append('note', note);
            const res = await fetch(`/api/incidents/${currentIncidentCaseId}/evidence`, { method: 'POST', body: form });
            const data = await res.json();
            if (!res.ok || !data.success) return titanAlert(data.error || 'فشل رفع الدليل');

            const input = document.getElementById('irEvidenceFile');
            if (input) input.value = '';
            document.getElementById('irEvidenceNote').value = '';
            await Promise.all([irLoadEvidence(), irLoadNotes(), irLoadCases()]);
        }

        async function irLoadEvidence() {
            const box = document.getElementById('irEvidenceList');
            if (!box || !currentIncidentCaseId) return;
            setResultLoading(box, 'Evidence Locker', 'Loading evidence...');
            const res = await fetch(`/api/incidents/${currentIncidentCaseId}/evidence`);
            const data = await res.json();
            if (!res.ok || !data.success) { setResultError(box, 'Failed'); return; }
            const rows = data.evidence || [];
            if (!rows.length) {
                setResultList(box, 'Evidence Locker', [], { badge: '0', emptyText: 'لا يوجد أدلة مرفوعة.' });
                return;
            }
            setResultMarkup(
                box,
                'Evidence Locker',
                rows.map((e) => `
                    <div class="mb-2 p-2 rounded border border-slate-700 bg-slate-900/40">
                        <div class="text-emerald-300 font-bold text-xs">${_osintEscape(e.filename || 'evidence.bin')}</div>
                        <div class="text-[10px] text-gray-400">${_osintEscape(e.mime_type || '')} | ${_osintEscape(e.file_size || 0)} bytes | ${_osintEscape(e.created_at || '')}</div>
                        <div class="text-[10px] text-gray-500 font-mono break-all" dir="ltr">sha256: ${_osintEscape(e.file_hash || '')}</div>
                        <div class="text-xs text-gray-200 mt-1">${_osintEscape(e.note || '')}</div>
                    </div>
                `).join(''),
                { badge: `${rows.length} Files` }
            );
        }

        async function irUpdateStatus(status) {
            if (!currentIncidentCaseId) return titanAlert('اختر قضية أولاً.');
            try {
                const res = await fetch(`/api/incidents/${currentIncidentCaseId}/status`, {
                    method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({status})
                });
                const data = await res.json();
                if (!res.ok || !data.success) return titanAlert(data.error || 'فشل تحديث الحالة');
                titanAlert(`✅ تم تحديث الحالة إلى ${status}`);
                await irLoadCases();
            } catch (e) {
                titanAlert(`فشل تحديث الحالة: ${e.message || e}`);
            }
        }

        async function irRunAutoPriority() {
            if (!currentIncidentCaseId) return titanAlert('اختر قضية أولاً.');
            try {
                const res = await fetch(`/api/incidents/${currentIncidentCaseId}/auto-priority`, { method: 'POST' });
                const data = await res.json();
                if (!res.ok || !data.success) return titanAlert(data.error || 'فشل تشغيل Auto Priority');
                const msg = data.updated
                    ? `✅ تم رفع الأولوية تلقائياً ${data.from} -> ${data.to}`
                    : `ℹ️ لا حاجة للتغيير. الأولوية الحالية ${data.from} (الموصى ${data.recommended})`;
                titanAlert(msg);
                await irLoadCases();
            } catch (e) {
                titanAlert(`فشل Auto Priority: ${e.message || e}`);
            }
        }

        async function irExportReport(format = 'json') {
            if (!currentIncidentCaseId) return titanAlert('اختر قضية أولاً.');
            try {
                if (format === 'pdf') {
                    const resPdf = await fetch(`/api/incidents/${currentIncidentCaseId}/report.pdf`);
                    if (!resPdf.ok) {
                        let msg = 'فشل تصدير PDF';
                        try {
                            const err = await resPdf.json();
                            msg = err.error || msg;
                        } catch (_) {}
                        return titanAlert(msg);
                    }
                    const blob = await resPdf.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `incident-${currentIncidentCaseId}-report.pdf`;
                    a.click();
                    URL.revokeObjectURL(url);
                    return titanAlert('✅ تم تصدير تقرير PDF بنجاح');
                }

                const res = await fetch(`/api/incidents/${currentIncidentCaseId}/report`);
                const data = await res.json();
                if (!res.ok || !data.success) return titanAlert(data.error || 'فشل التصدير');
                const blob = new Blob([JSON.stringify(data.report, null, 2)], {type:'application/json'});
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `incident-${currentIncidentCaseId}-report.json`;
                a.click();
                URL.revokeObjectURL(url);
                titanAlert('✅ تم تصدير التقرير بنجاح');
            } catch (e) {
                titanAlert(`فشل تصدير التقرير: ${e.message || e}`);
            }
        }

        async function irInitSection() {
            irBindFilters();
            await irLoadCases();
        }

        let currentForensicsSessionId = null;
        let currentForensicsSessionData = null;

        async function forensicsRefreshSummary() {
            try {
                const res = await fetch('/api/forensics/summary');
                const data = await res.json();
                if (!res.ok || !data.success) return;
                const s = data.summary || {};
                const set = (id, val) => {
                    const el = document.getElementById(id);
                    if (el) el.textContent = String(val ?? 0);
                };
                set('forensicsSumSessions', s.sessions || 0);
                set('forensicsSumHighRisk', s.high_risk_sessions || 0);
                set('forensicsSumEntropy', Number(s.avg_entropy || 0).toFixed(2));
                set('forensicsSumArtifacts', s.artifacts || 0);
            } catch (_) {}
        }

        async function forensicsTriage() {
            const file = document.getElementById('forensicsFile')?.files?.[0];
            const out = document.getElementById('forensicsResult');
            const minStringLen = Number(document.getElementById('forensicsMinStringLen')?.value || 6);
            if (!file || !out) return titanAlert('اختر ملفاً أولاً.');
            setResultLoading(out, 'Forensics Triage', 'Analyzing evidence...');

            const form = new FormData();
            form.append('file', file);
            form.append('min_string_len', String(minStringLen));
            const res = await fetch('/api/forensics/triage', { method:'POST', body: form });
            const data = await res.json();
            if (!res.ok || !data.success) {
                setResultError(out, data.error || 'Triage failed');
                return;
            }

            currentForensicsSessionId = data.session_id || null;
            const riskScore = Number(data.risk_score || 0);
            const riskTone = riskScore >= 70 ? 'danger' : (riskScore >= 40 ? 'warn' : 'safe');

            const infoRows = [
                { label: 'Filename', value: data.filename || '', tone: 'info' },
                { label: 'Type', value: data.file_type || 'unknown', tone: 'info' },
                { label: 'Risk', value: `${riskScore}/100`, tone: riskTone },
                { label: 'Entropy', value: Number(data.entropy || 0).toFixed(3), tone: 'warn' },
                { label: 'Size', value: `${data.size_bytes || 0} bytes`, tone: 'info' },
                { label: 'Session ID', value: data.session_id || '-', tone: 'info' },
            ];

            const iocCounts = data.ioc_counts || {};
            const topStrings = (data.strings_preview || []).map((s) => _resultEscape(s)).join('<br>') || 'N/A';
            const metadataObj = data.metadata || {};

            setResultMarkup(
                out,
                'Forensics Triage',
                `<div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                    ${infoRows.map((row) => `<div class="p-2 rounded border border-slate-700 bg-black/40 text-xs"><div class="text-gray-400">${_resultEscape(row.label)}</div><div class="font-bold text-gray-100">${_resultEscape(row.value)}</div></div>`).join('')}
                </div>
                <div class="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
                    <div class="p-2 rounded border border-slate-700 bg-slate-900/60 text-xs">
                        <div class="text-cyan-300 font-bold mb-1">IOC Counts</div>
                        <div class="text-gray-200">IPs: ${_resultEscape(iocCounts.ipv4 || 0)} | URLs: ${_resultEscape(iocCounts.urls || 0)} | Emails: ${_resultEscape(iocCounts.emails || 0)}</div>
                        <div class="text-gray-200">Domains: ${_resultEscape(iocCounts.domains || 0)} | Hashes: ${_resultEscape(iocCounts.hashes || 0)}</div>
                    </div>
                    <div class="p-2 rounded border border-slate-700 bg-slate-900/60 text-xs">
                        <div class="text-amber-300 font-bold mb-1">File Metadata</div>
                        <div class="text-gray-200 whitespace-pre-wrap">${_resultEscape(JSON.stringify(metadataObj, null, 2))}</div>
                    </div>
                </div>
                <div class="mt-2 p-2 rounded border border-slate-700 bg-slate-900/60 text-xs">
                    <div class="text-emerald-300 font-bold mb-1">Printable Strings Preview</div>
                    <div class="text-gray-200 whitespace-pre-wrap" dir="ltr">${topStrings}</div>
                </div>`,
                { badge: riskTone === 'danger' ? 'High Risk' : (riskTone === 'warn' ? 'Medium Risk' : 'Low Risk'), riskScore }
            );

            await Promise.all([forensicsLoadHistory(), forensicsRefreshSummary()]);
            if (currentForensicsSessionId) await forensicsLoadSessionDetail(currentForensicsSessionId);
        }

        async function forensicsExtractIocs() {
            const text = (document.getElementById('forensicsTextInput')?.value || '').trim();
            const out = document.getElementById('forensicsIocResult');
            if (!out) return;
            if (!text) return titanAlert('الصق نص أو لوج أولاً.');
            setResultLoading(out, 'IOC Extractor', 'Extracting indicators...');

            const res = await fetch('/api/forensics/extract-iocs', {
                method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({text})
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                setResultError(out, data.error || 'Extraction failed');
                return;
            }

            const i = data.iocs || {};
            setResultMarkup(
                out,
                'IOC Extractor',
                `<div class="text-xs space-y-2">
                    <div>Counts: IP=${_resultEscape(i.ipv4?.length || 0)} | URL=${_resultEscape(i.urls?.length || 0)} | Email=${_resultEscape(i.emails?.length || 0)} | Domain=${_resultEscape(i.domains?.length || 0)} | Hash=${_resultEscape(i.hashes?.length || 0)}</div>
                    <div class="p-2 rounded border border-slate-700 bg-slate-900/60"><div class="text-cyan-300 font-bold">IPs</div><div class="text-gray-200 font-mono">${(i.ipv4 || []).map(_resultEscape).join('<br>') || 'N/A'}</div></div>
                    <div class="p-2 rounded border border-slate-700 bg-slate-900/60"><div class="text-amber-300 font-bold">URLs</div><div class="text-gray-200 font-mono">${(i.urls || []).map(_resultEscape).join('<br>') || 'N/A'}</div></div>
                </div>`,
                { badge: 'Extracted' }
            );
        }

        async function forensicsLoadHistory() {
            const box = document.getElementById('forensicsHistory');
            if (!box) return;
            setResultLoading(box, 'Forensics Sessions', 'Loading sessions...');

            const risk = (document.getElementById('forensicsFilterRisk')?.value || 'all').trim();
            const fileType = (document.getElementById('forensicsFilterType')?.value || '').trim();
            const dateFrom = (document.getElementById('forensicsFilterFrom')?.value || '').trim();
            const dateTo = (document.getElementById('forensicsFilterTo')?.value || '').trim();
            const qs = new URLSearchParams();
            if (risk && risk !== 'all') qs.set('risk', risk);
            if (fileType) qs.set('file_type', fileType);
            if (dateFrom) qs.set('date_from', dateFrom);
            if (dateTo) qs.set('date_to', dateTo);

            const url = qs.toString() ? `/api/forensics/history?${qs.toString()}` : '/api/forensics/history';
            const res = await fetch(url);
            const data = await res.json();
            if (!res.ok || !data.success) {
                setResultError(box, data.error || 'Load failed');
                return;
            }
            const rows = data.sessions || [];
            if (!rows.length) {
                setResultList(box, 'Forensics Sessions', [], { badge: '0', emptyText: 'لا يوجد تحليل سابق بعد.' });
                return;
            }

            if (!currentForensicsSessionId) currentForensicsSessionId = rows[0].id;
            setResultMarkup(
                box,
                'Forensics Sessions',
                rows.map((r) => `
                    <button onclick="forensicsLoadSessionDetail(${r.id})" class="w-full text-right mb-2 p-2 rounded border ${currentForensicsSessionId===r.id ? 'border-teal-500 bg-teal-900/20' : 'border-slate-700 bg-slate-900/40'}">
                        <div class="text-xs font-bold text-gray-200">${_osintEscape(r.filename || 'unknown')}</div>
                        <div class="text-[10px] text-gray-500">#${_osintEscape(r.id)} | ${_osintEscape(r.file_type || 'unknown')} | risk ${_osintEscape(r.risk_score || 0)} | ${_osintEscape(r.created_at || '')}</div>
                    </button>
                `).join(''),
                { badge: `${rows.length} Sessions` }
            );
        }

        async function forensicsApplyHistoryFilters() {
            await forensicsLoadHistory();
        }

        async function forensicsResetHistoryFilters() {
            const risk = document.getElementById('forensicsFilterRisk');
            const type = document.getElementById('forensicsFilterType');
            const from = document.getElementById('forensicsFilterFrom');
            const to = document.getElementById('forensicsFilterTo');
            if (risk) risk.value = 'all';
            if (type) type.value = '';
            if (from) from.value = '';
            if (to) to.value = '';
            await forensicsLoadHistory();
        }

        async function forensicsLoadSessionDetail(sessionId) {
            currentForensicsSessionId = sessionId;
            const box = document.getElementById('forensicsSessionDetail');
            if (!box) return;
            setResultLoading(box, 'Session Details', 'Loading session...');

            const res = await fetch(`/api/forensics/session/${sessionId}`);
            const data = await res.json();
            if (!res.ok || !data.success) {
                setResultError(box, data.error || 'Failed');
                return;
            }
            currentForensicsSessionData = data;
            const s = data.session || {};
            const m = data.metadata || {};
            const c = data.ioc_counts || {};

            setResultMarkup(
                box,
                'Session Details',
                `<div class="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                    <div class="p-2 rounded border border-slate-700 bg-slate-900/60"><div class="text-gray-400">Filename</div><div class="text-gray-100 font-bold">${_resultEscape(s.filename || '')}</div></div>
                    <div class="p-2 rounded border border-slate-700 bg-slate-900/60"><div class="text-gray-400">Type</div><div class="text-gray-100 font-bold">${_resultEscape(s.file_type || '')}</div></div>
                    <div class="p-2 rounded border border-slate-700 bg-slate-900/60"><div class="text-gray-400">Risk</div><div class="text-red-300 font-bold">${_resultEscape(s.risk_score || 0)}/100</div></div>
                    <div class="p-2 rounded border border-slate-700 bg-slate-900/60"><div class="text-gray-400">Entropy</div><div class="text-amber-300 font-bold">${_resultEscape(Number(s.entropy || 0).toFixed(3))}</div></div>
                </div>
                <div class="mt-2 p-2 rounded border border-slate-700 bg-black/40 text-xs">
                    <div class="text-indigo-300 font-bold mb-1">IOC Counts</div>
                    <div>IP=${_resultEscape(c.ipv4 || 0)} | URL=${_resultEscape(c.urls || 0)} | Email=${_resultEscape(c.emails || 0)} | Domain=${_resultEscape(c.domains || 0)} | Hash=${_resultEscape(c.hashes || 0)}</div>
                </div>
                <div class="mt-2 p-2 rounded border border-slate-700 bg-black/40 text-xs">
                    <div class="text-cyan-300 font-bold mb-1">Metadata</div>
                    <div class="font-mono whitespace-pre-wrap" dir="ltr">${_resultEscape(JSON.stringify(m, null, 2))}</div>
                </div>`,
                { badge: `#${sessionId}` }
            );
            await forensicsLoadHistory();
        }

        async function forensicsExportSession(format) {
            if (!currentForensicsSessionId) return titanAlert('اختر جلسة أولاً.');
            try {
                if (format === 'pdf') {
                    const res = await fetch(`/api/forensics/session/${currentForensicsSessionId}/report.pdf`);
                    if (!res.ok) {
                        const data = await res.json().catch(() => ({}));
                        return titanAlert(data.error || 'فشل تصدير PDF');
                    }
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `forensics-${currentForensicsSessionId}.pdf`;
                    a.click();
                    URL.revokeObjectURL(url);
                    return titanAlert('✅ تم تصدير تقرير PDF');
                }

                const res = await fetch(`/api/forensics/session/${currentForensicsSessionId}/report`);
                const data = await res.json();
                if (!res.ok || !data.success) return titanAlert(data.error || 'فشل التصدير');
                const blob = new Blob([JSON.stringify(data.report, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `forensics-${currentForensicsSessionId}.json`;
                a.click();
                URL.revokeObjectURL(url);
                titanAlert('✅ تم تصدير تقرير JSON');
            } catch (e) {
                titanAlert(`فشل التصدير: ${e.message || e}`);
            }
        }

        async function forensicsCreateIncidentFromSession() {
            if (!currentForensicsSessionId) return titanAlert('اختر جلسة أولاً.');
            try {
                const res = await fetch(`/api/forensics/session/${currentForensicsSessionId}/create-incident`, { method: 'POST' });
                const data = await res.json();
                if (!res.ok || !data.success) return titanAlert(data.error || 'فشل إنشاء Incident');
                titanAlert(`✅ تم إنشاء Incident #${data.case_id} بالأولوية ${data.priority}`);
                if (typeof irInitSection === 'function') irInitSection();
            } catch (e) {
                titanAlert(`فشل إنشاء Incident: ${e.message || e}`);
            }
        }

        async function forensicsInitSection() {
            await Promise.all([forensicsRefreshSummary(), forensicsLoadHistory()]);
            if (currentForensicsSessionId) await forensicsLoadSessionDetail(currentForensicsSessionId);
        }

        const SE_INTEL_STORAGE_KEY = 'titan_se_intel_board';
        const SE_PLAYBOOK_STORAGE_KEY = 'titan_se_playbook';
        const SE_QUIZ_STORAGE_KEY = 'titan_se_quiz_state';

        function _seRenderTrendBars(points) {
            const host = document.getElementById('seRiskTrendBars');
            const meta = document.getElementById('seRiskTrendMeta');
            if (!host || !meta) return;
            const rows = Array.isArray(points) ? points : [];
            if (!rows.length) {
                host.innerHTML = '<div class="text-xs text-gray-500 col-span-7">لا توجد بيانات Trend كافية بعد.</div>';
                meta.textContent = 'Trend: no snapshots yet';
                return;
            }

            const visible = rows.slice(-7);
            host.innerHTML = visible.map((p) => {
                const score = Math.max(0, Math.min(100, Number(p.risk_index || 0)));
                const tone = score >= 70 ? 'bg-red-500' : (score >= 40 ? 'bg-amber-500' : 'bg-emerald-500');
                const dayLabel = String(p.day || '').slice(5);
                return `
                    <div class="rounded border border-slate-700 bg-black/40 p-2 flex flex-col gap-2 items-center justify-end">
                        <div class="w-full h-16 rounded bg-slate-800/80 border border-slate-700 overflow-hidden flex items-end">
                            <div class="w-full ${tone}" style="height:${score}%;"></div>
                        </div>
                        <div class="text-[10px] text-gray-400">${_resultEscape(dayLabel || '--')}</div>
                        <div class="text-[10px] text-gray-300">${score.toFixed(1)}</div>
                    </div>
                `;
            }).join('');

            const first = Number(visible[0]?.risk_index || 0);
            const last = Number(visible[visible.length - 1]?.risk_index || 0);
            const delta = (last - first).toFixed(1);
            meta.textContent = `Trend delta (last 7): ${delta >= 0 ? '+' : ''}${delta}`;
        }

        function _seComputeLocalRiskSnapshot() {
            const items = _seGetIntelItems().map((it) => ({ ...it, risk_score: Number(it.risk_score || _seIntelRiskScore(it)) }));
            const total = items.length;
            const high = items.filter((i) => Number(i.risk_score || 0) >= 70).length;
            const medium = items.filter((i) => Number(i.risk_score || 0) >= 40 && Number(i.risk_score || 0) < 70).length;
            const low = items.filter((i) => Number(i.risk_score || 0) < 40).length;
            const avg = total ? (items.reduce((acc, it) => acc + Number(it.risk_score || 0), 0) / total) : 0;
            return {
                total_items: total,
                high_count: high,
                medium_count: medium,
                low_count: low,
                avg_risk: Number(avg.toFixed(2))
            };
        }

        async function seSyncRiskSnapshot() {
            const payload = _seComputeLocalRiskSnapshot();
            try {
                await fetch('/api/social/risk/snapshot', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
            } catch (_) {}
        }

        async function seRefreshDashboard() {
            try {
                const [quizRes, trendRes] = await Promise.all([
                    fetch('/api/social/quiz/stats'),
                    fetch('/api/social/risk/trend')
                ]);
                const quizData = await quizRes.json();
                const trendData = await trendRes.json();

                const quizAccuracyEl = document.getElementById('seDashQuizAccuracy');
                const quizAnswersEl = document.getElementById('seDashQuizAnswers');
                const lastScoreEl = document.getElementById('seDashLastScore');
                const riskIndexEl = document.getElementById('seDashRiskIndex');

                if (quizData?.success) {
                    if (quizAccuracyEl) quizAccuracyEl.textContent = `${Number(quizData.accuracy || 0).toFixed(1)}%`;
                    if (quizAnswersEl) quizAnswersEl.textContent = String(quizData.total_answers || 0);
                    if (lastScoreEl) lastScoreEl.textContent = String(quizData.last_score || 0);
                }

                if (trendData?.success) {
                    const latest = trendData.latest || {};
                    if (riskIndexEl) riskIndexEl.textContent = Number(latest.risk_index || 0).toFixed(1);
                    _seRenderTrendBars(trendData.points || []);
                }
            } catch (_) {
                const meta = document.getElementById('seRiskTrendMeta');
                if (meta) meta.textContent = 'Trend: failed to load';
            }
        }

        const SE_QUIZ_BANK = [
            {
                question: 'طلبت رسالة عاجلة إدخال OTP لحماية الحساب. ما التصرف الصحيح؟',
                options: ['إرسال OTP لتسريع الإغلاق', 'الرفض والتحقق عبر قناة رسمية', 'إرسال OTP جزئي فقط'],
                answer: 1,
                explain: 'OTP سرّي ولا يُشارك. يتم التحقق عبر القنوات المعتمدة فقط.'
            },
            {
                question: 'إيميل يبدو من البنك لكن النطاق مختلف بحرف واحد. التقييم الأدق؟',
                options: ['آمن غالباً', 'مؤشر تصيد قوي', 'مجرد خطأ إملائي'],
                answer: 1,
                explain: 'النطاقات المشابهة Lookalike من أكثر تكتيكات التصيد شيوعاً.'
            },
            {
                question: 'رسالة من مدير تطلب تجاوز السياسة وإرسال بيانات عميل فوراً. ما الخطوة الأولى؟',
                options: ['التنفيذ لأن المرسل مدير', 'التحقق الثنائي ورفع الحالة', 'تجاهل الرسالة بلا توثيق'],
                answer: 1,
                explain: 'انتحال السلطة يتطلب تحقق ثنائي ومسار تصعيد رسمي.'
            }
        ];

        function _seConfidenceScore(level) {
            if (level === 'high') return 3;
            if (level === 'medium') return 2;
            return 1;
        }

        function _seCategoryWeight(category) {
            if (category === 'infrastructure') return 3;
            if (category === 'identity') return 2;
            if (category === 'behavior') return 2;
            return 1;
        }

        function _seTextRiskBoost(text) {
            const t = String(text || '').toLowerCase();
            const keywords = ['otp', 'password', 'urgent', 'wire', 'invoice', 'credentials', 'bypass', 'executive'];
            let boost = 0;
            keywords.forEach((k) => {
                if (t.includes(k)) boost += 7;
            });
            return Math.min(boost, 35);
        }

        function _seIntelRiskScore(item) {
            const confidenceBase = _seConfidenceScore(item.confidence) * 18;
            const categoryBase = _seCategoryWeight(item.category) * 10;
            const textBoost = _seTextRiskBoost(`${item.subject || ''} ${item.note || ''}`);
            return Math.min(100, confidenceBase + categoryBase + textBoost);
        }

        function _seRiskBand(score) {
            if (score >= 70) return { label: 'HIGH', cls: 'text-red-300 border-red-800/50 bg-red-900/20' };
            if (score >= 40) return { label: 'MEDIUM', cls: 'text-amber-300 border-amber-800/50 bg-amber-900/20' };
            return { label: 'LOW', cls: 'text-emerald-300 border-emerald-800/50 bg-emerald-900/20' };
        }

        function _seGetIntelItems() {
            try {
                return JSON.parse(localStorage.getItem(SE_INTEL_STORAGE_KEY) || '[]');
            } catch (_) {
                return [];
            }
        }

        function _seSetIntelItems(items) {
            localStorage.setItem(SE_INTEL_STORAGE_KEY, JSON.stringify((items || []).slice(0, 300)));
        }

        function _seGetPlaybookItems() {
            try {
                return JSON.parse(localStorage.getItem(SE_PLAYBOOK_STORAGE_KEY) || '[]');
            } catch (_) {
                return [];
            }
        }

        function _seSetPlaybookItems(items) {
            localStorage.setItem(SE_PLAYBOOK_STORAGE_KEY, JSON.stringify((items || []).slice(0, 120)));
        }

        function seAnalyzeSignal() {
            const out = document.getElementById('seSignalResult');
            if (!out) return;

            const channel = document.getElementById('seSignalChannel')?.value || 'email';
            const senderTrust = document.getElementById('seSignalSenderTrust')?.value || 'known';
            const urgency = document.getElementById('seSignalUrgency')?.value || 'medium';
            const hasLink = !!document.getElementById('seSignalHasLink')?.checked;
            const hasSensitiveReq = !!document.getElementById('seSignalSensitiveReq')?.checked;
            const hasPolicyBypass = !!document.getElementById('seSignalPolicyBypass')?.checked;

            let score = 12;
            if (channel === 'social_dm') score += 10;
            if (channel === 'phone') score += 8;
            if (senderTrust === 'unknown') score += 20;
            if (senderTrust === 'spoofed') score += 35;
            if (urgency === 'medium') score += 12;
            if (urgency === 'high') score += 25;
            if (hasLink) score += 14;
            if (hasSensitiveReq) score += 28;
            if (hasPolicyBypass) score += 20;
            score = Math.min(100, score);

            const band = _seRiskBand(score);
            const actions = [];
            if (score >= 70) {
                actions.push('اعزل الطلب فوراً ولا تستجب له.');
                actions.push('ارفع بلاغاً عاجلاً إلى SOC مع كل المؤشرات.');
                actions.push('تحقق من الحساب/الجهاز لاحتمال اختراق سابق.');
            } else if (score >= 40) {
                actions.push('أوقف التنفيذ لحين تحقق ثنائي عبر قناة رسمية.');
                actions.push('وثّق الأدلة (لقطة شاشة، وقت، مرسل).');
            } else {
                actions.push('استمر بحذر واتبع سياسة التحقق القياسية.');
                actions.push('راقب أي تغيّر مفاجئ في سلوك الرسائل.');
            }

            setResultMarkup(
                out,
                'Threat Signal Analyzer',
                `<div class="space-y-2">
                    <div class="flex items-center justify-between">
                        <span class="text-gray-300">Risk Score</span>
                        <span class="px-2 py-0.5 rounded border ${band.cls} font-bold">${band.label} - ${score}/100</span>
                    </div>
                    <div class="h-2 rounded bg-slate-800 border border-slate-700 overflow-hidden">
                        <div style="width:${score}%;" class="h-full ${score >= 70 ? 'bg-red-500' : (score >= 40 ? 'bg-amber-500' : 'bg-emerald-500')}"></div>
                    </div>
                    <div class="text-gray-200 text-xs">${actions.map(a => `• ${_resultEscape(a)}`).join('<br>')}</div>
                </div>`,
                { badge: band.label }
            );
        }

        async function seGenerateScenario() {
            const scenario_type = document.getElementById('seScenarioType')?.value || 'phishing_email';
            const sector = document.getElementById('seScenarioSector')?.value || 'banking';
            const pressure = document.getElementById('seScenarioPressure')?.value || 'normal';
            const out = document.getElementById('seScenarioResult');
            if (!out) return;
            setResultLoading(out, 'SE Scenario Lab', 'Generating defensive scenario...');
            try {
                const res = await fetch('/api/social/simulate', {
                    method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({scenario_type, sector})
                });
                const data = await res.json();
                if (!data.success) { setResultError(out, data.error || 'Failed'); return; }

                const difficultyRaw = String(data.difficulty || 'medium').toLowerCase();
                const difficulty = pressure === 'critical' ? 'critical' : (pressure === 'high' && difficultyRaw === 'medium' ? 'high' : difficultyRaw);
                const difficultyEl = document.getElementById('seScenarioDifficulty');
                if (difficultyEl) {
                    difficultyEl.textContent = `Difficulty: ${difficulty.toUpperCase()}`;
                }

                const html = `
                    <div class="space-y-2">
                        <div class="text-pink-300 font-bold">${_resultEscape(data.title || 'Scenario')}</div>
                        <div class="text-gray-100">${_resultEscape(data.scenario || '')}</div>
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                            <div class="rounded border border-slate-700 p-2 bg-slate-900/60">
                                <div class="text-[11px] text-amber-300 font-bold mb-1">Attacker Goal</div>
                                <div class="text-xs text-gray-200">${_resultEscape(data.attacker_goal || 'N/A')}</div>
                            </div>
                            <div class="rounded border border-slate-700 p-2 bg-slate-900/60">
                                <div class="text-[11px] text-red-300 font-bold mb-1">Potential Impact</div>
                                <div class="text-xs text-gray-200">${_resultEscape(data.impact || 'N/A')}</div>
                            </div>
                        </div>
                        <div class="rounded border border-slate-700 p-2 bg-slate-900/60">
                            <div class="text-[11px] text-rose-300 font-bold mb-1">Red Flags</div>
                            <div class="text-xs text-gray-200">${(data.red_flags || []).map((x) => `• ${_resultEscape(x)}`).join('<br>') || 'N/A'}</div>
                        </div>
                        <div class="rounded border border-slate-700 p-2 bg-slate-900/60">
                            <div class="text-[11px] text-emerald-300 font-bold mb-1">Recommended Response</div>
                            <div class="text-xs text-gray-200">${(data.defense_actions || []).map((x) => `• ${_resultEscape(x)}`).join('<br>') || 'N/A'}</div>
                        </div>
                        <div class="rounded border border-slate-700 p-2 bg-slate-900/60">
                            <div class="text-[11px] text-cyan-300 font-bold mb-1">Safe Reply Template</div>
                            <div class="text-xs text-gray-100">${_resultEscape(data.safe_reply_template || 'N/A')}</div>
                        </div>
                    </div>`;

                setResultMarkup(out, 'SE Scenario Lab', html, { badge: 'Generated' });
            } catch (e) {
                setResultError(out, e.message || 'Failed to generate scenario');
            }
        }

        function seUpdateIntelSummary(items) {
            const rows = items || [];
            let high = 0, medium = 0, low = 0;
            rows.forEach((it) => {
                const band = _seRiskBand(Number(it.risk_score || 0)).label;
                if (band === 'HIGH') high += 1;
                else if (band === 'MEDIUM') medium += 1;
                else low += 1;
            });
            const totalEl = document.getElementById('seIntelTotal');
            const highEl = document.getElementById('seIntelHighRisk');
            const mediumEl = document.getElementById('seIntelMediumRisk');
            const lowEl = document.getElementById('seIntelLowRisk');
            if (totalEl) totalEl.textContent = `Total: ${rows.length}`;
            if (highEl) highEl.textContent = `High Risk: ${high}`;
            if (mediumEl) mediumEl.textContent = `Medium Risk: ${medium}`;
            if (lowEl) lowEl.textContent = `Low Risk: ${low}`;
        }

        function seLoadIntelBoard() {
            const box = document.getElementById('seIntelBoardResult');
            if (!box) return;

            const search = (document.getElementById('seIntelSearch')?.value || '').trim().toLowerCase();
            const confFilter = document.getElementById('seIntelFilterConfidence')?.value || 'all';
            const catFilter = document.getElementById('seIntelFilterCategory')?.value || 'all';

            const allItems = _seGetIntelItems().map((it, idx) => ({ ...it, __index: idx, risk_score: Number(it.risk_score || _seIntelRiskScore(it)) }));
            seUpdateIntelSummary(allItems);

            const items = allItems.filter((it) => {
                if (confFilter !== 'all' && it.confidence !== confFilter) return false;
                if (catFilter !== 'all' && it.category !== catFilter) return false;
                if (search) {
                    const hay = `${it.subject || ''} ${it.source || ''} ${it.note || ''}`.toLowerCase();
                    if (!hay.includes(search)) return false;
                }
                return true;
            });

            if (!items.length) {
                box.innerHTML = '<div class="text-gray-500">لا توجد نتائج مطابقة. غيّر الفلاتر أو أضف ملاحظة جديدة.</div>';
                return;
            }

            box.innerHTML = items.map((it) => {
                const idx = Number(it.__index);
                const band = _seRiskBand(Number(it.risk_score || 0));
                return `
                    <div class="mb-2 p-2 rounded border border-slate-700 bg-slate-900/40">
                        <div class="flex items-center justify-between gap-2">
                            <div class="text-pink-300 font-bold">${_osintEscape(it.subject || 'unknown')}</div>
                            <div class="flex items-center gap-2">
                                <span class="text-[10px] px-2 py-0.5 rounded border ${band.cls}">${band.label} ${_osintEscape(String(it.risk_score || 0))}</span>
                                <button onclick="seDeleteIntelItem(${idx})" class="text-red-400 text-[10px]">حذف</button>
                            </div>
                        </div>
                        <div class="text-[10px] text-gray-400 mt-1">${_osintEscape(it.category)} | ${_osintEscape(it.confidence)} | ${_osintEscape(it.source)} | ${_osintEscape(it.created_at)}</div>
                        <div class="text-gray-200 mt-1 whitespace-pre-wrap">${_osintEscape(it.note || '')}</div>
                    </div>
                `;
            }).join('');
        }

        function seAddIntelItem() {
            const subject = (document.getElementById('seIntelSubject')?.value || '').trim();
            const source = (document.getElementById('seIntelSource')?.value || '').trim();
            const category = document.getElementById('seIntelCategory')?.value || 'message';
            const confidence = document.getElementById('seIntelConfidence')?.value || 'medium';
            const note = (document.getElementById('seIntelNote')?.value || '').trim();
            if (!subject || !note) return titanAlert('اكتب Subject والملاحظة أولاً.');

            const items = _seGetIntelItems();
            const duplicate = items.find((it) =>
                String(it.subject || '').toLowerCase() === subject.toLowerCase() &&
                String(it.note || '').toLowerCase() === note.toLowerCase()
            );
            if (duplicate) return titanAlert('هذه المعلومة موجودة مسبقاً.');

            const entry = {
                subject,
                source: source || 'unknown',
                category,
                confidence,
                note,
                score: _seConfidenceScore(confidence),
                risk_score: 0,
                created_at: new Date().toISOString()
            };
            entry.risk_score = _seIntelRiskScore(entry);

            items.unshift(entry);
            _seSetIntelItems(items);

            document.getElementById('seIntelSubject').value = '';
            document.getElementById('seIntelSource').value = '';
            document.getElementById('seIntelNote').value = '';
            seLoadIntelBoard();
            seSyncRiskSnapshot().then(seRefreshDashboard);
        }

        function seDeleteIntelItem(index) {
            const items = _seGetIntelItems();
            if (index < 0 || index >= items.length) return;
            items.splice(index, 1);
            _seSetIntelItems(items);
            seLoadIntelBoard();
            seSyncRiskSnapshot().then(seRefreshDashboard);
        }

        function seSortIntelBoard() {
            const items = _seGetIntelItems();
            items.forEach((it) => { it.risk_score = Number(it.risk_score || _seIntelRiskScore(it)); });
            items.sort((a, b) => {
                if ((Number(b.risk_score) || 0) !== (Number(a.risk_score) || 0)) return (Number(b.risk_score) || 0) - (Number(a.risk_score) || 0);
                return String(b.created_at || '').localeCompare(String(a.created_at || ''));
            });
            _seSetIntelItems(items);
            seLoadIntelBoard();
            titanAlert('تم ترتيب المعلومات حسب المخاطرة ثم الزمن.');
            seSyncRiskSnapshot().then(seRefreshDashboard);
        }

        function seExportIntelBoard() {
            const items = _seGetIntelItems().map((it) => ({ ...it, risk_score: Number(it.risk_score || _seIntelRiskScore(it)) }));
            const payload = {
                exported_at: new Date().toISOString(),
                total_items: items.length,
                summary: {
                    high: items.filter(i => Number(i.risk_score || 0) >= 70).length,
                    medium: items.filter(i => Number(i.risk_score || 0) >= 40 && Number(i.risk_score || 0) < 70).length,
                    low: items.filter(i => Number(i.risk_score || 0) < 40).length
                },
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
            localStorage.removeItem(SE_INTEL_STORAGE_KEY);
            seLoadIntelBoard();
            seSyncRiskSnapshot().then(seRefreshDashboard);
        }

        function seLoadPlaybook() {
            const box = document.getElementById('sePlaybookResult');
            if (!box) return;
            const rows = _seGetPlaybookItems();
            if (!rows.length) {
                box.innerHTML = '<div class="text-gray-500">لا توجد خطوات بعد. أضف خطوة استجابة.</div>';
                return;
            }
            box.innerHTML = rows.map((step, idx) => `
                <div class="mb-2 p-2 rounded border border-slate-700 bg-slate-900/40">
                    <div class="flex items-center justify-between gap-2">
                        <div class="text-emerald-300 font-bold">${_osintEscape(step.phase || 'detect')}</div>
                        <button onclick="seDeletePlaybookStep(${idx})" class="text-red-400 text-[10px]">حذف</button>
                    </div>
                    <div class="text-[10px] text-gray-400 mt-1">Owner: ${_osintEscape(step.owner || 'SOC')} | ETA: ${_osintEscape(step.eta || 'N/A')} | ${_osintEscape(step.created_at || '')}</div>
                    <div class="text-gray-200 mt-1">${_osintEscape(step.action || '')}</div>
                </div>
            `).join('');
        }

        function seAddPlaybookStep() {
            const phase = document.getElementById('sePlaybookPhase')?.value || 'detect';
            const owner = (document.getElementById('sePlaybookOwner')?.value || '').trim() || 'SOC';
            const eta = (document.getElementById('sePlaybookEta')?.value || '').trim() || 'N/A';
            const action = (document.getElementById('sePlaybookAction')?.value || '').trim();
            if (!action) return titanAlert('اكتب خطوة الاستجابة أولاً.');

            const rows = _seGetPlaybookItems();
            rows.push({ phase, owner, eta, action, created_at: new Date().toISOString() });
            _seSetPlaybookItems(rows);

            document.getElementById('sePlaybookOwner').value = '';
            document.getElementById('sePlaybookEta').value = '';
            document.getElementById('sePlaybookAction').value = '';
            seLoadPlaybook();
        }

        function seDeletePlaybookStep(index) {
            const rows = _seGetPlaybookItems();
            if (index < 0 || index >= rows.length) return;
            rows.splice(index, 1);
            _seSetPlaybookItems(rows);
            seLoadPlaybook();
        }

        function sePlaybookInjectTemplate() {
            const rows = _seGetPlaybookItems();
            const seed = [
                { phase: 'detect', owner: 'SOC', eta: '5m', action: 'تأكيد مؤشرات التهديد وتجميع الأدلة الأولية.' },
                { phase: 'verify', owner: 'IT', eta: '10m', action: 'التحقق عبر قناة ثانية مع صاحب الطلب.' },
                { phase: 'contain', owner: 'SOC', eta: '15m', action: 'حظر الرابط/المرسل وعزل الجلسات المشبوهة.' },
                { phase: 'report', owner: 'Manager', eta: '20m', action: 'إرسال تقرير حادث مختصر للجهات المعنية.' },
                { phase: 'lessons', owner: 'Awareness', eta: '1d', action: 'تحديث التوعية والإجراءات بناء على الدرس المستفاد.' }
            ];
            const merged = rows.concat(seed.map((s) => ({ ...s, created_at: new Date().toISOString() })));
            _seSetPlaybookItems(merged);
            seLoadPlaybook();
            titanAlert('تم إدراج قالب الاستجابة الدفاعي.');
        }

        function seExportPlaybook() {
            const rows = _seGetPlaybookItems();
            const payload = {
                exported_at: new Date().toISOString(),
                total_steps: rows.length,
                steps: rows
            };
            const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'se-response-playbook.json';
            a.click();
            URL.revokeObjectURL(url);
        }

        function seClearPlaybook() {
            if (!confirm('هل تريد حذف كل خطوات Playbook؟')) return;
            localStorage.removeItem(SE_PLAYBOOK_STORAGE_KEY);
            seLoadPlaybook();
        }

        function seLoadQuiz() {
            const stateRaw = localStorage.getItem(SE_QUIZ_STORAGE_KEY);
            let state = { idx: 0, score: 0, answered: false };
            if (stateRaw) {
                try { state = JSON.parse(stateRaw); } catch (_) {}
            }
            const q = SE_QUIZ_BANK[state.idx % SE_QUIZ_BANK.length];
            const qEl = document.getElementById('seQuizQuestion');
            const optsEl = document.getElementById('seQuizOptions');
            const metaEl = document.getElementById('seQuizMeta');
            const feedbackEl = document.getElementById('seQuizFeedback');
            if (!qEl || !optsEl || !metaEl || !feedbackEl) return;

            qEl.textContent = q.question;
            metaEl.textContent = `Question ${state.idx + 1}/${SE_QUIZ_BANK.length} - Score ${state.score}`;
            optsEl.innerHTML = q.options.map((op, i) =>
                `<button onclick="seSubmitQuizAnswer(${i})" class="w-full text-right p-2 rounded border border-slate-700 bg-slate-900/60 hover:bg-slate-800 text-xs">${_resultEscape(op)}</button>`
            ).join('');
            if (!state.answered) feedbackEl.textContent = 'اختر الإجابة الأنسب دفاعياً.';
        }

        async function seSubmitQuizAnswer(index) {
            const stateRaw = localStorage.getItem(SE_QUIZ_STORAGE_KEY);
            let state = { idx: 0, score: 0, answered: false };
            if (stateRaw) {
                try { state = JSON.parse(stateRaw); } catch (_) {}
            }
            if (state.answered) return;
            const q = SE_QUIZ_BANK[state.idx % SE_QUIZ_BANK.length];
            const feedbackEl = document.getElementById('seQuizFeedback');
            if (index === q.answer) {
                state.score += 1;
                if (feedbackEl) feedbackEl.textContent = `✅ صحيح: ${q.explain}`;
            } else {
                if (feedbackEl) feedbackEl.textContent = `❌ غير دقيق: ${q.explain}`;
            }
            state.answered = true;
            localStorage.setItem(SE_QUIZ_STORAGE_KEY, JSON.stringify(state));

            try {
                await fetch('/api/social/quiz/result', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        question_id: state.idx,
                        selected_option: index,
                        correct_option: q.answer,
                        is_correct: index === q.answer,
                        score_after: state.score
                    })
                });
            } catch (_) {}

            seLoadQuiz();
            seRefreshDashboard();
        }

        function seNextQuizQuestion() {
            const stateRaw = localStorage.getItem(SE_QUIZ_STORAGE_KEY);
            let state = { idx: 0, score: 0, answered: false };
            if (stateRaw) {
                try { state = JSON.parse(stateRaw); } catch (_) {}
            }
            state.idx = (state.idx + 1) % SE_QUIZ_BANK.length;
            state.answered = false;
            localStorage.setItem(SE_QUIZ_STORAGE_KEY, JSON.stringify(state));
            seLoadQuiz();
        }

        function seRestartQuiz() {
            localStorage.setItem(SE_QUIZ_STORAGE_KEY, JSON.stringify({ idx: 0, score: 0, answered: false }));
            seLoadQuiz();
        }

        function seBindIntelFilters() {
            if (window.__seFiltersBound) return;
            window.__seFiltersBound = true;
            const search = document.getElementById('seIntelSearch');
            const conf = document.getElementById('seIntelFilterConfidence');
            const cat = document.getElementById('seIntelFilterCategory');
            if (search) search.addEventListener('input', seLoadIntelBoard);
            if (conf) conf.addEventListener('change', seLoadIntelBoard);
            if (cat) cat.addEventListener('change', seLoadIntelBoard);
        }

        function seInitDefenseTab() {
            seBindIntelFilters();
            seLoadIntelBoard();
            seLoadPlaybook();
            seLoadQuiz();
            seSyncRiskSnapshot().then(seRefreshDashboard);

            const signalBox = document.getElementById('seSignalResult');
            if (signalBox && !signalBox.innerHTML.trim()) seAnalyzeSignal();
            const scenarioBox = document.getElementById('seScenarioResult');
            if (scenarioBox && !scenarioBox.innerHTML.trim()) seGenerateScenario();
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

        let burnNoteRecorder = null;
        let burnNoteRecordChunks = [];
        let burnNoteRecordStream = null;
        window.__burnNoteRecordedBlob = null;

        async function createBurnNote() {
            const textEl = document.getElementById('burnNoteText');
            const mediaEl = document.getElementById('burnNoteMedia');
            const text = (textEl.value || '').trim();
            const media = mediaEl.files && mediaEl.files[0] ? mediaEl.files[0] : null;
            const recordedBlob = window.__burnNoteRecordedBlob || null;
            if(!text && !media && !recordedBlob) return titanAlert("يرجى كتابة رسالة أو اختيار صورة أو تسجيل صوت قبل التوليد!");
            
            const formData = new FormData();
            if (text) formData.append('text', text);
            if (media) {
                formData.append('media', media);
            } else if (recordedBlob) {
                const voiceFile = new File([recordedBlob], 'burn-note-voice.webm', { type: recordedBlob.type || 'audio/webm' });
                formData.append('media', voiceFile);
            }
            
            try {
                const res = await fetch('/api/burn-note/create', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if(data.error) throw new Error(data.error);
                
                document.getElementById('burnNoteResult').classList.remove('hidden');
                document.getElementById('burnNoteLink').value = data.link;
                textEl.value = "";
                if (mediaEl) mediaEl.value = "";
                clearBurnNoteSelectedMedia(false);
                soundManager.success();
                refreshLogs();
            } catch (e) {
                titanAlert("خطأ: " + e.message);
                soundManager.error();
            }
        }

        function _setBurnNoteMediaStateLabel(text, tone) {
            const el = document.getElementById('burnNoteMediaState');
            if (!el) return;
            el.className = 'text-[11px] truncate ' + (tone || 'text-gray-400');
            el.textContent = text;
        }

        function triggerBurnNoteImagePicker() {
            const mediaEl = document.getElementById('burnNoteMedia');
            if (!mediaEl) return;
            mediaEl.onchange = () => {
                if (mediaEl.files && mediaEl.files[0]) {
                    window.__burnNoteRecordedBlob = null;
                    _setBurnNoteMediaStateLabel('🖼️ تم اختيار صورة: ' + mediaEl.files[0].name, 'text-orange-300');
                }
            };
            mediaEl.click();
        }

        async function startBurnNoteAudioRecording() {
            try {
                const mediaEl = document.getElementById('burnNoteMedia');
                if (mediaEl) mediaEl.value = '';
                window.__burnNoteRecordedBlob = null;

                burnNoteRecordStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                burnNoteRecordChunks = [];
                burnNoteRecorder = new MediaRecorder(burnNoteRecordStream);

                burnNoteRecorder.ondataavailable = (e) => {
                    if (e.data && e.data.size > 0) burnNoteRecordChunks.push(e.data);
                };

                burnNoteRecorder.onstop = () => {
                    if (burnNoteRecordChunks.length > 0) {
                        window.__burnNoteRecordedBlob = new Blob(burnNoteRecordChunks, { type: 'audio/webm' });
                        _setBurnNoteMediaStateLabel('🎤 تم تسجيل الصوت وجاهز للإرسال', 'text-emerald-300');
                    }
                    if (burnNoteRecordStream) {
                        burnNoteRecordStream.getTracks().forEach(t => t.stop());
                        burnNoteRecordStream = null;
                    }
                    const startBtn = document.getElementById('burnNoteRecStartBtn');
                    const stopBtn = document.getElementById('burnNoteRecStopBtn');
                    if (startBtn) startBtn.disabled = false;
                    if (stopBtn) stopBtn.disabled = true;
                };

                burnNoteRecorder.start();
                const startBtn = document.getElementById('burnNoteRecStartBtn');
                const stopBtn = document.getElementById('burnNoteRecStopBtn');
                if (startBtn) startBtn.disabled = true;
                if (stopBtn) stopBtn.disabled = false;
                _setBurnNoteMediaStateLabel('🔴 جاري تسجيل الصوت...', 'text-rose-300');
            } catch (e) {
                titanAlert('تعذر الوصول للميكروفون. اسمح بصلاحية الميكروفون أولاً.', 'error');
            }
        }

        function stopBurnNoteAudioRecording() {
            if (burnNoteRecorder && burnNoteRecorder.state === 'recording') {
                burnNoteRecorder.stop();
            }
        }

        function clearBurnNoteSelectedMedia(showToast = true) {
            const mediaEl = document.getElementById('burnNoteMedia');
            if (mediaEl) mediaEl.value = '';
            window.__burnNoteRecordedBlob = null;
            burnNoteRecordChunks = [];
            if (burnNoteRecorder && burnNoteRecorder.state === 'recording') {
                burnNoteRecorder.stop();
            }
            if (burnNoteRecordStream) {
                burnNoteRecordStream.getTracks().forEach(t => t.stop());
                burnNoteRecordStream = null;
            }
            const startBtn = document.getElementById('burnNoteRecStartBtn');
            const stopBtn = document.getElementById('burnNoteRecStopBtn');
            if (startBtn) startBtn.disabled = false;
            if (stopBtn) stopBtn.disabled = true;
            _setBurnNoteMediaStateLabel('لم يتم اختيار صورة أو تسجيل صوت بعد.', 'text-gray-400');
            if (showToast) titanAlert('تم مسح الوسيط المحدد', 'info');
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
                    const pickedFile = fileInput.files && fileInput.files[0];
                    if (!pickedFile) return;
                    const formData = new FormData();
                    formData.append('file', pickedFile);
                    formData.append('text', text);
                    try {
                        const res = await fetch('/api/steganography/encode', { method: 'POST', body: formData });
                        if (res.ok) {
                            const blob = await res.blob();
                            const url = window.URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = `stego_${(pickedFile.name || 'image').replace(/[.][^.]+$/, '')}.png`;
                            a.click();
                            window.URL.revokeObjectURL(url);
                            titanAlert('✅ تم تشفير الصورة وتحميلها');
                            refreshLogs();
                        } else {
                            const errData = await res.json();
                            titanAlert("خطأ في تشفير الصورة: " + (errData.error || "خطأ غير معروف"));
                        }
                    } catch (e) {
                        titanAlert("تعذر الاتصال بالخادم أثناء تشفير الصورة");
                    }
                };
                fileInput.click();
            } else {
                const fileInput = document.createElement('input');
                fileInput.type = 'file';
                fileInput.accept = 'image/*';
                fileInput.onchange = async () => {
                    const pickedFile = fileInput.files && fileInput.files[0];
                    if (!pickedFile) return;
                    const formData = new FormData();
                    formData.append('file', pickedFile);
                    try {
                        const res = await fetch('/api/steganography/decode', { method: 'POST', body: formData });
                        const data = await res.json();
                        if (!res.ok) {
                            titanAlert("فشل استخراج النص: " + (data.error || "خطأ غير معروف"));
                            return;
                        }
                        titanAlert("النص المستخرج: " + (data.result || "لا توجد بيانات"));
                        refreshLogs();
                    } catch (e) {
                        titanAlert("تعذر الاتصال بالخادم أثناء استخراج النص");
                    }
                };
                fileInput.click();
            }
        }

        /* --- Burn Chat Logic (E2E Encrypted) --- */
        let burnChatTimer = null;
        let currentRoomId = null;
        let currentUser = null;
        let burnChatRecorder = null;
        let burnChatRecordStream = null;
        let burnChatRecordChunks = [];

        function _burnCipherPreview(cipherText) {
            const raw = String(cipherText || '');
            if (raw.length <= 120) return _osintEscape(raw);
            const compact = raw.slice(0, 60) + ' ... ' + raw.slice(-28);
            return _osintEscape(compact);
        }

        function _setBurnChatUiConnected(isConnected) {
            const input = document.getElementById('burnChatInput');
            const sendBtn = document.getElementById('burnChatSendBtn');
            const mediaInput = document.getElementById('burnChatMediaInput');
            const mediaBtn = document.getElementById('burnChatMediaBtn');
            const destroyBtn = document.getElementById('burnChatDestroyBtn');
            const recStartBtn = document.getElementById('burnChatRecStartBtn');
            const recStopBtn = document.getElementById('burnChatRecStopBtn');
            const recState = document.getElementById('burnChatRecState');

            if (input) input.disabled = !isConnected;
            if (sendBtn) {
                sendBtn.disabled = !isConnected;
                sendBtn.className = isConnected
                    ? 'bg-pink-600 hover:bg-pink-500 text-white px-8 rounded-lg font-bold transition-all border border-pink-500/50 shadow-[0_0_15px_rgba(236,72,153,0.3)]'
                    : 'bg-slate-800 text-gray-500 px-8 rounded-lg font-bold transition-all border border-slate-700';
            }
            if (mediaInput) mediaInput.disabled = !isConnected;
            if (mediaBtn) {
                mediaBtn.disabled = !isConnected;
                mediaBtn.className = isConnected
                    ? 'bg-pink-900/40 hover:bg-pink-800 text-pink-300 px-4 py-2 rounded-lg font-bold transition-all border border-pink-800/50'
                    : 'bg-slate-800 text-gray-500 px-4 py-2 rounded-lg font-bold transition-all border border-slate-700';
            }
            if (recStartBtn) {
                recStartBtn.disabled = !isConnected;
                recStartBtn.className = isConnected
                    ? 'bg-emerald-900/40 hover:bg-emerald-800 text-emerald-300 px-4 py-2 rounded-lg font-bold transition-all border border-emerald-800/50'
                    : 'bg-slate-800 text-gray-500 px-4 py-2 rounded-lg font-bold transition-all border border-slate-700';
            }
            if (recStopBtn) {
                recStopBtn.disabled = true;
                recStopBtn.className = isConnected
                    ? 'bg-amber-900/40 hover:bg-amber-800 text-amber-300 px-4 py-2 rounded-lg font-bold transition-all border border-amber-800/50'
                    : 'bg-slate-800 text-gray-500 px-4 py-2 rounded-lg font-bold transition-all border border-slate-700';
            }
            if (recState) recState.textContent = isConnected ? 'جاهز لتسجيل الصوت داخل الغرفة' : 'تسجيل مباشر غير مفعل';
            if (destroyBtn) destroyBtn.disabled = !isConnected;
        }

        async function _sendBurnChatMediaDataUrl(dataUrl, mime, fileName) {
            if (!currentRoomId || !dataUrl) return;

            const encryptKey = prompt("🔐 أدخل مفتاح التشفير الخاص بهذه الوسائط:");
            if (!encryptKey) return;

            const payload = JSON.stringify({
                kind: 'media',
                mime: mime || 'application/octet-stream',
                name: fileName || 'file',
                data: dataUrl
            });
            const encryptedMsg = e2eEncrypt(payload, encryptKey);

            const display = document.getElementById('burnChatDisplay');
            const type = String(mime || '');
            if (type.startsWith('image/')) {
                display.innerHTML += `
                    <div class="flex justify-start mt-4">
                        <div class="bg-indigo-900/40 border border-indigo-700/50 text-indigo-200 px-4 py-3 rounded-lg text-sm max-w-[85%] break-y relative">
                            <span class="text-[10px] text-indigo-400 font-bold mb-1 block">أنت (${currentUser}) <span class="text-indigo-600 bg-indigo-950 px-1 rounded ml-2">🔒 صورة مشفرة</span></span>
                            <img src="${dataUrl}" alt="sent image" class="rounded border border-indigo-700/40 max-h-48 object-contain mt-2" />
                        </div>
                    </div>
                `;
            } else if (type.startsWith('video/')) {
                display.innerHTML += `
                    <div class="flex justify-start mt-4">
                        <div class="bg-indigo-900/40 border border-indigo-700/50 text-indigo-200 px-4 py-3 rounded-lg text-sm max-w-[85%] break-y relative">
                            <span class="text-[10px] text-indigo-400 font-bold mb-1 block">أنت (${currentUser}) <span class="text-indigo-600 bg-indigo-950 px-1 rounded ml-2">🔒 فيديو مشفر</span></span>
                            <video controls controlsList="nodownload noplaybackrate" disablePictureInPicture oncontextmenu="return false;" class="w-full max-h-56 rounded border border-indigo-700/40 mt-2"><source src="${dataUrl}"></video>
                        </div>
                    </div>
                `;
            } else {
                display.innerHTML += `
                    <div class="flex justify-start mt-4">
                        <div class="bg-indigo-900/40 border border-indigo-700/50 text-indigo-200 px-4 py-3 rounded-lg text-sm max-w-[85%] break-y relative">
                            <span class="text-[10px] text-indigo-400 font-bold mb-1 block">أنت (${currentUser}) <span class="text-indigo-600 bg-indigo-950 px-1 rounded ml-2">🔒 صوت مشفر</span></span>
                            <audio controls controlsList="nodownload noplaybackrate" disablePictureInPicture oncontextmenu="return false;" class="w-full mt-2"><source src="${dataUrl}"></audio>
                        </div>
                    </div>
                `;
            }
            display.scrollTop = display.scrollHeight;

            await fetch('/api/chat/send', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({room_id: currentRoomId, sender: currentUser, msg: encryptedMsg})
            });
            soundManager.success();
        }

        async function startBurnChatRecording() {
            if (!currentRoomId) return titanAlert('انضم للغرفة أولاً', 'warning');
            const recStartBtn = document.getElementById('burnChatRecStartBtn');
            const recStopBtn = document.getElementById('burnChatRecStopBtn');
            const recState = document.getElementById('burnChatRecState');

            try {
                burnChatRecordStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                burnChatRecordChunks = [];
                burnChatRecorder = new MediaRecorder(burnChatRecordStream);

                burnChatRecorder.ondataavailable = (e) => {
                    if (e.data && e.data.size > 0) burnChatRecordChunks.push(e.data);
                };

                burnChatRecorder.onstop = async () => {
                    const mime = burnChatRecorder?.mimeType || 'audio/webm';
                    const blob = new Blob(burnChatRecordChunks, { type: mime });

                    if (burnChatRecordStream) {
                        burnChatRecordStream.getTracks().forEach(t => t.stop());
                        burnChatRecordStream = null;
                    }

                    if (recStartBtn) recStartBtn.disabled = false;
                    if (recStopBtn) recStopBtn.disabled = true;
                    if (recState) recState.textContent = 'تم إيقاف التسجيل، جاري الإرسال...';

                    try {
                        const dataUrl = await new Promise((resolve, reject) => {
                            const reader = new FileReader();
                            reader.onload = () => resolve(String(reader.result || ''));
                            reader.onerror = () => reject(new Error('read_failed'));
                            reader.readAsDataURL(blob);
                        });
                        await _sendBurnChatMediaDataUrl(String(dataUrl), mime, 'burn-chat-recording.webm');
                        if (recState) recState.textContent = 'تم إرسال التسجيل المشفّر ✅';
                    } catch (e) {
                        if (recState) recState.textContent = 'فشل إرسال التسجيل';
                        titanAlert('فشل إرسال التسجيل الصوتي', 'error');
                    }
                };

                burnChatRecorder.start();
                if (recStartBtn) recStartBtn.disabled = true;
                if (recStopBtn) recStopBtn.disabled = false;
                if (recState) recState.textContent = '🔴 جاري التسجيل... اضغط إيقاف للإرسال';
            } catch (e) {
                titanAlert('تعذر الوصول إلى الميكروفون. اسمح بصلاحية الميكروفون.', 'error');
            }
        }

        function stopBurnChatRecording() {
            if (burnChatRecorder && burnChatRecorder.state !== 'inactive') {
                burnChatRecorder.stop();
            }
        }

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

            _setBurnChatUiConnected(true);
            document.getElementById('burnChatDisplay').innerHTML = '<div class="text-center text-pink-500 font-bold tracking-widest text-xs uppercase mt-auto mb-2 animate-pulse">-- 🔒 تم الاتصال بنفق مشفر (End-to-End) --</div><div class="text-center text-gray-500 tracking-widest text-[10px] uppercase">يتم تشفير/فك تشفير الرسائل محلياً داخل متصفحك فقط</div>';

            const mediaInput = document.getElementById('burnChatMediaInput');
            if (mediaInput) {
                mediaInput.value = '';
                mediaInput.onchange = sendBurnChatMedia;
            }

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

        async function sendBurnChatMedia() {
            const mediaInput = document.getElementById('burnChatMediaInput');
            if (!mediaInput || !mediaInput.files || !mediaInput.files.length || !currentRoomId) return;

            const file = mediaInput.files[0];
            if (!file) return;
            if (!(file.type || '').startsWith('image/') && !(file.type || '').startsWith('audio/') && !(file.type || '').startsWith('video/')) {
                titanAlert('الملف غير مدعوم. مسموح فقط صورة أو صوت أو فيديو.', 'error');
                mediaInput.value = '';
                return;
            }
            if (file.size > 12 * 1024 * 1024) {
                titanAlert('حجم الملف كبير جداً (الحد 12MB).', 'warning');
                mediaInput.value = '';
                return;
            }

            try {
                const dataUrl = await new Promise((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onload = () => resolve(String(reader.result || ''));
                    reader.onerror = () => reject(new Error('read_failed'));
                    reader.readAsDataURL(file);
                });
                await _sendBurnChatMediaDataUrl(String(dataUrl), file.type || 'application/octet-stream', file.name || 'file');
            } catch (e) {
                titanAlert('فشل إرسال الوسائط المشفرة', 'error');
            } finally {
                mediaInput.value = '';
            }
        }

        function _handleBurnRoomDestroyed(byUser) {
            if (burnChatRecorder && burnChatRecorder.state !== 'inactive') {
                burnChatRecorder.stop();
            }
            if (burnChatRecordStream) {
                burnChatRecordStream.getTracks().forEach(t => t.stop());
                burnChatRecordStream = null;
            }
            if (burnChatTimer) {
                clearInterval(burnChatTimer);
                burnChatTimer = null;
            }
            _setBurnChatUiConnected(false);
            currentRoomId = null;
            const display = document.getElementById('burnChatDisplay');
            if (display) {
                display.innerHTML = `
                    <div class="h-full flex flex-col items-center justify-center text-center">
                        <div class="text-4xl mb-2">💥</div>
                        <div class="text-rose-400 font-black">تم تدمير الغرفة بالكامل</div>
                        <div class="text-xs text-gray-500 mt-2">${byUser ? ('تم التدمير بواسطة: ' + byUser) : 'تم حذف كامل الجلسة والرسائل'}.</div>
                    </div>
                `;
            }
            titanAlert('💥 تم تدمير غرفة الدردشة وحذف جميع الرسائل', 'warning');
        }

        async function destroyBurnChatRoom() {
            if (!currentRoomId) return titanAlert('لا توجد غرفة نشطة حالياً', 'warning');
            const ok = await titanConfirm('هل أنت متأكد من تدمير الغرفة؟ سيتم حذف جميع الرسائل وإخراج جميع الأطراف.');
            if (!ok) return;
            try {
                const res = await fetch('/api/chat/destroy', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({room_id: currentRoomId, requester: currentUser || 'Unknown'})
                });
                const data = await res.json();
                if (!data.success) {
                    return titanAlert(data.error || 'فشل تدمير الغرفة', 'error');
                }
                _handleBurnRoomDestroyed(currentUser || 'You');
            } catch (e) {
                titanAlert('فشل الاتصال بالخادم أثناء التدمير', 'error');
            }
        }

        async function pollBurnChat() {
            if(!currentRoomId) return;
            
            try {
                const res = await fetch(`/api/chat/receive?room_id=${currentRoomId}&requester=${currentUser}`);
                const data = await res.json();

                if (data.destroyed) {
                    _handleBurnRoomDestroyed(data.by || 'Peer');
                    return;
                }
                
                if(data.messages && data.messages.length > 0) {
                    const display = document.getElementById('burnChatDisplay');
                    data.messages.forEach(m => {
                        // Generate a unique ID for this message block
                        const msgId = 'msg-' + Math.random().toString(36).substr(2, 9);
                        const cipherRaw = String(m.msg || '');
                        const cipherPreview = _burnCipherPreview(cipherRaw);
                        
                        display.innerHTML += `
                            <div class="flex justify-end mt-4 mb-2">
                                <div id="${msgId}" class="bg-pink-900/40 border border-pink-700/50 text-pink-200 px-5 py-4 rounded-lg text-sm max-w-[85%] break-y relative group shadow-[0_4px_20px_rgba(236,72,153,0.15)] transition-all">
                                    <div class="flex justify-between items-center mb-2 border-b border-pink-800/50 pb-2">
                                        <span class="text-xs text-pink-400 font-black">${m.sender}</span>
                                        <span class="text-[9px] text-gray-500 ml-3 uppercase bg-black/50 border border-slate-700 px-2 py-0.5 rounded">🔒 مشفر (Ciphertext)</span>
                                    </div>
                                    <!-- Ciphertext -->
                                    <div class="mb-3 p-2 bg-black/80 rounded border border-pink-900/50">
                                        <div class="text-[10px] font-mono text-pink-700/70 break-all">${cipherPreview}</div>
                                        <div class="text-[9px] text-pink-800 mt-1">cipher length: ${cipherRaw.length} chars</div>
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

                // Keep chat state; don't wipe entire app on single wrong key attempt.
                soundManager.error();
                return;
            }
            
            // Success: Replace the button area with the decrypted result
            let rendered = `<div class="text-white font-bold text-lg leading-relaxed bg-green-900/20 p-3 rounded border border-green-800/30">${result.text}</div>`;
            try {
                const parsed = JSON.parse(result.text);
                if (parsed && parsed.kind === 'media' && parsed.data) {
                    if (String(parsed.mime || '').startsWith('image/')) {
                        rendered = `<div class="bg-green-900/20 p-3 rounded border border-green-800/30"><div class="text-[10px] text-green-300 mb-2">📷 صورة مفكوكة التشفير</div><img src="${parsed.data}" alt="decrypted image" class="rounded border border-green-700/40 max-h-56 object-contain" /></div>`;
                    } else if (String(parsed.mime || '').startsWith('video/')) {
                        rendered = `<div class="bg-green-900/20 p-3 rounded border border-green-800/30"><div class="text-[10px] text-green-300 mb-2">🎬 فيديو مفكوك التشفير</div><video controls controlsList="nodownload noplaybackrate" disablePictureInPicture oncontextmenu="return false;" class="w-full max-h-56 rounded border border-green-700/40"><source src="${parsed.data}"></video></div>`;
                    } else if (String(parsed.mime || '').startsWith('audio/')) {
                        rendered = `<div class="bg-green-900/20 p-3 rounded border border-green-800/30"><div class="text-[10px] text-green-300 mb-2">🎧 ملف صوتي مفكوك التشفير</div><audio controls controlsList="nodownload noplaybackrate" disablePictureInPicture oncontextmenu="return false;" class="w-full"><source src="${parsed.data}"></audio></div>`;
                    }
                }
            } catch (e) {
                // plain text message; keep default rendering
            }
            actionArea.innerHTML = `
                <div class="text-[9px] text-green-400 mb-1">تم فك التشفير محلياً بنجاح باستخدام المفتاح المقدم:</div>
                ${rendered}
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

        document.addEventListener('DOMContentLoaded', function() {
            var aiLauncher = document.getElementById('ai-float-launcher');
            var aiPanel = document.getElementById('ai-section');

            if (aiPanel) {
                if (aiPanel.parentElement !== document.body) {
                    document.body.appendChild(aiPanel);
                }
                aiPanel.style.zIndex = '2147483646';
                aiPanel.style.width = 'min(92vw,34rem)';
                aiPanel.style.maxHeight = '78vh';
                aiPanel.style.transition = 'opacity 0.18s ease, transform 0.18s ease';
                aiPanel.style.willChange = 'transform, opacity';
                aiPanel.style.opacity = '0';
                aiPanel.style.transform = 'translateY(14px) scale(0.985)';
                aiPanel.style.display = 'none';
                aiPanel.style.pointerEvents = 'none';
            }

            if (!document.getElementById('ai-launcher-pulse-style')) {
                const style = document.createElement('style');
                style.id = 'ai-launcher-pulse-style';
                style.textContent = '@keyframes aiLauncherPulse{0%{transform:scale(1);box-shadow:0 0 0 0 rgba(168,85,247,0.42)}70%{transform:scale(1.03);box-shadow:0 0 0 14px rgba(168,85,247,0)}100%{transform:scale(1);box-shadow:0 0 0 0 rgba(168,85,247,0)}}';
                document.head.appendChild(style);
            }

            if (aiLauncher) {
                if (aiLauncher.parentElement !== document.body) {
                    document.body.appendChild(aiLauncher);
                }
            }
            applyAiDockPosition();
            window.addEventListener('resize', applyAiDockPosition);
            closeAiBubble();
            setAiBubbleVisibility(false);

            var aiInput = document.getElementById('ai-chat-input');
            if (aiInput) {
                aiInput.addEventListener('keydown', function(e) {
                    if (e.key === 'Enter') sendAiMessage();
                });
            }
            loadAiConversations();
        });

        function aiTopicLabel(v) {
            var map = {
                general_support: 'عام',
                incident_response: 'استجابة حوادث',
                malware_analysis: 'تحليل برمجيات خبيثة',
                network_security: 'أمن الشبكات',
                osint: 'OSINT',
                secure_coding: 'برمجة آمنة',
                learning_path: 'مسار تعلّم'
            };
            return map[v] || 'عام';
        }

        function renderAiBubble(flow, role, content) {
            var row = document.createElement('div');
            if (role === 'assistant') {
                row.className = 'flex justify-start items-end gap-2';
                row.innerHTML = '<div class="w-7 h-7 rounded-full bg-purple-900/50 border border-purple-700/40 flex items-center justify-center text-xs">🤖</div>' +
                    '<div class="bg-slate-800 text-gray-200 px-4 py-3 rounded-2xl rounded-bl-md max-w-[84%] text-sm shadow-lg border border-slate-700/60 leading-7">' + renderAiReplyPretty(content) + '</div>';
            } else {
                row.className = 'flex justify-end items-end gap-2';
                row.innerHTML = '<div class="bg-purple-700/70 text-white px-4 py-3 rounded-2xl rounded-br-md max-w-[80%] text-sm shadow-lg border border-purple-600/40">' +
                    _osintEscape(String(content || '')).replace(/\\n/g, '<br>') +
                    '</div><div class="w-7 h-7 rounded-full bg-purple-800/40 border border-purple-700/50 flex items-center justify-center text-xs">👤</div>';
            }
            flow.appendChild(row);
        }

        async function loadAiConversations() {
            const box = document.getElementById('ai-conv-list');
            if (!box) return;
            box.innerHTML = '<div class="text-gray-500">...loading</div>';
            try {
                const res = await fetch('/api/ai/conversations', { cache: 'no-store' });
                const data = await res.json();
                if (!data.success) {
                    box.innerHTML = '<div class="text-rose-300">تعذر تحميل المحادثات</div>';
                    return;
                }
                const rows = data.conversations || [];
                if (!rows.length) {
                    box.innerHTML = '<div class="text-gray-500">لا توجد محادثات بعد</div>';
                    return;
                }
                box.innerHTML = rows.map(r => {
                    const active = (window.__titanAiConversationId && window.__titanAiConversationId === r.conversation_id) ? 'border-purple-500/70 bg-purple-900/25' : 'border-slate-700 bg-slate-900/40';
                    return '<div class="w-full p-2 rounded border ' + active + ' transition-all overflow-hidden">' +
                        '<div class="flex items-start gap-2 min-w-0">' +
                            '<button onclick="openAiConversation(' + "'" + _osintEscape(r.conversation_id) + "'" + ')" class="flex-1 min-w-0 text-right hover:text-white transition-colors overflow-hidden">' +
                                '<div class="font-bold text-gray-200 truncate w-full">' + _osintEscape(r.title || 'محادثة جديدة') + '</div>' +
                                '<div class="text-[10px] text-purple-300">' + _osintEscape(aiTopicLabel(r.classification)) + '</div>' +
                                '<div class="text-[10px] text-gray-500 truncate w-full">' + _osintEscape(r.last_message_preview || '') + '</div>' +
                            '</button>' +
                            '<button onclick="deleteAiConversation(' + "'" + _osintEscape(r.conversation_id) + "'" + ')" title="حذف المحادثة" class="shrink-0 px-2 py-1 text-[10px] rounded border border-rose-700/60 bg-rose-900/20 text-rose-300 hover:bg-rose-800/30">حذف</button>' +
                        '</div>' +
                    '</div>';
                }).join('');
            } catch (e) {
                box.innerHTML = '<div class="text-rose-300">فشل الاتصال بالخادم</div>';
            }
        }

        async function deleteAiConversation(conversationId) {
            if (!conversationId) return;
            const ok = await titanConfirm('هل أنت متأكد من حذف هذه المحادثة نهائياً؟');
            if (!ok) return;
            try {
                let res = await fetch('/api/ai/conversations/' + encodeURIComponent(conversationId), { method: 'DELETE', cache: 'no-store' });
                if (res.status === 405) {
                    res = await fetch('/api/ai/conversations/' + encodeURIComponent(conversationId) + '/delete', { method: 'POST', cache: 'no-store' });
                }
                const data = await res.json();
                if (!data.success) {
                    titanAlert(data.error || 'تعذر المسح', 'error');
                    return;
                }

                if (window.__titanAiConversationId === conversationId) {
                    startNewAiConversation();
                }
                titanAlert('✅ تم حذف المحادثة', 'success');
                loadAiConversations();
            } catch (e) {
                titanAlert('تعذر المسح: فشل الاتصال بالخادم', 'error');
            }
        }

        async function openAiConversation(conversationId) {
            if (!conversationId) return;
            const flow = document.getElementById('ai-chat-flow');
            const meta = document.getElementById('ai-chat-meta');
            if (!flow) return;
            flow.innerHTML = '<div class="text-gray-500 text-xs">...loading chat</div>';
            try {
                const res = await fetch('/api/ai/conversations/' + encodeURIComponent(conversationId), { cache: 'no-store' });
                const data = await res.json();
                if (!data.success) {
                    flow.innerHTML = '<div class="text-rose-300 text-xs">تعذر فتح الدردشة: ' + _osintEscape(data.error || 'unknown error') + '</div>';
                    if (res.status === 404) loadAiConversations();
                    return;
                }
                window.__titanAiConversationId = conversationId;
                flow.innerHTML = '';
                (data.messages || []).forEach(m => renderAiBubble(flow, m.role, m.content));
                if (meta) {
                    meta.textContent = 'الموضوع: ' + aiTopicLabel(data.classification) + ' • الذاكرة: فعالة • Conversation: ' + conversationId;
                }
                scrollAiChatToBottom();
                loadAiConversations();
            } catch (e) {
                flow.innerHTML = '<div class="text-rose-300 text-xs">فشل الاتصال بالخادم</div>';
            }
        }

        async function sendAiMessage() {
            var input = document.getElementById('ai-chat-input');
            var messages = document.getElementById('ai-chat-messages');
            var flow = document.getElementById('ai-chat-flow') || messages;
            var btn = document.getElementById('ai-send-btn');
            var meta = document.getElementById('ai-chat-meta');
            var msg = input.value.trim();
            if (!msg) return;

            window.__titanAiConversationId = window.__titanAiConversationId || null;

            var userDiv = document.createElement('div');
            userDiv.className = 'flex justify-end items-end gap-2';
            userDiv.innerHTML = '<div class="bg-purple-700/70 text-white px-4 py-3 rounded-2xl rounded-br-md max-w-[80%] text-sm shadow-lg border border-purple-600/40">' +
                _osintEscape(msg).replace(/\\n/g, '<br>') +
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
            replyInner.className = 'bg-slate-800 text-gray-200 px-4 py-3 rounded-2xl rounded-bl-md max-w-[84%] text-sm shadow-lg border border-slate-700/60 leading-7';
            replyInner.textContent = '...';
            replyDiv.appendChild(botAvatar);
            replyDiv.appendChild(replyInner);
            flow.appendChild(replyDiv);
            messages.scrollTop = messages.scrollHeight;

            try {
                const res = await fetch('/api/ai/chat', {
                    method: 'POST',
                    cache: 'no-store',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        message: msg,
                        conversation_id: window.__titanAiConversationId
                    })
                });
                var data = await res.json();
                if (data.reply) {
                    window.__titanAiConversationId = data.conversation_id || window.__titanAiConversationId;
                    if (meta) {
                        var lbl = aiTopicLabel(data.classification);
                        meta.textContent = 'الموضوع: ' + lbl + ' • الذاكرة: فعالة • Conversation: ' + (window.__titanAiConversationId || '-');
                    }
                    replyInner.innerHTML = renderAiReplyPretty(data.reply);
                    loadAiConversations();
                } else {
                    replyInner.textContent = data.error || 'حدث خطأ';
                }
            } catch(e) {
                replyInner.textContent = 'فشل الاتصال';
            }
            btn.disabled = false;
            btn.textContent = 'إرسال';
            messages.scrollTop = messages.scrollHeight;
        }

        function renderAiReplyPretty(text) {
            const src = String(text || '');
            const esc = _osintEscape(src);
            const lines = esc.split(/\\n+/);
            let out = [];
            let openedList = false;

            function closeListIfOpen() {
                if (openedList) {
                    out.push('</ol>');
                    openedList = false;
                }
            }

            for (let i = 0; i < lines.length; i++) {
                const line = (lines[i] || '').trim();
                if (!line) {
                    closeListIfOpen();
                    continue;
                }

                if (line.startsWith('### ') || line.startsWith('## ') || line.startsWith('# ')) {
                    closeListIfOpen();
                    const title = line.replace(/^#+\\s*/, '');
                    out.push('<div class="text-purple-300 font-black text-[15px] mt-2 mb-1 tracking-wide">' + title + '</div>');
                    continue;
                }

                if (/^\\d+\\.\\s+/.test(line)) {
                    if (!openedList) {
                        out.push('<ol class="list-decimal mr-5 space-y-1 text-gray-100">');
                        openedList = true;
                    }
                    out.push('<li>' + line.replace(/^\\d+\\.\\s+/, '') + '</li>');
                    continue;
                }

                if (/^[-*]\\s+/.test(line)) {
                    closeListIfOpen();
                    out.push('<div class="text-gray-100">• ' + line.replace(/^[-*]\\s+/, '') + '</div>');
                    continue;
                }

                closeListIfOpen();
                out.push('<div class="text-gray-100">' + line + '</div>');
            }
            closeListIfOpen();
            return out.join('');
        }

        function startNewAiConversation() {
            window.__titanAiConversationId = null;
            const flow = document.getElementById('ai-chat-flow');
            const meta = document.getElementById('ai-chat-meta');
            if (!flow) return;
            flow.innerHTML = `
                <div class="flex justify-start items-end gap-2">
                    <div class="w-7 h-7 rounded-full bg-purple-900/50 border border-purple-700/40 flex items-center justify-center text-xs">🤖</div>
                    <div class="bg-slate-800 text-gray-300 px-4 py-3 rounded-2xl rounded-bl-md max-w-[80%] text-sm shadow-lg border border-slate-700/60">
                        بدأت محادثة جديدة ✅ اكتب سؤالك الأول وسأبني عليه سياق كامل.
                    </div>
                </div>
            `;
            if (meta) meta.textContent = 'الموضوع: عام • الذاكرة: مترابطة عبر كل محادثاتك';
            scrollAiChatToBottom();
            const input = document.getElementById('ai-chat-input');
            if (input) input.focus();
            loadAiConversations();
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
                const idNameEnWrap = document.getElementById('idNameEnWrap');
                const idNameEn = document.getElementById('idNameEn');
                const hasArabicName = /[\\u0600-\\u06FF]/.test(String(data.name || ''));
                const englishName = String(data.name_en || '').trim();
                if (idNameEnWrap && idNameEn) {
                    if (hasArabicName && englishName) {
                        idNameEn.innerText = englishName;
                        idNameEnWrap.classList.remove('hidden');
                    } else {
                        idNameEn.innerText = '';
                        idNameEnWrap.classList.add('hidden');
                    }
                }
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
    """Serve Tailwind CSS with robust production fallbacks."""
    css_path = os.path.join(app.root_path, 'static', 'css', 'tailwind.css')
    try:
        with open(css_path, 'r', encoding='utf-8') as f:
            css = f.read()
        resp = Response(css, mimetype='text/css')
        # Keep CSS cache short so production updates propagate quickly.
        resp.headers['Cache-Control'] = 'public, max-age=300'
        return resp
    except Exception:
        # Production safety net: when compiled CSS file is missing in slug,
        # pull a Tailwind build from CDN so the UI remains usable.
        try:
            cdn_res = requests.get(
                'https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css',
                timeout=6
            )
            if cdn_res.status_code == 200 and len(cdn_res.text) > 10000:
                resp = Response(cdn_res.text, mimetype='text/css')
                resp.headers['Cache-Control'] = 'public, max-age=1800'
                return resp
        except Exception:
            pass

        fallback_css = """
/* TITAN emergency CSS fallback */
html,body{margin:0;padding:0;font-family:'Tajawal',sans-serif;background:#070b19;color:#fff}
.hidden{display:none !important}
.container{width:100%;max-width:64rem;margin-left:auto;margin-right:auto}
.glass{background:rgba(10,15,30,.85);border:1px solid rgba(168,85,247,.2);border-radius:1rem}
.tab-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:.45rem}
button,input,textarea,select{font:inherit}
"""
        resp = Response(fallback_css, mimetype='text/css')
        resp.headers['Cache-Control'] = 'no-store, max-age=0'
        return resp


def _tailwind_version_token() -> str:
    """Generate a stable cache-busting token from CSS file mtime."""
    css_path = os.path.join(app.root_path, 'static', 'css', 'tailwind.css')
    try:
        mtime = int(os.path.getmtime(css_path))
        return str(mtime)
    except Exception:
        return str(int(time.time()))


def _has_local_tailwind_css() -> bool:
    css_path = os.path.join(app.root_path, 'static', 'css', 'tailwind.css')
    return os.path.exists(css_path)

@app.route('/')
def index():
    html = HTML_TEMPLATE.replace('__TAILWIND_V__', _tailwind_version_token())
    # Ensure full UI utility coverage when local compiled CSS is incomplete.
    html = html.replace(
        '__TAILWIND_PLAY_CDN__',
        '<script src="https://cdn.tailwindcss.com"></script>'
    )
    resp = Response(render_template_string(html), mimetype='text/html')
    # Prevent stale HTML from pinning an old CSS version on custom domains/CDNs.
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp

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
    file = request.files.get('file')
    text = (request.form.get('text') or '').strip()
    if not file:
        return jsonify({"error": "يرجى اختيار صورة أولاً"}), 400
    if not text:
        return jsonify({"error": "النص المراد إخفاؤه مطلوب"}), 400
    filename = file.filename or 'image.png'
    try:
        raw = file.read()
        if not _looks_like_image_bytes(raw):
            return jsonify({"error": "الملف المرفوع ليس صورة صالحة"}), 400
        processed_data = lsb_encode(raw, text)
        base_name = os.path.splitext(secure_filename(filename))[0] or 'image'
        add_audit_log("تشفير إخفاء (Stego)", f"إخفاء نص في {filename}")
        return send_file(
            io.BytesIO(processed_data),
            mimetype='image/png',
            as_attachment=True,
            download_name=f"stego_{base_name}.png"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/steganography/decode', methods=['POST'])
def stego_decode_route():
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "يرجى اختيار صورة أولاً"}), 400
    filename = file.filename or 'image.png'
    try:
        raw = file.read()
        if not _looks_like_image_bytes(raw):
            return jsonify({"error": "الملف المرفوع ليس صورة صالحة"}), 400
        decoded_text = lsb_decode(raw)
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


@app.route('/api/audit-logs', methods=['GET'])
def get_audit_logs():
    return jsonify(AUDIT_LOGS)


def _normalize_crypt_recommendation(rec: dict) -> dict:
    method = str(rec.get('method') or 'fernet').lower()
    kdf_profile = str(rec.get('kdf_profile') or 'strong').lower()
    output_format = str(rec.get('output_format') or 'b64').lower()
    reason = str(rec.get('reason') or 'تم اختيار إعداد آمن ومتوازن حسب السياق.').strip()
    warning = str(rec.get('warning') or '').strip()

    if method not in ('fernet', 'aes-cbc', 'chacha20', 'xor-stream'):
        method = 'fernet'
    if kdf_profile not in ('balanced', 'strong', 'paranoid'):
        kdf_profile = 'strong'
    if output_format not in ('b64', 'b64url'):
        output_format = 'b64'

    return {
        'method': method,
        'kdf_profile': kdf_profile,
        'output_format': output_format,
        'reason': reason[:600],
        'warning': warning[:300],
    }


def _fallback_crypt_recommendation(audience: str, sensitivity: str, purpose: str) -> dict:
    text = f"{audience} {purpose}".lower()
    sens = (sensitivity or 'high').lower()

    method = 'fernet'
    kdf_profile = 'strong'
    output_format = 'b64'
    warning = ''

    if sens == 'critical' or any(k in text for k in ['مالي', 'bank', 'law', 'قانون', 'secret', 'سري جدا']):
        method = 'fernet'
        kdf_profile = 'paranoid'
    elif any(k in text for k in ['api', 'url', 'link', 'webhook', 'browser', 'واتساب', 'telegram']):
        method = 'fernet'
        kdf_profile = 'strong'
        output_format = 'b64url'
    elif sens == 'normal':
        method = 'aes-cbc'
        kdf_profile = 'balanced'

    reason = (
        f"تم الاختيار بناءً على حساسية '{sens}' وطريقة الإرسال. "
        f"للإرسال إلى '{audience[:60]}', هذا الإعداد يوازن بين الأمان وسهولة المشاركة."
    )
    return _normalize_crypt_recommendation({
        'method': method,
        'kdf_profile': kdf_profile,
        'output_format': output_format,
        'reason': reason,
        'warning': warning,
    })


def _enforce_platform_crypto_reply_scope(reply: str) -> str:
    text = str(reply or '').strip()
    if not text:
        return (
            "ضمن المنصة الحالية، خيارات التشفير المتاحة فقط هي: "
            "Fernet + PBKDF2، AES-256-CBC + PBKDF2، ChaCha20 + PBKDF2، و XOR Stream (تعليمي)."
        )

    unsupported = re.search(
        r'\b(rsa|ecc|ecdh|x25519|ed25519|aes-gcm|gcm|blowfish|twofish|serpent|pgp|openpgp)\b',
        text,
        flags=re.IGNORECASE,
    )
    if unsupported:
        return (
            "ضمن هذه المنصة، لن أطرح إلا الخوارزميات المتوفرة فعليًا: "
            "Fernet + PBKDF2، AES-256-CBC + PBKDF2، ChaCha20 + PBKDF2، و XOR Stream (تعليمي فقط). "
            "اكتب لي حالة الاستخدام وسأعطيك أفضل اختيار من هذه الخيارات فقط."
        )
    return text


@app.route('/api/crypt/recommend', methods=['POST'])
def crypt_recommend_route():
    data = request.get_json(silent=True) or {}
    audience = str(data.get('audience') or '').strip()
    sensitivity = str(data.get('sensitivity') or 'high').strip().lower()
    purpose = str(data.get('purpose') or '').strip()

    if not audience:
        return jsonify({"error": "وصف الجهة المستلمة مطلوب"}), 400

    fallback = _fallback_crypt_recommendation(audience, sensitivity, purpose)

    if not DO_AI_KEY:
        return jsonify({"success": True, "recommendation": fallback, "source": "fallback"})

    advisor_system = (
        "You are a cryptography advisor for a secure messaging app. "
        "Return strict JSON only with keys: method, kdf_profile, output_format, reason, warning. "
        "method must be one of: fernet, aes-cbc, chacha20, xor-stream. "
        "kdf_profile must be one of: balanced, strong, paranoid. "
        "output_format must be one of: b64, b64url. "
        "Prefer security and practical sharing compatibility. "
        "Avoid recommending xor-stream unless user explicitly asks for learning/demo."
    )
    advisor_prompt = (
        f"Recipient context: {audience}\n"
        f"Sensitivity: {sensitivity}\n"
        f"Purpose: {purpose or 'general'}\n"
        "Choose one best configuration and explain briefly in Arabic in 'reason'."
    )

    try:
        raw = _call_do_ai(advisor_prompt, system_prompt=advisor_system)
        candidate = raw.strip()
        match = re.search(r'\{[\s\S]*\}', candidate)
        if match:
            candidate = match.group(0)
        parsed = json.loads(candidate)
        rec = _normalize_crypt_recommendation(parsed)
        return jsonify({"success": True, "recommendation": rec, "source": "ai"})
    except Exception:
        return jsonify({"success": True, "recommendation": fallback, "source": "fallback"})


@app.route('/api/crypt/recommend/chat', methods=['POST'])
def crypt_recommend_chat_route():
    data = request.get_json(silent=True) or {}
    message = str(data.get('message') or '').strip()
    context = data.get('context') or {}
    audience = str(context.get('audience') or '').strip()
    sensitivity = str(context.get('sensitivity') or 'high').strip().lower()
    purpose = str(context.get('purpose') or '').strip()
    conversation_id = str(data.get('conversation_id') or '').strip()

    if not message:
        return jsonify({"success": False, "error": "message required"}), 400
    if not conversation_id:
        conversation_id = secrets.token_urlsafe(10)

    user_key = str(session.get('user_id') or 'guest')
    session_key = f"crypt_adv::{user_key}::{conversation_id}"
    state = AI_CHAT_SESSIONS.get(session_key) or {"messages": []}
    raw_messages = state.get('messages') if isinstance(state, dict) else []
    history = list(raw_messages) if isinstance(raw_messages, list) else []

    fallback = _fallback_crypt_recommendation(audience or message, sensitivity, purpose)
    default_reply = (
        "هذه توصية أولية حسب التفاصيل الحالية. "
        f"استخدم {fallback['method']} مع {fallback['kdf_profile']} و {fallback['output_format']}."
    )

    if not DO_AI_KEY:
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": default_reply})
        AI_CHAT_SESSIONS[session_key] = {"messages": history[-16:]}
        return jsonify({
            "success": True,
            "conversation_id": conversation_id,
            "reply": default_reply,
            "recommendation": fallback,
            "source": "fallback"
        })

    topic_seed = f"{message} {audience} {purpose} encryption cryptography secure"
    topic = _classify_ai_topic(topic_seed)
    system_prompt = _build_ai_system_prompt(topic, user_text=message) + (
        "\n\n"
        "قواعد إلزامية لمستشار التشفير داخل المنصة:\n"
        "- ممنوع اقتراح أي خوارزمية غير موجودة في المنصة.\n"
        "- الخيارات الوحيدة المسموحة: fernet، aes-cbc، chacha20، xor-stream.\n"
        "- إذا طلب المستخدم خوارزمية غير متاحة، ارفض بلطف واقترح أقرب بديل من الخيارات المتاحة فقط.\n"
        "- لا تذكر RSA أو AES-GCM أو ECC أو PGP كخيارات تنفيذ داخل المنصة."
    )

    context_lines = []
    if audience:
        context_lines.append(f"المستلم/الجهة: {audience}")
    if sensitivity:
        context_lines.append(f"الحساسية: {sensitivity}")
    if purpose:
        context_lines.append(f"الغرض: {purpose}")

    enriched_message = message
    if context_lines:
        enriched_message = message + "\n\n[سياق التشفير]\n" + "\n".join(context_lines)

    history_for_ai = history[-12:] + [{"role": "user", "content": enriched_message}]
    try:
        reply = _call_do_ai_with_history(history_for_ai, system_prompt=system_prompt).strip() or default_reply
        reply = _enforce_platform_crypto_reply_scope(reply)
        recommendation = _fallback_crypt_recommendation((audience + ' ' + message).strip(), sensitivity, purpose)

        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": reply})
        AI_CHAT_SESSIONS[session_key] = {"messages": history[-16:]}

        return jsonify({
            "success": True,
            "conversation_id": conversation_id,
            "reply": reply,
            "recommendation": recommendation,
            "source": "ai"
        })
    except Exception:
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": default_reply})
        AI_CHAT_SESSIONS[session_key] = {"messages": history[-16:]}
        return jsonify({
            "success": True,
            "conversation_id": conversation_id,
            "reply": default_reply,
            "recommendation": fallback,
            "source": "fallback"
        })

@app.route('/crypt-text', methods=['POST'])
def crypt_text_route():
    data = request.json or {}
    text = data.get('text', '')
    key = data.get('key', '')
    action = data.get('action', '')
    method = (data.get('method') or 'fernet').lower()
    options = data.get('options') or {}
    if not text or not key or action not in ('encrypt', 'decrypt'):
        return jsonify({"error": "المدخلات غير مكتملة"}), 400
    try:
        if action == 'encrypt':
            result = encrypt_text_with_method(text, key, method, options)
            return jsonify({"result": result})
        else:
            selected_method = method if method else 'auto'
            result = decrypt_text_with_method(text, key, selected_method)
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


@app.route('/api/text-hide/encode', methods=['POST'])
def text_hide_encode_route():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "يرجى اختيار ملف TXT"}), 400
    file = request.files['file']
    filename = file.filename or 'text.txt'
    if not filename.lower().endswith('.txt'):
        return jsonify({"success": False, "error": "الامتداد المدعوم هو TXT فقط"}), 400

    secret = (request.form.get('secret') or '').strip()
    if not secret:
        return jsonify({"success": False, "error": "النص السري مطلوب"}), 400

    try:
        content = file.read().decode('utf-8', errors='replace')
        merged = hide_secret_in_txt(content, secret)
        add_audit_log("TXT Hide", f"إخفاء نص داخل {filename}", username=session.get('username', ''))
        return send_file(
            io.BytesIO(merged.encode('utf-8')),
            mimetype='text/plain; charset=utf-8',
            as_attachment=True,
            download_name=filename.replace('.txt', '') + '_with_hidden.txt'
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route('/api/text-hide/decode', methods=['POST'])
def text_hide_decode_route():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "يرجى اختيار ملف TXT"}), 400
    file = request.files['file']
    filename = file.filename or 'text.txt'
    if not filename.lower().endswith('.txt'):
        return jsonify({"success": False, "error": "الامتداد المدعوم هو TXT فقط"}), 400

    try:
        content = file.read().decode('utf-8', errors='replace')
        secret = extract_secret_from_txt(content)
        add_audit_log("TXT Reveal", f"استخراج نص من {filename}", username=session.get('username', ''))
        return jsonify({"success": True, "secret": secret})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

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
        return jsonify({"error": "كلمة السر الرئيسية غير صحيحة  ."}), 401

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
    try:
        file = request.files.get('file')
        if not file or not file.filename:
            return jsonify({"error": "لم يتم إرسال ملف النسخة الاحتياطية."}), 400

        filename = (file.filename or '').lower()
        if not (filename.endswith('.bak') or filename.endswith('.titan.bak')):
            return jsonify({"error": "صيغة الملف غير مدعومة. اختر ملف نسخ احتياطي بصيغة .bak"}), 400

        data = file.read()
        if not data:
            return jsonify({"error": "الملف المرفوع فارغ."}), 400

        # Vault backups are encrypted as: 16-byte salt + Fernet payload (starts with b'gAAAAA').
        if len(data) < 24 or data[16:22] != b'gAAAAA':
            return jsonify({"error": "ملف النسخة الاحتياطية غير صالح أو تالف."}), 400

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



@app.route('/api/burn-note/create', methods=['POST'])
def create_burn_note():
    payload = request.get_json(silent=True) or {}
    text = (request.form.get('text') or payload.get('text') or '').strip()
    media = request.files.get('media')

    note_payload = None

    if media and (media.filename or '').strip():
        raw = media.read()
        if not raw:
            return jsonify({"error": "الملف المرفوع فارغ"}), 400
        if len(raw) > (8 * 1024 * 1024):
            return jsonify({"error": "حجم الملف كبير جداً (الحد 8MB)"}), 400

        mime = (media.mimetype or '').lower().strip()
        if mime.startswith('image/'):
            note_payload = {
                "type": "image",
                "mime": mime,
                "data_b64": base64.b64encode(raw).decode('ascii')
            }
        elif mime.startswith('audio/'):
            note_payload = {
                "type": "audio",
                "mime": mime,
                "data_b64": base64.b64encode(raw).decode('ascii')
            }
        else:
            return jsonify({"error": "نوع الملف غير مدعوم. مسموح فقط صورة أو صوت."}), 400

    if text:
        if note_payload is None:
            note_payload = {"type": "text", "text": text}
        else:
            note_payload["text"] = text

    if note_payload is None:
        return jsonify({"error": "نص فارغ"}), 400
    
    note_id = str(uuid.uuid4())
    BURN_NOTES[note_id] = note_payload
    _burn_note_store_db(note_id, note_payload)
    add_audit_log("رسالة تدمير ذاتي 🔥", f"تم توليد رابط رسالة جديدة")
    
    # Generate full access URL
    url = f"{request.host_url}burn/{note_id}"
    return jsonify({"link": url})

@app.route('/burn/<note_id>', methods=['GET'])
def view_burn_note(note_id):
    # Strict one-time read: consume DB first (atomic), then clear any RAM mirror copy.
    payload = _burn_note_pop_db(note_id)
    if payload is not None:
        BURN_NOTES.pop(note_id, None)
    else:
        # Fallback when DB is unavailable: use RAM once.
        payload = BURN_NOTES.pop(note_id, None)

    if payload is not None:
        note_type = 'text'
        media_mime = ''
        media_b64 = ''
        text = ''

        if isinstance(payload, dict):
            note_type = str(payload.get('type') or 'text')
            media_mime = str(payload.get('mime') or '')
            media_b64 = str(payload.get('data_b64') or '')
            text = str(payload.get('text') or '')
        else:
            text = str(payload or '')

        if note_type in ('image', 'audio') and media_b64:
            safe_mime = html.escape(media_mime, quote=True)
            safe_b64 = html.escape(media_b64, quote=True)
            safe_caption = html.escape(text).replace('\n', '<br>') if text else ''
            is_audio = note_type == 'audio'
            media_html = ''
            if note_type == 'image':
                media_html = f'<img id="secureMedia" src="data:{safe_mime};base64,{safe_b64}" alt="burn image" style="max-width:100%;max-height:52vh;border-radius:10px;border:1px solid #374151;object-fit:contain;" />'
            else:
                media_html = f'<audio id="secureMedia" autoplay preload="auto" playsinline controlsList="nodownload noplaybackrate" style="width:100%;pointer-events:none;" src="data:{safe_mime};base64,{safe_b64}"></audio>'

            hold_btn_html = '' if is_audio else '<button id="holdRevealBtn" class="hold-btn">👆 اضغط مطولاً لعرض المحتوى</button>'
            wrap_class = 'secure-media' if is_audio else 'secure-media locked'
            warning_html = '🎧 سيتم تدمير الرسالة بعد انتهاء تشغيل التسجيل كاملاً. المتبقي التقريبي: <span id="countdown">--</span> ثانية' if is_audio else '⚠️ سيتم إخفاء المحتوى تلقائيًا خلال <span id="countdown">10</span> ثوانٍ'

            add_audit_log("رسالة مدمرة 💣", f"تم فتح رسالة {note_type} وتدميرها للأبد")
            return f'''
            <!DOCTYPE html>
            <html lang="ar" dir="rtl">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>وسيط ذاتي التدمير | TITAN</title>
                <style>
                    body {{ background: #050505; color: #fff; font-family: 'Segoe UI', Tahoma, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; background-image: radial-gradient(circle at center, #2e0909 0%, #050505 100%); user-select: none; -webkit-user-select: none; }}
                    .container {{ background: #0a0a0a; border: 1px solid #ef4444; border-radius: 12px; padding: 28px; box-shadow: 0 0 50px rgba(239, 68, 68, 0.2); max-width: 720px; text-align: center; position: relative; overflow: hidden; width: 94%; transition: filter 0.2s, opacity 0.2s; }}
                    .container::before {{ content:""; position:absolute; top:0; left:0; right:0; height:4px; background:linear-gradient(90deg, #ef4444, #f97316); }}
                    .warning {{ margin-top: 20px; font-size: 14px; color: #ef4444; opacity: 0.9; font-weight: bold; letter-spacing: 1px; }}
                    .secure-media {{ background:#000; border:1px dashed #ef4444; border-radius:10px; padding:14px; }}
                    .secure-media.locked {{ filter: blur(20px); opacity: 0.2; pointer-events: none; }}
                    .caption {{ margin-top: 10px; color: #d1d5db; line-height: 1.8; text-align: right; }}
                    .hold-btn {{ display: inline-flex; align-items: center; justify-content: center; gap: 8px; border: 1px solid #ef4444; color: #fecaca; background: rgba(239, 68, 68, 0.14); border-radius: 10px; padding: 10px 16px; font-weight: 700; cursor: pointer; margin-bottom: 12px; }}
                </style>
            </head>
            <body>
                <div class="container" id="secureContainer">
                    <div style="font-size: 52px; margin-bottom: 12px;">💣</div>
                    <h1 style="color:#ef4444;margin:0 0 8px 0;">تم فتح الرسالة بنجاح</h1>
                    <p style="color:#9ca3af;font-size:14px;line-height:1.6;margin-bottom:14px;">هذه رسالة لمرة واحدة فقط، وبعد إغلاق الصفحة لن تكون متاحة مجددًا.</p>
                    {hold_btn_html}
                    <div class="{wrap_class}" id="secureMediaWrap">{media_html}</div>
                    <div class="caption">{safe_caption}</div>
                    <div class="warning" id="timerWarning">{warning_html}</div>
                </div>
                <script>
                    let timeLeft = 10;
                    const isAudio = {str(is_audio).lower()};
                    const countdownEl = document.getElementById('countdown');
                    const warningBox = document.getElementById('timerWarning');
                    const holdBtn = document.getElementById('holdRevealBtn');
                    const wrap = document.getElementById('secureMediaWrap');
                    const audioEl = document.getElementById('secureMedia');
                    let destroyed = false;
                    let timer = null;
                    let maxAllowedTime = 0;

                    function destroyNow() {{
                        if (destroyed) return;
                        destroyed = true;
                        if (timer) clearInterval(timer);
                        if (holdBtn) holdBtn.remove();
                        wrap.classList.remove('locked');
                        wrap.innerHTML = '<div style="color:#ef4444;font-weight:900;font-size:22px;padding:20px;">💥 تم تدمير المحتوى نهائياً</div>';
                        warningBox.innerText = 'SECURE BURN COMPLETE // SYSTEM LOGGED';
                    }}

                    function lockView() {{ if (!isAudio) wrap.classList.add('locked'); }}
                    function unlockView() {{ if (!destroyed && !isAudio) wrap.classList.remove('locked'); }}

                    if (holdBtn) {{
                        holdBtn.addEventListener('mousedown', unlockView);
                        holdBtn.addEventListener('mouseup', lockView);
                        holdBtn.addEventListener('mouseleave', lockView);
                        holdBtn.addEventListener('touchstart', (e) => {{ e.preventDefault(); unlockView(); }}, {{ passive: false }});
                        holdBtn.addEventListener('touchend', lockView);
                    }}

                    if (isAudio && audioEl) {{
                        audioEl.controls = false;
                        audioEl.loop = false;

                        const forcePlay = () => {{
                            if (destroyed) return;
                            audioEl.play().catch(() => {{
                                warningBox.innerText = 'اضغط مرة واحدة على الشاشة لبدء التشغيل التلقائي ثم انتظر حتى النهاية...';
                            }});
                        }};

                        const updateRemaining = () => {{
                            if (!countdownEl) return;
                            const dur = Number(audioEl.duration || 0);
                            const cur = Number(audioEl.currentTime || 0);
                            if (cur > maxAllowedTime) maxAllowedTime = cur;
                            if (dur > 0) {{
                                const rem = Math.max(0, Math.ceil(dur - cur));
                                countdownEl.innerText = String(rem);
                            }}
                        }};

                        audioEl.addEventListener('loadedmetadata', () => {{
                            maxAllowedTime = 0;
                            forcePlay();
                            updateRemaining();
                        }});
                        audioEl.addEventListener('loadedmetadata', updateRemaining);
                        audioEl.addEventListener('timeupdate', updateRemaining);
                        audioEl.addEventListener('pause', () => {{
                            if (!destroyed && !audioEl.ended) forcePlay();
                        }});
                        audioEl.addEventListener('seeking', () => {{
                            const target = Number(audioEl.currentTime || 0);
                            if (target < (maxAllowedTime - 0.25) || target > (maxAllowedTime + 1.0)) {{
                                audioEl.currentTime = maxAllowedTime;
                            }}
                        }});
                        audioEl.addEventListener('ratechange', () => {{
                            if (audioEl.playbackRate !== 1) audioEl.playbackRate = 1;
                        }});
                        audioEl.addEventListener('ended', destroyNow);

                        // Fallback for autoplay policy: first user interaction starts playback once.
                        window.addEventListener('pointerdown', forcePlay, {{ once: true }});
                        forcePlay();
                    }} else {{
                        timer = setInterval(() => {{
                            timeLeft--;
                            if (countdownEl) countdownEl.innerText = timeLeft;
                            if (timeLeft <= 0) destroyNow();
                        }}, 1000);
                    }}

                    ['copy','cut','paste','selectstart','dragstart','contextmenu'].forEach((evt) => {{
                        document.addEventListener(evt, (e) => e.preventDefault());
                    }});

                    const secContainer = document.getElementById('secureContainer');
                    window.addEventListener('blur', () => {{
                        lockView();
                        secContainer.style.filter = 'blur(30px)';
                        secContainer.style.opacity = '0.05';
                    }});
                    window.addEventListener('focus', () => {{
                        secContainer.style.filter = 'none';
                        secContainer.style.opacity = '1';
                    }});
                </script>
            </body>
            </html>
            '''

        safe_text = html.escape(text).replace('\n', '<br>')
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
                .secure-text.locked {{
                    filter: blur(14px);
                    opacity: 0.2;
                }}
                .hold-btn {{
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    gap: 8px;
                    border: 1px solid #ef4444;
                    color: #fecaca;
                    background: rgba(239, 68, 68, 0.14);
                    border-radius: 10px;
                    padding: 10px 16px;
                    font-weight: 700;
                    cursor: pointer;
                    margin-bottom: 12px;
                }}
            </style>
        </head>
        <body oncontextmenu="return false;" onkeydown="return disableCopyKeys(event);">
            <div class="container" id="secureContainer">
                <div style="font-size: 60px; margin-bottom: 20px; animation: pulse-icon 2s infinite;">💣</div>
                <h1>تم فتح الرسالة بنجاح</h1>
                <p class="subtitle" id="topSubtitle">هذه رسالة لمرة واحدة فقط، وبعد إغلاق الصفحة لن تكون متاحة مجددًا.</p>
                <button id="holdRevealBtn" class="hold-btn">👆 اضغط مطولاً لعرض المحتوى</button>
                <!-- Full Arabic text - browser handles letter joining natively -->
                <div class="secure-text locked" id="secureText">{safe_text}</div>
                <p style="color:#6b7280; font-size:10px; margin:0 0 10px 0; letter-spacing:1px;">🔒 Secure View Enabled</p>
                <div class="warning" id="timerWarning">⚠️ سيتم إخفاء المحتوى تلقائيًا خلال <span id="countdown">10</span> ثوانٍ</div>
            </div>
            
            <script>
                let timeLeft = 10;
                const countdownEl = document.getElementById('countdown');
                const warningBox = document.getElementById('timerWarning');
                const topSubs = document.getElementById('topSubtitle');
                const secureTextEl = document.getElementById('secureText');
                const holdBtn = document.getElementById('holdRevealBtn');
                let destroyed = false;

                function lockView() {{
                    secureTextEl.classList.add('locked');
                }}

                function unlockView() {{
                    if (!destroyed) secureTextEl.classList.remove('locked');
                }}

                holdBtn.addEventListener('mousedown', unlockView);
                holdBtn.addEventListener('mouseup', lockView);
                holdBtn.addEventListener('mouseleave', lockView);
                holdBtn.addEventListener('touchstart', (e) => {{ e.preventDefault(); unlockView(); }}, {{ passive: false }});
                holdBtn.addEventListener('touchend', lockView);

                const timer = setInterval(() => {{
                    timeLeft--;
                    countdownEl.innerText = timeLeft;
                    
                    if (timeLeft <= 3) {{
                        countdownEl.style.fontSize = '24px';
                        countdownEl.parentElement.style.textShadow = '0 0 10px red';
                    }}
                    
                    if(timeLeft <= 0) {{
                        clearInterval(timer);
                        destroyed = true;
                        holdBtn.remove();
                        // Stop the CSS animation and replace text with destroyed message
                        secureTextEl.style.animation = 'none';
                        secureTextEl.style.color = '#ef4444';
                        secureTextEl.style.textAlign = 'center';
                        secureTextEl.classList.remove('locked');
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

                ['copy','cut','paste','selectstart','dragstart'].forEach((evt) => {{
                    document.addEventListener(evt, (e) => e.preventDefault());
                }});
                
                // Hide content when window loses focus to prevent screenshots/recording
                const secContainer = document.getElementById('secureContainer');
                window.addEventListener('blur', () => {{
                    lockView();
                    secContainer.style.filter = 'blur(30px)';
                    secContainer.style.opacity = '0.05';
                }});
                window.addEventListener('focus', () => {{
                    secContainer.style.filter = 'none';
                    secContainer.style.opacity = '1';
                }});

                document.addEventListener('visibilitychange', () => {{
                    if (document.hidden && !destroyed) {{
                        destroyed = true;
                        clearInterval(timer);
                        holdBtn.remove();
                        secureTextEl.style.animation = 'none';
                        secureTextEl.classList.remove('locked');
                        secureTextEl.style.color = '#ef4444';
                        secureTextEl.style.textAlign = 'center';
                        secureTextEl.textContent = '💥 تم تدمير الرسالة بسبب مغادرة الصفحة';
                        warningBox.innerText = 'SECURE BURN COMPLETE // HIDDEN TAB DETECTED';
                        topSubs.innerText = 'تم الإخفاء الذاتي بعد مغادرة الصفحة.';
                    }}
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
    mode = data.get('mode', 'deep')
    result = check_username_presence(username, mode)
    if not result.get('success'):
        return jsonify(result), 400
    add_audit_log("Username Hunter (OSINT)", f"فحص اليوزرنيم: {username} | mode={result.get('mode', 'deep')}")
    return jsonify(result)


def _ir_priority_rank(priority: str) -> int:
    mapping = {'p1': 1, 'p2': 2, 'p3': 3, 'p4': 4}
    return mapping.get((priority or 'p2').lower(), 2)


def _ir_recommended_priority(severity: str, top_ioc_risk: int = 0, sla_breached: bool = False) -> str:
    sev = (severity or 'medium').lower()
    if sev == 'critical' or top_ioc_risk >= 90:
        return 'p1'
    if sev == 'high' or top_ioc_risk >= 75 or sla_breached:
        return 'p2'
    if sev == 'medium' or top_ioc_risk >= 40:
        return 'p3'
    return 'p4'


def _ir_recompute_case_priority(conn, case_id: int, user_id: int | None, reason: str, actor: str = '') -> dict:
    if user_id is None:
        return {"updated": False, "error": "case_not_found"}
    c = conn.cursor()
    c.execute(
        "SELECT severity, priority, status, due_at FROM incident_cases WHERE id=%s AND user_id=%s",
        (case_id, user_id)
    )
    row = c.fetchone()
    if not row:
        return {"updated": False, "error": "case_not_found"}

    severity, current_priority, status, due_at = row
    c.execute("SELECT COALESCE(MAX(risk_score), 0) FROM incident_iocs WHERE case_id=%s", (case_id,))
    top_ioc_risk = int((c.fetchone() or [0])[0] or 0)

    now = datetime.datetime.now()
    due_dt = None
    try:
        due_dt = datetime.datetime.strptime(due_at, "%Y-%m-%d %H:%M:%S") if due_at else None
    except Exception:
        due_dt = None
    sla_breached = bool(due_dt and status != 'closed' and now > due_dt)

    recommended = _ir_recommended_priority(severity, top_ioc_risk=top_ioc_risk, sla_breached=sla_breached)
    old_rank = _ir_priority_rank(current_priority)
    rec_rank = _ir_priority_rank(recommended)

    # Auto-priority only escalates urgency automatically; downgrades remain manual.
    if rec_rank < old_rank:
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        c.execute("UPDATE incident_cases SET priority=%s, updated_at=%s WHERE id=%s", (recommended, now_str, case_id))
        c.execute(
            "INSERT INTO incident_case_notes (case_id, note_type, note, created_by, created_at) VALUES (%s,%s,%s,%s,%s)",
            (
                case_id,
                'analysis',
                f"Auto-priority escalated {current_priority} -> {recommended} (reason={reason}, top_ioc_risk={top_ioc_risk}, sla_breached={sla_breached})",
                actor,
                now_str,
            )
        )
        return {"updated": True, "from": current_priority, "to": recommended, "recommended": recommended, "top_ioc_risk": top_ioc_risk, "sla_breached": sla_breached}

    return {"updated": False, "from": current_priority, "to": current_priority, "recommended": recommended, "top_ioc_risk": top_ioc_risk, "sla_breached": sla_breached}


@app.route('/api/incidents/create', methods=['POST'])
def ir_create_case_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    data = request.json or {}
    title = data.get('title', '').strip()
    severity = (data.get('severity') or 'medium').strip().lower()
    priority = (data.get('priority') or 'p2').strip().lower()
    category = (data.get('category') or 'general').strip().lower()
    source = (data.get('source') or 'manual').strip().lower()
    owner = (data.get('owner') or 'SOC').strip()
    try:
        sla_minutes = int(data.get('sla_minutes', 240) or 240)
    except Exception:
        sla_minutes = 240
    sla_minutes = max(15, min(10080, sla_minutes))
    description = data.get('description', '').strip()
    if not title:
        return jsonify({"success": False, "error": "عنوان القضية مطلوب"}), 400
    if severity not in ('low', 'medium', 'high', 'critical'):
        severity = 'medium'
    if priority not in ('p1', 'p2', 'p3', 'p4'):
        priority = 'p2'
    if source not in ('manual', 'siem', 'user_report', 'external_feed'):
        source = 'manual'
    if category not in ('general', 'phishing', 'malware', 'account_takeover', 'data_leak', 'insider', 'fraud'):
        category = 'general'
    recommended_on_create = _ir_recommended_priority(severity, top_ioc_risk=0, sla_breached=False)
    if _ir_priority_rank(recommended_on_create) < _ir_priority_rank(priority):
        priority = recommended_on_create
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    due_at = (datetime.datetime.now() + datetime.timedelta(minutes=sla_minutes)).strftime("%Y-%m-%d %H:%M:%S")

    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO incident_cases
            (user_id, title, severity, priority, status, category, source, owner, sla_minutes, due_at, description, created_at, updated_at)
            VALUES (%s,%s,%s,%s,'open',%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (user_id, title, severity, priority, category, source, owner, sla_minutes, due_at, description, now, now))
        row = c.fetchone()
        if not row:
            conn.rollback()
            return jsonify({"success": False, "error": "فشل إنشاء القضية"}), 500
        case_id = row[0]
        c.execute(
            "INSERT INTO incident_case_notes (case_id, note_type, note, created_by, created_at) VALUES (%s,%s,%s,%s,%s)",
            (case_id, 'created', 'Case created and queued for triage.', session.get('username', ''), now)
        )
        conn.commit()
        add_audit_log("Incident Created", f"case#{case_id} {title} sev={severity} prio={priority}", username=session.get('username', ''))
        return jsonify({"success": True, "case_id": case_id, "due_at": due_at})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/incidents/summary', methods=['GET'])
def ir_summary_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    conn = None
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM incident_cases WHERE user_id=%s", (user_id,))
        total = int((c.fetchone() or [0])[0] or 0)

        c.execute("SELECT status, COUNT(*) FROM incident_cases WHERE user_id=%s GROUP BY status", (user_id,))
        by_status = {r[0]: int(r[1]) for r in (c.fetchall() or [])}

        c.execute("SELECT severity, COUNT(*) FROM incident_cases WHERE user_id=%s GROUP BY severity", (user_id,))
        by_severity = {r[0]: int(r[1]) for r in (c.fetchall() or [])}

        c.execute(
            "SELECT COUNT(*) FROM incident_cases WHERE user_id=%s AND status != 'closed' AND due_at IS NOT NULL AND due_at < %s",
            (user_id, now)
        )
        sla_breached = int((c.fetchone() or [0])[0] or 0)

        c.execute(
            """
            SELECT ROUND(AVG(ii.risk_score)::numeric, 2)
            FROM incident_iocs ii
            JOIN incident_cases ic ON ic.id = ii.case_id
            WHERE ic.user_id=%s
            """,
            (user_id,)
        )
        avg_ioc_risk = float((c.fetchone() or [0])[0] or 0)

        return jsonify({
            "success": True,
            "summary": {
                "total": total,
                "open": by_status.get('open', 0),
                "investigating": by_status.get('investigating', 0),
                "contained": by_status.get('contained', 0),
                "closed": by_status.get('closed', 0),
                "critical": by_severity.get('critical', 0),
                "high": by_severity.get('high', 0),
                "sla_breached": sla_breached,
                "avg_ioc_risk": avg_ioc_risk,
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/incidents/list', methods=['GET'])
def ir_list_cases_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    q = (request.args.get('q') or '').strip().lower()
    status_filter = (request.args.get('status') or 'all').strip().lower()
    severity_filter = (request.args.get('severity') or 'all').strip().lower()
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        query = """
            SELECT
                ic.id, ic.title, ic.severity, ic.priority, ic.status, ic.category, ic.source, ic.owner,
                ic.sla_minutes, ic.due_at, ic.closed_at, ic.description, ic.created_at, ic.updated_at,
                COALESCE(COUNT(ii.id), 0) AS ioc_count,
                COALESCE(SUM(CASE WHEN ii.risk_score >= 70 THEN 1 ELSE 0 END), 0) AS high_ioc_count,
                COALESCE(MAX(ii.risk_score), 0) AS top_ioc_risk
            FROM incident_cases ic
            LEFT JOIN incident_iocs ii ON ii.case_id = ic.id
            WHERE ic.user_id=%s
        """
        params: list[object] = [user_id]
        if q:
            query += " AND (LOWER(ic.title) LIKE %s OR LOWER(ic.description) LIKE %s)"
            like_q = f"%{q}%"
            params.extend([like_q, like_q])
        if status_filter in ('open', 'investigating', 'contained', 'closed'):
            query += " AND ic.status=%s"
            params.append(status_filter)
        if severity_filter in ('low', 'medium', 'high', 'critical'):
            query += " AND ic.severity=%s"
            params.append(severity_filter)
        query += " GROUP BY ic.id ORDER BY ic.id DESC"

        c.execute(query, tuple(params))
        rows = c.fetchall()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cases = [
            {
                "id": r[0], "title": r[1], "severity": r[2], "priority": r[3], "status": r[4], "category": r[5],
                "source": r[6], "owner": r[7], "sla_minutes": r[8], "due_at": r[9], "closed_at": r[10],
                "description": r[11], "created_at": r[12], "updated_at": r[13],
                "ioc_count": int(r[14] or 0), "high_ioc_count": int(r[15] or 0), "top_ioc_risk": int(r[16] or 0),
                "sla_state": 'breached' if (r[9] and r[4] != 'closed' and str(r[9]) < now) else 'ok',
                "recommended_priority": _ir_recommended_priority(
                    str(r[2] or 'medium'),
                    top_ioc_risk=int(r[16] or 0),
                    sla_breached=bool(r[9] and r[4] != 'closed' and str(r[9]) < now)
                )
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
    status_aliases = {
        'in_progress': 'investigating',
        'resolved': 'contained',
    }
    status = status_aliases.get(status, status)
    if status not in ('open', 'investigating', 'contained', 'closed'):
        return jsonify({"success": False, "error": "Status غير صالح"}), 400
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    closed_at = now if status == 'closed' else None
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE incident_cases SET status=%s, closed_at=%s, updated_at=%s WHERE id=%s AND user_id=%s",
            (status, closed_at, now, case_id, user_id)
        )
        c.execute(
            "INSERT INTO incident_case_notes (case_id, note_type, note, created_by, created_at) VALUES (%s,%s,%s,%s,%s)",
            (case_id, 'status', f"Status changed to {status}", session.get('username', ''), now)
        )
        _ir_recompute_case_priority(conn, case_id, user_id, reason='status_change', actor=session.get('username', ''))
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
        c.execute(
            "INSERT INTO incident_case_notes (case_id, note_type, note, created_by, created_at) VALUES (%s,%s,%s,%s,%s)",
            (case_id, 'ioc', f"IOC added: {ioc_type}={ioc_value} (risk={risk_score})", session.get('username', ''), now)
        )
        _ir_recompute_case_priority(conn, case_id, user_id, reason='ioc_added', actor=session.get('username', ''))
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


@app.route('/api/incidents/<int:case_id>/auto-priority', methods=['POST'])
def ir_auto_priority_route(case_id: int):
    user_id, err = _get_logged_in_user_id()
    if err: return err
    conn = None
    try:
        conn = get_db_conn()
        result = _ir_recompute_case_priority(conn, case_id, user_id, reason='manual_run', actor=session.get('username', ''))
        if result.get('error') == 'case_not_found':
            return jsonify({"success": False, "error": "القضية غير موجودة"}), 404
        conn.commit()
        add_audit_log("Incident Auto Priority", f"case#{case_id} {result.get('from')} -> {result.get('to')}", username=session.get('username', ''))
        return jsonify({"success": True, **result})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/incidents/<int:case_id>/notes', methods=['POST'])
def ir_add_note_route(case_id: int):
    user_id, err = _get_logged_in_user_id()
    if err: return err
    data = request.json or {}
    note_type = (data.get('note_type') or 'analysis').strip().lower()
    note = (data.get('note') or '').strip()
    if note_type not in ('analysis', 'containment', 'eradication', 'recovery', 'lesson', 'status', 'ioc', 'created'):
        note_type = 'analysis'
    if not note:
        return jsonify({"success": False, "error": "الملاحظة مطلوبة"}), 400
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT id FROM incident_cases WHERE id=%s AND user_id=%s", (case_id, user_id))
        if not c.fetchone():
            return jsonify({"success": False, "error": "القضية غير موجودة"}), 404
        c.execute(
            "INSERT INTO incident_case_notes (case_id, note_type, note, created_by, created_at) VALUES (%s,%s,%s,%s,%s)",
            (case_id, note_type, note, session.get('username', ''), now)
        )
        c.execute("UPDATE incident_cases SET updated_at=%s WHERE id=%s", (now, case_id))
        conn.commit()
        add_audit_log("Incident Note", f"case#{case_id} type={note_type}", username=session.get('username', ''))
        return jsonify({"success": True})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/incidents/<int:case_id>/notes', methods=['GET'])
def ir_list_notes_route(case_id: int):
    user_id, err = _get_logged_in_user_id()
    if err: return err
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT id FROM incident_cases WHERE id=%s AND user_id=%s", (case_id, user_id))
        if not c.fetchone():
            return jsonify({"success": False, "error": "القضية غير موجودة"}), 404
        c.execute(
            "SELECT id, note_type, note, created_by, created_at FROM incident_case_notes WHERE case_id=%s ORDER BY id DESC",
            (case_id,)
        )
        notes = [
            {"id": r[0], "note_type": r[1], "note": r[2], "created_by": r[3], "created_at": r[4]}
            for r in (c.fetchall() or [])
        ]
        return jsonify({"success": True, "notes": notes})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/incidents/<int:case_id>/evidence', methods=['POST'])
def ir_add_evidence_route(case_id: int):
    user_id, err = _get_logged_in_user_id()
    if err: return err
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "يرجى اختيار ملف دليل"}), 400

    file = request.files['file']
    note = (request.form.get('note') or '').strip()
    raw = file.read()
    if not raw:
        return jsonify({"success": False, "error": "الملف فارغ"}), 400

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_hash = hashlib.sha256(raw).hexdigest()
    mime_type = (file.mimetype or 'application/octet-stream').strip()
    filename = secure_filename(file.filename or 'evidence.bin')
    file_size = len(raw)

    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT id FROM incident_cases WHERE id=%s AND user_id=%s", (case_id, user_id))
        if not c.fetchone():
            return jsonify({"success": False, "error": "القضية غير موجودة"}), 404
        c.execute(
            """
            INSERT INTO incident_evidence (case_id, filename, file_hash, file_size, mime_type, note, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (case_id, filename, file_hash, file_size, mime_type, note, now)
        )
        c.execute(
            "INSERT INTO incident_case_notes (case_id, note_type, note, created_by, created_at) VALUES (%s,%s,%s,%s,%s)",
            (case_id, 'analysis', f"Evidence uploaded: {filename} sha256={file_hash[:16]}...", session.get('username', ''), now)
        )
        c.execute("UPDATE incident_cases SET updated_at=%s WHERE id=%s", (now, case_id))
        conn.commit()
        add_audit_log("Incident Evidence", f"case#{case_id} file={filename} size={file_size}", username=session.get('username', ''))
        return jsonify({"success": True, "filename": filename, "file_hash": file_hash, "file_size": file_size, "mime_type": mime_type})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/incidents/<int:case_id>/evidence', methods=['GET'])
def ir_list_evidence_route(case_id: int):
    user_id, err = _get_logged_in_user_id()
    if err: return err
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT id FROM incident_cases WHERE id=%s AND user_id=%s", (case_id, user_id))
        if not c.fetchone():
            return jsonify({"success": False, "error": "القضية غير موجودة"}), 404
        c.execute(
            "SELECT id, filename, file_hash, file_size, mime_type, note, created_at FROM incident_evidence WHERE case_id=%s ORDER BY id DESC",
            (case_id,)
        )
        evidence = [
            {
                "id": r[0], "filename": r[1], "file_hash": r[2], "file_size": int(r[3] or 0),
                "mime_type": r[4], "note": r[5], "created_at": r[6]
            }
            for r in (c.fetchall() or [])
        ]
        return jsonify({"success": True, "evidence": evidence})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


def _ir_build_report_payload(conn, case_id: int, user_id: int | None):
    if user_id is None:
        return None
    c = conn.cursor()
    c.execute(
        """
        SELECT id, title, severity, priority, status, category, source, owner,
               sla_minutes, due_at, closed_at, description, created_at, updated_at
        FROM incident_cases WHERE id=%s AND user_id=%s
        """,
        (case_id, user_id)
    )
    case_row = c.fetchone()
    if not case_row:
        return None

    c.execute("SELECT ioc_type, ioc_value, risk_score, created_at FROM incident_iocs WHERE case_id=%s ORDER BY id DESC", (case_id,))
    iocs = c.fetchall()
    c.execute("SELECT note_type, note, created_by, created_at FROM incident_case_notes WHERE case_id=%s ORDER BY id DESC", (case_id,))
    notes = c.fetchall()
    c.execute("SELECT filename, file_hash, file_size, mime_type, note, created_at FROM incident_evidence WHERE case_id=%s ORDER BY id DESC", (case_id,))
    evidence = c.fetchall()

    def _parse_dt(v):
        try:
            return datetime.datetime.strptime(v, "%Y-%m-%d %H:%M:%S") if v else None
        except Exception:
            return None

    created_dt = _parse_dt(case_row[12])
    closed_dt = _parse_dt(case_row[10])
    end_dt = closed_dt or datetime.datetime.now()
    mttr_minutes = int((end_dt - created_dt).total_seconds() // 60) if created_dt else 0
    mean_ioc_risk = round(sum((int(r[2] or 0) for r in iocs)) / max(1, len(iocs)), 2)

    return {
        "case": {
            "id": case_row[0], "title": case_row[1], "severity": case_row[2], "priority": case_row[3], "status": case_row[4],
            "category": case_row[5], "source": case_row[6], "owner": case_row[7], "sla_minutes": case_row[8],
            "due_at": case_row[9], "closed_at": case_row[10], "description": case_row[11], "created_at": case_row[12], "updated_at": case_row[13]
        },
        "iocs": [
            {"ioc_type": r[0], "ioc_value": r[1], "risk_score": r[2], "created_at": r[3]} for r in iocs
        ],
        "notes": [
            {"note_type": r[0], "note": r[1], "created_by": r[2], "created_at": r[3]} for r in notes
        ],
        "evidence": [
            {"filename": r[0], "file_hash": r[1], "file_size": r[2], "mime_type": r[3], "note": r[4], "created_at": r[5]} for r in evidence
        ],
        "metrics": {
            "ioc_count": len(iocs),
            "note_count": len(notes),
            "evidence_count": len(evidence),
            "high_risk_iocs": sum(1 for r in iocs if int(r[2] or 0) >= 70),
            "mean_ioc_risk": mean_ioc_risk,
            "mttr_minutes": mttr_minutes,
        },
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


def _build_minimal_pdf_bytes(lines: list[str]) -> bytes:
    safe_lines = [str(x or '').replace('(', '[').replace(')', ']').replace('\\', '/') for x in (lines or [])]
    y = 780
    content_lines = ["BT", "/F1 10 Tf"]
    for line in safe_lines[:90]:
        content_lines.append(f"1 0 0 1 40 {y} Tm ({line[:120]}) Tj")
        y -= 12
        if y < 40:
            break
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode('latin-1', errors='replace')

    objects: list[bytes] = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    objects.append(b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n")
    objects.append(b"4 0 obj << /Length " + str(len(stream)).encode('ascii') + b" >> stream\n" + stream + b"\nendstream endobj\n")
    objects.append(b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)
    xref_pos = len(pdf)
    pdf.extend(f"xref\n0 {len(objects)+1}\n".encode('ascii'))
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode('ascii'))
    pdf.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode('ascii'))
    return bytes(pdf)


def _shape_arabic_for_pdf(text: str) -> str:
    raw = str(text or '')
    if not _HAS_ARABIC_SHAPING or arabic_reshaper is None or get_display is None:
        return raw
    try:
        shaped = arabic_reshaper.reshape(raw)
        out = get_display(shaped)
        return str(out)
    except Exception:
        return raw


def _pdf_register_font() -> str:
    if not _HAS_REPORTLAB or pdfmetrics is None or TTFont is None:
        return 'Helvetica'
    font_name = 'Helvetica'
    candidates = [
        ('TITAN_Arabic', 'C:/Windows/Fonts/arial.ttf'),
        ('TITAN_Arabic', 'C:/Windows/Fonts/tahoma.ttf'),
    ]
    for name, path in candidates:
        try:
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont(name, path))
                return name
        except Exception:
            continue
    return font_name


@lru_cache(maxsize=1)
def _build_titan_logo_png_bytes() -> bytes:
    w, h = 920, 260
    img = Image.new('RGB', (w, h), (10, 12, 25))
    draw = ImageDraw.Draw(img)

    # Main plate
    draw.rounded_rectangle((14, 14, w - 14, h - 14), radius=28, fill=(18, 24, 46), outline=(124, 58, 237), width=4)
    draw.rounded_rectangle((30, 30, w - 30, h - 30), radius=22, fill=(9, 14, 28), outline=(56, 189, 248), width=2)

    def _load_font(size: int, bold: bool = False):
        candidates = [
            'C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf',
            'C:/Windows/Fonts/tahomabd.ttf' if bold else 'C:/Windows/Fonts/tahoma.ttf',
            'C:/Windows/Fonts/segoeuib.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf',
        ]
        for p in candidates:
            try:
                if os.path.exists(p):
                    return ImageFont.truetype(p, size=size)
            except Exception:
                continue
        return ImageFont.load_default()

    font_big = _load_font(110, bold=True)
    font_mid = _load_font(36, bold=True)
    font_small = _load_font(24, bold=False)

    draw.text((60, 72), 'TITAN', font=font_big, fill=(232, 224, 255))
    draw.text((530, 88), 'CYBER', font=font_mid, fill=(56, 189, 248))
    draw.text((530, 134), 'PLATFORM', font=font_mid, fill=(167, 139, 250))
    draw.text((64, 192), 'AI Security Engine', font=font_small, fill=(148, 163, 184))

    # Accent dots
    draw.ellipse((860, 42, 890, 72), fill=(34, 197, 94))
    draw.ellipse((860, 84, 890, 114), fill=(56, 189, 248))
    draw.ellipse((860, 126, 890, 156), fill=(168, 85, 247))

    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    return buf.getvalue()


def _build_learning_pdf_bytes_branded(payload: dict, lang: str = 'ar') -> bytes:
    if not _HAS_REPORTLAB or canvas is None:
        # Fallback to minimal engine when reportlab is unavailable.
        sim = payload.get('simulation') if isinstance(payload, dict) else {}
        sim = sim if isinstance(sim, dict) else {}
        analysis = payload.get('analysis') if isinstance(payload, dict) else {}
        analysis = analysis if isinstance(analysis, dict) else {}
        lines = [
            str(payload.get('platform_name') or 'TITAN CYBER PLATFORM'),
            f"Report ID: {payload.get('report_id', '')}",
            f"Scenario: {sim.get('title', '')}",
            f"Risk Score: {analysis.get('risk_score', 0)}/100",
            str(analysis.get('executive_summary', '')),
        ]
        return _build_minimal_pdf_bytes(lines)

    font_name = _pdf_register_font()
    page_w, page_h = A4
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    is_ar = str(lang or '').lower().startswith('ar')

    def tx(s: str) -> str:
        raw = str(s or '')
        if is_ar:
            return _shape_arabic_for_pdf(raw)
        return raw

    def _draw_confidential_watermark() -> None:
        label = tx('TITAN CONFIDENTIAL')
        c.saveState()
        try:
            try:
                c.setFillAlpha(0.18)  # type: ignore[attr-defined]
            except Exception:
                pass
            c.setFont(font_name, 58)
            c.setFillColorRGB(0.70, 0.35, 0.98)
            c.translate(page_w / 2, page_h / 2)
            c.rotate(32)
            c.drawCentredString(0, 0, label)
        finally:
            c.restoreState()

    def _draw_content_page_shell() -> None:
        # Full dark page background.
        c.setFillColorRGB(0.02, 0.01, 0.08)
        c.rect(0, 0, page_w, page_h, stroke=0, fill=1)

        # Top band.
        c.setFillColorRGB(0.11, 0.05, 0.27)
        c.rect(0, page_h - 110, page_w, 110, stroke=0, fill=1)
        c.setFillColorRGB(0.86, 0.41, 0.99)
        c.circle(42, page_h - 52, 18, stroke=0, fill=1)
        _draw_confidential_watermark()

        if ImageReader is not None:
            try:
                logo_small = ImageReader(io.BytesIO(_build_titan_logo_png_bytes()))
                c.drawImage(logo_small, 28, page_h - 102, width=120, height=36, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass

        c.setFillColorRGB(0.99, 0.95, 1)
        c.setFont(font_name, 16)
        c.drawString(72, page_h - 45, tx('TITAN'))
        c.setFont(font_name, 11)
        c.drawString(72, page_h - 64, tx(subtitle))

        c.setFont(font_name, 14)
        c.drawRightString(page_w - 36, page_h - 45, tx(title))
        c.setFont(font_name, 9)
        c.drawRightString(page_w - 36, page_h - 62, tx(f"Report ID: {report_id}"))

    sim = payload.get('simulation') if isinstance(payload, dict) else {}
    sim = sim if isinstance(sim, dict) else {}
    analysis = payload.get('analysis') if isinstance(payload, dict) else {}
    analysis = analysis if isinstance(analysis, dict) else {}

    title = 'تقرير التعلم والمحاكاة الدفاعية' if is_ar else 'Defensive Learning & Simulation Report'
    subtitle = 'منصة TITAN للأمن السيبراني' if is_ar else 'TITAN Cyber Platform'
    report_id = str(payload.get('report_id') or '')
    username = str(payload.get('username') or '')
    generated = str(sim.get('generated_at') or '')

    # Cover page
    c.setFillColorRGB(0.02, 0.01, 0.09)
    c.rect(0, 0, page_w, page_h, stroke=0, fill=1)
    c.setFillColorRGB(0.10, 0.03, 0.22)
    c.roundRect(32, 36, page_w - 64, page_h - 72, radius=20, stroke=0, fill=1)
    _draw_confidential_watermark()

    if ImageReader is not None:
        try:
            logo_reader = ImageReader(io.BytesIO(_build_titan_logo_png_bytes()))
            c.drawImage(logo_reader, 58, page_h - 250, width=480, height=136, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

    c.setFillColorRGB(0.97, 0.93, 1)
    c.setFont(font_name, 20)
    c.drawString(58, page_h - 290, tx(title))
    c.setFillColorRGB(0.82, 0.56, 0.98)
    c.setFont(font_name, 12)
    c.drawString(58, page_h - 316, tx(subtitle))

    c.setFillColorRGB(0.95, 0.90, 1)
    c.setFont(font_name, 11)
    c.drawString(58, page_h - 372, tx(f"Report ID: {report_id}"))
    c.drawString(58, page_h - 392, tx(f"User: {username}"))
    c.drawString(58, page_h - 412, tx(f"Generated: {generated}"))

    c.setFillColorRGB(0.83, 0.74, 0.96)
    c.setFont(font_name, 10)
    cover_note = (
        'This document is defensive and educational. No offensive instructions included.'
        if not is_ar else
        'هذا التقرير دفاعي وتوعوي فقط، ولا يتضمن تعليمات هجومية.'
    )
    c.drawString(58, 74, tx(cover_note))
    c.showPage()

    _draw_content_page_shell()

    y = page_h - 140
    c.setFillColorRGB(0.95, 0.88, 1)
    c.setFont(font_name, 10)
    c.drawString(36, y, tx(f"{'المستخدم' if is_ar else 'User'}: {username}"))
    c.drawRightString(page_w - 36, y, tx(f"{'تاريخ الإنشاء' if is_ar else 'Generated'}: {generated}"))
    y -= 20

    def _wrap_chunks(text: str, max_chars: int = 95) -> list[str]:
        src = str(text or '').strip()
        if not src:
            return ['']
        words = src.split(' ')
        chunks: list[str] = []
        cur = ''
        for w in words:
            candidate = (cur + ' ' + w).strip() if cur else w
            if len(candidate) <= max_chars:
                cur = candidate
                continue
            if cur:
                chunks.append(cur)
            if len(w) <= max_chars:
                cur = w
            else:
                for i in range(0, len(w), max_chars):
                    part = w[i:i + max_chars]
                    if len(part) == max_chars:
                        chunks.append(part)
                    else:
                        cur = part
        if cur:
            chunks.append(cur)
        return chunks or [src]

    sections = [
        (
            'شرح الثغرة' if is_ar else 'Vulnerability Brief',
            [
                f"{('العنوان' if is_ar else 'Title')}: {sim.get('vulnerability_title', '') or sim.get('title', '')}",
                str(sim.get('vulnerability_master_brief') or sim.get('summary') or 'N/A'),
            ],
        ),
        (
            'وين بتصير وكيف بتصير' if is_ar else 'Where It Happens and How',
            [
                str(sim.get('exploit_pattern') or 'N/A'),
            ],
        ),
        (
            'أشهر الأدوات' if is_ar else 'Common Tools',
            [f"- {x}" for x in (sim.get('common_tools') or [])] or ['- N/A'],
        ),
        (
            'أشهر الأوامر' if is_ar else 'Common Commands',
            [f"- {x}" for x in (sim.get('common_commands') or [])] or ['- N/A'],
        ),
    ]

    for section_title, rows in sections:
        if y < 90:
            c.showPage()
            _draw_content_page_shell()
            c.setFont(font_name, 10)
            c.setFillColorRGB(0.95, 0.88, 1)
            y = page_h - 50

        c.setFillColorRGB(0.86, 0.48, 1)
        c.setFont(font_name, 12)
        c.drawString(36, y, tx(section_title))
        y -= 16

        c.setFillColorRGB(0.93, 0.86, 1)
        c.setFont(font_name, 9.5)
        for row in rows:
            line = tx(str(row or ''))
            for chunk in _wrap_chunks(line, max_chars=95):
                if y < 70:
                    c.showPage()
                    _draw_content_page_shell()
                    c.setFont(font_name, 9.5)
                    c.setFillColorRGB(0.93, 0.86, 1)
                    y = page_h - 50
                c.drawString(42, y, chunk)
                y -= 13
        y -= 8

    c.setFont(font_name, 8.5)
    c.setFillColorRGB(0.72, 0.93, 1)
    footer = 'Generated by TITAN AI Security Engine'
    c.drawCentredString(page_w / 2, 24, tx(footer))
    c.save()
    return buf.getvalue()


def _learning_cleanup_report_cache(now_ts: float | None = None) -> None:
    ts = now_ts if isinstance(now_ts, (int, float)) else time.time()
    stale = []
    for token, payload in _LEARNING_REPORTS.items():
        raw_created = payload.get('created_at', 0)
        if isinstance(raw_created, (int, float, str)):
            try:
                created_at = float(raw_created or 0)
            except Exception:
                created_at = 0.0
        else:
            created_at = 0.0
        if not created_at or (ts - created_at) > _LEARNING_REPORT_TTL_SECONDS:
            stale.append(token)
    for token in stale:
        _LEARNING_REPORTS.pop(token, None)


def _learning_store_report(user_id: int, report_payload: dict) -> str:
    token = secrets.token_urlsafe(18)
    now_ts = time.time()

    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO learning_reports (token, user_id, payload_json, created_at, expires_at) VALUES (%s,%s,%s,%s,%s)",
            (
                token,
                int(user_id),
                json.dumps(report_payload, ensure_ascii=False),
                datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                float(now_ts + _LEARNING_REPORT_TTL_SECONDS),
            )
        )
        c.execute("DELETE FROM learning_reports WHERE expires_at < %s", (float(now_ts),))
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

    with _LEARNING_REPORTS_LOCK:
        _learning_cleanup_report_cache(now_ts)
        _LEARNING_REPORTS[token] = {
            'user_id': int(user_id),
            'created_at': now_ts,
            'payload': report_payload,
        }
    return token


def _learning_get_report(token: str, user_id: int) -> dict | None:
    key = str(token or '').strip()
    if not key:
        return None

    requested_uid = int(user_id)

    with _LEARNING_REPORTS_LOCK:
        _learning_cleanup_report_cache()
        cached = _LEARNING_REPORTS.get(key)
        if not cached:
            payload = None
        else:
            raw_uid = cached.get('user_id', -1)
            if isinstance(raw_uid, (int, str)):
                try:
                    owner_uid = int(raw_uid)
                except Exception:
                    owner_uid = -1
            else:
                owner_uid = -1
            if owner_uid == requested_uid:
                payload = cached.get('payload')
                if isinstance(payload, dict):
                    return payload

    conn = None
    try:
        now_ts = time.time()
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("DELETE FROM learning_reports WHERE expires_at < %s", (float(now_ts),))
        c.execute(
            "SELECT payload_json FROM learning_reports WHERE token=%s AND user_id=%s AND expires_at >= %s LIMIT 1",
            (key, requested_uid, float(now_ts))
        )
        row = c.fetchone()
        conn.commit()
        if not row or not row[0]:
            return None
        payload = json.loads(row[0])
        if not isinstance(payload, dict):
            return None

        with _LEARNING_REPORTS_LOCK:
            _LEARNING_REPORTS[key] = {
                'user_id': requested_uid,
                'created_at': now_ts,
                'payload': payload,
            }
        return payload
    except Exception:
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()


def _forensics_unique(values):
    out = []
    seen = set()
    for v in values or []:
        item = str(v or '').strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _forensics_entropy(raw: bytes) -> float:
    if not raw:
        return 0.0
    freq = {}
    for b in raw:
        freq[b] = freq.get(b, 0) + 1
    total = float(len(raw))
    ent = 0.0
    for count in freq.values():
        p = count / total
        if p > 0:
            ent -= p * math.log2(p)
    return round(ent, 4)


def _forensics_detect_file_type(raw: bytes, filename: str, mime_type: str) -> str:
    name = (filename or '').lower()
    mime = (mime_type or '').lower()
    head = raw[:16] if raw else b''

    if head.startswith(b'MZ'):
        return 'windows-pe'
    if head.startswith(b'%PDF'):
        return 'pdf'
    if head.startswith(b'PK\x03\x04'):
        if name.endswith(('.docx', '.xlsx', '.pptx')):
            return 'office-openxml'
        return 'zip'
    if head.startswith(b'\x89PNG'):
        return 'png'
    if head.startswith(b'\xff\xd8\xff'):
        return 'jpeg'
    if head.startswith((b'GIF87a', b'GIF89a')):
        return 'gif'
    if b'javascript' in head.lower() or name.endswith('.js'):
        return 'javascript'
    if mime.startswith('text/') or name.endswith(('.txt', '.log', '.csv', '.json', '.xml', '.html')):
        return 'text'
    return 'unknown'


def _forensics_extract_strings(raw: bytes, min_len: int = 6, max_items: int = 120):
    min_len = max(4, min(32, int(min_len or 6)))
    pattern = rb'[\x20-\x7e]{' + str(min_len).encode('ascii') + rb',}'
    found = re.findall(pattern, raw or b'')
    strings_out = []
    for chunk in found[: max_items * 3]:
        try:
            s = chunk.decode('ascii', errors='ignore').strip()
        except Exception:
            s = ''
        if s:
            strings_out.append(s[:220])
    return _forensics_unique(strings_out)[:max_items]


def _forensics_extract_iocs_text(text: str):
    body = str(text or '')
    ipv4 = re.findall(r'\b(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}\b', body)
    urls = re.findall(r'\bhttps?://[^\s"\'<>]+', body, flags=re.IGNORECASE)
    emails = re.findall(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}\b', body)
    hashes = re.findall(r'\b[a-fA-F0-9]{32}\b|\b[a-fA-F0-9]{40}\b|\b[a-fA-F0-9]{64}\b', body)
    domains = re.findall(r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b', body)

    blacklist = {'com', 'org', 'net', 'local', 'localhost'}
    norm_domains = []
    for d in domains:
        dd = d.lower()
        if dd in blacklist:
            continue
        if dd.startswith('http'):
            continue
        norm_domains.append(dd)

    return {
        'ipv4': _forensics_unique(ipv4),
        'urls': _forensics_unique(urls),
        'emails': _forensics_unique(emails),
        'domains': _forensics_unique(norm_domains),
        'hashes': _forensics_unique(hashes),
    }


def _forensics_build_analysis(raw: bytes, filename: str, mime_type: str, min_string_len: int):
    strings_preview = _forensics_extract_strings(raw, min_len=min_string_len, max_items=120)
    text_probe = '\n'.join(strings_preview)
    iocs = _forensics_extract_iocs_text(text_probe)
    entropy = _forensics_entropy(raw)
    file_type = _forensics_detect_file_type(raw, filename, mime_type)

    suspicious_keywords = [
        'powershell', 'cmd.exe', 'rundll32', 'regsvr32', 'invoke-webrequest', 'wget ',
        'curl ', 'base64', 'fromcharcode', 'mshta', 'wscript', 'cscript', 'certutil'
    ]
    lowered = text_probe.lower()
    keyword_hits = [k for k in suspicious_keywords if k in lowered]

    score = 0
    factors = []
    if entropy >= 7.2:
        score += 30
        factors.append('high_entropy')
    elif entropy >= 6.8:
        score += 16
        factors.append('medium_entropy')

    if file_type == 'windows-pe':
        score += 20
        factors.append('pe_executable')

    ioc_count = sum(len(v) for v in iocs.values())
    if ioc_count >= 12:
        score += 22
        factors.append('many_iocs')
    elif ioc_count >= 5:
        score += 12
        factors.append('some_iocs')

    if keyword_hits:
        score += min(25, len(keyword_hits) * 5)
        factors.append('suspicious_strings')

    score = int(max(0, min(100, score)))
    metadata = {
        'file_type': file_type,
        'mime_type': mime_type,
        'suspicious_keywords': keyword_hits,
        'ioc_total': ioc_count,
        'printable_strings': len(strings_preview),
        'risk_factors': factors,
    }

    return {
        'file_type': file_type,
        'entropy': entropy,
        'risk_score': score,
        'strings_preview': strings_preview[:30],
        'iocs': iocs,
        'ioc_counts': {k: len(v) for k, v in iocs.items()},
        'metadata': metadata,
    }


@app.route('/api/incidents/<int:case_id>/report', methods=['GET'])
def ir_case_report_route(case_id: int):
    user_id, err = _get_logged_in_user_id()
    if err: return err
    conn = None
    try:
        conn = get_db_conn()
        report = _ir_build_report_payload(conn, case_id, user_id)
        if not report:
            return jsonify({"success": False, "error": "القضية غير موجودة"}), 404
        return jsonify({"success": True, "report": report})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/incidents/<int:case_id>/report.pdf', methods=['GET'])
def ir_case_report_pdf_route(case_id: int):
    user_id, err = _get_logged_in_user_id()
    if err: return err
    conn = None
    try:
        conn = get_db_conn()
        report = _ir_build_report_payload(conn, case_id, user_id)
        if not report:
            return jsonify({"success": False, "error": "القضية غير موجودة"}), 404

        c = report.get('case', {})
        m = report.get('metrics', {})
        lines = [
            f"Incident Report - Case #{c.get('id', '')}",
            f"Title: {c.get('title', '')}",
            f"Severity/Priority: {c.get('severity', '')} / {c.get('priority', '')}",
            f"Status: {c.get('status', '')}",
            f"Category: {c.get('category', '')} | Source: {c.get('source', '')}",
            f"Owner: {c.get('owner', '')}",
            f"Created: {c.get('created_at', '')} | Updated: {c.get('updated_at', '')}",
            f"SLA minutes: {c.get('sla_minutes', 0)} | Due: {c.get('due_at', '')}",
            f"MTTR minutes: {m.get('mttr_minutes', 0)}",
            f"IOC count: {m.get('ioc_count', 0)} | High-risk IOCs: {m.get('high_risk_iocs', 0)} | Mean IOC risk: {m.get('mean_ioc_risk', 0)}",
            f"Evidence count: {m.get('evidence_count', 0)} | Notes: {m.get('note_count', 0)}",
            "",
            "Description:",
            str(c.get('description', '')),
            "",
            "Generated by TITAN IR",
            f"Generated at: {report.get('generated_at', '')}",
        ]
        pdf_bytes = _build_minimal_pdf_bytes(lines)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"incident-{case_id}-report.pdf"
        )
    except Exception as e:
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
    if not file:
        return jsonify({"success": False, "error": "يرجى اختيار ملف صالح"}), 400

    try:
        min_string_len = int(request.form.get('min_string_len', 6) or 6)
    except Exception:
        min_string_len = 6
    min_string_len = max(4, min(32, min_string_len))

    raw = file.read()
    if not raw:
        return jsonify({"success": False, "error": "الملف فارغ"}), 400

    filename = secure_filename(file.filename or 'artifact.bin')
    mime_type = (file.mimetype or 'application/octet-stream').strip()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    analysis = _forensics_build_analysis(raw, filename, mime_type, min_string_len)
    md5_val = hashlib.md5(raw).hexdigest()
    sha1_val = hashlib.sha1(raw).hexdigest()
    sha256_val = hashlib.sha256(raw).hexdigest()

    conn = None
    session_id = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO forensics_sessions
            (user_id, filename, file_size, file_type, mime_type, md5, sha1, sha256, entropy, risk_score, summary_json, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                user_id,
                filename,
                len(raw),
                analysis['file_type'],
                mime_type,
                md5_val,
                sha1_val,
                sha256_val,
                float(analysis['entropy']),
                int(analysis['risk_score']),
                json.dumps(analysis['metadata'], ensure_ascii=False),
                now,
            ),
        )
        row = c.fetchone()
        if not row:
            conn.rollback()
            return jsonify({"success": False, "error": "فشل حفظ جلسة التحليل"}), 500
        session_id = int(row[0])

        artifacts = [
            ('hash_md5', md5_val, 'high'),
            ('hash_sha1', sha1_val, 'high'),
            ('hash_sha256', sha256_val, 'high'),
        ]
        for ip in analysis['iocs'].get('ipv4', [])[:80]:
            artifacts.append(('ioc_ipv4', ip, 'high'))
        for u in analysis['iocs'].get('urls', [])[:80]:
            artifacts.append(('ioc_url', u, 'high'))
        for em in analysis['iocs'].get('emails', [])[:80]:
            artifacts.append(('ioc_email', em, 'medium'))
        for dm in analysis['iocs'].get('domains', [])[:120]:
            artifacts.append(('ioc_domain', dm, 'medium'))
        for hv in analysis['iocs'].get('hashes', [])[:120]:
            artifacts.append(('ioc_hash', hv, 'high'))
        for s in analysis['strings_preview'][:25]:
            artifacts.append(('string', s, 'low'))

        for art in artifacts:
            c.execute(
                "INSERT INTO forensics_artifacts (session_id, artifact_type, artifact_value, confidence, created_at) VALUES (%s,%s,%s,%s,%s)",
                (session_id, art[0], art[1], art[2], now)
            )

        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()

    add_audit_log("Forensics Triage", f"session#{session_id} {filename} risk={analysis['risk_score']}", username=session.get('username', ''))
    return jsonify({
        "success": True,
        "session_id": session_id,
        "filename": filename,
        "size_bytes": len(raw),
        "mime_type": mime_type,
        "file_type": analysis['file_type'],
        "md5": md5_val,
        "sha1": sha1_val,
        "sha256": sha256_val,
        "entropy": analysis['entropy'],
        "risk_score": analysis['risk_score'],
        "ioc_counts": analysis['ioc_counts'],
        "strings_preview": analysis['strings_preview'],
        "metadata": analysis['metadata'],
        "triaged_at": now,
    })


@app.route('/api/forensics/summary', methods=['GET'])
def forensics_summary_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*), COALESCE(AVG(entropy),0), COALESCE(SUM(CASE WHEN risk_score >= 70 THEN 1 ELSE 0 END),0) FROM forensics_sessions WHERE user_id=%s", (user_id,))
        row = c.fetchone() or (0, 0, 0)

        c.execute(
            """
            SELECT COUNT(*)
            FROM forensics_artifacts fa
            JOIN forensics_sessions fs ON fs.id = fa.session_id
            WHERE fs.user_id=%s
            """,
            (user_id,)
        )
        art_count = int((c.fetchone() or [0])[0] or 0)

        return jsonify({
            "success": True,
            "summary": {
                "sessions": int(row[0] or 0),
                "avg_entropy": round(float(row[1] or 0), 3),
                "high_risk_sessions": int(row[2] or 0),
                "artifacts": art_count,
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/forensics/history', methods=['GET'])
def forensics_history_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute(
            """
            SELECT id, filename, file_size, file_type, mime_type, entropy, risk_score, created_at
            FROM forensics_sessions
            WHERE user_id=%s
            ORDER BY id DESC
            LIMIT 120
            """,
            (user_id,)
        )
        rows = c.fetchall() or []
        sessions = [
            {
                "id": int(r[0]),
                "filename": r[1],
                "file_size": int(r[2] or 0),
                "file_type": r[3],
                "mime_type": r[4],
                "entropy": float(r[5] or 0),
                "risk_score": int(r[6] or 0),
                "created_at": r[7],
            }
            for r in rows
        ]
        return jsonify({"success": True, "sessions": sessions})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/forensics/session/<int:session_id>', methods=['GET'])
def forensics_session_detail_route(session_id: int):
    user_id, err = _get_logged_in_user_id()
    if err: return err
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute(
            """
            SELECT id, filename, file_size, file_type, mime_type, md5, sha1, sha256, entropy, risk_score, summary_json, created_at
            FROM forensics_sessions
            WHERE id=%s AND user_id=%s
            """,
            (session_id, user_id)
        )
        row = c.fetchone()
        if not row:
            return jsonify({"success": False, "error": "جلسة التحليل غير موجودة"}), 404

        c.execute(
            "SELECT artifact_type, artifact_value, confidence, created_at FROM forensics_artifacts WHERE session_id=%s ORDER BY id DESC LIMIT 600",
            (session_id,)
        )
        art_rows = c.fetchall() or []

        iocs = {
            'ipv4': [],
            'urls': [],
            'emails': [],
            'domains': [],
            'hashes': [],
        }
        strings_preview = []
        artifacts = []
        for a in art_rows:
            atype = str(a[0] or '')
            aval = str(a[1] or '')
            artifacts.append({
                'artifact_type': atype,
                'artifact_value': aval,
                'confidence': a[2],
                'created_at': a[3],
            })
            if atype == 'ioc_ipv4':
                iocs['ipv4'].append(aval)
            elif atype == 'ioc_url':
                iocs['urls'].append(aval)
            elif atype == 'ioc_email':
                iocs['emails'].append(aval)
            elif atype == 'ioc_domain':
                iocs['domains'].append(aval)
            elif atype in ('ioc_hash', 'hash_md5', 'hash_sha1', 'hash_sha256'):
                iocs['hashes'].append(aval)
            elif atype == 'string':
                strings_preview.append(aval)

        iocs = {k: _forensics_unique(v)[:200] for k, v in iocs.items()}
        strings_preview = _forensics_unique(strings_preview)[:40]
        ioc_counts = {k: len(v) for k, v in iocs.items()}

        try:
            summary_meta = json.loads(row[10] or '{}') if row[10] else {}
        except Exception:
            summary_meta = {}

        return jsonify({
            "success": True,
            "session": {
                "id": int(row[0]),
                "filename": row[1],
                "file_size": int(row[2] or 0),
                "file_type": row[3],
                "mime_type": row[4],
                "md5": row[5],
                "sha1": row[6],
                "sha256": row[7],
                "entropy": float(row[8] or 0),
                "risk_score": int(row[9] or 0),
                "created_at": row[11],
            },
            "ioc_counts": ioc_counts,
            "iocs": iocs,
            "strings_preview": strings_preview,
            "metadata": summary_meta,
            "artifacts_count": len(art_rows),
            "artifacts": artifacts[:200],
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/forensics/extract-iocs', methods=['POST'])
def forensics_extract_iocs_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    text = str((request.json or {}).get('text', '') or '').strip()
    if not text:
        return jsonify({"success": False, "error": "النص مطلوب"}), 400

    iocs = _forensics_extract_iocs_text(text)
    counts = {k: len(v) for k, v in iocs.items()}
    add_audit_log("Forensics IOC Extract", f"len={len(text)} iocs={sum(counts.values())}", username=session.get('username', ''))
    return jsonify({"success": True, "iocs": iocs, "counts": counts})


@app.route('/api/social/simulate', methods=['POST'])
def social_simulate_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    req = request.json or {}
    scenario_type = req.get('scenario_type', 'phishing_email')
    sector = (req.get('sector') or '').strip().lower()
    if scenario_type == 'sector_ar':
        scenario_type = {
            'banking': 'banking_ar',
            'education': 'education_ar',
            'healthcare': 'healthcare_ar'
        }.get(sector, 'banking_ar')
    payload = create_social_defense_scenario(scenario_type)
    add_audit_log("Social Engineering Drill", f"scenario={scenario_type} sector={sector or 'general'}", username=session.get('username', ''))
    return jsonify({"success": True, **payload})


@app.route('/api/social/quiz/result', methods=['POST'])
def social_quiz_result_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    req = request.json or {}

    try:
        question_id = int(req.get('question_id', 0))
        selected_option = int(req.get('selected_option', -1))
        correct_option = int(req.get('correct_option', -1))
        is_correct = 1 if bool(req.get('is_correct', False)) else 0
        score_after = int(req.get('score_after', 0))
    except Exception:
        return jsonify({"success": False, "error": "قيم غير صالحة"}), 400

    if question_id < 0 or selected_option < 0 or correct_option < 0:
        return jsonify({"success": False, "error": "البيانات ناقصة"}), 400

    conn = None
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO social_quiz_results
            (user_id, question_id, selected_option, correct_option, is_correct, score_after, answered_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (user_id, question_id, selected_option, correct_option, is_correct, score_after, now)
        )
        conn.commit()
        add_audit_log("SE Quiz", f"q={question_id} correct={is_correct} score={score_after}", username=session.get('username', ''))
        return jsonify({"success": True})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/social/quiz/stats', methods=['GET'])
def social_quiz_stats_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute(
            "SELECT COUNT(*), COALESCE(SUM(is_correct), 0), COALESCE(MAX(score_after), 0) FROM social_quiz_results WHERE user_id=%s",
            (user_id,)
        )
        total_answers, correct_answers, last_score = c.fetchone() or (0, 0, 0)

        c.execute(
            """
            SELECT SUBSTRING(answered_at, 1, 10) AS day, COUNT(*), COALESCE(SUM(is_correct), 0)
            FROM social_quiz_results
            WHERE user_id=%s
            GROUP BY day
            ORDER BY day DESC
            LIMIT 10
            """,
            (user_id,)
        )
        trend_rows = c.fetchall() or []
        trend = [{"day": r[0], "answers": int(r[1] or 0), "correct": int(r[2] or 0)} for r in trend_rows][::-1]

        accuracy = round((float(correct_answers) / float(total_answers) * 100.0), 2) if total_answers else 0.0
        return jsonify({
            "success": True,
            "total_answers": int(total_answers or 0),
            "correct_answers": int(correct_answers or 0),
            "accuracy": accuracy,
            "last_score": int(last_score or 0),
            "trend": trend
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/social/risk/snapshot', methods=['POST'])
def social_risk_snapshot_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    req = request.json or {}

    try:
        total_items = max(0, int(req.get('total_items', 0)))
        high_count = max(0, int(req.get('high_count', 0)))
        medium_count = max(0, int(req.get('medium_count', 0)))
        low_count = max(0, int(req.get('low_count', 0)))
        avg_risk = float(req.get('avg_risk', 0.0) or 0.0)
    except Exception:
        return jsonify({"success": False, "error": "مدخلات غير صالحة"}), 400

    risk_index = min(100.0, max(0.0, (high_count * 35.0) + (medium_count * 18.0) + (low_count * 6.0)))
    if total_items > 0:
        risk_index = round(min(100.0, (risk_index / float(total_items)) + (avg_risk * 0.35)), 2)
    else:
        risk_index = 0.0

    conn = None
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO social_risk_snapshots
            (user_id, total_items, high_count, medium_count, low_count, avg_risk, risk_index, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (user_id, total_items, high_count, medium_count, low_count, avg_risk, risk_index, now)
        )
        conn.commit()
        return jsonify({"success": True, "risk_index": risk_index})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/api/social/risk/trend', methods=['GET'])
def social_risk_trend_route():
    user_id, err = _get_logged_in_user_id()
    if err: return err
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute(
            """
            SELECT SUBSTRING(created_at, 1, 10) AS day,
                   ROUND(AVG(risk_index)::numeric, 2) AS avg_risk_index,
                   MAX(total_items) AS total_items,
                   MAX(high_count) AS high_count,
                   MAX(medium_count) AS medium_count,
                   MAX(low_count) AS low_count
            FROM social_risk_snapshots
            WHERE user_id=%s
            GROUP BY day
            ORDER BY day DESC
            LIMIT 14
            """,
            (user_id,)
        )
        rows = c.fetchall() or []
        points = [
            {
                "day": r[0],
                "risk_index": float(r[1] or 0.0),
                "total_items": int(r[2] or 0),
                "high_count": int(r[3] or 0),
                "medium_count": int(r[4] or 0),
                "low_count": int(r[5] or 0)
            }
            for r in rows
        ][::-1]
        latest = points[-1] if points else {
            "day": "",
            "risk_index": 0.0,
            "total_items": 0,
            "high_count": 0,
            "medium_count": 0,
            "low_count": 0
        }
        return jsonify({"success": True, "points": points, "latest": latest})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn: conn.close()

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
BURN_CHAT_DESTROYED: dict[str, dict[str, str]] = {}

@app.route('/api/chat/send', methods=['POST'])
def chat_send():
    data = request.json or {}
    room_id = data.get('room_id')
    sender = data.get('sender', 'Anonymous')
    msg = data.get('msg', '')
    
    if not room_id or not msg:
        return jsonify({"error": "بيانات مفقودة"}), 400
    if room_id in BURN_CHAT_DESTROYED:
        return jsonify({"error": "تم تدمير هذه الغرفة"}), 410
        
    if room_id not in BURN_CHAT_ROOMS:
        BURN_CHAT_ROOMS[room_id] = []
        
    BURN_CHAT_ROOMS[room_id].append({"sender": sender, "msg": msg})
    return jsonify({"success": True})

@app.route('/api/chat/receive', methods=['GET'])
def chat_receive():
    room_id = request.args.get('room_id')
    requester = request.args.get('requester', '')

    destroyed_meta = BURN_CHAT_DESTROYED.get(room_id or '')
    if destroyed_meta:
        return jsonify({"destroyed": True, "by": destroyed_meta.get('by', '')})
    
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


@app.route('/api/chat/destroy', methods=['POST'])
def chat_destroy():
    data = request.json or {}
    room_id = (data.get('room_id') or '').strip()
    requester = (data.get('requester') or '').strip() or 'Unknown'
    if not room_id:
        return jsonify({"success": False, "error": "room_id مطلوب"}), 400

    BURN_CHAT_ROOMS.pop(room_id, None)
    BURN_CHAT_DESTROYED[room_id] = {
        'by': requester,
        'at': datetime.datetime.now().isoformat()
    }
    add_audit_log("Burn Chat 💥", f"تم تدمير الغرفة [{room_id}] بواسطة {requester}")
    return jsonify({"success": True, "room_id": room_id})


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
def _contains_arabic_text(value: str) -> bool:
    return bool(re.search(r'[\u0600-\u06FF]', value or ''))


def _arabic_name_to_english(value: str) -> str:
    raw = re.sub(r'[\u064B-\u065F\u0670\u0640]', '', (value or '').strip())
    raw = raw.replace('ٱ', 'ا').replace('ﺍ', 'ا').replace('ﻻ', 'لا')
    raw = re.sub(r'\s+', ' ', raw).strip()

    phrase_map = {
        'عبد الله': 'Abdullah',
        'عبد الرحمن': 'Abdulrahman',
        'عبدالرحمن': 'Abdulrahman',
        'عبد العزيز': 'Abdulaziz',
        'عبدالعزيز': 'Abdulaziz',
        'ابن': 'Ibn',
        'بن': 'Bin',
    }
    if raw in phrase_map:
        return phrase_map[raw]

    token_map = {
        # Common first names (male)
        'محمد': 'Mohammad', 'أحمد': 'Ahmad', 'احمد': 'Ahmad', 'خالد': 'Khaled', 'عمر': 'Omar',
        'يوسف': 'Yousef', 'علي': 'Ali', 'حسن': 'Hasan', 'ماجد': 'Majed', 'فيصل': 'Faisal',
        'سامي': 'Sami', 'ليث': 'Laith', 'زيد': 'Zaid', 'يزن': 'Yazan', 'حمزة': 'Hamza',
        'عبدالله': 'Abdullah', 'عبد': 'Abd', 'الله': 'Allah', 'اللة': 'Allah',

        # Common first names (female)
        'فاطمة': 'Fatimah', 'مريم': 'Maryam', 'سارة': 'Sarah', 'نور': 'Noor', 'لينا': 'Lina',
        'رنا': 'Rana', 'دانا': 'Dana', 'هند': 'Hind', 'أمل': 'Amal', 'امل': 'Amal',
        'لمى': 'Lama', 'رهف': 'Rahaf', 'تالا': 'Tala', 'جنى': 'Jana', 'سلمى': 'Salma', 'ليان': 'Layan',

        # Common Jordanian surnames used in this project
        'العبدلي': 'Al-Abdali', 'الخطيب': 'Al-Khatib', 'القضاة': 'Al-Qudah', 'الزيود': 'Al-Zyoud',
        'الشرايري': 'Al-Shrairi', 'الطراونة': 'Al-Tarawneh', 'البطاينة': 'Al-Batayneh', 'الحجاوي': 'Al-Hajawi',
        'العساف': 'Al-Assaf', 'المجالي': 'Al-Majali', 'العدوان': 'Al-Adwan', 'الفايز': 'Al-Fayez',
        'الروسان': 'Al-Rousan', 'الخصاونة': 'Al-Khasawneh', 'العبادي': 'Al-Abadi',
    }

    char_map = {
        'ا': 'a', 'أ': 'a', 'إ': 'e', 'آ': 'aa', 'ب': 'b', 'ت': 't', 'ث': 'th',
        'ج': 'j', 'ح': 'h', 'خ': 'kh', 'د': 'd', 'ذ': 'dh', 'ر': 'r', 'ز': 'z',
        'س': 's', 'ش': 'sh', 'ص': 's', 'ض': 'd', 'ط': 't', 'ظ': 'z', 'ع': 'a',
        'غ': 'gh', 'ف': 'f', 'ق': 'q', 'ك': 'k', 'ل': 'l', 'م': 'm', 'ن': 'n',
        'ه': 'h', 'ة': 'ah', 'و': 'w', 'ؤ': 'w', 'ي': 'y', 'ى': 'a', 'ئ': 'e', 'ء': '',
    }

    def translit_token(token: str) -> str:
        t = token.strip()
        if not t:
            return ''
        if t in token_map:
            return token_map[t]
        if t.startswith('ال') and len(t) > 2:
            stem = translit_token(t[2:])
            return f"Al-{stem}" if stem else 'Al'

        out = ''.join(char_map.get(ch, ch) for ch in t)
        out = re.sub(r'([aeiou])\1+', r'\1', out)
        if not out:
            return ''
        return out[0].upper() + out[1:]

    parts = [translit_token(p) for p in raw.split(' ') if p.strip()]

    # Merge common compounds for accurate canonical spelling.
    if len(parts) >= 2 and parts[0] == 'Abd' and parts[1] in ('Allah', 'Alah', 'Al-lah', 'Al-Lah'):
        parts = ['Abdullah'] + parts[2:]

    return ' '.join(p for p in parts if p).strip()


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

        name_en = _arabic_name_to_english(full_name) if _contains_arabic_text(full_name) else ''

        return jsonify({
            'name': full_name,
            'name_en': name_en,
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
        return jsonify({"error": "كلمة السر خاطئة"}), 401
    except Exception as e:
        print(f"[TITAN] Vault download error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()





# =====================================================================
# === CTF Arena Routes ===
# =====================================================================

def _ctf_rotation_key() -> str:
    now = datetime.datetime.utcnow()
    slot = now.hour // 4
    return f"{now.strftime('%Y%m%d')}-slot{slot}"


def _ctf_seed_for_user(user_id, rotation_key: str, extra_nonce: str = '') -> int:
    base = f"{user_id}|{rotation_key}|{extra_nonce}"
    digest = hashlib.sha256(base.encode('utf-8')).hexdigest()
    return int(digest[:16], 16)


def _ctf_caesar_encrypt(text: str, shift: int) -> str:
    out = []
    for ch in text:
        if 'a' <= ch <= 'z':
            out.append(chr((ord(ch) - 97 + shift) % 26 + 97))
        elif 'A' <= ch <= 'Z':
            out.append(chr((ord(ch) - 65 + shift) % 26 + 65))
        else:
            out.append(ch)
    return ''.join(out)


def _ctf_xor_hex(text: str, key_char: str) -> str:
    kb = ord(key_char)
    return ''.join(f"{(ord(c) ^ kb):02x}" for c in text)


def _build_ctf_challenges(user_id, force_nonce: str = ''):
    rotation_key = _ctf_rotation_key()
    rng = random.Random(_ctf_seed_for_user(user_id, rotation_key, force_nonce))

    # Challenge 1: Base64
    b64_token = f"B64_{rng.randint(1000, 9999)}_{rng.choice(['FOX', 'NOVA', 'BYTE'])}"
    b64_flag = f"TITAN{{{b64_token}}}"
    b64_payload = base64.b64encode(b64_flag.encode('utf-8')).decode('ascii')

    # Challenge 2: Caesar
    caesar_word = rng.choice(['ciphertrail', 'shadowpacket', 'matrixroute', 'neonvector'])
    caesar_shift = rng.randint(2, 9)
    caesar_cipher = _ctf_caesar_encrypt(caesar_word, caesar_shift)
    caesar_flag = f"TITAN{{{caesar_word}}}"

    # Challenge 3: SHA1 + mini wordlist logic
    leak_word = rng.choice(['falcon', 'phantom', 'quantum', 'stalker', 'vortex'])
    leak_num = rng.randint(10, 99)
    leak_plain = f"{leak_word}{leak_num}"
    leak_sha1 = hashlib.sha1(leak_plain.encode('utf-8')).hexdigest()
    leak_flag = f"TITAN{{{leak_plain}}}"

    # Challenge 4: Epoch time conversion
    base_dt = datetime.datetime(2026, rng.randint(1, 12), rng.randint(1, 25), rng.randint(0, 23), rng.randint(0, 59), 0)
    epoch_val = int(base_dt.timestamp())
    epoch_answer = base_dt.strftime('%Y%m%d_%H%M')
    epoch_flag = f"TITAN{{{epoch_answer}}}"

    # Challenge 5: XOR
    xor_plain = rng.choice(['ctf_is_fun', 'learn_by_breaking', 'logic_over_luck', 'trace_the_bits'])
    xor_key = rng.choice(['K', 'Q', 'Z', 'M', 'R'])
    xor_hex = _ctf_xor_hex(xor_plain, xor_key)
    xor_flag = f"TITAN{{{xor_plain}}}"

    # Challenge 6: ROT13
    rot13_word = rng.choice(['packetstorm', 'cybermatrix', 'threatmodel', 'securevector'])
    rot13_map = str.maketrans(
        'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz',
        'NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm'
    )
    rot13_cipher = rot13_word.translate(rot13_map)
    rot13_flag = f"TITAN{{{rot13_word}}}"

    # Challenge 7: Hex to ASCII
    hex_plain = rng.choice(['redteamblue', 'trace_route', 'signal_chain', 'rapid_forensics'])
    hex_payload = hex_plain.encode('utf-8').hex()
    hex_flag = f"TITAN{{{hex_plain}}}"

    # Challenge 8: Binary to text
    bin_plain = rng.choice(['node_sync', 'intel_probe', 'darktrace', 'vault_unlock'])
    bin_payload = ' '.join(format(ord(c), '08b') for c in bin_plain)
    bin_flag = f"TITAN{{{bin_plain}}}"

    # Hard downloadable challenge A: Forensic log hunt
    log_token = f"LOG-{rng.randint(100,999)}-{rng.choice(['ALPHA','DELTA','NOVA'])}-{rng.randint(10,99)}"
    log_flag = f"TITAN{{{log_token}}}"
    log_lines = [
        '2026-03-28T10:21:11Z INFO auth login user=svc_monitor status=ok',
        '2026-03-28T10:22:44Z WARN api unusual endpoint=/internal/metrics source=10.0.2.18',
        f'2026-03-28T10:23:39Z ALERT secret_leak indicator={log_token} channel=debug_dump',
        '2026-03-28T10:24:08Z INFO mitigation enabled rule=R-71',
        '2026-03-28T10:25:02Z INFO trace session closed'
    ]
    log_file_content = '\n'.join(log_lines) + '\n'

    # Hard downloadable challenge B: Incident JSON
    json_code = f"INC-{rng.randint(1000,9999)}-{rng.choice(['QX','ZT','MK'])}"
    json_flag = f"TITAN{{{json_code}}}"
    json_file_obj = {
        "case_id": f"CASE-{rng.randint(10000,99999)}",
        "severity": rng.choice(["high", "critical"]),
        "timeline": [
            {"t": "10:31:09", "event": "suspicious dns burst"},
            {"t": "10:31:55", "event": "lateral movement candidate"},
            {"t": "10:32:10", "event": "containment started"}
        ],
        "artifact": {
            "key": json_code,
            "note": "Use this artifact key in final flag format"
        }
    }
    incident_json_content = json.dumps(json_file_obj, ensure_ascii=False, indent=2)

    # Kali-focused challenge C: Nmap analysis
    nmap_target = f"10.{rng.randint(10, 200)}.{rng.randint(1, 254)}.{rng.randint(1, 254)}"
    nmap_secret_port = rng.choice([2121, 8081, 8888, 9090])
    nmap_flag = f"TITAN{{{nmap_secret_port}}}"
    nmap_output = (
        f"Nmap scan report for {nmap_target}\n"
        "PORT     STATE SERVICE VERSION\n"
        "22/tcp   open  ssh     OpenSSH 8.4p1\n"
        "80/tcp   open  http    nginx 1.22\n"
        f"{nmap_secret_port}/tcp open  http    Node.js Express debug panel\n"
        "MAC Address: 08:00:27:AA:BB:CC (Oracle VirtualBox virtual NIC)"
    )

    # Kali-focused challenge D: Gobuster directory discovery
    gobuster_dir = rng.choice(['/admin-portal', '/backup-2026', '/dev-internal', '/hidden-dashboard'])
    gobuster_flag = f"TITAN{{{gobuster_dir.strip('/')}}}"
    gobuster_output = (
        "===============================================================\n"
        "Gobuster v3.6\n"
        "===============================================================\n"
        f"/assets               (Status: 301) [Size: 312]\n"
        f"/api                  (Status: 200) [Size: 845]\n"
        f"{gobuster_dir:<22} (Status: 200) [Size: 1932]\n"
        "/server-status        (Status: 403) [Size: 277]"
    )

    # Kali-focused challenge E: John/hash cracking
    john_plain = rng.choice(['shadowfox22', 'kali_master7', 'blue_team99', 'red_ops42'])
    john_hash = hashlib.md5(john_plain.encode('utf-8')).hexdigest()
    john_flag = f"TITAN{{{john_plain}}}"

    # Kali-focused challenge F: Binwalk firmware analysis
    fw_offset = rng.choice([24576, 32768, 40960, 49152])
    fw_artifact = rng.choice(['flag.db', 'creds.txt', 'vault.key', 'secret.env'])
    binwalk_flag = f"TITAN{{{fw_artifact}}}"
    binwalk_output = (
        "DECIMAL       HEXADECIMAL     DESCRIPTION\n"
        "--------------------------------------------------------------------------------\n"
        "0             0x0             uImage header, header size: 64 bytes\n"
        "1024          0x400           LZMA compressed data\n"
        f"{fw_offset:<13} 0x{fw_offset:04X}          Squashfs filesystem, little endian\n"
        f"{fw_offset + 2048:<13} 0x{fw_offset + 2048:04X}          ASCII text, contains: {fw_artifact}\n"
    )

    challenges = [
        {
            'id': 'ctf_b64',
            'title': 'Base64 Warmup',
            'category': 'crypto',
            'difficulty': 'easy',
            'points': 100,
            'flag_format': 'TITAN{...}',
            'description': (
                "المطلوب: فك ترميز النص التالي من Base64 ثم إرسال العلم الناتج كما هو.\n"
                f"Base64 Payload:\n{b64_payload}"
            ),
            'hints': [
                'استخدم أي أداة Base64 decode.',
                'الناتج نفسه هو العلم النهائي.'
            ],
            'method': 'تحويل النص من Base64 إلى نص عادي ثم التحقق من شكل العلم.',
            'answer': b64_flag
        },
        {
            'id': 'ctf_caesar',
            'title': 'Caesar Tunnel',
            'category': 'crypto',
            'difficulty': 'medium',
            'points': 150,
            'flag_format': 'TITAN{word}',
            'description': (
                f"النص المشفّر: {caesar_cipher}\\n"
                f"نوع التشفير: Caesar Cipher بإزاحة = {caesar_shift}.\\n"
                "استخرج الكلمة الأصلية lowercase ثم لفّها بصيغة العلم TITAN{word}."
            ),
            'hints': [
                'فك قيصر يعني إرجاع الحروف للخلف بنفس قيمة الإزاحة.',
                'الناتج كلمة إنجليزية lowercase.'
            ],
            'method': 'فك Caesar بإرجاع كل حرف للخلف بمقدار shift ثم تغليفه داخل العلم.',
            'answer': caesar_flag
        },
        {
            'id': 'ctf_hash',
            'title': 'Hash Peek',
            'category': 'forensics',
            'difficulty': 'medium',
            'points': 170,
            'flag_format': 'TITAN{wordNN}',
            'description': (
                f"لدينا SHA1 Hash: {leak_sha1}\\n"
                "الـ plaintext يتكوّن من كلمة واحدة من القائمة [falcon, phantom, quantum, stalker, vortex] ثم رقمين."
            ),
            'hints': [
                'جرب brute force صغير على 5 كلمات × 90 احتمال رقم.',
                'قارن SHA1 لكل مرشح مع الهاش المعطى.'
            ],
            'method': 'توليد كل المرشحين المحتملين وحساب SHA1 حتى تجد التطابق.',
            'answer': leak_flag
        },
        {
            'id': 'ctf_epoch',
            'title': 'Time Decoder',
            'category': 'osint',
            'difficulty': 'easy',
            'points': 120,
            'flag_format': 'TITAN{YYYYMMDD_HHMM}',
            'description': (
                f"قيمة الـ UNIX epoch المعطاة: {epoch_val}\\n"
                "حوّلها إلى UTC ثم اكتبها بالتنسيق YYYYMMDD_HHMM وبعدها ضعها داخل العلم."
            ),
            'hints': [
                'epoch -> UTC datetime conversion.',
                'انتبه لتنسيق الدقائق بدون ثواني.'
            ],
            'method': 'تحويل epoch إلى UTC ثم تنسيق التاريخ بالشكل المطلوب.',
            'answer': epoch_flag
        },
        {
            'id': 'ctf_xor',
            'title': 'XOR Trace',
            'category': 'reverse',
            'difficulty': 'hard',
            'points': 220,
            'flag_format': 'TITAN{plaintext}',
            'description': (
                f"Hex stream: {xor_hex}\\n"
                f"هذا النص تم XOR عليه بايت-بايت باستخدام حرف مفتاح واحد: '{xor_key}'.\\n"
                "استخرج النص الأصلي plaintext ثم أرسله بصيغة العلم."
            ),
            'hints': [
                'قسّم الـ hex إلى بايتات.',
                'لكل بايت: original = cipher ^ key.'
            ],
            'method': 'فك XOR على كل بايت باستخدام المفتاح الأحادي ثم تحويل الناتج لنص.',
            'answer': xor_flag
        },
        {
            'id': 'ctf_rot13',
            'title': 'ROT13 Relay',
            'category': 'crypto',
            'difficulty': 'easy',
            'points': 110,
            'flag_format': 'TITAN{word}',
            'description': (
                f"النص الحالي مشفّر بـ ROT13: {rot13_cipher}\\n"
                "فك النص ثم أرسله بصيغة TITAN{word}."
            ),
            'hints': [
                'ROT13 يستبدل كل حرف بالحرف الذي يبعد 13 مكان.',
                'تطبيق ROT13 مرة ثانية يعيد النص الأصلي.'
            ],
            'method': 'طبّق ROT13 على النص المعطى ثم لف الناتج بصيغة العلم.',
            'answer': rot13_flag
        },
        {
            'id': 'ctf_hex',
            'title': 'Hex Signal',
            'category': 'reverse',
            'difficulty': 'medium',
            'points': 160,
            'flag_format': 'TITAN{plaintext}',
            'description': (
                f"Hex data: {hex_payload}\\n"
                "حوّل hex إلى ASCII ثم أرسل الناتج بصيغة العلم."
            ),
            'hints': [
                'كل بايت في hex = رقمين.',
                'بعد التحويل ستظهر كلمة/عبارة واضحة.'
            ],
            'method': 'قسّم hex إلى بايتات ثم حوّل كل بايت إلى محرف ASCII.',
            'answer': hex_flag
        },
        {
            'id': 'ctf_binary',
            'title': 'Binary Trail',
            'category': 'forensics',
            'difficulty': 'medium',
            'points': 175,
            'flag_format': 'TITAN{plaintext}',
            'description': (
                f"Binary stream: {bin_payload}\\n"
                "حوّل القيم الثنائية إلى نص ASCII ثم أرسل العلم."
            ),
            'hints': [
                'كل 8 بت تمثل حرفاً واحداً.',
                'حوّل من binary -> decimal -> char.'
            ],
            'method': 'ترجمة كل 8-bit إلى محرف ASCII ثم دمج النص.',
            'answer': bin_flag
        },
        {
            'id': 'ctf_logfile',
            'title': 'Logfile Breach Hunt',
            'category': 'forensics',
            'difficulty': 'hard',
            'points': 260,
            'flag_format': 'TITAN{LOG-...}',
            'description': (
                "هذا تحدي صعب مع ملف إلزامي.\\n"
                "نزل ملف السجلات، استخرج مؤشر التسريب indicator من سطر ALERT، ثم أرسله داخل العلم."
            ),
            'hints': [
                'ابحث عن السطر الذي يحتوي ALERT.',
                'القيمة المطلوبة تظهر بعد indicator= مباشرة.'
            ],
            'method': 'تحليل ملف السجلات واستخراج قيمة indicator المطلوبة.',
            'download_required': True,
            'download_name': 'ctf_log_hunt.txt',
            'file_payload': log_file_content,
            'answer': log_flag
        },
        {
            'id': 'ctf_incident_json',
            'title': 'Incident Artifact',
            'category': 'osint',
            'difficulty': 'hard',
            'points': 280,
            'flag_format': 'TITAN{INC-...}',
            'description': (
                "هذا تحدي صعب مع ملف JSON إلزامي.\\n"
                "نزل الملف، ادخل إلى artifact.key، وخذ القيمة كما هي داخل العلم."
            ),
            'hints': [
                'افتح الملف كـ JSON وابحث عن الكائن artifact.',
                'المطلوب هو قيمة الحقل key فقط.'
            ],
            'method': 'تحليل بنية JSON واستخراج artifact.key بشكل دقيق.',
            'download_required': True,
            'download_name': 'incident_artifact.json',
            'file_payload': incident_json_content,
            'answer': json_flag
        },
        {
            'id': 'ctf_kali_nmap',
            'title': 'Kali Tool Drill: Nmap Service Hunt',
            'category': 'kali-tools',
            'difficulty': 'medium',
            'points': 190,
            'flag_format': 'TITAN{PORT}',
            'description': (
                "تدريب Kali (nmap): حلّل نتيجة الفحص وحدد البورت الخاص بلوحة debug المكشوفة.\n"
                "أدخل رقم البورت داخل العلم بصيغة TITAN{PORT}.\n\n"
                f"Nmap Output:\n{nmap_output}"
            ),
            'hints': [
                'ابحث عن السطر الذي يحتوي debug panel.',
                'المطلوب هو رقم البورت فقط داخل العلم.'
            ],
            'method': 'قراءة مخرجات nmap واستخراج البورت الأكثر حساسية (لوحة debug).',
            'answer': nmap_flag
        },
        {
            'id': 'ctf_kali_gobuster',
            'title': 'Kali Tool Drill: Gobuster Discovery',
            'category': 'kali-tools',
            'difficulty': 'easy',
            'points': 160,
            'flag_format': 'TITAN{dirname}',
            'description': (
                "تدريب Kali (gobuster): من مخرجات اكتشاف المسارات، حدّد المسار الحساس الذي رجع Status 200.\n"
                "اكتب اسم المجلد بدون / داخل العلم.\n\n"
                f"Gobuster Output:\n{gobuster_output}"
            ),
            'hints': [
                'ابحث عن المسار غير المعتاد مع Status 200.',
                'احذف الشرطة / من بداية المسار قبل وضعه داخل العلم.'
            ],
            'method': 'تحليل مخرجات gobuster والتركيز على المسار غير الطبيعي القابل للوصول.',
            'answer': gobuster_flag
        },
        {
            'id': 'ctf_kali_john',
            'title': 'Kali Tool Drill: John The Ripper',
            'category': 'kali-tools',
            'difficulty': 'medium',
            'points': 210,
            'flag_format': 'TITAN{password}',
            'description': (
                "تدريب Kali (john): لديك MD5 hash لكلمة مرور. اكسر الهاش باستخدام wordlist بسيطة.\n"
                "عند معرفة كلمة المرور، ضعها داخل العلم.\n\n"
                f"MD5 Hash: {john_hash}"
            ),
            'hints': [
                'استخدم john أو hashcat بوضع md5.',
                'الناتج كلمة مرور lowercase مع أرقام في النهاية.'
            ],
            'method': 'تشغيل john/hashcat على hash md5 ثم أخذ plaintext كما هو.',
            'answer': john_flag
        },
        {
            'id': 'ctf_kali_binwalk',
            'title': 'Kali Tool Drill: Binwalk Firmware Peek',
            'category': 'kali-tools',
            'difficulty': 'hard',
            'points': 260,
            'flag_format': 'TITAN{artifact_name}',
            'description': (
                "تدريب Kali (binwalk): راجع مخرجات firmware analysis وحدد اسم الـ artifact المكتوب داخل النص.\n"
                "أدخل الاسم كما هو داخل العلم.\n\n"
                f"Binwalk Output:\n{binwalk_output}"
            ),
            'hints': [
                'السطر الأخير يحتوي اسم الملف المطلوب مباشرة.',
                'المطلوب اسم الملف فقط وليس الإزاحة.'
            ],
            'method': 'قراءة مخرجات binwalk واستخراج اسم الملف المضمّن داخل النص.',
            'answer': binwalk_flag
        },
    ]

    return challenges, rotation_key


def _get_ctf_session_state(force_refresh: bool = False):
    if 'user_id' not in session:
        return None, None

    if force_refresh:
        session['ctf_force_nonce'] = uuid.uuid4().hex[:8]

    nonce = session.get('ctf_force_nonce', '')
    challenges, rotation_key = _build_ctf_challenges(session['user_id'], nonce)
    answers = {c['id']: c['answer'] for c in challenges}

    session['ctf_rotation_key'] = rotation_key
    session['ctf_answers'] = answers
    session.setdefault('ctf_solved', [])
    session.setdefault('ctf_total_solved', 0)
    session.setdefault('ctf_total_points', 0)

    solved_set = set(session.get('ctf_solved', []))
    public = []
    for c in challenges:
        cc = {k: _ctf_normalize_newlines(v) for k, v in c.items() if k not in ('answer', 'file_payload')}
        cc['solved'] = c['id'] in solved_set
        public.append(cc)

    return public, rotation_key


@app.route('/api/ctf/challenges', methods=['GET'])
def ctf_challenges_route():
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "غير مصرح"}), 401

    refresh = request.args.get('refresh', '0') == '1'
    challenges, rotation_key = _get_ctf_session_state(force_refresh=refresh)
    if challenges is None:
        return jsonify({"success": False, "error": "failed to build ctf state"}), 500

    solved = session.get('ctf_solved', []) or []
    total_solved = int(session.get('ctf_total_solved', 0) or 0)
    total_points = int(session.get('ctf_total_points', 0) or 0)
    return jsonify({
        "success": True,
        "rotation_key": rotation_key,
        "solved_count": len(solved),
        "total_solved": total_solved,
        "total_points": total_points,
        "challenges": challenges
    })


@app.route('/api/ctf/submit', methods=['POST'])
def ctf_submit_route():
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "غير مصرح"}), 401

    data = request.json or {}
    challenge_id = (data.get('challenge_id') or '').strip()
    answer = (data.get('answer') or '').strip()
    if not challenge_id or not answer:
        return jsonify({"success": False, "error": "challenge_id and answer required"}), 400

    _get_ctf_session_state(force_refresh=False)
    answers = session.get('ctf_answers', {}) or {}
    expected = answers.get(challenge_id)
    if not expected:
        return jsonify({"success": False, "error": "challenge not found"}), 404

    if answer.strip() == expected.strip():
        solved = set(session.get('ctf_solved', []) or [])
        newly_solved = challenge_id not in solved
        solved.add(challenge_id)
        session['ctf_solved'] = list(solved)

        pts = 0
        current, _ = _get_ctf_session_state(force_refresh=False)
        for c in (current or []):
            if c.get('id') == challenge_id:
                pts = int(c.get('points') or 0)
                break

        if newly_solved:
            session['ctf_total_solved'] = int(session.get('ctf_total_solved', 0) or 0) + 1
            session['ctf_total_points'] = int(session.get('ctf_total_points', 0) or 0) + pts

        # فور حل التحدي: أنشئ مجموعة تحديات جديدة ليظهر بديل مباشر.
        session['ctf_force_nonce'] = uuid.uuid4().hex[:8]
        session['ctf_solved'] = []
        _get_ctf_session_state(force_refresh=False)

        add_audit_log("CTF Solved", f"challenge={challenge_id} +{pts}pts", username=session.get('username', ''))
        return jsonify({
            "success": True,
            "correct": True,
            "points": pts,
            "total_solved": int(session.get('ctf_total_solved', 0) or 0),
            "total_points": int(session.get('ctf_total_points', 0) or 0),
            "next_batch": True
        })

    return jsonify({"success": True, "correct": False, "message": "حل قريب؟ جرّب منهجية مختلفة أو اطلب تلميح AI."})


@app.route('/api/ctf/challenge-file/<challenge_id>', methods=['GET'])
def ctf_challenge_file_route(challenge_id):
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "غير مصرح"}), 401

    nonce = session.get('ctf_force_nonce', '')
    challenges, _ = _build_ctf_challenges(session['user_id'], nonce)
    target = next((c for c in challenges if c.get('id') == challenge_id), None)
    if not target:
        return jsonify({"success": False, "error": "challenge not found"}), 404

    payload = target.get('file_payload')
    if not payload:
        return jsonify({"success": False, "error": "this challenge has no downloadable file"}), 404

    filename = secure_filename(target.get('download_name') or f"{challenge_id}.txt")
    mimetype = 'application/json' if filename.lower().endswith('.json') else 'text/plain'
    buf = io.BytesIO(str(payload).encode('utf-8'))
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=filename, mimetype=mimetype)


@app.route('/api/ctf/assistant', methods=['POST'])
def ctf_ai_assistant_route():
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "غير مصرح"}), 401
    if not DO_AI_KEY:
        return jsonify({"success": False, "error": "DO_AI_KEY غير مضبوط"}), 500

    data = request.json or {}
    challenge_id = (data.get('challenge_id') or '').strip()
    question = (data.get('question') or '').strip()
    attempt = (data.get('attempt') or '').strip()
    if not challenge_id:
        return jsonify({"success": False, "error": "challenge_id required"}), 400

    challenges, _ = _get_ctf_session_state(force_refresh=False)
    if not challenges:
        return jsonify({"success": False, "error": "no challenges loaded"}), 500

    target = next((c for c in challenges if c.get('id') == challenge_id), None)
    if not target:
        return jsonify({"success": False, "error": "challenge not found"}), 404

    ctf_system = (
        "You are TITAN, a friendly human-like CTF coach. "
        "Give educational hints and methodology only. "
        "Never reveal the final flag, exact answer, or full direct solve string. "
        "If asked for direct answer, refuse briefly and provide next actionable hint. "
        "Respond in Arabic with warm natural tone, light humor when suitable, and 3-5 emojis. "
        "Keep steps concise and practical."
    )

    user_prompt = (
        f"Challenge title: {target.get('title')}\\n"
        f"Category: {target.get('category')} | Difficulty: {target.get('difficulty')}\\n"
        f"Description: {target.get('description')}\\n"
        f"Hints available: {target.get('hints')}\\n"
        f"Expected flag format: {target.get('flag_format')}\\n"
        f"Student question: {question or 'اشرح أول خطوة'}\\n"
        f"Student attempt: {attempt or '(none)'}\\n"
        "Give step-by-step guidance, common mistakes, and one concrete next step. Do not reveal final flag."
    )

    try:
        reply = _call_do_ai(user_prompt, system_prompt=ctf_system)
        add_audit_log("CTF AI Hint", f"challenge={challenge_id}", username=session.get('username', ''))
        return jsonify({
            "success": True,
            "reply": reply,
            "source": "titan",
            "model": (DO_AI_MODEL or 'tor1')
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"AI hint failed: {str(e)}"}), 500


# =====================================================================
# === AI Routes (DigitalOcean Agent) ===
# =====================================================================

@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح"}), 401

    if (request.content_type or '').lower().startswith('multipart/form-data'):
        return jsonify({"error": "رفع الصور والملفات للذكاء الصناعي معطل حالياً. أرسل نص فقط."}), 400

    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    model = (DO_AI_MODEL or 'tor1').strip()
    conversation_id = (data.get('conversation_id') or '').strip()

    if not message:
        return jsonify({"error": "الرسالة مطلوبة"}), 400
    if not DO_AI_KEY:
        return jsonify({"error": "DO_AI_KEY غير مضبوط"}), 500

    try:
        if not conversation_id:
            conversation_id = secrets.token_urlsafe(10)

        user_id = int(session['user_id'])
        conn = get_db_conn()
        c = conn.cursor()
        _ensure_ai_chat_tables(c)
        history = _ai_load_history_db(c, user_id, conversation_id, limit=14)
        cross_context = _ai_load_cross_conversation_context_db(c, user_id, exclude_conversation_id=conversation_id, limit=10)

        topic = _classify_ai_topic(message)
        context_messages = []
        # If current thread is new/empty, inject recent context from other chats to keep memory linked.
        if not history and cross_context:
            context_messages.append({
                "role": "assistant",
                "content": "سياق تراكمي من محادثاتك السابقة لنفس الحساب (للاستمرارية فقط):"
            })
            context_messages.extend(cross_context)
        context_messages.extend(history)
        context_messages.append({"role": "user", "content": message})

        system_prompt = _build_ai_system_prompt(topic, user_text=message)
        reply = _call_do_ai_with_history(context_messages, system_prompt=system_prompt, model=model)

        now = datetime.datetime.now().isoformat()
        preview = _ai_trim_title(reply, 120)
        title_seed = ''
        for h in history:
            if str(h.get('role') or '') == 'user':
                title_seed = str(h.get('content') or '').strip()
                if title_seed:
                    break
        if not title_seed:
            title_seed = message

        _ai_upsert_thread_db(
            c,
            user_id,
            conversation_id,
            _ai_trim_title(title_seed, 72),
            topic,
            model,
            now,
            preview
        )
        _ai_append_message_db(c, user_id, conversation_id, 'user', message, now)
        _ai_append_message_db(c, user_id, conversation_id, 'assistant', reply, now)
        conn.commit()
        conn.close()

        add_audit_log("AI Chat 🤖", f"AI: {message[:50]} | files=0 | model={model} | topic={topic}", username=session.get('username', ''))
        return jsonify({
            "success": True,
            "reply": reply,
            "conversation_id": conversation_id,
            "classification": topic
        })
    except Exception as e:
        print(f"[TITAN AI] Error: {e}")
        return jsonify({"error": f"فشل الاتصال بـ TITAN AI: {str(e)}"}), 500


@app.route('/api/ai/conversations', methods=['GET'])
def ai_conversations_route():
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "غير مصرح"}), 401
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        _ensure_ai_chat_tables(c)
        c.execute(
            """
            SELECT conversation_id, title, classification, model, updated_at, last_message_preview
            FROM ai_chat_threads
            WHERE user_id=%s
            ORDER BY updated_at DESC
            LIMIT 40
            """,
            (session['user_id'],)
        )
        rows = c.fetchall() or []
        return _json_no_cache({
            "success": True,
            "conversations": [
                {
                    "conversation_id": str(r[0]),
                    "title": str(r[1] or ''),
                    "classification": str(r[2] or 'general_support'),
                    "model": str(r[3] or DO_AI_MODEL or 'tor1'),
                    "updated_at": str(r[4] or ''),
                    "last_message_preview": str(r[5] or '')
                }
                for r in rows
            ]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/ai/conversations/<conversation_id>', methods=['GET'])
def ai_conversation_messages_route(conversation_id):
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "غير مصرح"}), 401
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        _ensure_ai_chat_tables(c)
        c.execute(
            """
            SELECT title, classification, model
            FROM ai_chat_threads
            WHERE user_id=%s AND conversation_id=%s
            LIMIT 1
            """,
            (session['user_id'], conversation_id)
        )
        thread = c.fetchone()
        if not thread:
            return _json_no_cache({"success": False, "error": "conversation not found"}, status=404)

        c.execute(
            """
            SELECT role, content, created_at
            FROM ai_chat_messages
            WHERE user_id=%s AND conversation_id=%s
            ORDER BY id ASC
            LIMIT 120
            """,
            (session['user_id'], conversation_id)
        )
        rows = c.fetchall() or []
        return _json_no_cache({
            "success": True,
            "conversation_id": conversation_id,
            "title": str(thread[0] or ''),
            "classification": str(thread[1] or 'general_support'),
            "model": str(thread[2] or DO_AI_MODEL or 'tor1'),
            "messages": [
                {"role": str(r[0] or ''), "content": str(r[1] or ''), "created_at": str(r[2] or '')}
                for r in rows
                if str(r[0] or '') in ('user', 'assistant')
            ]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/ai/conversations/<conversation_id>', methods=['DELETE'])
def ai_conversation_delete_route(conversation_id):
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "غير مصرح"}), 401
    conn = None
    try:
        conn = get_db_conn()
        c = conn.cursor()
        _ensure_ai_chat_tables(c)

        c.execute(
            "SELECT 1 FROM ai_chat_threads WHERE user_id=%s AND conversation_id=%s LIMIT 1",
            (session['user_id'], conversation_id)
        )
        if not c.fetchone():
            return _json_no_cache({"success": False, "error": "conversation not found"}, status=404)

        c.execute(
            "DELETE FROM ai_chat_messages WHERE user_id=%s AND conversation_id=%s",
            (session['user_id'], conversation_id)
        )
        c.execute(
            "DELETE FROM ai_chat_threads WHERE user_id=%s AND conversation_id=%s",
            (session['user_id'], conversation_id)
        )
        conn.commit()
        add_audit_log("AI Chat Delete 🗑️", f"conversation={conversation_id}", username=session.get('username', ''))
        return _json_no_cache({"success": True})
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/ai/conversations/<conversation_id>/delete', methods=['POST'])
def ai_conversation_delete_route_post(conversation_id):
    return ai_conversation_delete_route(conversation_id)


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
        analysis = _call_do_ai(prompt, system_prompt=AI_SYSTEM_PROMPT)
        add_audit_log("AI تحليل 🤖", f"تحليل {analyze_type}", username=session.get('username', ''))
        return jsonify({"success": True, "analysis": analysis})
    except Exception as e:
        print(f"[TITAN AI] Analyze error: {e}")
        return jsonify({"error": f"فشل التحليل: {str(e)}"}), 500


@app.route('/api/ai/models', methods=['GET'])
def ai_models():
    return jsonify({"models": ["TITAN-SEC AI (DigitalOcean)"], "success": True})


@app.route('/api/learning/simulate', methods=['POST'])
def learning_simulate_route():
    user_id, err = _get_logged_in_user_id()
    if err:
        return err
    assert user_id is not None

    data = request.get_json(silent=True) or {}
    custom_attack_type = (data.get('custom_attack_type') or '').strip()
    custom_objective = (data.get('custom_objective') or '').strip()
    org_context = (data.get('org_context') or '').strip()
    result_lang = _learning_normalize_lang(data.get('result_lang') or 'ar')
    training_level = str(data.get('training_level') or 'intermediate').strip().lower()
    if training_level not in ('beginner', 'intermediate', 'advanced'):
        training_level = 'intermediate'
    if not custom_attack_type:
        return jsonify({'success': False, 'error': 'custom_attack_type مطلوب'}), 400

    attack_suggestion = _learning_suggest_attack_type(custom_attack_type)
    if attack_suggestion and not bool(attack_suggestion.get('matched')):
        canonical = str(attack_suggestion.get('canonical') or '').strip()
        label_ar = str(attack_suggestion.get('label_ar') or canonical)
        label_en = str(attack_suggestion.get('label_en') or canonical)
        score = float(attack_suggestion.get('score') or 0.0)
        suggestions = attack_suggestion.get('suggestions')
        suggestions_list = suggestions if isinstance(suggestions, list) else []
        if result_lang == 'en':
            msg = (
                "Did you mean one of these attacks?"
                if score >= 0.68 else
                "Attack name is unclear. Please pick the closest option:"
            )
        else:
            msg = (
                "هل تقصد واحدة من هذه الهجمات؟"
                if score >= 0.68 else
                "اسم الهجمة غير واضح. اختر الأقرب من الخيارات التالية:"
            )
        return jsonify({
            'success': False,
            'error': msg,
            'code': 'attack_type_suggestion',
            'suggested_attack_type': canonical,
            'suggested_label_ar': label_ar,
            'suggested_label_en': label_en,
            'match_score': round(score, 3),
            'suggestions': suggestions_list,
        }), 400

    attack = _learning_build_custom_attack_from_ai(custom_attack_type, org_context, training_level, lang=result_lang)

    awareness = _learning_awareness_profile(attack)
    exploit_pattern = _learning_apply_level_tone(
        _learning_exploit_pattern(str(attack.get('category') or '')),
        training_level,
    )
    attack_method = _learning_apply_level_tone(str(awareness.get('attack_method') or ''), training_level)
    awareness_goal = _learning_apply_level_tone(str(awareness.get('awareness_goal') or ''), training_level)

    ai_explanation = ''
    if DO_AI_KEY:
        safe_system = (
            "You are a defensive cybersecurity coach. Never provide offensive commands or exploit steps. "
            "Provide awareness-first defensive guidance only."
            if result_lang == 'en' else
            "أنت مدرب أمن سيبراني دفاعي. ممنوع نهائياً تقديم أوامر تنفيذية أو أكواد استغلال أو خطوات اختراق عملية أو أوامر Metasploit. "
            "قدّم شرحاً تعليمياً دفاعياً فقط: كيف يعمل التهديد، مؤشرات الكشف، خطة احتواء، وخطة تحصين طويلة المدى. "
            "إذا طُلب أي تنفيذ هجومي، ارفضه وقدم بديل دفاعي آمن."
        )
        safe_prompt = (
            f"Scenario: {attack.get('title', '')}\n"
            f"Category: {attack.get('category', '')}\n"
            f"Severity: {attack.get('severity', '')}\n"
            f"Summary: {attack.get('summary', '')}\n"
            f"Awareness attack method: {awareness.get('attack_method', '')}\n"
            f"Awareness attack journey: {' | '.join(awareness.get('attack_journey') or [])}\n"
            f"Awareness exploit pattern (high-level): {exploit_pattern}\n"
            f"Awareness goal: {awareness_goal}\n"
            f"Training level: {training_level}\n"
            f"Potential IOCs: {', '.join(attack.get('key_iocs') or [])}\n"
            f"Defensive focus: {', '.join(attack.get('defense_focus') or [])}\n"
            f"Defensive metasploit context: {attack.get('metasploit_context', '')}\n"
            f"Organization context: {org_context or 'N/A'}\n\n"
            f"Exercise objective: {custom_objective or 'N/A'}\n"
            + (
                "Provide a structured answer with these sections:\n"
                "1) Threat overview\n"
                "2) Conceptual exploitation path (no commands)\n"
                "3) Defensive simulation timeline\n"
                "4) Detection (Logs + IOCs)\n"
                "5) Containment and recovery\n"
                "6) Hardening actions\n"
                "7) Metasploit as defensive lab reference only\n"
                "8) Safe defensive alternatives (what to monitor and disable)"
                if result_lang == 'en' else
                "أعطني إجابة مرتبة بهذا الشكل:\n"
                "1) شرح مبسط للهجمة\n"
                "2) كيف يتم استغلال الثغرة مفاهيميا (بدون أوامر)\n"
                "3) سيناريو محاكاة دفاعية على مراحل (بدون أي تنفيذ هجومي)\n"
                "4) كيف نكتشف الهجمة (Logs + IOCs)\n"
                "5) كيف نحتويها ونتعافى\n"
                "6) كيف نحصّن البيئة لتجنب تكرارها\n"
                "7) كيف نستخدم Metasploit كمرجع دفاعي في مختبر مصرح فقط دون أوامر تشغيل\n"
                "8) بدائل دفاعية آمنة بدل الأوامر الهجومية (ماذا نراقب؟ وماذا نعطّل؟)"
            )
        )
        try:
            ai_explanation = _call_do_ai(safe_prompt, system_prompt=safe_system)
        except Exception:
            ai_explanation = ''

    if not ai_explanation:
        ai_explanation = (
            (
                "Automated defensive explanation:\n"
                f"- Attack method (awareness): {attack_method}\n"
                f"- Conceptual exploitation path: {exploit_pattern}\n"
                f"- Attack journey: {' > '.join(awareness.get('attack_journey') or [])}\n"
                "- No offensive commands are shown; focus on detection, containment, and hardening.\n"
                "- Validate IOC patterns across logs and network telemetry.\n"
                "- Execute phased containment, then controlled recovery with root-cause analysis."
            )
            if result_lang == 'en' else
            (
                "شرح دفاعي تلقائي:\n"
                f"- طريقة الهجوم (توعوي): {attack_method}\n"
                f"- كيف يتم الاستغلال مفاهيميا: {exploit_pattern}\n"
                f"- مسار الهجوم: {' > '.join(awareness.get('attack_journey') or [])}\n"
                "- لا يتم عرض أوامر هجومية؛ البديل هو إجراءات كشف واحتواء وتحصين.\n"
                "- افهم مسار الهجمة وتأثيرها على الأصول.\n"
                "- راقب مؤشرات IOC في السجلات والشبكة.\n"
                "- فعّل الاحتواء المرحلي (عزل، منع اتصال، تعطيل حسابات مشبوهة).\n"
                "- نفذ الاستعادة من نسخ سليمة مع تحليل السبب الجذري.\n"
                "- طبّق ضوابط منع التكرار: تحديثات، MFA، تقسيم شبكة، ومراقبة مستمرة.\n"
                "- أي استخدام لـ Metasploit يكون داخل مختبر مصرح فقط ولأغراض التقييم الدفاعي."
            )
        )

    severity = str(attack.get('severity') or '').lower()
    base_risk = {
        'critical': 90,
        'high': 72,
        'medium': 50,
        'low': 28,
    }.get(severity, 55)

    analysis = {
        'risk_score': base_risk,
        'executive_summary': ('Baseline defensive analysis: prioritize early detection and structured containment.' if result_lang == 'en' else 'تحليل افتراضي دفاعي: يلزم رصد مبكر وخطة احتواء واضحة.'),
        'detection_plan': (
            [
                'Enable SIEM alerts for abnormal patterns tied to the scenario.',
                'Correlate IOC signals with EDR and DNS/Proxy logs.',
                'Monitor lateral movement attempts and rising security errors.'
            ]
            if result_lang == 'en' else
            [
                'تفعيل تنبيهات SIEM على الأنماط الشاذة المتعلقة بالسيناريو.',
                'ربط مؤشرات IOC مع قواعد EDR وDNS/Proxy logs.',
                'مراقبة محاولات الحركة الجانبية وارتفاع الأخطاء الأمنية.'
            ]
        ),
        'response_plan': (
            [
                'Isolate impacted systems and block suspicious communications immediately.',
                'Preserve evidence and maintain an incident timeline.',
                'Start phased recovery with post-fix validation.'
            ]
            if result_lang == 'en' else
            [
                'عزل الأنظمة المتأثرة فوراً ومنع الاتصالات المشبوهة.',
                'توثيق الأدلة وحفظ timeline للحادث.',
                'بدء الاستعادة التدريجية مع التحقق بعد المعالجة.'
            ]
        ),
        'hardening_plan': (
            [
                'Continuous patch management and legacy service reduction.',
                'Apply MFA and least-privilege access policies.',
                'Run periodic simulations and keep playbooks updated.'
            ]
            if result_lang == 'en' else
            [
                'Patch management مستمر + إغلاق الخدمات القديمة.',
                'تطبيق MFA وسياسات وصول أقل صلاحية.',
                'اختبارات محاكاة دورية وتحديث playbooks.'
            ]
        ),
    }

    if DO_AI_KEY:
        structured_system = (
            "أنت محلل SOC دفاعي. أعد JSON فقط بدون أي نص زائد. "
            "ممنوع الأوامر الهجومية أو خطوات استغلال."
        )
        structured_prompt = (
            f"Return strict JSON with keys: risk_score (0-100 integer), executive_summary (string), "
            f"detection_plan (array of 3 short strings), response_plan (array of 3 short strings), "
            f"hardening_plan (array of 3 short strings).\n"
            f"Scenario={attack.get('title', '')}; Severity={attack.get('severity', '')}; "
            f"Category={attack.get('category', '')}; Summary={attack.get('summary', '')}; "
            f"IOCs={', '.join(attack.get('key_iocs') or [])}; "
            f"Defense={', '.join(attack.get('defense_focus') or [])}; Context={org_context or 'N/A'}"
        )
        try:
            structured_raw = _call_do_ai(structured_prompt, system_prompt=structured_system)
            parsed = None
            try:
                parsed = json.loads(structured_raw)
            except Exception:
                m = re.search(r'\{[\s\S]*\}', structured_raw)
                if m:
                    parsed = json.loads(m.group(0))
            if isinstance(parsed, dict):
                rs = parsed.get('risk_score', analysis['risk_score'])
                if isinstance(rs, (int, float, str)):
                    try:
                        analysis['risk_score'] = int(max(0, min(100, int(float(rs)))))
                    except Exception:
                        pass
                summary = parsed.get('executive_summary')
                if isinstance(summary, str) and summary.strip():
                    analysis['executive_summary'] = summary.strip()
                for k in ('detection_plan', 'response_plan', 'hardening_plan'):
                    v = parsed.get(k)
                    if isinstance(v, list):
                        clean = [str(x).strip() for x in v if str(x).strip()][:5]
                        if clean:
                            analysis[k] = clean
        except Exception:
            pass

    simulation = {
        'id': attack.get('id'),
        'title': attack.get('title'),
        'category': attack.get('category'),
        'severity': attack.get('severity'),
        'summary': attack.get('summary'),
        'training_level': training_level,
        'training_level_label': _learning_level_label(training_level),
        'attack_method': attack_method,
        'exploit_pattern': exploit_pattern,
        'attack_journey': awareness.get('attack_journey') or [],
        'awareness_goal': awareness_goal,
        'key_iocs': attack.get('key_iocs') or [],
        'defense_focus': attack.get('defense_focus') or [],
        'metasploit_context': attack.get('metasploit_context') or '',
        'ai_explanation': ai_explanation,
        'org_context': org_context,
        'custom_attack_type': custom_attack_type,
        'custom_objective': custom_objective,
        'exercise_authority': ('صلاحيات كاملة داخل بيئة محاكاة' if result_lang == 'ar' else 'Full authority in simulation environment'),
        'result_lang': result_lang,
        'generated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    realism_pack = _learning_build_realism_pack(attack, awareness, analysis, org_context, training_level, lang=result_lang)
    simulation.update({
        'simulation_style': realism_pack.get('simulation_style'),
        'simulation_pace_note': realism_pack.get('simulation_pace_note'),
        'initial_access_vector': realism_pack.get('initial_access_vector'),
        'business_context': realism_pack.get('business_context'),
        'vulnerability_title': realism_pack.get('vulnerability_title') or '',
        'vulnerability_master_brief': realism_pack.get('vulnerability_master_brief') or '',
        'vulnerability_root_causes': realism_pack.get('vulnerability_root_causes') or [],
        'vulnerability_impact_chain': realism_pack.get('vulnerability_impact_chain') or [],
        'commander_brief': realism_pack.get('commander_brief') or '',
        'scenario_timeline': realism_pack.get('timeline') or [],
        'scenario_injects': realism_pack.get('injects') or [],
        'expected_artifacts': realism_pack.get('artifacts') or [],
        'decision_points': realism_pack.get('decision_points') or [],
        'live_feed': realism_pack.get('live_feed') or [],
        'pressure_cards': realism_pack.get('pressure_cards') or [],
        'win_conditions': realism_pack.get('win_conditions') or [],
        'common_tools': realism_pack.get('common_tools') or [],
        'common_commands': realism_pack.get('common_commands') or [],
        'success_signals': realism_pack.get('success_signals') or [],
        'failure_signals': realism_pack.get('failure_signals') or [],
        'exercise_kpis': realism_pack.get('kpis') or [],
    })
    simulation['training_checklist'] = _learning_build_training_checklist(attack, awareness, analysis, org_context, lang=result_lang)

    add_audit_log(
        'Learning Simulation',
        f"attack={attack.get('id', '')} severity={attack.get('severity', '')} custom={'yes' if custom_attack_type else 'no'}",
        username=session.get('username', '')
    )
    return jsonify({'success': True, 'simulation': simulation, 'analysis': analysis})


@app.route('/api/learning/report.pdf', methods=['GET'])
def learning_report_pdf_route():
    return jsonify({'success': False, 'error': 'تم تعطيل تصدير PDF لهذا القسم'}), 410


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
