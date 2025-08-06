# my_app/auth_commands.py (新檔案)

import click
from flask.cli import with_appcontext
from . import db
from .models import User

# 建立一個指令群組
@click.group(name='auth', help="使用者驗證相關指令")
def auth_cli():
    pass

@auth_cli.command("create-user")
@click.argument("username")
@click.argument("password")
@with_appcontext
def create_user(username, password):
    """建立一個新的使用者帳號"""
    if User.query.filter_by(username=username).first():
        click.echo(f"錯誤：使用者 '{username}' 已經存在。")
        return
    
    new_user = User(username=username)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    click.echo(f"成功建立使用者：'{username}'。")

@auth_cli.command("reset-password")
@click.argument("username")
@click.argument("new_password")
@with_appcontext
def reset_password(username, new_password):
    """重設指定使用者的密碼"""
    # 根據帳號名稱尋找使用者
    user = User.query.filter_by(username=username).first()

    # 如果找不到該使用者，顯示錯誤訊息並結束
    if user is None:
        click.echo(f"錯誤：找不到使用者 '{username}'。")
        return
    
    # 如果找到了，就使用我們在 User 模型中定義好的 set_password 方法來設定新密碼
    user.set_password(new_password)
    # 提交資料庫變更
    db.session.commit()
    click.echo(f"使用者 '{username}' 的密碼已成功重設。")
    
def init_app(app):
    """在 App 中註冊指令"""
    app.cli.add_command(auth_cli)