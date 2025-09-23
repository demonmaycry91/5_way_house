# app/backup_commands.py
import click
import atexit
import threading
from flask.cli import with_appcontext
from flask import current_app
from .services.backup_service import backup_instance_to_drive, BackupScheduler
from .models import SystemSetting

@click.group(name='backup', help="管理雲端備份相關指令")
def backup_cli():
    pass

@backup_cli.command("init")
@with_appcontext
def init_backup_scheduler():
    """初始化並啟動備份排程器"""
    try:
        backup_frequency = SystemSetting.get('instance_backup_frequency', 'off')
        if backup_frequency == 'startup':
            backup_instance_to_drive()
            click.echo("已執行啟動時備份。")
        elif backup_frequency == 'shutdown':
            atexit.register(backup_instance_to_drive)
            click.echo("已註冊關閉時備份。")
        elif backup_frequency == 'interval':
            scheduler = BackupScheduler(current_app)
            scheduler.daemon = True
            scheduler.start()
            atexit.register(scheduler.stop)
            click.echo("已啟動固定間隔備份排程器。")
        else:
            click.echo("備份頻率設定為 '關閉'。")
        click.echo("備份初始化完成。")
    except Exception as e:
        click.echo(f"錯誤：備份初始化失敗，請確認資料庫已遷移：{e}")

def init_app(app):
    """在 App 中註冊指令"""
    app.cli.add_command(backup_cli)