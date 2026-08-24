import re
import shutil
import sqlite3
from difflib import get_close_matches

import ftfy
import pandas as pd
import pdfplumber

import config_v2


def connect_database():
    conn = sqlite3.connect(config_v2.DATABASE_FILE)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def setup_database(conn):
    config_v2.ARCHIVE_FOLDER.mkdir(
        parents=True,
        exist_ok=True
    )

    config_v2.PROCESSING_FOLDER.mkdir(
        parents=True,
        exist_ok=True
    )

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Deals (
            deal_id INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_name TEXT NOT NULL UNIQUE,
            deal_type TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Deal_Factor_Labels (
            label_id INTEGER PRIMARY KEY AUTOINCREMENT,
            label_name TEXT NOT NULL UNIQUE,
            category TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Deal_Factors (
            deal_factor_id INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_id INTEGER,
            sentiment TEXT NOT NULL,
            label_id INTEGER,
            factor_text TEXT,
            FOREIGN KEY (deal_id) REFERENCES Deals(deal_id),
            FOREIGN KEY (label_id) REFERENCES Deal_Factor_Labels(label_id)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Properties (
            property_id INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_id INTEGER,
            property_name TEXT NOT NULL,
            property_type TEXT,
            property_subtype TEXT,
            collateral_description TEXT,
            FOREIGN KEY (deal_id) REFERENCES Deals(deal_id),
            UNIQUE (deal_id, property_name)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Property_Factor_Labels (
            label_id INTEGER PRIMARY KEY AUTOINCREMENT,
            label_name TEXT NOT NULL UNIQUE,
            category TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Property_Factors (
            factor_id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER,
            sentiment TEXT NOT NULL,
            label_id INTEGER,
            factor_text TEXT,
            FOREIGN KEY (property_id) REFERENCES Properties(property_id),
            FOREIGN KEY (label_id) REFERENCES Property_Factor_Labels(label_id)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS NCF_Analysis (
            ncf_analysis_id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL UNIQUE,
            variance_pct REAL NOT NULL,
            direction TEXT NOT NULL,
            primary_drivers_text TEXT,
            intro_text TEXT,
            FOREIGN KEY (property_id) REFERENCES Properties(property_id),
            CHECK (direction IN ('below', 'above'))
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS NCF_Haircuts (
            haircut_id INTEGER PRIMARY KEY AUTOINCREMENT,
            ncf_analysis_id INTEGER NOT NULL,
            sequence_number INTEGER NOT NULL,
            haircut_text TEXT NOT NULL,
            FOREIGN KEY (ncf_analysis_id)
                REFERENCES NCF_Analysis(ncf_analysis_id),
            UNIQUE (ncf_analysis_id, sequence_number)
        );
    """)

    conn.commit()


def get_existing_deal_id(cursor, deal_name):
    cursor.execute(
        "SELECT deal_id FROM Deals WHERE deal_name = ?",
        (deal_name,)
    )

    row = cursor.fetchone()

    return row[0] if row else None


def create_deal(cursor, deal_name, deal_type):
    cursor.execute(
        """
        INSERT INTO Deals (
            deal_name,
            deal_type
        )
        VALUES (?, ?)
        """,
        (
            deal_name,
            deal_type
        )
    )

    return cursor.lastrowid


def get_or_create_property(
    cursor,
    deal_id,
    property_name,
    collateral_description=None
):
    property_name = clean_inline_text(property_name)

    cursor.execute(
        """
        SELECT property_id
        FROM Properties
        WHERE deal_id = ?
          AND property_name = ?
        """,
        (
            deal_id,
            property_name
        )
    )

    row = cursor.fetchone()

    if row:
        if collateral_description:
            cursor.execute(
                """
                UPDATE Properties
                SET collateral_description = ?
                WHERE property_id = ?
                """,
                (
                    collateral_description,
                    row[0]
                )
            )

        return row[0]

    cursor.execute(
        """
        INSERT INTO Properties (
            deal_id,
            property_name,
            collateral_description
        )
        VALUES (?, ?, ?)
        """,
        (
            deal_id,
            property_name,
            collateral_description
        )
    )

    return cursor.lastrowid


def get_or_create_label(
    cursor,
    table_name,
    label_name
):
    label_name = clean_inline_text(label_name)

    cursor.execute(
        f"""
        SELECT label_id
        FROM {table_name}
        WHERE label_name = ?
        """,
        (label_name,)
    )

    row = cursor.fetchone()

    if row:
        return row[0]

    cursor.execute(
        f"""
        INSERT INTO {table_name} (
            label_name
        )
        VALUES (?)
        """,
        (label_name,)
    )

    return cursor.lastrowid

def clean_text(text):
    if text is None:
        return None

    text = ftfy.fix_text(str(text))

    for bad, good in config_v2.TEXT_REPLACEMENTS.items():
        text = text.replace(
            bad,
            good
        )

    text = config_v2.ZERO_WIDTH_REGEX.sub(
        "",
        text
    )

    text = text.replace(
        "\r\n",
        "\n"
    )

    text = text.replace(
        "\r",
        "\n"
    )

    return text


def clean_inline_text(text):
    if text is None:
        return None

    text = clean_text(text)

    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def strip_page_headers_and_footers(page_text):
    cleaned_lines = []

    for line in page_text.splitlines():
        stripped = line.strip()

        if (
            len(stripped)
            < config_v2.PAGE_FOOTER_MAX_LENGTH
            and config_v2.PAGE_FOOTER_REGEX.search(stripped)
        ):
            continue

        if config_v2.PAGE_HEADER_REGEX.match(stripped):
            continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def find_standalone_heading(
    text,
    heading,
    start=0,
    use_last=False
):
    pattern = re.compile(
        r"^\s*"
        + re.escape(heading)
        + r"\s*$",
        re.IGNORECASE | re.MULTILINE
    )

    matches = list(
        pattern.finditer(
            text,
            start
        )
    )

    if not matches:
        return None

    if use_last:
        return matches[-1]

    return matches[0]


def get_next_presale_heading(current_heading):
    try:
        index = config_v2.PRESALE_CONTENTS.index(
            current_heading
        )
    except ValueError:
        return None

    if index + 1 >= len(config_v2.PRESALE_CONTENTS):
        return None

    return config_v2.PRESALE_CONTENTS[
        index + 1
    ]


def extract_section_between_headings(
    full_text,
    start_heading,
    end_heading=None
):
    start_match = find_standalone_heading(
        full_text,
        start_heading,
        use_last=True
    )

    if not start_match:
        return None

    start_index = start_match.end()
    text_after = full_text[start_index:]

    if not end_heading:
        return text_after.strip()

    end_match = find_standalone_heading(
        text_after,
        end_heading
    )

    if not end_match:
        return text_after.strip()

    return text_after[
        :end_match.start()
    ].strip()


def extract_full_text(pdf):
    pages = []

    for page in pdf.pages:
        page_text = page.extract_text(
            x_tolerance=config_v2.PDF_X_TOLERANCE,
            y_tolerance=config_v2.PDF_Y_TOLERANCE
        )

        if not page_text:
            continue

        page_text = clean_text(page_text)

        page_text = strip_page_headers_and_footers(
            page_text
        )

        pages.append(page_text)

    return "\n".join(pages).strip()

def extract_top20_loan_names(pdf):
    target_page_index = None

    for index, page in enumerate(pdf.pages):
        page_text = page.extract_text(
            x_tolerance=config_v2.PDF_X_TOLERANCE,
            y_tolerance=config_v2.PDF_Y_TOLERANCE
        )

        if not page_text:
            continue

        page_text = clean_text(page_text)
        lower_text = page_text.lower()

        if all(
            keyword.lower() in lower_text
            for keyword
            in config_v2.LOAN_TABLE_HEADER_KEYWORDS
        ):
            target_page_index = index
            break

    if target_page_index is None:
        return []

    page_text = pdf.pages[
        target_page_index
    ].extract_text(
        x_tolerance=config_v2.PDF_X_TOLERANCE,
        y_tolerance=config_v2.PDF_Y_TOLERANCE
    )

    page_text = clean_text(
        page_text or ""
    )

    if target_page_index + 1 < len(pdf.pages):
        next_page_text = pdf.pages[
            target_page_index + 1
        ].extract_text(
            x_tolerance=config_v2.PDF_X_TOLERANCE,
            y_tolerance=config_v2.PDF_Y_TOLERANCE
        )

        page_text += (
            "\n"
            + clean_text(next_page_text or "")
        )

    header_match = (
        config_v2.LOAN_TABLE_HEADER_REGEX.search(
            page_text
        )
    )

    if not header_match:
        return []

    footer_match = (
        config_v2.LOAN_TABLE_FOOTER_REGEX.search(
            page_text,
            header_match.end()
        )
    )

    footer_index = (
        footer_match.start()
        if footer_match
        else len(page_text)
    )

    table_text = page_text[
        header_match.end():footer_index
    ]

    official_names = []

    for line in table_text.splitlines():
        line = line.strip()

        if not line:
            continue

        row_match = (
            config_v2.LOAN_NAME_PLAN_B_REGEX.match(
                line
            )
        )

        if not row_match:
            continue

        raw_name = row_match.group(1).strip()

        if (
            not raw_name
            or raw_name.lower() == "loan name"
        ):
            continue

        clean_match = (
            config_v2.LOAN_NAME_CLEANER_REGEX.match(
                raw_name
            )
        )

        if not clean_match:
            continue

        loan_name = clean_inline_text(
            clean_match.group(1)
        )

        if (
            loan_name
            and loan_name not in official_names
        ):
            official_names.append(loan_name)

        if (
            len(official_names)
            == config_v2.TOP_LOAN_LIMIT
        ):
            break

    return official_names


def extract_top10_appendix(full_text):
    start_heading = (
        config_v2.SECTION_HEADINGS[
            "TOP10_APPENDIX"
        ]
    )

    end_heading = get_next_presale_heading(
        start_heading
    )

    return extract_section_between_headings(
        full_text,
        start_heading,
        end_heading
    )


def extract_deal_factors_text(full_text):
    strengths_heading = (
        config_v2.SECTION_HEADINGS[
            "DEAL_STRENGTHS"
        ]
    )

    challenges_heading = (
        config_v2.SECTION_HEADINGS[
            "DEAL_CHALLENGES"
        ]
    )

    strengths_end = get_next_presale_heading(
        strengths_heading
    )

    challenges_end = get_next_presale_heading(
        challenges_heading
    )

    strengths_text = extract_section_between_headings(
        full_text,
        strengths_heading,
        strengths_end
    )

    challenges_text = extract_section_between_headings(
        full_text,
        challenges_heading,
        challenges_end
    )

    return (
        strengths_text,
        challenges_text
    )


def extract_collateral_description(block_text):
    block_text = clean_text(
        block_text
    ).strip()

    boundaries = []

    for heading_key in (
        "PROPERTY_STRENGTHS",
        "PROPERTY_CHALLENGES"
    ):
        heading = (
            config_v2.SECTION_HEADINGS[
                heading_key
            ]
        )

        match = find_standalone_heading(
            block_text,
            heading
        )

        if match:
            boundaries.append(
                match.start()
            )

    if boundaries:
        description_text = block_text[
            :min(boundaries)
        ]
    else:
        description_text = block_text[
            :config_v2.COLLATERAL_DESCRIPTION_MAX_CHARS
        ]

    description_text = re.sub(
        r"\n\s*\n",
        "\n\n",
        description_text
    )

    description_text = re.sub(
        r"[ \t]+",
        " ",
        description_text
    )

    return (
        description_text.strip()
        or None
    )

def parse_labeled_factor_section(section_text):
    factors = []

    if not section_text:
        return factors

    current_label = None
    current_text_parts = []

    def flush_current():
        if current_label is None:
            return

        factor_text = clean_inline_text(
            " ".join(current_text_parts)
        )

        if factor_text:
            factors.append(
                (
                    clean_inline_text(current_label),
                    factor_text
                )
            )

    for raw_line in clean_text(
        section_text
    ).splitlines():
        line = raw_line.strip()

        if not line:
            continue

        match = (
            config_v2.LABELED_FACTOR_START_REGEX.match(
                line
            )
        )

        if match:
            flush_current()

            current_label = match.group(
                "label"
            )

            current_text_parts = []

            first_text = clean_inline_text(
                match.group("text")
            )

            if first_text:
                current_text_parts.append(
                    first_text
                )

            continue

        if current_label is not None:
            continuation = (
                config_v2.CONTINUATION_BULLET_PREFIX_REGEX.sub(
                    "",
                    line
                )
            )

            continuation = clean_inline_text(
                continuation
            )

            if continuation:
                current_text_parts.append(
                    continuation
                )

    flush_current()

    return factors


def parse_deal_factors(
    strengths_text,
    challenges_text
):
    strengths = parse_labeled_factor_section(
        strengths_text
    )

    challenges = parse_labeled_factor_section(
        challenges_text
    )

    return (
        strengths,
        challenges
    )


def find_property_factor_end(
    loan_text,
    start
):
    end_positions = []

    ncf_match = (
        config_v2.NCF_OPENING_REGEX.search(
            loan_text,
            start
        )
    )

    if ncf_match:
        end_positions.append(
            ncf_match.start()
        )

    for heading in (
        config_v2.PROPERTY_FACTOR_END_HEADERS
    ):
        match = find_standalone_heading(
            loan_text,
            heading,
            start=start
        )

        if match:
            end_positions.append(
                match.start()
            )

    if end_positions:
        return min(end_positions)

    return len(loan_text)


def parse_property_factors(loan_text):
    loan_text = clean_text(loan_text)

    strengths_heading = (
        config_v2.SECTION_HEADINGS[
            "PROPERTY_STRENGTHS"
        ]
    )

    challenges_heading = (
        config_v2.SECTION_HEADINGS[
            "PROPERTY_CHALLENGES"
        ]
    )

    strengths_match = find_standalone_heading(
        loan_text,
        strengths_heading
    )

    if not strengths_match:
        return [], []

    challenges_match = find_standalone_heading(
        loan_text,
        challenges_heading,
        start=strengths_match.end()
    )

    if not challenges_match:
        return [], []

    strengths_text = loan_text[
        strengths_match.end():
        challenges_match.start()
    ]

    challenges_start = (
        challenges_match.end()
    )

    challenges_end = find_property_factor_end(
        loan_text,
        challenges_start
    )

    challenges_text = loan_text[
        challenges_start:
        challenges_end
    ]

    strengths = parse_labeled_factor_section(
        strengths_text
    )

    challenges = parse_labeled_factor_section(
        challenges_text
    )

    return (
        strengths,
        challenges
    )

def find_first_heading_start(
    text,
    headings,
    start
):
    positions = []

    for heading in headings:
        match = find_standalone_heading(
            text,
            heading,
            start=start
        )

        if match:
            positions.append(
                match.start()
            )

    if positions:
        return min(positions)

    return len(text)


def parse_ncf_details(loan_text):
    loan_text = clean_text(loan_text)

    opening_match = (
        config_v2.NCF_OPENING_REGEX.search(
            loan_text
        )
    )

    if not opening_match:
        return None

    end_index = find_first_heading_start(
        loan_text,
        config_v2.NCF_END_HEADERS,
        opening_match.end()
    )

    section_text = loan_text[
        opening_match.start():
        end_index
    ].strip()

    bullet_match = (
        config_v2.NCF_BULLET_REGEX.search(
            section_text
        )
    )

    if bullet_match:
        intro_text = section_text[
            :bullet_match.start()
        ]

        bullets_text = section_text[
            bullet_match.start():
        ]
    else:
        intro_text = section_text
        bullets_text = ""

    intro_text = clean_inline_text(
        intro_text
    )

    drivers_match = (
        config_v2.NCF_DRIVERS_REGEX.search(
            intro_text
        )
    )

    if drivers_match:
        primary_drivers_text = clean_inline_text(
            drivers_match.group(1)
        )
    else:
        primary_drivers_text = None

    haircuts = []

    if bullets_text:
        for raw_bullet in (
            config_v2.NCF_BULLET_REGEX.split(
                bullets_text
            )
        ):
            haircut_text = clean_inline_text(
                raw_bullet
            )

            if haircut_text:
                haircuts.append(
                    haircut_text
                )

    return {
        "variance_pct": float(
            opening_match.group(1)
        ),
        "direction": (
            opening_match.group(2).lower()
        ),
        "primary_drivers_text": (
            primary_drivers_text
        ),
        "intro_text": intro_text,
        "haircuts": haircuts
    }


def map_loan_name(
    extracted_name,
    clean_chunk_text,
    official_name_list
):
    extracted_name = (
        config_v2.LOAN_NAME_PREFIX_REGEX.sub(
            "",
            clean_inline_text(extracted_name)
        )
    )

    extracted_name = extracted_name.lstrip(
        "» "
    )

    best_match = get_close_matches(
        extracted_name,
        official_name_list,
        n=1,
        cutoff=config_v2.LOAN_NAME_MATCH_CUTOFF
    )

    if best_match:
        return best_match[0]

    lower_chunk = (
        clean_chunk_text.lower()
    )

    for official_name in official_name_list:
        if (
            official_name.lower()
            in lower_chunk
        ):
            return official_name

    return extracted_name


def split_top10_appendix_by_loan(
    appendix_text,
    official_name_list
):
    heading = (
        config_v2.SECTION_HEADINGS[
            "COLLATERAL_DESCRIPTION"
        ]
    )

    blocks = re.split(
        r"^\s*"
        + re.escape(heading)
        + r"\s*$",
        appendix_text,
        flags=re.IGNORECASE | re.MULTILINE
    )

    loan_blocks = blocks[
        1:
        config_v2.TOP_LOAN_LIMIT + 1
    ]

    if (
        len(loan_blocks)
        < config_v2.TOP_LOAN_LIMIT
    ):
        print(
            f"  ERROR: Found {len(loan_blocks)} "
            f"loan blocks; expected "
            f"{config_v2.TOP_LOAN_LIMIT}."
        )

        return []

    results = []

    for block in loan_blocks:
        clean_chunk_text = clean_inline_text(
            block
        )

        name_match = (
            config_v2.APPENDIX_NAME_EXTRACTOR_REGEX.search(
                clean_chunk_text
            )
        )

        if not name_match:
            continue

        final_name = map_loan_name(
            name_match.group(1),
            clean_chunk_text,
            official_name_list
        )

        collateral_description = (
            extract_collateral_description(
                block
            )
        )

        results.append(
            (
                final_name,
                collateral_description,
                block
            )
        )

    if (
        len(results)
        < config_v2.TOP_LOAN_LIMIT
    ):
        print(
            f"  ERROR: Parsed only "
            f"{len(results)} of "
            f"{config_v2.TOP_LOAN_LIMIT} "
            f"loan blocks."
        )

        return []

    print(
        f"  Extracted "
        f"{len(results)} loan blocks."
    )

    return results

def insert_factor(
    cursor,
    factor_table,
    entity_column,
    entity_id,
    sentiment,
    label_id,
    factor_text
):
    cursor.execute(
        f"""
        INSERT INTO {factor_table} (
            {entity_column},
            sentiment,
            label_id,
            factor_text
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            entity_id,
            sentiment,
            label_id,
            factor_text
        )
    )


def save_deal_factors(
    deal_id,
    strengths,
    challenges,
    cursor
):
    for label, text in strengths:
        label_id = get_or_create_label(
            cursor,
            "Deal_Factor_Labels",
            label
        )

        insert_factor(
            cursor,
            "Deal_Factors",
            "deal_id",
            deal_id,
            "Strength",
            label_id,
            text
        )

    for label, text in challenges:
        label_id = get_or_create_label(
            cursor,
            "Deal_Factor_Labels",
            label
        )

        insert_factor(
            cursor,
            "Deal_Factors",
            "deal_id",
            deal_id,
            "Challenge",
            label_id,
            text
        )

    return (
        len(strengths),
        len(challenges)
    )


def save_ncf_data(
    cursor,
    property_id,
    ncf_data
):
    if not ncf_data:
        return 0

    cursor.execute(
        """
        SELECT ncf_analysis_id
        FROM NCF_Analysis
        WHERE property_id = ?
        """,
        (property_id,)
    )

    row = cursor.fetchone()

    if row:
        ncf_analysis_id = row[0]

        cursor.execute(
            """
            UPDATE NCF_Analysis
            SET variance_pct = ?,
                direction = ?,
                primary_drivers_text = ?,
                intro_text = ?
            WHERE ncf_analysis_id = ?
            """,
            (
                ncf_data["variance_pct"],
                ncf_data["direction"],
                ncf_data["primary_drivers_text"],
                ncf_data["intro_text"],
                ncf_analysis_id
            )
        )

        cursor.execute(
            """
            DELETE FROM NCF_Haircuts
            WHERE ncf_analysis_id = ?
            """,
            (ncf_analysis_id,)
        )

    else:
        cursor.execute(
            """
            INSERT INTO NCF_Analysis (
                property_id,
                variance_pct,
                direction,
                primary_drivers_text,
                intro_text
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                property_id,
                ncf_data["variance_pct"],
                ncf_data["direction"],
                ncf_data["primary_drivers_text"],
                ncf_data["intro_text"]
            )
        )

        ncf_analysis_id = (
            cursor.lastrowid
        )

    for (
        sequence_number,
        haircut_text
    ) in enumerate(
        ncf_data["haircuts"],
        start=1
    ):
        cursor.execute(
            """
            INSERT INTO NCF_Haircuts (
                ncf_analysis_id,
                sequence_number,
                haircut_text
            )
            VALUES (?, ?, ?)
            """,
            (
                ncf_analysis_id,
                sequence_number,
                haircut_text
            )
        )

    return len(
        ncf_data["haircuts"]
    )


def save_loan_blocks(
    loan_blocks,
    deal_id,
    cursor
):
    total_strengths = 0
    total_challenges = 0
    total_ncf_analyses = 0
    total_ncf_haircuts = 0

    for (
        property_name,
        collateral_description,
        loan_text
    ) in loan_blocks:
        property_id = get_or_create_property(
            cursor,
            deal_id,
            property_name,
            collateral_description
        )

        strengths, challenges = (
            parse_property_factors(
                loan_text
            )
        )

        ncf_data = parse_ncf_details(
            loan_text
        )

        for label, text in strengths:
            label_id = get_or_create_label(
                cursor,
                "Property_Factor_Labels",
                label
            )

            insert_factor(
                cursor,
                "Property_Factors",
                "property_id",
                property_id,
                "Strength",
                label_id,
                text
            )

        for label, text in challenges:
            label_id = get_or_create_label(
                cursor,
                "Property_Factor_Labels",
                label
            )

            insert_factor(
                cursor,
                "Property_Factors",
                "property_id",
                property_id,
                "Challenge",
                label_id,
                text
            )

        haircut_count = save_ncf_data(
            cursor,
            property_id,
            ncf_data
        )

        total_strengths += len(
            strengths
        )

        total_challenges += len(
            challenges
        )

        if ncf_data:
            total_ncf_analyses += 1
            total_ncf_haircuts += (
                haircut_count
            )

            ncf_status = (
                f"{ncf_data['variance_pct']}% "
                f"{ncf_data['direction']}, "
                f"{haircut_count} NCF haircuts"
            )
        else:
            ncf_status = (
                "no NCF detail"
            )

        print(
            f"    {property_name}: "
            f"{len(strengths)} strengths, "
            f"{len(challenges)} challenges, "
            f"{ncf_status}"
        )

    return {
        "strengths": total_strengths,
        "challenges": total_challenges,
        "ncf_analyses": total_ncf_analyses,
        "ncf_haircuts": total_ncf_haircuts
    }

def derive_deal_info(pdf_name):
    if not pdf_name.lower().endswith(
        ".pdf"
    ):
        return None, None

    for deal_type in (
        config_v2.PROCESS_DEAL_TYPES
    ):
        prefix = f"{deal_type}_"

        if not pdf_name.startswith(prefix):
            continue

        remaining = pdf_name[
            len(prefix):
        ]

        if remaining.endswith(
            config_v2.PRESALE_FILE_SUFFIX
        ):
            deal_name = remaining[
                :-len(
                    config_v2.PRESALE_FILE_SUFFIX
                )
            ]
        else:
            deal_name = remaining[:-4]

        deal_name = deal_name.replace(
            "_",
            " "
        ).strip()

        return (
            deal_type,
            deal_name
        )

    return None, None


def archive_file(
    source_path,
    deal_name
):
    try:
        config_v2.ARCHIVE_FOLDER.mkdir(
            parents=True,
            exist_ok=True
        )

        destination_path = (
            config_v2.ARCHIVE_FOLDER
            / source_path.name
        )

        shutil.move(
            str(source_path),
            str(destination_path)
        )

        if (
            config_v2.INTAKE_LOG_FILE.exists()
        ):
            df = pd.read_csv(
                config_v2.INTAKE_LOG_FILE
            )

            df.loc[
                df["Deal Name"] == deal_name,
                "Status"
            ] = "Databased"

            df.to_csv(
                config_v2.INTAKE_LOG_FILE,
                index=False
            )

        print(
            f"  Archived: "
            f"{source_path.name}"
        )

    except Exception as exc:
        print(
            f"  WARNING: Database saved, "
            f"but archive failed: {exc}"
        )


def process_pdf(
    pdf_path,
    conn
):
    cursor = conn.cursor()

    deal_type, deal_name = (
        derive_deal_info(
            pdf_path.name
        )
    )

    if not deal_type:
        return

    existing_deal_id = (
        get_existing_deal_id(
            cursor,
            deal_name
        )
    )

    if existing_deal_id:
        print(
            f"SKIPPED: {deal_name} "
            f"already exists in database."
        )

        return

    print(
        f"\n{'=' * 60}"
    )

    print(
        f"Processing: {deal_name} "
        f"(Type: {deal_type})"
    )

    print(
        f"{'=' * 60}"
    )

    try:
        with pdfplumber.open(
            pdf_path
        ) as pdf:
            full_text = extract_full_text(
                pdf
            )

            if not full_text:
                print(
                    "  ERROR: No text extracted."
                )
                return

            official_loan_names = (
                extract_top20_loan_names(
                    pdf
                )
            )

        if (
            len(official_loan_names)
            < config_v2.TOP_LOAN_LIMIT
        ):
            print(
                f"  ERROR: Extracted only "
                f"{len(official_loan_names)} "
                f"official loan names."
            )

            return

        appendix_text = (
            extract_top10_appendix(
                full_text
            )
        )

        if not appendix_text:
            print(
                "  ERROR: Could not extract "
                "Top 10 appendix."
            )

            return

        loan_blocks = (
            split_top10_appendix_by_loan(
                appendix_text,
                official_loan_names
            )
        )

        if not loan_blocks:
            print(
                "  ERROR: Could not extract "
                "loan blocks."
            )

            return

        (
            strengths_text,
            challenges_text
        ) = extract_deal_factors_text(
            full_text
        )

        (
            deal_strengths,
            deal_challenges
        ) = parse_deal_factors(
            strengths_text,
            challenges_text
        )

        deal_id = create_deal(
            cursor,
            deal_name,
            deal_type
        )

        (
            deal_strength_count,
            deal_challenge_count
        ) = save_deal_factors(
            deal_id,
            deal_strengths,
            deal_challenges,
            cursor
        )

        property_totals = (
            save_loan_blocks(
                loan_blocks,
                deal_id,
                cursor
            )
        )

        conn.commit()

        print(
            f"  Deal factors: "
            f"{deal_strength_count} strengths, "
            f"{deal_challenge_count} challenges"
        )

        print(
            f"  Property factors: "
            f"{property_totals['strengths']} strengths, "
            f"{property_totals['challenges']} challenges"
        )

        print(
            f"  NCF: "
            f"{property_totals['ncf_analyses']} analyses, "
            f"{property_totals['ncf_haircuts']} haircuts"
        )

        print(
            f"  SUCCESS: Saved {deal_name}"
        )

        archive_file(
            pdf_path,
            deal_name
        )

    except Exception as exc:
        conn.rollback()

        print(
            f"  CRITICAL ERROR: "
            f"{type(exc).__name__}: {exc}"
        )


def process_all_pdfs(conn):
    for pdf_path in sorted(
        config_v2.PROCESSING_FOLDER.iterdir()
    ):
        if not pdf_path.is_file():
            continue

        deal_type, _ = derive_deal_info(
            pdf_path.name
        )

        if not deal_type:
            continue

        process_pdf(
            pdf_path,
            conn
        )


def main():
    conn = connect_database()

    try:
        setup_database(conn)
        process_all_pdfs(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
