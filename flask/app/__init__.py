import os
import logging
import logging.handlers
from flask import Flask
from flask_cors import CORS
from flask.logging import default_handler
from flask_wtf import CSRFProtect

from .config import DevConfig, ProdConfig, BASEDIR
from .models import db
from .modules.socketio import socketio


log = logging.getLogger(__name__)


def validate_secret_key(production: bool, secret_key: str | None) -> None:
    if production and len(secret_key or "") < 32:
        raise RuntimeError("SECRET_KEY must be at least 32 characters in production")


def init_logger(debug: bool=False) -> None:
    """
    Initialize the logger.
    
    Parameters
    ----------
    debug: :type:`bool`
        If debug is true, the logger will log all messages.
    """
        
    formatter = logging.Formatter("[{asctime}] {levelname} {name}: {message}", datefmt="%Y-%m-%d %H:%M:%S", style="{")
    
    if debug:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)
        
    file_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(BASEDIR, "logs", "app.log"),
        encoding="utf-8",
        maxBytes=8**7, 
    )
        
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logging.getLogger().addHandler(file_handler)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logging.getLogger().addHandler(console_handler)
    
    error_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(BASEDIR, "logs", "error.log"),
        encoding="utf-8",
        maxBytes=8**7, 
    )
        
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(formatter)
    logging.getLogger().addHandler(error_handler)

    #logging.getLogger().addHandler(default_handler)
    
def app_load_blueprints(app: Flask) -> None:
    """
    Load all blueprints
    
    Parameters
    ----------
    app: :class:`Flask`
        The flask app.
    """
    
    from .views.account_sys import account_sys
    from .views.admin_api import admin_api
    from .views.api import api
    from .views.error_handler import error_handler
    from .views.main import main
    from .views.haha import haha
    
    app.register_blueprint(account_sys)
    app.register_blueprint(admin_api)
    app.register_blueprint(api)
    app.register_blueprint(error_handler)
    app.register_blueprint(main)
    app.register_blueprint(haha)
    
    
def create_app() -> Flask:
    """
    Initialize the app.
    
    Returns
    -------
    app: :class:`Flask`
        A flask app.
    """
    production = os.getenv("PRODUCTION", "False").lower() in ("true", "1", "t")
    init_logger(debug=True)
    app = Flask(__name__)
    app.config.from_object(ProdConfig if production else DevConfig)
    validate_secret_key(production, app.config.get("SECRET_KEY"))

    from .core import core

    csrf = CSRFProtect(app)
    CORS(app)
    app_load_blueprints(app)
    db.init_app(app)
    # Use gevent in production (Docker), threading in development
    async_mode = 'gevent' if production else 'threading'
    socketio.init_app(app, cors_allowed_origins="*", async_mode=async_mode)
    core.init_socketio(socketio)
    with app.app_context(): db.create_all()
    
    return app
