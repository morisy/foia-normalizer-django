import pandas as pd
import os
from django.conf import settings
from .models import ColumnSynonym, StatusSynonym, ProcessingLog, ColumnMapping, StatusMapping
import difflib
import re


class SynonymLoader:
    @staticmethod
    def load_synonyms_from_file(file_path, model_class):
        """Load synonyms from text file into database"""
        if not os.path.exists(file_path):
            return
        
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if ':' not in line:
                    continue
                
                standard_name, synonyms = line.split(':', 1)
                standard_name = standard_name.strip()
                
                for synonym in synonyms.split(','):
                    synonym = synonym.strip().strip('"').strip("'")
                    if synonym:
                        # Handle different field names for different models
                        if model_class == StatusSynonym:
                            model_class.objects.get_or_create(
                                standard_status=standard_name,
                                synonym=synonym
                            )
                        else:
                            model_class.objects.get_or_create(
                                standard_name=standard_name,
                                synonym=synonym
                            )


class FOIANormalizer:
    def __init__(self, upload_instance):
        self.upload = upload_instance
        self.sflf_columns = [
            'request id', 'requester', 'requester organization', 'subject',
            'date requested', 'date perfected', 'date completed', 'status',
            'exemptions cited', 'fee category', 'fee waiver', 'fees charged',
            'processed under privacy act', 'source', 'agency', 'time period of log'
        ]
        self.sflf_statuses = [
            'processed', 'appealing', 'fix', 'payment', 'lawsuit',
            'rejected', 'no_docs', 'done', 'partial', 'abandoned', ''
        ]
    
    def log_message(self, log_type, message):
        """Add a log entry for this upload"""
        ProcessingLog.objects.create(
            upload=self.upload,
            log_type=log_type,
            message=message
        )
    
    def clean_problematic_rows(self, df):
        """Use statistical methods to identify and remove problematic header/blank rows"""
        if len(df) < 5:
            return df
        
        try:
            # Analyze first 10 rows for patterns
            sample_rows = df.head(10).copy()
            rows_to_skip = 0
            
            for i in range(min(10, len(sample_rows))):
                row = sample_rows.iloc[i]
                
                # Check if row is mostly empty
                non_empty_count = row.notna().sum()
                if non_empty_count <= 1:
                    rows_to_skip = i + 1
                    continue
                
                # Check if row contains metadata patterns
                row_text = ' '.join(str(val) for val in row if pd.notna(val)).lower()
                metadata_patterns = ['generated on', 'report', 'page', 'total', 'summary', 
                                   'header', 'title', 'department', 'agency name']
                
                if any(pattern in row_text for pattern in metadata_patterns):
                    rows_to_skip = i + 1
                    continue
                
                # Check if row appears to be actual data (has dates, IDs, etc)
                has_date = bool(re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', row_text))
                has_id = bool(re.search(r'\b\d{4,}\b', row_text))  # 4+ digit numbers
                has_request_terms = any(term in row_text for term in ['request', 'foia', 'record'])
                
                if has_date or has_id or has_request_terms:
                    # This looks like real data, stop skipping
                    break
            
            if rows_to_skip > 0:
                df_cleaned = df.iloc[rows_to_skip:].reset_index(drop=True)
                self.log_message('info', f'Removed {rows_to_skip} problematic rows from top using statistical analysis')
                return df_cleaned
            else:
                self.log_message('info', 'No problematic rows detected')
                return df
                
        except Exception as e:
            self.log_message('error', f"Row cleaning failed: {str(e)}. Continuing without row cleaning.")
            return df

    def load_file(self):
        """Load the uploaded file into a pandas DataFrame"""
        file_path = self.upload.file.path
        file_ext = os.path.splitext(file_path)[1].lower()
        
        try:
            if file_ext == '.csv':
                df = pd.read_csv(file_path)
            elif file_ext in ['.xlsx', '.xls']:
                # Try reading normally first
                df = pd.read_excel(file_path)
                
                # If we get unnamed columns, try reading with header in different rows
                if any(str(col).startswith('Unnamed:') for col in df.columns):
                    self.log_message('warning', 'Detected missing headers, trying different header rows')
                    
                    # Try reading with header in row 1, 2, or 3
                    for header_row in [1, 2, 3]:
                        try:
                            test_df = pd.read_excel(file_path, header=header_row)
                            if not any(str(col).startswith('Unnamed:') for col in test_df.columns if pd.notna(col)):
                                df = test_df
                                self.log_message('info', f'Found headers in row {header_row}')
                                break
                        except:
                            continue
                    
                    # If still no good headers, try to infer from first few rows
                    if any(str(col).startswith('Unnamed:') for col in df.columns):
                        # Check if first row has meaningful text that could be headers
                        first_row = df.iloc[0]
                        if all(isinstance(val, str) or pd.isna(val) for val in first_row):
                            # Use first row as headers
                            new_columns = []
                            for i, val in enumerate(first_row):
                                if pd.notna(val) and isinstance(val, str) and val.strip():
                                    new_columns.append(val.strip())
                                else:
                                    new_columns.append(f'Column_{i+1}')
                            
                            df.columns = new_columns
                            df = df.iloc[1:].reset_index(drop=True)  # Remove header row from data
                            self.log_message('info', 'Used first data row as column headers')
                        else:
                            # This appears to be a data-only file, infer logical column names
                            # based on typical FOIA log structure
                            inferred_columns = []
                            num_cols = len(df.columns)
                            
                            # Common FOIA log patterns based on column count and data inspection
                            if num_cols >= 3:
                                # Look at the data to infer column purposes
                                sample_data = df.head(10)
                                used_names = set()
                                
                                for i, col in enumerate(df.columns):
                                    col_data = sample_data[col].dropna()
                                    inferred_name = None
                                    
                                    if i == 0 and (col_data.empty or all(pd.isna(val) or val == '' for val in col_data)):
                                        inferred_name = 'index'
                                    elif ('request_id' not in used_names and 
                                          any(str(val).replace('-', '').replace('_', '').isalnum() and 
                                              len(str(val)) < 20 for val in col_data)):
                                        # Short alphanumeric strings - likely request IDs
                                        inferred_name = 'request_id'
                                    elif ('requester' not in used_names and 
                                          any('(' in str(val) and ')' in str(val) for val in col_data)):
                                        # Contains parentheses - likely redacted names
                                        inferred_name = 'requester'  
                                    elif ('organization' not in used_names and 
                                          any(str(val).upper() == str(val) and len(str(val)) > 10 for val in col_data)):
                                        # All caps longer strings - likely organizations
                                        inferred_name = 'organization'
                                    elif ('subject' not in used_names and 
                                          any('RECORDS' in str(val).upper() or 'DOCUMENTS' in str(val).upper() 
                                              for val in col_data)):
                                        # Contains typical FOIA request language
                                        inferred_name = 'subject'
                                    elif ('date_requested' not in used_names and 
                                          any(hasattr(val, 'year') for val in col_data)):
                                        # Date columns
                                        inferred_name = 'date_requested'
                                    elif ('status_code' not in used_names and 
                                          all(len(str(val)) <= 3 and str(val).isalpha() for val in col_data)):
                                        # Short alphabetic codes - likely status
                                        inferred_name = 'status_code'
                                    
                                    # Ensure unique names
                                    if inferred_name and inferred_name not in used_names:
                                        inferred_columns.append(inferred_name)
                                        used_names.add(inferred_name)
                                    else:
                                        inferred_columns.append(f'column_{i+1}')
                                        used_names.add(f'column_{i+1}')
                            
                            # Apply inferred column names
                            if len(inferred_columns) == len(df.columns):
                                df.columns = inferred_columns
                                self.log_message('info', f'Inferred column names: {inferred_columns}')
                            else:
                                # Fallback to generic names
                                df.columns = [f'column_{i+1}' for i in range(len(df.columns))]
                                self.log_message('warning', 'Used generic column names')
            else:
                raise ValueError(f"Unsupported file format: {file_ext}")
            
            # Clean up column names
            df.columns = [str(col).strip() if pd.notna(col) else f'Column_{i+1}' 
                         for i, col in enumerate(df.columns)]
            
            # Clean problematic rows using statistical methods
            df = self.clean_problematic_rows(df)
            
            self.log_message('info', f"Loaded file with {len(df)} rows and {len(df.columns)} columns")
            self.log_message('info', f"Column names: {list(df.columns)}")
            return df
        
        except Exception as e:
            self.log_message('error', f"Error loading file: {str(e)}")
            raise
    
    def map_columns(self, df):
        """Map column names using synonyms and AI"""
        column_mappings = {}
        
        for col in df.columns:
            # Convert to string to handle integer column names
            col_str = str(col)
            col_lower = col_str.lower().strip()
            
            # First try synonym lookup
            synonym = ColumnSynonym.objects.filter(synonym__iexact=col_lower).first()
            if synonym:
                mapped_col = synonym.standard_name
                confidence = 1.0
                self.log_message('info', f"Column '{col}' mapped to '{mapped_col}' via synonym")
            else:
                # Try fuzzy matching
                mapped_col, confidence = self._fuzzy_map_column(col)
                if not mapped_col:
                    mapped_col = col_str  # Keep original if no mapping found
                    confidence = 0.0
                    self.log_message('warning', f"No mapping found for column '{col}'")
            
            column_mappings[col] = mapped_col
            
            # Store mapping in database
            ColumnMapping.objects.update_or_create(
                upload=self.upload,
                original_column=col,
                defaults={
                    'mapped_column': mapped_col,
                    'confidence': confidence,
                    'user_confirmed': False
                }
            )
        
        return column_mappings
    
    def map_statuses(self, df, status_column):
        """Map status values using synonyms and AI"""
        if status_column not in df.columns:
            return {}
        
        status_mappings = {}
        unique_statuses = df[status_column].dropna().unique()
        
        for status in unique_statuses:
            status_str = str(status).strip()
            status_lower = status_str.lower()
            
            # First try synonym lookup
            synonym = StatusSynonym.objects.filter(synonym__iexact=status_lower).first()
            if synonym:
                mapped_status = synonym.standard_status
                confidence = 1.0
                self.log_message('info', f"Status '{status}' mapped to '{mapped_status}' via synonym")
            else:
                # Try fuzzy matching
                mapped_status, confidence = self._fuzzy_map_status(status_str)
                if not mapped_status:
                    mapped_status = status_str  # Keep original if no mapping found
                    confidence = 0.0
                    self.log_message('warning', f"No mapping found for status '{status}'")
            
            status_mappings[status] = mapped_status
            
            # Store mapping in database
            StatusMapping.objects.update_or_create(
                upload=self.upload,
                original_status=status_str,
                defaults={
                    'mapped_status': mapped_status,
                    'confidence': confidence,
                    'user_confirmed': False
                }
            )
        
        return status_mappings
    
    def _fuzzy_map_column(self, column_name):
        """Use fuzzy matching to map column name"""
        # Convert to string if it's not already (handles integer column names)
        column_str = str(column_name)
        column_lower = column_str.lower().strip()
        
        # Direct keyword matching with confidence scores
        keyword_mappings = {
            'request id': ['id', 'number', 'tracking', 'control', 'case', 'ref'],
            'requester': ['name', 'requester', 'requestor', 'from', 'who'],
            'requester organization': ['org', 'company', 'affiliation', 'entity'],
            'subject': ['subject', 'description', 'request', 'topic', 'about'],
            'date requested': ['requested', 'received', 'submitted', 'date_req'],
            'date perfected': ['perfected', 'complete', 'perfection'],
            'date completed': ['completed', 'closed', 'resolved', 'finished'],
            'status': ['status', 'state', 'disposition', 'outcome'],
            'exemptions cited': ['exemption', 'withhold', 'redact', 'b('],
            'fee category': ['fee_cat', 'category', 'fee_type'],
            'fee waiver': ['waiver', 'fee_waiv', 'discount'],
            'fees charged': ['fee', 'cost', 'charge', 'amount', 'paid'],
            'processed under privacy act': ['privacy', 'privacy_act']
        }
        
        # First try exact keyword matching
        for sflf_col, keywords in keyword_mappings.items():
            for keyword in keywords:
                if keyword in column_lower:
                    confidence = 0.9 if keyword == column_lower else 0.7
                    self.log_message('info', f"Fuzzy matched column '{column_name}' to '{sflf_col}' (confidence: {confidence})")
                    return sflf_col, confidence
        
        # Try fuzzy string matching
        best_match = None
        best_ratio = 0
        
        for sflf_col in self.sflf_columns:
            ratio = difflib.SequenceMatcher(None, column_lower, sflf_col.lower()).ratio()
            if ratio > best_ratio and ratio > 0.6:  # 60% similarity threshold
                best_match = sflf_col
                best_ratio = ratio
        
        if best_match:
            confidence = best_ratio * 0.8  # Scale down confidence for fuzzy matches
            self.log_message('info', f"Fuzzy matched column '{column_name}' to '{best_match}' (confidence: {confidence:.2f})")
            return best_match, confidence
        
        return None, 0.0
    
    def _fuzzy_map_status(self, status_value):
        """Use fuzzy matching to map status value"""
        # Convert to string if it's not already
        status_str = str(status_value)
        status_lower = status_str.lower().strip()
        
        # Direct keyword mapping
        status_mappings = {
            'processed': ['processing', 'in process', 'pending', 'open', 'active'],
            'appealing': ['appeal', 'appealed', 'under appeal'],
            'fix': ['fix', 'clarification', 'need info', 'incomplete'],
            'payment': ['payment', 'fee', 'invoice', 'billing'],
            'lawsuit': ['lawsuit', 'litigation', 'court', 'legal'],
            'rejected': ['rejected', 'denied', 'reject', 'denial'],
            'no_docs': ['no docs', 'no records', 'no responsive', 'nothing found'],
            'done': ['done', 'complete', 'closed', 'fulfilled'],
            'partial': ['partial', 'partially', 'some records'],
            'abandoned': ['abandoned', 'withdrawn', 'cancelled', 'closed by requester']
        }
        
        # First try exact keyword matching
        for sflf_status, keywords in status_mappings.items():
            for keyword in keywords:
                if keyword in status_lower or status_lower in keyword:
                    confidence = 0.9 if keyword == status_lower else 0.7
                    self.log_message('info', f"Fuzzy matched status '{status_value}' to '{sflf_status}' (confidence: {confidence})")
                    return sflf_status, confidence
        
        # Try fuzzy string matching
        best_match = None
        best_ratio = 0
        
        for sflf_status in self.sflf_statuses:
            if not sflf_status:  # Skip empty status
                continue
            ratio = difflib.SequenceMatcher(None, status_lower, sflf_status.lower()).ratio()
            if ratio > best_ratio and ratio > 0.6:  # 60% similarity threshold
                best_match = sflf_status
                best_ratio = ratio
        
        if best_match:
            confidence = best_ratio * 0.8  # Scale down confidence for fuzzy matches
            self.log_message('info', f"Fuzzy matched status '{status_value}' to '{best_match}' (confidence: {confidence:.2f})")
            return best_match, confidence
        
        return None, 0.0
    
    def normalize_dataframe(self, df, column_mappings, status_mappings):
        """Apply mappings to create normalized DataFrame"""
        # Create a new dataframe with only SFLF columns that have data
        df_normalized = pd.DataFrame()
        
        # Map each SFLF column from the original data
        for sflf_col in self.sflf_columns:
            # Find which original column maps to this SFLF column
            source_col = None
            for orig_col, mapped_col in column_mappings.items():
                if mapped_col == sflf_col:
                    source_col = orig_col
                    break
            
            if source_col and source_col in df.columns:
                # Check if the source column has any meaningful data
                source_data = df[source_col]
                non_empty_count = source_data.count()  # Counts non-null values
                non_whitespace_count = sum(1 for val in source_data if pd.notna(val) and str(val).strip())
                
                # Only include column if it has meaningful data
                if non_empty_count > 0 and non_whitespace_count > 0:
                    # Copy data from source column
                    df_normalized[sflf_col] = df[source_col]
                    
                    # Apply status mappings if this is the status column
                    if sflf_col == 'status':
                        df_normalized[sflf_col] = df_normalized[sflf_col].map(
                            lambda x: status_mappings.get(x, x) if pd.notna(x) else x
                        )
                    
                    self.log_message('info', f'Included column "{sflf_col}" with {non_whitespace_count} data values')
                else:
                    self.log_message('info', f'Skipped empty column "{sflf_col}" (mapped from "{source_col}")')
            # Note: We no longer create empty columns for unmapped SFLF columns
        
        # Add metadata fields from upload instance
        self._add_metadata_columns(df_normalized)
        
        return df_normalized
    
    def _add_metadata_columns(self, df_normalized):
        """Add SFLF metadata columns from upload instance"""
        if hasattr(self.upload, 'source') and self.upload.source:
            df_normalized['source'] = self.upload.source
            self.log_message('info', 'Added source metadata column')
            
        if hasattr(self.upload, 'agency') and self.upload.agency:
            df_normalized['agency'] = self.upload.agency
            self.log_message('info', 'Added agency metadata column')
            
        if (hasattr(self.upload, 'time_period_start') and self.upload.time_period_start and
            hasattr(self.upload, 'time_period_end') and self.upload.time_period_end):
            # Format time period as a readable string
            time_period = f"{self.upload.time_period_start} to {self.upload.time_period_end}"
            df_normalized['time period of log'] = time_period
            self.log_message('info', 'Added time period metadata column')
    
    def generate_preview_data(self, df, column_mappings, max_rows=5):
        """Generate preview data showing original vs mapped columns with sample data"""
        preview_data = {
            'column_mappings': [],
            'sample_data': [],
            'statistics': {
                'total_rows': len(df),
                'total_columns': len(df.columns),
                'mapped_columns': len([m for m in column_mappings.values() if m != m.lower().replace(' ', '_')]),
                'empty_rows': df.isnull().all(axis=1).sum(),
                'will_include_columns': 0,
                'will_skip_columns': 0,
                'unmapped_columns': len([m for m in column_mappings.values() if m == column_mappings.get(m, m)])
            }
        }
        
        # Column mapping preview with data analysis
        for original_col in df.columns:
            mapped_col = column_mappings.get(original_col, original_col)
            
            # Get sample values from this column
            sample_values = df[original_col].dropna().head(3).tolist()
            sample_values = [str(val)[:50] + '...' if len(str(val)) > 50 else str(val) 
                           for val in sample_values]
            
            # Check if column will be included in final output
            non_empty_count = df[original_col].count()
            non_whitespace_count = sum(1 for val in df[original_col] if pd.notna(val) and str(val).strip())
            will_include = non_empty_count > 0 and non_whitespace_count > 0
            
            if will_include:
                preview_data['statistics']['will_include_columns'] += 1
            else:
                preview_data['statistics']['will_skip_columns'] += 1
            
            preview_data['column_mappings'].append({
                'original': original_col,
                'mapped': mapped_col,
                'samples': sample_values,
                'is_mapped': mapped_col != original_col,
                'non_empty_count': df[original_col].count(),
                'will_include': will_include,
                'skip_reason': 'Empty column - will be omitted' if not will_include else None
            })
        
        # Sample data preview
        sample_rows = df.head(max_rows)
        for i, (idx, row) in enumerate(sample_rows.iterrows()):
            row_data = {}
            for col in df.columns:
                value = row[col]
                if pd.isna(value):
                    display_value = "(empty)"
                else:
                    str_val = str(value)
                    display_value = str_val[:100] + '...' if len(str_val) > 100 else str_val
                
                row_data[col] = {
                    'original': display_value,
                    'mapped_column': column_mappings.get(col, col)
                }
            
            preview_data['sample_data'].append({
                'row_number': idx + 1,
                'data': row_data
            })
        
        return preview_data
    
    def save_normalized_file(self, df_normalized):
        """Save normalized DataFrame as CSV"""
        output_filename = f"normalized_{os.path.splitext(self.upload.filename)[0]}.csv"
        output_path = os.path.join(settings.MEDIA_ROOT, 'outputs', output_filename)
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        df_normalized.to_csv(output_path, index=False)
        
        # Update upload record
        self.upload.output_file.name = f'outputs/{output_filename}'
        self.upload.processed = True
        self.upload.save()
        
        self.log_message('info', f"Normalized file saved as {output_filename}")
        return output_path