# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Django web application for community-driven normalization of FOIA (Freedom of Information Act) logs from various government agencies into the Standard FOIA Log Format (SFLF) v1.5.0. The application uses a submission queue system where contributors upload files for AI-assisted manual review, then authenticated moderators approve or reject submissions.

## Common Development Commands

```bash
# Install dependencies
pip install django pandas difflib

# Database operations
python manage.py migrate
python manage.py createsuperuser

# Load synonym mappings (required for processing)
python manage.py load_synonyms --synonyms-path="../synonyms.txt" --status-synonyms-path="../status_synonyms.txt"

# Run development server
python manage.py runserver
```

## Architecture Overview

### Core Submission Flow
1. **Upload**: Users upload FOIA log files with optional username/email for attribution
2. **AI-Assisted Review**: System uses statistical methods to suggest column/status mappings
3. **Manual Review**: Users review and confirm AI suggestions before submission
4. **Submission Queue**: Submissions enter a pending queue for moderator review
5. **Approval/Rejection**: Authenticated users can approve or reject submissions
6. **Public Access**: Only approved submissions are publicly visible and downloadable

### Key Components
- **`normalizer/models.py`**: 
  - `FOIAUpload`: Core model with submission status and attribution fields
  - `ContributorStats`: Tracks contributor statistics for leaderboard
  - `ColumnMapping`/`StatusMapping`: AI-suggested mappings with confidence scores
- **`normalizer/views.py`**: Community workflow views (upload, review, approval, leaderboard)
- **`normalizer/utils.py`**: Statistical analysis instead of OpenAI (fuzzy matching, pattern detection)
- **`normalizer/forms.py`**: Forms with optional attribution fields and approval workflow

### Statistical AI Methods (No OpenAI)
The application uses statistical methods for intelligent mapping:
- **Fuzzy string matching** using `difflib.SequenceMatcher`
- **Keyword pattern matching** for common FOIA log terms
- **Statistical row analysis** to detect and remove problematic headers
- **Confidence scoring** based on match quality

### Submission Queue System
- **Pending**: Newly submitted files await moderator review
- **Approved**: Publicly visible and downloadable files
- **Rejected**: Files rejected by moderators with reasons
- **Attribution**: Optional usernames credited on leaderboard
- **Privacy**: Email addresses kept private, used only for tracking

### SFLF Standard Columns
The application normalizes logs to these standard columns:
- request id, requester, requester organization, subject
- date requested, date perfected, date completed
- status, exemptions cited, fee category, fee waiver, fees charged
- processed under privacy act

## Key URLs
- `/` - Home page with upload interface and stats
- `/files/<id>/review/` - AI-assisted manual review interface
- `/files/<id>/status/` - Submission status page
- `/queue/` - Moderation queue (authenticated users only)
- `/queue/<id>/approve/` - Approve/reject interface
- `/leaderboard/` - Top contributors leaderboard

## Key Files to Understand
- `normalizer/utils.py`: Core `FOIANormalizer` class with statistical methods
- `normalizer/views.py`: Community workflow and moderation views
- `normalizer/models.py`: Submission queue and contributor tracking models
- `standard-foia-log-format.md`: SFLF v1.5.0 specification