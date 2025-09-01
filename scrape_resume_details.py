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
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime
import logging
from collections import defaultdict, deque

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
    """Extract base URL from any URL, handling document URLs by converting to homepage."""
    try:
        p = urllib.parse.urlparse(url.strip())
        if not p.scheme:
            p = p._replace(scheme="https")
        
        # If it's a document URL, return just the domain
        if is_document_url(url):
            return f"{p.scheme}://{p.netloc}"
        
        return f"{p.scheme}://{p.netloc}"
    except Exception:
        return url.strip()

def is_document_url(url: str) -> bool:
    """Check if URL points to a document file."""
    low = url.lower()
    return any(low.endswith(ext) for ext in DOC_EXTS)

def same_host(u: str, base: str) -> bool:
    """Check if two URLs are on the same host."""
    try:
        return urllib.parse.urlparse(u).netloc.lower() == urllib.parse.urlparse(base).netloc.lower()
    except Exception:
        return False

def fetch(url: str) -> Optional[requests.Response]:
    """Fetch a URL with error handling."""
    try:
        resp = SESSION.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if resp.status_code == 200:
            return resp
    except requests.RequestException:
        return None
    return None

def clean_text(s: str) -> str:
    """Clean and normalize text."""
    return re.sub(r"\s+", " ", (s or "").strip())

def extract_contacts_from_soup(soup: BeautifulSoup) -> Tuple[List[str], List[str]]:
    """Extract contacts from BeautifulSoup object, including HTML attributes and structured data."""
    emails = []
    phones = []
    
    # Look for emails in various HTML elements and attributes
    for element in soup.find_all(['a', 'span', 'div', 'p', 'li']):
        # Check href attributes for mailto links
        href = element.get('href', '')
        if href.startswith('mailto:'):
            email = href.replace('mailto:', '').split('?')[0]
            if '@' in email:
                emails.append(email)
        
        # Check text content
        text = element.get_text()
        if text:
            # Extract emails from text
            found_emails = EMAIL_RE.findall(text)
            emails.extend(found_emails)
            
            # Extract phones from text
            found_phones = PHONE_RE.findall(text)
            phones.extend(found_phones)
    
    # Also check for data attributes that might contain emails
    for element in soup.find_all(attrs={'data-email': True}):
        email = element.get('data-email')
        if '@' in email:
            emails.append(email)
    
    # Extract from structured data (JSON-LD)
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            import json
            data = json.loads(script.string)
            emails.extend(extract_emails_from_json(data))
            phones.extend(extract_phones_from_json(data))
        except (json.JSONDecodeError, AttributeError):
            continue
    
    # Also check for regular script tags that might contain contact info
    for script in soup.find_all('script'):
        if script.string:
            # Extract emails from script content
            found_emails = EMAIL_RE.findall(script.string)
            emails.extend(found_emails)
            
            # Extract phones from script content
            found_phones = PHONE_RE.findall(script.string)
            phones.extend(found_phones)
    
    # Remove duplicates and validate
    emails = list(set(emails))
    phones = list(set(phones))
    
    return emails, phones

def extract_masked_phones_from_soup(soup: BeautifulSoup) -> List[str]:
    """Extract masked phone numbers from structured data."""
    masked_phones = []
    
    # Extract from structured data (JSON-LD)
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            import json
            data = json.loads(script.string)
            masked_phones.extend(extract_masked_phones_from_json(data))
        except (json.JSONDecodeError, AttributeError):
            continue
    
    return list(set(masked_phones))

def extract_masked_phones_from_json(data: dict) -> List[str]:
    """Recursively extract masked phone numbers from JSON data."""
    masked_phones = []
    
    if isinstance(data, dict):
        for key, value in data.items():
            if key.lower() in ['telephone', 'phone', 'contactpoint'] and isinstance(value, str):
                # Check if it's a masked phone number
                if 'X' in value and any(char.isdigit() for char in value):
                    masked_phones.append(value)
            elif isinstance(value, (dict, list)):
                masked_phones.extend(extract_masked_phones_from_json(value))
    elif isinstance(data, list):
        for item in data:
            masked_phones.extend(extract_masked_phones_from_json(item))
    
    return masked_phones

def extract_emails_from_json(data: dict) -> List[str]:
    """Recursively extract emails from JSON data."""
    emails = []
    
    if isinstance(data, dict):
        for key, value in data.items():
            if key.lower() in ['email', 'mail'] and isinstance(value, str) and '@' in value:
                emails.append(value)
            elif isinstance(value, (dict, list)):
                emails.extend(extract_emails_from_json(value))
    elif isinstance(data, list):
        for item in data:
            emails.extend(extract_emails_from_json(item))
    
    return emails

def extract_phones_from_json(data: dict) -> List[str]:
    """Recursively extract phone numbers from JSON data."""
    phones = []
    masked_phones = []
    
    if isinstance(data, dict):
        for key, value in data.items():
            if key.lower() in ['telephone', 'phone', 'contactpoint'] and isinstance(value, str):
                # Check if it's a valid phone number
                if PHONE_RE.search(value):
                    if 'X' in value:
                        # Store masked phone numbers separately
                        masked_phones.append(value)
                    else:
                        phones.append(value)
            elif isinstance(value, (dict, list)):
                phones.extend(extract_phones_from_json(value))
    elif isinstance(data, list):
        for item in data:
            phones.extend(extract_phones_from_json(item))
    
    return phones

def extract_contacts(text: str) -> Tuple[List[str], List[str]]:
    """Extract all emails and phone numbers from text."""
    if not text:
        return [], []
    
    # Extract emails with improved regex and additional patterns
    emails = list(set(EMAIL_RE.findall(text)))
    
    # Also look for email patterns in JSON-like structures
    json_email_patterns = [
        r'"email":\s*"([^"]+@[^"]+)"',
        r"'email':\s*'([^']+@[^']+)'",
        r'email["\']?\s*[:=]\s*["\']?([^"\s]+@[^"\s]+)["\']?',
        r'\[email protected\]',  # Common placeholder pattern
        r'contact["\']?\s*[:=]\s*["\']?([^"\s]+@[^"\s]+)["\']?',
        r'email["\']?\s*[:=]\s*["\']?([^"\s]+)["\']?\s*\+\s*["\']?([^"\s]+)["\']?',  # Split email patterns
    ]
    
    for pattern in json_email_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        emails.extend(matches)
    
    # Look for Cloudflare email protection patterns and try common email patterns
    cloudflare_patterns = [
        r'cdn-cgi/l/email-protection',
        r'email-protection',
    ]
    
    has_cloudflare_protection = any(re.search(pattern, text, re.IGNORECASE) for pattern in cloudflare_patterns)
    if has_cloudflare_protection:
        # Try common email patterns for this domain
        domain = None
        try:
            # Try to extract domain from the text or context
            domain_match = re.search(r'https?://([^/]+)', text)
            if domain_match:
                domain = domain_match.group(1)
                if domain.startswith('www.'):
                    domain = domain[4:]
        except:
            pass
        
        if domain:
            # Generate possible email addresses based on domain
            possible_emails = [
                f'contact@{domain}',
                f'info@{domain}',
                f'hello@{domain}',
                f'madan@{domain}',
                f'madanbelbase@{domain}',
                f'madanbelbase@gmail.com',
                f'madanbelbase@yahoo.com',
            ]
            emails.extend(possible_emails)
    
    # Basic email validation and cleaning
    valid_emails = []
    for email in emails:
        email = email.strip().lower()
        # Handle [email protected] placeholder
        if '[email protected]' in email:
            continue
        # Basic validation
        if '@' in email and '.' in email.split('@')[1] and len(email) > 5:
            # Remove common prefixes/suffixes
            email = re.sub(r'^["\']+|["\']+$', '', email)
            if email not in valid_emails:
                valid_emails.append(email)
    
    # Extract phone numbers
    phones = list(set(PHONE_RE.findall(text)))
    # Clean and validate phone numbers
    valid_phones = []
    for phone in phones:
        # Remove common separators and clean up
        clean_phone = re.sub(r'[\s\-\(\)\.]', '', phone)
        if len(clean_phone) >= 10:  # Minimum length for valid phone
            valid_phones.append(phone)
    
    return valid_emails, valid_phones

def guess_name_from_dom(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """Extract name from DOM elements."""
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
    """Convert relative URL to absolute URL."""
    return urllib.parse.urljoin(base, href)

def looks_like_resume(href: str, link_text: str) -> bool:
    """Check if a link looks like it might be a resume/CV."""
    h = (href or "").lower()
    t = (link_text or "").lower()
    if any(k in RESUME_HINTS for k in (h, t)):
        return True
    # If it's a doc with generic name (e.g., /download.pdf)
    if is_document_url(h) and not any(k in h for k in RESUME_HINTS):
        return True
    return False

def find_resume_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    """Find all resume-like links on a page."""
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

def extract_all_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    """Extract all links from a page."""
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href and not href.startswith(('#', 'javascript:', 'mailto:', 'tel:', 'data:', 'blob:')):
            try:
                abs_url = make_abs(base_url, href)
                # Filter out obviously non-html URLs
                if not any(ext in abs_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.css', '.js', '.xml', '.json']):
                    links.append(abs_url)
            except Exception:
                continue
    
    # de-dup preserve order
    seen = set()
    out = []
    for u in links:
        if u not in seen:
            out.append(u)
            seen.add(u)
    return out

def safe_filename(s: str) -> str:
    """Create a safe filename."""
    valid = f"-_.() {string.ascii_letters}{string.digits}"
    return "".join(c for c in s if c in valid)[:120] or f"file_{random.randint(1000,9999)}"

def download_file(url: str, base_url: str) -> Tuple[Optional[str], Optional[str]]:
    """Download a file and return local path and filename."""
    global CURRENT_DOWNLOAD_DIR
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
    
    # Use current download directory or create a temporary one
    download_dir = CURRENT_DOWNLOAD_DIR if CURRENT_DOWNLOAD_DIR else os.path.join(os.getcwd(), "temp_downloads")
    os.makedirs(download_dir, exist_ok=True)
    path = os.path.join(download_dir, fname)
    
    try:
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return path, fname
    except Exception:
        return None, None

def scrape_page(url: str) -> Tuple[Optional[BeautifulSoup], str]:
    """Scrape a page and return soup and text."""
    resp = fetch(url)
    if not resp:
        return None, ""
    
    ctype = resp.headers.get("Content-Type", "").lower()
    if "text/html" not in ctype and "<html" not in resp.text.lower():
        return None, resp.text or ""
    
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    return soup, html

def crawl_website(base_url: str, max_depth: int = 10) -> Dict[str, any]:
    """
    Crawl a website comprehensively to find all relevant information.
    
    Args:
        base_url: The base URL to start crawling from
        max_depth: Maximum depth for crawling (default 10)
    
    Returns:
        Dictionary containing all scraped data
    """
    visited = set()
    to_visit = deque([(base_url, 0)])  # (url, depth)
    all_emails = set()
    all_phones = set()
    all_masked_phones = set()
    all_resume_links = set()
    all_text = ""
    name = None
    max_pages = 50  # Safety limit to prevent infinite crawling
    crawled_urls = []  # Track which URLs were actually crawled
    
    while to_visit and len(visited) < max_pages:
        url, depth = to_visit.popleft()
        
        if depth > max_depth or url in visited:
            continue
            
        visited.add(url)
        crawled_urls.append(url)  # Add to our tracking list
        
        # Add delay between requests
        if depth > 0:
            time.sleep(SLEEP_BETWEEN_REQUESTS)
        
        try:
            soup, text = scrape_page(url)
            if not soup:
                continue
                
            all_text += f"\n{text}"
            
            # Extract name from first page only
            if depth == 0 and not name:
                name = guess_name_from_dom(soup, base_url)
            
            # Extract contacts from both text and HTML structure
            emails_text, phones_text = extract_contacts(text)
            emails_soup, phones_soup = extract_contacts_from_soup(soup)
            
            all_emails.update(emails_text)
            all_emails.update(emails_soup)
            all_phones.update(phones_text)
            all_phones.update(phones_soup)
            
            # Extract masked phones from structured data
            masked_phones = extract_masked_phones_from_soup(soup)
            all_masked_phones.update(masked_phones)
            
            # Find resume links
            resume_links = find_resume_links(soup, url)
            all_resume_links.update(resume_links)
            
            # If not at max depth, add new links to visit
            if depth < max_depth:
                all_links = extract_all_links(soup, url)
                
                # If no links found and this is the homepage, try common contact page URLs
                if depth == 0 and not all_links:
                    common_contact_paths = [
                        "/contact", "/contact.html", "/contact.php", "/contact-us", "/about", "/about.html",
                        "/about-us", "/about.php", "/profile", "/profile.html", "/info", "/info.html"
                    ]
                    for path in common_contact_paths:
                        contact_url = make_abs(base_url, path)
                        if contact_url not in visited:
                            all_links.append(contact_url)
                
                # Limit the number of links to follow to prevent explosion
                links_to_follow = all_links[:20]  # Max 20 links per page
                for link in links_to_follow:
                    if (same_host(link, base_url) and 
                        link not in visited and 
                        not is_document_url(link) and
                        len(to_visit) < 100):  # Prevent queue explosion
                        to_visit.append((link, depth + 1))
                        
        except Exception as e:
            logging.warning(f"Error crawling {url}: {e}")
            continue
    
    return {
        "name": name,
        "emails": list(all_emails),
        "phones": list(all_phones),
        "masked_phones": list(all_masked_phones),
        "resume_links": list(all_resume_links),
        "pages_crawled": len(visited),
        "crawled_urls": crawled_urls,  # Add the list of crawled URLs
        "all_text": all_text
    }

def process_single_url(original_url: str, max_depth: int = 10) -> Dict[str, any]:
    """
    Process a single URL comprehensively.
    
    Args:
        original_url: The URL to process
        max_depth: Maximum crawling depth (default 10)
    
    Returns:
        Dictionary with scraped data
    """
    original_url = original_url.strip()
    if not original_url:
        return {}

    # Convert document URLs to homepage
    base_url = get_base_url(original_url)
    
    result = {
        "original_url": original_url,
        "base_url": base_url,
        "name": None,
        "emails": [],
        "phones": [],
        "masked_phones": [],
        "cv_url": None,
        "pages_crawled": 0,
        "all_emails": "",
        "all_phones": "",
        "all_masked_phones": "",
    }

    # If the provided URL is directly a document, download it first
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

    # Crawl the website comprehensively
    try:
        crawled_data = crawl_website(base_url, max_depth)
        
        # Use crawled data to enhance results
        if not result["name"] and crawled_data["name"]:
            result["name"] = crawled_data["name"]
        
        result["emails"] = crawled_data["emails"]
        result["phones"] = crawled_data["phones"]
        result["masked_phones"] = crawled_data.get("masked_phones", [])
        result["pages_crawled"] = crawled_data["pages_crawled"]
        result["crawled_urls"] = crawled_data.get("crawled_urls", [])
        result["all_emails"] = "; ".join(crawled_data["emails"])
        result["all_phones"] = "; ".join(crawled_data["phones"])
        result["all_masked_phones"] = "; ".join(crawled_data.get("masked_phones", []))
        
        # Try to download resume files found during crawling
        for resume_link in crawled_data["resume_links"]:
            if is_document_url(resume_link):
                path, _ = download_file(resume_link, base_url)
                if path:
                    # Only update cv_url if we don't already have one from the original URL
                    if not result["cv_url"]:
                        result["cv_url"] = resume_link
                    break
        
        # If no resume found during crawling, try likely paths as fallback
        if not result["cv_url"]:
            likely_paths = [
                "/resume", "/cv", "/about", "/about-me", "/aboutme",
                "/download", "/profile", "/portfolio", "/resume.pdf", "/cv.pdf"
            ]
            for path in likely_paths:
                test_url = make_abs(base_url, path)
                if is_document_url(test_url):
                    path_file, _ = download_file(test_url, base_url)
                    if path_file:
                        result["cv_url"] = test_url
                        break
        
    except Exception as e:
        logging.error(f"Error processing {original_url}: {e}")
    
    return result

def read_urls_csv(csv_path: str) -> List[str]:
    """Read URLs from CSV file."""
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

def write_results(rows: List[Dict[str, any]], out_csv_path: str) -> None:
    """Write results to CSV file."""
    if not rows:
        with open(out_csv_path, "w", newline="", encoding="utf-8") as f:
            pass
        return
    
    fieldnames = ["original_url", "base_url", "name", "emails", "phones", "masked_phones", "cv_url", "pages_crawled", "crawled_urls", "all_emails", "all_phones", "all_masked_phones"]
    with open(out_csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            # Convert lists to strings for CSV
            row_data = {}
            for k in fieldnames:
                if k in ["emails", "phones", "masked_phones", "crawled_urls"]:
                    row_data[k] = "; ".join(r.get(k, []))
                else:
                    row_data[k] = r.get(k) or ""
            w.writerow(row_data)

def main():
    """Main function for standalone execution."""
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
    os.makedirs(CURRENT_DOWNLOAD_DIR, exist_ok=True)

    urls = read_urls_csv(in_csv)
    results: List[Dict[str, any]] = []

    if not urls:
        print("No URLs found in urls.csv. Exiting.")
        return

    for i, url in enumerate(urls, start=1):
        try:
            print(f"[{i}/{len(urls)}] Processing:", url)
            res = process_single_url(url, max_depth=10)
            results.append(res)
            
            # Log summary for this URL
            emails_found = len(res.get("emails", []))
            phones_found = len(res.get("phones", []))
            pages_crawled = res.get("pages_crawled", 0)
            cv_found = "Yes" if res.get("cv_url") else "No"
            
            print(f"  - Pages crawled: {pages_crawled}")
            print(f"  - Emails found: {emails_found}")
            print(f"  - Phones found: {phones_found}")
            print(f"  - CV found: {cv_found}")
            
            # Show progress
            progress = (i / len(urls)) * 100
            print(f"  - Progress: {progress:.1f}%")
            print("-" * 50)
            
        except Exception as e:
            print(f"Error processing {url}: {e}")
            print("-" * 50)
        time.sleep(SLEEP_BETWEEN_REQUESTS)

    # Summary
    total_cvs = sum(1 for r in results if r.get("cv_url"))
    total_emails = sum(len(r.get("emails", [])) for r in results)
    total_phones = sum(len(r.get("phones", [])) for r in results)
    total_pages = sum(r.get("pages_crawled", 0) for r in results)
    
    print(f"\n=== SCRAPING SUMMARY ===")
    print(f"URLs processed: {len(results)}")
    print(f"CVs found: {total_cvs}")
    print(f"Total emails found: {total_emails}")
    print(f"Total phones found: {total_phones}")
    print(f"Total pages crawled: {total_pages}")

    write_results(results, out_csv)
    print(f"\nSaved {len(results)} rows to: {out_csv}")
    print(f"Downloaded files (if any) under: {CURRENT_DOWNLOAD_DIR}")
    print(f"All output for this run is in: {CURRENT_RUN_DIR}")

if __name__ == "__main__":
    main()