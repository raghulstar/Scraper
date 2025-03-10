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


def query_ollama_batch(text_content, questions, model="tinyllama:latest", max_chunk_size=5000, max_retries=3):
    """
    Send a batch query to Ollama LLM with multiple questions at once
    and parse the responses with enhanced consistency checking.
    Includes beginning, middle, and end portions of long documents.

    Args:
        text_content (str): The text content from the PDF
        questions (list): List of questions to ask the LLM
        model (str): The Ollama model to use
        max_chunk_size (int): Maximum size of text to send
        max_retries (int): Number of retries on failure

    Returns:
        dict: Dictionary mapping questions to Yes/No answers
    """
    # Ollama API endpoint
    url = "http://localhost:11434/api/generate"

    # Improved truncation that includes middle portions
    if len(text_content) > max_chunk_size:
        # Calculate portions
        first_portion = int(max_chunk_size * 0.4)  # 40% from beginning
        middle_portion = int(max_chunk_size * 0.2)  # 20% from middle
        last_portion = int(max_chunk_size * 0.4)  # 40% from end

        # Extract portions
        first_part = text_content[:first_portion]

        # Calculate middle segment position
        middle_start = (len(text_content) - middle_portion) // 2
        middle_part = text_content[middle_start:middle_start + middle_portion]

        last_part = text_content[-last_portion:]

        # Combine with markers
        truncated_content = (
                first_part +
                "\n...[Beginning content truncated]...\n" +
                middle_part +
                "\n...[Middle content truncated]...\n" +
                last_part
        )
    else:
        truncated_content = text_content

    # Format all questions as a numbered list
    questions_formatted = "\n".join([f"{i + 1}. {q}" for i, q in enumerate(questions)])

    # Make the prompt even more explicit about the required format
    prompt = f"""
    You are assisting a Quantitative Analyst at a high-frequency trading firm who needs to rapidly parse stock market announcements from the Bombay Stock Exchange (BSE).

    ANNOUNCEMENT CONTENT:
    
    {truncated_content}

    TASK:
    As a trading algorithm input, I need precise Yes/No classifications for the following questions:

    {questions_formatted}

    REQUIRED FORMAT:
    Respond with ONLY a numbered list containing Yes or No answers.
    Example format:
    1. Yes
    2. No
    3. Yes
    ...etc.

    CRITICAL INSTRUCTIONS:
    - Provide ONLY the numbered Yes/No responses
    - DO NOT include explanations or reasoning
    - DO NOT add any text before or after the list
    - These classifications will be used for algorithmic trading decisions

    RESPONSE:
    """

    # Prepare the request payload
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }

    for attempt in range(max_retries):
        try:
            # Make the API request
            response = requests.post(url, json=payload, timeout=120)  # Increased timeout for batch processing
            response.raise_for_status()

            # Extract the response
            result = response.json()
            if "response" in result:
                raw_response = result["response"].strip()

                # Print the raw response for debugging
                # print(f"  Raw response from Ollama: {raw_response[:100]}...")

                # Create a dictionary to hold answers and evidence
                answers = {}
                evidence = {}

                # Extract key topics from questions for content matching
                question_topics = {
                    0: ["merger", "acquisition", "merge", "acquire"],
                    1: ["stock split", "dividend", "stock", "share"],
                    2: ["regulatory", "regulation", "penalty", "action", "fine", "sanction"],
                    3: ["earnings", "financial", "result", "profit", "loss", "revenue"],
                    4: ["management", "executive", "director", "leadership", "appointment", "resign"]
                }

                # Initial check of the first paragraph for overarching statements
                first_paragraph = raw_response.split('\n\n')[0].lower()
                paragraph_evidence = {}

                # Check if the first paragraph contains overarching answers
                for q_idx, topics in question_topics.items():
                    question = questions[q_idx]
                    for topic in topics:
                        # Check for clear positive or negative patterns
                        if f"mentions {topic}" in first_paragraph or f"does mention {topic}" in first_paragraph:
                            paragraph_evidence[question] = "Yes"
                            break
                        elif (f"no {topic}" in first_paragraph or
                              f"not mention {topic}" in first_paragraph or
                              f"doesn't mention {topic}" in first_paragraph or
                              f"does not mention {topic}" in first_paragraph):
                            paragraph_evidence[question] = "No"
                            break

                # More robust parsing approach
                response_lines = raw_response.split('\n')

                for i, question in enumerate(questions):
                    question_num = i + 1
                    answer = None
                    evidence_text = []

                    # Method 1: Look for structured numbered responses
                    for line in response_lines:
                        line = line.strip()

                        # Match patterns like "1. Yes", "1) Yes", "1: Yes", etc.
                        patterns = [
                            f"{question_num}\\.\s*([Yy]es|[Nn]o)",
                            f"{question_num}\\)\s*([Yy]es|[Nn]o)",
                            f"{question_num}[\\.\\)]?\s+([Yy]es|[Nn]o)",
                            f"{question_num}:\s*([Yy]es|[Nn]o)"
                        ]

                        for pattern in patterns:
                            match = re.search(pattern, line)
                            if match:
                                matched_answer = match.group(1).lower()
                                answer = "Yes" if matched_answer == "yes" else "No"
                                evidence_text.append(f"Matched pattern: {line}")
                                break

                        if answer:
                            break

                    # Method 2: Look for the question content in sentences
                    if not answer:
                        # Extract key words from the question
                        question_keywords = question_topics[i]

                        # Find sentences that mention these keywords
                        for line in raw_response.lower().split('.'):
                            for keyword in question_keywords:
                                if keyword in line:
                                    if "yes" in line and not any(
                                            neg in line for neg in ["no ", "not ", "doesn't", "does not"]):
                                        answer = "Yes"
                                        evidence_text.append(f"Keyword '{keyword}' in: {line}")
                                        break
                                    elif any(neg in line for neg in ["no ", "not ", "doesn't", "does not"]):
                                        answer = "No"
                                        evidence_text.append(f"Negative + keyword '{keyword}' in: {line}")
                                        break
                            if answer:
                                break

                    # Method 3: Check the overall document tone for this topic
                    if not answer:
                        topics = question_topics[i]
                        # Count positive vs negative mentions of key topics
                        positive_count = 0
                        negative_count = 0

                        for topic in topics:
                            for line in raw_response.lower().split('\n'):
                                if topic in line:
                                    if "yes" in line:
                                        positive_count += 1
                                    if "no" in line or "not" in line:
                                        negative_count += 1

                        if positive_count > negative_count:
                            answer = "Yes"
                            evidence_text.append(f"More positive than negative mentions of topics: {topics}")
                        elif negative_count > 0:
                            answer = "No"
                            evidence_text.append(f"More negative than positive mentions of topics: {topics}")

                    # Method 4: Check the first paragraph evidence if we found any
                    if not answer and question in paragraph_evidence:
                        answer = paragraph_evidence[question]
                        evidence_text.append(f"From first paragraph: {first_paragraph[:50]}...")

                    # Final fallback - check for global Yes/No statements
                    if not answer:
                        # Check if the first sentences contain a clear overarching Yes/No
                        first_sentences = raw_response.lower()[:200].split('.')

                        for sentence in first_sentences:
                            # Check for statements about what the document contains or doesn't contain
                            doc_indicators = ["the document", "the announcement", "this announcement", "this document"]
                            contains_indicators = ["mentions", "includes", "contains", "discusses", "has", "there is",
                                                   "yes"]
                            missing_indicators = ["does not mention", "doesn't mention", "no mention of",
                                                  "doesn't include", "does not include", "doesn't contain",
                                                  "does not contain"]

                            # Check for document-wide statements
                            topic_mentioned = False
                            for topic in question_topics[i]:
                                if topic in sentence:
                                    topic_mentioned = True

                                    # If the sentence indicates the document contains the topic
                                    if any(di in sentence for di in doc_indicators) and any(
                                            ci in sentence for ci in contains_indicators):
                                        answer = "Yes"
                                        evidence_text.append(f"Document contains statement: {sentence}")
                                        break

                                    # If the sentence indicates the document doesn't contain the topic
                                    if any(di in sentence for di in doc_indicators) and any(
                                            mi in sentence for mi in missing_indicators):
                                        answer = "No"
                                        evidence_text.append(f"Document missing statement: {sentence}")
                                        break

                            if topic_mentioned and answer:
                                break

                    # Very last fallback
                    if not answer:
                        answer = "No"  # Default to "No" as a safer assumption
                        evidence_text.append("No clear evidence found, defaulting to No")

                    answers[question] = answer
                    evidence[question] = evidence_text

                # FINAL CONSISTENCY CHECK
                # If the first sentence strongly contradicts our parsed answers, consider overriding
                first_sentence = raw_response.split('.')[0].lower()

                # Check for clear merger/acquisition statements in the first sentence
                if "merger" in first_sentence or "acquisition" in first_sentence or "merge" in first_sentence:
                    # If we detect a positive merger statement at the beginning but our parsed answer is No
                    if ("yes" in first_sentence[:20] or "mention" in first_sentence) and answers[questions[0]] == "No":
                        # Only override if there's no strong negative language
                        if not any(neg in first_sentence for neg in ["no ", "not ", "doesn't", "does not"]):
                            print(f"  ⚠️ Overriding merger/acquisition answer based on first sentence evidence")
                            answers[questions[0]] = "Yes"

                # Print debug info about evidence for difficult questions
                for q_idx, question in enumerate(questions):
                    if question in evidence:
                        evidence_items = evidence[question]
                        if evidence_items and evidence_items[-1].startswith("No clear evidence"):
                            print(f"  ℹ️ Limited evidence for Q{q_idx + 1}: {answers[question]} - {evidence_items}")

                return answers
            else:
                if attempt < max_retries - 1:
                    print(f"  ⚠️ Attempt {attempt + 1} failed with unexpected response format. Retrying...")
                    time.sleep(3)  # Wait before retrying
                else:
                    # Return error responses for all questions
                    return {q: "Error: Unexpected response format from Ollama" for q in questions}

        except requests.exceptions.ConnectionError:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Attempt {attempt + 1} failed with connection error. Retrying...")
                time.sleep(3)  # Wait before retrying
            else:
                return {q: "Error: Could not connect to Ollama" for q in questions}

        except requests.exceptions.HTTPError as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Attempt {attempt + 1} failed with HTTP error: {e}. Retrying...")
                time.sleep(5)  # Longer wait for server errors
            else:
                return {q: f"Error: HTTP error occurred: {e}" for q in questions}

        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Attempt {attempt + 1} failed with error: {e}. Retrying...")
                time.sleep(3)  # Wait before retrying
            else:
                return {q: f"Error: An unexpected error occurred: {str(e)}" for q in questions}

    return {q: "Error: Maximum retries exceeded" for q in questions}


def process_pdf_for_qa_batch(text_file_path, announcement_info, qa_base_dir, csv_path, ollama_model="tinyllama"):
    """
    Process a PDF's extracted text with Ollama LLM by asking all predefined questions in a single batch.
    Now uses precomputed OCR text from images.
    """
    if not os.path.exists(text_file_path):
        print(f"❌ Text file not found: {text_file_path}")
        return

    try:
        # Read the extracted text content
        with open(text_file_path, 'r', encoding='utf-8', errors='replace') as file:
            text_content = file.read()

        # Get folder paths
        date = announcement_info['date_time']
        date_folder = os.path.join(qa_base_dir, date.replace("-", "_"))
        os.makedirs(date_folder, exist_ok=True)

        company_name = sanitize_filename(announcement_info['company_name'])
        script_id = announcement_info['script_id']
        description = sanitize_filename(announcement_info['description'])
        company_folder = os.path.join(date_folder, f"{company_name}_{script_id}_{description}")
        os.makedirs(company_folder, exist_ok=True)

        # Get the parent company folder path
        parent_company_folder = os.path.dirname(os.path.dirname(text_file_path))

        # Look for OCR text file - use precomputed OCR from scraper.py
        ocr_folder = os.path.join(parent_company_folder, "ocr")
        ocr_text = ""

        # Get the OCR file name from metadata
        metadata_path = os.path.join(parent_company_folder, "metadata.json")
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                ocr_file_name = metadata.get("extraction_results", {}).get("ocr_text_file")

                if ocr_file_name:
                    ocr_file_path = os.path.join(ocr_folder, ocr_file_name)
                    if os.path.exists(ocr_file_path):
                        with open(ocr_file_path, 'r', encoding='utf-8', errors='replace') as ocr_file:
                            ocr_text = ocr_file.read()
            except Exception as e:
                print(f"⚠️ Error loading OCR text: {e}")

        # Combine text and OCR text
        if ocr_text:
            combined_content = text_content + "\n\n" + ocr_text
        else:
            combined_content = text_content
            print(f"⚠️ No OCR text found for this announcement")

        # Prepare QA results structure
        qa_results = {
            "announcement_info": announcement_info,
            "questions_and_answers": {},
            "processing_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        print(f"\n📝 Processing QA for: {company_name} ({script_id}) - {announcement_info['description']}")

        # Track time for this announcement
        announcement_start_time = time.time()

        # BATCH PROCESSING: Send all questions at once
        print(f"  🤔 Asking all {len(PREDEFINED_QUESTIONS)} questions in a batch")
        batch_start_time = time.time()

        # Get all answers in one call (using combined content with OCR text)
        all_answers = query_ollama_batch(combined_content, PREDEFINED_QUESTIONS, model=ollama_model)

        batch_time_taken = time.time() - batch_start_time

        # Store each answer
        for question, answer in all_answers.items():
            qa_results["questions_and_answers"][question] = answer
            print(f"  ✅ Answer for '{question[:30]}...': {answer}")

        print(f"  ✅ All answers received in {batch_time_taken:.2f} seconds")

        announcement_time_taken = time.time() - announcement_start_time
        print(f"🕒 Total time for announcement: {announcement_time_taken:.2f} seconds")

        # Save the timing data to the results
        qa_results["processing_time_seconds"] = announcement_time_taken

        # Add metadata about processing
        qa_results["processing_details"] = {
            "text_file_processed": os.path.basename(text_file_path),
            "ocr_text_used": ocr_text != "",
            "combined_content_length": len(combined_content)
        }

        # Save results to JSON
        qa_file_path = os.path.join(company_folder, "qa_results.json")
        with open(qa_file_path, 'w', encoding='utf-8') as json_file:
            json.dump(qa_results, json_file, indent=4, ensure_ascii=False)

        # Update the CSV with path to QA results
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
    columns = ['Company Name', 'Script ID', 'Description', 'Date', 'Prompt', 'Response']
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
                    script_id = qa_results.get("announcement_info", {}).get("script_id", "Unknown")
                    description = qa_results.get("announcement_info", {}).get("description", "Unknown")
                    date = qa_results.get("announcement_info", {}).get("date_time", "Unknown")

                    # Add each Q&A pair as a row
                    for question, full_response in qa_results.get("questions_and_answers", {}).items():
                        # Use regex function to extract clean Yes/No for summary table
                        clean_response = extract_yes_no(full_response)
                        qa_data.append([company_name, script_id, description, date, question, clean_response])
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


# Update the run_qa_on_extracted_pdfs function to use the batch version
def run_qa_on_extracted_pdfs_batch(base_output_dir, announcements_data, ollama_model="tinyllama"):
    """
    Run QA on all extracted PDFs based on announcements data using batch processing
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
            description = sanitize_filename(announcement['description'])
            date_folder = os.path.join(base_output_dir, date.replace("-", "_"))
            company_folder = os.path.join(date_folder, f"{company_name}_{script_id}_{description}")

            metadata_path = os.path.join(company_folder, "metadata.json")

            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r', encoding='utf-8') as meta_file:
                        metadata = json.load(meta_file)

                    text_file_name = metadata.get("extraction_results", {}).get("text_file")

                    if text_file_name:
                        text_file_path = os.path.join(company_folder, "text", text_file_name)

                        if os.path.exists(text_file_path):
                            if process_pdf_for_qa_batch(text_file_path, announcement, qa_base_dir, csv_path,
                                                        ollama_model):
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
    print(f"Ollama QA Processing Summary: ")
    print(f"✅ Successfully processed: {total_processed}")
    print(f"❌ Failed to process: {total_failed}")
    print(f"📊 Results saved to {qa_base_dir}")
    print(f"📝 CSV report at {csv_path}")
    print("=" * 50)


# Update the main entry point function to use batch processing
def process_announcements_with_ollama_batch(base_output_dir, announcements_data, model="tinyllama"):
    """
    Main entry point for processing announcements with Ollama using batch processing
    """
    print("\n" + "=" * 50)
    print("Starting Ollama LLM Question Answering (Batch Mode)...")
    run_qa_on_extracted_pdfs_batch(base_output_dir, announcements_data, ollama_model=model)

    # Create summary table after processing is complete
    print("\nCreating QA summary table...")
    create_qa_summary_table(base_output_dir)
