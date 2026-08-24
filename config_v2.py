from pathlib import Path
import re

BASE_DIR = Path(r"/Users/nina/Documents/Projects/presale")

INTAKE_FOLDER = BASE_DIR / "intake"
PROCESSING_FOLDER = BASE_DIR / "pdfs"
ARCHIVE_FOLDER = BASE_DIR / "archive"

DATABASE_FILE = BASE_DIR / "presale_data.db"
INTAKE_LOG_FILE = BASE_DIR / "presale_log.csv"

DEAL_TYPES = {
    "large loan transaction": "llsasb",
    "single asset/single borrower": "llsasb",
    "CMBS conduit/fusion transaction": "conduit",
    "Conduit/Fusion": "conduit"
}

PROCESS_DEAL_TYPES = ["conduit"]
INTAKE_LOG_HEADERS = ["Deal Name", "Deal Type", "Status"]

TOP_LOAN_LIMIT = 10
LOAN_NAME_MATCH_CUTOFF = 0.5
COLLATERAL_DESCRIPTION_MAX_CHARS = 3000

PDF_X_TOLERANCE = 2
PDF_Y_TOLERANCE = 2
PAGE_FOOTER_MAX_LENGTH = 120

PRESALE_FILE_SUFFIX = "_presale.pdf"

SECTION_HEADINGS = {
    "DEAL_STRENGTHS": "Credit strengths",
    "DEAL_CHALLENGES": "Credit challenges",
    "TOP10_APPENDIX": "Appendix: Top 10 loan summaries",
    "COLLATERAL_DESCRIPTION": "Collateral description",
    "PROPERTY_STRENGTHS": "Strengths",
    "PROPERTY_CHALLENGES": "Challenges"
}

PRESALE_CONTENTS = [
    "Summary",
    "Credit strengths",
    "Credit challenges",
    "Key characteristics",
    "Asset description",
    "Asset analysis",
    "Securitization structure description",
    "ESG considerations",
    "Methodology and monitoring",
    "17g-7 Report of Representations & Warranties",
    "Appendix: Top 10 loan summaries",
    "Appendix: Moody's Red-Yellow-Green",
    "Appendix: Moody's Loan-Level Legal Analysis",
    "Appendix: Moody's Climate On Demand analysis",
    "Appendix: Moody's Economic Diversity Composite",
    "Appendix: The Herfindahl Index explained"
]

LOAN_TABLE_HEADER_KEYWORDS = (
    "Top 20",
    "Loan name"
)

LOAN_TABLE_HEADER_REGEX = re.compile(
    r"Loan name",
    re.IGNORECASE
)

LOAN_TABLE_FOOTER_REGEX = re.compile(
    r"Total/Wtd\.\s+Average\s+Top\s+10",
    re.IGNORECASE | re.DOTALL
)

POST_NCF_SECTION_HEADERS = [
    "Portfolio summary",
    "Tenant information",
    "Historical occupancy",
    "Historical occupancy and RevPAR",
    "Historical RevPAR",
    "Tenant overview"
]

NCF_END_HEADERS = POST_NCF_SECTION_HEADERS

PROPERTY_FACTOR_END_HEADERS = [
    "Cash flow analysis",
    *POST_NCF_SECTION_HEADERS
]

TEXT_REPLACEMENTS = {
    "â€™": "'",
    "â€˜": "'",
    "â€œ": '"',
    "â€": '"',
    "â€“": "-",
    "â€”": "-",
    "Â»": "»",
    "Â·": "·",
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "-",
    "\u00a0": " ",
    "Â": ""
}

ZERO_WIDTH_REGEX = re.compile(
    r"[\u200b-\u200d\ufeff]"
)

PAGE_FOOTER_REGEX = re.compile(
    r"(?=.*\b20\d{2}\b)(?=.*\b(?:Pre-Sale|presale)\b)",
    re.IGNORECASE
)

PAGE_HEADER_REGEX = re.compile(
    r"^(?:Moody.s Ratings|Structured Finance)",
    re.IGNORECASE
)

MAIN_BULLET_PATTERN = r"(?:»|>>>|•)"

FACTOR_BULLET_REGEX = re.compile(
    MAIN_BULLET_PATTERN
)

LABELED_FACTOR_START_REGEX = re.compile(
    rf"^\s*(?:{MAIN_BULLET_PATTERN}\s*)?"
    r"(?![-–—◦▪])"
    r"(?P<label>[^:\n]{2,120})"
    r"\s*:\s*"
    r"(?P<text>.*)$"
)

CONTINUATION_BULLET_PREFIX_REGEX = re.compile(
    r"^\s*(?:»|>>>|•|[-–—◦▪]+)\s*"
)

LOAN_NAME_PREFIX_REGEX = re.compile(
    r"^(?:the\s+)?"
    r"(?:mortgage\s+)?"
    r"(?:loan\s+)?"
    r"(?:is\s+)?",
    re.IGNORECASE
)

LOAN_NAME_CLEANER_REGEX = re.compile(
    r"""
    ^(.*?)
    (?=
        \s{2,}
        |
        \s+(?:Mixed\s+Use|Self\s+Storage|
            Hospitality|Office|Multifamily|Retail|Industrial|
            Various|Other|Manufactured\s+Housing|Anchored\s+Retail|
            Lifestyle\s+Center|Suburban|Garden|Mid\s+Rise|High\s+Rise|
            Full\s+Service|Limited\s+Service|CBD)
        |
        $
        |
        (?<![&\s])\s+\d
    )
    """,
    re.IGNORECASE | re.VERBOSE
)

LOAN_NAME_PLAN_B_REGEX = re.compile(
    r"""
    ^
    ([A-Za-z0-9\s\.'&-]+?)
    (?=\s{3,}|%|$)
    """,
    re.VERBOSE
)

APPENDIX_NAME_EXTRACTOR_REGEX = re.compile(
    r"""
    ^
    (.*?)
    \s+
    (?:loan\s+)?
    (?:
        (?:is\s+
          (?:an\s+acquisition\s+loan\s+)?
          secured\s+by
        )
        |
        (?:property\s+is\s+a)
        |
        (?:is\s+secured)
    )
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE
)

NCF_OPENING_REGEX = re.compile(
    r"(?:The\s+)?Moody[’']s\s+NCF\s+is\s+"
    r"(\d+(?:\.\d+)?)%\s+"
    r"(below|above)\s+the\s+lender[’']s(?:\s+NCF)?\.",
    re.IGNORECASE
)

NCF_DRIVERS_REGEX = re.compile(
    r"Our\s+primary\s+haircut\s+drivers\s+are\s*:?\s*"
    r"(.+?)(?:\.\s*$|$)",
    re.IGNORECASE
)

NCF_BULLET_REGEX = re.compile(
    r"»|>>>"
)

SUMMARY_START_PATTERN = re.compile(
    r"^\s*Summary\s*$",
    re.IGNORECASE | re.MULTILINE
)

SUMMARY_END_PATTERN = re.compile(
    r"^\s*(?:"
    + "|".join(re.escape(x) for x in PRESALE_CONTENTS)
    + r")",
    re.IGNORECASE | re.MULTILINE
)

PROPERTY_TYPE_LINE_REGEX = re.compile(
    r"""
    Property\s+type\s*?
    \n?
    \s*(.*?)\s*
    -
    \s*(.*?)(?=\n|$)
    """,
    re.IGNORECASE | re.VERBOSE
)
