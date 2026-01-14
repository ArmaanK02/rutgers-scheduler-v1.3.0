# Scarlet Scheduler AI 🎓 (v1.3.0)

An intelligent course scheduling assistant for Rutgers University students. Unlike traditional manual schedulers, this system uses AI to understand natural language requests and builds mathematically valid schedules.

## What's New in v1.3.0

### 🔧 Major Fixes
- **Fixed Gemini API Model Names**: Updated to use actual available models (`gemini-2.0-flash-lite`, `gemini-2.0-flash`, etc.)
- **Exponential Backoff for Rate Limits**: No more rapid-fire 429 errors - the app now waits and retries intelligently
- **Request Throttling**: Built-in delays between API calls to avoid hitting rate limits
- **Working Model Cache**: Once a model works, it's remembered to reduce discovery overhead

### 🐛 Bug Fixes
- Fixed "All keys and models failed" error loop
- Reduced 403/404/429 API errors dramatically
- Better fallback to local analysis when AI is unavailable

## Features

- **Natural Language Understanding**: Ask for courses in plain English
  - "Schedule CS 111 and Calc 1"
  - "I'm a CS major, need 15 credits, no Fridays"
  - "What computer science courses should I take?"

- **Smart Scheduling**: 
  - Automatically detects and avoids time conflicts
  - Considers travel time between campuses
  - Checks prerequisites
  - Filters out closed sections

- **Course History Import**: Paste your Degree Navigator history to avoid scheduling courses you've already taken

- **Visual Schedule**: See your schedule as a calendar grid or list view

## Quick Start

### 1. Clone/Download the Project

```bash
unzip rutgers-scheduler-v1.3.0.zip
cd rutgers-scheduler-v1.3.0
```

### 2. Set Up Python Environment

```bash
# Create virtual environment (recommended)
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure API Key

Get a free Gemini API key:
1. Go to https://makersuite.google.com/app/apikey
2. Create a new API key
3. **Important**: Enable the Generative Language API at:
   https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com

Edit the `.env` file:
```
GEMINI_API_KEY=your-api-key-here
```

### 4. Test Your API Connection (NEW!)

```bash
python test_api.py
```

This will verify:
- Your API keys are valid
- The Generative Language API is enabled
- Which models are available
- Actual text generation works

### 5. Run the Application

```bash
python app.py
```

Open your browser to: **http://localhost:5000**

## API Troubleshooting

### Error: 403 Forbidden
The Generative Language API is not enabled for your project:
1. Go to [Google Cloud Console - Generative Language API](https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com)
2. Select your project (or create one)
3. Click **"ENABLE"**
4. Wait 1-2 minutes for activation

### Error: 429 Too Many Requests
This is handled automatically in v1.3.0! The app will:
1. Wait with exponential backoff (2s, 4s, 8s, etc.)
2. Retry the request
3. Fall back to local analysis if needed

### Error: 404 Model Not Found
The app will automatically try the next model. If all fail, it falls back to local pattern matching.

### Running the Rate Limit Test
```bash
python test_api.py --rate-test
```

## Configuration

Environment variables (in `.env`):
| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key | Required |
| `GEMINI_API_KEY_2` | Backup API key | Optional |
| `FLASK_ENV` | Environment mode | development |
| `PORT` | Server port | 5000 |
| `SEMESTER_CODE` | Rutgers semester code | 92025 (Fall 2025) |
| `CAMPUS_CODE` | Campus code | NB (New Brunswick) |

## Usage Examples

### Basic Scheduling
```
"Schedule 198:111 and 640:151"
"I need CS 111, Calc 1, and Expos"
```

### With Constraints
```
"Schedule CS 111 and Data Structures, no Fridays"
"I need 4 classes with mornings free"
```

### Major-Based Planning
```
"I'm a computer science major, what should I take?"
"Fill my schedule for an econ major"
```

### Import History
1. Click the import button (📥)
2. Go to Degree Navigator and copy your course list
3. Paste it into the dialog
4. The scheduler will now avoid your completed courses

## Project Structure

```
rutgers-scheduler-v1.3.0/
├── app.py                  # Main Flask application (v1.3.0 - fixed API)
├── test_api.py             # NEW: API connectivity tester
├── config.py               # Configuration management
├── scheduler_core.py       # Domain models (Course, Section, TimeSlot)
├── scheduler_strategies.py # Scheduling algorithm
├── data_adapter.py         # Rutgers API client
├── prerequisite_parser.py  # History parsing
├── pdf_scraper.py          # Catalog scraper
├── major_requirements.json # 129 majors, 163 minors, 88 certificates
├── requirements.txt        # Python dependencies
├── .env                    # API keys (DO NOT COMMIT)
├── templates/
│   └── index.html         # HTML template
└── static/
    ├── style.css          # Styles
    └── app.js             # Frontend JavaScript
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main chat interface |
| `/api/chat` | POST | Send scheduling request |
| `/api/parse_history` | POST | Import course history |
| `/api/clear_history` | POST | Clear imported history |
| `/api/health` | GET | Check system status |
| `/api/search` | GET | Search for courses |
| `/api/majors` | GET | List available majors |

## How the AI Works (v1.3.0)

1. **Model Selection**: Uses these models in order of preference:
   - `gemini-2.0-flash-lite` (fastest, best for free tier)
   - `gemini-2.0-flash`
   - `gemini-2.5-flash-lite`
   - `gemini-2.5-flash`

2. **Rate Limit Handling**:
   - Minimum 1 second between requests
   - Exponential backoff on 429 errors (2s → 4s → 8s → 16s → max 60s)
   - Automatic key rotation if multiple keys configured

3. **Fallback Strategy**:
   - If AI fails, uses local pattern matching
   - Local analysis handles: course codes, course names, day constraints
   - No AI needed for basic scheduling requests

## Development

### Running Tests
```bash
pytest tests/
```

### Checking API Status
```bash
curl http://localhost:5000/api/health
```

## License

MIT License - Feel free to use and modify for your own projects.

## Acknowledgments

- Rutgers University Schedule of Classes API
- Google Gemini API for AI features
- Font Awesome for icons
