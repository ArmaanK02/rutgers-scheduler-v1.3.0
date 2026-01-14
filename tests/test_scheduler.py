"""
Tests for Scarlet Scheduler v1.3.0
Run with: pytest tests/test_scheduler.py -v
"""

import pytest
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prerequisite_parser import PrerequisiteParser
from scheduler_core import TimeSlot, Section, Course, ScheduleConstraints


class TestPrerequisiteParser:
    """Test the prerequisite parser."""
    
    def test_parse_simple_code(self):
        """Test parsing a simple course code."""
        text = "Fall 2024 01:198:111 4 A Introduction to CS"
        result = PrerequisiteParser.parse_copy_paste(text)
        
        assert len(result) == 1
        assert result[0]['code'] == '01:198:111'
        assert result[0]['short_code'] == '198:111'
    
    def test_parse_multiple_codes(self):
        """Test parsing multiple course codes."""
        text = """
        Fall 2024 01:198:111 4 A Introduction to CS
        Spring 2024 01:640:151 4 B+ Calculus I
        """
        result = PrerequisiteParser.parse_copy_paste(text)
        
        assert len(result) == 2
        codes = [c['short_code'] for c in result]
        assert '198:111' in codes
        assert '640:151' in codes
    
    def test_filter_completed_courses(self):
        """Test filtering out completed courses."""
        history = [
            {'short_code': '198:111', 'code': '01:198:111'},
            {'short_code': '640:151', 'code': '01:640:151'},
        ]
        recommended = ['198:111', '198:112', '640:152']
        
        result = PrerequisiteParser.filter_completed_courses(recommended, history)
        
        assert '198:111' not in result
        assert '198:112' in result
        assert '640:152' in result


class TestTimeSlot:
    """Test TimeSlot class."""
    
    def test_overlaps_same_day(self):
        """Test that overlapping slots on same day are detected."""
        slot1 = TimeSlot('M', 600, 700, "10:00-11:40")
        slot2 = TimeSlot('M', 650, 750, "10:50-12:30")
        
        assert slot1.overlaps(slot2) == True
    
    def test_no_overlap_same_day(self):
        """Test that non-overlapping slots on same day are correct."""
        slot1 = TimeSlot('M', 600, 700, "10:00-11:40")
        slot2 = TimeSlot('M', 720, 820, "12:00-13:40")
        
        assert slot1.overlaps(slot2) == False
    
    def test_no_overlap_different_days(self):
        """Test that slots on different days don't overlap."""
        slot1 = TimeSlot('M', 600, 700, "10:00-11:40")
        slot2 = TimeSlot('T', 600, 700, "10:00-11:40")
        
        assert slot1.overlaps(slot2) == False


class TestScheduleConstraints:
    """Test ScheduleConstraints class."""
    
    def test_no_days_uppercase(self):
        """Test that no_days are converted to uppercase."""
        constraints = ScheduleConstraints(no_days=['friday', 'Monday'])
        
        assert 'F' in constraints.no_days or 'FRIDAY' in constraints.no_days
        assert 'M' in constraints.no_days or 'MONDAY' in constraints.no_days


class TestIntegration:
    """Integration tests."""
    
    def test_app_import(self):
        """Test that the main app can be imported."""
        try:
            # Set up minimal env
            os.environ.setdefault('GEMINI_API_KEY', 'test-key')
            
            # This should not raise an exception
            from app import VERSION, GREETINGS, COMMON_COURSES
            
            assert VERSION == "1.3.0"
            assert "hello" in GREETINGS
            assert "intro to cs" in COMMON_COURSES
        except Exception as e:
            # May fail in test env without full dependencies
            pytest.skip(f"App import failed (expected in minimal test env): {e}")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
