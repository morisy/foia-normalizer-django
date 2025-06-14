import pandas as pd
import os
from django.conf import settings
from .models import ColumnSynonym, StatusSynonym, ProcessingLog, ColumnMapping, StatusMapping
from openai import OpenAI
import json


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
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
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
        """Use AI to identify and remove problematic header/blank rows"""
        if not self.client or len(df) < 5:
            if not self.client:
                self.log_message('info', 'Skipping AI row cleaning - no OpenAI API key configured')
            return df
        
        try:
            # Get first 10 rows for analysis
            sample_rows = df.head(10).copy()
            
            # Convert to string representation for AI analysis
            sample_text = ""
            for i, row in sample_rows.iterrows():
                row_data = [str(val) if pd.notna(val) else "EMPTY" for val in row]
                sample_text += f"Row {i}: {' | '.join(row_data)}\n"
            
            # Limit sample text length to avoid token limits
            if len(sample_text) > 3000:
                sample_text = sample_text[:3000] + "..."
            
            prompt = f"""
            Analyze this FOIA log data and determine if any of the first rows should be removed.
            Look for:
            1. Header rows that aren't actual data
            2. Blank/empty rows  
            3. Summary rows or metadata
            4. Rows that don't contain actual FOIA request data
            
            Data sample:
            {sample_text}
            
            Return only a number indicating how many rows to skip from the top (0-9).
            If the data looks clean, return 0.
            Only return the number, nothing else.
            """
            
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
                temperature=0
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Try to extract a number from the response
            import re
            numbers = re.findall(r'\d+', response_text)
            if numbers:
                rows_to_skip = int(numbers[0])
            else:
                self.log_message('warning', f'AI returned non-numeric response: {response_text}')
                return df
            
            if 0 <= rows_to_skip <= 9 and rows_to_skip > 0:
                df_cleaned = df.iloc[rows_to_skip:].reset_index(drop=True)
                self.log_message('openai', f'AI suggested removing {rows_to_skip} problematic rows from top')
                return df_cleaned
            else:
                self.log_message('openai', 'AI determined no rows need to be removed')
                return df
                
        except Exception as e:
            self.log_message('error', f"AI row cleaning failed: {str(e)}. Continuing without row cleaning.")
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
                if any(col.startswith('Unnamed:') for col in df.columns):
                    self.log_message('warning', 'Detected missing headers, trying different header rows')
                    
                    # Try reading with header in row 1, 2, or 3
                    for header_row in [1, 2, 3]:
                        try:
                            test_df = pd.read_excel(file_path, header=header_row)
                            if not any(col.startswith('Unnamed:') for col in test_df.columns if pd.notna(col)):
                                df = test_df
                                self.log_message('info', f'Found headers in row {header_row}')
                                break
                        except:
                            continue
                    
                    # If still no good headers, try to infer from first few rows
                    if any(col.startswith('Unnamed:') for col in df.columns):
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
            
            # Use AI to clean problematic rows if available
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
            col_lower = col.lower().strip()
            
            # First try synonym lookup
            synonym = ColumnSynonym.objects.filter(synonym__iexact=col_lower).first()
            if synonym:
                mapped_col = synonym.standard_name
                confidence = 1.0
                self.log_message('info', f"Column '{col}' mapped to '{mapped_col}' via synonym")
            else:
                # Try AI mapping if available
                mapped_col, confidence = self._ai_map_column(col)
                if not mapped_col:
                    mapped_col = col  # Keep original if no mapping found
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
                # Try AI mapping if available
                mapped_status, confidence = self._ai_map_status(status_str)
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
    
    def _ai_map_column(self, column_name):
        """Use OpenAI to map column name"""
        if not self.client:
            return None, 0.0
        
        try:
            prompt = f"""
            Map the following column name to one of the Standard FOIA Log Format columns.
            
            Column name: "{column_name}"
            
            Standard SFLF columns:
            {', '.join(self.sflf_columns)}
            
            If the column doesn't match any standard column, return "unmapped".
            Return only the exact column name from the list above, or "unmapped".
            """
            
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0
            )
            
            result = response.choices[0].message.content.strip()
            confidence = 0.8  # AI mapping confidence
            
            if result == "unmapped" or result not in self.sflf_columns:
                return None, 0.0
            
            self.log_message('openai', f"AI mapped column '{column_name}' to '{result}'")
            return result, confidence
        
        except Exception as e:
            self.log_message('error', f"AI column mapping failed: {str(e)}")
            return None, 0.0
    
    def _ai_map_status(self, status_value):
        """Use OpenAI to map status value"""
        if not self.client:
            return None, 0.0
        
        try:
            prompt = f"""
            Map the following status value to one of the Standard FOIA Log Format statuses.
            
            Status value: "{status_value}"
            
            Standard SFLF statuses:
            {', '.join([s for s in self.sflf_statuses if s])} (or empty)
            
            If the status doesn't match any standard status, return "unmapped".
            Return only the exact status from the list above, or "unmapped".
            """
            
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0
            )
            
            result = response.choices[0].message.content.strip()
            confidence = 0.8  # AI mapping confidence
            
            if result == "unmapped" or result not in self.sflf_statuses:
                return None, 0.0
            
            self.log_message('openai', f"AI mapped status '{status_value}' to '{result}'")
            return result, confidence
        
        except Exception as e:
            self.log_message('error', f"AI status mapping failed: {str(e)}")
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
                'will_skip_columns': 0
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