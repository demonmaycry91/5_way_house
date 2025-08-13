from . import db
from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# --- 中介關聯表 ---
roles_users = db.Table('roles_users',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('role.id'), primary_key=True)
)

# --- 權限常數 ---
class Permission:
    MANAGE_USERS = 'manage_users'
    MANAGE_ROLES = 'manage_roles'
    MANAGE_LOCATIONS = 'manage_locations'
    VIEW_REPORTS = 'view_reports'
    OPERATE_POS = 'operate_pos'
    SYSTEM_SETTINGS = 'system_settings'

class Role(db.Model):
    """角色模型"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    permissions = db.Column(db.Text, nullable=True) # 以逗號分隔的權限字串
    users = db.relationship('User', secondary=roles_users, back_populates='roles')

    def __repr__(self):
        return f'<Role {self.name}>'
        
    def get_permissions(self):
        if self.permissions:
            return self.permissions.split(',')
        return []

class User(db.Model, UserMixin):
    """使用者模型"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    
    # --- 新增/修改：Google 登入相關欄位 ---
    email = db.Column(db.String(120), unique=True, nullable=True)
    google_id = db.Column(db.String(120), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(200), nullable=True) # 允許密碼為空
    
    roles = db.relationship('Role', secondary=roles_users, back_populates='users', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)
        
    def has_role(self, role_name):
        return self.roles.filter_by(name=role_name).first() is not None

    def can(self, permission_name):
        """檢查使用者是否具備某項權限"""
        for role in self.roles:
            if permission_name in role.get_permissions():
                return True
        return False

    def __repr__(self):
        return f'<User {self.username}>'

# (Location, BusinessDay, Transaction 模型維持不變)
class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    business_days = db.relationship('BusinessDay', back_populates='location', lazy=True)
    def __repr__(self):
        return f'<Location {self.name}>'
    
class BusinessDay(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'), nullable=False)
    location = db.relationship('Location', back_populates='business_days')
    location_notes = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='NOT_STARTED')
    opening_cash = db.Column(db.Float, nullable=False)
    total_sales = db.Column(db.Float, default=0.0)
    closing_cash = db.Column(db.Float, nullable=True)
    expected_cash = db.Column(db.Float, nullable=True)
    cash_diff = db.Column(db.Float, nullable=True)
    total_items = db.Column(db.Integer, default=0)
    total_transactions = db.Column(db.Integer, default=0)
    cash_breakdown = db.Column(db.Text, nullable=True)
    signature_operator = db.Column(db.Text, nullable=True)
    signature_reviewer = db.Column(db.Text, nullable=True)
    signature_cashier = db.Column(db.Text, nullable=True)
    transactions = db.relationship('Transaction', backref='business_day', lazy=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    def __repr__(self):
        return f'<BusinessDay {self.date} - {self.location.name}>'

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    amount = db.Column(db.Float, nullable=False)
    item_count = db.Column(db.Integer, nullable=False)
    business_day_id = db.Column(db.Integer, db.ForeignKey('business_day.id'), nullable=False)
    def __repr__(self):
        return f'<Transaction {self.id} - Amount: {self.amount}>'

# --- 新增：系統設定模型 ---
# 這是一個簡單的鍵值對儲存模型，用於存放全域設定
class SystemSetting(db.Model):
    __tablename__ = 'system_setting'
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(200), nullable=True)

    @staticmethod
    def get(key, default=None):
        """一個方便的靜態方法，用於根據鍵名獲取設定值"""
        setting = db.session.get(SystemSetting, key)
        return setting.value if setting else default

    @staticmethod
    def set(key, value):
        """一個方便的靜態方法，用於設定或更新一個值"""
        setting = db.session.get(SystemSetting, key)
        if setting:
            setting.value = value
        else:
            setting = SystemSetting(key=key, value=value)
            db.session.add(setting)
        db.session.commit()

