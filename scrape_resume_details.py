# This is the base code for scraping the details from the portfolio which will be integrated to main.py search

import os
import re
import csv
import time
import json
import shutil
import string
import random
import urllib.parse
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import logging

import requests
from bs4 import BeautifulSoup

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
})
REQUEST_TIMEOUT = 20
SLEEP_BETWEEN_REQUESTS = 0.5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

DOC_EXTS = (".pdf", ".doc", ".docx", ".rtf", ".odt")
KEYWORDS = [
    "resume", "cv", "curriculum", "vitae", "bio", "biodata",
    "profile", "portfolio", "about", "download", "hire", "work", "career"
]
RESUME_HINTS = [
    "resume", "cv", "curriculum", "vitae", "biodata"
]
LIKELY_PATHS = [
    "/", "/resume", "/cv", "/about", "/about-me", "/aboutme",
    "/download", "/profile", "/portfolio"
]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
# Nepal-focused but permissive: +977 98/97..., or 98/97xxxxxxxx, or 10-digit 9XXXXXXXXX
PHONE_RE = re.compile(r"(?:\+?977[\s\-]?)?(?:9[78]\d{8}|0?9[78]\d{8}|\b9\d{9}\b)")
NAME_TAGS = ["h1", "h2", "title"]

# --- Modified Output Directory Structure ---
# Base directory for all scraped runs
BASE_EXPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scraped")
# This will be set dynamically for each run
CURRENT_RUN_DIR: str = ""
CURRENT_DOWNLOAD_DIR: str = ""
# --- End Modified Output Directory Structure ---


def get_base_url(url: str) -> str:
    try:
        p = urllib.parse.urlparse(url.strip())
        if not p.scheme:
            p = p._replace(scheme="https")
        return f"{p.scheme}://{p.netloc}"
    except Exception:
        return url.strip()

def is_document_url(url: str) -> bool:
    low = url.lower()
    return any(low.endswith(ext) for ext in DOC_EXTS)

def same_host(u: str, base: str) -> bool:
    try:
        return urllib.parse.urlparse(u).netloc.lower() == urllib.parse.urlparse(base).netloc.lower()
    except Exception:
        return False

def fetch(url: str) -> Optional[requests.Response]:
    try:
        resp = SESSION.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if resp.status_code == 200:
            return resp
    except requests.RequestException:
        return None
    return None

def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def extract_contacts(text: str) -> Tuple[Optional[str], Optional[str]]:
    if not text:
        return None, None
    email = None
    phone = None
    em = EMAIL_RE.search(text)
    if em:
        email = em.group(0)
    pm = PHONE_RE.search(text)
    if pm:
        phone = pm.group(0)
    return email, phone

def guess_name_from_dom(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    # priority: <h1>, then <title>, then prominent <h2>
    for tag in NAME_TAGS:
        node = soup.find(tag)
        if node and node.get_text(strip=True):
            cand = clean_text(node.get_text())
            # Remove separators common in titles: "Name - Role" or "Name | Portfolio"
            cand = re.split(r"\s[-|–]\s", cand)[0].strip()
            # Keep it short-ish
            if 2 <= len(cand.split()) <= 5:
                return cand
            if tag in ("h1", "h2") and len(cand.split()) <= 8:
                return cand
    # Fallback: meta og:site_name
    meta = soup.find("meta", attrs={"property": "og:site_name"})
    if meta and meta.get("content"):
        return clean_text(meta["content"])
    # Fallback: domain part
    host = urllib.parse.urlparse(base_url).netloc
    host = host.split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    base = host.split(".")[0]
    return base.capitalize() if base else None

def make_abs(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, href)

def looks_like_resume(href: str, link_text: str) -> bool:
    h = (href or "").lower()
    t = (link_text or "").lower()
    if any(k in RESUME_HINTS for k in (h, t)):
        return True
    # If it's a doc with generic name (e.g., /download.pdf)
    if is_document_url(h) and not any(k in h for k in RESUME_HINTS):
        return True
    return False


def find_resume_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True)
        if looks_like_resume(href, text):
            links.append(make_abs(base_url, href))
    # de-dup preserve order
    seen = set()
    out = []
    for u in links:
        if u not in seen:
            out.append(u)
            seen.add(u)
    return out

def try_likely_paths(base_url: str) -> List[str]:
    out = []
    for p in LIKELY_PATHS:
        u = make_abs(base_url, p)
        out.append(u)
        # also try common file names under root
        for fname in ["resume.pdf", "cv.pdf", "Resume.pdf", "CV.pdf", "resume", "cv"]:
            out.append(make_abs(base_url, f"/{fname}"))
    # de-dup
    seen = set()
    uniq = []
    for u in out:
        if u not in seen:
            uniq.append(u)
            seen.add(u)
    return uniq

def safe_filename(s: str) -> str:
    valid = f"-_.() {string.ascii_letters}{string.digits}"
    return "".join(c for c in s if c in valid)[:120] or f"file_{random.randint(1000,9999)}"

def download_file(url: str, base_url: str) -> Tuple[Optional[str], Optional[str]]:
    global CURRENT_DOWNLOAD_DIR # Use the globally set download directory for the current run
    resp = fetch(url)
    if not resp:
        return None, None
    # choose filename
    parsed = urllib.parse.urlparse(url)
    name = os.path.basename(parsed.path) or "download"
    if "?" in name:
        name = name.split("?")[0]
    host = urllib.parse.urlparse(base_url).netloc.replace(":", "_")
    fname = f"{host}__{safe_filename(name)}"
    
    # Ensure the download directory exists for the current run
    os.makedirs(CURRENT_DOWNLOAD_DIR, exist_ok=True)
    path = os.path.join(CURRENT_DOWNLOAD_DIR, fname)
    
    try:
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return path, fname
    except Exception:
        return None, None

def scrape_page(url: str) -> Tuple[Optional[BeautifulSoup], str]:
    resp = fetch(url)
    if not resp:
        return None, ""
    ctype = resp.headers.get("Content-Type", "").lower()
    if "text/html" not in ctype and "<html" not in resp.text.lower():
        return None, resp.text or ""
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    return soup, html

def process_single_url(original_url: str) -> Dict[str, Optional[str]]:
    original_url = original_url.strip()
    if not original_url:
        return {}

    base_url = get_base_url(original_url)

    result = {
        "original_url": original_url,
        "base_url": base_url,
        "name": None,
        "email": None,
        "phone": None,
        "cv_url": None,
    }

    # If the provided URL is directly a document, download and return
    if is_document_url(original_url):
        path, _ = download_file(original_url, base_url)
        result["cv_url"] = original_url
        # Derive some hints from filename
        file_part = os.path.basename(urllib.parse.urlparse(original_url).path)
        if not result["name"]:
            stem = os.path.splitext(file_part)[0]
            stem = stem.replace("-", " ").replace("_", " ")
            if 2 <= len(stem.split()) <= 6:
                result["name"] = stem.title()
        return result

    # Crawl base and a few likely pages
    visited = set()
    pages_to_try = [make_abs(base_url, p) for p in LIKELY_PATHS]
    pages_to_try = [u for u in pages_to_try if same_host(u, base_url)]
    pages_to_try = list(dict.fromkeys(pages_to_try))[:8]  # cap

    resume_candidates: List[str] = []
    aggregated_text = ""

    for u in pages_to_try:
        if u in visited:
            continue
        visited.add(u)
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        soup, text = scrape_page(u)
        aggregated_text += f"\n{text}"
        if not soup:
            continue

        # name heuristics
        if not result["name"]:
            nm = guess_name_from_dom(soup, base_url)
            if nm:
                result["name"] = nm

        # find resume-like links on this page
        links = find_resume_links(soup, u)
        for lk in links:
            if same_host(lk, base_url) or is_document_url(lk):
                resume_candidates.append(lk)

        # also consider anchors with keywords only (no file ext)
        for a in soup.find_all("a", href=True):
            t = a.get_text(" ", strip=True).lower()
            if any(k in t for k in KEYWORDS):
                resume_candidates.append(make_abs(u, a["href"]))

        # De-dup and cap exploration
        resume_candidates = list(dict.fromkeys(resume_candidates))
        if len(resume_candidates) > 10:
            resume_candidates = resume_candidates[:10]

    # Extract email/phone from all gathered text
    email, phone = extract_contacts(aggregated_text)
    if email:
        result["email"] = email
    if phone:
        result["phone"] = phone

    # Try candidates; if HTML, follow and see if they link to docs
    tried = set()
    for cand in resume_candidates:
        if cand in tried:
            continue
        tried.add(cand)

        if is_document_url(cand):
            path, _ = download_file(cand, base_url)
            if path:
                result["cv_url"] = cand
                break
            continue

        # If HTML, open it and search for doc links
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        soup, text = scrape_page(cand)
        if soup:
            # Contact info from resume page as well
            em2, ph2 = extract_contacts(text)
            if em2 and not result["email"]:
                result["email"] = em2
            if ph2 and not result["phone"]:
                result["phone"] = ph2

            doc_links = find_resume_links(soup, cand)
            for dl in doc_links:
                if is_document_url(dl):
                    path, _ = download_file(dl, base_url)
                    if path:
                        result["cv_url"] = dl
                        break
    
    return result

def read_urls_csv(csv_path: str) -> List[str]:
    urls: List[str] = []
    if not os.path.exists(csv_path):
        print(f"Error: Input CSV file not found at {csv_path}")
        return []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            urls.append(s)
    return urls

def write_results(rows: List[Dict[str, Optional[str]]], out_csv_path: str) -> None:
    if not rows:
        with open(out_csv_path, "w", newline="", encoding="utf-8") as f:
            pass
        return
    fieldnames = ["original_url", "base_url", "name", "email", "phone", "cv_url"]
    with open(out_csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            # Only export the selected fields
            w.writerow({k: r.get(k) or "" for k in fieldnames})

def main():
    global CURRENT_RUN_DIR, CURRENT_DOWNLOAD_DIR

    project_dir = os.path.dirname(os.path.abspath(__file__))
    in_csv = os.path.join(project_dir, "urls.csv")

    # Create a timestamped directory for the current run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    date_only = timestamp.split("_")[0]
    CURRENT_RUN_DIR = os.path.join(BASE_EXPORTS_DIR, f"scraped_run_{timestamp}")
    os.makedirs(CURRENT_RUN_DIR, exist_ok=True)
    
    # Define the output CSV path within the current run's directory, append date to filename
    out_csv = os.path.join(CURRENT_RUN_DIR, f"scraped_data_{date_only}.csv")
    
    # Define the CV download directory within the current run's directory
    CURRENT_DOWNLOAD_DIR = os.path.join(CURRENT_RUN_DIR, "downloaded_cvs")
    os.makedirs(CURRENT_DOWNLOAD_DIR, exist_ok=True) # Ensure this directory exists

    urls = read_urls_csv(in_csv)
    results: List[Dict[str, Optional[str]]] = []

    if not urls:
        print("No URLs found in urls.csv. Exiting.")
        return

    for i, url in enumerate(urls, start=1):
        try:
            print(f"[{i}/{len(urls)}] Processing:", url)
            res = process_single_url(url)
            results.append(res)
            # Log if expected data points are missing for this site
            missing_fields = [k for k in ["name", "email", "phone", "cv_url"] if not (res.get(k) or "")]
            if missing_fields:
                logging.warning(f"Data not found for {url}: missing {', '.join(missing_fields)}")
        except Exception as e:
            print(f"Error processing {url}: {e}")
        time.sleep(SLEEP_BETWEEN_REQUESTS)

    # Summary: X out of Y CVs found (download URLs identified)
    num_found = sum(1 for r in results if r.get("cv_url"))
    print(f"\n{num_found} out of {len(results)} CVs found")

    write_results(results, out_csv)
    print(f"\nSaved {len(results)} rows to: {out_csv}")
    print(f"Downloaded files (if any) under: {CURRENT_DOWNLOAD_DIR}")
    print(f"All output for this run is in: {CURRENT_RUN_DIR}")

if __name__ == "__main__":
    main()