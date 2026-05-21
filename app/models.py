import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db


# ============================================================
# 用户与权限
# ============================================================

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(16), nullable=False, default='student')  # student / teacher / admin
    email = db.Column(db.String(128), unique=True)
    display_name = db.Column(db.String(64))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    # Relationships
    courses_teaching = db.relationship('Course', backref='teacher', lazy='dynamic')
    enrollments = db.relationship('Enrollment', backref='student', lazy='dynamic')
    submissions = db.relationship('Submission', backref='student', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username} [{self.role}]>'


# ============================================================
# 课程与班级
# ============================================================

class Course(db.Model):
    __tablename__ = 'courses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    invite_code = db.Column(db.String(16), unique=True, nullable=False, index=True)
    semester = db.Column(db.String(32))
    description = db.Column(db.Text)
    is_archived = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    # Relationships
    enrollments = db.relationship('Enrollment', backref='course', lazy='dynamic')
    assignments = db.relationship('Assignment', backref='course', lazy='dynamic')

    def __repr__(self):
        return f'<Course {self.name} ({self.semester})>'


class Enrollment(db.Model):
    __tablename__ = 'enrollments'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('student_id', 'course_id', name='uq_student_course'),
    )

    def __repr__(self):
        return f'<Enrollment student={self.student_id} course={self.course_id}>'


# ============================================================
# 作业与提交
# ============================================================

class Assignment(db.Model):
    __tablename__ = 'assignments'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    title = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)
    due_date = db.Column(db.DateTime, nullable=False)
    allowed_extensions = db.Column(db.String(128), default='py,java,c,cpp,js')
    similarity_threshold = db.Column(db.Float, default=0.70)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    # Relationships
    submissions = db.relationship('Submission', backref='assignment', lazy='dynamic')
    similarity_results = db.relationship('SimilarityResult', backref='assignment', lazy='dynamic')
    plagiarism_groups = db.relationship('PlagiarismGroup', backref='assignment', lazy='dynamic')
    analysis_tasks = db.relationship('AnalysisTask', backref='assignment', lazy='dynamic')

    def __repr__(self):
        return f'<Assignment {self.title}>'


class Submission(db.Model):
    __tablename__ = 'submissions'

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    file_name = db.Column(db.String(256), nullable=False)
    file_size = db.Column(db.Integer)  # bytes
    language = db.Column(db.String(16))
    ast_data = db.Column(db.JSON)  # normalized AST fingerprint data
    submitted_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    is_late = db.Column(db.Boolean, default=False)
    version = db.Column(db.Integer, default=1)

    # Relationships
    versions = db.relationship('SubmissionVersion', backref='submission', lazy='dynamic',
                               order_by='SubmissionVersion.uploaded_at')

    def __repr__(self):
        return f'<Submission {self.file_name} by student={self.student_id}>'


class SubmissionVersion(db.Model):
    """Historical versions of a submission (for resubmission tracking)."""
    __tablename__ = 'submission_versions'

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('submissions.id'), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    file_name = db.Column(db.String(256), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        return f'<SubmissionVersion submission={self.submission_id} v{self.id}>'


# ============================================================
# 查重结果
# ============================================================

class SimilarityResult(db.Model):
    __tablename__ = 'similarity_results'

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id'), nullable=False)
    submission_a_id = db.Column(db.Integer, db.ForeignKey('submissions.id'), nullable=False)
    submission_b_id = db.Column(db.Integer, db.ForeignKey('submissions.id'), nullable=False)

    # Multi-dimensional similarity scores
    jaccard_similarity = db.Column(db.Float)
    tree_edit_similarity = db.Column(db.Float)
    semantic_hash_similarity = db.Column(db.Float)
    ngram_similarity = db.Column(db.Float)
    final_similarity = db.Column(db.Float, nullable=False, index=True)

    # Manual review
    is_plagiarism = db.Column(db.Boolean, default=None)  # None=unreviewed, True=confirmed, False=cleared
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    # Relationships for manual review access
    submission_a = db.relationship('Submission', foreign_keys=[submission_a_id])
    submission_b = db.relationship('Submission', foreign_keys=[submission_b_id])
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])

    __table_args__ = (
        db.UniqueConstraint('assignment_id', 'submission_a_id', 'submission_b_id',
                            name='uq_pair'),
        db.CheckConstraint('submission_a_id < submission_b_id',
                           name='ck_ordered_pair'),
    )

    def __repr__(self):
        return f'<SimilarityResult {self.submission_a_id} vs {self.submission_b_id} = {self.final_similarity:.2%}>'


class PlagiarismGroup(db.Model):
    """Group of submissions identified as suspiciously similar."""
    __tablename__ = 'plagiarism_groups'

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id'), nullable=False)
    label = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    members = db.relationship('PlagiarismGroupMember', backref='group', lazy='dynamic')

    def __repr__(self):
        return f'<PlagiarismGroup {self.label}>'


class PlagiarismGroupMember(db.Model):
    __tablename__ = 'plagiarism_group_members'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('plagiarism_groups.id'), nullable=False)
    submission_id = db.Column(db.Integer, db.ForeignKey('submissions.id'), nullable=False)
    is_original = db.Column(db.Boolean, default=False)

    submission = db.relationship('Submission')

    __table_args__ = (
        db.UniqueConstraint('group_id', 'submission_id', name='uq_group_member'),
    )

    def __repr__(self):
        return f'<PlagiarismGroupMember group={self.group_id} sub={self.submission_id}>'


class CodeFragment(db.Model):
    """Similar code fragments extracted during AST comparison."""
    __tablename__ = 'code_fragments'

    id = db.Column(db.Integer, primary_key=True)
    similarity_result_id = db.Column(db.Integer, db.ForeignKey('similarity_results.id'), nullable=False)
    source_start_line = db.Column(db.Integer)
    source_end_line = db.Column(db.Integer)
    target_start_line = db.Column(db.Integer)
    target_end_line = db.Column(db.Integer)
    similarity = db.Column(db.Float)

    similarity_result = db.relationship('SimilarityResult', backref='fragments')


# ============================================================
# 异步分析任务
# ============================================================

class AnalysisTask(db.Model):
    __tablename__ = 'analysis_tasks'

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id'), nullable=False)
    status = db.Column(db.String(16), default='pending')  # pending / running / completed / failed
    total_pairs = db.Column(db.Integer, default=0)
    processed_pairs = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def progress_pct(self):
        if self.total_pairs == 0:
            return 0
        return round(self.processed_pairs / self.total_pairs * 100, 1)

    def __repr__(self):
        return f'<AnalysisTask assignment={self.assignment_id} [{self.status}]>'


# ============================================================
# 系统配置（管理员可编辑）
# ============================================================

class SystemConfig(db.Model):
    __tablename__ = 'system_config'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=False)
    description = db.Column(db.String(256))
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    updater = db.relationship('User')

    @staticmethod
    def get(key, default=None):
        entry = SystemConfig.query.filter_by(key=key).first()
        return entry.value if entry else default

    @staticmethod
    def set(key, value, description=None, updated_by=None):
        entry = SystemConfig.query.filter_by(key=key).first()
        if entry:
            entry.value = str(value)
            entry.updated_at = datetime.datetime.utcnow()
            if updated_by:
                entry.updated_by = updated_by
            if description:
                entry.description = description
        else:
            entry = SystemConfig(key=key, value=str(value),
                                 description=description, updated_by=updated_by)
            db.session.add(entry)
        db.session.commit()
        return entry

    def __repr__(self):
        return f'<SystemConfig {self.key}={self.value}>'


# ============================================================
# 审计日志
# ============================================================

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(64), nullable=False)  # e.g. view_report, view_code, export_report
    target_type = db.Column(db.String(32))              # e.g. submission, similarity_result
    target_id = db.Column(db.Integer)
    ip_address = db.Column(db.String(45))
    detail = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    user = db.relationship('User', backref='audit_logs')

    def __repr__(self):
        return f'<AuditLog {self.action} by user={self.user_id}>'
