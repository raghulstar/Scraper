import ollama
import os
import time
import requests
import re
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.keys import Keys
from collections import defaultdict
from datetime import datetime
from selenium.webdriver.common.by import By
import fitz  # PyMuPDF
import pandas as pd
import cv2
import numpy as np
import pytesseract
from PIL import Image

# And set the tesseract path if needed (adjust path as necessary for your system)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


def sanitize_filename(filename):
    return re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)[:150]


def extract_company_details(text):
    # First pattern to match: "COMPANY NAME - SCRIPT_ID - Description-Subcategory"
    pattern1 = r'(.*?)\s*-\s*(\d+)\s*-\s*(.*?)-(.*)'

    # Second pattern to match: "COMPANY NAME - SCRIPT_ID - Description" (no subcategory)
    pattern2 = r'(.*?)\s*-\s*(\d+)\s*-\s*(.*)'

    # Try first pattern (with subcategory)
    match = re.match(pattern1, text)
    if match:
        return {
            'company_name': match.group(1).strip(),
            'script_id': match.group(2).strip(),
            'description': match.group(3).strip(),
            'subcategory': match.group(4).strip()
        }

    # Try second pattern (no subcategory)
    match = re.match(pattern2, text)
    if match:
        return {
            'company_name': match.group(1).strip(),
            'script_id': match.group(2).strip(),
            'description': match.group(3).strip(),
            'subcategory': "Others"  # Default subcategory
        }

    return None


def extract_file_size(size_text):
    if not size_text:
        return ""
    size_match = re.search(r'(\d+(?:\.\d+)?\s*MB)', size_text)
    return size_match.group(1) if size_match else ""


def is_valid_pdf(file_path):
    try:
        with open(file_path, "rb") as f:
            header = f.read(5)
            return header == b"%PDF-"
    except Exception as e:
        print(f"⚠️ Error reading file {file_path}: {e}")
        return False


def safe_find_element(row, selector):
    """Safely find an element, return None if not found"""
    try:
        return row.find_element(By.CSS_SELECTOR, selector)
    except NoSuchElementException:
        return None


def extract_announcement_details(row):
    try:
        # Try different selectors for company information
        company_span = (
                safe_find_element(row, "span[ng-bind-html='cann.NEWSSUB']") or
                safe_find_element(row, "td.tdcolumngrey span") or
                safe_find_element(row, "td span.ng-binding")
        )

        if not company_span:
            return None

        company_text = company_span.text.strip()
        if not company_text:
            return None

        # Extract company details
        company_info = extract_company_details(company_text)
        if not company_info:
            # Try alternative parsing if the standard format fails
            words = company_text.split()
            if len(words) >= 2:
                company_info = {
                    'company_name': ' '.join(words[:-1]),
                    'script_id': words[-1],
                    'description': 'General Announcement',
                    'subcategory': 'Others'
                }
            else:
                return None

        # Find the PDF link - this is essential
        pdf_link = safe_find_element(row, "a[href*='.pdf']")
        if not pdf_link:
            return None
        pdf_url = pdf_link.get_attribute("href")
        if not pdf_url:
            return None

        # Get file size (optional)
        file_size = ""
        size_span = safe_find_element(row, "span[ng-if*='cann.Fld_Attachsize']")
        if size_span:
            file_size = extract_file_size(size_span.text.strip())

        # Get category from the specific HTML element
        category = "Announcement"  # Default category
        category_td = safe_find_element(row,
                                        "td.tdcolumngrey.ng-binding.ng-scope[ng-if=\"cann.CATEGORYNAME != 'NULL' \"]")
        if category_td:
            category = category_td.text.strip() or category

        # IMPROVED DATE EXTRACTION: Try multiple selectors to find the date
        date_time = datetime.now().strftime("%d-%m-%Y")  # Default fallback

        # Try multiple possible date element selectors
        date_element = (
                safe_find_element(row, "b.ng-binding") or
                safe_find_element(row, "td b.ng-binding") or
                safe_find_element(row, "td[ng-bind='cann.ANNOUNCEDT']") or
                safe_find_element(row, "td.tdcolumngrey b")
        )

        if date_element and date_element.text:
            # Extract just the date part from format like "24-02-2025 20:40:09"
            date_text = date_element.text.strip()

            # Handle different date formats that might appear
            # Try to match DD-MM-YYYY format first (with or without time)
            date_match = re.search(r'(\d{2}-\d{2}-\d{4})', date_text)
            if date_match:
                date_time = date_match.group(1)
            # If no match, try other common formats
            elif re.match(r'\d{2}/\d{2}/\d{4}', date_text):
                parts = date_text.split('/')
                date_time = f"{parts[0]}-{parts[1]}-{parts[2]}"

        # If we still don't have a date, try to get it from parent elements
        if date_time == datetime.now().strftime("%d-%m-%Y"):
            # Try to get date from parent row or previous sibling
            parent_row = row.find_element(By.XPATH, "..")
            parent_date_element = safe_find_element(parent_row, "b.ng-binding") or safe_find_element(parent_row, "td b")
            if parent_date_element and parent_date_element.text:
                date_text = parent_date_element.text.strip()
                date_match = re.search(r'(\d{2}-\d{2}-\d{4})', date_text)
                if date_match:
                    date_time = date_match.group(1)

        return {
            "date_time": date_time,
            "script_id": company_info['script_id'],
            "company_name": company_info['company_name'],
            "description": company_info.get('description', ''),
            "pdf_link": pdf_url,
            "category": category,
            "subcategory": company_info.get('subcategory', 'Others'),
            "file_size": file_size
        }

    except Exception as e:
        print(f"Warning: Issue processing row: {str(e)}")
        return None


def get_user_date_input(prompt):
    while True:
        date_str = input(prompt + " (DD/MM/YYYY): ")
        # Basic validation for date format
        if re.match(r'^\d{2}/\d{2}/\d{4}$', date_str):
            return date_str
        print("Invalid date format. Please use DD/MM/YYYY format.")


def get_company_update_selection():
    company_updates = [
        "AGM/EGM", "Board Meeting", "Company Update", "Corp. Action",
        "Insider Trading / SAST", "New Listing", "Result",
        "Integrated Filing", "Others"
    ]

    print("\nAvailable company update types:")
    for i, update in enumerate(company_updates, 1):
        print(f"{i}. {update}")

    while True:
        try:
            selection = int(input("\nSelect a company update type (1-9, or 0 for --Select Category--): "))
            if 0 <= selection <= 9:
                if selection == 0:
                    return "-1"  # --Select Category--
                else:
                    return company_updates[selection - 1]
            else:
                print("Please enter a number between 0 and 9.")
        except ValueError:
            print("Please enter a valid number.")


def set_date_in_datepicker(driver, element_id, date_str):
    """Set date in a datepicker by clicking and typing the date"""
    try:
        # First enable the date input by unchecking any disabled checkbox if it exists
        try:
            if element_id == "txtFromDt":
                checkbox = driver.find_element(By.ID, "chkfrmDate")
                if checkbox.is_selected():
                    checkbox.click()
            elif element_id == "txtToDt":
                checkbox = driver.find_element(By.ID, "chktoDate")
                if checkbox.is_selected():
                    checkbox.click()
        except:
            pass  # If no checkbox exists or other error, continue

        # Click the input field
        date_input = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, element_id))
        )
        date_input.click()
        time.sleep(0.5)

        # Clear the input field
        date_input.clear()
        date_input.send_keys(Keys.CONTROL + "a")  # Select all text
        date_input.send_keys(Keys.DELETE)  # Delete selected text

        # Type the date
        date_input.send_keys(date_str)
        date_input.send_keys(Keys.TAB)  # Tab out to confirm date
        time.sleep(0.5)

        # Try both JavaScript and direct input to ensure the date is set
        driver.execute_script(f"document.getElementById('{element_id}').value = '{date_str}';")
        driver.execute_script(
            f"angular.element(document.getElementById('{element_id}')).val('{date_str}').trigger('change');")

        print(f"Date set for {element_id}: {date_str}")
        return True
    except Exception as e:
        print(f"Error setting date for {element_id}: {e}")
        return False


def extract_text_from_pdf(pdf_path):
    """Extract all text content from a PDF file using PyMuPDF with error handling"""
    try:
        text_content = ""
        with fitz.open(pdf_path) as pdf:
            for page_num in range(len(pdf)):
                try:
                    page = pdf[page_num]
                    text_content += page.get_text()
                except Exception as e:
                    print(f"Warning: Could not extract text from page {page_num + 1}: {e}")
                    continue
        return text_content
    except Exception as e:
        print(f"Error extracting text from {pdf_path}: {e}")
        return ""


def extract_tables_from_pdf_with_pymupdf(pdf_path):
    """Extract tables from PDF using PyMuPDF's table detection capability"""
    try:
        import fitz
        tables = []

        with fitz.open(pdf_path) as doc:
            for page_num in range(min(len(doc), 50)):  # Limit to first 50 pages to avoid excessive processing
                try:
                    page = doc[page_num]
                    # Use PyMuPDF's built-in table detection
                    tab = page.find_tables()
                    if tab and hasattr(tab, 'tables') and tab.tables:
                        for idx, table in enumerate(tab.tables):
                            # Convert to pandas DataFrame
                            rows = []
                            cells = table.extract()
                            if cells:
                                for cell_row in cells:
                                    row_data = []
                                    for cell in cell_row:
                                        # Check if cell is a proper object with text attribute
                                        if hasattr(cell, 'text'):
                                            row_data.append(cell.text)
                                        elif isinstance(cell, str):
                                            row_data.append(cell)
                                        elif cell is None:
                                            row_data.append("")
                                        else:
                                            # For any other type, convert to string
                                            row_data.append(str(cell))
                                    rows.append(row_data)

                                if rows and len(rows) > 0:
                                    # Create DataFrame
                                    df = pd.DataFrame(rows)
                                    # Add metadata about source
                                    df.attrs['page'] = page_num + 1
                                    df.attrs['table_index'] = idx + 1
                                    tables.append(df)
                except Exception as e:
                    print(f"Warning: Could not extract tables from page {page_num + 1}: {e}")
                    continue

        return tables
    except Exception as e:
        print(f"Error extracting tables with PyMuPDF from {pdf_path}: {e}")
        return []


def extract_tables_from_pdf(pdf_path):
    """Attempt to extract tables using multiple methods with fallbacks"""
    tables = []

    # First try using tabula-py if available
    try:
        import tabula
        print(f"Attempting to extract tables with tabula-py...")
        tables = tabula.read_pdf(pdf_path, pages='all', multiple_tables=True, silent=True)
        if tables:
            print(f"Successfully extracted {len(tables)} tables with tabula-py")
            return tables
    except Exception as e:
        print(f"Tabula extraction failed: {e}. Trying PyMuPDF fallback...")

    # Fallback to PyMuPDF
    tables = extract_tables_from_pdf_with_pymupdf(pdf_path)

    # If we found tables with PyMuPDF
    if tables:
        print(f"Successfully extracted {len(tables)} tables with PyMuPDF")
        return tables

    # Last resort: try to detect tables based on text layout patterns
    # This is simplified and may not work for complex layouts
    try:
        text_content = extract_text_from_pdf(pdf_path)
        # Look for potential tabular data patterns (sequences of whitespace-separated numbers or words)
        lines = text_content.split('\n')
        potential_table_rows = []
        current_table = []

        for line in lines:
            # If line has multiple tab or multiple space separations, it might be a table row
            parts = re.split(r'\t+|\s{2,}', line.strip())
            if len(parts) >= 3 and any(part.strip() for part in parts):  # At least 3 columns with content
                current_table.append(parts)
            elif current_table:
                # End of current table section
                if len(current_table) >= 3:  # At least 3 rows to be considered a table
                    potential_table_rows.append(current_table)
                current_table = []

        # Add the last table if it exists
        if current_table and len(current_table) >= 3:
            potential_table_rows.append(current_table)

        # Convert potential tables to DataFrames
        for idx, table_data in enumerate(potential_table_rows):
            headers = table_data[0]
            data = table_data[1:]
            df = pd.DataFrame(data, columns=headers)
            df.attrs['extraction_method'] = 'text_pattern'
            df.attrs['table_index'] = idx + 1
            tables.append(df)

        if tables:
            print(f"Extracted {len(tables)} potential tables using text pattern detection")
    except Exception as e:
        print(f"Text pattern table detection failed: {e}")

    return tables


def extract_images_from_pdf(pdf_path, output_folder):
    """Extract images from PDF using PyMuPDF with error handling for JPEG2000 issues"""
    image_files = []
    try:
        with fitz.open(pdf_path) as pdf:
            for page_num in range(len(pdf)):
                try:
                    page = pdf[page_num]

                    # First method: Get images using get_images
                    try:
                        image_list = page.get_images(full=True)
                        for img_index, img in enumerate(image_list):
                            try:
                                xref = img[0]
                                base_image = pdf.extract_image(xref)
                                if base_image:
                                    image_bytes = base_image["image"]
                                    image_ext = base_image["ext"]

                                    # Create a unique filename for each image
                                    image_filename = f"page{page_num + 1}_img{img_index + 1}.{image_ext}"
                                    image_path = os.path.join(output_folder, image_filename)

                                    with open(image_path, "wb") as img_file:
                                        img_file.write(image_bytes)

                                    image_files.append(image_path)
                            except Exception as img_err:
                                print(f"Warning: Could not extract image {img_index} on page {page_num + 1}: {img_err}")
                    except Exception as e:
                        print(f"Could not get images using get_images for page {page_num + 1}: {e}")

                    # Second method: Alternative extraction using page rendering
                    # This can help when there are JPEG2000 images or complex formats
                    try:
                        pix = page.get_pixmap(alpha=False)
                        img_filename = f"page{page_num + 1}_full.png"
                        img_path = os.path.join(output_folder, img_filename)
                        pix.save(img_path)
                        image_files.append(img_path)
                    except Exception as pix_err:
                        print(f"Warning: Could not render page {page_num + 1} as image: {pix_err}")

                except Exception as page_err:
                    print(f"Warning: Error processing page {page_num + 1} for images: {page_err}")

        return image_files
    except Exception as e:
        print(f"Error extracting images from {pdf_path}: {e}")
        return []


def process_pdf_content(pdf_path, output_folder):
    """Process a single PDF file and extract text, tables, and images with robust error handling"""
    try:
        # Create subdirectories for different content types
        text_folder = os.path.join(output_folder, "text")
        tables_folder = os.path.join(output_folder, "tables")
        images_folder = os.path.join(output_folder, "images")
        ocr_folder = os.path.join(output_folder, "ocr")  # New folder for OCR extracted text

        os.makedirs(text_folder, exist_ok=True)
        os.makedirs(tables_folder, exist_ok=True)
        os.makedirs(images_folder, exist_ok=True)
        os.makedirs(ocr_folder, exist_ok=True)  # Create OCR folder

        # Get the base name of the PDF
        pdf_basename = os.path.basename(pdf_path)
        base_name = os.path.splitext(pdf_basename)[0]

        # Initialize result dictionary
        result = {
            "text_file": None,
            "table_files": [],
            "image_files": [],
            "ocr_text_file": None  # New field for OCR-extracted text
        }

        # Extract and save text
        print(f"Extracting text from {pdf_basename}...")
        text_content = extract_text_from_pdf(pdf_path)
        if text_content:
            text_file_path = os.path.join(text_folder, f"{base_name}.txt")
            with open(text_file_path, "w", encoding="utf-8", errors="replace") as text_file:
                text_file.write(text_content)
            print(f"✅ Text extracted and saved to {text_file_path}")
            result["text_file"] = text_file_path
        else:
            print(f"⚠️ No text content extracted from {pdf_basename}")

        # Extract and save tables
        print(f"Extracting tables from {pdf_basename}...")
        tables = extract_tables_from_pdf(pdf_path)
        for idx, table in enumerate(tables):
            if not table.empty:
                table_file_path = os.path.join(tables_folder, f"{base_name}_table{idx + 1}.csv")
                try:
                    table.to_csv(table_file_path, index=False, encoding="utf-8", errors="replace")
                    print(f"✅ Table {idx + 1} extracted and saved to {table_file_path}")
                    result["table_files"].append(table_file_path)
                except Exception as table_err:
                    print(f"⚠️ Error saving table {idx + 1}: {table_err}")

        if not tables:
            print(f"⚠️ No tables found in {pdf_basename}")

        # Extract and save images
        print(f"Extracting images from {pdf_basename}...")
        image_files = extract_images_from_pdf(pdf_path, images_folder)
        if image_files:
            print(f"✅ {len(image_files)} images extracted from {pdf_basename}")
            result["image_files"] = image_files

            # Process OCR on extracted images right away
            print(f"Processing OCR on extracted images...")

            # Get full page images
            all_image_files = [f for f in os.listdir(images_folder)
                               if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp'))]
            full_page_images = [f for f in all_image_files if "_full." in f]

            if not full_page_images:
                print("No full page images found, processing all images instead...")
                image_files_to_process = all_image_files
            else:
                print(f"Processing {len(full_page_images)} full page images for OCR...")
                image_files_to_process = full_page_images

            # Sort images by page number for consistent processing
            image_files_to_process.sort(key=lambda x: int(x.split('page')[1].split('_')[0])
            if 'page' in x and '_' in x.split('page')[1] else 0)

            ocr_text = ""
            for img_file in image_files_to_process:
                img_path = os.path.join(images_folder, img_file)
                try:
                    # Open the image file
                    image = Image.open(img_path)
                    # Convert to grayscale
                    image = image.convert('L')
                    # Convert to numpy array for OpenCV processing
                    img_array = np.array(image)
                    # Apply adaptive thresholding for better text extraction
                    img_array = cv2.adaptiveThreshold(
                        img_array, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
                    )
                    # Convert back to PIL Image
                    image = Image.fromarray(img_array)
                    # Configure OCR for business documents
                    custom_config = r'--oem 3 --psm 6 -l eng'
                    # Extract text using pytesseract
                    text = pytesseract.image_to_string(image, config=custom_config)

                    if text.strip():
                        # Add page indicator for full page images
                        if "_full." in img_file:
                            page_num = img_file.split('page')[1].split('_')[0]
                            ocr_text += f"\n\n[PAGE {page_num}]\n[EXTRACTED FROM IMAGE: {img_file}]\n{text}\n[END OF IMAGE TEXT]"
                        else:
                            ocr_text += f"\n\n[EXTRACTED FROM IMAGE: {img_file}]\n{text}\n[END OF IMAGE TEXT]"
                        print(f"✅ Extracted OCR text from image: {img_file}")
                    else:
                        print(f"⚠️ No OCR text found in image: {img_file}")

                except Exception as e:
                    print(f"⚠️ Error extracting OCR text from image {img_file}: {e}")

            # Save OCR text to file if any was extracted
            if ocr_text.strip():
                ocr_file_path = os.path.join(ocr_folder, f"{base_name}_ocr.txt")
                with open(ocr_file_path, "w", encoding="utf-8", errors="replace") as ocr_file:
                    ocr_file.write(ocr_text)
                print(f"✅ OCR text extracted and saved to {ocr_file_path}")
                result["ocr_text_file"] = ocr_file_path
            else:
                print(f"⚠️ No OCR text extracted from images")
        else:
            print(f"⚠️ No images extracted from {pdf_basename}")

        return result

    except Exception as e:
        print(f"⚠️ Error processing {pdf_path}: {e}")
        return {"text_file": None, "table_files": [], "image_files": [], "ocr_text_file": None}


def create_merged_data_file(base_output_dir, announcements_data):
    """
    Create a single merged file containing both announcements_data and extraction metadata,
    preserving previous results.

    Args:
        base_output_dir (str): Base directory where announcements are stored
        announcements_data (dict): Dictionary of announcement data by date

    Returns:
        str: Path to the merged data file
    """
    merged_file = os.path.join(base_output_dir, "merged_announcements_data.json")

    # Initialize structure for merged data
    merged_data = {
        "announcements": {}
    }

    # Try to load existing merged data file to preserve previous results
    if os.path.exists(merged_file):
        try:
            with open(merged_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                # Copy existing announcements data
                if "announcements" in existing_data:
                    merged_data["announcements"] = existing_data["announcements"]
                # Copy existing summary if available
                if "summary" in existing_data:
                    merged_data["summary"] = existing_data["summary"]
        except Exception as e:
            print(f"Warning: Could not read existing merged data file: {str(e)}")
            print("Creating a new merged data file.")

    # Track statistics
    total_announcements = 0
    total_with_metadata = 0
    previously_processed = 0

    # If we loaded existing data, count the previously processed entries
    for date_entries in merged_data["announcements"].values():
        previously_processed += len(date_entries)

    # First, create a lookup dictionary using PDF links as keys for faster matching
    metadata_lookup = {}
    processed_pdf_links = set()  # Track processed PDF links to avoid duplicates

    # Collect PDF links that are already in the merged data to avoid duplicates
    for date, date_entries in merged_data["announcements"].items():
        for entry in date_entries:
            if "announcement_info" in entry and "pdf_link" in entry["announcement_info"]:
                processed_pdf_links.add(entry["announcement_info"]["pdf_link"])

    # Walk through the directory to find all metadata.json files
    for root, dirs, files in os.walk(base_output_dir):
        for file in files:
            if file == "metadata.json":
                file_path = os.path.join(root, file)

                try:
                    # Read the metadata file
                    with open(file_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)

                    # Use PDF link as key for lookup
                    if "announcement_info" in metadata and "pdf_link" in metadata["announcement_info"]:
                        pdf_link = metadata["announcement_info"]["pdf_link"]
                        metadata["_source_path"] = os.path.relpath(file_path, base_output_dir)
                        metadata_lookup[pdf_link] = metadata

                except Exception as e:
                    print(f"Error processing metadata file {file_path}: {str(e)}")

    # Now go through announcements_data and merge with metadata
    for date, announcements in announcements_data.items():
        # Make sure the date key exists in merged data
        if date not in merged_data["announcements"]:
            merged_data["announcements"][date] = []

        for announcement in announcements:
            total_announcements += 1

            # Skip if this PDF link is already in our merged data
            if "pdf_link" in announcement and announcement["pdf_link"] in processed_pdf_links:
                continue

            # Add this PDF link to processed set
            if "pdf_link" in announcement:
                processed_pdf_links.add(announcement["pdf_link"])

            # Create enhanced announcement object
            enhanced_announcement = {
                "announcement_info": announcement,
                "extraction_results": None,
                "processed_timestamp": None
            }

            # Try to find matching metadata
            if "pdf_link" in announcement and announcement["pdf_link"] in metadata_lookup:
                metadata = metadata_lookup[announcement["pdf_link"]]

                # Copy extraction results and timestamp if available
                if "extraction_results" in metadata:
                    enhanced_announcement["extraction_results"] = metadata["extraction_results"]

                if "processed_timestamp" in metadata:
                    enhanced_announcement["processed_timestamp"] = metadata["processed_timestamp"]

                total_with_metadata += 1

            # Add to merged data
            merged_data["announcements"][date].append(enhanced_announcement)

    # Update summary information
    total_in_merged_file = previously_processed + total_announcements

    # Calculate the actual total by counting all entries in the merged data
    actual_total = sum(len(entries) for entries in merged_data["announcements"].values())

    merged_data["summary"] = {
        "total_announcements": actual_total,
        "new_announcements_this_run": total_announcements,
        "previously_processed_announcements": previously_processed,
        "total_with_metadata": total_with_metadata + (merged_data.get("summary", {}).get("total_with_metadata", 0) - total_with_metadata),
        "generation_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_directory": base_output_dir
    }

    # Save the merged data
    with open(merged_file, 'w', encoding='utf-8') as f:
        json.dump(merged_data, f, indent=4, ensure_ascii=False)

    print("\n" + "=" * 50)
    print(f"Merged Data File Creation Complete: ")
    print(f"✅ New announcements processed: {total_announcements}")
    print(f"✅ Previously processed announcements: {previously_processed}")
    print(f"✅ Total announcements in merged file: {actual_total}")
    print(f"✅ Announcements with extraction metadata: {merged_data['summary']['total_with_metadata']}")
    print(f"📄 Merged file saved to: {merged_file}")
    print("=" * 50)

    return merged_file


# Main execution starts here
if __name__ == "__main__":

    total_process_start_time = time.time()
    # Get user inputs for date range and company update type
    print("=" * 50)
    print("BSE Announcement Scraper")
    print("=" * 50)
    from_date = get_user_date_input("Enter FROM date")
    to_date = get_user_date_input("Enter TO date")
    company_update = get_company_update_selection()

    print(f"\nSearching announcements from {from_date} to {to_date}")
    print(f"Company update type: {company_update if company_update != '-1' else '--Select Category--'}")
    print("=" * 50)

    # Create base output directory
    base_output_dir = "BSE_Announcements"
    os.makedirs(base_output_dir, exist_ok=True)

    # Configure Selenium WebDriver
    chrome_options = Options()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920x1080")
    # Uncomment below if you want to see the browser
    # chrome_options.add_argument("--start-maximized")
    # chrome_options.headless = False

    service = Service(r"C:\\chromedriver.exe")
    driver = webdriver.Chrome(service=service, options=chrome_options)

    announcements_data = defaultdict(list)
    processed_urls = set()

    try:
        url = "https://www.bseindia.com/corporates/ann.html"
        driver.get(url)

        # Wait for the page to load
        time.sleep(3)

        # Set from date with improved method
        set_date_in_datepicker(driver, "txtFromDt", from_date)

        # Set to date with improved method
        set_date_in_datepicker(driver, "txtToDt", to_date)

        # Select company update type
        update_dropdown = Select(WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "ddlPeriod"))
        ))
        update_dropdown.select_by_value(company_update)

        # Take a small pause to ensure everything is set
        time.sleep(1)

        # Verify the values are set correctly
        from_date_value = driver.execute_script("return document.getElementById('txtFromDt').value")
        to_date_value = driver.execute_script("return document.getElementById('txtToDt').value")
        print(f"Verified FROM date: {from_date_value}")
        print(f"Verified TO date: {to_date_value}")

        # Click the submit button
        submit_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.ID, "btnSubmit"))
        )
        submit_button.click()
        print("Search button clicked")

        # Wait for table to load
        try:
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
            print("Table loaded successfully")
        except:
            print("No results table found - please check your search criteria")
            driver.save_screenshot("search_results.png")
            print("Screenshot saved as search_results.png")

        while True:
            print("\nProcessing current page...")
            time.sleep(2)

            # Get all rows excluding header
            rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")

            if not rows:
                print("No rows found on current page")
                break

            processed_on_page = 0
            for row in rows:
                try:
                    announcement_info = extract_announcement_details(row)
                    if announcement_info and announcement_info['pdf_link'] not in processed_urls:
                        processed_urls.add(announcement_info['pdf_link'])
                        current_date = announcement_info['date_time']
                        announcements_data[current_date].append(announcement_info)
                        processed_on_page += 1
                        print(
                            f"✅ Processed announcement: {announcement_info['company_name']} - Date: {announcement_info['date_time']} - Category: {announcement_info['category']}")

                except Exception as e:
                    continue

            print(f"Processed {processed_on_page} announcements on this page")

            # Check for next page
            try:
                next_button = driver.find_element(By.LINK_TEXT, "Next")
                if next_button.is_enabled():
                    next_button.click()
                    time.sleep(3)
                else:
                    break
            except Exception:
                print("No 'Next' button found or not clickable. Exiting loop.")
                break

        # Download PDFs and process their content
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        # Create a mapping of PDF files to their announcement info for post-processing
        pdf_file_mapping = {}

        print(f"\nDownloading and processing {len(processed_urls)} PDFs...")
        for date, announcements in announcements_data.items():
            # Create date-wise folder
            date_folder = os.path.join(base_output_dir, date.replace("-", "_"))
            os.makedirs(date_folder, exist_ok=True)

            for idx, announcement in enumerate(announcements):
                try:
                    pdf_url = announcement['pdf_link']
                    if pdf_url not in processed_urls:
                        continue

                    # Create unique company-announcement folder within date folder
                    company_name = sanitize_filename(announcement['company_name'])
                    script_id = announcement['script_id']
                    description = sanitize_filename(announcement['description'])
                    # Create a uniquely identified folder using company name, script ID and description
                    company_folder = os.path.join(date_folder, f"{company_name}_{script_id}_{description}")
                    os.makedirs(company_folder, exist_ok=True)

                    # Download PDF file
                    response_head = requests.head(pdf_url, headers=headers, allow_redirects=True)
                    final_url = response_head.url

                    # description = sanitize_filename(announcement['description'])
                    pdf_filename = f"{company_name}_{script_id}_{description}.pdf"
                    pdf_path = os.path.join(company_folder, pdf_filename)

                    pdf_response = requests.get(final_url, headers=headers, stream=True)
                    if pdf_response.status_code != 200:
                        print(f"❌ Failed to download {pdf_url}: HTTP {pdf_response.status_code}")
                        continue

                    with open(pdf_path, "wb") as pdf_file:
                        for chunk in pdf_response.iter_content(1024):
                            pdf_file.write(chunk)

                    if is_valid_pdf(pdf_path):
                        print(f"✅ PDF downloaded successfully: {pdf_filename}")

                        # Process PDF content (extract text, tables, images)
                        print(f"📄 Processing content for {pdf_filename}...")
                        extraction_results = process_pdf_content(pdf_path, company_folder)

                        # Save extraction metadata
                        metadata = {
                            "announcement_info": announcement,
                            "extraction_results": {
                                "text_file": os.path.basename(extraction_results["text_file"]) if extraction_results[
                                    "text_file"] else None,
                                "table_files": [os.path.basename(tf) for tf in extraction_results["table_files"]],
                                "image_files": [os.path.basename(img) for img in extraction_results["image_files"]],
                                "ocr_text_file": os.path.basename(extraction_results["ocr_text_file"]) if
                                extraction_results[
                                    "ocr_text_file"] else None
                            },
                            "processed_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }

                        metadata_file = os.path.join(company_folder, "metadata.json")
                        with open(metadata_file, "w", encoding="utf-8") as mf:
                            json.dump(metadata, mf, indent=4, ensure_ascii=False)

                        print(f"✅ Content extraction completed for {pdf_filename}")
                    else:
                        print(f"❌ Invalid PDF: {pdf_path}, deleting...")
                        os.remove(pdf_path)

                except Exception as e:
                    print(f"⚠️ Error processing announcement: {e}")

    finally:
        driver.quit()

    # Run Ollama LLM for question answering
    print("\n" + "=" * 50)
    print("Starting Question Answering with Ollama...")
    ollama.process_announcements_with_ollama_batch(base_output_dir, announcements_data,
                                                   model="tinyllama:latest")

    print("\n" + "=" * 50)
    print("Creating merged announcements and metadata file...")
    merged_file = create_merged_data_file(base_output_dir, announcements_data)
    print(f"Merged data file created at: {merged_file}")

    # Track total time after everything finishes
    total_process_end_time = time.time()
    total_process_duration = total_process_end_time - total_process_start_time

    hours, remainder = divmod(total_process_duration, 3600)
    minutes, seconds = divmod(remainder, 60)
    time_formatted = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"

    print(f"\n⏱️ Total time taken for the entire process: {time_formatted}")
    print(f"⏱️ Raw time: {total_process_duration:.2f} seconds")

    print("\n" + "=" * 50)
    print(f"BSE Announcement Scraping, PDF Processing, and QA Complete")
    print(f"Results saved to {base_output_dir} folder")
    print("=" * 50)
