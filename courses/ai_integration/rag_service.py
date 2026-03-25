import os
import google.generativeai as genai
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from django.conf import settings
from django.core.cache import cache
import logging
from typing import List, Dict, Any, Optional

# Configure Google Generative AI
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Initialize model for embeddings and text generation
embedding_model = "models/text-embedding-004"
text_model = genai.GenerativeModel("gemini-2.0-flash-exp")

logger = logging.getLogger(__name__)

def get_course_embeddings(course) -> Dict[str, Any]:
    """Generate embeddings for course content using Google's embedding model"""
    try:
        content_parts = [
            f"Course: {course.title}\nDescription: {course.description}"
        ]
        
        for chapter in course.chapter_set.all().order_by('order'):
            content_parts.append(
                f"Chapter {chapter.order}: {chapter.title}\n"
                f"Introduction: {chapter.introduction}\n"
                f"Content: {chapter.main_content}\n"
                f"Summary: {chapter.summary}"
            )
        
        content = "\n\n".join(content_parts)
        
        # Split into chunks (simplified - you may want to use more sophisticated chunking)
        chunk_size = 1000
        chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
        
        # Generate embeddings using Google's embedding model
        embeddings = []
        for chunk in chunks:
            try:
                result = genai.embed_content(
                    model=embedding_model,
                    content=chunk,
                    task_type="retrieval_document"
                )
                embeddings.append(result['embedding'])
            except Exception as e:
                logger.error(f"Error generating embedding for chunk: {e}")
                # Fallback: create zero vector if embedding fails
                embeddings.append([0.0] * 768)  # Default embedding size
        
        return {
            "chunks": chunks,
            "embeddings": embeddings
        }
        
    except Exception as e:
        logger.error(f"Error generating course embeddings: {e}")
        return {
            "chunks": [f"Course: {course.title}\nDescription: {course.description}"],
            "embeddings": [[0.0] * 768]
        }

def rag_query(course, question: str, conversation_history: List[Dict] = None) -> str:
    """Answer question using RAG approach with Google Generative AI"""
    if conversation_history is None:
        conversation_history = []
        
    try:
        # Get or create embeddings
        cache_key = f"course_embeddings_{course.id}"
        embeddings_data = cache.get(cache_key)
        
        if not embeddings_data:
            logger.info(f"Generating embeddings for course: {course.title}")
            embeddings_data = get_course_embeddings(course)
            cache.set(cache_key, embeddings_data, timeout=86400)  # Cache for 24h
        
        # Embed the question using Google's embedding model
        try:
            q_embedding_result = genai.embed_content(
                model=embedding_model,
                content=question,
                task_type="retrieval_query"
            )
            q_embedding = q_embedding_result['embedding']
        except Exception as e:
            logger.error(f"Error embedding question: {e}")
            # Fallback response if embedding fails
            return "I'm sorry, I'm having trouble processing your question right now. Please try again later."
        
        # Find relevant chunks using cosine similarity
        if embeddings_data["embeddings"] and q_embedding:
            try:
                similarities = cosine_similarity(
                    [q_embedding],
                    embeddings_data["embeddings"]
                )[0]
                
                # Get top 3 most relevant chunks
                top_indices = np.argsort(similarities)[-3:][::-1]
                context_chunks = [embeddings_data["chunks"][i] for i in top_indices]
                context = "\n\n".join(context_chunks)
                
                # Log similarity scores for debugging
                top_scores = [similarities[i] for i in top_indices]
                logger.info(f"Top similarity scores: {top_scores}")
                
            except Exception as e:
                logger.error(f"Error computing similarities: {e}")
                # Use all available context as fallback
                context = "\n\n".join(embeddings_data["chunks"])
        else:
            context = "\n\n".join(embeddings_data["chunks"])
        
        # Prepare conversation history for context
        history_context = ""
        if conversation_history:
            recent_history = conversation_history[-5:]  # Last 5 messages
            history_parts = []
            for msg in recent_history:
                role = "User" if msg.get("is_user", True) else "Assistant"
                history_parts.append(f"{role}: {msg.get('message', '')}")
            history_context = f"\n\nRecent Conversation:\n{chr(10).join(history_parts)}\n"
        
        # Create comprehensive prompt for Gemini
        prompt = f"""You are a helpful course assistant for the course "{course.title}".

Your role:
- Answer questions based ONLY on the provided course content
- If information is not available in the course content, politely say so
- Be concise, accurate, and helpful
- Maintain context from the conversation history when relevant

Course Content:
{context}
{history_context}

Student Question: {question}

Please provide a helpful answer based on the course content above."""
        
        # Generate response using Gemini
        response = text_model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=500,
                top_p=0.8,
                top_k=40
            )
        )
        
        return response.text.strip()
        
    except Exception as e:
        logger.error(f"Error in RAG query: {e}")
        return f"I apologize, but I'm experiencing technical difficulties. Please try asking your question again, or contact support if the problem persists."

def get_question_embedding(question: str) -> Optional[List[float]]:
    """Helper function to get embedding for a single question"""
    try:
        result = genai.embed_content(
            model=embedding_model,
            content=question,
            task_type="retrieval_query"
        )
        return result['embedding']
    except Exception as e:
        logger.error(f"Error getting question embedding: {e}")
        return None

def verify_rag_setup() -> bool:
    """Verify that the RAG system is properly configured"""
    try:
        # Test embedding generation
        test_result = genai.embed_content(
            model=embedding_model,
            content="This is a test.",
            task_type="retrieval_document"
        )
        
        # Test text generation
        test_response = text_model.generate_content("Hello, this is a test.")
        
        logger.info("RAG system setup verified successfully")
        return True
    except Exception as e:
        logger.error(f"RAG system setup failed: {e}")
        return False

def clear_course_embeddings_cache(course_id: int):
    """Clear cached embeddings for a specific course"""
    cache_key = f"course_embeddings_{course_id}"
    cache.delete(cache_key)
    logger.info(f"Cleared embeddings cache for course {course_id}")

def update_course_embeddings(course):
    """Force update embeddings for a course (useful when course content changes)"""
    logger.info(f"Updating embeddings for course: {course.title}")
    
    # Clear existing cache
    clear_course_embeddings_cache(course.id)
    
    # Generate new embeddings
    embeddings_data = get_course_embeddings(course)
    
    # Cache the new embeddings
    cache_key = f"course_embeddings_{course.id}"
    cache.set(cache_key, embeddings_data, timeout=86400)
    
    logger.info(f"Successfully updated embeddings for course: {course.title}")
    return embeddings_data

def search_similar_content(course, query: str, top_k: int = 5) -> List[Dict]:
    """Search for similar content within a course"""
    try:
        # Get embeddings
        cache_key = f"course_embeddings_{course.id}"
        embeddings_data = cache.get(cache_key)
        
        if not embeddings_data:
            embeddings_data = get_course_embeddings(course)
            cache.set(cache_key, embeddings_data, timeout=86400)
        
        # Embed the search query
        q_embedding_result = genai.embed_content(
            model=embedding_model,
            content=query,
            task_type="retrieval_query"
        )
        q_embedding = q_embedding_result['embedding']
        
        # Calculate similarities
        similarities = cosine_similarity(
            [q_embedding],
            embeddings_data["embeddings"]
        )[0]
        
        # Get top results
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        
        results = []
        for idx in top_indices:
            results.append({
                "content": embeddings_data["chunks"][idx],
                "similarity_score": similarities[idx],
                "chunk_index": idx
            })
        
        return results
        
    except Exception as e:
        logger.error(f"Error searching similar content: {e}")
        return []