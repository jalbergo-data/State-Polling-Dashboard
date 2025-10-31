#!/usr/bin/env python3
# extract_state_demographics.py
# Usage: python extract_state_demographics.py "All State Data.pdf"
#
# Requirements:
# pip install pymupdf pandas numpy tqdm

import sys, os, re, json
from collections import OrderedDict, defaultdict
import fitz
import pandas as pd
import numpy as np
from tqdm import tqdm

PDF = sys.argv[1] if len(sys.argv) > 1 else "All State Data.pdf"
OUT = "bottom_up_outputs"
os.makedirs(OUT, exist_ok=True)

# canonical state list (50)
STATES = ["Alabama","Alaska","Arizona","Arkansas","California","Colorado","Connecticut","Delaware","Florida","Georgia",
          "Hawaii","Idaho","Illinois","Indiana","Iowa","Kansas","Kentucky","Louisiana","Maine","Maryland",
          "Massachusetts","Michigan","Minnesota","Mississippi","Missouri","Montana","Nebraska","Nevada","New Hampshire","New Jersey",
          "New Mexico","New York","North Carolina","North Dakota","Ohio","Oklahoma","Oregon","Pennsylvania","Rhode Island","South Carolina",
          "South Dakota","Tennessee","Texas","Utah","Vermont","Virginia","Washington","West Virginia","Wisconsin","Wyoming"]

# Regex helpers
pct_re = re.compile(r'(-?\d+\.\d+%|-?\d+%)')
sample_re = re.compile(r'Sample Size[:\s]+([\d,]+)', re.IGNORECASE)
header_re = re.compile(r'2024 Presidential\s*[-–]\s*([A-Za-z ]+)', re.IGNORECASE)

def extract_pages(pdf_path):
    doc = fitz.open(pdf_path)
    pages = []
    for i in range(doc.page_count):
        pages.append(doc[i].get_text("text") or "")
    return pages

def find_state_starts(pages):
    first_page = {}
    for i, txt in enumerate(pages):
        if not txt: continue
        m = header_re.search(txt)
        if m:
            found = m.group(1).strip()
            for S in STATES:
                if S.upper() in found.upper():
                    if S not in first_page:
                        first_page[S] = i
        else:
            # fallback: look for exact uppercase state on a line
            for S in STATES:
                if f"\n{S.upper()}\n" in txt.upper():
                    if S not in first_page:
                        first_page[S] = i
    # final fallback - scan whole doc for any missing states
    for S in STATES:
        if S in first_page: continue
        for i, txt in enumerate(pages):
            if S.upper() in txt.upper():
                first_page[S] = i
                break
    ordered = OrderedDict(sorted(first_page.items(), key=lambda kv: kv[1]))
    return ordered

def parse_state_block(text):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    data = {"sample_size": None, "groups": defaultdict(list), "raw_header": lines[0] if lines else ""}
    # sample size
    for ln in lines[:80]:
        m = sample_re.search(ln)
        if m:
            try:
                data["sample_size"] = int(m.group(1).replace(",", ""))
            except:
                data["sample_size"] = None
            break
    # parse numeric group lines
    for ln in lines:
        if '%' not in ln:
            continue
        s = ' '.join(ln.split())
        # label heuristic: leading text before first number
        mlabel = re.match(r'^(.{1,80}?)\s+(-?\d+\.\d+%|-?\d+%)', s)
        label = mlabel.group(1).strip() if mlabel else None
        pcts = pct_re.findall(s)
        l = s.lower()
        # group type heuristics
        if re.search(r'18[\s\-\–]29|30[\s\-\–]44|45[\s\-\–]64|65\+|65 \+', l):
            gtype = "Age"
        elif any(k in l for k in ['white','black','hispanic','latino','asian','native','multiracial']):
            gtype = "Race"
        elif any(k in l for k in ['college','no college','some college','high school','hs','postgraduate','college grad']):
            gtype = "Education"
        elif any(k in l for k in ['men','women','non-binary','nonbinary']):
            gtype = "Gender"
        else:
            # treat as miscellaneous/detailed cell (e.g., "White non-college 18-29")
            gtype = "Misc"
        # parse numeric columns into a values dict (attempt flexible mapping)
        vals = {"total_pct": None, "dem_pct": None, "gop_pct": None, "other_pct": None}
        try:
            nums = [float(x.strip('%')) for x in pcts]
        except:
            nums = []
        if len(nums) >= 4:
            vals["total_pct"], vals["dem_pct"], vals["gop_pct"], vals["other_pct"] = nums[0], nums[1], nums[2], nums[3]
        elif len(nums) == 3:
            vals["dem_pct"], vals["gop_pct"], vals["other_pct"] = nums[0], nums[1], nums[2]
        elif len(nums) == 2:
            # maybe dem and gop only
            vals["dem_pct"], vals["gop_pct"] = nums[0], nums[1]
        else:
            # keep pcts list as fallback in values
            for idx, v in enumerate(nums):
                vals[f"col{idx}"] = v
        data["groups"][gtype].append({"label": label, "line": s, "values": vals})
    return data

def normalize_and_flatten(parsed_states):
    rows = []
    for st, pdata in parsed_states.items():
        sample = pdata.get("sample_size") or None
        for gtype, entries in pdata.get("groups", {}).items():
            for ent in entries:
                v = ent.get("values", {})
                rows.append({
                    "state": st,
                    "state_sample": sample,
                    "group_type": gtype,
                    "label": ent.get("label"),
                    "total_pct": v.get("total_pct"),
                    "dem_pct": v.get("dem_pct"),
                    "gop_pct": v.get("gop_pct"),
                    "other_pct": v.get("other_pct"),
                    "source_line": ent.get("line")
                })
    df = pd.DataFrame(rows)
    # coerce
    for c in ["total_pct","dem_pct","gop_pct","state_sample"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    # drop empty
    df_clean = df.dropna(subset=["state_sample", "total_pct", "dem_pct"]).copy()
    # normalize total_pct by state so that shares sum to ~100 inside each state (if needed)
    # compute sum_by_state and rescale groups to sum to 100 if sums differ significantly
    sum_by_state = df_clean.groupby("state")["total_pct"].sum()
    for st, ssum in sum_by_state.items():
        if ssum <= 0: continue
        if not (95 <= ssum <= 105):
            # rescale
            df_clean.loc[df_clean["state"] == st, "total_pct"] = df_clean.loc[df_clean["state"] == st, "total_pct"] / ssum * 100.0
    # compute electorate share (turnout share) per group: group_share_of_state
    df_clean["grp_share_of_state"] = df_clean["total_pct"] / 100.0
    # dem_rate as decimal
    df_clean["dem_rate"] = df_clean["dem_pct"] / 100.0
    return df_clean

def compute_state_baselines(df):
    # aggregated per-state baseline margin = sum(group_share * (2*dem_rate-1)*100)
    # alternatively compute dem_share then margin = 2*dem_share-100
    out = []
    for st, g in df.groupby("state"):
        sample = g["state_sample"].iloc[0]
        dem_votes = (g["grp_share_of_state"] * g["dem_rate"] * sample).sum()
        total_votes = (g["grp_share_of_state"] * sample).sum()
        if total_votes > 0:
            dem_share = dem_votes / total_votes * 100.0
            margin = 2 * dem_share - 100.0
        else:
            dem_share = None; margin = None
        out.append({"state": st, "sample_size": sample, "baseline_dem_share": dem_share, "baseline_margin": margin})
    return pd.DataFrame(out)

def main(pdf):
    pages = extract_pages(pdf)
    starts = find_state_starts(pages)
    keys = list(starts.keys())
    parsed = OrderedDict()
    for i, st in enumerate(keys):
        s = starts[st]
        e = len(pages) - 1
        if i + 1 < len(keys):
            e = starts[keys[i+1]] - 1
        block = "\n".join(pages[s:e+1])
        parsed[st] = parse_state_block(block)
    # save full parsed JSON
    with open(os.path.join(OUT, "state_data_full_parsed.json"), "w") as f:
        json.dump(parsed, f, indent=2)
    # flatten and normalize
    df_clean = normalize_and_flatten(parsed)
    csv_flat = os.path.join(OUT, "state_groups_full_parsed.csv")
    df_clean.to_csv(csv_flat, index=False)
    # compute baselines
    df_baselines = compute_state_baselines(df_clean)
    df_baselines.to_csv(os.path.join(OUT, "state_baselines_2024.csv"), index=False)
    # convert to state_demographics format (electorate shares)
    # For each row keep: state, label, group_type, electorate_share, dem_rate, gop_pct
    df_dem = df_clean[["state","group_type","label","grp_share_of_state","dem_rate","gop_pct"]].rename(columns={
        "grp_share_of_state":"electorate_share"
    })
    df_dem.to_csv(os.path.join(OUT, "state_demographics_2024.csv"), index=False)
    print("Saved outputs to", OUT)
    print("Preview baselines:")
    print(df_baselines.head(10))

if __name__ == "__main__":
    main(PDF)
