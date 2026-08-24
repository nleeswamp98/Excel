import csv, os, re, pdfplumber, shutil
from pathlib import Path
import config

def extract_deal_name(pdf_path):

    with pdfplumber.open(pdf_path) as pdf:
        first_page = pdf.pages[0]
        words = first_page.extract_words(extra_attrs = ["size", "fontname", "x0", "top"])

        if not words:
            text = first_page.extract_text()
            if text:
                for line in text.split('\n'):
                    if line.strip():
                        return line.strip()
            return "No text found"

        max_size = max(word['size'] for word in words)
        header_words = [w for w in words if w['size'] == max_size]

        lines = {}
        for w in header_words:
            key = round(w['top'], 1)
            lines.setdefault(key, []).append(w)

        sorted_lines_keys = sorted(lines.keys())
        header_lines =[]
        for key in sorted_lines_keys:
            line_words = sorted(lines[key], key = lambda x: x['x0'])

            line_text =""
            prev_x1 = None

            for word in line_words:
                if prev_x1 is not None and word['x0'] - prev_x1 >2:
                    line_text += " "
                
                line_text += word['text']
                prev_x1 = word['x1']

            header_lines.append(line_text)

        return " ".join(header_lines).strip() 

def load_processed_deals_log(log_file_path, log_headers):

    processed_deals = {}
    try:
        with open(log_file_path, 'r', encoding = 'utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                deal_name = row.get("Deal Name")
                status = row.get("Status")
                if deal_name and status:
                    clean_key = deal_name.strip().lower()
                    clean_status = status.strip().title()
                    processed_deals[clean_key] = clean_status
    except FileNotFoundError:
        print(f"Log file not found. Creating new log at {log_file_path}")
        try:
            with open(log_file_path, 'w', newline= '', encoding= 'utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(log_headers)
        except Exception as e:
            print(f"CRITICAL ERROR: Could not create log file: {e}")
    except Exception as e:
        print(f"CRITICAL ERROR: Could not read log file: {e}")
    
    return processed_deals

def move_and_log_presales(original_file_path, new_file_destination, log_file_path, deal_name, deal_type):
    
    try:
        shutil.move(original_file_path, new_file_destination)

        try:
            with open(log_file_path, "a", newline='', encoding= 'utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([deal_name, deal_type, "Processing"])
        except Exception as e:
            return f"MOVE SUCEEDED but LOG FAILED: {e}"
        
        return f"renamed to {os.path.basename(new_file_destination)} and logged as \"Processing\""
    
    except Exception as e:
        return f"MOVE FAILED: {e}"

def find_summary_text(full_text):

    section_title = "Summary"

    start_match = config.SUMMARY_START_PATTERN.search(full_text)

    if not start_match:
        return None
    
    text_start_index = start_match.end()

    end_match = config.SUMMARY_END_PATTERN.search(full_text, pos= text_start_index)

    summary_text = ""
    if end_match:
        text_end_index = end_match.start()
        summary_text = full_text[text_start_index : text_end_index]
    else:
        summary_text = full_text[text_start_index :]
    
    return summary_text.strip()

def process_pdf(pdf_file, processed_deals):

    full_pdf_path = os.path.join(config.INTAKE_FOLDER, pdf_file)
    full_text = ""

    try:
        with pdfplumber.open(full_pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text(x_tolerance = 2, y_tolerance = 2)
                if page_text:
                    full_text += page_text + "\n"
        if not full_text:
            return "No text extracted"
    except Exception as e:
        return f"Error opening PDF: {e}"
    
    deal_name = extract_deal_name(full_pdf_path)
    deal_key = deal_name.lower()

    deal_status = processed_deals.get(deal_key)
    if deal_status in ["Processing", "Completed"]:
        return f"SKIPPED {deal_name}, already logged as {deal_status}"
    
    summary_text = find_summary_text(full_text)

    if summary_text is None:
        deal_type = "clo"
        new_filename = f"{deal_type}_{deal_name}_presale.pdf"

        new_file_destination = os.path.join(config.PROCESSING_FOLDER, new_filename)
        status = move_and_log_presales(full_pdf_path, new_file_destination, config.INTAKE_LOG_FILE, deal_name, deal_type)
        if "Moved" in status:
            processed_deals[deal_key] = "Processing"
        return status
    
    if not summary_text:
        return "Summary was found but empty"
    
    found_keywords = []

    for search_term in config.DEAL_TYPES:
        pattern = r'\b' + r'\s*'.join(re.escape(part) for part in re.split(r'(\s+|)', search_term)) + r'\b'
        if re.search(pattern, summary_text, re.IGNORECASE):
            found_keywords.append(search_term)

    if found_keywords:
        deal_type = config.DEAL_TYPES[found_keywords[0]]
        new_filename = f"{deal_type}_{deal_name}_presale.pdf"

        new_file_destination = os.path.join(config.PROCESSING_FOLDER, new_filename)
        status = move_and_log_presales(full_pdf_path, new_file_destination, config.INTAKE_LOG_FILE, deal_name, deal_type)
        if "Moved" in status:
            processed_deals[deal_key] = "Processing"
        return status
    else:
        return "Summary found, but no deal keywords matched"
    
def main():
    
    processed_deals = load_processed_deals_log(config.INTAKE_LOG_FILE, config.INTAKE_LOG_HEADERS)

    if not os.path.isdir(config.INTAKE_FOLDER):
        print(f"CRITICAL ERROR: Intake folder now found at {config.INTAKE_FOLDER}")
        return

    unprocessed_pdfs = [f for f in os.listdir(config.INTAKE_FOLDER) if f.endswith('.pdf')]

    if not unprocessed_pdfs:
        print("No new PDFs found in the intake folder")
        return
    
    print(f"Found {len(unprocessed_pdfs)} new PDFs. Startring processing...")

    processing_summary = {}

    for pdf_file in unprocessed_pdfs:
        status_message = process_pdf(pdf_file, processed_deals)
        processing_summary[pdf_file] = status_message

    print("\n---Processing Complete: Final Results---")
    for file_name, message in processing_summary.items():
        print(f"{file_name}: {message}\n")

if __name__ == "__main__":
    main()
