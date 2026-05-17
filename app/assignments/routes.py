import os
import uuid
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user

from app import db
from app.models import Assignment, Course, Submission, SubmissionVersion
from app.utils.decorators import role_required

assignments_bp = Blueprint('assignments', __name__)


ALLOWED_EXTENSIONS = {'py', 'java', 'c', 'cpp', 'js'}
EXT_TO_LANG = {
    'py': 'python', 'java': 'java', 'c': 'c',
    'cpp': 'cpp', 'js': 'javascript'
}


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@assignments_bp.route('/')
@login_required
def index():
    """Show assignments based on role."""
    if current_user.role == 'student':
        enrolled_ids = [e.course_id for e in current_user.enrollments.all()]
        assignments = Assignment.query.filter(
            Assignment.course_id.in_(enrolled_ids)
        ).order_by(Assignment.due_date.asc()).all() if enrolled_ids else []
    else:
        teach_ids = [c.id for c in Course.query.filter_by(
            teacher_id=current_user.id).all()]
        assignments = Assignment.query.filter(
            Assignment.course_id.in_(teach_ids)
        ).order_by(Assignment.due_date.asc()).all() if teach_ids else []
    return render_template('assignments/index.html', assignments=assignments)


@assignments_bp.route('/<int:assignment_id>')
@login_required
def detail(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    course = Course.query.get(assignment.course_id)

    if current_user.role == 'teacher' or current_user.role == 'admin':
        submissions = assignment.submissions.order_by(
            Submission.submitted_at.desc()).all()
    else:
        submissions = assignment.submissions.filter_by(
            student_id=current_user.id).all()

    my_submission = None
    if current_user.role == 'student':
        my_submission = assignment.submissions.filter_by(
            student_id=current_user.id).order_by(
            Submission.submitted_at.desc()).first()

    return render_template('assignments/detail.html',
                           assignment=assignment, course=course,
                           submissions=submissions, my_submission=my_submission)


@assignments_bp.route('/<int:assignment_id>/submit', methods=['POST'])
@login_required
@role_required('student')
def submit(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)

    if 'file' not in request.files:
        flash('请选择要上传的文件。')
        return redirect(url_for('assignments.detail', assignment_id=assignment.id))

    file = request.files['file']
    if file.filename == '':
        flash('请选择要上传的文件。')
        return redirect(url_for('assignments.detail', assignment_id=assignment.id))

    if not _allowed_file(file.filename):
        flash('不支持的文件类型。允许的类型：py, java, c, cpp, js')
        return redirect(url_for('assignments.detail', assignment_id=assignment.id))

    ext = file.filename.rsplit('.', 1)[1].lower()
    language = EXT_TO_LANG.get(ext, ext)

    # Build upload path: uploads/<course_id>/<assignment_id>/<user_id>/
    upload_dir = os.path.join(
        current_app.config['UPLOAD_FOLDER'],
        str(assignment.course_id),
        str(assignment.id),
        str(current_user.id)
    )
    os.makedirs(upload_dir, exist_ok=True)

    # Generate unique filename
    unique_name = f"{uuid.uuid4().hex[:12]}_{file.filename}"
    file_path = os.path.join(upload_dir, unique_name)
    file.save(file_path)

    # Check if user already has a submission for this assignment
    existing = assignment.submissions.filter_by(
        student_id=current_user.id).order_by(
        Submission.submitted_at.desc()).first()

    if existing:
        # Save old version
        version = SubmissionVersion(
            submission_id=existing.id,
            file_path=existing.file_path,
            file_name=existing.file_name
        )
        db.session.add(version)

        # Update existing submission
        existing.file_path = file_path
        existing.file_name = file.filename
        existing.file_size = os.path.getsize(file_path)
        existing.language = language
        existing.submitted_at = datetime.utcnow()
        existing.is_late = datetime.utcnow() > assignment.due_date
        existing.version += 1
        db.session.commit()
        flash(f'代码已重新提交（版本 {existing.version}）。')
    else:
        submission = Submission(
            assignment_id=assignment.id,
            student_id=current_user.id,
            file_path=file_path,
            file_name=file.filename,
            file_size=os.path.getsize(file_path),
            language=language,
            submitted_at=datetime.utcnow(),
            is_late=datetime.utcnow() > assignment.due_date
        )
        db.session.add(submission)
        db.session.commit()
        flash('代码提交成功！')

    return redirect(url_for('assignments.detail', assignment_id=assignment.id))


@assignments_bp.route('/create/<int:course_id>', methods=['GET', 'POST'])
@login_required
@role_required('teacher', 'admin')
def create(course_id):
    course = Course.query.get_or_404(course_id)

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        due_date_str = request.form.get('due_date', '').strip()
        allowed_ext = request.form.get('allowed_extensions', 'py,java,c,cpp')
        threshold = float(request.form.get('similarity_threshold', 0.70))

        if not title or not due_date_str:
            flash('作业标题和截止日期不能为空。')
            return render_template('assignments/create.html', course=course)

        from datetime import datetime
        due_date = datetime.strptime(due_date_str, '%Y-%m-%dT%H:%M')

        assignment = Assignment(
            course_id=course.id,
            title=title,
            description=description,
            due_date=due_date,
            allowed_extensions=allowed_ext,
            similarity_threshold=threshold
        )
        db.session.add(assignment)
        db.session.commit()
        flash(f'作业 "{title}" 创建成功！')
        return redirect(url_for('courses.detail', course_id=course.id))

    return render_template('assignments/create.html', course=course)
