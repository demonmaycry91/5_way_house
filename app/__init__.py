from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
import os
from dotenv import load_dotenv
from redis import Redis
import rq
from flask_wtf.csrf import CSRFProtect

load_dotenv()
csrf = CSRFProtect()

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'cashier.login'

def create_app():
    app = Flask(__name__, instance_relative_config=True)

    # 從 .env 讀取設定
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a-fallback-secret-key')
    
    # 設定資料庫 URI
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    db_path = os.path.join(app.instance_path, 'app.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # 從 .env 讀取 Redis URL 並建立連線
    app.config['REDIS_URL'] = os.getenv('REDIS_URL', 'redis://')
    # 建立 Redis 連線物件和 RQ 任務隊列物件，並將它們附加到 app 物件上
    app.redis = Redis.from_url(app.config['REDIS_URL'])
    app.task_queue = rq.Queue('cashier-tasks', connection=app.redis)

    # 初始化資料庫等擴充套件
    csrf.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # 註冊藍圖
    from .routes import main_routes, ocr_routes, cashier_routes, google_routes, admin_routes
    app.register_blueprint(main_routes.bp)
    app.register_blueprint(ocr_routes.bp)
    app.register_blueprint(cashier_routes.bp)
    app.register_blueprint(google_routes.bp)
    app.register_blueprint(admin_routes.bp)

    from . import models
    from . import auth_commands
    auth_commands.init_app(app)

    return app
