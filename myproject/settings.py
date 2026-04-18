import os
import dj_database_url
from pathlib import Path
from dotenv import load_dotenv

# --- 1. SET UP PATHS ---
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- 2. LOAD ENVIRONMENT VARIABLES ---
# This must come AFTER BASE_DIR is defined so it knows where the .env file is
load_dotenv(os.path.join(BASE_DIR, '.env'))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-s8l$(311kw#lec+vp)&^@n!677mx#@n(fe3m)s(e$64^t5-ltz'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = [
    'boemp.com',
    'www.boemp.com',
    'localhost',
    '127.0.0.1',
    '202.155.8.168'
]

# Application definition
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
    'whitenoise.middleware.WhiteNoiseMiddleware', # For CSS/Images on Railway
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

# --- 3. DATABASE SETTINGS ---
# Using the hardcoded Aiven URI as requested
DATABASES = {
    'default': dj_database_url.parse('postgres://avnadmin:AVNS_Fqf3-7U6nNhAXZbLtHU@pg-12ac4d70-rachelwilson29099-7626.l.aivencloud.com:28390/defaultdb?sslmode=require')
}

# --- SMART DATABASE SETTINGS (Keep your original logic as comments) ---
#if os.getenv('DATABASE_URL'):
#    DATABASES = {
#        'default': dj_database_url.config(
#            conn_max_age=600,
#            ssl_require=True  # Changed to True for Aiven Cloud
#        )
#    }
#else:
#    DATABASES = {
#        'default': {
#            'ENGINE': 'django.db.backends.postgresql',
#            'NAME': 'ubuydatabase',
#            'USER': 'postgres',
#            'PASSWORD': '123123',
#            'HOST': '127.0.0.1',
#            'PORT': '5432',
#        }
#    }

# Password validation
AUTH_PASSWORD_VALIDATORS = []

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
LOGIN_URL = '/login/'
STAFF_LOGIN_URL = '/staff/login/'

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- SECURITY SETTINGS ---

# Fix "Origin checking failed" error
CSRF_TRUSTED_ORIGINS = [
    'https://boemp.com',
    'https://www.boemp.com',
    'http://202.155.8.168',        # Added for VPS IP
    'http://202.155.8.168:8000'    # Added for VPS IP with Port
]

CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True

# For Nginx reverse proxy with HTTPS
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
