import click
from flask.cli import with_appcontext
from . import db
from .models import User, Role

@click.group(name='auth', help="使用者驗證相關指令")
def auth_cli():
    pass

@auth_cli.command("create-user")
@click.argument("username")
@click.argument("password")
@click.option('--role', default='Cashier', help="為使用者指派的角色 (例如: Admin, Cashier)")
@with_appcontext
def create_user(username, password, role):
    """建立一個新的使用者帳號"""
    if User.query.filter_by(username=username).first():
        click.echo(f"錯誤：使用者 '{username}' 已經存在。")
        return

    user_role = Role.query.filter_by(name=role).first()
    if not user_role:
        click.echo(f"錯誤：角色 '{role}' 不存在。請先執行 'flask auth init-roles'。")
        return

    new_user = User(username=username)
    new_user.set_password(password)
    new_user.roles.append(user_role) # 指派角色
    db.session.add(new_user)
    db.session.commit()
    click.echo(f"成功建立使用者：'{username}'，並指派角色：'{role}'。")

@auth_cli.command("reset-password")
@click.argument("username")
@click.argument("new_password")
@with_appcontext
def reset_password(username, new_password):
    """重設指定使用者的密碼"""
    user = User.query.filter_by(username=username).first()
    if user is None:
        click.echo(f"錯誤：找不到使用者 '{username}'。")
        return
    user.set_password(new_password)
    db.session.commit()
    click.echo(f"使用者 '{username}' 的密碼已成功重設。")

# --- 新增：初始化角色的指令 ---
@auth_cli.command("init-roles")
@with_appcontext
def init_roles():
    """在資料庫中建立預設的角色 (Admin, Cashier)"""
    roles = ['Admin', 'Cashier']
    for r in roles:
        role = Role.query.filter_by(name=r).first()
        if not role:
            role = Role(name=r)
            db.session.add(role)
            click.echo(f"成功建立角色：'{r}'")
    db.session.commit()
    click.echo("角色初始化完成。")


def init_app(app):
    """在 App 中註冊指令"""
    app.cli.add_command(auth_cli)
