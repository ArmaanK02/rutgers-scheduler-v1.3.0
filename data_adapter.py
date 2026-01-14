import json
import os
import re
import requests
from typing import List, Dict, Set
from scheduler_core import ICourseRepository, Course, Section
from config import get_config
import logging

logger = logging.getLogger(__name__)
Config = get_config()

class RutgersAPIClient:
    BASE_URL = "http://sis.rutgers.edu/soc/api/courses.json"

    @staticmethod
    def fetch_schedule(semester_code: str, campus: str, level: str) -> List[Dict]:
        if len(semester_code) >= 5:
            term = semester_code[0]
            year = semester_code[1:]
        else:
            term = "9" 
            year = "2025"

        params = {
            "year": year,
            "term": term,
            "campus": campus,
            "level": level
        }

        logger.info(f"Fetching live data from Rutgers API: {params}")
        try:
            response = requests.get(RutgersAPIClient.BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Successfully fetched {len(data)} courses.")
            return data
        except Exception as e:
            logger.error(f"Failed to fetch data from Rutgers API: {e}")
            return []

class JsonFileAdapter(ICourseRepository):
    def __init__(self, file_path: str = None):
        self.file_path = file_path or Config.DATA_FILE_PATH
        self.data_cache = self._initialize_data()

    def _initialize_data(self) -> List[Dict]:
        if os.path.exists(self.file_path):
            try:
                logger.info(f"Loading cached data from {self.file_path}")
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data: return data
            except json.JSONDecodeError:
                logger.warning("Local data file is corrupt. Re-fetching...")

        logger.info("Local cache missing or invalid. Triggering self-healing fetch...")
        return self.force_update()

    def force_update(self) -> List[Dict]:
        data = RutgersAPIClient.fetch_schedule(
            Config.SEMESTER_CODE,
            Config.CAMPUS_CODE,
            Config.LEVEL_CODE
        )

        if data:
            try:
                os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
                with open(self.file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f)
                logger.info(f"Saved fresh data to {self.file_path}")
            except Exception as e:
                logger.error(f"Could not save data to file: {e}")
        
        return data

    def _extract_prereqs(self, course_data: Dict) -> Set[str]:
        """
        Parses 'preReqNotes' and 'sectionNotes' to find course codes.
        Example text: "Any Course EQUAL or GREATER Than: (01:640:111 )"
        """
        prereqs = set()
        
        # Combine relevant text fields
        # Note: sectionNotes are inside sections list, but preReqNotes is at course level
        # We focus on course-level preReqNotes for general course requirements
        # Section-specific notes usually refine this or add restrictions like "Majors only"
        
        raw_text = str(course_data.get('preReqNotes', '')) + " " + str(course_data.get('courseNotes', ''))
        
        # Regex to find course codes like "01:198:111" or "198:111"
        # We normalize to "198:111" (Short Code) for comparison
        # Pattern: Optional 2 digits + colon, then 3 digits, colon, 3 digits
        matches = re.findall(r'(?:(\d{2}):)?(\d{3}):(\d{3})', raw_text)
        
        for m in matches:
            # m is tuple: (school, subject, course)
            # We reconstruct "Subject:Course"
            short_code = f"{m[1]}:{m[2]}"
            prereqs.add(short_code)
            
        return prereqs

    def get_courses(self, course_codes: List[str]) -> List[Course]:
        found_courses = []
        target_codes = {code.strip().upper() for code in course_codes if code.strip()}
        
        for course_data in self.data_cache:
            subj = str(course_data.get('subject', ''))
            num = str(course_data.get('courseNumber', ''))
            full_code = f"{subj}:{num}"
            
            if full_code in target_codes:
                title = course_data.get('title', 'Unknown Course')
                sections_data = course_data.get('sections', [])
                sections = [Section(s) for s in sections_data]
                
                # Extract Prereqs
                prereqs = self._extract_prereqs(course_data)
                
                found_courses.append(Course(title, full_code, sections, prereqs))
                
                target_codes.remove(full_code)
                if not target_codes:
                    break
        
        return found_courses

    def search_courses(self, query: str) -> List[Course]:
        query = query.upper().strip()
        matches = []
        
        for course_data in self.data_cache:
            subj = str(course_data.get('subject', ''))
            title = str(course_data.get('title', '')).upper()
            
            if query == subj or query in title:
                full_code = f"{subj}:{str(course_data.get('courseNumber', ''))}"
                sections = [Section(s) for s in course_data.get('sections', [])]
                prereqs = self._extract_prereqs(course_data)
                matches.append(Course(course_data.get('title'), full_code, sections, prereqs))
                
                if len(matches) >= 20:
                    break
        
        return matches

class DataServiceFactory:
    @staticmethod
    def get_repository() -> ICourseRepository:
        return JsonFileAdapter()
