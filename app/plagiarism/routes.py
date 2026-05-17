import json
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from app import db
from app.models import (Assignment, Submission, SimilarityResult,
                         PlagiarismGroup, PlagiarismGroupMember,
                         AnalysisTask, AuditLog)
from app.utils.decorators import role_required
from app.plagiarism.ast_parser import extract_features
from app.plagiarism.similarity import compute_similarity, batch_compare
from app.plagiarism.code_analyzer import analyze_code

plagiarism_bp = Blueprint('plagiarism', __name__)


@plagiarism_bp.route('/')
@login_required
def index():
    """查重任务列表（教师看自己课程的查重记录）。"""
    if current_user.role == 'teacher':
        from app.models import Course
        course_ids = [c.id for c in Course.query.filter_by(
            teacher_id=current_user.id).all()]
        assignments = Assignment.query.filter(
            Assignment.course_id.in_(course_ids)
        ).order_by(Assignment.created_at.desc()).all() if course_ids else []
    elif current_user.role == 'admin':
        assignments = Assignment.query.order_by(
            Assignment.created_at.desc()).all()
    else:
        from app.models import Course
        enrolled_ids = [e.course_id for e in current_user.enrollments.all()]
        assignments = Assignment.query.filter(
            Assignment.course_id.in_(enrolled_ids)
        ).order_by(Assignment.created_at.desc()).all() if enrolled_ids else []

    # Attach analysis task status
    for a in assignments:
        a._latest_task = a.analysis_tasks.order_by(
            AnalysisTask.created_at.desc()).first()

    return render_template('plagiarism/index.html', assignments=assignments)


@plagiarism_bp.route('/run/<int:assignment_id>', methods=['POST'])
@login_required
@role_required('teacher', 'admin')
def run_analysis(assignment_id):
    """启动查重分析（同步执行，适合小规模）。"""
    assignment = Assignment.query.get_or_404(assignment_id)
    submissions = assignment.submissions.order_by(
        Submission.submitted_at.asc()).all()

    if len(submissions) < 2:
        flash('至少需要 2 份提交才能进行查重。')
        return redirect(url_for('plagiarism.index'))

    # Create task record
    task = AnalysisTask(
        assignment_id=assignment.id,
        status='running',
        total_pairs=len(submissions) * (len(submissions) - 1) // 2,
        started_at=datetime.utcnow()
    )
    db.session.add(task)
    db.session.commit()

    try:
        # 1. Parse all submissions
        parsed = []
        for sub in submissions:
            try:
                features = extract_features(sub.file_path, sub.language or 'python')
                sub.ast_data = features
                parsed.append((sub.id, features))
            except Exception as e:
                print(f'[WARN] Failed to parse submission {sub.id}: {e}')
                continue

        if len(parsed) < 2:
            task.status = 'failed'
            task.error_message = '可解析的提交不足 2 份。'
            db.session.commit()
            flash('解析失败：有效的代码文件不足 2 份。')
            return redirect(url_for('plagiarism.index'))

        # 2. Delete old results
        SimilarityResult.query.filter_by(assignment_id=assignment.id).delete()
        PlagiarismGroupMember.query.filter(
            PlagiarismGroupMember.group_id.in_(
                db.session.query(PlagiarismGroup.id).filter_by(
                    assignment_id=assignment.id)
            )
        ).delete(synchronize_session='fetch')
        PlagiarismGroup.query.filter_by(assignment_id=assignment.id).delete()

        # 3. Batch compare
        threshold = assignment.similarity_threshold or 0.70
        results = batch_compare(parsed, threshold=threshold)

        # 4. Store results
        stored_count = 0
        suspicious_subs = set()
        for id_a, id_b, scores in results:
            sim = SimilarityResult(
                assignment_id=assignment.id,
                submission_a_id=id_a,
                submission_b_id=id_b,
                jaccard_similarity=scores['jaccard'],
                tree_edit_similarity=scores['tree_edit'],
                ngram_similarity=scores['ngram'],
                final_similarity=scores['final'],
            )
            db.session.add(sim)
            suspicious_subs.add(id_a)
            suspicious_subs.add(id_b)
            stored_count += 1

        # 5. Group suspicious submissions
        if suspicious_subs:
            group = PlagiarismGroup(
                assignment_id=assignment.id,
                label=f'疑似抄袭组 - {assignment.title[:20]}'
            )
            db.session.add(group)
            db.session.flush()

            # Mark earliest submission as potential original
            earliest_sub = min(
                suspicious_subs,
                key=lambda sid: next(s.submitted_at for s in submissions if s.id == sid)
            )
            for sub_id in suspicious_subs:
                member = PlagiarismGroupMember(
                    group_id=group.id,
                    submission_id=sub_id,
                    is_original=(sub_id == earliest_sub)
                )
                db.session.add(member)

        # 6. Update task
        task.status = 'completed'
        task.processed_pairs = len(parsed) * (len(parsed) - 1) // 2
        task.completed_at = datetime.utcnow()
        db.session.commit()

        flash(f'查重完成！共比对 {task.total_pairs} 对，发现 {stored_count} 对疑似相似。')

    except Exception as e:
        db.session.rollback()
        task.status = 'failed'
        task.error_message = str(e)
        db.session.commit()
        flash(f'查重执行出错：{e}')

    return redirect(url_for('plagiarism.report', assignment_id=assignment.id))


@plagiarism_bp.route('/report/<int:assignment_id>')
@login_required
def report(assignment_id):
    """查看某次作业的查重报告。"""
    assignment = Assignment.query.get_or_404(assignment_id)

    # Get similarity results
    sim_results = assignment.similarity_results.order_by(
        SimilarityResult.final_similarity.desc()).all()

    # Get plagiarism groups
    groups = assignment.plagiarism_groups.all()

    # Get latest analysis task
    task = assignment.analysis_tasks.order_by(
        AnalysisTask.created_at.desc()).first()

    # Build data for heatmap
    submissions = assignment.submissions.order_by(
        Submission.submitted_at.asc()).all()
    labels = [s.student.username for s in submissions]
    heatmap_data = []
    sim_map = {}
    for r in sim_results:
        idx_a = next(i for i, s in enumerate(submissions) if s.id == r.submission_a_id)
        idx_b = next(i for i, s in enumerate(submissions) if s.id == r.submission_b_id)
        heatmap_data.append([idx_a, idx_b, round(r.final_similarity, 2)])
        heatmap_data.append([idx_b, idx_a, round(r.final_similarity, 2)])
        sim_map[(r.submission_a_id, r.submission_b_id)] = r
        sim_map[(r.submission_b_id, r.submission_a_id)] = r

    return render_template('plagiarism/report.html',
                           assignment=assignment,
                           sim_results=sim_results,
                           groups=groups,
                           task=task,
                           submissions=submissions,
                           labels=json.dumps(labels),
                           heatmap_data=json.dumps(heatmap_data),
                           sim_map=sim_map)


@plagiarism_bp.route('/compare/<int:result_id>')
@login_required
def compare_code(result_id):
    """双栏代码对比视图。"""
    sim = SimilarityResult.query.get_or_404(result_id)

    # Read source code from both submissions
    def read_code(submission):
        try:
            with open(submission.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception:
            return '[无法读取文件]'

    code_a = read_code(sim.submission_a)
    code_b = read_code(sim.submission_b)

    # Log audit
    log = AuditLog(
        user_id=current_user.id,
        action='view_code_compare',
        target_type='similarity_result',
        target_id=result_id,
        ip_address=request.remote_addr,
        detail=f'compare {sim.submission_a_id} vs {sim.submission_b_id}'
    )
    db.session.add(log)
    db.session.commit()

    return render_template('plagiarism/compare.html', sim=sim,
                           code_a=code_a, code_b=code_b)


@plagiarism_bp.route('/review/<int:result_id>', methods=['POST'])
@login_required
@role_required('teacher', 'admin')
def review(result_id):
    """教师人工复核标注。"""
    sim = SimilarityResult.query.get_or_404(result_id)
    action = request.form.get('action')  # confirm / clear / false_positive

    if action == 'confirm':
        sim.is_plagiarism = True
    elif action == 'clear':
        sim.is_plagiarism = False
    else:
        flash('无效的复核操作。')
        return redirect(request.referrer or url_for('plagiarism.index'))

    sim.reviewed_by = current_user.id
    sim.reviewed_at = datetime.utcnow()
    db.session.commit()

    flash('复核结果已保存。')
    return redirect(url_for('plagiarism.report',
                            assignment_id=sim.assignment_id))


@plagiarism_bp.route('/api/graph/<int:assignment_id>')
@login_required
def api_graph_data(assignment_id):
    """API: 返回图谱数据（供 ECharts 渲染）。"""
    assignment = Assignment.query.get_or_404(assignment_id)
    submissions = assignment.submissions.all()
    results = assignment.similarity_results.filter(
        SimilarityResult.final_similarity >= (assignment.similarity_threshold or 0.70)
    ).all()

    nodes = []
    for s in submissions:
        nodes.append({
            'id': s.id,
            'name': s.student.display_name or s.student.username,
            'symbolSize': 30,
        })

    links = []
    for r in results:
        links.append({
            'source': r.submission_a_id,
            'target': r.submission_b_id,
            'value': round(r.final_similarity, 2),
        })

    return jsonify({'nodes': nodes, 'links': links})


# ================================================================
# 学生端：学习辅助
# ================================================================

@plagiarism_bp.route('/my-report')
@login_required
@role_required('student')
def my_report():
    """学生个人学习报告 —— 历史相似度趋势 + 代码质量得分。"""
    submissions = current_user.submissions.order_by(
        Submission.submitted_at.desc()).all()

    # Analyze each submission
    analyzed = []
    for sub in submissions:
        try:
            report = analyze_code(sub.file_path, sub.language or 'python')
        except Exception:
            report = {'score': None, 'grade': 'N/A', 'issues': [], 'suggestions': []}
        analyzed.append({
            'submission': sub,
            'report': report,
        })

    # Get similarity results involving this student
    from sqlalchemy import or_
    sim_results = SimilarityResult.query.filter(
        or_(
            SimilarityResult.submission_a_id.in_([s.id for s in submissions]),
            SimilarityResult.submission_b_id.in_([s.id for s in submissions]),
        )
    ).order_by(SimilarityResult.final_similarity.desc()).all()

    # Trend data for chart
    dates = []
    scores = []
    sim_trends = []
    for sub in sorted(submissions, key=lambda s: s.submitted_at):
        dates.append(sub.submitted_at.strftime('%m-%d'))
        # Get quality score
        try:
            r = analyze_code(sub.file_path, sub.language or 'python')
            scores.append(r['score'])
        except Exception:
            scores.append(0)
        # Get max similarity for this submission
        max_sim = 0
        for sr in sim_results:
            if sr.submission_a_id == sub.id or sr.submission_b_id == sub.id:
                max_sim = max(max_sim, sr.final_similarity)
        sim_trends.append(round(max_sim * 100, 1))

    return render_template('plagiarism/student_report.html',
                           analyzed=analyzed,
                           submissions=submissions,
                           sim_results=sim_results,
                           dates=json.dumps(dates),
                           scores=json.dumps(scores),
                           sim_trends=json.dumps(sim_trends))


@plagiarism_bp.route('/code-review/<int:submission_id>')
@login_required
def code_review(submission_id):
    """代码质量详细审查报告。"""
    sub = Submission.query.get_or_404(submission_id)

    # Permission: student can only see own, teacher/admin can see all
    if current_user.role == 'student' and sub.student_id != current_user.id:
        flash('无权查看此报告。')
        return redirect(url_for('plagiarism.my_report'))

    try:
        report = analyze_code(sub.file_path, sub.language or 'python')
    except Exception as e:
        flash(f'代码分析失败：{e}')
        return redirect(request.referrer or url_for('plagiarism.index'))

    # Get similar submissions for context
    sim_pairs = SimilarityResult.query.filter(
        (SimilarityResult.submission_a_id == submission_id) |
        (SimilarityResult.submission_b_id == submission_id)
    ).order_by(SimilarityResult.final_similarity.desc()).all()

    try:
        with open(sub.file_path, 'r', encoding='utf-8', errors='ignore') as f:
            source_code = f.read()
    except Exception:
        source_code = '[无法读取]'

    return render_template('plagiarism/code_review.html',
                           submission=sub,
                           report=report,
                           sim_pairs=sim_pairs,
                           source_code=source_code)
