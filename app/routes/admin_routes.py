import os
import json
from flask import (
    render_template,
    request,
    flash,
    redirect,
    url_for,
    Blueprint,
    jsonify,
    current_app,
    Response
)

from flask_login import login_user, logout_user, login_required, current_user
from ..models import User, BusinessDay, Transaction, Location, SystemSetting, Category, TransactionItem, Role, Permission
from .. import db, login_manager, csrf
from ..forms import LoginForm, StartDayForm, CloseDayForm, ConfirmReportForm, GoogleSettingsForm, LocationForm, UserForm, RoleForm, CategoryForm
from datetime import date, datetime
from ..services import google_service
from sqlalchemy.orm import contains_eager
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError # 新增此行
from ..decorators import admin_required
from weasyprint import HTML
from sqlalchemy.sql import func
from sqlalchemy import case


bp = Blueprint('admin', __name__, url_prefix='/admin')

@bp.before_request
@login_required
@admin_required
def before_request():
    """保護所有 admin 藍圖下的路由"""
    pass

# --- 據點管理 (維持不變) ---
@bp.route('/locations')
def list_locations():
    locations = Location.query.order_by(Location.id).all()
    return render_template('admin/locations.html', locations=locations)

@bp.route('/locations/add', methods=['GET', 'POST'])
def add_location():
    form = LocationForm()
    if form.validate_on_submit():
        new_location = Location(name=form.name.data, slug=form.slug.data)
        db.session.add(new_location)
        db.session.commit()
        flash('據點已新增', 'success')
        return redirect(url_for('admin.list_locations'))
    return render_template('admin/location_form.html', form=form, form_title='新增據點')

@bp.route('/locations/<int:location_id>/edit', methods=['GET', 'POST'])
def edit_location(location_id):
    location = Location.query.get_or_404(location_id)
    form = LocationForm(obj=location)
    if form.validate_on_submit():
        form.populate_obj(location)
        db.session.commit()
        flash('據點已更新', 'success')
        return redirect(url_for('admin.list_locations'))
    return render_template('admin/location_form.html', form=form, form_title='編輯據點')

@bp.route('/locations/<int:location_id>/delete', methods=['POST'])
def delete_location(location_id):
    location = Location.query.get_or_404(location_id)
    if location.business_days:
        flash(f'錯誤：無法刪除據點 "{location.name}"，因為它仍有相關的營業日紀錄。', 'danger')
        return redirect(url_for('admin.list_locations'))
    db.session.delete(location)
    db.session.commit()
    flash('據點已刪除', 'success')
    return redirect(url_for('admin.list_locations'))

# --- 商品類別管理 ---
@bp.route('/locations/<int:location_id>/categories', methods=['GET', 'POST'])
@csrf.exempt
# --- 商品類別管理 ---
@bp.route('/locations/<int:location_id>/categories', methods=['GET', 'POST'])
@csrf.exempt
def list_categories(location_id):
    location = Location.query.get_or_404(location_id)
    product_categories_query = Category.query.filter_by(location_id=location.id, category_type='product').all()
    product_categories_choices = [(0, '--- 全部商品 ---')] + [(p.id, p.name) for p in product_categories_query]

    if request.method == 'POST':
        try:
            # 處理現有類別的更新
            for category in location.categories:
                cat_id = category.id
                prefix = f'category-{cat_id}-'
                if request.form.get(prefix + 'name') is not None:
                    category.name = request.form.get(prefix + 'name')
                    category.color = request.form.get(prefix + 'color')
                    category.category_type = request.form.get(prefix + 'type')
                    
                    rules = {}
                    ctype = category.category_type
                    if ctype in ['buy_n_get_m', 'buy_x_get_x_minus_1', 'buy_odd_even']:
                        target_id = request.form.get(f'rule-{cat_id}-target_category_id')
                        if target_id: rules['target_category_id'] = int(target_id)
                    
                    if ctype == 'buy_n_get_m':
                        buy_n = request.form.get(f'rule-{cat_id}-buy_n')
                        get_m = request.form.get(f'rule-{cat_id}-get_m_free')
                        if buy_n: rules['buy_n'] = int(buy_n)
                        if get_m: rules['get_m_free'] = int(get_m)

                    category.set_rules(rules) if rules else setattr(category, 'discount_rules', None)

            # 處理新增的類別
            new_names = request.form.getlist('new-name')
            if new_names:
                new_colors = request.form.getlist('new-color')
                new_types = request.form.getlist('new-type')
                new_targets = request.form.getlist('new-rule-target_category_id')
                new_buy_ns = request.form.getlist('new-rule-buy_n')
                new_get_ms = request.form.getlist('new-rule-get_m_free')
                
                target_idx, buy_get_idx = 0, 0
                for i, name in enumerate(new_names):
                    if name.strip():
                        new_category = Category(
                            name=name.strip(),
                            color=new_colors[i] or '#cccccc',
                            location_id=location.id,
                            category_type=new_types[i]
                        )
                        
                        new_rules = {}
                        ctype = new_types[i]
                        if ctype in ['buy_n_get_m', 'buy_x_get_x_minus_1', 'buy_odd_even']:
                            if target_idx < len(new_targets):
                                new_rules['target_category_id'] = int(new_targets[target_idx])
                                target_idx += 1
                        
                        if ctype == 'buy_n_get_m':
                            if buy_get_idx < len(new_buy_ns) and new_buy_ns[buy_get_idx]:
                                new_rules['buy_n'] = int(new_buy_ns[buy_get_idx])
                            if buy_get_idx < len(new_get_ms) and new_get_ms[buy_get_idx]:
                                new_rules['get_m_free'] = int(new_get_ms[buy_get_idx])
                            buy_get_idx += 1
                        
                        if new_rules:
                            new_category.set_rules(new_rules)
                        
                        db.session.add(new_category)
            
            db.session.commit()
            flash('所有變更已成功儲存！', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'儲存失敗，發生錯誤：{e}', 'danger')

        return redirect(url_for('admin.list_categories', location_id=location.id))

    categories = Category.query.filter_by(location_id=location.id).order_by(Category.id).all()
    return render_template('admin/categories.html', location=location, categories=categories, product_categories_choices=product_categories_choices)


def get_category_form_data(form, category):
    category.name = form.name.data
    category.color = form.color.data
    category.category_type = form.category_type.data
    
    rules = {}
    ctype = form.category_type.data
    if ctype in ['buy_n_get_m', 'buy_x_get_x_minus_1', 'buy_odd_even']:
        if form.rule_target_category_id.data is not None:
             rules['target_category_id'] = form.rule_target_category_id.data
    if ctype == 'buy_n_get_m':
        if form.rule_buy_n.data is not None:
            rules['buy_n'] = form.rule_buy_n.data
        if form.rule_get_m.data is not None:
            rules['get_m_free'] = form.rule_get_m.data
    
    category.set_rules(rules) if rules else setattr(category, 'discount_rules', None)


@bp.route('/locations/<int:location_id>/categories/add', methods=['GET', 'POST'])
def add_category(location_id):
    location = Location.query.get_or_404(location_id)
    form = CategoryForm(location_id=location.id)
    if form.validate_on_submit():
        new_category = Category(location_id=location.id)
        get_category_form_data(form, new_category)
        db.session.add(new_category)
        db.session.commit()
        flash(f'類別 "{new_category.name}" 已成功新增。', 'success')
        return redirect(url_for('admin.list_categories', location_id=location.id))
    return render_template('admin/category_form.html', form=form, form_title='新增商品類別', location=location)

@bp.route('/categories/<int:category_id>/edit', methods=['GET', 'POST'])
def edit_category(category_id):
    category = Category.query.get_or_404(category_id)
    location = category.location
    form = CategoryForm(location_id=location.id, obj=category)
    
    if form.validate_on_submit():
        get_category_form_data(form, category)
        db.session.commit()
        flash(f'類別 "{category.name}" 已更新。', 'success')
        return redirect(url_for('admin.list_categories', location_id=location.id))
    
    rules = category.get_rules()
    form.rule_target_category_id.data = rules.get('target_category_id')
    form.rule_buy_n.data = rules.get('buy_n')
    form.rule_get_m.data = rules.get('get_m_free')
        
    return render_template('admin/category_form.html', form=form, form_title='編輯商品類別', location=location, category=category)

@bp.route('/categories/<int:category_id>/delete', methods=['POST'])
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    location_id = category.location_id
    
    # 檢查是否有任何交易項目關聯此類別
    if TransactionItem.query.filter_by(category_id=category_id).first():
        flash(f'錯誤：無法刪除類別 "{category.name}"，因為已有交易紀錄使用此類別。', 'danger')
        return redirect(url_for('admin.list_categories', location_id=location_id))
        
    # 檢查是否有任何折扣規則關聯此類別
    if Category.query.filter(Category.discount_rules.like(f'%"{category_id}"%')).first():
        flash(f'錯誤：無法刪除類別 "{category.name}"，因為它被其他折扣規則所引用。', 'danger')
        return redirect(url_for('admin.list_categories', location_id=location_id))

    try:
        db.session.delete(category)
        db.session.commit()
        flash('類別已刪除。', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'刪除失敗，發生未預期錯誤：{e}', 'danger')
        current_app.logger.error(f"刪除類別 {category_id} 時發生錯誤: {e}", exc_info=True)

    return redirect(url_for('admin.list_categories', location_id=location_id))

# --- 使用者與角色管理 (維持不變) ---
@bp.route('/users')
def list_users():
    users = User.query.order_by(User.id).all()
    return render_template('admin/users.html', users=users)

@bp.route('/users/add', methods=['GET', 'POST'])
def add_user():
    form = UserForm(user=None)
    if form.validate_on_submit():
        user = User(username=form.username.data)
        if form.password.data:
            user.set_password(form.password.data)
        for role_id in form.roles.data:
            role = Role.query.get(role_id)
            user.roles.append(role)
        db.session.add(user)
        db.session.commit()
        flash('新使用者已建立。', 'success')
        return redirect(url_for('admin.list_users'))
    return render_template('admin/user_form.html', form=form, form_title="建立新使用者")

@bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    form = UserForm(user=user, obj=user)
    if form.validate_on_submit():
        user.username = form.username.data
        if form.password.data:
            user.set_password(form.password.data)
        user.roles = []
        for role_id in form.roles.data:
            role = Role.query.get(role_id)
            user.roles.append(role)
        db.session.commit()
        flash('使用者資料已更新。', 'success')
        return redirect(url_for('admin.list_users'))
    form.roles.data = [role.id for role in user.roles]
    return render_template('admin/user_form.html', form=form, form_title="編輯使用者", user=user)

@bp.route('/users/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash('使用者已刪除。', 'success')
    return redirect(url_for('admin.list_users'))

@bp.route('/roles')
def list_roles():
    roles = Role.query.order_by(Role.id).all()
    return render_template('admin/roles.html', roles=roles)

@bp.route('/roles/add', methods=['GET', 'POST'])
def add_role():
    form = RoleForm()
    form.permissions.choices = [
        (p, p) for p in dir(Permission) 
        if not p.startswith('__') and isinstance(getattr(Permission, p), str)
    ]
    if form.validate_on_submit():
        role = Role(name=form.name.data, permissions=','.join(form.permissions.data))
        db.session.add(role)
        db.session.commit()
        flash('新角色已建立。', 'success')
        return redirect(url_for('admin.list_roles'))
    return render_template('admin/role_form.html', form=form, form_title="建立新角色")

@bp.route('/roles/<int:role_id>/edit', methods=['GET', 'POST'])
def edit_role(role_id):
    role = Role.query.get_or_404(role_id)
    form = RoleForm(obj=role)
    form.permissions.choices = [
        (p, p) for p in dir(Permission) 
        if not p.startswith('__') and isinstance(getattr(Permission, p), str)
    ]
    if form.validate_on_submit():
        role.name = form.name.data
        role.permissions = ','.join(form.permissions.data)
        db.session.commit()
        flash('角色已更新。', 'success')
        return redirect(url_for('admin.list_roles'))
    form.permissions.data = role.get_permissions()
    return render_template('admin/role_form.html', form=form, form_title="編輯角色")

@bp.route('/roles/<int:role_id>/delete', methods=['POST'])
def delete_role(role_id):
    role = Role.query.get_or_404(role_id)
    db.session.delete(role)
    db.session.commit()
    flash('角色已刪除。', 'success')
    return redirect(url_for('admin.list_roles'))