# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os
from dotenv import load_dotenv
from redis import Redis
import rq
from flask_wtf.csrf import CSRFProtect
# --- 新增匯入 ---
from sqlalchemy import MetaData
# --- 修正點：匯入 LoginManager ---
from flask_login import LoginManager
import json

load_dotenv()
csrf = CSRFProtect()

# --- 新增：為資料庫約束(constraint)定義命名慣例 ---
# 這會告訴 SQLAlchemy 如何自動為索引、唯一約束、外鍵等命名
convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

# --- 修改：將命名慣例應用到 SQLAlchemy ---
metadata = MetaData(naming_convention=convention)
db = SQLAlchemy(metadata=metadata)

migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'cashier.login'

def create_app():
    app = Flask(__name__, instance_relative_config=True)

    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a-fallback-secret-key')
    app.config['SESSION_PERMANENT'] = False
    
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    db_path = os.path.join(app.instance_path, 'app.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    app.config['REDIS_URL'] = os.getenv('REDIS_URL', 'redis://')
    app.redis = Redis.from_url(app.config['REDIS_URL'])
    app.task_queue = rq.Queue('cashier-tasks', connection=app.redis)

    csrf.init_app(app)
    db.init_app(app)
    # --- 修改：加入 render_as_batch=True 以支援 SQLite 的表結構變更 ---
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)

    # --- 新增：註冊自訂的 Jinja2 過濾器 ---
    def from_json_filter(value):
        if value:
            return json.loads(value)
        return {}
    app.jinja_env.filters['from_json'] = from_json_filter

    from .routes import main_routes, ocr_routes, cashier_routes, google_routes, admin_routes, report_routes
    app.register_blueprint(main_routes.bp)
    app.register_blueprint(ocr_routes.bp)
    app.register_blueprint(cashier_routes.bp)
    app.register_blueprint(google_routes.bp)
    app.register_blueprint(admin_routes.bp)
    app.register_blueprint(report_routes.bp)

    from . import models
    from . import auth_commands
    auth_commands.init_app(app)

    return app