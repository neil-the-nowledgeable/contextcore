"""
Lesson Retriever module for ContextCore.

Queries lessons from Tempo using TraceQL for agent work sessions,
enabling continuous learning from past experiences.
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Optional

from contextcore.learning.models import Lesson, LessonQuery, LessonCategory

__all__ = ['LessonRetriever']


class LessonRetriever:
    """Retrieves lessons from Tempo tracing backend using TraceQL queries."""
    
    def __init__(self, tempo_url: str = "http://localhost:3200") -> None:
        """Initialize the retriever with Tempo URL.
        
        Args:
            tempo_url: Base URL for Tempo API (default: http://localhost:3200)
        """
        self.tempo_url = tempo_url.rstrip('/')

    def retrieve(self, query: LessonQuery) -> List[Lesson]:
        """Retrieve lessons based on query parameters.
        
        Args:
            query: LessonQuery object with search criteria
            
        Returns:
            List of Lesson objects sorted by effectiveness_score descending
        """
        try:
            # Build TraceQL query string
            traceql = self._build_traceql(query)
            
            # Query Tempo and get raw results
            raw_results = self._query_tempo(traceql, query.time_range or "7d")
            
            # Parse results into Lesson objects
            lessons = self._parse_results(raw_results)
            
            # Apply confidence filtering
            min_confidence = query.min_confidence or 0.0
            lessons = [lesson for lesson in lessons if lesson.confidence >= min_confidence]
            
            # Sort by effectiveness_score descending
            lessons.sort(key=lambda x: x.effectiveness_score, reverse=True)
            
            # Return top max_results
            return lessons[:query.max_results or len(lessons)]
            
        except Exception as e:
            print(f"Error retrieving lessons: {e}")
            return []

    def get_lessons_for_file(self, file_path: str, project_id: Optional[str] = None, 
                           category: Optional[LessonCategory] = None) -> List[Lesson]:
        """Get lessons that apply to a specific file.
        
        Args:
            file_path: Path to the file
            project_id: Optional project ID filter
            category: Optional lesson category filter
            
        Returns:
            List of relevant lessons
        """
        query = LessonQuery(
            project_id=project_id,
            file_pattern=file_path,
            category=category,
            time_range="7d"
        )
        return self.retrieve(query)

    def get_lessons_for_task(self, task_type: str, project_id: Optional[str] = None) -> List[Lesson]:
        """Get lessons for a specific task type.
        
        Args:
            task_type: Type of task (testing, debugging, implementation, refactoring)
            project_id: Optional project ID filter
            
        Returns:
            List of relevant lessons
        """
        # Map task types to categories
        task_mapping = {
            "testing": LessonCategory.TESTING,
            "debugging": LessonCategory.DEBUGGING,
            "implementation": LessonCategory.IMPLEMENTATION,
            "refactoring": LessonCategory.REFACTORING
        }
        
        category = task_mapping.get(task_type)
        if not category:
            return []
            
        query = LessonQuery(
            project_id=project_id,
            category=category,
            time_range="7d"
        )
        return self.retrieve(query)

    def get_global_lessons(self, category: Optional[LessonCategory] = None, 
                         min_confidence: float = 0.9) -> List[Lesson]:
        """Get global lessons across all projects.
        
        Args:
            category: Optional lesson category filter
            min_confidence: Minimum confidence threshold (default: 0.9)
            
        Returns:
            List of high-confidence global lessons
        """
        query = LessonQuery(
            category=category,
            time_range="7d",
            min_confidence=min_confidence
        )
        return self.retrieve(query)

    def _build_traceql(self, query: LessonQuery) -> str:
        """Build TraceQL query string from LessonQuery object.
        
        Args:
            query: LessonQuery object with search criteria
            
        Returns:
            TraceQL query string in format "{ condition1 && condition2 && ... }"
        """
        conditions = []
        
        # Always filter for lesson insights
        conditions.append('span.insight.type = "lesson"')
        
        # Add project filter or include global lessons
        if query.project_id:
            conditions.append(f'(resource.project.id = "{query.project_id}" || resource.project.id = "global")')
        
        # Add category filter
        if query.category:
            conditions.append(f'span.insight.category = "{query.category.value}"')
            
        # Add file pattern regex matching
        if query.file_pattern:
            # Escape special regex characters in file path
            escaped_pattern = query.file_pattern.replace(".", r"\.")
            conditions.append(f'span.lesson.applies_to =~ ".*{escaped_pattern}.*"')
        
        return "{ " + " && ".join(conditions) + " }"

    def _query_tempo(self, traceql: str, time_range: str) -> List[dict]:
        """Execute TraceQL query against Tempo API.
        
        Args:
            traceql: TraceQL query string
            time_range: Time range string (e.g., "7d", "1h")
            
        Returns:
            List of trace dictionaries from Tempo response
        """
        try:
            # Parse time range to get start/end timestamps
            start_time, end_time = self._parse_time_range(time_range)
            
            # Build API request URL
            params = {
                'q': traceql,
                'start': str(int(start_time.timestamp() * 1000)),  # Convert to milliseconds
                'end': str(int(end_time.timestamp() * 1000))
            }
            
            url = f"{self.tempo_url}/api/search?" + urllib.parse.urlencode(params)
            
            # Execute HTTP request
            with urllib.request.urlopen(url) as response:
                result = json.loads(response.read())
                return result.get('traces', [])
                
        except urllib.error.HTTPError as e:
            print(f"HTTP error querying Tempo: {e}")
            return []
        except urllib.error.URLError as e:
            print(f"Network error querying Tempo: {e}")
            return []
        except json.JSONDecodeError as e:
            print(f"JSON decode error from Tempo response: {e}")
            return []
        except Exception as e:
            print(f"Unexpected error querying Tempo: {e}")
            return []

    def _parse_results(self, raw_results: List[dict]) -> List[Lesson]:
        """Parse raw Tempo results into Lesson objects.
        
        Args:
            raw_results: List of trace dictionaries from Tempo
            
        Returns:
            List of parsed Lesson objects
        """
        lessons = []
        
        for trace in raw_results:
            try:
                # Extract spans from trace
                spans = trace.get('spans', [])
                
                for span in spans:
                    # Extract lesson attributes
                    attributes = span.get('attributes', {})
                    
                    # Parse applies_to from JSON string
                    applies_to_str = attributes.get('applies_to', '[]')
                    try:
                        applies_to = json.loads(applies_to_str) if applies_to_str else []
                    except json.JSONDecodeError:
                        applies_to = [applies_to_str] if applies_to_str else []
                    
                    # Create Lesson object with all required fields
                    lesson = Lesson(
                        id=span.get('spanID', ''),
                        content=attributes.get('content', ''),
                        category=LessonCategory(attributes.get('category', 'GENERAL')),
                        confidence=float(attributes.get('confidence', 0.0)),
                        effectiveness_score=float(attributes.get('effectiveness_score', 0.0)),
                        applies_to=applies_to,
                        context=attributes.get('context', {}),
                        learned_at=datetime.fromisoformat(attributes.get('learned_at', datetime.now().isoformat())),
                        project_id=attributes.get('project_id')
                    )
                    
                    lessons.append(lesson)
                    
            except (KeyError, ValueError, TypeError) as e:
                print(f"Error parsing trace result: {e}")
                continue
        
        return lessons

    def _parse_time_range(self, time_range: str) -> tuple[datetime, datetime]:
        """Parse time range string into start and end datetime objects.
        
        Args:
            time_range: Time range string (e.g., "1h", "7d", "30d", "1m")
            
        Returns:
            Tuple of (start_time, end_time) datetime objects
        """
        end_time = datetime.now()
        
        try:
            if not time_range:
                # Default to 7 days
                start_time = end_time - timedelta(days=7)
            elif time_range.endswith('h'):
                # Hours
                hours = int(time_range[:-1])
                start_time = end_time - timedelta(hours=hours)
            elif time_range.endswith('d'):
                # Days
                days = int(time_range[:-1])
                start_time = end_time - timedelta(days=days)
            elif time_range.endswith('m'):
                # Months (approximate as 30 days)
                months = int(time_range[:-1])
                start_time = end_time - timedelta(days=30 * months)
            else:
                # Default fallback
                start_time = end_time - timedelta(days=7)
                
        except (ValueError, IndexError):
            # If parsing fails, default to 7 days
            start_time = end_time - timedelta(days=7)
        
        return start_time, end_time