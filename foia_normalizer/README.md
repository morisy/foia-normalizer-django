# FOIA Log Normalizer

A Django web application that standardizes FOIA (Freedom of Information Act) logs from various government agencies into the Standard FOIA Log Format (SFLF) specification.

## Features

- **File Upload**: Drag-and-drop interface supporting CSV, XLS, and XLSX files
- **Dual Processing Modes**:
  - **Manual Mode**: Review and confirm column/status mappings before processing
  - **AI Assist Mode**: Automatic processing using AI and synonym databases
- **Synonym Management**: Built-in synonym databases for column names and status values
- **OpenAI Integration**: AI-powered mapping for unmapped columns and statuses
- **Admin Interface**: Django admin for managing synonyms and viewing processing logs
- **Download Processed Files**: Download standardized CSV files
- **Processing Logs**: Detailed logs for troubleshooting and audit trails

## Quick Start

1. **Install Dependencies**:
   ```bash
   pip install django pandas openpyxl openai python-dotenv
   ```

2. **Setup Environment**:
   ```bash
   cp .env.example .env
   # Edit .env to add your OpenAI API key (optional)
   ```

3. **Run Migrations**:
   ```bash
   python manage.py migrate
   ```

4. **Create Superuser**:
   ```bash
   python manage.py createsuperuser
   ```

5. **Load Synonyms**:
   ```bash
   python manage.py load_synonyms --synonyms-path="../synonyms.txt" --status-synonyms-path="../status_synonyms.txt"
   ```

6. **Start Server**:
   ```bash
   python manage.py runserver
   ```

7. **Access Application**:
   - Main interface: http://localhost:8000/
   - Admin interface: http://localhost:8000/admin/

## Standard FOIA Log Format (SFLF)

The application normalizes uploaded logs to match SFLF v1.5.0 specification with these columns:

- **request id**: Unique identifier for each request
- **requester**: Name of the person/entity making the request
- **requester organization**: Organization affiliation (if applicable)
- **subject**: Brief description of the request
- **date requested**: Date the request was submitted
- **date perfected**: Date the agency determined the request was complete
- **date completed**: Date the request was resolved
- **status**: Current status (processed, done, rejected, etc.)
- **exemptions cited**: FOIA exemptions applied
- **fee category**: Fee category (commercial, educational, news media, etc.)
- **fee waiver**: Fee waiver status
- **fees charged**: Amount charged to requester
- **processed under privacy act**: Whether processed under Privacy Act

## Processing Modes

### Manual Mode
1. Upload file via drag-and-drop interface
2. Review suggested column mappings
3. Review suggested status mappings
4. Confirm or modify mappings
5. Process file and download normalized result

### AI Assist Mode
1. Upload file via drag-and-drop interface
2. File is automatically processed using:
   - Built-in synonym databases
   - OpenAI API for unmapped fields (if configured)
3. Download normalized result immediately

## Configuration

### Environment Variables
- `OPENAI_API_KEY`: OpenAI API key for AI-assisted mapping (optional)
- `DEBUG`: Set to `False` in production
- `SECRET_KEY`: Django secret key

### Synonym Files
The application uses two text files for mapping non-standard terms:

- `synonyms.txt`: Maps column names to SFLF standard columns
- `status_synonyms.txt`: Maps status values to SFLF standard statuses

Format example:
```
request id: #, request number, tracking number, control_number
requester: requestor, requester name, request from, name
```

## Admin Interface

Access `/admin/` to:
- View uploaded files and processing status
- Manage column and status synonyms
- View processing logs
- Monitor file processing history

## File Support

- **Formats**: CSV, XLS, XLSX
- **Size Limit**: 50MB per file
- **Encoding**: UTF-8 preferred for CSV files

## API Integration

The application integrates with OpenAI's API to suggest mappings for columns and statuses not found in the synonym databases. This is optional and requires an API key.

## Troubleshooting

1. **File Upload Issues**: Check file format and size limits
2. **Processing Errors**: Check processing logs in file detail view
3. **Missing Mappings**: Add synonyms via admin interface
4. **AI Mapping Issues**: Verify OpenAI API key configuration

## Development

To extend the application:

1. **Add New Synonym Sources**: Modify `SynonymLoader` in `utils.py`
2. **Custom Processing Logic**: Extend `FOIANormalizer` class
3. **Additional File Formats**: Add support in `load_file()` method
4. **UI Customization**: Modify templates in `normalizer/templates/`

## License

This project implements the Standard FOIA Log Format (SFLF) specification for standardizing government transparency data.