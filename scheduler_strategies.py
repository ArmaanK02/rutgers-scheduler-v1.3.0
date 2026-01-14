from typing import List
from scheduler_core import ISchedulingStrategy, Course, Section, ScheduleConstraints
from config import get_config

Config = get_config()

class DeepSeekSchedulerStrategy(ISchedulingStrategy):
    
    STANDARD_TRAVEL_MINUTES = 40
    SHORT_TRAVEL_MINUTES = 30 # Busch <-> Livi

    def generate_schedules(self, courses: List[Course], constraints: ScheduleConstraints = None) -> List[List[Section]]:
        valid_schedules = []
        # Sort courses to try to place harder-to-schedule ones first (fewer sections)
        sorted_courses = sorted(courses, key=lambda c: len(c.sections))
        
        def backtrack(course_idx: int, current_schedule: List[Section]):
            if len(valid_schedules) >= Config.MAX_SCHEDULES: return
            if course_idx == len(sorted_courses):
                valid_schedules.append(list(current_schedule))
                return

            current_course = sorted_courses[course_idx]

            # --- PREREQUISITE CHECK (Same Semester Conflict) ---
            # We only check if we are trying to schedule a course AND its prereq in the SAME semester.
            # We do NOT check against history here (that is done in app.py filtering).
            for i, scheduled_section in enumerate(current_schedule):
                scheduled_course = sorted_courses[i]
                
                # Conflict: Scheduled course is a prereq for Current
                if scheduled_course.code in current_course.prereqs:
                    return 
                # Conflict: Current course is a prereq for Scheduled (rare but possible order)
                if current_course.code in scheduled_course.prereqs:
                    return

            for section in current_course.sections:
                if not section.open_status: continue 
                
                # Overlap & Travel Checks
                if self._has_issue(section, current_schedule): continue

                # Constraints
                if constraints and not self._satisfies_constraints(section, constraints): continue

                current_schedule.append(section)
                backtrack(course_idx + 1, current_schedule)
                current_schedule.pop()

        backtrack(0, [])
        return valid_schedules

    def _has_issue(self, new_section: Section, current_schedule: List[Section]) -> bool:
        """Checks for Time Overlap AND Travel Feasibility."""
        for existing_section in current_schedule:
            # 1. Direct Time Overlap (Using strictly parsed TimeSlot objects)
            if new_section.overlaps(existing_section): return True
            
            # 2. Travel Time Check
            if not self._check_travel(new_section, existing_section): return True
            
        return False
    
    def _check_travel(self, sec1: Section, sec2: Section) -> bool:
        """Returns True if travel is feasible (or days differ)."""
        for slot1 in sec1.time_slots:
            for slot2 in sec2.time_slots:
                if slot1.day != slot2.day: continue
                
                # Determine order based on parsed minutes
                first, second = (slot1, slot2) if slot1.end_time < slot2.start_time else (slot2, slot1)
                gap = second.start_time - first.end_time
                
                c1 = slot1.campus.upper()
                c2 = slot2.campus.upper()
                
                # Ignore Online/Same Campus
                if c1 == c2 or "ONLINE" in c1 or "ONLINE" in c2:
                    continue

                # Different Campuses
                is_pair_BL = ("BUSCH" in c1 and "LIV" in c2) or ("LIV" in c1 and "BUSCH" in c2)
                required_time = self.SHORT_TRAVEL_MINUTES if is_pair_BL else self.STANDARD_TRAVEL_MINUTES
                
                if gap < required_time:
                    return False # Fail
                    
        return True

    def _satisfies_constraints(self, section: Section, constraints: ScheduleConstraints) -> bool:
        for slot in section.time_slots:
            if slot.day.upper() in constraints.no_days: return False
        return True
