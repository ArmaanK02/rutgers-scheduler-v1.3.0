from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Set

# --- Domain Models ---

class TimeSlot:
    """Represents a specific meeting time."""
    def __init__(self, day: str, start_time: int, end_time: int, raw_time_str: str = "", campus: str = "", room: str = ""):
        self.day = day
        self.start_time = start_time # Minutes from midnight
        self.end_time = end_time     # Minutes from midnight
        self.raw_time_str = raw_time_str
        self.campus = campus
        self.room = room  # Building and room number

    def overlaps(self, other: 'TimeSlot') -> bool:
        if self.day != other.day:
            return False
        return max(self.start_time, other.start_time) < min(self.end_time, other.end_time)

    def __repr__(self):
        return f"{self.day} {self.raw_time_str} ({self.campus})"

class Section:
    """Represents a specific section of a course."""
    def __init__(self, section_data: Dict):
        self.section_number = section_data.get('number', 'UNKNOWN')
        self.index = section_data.get('index', '00000')
        self.instructors = section_data.get('instructors', [])
        self.raw_times = section_data.get('meetingTimes', [])
        # Extract campus from meeting times (usually consistent for a section)
        self.time_slots: List[TimeSlot] = self._parse_times(self.raw_times)
        self.open_status = section_data.get('openStatus', False)

    def _parse_times(self, meeting_times: List[Dict]) -> List[TimeSlot]:
        """Parses raw Rutgers time data into comparable TimeSlot objects."""
        slots = []
        for mt in meeting_times:
            if mt.get('meetingDay') is None:
                continue
            
            start_str = mt.get('startTime')
            end_str = mt.get('endTime')
            # Extract Campus Name (e.g. "LIVINGSTON", "BUSCH")
            campus = mt.get('campusName', mt.get('campusLocation', 'Unknown'))
            campus = campus.upper() if campus else 'UNKNOWN'
            
            if not start_str or not end_str:
                continue
            
            pm_code = mt.get('pmCode')
            start_minutes = self._convert_to_minutes(start_str, pm_code, is_start=True)
            end_minutes = self._convert_to_minutes(end_str, pm_code, is_start=False)
            
            # Handle edge case: if end < start, the class crosses noon
            # and end time should be in PM even if pmCode is 'A'
            if end_minutes < start_minutes:
                end_minutes += 12 * 60  # Add 12 hours

            # Extract room/building information
            room = mt.get('roomNumber', mt.get('room', ''))
            building = mt.get('buildingCode', mt.get('building', ''))
            location = f"{building} {room}".strip() if building or room else ""
            
            slots.append(TimeSlot(
                day=mt['meetingDay'],
                start_time=start_minutes,
                end_time=end_minutes, 
                raw_time_str=f"{start_str}-{end_str}",
                campus=campus,
                room=location
            ))
        return slots

    def _convert_to_minutes(self, time_str: str, pm_code: str = None, is_start: bool = True) -> int:
        """Helper to convert '1230' or '10:30' to minutes from midnight.
        
        Args:
            time_str: Time string like '1030' or '10:30'
            pm_code: 'A' for AM, 'P' for PM
            is_start: Whether this is start time (used for context)
        """
        try:
            time_str = time_str.replace(":", "")
            hours = int(time_str[:2])
            minutes = int(time_str[2:]) if len(time_str) > 2 else 0
            
            # Handle PM code
            if pm_code == 'P' and hours != 12:
                hours += 12
            elif pm_code == 'A' and hours == 12:
                # 12:XX AM is typically rare for classes; usually means noon
                # But in Rutgers data, 12:XX with pmCode='A' for end times
                # usually means 12:XX PM (crossing noon)
                # We handle this in _parse_times with the end < start check
                pass  # Keep hours as 12 for now; corrected in _parse_times
                
            return hours * 60 + minutes
        except:
            return 0

    def overlaps(self, other: 'Section') -> bool:
        for my_slot in self.time_slots:
            for other_slot in other.time_slots:
                if my_slot.overlaps(other_slot):
                    return True
        return False

class Course:
    """Represents a Course with multiple sections and prerequisites."""
    def __init__(self, title: str, code: str, sections: List[Section], prereqs: Set[str] = None, credits: float = 3.0):
        self.title = title
        self.code = code
        self.sections = sections
        self.prereqs = prereqs or set() # Set of codes like "01:640:111"
        self.credits = credits

    def __repr__(self):
        return f"{self.title} ({self.code})"

class ScheduleConstraints:
    """Holds user-defined constraints for the schedule."""
    def __init__(self, no_days: List[str] = None):
        self.no_days = [d.upper() for d in (no_days or [])] 

# --- Interfaces (Strategy Pattern) ---

class ISchedulingStrategy(ABC):
    @abstractmethod
    def generate_schedules(self, courses: List[Course], constraints: ScheduleConstraints = None) -> List[List[Section]]:
        pass

# --- Interfaces (Adapter Pattern) ---

class ICourseRepository(ABC):
    @abstractmethod
    def get_courses(self, course_codes: List[str]) -> List[Course]:
        pass
    
    @abstractmethod
    def search_courses(self, query: str) -> List[Course]:
        pass
