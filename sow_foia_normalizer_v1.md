
# 📄 Scope of Work: FOIA Log Normalizer v1

## 🎯 Objective
Build a Django-based web application that allows users to upload FOIA/public records logs (in XLS, XLSX, or CSV format) and outputs normalized logs in the Standard FOIA Log Format (SFLF), using a combination of synonym files and OpenAI's API to assist in standardizing columns and request statuses.

## 🔖 Core Features

### 1. Upload System
- Users can upload files via a drag-and-drop interface (or fallback file input).
- Support XLS, XLSX, and CSV uploads.
- Validate files before accepting.
- Save uploaded files to local storage or Django’s default media system.

### 2. Processing Logic
- On upload, parse the log file using pandas or equivalent.
- Normalize column names using `synonyms.txt`.
- Normalize status values using `status_synonyms.txt`.
- For unmapped columns/statuses, query the OpenAI API to suggest mappings.
- Generate a normalized CSV following the SFLF spec.

### 3. Dual Modes
- **Manual Mode:**
  - Show preview of column mappings (original + mapped).
  - Allow user to edit incorrect mappings via dropdown UI.
  - Show preview of status normalization with ability to override.
- **AI Assist Mode:**
  - Automatically process multiple files on upload.
  - No human review.
  - Outputs downloadable standardized logs.

### 4. Output & Download
- After processing, output a downloadable CSV for each file.
- Store processed output temporarily on disk.

### 5. Admin Panel
- Use Django Admin to:
  - View uploaded files and processed status.
  - Manage synonyms (ColumnSynonym, StatusSynonym).
- Admin can add new mappings over time to improve future results.

### 6. Authentication
- Allow uploads without login (basic uploader mode).
- Admins must log in to access admin features.

### 7. UI/UX
- Clean, mobile-friendly Django template-based frontend.
- Drag-and-drop uploader with fallback.
- File list page showing uploaded and processed files with status and download link.
- Clear status messages and error handling.

## 🧱 Models

```python
class FOIAUpload(models.Model):
    file = models.FileField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    processed = models.BooleanField(default=False)
    output_file = models.FileField(null=True, blank=True)

class ColumnSynonym(models.Model):
    standard_name = models.CharField(max_length=255)
    synonym = models.CharField(max_length=255)

class StatusSynonym(models.Model):
    standard_status = models.CharField(max_length=255)
    synonym = models.CharField(max_length=255)
```

## 🛠️ Tools / Libraries
- Python 3.11+
- Django 4.x
- pandas
- openpyxl
- openai SDK
- Bootstrap 5 (optional for frontend layout)
- Dropzone.js (optional for drag-and-drop)
- SQLite (for dev/local)

## 📤 Inputs
- Raw FOIA log in XLS, XLSX, or CSV.
- `synonyms.txt` and `status_synonyms.txt` files.
- OpenAI API Key (provided via environment variable).

## 📥 Outputs
- Standardized CSV file matching SFLF spec.
- Mapping logs for troubleshooting (optional).
- Updated synonym entries based on corrections (optional).

## ⚙️ Configuration
- `.env` for secrets like `OPENAI_API_KEY`
- Configurable synonym source (text file or database)

## ✅ Acceptance Criteria
- Uploading and parsing of at least 3 test files (1 CSV, 1 XLSX, 1 wild-format).
- Normalized output matches SFLF.
- Unknown columns/statuses are correctly routed through OpenAI and results stored.
- Manual review UI allows column override and final confirmation.
- AI Assist mode processes batch files without interaction.
- Admin panel allows management of synonym mappings.

## 🗓️ Timeline
Deliver core working demo in **2 weeks**, with the following phased milestones:
1. File upload + basic parsing.
2. Synonym normalization.
3. OpenAI integration.
4. Manual review UI.
5. AI Assist mode.
6. Final polish + admin.
