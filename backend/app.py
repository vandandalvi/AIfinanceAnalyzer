from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import pandas as pd
import numpy as np
import os
import io
import re
import json
import hashlib
import pdfplumber
from dotenv import load_dotenv
import google.generativeai as genai
import statistics

load_dotenv() 

app = Flask(__name__)
CORS(app, 
     resources={r"/*": {"origins": "*"}},
     supports_credentials=True)


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

ANSWER_MODE = os.getenv("ANSWER_MODE", "ai-only").strip().lower()
CSV_CONTEXT_MAX_CHARS = int(os.getenv("CSV_CONTEXT_MAX_CHARS", "120000"))
UNKNOWN_UPI_OTHER_THRESHOLD = float(os.getenv("UNKNOWN_UPI_OTHER_THRESHOLD", "200"))


def _llm_chat(prompt: str):
    """Call Gemini API directly.
    Returns (answer, meta) or raises an Exception with the last error.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("LLM client not configured")

    # Try different Gemini models with correct identifiers (based on actual available models)
    candidates = [
        "models/gemini-2.5-flash",
        "models/gemini-2.0-flash",
        "models/gemini-flash-latest",
        "models/gemini-2.5-pro",
        "models/gemini-2.0-flash-exp",
        "models/gemini-pro-latest",
    ]

    last_err = None
    for model_name in candidates:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text, {"model": model_name}
        except Exception as e:
            msg = str(e)
            last_err = msg
            # If it's a NOT_FOUND/404 for a given model, try the next
            if "404" in msg or "NOT_FOUND" in msg or "was not found" in msg or "not found" in msg:
                continue
            # other errors should stop the loop
            break

    raise RuntimeError(last_err or "Unknown LLM error")


def _savings_intent(text: str) -> bool:
    t = (text or "").lower()
    keywords = [
        "save", "saving", "savings", "waste", "wasted", "useless",
        "cut down", "reduce", "optimize", "where can i save",
    ]
    return any(k in t for k in keywords)


def _local_savings_suggestions(df: pd.DataFrame) -> str:
    if df is None or df.empty or "Amount" not in df.columns:
        return "I need valid transaction data (Amount column) to suggest savings."
    # Basic aggregates
    cat_totals = (
        df.groupby("Category")["Amount"].sum().sort_values(ascending=False)
        if "Category" in df.columns else None
    )
    cat_medians = (
        df.groupby("Category")["Amount"].median() if "Category" in df.columns else None
    )
    # Treat Description as merchant/item label
    desc_stats = (
        df.groupby(["Description"])
          .agg(total=("Amount", "sum"), avg=("Amount", "mean"), count=("Amount", "count"))
          .sort_values("total", ascending=False)
          .reset_index()
    )
    # Attach category for each description by its most frequent category
    if "Category" in df.columns:
        top_cat = (
            df.groupby(["Description", "Category"]).size().reset_index(name="n")
              .sort_values(["Description", "n"], ascending=[True, False])
              .drop_duplicates("Description")[["Description", "Category"]]
        )
        desc_stats = desc_stats.merge(top_cat, on="Description", how="left")
    # Compute premium vs category median
    if cat_medians is not None and not cat_medians.empty and "Category" in desc_stats.columns:
        def premium(row):
            cat = row.get("Category")
            med = cat_medians.get(cat, None)
            if med and med > 0:
                return (row["avg"] - med) / med
            return 0.0
        desc_stats["premium_vs_cat_median"] = desc_stats.apply(premium, axis=1)
    else:
        desc_stats["premium_vs_cat_median"] = 0.0

    # Detect subscription-like: same amount repeating (low unique amounts and count>=2)
    subs = []
    if "Description" in df.columns:
        for desc, grp in df.groupby("Description"):
            amounts = grp["Amount"].dropna()
            if len(amounts) >= 2 and amounts.nunique() == 1:
                subs.append((desc, float(amounts.iloc[0]), len(amounts)))

    suggestions = []
    # 1) Biggest categories to target
    if cat_totals is not None:
        top_cats = cat_totals.head(3)
        if len(top_cats) > 0:
            cat_lines = ", ".join([f"{c}: Rs {v:.0f}" for c, v in top_cats.items()])
            suggestions.append(f"Your top spending categories are {cat_lines}. Consider setting weekly limits for these.")

    # 2) High-spend merchants/items with specific actionable advice
    top_desc = desc_stats.head(5)
    for _, r in top_desc.iterrows():
        d = r["Description"]
        total = r["total"]
        avg = r["avg"]
        cnt = int(r["count"]) if pd.notna(r["count"]) else 0
        cat = r.get("Category", None)
        prem = r.get("premium_vs_cat_median", 0.0) or 0.0
        if prem > 0.2:  # >20% above category median
            suggestions.append(
                f"You spent Rs {total:.0f} on {d}, which is {prem*100:.0f}% higher than your {cat} median. You can save by switching to cheaper alternatives or reducing frequency."
            )
        elif total > 1000:  # High spending regardless of premium
            suggestions.append(
                f"You spent Rs {total:.0f} on {d} over {cnt} visits. Consider reducing this habit to save money."
            )

    # 3) Subscriptions
    for desc, amt, cnt in subs:
        suggestions.append(
            f"Subscription-like: {desc} appears {cnt}× at Rs {amt:.0f}. Check for plan downgrades or duplicate charges."
        )

    # Keep it concise
    if not suggestions:
        return "I didn’t find clear savings patterns. Try asking about a specific category or merchant."
    # Limit to top 6 suggestions
    return "Here are ways you can save based on your transactions:\n- " + "\n- ".join(suggestions[:6])


def _summaries_for_llm(df: pd.DataFrame) -> str:
    lines = []
    if df is None or df.empty:
        return ""
    if "Category" in df.columns and "Amount" in df.columns:
        cat_totals = df.groupby("Category")["Amount"].sum().sort_values(ascending=False)
        top = ", ".join([f"{c}: Rs {v:.0f}" for c, v in cat_totals.head(5).items()])
        lines.append(f"Top categories by spend: {top}")
    if "Description" in df.columns and "Amount" in df.columns:
        desc_totals = df.groupby("Description")["Amount"].sum().sort_values(ascending=False)
        topd = ", ".join([f"{d}: Rs {v:.0f}" for d, v in desc_totals.head(5).items()])
        lines.append(f"Top merchants/items: {topd}")
    return "\n".join(lines)

# Globals for uploaded data
transactions_df = None
csv_text = ""
analysis_cache = {}


CATEGORY_RULES_V2 = {
    "Investment": [
        "UPSTOX", "ZERODHA", "GROWW", "MUTUAL FUND", "SIP", "DEMAT", "NSE", "BSE", "TRADING", "INVESTMENT"
    ],
    "Credit Card": [
        "CRED", "CREDIT CARD", "CC PAYMENT", "CARD PAYMENT", "HDFC CARD", "SBI CARD", "ICICI CARD"
    ],
    "Food & Dining": [
        "SWIGGY", "ZOMATO", "RESTAURANT", "CAFE", "STARBUCKS", "PIZZA", "DOMINOS", "KFC", "MCDONALD", "BARBEQUE"
    ],
    "Transportation": [
        "UBER", "OLA", "RAPIDO", "METRO", "FUEL", "PETROL", "DIESEL", "BPCL", "HPCL", "IOCL", "TOLL", "FASTAG"
    ],
    "Shopping": [
        "AMAZON", "FLIPKART", "MYNTRA", "AJIO", "MEESHO", "NYKAA", "SHOPPING", "LIFESTYLE", "DMART", "BIGBASKET", "GROCERS", "MART"
    ],
    "Entertainment": [
        "NETFLIX", "SPOTIFY", "PRIME", "HOTSTAR", "YOUTUBE", "BOOKMYSHOW", "SONYLIV", "JIOCINEMA"
    ],
    "Utilities": [
        "AIRTEL", "JIO", "VODAFONE", "ELECTRICITY", "BILL", "RECHARGE", "GAS", "WATER", "BROADBAND", "DTH", "EBILL", "POSTPAID"
    ],
    "Healthcare": [
        "APOLLO", "PHARMACY", "MEDICAL", "HOSPITAL", "CLINIC", "DIAGNOSTIC", "LABS"
    ],
    "Travel": [
        "IRCTC", "MAKEMYTRIP", "YATRA", "GOIBIBO", "AIRINDIA", "INDIGO", "HOTEL", "BOOKING.COM"
    ],
    "Rent & Housing": [
        "RENT", "HOUSE RENT", "MAINTENANCE", "SOCIETY", "BROKERAGE"
    ],
    "Loan & EMI": [
        "EMI", "LOAN", "BAJAJ FIN", "HOME LOAN", "CAR LOAN", "PERSONAL LOAN"
    ],
    "Insurance": [
        "INSURANCE", "LIC", "POLICY", "PREMIUM", "HEALTH INS"
    ],
    "Taxes": [
        "INCOME TAX", "TAX", "GST", "TDS", "ADVANCE TAX"
    ],
    "Education": [
        "UDemy", "COURSERA", "BYJU", "UNACADEMY", "COLLEGE", "SCHOOL", "TUITION", "EXAM"
    ],
    "Cash Withdrawal": [
        "ATM", "CASH WDL", "CASH WITHDRAWAL", "WDL"
    ],
    "Money Transfer": [
        "NEFT", "IMPS", "RTGS", "TRANSFER", "BY TRANSFER", "TO TRANSFER"
    ],
    "Bank Charges": [
        "CHARGES", "FEE", "PENALTY", "GST CHARGE", "AMC"
    ],
    "Income": [
        "SALARY", "INTEREST", "DIVIDEND", "REFUND", "CASHBACK", "REWARD", "NEFT INWARD"
    ],
}


def _clear_analysis_cache():
    analysis_cache.clear()


def _df_signature(df: pd.DataFrame) -> str:
    """Create a stable signature for DataFrame-level response caching."""
    if df is None or df.empty:
        return "empty"

    parts = [str(len(df))]
    if "Amount" in df.columns:
        parts.append(f"{float(df['Amount'].sum()):.4f}")
        parts.append(f"{float(df['Amount'].abs().sum()):.4f}")
    if "Date" in df.columns and not df["Date"].dropna().empty:
        parts.append(str(df["Date"].min()))
        parts.append(str(df["Date"].max()))
    if "Description" in df.columns:
        parts.append(str(df["Description"].astype(str).head(20).tolist()))

    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str, signature: str):
    item = analysis_cache.get(key)
    if not item:
        return None
    if item.get("signature") != signature:
        return None
    return item.get("payload")


def _cache_set(key: str, signature: str, payload: dict):
    analysis_cache[key] = {
        "signature": signature,
        "payload": payload,
    }


def _extract_merchant(description: str) -> str:
    if pd.isna(description):
        return ""
    desc = str(description).upper().strip()
    desc = re.sub(r"[^A-Z0-9 /_-]", " ", desc)
    tokens = [t for t in re.split(r"[\s/_-]+", desc) if t and len(t) > 2]
    if not tokens:
        return ""
    # Skip common transport words and pick first useful token
    skip = {"UPI", "IMPS", "NEFT", "RTGS", "TRANSFER", "BY", "TO", "DR", "CR", "PAYMENT", "SENT", "RECEIVED"}
    for tok in tokens:
        if tok not in skip and not tok.isdigit():
            return tok
    return tokens[0]


def _normalize_desc_for_classification(description: str) -> str:
    if pd.isna(description):
        return ""
    desc = str(description).upper().strip()
    desc = desc.replace("\\n", " ")
    desc = re.sub(r"[^A-Z0-9 /_.-]", " ", desc)
    desc = re.sub(r"\s+", " ", desc)
    return desc


def _extract_merchant_candidates(description: str) -> list:
    desc = _normalize_desc_for_classification(description)
    if not desc:
        return []

    candidates = []

    # UPI/IMPS/NEFT style segments
    split_chars = r"[ /_.:-]+"
    tokens = [t for t in re.split(split_chars, desc) if t]

    skip = {
        "UPI", "IMPS", "NEFT", "RTGS", "TRANSFER", "BY", "TO", "DR", "CR", "PAYMENT",
        "SENT", "RECEIVED", "BANK", "ACCOUNT", "A", "THE", "FROM", "FOR", "REF", "NO"
    }

    for tok in tokens:
        if len(tok) <= 2 or tok.isdigit() or tok in skip:
            continue
        candidates.append(tok)

    # Add extracted merchant from existing helper as fallback
    primary = _extract_merchant(desc)
    if primary and primary not in candidates:
        candidates.insert(0, primary)

    return candidates[:12]


def _categorize_transaction_v2(description: str, amount: float = None) -> str:
    """Category intelligence v2 with richer keyword mapping and direction-aware fallback."""
    if pd.isna(description):
        return "Other"

    desc = _normalize_desc_for_classification(description)
    merchants = _extract_merchant_candidates(desc)
    merchant = merchants[0] if merchants else ""
    is_upi = "UPI" in desc

    def _format_upi_category(base_category: str) -> str:
        if not is_upi:
            return base_category
        # Keep credits and non-UPI spend types plain
        if base_category in {"Income", "Bank Charges", "Cash Withdrawal"}:
            return base_category
        # Show UPI context on spend category (e.g., UPI - Shopping)
        return f"UPI - {base_category}"

    for category, keywords in CATEGORY_RULES_V2.items():
        if any(keyword in desc for keyword in keywords):
            return _format_upi_category(category)

    # Merchant-aware backoffs
    merchant_map = {
        "SWIGGY": "Food & Dining",
        "ZOMATO": "Food & Dining",
        "EATCLUB": "Food & Dining",
        "DOMINOS": "Food & Dining",
        "AMAZON": "Shopping",
        "FLIPKART": "Shopping",
        "DMART": "Shopping",
        "BIGBASKET": "Shopping",
        "UBER": "Transportation",
        "OLA": "Transportation",
        "RAPIDO": "Transportation",
        "NETFLIX": "Entertainment",
        "SPOTIFY": "Entertainment",
        "HOTSTAR": "Entertainment",
        "AIRTEL": "Utilities",
        "JIO": "Utilities",
        "APOLLO": "Healthcare",
        "LIC": "Insurance",
        "IRCTC": "Travel",
        "MAKEMYTRIP": "Travel",
        "BAJAJ": "Loan & EMI",
        "HDFCLTD": "Loan & EMI",
    }
    for m in merchants:
        if m in merchant_map:
            return _format_upi_category(merchant_map[m])

    # Direction-aware fallback
    if amount is not None:
        try:
            if float(amount) > 0:
                return "Income"
        except Exception:
            pass

    # Unknown UPI fallback: small unknown UPI -> Other, larger -> UPI Payments
    if is_upi:
        amt_abs = None
        try:
            amt_abs = abs(float(amount)) if amount is not None else None
        except Exception:
            amt_abs = None

        if amt_abs is not None and amt_abs <= UNKNOWN_UPI_OTHER_THRESHOLD:
            return "Other"
        return "UPI Payments"

    return "Other"


def _reclassify_other_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """Improve category accuracy by reusing consistent merchant-category pairs from same dataset."""
    if df is None or df.empty or "Description" not in df.columns or "Category" not in df.columns:
        return df

    work_df = df.copy()
    work_df["MerchantKey"] = work_df["Description"].apply(lambda x: _extract_merchant_candidates(x)[0] if _extract_merchant_candidates(x) else "")

    valid = work_df[(work_df["Category"] != "Other") & (work_df["MerchantKey"] != "")]
    if valid.empty:
        return work_df.drop(columns=["MerchantKey"])

    merchant_to_category = (
        valid.groupby(["MerchantKey", "Category"]).size().reset_index(name="n")
        .sort_values(["MerchantKey", "n"], ascending=[True, False])
        .drop_duplicates("MerchantKey")
        .set_index("MerchantKey")["Category"]
        .to_dict()
    )

    mask_other = (work_df["Category"] == "Other") & (work_df["MerchantKey"] != "")
    work_df.loc[mask_other, "Category"] = work_df.loc[mask_other, "MerchantKey"].map(merchant_to_category).fillna(work_df.loc[mask_other, "Category"])

    # Final fallback for unknown UPI:
    # small values remain Other, larger values become UPI Payments
    if "Description" in work_df.columns:
        upi_other_mask = (
            (work_df["Category"] == "Other")
            & work_df["Description"].astype(str).str.contains(r"\bUPI\b|UPI/|UPI-", case=False, regex=True, na=False)
        )
        if "Amount" in work_df.columns:
            upi_abs = pd.to_numeric(work_df.loc[upi_other_mask, "Amount"], errors="coerce").abs()
            idx = work_df.loc[upi_other_mask].index
            large_unknown_idx = idx[upi_abs.fillna(0) > UNKNOWN_UPI_OTHER_THRESHOLD]
            work_df.loc[large_unknown_idx, "Category"] = "UPI Payments"
        else:
            work_df.loc[upi_other_mask, "Category"] = "UPI Payments"

    return work_df.drop(columns=["MerchantKey"])


def _sum_for_query(df: pd.DataFrame, mask: pd.Series, query_text: str) -> float:
    """Return amount aligned with user intent words (spend/income/net)."""
    q = (query_text or "").lower()
    subset = pd.to_numeric(df.loc[mask, "Amount"], errors="coerce").dropna()
    if subset.empty:
        return 0.0

    if any(k in q for k in ["income", "credit", "received", "salary", "earned"]):
        return float(subset[subset > 0].sum())

    if any(k in q for k in ["spent", "spending", "expense", "debit", "paid", "pay"]):
        debits = subset[subset < 0]
        if not debits.empty:
            return float(abs(debits.sum()))
        return float(abs(subset).sum())

    return float(subset.sum())


def _compute_health_score(df: pd.DataFrame) -> dict:
    """Compute monthly health score (0-100) using savings, stability, concentration, and recurring drains."""
    if df is None or df.empty or "Amount" not in df.columns:
        return {"score": 0, "grade": "D", "factors": [], "monthly": []}

    def _compute_core(core_df: pd.DataFrame):
        local_df = core_df.copy()
        local_df["Amount"] = pd.to_numeric(local_df["Amount"], errors="coerce").fillna(0)

        income = float(local_df.loc[local_df["Amount"] > 0, "Amount"].sum())
        expense = float(abs(local_df.loc[local_df["Amount"] < 0, "Amount"].sum()))
        if expense == 0:
            expense = float(local_df["Amount"].abs().sum())

        if expense == 0 and income == 0:
            return 0, "D", [], {
                "savings_rate": 0,
                "volatility": 1,
                "concentration": 1,
                "recurring_count": 0,
                "savings_points": 0,
                "stability_points": 0,
                "concentration_penalty": 0,
                "recurring_penalty": 0,
            }

        savings_rate = 0
        if income > 0:
            savings_rate = max(min((income - expense) / income, 1), -1)

        monthly_totals = pd.Series([expense], index=["overall"], dtype=float)
        if "Date" in local_df.columns and not local_df["Date"].isna().all():
            dated = local_df.dropna(subset=["Date"]).copy()
            if not dated.empty:
                dated["Month"] = pd.to_datetime(dated["Date"], errors="coerce").dt.strftime("%Y-%m")
                series = dated.groupby("Month")["Amount"].apply(lambda x: abs(x[x < 0].sum()) or abs(x).sum())
                if not series.empty:
                    monthly_totals = series

        mean_month = float(monthly_totals.mean()) if len(monthly_totals) > 0 else 0
        std_month = float(monthly_totals.std()) if len(monthly_totals) > 1 else 0
        volatility = (std_month / mean_month) if mean_month > 0 else 0

        concentration = 0
        if "Category" in local_df.columns and expense > 0:
            cat_exp = local_df.loc[local_df["Amount"] < 0].groupby("Category")["Amount"].sum().abs()
            if cat_exp.empty:
                cat_exp = local_df.groupby("Category")["Amount"].sum().abs()
            if not cat_exp.empty and cat_exp.sum() > 0:
                concentration = float(cat_exp.max() / cat_exp.sum())

        recurring_count = 0
        if "Description" in local_df.columns:
            for _, grp in local_df.groupby("Description"):
                vals = grp["Amount"].round(2)
                if len(vals) >= 2 and vals.nunique() == 1:
                    recurring_count += 1

        savings_points = max(min((savings_rate + 0.2) * 60, 35), 0)
        stability_points = max(25 - min(volatility, 1.5) * 18, 0)
        concentration_penalty = min(concentration * 30, 15)
        recurring_penalty = min(recurring_count * 1.8, 10)

        score = int(round(max(min(40 + savings_points + stability_points - concentration_penalty - recurring_penalty, 100), 0)))

        grade = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D"

        factors = [
            {"name": "Savings Rate", "value": round(savings_rate * 100, 1), "impact": round(savings_points, 1)},
            {"name": "Spending Stability", "value": round(max(0, 100 - volatility * 100), 1), "impact": round(stability_points, 1)},
            {"name": "Top Category Concentration", "value": round(concentration * 100, 1), "impact": -round(concentration_penalty, 1)},
            {"name": "Recurring Spend Count", "value": recurring_count, "impact": -round(recurring_penalty, 1)},
        ]

        details = {
            "savings_rate": savings_rate,
            "volatility": volatility,
            "concentration": concentration,
            "recurring_count": recurring_count,
            "savings_points": savings_points,
            "stability_points": stability_points,
            "concentration_penalty": concentration_penalty,
            "recurring_penalty": recurring_penalty,
        }
        return score, grade, factors, details

    score, grade, factors, _ = _compute_core(df)

    monthly_scores = []
    if "Date" in df.columns and not df["Date"].isna().all():
        temp = df.dropna(subset=["Date"]).copy()
        if not temp.empty:
            temp["Month"] = pd.to_datetime(temp["Date"], errors="coerce").dt.strftime("%Y-%m")
            for month, grp in temp.groupby("Month"):
                m_score, _, _, _ = _compute_core(grp)
                monthly_scores.append({"month": month, "score": m_score})

    return {"score": score, "grade": grade, "factors": factors, "monthly": monthly_scores[:12]}


def _build_category_intelligence(df: pd.DataFrame) -> dict:
    if df is None or df.empty or "Amount" not in df.columns or "Category" not in df.columns:
        return {"uncategorizedPercent": 0, "uncategorizedCount": 0, "topNeedsReview": [], "suggestions": []}

    total = len(df)
    other_mask = df["Category"].isin(["Other", "Unknown", "Uncategorized", "Other (Unknown UPI)"])
    other_count = int(other_mask.sum())

    top_needs_review = []
    if "Description" in df.columns and other_count > 0:
        review_df = (
            df.loc[other_mask]
            .groupby("Description")["Amount"]
            .agg(total=lambda x: float(abs(x.sum())), count="count")
            .sort_values(["total", "count"], ascending=False)
            .head(5)
            .reset_index()
        )
        top_needs_review = review_df.to_dict(orient="records")

    suggestions = [
        "Add custom merchant rules for frequent 'Other' transactions.",
        "Review recurring uncategorized entries and map them once.",
        "Prefer cleaned descriptions (UPI merchant names) for better auto-tagging.",
    ]

    return {
        "uncategorizedPercent": round((other_count / total) * 100, 2) if total else 0,
        "uncategorizedCount": other_count,
        "topNeedsReview": top_needs_review,
        "suggestions": suggestions,
    }


def _build_report_payload(df: pd.DataFrame) -> dict:
    payload = {
        "summary": {},
        "healthScore": _compute_health_score(df),
        "categoryIntelligence": _build_category_intelligence(df),
    }

    if df is None or df.empty or "Amount" not in df.columns:
        return payload

    amounts = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    spending = float(abs(amounts[amounts < 0].sum())) if (amounts < 0).any() else float(abs(amounts).sum())
    income = float(amounts[amounts > 0].sum())

    payload["summary"] = {
        "transactions": int(len(df)),
        "totalSpending": round(spending, 2),
        "totalIncome": round(income, 2),
        "net": round(income - spending, 2),
    }

    if "Category" in df.columns:
        cat = (
            df.groupby("Category")["Amount"].sum().abs().sort_values(ascending=False).head(10)
            .reset_index()
        )
        cat.columns = ["category", "total"]
        payload["topCategories"] = cat.to_dict(orient="records")

    return payload


def _normalize_columns_bank_specific(df: pd.DataFrame, bank: str) -> pd.DataFrame:
    """Bank-specific column normalization and data processing."""
    if df is None or df.empty:
        return df
    
    print(f"Processing {bank} format. Original columns: {df.columns.tolist()}")
    
    if bank == 'sbi':
        return _process_sbi_format(df)
    elif bank == 'kotak':
        return _process_kotak_format(df)
    elif bank == 'axis':
        return _process_axis_format(df)
    else:
        # Fallback to generic normalization
        return _normalize_columns(df)


def _parse_amount_cell(value, kind: str = None) -> float:
    """Parse bank amount cells robustly and preserve intended sign.
    kind can be 'debit' or 'credit' to apply default sign when explicit sign is missing.
    """
    if pd.isna(value):
        return 0.0

    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "-", "--"}:
        return 0.0

    raw = s.upper().replace(",", "")
    is_negative = (
        raw.startswith("-")
        or ("(" in raw and ")" in raw)
        or raw.endswith("DR")
        or " DR" in raw
    )
    is_positive = raw.startswith("+") or raw.endswith("CR") or " CR" in raw

    match = re.search(r"-?\d+(?:\.\d+)?", raw)
    if not match:
        return 0.0

    num = abs(float(match.group(0)))

    # Default by column type when sign is absent.
    if kind == "debit":
        sign = -1
    elif kind == "credit":
        sign = 1
    else:
        sign = -1 if is_negative and not is_positive else 1

    # Explicit signs/markers override defaults.
    if is_negative:
        sign = -1
    elif is_positive:
        sign = 1

    return sign * num

def _process_sbi_format(df: pd.DataFrame) -> pd.DataFrame:
    """Process SBI bank statement format."""
    # SBI columns: Txn Date, Value Date, Description, Ref No./Cheque No., Debit, Credit, Balance
    mapping = {}
    for col in df.columns:
        lc = str(col).strip().lower()
        if 'txn date' in lc or 'transaction date' in lc:
            mapping[col] = "Date"
        elif 'description' in lc or 'particulars' in lc:
            mapping[col] = "Description"
        elif 'debit' in lc:
            mapping[col] = "Debit"
        elif 'credit' in lc:
            mapping[col] = "Credit"
    
    if mapping:
        df = df.rename(columns=mapping)
    
    # Process SBI amounts - handle empty strings and combine Debit and Credit
    if "Debit" in df.columns and "Credit" in df.columns:
        df["Debit"] = df["Debit"].apply(lambda v: _parse_amount_cell(v, "debit"))
        df["Credit"] = df["Credit"].apply(lambda v: _parse_amount_cell(v, "credit"))
        # Debit is negative, credit is positive
        df["Amount"] = df["Credit"] + df["Debit"]
    
    # Clean and categorize SBI descriptions
    if "Description" in df.columns:
        df["Category"] = df.apply(
            lambda row: _categorize_sbi_transaction(row.get("Description"), row.get("Amount")),
            axis=1,
        )
        df["Description"] = df["Description"].apply(_clean_sbi_description)
    
    # Process dates - handle SBI date format like "1 Jan 2024"
    if "Date" in df.columns:
        try:
            # use errors='raise' so it drops to except block if format mismatch
            df["Date"] = pd.to_datetime(df["Date"], errors="raise", format='%d %b %Y')
        except:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    
    return df

def _process_kotak_format(df: pd.DataFrame) -> pd.DataFrame:
    """Process Kotak bank statement format."""
    # Kotak columns: Date, Particulars, Debit, Credit, Balance
    mapping = {}
    for col in df.columns:
        lc = str(col).strip().lower()
        if 'date' in lc:
            mapping[col] = "Date"
        elif 'particulars' in lc or 'description' in lc or 'narration' in lc:
            mapping[col] = "Description"
        elif 'debit' in lc or 'withdrawal' in lc:
            mapping[col] = "Debit"
        elif 'credit' in lc or 'deposit' in lc:
            mapping[col] = "Credit"
    
    if mapping:
        df = df.rename(columns=mapping)
    
    # Process Kotak amounts - handle empty strings
    if "Debit" in df.columns and "Credit" in df.columns:
        df["Debit"] = df["Debit"].apply(lambda v: _parse_amount_cell(v, "debit"))
        df["Credit"] = df["Credit"].apply(lambda v: _parse_amount_cell(v, "credit"))
        df["Amount"] = df["Credit"] + df["Debit"]
    
    # Clean and categorize Kotak descriptions
    if "Description" in df.columns:
        print(f"Categorizing {len(df)} Kotak transactions...")
        df["Category"] = df.apply(
            lambda row: _categorize_kotak_transaction(row.get("Description"), row.get("Amount")),
            axis=1,
        )
        # Debug: print investment transactions
        investment_txns = df[df["Category"] == "Investment"]
        if not investment_txns.empty:
            print(f"Found {len(investment_txns)} Investment transactions:")
            for idx, row in investment_txns.iterrows():
                print(f"  - {row['Description']} -> {row['Category']}")
        df["Description"] = df["Description"].apply(_clean_kotak_description)
    
    # Process dates - handle Kotak date format like "01/01/2024"
    if "Date" in df.columns:
        try:
            df["Date"] = pd.to_datetime(df["Date"], errors="raise", format='%d/%m/%Y')
        except:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    
    return df

def _process_axis_format(df: pd.DataFrame) -> pd.DataFrame:
    """Process Axis bank statement format."""
    # Axis columns: Tran Date, Description, Chq/Ref Number, Value Dt, Withdrawal Amt, Deposit Amt, Closing Balance
    mapping = {}
    for col in df.columns:
        lc = str(col).strip().lower()
        if 'tran date' in lc or 'transaction date' in lc or 'date' in lc:
            mapping[col] = "Date"
        elif 'description' in lc or 'particulars' in lc:
            mapping[col] = "Description"
        elif 'withdrawal' in lc or 'debit' in lc:
            mapping[col] = "Debit"
        elif 'deposit' in lc or 'credit' in lc:
            mapping[col] = "Credit"
    
    if mapping:
        df = df.rename(columns=mapping)
    
    # Process Axis amounts - handle empty strings
    if "Debit" in df.columns and "Credit" in df.columns:
        df["Debit"] = df["Debit"].apply(lambda v: _parse_amount_cell(v, "debit"))
        df["Credit"] = df["Credit"].apply(lambda v: _parse_amount_cell(v, "credit"))
        df["Amount"] = df["Credit"] + df["Debit"]
    
    # Clean and categorize Axis descriptions
    if "Description" in df.columns:
        df["Category"] = df.apply(
            lambda row: _categorize_axis_transaction(row.get("Description"), row.get("Amount")),
            axis=1,
        )
        df["Description"] = df["Description"].apply(_clean_axis_description)
    
    # Process dates - handle Axis date format like "01/01/2024"
    if "Date" in df.columns:
        try:
            df["Date"] = pd.to_datetime(df["Date"], errors="raise", format='%d/%m/%Y')
        except:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    
    return df

def _categorize_sbi_transaction(description: str, amount: float = None) -> str:
    """Categorize SBI transactions using category intelligence v2."""
    return _categorize_transaction_v2(description, amount)


def _categorize_kotak_transaction(description: str, amount: float = None) -> str:
    """Categorize Kotak transactions using category intelligence v2."""
    return _categorize_transaction_v2(description, amount)


def _categorize_axis_transaction(description: str, amount: float = None) -> str:
    """Categorize Axis transactions using category intelligence v2."""
    return _categorize_transaction_v2(description, amount)

def _clean_sbi_description(description: str) -> str:
    """Clean SBI transaction descriptions for better readability."""
    if pd.isna(description):
        return "Unknown Transaction"
    
    desc = str(description).strip()
    
    # Clean UPI transactions - extract merchant names
    if "UPI/DR" in desc or "UPI/CR" in desc:
        # Extract merchant from UPI patterns like "BY TRANSFER-UPI/DR/400252792161/MAHAB"
        parts = desc.split("/")
        if len(parts) >= 4:
            merchant = parts[-1]  # Last part is usually merchant
            if merchant and len(merchant) > 2:
                return f"UPI Payment - {merchant.title()}"
        return "UPI Payment"
    
    # Clean transfer descriptions
    elif "BY TRANSFER" in desc:
        if "MAHAB" in desc:
            return "Money Transfer"
        return "Bank Transfer"
    
    elif "TO TRANSFER" in desc:
        if "Hamara" in desc:
            return "Payment to Hamara"
        elif "SONU" in desc:
            return "Payment to Contact"
        return "Money Transfer"
    
    # Clean AMC and charges
    elif "AMC" in desc:
        return "Annual Maintenance Charge"
    
    elif "ECS/ACH RETURN" in desc:
        return "ECS Return Charges"
    
    # NEFT transactions
    elif "NEFT" in desc:
        if "SALARY" in desc:
            return "Salary Credit"
        return "NEFT Transfer"
    
    # ATM transactions
    elif "ATM" in desc and "WDL" in desc:
        return "ATM Cash Withdrawal"
    
    # Return cleaned description (first 40 characters)
    return desc[:40] + "..." if len(desc) > 40 else desc

def _clean_kotak_description(description: str) -> str:
    """Clean Kotak transaction descriptions."""
    if pd.isna(description):
        return "Unknown Transaction"
    
    desc = str(description).strip()
    
    # Clean UPI transactions
    if "UPI/" in desc:
        parts = desc.split("/")
        if len(parts) >= 2:
            merchant = parts[1]  # Second part is usually merchant
            if merchant:
                return f"UPI - {merchant.title()}"
        return "UPI Payment"
    
    # Clean IMPS transactions
    elif "IMPS/" in desc:
        if "AMAZON" in desc:
            return "IMPS - Amazon"
        return "IMPS Transfer"
    
    # ATM withdrawals
    elif "ATM" in desc:
        return "ATM Cash Withdrawal"
    
    # NEFT salary
    elif "SALARY" in desc and "NEFT" in desc:
        return "Salary Credit"
    
    # Mobile recharge
    elif "MOBILE RECHARGE" in desc:
        return "Mobile Recharge"
    
    return desc[:40] + "..." if len(desc) > 40 else desc

def _clean_axis_description(description: str) -> str:
    """Clean Axis transaction descriptions."""
    if pd.isna(description):
        return "Unknown Transaction"
    
    desc = str(description).strip()
    
    # Clean UPI transactions - Axis format: "UPI-SWIGGY-FOOD DELIVERY-123456789"
    if "UPI-" in desc:
        parts = desc.split("-")
        if len(parts) >= 2:
            merchant = parts[1]  # Second part is merchant
            service = parts[2] if len(parts) > 2 else ""
            if merchant:
                return f"UPI - {merchant.title()}"
        return "UPI Payment"
    
    # NEFT transactions
    elif "NEFT-" in desc:
        if "SALARY" in desc:
            return "Salary Credit"
        return "NEFT Transfer"
    
    # ATM transactions
    elif "ATM-" in desc:
        return "ATM Cash Withdrawal"
    
    return desc[:40] + "..." if len(desc) > 40 else desc

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to standard names: Date, Description, Category, Amount (case-insensitive)."""
    if df is None or df.empty:
        return df
    mapping = {}
    for col in df.columns:
        lc = str(col).strip().lower()
        if lc in {"date", "transaction date", "posted date", "txn date"}:
            mapping[col] = "Date"
        elif lc in {"description", "details", "merchant", "narration", "memo"}:
            mapping[col] = "Description"
        elif lc in {"category", "cat", "type"}:
            mapping[col] = "Category"
        elif lc in {"amount", "amt", "value", "debit", "credit", "amount (inr)", "amount(rs)", "amount inr", "amount rs"}:
            mapping[col] = "Amount"
    if mapping:
        df = df.rename(columns=mapping)
    # Coerce types if present - but only if not already processed
    if "Amount" in df.columns and df["Amount"].dtype == 'object':
        df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")
    if "Date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["Date"]):
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    if "Category" in df.columns:
        df["Category"] = df["Category"].astype(str)
    return df

def _extract_pdf_kotak(file_stream) -> pd.DataFrame:
    """Extract table data from Kotak PDF statements."""
    all_data = []
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if len(row) >= 6:
                        # Clean up newlines in cells
                        cleaned_row = [str(cell).replace('\\n', ' ') if cell is not None else "" for cell in row]
                        all_data.append(cleaned_row[:6])
    
    if not all_data:
        return pd.DataFrame()
        
    headers = ['Date', 'Description', 'Ref No', 'Debit', 'Credit', 'Balance']
    df = pd.DataFrame(all_data, columns=headers)
    
    # Filter out header rows that might be repeated on multiple pages
    df = df[~df['Date'].str.contains('DATE', na=False, case=False)]
    
    return df

@app.get("/")
def health():
    return jsonify({"status": "ok", "message": "Backend is running"})


@app.route("/upload", methods=["POST"])
def upload_csv():
    global transactions_df, csv_text
    file = request.files.get("file")
    bank = request.form.get("bank", "").lower()
    
    if file is None:
        return jsonify({"message": "No file provided"}), 400
    
    if not bank:
        return jsonify({"message": "Bank selection required"}), 400
    
    try:
        filename = file.filename.lower()
        if filename.endswith('.pdf') and bank == 'kotak':
            file_stream = io.BytesIO(file.read())
            transactions_df = _extract_pdf_kotak(file_stream)
            print(f"Extracted PDF shape: {transactions_df.shape}, columns: {transactions_df.columns.tolist()}")
        else:
            transactions_df = pd.read_csv(file)
            print(f"Original CSV shape: {transactions_df.shape}, columns: {transactions_df.columns.tolist()}")
            
        print(f"Processing as {bank.upper()} format")
        
        # Use bank-specific processing
        transactions_df = _normalize_columns_bank_specific(transactions_df, bank)
        print(f"After {bank} normalization: {transactions_df.shape}, columns: {transactions_df.columns.tolist()}")

        if "Amount" in transactions_df.columns:
            transactions_df["Amount"] = pd.to_numeric(transactions_df["Amount"], errors="coerce")
        if "Date" in transactions_df.columns:
            transactions_df["Date"] = pd.to_datetime(transactions_df["Date"], errors="coerce")
        
        # Filter out rows with invalid amounts or dates
        if "Amount" in transactions_df.columns:
            transactions_df = transactions_df.dropna(subset=["Amount"])
            # Only remove zero amount transactions if they're clearly invalid
            # (keep them if they might be valid like balance inquiries)
        
        if "Date" in transactions_df.columns:
            transactions_df = transactions_df.dropna(subset=["Date"])

        # Improve category accuracy by propagating known merchant categories
        transactions_df = _reclassify_other_transactions(transactions_df)
        
        print(f"After filtering: {transactions_df.shape} rows")
        
        # Convert each row to text for LLM context (best-effort if columns present)
        def row_to_text(row):
            date = row["Date"] if "Date" in row and pd.notna(row["Date"]) else "?"
            amount = row["Amount"] if "Amount" in row and pd.notna(row["Amount"]) else "?"
            category = row["Category"] if "Category" in row and pd.notna(row["Category"]) else "?"
            desc = row["Description"] if "Description" in row and pd.notna(row["Description"]) else ""
            return f"On {date} you spent ₹{abs(amount):.2f} on {category}: {desc}"
        
        try:
            csv_text = "\n".join(transactions_df.apply(row_to_text, axis=1))
            print(f"CSV text length: {len(csv_text)} chars")
        except Exception as e:
            print(f"Error creating CSV text: {e}")
            # Fallback to raw CSV text
            csv_text = transactions_df.to_csv(index=False)

        _clear_analysis_cache()
        
        print(f"CSV upload successful! Processed {len(transactions_df)} transactions from {bank.upper()} format")
        return jsonify({
            "message": f"CSV uploaded successfully! Processed {len(transactions_df)} {bank.upper()} transactions", 
            "columns": list(transactions_df.columns),
            "bank": bank.upper(),
            "transaction_count": len(transactions_df)
        })
    except Exception as e:
        print(f"CSV upload error: {e}")
        return jsonify({"message": f"Error processing CSV: {str(e)}"}), 400

@app.route("/dashboard", methods=["POST"])
def dashboard():
    global transactions_df
    print(f"Dashboard called. transactions_df is None: {transactions_df is None}")
    if transactions_df is None:
        print("No transactions_df found")
        return jsonify({"error": "No data found. Please upload a CSV first."}), 400
    
    if transactions_df.empty:
        print("transactions_df is empty")
        return jsonify({"error": "No data found. Please upload a CSV first."}), 400
    
    df = transactions_df.copy()
    print(f"DataFrame shape: {df.shape}, columns: {df.columns.tolist()}")

    signature = _df_signature(df)
    cached = _cache_get("dashboard", signature)
    if cached:
        return jsonify(cached)

    amounts = pd.to_numeric(df.get("Amount", pd.Series(dtype=float)), errors="coerce").fillna(0)
    spend_series = amounts[amounts < 0]
    total_spending = float(abs(spend_series.sum())) if not spend_series.empty else float(abs(amounts).sum())
    avg_transaction = float(abs(amounts).mean()) if not amounts.empty else 0

    dashboard_data = {
        "totalSpending": total_spending,
        "totalTransactions": len(df),
        "totalCategories": int(df["Category"].nunique()) if "Category" in df.columns else 0,
        "avgTransaction": avg_transaction,
        "healthScore": _compute_health_score(df),
        "categoryIntelligence": _build_category_intelligence(df),
    }

    # Category breakdown
    if "Category" in df.columns and "Amount" in df.columns:
        expense_df = df.copy()
        expense_df["Amount"] = pd.to_numeric(expense_df["Amount"], errors="coerce").fillna(0)
        expense_only = expense_df[expense_df["Amount"] < 0]
        category_totals = (
            expense_only.groupby("Category")["Amount"].sum().abs().sort_values(ascending=False)
            if not expense_only.empty
            else expense_df.groupby("Category")["Amount"].sum().abs().sort_values(ascending=False)
        )
        dashboard_data["categories"] = [
            {"category": str(cat), "total": float(total)}
            for cat, total in category_totals.head(10).items()
        ]

    # Monthly spending (if Date column exists)
    if "Date" in df.columns and "Amount" in df.columns:
        date_df = df.copy()
        date_df["Date"] = pd.to_datetime(date_df["Date"], errors="coerce")
        date_df = date_df.dropna(subset=["Date"])
        if not date_df.empty:
            date_df["Month"] = date_df["Date"].dt.strftime("%Y-%m")
            monthly_totals = date_df.groupby("Month")["Amount"].sum().sort_index()
            dashboard_data["monthly"] = [
                {"month": month, "total": float(abs(total))}
                for month, total in monthly_totals.items()
            ]

    # Top merchants
    if "Description" in df.columns and "Amount" in df.columns:
        merchant_df = df.copy()
        merchant_df["Amount"] = pd.to_numeric(merchant_df["Amount"], errors="coerce").fillna(0)
        merchant_spend = merchant_df[merchant_df["Amount"] < 0]
        merchant_totals = (
            merchant_spend.groupby("Description")["Amount"].sum().abs().sort_values(ascending=False)
            if not merchant_spend.empty
            else merchant_df.groupby("Description")["Amount"].sum().abs().sort_values(ascending=False)
        )
        dashboard_data["topMerchants"] = [
            {"merchant": str(merchant), "total": float(total)}
            for merchant, total in merchant_totals.head(8).items()
        ]

    report_payload = _build_report_payload(df)
    dashboard_data["reportSummary"] = report_payload.get("summary", {})

    _cache_set("dashboard", signature, dashboard_data)
    return jsonify(dashboard_data)

@app.route("/chat", methods=["POST"])
def chat():
    global csv_text, transactions_df
    if not csv_text or transactions_df is None:
        return jsonify({"response": "Please upload a CSV first."})

    user_query = (request.json or {}).get("query", "")
    # Ensure normalized and typed
    df = transactions_df.copy()

    q = user_query.lower()

    # If AI-only mode, always call Gemini with the CSV context
    if ANSWER_MODE == "ai-only":
        if not GEMINI_API_KEY:
            return jsonify({
                "response": (
                    "AI is not configured yet. Add GEMINI_API_KEY in backend/.env to enable AI answers.\n"
                    "Meanwhile, try: 'What is my total spending?', 'How much on Food?', 'Show my highest transaction', or 'How much in September 2025?'."
                ),
                "needs_key": True,
                "meta": {"mode": "ai-only", "rule": "no-llm"},
            })

        # Optionally trim context to avoid overlong prompts
        context_text = csv_text
        truncated = False
        if len(context_text) > CSV_CONTEXT_MAX_CHARS:
            context_text = context_text[-CSV_CONTEXT_MAX_CHARS:]
            truncated = True

        helper = _summaries_for_llm(df) if _savings_intent(user_query) else ""
        helper_text = f"Helper summaries:\n{helper}" if helper else ""
        truncation_note = " [TRUNCATED]" if truncated else ""
        
        prompt = f"""
You are a personal finance chat agent. Always reply in 2-3 short, plain sentences, spaced like a real chat. Never use Markdown, never use bullet points, never use headings, never use lists, never use bold or italics. Do not summarize categories or give long explanations.

IMPORTANT: All amounts are in Indian Rupees (INR). Always mention amounts with "Rs" or "₹" symbol, never use dollars ($).

When asked about saving money or useless spending, do this:
For each suggestion, mention the merchant/item, the amount spent in Rs, and if it is above the category median, say how much percent higher (e.g., 'You spent Rs 350 on Starbucks, which is 40% higher than your Food median. You can cut this habit.').
Give a concrete, actionable suggestion for each, like 'You can save by switching to regular coffee.'
If there is nothing to cut, say 'Your spending looks reasonable.'

Data (one line per transaction){truncation_note}:

{context_text}

{helper_text}

Question:
{user_query}
"""

        try:
            # Add a system message to enforce style
            system_prompt = (
                "You are a helpful, concise personal finance chat agent. Reply in 2-3 short, plain sentences, spaced like a real chat. Never use Markdown, never use bullet points, never use headings, never use lists, never use bold or italics. No long answers. IMPORTANT: All amounts are in Indian Rupees (INR) - always use Rs or ₹ symbol, never dollars ($)."
            )
            full_prompt = system_prompt + "\n\n" + prompt
            answer, meta = _llm_chat(full_prompt)
            # Post-process: remove Markdown, lists, and enforce chat-style spacing
            import re
            def clean_answer(text):
                # Remove Markdown bold/italic, bullets, and numbers
                text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
                text = re.sub(r"\*([^*]+)\*", r"\1", text)
                text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
                text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
                # Remove extra newlines, keep max 2 in a row
                text = re.sub(r"\n{3,}", "\n\n", text)
                # Add a space after every sentence for chat feel
                text = re.sub(r"([.!?])([^ \n])", r"\1 \2", text)
                # Remove leading/trailing whitespace
                return text.strip()
            answer = clean_answer(answer)
        except Exception as e:
            # Fallback to local suggestions for savings intent
            if _savings_intent(user_query):
                answer = _local_savings_suggestions(df)
                meta = {"error": True, "fallback": "local-savings"}
            else:
                answer = f"LLM error: {e}."
                meta = {"error": True}

        return jsonify({"response": answer, "meta": {"mode": "ai-only", "rule": "llm", **meta}})

    # HYBRID mode below: rule-based shortcuts first, then LLM
    # 1) Total spending
    if "total" in q and "Amount" in df.columns:
        all_mask = df["Amount"].notna()
        total = _sum_for_query(df, all_mask, q if q else "spent")
        return jsonify({"response": f"Your total is {total:.2f}.", "meta": {"rule": "total"}})

    # 2) Highest / Lowest transaction
    if "highest" in q or "largest" in q or "max" in q:
        if "Amount" in df.columns and not df["Amount"].dropna().empty:
            amt = pd.to_numeric(df["Amount"], errors="coerce")
            if any(k in q for k in ["spent", "spending", "debit", "paid", "expense"]):
                spend = amt[amt < 0]
                idx = spend.idxmin() if not spend.empty else amt.abs().idxmax()
            elif any(k in q for k in ["income", "credit", "received", "salary"]):
                inc = amt[amt > 0]
                idx = inc.idxmax() if not inc.empty else amt.abs().idxmax()
            else:
                idx = amt.abs().idxmax()
            row = df.loc[idx]
            return jsonify({"response": f"Highest transaction is {abs(float(row['Amount'])):.2f} on {row.get('Date', '')} for {row.get('Category', '')}: {row.get('Description', '')}", "meta": {"rule": "highest"}})
    if "lowest" in q or "smallest" in q or "min" in q:
        if "Amount" in df.columns and not df["Amount"].dropna().empty:
            amt = pd.to_numeric(df["Amount"], errors="coerce").dropna()
            non_zero = amt[amt != 0]
            idx = non_zero.abs().idxmin() if not non_zero.empty else amt.abs().idxmin()
            row = df.loc[idx]
            return jsonify({"response": f"Lowest transaction is {abs(float(row['Amount'])):.2f} on {row.get('Date', '')} for {row.get('Category', '')}: {row.get('Description', '')}", "meta": {"rule": "lowest"}})

    # 3) Spending by category, e.g., "on Food" or "category Food"
    import re
    cat_match = re.search(r"(?:on|category)\s+([\w &-]+)", q)
    if cat_match and "Category" in df.columns and "Amount" in df.columns:
        cat = cat_match.group(1).strip().lower()
        mask = df["Category"].str.lower() == cat
        amount = _sum_for_query(df, mask, q if q else "spent")
        return jsonify({"response": f"You spent {amount:.2f} on {cat}.", "meta": {"rule": "category", "category": cat}})

    # 4) Monthly spending: detect month name and optional year
    months = ["january","february","march","april","may","june","july","august","september","october","november","december"]
    month_idx = next((i+1 for i,m in enumerate(months) if m in q), None)
    year_match = re.search(r"(20\d{2})", q)
    if month_idx and "Date" in df.columns and "Amount" in df.columns:
        mask = df["Date"].dt.month == month_idx
        year = None
        if year_match:
            year = int(year_match.group(1))
            mask = mask & (df["Date"].dt.year == year)
        amount = _sum_for_query(df, mask, q if q else "spent")
        month_name = months[month_idx-1].capitalize()
        suffix = f" {year}" if year else ""
        return jsonify({"response": f"You spent {amount:.2f} in {month_name}{suffix}.", "meta": {"rule": "month", "month": month_name, "year": year}})

    # 5) Category in a given month (e.g., "Food in September 2025")
    if "Category" in df.columns and "Amount" in df.columns and "Date" in df.columns:
        cat_match2 = re.search(r"(?:on|category)\s+([\w &-]+)", q)
        if cat_match2 or any(m in q for m in months):
            cat = cat_match2.group(1).strip().lower() if cat_match2 else None
            m_idx = next((i+1 for i,m in enumerate(months) if m in q), None)
            yr_match = re.search(r"(20\d{2})", q)
            mask = df["Amount"].notna()
            if cat:
                mask = mask & (df["Category"].str.lower() == cat)
            if m_idx:
                mask = mask & (df["Date"].dt.month == m_idx)
            if yr_match:
                mask = mask & (df["Date"].dt.year == int(yr_match.group(1)))
            amount = _sum_for_query(df, mask, q if q else "spent")
            parts = []
            if cat:
                parts.append(f"on {cat}")
            if m_idx:
                parts.append(months[m_idx-1].capitalize())
            if yr_match:
                parts.append(yr_match.group(1))
            scope = " in " + " ".join(parts) if parts else ""
            return jsonify({"response": f"You spent {amount:.2f}{scope}.", "meta": {"rule": "category+month", "category": cat, "month": months[m_idx-1].capitalize() if m_idx else None, "year": yr_match.group(1) if yr_match else None}})

    prompt = f"""
You are an AI personal finance assistant.
Here is the user's bank data (one per line):

{csv_text}

Answer the following question based on this data:
{user_query}
"""

    if not GEMINI_API_KEY:
        # Friendly 200 response so the frontend can show it in chat without error handling
        return jsonify({
            "response": (
                "AI is not configured yet. Add GEMINI_API_KEY in backend/.env to enable AI answers.\n"
                "Meanwhile, try: 'What is my total spending?', 'How much on Food?', 'Show my highest transaction', or 'How much in September 2025?'."
            ),
            "needs_key": True,
            "meta": {"rule": "no-llm"},
        })

    try:
        answer, meta = _llm_chat(prompt)
    except Exception as e:
        answer = f"LLM error: {e}. Try asking for 'total' to use a local calculation."
        meta = {"error": True}

    return jsonify({"response": answer, "meta": {"mode": "hybrid", "rule": "llm", **meta}})


@app.route("/advanced-analytics", methods=["POST"])
def advanced_analytics():
    """Advanced data science analytics endpoint with statistical analysis."""
    global transactions_df
    
    if transactions_df is None or transactions_df.empty:
        return jsonify({"error": "No data found. Please upload a CSV first."}), 400
    
    df = transactions_df.copy()
    signature = _df_signature(df)
    cached = _cache_get("advanced_analytics", signature)
    if cached:
        return jsonify(cached)
    
    # Initialize analytics data
    analytics_data = {}
    
    # 1. Statistical Summary
    if "Amount" in df.columns:
        amounts = df["Amount"].abs()  # Use absolute values for stats
        analytics_data["statistics"] = {
            "mean": float(amounts.mean()),
            "median": float(amounts.median()),
            "std": float(amounts.std()),
            "min": float(amounts.min()),
            "max": float(amounts.max()),
            "count": int(amounts.count()),
            "q25": float(amounts.quantile(0.25)),
            "q75": float(amounts.quantile(0.75))
        }
    
    # 2. Outlier Detection using IQR method
    outliers = []
    if "Amount" in df.columns:
        amounts = df["Amount"].abs()
        Q1 = amounts.quantile(0.25)
        Q3 = amounts.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        
        outlier_mask = (amounts < lower_bound) | (amounts > upper_bound)
        outlier_df = df[outlier_mask].copy()
        
        for _, row in outlier_df.head(10).iterrows():
            outliers.append({
                "amount": float(row.get("Amount", 0)),
                "description": str(row.get("Description", "Unknown")),
                "category": str(row.get("Category", "Unknown")),
                "date": str(row.get("Date", "Unknown"))
            })
    
    analytics_data["outliers"] = outliers
    
    # 3. Category Trends - Average and Median by Category
    category_trends = []
    if "Category" in df.columns and "Amount" in df.columns:
        cat_stats = df.groupby("Category")["Amount"].agg([
            ('avg', lambda x: abs(x).mean()),
            ('median', lambda x: abs(x).median()),
            ('total', lambda x: abs(x).sum()),
            ('count', 'count')
        ]).sort_values('total', ascending=False)
        
        for cat, row in cat_stats.head(8).iterrows():
            category_trends.append({
                "category": str(cat),
                "avg": float(row['avg']),
                "median": float(row['median']),
                "total": float(row['total']),
                "count": int(row['count'])
            })
    
    analytics_data["categoryTrends"] = category_trends
    
    # 4. Spending by Day of Week
    weekday_spending = [0] * 7
    if "Date" in df.columns and "Amount" in df.columns:
        df["DayOfWeek"] = pd.to_datetime(df["Date"]).dt.dayofweek
        weekday_totals = df.groupby("DayOfWeek")["Amount"].apply(lambda x: abs(x).sum())
        for day, total in weekday_totals.items():
            if 0 <= day < 7:
                weekday_spending[day] = float(total)
    
    analytics_data["weekdaySpending"] = weekday_spending
    
    # 5. Spending by Hour of Day (if time information is available)
    hourly_spending = [0] * 24
    if "Date" in df.columns and "Amount" in df.columns:
        try:
            df["Hour"] = pd.to_datetime(df["Date"]).dt.hour
            hourly_totals = df.groupby("Hour")["Amount"].apply(lambda x: abs(x).sum())
            for hour, total in hourly_totals.items():
                if 0 <= hour < 24:
                    hourly_spending[hour] = float(total)
        except:
            # If no time information, distribute spending across business hours (9-21)
            if "Amount" in df.columns:
                avg_per_hour = abs(df["Amount"]).sum() / 13  # 13 business hours
                for hour in range(9, 22):
                    hourly_spending[hour] = float(avg_per_hour)
    
    analytics_data["hourlySpending"] = hourly_spending
    
    # 6. Frequent Merchants
    frequent_merchants = []
    if "Description" in df.columns and "Amount" in df.columns:
        merchant_stats = df.groupby("Description").agg({
            "Amount": [('total', lambda x: abs(x).sum()), 
                       ('avg', lambda x: abs(x).mean()), 
                       ('count', 'count')]
        })
        merchant_stats.columns = ['total', 'avg', 'count']
        merchant_stats = merchant_stats.sort_values('count', ascending=False)
        
        for merchant, row in merchant_stats.head(8).iterrows():
            frequent_merchants.append({
                "merchant": str(merchant),
                "total": float(row['total']),
                "avg": float(row['avg']),
                "count": int(row['count'])
            })
    
    analytics_data["frequentMerchants"] = frequent_merchants
    
    # 7. Data Quality Metrics
    total_records = len(df)
    missing_values = df.isnull().sum().sum()
    duplicates = df.duplicated().sum()
    completeness = ((total_records * len(df.columns) - missing_values) / 
                    (total_records * len(df.columns)) * 100) if total_records > 0 else 100
    
    analytics_data["dataQuality"] = {
        "total": total_records,
        "missing": int(missing_values),
        "duplicates": int(duplicates),
        "completeness": round(float(completeness), 2)
    }
    
    # 8. Generate Insights
    insights = []
    
    # Insight 1: Highest spending category
    if category_trends:
        top_cat = category_trends[0]
        insights.append({
            "icon": "📊",
            "title": "Top Spending Category",
            "text": f"You spent the most on {top_cat['category']} with ₹{top_cat['total']:.2f} across {top_cat['count']} transactions."
        })
    
    # Insight 2: Most expensive transaction
    if "Amount" in df.columns:
        max_transaction = abs(df["Amount"]).max()
        insights.append({
            "icon": "💰",
            "title": "Largest Transaction",
            "text": f"Your largest single transaction was ₹{max_transaction:.2f}. Review large purchases to identify savings opportunities."
        })
    
    # Insight 3: Spending pattern by day
    if weekday_spending:
        max_day_idx = weekday_spending.index(max(weekday_spending))
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        insights.append({
            "icon": "📅",
            "title": "Peak Spending Day",
            "text": f"You spend the most on {days[max_day_idx]} (₹{weekday_spending[max_day_idx]:.2f}). Consider budgeting extra for this day."
        })
    
    # Insight 4: Frequent merchant
    if frequent_merchants:
        top_merchant = frequent_merchants[0]
        insights.append({
            "icon": "🏪",
            "title": "Most Frequent Merchant",
            "text": f"You transact most often with {top_merchant['merchant']} ({top_merchant['count']} times), spending ₹{top_merchant['total']:.2f} in total."
        })
    
    # Insight 5: Spending consistency
    if "Amount" in df.columns:
        cv = (analytics_data["statistics"]["std"] / analytics_data["statistics"]["mean"]) * 100
        consistency = "very consistent" if cv < 50 else "moderately consistent" if cv < 100 else "highly variable"
        insights.append({
            "icon": "📈",
            "title": "Spending Consistency",
            "text": f"Your spending is {consistency} with a coefficient of variation of {cv:.1f}%. {'This is good!' if cv < 50 else 'Try to maintain consistent spending habits.'}"
        })
    
    # Insight 6: Data quality
    if analytics_data["dataQuality"]["completeness"] >= 95:
        insights.append({
            "icon": "✅",
            "title": "Data Quality",
            "text": f"Your financial data is {analytics_data['dataQuality']['completeness']:.1f}% complete with only {analytics_data['dataQuality']['missing']} missing values. Excellent data quality!"
        })
    else:
        insights.append({
            "icon": "⚠️",
            "title": "Data Quality Warning",
            "text": f"Your data has {analytics_data['dataQuality']['missing']} missing values ({analytics_data['dataQuality']['completeness']:.1f}% complete). Consider data cleanup for better insights."
        })
    
    analytics_data["insights"] = insights
    _cache_set("advanced_analytics", signature, analytics_data)
    return jsonify(analytics_data)


@app.route("/export/transactions.csv", methods=["GET"])
def export_transactions_csv():
    """Export current normalized transactions as CSV."""
    global transactions_df
    if transactions_df is None or transactions_df.empty:
        return jsonify({"error": "No data found. Please upload a CSV first."}), 400

    export_df = transactions_df.copy()
    if "Date" in export_df.columns:
        export_df["Date"] = pd.to_datetime(export_df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")

    csv_data = export_df.to_csv(index=False)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions_export.csv"},
    )


@app.route("/export/report.json", methods=["GET"])
def export_report_json():
    """Export computed report summary including health score and category intelligence."""
    global transactions_df
    if transactions_df is None or transactions_df.empty:
        return jsonify({"error": "No data found. Please upload a CSV first."}), 400

    payload = _build_report_payload(transactions_df.copy())
    return Response(
        json.dumps(payload, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=finance_report.json"},
    )

@app.route("/test-categorization", methods=["GET"])
def test_categorization():
    """Test endpoint to verify categorization is working"""
    test_descriptions = [
        "UPI/INDIAN CLEARING/Sent using Paytm",
        "IMPS/UPSTOXSECURITIES",
        "UPI/NETFLIX.COM/Monthly autorenew",
        "UPI/Flipkart/Purchase",
        "UPI/CRED CASHBACK EARNED"
    ]
    results = {}
    for desc in test_descriptions:
        category = _categorize_kotak_transaction(desc)
        results[desc] = category
    return jsonify({
        "message": "Categorization test",
        "results": results
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    url = f"http://0.0.0.0:{port}"
    print(f"Starting Flask server at {url}")
    # Use gunicorn in production, simple server for development
    app.run(host="0.0.0.0", port=port, debug=False)
