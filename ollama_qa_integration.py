import os
import json
import csv
import requests
import pandas as pd
import os
from datetime import datetime
import time
import re


# Predefined questions to ask the LLM
PREDEFINED_QUESTIONS = [
    "Does the announcement mention a merger or acquisition?",
    "Is there any mention of a stock split or dividend declaration?",
    "Are there any regulatory actions or penalties mentioned?",
    "Is there an earnings report included in this announcement?",
    "Does the announcement include any management changes?"
]


def sanitize_filename(filename):
    """Sanitize filename to remove invalid characters"""
    import re
    return re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)[:150]


def setup_qa_directories(base_output_dir):
    """Set up necessary directories for the QA process"""
    # Create a main QA directory
    qa_base_dir = os.path.join(base_output_dir, "QA_Results")
    os.makedirs(qa_base_dir, exist_ok=True)

    # Create CSV file to track all answers
    csv_path = os.path.join(qa_base_dir, "all_qa_results.csv")

    # Initialize CSV with headers if it doesn't exist
    if not os.path.exists(csv_path):
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            headers = [
                'Date', 'Company', 'Script ID', 'Description', 'Category',
                'Subcategory', 'QA_Results_Path', 'Processing_Timestamp'
            ]
            writer.writerow(headers)

    return qa_base_dir, csv_path

def extract_yes_no(response):
    """
    Extract 'Yes' or 'No' from the response using regex.
    - If 'yes' is found, return 'Yes'.
    - If 'no' is found, return 'No'.
    - If neither is found, return 'Unclear' (fallback).
    """
    response_lower = response.lower()
    if re.search(r'\byes\b', response_lower):
        return "Yes"
    elif re.search(r'\bno\b', response_lower):
        return "No"
    else:
        return "No"  # Optional fallback for unexpected cases

# def query_ollama(text_content, question, model="deepseek-coder:latest", max_chunk_size=6000, max_retries=2):
#     """
#     Send a query to Ollama LLM and get a reliable Yes/No response
#     """
#     url = "http://localhost:11434/api/generate"
#
#     # Better question definitions focused on explicit evidence
#     specific_questions = {
#         "Does the announcement mention a merger or acquisition?":
#             "Does the document mention or discuss any merger, acquisition, takeover, or business combination?",
#
#         "Is there any mention of a stock split or dividend declaration?":
#             "Does the document mention any dividend payment, stock split, or distribution to shareholders?",
#
#         "Are there any regulatory actions or penalties mentioned?":
#             "Does the document reference any penalties, fines, sanctions, or regulatory compliance issues?",
#
#         "Is there an earnings report included in this announcement?":
#             "Does the document include financial results, financial statements, profit/loss data, or tables showing "
#             "revenue/income figures? The document should be analyzed for ANY presence of financial performance data, "
#             "even if just mentioned or referred to.",
#
#         "Does the announcement include any management changes?":
#             "Does the document mention any executive appointments, resignations, or changes to the board of directors "
#             "or leadership team? "
#     }
#
#     specific_question = specific_questions.get(question, question)
#
#     if len(text_content) > max_chunk_size:
#         truncated_content = text_content[:max_chunk_size]
#     else:
#         truncated_content = text_content
#
#     # Two-step analysis process to improve accuracy
#     prompt = f"""
# <document>
# {truncated_content}
# </document>
#
# You are an expert financial document analyzer. First analyze carefully if the document contains the specific information requested, then provide your conclusion.
#
# QUESTION: {specific_question}
#
# ANALYSIS PROCESS:
# 1. First, carefully examine the document for ANY mention or evidence related to the question
# 2. For financial reports, look for ANY tables, numbers, or mentions of financial results
# 3. Be especially attentive to headers, subject lines, and statements about what's being submitted/approved
#
# When determining if an earnings report is included:
# - Look for terms like "financial results", "unaudited results", "profit/loss", "income", or "statement of assets & liabilities"
# - The presence of financial tables with numbers is strong evidence of an earnings report
# - Even if just announced or referenced without full details, this counts as including an earnings report
#
# Answer ONLY with "Yes" or "No". Answer "Yes" if there is ANY evidence of the requested information.
# """
#
#     payload = {
#         "model": model,
#         "prompt": prompt,
#         "stream": False,
#         "options": {
#             # "temperature": 0.8,     # Slightly higher temperature for better reasoning
#             "num_ctx": 8192,
#             "num_predict": 5,
#             "top_p": 0.7
#         }
#     }
#
#     yes_votes = 0
#     no_votes = 0
#
#     for attempt in range(max_retries):
#         try:
#             response = requests.post(url, json=payload, timeout=90)
#             response.raise_for_status()
#
#             result = response.json()
#             if "response" in result:
#                 raw_response = result["response"].strip().lower()
#
#                 if "yes" in raw_response[:10]:
#                     yes_votes += 1
#                     print(f"  📊 Vote {attempt+1}: Yes")
#                 else:
#                     no_votes += 1
#                     print(f"  📊 Vote {attempt+1}: No")
#             else:
#                 print(f"  ⚠️ Attempt {attempt+1} failed with unexpected response format.")
#                 no_votes += 1
#
#         except Exception as e:
#             print(f"  ⚠️ Attempt {attempt+1} failed: {e}")
#             no_votes += 1
#
#     if yes_votes > no_votes:
#         return "Yes"
#     else:
#         return "No"

def query_ollama(text_content, question, model="tinyllama:latest", max_chunk_size=5000, max_retries=3):
    """
    Send a query to Ollama LLM and get a response with improved error handling

    Args:
        text_content (str): The text content from the PDF
        question (str): The question to ask the LLM
        model (str): The Ollama model to use
        max_chunk_size (int): Maximum size of text to send
        max_retries (int): Number of retries on failure

    Returns:
        str: The LLM's response
    """
    # Ollama API endpoint
    url = "http://localhost:11434/api/generate"

    # Truncate text content to avoid overwhelming the model
    if len(text_content) > max_chunk_size:
        # Take the first part of the document for context
        first_part = text_content[:int(max_chunk_size * 0.7)]
        # Take the last part of the document for context
        last_part = text_content[-int(max_chunk_size * 0.3):]
        truncated_content = first_part + "\n...[Content truncated for brevity]...\n" + last_part
    else:
        truncated_content = text_content

    # Construct prompt with content and question
    prompt = f"""
    You are an AI assistant helping analyze corporate announcements.

    Here is the content of a corporate announcement document:

    {truncated_content}

    Based on this content, please answer the following question:
    {question}

    Give me only one word answer just Yes or NO. Answer with only "Yes" if there is clear evidence, "No" if there is clear evidence against. I only need Yes/No
    nothing more than that."""

    # Prepare the request payload
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }

    for attempt in range(max_retries):
        try:
            # Make the API request
            response = requests.post(url, json=payload, timeout=60)  # Added timeout
            response.raise_for_status()

            # Extract the response
            result = response.json()
            if "response" in result:
                return result["response"].strip()
            else:
                if attempt < max_retries - 1:
                    print(f"  ⚠️ Attempt {attempt + 1} failed with unexpected response format. Retrying...")
                    time.sleep(3)  # Wait before retrying
                else:
                    return "Error: Unexpected response format from Ollama"

        except requests.exceptions.ConnectionError:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Attempt {attempt + 1} failed with connection error. Retrying...")
                time.sleep(3)  # Wait before retrying
            else:
                return "Error: Could not connect to Ollama. Is it running on localhost:11434?"

        except requests.exceptions.HTTPError as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Attempt {attempt + 1} failed with HTTP error: {e}. Retrying...")
                time.sleep(5)  # Longer wait for server errors
            else:
                return f"Error: HTTP error occurred: {e}"

        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Attempt {attempt + 1} failed with error: {e}. Retrying...")
                time.sleep(3)  # Wait before retrying
            else:
                return f"Error: An unexpected error occurred: {str(e)}"

    return "Error: Maximum retries exceeded"


def process_pdf_for_qa(text_file_path, announcement_info, qa_base_dir, csv_path, ollama_model="tinyllama"):
    """
    Process a PDF's extracted text with Ollama LLM by asking predefined questions
    (With timing added for per-announcement processing time)
    """
    if not os.path.exists(text_file_path):
        print(f"❌ Text file not found: {text_file_path}")
        return

    try:
        with open(text_file_path, 'r', encoding='utf-8', errors='replace') as file:
            text_content = file.read()

        date = announcement_info['date_time']
        date_folder = os.path.join(qa_base_dir, date.replace("-", "_"))
        os.makedirs(date_folder, exist_ok=True)

        company_name = sanitize_filename(announcement_info['company_name'])
        script_id = announcement_info['script_id']
        company_folder = os.path.join(date_folder, f"{company_name}_{script_id}")
        os.makedirs(company_folder, exist_ok=True)

        qa_results = {
            "announcement_info": announcement_info,
            "questions_and_answers": {},
            "processing_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        print(f"\n📝 Processing QA for: {company_name} ({script_id}) - {announcement_info['description']}")

        # Track time for this announcement
        announcement_start_time = time.time()

        for question in PREDEFINED_QUESTIONS:
            print(f"  🤔 Asking: {question}")

            # Query Ollama LLM
            question_start_time = time.time()
            answer = query_ollama(text_content, question, model=ollama_model)
            question_time_taken = time.time() - question_start_time

            qa_results["questions_and_answers"][question] = answer
            print(f"  ✅ Answer received in {question_time_taken:.2f} seconds")

            time.sleep(3)  # Keeping your existing sleep logic

        announcement_time_taken = time.time() - announcement_start_time
        print(f"🕒 Total time for announcement: {announcement_time_taken:.2f} seconds")

        # Save the timing data to the results
        qa_results["processing_time_seconds"] = announcement_time_taken

        qa_file_path = os.path.join(company_folder, "qa_results.json")
        with open(qa_file_path, 'w', encoding='utf-8') as json_file:
            json.dump(qa_results, json_file, indent=4, ensure_ascii=False)

        with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                announcement_info['date_time'],
                announcement_info['company_name'],
                announcement_info['script_id'],
                announcement_info['description'],
                announcement_info['category'],
                announcement_info.get('subcategory', 'Others'),
                qa_file_path,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])

            print(f"✅ QA processing complete for {company_name} - Results saved to {qa_file_path}")
        return qa_file_path

    except Exception as e:
        print(f"❌ Error in QA processing: {str(e)}")
        return None


# def process_pdf_for_qa(text_file_path, announcement_info, qa_base_dir, csv_path, ollama_model="tinyllama"):
#     """
#     Process a PDF's extracted text with Ollama LLM by asking predefined questions
#
#     Args:
#         text_file_path (str): Path to the extracted text file
#         announcement_info (dict): Information about the announcement
#         qa_base_dir (str): Base directory for QA results
#         csv_path (str): Path to the CSV file tracking all QA results
#         ollama_model (str): Ollama model to use
#     """
#     if not os.path.exists(text_file_path):
#         print(f"❌ Text file not found: {text_file_path}")
#         return
#
#     try:
#         # Read the extracted text content
#         with open(text_file_path, 'r', encoding='utf-8', errors='replace') as file:
#             text_content = file.read()
#
#         # Create date-wise folder in QA directory
#         date = announcement_info['date_time']
#         date_folder = os.path.join(qa_base_dir, date.replace("-", "_"))
#         os.makedirs(date_folder, exist_ok=True)
#
#         # Create company-specific folder
#         company_name = sanitize_filename(announcement_info['company_name'])
#         script_id = announcement_info['script_id']
#         company_folder = os.path.join(date_folder, f"{company_name}_{script_id}")
#         os.makedirs(company_folder, exist_ok=True)
#
#         # Prepare to save QA results
#         qa_results = {
#             "announcement_info": announcement_info,
#             "questions_and_answers": {},
#             "processing_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#         }
#
#         print(f"\n📝 Processing QA for: {company_name} ({script_id}) - {announcement_info['description']}")
#
#         # Track time for this announcement
#         announcement_start_time = time.time()
#
#         # Process each predefined question
#         for question in PREDEFINED_QUESTIONS:
#             print(f"  🤔 Asking: {question}")
#
#             # Query Ollama LLM
#             question_start_time = time.time()
#             answer = query_ollama(text_content, question, model=ollama_model)
#             question_time_taken = time.time() - question_start_time
#
#
#             # Add to results
#             qa_results["questions_and_answers"][question] = answer
#             print(f"  ✅ Answer received")
#
#             # Add a longer delay to avoid overwhelming Ollama
#             time.sleep(3)  # Increased from 0.5 to give Ollama more time between requests
#
#         # Save QA results to JSON file
#         qa_file_path = os.path.join(company_folder, "qa_results.json")
#         with open(qa_file_path, 'w', encoding='utf-8') as json_file:
#             json.dump(qa_results, json_file, indent=4, ensure_ascii=False)
#
#         # Update CSV with path to QA results
#         with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
#             writer = csv.writer(csvfile)
#             writer.writerow([
#                 announcement_info['date_time'],
#                 announcement_info['company_name'],
#                 announcement_info['script_id'],
#                 announcement_info['description'],
#                 announcement_info['category'],
#                 announcement_info.get('subcategory', 'Others'),
#                 qa_file_path,
#                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#             ])
#
#         print(f"✅ QA processing complete for {company_name} - Results saved to {qa_file_path}")
#         return qa_file_path
#
#     except Exception as e:
#         print(f"❌ Error in QA processing: {str(e)}")
#         return None


def create_qa_summary_table(base_output_dir, csv_path=None):
    """
    Create a summary table of all QA results in tabular format

    Args:
        base_output_dir (str): Base output directory
        csv_path (str, optional): Path to save the CSV file. If None,
                                 saved to base_output_dir/QA_Results/qa_summary_table.csv

    Returns:
        str: Path to the created CSV file
    """
    if csv_path is None:
        qa_base_dir = os.path.join(base_output_dir, "QA_Results")
        csv_path = os.path.join(qa_base_dir, "qa_summary_table.csv")

    # Create dataframe to store all QA data
    columns = ['Company Name', 'Date', 'Prompt', 'Response']
    qa_data = []

    # Walk through the QA_Results directory
    qa_base_dir = os.path.join(base_output_dir, "QA_Results")
    for root, dirs, files in os.walk(qa_base_dir):
        for file in files:
            if file == "qa_results.json":
                try:
                    file_path = os.path.join(root, file)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        qa_results = json.load(f)

                    # Extract relevant information
                    company_name = qa_results.get("announcement_info", {}).get("company_name", "Unknown")
                    date = qa_results.get("announcement_info", {}).get("date_time", "Unknown")

                    # Add each Q&A pair as a row
                    # for question, answer in qa_results.get("questions_and_answers", {}).items():
                    #     qa_data.append([company_name, date, question, answer])
                    for question, full_response in qa_results.get("questions_and_answers", {}).items():
                        # Use regex function to extract clean Yes/No for summary table
                        clean_response = extract_yes_no(full_response)
                        qa_data.append([company_name, date, question, clean_response])

                except Exception as e:
                    print(f"⚠️ Error processing {file_path}: {e}")

    # Create DataFrame and save to CSV
    if qa_data:
        df = pd.DataFrame(qa_data, columns=columns)
        df.to_csv(csv_path, index=False, encoding='utf-8')
        print(f"✅ QA summary table created at {csv_path}")
        return csv_path
    else:
        print("⚠️ No QA data found to create summary table")
        return None


def check_ollama_availability(model="tinyllama"):
    """Check if Ollama is available and the specified model is loaded"""
    try:
        # Check if Ollama server is running
        response = requests.get("http://localhost:11434/api/tags")
        if response.status_code != 200:
            print("⚠️ Ollama server is not responding correctly")
            return False

        # Check if the requested model is available
        models = response.json().get("models", [])
        model_names = [m.get("name") for m in models]

        print(f"Available models: {', '.join(model_names)}")

        # Try to match with or without the :latest tag
        base_model_name = model.split(':')[0]
        if model in model_names:
            return True
        elif f"{base_model_name}:latest" in model_names:
            print(f"Found model as {base_model_name}:latest, will use this instead of {model}")
            return True
        else:
            print(f"⚠️ Model '{model}' is not loaded in Ollama. Available models: {', '.join(model_names)}")
            print(f"  You can pull the model using: ollama pull {model}")
            return False

    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to Ollama. Is it running on localhost:11434?")
        print("  You can start Ollama with: ollama serve")
        return False
    except Exception as e:
        print(f"❌ Error checking Ollama availability: {str(e)}")
        return False

def run_qa_on_extracted_pdfs(base_output_dir, announcements_data, ollama_model="tinyllama"):
    """
    Run QA on all extracted PDFs based on announcements data
    (With total processing time tracking for all announcements)
    """
    qa_base_dir, csv_path = setup_qa_directories(base_output_dir)

    if not check_ollama_availability(ollama_model):
        print("⚠️ Skipping QA processing due to Ollama availability issues")
        return

    total_processed = 0
    total_failed = 0

    total_qa_start_time = time.time()  # Start timing all QA processing

    for date, announcements in announcements_data.items():
        for announcement in announcements:
            company_name = sanitize_filename(announcement['company_name'])
            script_id = announcement['script_id']
            date_folder = os.path.join(base_output_dir, date.replace("-", "_"))
            company_folder = os.path.join(date_folder, f"{company_name}_{script_id}")

            metadata_path = os.path.join(company_folder, "metadata.json")

            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r', encoding='utf-8') as meta_file:
                        metadata = json.load(meta_file)

                    text_file_name = metadata.get("extraction_results", {}).get("text_file")

                    if text_file_name:
                        text_file_path = os.path.join(company_folder, "text", text_file_name)

                        if os.path.exists(text_file_path):
                            if process_pdf_for_qa(text_file_path, announcement, qa_base_dir, csv_path, ollama_model):
                                total_processed += 1
                            else:
                                total_failed += 1
                        else:
                            print(f"⚠️ Text file not found at expected path: {text_file_path}")
                            total_failed += 1
                    else:
                        print(f"⚠️ No text file information in metadata for: {company_name}")
                        total_failed += 1

                except Exception as e:
                    print(f"❌ Error processing announcement for QA: {str(e)}")
                    total_failed += 1
            else:
                print(f"⚠️ No metadata file found for: {company_name} at {metadata_path}")
                total_failed += 1

    total_qa_time_taken = time.time() - total_qa_start_time
    hours, remainder = divmod(total_qa_time_taken, 3600)
    minutes, seconds = divmod(remainder, 60)
    time_formatted = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"

    print(f"\n⏱️ Total time taken for the LLM processing time for all announcements: {time_formatted}")
    print(f"\n⏱️ Total Raw LLM processing time for all announcements: {total_qa_time_taken:.2f} seconds")

    print("\n" + "=" * 50)
    print(f"Ollama QA Processing Summary:")
    print(f"✅ Successfully processed: {total_processed}")
    print(f"❌ Failed to process: {total_failed}")
    print(f"📊 Results saved to {qa_base_dir}")
    print(f"📝 CSV report at {csv_path}")
    print("=" * 50)


# def run_qa_on_extracted_pdfs(base_output_dir, announcements_data, ollama_model="tinyllama"):
#     """
#     Run QA on all extracted PDFs based on announcements data
#
#     Args:
#         base_output_dir (str): Base output directory
#         announcements_data (dict): Dictionary of announcement data
#         ollama_model (str): Ollama model to use
#     """
#     # Set up QA directories and CSV
#     qa_base_dir, csv_path = setup_qa_directories(base_output_dir)
#
#     # Check Ollama availability
#     if not check_ollama_availability(ollama_model):
#         print("⚠️ Skipping QA processing due to Ollama availability issues")
#         return
#
#     total_processed = 0
#     total_failed = 0
#
#     # Process each announcement
#     for date, announcements in announcements_data.items():
#         for announcement in announcements:
#             # Determine the text file path based on the same structure as in extraction
#             company_name = sanitize_filename(announcement['company_name'])
#             script_id = announcement['script_id']
#             date_folder = os.path.join(base_output_dir, date.replace("-", "_"))
#             company_folder = os.path.join(date_folder, f"{company_name}_{script_id}")
#
#             # Look for metadata file to find the text file path
#             metadata_path = os.path.join(company_folder, "metadata.json")
#
#             if os.path.exists(metadata_path):
#                 try:
#                     with open(metadata_path, 'r', encoding='utf-8') as meta_file:
#                         metadata = json.load(meta_file)
#
#                     text_file_name = metadata.get("extraction_results", {}).get("text_file")
#
#                     if text_file_name:
#                         text_file_path = os.path.join(company_folder, "text", text_file_name)
#
#                         if os.path.exists(text_file_path):
#                             # Process this text file with Ollama for QA
#                             if process_pdf_for_qa(text_file_path, announcement, qa_base_dir, csv_path, ollama_model):
#                                 total_processed += 1
#                             else:
#                                 total_failed += 1
#                         else:
#                             print(f"⚠️ Text file not found at expected path: {text_file_path}")
#                             total_failed += 1
#                     else:
#                         print(f"⚠️ No text file information in metadata for: {company_name}")
#                         total_failed += 1
#
#                 except Exception as e:
#                     print(f"❌ Error processing announcement for QA: {str(e)}")
#                     total_failed += 1
#             else:
#                 print(f"⚠️ No metadata file found for: {company_name} at {metadata_path}")
#                 total_failed += 1
#
#     print("\n" + "=" * 50)
#     print(f"Ollama QA Processing Summary:")
#     print(f"✅ Successfully processed: {total_processed}")
#     print(f"❌ Failed to process: {total_failed}")
#     print(f"📊 Results saved to {qa_base_dir}")
#     print(f"📝 CSV report at {csv_path}")
#     print("=" * 50)


# Main function that will be called from other scripts
# def process_announcements_with_ollama(base_output_dir, announcements_data, model="tinyllama"):
#     """
#     Main entry point for processing announcements with Ollama
#
#     Args:
#         base_output_dir (str): Base output directory
#         announcements_data (dict): Dictionary of announcement data
#         model (str): Ollama model to use
#     """
#     print("\n" + "=" * 50)
#     print("Starting Ollama LLM Question Answering...")
#     run_qa_on_extracted_pdfs(base_output_dir, announcements_data, ollama_model=model)

def process_announcements_with_ollama(base_output_dir, announcements_data, model="tinyllama"):
    """
    Main entry point for processing announcements with Ollama

    Args:
        base_output_dir (str): Base output directory
        announcements_data (dict): Dictionary of announcement data
        model (str): Ollama model to use
    """
    print("\n" + "=" * 50)
    print("Starting Ollama LLM Question Answering...")
    run_qa_on_extracted_pdfs(base_output_dir, announcements_data, ollama_model=model)

    # Create summary table after processing is complete
    print("\nCreating QA summary table...")
    create_qa_summary_table(base_output_dir)