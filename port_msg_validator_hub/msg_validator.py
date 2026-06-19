import frappe
import json
import os
import xmltodict
from datetime import datetime
from frappe import _
import re
import jsonschema
from jsonschema import Draft7Validator


class UniversalMessageValidator:
    """
    Universal validator for any message type (MSG3501, MSG2701, etc.).
    Auto-detects message type and applies appropriate schema.
    All field parsing is case-insensitive.
    """
    
    # Mapping of message types to their schema files (use lowercase keys for normalized lookup)
    MESSAGE_TYPE_SCHEMA_MAP = {
        'msg03501': '[MSG3501]-message_schema.json',
        'msg02701': '[MSG2701]-message_schema.json',
        'msg00101': '[MSG101]-message_schema.json',
        # Add more message types as needed
    }
    
    # Default blocked ports (blacklist)
    BLOCKED_PORTS = ['XZiii']
    
    def __init__(self):
        self.detected_message_type = None
        self.schema = None
        self.schema_format = None  # 'json-schema' or 'custom'
        self.errors = {
            'structural_errors': [],
            'missing_required': [],
            'invalid_values': [],
            'type_errors': [],
            'length_errors': []
        }
        self.error_paths = []
    
    def _normalize_key(self, key):
        """Convert key to lowercase for case-insensitive comparison."""
        return str(key).lower() if key else key
    
    def _get_case_insensitive_value(self, data, key):
        """Get value from dict using case-insensitive key matching."""
        if not isinstance(data, dict):
            return None
        
        normalized_key = self._normalize_key(key)
        for actual_key, value in data.items():
            if self._normalize_key(actual_key) == normalized_key:
                return value
        return None
    
    def _get_all_keys_normalized(self, data):
        """Get all keys from dict with normalized versions."""
        if not isinstance(data, dict):
            return {}
        
        normalized = {}
        for key, value in data.items():
            normalized[self._normalize_key(key)] = value
        return normalized
    
    def _load_schema(self, message_type):
        """
        Load the appropriate message schema based on message type.
        
        Args:
            message_type (str): The message type (e.g., 'MSG03501')
            
        Returns:
            dict: The loaded schema or None
        """
        try:
            # Normalize message type
            normalized_type = self._normalize_key(message_type)
            
            # Get schema filename
            schema_filename = self.MESSAGE_TYPE_SCHEMA_MAP.get(normalized_type)
            if not schema_filename:
                frappe.log_error(
                    f"Unknown message type: {message_type}",
                    "UniversalMessageValidator._load_schema"
                )
                return None
            
            schema_path = os.path.join(
                os.path.dirname(__file__),
                schema_filename
            )
            
            if not os.path.exists(schema_path):
                frappe.log_error(
                    f"Schema file not found: {schema_filename}",
                    "UniversalMessageValidator._load_schema"
                )
                return None
            
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema = json.load(f)
            
            # Detect schema format
            if '$schema' in schema or 'properties' in schema:
                self.schema_format = 'json-schema'
            else:
                self.schema_format = 'custom'
            
            return schema
            
        except json.JSONDecodeError as e:
            frappe.log_error(
                f"Invalid JSON in schema file: {str(e)}", 
                "UniversalMessageValidator._load_schema"
            )
            return None
        except Exception as e:
            frappe.log_error(
                f"Error loading schema: {str(e)}", 
                "UniversalMessageValidator._load_schema"
            )
            return None
    
    def validate_message(self, xml_string):
        """
        Main validation method - validates any message type.
        Auto-detects message type and applies appropriate schema.
        Handles both 'header'/'_header' and 'Business_Data'/'XML' wrappers.
        
        Args:
            xml_string (str): The XML message to validate
            
        Returns:
            dict: Validation result with status and errors
        """
        try:
            # Step 1: Parse XML
            parsed_data = self._parse_xml(xml_string)
            if not parsed_data:
                return self._error_response("Failed to parse XML")
            
            # Step 2: Detect message type
            message_type = self._detect_message_type(parsed_data)
            if not message_type:
                return self._error_response("Could not detect message type")
            
            self.detected_message_type = message_type
            
            # Step 3: Load appropriate schema
            self.schema = self._load_schema(message_type)
            if not self.schema:
                return self._error_response(f"Schema for message type '{message_type}' not found")
            
            # Step 4: Validate from root using recursive property validator
            # Step 4: Coerce data and validate with jsonschema
            message_data = self._get_case_insensitive_value(parsed_data, 'message')
            if not message_data:
                return self._error_response("Root element 'message' not found")
            
            # Get the message schema definition
            message_schema = self.schema.get('properties', {}).get('message')
            if not message_schema:
                message_schema = self.schema
            
            # Step 4: Validate structure
            # We do two passes of coercion: 
            # 1. Clean data for jsonschema (omitting missing fields to trigger 'required' errors)
            # 2. Full data for display (including missing fields as None for UI highlighting)
            coerced_validation = self._coerce_data(message_data, message_schema, fill_missing=False)
            coerced_display = self._coerce_data(message_data, message_schema, fill_missing=True)
            
            # Step 4.2 Validate with jsonschema
            validator = Draft7Validator(message_schema)
            for error in validator.iter_errors(coerced_validation):
                self._handle_jsonschema_error(error)
            
            # Step 4.3 Validate custom business rules (Port codes, etc.)
            self._validate_business_rules(coerced_validation)
            
            # Step 5: Return results
            result = self._format_response()
            if result['valid'] or coerced_display:
                result['coerced_data'] = coerced_display
                result['error_paths'] = self.error_paths
            return result
            
        except Exception as e:
            frappe.log_error(
                title="UniversalMessageValidator.validate_message error",
                message=f"Unexpected error in validate_message: {str(e)}\nInput XML: {xml_string[:500] if xml_string else None}"
            )
            return self._error_response(f"Validation failed: {str(e)}")
    
    def _detect_message_type(self, parsed_data):
        """
        Detect message type from parsed XML data.
        Looks for message_type field in header section (case-insensitive).
        Handles both 'header' and '_header' field names.
        
        Args:
            parsed_data (dict): Parsed XML data
            
        Returns:
            str: Detected message type or None
        """
        try:
            message = self._get_case_insensitive_value(parsed_data, 'message')
            if not isinstance(message, dict):
                return None
            
            # Try to find header (case-insensitive) - handles both 'header' and '_header'
            header = self._get_case_insensitive_value(message, 'header')
            if not isinstance(header, dict):
                # Try _header variant
                header = self._get_case_insensitive_value(message, '_header')
            
            if not isinstance(header, dict):
                return None
            
            # Try to find message_type (case-insensitive)
            message_type = self._get_case_insensitive_value(header, 'message_type')
            return message_type if message_type else None
            
        except Exception as e:
            frappe.log_error(
                f"Error detecting message type: {str(e)}",
                "UniversalMessageValidator._detect_message_type"
            )
            return None
    
    def _coerce_data(self, data, schema, fill_missing=False):
        """
        Recursively coerce data to match schema types and casing.
        Handles XML quirks like strings-as-numbers and case-insensitivity.
        """
        if not schema or not isinstance(schema, dict):
            return data
            
        # Handle "type" being a list
        prop_types = schema.get('type')
        if isinstance(prop_types, list):
            # Prefer non-null type if available
            prop_type = next((t for t in prop_types if t != 'null'), prop_types[0])
        else:
            prop_type = prop_types

        if prop_type == 'object':
            if not isinstance(data, dict):
                # xmltodict makes duplicated tags a list
                if isinstance(data, list) and data:
                    data = data[0]
                else:
                    return data
            
            properties = schema.get('properties', {})
            coerced_dict = {}
            
            # Get normalized keys from data for case-insensitive lookup
            data_normalized = self._get_all_keys_normalized(data)
            
            for schema_key, schema_val in properties.items():
                norm_schema_key = self._normalize_key(schema_key)
                
                # Find the value in data
                val = None
                if norm_schema_key in data_normalized:
                    val = data_normalized[norm_schema_key]
                elif norm_schema_key == 'header' and '_header' in data_normalized:
                    val = data_normalized['_header']
                
                if val is not None:
                    coerced_dict[schema_key] = self._coerce_data(val, schema_val, fill_missing)
                elif fill_missing:
                    # For display purposes, show missing fields as None
                    coerced_dict[schema_key] = self._coerce_data(None, schema_val, fill_missing)
            
            return coerced_dict
            
        elif prop_type == 'array':
            items_schema = schema.get('items', {})
            if not isinstance(data, list):
                if data is not None:
                    data = [data]
                else:
                    data = []
            return [self._coerce_data(item, items_schema, fill_missing) for item in data]
            
        elif prop_type == 'integer':
            try:
                return int(data) if data is not None else None
            except (ValueError, TypeError):
                return data
        elif prop_type == 'number':
            try:
                return float(data) if data is not None else None
            except (ValueError, TypeError):
                return data
        elif prop_type == 'boolean':
            if isinstance(data, str):
                return data.lower() in ('true', '1', 'y', 'yes')
            return bool(data)
        
        return data

    def _handle_jsonschema_error(self, error):
        """Map jsonschema errors to existing error categories."""
        path_list = [str(p) for p in error.path]
        path = " -> ".join(path_list)
        
        # Store the path for highlighting in frontend
        self.error_paths.append(path_list)
        
        # If it's a 'required' error, the path points to the parent. 
        # We also want to highlight the specific missing field.
        if error.validator == 'required':
            # Extract missing field name from error message (e.g. "'Field' is a required property")
            match = re.search(r"'([^']+)' is a required property", error.message)
            if match:
                missing_field = match.group(1)
                self.error_paths.append(path_list + [missing_field])

        msg = f"Field '{path}': {error.message}"
        
        if error.validator == 'required':
            self.errors['missing_required'].append(msg)
        elif error.validator == 'type':
            self.errors['type_errors'].append(msg)
        elif error.validator in ('maxLength', 'minLength', 'maximum', 'minimum'):
            self.errors['length_errors'].append(msg)
        elif error.validator in ('enum', 'const', 'format', 'pattern'):
            self.errors['invalid_values'].append(msg)
        else:
            self.errors['invalid_values'].append(msg)
            
    def _validate_port_code(self, port_code):
        """
        Check if port code exists in SPS-Port doctype and is not blocked.
        Returns: (is_valid, error_message)
        """
        if not port_code:
            return False, "Port code is missing"
            
        # Get blocked ports from schema or use default
        blocked_ports = []
        if self.schema and isinstance(self.schema, dict):
            blocked_ports = self.schema.get('x-business-rules', {}).get('blocked_ports', self.BLOCKED_PORTS)
            
        if port_code in blocked_ports:
            return False, f"Port code '{port_code}' is blocked (International Water)"
            
        exists = frappe.db.exists("SPS-Port", {"name": port_code})
        if not exists:
            return False, f"Port code '{port_code}' does not exist in the system"
            
        return True, None

    def _validate_package_type(self, package_type_code):
        """
        Check if package type exists in Type of Package doctype.
        Returns: (is_valid, error_message)
        """
        if not package_type_code:
            return False, "Package type code is missing"
            
        exists = frappe.db.exists("Type of Package", {"code": package_type_code})
        if not exists:
            return False, f"Package type code '{package_type_code}' does not exist in the system"
            
        return True, None

    def _validate_business_rules(self, data, path_prefix=None):
        """
        Recursively validate custom business rules (like port code existence).
        """
        if path_prefix is None:
            path_prefix = []
            
        if isinstance(data, dict):
            # Port fields to validate (case-insensitive keys are handled by coercion, 
            # so we check the normalized schema keys)
            port_fields = ['Port_of_Loading', 'Port_of_Delivery', 'Port_of_Discharge']
            
            for key, value in data.items():
                current_path = path_prefix + [key]
                
                # Check if this key is a port field
                if key in port_fields and value:
                    is_valid, error_msg = self._validate_port_code(value)
                    if not is_valid:
                        path_str = " -> ".join(current_path)
                        self.error_paths.append(current_path)
                        self.errors['invalid_values'].append(
                            f"Field '{path_str}': {error_msg}"
                        )
                
                # Check if this key is a package type field
                if key == 'Type_of_Packages' and value:
                    is_valid, error_msg = self._validate_package_type(value)
                    if not is_valid:
                        path_str = " -> ".join(current_path)
                        self.error_paths.append(current_path)
                        self.errors['invalid_values'].append(
                            f"Field '{path_str}': {error_msg}"
                        )
                
                # Special check for Goods_Details uniqueness
                if key == 'Goods_Details' and isinstance(value, list):
                    seen_item_numbers = set()
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            item_num = item.get('Goods_Item_Number')
                            if item_num is not None:
                                if item_num in seen_item_numbers:
                                    item_path = current_path + [str(i), 'Goods_Item_Number']
                                    path_str = " -> ".join(item_path)
                                    self.error_paths.append(item_path)
                                    self.errors['invalid_values'].append(
                                        f"Field '{path_str}': Duplicate Goods_Item_Number '{item_num}' found within the same Goods_Details list"
                                    )
                                seen_item_numbers.add(item_num)
                
                # Special check for Cargo_Information BL_Number uniqueness
                if key == 'Cargo_Information' and isinstance(value, list):
                    seen_bl_numbers = set()
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            bl_num = item.get('BL_Number')
                            if bl_num is not None:
                                if bl_num in seen_bl_numbers:
                                    item_path = current_path + [str(i), 'BL_Number']
                                    path_str = " -> ".join(item_path)
                                    self.error_paths.append(item_path)
                                    self.errors['invalid_values'].append(
                                        f"Field '{path_str}': Duplicate BL_Number '{bl_num}' found within the same message"
                                    )
                                seen_bl_numbers.add(bl_num)
                
                # Recurse
                self._validate_business_rules(value, current_path)
                
        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_path = path_prefix + [str(i)]
                self._validate_business_rules(item, current_path)
    
    def _parse_xml(self, xml_string):
        """
        Parse and validate XML structure.
        
        Args:
            xml_string (str): The XML string to parse
            
        Returns:
            dict: Parsed XML data or None if parsing fails
        """
        try:
            if not xml_string or not xml_string.strip():
                self.errors['structural_errors'].append("XML string is empty")
                return None
            
            # Extract message XML
            cleaned_xml = self._extract_xml(xml_string)
            if not cleaned_xml:
                self.errors['structural_errors'].append("No valid XML structure found")
                return None
            
            # Validate well-formed XML
            is_valid, parse_error = self._is_well_formed_xml(cleaned_xml)
            if not is_valid:
                self.errors['structural_errors'].append(f"XML is not well-formed: {parse_error}")
                return None
            
            # Parse with xmltodict
            parsed = xmltodict.parse(cleaned_xml)
            return parsed
            
        except Exception as e:
            self.errors['structural_errors'].append(f"XML parsing error: {str(e)}")
            return None
    
    def _extract_xml(self, input_string):
        """Extract message XML from input string."""
        message_pattern = r'<message[^>]*>.*?</message>'
        match = re.search(message_pattern, input_string, re.DOTALL | re.IGNORECASE)
        
        if not match:
            self_closing_pattern = r'<message[^>]*\s*/>'
            match = re.search(self_closing_pattern, input_string, re.IGNORECASE)
        
        return match.group(0) if match else None
    
    def _is_well_formed_xml(self, xml_string):
        """Check if XML is well-formed and return error details."""
        try:
            import xml.etree.ElementTree as ET
            ET.fromstring(xml_string)
            return True, None
        except Exception as e:
            error_msg = str(e)
            if "&" in xml_string and "&amp;" not in xml_string:
                if "not well-formed" in error_msg.lower() or "invalid token" in error_msg.lower():
                    error_msg += " (Hint: Replace '&' with '&amp;')"
            return False, error_msg
    
        return False
    
    def _format_response(self):
        """Format validation response."""
        has_errors = any([
            self.errors['structural_errors'],
            self.errors['missing_required'],
            self.errors['invalid_values'],
            self.errors['type_errors'],
            self.errors['length_errors']
        ])
        
        return {
            'valid': not has_errors,
            'status': 'success' if not has_errors else 'validation_failed',
            'message': 'Message validation passed' if not has_errors else 'Message validation failed',
            'errors': self.errors if has_errors else None,
            'error_count': sum(len(v) for v in self.errors.values())
        }
    
    def _error_response(self, error_message):
        """Format error response."""
        return {
            'valid': False,
            'status': 'error',
            'message': error_message,
            'errors': self.errors,
            'error_count': sum(len(v) for v in self.errors.values())
        }




@frappe.whitelist()
def validate_message(xml_string):
    """
    Public method to validate any XML message type from frontend.
    Auto-detects message type and applies appropriate schema.
    All field parsing is case-insensitive.
    
    Args:
        xml_string (str): The XML message to validate (MSG03501, MSG02701, etc.)
        
    Returns:
        dict: Validation result with status and detailed errors, plus parsed_message if valid.
    """
    validator = UniversalMessageValidator()
    result = validator.validate_message(xml_string)
    
    # Include the parsed message structure for front-end display (even if invalid)
    if result.get('coerced_data'):
        result['parsed_message'] = result.get('coerced_data')
            
    return result


@frappe.whitelist()
def validate_message_structure_only(xml_string):
    """
    Validate only the structure of the message (quick validation).
    
    Args:
        xml_string (str): The XML message to validate
        
    Returns:
        dict: Validation result
    """
    validator = UniversalMessageValidator()
    try:
        parsed_data = validator._parse_xml(xml_string)
        if not parsed_data:
            return {
                'valid': False,
                'status': 'error',
                'message': 'XML parsing failed',
                'errors': validator.errors
            }
        
        if 'message' not in validator._get_all_keys_normalized(parsed_data):
            return {
                'valid': False,
                'status': 'error',
                'message': 'Root element "message" not found',
                'errors': validator.errors
            }
        
        return {
            'valid': True,
            'status': 'success',
            'message': 'XML structure is valid'
        }
    except Exception as e:
        return {
            'valid': False,
            'status': 'error',
            'message': f'Structure validation failed: {str(e)}'
        }



@frappe.whitelist()
def get_message_schema_for_xml(xml_string):
    """
    Detect message type from XML and return its schema.
    """
    validator = UniversalMessageValidator()
    parsed_data = validator._parse_xml(xml_string)
    if not parsed_data:
        return {'error': 'Failed to parse XML'}
    
    message_type = validator._detect_message_type(parsed_data)
    if not message_type:
        return {'error': 'Could not detect message type'}
    
    schema = validator._load_schema(message_type)
    if not schema:
        return {'error': f"Schema for message type '{message_type}' not found"}
    
    return {
        'message_type': message_type,
        'schema': schema
    }


@frappe.whitelist()
def get_message_schema(message_type):
    """
    Return the schema for a specific message type.
    Handles normalization (e.g. MSG2701-I -> MSG02701).
    """
    if not message_type:
        return {'error': 'Message type is required'}
        
    # Normalization logic
    normalized_type = str(message_type).strip().upper()
    
    # Remove subtype if present (e.g. MSG2701-I -> MSG2701)
    if '-' in normalized_type:
        normalized_type = normalized_type.split('-')[0]
        
    # Standardize format (e.g. MSG2701 -> MSG02701, MSG101 -> MSG00101)
    # The schema map expects 5 digits for the message number
    if normalized_type.startswith('MSG'):
        num_part = normalized_type[3:]
        if len(num_part) < 5:
            normalized_type = f"MSG{num_part.zfill(5)}"
        
    validator = UniversalMessageValidator()
    schema = validator._load_schema(normalized_type)
    if not schema:
        return {'error': f"Schema for message type '{normalized_type}' not found"}
    
    return {
        'message_type': normalized_type,
        'display_type': message_type,
        'schema': schema
    }
