# gemini_integration.py - Fixed version with quota management and batching
import google.generativeai as genai
from typing import Dict, List, Optional, Union
import logging
import json
import os
from django.core.cache import cache
from django.conf import settings
import time
from .youtube_fetcher import fetch_youtube_videos


# ---------------------------------------------------------------
# SECURITY FIX: API key loaded from environment variable ONLY.
# Never hardcode API keys in source code.
# Set GEMINI_API_KEY in your .env file.
# ---------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise EnvironmentError(
        "GEMINI_API_KEY environment variable is not set. "
        "Add it to your .env file: GEMINI_API_KEY=your-key-here"
    )


# Create model object with error handling
try:
    model = genai.GenerativeModel("gemini-2.0-flash-exp")
except Exception as e:
    logging.error(f"Failed to initialize Gemini model: {e}")
    model = None

logger = logging.getLogger(__name__)

# Quota management constants
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
CACHE_TIMEOUT = 86400  # 24 hours

def safe_gemini_call(prompt: str, cache_key: str = None, max_tokens: int = 1000) -> str:
    """
    Make a safe Gemini API call with quota management and caching.
    """
    if not model:
        logger.error("Gemini model not initialized")
        return "Error: Gemini model not available"
    
    # Check cache first
    if cache_key:
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.info(f"Using cached result for {cache_key}")
            return cached_result
    
    # Make API call with retries
    for attempt in range(MAX_RETRIES):
        try:
            response = model.generate_content(prompt)
            result = response.text.strip()
            
            # Cache successful result
            if cache_key and result:
                cache.set(cache_key, result, CACHE_TIMEOUT)
                logger.info(f"Cached result for {cache_key}")
            
            return result
            
        except Exception as e:
            error_msg = str(e).lower()
            if "quota" in error_msg or "429" in error_msg:
                logger.warning(f"Quota exceeded, attempt {attempt + 1}/{MAX_RETRIES}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff
                else:
                    logger.error("Quota exhausted, using fallback content")
                    return "Content temporarily unavailable due to API limits. Please try again later."
            else:
                logger.error(f"Gemini API error: {e}")
                return f"Error generating content: {str(e)}"
    
    return "Error: Failed to generate content after multiple attempts"

def fix_course_typos(text: str) -> str:
    """Fix common course title typos."""
    if not text:
        return ""
    
    replacements = {
        "Precalculu": "Precalculus",
        "Calculic": "Calculus", 
        "Algebraic": "Algebra",
        "Geometr": "Geometry",
        "Statistic": "Statistics"
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

def generate_comprehensive_chapter_content(
    chapter_title: str,
    course_topic: str,
    file_context: str = "",
    keywords: List[str] = []
) -> Dict[str, str]:
    """
    Generate ALL chapter content in a single API call to save quota.
    """
    try:
        # Create cache key
        cache_key = f"chapter_content_{hash(chapter_title + course_topic + file_context[:100])}"
        
        keyword_context = f" Key concepts: {', '.join(keywords[:5])}" if keywords else ""
        file_context_snippet = file_context[:800] + "..." if len(file_context) > 800 else file_context
        file_context_hint = f"\n\nInstructor's Materials:\n{file_context_snippet}" if file_context else ""
        
        prompt = f"""
You are an expert educator creating comprehensive educational content. 
Generate ALL of the following for chapter '{chapter_title}' in course '{course_topic}':
{keyword_context}{file_context_hint}

Please provide in this exact format:

INTRODUCTION:
[Provide context, motivation, and real-world applications. Reference instructor materials if provided.]

MAIN_CONTENT:
[Break down key concepts with examples and explanations. Incorporate instructor materials.]

SUMMARY:
[Recap key points and connect to future topics.]

LEARNING_OBJECTIVES:
1. [Objective starting with action verb like analyze/evaluate/solve/apply/demonstrate]
2. [Second objective]
3. [Third objective]
4. [Fourth objective]
5. [Fifth objective]

PRACTICAL_EXAMPLES:
Example 1: [Title]
[Real-world scenario and step-by-step solution]

Example 2: [Title]
[Real-world scenario and step-by-step solution]

QUIZ_QUESTIONS:
1. [Question text]
A) [Option A]
B) [Option B]
C) [Option C]
D) [Option D]
CORRECT: [A/B/C/D]
EXPLANATION: [Brief explanation]

2. [Question text]
A) [Option A]
B) [Option B]
C) [Option C] 
D) [Option D]
CORRECT: [A/B/C/D]
EXPLANATION: [Brief explanation]

3. [Question text]
A) [Option A]
B) [Option B]
C) [Option C]
D) [Option D]
CORRECT: [A/B/C/D]
EXPLANATION: [Brief explanation]

VIDEO_SEARCH_QUERY:
[Optimized YouTube search query for this chapter - under 10 words]
"""

        # Make single API call
        response = safe_gemini_call(prompt, cache_key)
        
        if "Error" in response or "temporarily unavailable" in response:
            return create_fallback_chapter_content(chapter_title)
        
        # Parse the comprehensive response
        return parse_comprehensive_response(response, chapter_title)
        
    except Exception as e:
        logger.error(f"Error generating comprehensive chapter content: {e}")
        return create_fallback_chapter_content(chapter_title)

def parse_comprehensive_response(response: str, chapter_title: str) -> Dict[str, str]:
    """
    Parse the comprehensive response from Gemini into structured data.
    """
    try:
        sections = {}
        current_section = None
        current_content = []
        
        lines = response.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Check for section headers
            if line.startswith('INTRODUCTION:'):
                if current_section:
                    sections[current_section] = '\n'.join(current_content)
                current_section = 'introduction'
                current_content = []
            elif line.startswith('MAIN_CONTENT:'):
                if current_section:
                    sections[current_section] = '\n'.join(current_content)
                current_section = 'main_content'
                current_content = []
            elif line.startswith('SUMMARY:'):
                if current_section:
                    sections[current_section] = '\n'.join(current_content)
                current_section = 'summary'
                current_content = []
            elif line.startswith('LEARNING_OBJECTIVES:'):
                if current_section:
                    sections[current_section] = '\n'.join(current_content)
                current_section = 'learning_objectives'
                current_content = []
            elif line.startswith('PRACTICAL_EXAMPLES:'):
                if current_section:
                    sections[current_section] = '\n'.join(current_content)
                current_section = 'practical_examples'
                current_content = []
            elif line.startswith('QUIZ_QUESTIONS:'):
                if current_section:
                    sections[current_section] = '\n'.join(current_content)
                current_section = 'quiz_questions'
                current_content = []
            elif line.startswith('VIDEO_SEARCH_QUERY:'):
                if current_section:
                    sections[current_section] = '\n'.join(current_content)
                current_section = 'video_search_query'
                current_content = []
            else:
                current_content.append(line)
        
        # Add final section
        if current_section:
            sections[current_section] = '\n'.join(current_content)
        
        # Parse learning objectives
        learning_objectives = []
        if 'learning_objectives' in sections:
            for line in sections['learning_objectives'].split('\n'):
                if line.strip() and (line.strip().startswith(tuple('12345')) or 
                                   any(verb in line.lower() for verb in ['analyze', 'evaluate', 'solve', 'apply', 'demonstrate'])):
                    learning_objectives.append(line.strip().lstrip('12345. '))
        
        # Parse practical examples
        practical_examples = []
        if 'practical_examples' in sections:
            examples_text = sections['practical_examples']
            example_parts = examples_text.split('Example ')
            for part in example_parts[1:]:  # Skip first empty part
                if part.strip():
                    lines = part.strip().split('\n')
                    title = f"Example {lines[0].split(':')[0]}"
                    content = '\n'.join(lines[1:]) if len(lines) > 1 else lines[0]
                    practical_examples.append({"title": title, "content": content})
        
        # Parse quiz questions
        quiz_questions = []
        if 'quiz_questions' in sections:
            quiz_text = sections['quiz_questions']
            questions = quiz_text.split('\n\n')
            
            for i, q in enumerate(questions):
                if q.strip() and any(char.isdigit() for char in q[:3]):
                    lines = [line.strip() for line in q.split('\n') if line.strip()]
                    if len(lines) >= 6:  # Question + 4 options + correct + explanation
                        question_text = lines[0].split('.', 1)[1].strip() if '.' in lines[0] else lines[0]
                        options = [line[2:].strip() for line in lines[1:5] if line.startswith(('A)', 'B)', 'C)', 'D)'))]
                        correct_line = next((line for line in lines if line.startswith('CORRECT:')), '')
                        explanation_line = next((line for line in lines if line.startswith('EXPLANATION:')), '')
                        
                        correct_answer = 0  # Default
                        if correct_line:
                            correct_letter = correct_line.split(':', 1)[1].strip()
                            correct_answer = ord(correct_letter.upper()) - ord('A') if correct_letter in 'ABCD' else 0
                        
                        explanation = explanation_line.split(':', 1)[1].strip() if explanation_line else ""
                        
                        if len(options) == 4:
                            quiz_questions.append({
                                "id": i + 1,
                                "question": question_text,
                                "options": options,
                                "correct_answer": correct_answer,
                                "user_correct_answer": None,
                                "explanation": explanation
                            })
        
        # Get video search query
        video_query = sections.get('video_search_query', f"{chapter_title} tutorial").strip()
        
        return {
            "introduction": sections.get('introduction', f"Introduction to {chapter_title}"),
            "main_content": sections.get('main_content', f"Main content for {chapter_title}"),
            "summary": sections.get('summary', f"Summary of {chapter_title}"),
            "subtopics": [chapter_title],
            "learning_objectives": learning_objectives[:5] or [f"Understand {chapter_title}"],
            "practical_examples": practical_examples or [{"title": "Example 1", "content": f"Practical application of {chapter_title}"}],
            "quiz": {"questions": quiz_questions[:5]},
            "video_search_query": video_query
        }
        
    except Exception as e:
        logger.error(f"Error parsing comprehensive response: {e}")
        return create_fallback_chapter_content(chapter_title)

def create_fallback_chapter_content(chapter_title: str) -> Dict[str, str]:
    """Create fallback content when API calls fail."""
    return {
        "introduction": f"Welcome to {chapter_title}. This chapter introduces fundamental concepts and practical applications.",
        "main_content": f"In this chapter, we explore the key principles of {chapter_title} with detailed explanations and examples.",
        "summary": f"This chapter covered the essential aspects of {chapter_title} and its practical applications.",
        "subtopics": [chapter_title],
        "learning_objectives": [
            f"Understand the fundamental concepts of {chapter_title}",
            f"Apply {chapter_title} principles to solve problems",
            f"Analyze real-world applications of {chapter_title}",
            f"Evaluate different approaches in {chapter_title}",
            f"Demonstrate proficiency in {chapter_title} techniques"
        ],
        "practical_examples": [
            {"title": "Basic Example", "content": f"A fundamental example demonstrating {chapter_title} concepts."},
            {"title": "Advanced Example", "content": f"A more complex application of {chapter_title} principles."}
        ],
        "quiz": {
            "questions": [
                {
                    "id": 1,
                    "question": f"What is a key concept in {chapter_title}?",
                    "options": [
                        "Understanding fundamental principles",
                        "Applying theoretical concepts", 
                        "Analyzing complex problems",
                        "All of the above"
                    ],
                    "correct_answer": 3,
                    "user_correct_answer": None,
                    "explanation": f"All aspects are important in mastering {chapter_title}."
                }
            ]
        },
        "video_search_query": f"{chapter_title} tutorial basics"
    }

def generate_course_from_prompt(
    prompt: str,
    file_context: str = "",
    keywords: List[str] = []
) -> dict:
    """Generate complete course structure with single API call per chapter."""
    try:
        # Validate inputs
        if not prompt or not isinstance(prompt, str) or len(prompt.strip()) == 0:
            raise ValueError("Prompt must be a non-empty string")
        
        # Create cache key for course structure
        structure_cache_key = f"course_structure_{hash(prompt + file_context[:100])}"
        
        keyword_context = f" Key concepts: {', '.join(keywords[:5])}" if keywords else ""
        file_context_hint = f"\n\nInstructor's Materials:\n{file_context[:1000]}" if file_context else ""
        
        # Generate course structure
        structure_prompt = f"""
Create a course structure in exact JSON format:
{{
  "title": "Course Title",
  "description": "Course description", 
  "topic": "Main topic",
  "chapters": [
    {{
      "title": "Chapter Title",
      "learning_objectives": ["objective1", "objective2"],
      "subtopics": ["subtopic1", "subtopic2"]
    }}
  ]
}}

Base the course on: {prompt}
{keyword_context}{file_context_hint}

Return ONLY valid JSON, no additional text.
"""
        
        response = safe_gemini_call(structure_prompt, structure_cache_key)
        
        # Parse JSON response
        try:
            if response.startswith('```json'):
                response = response[7:-3].strip()
            elif response.startswith('```'):
                response = response[3:-3].strip()
            
            course_data = json.loads(response)
        except json.JSONDecodeError:
            logger.warning("JSON parsing failed, using fallback structure")
            course_data = {
                "title": f"Course: {prompt[:50]}",
                "description": "A comprehensive course based on your requirements",
                "topic": prompt[:50],
                "chapters": [
                    {
                        "title": "Introduction",
                        "learning_objectives": ["Understand basic concepts"],
                        "subtopics": ["Fundamentals"]
                    },
                    {
                        "title": "Core Concepts", 
                        "learning_objectives": ["Apply key principles"],
                        "subtopics": ["Main topics"]
                    }
                ]
            }
        
        # Generate content for each chapter using comprehensive method
        for chapter in course_data['chapters']:
            chapter_content = generate_comprehensive_chapter_content(
                chapter_title=chapter['title'],
                course_topic=course_data['topic'], 
                file_context=file_context,
                keywords=keywords
            )
            
            # Update chapter with all content
            chapter.update(chapter_content)
            
            # Add video recommendations (limit to save quota)
            try:
                videos = fetch_youtube_videos(
                    query=chapter_content.get('video_search_query', f"{chapter['title']} tutorial"),
<<<<<<< HEAD
                    max_results=3,  # Reduced from 5
                    keywords=keywords[:3]  # Limit keywords
                )
                chapter['videos'] = [{
                    "video": vid,
                    "summary": f"Educational video about {chapter['title']}",  # Simple summary to save API calls
=======
                    max_results=3,
                    keywords=keywords[:3]
                )
                chapter['videos'] = [{
                    "video": vid,
                    "summary": f"Educational video about {chapter['title']}",
>>>>>>> 8ec92ca (Initial commit)
                    "relevance_point": chapter['title']
                } for vid in videos]
            except Exception as e:
                logger.error(f"Error fetching videos: {e}")
                chapter['videos'] = []
        
        logger.info(f"Successfully generated course: {course_data['title']}")
        return course_data
    
    except Exception as e:
        logger.error(f"Error generating course from prompt: {e}")
        raise

def verify_gemini_setup():
    """Verify Gemini API setup with quota-aware testing."""
    try:
        if not model:
            logger.error("Gemini model not initialized")
            return False
            
        test_response = safe_gemini_call("Hello, this is a test.", "gemini_test")
        
        if "Error" in test_response or "temporarily unavailable" in test_response:
            logger.warning("Gemini API has quota issues but connection works")
<<<<<<< HEAD
            return True  # Connection works, just quota limited
=======
            return True
>>>>>>> 8ec92ca (Initial commit)
        
        logger.info("Gemini API setup verified successfully")
        return True
    except Exception as e:
        logger.error(f"Gemini API setup failed: {e}")
        return False

<<<<<<< HEAD
# Legacy functions for backward compatibility - now use comprehensive generation
=======
# Legacy functions for backward compatibility
>>>>>>> 8ec92ca (Initial commit)
def generate_chapter_content(chapter_title, course_topic, file_context="", keywords=[]):
    """Legacy wrapper - now uses comprehensive generation."""
    result = generate_comprehensive_chapter_content(chapter_title, course_topic, file_context, keywords)
    return {
        "introduction": result["introduction"],
        "main_content": result["main_content"], 
        "summary": result["summary"],
        "subtopics": result["subtopics"]
    }

def generate_quiz(chapter_title, chapter_content, file_context="", keywords=[]):
    """Legacy wrapper."""
    result = generate_comprehensive_chapter_content(chapter_title, "General", file_context, keywords)
    return result["quiz"]

def generate_learning_objectives(chapter_title, chapter_content, file_context="", keywords=[]):
    """Legacy wrapper."""
    result = generate_comprehensive_chapter_content(chapter_title, "General", file_context, keywords)
    return result["learning_objectives"]

def generate_practical_examples(chapter_title, chapter_content, file_context="", keywords=[]):
    """Legacy wrapper."""
    result = generate_comprehensive_chapter_content(chapter_title, "General", file_context, keywords) 
    return result["practical_examples"]


<<<<<<< HEAD
# Add these exam-related functions to your gemini_integration.py file

=======
>>>>>>> 8ec92ca (Initial commit)
def generate_comprehensive_exam(
    course_content: Dict,
    prompt: str = "",
    template_file: Optional[str] = None
) -> Dict:
<<<<<<< HEAD
    """
    Generate a comprehensive exam for a course using AI.
    
    Args:
        course_content: The course content structure
        prompt: Custom instructions for exam generation
        template_file: Path to uploaded exam template (if any)
    
    Returns:
        Dict: Exam structure with questions, answers, and grading rubric
    """
    try:
        # Create cache key
        cache_key = f"exam_{hash(str(course_content) + prompt)}"
        
        # Build the exam generation prompt
=======
    """Generate a comprehensive exam for a course using AI."""
    try:
        cache_key = f"exam_{hash(str(course_content) + prompt)}"
        
>>>>>>> 8ec92ca (Initial commit)
        exam_prompt = f"""
        You are an expert educator creating a comprehensive final exam for a course.
        
        COURSE CONTENT:
        {json.dumps(course_content, indent=2)}
        
        INSTRUCTOR INSTRUCTIONS:
        {prompt if prompt else "Create a comprehensive exam that tests both theoretical knowledge and practical application."}
        
        Please generate a complete exam with the following structure:
        
        EXAM STRUCTURE:
        - Title: [Appropriate exam title]
        - Description: [Brief exam description]
        - Time Limit: [Recommended time in minutes]
        - Total Points: [Total possible score]
        - Passing Score: [Recommended passing percentage]
        
        SECTIONS:
        1. Multiple Choice Questions (30% of total points)
        2. True/False Questions (20% of total points) 
        3. Short Answer Questions (25% of total points)
        4. Essay Questions (15% of total points)
        5. Practical/Application Questions (10% of total points)
        
        For each question, provide:
        - Question text
        - Points value
        - For multiple choice: options and correct answer
        - For true/false: correct answer
        - For short answer: sample correct answer
        - For essay: grading rubric and expected key points
        - For practical: scenario and expected solution approach
        
        Also provide:
        - Answer key with explanations
        - Grading guidelines for subjective questions
        
        Return the exam in a structured JSON format.
        """
        
        response = safe_gemini_call(exam_prompt, cache_key, max_tokens=4000)
        
        if "Error" in response or "temporarily unavailable" in response:
            return create_fallback_exam(course_content)
        
        try:
<<<<<<< HEAD
            # Try to parse JSON response
=======
>>>>>>> 8ec92ca (Initial commit)
            if response.startswith('```json'):
                response = response[7:-3].strip()
            elif response.startswith('```'):
                response = response[3:-3].strip()
                
            exam_data = json.loads(response)
            return exam_data
        except json.JSONDecodeError:
            logger.error("Failed to parse exam JSON, using fallback")
            return create_fallback_exam(course_content)
            
    except Exception as e:
        logger.error(f"Error generating comprehensive exam: {e}")
        return create_fallback_exam(course_content)

def create_fallback_exam(course_content: Dict) -> Dict:
    """Create a fallback exam structure when AI generation fails."""
    return {
        "title": f"Final Exam: {course_content.get('title', 'Course')}",
        "description": "Comprehensive examination covering course materials",
        "time_limit_minutes": 120,
        "total_points": 100,
        "passing_score": 70,
        "sections": [
            {
                "type": "multiple_choice",
                "title": "Multiple Choice Questions",
                "description": "Select the best answer for each question",
                "points_per_question": 2,
                "questions": [
                    {
                        "id": 1,
                        "question": "What is a key concept covered in this course?",
                        "options": [
                            "Fundamental principles",
                            "Advanced techniques",
                            "Practical applications", 
                            "All of the above"
                        ],
                        "correct_answer": 3,
                        "explanation": "The course covers all these aspects comprehensively."
                    }
                ]
            },
            {
                "type": "true_false", 
                "title": "True/False Questions",
                "description": "Determine if each statement is true or false",
                "points_per_question": 1,
                "questions": [
                    {
                        "id": 1,
                        "question": "This statement is true.",
                        "correct_answer": True,
                        "explanation": "The statement is indeed true."
                    }
                ]
            }
        ],
        "answer_key": {},
        "grading_guidelines": "Grade based on accuracy and completeness of responses."
    }

def analyze_exam_responses(exam_session) -> Dict:
<<<<<<< HEAD
    """
    Analyze student exam responses using AI for grading and feedback.
    
    Args:
        exam_session: The ExamSession object with student answers
    
    Returns:
        Dict: Analysis results with scores, feedback, and cheating indicators
    """
    try:
        # Prepare data for AI analysis
=======
    """Analyze student exam responses using AI for grading and feedback."""
    try:
>>>>>>> 8ec92ca (Initial commit)
        exam_data = {
            "exam_structure": exam_session.exam.structure,
            "student_answers": [],
            "question_data": []
        }
        
<<<<<<< HEAD
        # Collect questions and answers
=======
>>>>>>> 8ec92ca (Initial commit)
        for answer in exam_session.answers.all():
            question_data = {
                "id": answer.question.id,
                "type": answer.question.question_type,
                "question_text": answer.question.question_text,
                "correct_answer": answer.question.correct_answer,
                "points": answer.question.points,
                "student_answer": answer.answer_text
            }
            exam_data["question_data"].append(question_data)
            
            answer_data = {
                "question_id": answer.question.id,
                "answer": answer.answer_text,
                "is_correct": answer.is_correct
            }
            exam_data["student_answers"].append(answer_data)
        
<<<<<<< HEAD
        # Create cache key
        cache_key = f"exam_analysis_{exam_session.id}"
        
        # Build analysis prompt
=======
        cache_key = f"exam_analysis_{exam_session.id}"
        
>>>>>>> 8ec92ca (Initial commit)
        analysis_prompt = f"""
        You are an expert educator grading exam responses. Analyze the following exam:
        
        EXAM DATA:
        {json.dumps(exam_data, indent=2)}
        
        Please provide:
        1. Overall score calculation
        2. Detailed feedback on each response
        3. Identification of potential cheating patterns
        4. Recommendations for improvement
        
<<<<<<< HEAD
        For cheating detection, look for:
        - Unusual answer patterns
        - Responses that seem copied or AI-generated
        - Inconsistencies in knowledge demonstration
        
=======
>>>>>>> 8ec92ca (Initial commit)
        Return analysis in JSON format with:
        - overall_score: number
        - max_score: number  
        - percentage: number
        - question_feedback: array of feedback objects
        - cheating_indicators: array of potential issues
        - recommendations: array of improvement suggestions
        """
        
        response = safe_gemini_call(analysis_prompt, cache_key, max_tokens=3000)
        
        if "Error" in response or "temporarily unavailable" in response:
            return create_fallback_exam_analysis(exam_data)
        
        try:
<<<<<<< HEAD
            # Try to parse JSON response
=======
>>>>>>> 8ec92ca (Initial commit)
            if response.startswith('```json'):
                response = response[7:-3].strip()
            elif response.startswith('```'):
                response = response[3:-3].strip()
                
            analysis = json.loads(response)
            return analysis
        except json.JSONDecodeError:
            logger.error("Failed to parse exam analysis JSON, using fallback")
            return create_fallback_exam_analysis(exam_data)
            
    except Exception as e:
        logger.error(f"Error analyzing exam responses: {e}")
        return create_fallback_exam_analysis({})

def create_fallback_exam_analysis(exam_data: Dict) -> Dict:
    """Create fallback exam analysis when AI fails."""
<<<<<<< HEAD
    # Calculate basic score
=======
>>>>>>> 8ec92ca (Initial commit)
    total_score = 0
    max_score = 0
    
    for question in exam_data.get("question_data", []):
        max_score += question.get("points", 1)
        if question.get("student_answer") == question.get("correct_answer"):
            total_score += question.get("points", 1)
    
    percentage = (total_score / max_score * 100) if max_score > 0 else 0
    
    return {
        "overall_score": total_score,
        "max_score": max_score,
        "percentage": percentage,
        "question_feedback": [],
        "cheating_indicators": [],
        "recommendations": ["Review course materials and try again."]
    }

def detect_cheating_patterns(proctoring_data: Dict) -> Dict:
<<<<<<< HEAD
    """
    Analyze proctoring data for potential cheating patterns.
    
    Args:
        proctoring_data: Dictionary of proctoring events and metrics
    
    Returns:
        Dict: Cheating analysis with confidence scores and evidence
    """
    try:
        # Create cache key
        cache_key = f"cheating_analysis_{hash(str(proctoring_data))}"
        
        # Build cheating detection prompt
=======
    """Analyze proctoring data for potential cheating patterns."""
    try:
        cache_key = f"cheating_analysis_{hash(str(proctoring_data))}"
        
>>>>>>> 8ec92ca (Initial commit)
        cheating_prompt = f"""
        You are a proctoring expert analyzing exam session data for cheating patterns.
        
        PROCTORING DATA:
        {json.dumps(proctoring_data, indent=2)}
        
        Analyze this data for potential cheating indicators:
        - Frequent tab switching
        - Fullscreen exits
        - Face not visible
        - Multiple faces detected
        - Audio detection
        - Unusual timing patterns
        - Inconsistent performance
        
        Return analysis in JSON format with:
        - cheating_detected: boolean
        - confidence_score: number (0-100)
        - indicators: array of detected patterns
        - evidence: specific examples from the data
        - recommendation: action to take
        """
        
        response = safe_gemini_call(cheating_prompt, cache_key, max_tokens=2000)
        
        if "Error" in response or "temporarily unavailable" in response:
            return create_fallback_cheating_analysis(proctoring_data)
        
        try:
<<<<<<< HEAD
            # Try to parse JSON response
=======
>>>>>>> 8ec92ca (Initial commit)
            if response.startswith('```json'):
                response = response[7:-3].strip()
            elif response.startswith('```'):
                response = response[3:-3].strip()
                
            analysis = json.loads(response)
            return analysis
        except json.JSONDecodeError:
            logger.error("Failed to parse cheating analysis JSON, using fallback")
            return create_fallback_cheating_analysis(proctoring_data)
            
    except Exception as e:
        logger.error(f"Error detecting cheating patterns: {e}")
        return create_fallback_cheating_analysis(proctoring_data)

def create_fallback_cheating_analysis(proctoring_data: Dict) -> Dict:
    """Create fallback cheating analysis when AI fails."""
<<<<<<< HEAD
    # Simple heuristic-based analysis
=======
>>>>>>> 8ec92ca (Initial commit)
    tab_switches = proctoring_data.get("tab_switch_count", 0)
    fullscreen_exits = proctoring_data.get("fullscreen_exit_count", 0)
    face_not_visible = proctoring_data.get("face_not_visible_count", 0)
    
    cheating_detected = (tab_switches > 5 or fullscreen_exits > 3 or face_not_visible > 10)
    confidence = min(100, (tab_switches * 10 + fullscreen_exits * 15 + face_not_visible * 8))
    
    indicators = []
    if tab_switches > 5:
        indicators.append(f"Excessive tab switching ({tab_switches} times)")
    if fullscreen_exits > 3:
        indicators.append(f"Multiple fullscreen exits ({fullscreen_exits} times)")
    if face_not_visible > 10:
        indicators.append(f"Face not visible for extended periods ({face_not_visible} times)")
    
    return {
        "cheating_detected": cheating_detected,
        "confidence_score": confidence,
        "indicators": indicators,
        "evidence": proctoring_data,
        "recommendation": "Review session recording for confirmation" if cheating_detected else "No action needed"
    }

def generate_certificate_content(
    student_name: str,
    course_title: str,
    score: float,
    completion_date: str
) -> Dict:
<<<<<<< HEAD
    """
    Generate certificate content using AI.
    
    Args:
        student_name: Name of the student
        course_title: Title of the course
        score: Final score achieved
        completion_date: Date of course completion
    
    Returns:
        Dict: Certificate content with text, design suggestions, and metadata
    """
    try:
        # Create cache key
        cache_key = f"certificate_{hash(student_name + course_title + str(score))}"
        
        # Build certificate generation prompt
=======
    """Generate certificate content using AI."""
    try:
        cache_key = f"certificate_{hash(student_name + course_title + str(score))}"
        
>>>>>>> 8ec92ca (Initial commit)
        certificate_prompt = f"""
        You are creating a professional certificate of completion.
        
        STUDENT: {student_name}
        COURSE: {course_title}
        SCORE: {score}%
        DATE: {completion_date}
        
        Generate certificate content including:
        1. Formal certificate text
        2. Design suggestions (colors, layout, elements)
        3. Optional motivational quote
        4. Signature lines for instructor and institution
        5. Certificate number format
        
        Return in JSON format with:
        - title: Certificate title
        - text: Main certificate text
        - design_suggestions: Array of design ideas
        - quote: Optional motivational quote
        - signature_lines: Array of signature fields
        - certificate_number_format: Suggested format for certificate numbers
        """
        
        response = safe_gemini_call(certificate_prompt, cache_key, max_tokens=1500)
        
        if "Error" in response or "temporarily unavailable" in response:
            return create_fallback_certificate(student_name, course_title, score, completion_date)
        
        try:
<<<<<<< HEAD
            # Try to parse JSON response
=======
>>>>>>> 8ec92ca (Initial commit)
            if response.startswith('```json'):
                response = response[7:-3].strip()
            elif response.startswith('```'):
                response = response[3:-3].strip()
                
            certificate = json.loads(response)
            return certificate
        except json.JSONDecodeError:
            logger.error("Failed to parse certificate JSON, using fallback")
            return create_fallback_certificate(student_name, course_title, score, completion_date)
            
    except Exception as e:
        logger.error(f"Error generating certificate content: {e}")
        return create_fallback_certificate(student_name, course_title, score, completion_date)

def create_fallback_certificate(
    student_name: str,
    course_title: str, 
    score: float,
    completion_date: str
) -> Dict:
    """Create fallback certificate content when AI fails."""
    return {
        "title": "Certificate of Completion",
        "text": f"This certifies that {student_name} has successfully completed the course '{course_title}' with a score of {score}% on {completion_date}.",
        "design_suggestions": [
            "Use a formal border design",
            "Include institution logo at the top",
            "Use classic serif fonts for formal appearance",
            "Add a gold seal for authenticity"
        ],
        "quote": "Education is the most powerful weapon which you can use to change the world. - Nelson Mandela",
        "signature_lines": [
            {"title": "Instructor", "line": "___________________________"},
            {"title": "Date", "line": completion_date},
            {"title": "Institution", "line": "CoursePlatform Certification Authority"}
        ],
        "certificate_number_format": "CP-{course_id}-{student_id}-{date}"
    }
<<<<<<< HEAD
    
=======

>>>>>>> 8ec92ca (Initial commit)
def generate_video_search_query(topic):
    return f"educational videos about {topic}"

def summarize_video(video_url):
<<<<<<< HEAD
    # Placeholder summary since AI is bypassed
    return "AI didn't generate a video summary because placeholder mode is active."

    
=======
    return "AI didn't generate a video summary because placeholder mode is active."
>>>>>>> 8ec92ca (Initial commit)
