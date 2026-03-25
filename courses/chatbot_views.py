from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from .models import ChatbotConversation, ChatMessage, Course
from .ai_integration.rag_service import rag_query
import json
import logging

logger = logging.getLogger(__name__)


@csrf_exempt
def start_chatbot_session(request, course_id):
    """Handle chatbot session creation (no authentication required)"""
    course = get_object_or_404(Course, id=course_id)
    
    # Generate unique session ID for anonymous users
    session_key = request.session.session_key
    if not session_key:
        request.session.create()
        session_key = request.session.session_key
    
    # Use session-based tracking instead of user authentication
    conversation, created = ChatbotConversation.objects.get_or_create(
        session_key=session_key,
        course=course,
        defaults={
            'created_at': timezone.now()
        }
    )
    
    return JsonResponse({
        "success": True,
        "conversation_id": conversation.id,
        "welcome_message": f"Hello! I'm your assistant for '{course.title}'. How can I help?",
        "is_new": created
    })

@csrf_exempt
def chatbot_interact(request, conversation_id):
    """Handle chatbot interactions (no authentication required)"""
    if request.method != "POST":
        return JsonResponse({
            "error": "Only POST requests are allowed",
            "status": 405
        }, status=405)
    
    try:
        data = json.loads(request.body)
        user_message = data.get("message", "").strip()
        
        if not user_message:
            return JsonResponse({
                "error": "Message cannot be empty",
                "status": 400
            }, status=400)
        
        if len(user_message) > 500:
            return JsonResponse({
                "error": "Message too long (max 500 characters)",
                "status": 400
            }, status=400)
        
        # Get conversation with session validation
        conversation = get_object_or_404(ChatbotConversation, id=conversation_id)
        
        # Verify session ownership
        if conversation.session_key != request.session.session_key:
            return JsonResponse({
                "error": "Session mismatch",
                "status": 403
            }, status=403)
        
        # Save user message
        ChatMessage.objects.create(
            conversation=conversation,
            message=user_message,
            is_user=True
        )
        
        # Rate limiting check
        last_hour = timezone.now() - timezone.timedelta(hours=1)
        recent_messages = ChatMessage.objects.filter(
            conversation=conversation,
            timestamp__gte=last_hour
        ).count()
        
        if recent_messages > 30:  # 30 messages/hour limit
            return JsonResponse({
                "error": "Rate limit exceeded (30 messages/hour)",
                "status": 429
            }, status=429)
        
        # Get conversation history (last 5 messages)
        history_messages = ChatMessage.objects.filter(
            conversation=conversation
        ).order_by('-timestamp')[:5]
        
        history = [
            {
                "message": msg.message,
                "is_user": msg.is_user,
                "timestamp": msg.timestamp.isoformat()
            }
            for msg in history_messages
        ]
        
        # Get RAG response with timeout
        try:
            bot_response = rag_query(
                course=conversation.course,
                question=user_message,
                conversation_history=history
            )
        except Exception as e:
            bot_response = "I'm having trouble responding right now. Please try again later."
        
        # Save bot response
        ChatMessage.objects.create(
            conversation=conversation,
            message=bot_response,
            is_user=False
        )
        
        return JsonResponse({
            "success": True,
            "response": bot_response,
            "course_id": conversation.course.id,
            "timestamp": timezone.now().isoformat()
        })
    
    except json.JSONDecodeError:
        return JsonResponse({
            "error": "Invalid JSON data",
            "status": 400
        }, status=400)
    except Exception as e:
        return JsonResponse({
            "error": "Internal server error",
            "status": 500,
            "detail": str(e)
        }, status=500)

def get_course_info(request, course_id):
    """Public endpoint to get basic course info for chatbot context"""
    course = get_object_or_404(Course, id=course_id)
    
    return JsonResponse({
        "success": True,
        "course": {
            "id": course.id,
            "title": course.title,
            "description": course.description,
            "chapters": [
                {
                    "id": chapter.id,
                    "title": chapter.title,
                    "order": chapter.order
                }
                for chapter in course.chapter_set.all().order_by('order')
            ]
        }
    }) 