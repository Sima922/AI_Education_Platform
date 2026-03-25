from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.contrib import messages
import logging
from .models import Enrollment, Chapter
from .models import UserProgress

logger = logging.getLogger(__name__)

def submit_quiz(request, chapter_id):
    """Handle quiz submission and scoring."""
    chapter = get_object_or_404(Chapter, id=chapter_id)
    if request.method == "POST":
        quiz_data = chapter.quiz
        score = 0
        total = 0
        user_responses = {}
        
        if quiz_data and "questions" in quiz_data:
            for i, question in enumerate(quiz_data["questions"], 1):
                question_id = question.get("id", i)
                user_answer = request.POST.get(f"question_{i}")
                
                # Get correct answer
                correct_answer = None
                if question.get("user_correct_answer") is not None:
                    correct_answer = str(question.get("user_correct_answer"))
                elif question.get("correct_answer") is not None:
                    correct_answer = str(question.get("correct_answer"))
                else:
                    correct_answer = "0"
                
                # Get text representations for answers
                user_answer_index = int(user_answer) if user_answer and user_answer.isdigit() else None
                user_answer_text = "No answer" 
                if user_answer_index is not None and 0 <= user_answer_index < len(question["options"]):
                    user_answer_text = question["options"][user_answer_index]
                
                correct_answer_index = int(correct_answer) if correct_answer and correct_answer.isdigit() else 0
                correct_answer_text = "Answer unavailable"
                if 0 <= correct_answer_index < len(question["options"]):
                    correct_answer_text = question["options"][correct_answer_index]
                
                is_correct = user_answer == correct_answer
                
                user_responses[question_id] = {
                    "question": question["question"],
                    "user_answer": user_answer_text,
                    "correct_answer": correct_answer_text,
                    "is_correct": is_correct,
                    "explanation": question.get("explanation", "")
                }
                
                if is_correct:
                    score += 1
                total += 1
            
            percentage = (score / total) * 100 if total > 0 else 0
            
            # Store results in session
            request.session[f'quiz_results_{chapter_id}'] = {
                "score": score,
                "total": total,
                "percentage": percentage,
                "responses": user_responses,
                "chapter_id": chapter_id,
                "timestamp": timezone.now().isoformat()
            }
            request.session.modified = True
            
            # Update user progress - NEW CODE
            if request.user.is_authenticated:
                progress, created = UserProgress.objects.get_or_create(
                    user=request.user,
                    course=chapter.course,
                    chapter=chapter,
                    defaults={'quiz_completed': True, 'quiz_score': percentage}
                )
                if not created:
                    progress.mark_quiz_completed(percentage)
            
            messages.success(
                request,
                f"Quiz completed! Score: {score}/{total} ({percentage:.1f}%)"
            )
        else:
            messages.error(request, "Quiz data not found")
            
    return redirect(reverse("courses:view_course", kwargs={"pk": chapter.course.id}) + f"?scroll_to=quiz-{chapter_id}#quiz-{chapter_id}")

def reset_quiz(request, chapter_id):
    """Reset quiz results to allow retaking the quiz."""
    if f'quiz_results_{chapter_id}' in request.session:
        del request.session[f'quiz_results_{chapter_id}']
        request.session.modified = True
    
    chapter = get_object_or_404(Chapter, id=chapter_id)    
    return redirect(reverse("courses:view_course", kwargs={
        "pk": chapter.course.id
    }) + f"?scroll_to=quiz-{chapter_id}#quiz-{chapter_id}")                                                                                                                                                                                         


