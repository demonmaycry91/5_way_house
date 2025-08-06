from flask import render_template, request, flash, redirect, url_for, Blueprint
from flask_login import login_user, logout_user, login_required, current_user
from ..models import User
from .. import db, login_manager

# 1. 定義藍圖 (這是您原本就有的，保持不變)
bp = Blueprint('cashier', __name__, url_prefix='/cashier')


# 2. 定義 user_loader，它需要從 my_app/__init__.py 匯入 login_manager
@login_manager.user_loader
def load_user(user_id):
    """Flask-Login 需要這個函式來知道如何根據 user_id 找到使用者物件"""
    return User.query.get(int(user_id))


# 3. 定義路由，並使用 @login_required 保護需要登入的頁面
@bp.route('/')
@login_required
def cashier_page():
    """收銀機主頁，登入後才能看到"""
    return f"<h1>歡迎, {current_user.username}!</h1><a href='{url_for('cashier.logout')}'>點此登出</a>"


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """處理登入邏輯"""
    if current_user.is_authenticated:
        return redirect(url_for('cashier.cashier_page'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()

        if user is None or not user.check_password(password):
            flash('帳號或密碼錯誤，請重新輸入。', 'danger')
            return redirect(url_for('cashier.login'))
        
        login_user(user)
        flash('登入成功！', 'success')

        next_page = request.args.get('next')
        return redirect(next_page or url_for('cashier.cashier_page'))

    return render_template('cashier/login.html')


@bp.route('/logout')
@login_required
def logout():
    """處理登出邏輯"""
    logout_user()
    flash('您已成功登出。', 'info')
    return redirect(url_for('cashier.login'))