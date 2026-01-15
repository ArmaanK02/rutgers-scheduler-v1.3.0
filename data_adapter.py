import json
import os
import requests
import time
from typing import List, Dict, Optional
from scheduler_core import Course, Section, TimeSlot
from config import get_config

Config = get_config()

class DataRepository:
    def __init__(self, data_file: str):
        self.data_file = data_file
        self.data_cache = []
        self.title_lookup = {}  # Cache for code -> title
        self.load_data()
        
    def load_data(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    self.data_cache = json.load(f)
                    # Populate title lookup from current semester data
                    for entry in self.data_cache:
                        code = f"{entry.get('subject')}:{entry.get('courseNumber')}"
                        # Also support full code with school if available in your data, usually it's just subject:number in this specific file structure?
                        # Let's assume standard Rutgers format is needed.
                        # If the json has 'school' field, use it.
                        school = entry.get('schoolCode', '01') # Default to 01 if missing, or handle broadly
                        full_code = f"{school}:{code}"
                        
                        raw_title = entry.get('title', '')
                        title = self._format_title(raw_title)
                        
                        self.title_lookup[code] = title
                        self.title_lookup[full_code] = title
            except Exception as e:
                print(f"Error loading data: {e}")
                self.data_cache = []
        else:
            print("Data file not found. Please scrape data first.")
            self.data_cache = []

    def fetch_historical_titles(self):
        """
        Fetches course titles from 2023-present to build a robust title lookup.
        Rutgers SOC API format: https://sis.rutgers.edu/soc/api/courses.json?year={year}&term={term}&campus=NB
        Terms: 1=Spring, 7=Summer, 9=Fall
        """
        # Seasons: 1=Spring, 7=Summer, 9=Fall
        seasons = [1, 7, 9]
        # Years to check
        years = [2023, 2024, 2025, 2026] 
        
        base_url = "https://sis.rutgers.edu/soc/api/courses.json"
        
        print("Building historical course title database...")
        
        for year in years:
            for term in seasons:
                # Skip future terms that probably don't exist yet (simple heuristic)
                if year > 2026: continue 
                
                print(f"Fetching {term}/{year}...")
                params = {
                    'year': year,
                    'term': term,
                    'campus': 'NB'
                }
                
                try:
                    resp = requests.get(base_url, params=params, timeout=5)
                    if resp.status_code == 200:
                        courses = resp.json()
                        for c in courses:
                            # Extract identifiers
                            school = c.get('schoolCode', '01')
                            subject = c.get('subject')
                            number = c.get('courseNumber')
                            raw_title = c.get('title')
                            
                            if school and subject and number and raw_title:
                                full_code = f"{school}:{subject}:{number}"
                                short_code = f"{subject}:{number}" # for loose matching
                                
                                title = self._format_title(raw_title)
                                
                                # Store in lookup
                                self.title_lookup[full_code] = title
                                self.title_lookup[short_code] = title
                    
                    # Be nice to the API
                    time.sleep(0.5)
                    
                except Exception as e:
                    print(f"Failed to fetch {term}/{year}: {e}")
        
        print(f"Historical database built. {len(self.title_lookup)} titles cached.")

    def _format_title(self, title: str) -> str:
        """Helper to title case the course name."""
        if not title: return ""
        # .title() is simple but sometimes messes up acronyms (e.g. 'Ii' instead of 'II')
        # A simple approach for now, can be made more robust if needed
        words = title.lower().split()
        return " ".join(w.capitalize() for w in words)

    def get_course_title(self, code: str) -> str:
        """
        Returns the title for a course code from the cache.
        Tries exact match first, then loose match (subject:number).
        """
        # Try exact match "01:198:111"
        if code in self.title_lookup:
            return self.title_lookup[code]
            
        # Try loose match "198:111" (strip school if present)
        parts = code.split(':')
        if len(parts) >= 2:
            short_code = f"{parts[-2]}:{parts[-1]}"
            if short_code in self.title_lookup:
                return self.title_lookup[short_code]
                
        return "Unknown Title"

    def get_courses(self, codes: List[str]) -> List[Course]:
        found_courses = []
        for code in codes:
            # Normalize code (remove school code if present for searching)
            # Input might be "198:111"
            parts = code.split(':')
            if len(parts) >= 2:
                subj = parts[-2]
                num = parts[-1]
                
                # Search in cache
                for entry in self.data_cache:
                    if str(entry['subject']) == subj and str(entry['courseNumber']) == num:
                        found_courses.append(self._map_to_domain(entry))
                        break
        return found_courses

    def search_courses(self, query: str) -> List[Course]:
        query = query.lower()
        results = []
        for entry in self.data_cache:
            title = entry.get('title', '').lower()
            code = f"{entry.get('subject')}:{entry.get('courseNumber')}"
            
            if query in title or query in code:
                results.append(self._map_to_domain(entry))
                
        return results

    def _map_to_domain(self, entry: Dict) -> Course:
        sections = []
        for sect in entry.get('sections', []):
            # Section constructor expects a Dict with specific keys
            section_data = {
                'number': sect.get('number', sect.get('sectionNumber', 'UNKNOWN')),
                'index': sect.get('index', '00000'),
                'instructors': sect.get('instructors', []),
                'meetingTimes': sect.get('meetingTimes', []),
                'openStatus': sect.get('openStatus', True)
            }
            sections.append(Section(section_data))
            
        return Course(
            title=entry.get('title', 'Unknown Title'),
            code=f"{entry.get('subject', '')}:{entry.get('courseNumber', '')}",
            sections=sections,
            prereqs=set(),  # Prerequisites would need to be loaded from another source
            credits=float(entry.get('credits', entry.get('creditHours', 3.0)))
        )

    def _time_to_minutes(self, hhmm: str) -> int:
        try:
            # Format usually "1230" or "0900"
            # Some might be "9:30 PM" - need robust parsing if source varies
            # Assuming Rutgers API 4-digit format or HH:MM
            hhmm = str(hhmm).replace(':', '')
            if len(hhmm) == 3: hhmm = '0' + hhmm # 900 -> 0900
            
            # Simple conversion for standard 24hr or 12hr... 
            # Rutgers API typically uses military 1730 etc? 
            # Let's assume standard military for now based on typical scrapers
            hours = int(hhmm[:2])
            mins = int(hhmm[2:])
            
            # Handle PM if needed? (Usually handled by API)
            return hours * 60 + mins
        except:
            return 0

class DataServiceFactory:
    _repo = None
    
    @staticmethod
    def get_repository():
        if DataServiceFactory._repo is None:
            DataServiceFactory._repo = DataRepository(Config.DATA_FILE_PATH)
        return DataServiceFactory._repo