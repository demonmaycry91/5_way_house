# app/routes/admin_routes.py (新檔案)

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from ..models import Location
from .. import db
import re

# 建立名為 'admin' 的藍圖，並設定 URL 前綴為 /admin
bp = Blueprint('admin', __name__, url_prefix='/admin')

def generate_slug(name):
    """一個簡單的函式，根據中文名稱產生一個 URL-friendly 的 slug。"""
    # 移除非中文字元、字母和數字的字元
    name = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '-', name)
    # 將連續的連字號替換為單個連字號
    name = re.sub(r'-+', '-', name)
    # 移除開頭和結尾的連字號
    return name.lower().strip('-')

@bp.route('/locations')
@login_required
def list_locations():
    """顯示所有據點的列表頁面。"""
    locations = Location.query.order_by(Location.id).all()
    return render_template('admin/locations.html', locations=locations)

@bp.route('/locations/add', methods=['GET', 'POST'])
@login_required
def add_location():
    """處理新增據點的頁面和邏輯。"""
    if request.method == 'POST':
        name = request.form.get('name')
        slug = request.form.get('slug')

        if not name or not slug:
            flash('據點名稱和 Slug 皆為必填欄位。', 'danger')
            return render_template('admin/location_form.html', form_title='新增據點')

        # 檢查名稱或 slug 是否已存在
        if Location.query.filter((Location.name == name) | (Location.slug == slug)).first():
            flash('據點名稱或 Slug 已存在，請使用不同的名稱。', 'danger')
            return render_template('admin/location_form.html', form_title='新增據點', name=name, slug=slug)
        
        # 建立新的 Location 物件並存入資料庫
        new_location = Location(name=name, slug=slug)
        db.session.add(new_location)
        db.session.commit()
        
        flash(f'據點 "{name}" 已成功新增！', 'success')
        return redirect(url_for('admin.list_locations'))

    return render_template('admin/location_form.html', form_title='新增據點')


@bp.route('/locations/<int:location_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_location(location_id):
    """處理編輯現有據點的頁面和邏輯。"""
    location = Location.query.get_or_404(location_id)

    if request.method == 'POST':
        name = request.form.get('name')
        slug = request.form.get('slug')

        if not name or not slug:
            flash('據點名稱和 Slug 皆為必填欄位。', 'danger')
            return render_template('admin/location_form.html', form_title='編輯據點', location=location)

        # 檢查新名稱或 slug 是否與其他據點衝突
        existing_location = Location.query.filter(Location.id != location_id, (Location.name == name) | (Location.slug == slug)).first()
        if existing_location:
            flash('據點名稱或 Slug 已被其他據點使用。', 'danger')
            return render_template('admin/location_form.html', form_title='編輯據點', location=location)

        location.name = name
        location.slug = slug
        db.session.commit()
        
        flash(f'據點 "{name}" 已成功更新！', 'success')
        return redirect(url_for('admin.list_locations'))

    return render_template('admin/location_form.html', form_title='編輯據點', location=location)


@bp.route('/locations/<int:location_id>/delete', methods=['POST'])
@login_required
def delete_location(location_id):
    """處理刪除據點的邏輯。"""
    location = Location.query.get_or_404(location_id)
    
    # 檢查該據點是否仍有關聯的營業日紀錄
    if location.business_days:
        flash(f'錯誤：無法刪除據點 "{location.name}"，因為它仍有相關的營業日紀錄。', 'danger')
        return redirect(url_for('admin.list_locations'))

    db.session.delete(location)
    db.session.commit()
    
    flash(f'據點 "{location.name}" 已成功刪除。', 'success')
    return redirect(url_for('admin.list_locations'))
