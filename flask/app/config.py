import os
from dotenv import load_dotenv
from datetime import timedelta


BASEDIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(os.path.dirname(BASEDIR), ".flaskenv"), override=True)
load_dotenv(os.path.join(BASEDIR, ".env"), override=True)

TOKEN = os.getenv("TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI") or "/oauth/callback"
SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI")
SECRET_KEY = os.getenv("SECRET_KEY")
OAUTH_URL = "https://discord.com/oauth2/authorize" if CLIENT_ID else None

AUTH_SESSION_IDLE_MINUTES = int(os.getenv("AUTH_SESSION_IDLE_MINUTES", "30"))
AUTH_SESSION_ABSOLUTE_HOURS = int(os.getenv("AUTH_SESSION_ABSOLUTE_HOURS", "12"))
UNKNOWN_PLAYER_TTL_SECONDS = int(os.getenv("UNKNOWN_PLAYER_TTL_SECONDS", "1800"))
UNKNOWN_PLAYER_LIMIT = int(os.getenv("UNKNOWN_PLAYER_LIMIT", "200"))

YELLOW_TEXT_COLOR = "\33[33m"
RESET_TEXT_COLOR = "\33[0m"


class Config(object):
    SECRET_KEY = SECRET_KEY
    JSON_AS_ASCII = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=AUTH_SESSION_IDLE_MINUTES)
    AUTH_SESSION_ABSOLUTE_LIFETIME = timedelta(hours=AUTH_SESSION_ABSOLUTE_HOURS)
    SESSION_REFRESH_EACH_REQUEST = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"


class ProdConfig(Config):
    DEBUG = False
    SESSION_COOKIE_NAME = "__Host-izcc_session"
    SESSION_COOKIE_SECURE = True
    SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI
    if SQLALCHEMY_DATABASE_URI is None:
        print("Warning: SQLALCHEMY_DATABASE_URI is not set, using sqlite database instead.")
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASEDIR, "db.sqlite3")


class DevConfig(Config):
    DEBUG = True
    SECRET_KEY = SECRET_KEY or os.urandom(32).hex()
    SESSION_COOKIE_NAME = "izcc_session"
    SESSION_COOKIE_SECURE = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASEDIR, "db.sqlite3")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
