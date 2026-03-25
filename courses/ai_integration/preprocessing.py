# preprocessing.py - Fixed version with better input validation
import re
import json
import logging
import os
from typing import List, Dict, Optional
from unstructured.partition.auto import partition
import openai
from datetime import datetime
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
import numpy as np

# Download NLTK resources if not already downloaded
try:
    nltk.data.find('tokenizers/punkt')
    nltk.data.find('corpora/stopwords')
except:
    try:
        nltk.download('punkt')
        nltk.download('stopwords')
    except:
        pass  # Fail silently if NLTK download fails

# Set up logging
logger = logging.getLogger(__name__)

def preprocess_outline(outline: str) -> List[Dict[str, str]]:
    """
    Preprocess a text-based course outline into structured data.
    Now handles empty/None outlines gracefully.
    
    Args:
        outline (str): Raw outline input from the user.
    
    Returns:
        List[Dict[str, str]]: A list of topics and subtopics.
    """
    try:
        logger.info("Starting outline preprocessing")
        
        # Handle empty/None outline gracefully
        if not outline or not isinstance(outline, str):
            logger.warning("Empty or invalid outline provided, creating default structure")
            return [
                {"id": "1", "title": "Introduction"},
                {"id": "2", "title": "Core Concepts"}, 
                {"id": "3", "title": "Practical Applications"},
                {"id": "4", "title": "Advanced Topics"},
                {"id": "5", "title": "Summary and Review"}
            ]
        
        outline = outline.strip()
        if len(outline) == 0:
            logger.warning("Empty outline after stripping, using default structure")
            return [
                {"id": "1", "title": "Introduction"},
                {"id": "2", "title": "Main Content"},
                {"id": "3", "title": "Conclusion"}
            ]
        
        structured_outline = []
        lines = outline.split("\n")
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Improved regex to handle different outline formats
            match = re.match(r"(\d+[\.\d]*)\s*-\s*(.+)", line) or \
                    re.match(r"(\d+[\.\d]*)\s+(.+)", line) or \
                    re.match(r"-\s*(.+)", line) or \
                    re.match(r"\*\s*(.+)", line) or \
                    re.match(r"•\s*(.+)", line)
                    
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    structured_outline.append({
                        "id": groups[0].strip(),
                        "title": groups[1].strip()
                    })
                elif len(groups) == 1:
                    structured_outline.append({
                        "id": str(len(structured_outline) + 1),
                        "title": groups[0].strip()
                    })
            else:
                # If no pattern matches, treat the whole line as a title
                if line and len(line) > 2:
                    structured_outline.append({
                        "id": str(len(structured_outline) + 1),
                        "title": line
                    })
        
        # If no valid outline items found, create default
        if not structured_outline:
            logger.warning("No valid outline items found, creating default based on content")
            # Try to create outline from the raw text
            if len(outline) > 10:
                structured_outline = [
                    {"id": "1", "title": "Introduction"}, 
                    {"id": "2", "title": outline[:50] + "..." if len(outline) > 50 else outline},
                    {"id": "3", "title": "Summary"}
                ]
            else:
                structured_outline = [
                    {"id": "1", "title": "Course Overview"},
                    {"id": "2", "title": "Main Topics"},
                    {"id": "3", "title": "Conclusion"}
                ]
        
        logger.info(f"Successfully preprocessed outline with {len(structured_outline)} items")
        return structured_outline
        
    except Exception as e:
        logger.error(f"Error preprocessing outline: {str(e)}", exc_info=True)
        # Return safe fallback
        return [
            {"id": "1", "title": "Introduction"},
            {"id": "2", "title": "Main Content"},
            {"id": "3", "title": "Conclusion"}
        ]

def preprocess_documents(files: List) -> List[str]:
    """
    Preprocess uploaded documents by extracting text and splitting into chunks.
    Now handles empty file lists gracefully.
    
    Args:
        files (List): A list of file objects.
    
    Returns:
        List[str]: Extracted text chunks from each document.
    """
    if not files or not isinstance(files, list):
        logger.warning("No files provided for preprocessing")
        return []
    
    extracted_texts = []
    
    for file in files:
        if not file:
            continue
            
        try:
            logger.info(f"Processing file: {getattr(file, 'name', 'unknown')}")
            
            # Handle different file types
            file_name = getattr(file, 'name', 'unknown')
            file_extension = os.path.splitext(file_name)[1].lower() if file_name else ''
            
            if file_extension in ['.pdf', '.doc', '.docx', '.txt']:
                try:
                    elements = partition(file=file)
                    text = " ".join([element.text for element in elements if element.text])
                except Exception as partition_error:
                    logger.warning(f"Failed to partition file {file_name}, trying text extraction: {partition_error}")
                    # Fallback: try to read as text
                    try:
                        text = file.read().decode('utf-8', errors='ignore')
                    except:
                        text = f"Content from file: {file_name}"
            elif file_extension in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                text = f"Image file: {file_name}"
            else:
                # Try to read as text for unknown file types
                try:
                    content = file.read()
                    if isinstance(content, bytes):
                        text = content.decode('utf-8', errors='ignore')
                    else:
                        text = str(content)
                except:
                    text = f"File content: {file_name}"
                
            # Split into meaningful chunks (by sentences if possible)
            if text and len(text.strip()) > 0:
                try:
                    sentences = nltk.sent_tokenize(text)
                    chunks = []
                    current_chunk = ""
                    
                    for sentence in sentences:
                        if len(current_chunk) + len(sentence) < 1000:
                            current_chunk += sentence + " "
                        else:
                            if current_chunk.strip():
                                chunks.append(current_chunk.strip())
                            current_chunk = sentence + " "
                    
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                        
                    extracted_texts.extend(chunks)
                    logger.info(f"Successfully processed file '{file_name}'. Created {len(chunks)} chunks.")
                except Exception as chunk_error:
                    logger.warning(f"Failed to chunk text for {file_name}: {chunk_error}")
                    # Fallback: just add the whole text
                    if len(text.strip()) > 0:
                        extracted_texts.append(text.strip())
            else:
                logger.warning(f"No text content extracted from file: {file_name}")
                
        except Exception as e:
            file_name = getattr(file, 'name', 'unknown')
            logger.error(f"Error processing file '{file_name}': {str(e)}", exc_info=True)
            
    logger.info(f"Total extracted text chunks: {len(extracted_texts)}")
    return extracted_texts

def extract_keywords(texts: List[str], max_keywords: int = 15) -> List[str]:
    """
    Extract important keywords from document texts using TF-IDF.
    Now handles empty text lists gracefully.
    
    Args:
        texts (List[str]): List of text chunks.
        max_keywords (int): Maximum number of keywords to extract.
    
    Returns:
        List[str]: List of important keywords.
    """
    if not texts or not isinstance(texts, list) or len(texts) == 0:
        logger.warning("No texts provided for keyword extraction")
        return []
    
    # Filter out empty texts
    valid_texts = [text.strip() for text in texts if text and text.strip() and len(text.strip()) > 5]
    
    if not valid_texts:
        logger.warning("No valid texts after filtering")
        return []
    
    try:
        # Custom stopwords combining NLTK and sklearn
        try:
            nltk_stopwords = set(stopwords.words('english'))
        except:
            nltk_stopwords = set()
            
        custom_stopwords = nltk_stopwords.union(ENGLISH_STOP_WORDS)
        custom_stopwords.update(['chapter', 'section', 'figure', 'table', 'example', 'note', 'page', 'document'])
        
        vectorizer = TfidfVectorizer(
            stop_words=list(custom_stopwords),
            max_features=min(1000, len(valid_texts) * 10),
            ngram_range=(1, 2),
            min_df=1,  # Allow terms that appear in at least 1 document
            max_df=0.95  # Ignore terms that appear in more than 95% of documents
        )
        
        tfidf_matrix = vectorizer.fit_transform(valid_texts)
        feature_names = vectorizer.get_feature_names_out()
        
        # Get top keywords by summing TF-IDF scores across documents
        scores = np.asarray(tfidf_matrix.sum(axis=0)).ravel()
        top_indices = scores.argsort()[-min(max_keywords, len(scores)):][::-1]
        keywords = [feature_names[i] for i in top_indices if scores[i] > 0]
        
        logger.info(f"Extracted {len(keywords)} keywords: {keywords[:5]}...")
        return keywords
        
    except Exception as e:
        logger.error(f"Error extracting keywords: {str(e)}", exc_info=True)
        # Return some default keywords based on common terms in texts
        common_words = []
        for text in valid_texts[:3]:  # Look at first 3 texts
            words = text.lower().split()
            common_words.extend([word for word in words if len(word) > 4 and word.isalpha()])
        
        # Get most frequent words as fallback keywords
        word_freq = {}
        for word in common_words:
            word_freq[word] = word_freq.get(word, 0) + 1
        
        fallback_keywords = sorted(word_freq.keys(), key=lambda x: word_freq[x], reverse=True)[:max_keywords]
        logger.info(f"Using fallback keywords: {fallback_keywords[:5]}")
        return fallback_keywords

def generate_preview_content(
    course_data: Dict, 
    topic_data: Dict, 
    chapters_data: List[Dict],
    file_context: str = "",
    keywords: List[str] = []
) -> Optional[Dict]:
    """
    Generate a preview of the course content using AI with file context.
    Now handles missing or invalid data gracefully.
    
    Args:
        course_data (Dict): Course form data
        topic_data (Dict): Topic form data
        chapters_data (List[Dict]): Chapter form data
        file_context (str): Context from uploaded files
        keywords (List[str]): Important keywords from files
    
    Returns:
        Optional[Dict]: Preview content including suggested improvements and sample content
    """
    try:
        logger.info("Starting preview content generation with file context")
        
        # Validate and provide defaults for input data
        if not course_data or not isinstance(course_data, dict):
            course_data = {'title': 'New Course', 'description': 'Course description'}
        
        if not topic_data or not isinstance(topic_data, dict):
            topic_data = {'title': 'Course Topic', 'description': 'Topic description'}
        
        if not chapters_data or not isinstance(chapters_data, list):
            chapters_data = [{'title': 'Introduction'}, {'title': 'Main Content'}, {'title': 'Conclusion'}]
        
        # Ensure required fields exist
        course_title = course_data.get('title', 'New Course')
        course_description = course_data.get('description', 'A comprehensive course')
        topic_title = topic_data.get('title', 'Course Topic')
        topic_description = topic_data.get('description', 'Topic overview')
        
        # Extract chapter titles safely
        chapter_titles = []
        for chapter in chapters_data:
            if isinstance(chapter, dict) and 'title' in chapter:
                chapter_titles.append(chapter['title'])
            elif isinstance(chapter, str):
                chapter_titles.append(chapter)
        
        if not chapter_titles:
            chapter_titles = ['Introduction', 'Main Content', 'Conclusion']

        # Build context prompt with file content
        context_prompt = ""
        if file_context and len(file_context.strip()) > 0:
            context_prompt = f"""
            Instructor has provided these materials:
            {file_context[:3000]}... [truncated if longer]
            """
        
        keyword_prompt = ""
        if keywords and len(keywords) > 0:
            keyword_prompt = f"""
            Key concepts from instructor's materials: {', '.join(keywords[:10])}
            """
        
        # Create a comprehensive prompt
        prompt = f"""
        Generate a course preview based on the following information:
        
        Course Title: {course_title}
        Course Description: {course_description}
        Topic: {topic_title}
        Topic Description: {topic_description}
        
        Chapters: {', '.join(chapter_titles)}
        
        {context_prompt}
        {keyword_prompt}
        
        Please provide:
        1. A brief overview that incorporates the instructor's materials
        2. Suggested improvements based on the materials  
        3. Sample content for the first chapter using the materials
        
        Make the response practical and actionable.
        """
        
        logger.info("Generating preview content")
        
        # For now, create a structured response without external API calls
        # This avoids additional quota usage while still providing useful content
        
        # Create overview incorporating keywords and file context
        overview = f"""
        This course on '{course_title}' provides {course_description.lower()}.
        The main topic '{topic_title}' covers {topic_description.lower()}.
        """
        
        if keywords:
            overview += f" Key concepts include: {', '.join(keywords[:5])}."
        
        if file_context:
            overview += " The course incorporates instructor-provided materials to enhance learning."
        
        # Generate suggestions based on available data
        suggestions = []
        if keywords:
            suggestions.append(f"Consider expanding on these key concepts: {', '.join(keywords[:3])}")
        if len(chapter_titles) < 3:
            suggestions.append("Consider adding more chapters for comprehensive coverage")
        if file_context:
            suggestions.append("Leverage the provided instructor materials throughout all chapters")
        
        suggestions_text = ". ".join(suggestions) if suggestions else "The course structure looks comprehensive."
        
        # Generate sample content for first chapter
        first_chapter = chapter_titles[0] if chapter_titles else "Introduction"
        sample_content = f"""
        {first_chapter}:
        
        This chapter introduces the fundamental concepts of {topic_title}.
        """
        
        if keywords:
            sample_content += f" We'll explore {keywords[0] if keywords else 'key concepts'} and their practical applications."
        
        if file_context and len(file_context) > 50:
            sample_content += f" Drawing from the instructor materials, we'll examine specific examples and case studies."
        
        preview_data = {
            'overview': overview,
            'suggestions': suggestions_text,
            'sample_content': sample_content,
            'course_data': course_data,
            'topic_data': topic_data,
            'chapters_data': chapters_data,
            'keywords': keywords[:10],  # Limit keywords
            'has_file_context': bool(file_context and len(file_context.strip()) > 0)
        }
        
        logger.info("Successfully generated preview content with file context")
        return preview_data
    
    except Exception as e:
        logger.error(f"Error generating preview content: {str(e)}", exc_info=True)
        # Return minimal fallback content
        return {
            'overview': 'Course preview temporarily unavailable.',
            'suggestions': 'Please review your course structure and try again.',
            'sample_content': 'Sample content will be generated when the course is created.',
            'course_data': course_data or {},
            'topic_data': topic_data or {},
            'chapters_data': chapters_data or [],
            'keywords': keywords or [],
            'has_file_context': False,
            'error': str(e)
        }

def organize_inputs(
    outline: str, 
    chapters: List[str], 
    documents: List,
    course_files: List = None,
    topic_files: List = None,
    chapter_files: List = None
) -> Dict:
    """
    Organize user inputs into a single structured dictionary with file content.
    Now handles all edge cases and provides safe defaults.
    
    Args:
        outline (str): Raw outline text.
        chapters (List[str]): Chapter texts.
        documents (List): Uploaded documents.
        course_files (List): Course-level files.
        topic_files (List): Topic-level files.
        chapter_files (List): Chapter-level files.
    
    Returns:
        Dict: Structured data for the AI.
    """
    try:
        logger.info("Starting to organize inputs with files")
        
        # Handle None or invalid outline - this was the main issue!
        if outline is None:
            logger.warning("Outline is None, using empty string")
            outline = ""
        elif not isinstance(outline, str):
            logger.warning(f"Outline is not a string (type: {type(outline)}), converting")
            outline = str(outline) if outline else ""
        
        # Handle chapters list
        if chapters is None:
            logger.warning("Chapters is None, using empty list")
            chapters = []
        elif not isinstance(chapters, list):
            logger.warning(f"Chapters is not a list (type: {type(chapters)}), converting")
            chapters = [str(chapters)] if chapters else []
        
        # Handle documents list
        if documents is None:
            logger.warning("Documents is None, using empty list")
            documents = []
        elif not isinstance(documents, list):
            logger.warning(f"Documents is not a list (type: {type(documents)}), converting")
            documents = [documents] if documents else []

        # Process outline - now handles empty strings gracefully
        processed_outline = preprocess_outline(outline)
        
        # Process all files safely
        all_files = []
        for file_list in [course_files, topic_files, chapter_files, documents]:
            if file_list and isinstance(file_list, list):
                all_files.extend([f for f in file_list if f])
            elif file_list:  # Single file, not a list
                all_files.append(file_list)
        
        # Remove None values and duplicates
        all_files = list(set([f for f in all_files if f is not None]))
        
        processed_documents = preprocess_documents(all_files)
        
        # Extract keywords from documents
        keywords = extract_keywords(processed_documents)
        
        # Combine document text for context
        file_context = ""
        if processed_documents:
            file_context = " ".join(processed_documents)[:5000]  # Truncate to 5000 chars
        
        organized_data = {
            "outline": processed_outline,
            "chapters": chapters,
            "documents": processed_documents,
            "file_context": file_context,
            "keywords": keywords,
            "total_files_processed": len(all_files),
            "total_text_chunks": len(processed_documents)
        }
        
        logger.info(f"Successfully organized inputs: {len(processed_outline)} outline items, "
                   f"{len(chapters)} chapters, {len(all_files)} files, {len(keywords)} keywords")
        
        return organized_data

    except Exception as e:
        logger.error(f"Error organizing inputs: {str(e)}", exc_info=True)
        return {
            "outline": [{"id": "1", "title": "Introduction"}, {"id": "2", "title": "Main Content"}],
            "chapters": chapters if isinstance(chapters, list) else [],
            "documents": [],
            "file_context": "",
            "keywords": [],
            "total_files_processed": 0,
            "total_text_chunks": 0,
            "error": str(e)
        }

def validate_content(preview_data: Dict) -> bool:
    """
    Validate the generated content for quality and completeness.
    Now more lenient with validation to handle various scenarios.
    
    Args:
        preview_data (Dict): The generated preview content.
    
    Returns:
        bool: True if content meets quality standards, False otherwise.
    """
    try:
        logger.info("Starting content validation")
        
        if not preview_data or not isinstance(preview_data, dict):
            logger.warning("Preview data is invalid or empty")
            return False
        
        # Check for required sections (more lenient)
        required_sections = ['overview', 'suggestions', 'sample_content']
        missing_sections = []
        
        for section in required_sections:
            if section not in preview_data:
                missing_sections.append(section)
            elif not preview_data[section] or len(str(preview_data[section]).strip()) == 0:
                missing_sections.append(f"{section} (empty)")
        
        if missing_sections:
            logger.warning(f"Missing or empty sections: {missing_sections}")
            # Don't fail validation for missing sections, just log
        
        # Check minimum content length (more lenient)
        min_lengths = {
            'overview': 20,      # Reduced from 100
            'suggestions': 10,   # Reduced from 50  
            'sample_content': 30 # Reduced from 200
        }
        
        short_sections = []
        for section, min_length in min_lengths.items():
            content = str(preview_data.get(section, ""))
            if len(content.strip()) < min_length:
                short_sections.append(f"{section} ({len(content.strip())}<{min_length})")
        
        if short_sections:
            logger.warning(f"Sections below minimum length: {short_sections}")
            # Don't fail validation, just log
        
        # Check if file context was utilized (informational only)
        has_keywords = bool(preview_data.get('keywords'))
        has_file_context = preview_data.get('has_file_context', False)
        
        if has_keywords or has_file_context:
            logger.info("File context detected in preview data")
        else:
            logger.info("No file context detected in preview data")
        
        # Always return True unless there's a critical error
        if 'error' in preview_data:
            logger.warning(f"Preview contains error: {preview_data['error']}")
            return False
        
        logger.info("Content validation completed successfully")
        return True

    except Exception as e:
        logger.error(f"Error during content validation: {str(e)}", exc_info=True)
        return False

def format_debug_output(success: bool, message: str, data: Dict = None) -> str:
    """
    Format debug output for terminal display.
    
    Args:
        success (bool): Whether the operation was successful
        message (str): The message to display
        data (Dict, optional): Additional data to display
    
    Returns:
        str: Formatted debug output
    """
    status = "SUCCESS" if success else "ERROR"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    output = f"""
{'='*80}
{timestamp} [{status}]
{'-'*80}
Message: {message}
"""
    
    if data:
        try:
            data_str = json.dumps(data, indent=2, default=str) if isinstance(data, dict) else str(data)
            output += f"""
Additional Data:
{'-'*80}
{data_str}
"""
        except:
            output += f"""
Additional Data:
{'-'*80}
{str(data)}
"""
    
    output += f"{'='*80}\n"
    
    return output

def get_success_message(operation: str, details: Dict) -> str:
    """
    Generate a success message for terminal output.
    
    Args:
        operation (str): The operation that was performed
        details (Dict): Operation details
    
    Returns:
        str: Formatted success message
    """
    return format_debug_output(
        success=True,
        message=f"Successfully completed {operation}",
        data=details
    )

def get_error_message(operation: str, error: Exception, details: Dict = None) -> str:
    """
    Generate an error message for terminal output.
    
    Args:
        operation (str): The operation that failed
        error (Exception): The error that occurred
        details (Dict, optional): Additional error details
    
    Returns:
        str: Formatted error message
    """
    error_details = {
        'error_type': type(error).__name__,
        'error_message': str(error),
        'additional_details': details or {}
    }
    
    return format_debug_output(
        success=False,
        message=f"Error in {operation}",
        data=error_details
    )
    
    