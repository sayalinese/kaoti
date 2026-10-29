import sqlite3

from flask import Flask, jsonify, send_from_directory

from .config import WEB_DIR
from .db import init_db, storage_status
from .errors import AppError
from .routes.imports import bp as imports_bp
from .routes.library import bp as library_bp
from .routes.ocr import bp as ocr_bp
from .routes.quiz import bp as quiz_bp
from .routes.settings import bp as settings_bp


def create_app() -> Flask:
    app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="")
    app.json.ensure_ascii = False
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
    app.config["APP_BUILD"] = "image-extract-v2"

    init_db()

    app.register_blueprint(settings_bp)
    app.register_blueprint(library_bp)
    app.register_blueprint(ocr_bp)
    app.register_blueprint(imports_bp)
    app.register_blueprint(quiz_bp)

    @app.get("/")
    def index():
        return send_from_directory(WEB_DIR, "index.html")

    @app.get("/api/health")
    def health():
        return jsonify({**storage_status(), "build": app.config["APP_BUILD"]})

    @app.errorhandler(AppError)
    def handle_app_error(exc: AppError):
        return jsonify({"error": str(exc)}), exc.status

    @app.errorhandler(413)
    def handle_too_large(exc):
        return jsonify({"error": "上传内容超过 25MB，请拆分后再导入"}), 413

    @app.errorhandler(sqlite3.Error)
    def handle_database_error(exc):
        app.logger.exception("SQLite operation failed")
        return jsonify({"error": "数据库读写失败，请检查题库数据目录"}), 500

    return app
