import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm.auto import tqdm

INPUT_FILE = r"C:\my_codes\geomapping\extrap.csv"
OUTPUT_FILE = r"C:\my_codes\geomapping\extrap_geomapped.csv"

ADDRESS_COL = "Address"
CITY_COL = "City"
STATE_COL = "State"
ZIP_COL = "Zip"

df = pd.read_csv(
    INPUT_FILE,
    encoding="latin1",
    dtype={
        ADDRESS_COL: "string",
        CITY_COL: "string",
        STATE_COL: "string",
        ZIP_COL: "string"
    }
)

df[ZIP_COL] = (
    df[ZIP_COL]
    .fillna("")
    .str.strip()
    .str.replace(r"\.0$", "", regex=True)
)

has_zip = df[ZIP_COL] != " "
df.loc[has_zip, ZIP_COL] = df.loc[has_zip, ZIP_COL].str.zfill(5)

retry_strategy = Retry(
    total = 4,
    backoff_factor= 1,
    status_forcelist= [429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)

session = requests.Session()
session.mount(
    "https://",
    HTTPAdapter(max_retries=retry_strategy)
)

cache = {}

def clean_value(value):
    if pd.isna(value):
        return ""
    return str(value).strip()

def geocode_row(row):
    street = clean_value(row[ADDRESS_COL])
    city = clean_value(row[CITY_COL])
    state = clean_value(row[STATE_COL])
    zip_code = clean_value(row[ZIP_COL])

    key = (
        street.upper(),
        city.upper(),
        state.upper(),
        zip_code
    )

    if key in cache:
        return cache

    if not street or not (zip_code or (city and state)):
        result = (pd.NA, pd.NA, pd.NA, "insufficient_address")
        cache[key] = result
        return result

    parameters = {
        "street": street,
        "city": city,
        "state": state,
        "zip": zip_code,
        "benchmark": "Public_AR_Current",
        "format": "json"
    }

    try:
        response = session.get(
            "https://geocoding.geo.census.gov/geocoder/locations/address",
            params=parameters,
            timeout=30
        )

        response.raise_for_status()
        matches = response.json()["result"]["addressMatches"]

        if not matches:
            result = (pd.NA, pd.NA, pd.NA, "no_match")
        else:
            match = matches[0]
            latitude = match["coordinates"]["y"]
            longitude = match["coordinates"]["x"]
            matched_address = match["matchedAddress"]

            result = (
                latitude,
                longitude,
                matched_address,
                "matched"
            )
    except (requests.RequestException, ValueError, KeyError):
        result = (pd.NA, pd.NA, pd.NA, "request_error")

        cache[key] = result
        return result

tqdm.pandas(desc="Geocoding addresses")

results = df.progress_apply(
    geocode_row,
    axis=1,
    result_type="expand"
)

results.columns = [
    "latitude",
    "longitude",
    "matched_address",
    "geocode_status"
]

df = pd.concat(
    [df, results], 
    axis=1
)

df.to_csv(
    OUTPUT_FILE,
    index=False
)

print(df["geocode_status"].value_counts(dropna=False))
print(f"Saved geocoded file to {OUTPUT_FILE}")
