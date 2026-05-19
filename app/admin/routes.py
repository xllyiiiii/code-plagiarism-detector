import json
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user

from app import db
from app.models import User, Course, Assignment, Submission, SimilarityResult, AuditLog, PlagiarismGroup
from app.utils.decorators import role_required

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/')
@login_required
@role_required('admin')
def index():
    """管理后台首页 —— 系统概览。"""
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

    # Recent audit logs
    recent_logs = AuditLog.query.order_by(
        AuditLog.created_at.desc()).limit(20).all()

    # Storage estimate
    import os
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
    """用户列表。"""
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=all_users)


@admin_bp.route('/users/create', methods=['POST'])
@login_required
@role_required('admin')
def create_user():
    """管理员创建用户（教师账号）。"""
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
    """启用/禁用用户。"""
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('不能操作自己的账号。')
        return redirect(url_for('admin.users'))

    user.is_active = not getattr(user, 'is_active', True)
    db.session.commit()
    state = '已启用' if user.is_active else '已禁用'
    flash(f'用户 "{user.username}" {state}。')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@role_required('admin')
def reset_password(user_id):
    """重置用户密码。"""
    user = User.query.get_or_404(user_id)
    new_password = request.form.get('new_password', '').strip()
    if not new_password or len(new_password) < 6:
        flash('密码长度至少 6 位。')
        return redirect(url_for('admin.users'))

    user.set_password(new_password)
    db.session.commit()
    flash(f'用户 "{user.username}" 的密码已重置。')
    return redirect(url_for('admin.users'))


# ================================================================
# 审计日志
# ================================================================

@admin_bp.route('/logs')
@login_required
@role_required('admin')
def audit_logs():
    """查看审计日志。"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    pagination = AuditLog.query.order_by(
        AuditLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    return render_template('admin/logs.html', logs=pagination.items,
                           pagination=pagination)


# ================================================================
# 系统配置
# ================================================================

@admin_bp.route('/config')
@login_required
@role_required('admin')
def system_config():
    """系统配置页面。"""
    config_info = {
        'SECRET_KEY': '*** (已设置)' if current_app.config.get('SECRET_KEY') else '未设置',
        'SQLALCHEMY_DATABASE_URI': _mask_db_url(current_app.config.get('SQLALCHEMY_DATABASE_URI', '')),
        'UPLOAD_FOLDER': current_app.config.get('UPLOAD_FOLDER', ''),
        'MAX_CONTENT_LENGTH': f'{current_app.config.get("MAX_CONTENT_LENGTH", 0) // (1024*1024)} MB',
        'ALLOWED_EXTENSIONS': ', '.join(current_app.config.get('ALLOWED_EXTENSIONS', set())),
        'SIMILARITY_THRESHOLD_DEFAULT': current_app.config.get('SIMILARITY_THRESHOLD_DEFAULT', 0.70),
    }
    return render_template('admin/config.html', config=config_info)


def _mask_db_url(url):
    """Mask sensitive info in database URL."""
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
    """返回系统统计数据 JSON。"""
    import os
    from sqlalchemy import func

    # Submission trend (last 7 days)
    seven_days_ago = datetime.utcnow() - __import__('datetime').timedelta(days=7)
    daily_subs = db.session.query(
        func.date(Submission.submitted_at).label('date'),
        func.count(Submission.id).label('count')
    ).filter(Submission.submitted_at >= seven_days_ago) \
     .group_by(func.date(Submission.submitted_at)).all()

    # Similarity distribution across all assignments
    all_results = SimilarityResult.query.all()
    bins = [0, 0, 0, 0, 0]  # 0-20, 20-40, 40-60, 60-80, 80-100
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

    return {
        'daily_submissions': [{'date': str(d), 'count': c} for d, c in daily_subs],
        'similarity_distribution': bins,
        'total_users': User.query.count(),
        'total_courses': Course.query.count(),
        'total_submissions': Submission.query.count(),
    }
