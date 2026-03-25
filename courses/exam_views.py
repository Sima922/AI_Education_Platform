# courses/exam_views.py
import logging
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, Http404
from django.db import transaction
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.core.exceptions import PermissionDenied
from django.conf import settings

from .models import (
    Course, Enrollment, CourseExam, ExamSession, ExamQuestion, 
    ExamAnswer, ProctorLog, ExamResult, UserProgress, Chapter
)
from .forms import ExamConfigurationForm, ExamPreflightForm, ExamReviewForm, ExamFeedbackForm
from .ai_integration.ai_module import (
    generate_comprehensive_exam, analyze_exam_responses, 
    detect_cheating_patterns, generate_certificate_content
)
from .utils import calculate_exam_score, generate_certificate_pdf

logger = logging.getLogger(__name__)

@login_required
def configure_exam_settings(request, course_id):
    """
    Configure exam settings during course creation
    """
    course = get_object_or_404(Course, id=course_id)
    
    # Check permission
    if course.creator != request.user:
        raise PermissionDenied("You don't have permission to configure this exam")
    
    exam, created = CourseExam.objects.get_or_create(course=course)
    
    if request.method == 'POST':
        form = ExamConfigurationForm(request.POST, request.FILES, instance=exam)
        if form.is_valid():
            exam = form.save(commit=False)
            
            # If exam is enabled, generate it
            if exam.is_enabled:
                try:
                    # Generate exam using AI
                    exam_structure = generate_comprehensive_exam(
                        course_content=course.content,
                        prompt=exam.prompt,
                        template_file=exam.template_file
                    )
                    exam.structure = exam_structure
                    exam.save()
                    
                    # Create exam questions
                    for i, question_data in enumerate(exam_structure.get('questions', [])):
                        ExamQuestion.objects.create(
                            exam=exam,
                            question_type=question_data['type'],
                            question_text=question_data['question'],
                            options=question_data.get('options'),
                            correct_answer=question_data.get('correct_answer'),
                            points=question_data.get('points', 1),
                            order=i
                        )
                    
                    messages.success(request, "Exam generated successfully!")
                except Exception as e:
                    logger.error(f"Error generating exam: {e}")
                    messages.error(request, f"Error generating exam: {str(e)}")
                    exam.is_enabled = False
                    exam.save()
            else:
                exam.save()
                messages.success(request, "Exam settings updated")
            
            return redirect('courses:preview_course', draft_id=request.session.get('editing_draft_id'))
    else:
        form = ExamConfigurationForm(instance=exam)
    
    return render(request, 'exams/exam_configuration.html', {
        'form': form,
        'course': course,
        'exam': exam
    })

@login_required
def exam_eligibility_check(request, course_id):
    """
    Check if user is eligible to take the exam
    """
    course = get_object_or_404(Course, id=course_id)
    enrollment = get_object_or_404(Enrollment, user=request.user, course=course)
    
    # Check if course has an exam
    if not hasattr(course, 'exam') or not course.exam.is_enabled:
        messages.error(request, "This course doesn't have an exam")
        return redirect('courses:view_course', pk=course_id)
    
    # Check if user has completed the course
    chapters = Chapter.objects.filter(course=course)
    completed_chapters = UserProgress.objects.filter(
        user=request.user, 
        course=course, 
        chapter_completed=True
    ).count()
    
    if completed_chapters < chapters.count():
        messages.error(request, "You must complete all chapters before taking the exam")
        return redirect('courses:view_course', pk=course_id)
    
    # Check attempt limits
    exam = course.exam
    previous_attempts = ExamSession.objects.filter(
        user=request.user, 
        exam=exam
    ).count()
    
    if previous_attempts >= exam.max_attempts:
        messages.error(request, "You've reached the maximum number of exam attempts")
        return redirect('courses:view_course', pk=course_id)
    
    # Mark user as eligible for exam
    enrollment.exam_eligible = True
    enrollment.save()
    
    return redirect('courses:exam_preflight', course_id=course_id)

@login_required
def exam_preflight_check(request, course_id):
    """
    Pre-exam verification and agreement
    """
    course = get_object_or_404(Course, id=course_id)
    enrollment = get_object_or_404(Enrollment, user=request.user, course=course)
    
    if not enrollment.exam_eligible:
        messages.error(request, "You're not eligible to take this exam")
        return redirect('courses:view_course', pk=course_id)
    
    if request.method == 'POST':
        form = ExamPreflightForm(request.POST)
        if form.is_valid():
            # Store preflight data in session
            request.session['exam_preflight'] = {
                'full_name': form.cleaned_data['full_name'],
                'agree_terms': form.cleaned_data['agree_terms'],
                'agree_proctoring': form.cleaned_data['agree_proctoring'],
                'confirm_ready': form.cleaned_data['confirm_ready']
            }
            return redirect('courses:start_exam', course_id=course_id)
    else:
        form = ExamPreflightForm()
    
    return render(request, 'exams/exam_preflight.html', {
        'form': form,
        'course': course
    })

@login_required
def start_exam_session(request, course_id):
    """
    Start a new exam session
    """
    course = get_object_or_404(Course, id=course_id)
    enrollment = get_object_or_404(Enrollment, user=request.user, course=course)
    
    if not enrollment.exam_eligible:
        messages.error(request, "You're not eligible to take this exam")
        return redirect('courses:view_course', pk=course_id)
    
    # Check if preflight data exists
    preflight_data = request.session.get('exam_preflight')
    if not preflight_data:
        return redirect('courses:exam_preflight', course_id=course_id)
    
    # Create exam session
    exam = course.exam
    session = ExamSession.objects.create(
        user=request.user,
        exam=exam,
        started_at=timezone.now(),
        status='in_progress'
    )
    
    # Clear preflight data from session
    if 'exam_preflight' in request.session:
        del request.session['exam_preflight']
    
    return redirect('courses:exam_interface', session_id=session.id)

@login_required
def exam_interface(request, session_id):
    """
    Exam interface with view-once protection
    """
    session = get_object_or_404(ExamSession, id=session_id, user=request.user)
    
    if session.status != 'in_progress':
        messages.error(request, "This exam session is not active")
        return redirect('courses:view_course', pk=session.exam.course.id)
    
    # Check if exam time has expired
    time_elapsed = (timezone.now() - session.started_at).total_seconds()
    time_limit_seconds = session.exam.time_limit_minutes * 60
    
    if time_elapsed > time_limit_seconds:
        session.status = 'submitted'
        session.ended_at = timezone.now()
        session.time_spent_seconds = time_limit_seconds
        session.save()
        messages.error(request, "Exam time has expired")
        return redirect('courses:exam_results', session_id=session.id)
    
    # Get exam questions
    questions = session.exam.questions.all().order_by('order')
    
    return render(request, 'exams/exam_interface.html', {
        'session': session,
        'questions': questions,
        'time_limit_seconds': time_limit_seconds,
        'time_elapsed': int(time_elapsed),
        'time_remaining': int(time_limit_seconds - time_elapsed)
    })

@login_required
@require_http_methods(["POST"])
def submit_exam(request, session_id):
    """
    Submit exam answers
    """
    session = get_object_or_404(ExamSession, id=session_id, user=request.user)
    
    if session.status != 'in_progress':
        return JsonResponse({'error': 'Exam already submitted'}, status=400)
    
    try:
        data = json.loads(request.body)
        answers = data.get('answers', {})
        
        # Save answers
        for question_id, answer_text in answers.items():
            question = get_object_or_404(ExamQuestion, id=question_id, exam=session.exam)
            ExamAnswer.objects.create(
                session=session,
                question=question,
                answer_text=answer_text
            )
        
        # Update session
        session.status = 'submitted'
        session.ended_at = timezone.now()
        session.time_spent_seconds = (session.ended_at - session.started_at).total_seconds()
        session.save()
        
        # Process exam (AI grading and cheating detection)
        process_exam_results.delay(session.id)
        
        return JsonResponse({'status': 'success', 'redirect_url': reverse('courses:exam_results', args=[session.id])})
    
    except Exception as e:
        logger.error(f"Error submitting exam: {e}")
        return JsonResponse({'error': 'Error submitting exam'}, status=500)

@login_required
def exam_results(request, session_id):
    """
    View exam results
    """
    session = get_object_or_404(ExamSession, id=session_id, user=request.user)
    
    # Check if results are available
    if not hasattr(session, 'result'):
        return render(request, 'exams/exam_pending.html', {'session': session})
    
    result = session.result
    
    return render(request, 'exams/exam_results.html', {
        'session': session,
        'result': result,
        'course': session.exam.course
    })

@login_required
def certificate_view(request, course_id):
    """
    View certificate for a completed course
    """
    course = get_object_or_404(Course, id=course_id)
    enrollment = get_object_or_404(Enrollment, user=request.user, course=course)
    
    if not enrollment.certificate_earned:
        messages.error(request, "You haven't earned a certificate for this course yet")
        return redirect('courses:view_course', pk=course_id)
    
    # Get the latest passing exam result
    result = ExamResult.objects.filter(
        session__user=request.user,
        session__exam__course=course,
        passed=True
    ).order_by('-created_at').first()
    
    return render(request, 'exams/certificate.html', {
        'course': course,
        'result': result,
        'enrollment': enrollment
    })

# Additional views for instructors
@login_required
def review_exam_attempts(request, course_id):
    """
    Instructor view to review exam attempts
    """
    course = get_object_or_404(Course, id=course_id)
    
    if course.creator != request.user:
        raise PermissionDenied("You don't have permission to review these exams")
    
    exam = get_object_or_404(CourseExam, course=course)
    sessions = ExamSession.objects.filter(exam=exam).select_related('user', 'result')
    
    return render(request, 'exams/review_attempts.html', {
        'course': course,
        'exam': exam,
        'sessions': sessions
    })

@login_required
def review_exam_detail(request, session_id):
    """
    Instructor view to review a specific exam attempt
    """
    session = get_object_or_404(ExamSession, id=session_id)
    
    if session.exam.course.creator != request.user:
        raise PermissionDenied("You don't have permission to review this exam")
    
    if request.method == 'POST':
        form = ExamReviewForm(request.POST, instance=session.result)
        if form.is_valid():
            form.save()
            messages.success(request, "Exam review saved successfully")
            return redirect('courses:review_exam_attempts', course_id=session.exam.course.id)
    else:
        form = ExamReviewForm(instance=session.result)
    
    return render(request, 'exams/review_detail.html', {
        'session': session,
        'form': form
    })

# Utility function to process exam results (could be a Celery task)
def process_exam_results(session_id):
    """
    Process exam results using AI for grading and cheating detection
    """
    try:
        session = ExamSession.objects.get(id=session_id)
        
        # AI grading
        score_data = analyze_exam_responses(session)
        
        # Cheating detection
        cheating_analysis = detect_cheating_patterns(session)
        
        # Create exam result
        result = ExamResult.objects.create(
            session=session,
            score=score_data['score'],
            max_score=score_data['max_score'],
            percentage=score_data['percentage'],
            passed=score_data['percentage'] >= session.exam.passing_score,
            graded_by_ai=True
        )
        
        # Update cheating detection
        session.cheating_detected = cheating_analysis['cheating_detected']
        session.cheating_analysis = cheating_analysis
        session.save()
        
        # Generate certificate if passed
        if result.passed:
            enrollment = Enrollment.objects.get(
                user=session.user, 
                course=session.exam.course
            )
            enrollment.certificate_earned = True
            enrollment.save()
            
            # Generate certificate content
            certificate_content = generate_certificate_content(session, result)
            certificate_url = generate_certificate_pdf(certificate_content)
            
            result.certificate_generated = True
            result.certificate_url = certificate_url
            result.save()
            
    except Exception as e:
        logger.error(f"Error processing exam results: {e}")