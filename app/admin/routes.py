import csv
import io
import os
import shutil
import zipfile
from datetime import datetime, timedelta

from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, current_app, jsonify, send_file, Response)
from flask_login import login_required, current_user

from app import db
from app.models import (User, Course, Assignment, Submission, SimilarityResult,
                        AuditLog, PlagiarismGroup, AnalysisTask, SystemConfig,
                        Enrollment)
from app.utils.decorators import role_required

admin_bp = Blueprint('admin', __name__)

ALLOWED_EXTENSIONS = {'py', 'java', 'c', 'cpp', 'js'}
SUPPORTED_LANGUAGES = {'python', 'java', 'c', 'cpp', 'javascript'}


# ================================================================
# 种子配置（首次启动时初始化默认值）
# ================================================================

def _seed_default_config():
    defaults = {
        'allowed_extensions': ','.join(sorted(ALLOWED_EXTENSIONS)),
        'supported_languages': ','.join(sorted(SUPPORTED_LANGUAGES)),
        'similarity_threshold_default': '0.70',
        'weight_jaccard': '0.30',
        'weight_tree_edit': '0.40',
        'weight_semantic': '0.20',
        'weight_ngram': '0.10',
        'max_concurrent_tasks': '2',
        'max_file_size_mb': '2',
        'parser_timeout_seconds': '30',
    }
    for k, v in defaults.items():
        if SystemConfig.query.filter_by(key=k).first() is None:
            SystemConfig.set(k, v)


# ================================================================
# 管理后台首页 —— 系统概览
# ================================================================

@admin_bp.route('/')
@login_required
@role_required('admin')
def index():
    _seed_default_config()

    stats = {
        'user_count': User.query.count(),
        'student_count': User.query.filter_by(role='student').count(),
        'teacher_count': User.query.filter_by(role='teacher').count(),
        'course_count': Course.query.count(),
        'active_course_count': Course.query.filter_by(is_archived=False).count(),
        'assignment_count': Assignment.query.count(),
        'submission_count': Submission.query.count(),
        'analysis_count': SimilarityResult.query.count(),
        'plagiarism_group_count': PlagiarismGroup.query.count(),
    }

    recent_logs = AuditLog.query.order_by(
        AuditLog.created_at.desc()).limit(20).all()

    # Task stats
    stats['task_pending'] = AnalysisTask.query.filter_by(status='pending').count()
    stats['task_running'] = AnalysisTask.query.filter_by(status='running').count()
    stats['task_failed'] = AnalysisTask.query.filter_by(status='failed').count()

    # Storage estimate
    upload_folder = current_app.config['UPLOAD_FOLDER']
    total_size = 0
    file_count = 0
    if os.path.exists(upload_folder):
        for dirpath, _, filenames in os.walk(upload_folder):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.isfile(fp):
                    total_size += os.path.getsize(fp)
                    file_count += 1

    stats['storage_mb'] = round(total_size / (1024 * 1024), 2)
    stats['upload_count'] = file_count

    return render_template('admin/index.html', stats=stats, recent_logs=recent_logs)


# ================================================================
# 用户管理
# ================================================================

@admin_bp.route('/users')
@login_required
@role_required('admin')
def users():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    role_filter = request.args.get('role_filter', '').strip()

    query = User.query
    if search:
        query = query.filter(
            db.or_(User.username.contains(search),
                   User.display_name.contains(search),
                   User.email.contains(search)))
    if role_filter in ('student', 'teacher', 'admin'):
        query = query.filter_by(role=role_filter)

    pagination = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=30, error_out=False)

    return render_template('admin/users.html', users=pagination.items,
                           pagination=pagination, search=search,
                           role_filter=role_filter)


@admin_bp.route('/users/create', methods=['POST'])
@login_required
@role_required('admin')
def create_user():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'teacher')
    display_name = request.form.get('display_name', '').strip()
    email = request.form.get('email', '').strip()

    if not username or not password:
        flash('用户名和密码不能为空。')
        return redirect(url_for('admin.users'))

    if User.query.filter_by(username=username).first():
        flash('用户名已存在。')
        return redirect(url_for('admin.users'))

    if role not in ('student', 'teacher', 'admin'):
        flash('无效的角色。')
        return redirect(url_for('admin.users'))

    user = User(username=username, role=role,
                display_name=display_name or username,
                email=email or None)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    flash(f'用户 "{username}" ({role}) 创建成功。')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@role_required('admin')
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('不能操作自己的账号。')
        return redirect(url_for('admin.users'))

    user.is_active = not user.is_active
    db.session.commit()
    state = '已启用' if user.is_active else '已禁用'
    flash(f'用户 "{user.username}" {state}。')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@role_required('admin')
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    new_password = request.form.get('new_password', '').strip()
    if not new_password or len(new_password) < 6:
        flash('密码长度至少 6 位。')
        return redirect(url_for('admin.users'))

    user.set_password(new_password)
    db.session.commit()
    flash(f'用户 "{user.username}" 的密码已重置。')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/batch-import', methods=['POST'])
@login_required
@role_required('admin')
def batch_import_users():
    """批量导入用户（CSV/Excel 格式：username,password,role,display_name,email）。"""
    uploaded = request.files.get('file')
    if not uploaded or uploaded.filename == '':
        flash('请选择一个 CSV 文件。')
        return redirect(url_for('admin.users'))

    filename = uploaded.filename.lower()
    if not (filename.endswith('.csv') or filename.endswith('.txt')):
        flash('仅支持 CSV 或 TXT 文件（逗号分隔，UTF-8 编码）。')
        return redirect(url_for('admin.users'))

    try:
        content = uploaded.read()
        # Try UTF-8 first, then GBK
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            text = content.decode('gbk')

        reader = csv.reader(io.StringIO(text))
        created = 0
        skipped = 0
        errors = []

        for i, row in enumerate(reader, start=1):
            # Skip empty rows and header row
            if not row or all(c.strip() == '' for c in row):
                continue
            if i == 1 and row[0].strip().lower() in ('username', '用户名', '账号'):
                continue

            if len(row) < 2:
                errors.append(f'第 {i} 行：缺少列（至少需要 username,password）')
                skipped += 1
                continue

            username = row[0].strip()
            password = row[1].strip()
            role = row[2].strip().lower() if len(row) > 2 and row[2].strip() else 'student'
            display_name = row[3].strip() if len(row) > 3 else ''
            email = row[4].strip() if len(row) > 4 else ''

            if not username or not password:
                errors.append(f'第 {i} 行：用户名或密码为空')
                skipped += 1
                continue

            if role not in ('student', 'teacher', 'admin'):
                role = 'student'

            if User.query.filter_by(username=username).first():
                errors.append(f'第 {i} 行：用户名 "{username}" 已存在')
                skipped += 1
                continue

            user = User(username=username, role=role,
                        display_name=display_name or username,
                        email=email or None)
            user.set_password(password)
            db.session.add(user)
            created += 1

        db.session.commit()
        msg = f'批量导入完成：成功创建 {created} 个用户，跳过 {skipped} 条。'
        if errors:
            msg += f'（前 {min(5, len(errors))} 条错误：{"; ".join(errors[:5])}）'
        flash(msg)
    except Exception as e:
        flash(f'导入失败：{str(e)}')

    return redirect(url_for('admin.users'))


@admin_bp.route('/users/export')
@login_required
@role_required('admin')
def export_users():
    """导出全部用户为 CSV 文件。"""
    output = io.StringIO()
    output.write('﻿')  # UTF-8 BOM for Excel
    writer = csv.writer(output)
    writer.writerow(['用户名', '角色', '显示名称', '邮箱', '状态', '注册时间'])

    users_list = User.query.order_by(User.id).all()
    for u in users_list:
        writer.writerow([
            u.username,
            u.role,
            u.display_name or '',
            u.email or '',
            '正常' if u.is_active else '已禁用',
            u.created_at.strftime('%Y-%m-%d %H:%M:%S') if u.created_at else ''
        ])

    output.seek(0)
    return Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=users_export.csv'}
    )


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_user(user_id):
    """删除用户及其关联数据。"""
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('不能删除自己的账号。')
        return redirect(url_for('admin.users'))

    username = user.username
    # Delete related records
    Submission.query.filter_by(student_id=user_id).delete()
    SimilarityResult.query.filter_by(reviewed_by=user_id).update(
        {SimilarityResult.reviewed_by: None})
    AuditLog.query.filter_by(user_id=user_id).delete()
    Enrollment.query.filter_by(student_id=user_id).delete()
    db.session.delete(user)
    db.session.commit()
    flash(f'用户 "{username}" 及其相关数据已删除。')
    return redirect(url_for('admin.users'))


# ================================================================
# 审计日志
# ================================================================

@admin_bp.route('/logs')
@login_required
@role_required('admin')
def audit_logs():
    page = request.args.get('page', 1, type=int)
    action_filter = request.args.get('action', '').strip()
    user_search = request.args.get('user', '').strip()

    query = AuditLog.query
    if action_filter:
        query = query.filter_by(action=action_filter)
    if user_search:
        query = query.join(User).filter(
            db.or_(User.username.contains(user_search),
                   User.display_name.contains(user_search)))

    pagination = query.order_by(
        AuditLog.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False)

    # Distinct action types for filter dropdown
    actions = [r[0] for r in db.session.query(AuditLog.action).distinct().all()
               if r[0]]

    return render_template('admin/logs.html', logs=pagination.items,
                           pagination=pagination, action_filter=action_filter,
                           user_search=user_search, actions=actions)


# ================================================================
# 任务监控
# ================================================================

@admin_bp.route('/tasks')
@login_required
@role_required('admin')
def tasks():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '').strip()

    query = AnalysisTask.query
    if status_filter in ('pending', 'running', 'completed', 'failed'):
        query = query.filter_by(status=status_filter)

    pagination = query.order_by(AnalysisTask.created_at.desc()).paginate(
        page=page, per_page=30, error_out=False)

    return render_template('admin/tasks.html', tasks=pagination.items,
                           pagination=pagination, status_filter=status_filter)


@admin_bp.route('/tasks/<int:task_id>/retry', methods=['POST'])
@login_required
@role_required('admin')
def retry_task(task_id):
    """重试失败的分析任务。"""
    task = AnalysisTask.query.get_or_404(task_id)
    if task.status not in ('failed', 'completed'):
        flash('只能重试失败或已完成的任务。')
        return redirect(url_for('admin.tasks'))

    task.status = 'pending'
    task.processed_pairs = 0
    task.error_message = None
    task.started_at = None
    task.completed_at = None
    db.session.commit()
    flash(f'任务 #{task_id} 已重新加入队列。')
    return redirect(url_for('admin.tasks'))


@admin_bp.route('/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_task(task_id):
    """删除任务记录。"""
    task = AnalysisTask.query.get_or_404(task_id)
    task_id_copy = task.id
    db.session.delete(task)
    db.session.commit()
    flash(f'任务 #{task_id_copy} 已删除。')
    return redirect(url_for('admin.tasks'))


# ================================================================
# 数据备份
# ================================================================

def _backup_dir():
    path = os.path.join(current_app.instance_path, '..', 'backups')
    os.makedirs(path, exist_ok=True)
    return path


@admin_bp.route('/backup')
@login_required
@role_required('admin')
def backup():
    """备份管理页面。"""
    backup_dir = _backup_dir()
    files = []
    if os.path.exists(backup_dir):
        for f in sorted(os.listdir(backup_dir), reverse=True):
            fp = os.path.join(backup_dir, f)
            if os.path.isfile(fp):
                files.append({
                    'name': f,
                    'size_mb': round(os.path.getsize(fp) / (1024 * 1024), 2),
                    'mtime': datetime.fromtimestamp(os.path.getmtime(fp))
                })

    return render_template('admin/backup.html', files=files)


@admin_bp.route('/backup/create', methods=['POST'])
@login_required
@role_required('admin')
def create_backup():
    """创建数据库和上传文件的 ZIP 备份。"""
    try:
        backup_dir = _backup_dir()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        zip_name = f'backup_{timestamp}.zip'
        zip_path = os.path.join(backup_dir, zip_name)

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Backup SQLite database
            db_path = os.path.join(current_app.instance_path, 'app.db')
            if os.path.exists(db_path):
                zf.write(db_path, 'database/app.db')

            # Backup uploaded files
            upload_folder = current_app.config['UPLOAD_FOLDER']
            if os.path.exists(upload_folder):
                for dirpath, _, filenames in os.walk(upload_folder):
                    for fname in filenames:
                        fp = os.path.join(dirpath, fname)
                        arcname = 'uploads/' + os.path.relpath(fp, upload_folder)
                        zf.write(fp, arcname)

        zip_size = round(os.path.getsize(zip_path) / (1024 * 1024), 2)
        flash(f'备份已创建：{zip_name} ({zip_size} MB)')
    except Exception as e:
        flash(f'备份失败：{str(e)}')

    return redirect(url_for('admin.backup'))


@admin_bp.route('/backup/download/<filename>')
@login_required
@role_required('admin')
def download_backup(filename):
    """下载备份文件。"""
    backup_dir = _backup_dir()
    filepath = os.path.join(backup_dir, filename)
    if not os.path.isfile(filepath):
        flash('备份文件不存在。')
        return redirect(url_for('admin.backup'))

    return send_file(filepath, as_attachment=True, download_name=filename)


@admin_bp.route('/backup/delete/<filename>', methods=['POST'])
@login_required
@role_required('admin')
def delete_backup(filename):
    """删除备份文件。"""
    backup_dir = _backup_dir()
    filepath = os.path.join(backup_dir, filename)
    if os.path.isfile(filepath):
        os.remove(filepath)
        flash(f'备份 "{filename}" 已删除。')
    return redirect(url_for('admin.backup'))


# ================================================================
# 系统配置
# ================================================================

@admin_bp.route('/config', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def system_config():
    _seed_default_config()

    if request.method == 'POST':
        editable_keys = [
            'allowed_extensions', 'supported_languages',
            'similarity_threshold_default',
            'weight_jaccard', 'weight_tree_edit',
            'weight_semantic', 'weight_ngram',
            'max_concurrent_tasks', 'max_file_size_mb',
            'parser_timeout_seconds',
        ]
        for key in editable_keys:
            value = request.form.get(key, '').strip()
            if value:
                SystemConfig.set(key, value, updated_by=current_user.id)

        # Update Flask app config for current session
        try:
            thr = float(SystemConfig.get('similarity_threshold_default', '0.70'))
            current_app.config['SIMILARITY_THRESHOLD_DEFAULT'] = thr
        except ValueError:
            pass
        try:
            mfs = int(SystemConfig.get('max_file_size_mb', '2'))
            current_app.config['MAX_CONTENT_LENGTH'] = mfs * 1024 * 1024
        except ValueError:
            pass
        try:
            exts = set(SystemConfig.get('allowed_extensions', 'py,java,c,cpp,js').split(','))
            current_app.config['ALLOWED_EXTENSIONS'] = {e.strip() for e in exts if e.strip()}
        except Exception:
            pass

        flash('系统配置已更新。')
        return redirect(url_for('admin.system_config'))

    # Gather editable config values
    config_items = {}
    for item in SystemConfig.query.all():
        config_items[item.key] = {
            'value': item.value,
            'description': item.description or '',
            'updated_at': item.updated_at,
        }

    # Show static config info too
    static_config = {
        'SECRET_KEY': '*** (已设置)' if current_app.config.get('SECRET_KEY') else '未设置',
        'SQLALCHEMY_DATABASE_URI': _mask_db_url(
            current_app.config.get('SQLALCHEMY_DATABASE_URI', '')),
        'UPLOAD_FOLDER': current_app.config.get('UPLOAD_FOLDER', ''),
    }

    return render_template('admin/config.html',
                           config=config_items, static_config=static_config)


def _mask_db_url(url):
    if not url:
        return '未配置'
    if 'sqlite:///' in url:
        return url.replace('\\', '/')
    import re
    return re.sub(r'://[^:]+:[^@]+@', '://***:***@', url)


# ================================================================
# API
# ================================================================

@admin_bp.route('/api/stats')
@login_required
@role_required('admin')
def api_stats():
    from sqlalchemy import func

    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    daily_subs = db.session.query(
        func.date(Submission.submitted_at).label('date'),
        func.count(Submission.id).label('count')
    ).filter(Submission.submitted_at >= seven_days_ago) \
     .group_by(func.date(Submission.submitted_at)).all()

    all_results = SimilarityResult.query.all()
    bins = [0, 0, 0, 0, 0]
    for r in all_results:
        s = r.final_similarity
        if s < 0.2:
            bins[0] += 1
        elif s < 0.4:
            bins[1] += 1
        elif s < 0.6:
            bins[2] += 1
        elif s < 0.8:
            bins[3] += 1
        else:
            bins[4] += 1

    # Weekly submissions trend
    daily_labels = []
    daily_counts = []
    day_map = {}
    for d, c in daily_subs:
        day_map[str(d)] = c
    for i in range(6, -1, -1):
        day = (datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d')
        daily_labels.append(day[5:])  # MM-DD
        daily_counts.append(day_map.get(day, 0))

    return jsonify({
        'daily_submissions': [{'date': d, 'count': c} for d, c in daily_subs],
        'daily_labels': daily_labels,
        'daily_counts': daily_counts,
        'similarity_distribution': bins,
        'total_users': User.query.count(),
        'total_courses': Course.query.count(),
        'total_submissions': Submission.query.count(),
    })
