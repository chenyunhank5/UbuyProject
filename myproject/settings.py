import os
import dj_database_url
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(os.path.join(BASE_DIR, '.env'))
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-s8l$(311kw#lec+vp)&^@n!677mx#@n(fe3m)s(e$64^t5-ltz'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# --- UPDATED: ALLOWED_HOSTS ---
ALLOWED_HOSTS = ['*', 'localhost', '127.0.0.1', '.railway.app']

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

DATABASES = {
    'default': dj_database_url.parse('postgres://avnadmin:AVNS_Fqf3-7U6nNhAXZbLtHU@pg-12ac4d70-rachelwilson29099-7626.l.aivencloud.com:28390/defaultdb?sslmode=require')
}
# --- SMART DATABASE SETTINGS ---
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

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- ADD THESE LINES BELOW FOR RAILWAY SECURITY ---

# This fixes the "Origin checking failed" error
CSRF_TRUSTED_ORIGINS = [
    'https://ubuyproject.up.railway.app',
    'https://*.railway.app',
    'http://202.155.8.168',        # Add this
    'http://202.155.8.168:8000'   # Add this
]

# Tell Django to use secure cookies since Railway uses HTTPS
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
