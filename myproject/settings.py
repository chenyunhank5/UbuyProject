import os
import dj_database_url
import sys
from pathlib import Path
from dotenv import load_dotenv

# --- 1. SET UP PATHS ---
BASE_DIR = Path(__file__).resolve().parent.parent

# --- 2. LOAD ENVIRONMENT VARIABLES ---
load_dotenv(os.path.join(BASE_DIR, '.env'))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-s8l$(311kw#lec+vp)&^@n!677mx#@n(fe3m)s(e$64^t5-ltz'

# --- 3. DYNAMIC DEBUG & HOSTS ---
ALLOWED_HOSTS = [
    'boemp.com',
    'www.boemp.com',
    'localhost',
    '127.0.0.1',
    '202.155.8.168'
]

# Detect if we are running locally on your PC
IS_LOCAL = 'runserver' in sys.argv and ('127.0.0.1' in sys.argv or 'localhost' in sys.argv)

# ✅ This is the fix: True on your PC, False on the server
DEBUG = IS_LOCAL

# --- 4. APPLICATION DEFINITION ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'MyApp',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'myproject.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'myproject.wsgi.application'

# --- 5. DATABASE SETTINGS ---
DATABASES = {
    'default': dj_database_url.parse(
        'postgres://avnadmin:AVNS_Fqf3-7U6nNhAXZbLtHU@pg-12ac4d70-rachelwilson29099-7626.l.aivencloud.com:28390/defaultdb?sslmode=require'
    )
}

# --- 6. PASSWORD VALIDATION ---
AUTH_PASSWORD_VALIDATORS = []

# --- 7. INTERNATIONALIZATION ---
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# --- 8. LOGIN URLS ---
LOGIN_URL = '/login/'
STAFF_LOGIN_URL = '/staff/login/'

# --- 9. STATIC & MEDIA FILES ---
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- 10. SECURITY SETTINGS ---
CSRF_TRUSTED_ORIGINS = [
    'https://boemp.com',
    'https://www.boemp.com',
    'http://202.155.8.168',
    'http://202.155.8.168:8000'
]

if IS_LOCAL:
    # PC Testing Settings
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
else:
    # Live Production Settings
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    USE_X_FORWARDED_HOST = True
    SECURE_HSTS_SECONDS = 31536000 # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
