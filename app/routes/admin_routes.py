from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
# --- 新增匯入 Category 模型 ---
from ..models import Location, User, Role, Permission, Category
from .. import db
# --- 新增匯入 CategoryForm ---
from ..forms import LocationForm, RoleForm, UserForm, CategoryForm
from ..decorators import admin_required

bp = Blueprint('admin', __name__, url_prefix='/admin')

@bp.before_request
@login_required
@admin_required
def before_request():
    """保護所有 admin 藍圖下的路由"""
    pass

# --- 據點管理 ---
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

# --- 新增：商品類別管理 ---
@bp.route('/locations/<int:location_id>/categories')
def list_categories(location_id):
    location = Location.query.get_or_404(location_id)
    # 確保只顯示該據點的類別
    categories = Category.query.filter_by(location_id=location.id).order_by(Category.id).all()
    return render_template('admin/categories.html', location=location, categories=categories)

@bp.route('/locations/<int:location_id>/categories/add', methods=['GET', 'POST'])
def add_category(location_id):
    location = Location.query.get_or_404(location_id)
    form = CategoryForm()
    if form.validate_on_submit():
        new_category = Category(
            name=form.name.data,
            color=form.color.data,
            location_id=location.id
        )
        db.session.add(new_category)
        db.session.commit()
        flash(f'類別 "{new_category.name}" 已成功新增至據點 "{location.name}"。', 'success')
        return redirect(url_for('admin.list_categories', location_id=location.id))
    return render_template('admin/category_form.html', form=form, form_title='新增商品類別', location=location)

@bp.route('/categories/<int:category_id>/edit', methods=['GET', 'POST'])
def edit_category(category_id):
    category = Category.query.get_or_404(category_id)
    location = category.location
    form = CategoryForm(obj=category)
    if form.validate_on_submit():
        form.populate_obj(category)
        db.session.commit()
        flash(f'類別 "{category.name}" 已更新。', 'success')
        return redirect(url_for('admin.list_categories', location_id=location.id))
    return render_template('admin/category_form.html', form=form, form_title='編輯商品類別', location=location)

@bp.route('/categories/<int:category_id>/delete', methods=['POST'])
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    location_id = category.location_id
    # TODO: 檢查是否有交易品項關聯到此類別
    db.session.delete(category)
    db.session.commit()
    flash('類別已刪除。', 'success')
    return redirect(url_for('admin.list_categories', location_id=location_id))


# --- 使用者管理 ---
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

# --- 角色與權限管理 ---
@bp.route('/roles')
def list_roles():
    roles = Role.query.order_by(Role.id).all()
    return render_template('admin/roles.html', roles=roles)

@bp.route('/roles/add', methods=['GET', 'POST'])
def add_role():
    form = RoleForm()
    # 動態地從 Permission class 取得所有權限常數作為選項
    form.permissions.choices = [
        (p, p) for p in dir(Permission) 
        if not p.startswith('__') and isinstance(getattr(Permission, p), str)
    ]
    if form.validate_on_submit():
        # 將勾選的權限列表組合成一個字串儲存
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
    # 在 GET 請求時，預先勾選該角色已有的權限
    form.permissions.data = role.get_permissions()
    return render_template('admin/role_form.html', form=form, form_title="編輯角色")

@bp.route('/roles/<int:role_id>/delete', methods=['POST'])
def delete_role(role_id):
    role = Role.query.get_or_404(role_id)
    db.session.delete(role)
    db.session.commit()
    flash('角色已刪除。', 'success')
    return redirect(url_for('admin.list_roles'))