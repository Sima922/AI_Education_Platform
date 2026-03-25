import requests
import logging
from typing import Dict, List, Optional
from urllib.parse import quote
import math
import re
from datetime import datetime, timezone

# Setup logging
logger = logging.getLogger(__name__)

class YouTubeError(Exception):
    """Custom exception for YouTube API errors."""
    pass

def get_youtube_api_key():
    """Get YouTube API key."""
    return "AIzaSyB8Efv8BUwYFJWC9IRHwiH_tLfP1mZt6VQ"

def fetch_youtube_videos(query: str, max_results: int = 8, keywords: List[str] = None) -> List[Dict]:
    """
    Fetch relevant YouTube videos with enhanced metadata and filtering.

    Args:
        query: Search query string
        max_results: Maximum number of videos to return (default: 8, min: 3, max: 12).
        keywords: List of keywords to enhance search

    Returns:
        List of dictionaries containing video information.
    """
    api_key = get_youtube_api_key()
    if not api_key:
        logger.warning("YouTube API key not available.")
        return _get_fallback_videos(query, max_results)

    # Ensure reasonable limits
    max_results = max(3, min(max_results, 12))
    
    try:
        # Build enhanced query
        enhanced_query = _build_search_query(query, keywords)
        
        # Search for videos
        search_params = {
            "part": "snippet",
            "q": enhanced_query,
            "type": "video",
            "maxResults": min(max_results * 2, 50),  # Get more to filter from
            "key": api_key,
            "relevanceLanguage": "en",
            "videoEmbeddable": "true",
            "safeSearch": "strict",
            "order": "relevance"
        }

        logger.info(f"Searching YouTube with query: {enhanced_query}")
        
        search_response = requests.get(
            "https://www.googleapis.com/youtube/v3/search", 
            params=search_params,
            timeout=10
        )
        search_response.raise_for_status()
        search_data = search_response.json()

        if "error" in search_data:
            logger.error(f"YouTube API error: {search_data['error']}")
            return _get_fallback_videos(query, max_results)

        if not search_data.get("items"):
            logger.warning(f"No videos found for query: {enhanced_query}")
            return _get_fallback_videos(query, max_results)

        # Extract video IDs
        video_ids = []
        for item in search_data["items"]:
            if "id" in item and "videoId" in item["id"]:
                video_ids.append(item["id"]["videoId"])

        if not video_ids:
            logger.warning("No valid video IDs found")
            return _get_fallback_videos(query, max_results)

        # Get detailed video information
        video_details = _get_video_details(video_ids[:max_results * 2], api_key)
        
        # Process and filter videos
        processed_videos = []
        for video_detail in video_details:
            try:
                processed_video = _process_video_data(video_detail, query, keywords)
                if processed_video and _is_suitable_educational_video(processed_video):
                    processed_videos.append(processed_video)
            except Exception as e:
                logger.warning(f"Error processing video {video_detail.get('id', 'unknown')}: {str(e)}")
                continue

        # Sort by relevance and return top results
        processed_videos.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        result = processed_videos[:max_results]
        
        logger.info(f"Successfully fetched {len(result)} videos for query: {query}")
        return result

    except requests.exceptions.RequestException as e:
        logger.error(f"YouTube API request failed: {e}")
        return _get_fallback_videos(query, max_results)
    except Exception as e:
        logger.error(f"Unexpected error fetching YouTube videos: {e}")
        return _get_fallback_videos(query, max_results)

def _build_search_query(query: str, keywords: List[str] = None) -> str:
    """Build an enhanced search query."""
    # Clean and enhance the base query
    enhanced_query = query.strip()
    
    # Add educational terms
    educational_terms = ["tutorial", "lesson", "explained", "introduction"]
    if not any(term in enhanced_query.lower() for term in educational_terms):
        enhanced_query += " tutorial"
    
    # Add keywords if provided
    if keywords:
        # Add up to 2 most relevant keywords
        for keyword in keywords[:2]:
            if keyword.lower() not in enhanced_query.lower():
                enhanced_query += f" {keyword}"
    
    return enhanced_query

def _get_video_details(video_ids: List[str], api_key: str) -> List[Dict]:
    """Get detailed information for a list of video IDs."""
    try:
        video_params = {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(video_ids),
            "key": api_key,
        }

        video_response = requests.get(
            "https://www.googleapis.com/youtube/v3/videos", 
            params=video_params,
            timeout=10
        )
        video_response.raise_for_status()
        video_data = video_response.json()

        if "error" in video_data:
            logger.error(f"YouTube API error getting video details: {video_data['error']}")
            return []

        return video_data.get("items", [])
    
    except Exception as e:
        logger.error(f"Error getting video details: {e}")
        return []

def _process_video_data(item: Dict, query: str, keywords: List[str] = None) -> Optional[Dict]:
    """Process raw YouTube API video data into our format."""
    try:
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})
        content_details = item.get("contentDetails", {})
        
        video_id = item.get("id", "")
        if not video_id:
            return None

        # Extract basic information
        title = snippet.get("title", "")
        description = snippet.get("description", "")
        
        if not title:  # Skip videos without titles
            return None

        # Parse duration
        duration_str = content_details.get("duration", "PT0S")
        duration_formatted = _parse_duration(duration_str)
        duration_seconds = _duration_to_seconds(duration_str)

        # Get statistics with defaults
        view_count = int(statistics.get("viewCount", 0))
        like_count = int(statistics.get("likeCount", 0))

        # Calculate relevance score
        relevance_score = _calculate_relevance_score({
            "title": title,
            "description": description,
            "view_count": view_count,
            "like_count": like_count,
            "duration_seconds": duration_seconds
        }, query, keywords)

        return {
            "title": title,
            "description": description[:500],  # Limit description length
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "source": f"https://www.youtube.com/watch?v={video_id}",  # Added for compatibility
            "embed_url": f"https://www.youtube.com/embed/{video_id}",
            "thumbnail": _get_best_thumbnail(snippet.get("thumbnails", {})),
            "duration": duration_formatted,
            "duration_seconds": duration_seconds,
            "view_count": view_count,
            "like_count": like_count,
            "published_at": snippet.get("publishedAt", ""),
            "channel_title": snippet.get("channelTitle", ""),
            "relevance_score": relevance_score,
            "video_type": "youtube"  # Added for compatibility
        }

    except Exception as e:
        logger.warning(f"Error processing video data: {e}")
        return None

def _get_best_thumbnail(thumbnails: Dict) -> str:
    """Get the highest quality thumbnail available."""
    for quality in ["maxres", "standard", "high", "medium", "default"]:
        if quality in thumbnails and "url" in thumbnails[quality]:
            return thumbnails[quality]["url"]
    return ""

def _parse_duration(duration_str: str) -> str:
    """Convert ISO 8601 duration to a readable format (MM:SS or HH:MM:SS)."""
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
    if not match:
        return "0:00"

    hours, minutes, seconds = match.groups()
    hours = int(hours or 0)
    minutes = int(minutes or 0)
    seconds = int(seconds or 0)
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"

def _duration_to_seconds(duration_str: str) -> int:
    """Convert ISO 8601 duration to total seconds."""
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
    if not match:
        return 0

    hours, minutes, seconds = match.groups()
    hours = int(hours or 0)
    minutes = int(minutes or 0)
    seconds = int(seconds or 0)
    
    return hours * 3600 + minutes * 60 + seconds

def _is_suitable_educational_video(video: Dict) -> bool:
    """Check if video appears to be suitable educational content."""
    try:
        duration_seconds = video.get("duration_seconds", 0)
        title = video.get("title", "").lower()
        channel = video.get("channel_title", "").lower()
        
        # Duration filter: 1 minute to 1 hour (more lenient)
        if not (60 <= duration_seconds <= 3600):
            return False
        
        # Check for educational indicators
        educational_indicators = [
            "tutorial", "lesson", "lecture", "learn", "explained", 
            "introduction", "guide", "how to", "basics", "fundamentals"
        ]
        
        # Educational terms in title
        if any(term in title for term in educational_indicators):
            return True
            
        # Educational channels
        educational_channels = [
            "university", "academy", "education", "school", "college",
            "learning", "tutorial", "khan", "coursera", "edx"
        ]
        if any(term in channel for term in educational_channels):
            return True
            
        # High-quality content indicators
        view_count = video.get("view_count", 0)
        if view_count > 10000:  # Has some popularity
            return True
            
        return False
        
    except Exception as e:
        logger.warning(f"Error checking video suitability: {e}")
        return True  # Default to including the video

def _calculate_relevance_score(video: Dict, query: str, keywords: List[str] = None) -> float:
    """Calculate relevance score based on multiple factors."""
    score = 0.0
    
    title = video.get("title", "").lower()
    description = video.get("description", "").lower()
    query_lower = query.lower()
    
    # Query match in title (highest weight)
    if query_lower in title:
        score += 50
    
    # Individual query words in title
    query_words = query_lower.split()
    title_word_matches = sum(1 for word in query_words if word in title)
    score += title_word_matches * 10
    
    # Query match in description
    if query_lower in description:
        score += 20
    
    # Keywords match
    if keywords:
        for keyword in keywords:
            if keyword.lower() in title:
                score += 15
            elif keyword.lower() in description:
                score += 10
    
    # View count factor (logarithmic to prevent domination)
    views = video.get("view_count", 0)
    if views > 0:
        score += min(math.log10(views), 10)
    
    # Like ratio factor
    likes = video.get("like_count", 0)
    if views > 0 and likes > 0:
        like_ratio = likes / views
        score += min(like_ratio * 1000, 20)  # Cap at 20 points
    
    # Duration preference (5-20 minutes gets bonus)
    duration_seconds = video.get("duration_seconds", 0)
    if 300 <= duration_seconds <= 1200:  # 5-20 minutes
        score += 10
    
    return score

def _get_fallback_videos(query: str, max_results: int) -> List[Dict]:
    """Return fallback videos when YouTube API is unavailable."""
    logger.info(f"Returning fallback videos for query: {query}")
    
    fallback_videos = []
    for i in range(min(max_results, 3)):
        fallback_videos.append({
            "title": f"Educational Video: {query} - Part {i+1}",
            "description": f"This is a placeholder for educational content about {query}. Please configure your YouTube API key to fetch real videos.",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Rick Roll as placeholder
            "source": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "embed_url": "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "thumbnail": "https://img.youtube.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
            "duration": "3:33",
            "duration_seconds": 213,
            "view_count": 1000000,
            "like_count": 10000,
            "published_at": "2023-01-01T00:00:00Z",
            "channel_title": "Educational Content",
            "relevance_score": 10.0,
            "video_type": "youtube"
        })
    
    return fallback_videos