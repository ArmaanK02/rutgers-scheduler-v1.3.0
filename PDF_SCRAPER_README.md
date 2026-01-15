# Advanced PDF Scraper - Usage Guide

## Overview

The new `pdf_scraper_advanced.py` uses Gemini AI to intelligently parse the Rutgers course catalog PDF and extract structured requirements including:

- **Core/Required Courses**: Mandatory courses for the major/minor
- **Electives**: With upper/lower level distinctions
- **Prerequisites**: Course dependencies
- **Complex Patterns**: "Choose 7 electives (4 upper level, 3 lower level)" type requirements

## Features

### 1. AI-Powered Parsing
- Uses Gemini AI to understand natural language requirements
- Extracts course codes, names, credits, and prerequisites
- Handles complex requirement structures

### 2. Structured Requirements Format
The scraper now outputs requirements in a structured JSON format:

```json
{
  "core_requirements": [
    {
      "code": "220:102",
      "name": "Introduction to Microeconomics",
      "credits": 3,
      "prerequisites": []
    }
  ],
  "electives": {
    "lower_level": {
      "required_count": 3,
      "courses": [...]
    },
    "upper_level": {
      "required_count": 4,
      "courses": [...]
    }
  },
  "total_credits": 45,
  "notes": "Additional requirements..."
}
```

### 3. Enhanced Progress Tracking
The updated progress dashboard now shows:
- Core requirements completion
- Elective progress by level (upper/lower)
- Prerequisites visualization
- Detailed course information

## Usage

### Basic Usage
```bash
python pdf_scraper_advanced.py rutgers-catalog-1746803554494.pdf
```

### Options
```bash
# Process only first 10 programs (for testing)
python pdf_scraper_advanced.py catalog.pdf --limit 10

# Use basic extraction (no AI, faster but less accurate)
python pdf_scraper_advanced.py catalog.pdf --no-ai
```

## How It Works

1. **Text Extraction**: Extracts all text from the PDF
2. **Program Identification**: Identifies all majors, minors, and certificates
3. **Section Extraction**: Finds the requirements section for each program
4. **AI Parsing**: Uses Gemini AI to parse complex requirement structures
5. **Structured Output**: Saves structured requirements to `major_requirements.json`

## Integration

The structured requirements are automatically used by:
- **Progress Dashboard**: Shows detailed progress with core/elective breakdown
- **AI Recommendations**: Uses prerequisites and requirement structure for better suggestions
- **What-If Analysis**: Accurately tracks progress for different majors

## Improvements Made

### 1. Schedule Visualization
- Weekly calendar view with days as columns
- Course blocks with code, title, time, and campus
- Visual styling for better readability

### 2. AI Integration
- Course history is now properly used in recommendations
- AI checks prerequisites before suggesting courses
- Understands elective requirements (upper/lower level)

### 3. UI/UX Enhancements
- Thinking animation while AI processes
- Better schedule display format
- Enhanced progress tracker with structured requirements
- Prerequisites visualization

### 4. Data Adapter Improvements
- AI-powered PDF parsing
- Structured requirement extraction
- Prerequisite detection
- Elective categorization

## Next Steps

1. Run the advanced scraper on your PDF:
   ```bash
   python pdf_scraper_advanced.py rutgers-catalog-1746803554494.pdf --limit 5
   ```

2. Check the output in `major_requirements.json` to verify structured requirements

3. Test the progress dashboard with a major that has structured requirements

4. The system will automatically use structured requirements when available, with fallback to simple lists

## Notes

- The AI parsing takes time (about 1-2 seconds per program)
- Use `--limit` for testing to avoid processing all programs at once
- The scraper preserves existing program names and adds structured requirements
- If AI parsing fails, it falls back to basic course code extraction

