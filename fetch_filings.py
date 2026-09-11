"""
Build the corpus: download recent SEC filings and convert them to plain text.

Why this exists as a script rather than committed data: the filings are public,
but a repo that ships 350KB of scraped text per company is a repo nobody can
verify. Shipping the fetcher means anyone who clones this rebuilds the same
corpus and can re-run the eval and get the same numbers.

EDGAR requires a User-Agent header identifying you, or it returns 403. Set it
in the environment so this file carries no personal data:

    export SEC_USER_AGENT="Your Name your@email.com"
    python fetch_filings.py

Writes corpus/{ticker}-{form}-{period}.txt, one file per filing.
"""
import os
import re
import sys
import time
import json
import html
import urllib.request

# CIK is the SEC's permanent company id. Zero-padded to 10 digits in API paths.
COMPANIES = {
    "PINS": 1506293,   # Pinterest
    "SNAP": 1564408,   # Snap
    "RDDT": 1713445,   # Reddit
    "META": 1326801,   # Meta Platforms
}

FORMS = ("10-K", "10-Q")
PER_COMPANY = 4          # most recent N filings per company
OUT_DIR = "corpus"
RATE_LIMIT_SECONDS = 0.2  # SEC asks for 10 requests/second maximum


def user_agent():
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        sys.exit(
            "SEC_USER_AGENT is not set. EDGAR rejects requests without one.\n"
            '  export SEC_USER_AGENT="Your Name your@email.com"'
        )
    return ua


def get(url, ua):
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="ignore")


def html_to_text(raw):
    """Strip HTML to readable text, preserving block structure.

    The newline and tab substitutions matter more than they look. Chunking
    later depends on being able to see where a block ended, and financial
    tables are meaningless once their row boundaries collapse into one line.
    """
    # Inline XBRL: SEC filings embed machine-readable financial tagging in the
    # same HTML as the prose. <ix:header> appears once per filing and holds all
    # the hidden context: CIK numbers, taxonomy codes like us-gaap:CommonClassBMember,
    # and hundreds of ISO dates. None of it is text anyone would ask about, and
    # before this was stripped it produced 456 junk chunks out of 9,811, stuffed
    # with date terms that then competed in every date-related search.
    #
    # The ix:nonFraction and ix:nonNumeric tags are left alone on purpose. Those
    # wrap real displayed numbers, and the tag stripper below correctly keeps the
    # value inside them.
    raw = re.sub(r"(?is)<ix:header.*?</ix:header>", " ", raw)
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    raw = re.sub(r"(?i)</(p|div|tr|h[1-6]|li)>", "\n", raw)
    raw = re.sub(r"(?i)</t[dh]>", "\t", raw)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    # Collapse runs of spaces but NOT tabs. The line above turns each table cell
    # boundary into a tab, and an earlier version of this collapsed them away two
    # lines later, silently undoing the table structure this function claims to
    # preserve.
    text = re.sub(r"[ ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def recent_filings(cik, ua):
    """Return (form, period, document_url) for this company's recent filings."""
    url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    data = json.loads(get(url, ua))
    recent = data["filings"]["recent"]
    out = []
    for i in range(len(recent["form"])):
        if recent["form"][i] not in FORMS:
            continue
        accession = recent["accessionNumber"][i].replace("-", "")
        doc = recent["primaryDocument"][i]
        out.append((
            recent["form"][i],
            recent["reportDate"][i],
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}",
        ))
        if len(out) >= PER_COMPANY:
            break
    return out


def main():
    ua = user_agent()
    os.makedirs(OUT_DIR, exist_ok=True)
    total_chars = 0

    for ticker, cik in COMPANIES.items():
        print(f"\n{ticker} (CIK {cik})")
        try:
            filings = recent_filings(cik, ua)
        except Exception as e:
            print(f"  could not list filings: {e}")
            continue
        time.sleep(RATE_LIMIT_SECONDS)

        for form, period, url in filings:
            name = f"{ticker}-{form}-{period}.txt".replace("/", "-")
            path = os.path.join(OUT_DIR, name)
            if os.path.exists(path):
                print(f"  skip   {name} (already downloaded)")
                continue
            try:
                text = html_to_text(get(url, ua))
            except Exception as e:
                print(f"  FAILED {name}: {e}")
                continue
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            total_chars += len(text)
            print(f"  wrote  {name}  ({len(text):,} chars)")
            time.sleep(RATE_LIMIT_SECONDS)

    files = os.listdir(OUT_DIR)
    print(f"\n{len(files)} files in {OUT_DIR}/, {total_chars:,} new chars this run")


if __name__ == "__main__":
    main()
