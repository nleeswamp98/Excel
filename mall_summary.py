import pandas as pd

# ============================ CONFIG (edit these) ============================
INPUT_FILE = r"C:\Retail Sales\darrell update\clean_name_regex.xlsx"
OUTPUT_FILE = r"C:\Retail Sales\darrell update\mall_rent_summary_all_years.xlsx"         
INPUT_SHEET = 0                

PROPERTY_COL = "Property Name"
TENANT_COL = "Clean Name"
SIZE_BUCKET_COL = "Size Bucket"
SF_COL = "SF"
RENT_PSF_COL = "Gross Rent PSF"
BASE_RENT_COL = "Annual In-place Base Rent Total"
OCC_STATUS_COL = "Occupied or Vacant?"
OCC_COST_COL = "Gross Occ Cost %"

size_bins  = [
    0,
    500, 
    1000,
    1500, 
    2000,
    3000,
    4000, 
    5000,
    7500,
    10000,
    15000,
    20000,
    25000,
    50000,
    float("inf")
]

size_labels  = [
    "<500 SF",
    "500-1,000 SF",
    "1,000-1,500 SF",
    "1,500-2,000 SF",
    "2,000-3,000 SF",
    "3,000-4,000 SF",
    "4,000-5,000 SF",
    "5,000-7,500 SF",
    "7,500-10,000 SF",
    "10,000-15,000 SF",
    "15,000-20,000 SF",
    "20,000-25,000 SF",
    "25,000-50,000 SF",
    ">50,000 SF"
]

df = pd.read_excel(
    INPUT_FILE, 
    sheet_name=INPUT_SHEET
)

df = pd.read_excel(
    INPUT_FILE, 
    sheet_name=INPUT_SHEET
)

df[PROPERTY_COL] = pd.to_numeric(
    df[PROPERTY_COL],
    errors="coerce"
)

df[TENANT_COL] = pd.to_numeric(
    df[TENANT_COL],
    errors="coerce"
)

df[SF_COL] = pd.to_numeric(
    df[SF_COL],
    errors="coerce"
)

df[RENT_PSF_COL] = pd.to_numeric(
    df[RENT_PSF_COL],
    errors="coerce"
)

df[BASE_RENT_COL] = pd.to_numeric(
    df[BASE_RENT_COL],
    errors="coerce"
)

df[OCC_COST_COL] = pd.to_numeric(
    df[OCC_COST_COL],
    errors="coerce"
)

df[SIZE_BUCKET_COL] = pd.cut(
    df[SF_COL],
    bins=size_bins,
    labels=size_labels,
    right=False,
    include_lowest=True,
    ordered=True
)

print(
    df[OCC_STATUS_COL]
    .value_counts(dropna=False)
)

occupied_df = df[
    df[OCC_STATUS_COL]
    .astype(str)
    .str.strip()
    .str.upper()
    .eq("Occupied")
].copy()

occupied_df = occupied_df[
    occupied_df[PROPERTY_COL].notna()
    & occupied_df[TENANT_COL].notna()
    & occupied_df[SIZE_BUCKET_COL].notna()
].copy()

mall_store_counts = (
    occupied_df
    .groupby(
        PROPERTY_COL,
        as_index=False
    )
    .agg(
        Total_Store_Count = (
            TENANT_COL,
            "nunique"
        )
    )
    .sort_values(
        by=[
            "Total_Store_Count",
            PROPERTY_COL
        ],
        ascending=[
            False,
            True
        ]
    )
    .reset_index(drop=True)
)

mall_order = mall_store_counts[
    PROPERTY_COL
].tolist()

mall_rent_df = occupied_df[
    occupied_df[RENT_PSF_COL].notna()
    & occupied_df[SF_COL].gt(0)
].copy()

mall_average_rent = (
    mall_rent_df
    .groupby(
        [
            PROPERTY_COL,
            SIZE_BUCKET_COL
        ],
        observed=True
    )
    .agg(
        Average_Rent_PSF = (
            RENT_PSF_COL,
            "mean"
        )
    )
    .reset_index()
)

mall_rent_matrix = mall_average_rent.pivot(
    index=PROPERTY_COL,
    columns=SIZE_BUCKET_COL,
    values="Average_Rent_PSF"
)

mall_rent_matrix = mall_rent_matrix.reindex(
    index=mall_order,
    columns=size_labels
)

mall_rent_matrix.insert(
    0,
    "Total Store Count",
    mall_store_counts
    .set_index(PROPERTY_COL)
    .reindex(mall_order)["Total_Store_Count"]
)

mall_oc_df = occupied_df[
    occupied_df[OCC_COST_COL].notna()
    & occupied_df[PROPERTY_COL].notna()
    & occupied_df[SIZE_BUCKET_COL].notna()
].copy()

print("Occ Cost source column:", OCC_COST_COL)
print("Column exists:", OCC_COST_COL in mall_oc_df.columns)
print("available columns:")
print(mall_oc_df.columns.tolist())

mall_oc_matrix = pd.pivot_table(
    mall_oc_df,
    index=PROPERTY_COL,
    columns=SIZE_BUCKET_COL,
    values=OCC_COST_COL,
    aggfunc="mean",
    observed=True
)

mall_oc_matrix = mall_oc_matrix.reindex(
    index=mall_order,
    columns=size_labels
)

mall_oc_matrix.insert(
    0,
    "Total Store Count",
    mall_store_counts
    .set_index(PROPERTY_COL)
    .reindex(mall_order)["Total_Store_Count"]
)

mall_average_oc = (
    mall_oc_df
    .groupby(
        [
            PROPERTY_COL,
            SIZE_BUCKET_COL
        ],
        observed=True
    )[OCC_COST_COL]
    .mean()
    .reset_index(
        name="Average_Occupancy_Cost_Pct"
    )
)

print(mall_average_oc.columns.tolist())
print(mall_average_oc.head())

mall_oc_matrix = mall_average_rent.pivot(
    index=PROPERTY_COL,
    columns=SIZE_BUCKET_COL,
    values="Average_Occupancy_Cost_Pct"
)

mall_oc_matrix = mall_oc_matrix.reindex(
    index=mall_order,
    columns=size_labels
)

mall_oc_matrix.insert(
    0,
    "Total Store Count",
    mall_store_counts
    .set_index(PROPERTY_COL)
    .reindex(mall_order)["Total_Store_Count"]
)

mall_bucket_counts = (
    occupied_df
    .groupby(
        [
            PROPERTY_COL,
            SIZE_BUCKET_COL
        ],
        observed=True
    )
    .agg(
        Store_Count = (
            TENANT_COL,
            "nunique"
        )
    )
    .reset_index()
)

mall_count_matrix = mall_bucket_counts.pivot(
    index=PROPERTY_COL,
    columns=SIZE_BUCKET_COL,
    values="Store_Count"
)

mall_count_matrix = mall_count_matrix.reindex(
    index=mall_order,
    columns=size_labels
)

mall_count_matrix.insert(
    0,
    "Total Store Count",
    mall_store_counts
    .set_index(PROPERTY_COL)
    .reindex(mall_order)["Total_Store_Count"]
)

mall_summary = (
    mall_bucket_counts
    .merge(
        mall_average_rent,
        on = [
            PROPERTY_COL,
            SIZE_BUCKET_COL
        ],
        how="left"
    )
    .merge(
        mall_average_oc,
        on = [
            PROPERTY_COL,
            SIZE_BUCKET_COL
        ],
        how="left"
    )
    .merge(
            mall_store_counts,
            on = [
                PROPERTY_COL,
                SIZE_BUCKET_COL
            ],
            how="left"
        )    
)

mall_rank_map = {
    mall: rank
    for rank, mall in enumerate(mall_order)
}

bucket_rank_map = {
    bucket: rank
    for rank, bucket in enumerate(size_labels)
}

mall_summary["Mall_Rank"] = (
    mall_summary[PROPERTY_COL]
    .map(mall_rank_map)
)

mall_summary["Bucket_Rank"] = (
    mall_summary[SIZE_BUCKET_COL]
    .astype(str)
    .map(bucket_rank_map)
)

mall_summary = (
    mall_summary
    .sort_values(
        by = [
            "Mall_Rank",
            "Bucket_Rank"
        ],
        ascending = [
            True,
            True
        ]
    )
    .drop(
        columns = [
            "Mall_Rank",
            "Bucket_Rank"
        ]
    )
    .reset_index(drop=True)
)

with pd.ExcelWriter(
    OUTPUT_FILE,
    engine="openpyxl"
) as writer:

    mall_summary.to_excel(
        writer,
        sheet_name = "Mall Summary",
        index=False
    )

    mall_rent_matrix.to_excel(
        writer,
        sheet_name = "Mall Avg Rent"
    )

    mall_oc_matrix.to_excel(
        writer,
        sheet_name = "Mall Avg OC"
    )

    mall_count_matrix.to_excel(
            writer,
            sheet_name = "Mall Store Counts"
        )

    occupied_df.to_excel(
        writer,
        sheet_name = "Underlying Data",
        index=False
    )

    workbook = writer.book

    summary_sheet = workbook["Mall Summary"]
    rent_sheet = workbook["Mall Avg Rent"]
    oc_sheet = workbook["Mall Avg OC"]
    count_sheet = workbook["Mall Store Count"]
    detail_sheet = workbook["Underlying Data"]

    summary_sheet.freeze_panes = "A2"
    rent_sheet.freeze_panes = "B2"
    oc_sheet.freeze_panes = "B2"
    count_sheet.freeze_panes = "B2"
    detail_sheet.freeze_panes = "A2"

    summary_sheet.auto_filter.ref = summary_sheet.dimensions
    detail_sheet.auto_filter.ref = detail_sheet.dimensions

    for sheet in [
        summary_sheet,
        rent_sheet,
        oc_sheet,
        count_sheet,
        detail_sheet
    ]:
        for cell in sheet[1]:
            cell.font = cell.font.copy(
                bold = True
            )

        for row in rent_sheet.iter_rows(
            min_row=2,
            min_col=3
        ):
            for cell in row:
                cell.number_format = '$#,##0.00'

        for row in oc_sheet.iter_rows(
            min_row=2,
            min_col=3
        ):
            for cell in row:
                cell.number_format = '0.00%'

    summary_headers = {
        cell.value: cell.column
        for cell in summary_sheet[1]
    }

    rent_col_num = summary_headers[
        "Average_Rent_PSF"
    ]

    oc_col_num = summary_headers[
        "Average_Occupancy_Cost_Pct"
    ]

    for row in range(
        2,
        summary_sheet.max_row + 1
    ):
        summary_sheet.cell(
            row=row,
            column=rent_col_num
        ).number_format = '$#,##0.00'

        summary_sheet.cell(
            row=row,
            column=oc_col_num
        ).number_format = '0.00%'

    for sheet in [
        summary_sheet,
        rent_sheet,
        oc_sheet,
        count_sheet,
        detail_sheet
    ]:
        for column_cells in sheet.columns:
            max_length = 0
            column_letter = (
                column_cells[0]
                .column_letter
            )

            for cell in column_cells:
                if cell.value is not None:
                    cell_length = len(
                        str(cell.value)
                    )

                    max_length = max(
                        max_length,
                        cell_length
                    )

            sheet.column_dimensions[
                column_letter
            ].width = min(
                max_length + 2,
                35
            )

print(
    f"Finished. Output saved to: {OUTPUT_FILE}"
)

PS C:\Retail Sales\darrell update> 













                                   & "C:\Program Files\Python313\python.exe" "c:/Retail Sales/darrell update/mall_summary.py"
Occupied or Vacant?
Occupied    47204
In Place       22
Name: count, dtype: int64
Occ Cost source column: Gross Occ Cost %
Column exists: True
available columns:
['Deal Name', 'Property Name', 'Tenant Name', 'SF', 'Rent PSF', 'Occupied or Vacant?', 'Annual In-place Base Rent Total', 'Percentage Rent Total', 'In-Place Recoveries', 'Sales Year', 'Full Year Sales?', 'Total Sales', 'Sales Yr', 'Clean Name', 'Gross Rent', 'Sales PSF', 'Occ Cost %', 'Gross Rent PSF', 'Gross Occ Cost %', 'Occ Cost PSF', 'Size Bucket']
['Property Name', 'Size Bucket', 'Average_Occupancy_Cost_Pct']
Empty DataFrame
Columns: [Property Name, Size Bucket, Average_Occupancy_Cost_Pct]
Index: []
Traceback (most recent call last):
  File "C:\Users\leen5\AppData\Roaming\Python\Python313\site-packages\pandas\core\indexes\base.py", line 3641, in get_loc
    return self._engine.get_loc(casted_key)
           ~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^
  File "pandas/_libs/index.pyx", line 168, in pandas._libs.index.IndexEngine.get_loc
  File "pandas/_libs/index.pyx", line 197, in pandas._libs.index.IndexEngine.get_loc
  File "pandas/_libs/hashtable_class_helper.pxi", line 7668, in pandas._libs.hashtable.PyObjectHashTable.get_item
  File "pandas/_libs/hashtable_class_helper.pxi", line 7676, in pandas._libs.hashtable.PyObjectHashTable.get_item
KeyError: 'Average_Occupancy_Cost_Pct'

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "c:\Retail Sales\darrell update\mall_summary.py", line 242, in <module>
    mall_oc_matrix = mall_average_rent.pivot(
        index=PROPERTY_COL,
        columns=SIZE_BUCKET_COL,
        values="Average_Occupancy_Cost_Pct"
    )
  File "C:\Users\leen5\AppData\Roaming\Python\Python313\site-packages\pandas\core\frame.py", line 10986, in pivot
    return pivot(self, index=index, columns=columns, values=values)
  File "C:\Users\leen5\AppData\Roaming\Python\Python313\site-packages\pandas\core\reshape\pivot.py", line 905, in pivot
    indexed = data._constructor_sliced(data[values]._values, index=multiindex)
                                       ~~~~^^^^^^^^
  File "C:\Users\leen5\AppData\Roaming\Python\Python313\site-packages\pandas\core\frame.py", line 4378, in __getitem__
    indexer = self.columns.get_loc(key)
  File "C:\Users\leen5\AppData\Roaming\Python\Python313\site-packages\pandas\core\indexes\base.py", line 3648, in get_loc
    raise KeyError(key) from err
KeyError: 'Average_Occupancy_Cost_Pct'
PS C:\Retail Sales\darrell update> 
