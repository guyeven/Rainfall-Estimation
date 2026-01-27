import pandas as pd

xlsx = "coverage_stats_long_idw_003.xlsx"  # change to your output

def check_sheet(sheet_name, group_cols, l1_col="l1_abs_sum"):
    df = pd.read_excel(xlsx, sheet_name=sheet_name)
    needed = set(group_cols + ["n_pixels", l1_col])
    missing = [c for c in needed if c not in df.columns]
    if missing:
        print(f"[{sheet_name}] missing columns:", missing)
        return

    g = df.groupby(group_cols, dropna=False).agg(
        n_pixels_sum=("n_pixels", "sum"),
        l1_sum=(l1_col, "sum"),
        rows=("n_pixels", "size"),
    ).reset_index()

    # Just display a few groups so you can eyeball them
    print(f"\n[{sheet_name}] groups:", len(g))
    print(g.head(10).to_string(index=False))

def main():
    # Coverage sheets: buckets partition pixels (by coverage_bin)
    check_sheet("CoverageStats", ["patch_key", "mask_type"])
    check_sheet("CoverageStats_GTvsIDW", ["patch_key", "mask_type"])

    # Distance sheets: buckets partition pixels (by dist_bin)
    check_sheet("DistanceStats", ["patch_key", "mask_type"])
    check_sheet("DistanceStats_GTvsIDW", ["patch_key", "mask_type"])

if __name__ == "__main__":
    main()
