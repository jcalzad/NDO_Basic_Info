'''*
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *'''


import os
import json
import zipfile
import tarfile
import glob
import re
from datetime import datetime
import argparse

''' 
This script will parse a tech-support file generated from NDO to pull basic outputs such as:
- NDO version
- Site number, name, ACI version, OID
- Last 20 audits (excluding backups)
'''


SCRIPT_VERSION = "v1.0"

# Function to extract contents of a zip file
def extract_zip(file_path, extract_to):
    with zipfile.ZipFile(file_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)  # Extract all contents to the specified directory

# Function to extract contents of a tar.gz file
def extract_tar_gz(file_path, extract_to):
    with tarfile.open(file_path, 'r:gz') as tar_ref:
        def tar_filter(tarinfo, path):
            return tarinfo
        tar_ref.extractall(extract_to, filter=tar_filter)  # Extract all contents to the specified directory

# Function to determine and process the file type (zip or tar.gz)
def process_file(file_path):
    if file_path.endswith('.zip'):
        extract_dir = file_path.replace('.zip', '')
        os.makedirs(extract_dir, exist_ok=True)  # Create directory if it doesn't exist
        extract_zip(file_path, extract_dir)  # Extract zip contents
        handle_extracted_directory(extract_dir)  # Process the extracted directory
    elif file_path.endswith('.tar.gz'):
        extract_dir = file_path.replace('.tar.gz', '')
        os.makedirs(extract_dir, exist_ok=True)  # Create directory if it doesn't exist
        extract_tar_gz(file_path, extract_dir)  # Extract tar.gz contents
        handle_extracted_directory(extract_dir)  # Process the extracted directory

# Function to handle files in a directory recursively
def handle_extracted_directory(directory):
    for file_name in os.listdir(directory):
        file_path = os.path.join(directory, file_name)
        if os.path.isfile(file_path):
            process_file(file_path)  # Process each file found

# Function to correct JSON format from a file by ensuring valid JSON structure
def correct_json_format(file_path):
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        # Use regex to find JSON objects in the file content
        json_objects = re.findall(r'{.*?}(?=\s*{|\s*$)', content, re.DOTALL)
        corrected_json = '[' + ','.join(json_objects) + ']'  # Wrap objects in a list
        return corrected_json
    except Exception as e:
        print(f"Error correcting JSON format: {e}")
        return '[]'

# Function to parse JSON data from a file and return it as a list
def parse_json_file(file_path):
    try:
        corrected_json = correct_json_format(file_path)
        data = json.loads(corrected_json)
        return data if isinstance(data, list) else [data]  # Ensure data is returned as a list
    except FileNotFoundError:
        print(f"File not found: {file_path}")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from file: {file_path} - {e}")
    return []

# Function to extract site-specific data from a JSON object
def extract_site_data(data):
    results = []
    if not isinstance(data, dict):
        return results  # Return empty if data is not a dictionary
    
    try:
        # Extract relevant site information
        site_id = data.get("common", {}).get("siteid", "Unknown Site ID")
        name = data.get("common", {}).get("name", "Unknown Name")
        site_version = data.get("common", {}).get("siteversion", "Unknown Version")
        oid = data.get("_id", {}).get("$oid", "Unknown Site OID")

        results.append({
            "Site ID": site_id,
            "Name": name,
            "Site Version": site_version,
            "Site OID": oid
        })
    except Exception as e:
        print(f"Error extracting site data: {e}")
    return results

# Function to display site data in a tabular format
def display_site_list(site_data):
    headers = ["Site ID", "Name", "Site Version", "Site OID"]
    # Determine the max width for each column
    max_widths = {header: len(header) for header in headers}

    for entry in site_data:
        for key in headers:
            value = entry.get(key, "")
            max_widths[key] = max(max_widths[key], len(str(value)))

    # Print the headers
    header_row = ' '.join(f"{header:<{max_widths[header]}}" for header in headers)
    print(header_row)
    print(' '.join('-' * max_widths[header] for header in headers))

    # Print each data row
    for entry in site_data:
        row = ' '.join(f"{str(entry.get(key, '')):<{max_widths[key]}}" for key in headers)
        print(row)

# Function to get all NDO versions and their timestamps from the version file
def get_ndo_versions(directory):
    # Path to the version file
    version_file_glob = os.path.join(directory, "msc-db-json-*_temp/*_temp/backup/msc_versions.json")
    version_files = glob.glob(version_file_glob)

    version_info = []  # List to store version info

    if version_files:
        version_file = version_files[0]  # There should be only one version file
        try:
            with open(version_file, 'r') as file:
                content = file.read()
                # Find multiple JSON objects within the file
                json_objects = re.findall(r'{.*?}(?=\s*{|\s*$)', content, re.DOTALL)
                for obj in json_objects:
                    try:
                        data = json.loads(obj)
                        version = data.get("version", "Unknown Version")
                        timestamp = data.get("timestamp", "Unknown Timestamp")
                        version_info.append((version, timestamp))  # Add each version and timestamp to the list
                    except json.JSONDecodeError:
                        print(f"Error decoding JSON object in file: {version_file}")
        except FileNotFoundError:
            print(f"Version file not found: {version_file}")

    # Sort version info by timestamp in descending order
    version_info.sort(key=lambda x: datetime.fromisoformat(x[1]), reverse=True)

    if not version_info:
        print(f"No valid version information found in file: {version_file}")

    return version_info  # Return the list of version info

# Function to get the last 10 audits from the audits file
def get_last_audits(directory):
    audit_file_path = os.path.join(directory, "msc-db-json-*_temp/*_temp/backup/msc_audit.json")
    audit_files = glob.glob(audit_file_path)

    audit_entries = []

    if audit_files:
        audit_file = audit_files[0]  # There should be only one audit file
        try:
            with open(audit_file, 'r') as file:
                content = file.read()
                # Find multiple JSON objects within the file
                json_objects = re.findall(r'{.*?}(?=\s*{|\s*$)', content, re.DOTALL)
                for obj in json_objects:
                    try:
                        data = json.loads(obj)
                        if data.get("type") not in ["backup", "backup-record"]:
                            timestamp = data.get("timestamp", "Unknown Timestamp")
                            description = data.get("description", "No Description")
                            audit_entries.append((timestamp, description))
                    except json.JSONDecodeError:
                        print(f"Error decoding JSON object in file: {audit_file}")
        except FileNotFoundError:
            print(f"Audit file not found: {audit_file}")

    # Sort audit entries by timestamp in descending order and get the last 20
    audit_entries.sort(key=lambda x: datetime.fromisoformat(x[0]), reverse=True)
    return audit_entries[:20]

# Main function to execute the script
def main():
    parser = argparse.ArgumentParser(description='''Script to parse basic outputs from NDO tech-support zip file.''')
    parser.add_argument("zipfile", help="Path to the NDO tech-support zip file")
    args = parser.parse_args()

    initial_zip = args.zipfile
    initial_extract_dir = initial_zip.replace('.zip', '')

    # Extract the initial zip file and process its contents
    extract_zip(initial_zip, initial_extract_dir)
    handle_extracted_directory(initial_extract_dir)
    
    # Print script version
    print(f'NDO Basic Output {SCRIPT_VERSION}\n\n')

    # Extract and display all NDO versions and their timestamps found
    ndo_versions = get_ndo_versions(initial_extract_dir)
    if ndo_versions:
        print("NDO versions found:")
        for version, timestamp in ndo_versions:
            print(f" - Version: {version}, Date: {timestamp}")
    else:
        print("No NDO version information found.\n")

    # Print a space between version information and site information
    print("\n")

    # Define the path pattern for site JSON files
    json_path = os.path.join(initial_extract_dir, "msc-db-json-*_temp/*_temp/backup/msc_site2.json")
    
    site_data = []
    # Parse each JSON file found matching the pattern
    for file_path in glob.glob(json_path):
        data_list = parse_json_file(file_path)
        for entry in data_list:
            site_results = extract_site_data(entry)
            site_data.extend(site_results)

    # Sort the site data by Site ID
    site_data = sorted(site_data, key=lambda x: x.get("Site ID", ""))
    
    # Display the sorted site list
    if site_data:
        display_site_list(site_data)
    else:
        print("No site information found in the JSON file.")

    # Get the last 10 audit entries (excluding specified types)
    audits = get_last_audits(initial_extract_dir)
    if audits:
        print("\nLast 20 audits (ignoring backup):")
        print("----------------------------------")
        for timestamp, description in audits:
            print(f"{timestamp} - {description}")
    else:
        print("\nNo relevant audit entries found.")

# Entry point for the script
if __name__ == '__main__':
    main()