import sqlite3, os, re, pdfplumber, shutil, ftfy
from difflib import get_close_matches
import pandas as pd
import config


# =============================================================================
# DATABASE SETUP
# =============================================================================

def setup_database():
    if not os.path.exists(config.ARCHIVE_FOLDER):
        os.makedirs(config.ARCHIVE_FOLDER)

    conn = sqlite3.connect(config.DATABASE_FILE)
    cursor = conn.cursor()

    # --- DEAL LEVEL ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Deals (
            deal_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_name   TEXT NOT NULL UNIQUE,
            deal_type   TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Deal_Factor_Labels (
            label_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            label_name  TEXT NOT NULL UNIQUE,
            category    TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Deal_Factors (
            deal_factor_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_id         INTEGER,
            sentiment       TEXT NOT NULL,
            label_id        INTEGER,
            factor_text     TEXT,
            FOREIGN KEY (deal_id) REFERENCES Deals(deal_id),
            FOREIGN KEY (label_id) REFERENCES Deal_Factor_Labels(label_id)
        );
    """)

    # --- PROPERTY LEVEL ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Properties (
            property_id             INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_id                 INTEGER,
            property_name           TEXT NOT NULL,
            property_type           TEXT,
            property_subtype        TEXT,
            collateral_description  TEXT,
            FOREIGN KEY (deal_id) REFERENCES Deals(deal_id),
            UNIQUE (deal_id, property_name)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Property_Factor_Labels (
            label_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            label_name  TEXT NOT NULL UNIQUE,
            category    TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Property_Factors (
            factor_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER,
            sentiment   TEXT NOT NULL,
            label_id    INTEGER,
            factor_text TEXT,
            FOREIGN KEY (property_id) REFERENCES Properties(property_id),
            FOREIGN KEY (label_id) REFERENCES Property_Factor_Labels(label_id)
        );
    """)

    conn.commit()
    conn.close()
    print("Database setup complete.")


# =============================================================================
# DATABASE HELPERS
# =============================================================================

def get_or_create_deal(cursor, deal_name, deal_type):
    cursor.execute("SELECT deal_id FROM Deals WHERE deal_name = ?", (deal_name,))
    row = cursor.fetchone()
    if row:
        return row[0], True
    else:
        cursor.execute("INSERT INTO Deals (deal_name, deal_type) VALUES (?, ?)", (deal_name, deal_type))
        return cursor.lastrowid, False


def get_or_create_property(cursor, deal_id, property_name, collateral_description=None):
    """Create property with name and description only. Type/subtype set by categorize_properties.py"""
    property_name_clean = property_name.replace("\n", " ").strip()

    cursor.execute(
        "SELECT property_id FROM Properties WHERE deal_id = ? AND property_name = ?",
        (deal_id, property_name_clean)
    )
    row = cursor.fetchone()

    if row:
        if collateral_description:
            cursor.execute(
                "UPDATE Properties SET collateral_description = ? WHERE property_id = ?",
                (collateral_description, row[0])
            )
        return row[0]
    else:
        cursor.execute(
            "INSERT INTO Properties (deal_id, property_name, collateral_description) VALUES (?, ?, ?)",
            (deal_id, property_name_clean, collateral_description)
        )
        return cursor.lastrowid


def get_or_create_deal_factor_label(cursor, label_name):
    label_name_clean = label_name.strip()
    cursor.execute(
        "SELECT label_id FROM Deal_Factor_Labels WHERE label_name = ?",
        (label_name_clean,)
    )
    row = cursor.fetchone()
    if row:
        return row[0]
    else:
        cursor.execute(
            "INSERT INTO Deal_Factor_Labels (label_name) VALUES (?)",
            (label_name_clean,)
        )
        return cursor.lastrowid


def get_or_create_property_factor_label(cursor, label_name):
    label_name_clean = label_name.strip()
    cursor.execute(
        "SELECT label_id FROM Property_Factor_Labels WHERE label_name = ?",
        (label_name_clean,)
    )
    row = cursor.fetchone()
    if row:
        return row[0]
    else:
        cursor.execute(
            "INSERT INTO Property_Factor_Labels (label_name) VALUES (?)",
            (label_name_clean,)
        )
        return cursor.lastrowid


# =============================================================================
# TEXT CLEANING
# =============================================================================

def strip_page_headers_and_footers(page_text):
    lines = page_text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Strip footers: contain a year and "Pre-Sale"
        if (len(stripped) < 120
                and re.search(r'\b20\d{2}\b', stripped)
                and re.search(r'\bPre-Sale\b|\bpresale\b', stripped, re.IGNORECASE)):
            continue
        # Strip page headers: "Moody's Ratings" and "Structured Finance"
        if re.match(r"Moody.s Ratings|Structured Finance", stripped, re.IGNORECASE):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned)


# =============================================================================
# EXTRACTION
# =============================================================================

def extract_top20_loan_names(pdf):
    """STEP 2: Extract official loan names from Top 20 table."""

    target_page_index = -1
    for i, page in enumerate(pdf.pages):
        page_text = page.extract_text(x_tolerance=2, y_tolerance=2)
        if not page_text:
            continue

        if (config.LOAN_TABLE_KEYWORDS["HEADER_FIND_1"] in page_text and
                config.LOAN_TABLE_KEYWORDS["HEADER_FIND_2"] in page_text):
            target_page_index = i
            break

    if target_page_index == -1:
        print("    ERROR - Could not find Top 20 table.")
        return []

    page_text = pdf.pages[target_page_index].extract_text(x_tolerance=2, y_tolerance=2)
    if target_page_index + 1 < len(pdf.pages):
        page_text += "\n" + pdf.pages[target_page_index + 1].extract_text(x_tolerance=2, y_tolerance=2)

    try:
        header_index = re.search(r"Loan name", page_text, re.IGNORECASE).end()

        footer_match = re.search(
            config.LOAN_TABLE_KEYWORDS["FOOTER_FIND_REGEX"],
            page_text, re.IGNORECASE | re.DOTALL
        )
        footer_index = footer_match.start() if footer_match else -1

        if footer_index > 0:
            table_text = page_text[header_index:footer_index]
        else:
            table_text = page_text[header_index:]

        official_names = []
        for line in table_text.split('\n'):
            cleaned_line = line.strip()
            if not cleaned_line:
                continue

            match = config.LOAN_NAME_PLAN_B_REGEX.match(cleaned_line)
            if match:
                raw_name = match.group(1).strip()
                if raw_name and raw_name.lower() != "loan name":
                    clean_match = config.LOAN_NAME_CLEANER_REGEX.match(raw_name)
                    if clean_match:
                        loan_name = clean_match.group(1).strip()
                        official_names.append(loan_name)

                        if len(official_names) == 10:
                            print(f"  STEP 2: Success. Found 10 names.")
                            return official_names

        #print(f"  Success. Found {len(official_names)} names.")
        return official_names[:10]

    except Exception as e:
        print(f"    ERROR - Failed to parse: {e}")
        return []


def extract_top10_appendix(full_text):
    """STEP 3: Extract the Appendix: Top 10 loan summaries section."""

    start_heading = "Appendix: Top 10 loan summaries"
    end_heading = None

    try:
        idx = config.PRESALE_CONTENTS.index(start_heading)
        if idx + 1 < len(config.PRESALE_CONTENTS):
            end_heading = config.PRESALE_CONTENTS[idx + 1]
    except ValueError:
        print(f"    ERROR - '{start_heading}' not in PRESALE_CONTENTS.")
        return None
    start_pattern = re.compile(r"^\s*" + re.escape(start_heading) + r"\s*(?!\d)$", re.IGNORECASE | re.MULTILINE)
    start_search = start_pattern.search(full_text)

    if not start_search:
        print("    ERROR - Could not find appendix heading in PDF.")
        return None

    start_index = start_search.end()
    text_after_start = full_text[start_index:]

    if end_heading:
        end_pattern = re.compile(r"^\s*" + re.escape(end_heading) + r"\s*(?!\d)$", re.IGNORECASE | re.MULTILINE)
        end_match = end_pattern.search(text_after_start)
        if end_match:
            appendix_text = full_text[start_index: start_index + end_match.start()]
        else:
            appendix_text = text_after_start
    else:
        appendix_text = text_after_start

    return appendix_text


def extract_deal_factors_text(full_text):
    try:
        strengths_idx = config.PRESALE_CONTENTS.index("Credit strengths")
        challenges_idx = config.PRESALE_CONTENTS.index("Credit challenges")
    except ValueError as e:
        return None, None

    def extract_section(start_heading, end_heading):
        start_pattern = re.compile(r"^\s*" + re.escape(start_heading) + r"\s*(?!\d)$", re.IGNORECASE | re.MULTILINE)
        start_match = start_pattern.search(full_text)
        if not start_match:
            return None
        start_index = start_match.end()
        text_after = full_text[start_index:]
        end_pattern = re.compile(r"^\s*" + re.escape(end_heading) + r"\s*(?!\d)$", re.IGNORECASE | re.MULTILINE)
        end_match = end_pattern.search(text_after)
        if end_match:
            return text_after[:end_match.start()]
        return text_after

    strengths_end = config.PRESALE_CONTENTS[strengths_idx + 1]
    challenges_end = config.PRESALE_CONTENTS[challenges_idx + 1]

    strengths_text = extract_section("Credit strengths", strengths_end)
    challenges_text = extract_section("Credit challenges", challenges_end)

    if not strengths_text and not challenges_text:
        return None, None
    
    if strengths_text:
        strengths_text = strengths_text.replace('â€"', '–').replace('â€"', '—').replace('â€™', "'").replace('Â»', '»')
    if challenges_text:
        challenges_text = challenges_text.replace('â€"', '–').replace('â€"', '—').replace('â€™', "'").replace('Â»', '»')

    return strengths_text, challenges_text


def extract_collateral_description(block_text):
    """Extract collateral description text from a loan block (before Strengths section)."""
    text = block_text.strip()

    strengths_match = re.search(r'\n\s*Strengths\s*\n', text, re.IGNORECASE)
    if strengths_match:
        description_text = text[:strengths_match.start()]
    else:
        challenges_match = re.search(r'\n\s*Challenges\s*\n', text, re.IGNORECASE)
        if challenges_match:
            description_text = text[:challenges_match.start()]
        else:
            description_text = text[:3000] if len(text) > 3000 else text

    description_text = re.sub(r'\n\s*\n', '\n\n', description_text)
    description_text = re.sub(r'[ \t]+', ' ', description_text)

    return description_text.strip() if description_text else None


# =============================================================================
# PARSING
# =============================================================================

def parse_deal_factors(strengths_text, challenges_text):
    """Parse deal-level Credit strengths and Credit challenges bullets."""
    strength_factors = []
    challenge_factors = []

    for block, target_list in [(strengths_text or "", strength_factors),
                                (challenges_text or "", challenge_factors)]:
        for bullet in re.split(config.FACTOR_BULLET_REGEX, block):
            if ":" in bullet:
                try:
                    label_name, description = bullet.split(":", 1)
                    label_name = label_name.strip()
                    description = description.strip().replace("\n", " ")
                    description = description.replace('â€"', '-').replace('â€"', '—').replace('â€™', "'").replace('Â»', '»').replace('Â»', '»')
                    label_name = label_name.replace('Â»', '»').lstrip('»Â\u00bb\u00c2 ')
                    
                    if label_name and description:
                        target_list.append((label_name, description))
                except ValueError:
                    continue

    return strength_factors, challenge_factors


def parse_property_factors(loan_text):
    """Parse property-level Strengths and Challenges bullets from a loan block."""
    strength_factors = []
    challenge_factors = []

    pattern = re.compile(
        r"Strengths\s*(.*?)\s*Challenges\s*(.*?)"
        r"(?=\n\s*(?:Cash flow analysis|Moody(?:'s)? Ratings|Structured Finance|Exhibit\s+\d|[A-Z][^\n]+:)|\Z)",
        re.DOTALL | re.IGNORECASE
    )

    match = pattern.search(loan_text)
    if not match:
        return strength_factors, challenge_factors

    strengths_block = match.group(1).strip()
    challenges_block = match.group(2).strip()

    for block, target_list in [(strengths_block, strength_factors),
                                (challenges_block, challenge_factors)]:
        for bullet in re.split(config.FACTOR_BULLET_REGEX, block):
            if ":" in bullet:
                try:
                    label_name, description = bullet.split(":", 1)
                    label_name = label_name.strip()
                    label_name = label_name.lstrip('»Â\u00bb\u00c2 ')  # strip bullet artifacts from label
                    description = description.strip().replace("\n", " ")
                    description = description.replace('â€"', '–').replace('â€"', '—').replace('â€™', "'").replace('Â»', '»')
                    label_name = label_name.replace('Â»', '»').lstrip('»Â\u00bb\u00c2 ')

                    if label_name and description:
                        target_list.append((label_name, description))
                except ValueError:
                    continue

    return strength_factors, challenge_factors


# =============================================================================
# SPLITTING
# =============================================================================

def split_top10_appendix_by_loan(appendix_text, official_name_list):
    """STEP 4: Split appendix into loan blocks and extract names + descriptions."""

    collateral_blocks = re.split(
        rf'{config.APPENDIX_SPLIT_HEADINGS["LOAN_CHUNK"]}',
        appendix_text,
        flags=re.IGNORECASE
    )

    if len(collateral_blocks) < 10:
       # print(f"    WARNING: Only {len(collateral_blocks)} blocks found (expected 10+).")
        return []

    loan_blocks = []

    for i, block in enumerate(collateral_blocks[1:]):
        clean_chunk_text = block.replace("\n", " ").strip()
        match = config.APPENDIX_NAME_EXTRACTOR_REGEX.search(clean_chunk_text)

        if not match:
            #print(f"    Block {i+1}: No name match found, skipping.")
            continue

        extracted_name = match.group(1).strip()

        # Strip false prefixes and bullet artifacts
        extracted_name = re.sub(
            r'^(?:the\s+)?(?:mortgage\s+)?(?:loan\s+)?(?:is\s+)?',
            '', extracted_name, flags=re.IGNORECASE
        ).strip()
        extracted_name = extracted_name.replace('Â»', '»').lstrip('»Â\u00bb\u00c2 ')

        # Try fuzzy match against official names from Top 20 table
        best_match = get_close_matches(extracted_name, official_name_list, n=1, cutoff=0.5)
        if best_match:
            final_name = best_match[0]
        else:
            # Fallback: check if any official name appears verbatim in the block
            final_name = extracted_name
            for name in official_name_list:
                if name.lower() in clean_chunk_text.lower():
                    final_name = name
                    break

        collateral_desc = extract_collateral_description(block)

        loan_blocks.append((final_name, collateral_desc, block))

    print(f"  Extracted {len(loan_blocks)} loan blocks.")
    return loan_blocks

# =============================================================================
# SAVING
# =============================================================================

def save_deal_factors(deal_id, strengths, challenges, cursor):
    """STEP 3b: Save deal-level strengths and challenges to database."""
    total_strengths = 0
    total_challenges = 0

    for label, text in strengths:
        label_id = get_or_create_deal_factor_label(cursor, label)
        cursor.execute(
            "INSERT INTO Deal_Factors (deal_id, sentiment, label_id, factor_text) VALUES (?, ?, ?, ?)",
            (deal_id, "Strength", label_id, text)
        )
        total_strengths += 1

    for label, text in challenges:
        label_id = get_or_create_deal_factor_label(cursor, label)
        cursor.execute(
            "INSERT INTO Deal_Factors (deal_id, sentiment, label_id, factor_text) VALUES (?, ?, ?, ?)",
            (deal_id, "Challenge", label_id, text)
        )
        total_challenges += 1



def save_loan_blocks(loan_blocks, deal_id, cursor):
    """STEP 5: Save properties and property-level factors to database."""

    total_strengths = 0
    total_challenges = 0

    for property_name, collateral_desc, loan_text in loan_blocks:
        property_id = get_or_create_property(cursor, deal_id, property_name, collateral_desc)

        strengths, challenges = parse_property_factors(loan_text)

        if not strengths and not challenges:
            continue

       # print(f"{property_name}: {len(strengths)} strengths, {len(challenges)} challenges")

        for label, desc in strengths:
            label_id = get_or_create_property_factor_label(cursor, label)
            cursor.execute(
                "INSERT INTO Property_Factors (property_id, sentiment, label_id, factor_text) VALUES (?, ?, ?, ?)",
                (property_id, "Strength", label_id, desc)
            )

        for label, desc in challenges:
            label_id = get_or_create_property_factor_label(cursor, label)
            cursor.execute(
                "INSERT INTO Property_Factors (property_id, sentiment, label_id, factor_text) VALUES (?, ?, ?, ?)",
                (property_id, "Challenge", label_id, desc)
            )

        total_strengths += len(strengths)
        total_challenges += len(challenges)

    print(f"    Success. Total: {total_strengths} strengths, {total_challenges} challenges.")


def archive_file(source_path, archive_dir, pdf_file, deal_name):
    """Move processed PDF to archive folder after successful processing."""
    try:
        if not os.path.exists(archive_dir):
            os.makedirs(archive_dir)
        destination_path = os.path.join(archive_dir, pdf_file)
        shutil.move(source_path, destination_path)
        print(f"  Archived: '{pdf_file}'")

        if os.path.exists(config.INTAKE_LOG_FILE):
            df = pd.read_csv(config.INTAKE_LOG_FILE)
            df.loc[df["Deal Name"] == deal_name, "Status"] = "Databased"
            df.to_csv(config.INTAKE_LOG_FILE, index=False)
            print(f"    Log updated: '{deal_name} marked as Databased.")

    except Exception as e:
        print(f"  WARNING: Could not archive file: {e}")


# =============================================================================
# MAIN PROCESSING
# =============================================================================

def process_all_pdfs(conn):
    """Process all PDFs in the processing folder."""
    cursor = conn.cursor()

    for pdf_file in os.listdir(config.PROCESSING_FOLDER):
        deal_type = None
        for prefix in config.PROCESS_DEAL_TYPES:
            if pdf_file.startswith(f"{prefix}_"):
                deal_type = prefix
                break

        if not deal_type or not pdf_file.endswith(".pdf"):
            continue

        full_pdf_path = os.path.join(config.PROCESSING_FOLDER, pdf_file)

        try:
            name_and_suffix = pdf_file.replace(f"{deal_type}_", "", 1)
            deal_name = name_and_suffix.replace("_presale.pdf", "").replace("_", " ")

            print(f"\n{'='*60}")
            print(f"Processing: {deal_name} (Type: {deal_type})")
            print(f"{'='*60}")

            deal_id, was_found = get_or_create_deal(cursor, deal_name, deal_type)
            if was_found:
                print(f"SKIPPED: Already in database.")
                continue

            # STEP 1: Extract and clean full text
            print(f"Extracting text from PDF...")
            full_text = ""
            official_loan_names = []

            with pdfplumber.open(full_pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text(x_tolerance=2, y_tolerance=2)
                    if page_text:
                        cleaned = ftfy.fix_text(page_text)
                        cleaned = cleaned.replace('â€"', '–').replace('â€"', '—').replace('â€™', "'").replace('â€œ', '"').replace('â€\x9d', '"').replace('Â»', '»').replace('Â·', '·')
                        full_text += strip_page_headers_and_footers(cleaned) + "\n"

                if not full_text:
                    print("    ERROR: No text extracted. Skipping.")
                    continue
                #print(f"    Success. {len(full_text)} characters.")

                # STEP 2: Extract loan names from Top 20 table
                official_loan_names = extract_top20_loan_names(pdf)

            if not official_loan_names:
                print("  ERROR: Could not get loan names. Skipping.")
                continue

            # STEP 3: Extract Top 10 appendix text
            appendix_text = extract_top10_appendix(full_text)
            if not appendix_text:
                print("  ERROR: Could not get appendix. Skipping.")
                continue

            # STEP 3b: Extract and save deal-level factors
            strengths_text, challenges_text = extract_deal_factors_text(full_text)
            if strengths_text or challenges_text:
                deal_strengths, deal_challenges = parse_deal_factors(strengths_text, challenges_text)
                save_deal_factors(deal_id, deal_strengths, deal_challenges, cursor)
            else:
                print("  WARNING: Could not extract deal-level factors. Continuing.")

            # STEP 4: Split appendix into individual loan blocks
            loan_blocks = split_top10_appendix_by_loan(appendix_text, official_loan_names)
            if not loan_blocks:
                print("  ERROR: Could not extract loan blocks. Skipping.")
                continue

            # STEP 5: Save properties and property-level factors
            save_loan_blocks(loan_blocks, deal_id, cursor)

            conn.commit()
            print(f"\n SUCCESS: Saved '{deal_name}' to database.")

            archive_file(full_pdf_path, config.ARCHIVE_FOLDER, pdf_file, deal_name)

        except Exception as e:
            print(f"  CRITICAL ERROR: {e}")
            conn.rollback()


def main():
    setup_database()
    conn = sqlite3.connect(config.DATABASE_FILE)

    try:
        process_all_pdfs(conn)
    except Exception as e:
        print(f"Critical error: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
