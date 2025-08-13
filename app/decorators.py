from functools import wraps
from flask import abort
from flask_login import current_user

def admin_required(f):
    """
    一個裝飾器，用來確保只有具備 'Admin' 角色的使用者才能存取某個路由。
    如果使用者未登入或不具備 'Admin' 角色，將會回傳 403 Forbidden 錯誤。
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.has_role('Admin'):
            abort(403)  # Forbidden
        return f(*args, **kwargs)
    return decorated_function
