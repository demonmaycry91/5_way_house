from . import db
from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import json

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
    permissions = db.Column(db.Text, nullable=True)
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
    email = db.Column(db.String(120), unique=True, nullable=True)
    google_id = db.Column(db.String(120), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(200), nullable=True)
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
        for role in self.roles:
            if permission_name in role.get_permissions():
                return True
        return False

    def __repr__(self):
        return f'<User {self.username}>'

class Location(db.Model):
    """營業據點模型"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    business_days = db.relationship('BusinessDay', back_populates='location', lazy=True, cascade="all, delete-orphan")
    categories = db.relationship('Category', back_populates='location', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Location {self.name}>'

class Category(db.Model):
    """商品類別模型"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(7), nullable=False, default='#cccccc')
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'), nullable=False)
    
    category_type = db.Column(db.String(30), nullable=False, default='product', server_default='product')
    discount_rules = db.Column(db.Text, nullable=True)

    location = db.relationship('Location', back_populates='categories')
    items = db.relationship('TransactionItem', back_populates='category', lazy=True)

    def get_rules(self):
        if self.discount_rules:
            try:
                return json.loads(self.discount_rules)
            except json.JSONDecodeError:
                return {}
        return {}

    def set_rules(self, rules_dict):
        self.discount_rules = json.dumps(rules_dict)

    def __repr__(self):
        return f'<Category {self.name}>'
    
class BusinessDay(db.Model):
    """營業日模型"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    
    # --- ↓↓↓ 核心修正處 (將 location__id 改回 location_id) ↓↓↓ ---
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'), nullable=False)
    # --- ↑↑↑ 修正結束 ↑↑↑ ---

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
    transactions = db.relationship('Transaction', backref='business_day', lazy=True, cascade="all, delete-orphan")
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    donation_total = db.Column(db.Float, default=0.0)
    other_total = db.Column(db.Float, default=0.0)

    def __repr__(self):
        return f'<BusinessDay {self.date} - {self.location.name}>'

class Transaction(db.Model):
    """交易紀錄模型"""
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    amount = db.Column(db.Float, nullable=False)
    item_count = db.Column(db.Integer, nullable=False)
    business_day_id = db.Column(db.Integer, db.ForeignKey('business_day.id'), nullable=False)
    items = db.relationship('TransactionItem', back_populates='transaction', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Transaction {self.id} - Amount: {self.amount}>'

class TransactionItem(db.Model):
    """單一交易品項模型"""
    id = db.Column(db.Integer, primary_key=True)
    price = db.Column(db.Float, nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transaction.id'), nullable=False)
    transaction = db.relationship('Transaction', back_populates='items')
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    category = db.relationship('Category', back_populates='items')

    def __repr__(self):
        return f'<TransactionItem {self.id} - Price: {self.price}>'

class SystemSetting(db.Model):
    __tablename__ = 'system_setting'
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(200), nullable=True)

    @staticmethod
    def get(key, default=None):
        setting = db.session.get(SystemSetting, key)
        return setting.value if setting else default

    @staticmethod
    def set(key, value):
        setting = db.session.get(SystemSetting, key)
        if setting:
            setting.value = value
        else:
            setting = SystemSetting(key=key, value=value)
            db.session.add(setting)
        db.session.commit()