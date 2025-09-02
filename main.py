import os
import time
import json 
import requests
import pandas as pd
import streamlit as st
from urllib.parse import urlparse
from dotenv import load_dotenv
import csv
from datetime import datetime

import scrape_resume_details as scraper


load_dotenv()
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
SERPER_URL = "https://google.serper.dev/search"
SERPER_HEADERS = {"X-API-KEY": SERPER_API_KEY or "", "Content-Type": "application/json"}

DEFAULT_GL = "np"
DEFAULT_HL = "en"
DEFAULT_LOCATION = "Kathmandu, Nepal"


st.set_page_config(layout="wide", page_title="No Bull Code Talent Sourcing (Simple & Advanced)")

def _host(u: str) -> str:
    try:
        return urlparse(u).netloc.lower()
    except Exception:
        return ""

def _safe_project_dir() -> str:
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.getcwd()

favicon_path = os.path.join(_safe_project_dir(), "nobullcode_favicon.png")

st.set_page_config(
    layout="wide", 
    page_title="No Bull Code Talent Sourcing", 
    page_icon=favicon_path if os.path.exists(favicon_path) else "🔍"
)

cols = st.columns([0.3, 4])
with cols[0]:
    st.image(os.path.join(_safe_project_dir(), "nobullcode_favicon.png"), width=80)
with cols[1]:
    st.title("No Bull Code Talent Sourcing")
    st.caption("Switch between a simple extractor and an advanced, role-aware fan-out search. Export results and review selections with ease.")


def _safe_filename_from_query(q: str) -> str:
    return "".join([c if c.isalnum() or c in (" ", "_", "-") else "" for c in q]).strip().replace(" ", "_").lower()

def _serper_page(query: str, page: int, gl: str=None, hl: str=None, location: str=None, tbs: str=None, num: int = None):
    """
    Single Serper request for one page.
    - query: search string
    - page: 1-based page index
    Optional:
      gl: country code (e.g., "np"), hl: lang (e.g., "en"), location: city string
      tbs: time-based search ("qdr:m","qdr:y", etc.)
      num: Requested results count. Serper's /search supports 10 by default; keep None or 10.
    """
    payload = {"q": query, "page": page}
    if gl: payload["gl"] = gl
    if hl: payload["hl"] = hl
    if location: payload["location"] = location
    if tbs: payload["tbs"] = tbs
    if num: payload["num"] = num

    r = requests.post(SERPER_URL, headers=SERPER_HEADERS, json=payload, timeout=25)
    r.raise_for_status()
    return r.json()


def build_role_variants_from_query(base_query: str, role_synonyms_enabled: bool = True):
    """
    Infer buckets (backend/frontend/devops/…) from the user's query and return a
    compact list of quoted role phrases tailored to that intent.
    """
    q = (base_query or "").lower()

    buckets = {
        "backend": [
            "backend", "back-end", "server", "api", "django", "flask", "fastapi",
            "spring", "spring boot", "laravel", "node", "express", "rails", "golang", "rust"
        ],
        "frontend": [
            "frontend", "front-end", "react", "vue", "nuxt", "next", "angular", "svelte",
            "ui developer", "web developer", "javascript developer"
        ],
        "devops": [
            "devops", "sre", "site reliability", "platform engineer", "kubernetes",
            "k8s", "docker", "terraform", "ansible", "jenkins", "cicd", "ci/cd", "aws", "gcp", "azure"
        ],
        "mobile": [
            "mobile", "android", "kotlin", "java android", "ios", "swift", "react native", "flutter"
        ],
        "data": [
            "data engineer", "data engineering", "spark", "hadoop", "etl", "elt", "snowflake",
            "databricks", "airflow", "bigquery", "redshift"
        ],
        "mlai": [
            "machine learning", "ml engineer", "mlops", "deep learning", "pytorch",
            "tensorflow", "sklearn", "llm", "nlp", "computer vision", "genai", "generative ai"
        ],
        "qa": [
            "qa", "quality assurance", "test automation", "sdet", "selenium", "cypress", "playwright"
        ],
        "security": [
            "security", "appsec", "cloud security", "penetration testing", "pentest", "soc", "siem", "devsecops"
        ],
        "cloud": [
            "cloud", "aws", "gcp", "azure", "cloud architect", "cloud engineer"
        ],
        "iot": [
            "iot", "internet of things", "embedded", "firmware", "rtos", "microcontroller",
            "stm32", "arduino", "esp32", "bluetooth low energy", "ble", "edge"
        ],
        "fullstack": [
            "full stack", "full-stack", "mern", "mean", "t3 stack", "nextjs", "next.js"
        ],
        "game": [
            "game", "unity", "unreal", "godot", "gameplay programmer"
        ],
        "blockchain": [
            "blockchain", "web3", "solidity", "smart contract", "defi"
        ],
    }

    expansions = {
        "backend": [
            '"backend developer"', '"backend engineer"', '"python developer"', '"django developer"',
            '"node.js developer"', '"express developer"', '"spring boot developer"', '"golang developer"'
        ],
        "frontend": [
            '"frontend developer"', '"frontend engineer"', '"react developer"', '"next.js developer"',
            '"vue developer"', '"angular developer"', '"ui developer"'
        ],
        "devops": [
            '"devops engineer"', '"site reliability engineer"', '"platform engineer"', '"cloud devops engineer"',
            '"kubernetes engineer"'
        ],
        "mobile": [
            '"android developer"', '"ios developer"', '"mobile developer"', '"react native developer"', '"flutter developer"'
        ],
        "data": [
            '"data engineer"', '"etl engineer"', '"data pipeline engineer"', '"big data engineer"'
        ],
        "mlai": [
            '"machine learning engineer"', '"ml engineer"', '"mlops engineer"', '"computer vision engineer"', '"nlp engineer"'
        ],
        "qa": [
            '"qa engineer"', '"sdet"', '"test automation engineer"', '"quality assurance engineer"'
        ],
        "security": [
            '"application security engineer"', '"security engineer"', '"devsecops engineer"', '"penetration tester"'
        ],
        "cloud": [
            '"cloud engineer"', '"cloud architect"', '"aws engineer"', '"gcp engineer"', '"azure engineer"'
        ],
        "iot": [
            '"iot engineer"', '"embedded engineer"', '"firmware engineer"', '"embedded linux engineer"'
        ],
        "fullstack": [
            '"full stack developer"', '"full stack engineer"', '"mern developer"', '"next.js full stack developer"'
        ],
        "game": [
            '"game developer"', '"unity developer"', '"unreal developer"', '"gameplay programmer"'
        ],
        "blockchain": [
            '"blockchain developer"', '"solidity developer"', '"web3 developer"', '"smart contract engineer"'
        ],
    }

    matched = set()
    for bucket, keys in buckets.items():
        if any(k in q for k in keys):
            matched.add(bucket)

    if not matched:
        if role_synonyms_enabled:
            return [
                '"backend developer"', '"backend engineer"', '"python developer"', '"node.js developer"',
                '"django developer"', '"express developer"', '"spring boot developer"'
            ]
        else:
            return ['"backend developer"']

    roles = []
    if role_synonyms_enabled:
        for b in matched:
            roles.extend(expansions.get(b, []))
    else:
        for b in matched:
            roles.extend(expansions.get(b, [])[:1])

    seen = set()
    out = []
    for r in roles:
        if r not in seen:
            out.append(r)
            seen.add(r)
    return out[:40]


@st.cache_data(ttl=3600, show_spinner=False)
def get_many_google_results(
    base_query: str,
    num_results: int = 100,
    gl: str = DEFAULT_GL,
    hl: str = DEFAULT_HL,
    location: str = DEFAULT_LOCATION,
    tbs: str = None,
    max_pages_per_query: int = 5,
    polite_delay: float = 0.4,
    enable_site_variants: bool = True,
    enable_filetype_variants: bool = True,
    enable_intitle_inurl_variants: bool = True,
    role_synonyms_enabled: bool = True,
):
    if not SERPER_API_KEY:
        return [{"error": "Missing SERPER_API_KEY in environment."}]

    geo = '(nepal OR kathmandu OR lalitpur OR bhaktapur OR pokhara OR biratnagar OR butwal)'
    role_variants = build_role_variants_from_query(base_query, role_synonyms_enabled=role_synonyms_enabled)
    intent_variants = ['(cv OR resume OR portfolio)']
    intitle_inurl_variants = [
        'intitle:resume', 'intitle:portfolio', 'inurl:resume', 'inurl:cv'
    ] if enable_intitle_inurl_variants else []
    filetype_variants = [
        'filetype:pdf (resume OR cv)', 'filetype:doc OR filetype:docx "resume"'
    ] if enable_filetype_variants else []
    site_variants = [
        'site:github.io', 'site:wixsite.com', 'site:canva.site', 'site:notion.site',
        'site:about.me', 'site:googleusercontent.com'
    ] if enable_site_variants else []

    variants = [base_query.strip()]
    for role in role_variants:
        for intent in intent_variants:
            variants.append(f'{role} {intent} {geo}')
    for role in role_variants:
        for ii in intitle_inurl_variants:
            variants.append(f'{role} {ii} {geo}')
    for role in role_variants:
        for ft in filetype_variants:
            variants.append(f'{role} {ft} {geo}')
    for role in role_variants:
        for site in site_variants:
            variants.append(f'{role} {geo} {site}')

    seen_v = set()
    clean_variants = []
    for v in variants:
        vv = " ".join(v.split())
        if vv and vv not in seen_v:
            clean_variants.append(vv)
            seen_v.add(vv)

    results = []
    seen_urls, seen_hosts = set(), set()
    status = st.empty()

    for vi, q in enumerate(clean_variants, start=1):
        if len(results) >= num_results:
            break
        for page in range(1, max_pages_per_query + 1):
            if len(results) >= num_results:
                break
            status.info(f'🔎 Searching variant {vi}/{len(clean_variants)} — page {page} … '
                        f'Collected {len(results)}/{num_results}')
            try:
                data = _serper_page(q, page, gl=gl, hl=hl, location=location, tbs=tbs)
            except requests.RequestException as e:
                results.append({
                    "query_variant": q,
                    "link": None,
                    "title": f"[ERROR] {str(e)}",
                    "snippet": ""
                })
                break

            organic = data.get('organic', []) or []
            if not organic:
                break

            page_got_new = False
            for item in organic:
                link = item.get('link')
                if not link:
                    continue
                host = _host(link)
                if (link in seen_urls) or (host in seen_hosts):
                    continue

                seen_urls.add(link)
                seen_hosts.add(host)
                results.append({
                    "query_variant": q,
                    "link": link,
                    "title": item.get('title', ''),
                    "snippet": item.get('snippet', '')
                })
                page_got_new = True

                if len(results) >= num_results:
                    break

            if not page_got_new or len(organic) < 10:
                break

            if polite_delay:
                time.sleep(polite_delay)

    status.empty()
    return results[:num_results]


@st.cache_data(ttl=3600, show_spinner=False)
def get_google_search_results_simple(query: str, num_results_to_fetch: int = 100):
    if not SERPER_API_KEY:
        return []

    url = SERPER_URL
    headers = SERPER_HEADERS

    all_results = []
    max_results_per_page = 10
    num_pages = (num_results_to_fetch + max_results_per_page - 1) // max_results_per_page

    status_message = st.empty()
    for page in range(num_pages):
        if len(all_results) >= num_results_to_fetch:
            break
        payload = {"q": query, "page": page + 1}
        try:
            status_message.info(
                f"Fetching page {page + 1}/{num_pages} "
                f"(collected {len(all_results)}/{num_results_to_fetch})…"
            )
            response = requests.post(url, headers=headers, json=payload, timeout=25)
            response.raise_for_status()
            data = response.json()

            if 'organic' in data:
                for result in data['organic']:
                    all_results.append({
                        'link': result.get('link'),
                        'title': result.get('title'),
                        'snippet': result.get('snippet')
                    })

            if 'organic' not in data or len(data.get('organic', [])) < max_results_per_page:
                status_message.warning(
                    f"Fewer results returned on page {page + 1}; stopping pagination."
                )
                break

            if page < num_pages - 1 and len(all_results) < num_results_to_fetch:
                time.sleep(0.5)
        except requests.exceptions.RequestException as e:
            status_message.error(f"Error calling Serper API on page {page + 1}: {e}")
            break

    status_message.empty()
    return all_results[:num_results_to_fetch]


def _export_selected(selected_rows, base_query_for_name: str, folder_name: str):
    if not selected_rows:
        st.warning("No items selected.")
        return
    project_dir = _safe_project_dir()
    export_dir = os.path.join(project_dir, "exports", folder_name)
    os.makedirs(export_dir, exist_ok=True)
    out_df = pd.DataFrame(selected_rows)
    out_path = os.path.join(export_dir, f"{_safe_filename_from_query(base_query_for_name)}_selected.csv")
    try:
        out_df.to_csv(out_path, index=False)
        st.success(f"Saved {len(out_df)} selected rows to:\n`{out_path}`")
    except Exception as e:
        st.error(f"Error saving CSV: {e}")

def _ensure_scrape_run_dirs(base_query_for_name: str, folder_name: str):
    """
    Deprecated in favor of CLI-like run dirs. Kept for backward compat.
    """
    project_dir = _safe_project_dir()
    export_dir = os.path.join(project_dir, "exports", folder_name or "my_search_exports")
    os.makedirs(export_dir, exist_ok=True)
    csv_name = f"{_safe_filename_from_query(base_query_for_name)}_scraped.csv"
    csv_path = os.path.join(export_dir, csv_name)
    download_dir = os.path.join(export_dir, f"{_safe_filename_from_query(base_query_for_name)}_downloads")
    os.makedirs(download_dir, exist_ok=True)
    return csv_path, download_dir

def _append_scraped_rows(csv_path: str, rows: list):
    """Append scraped rows to a CSV, creating it with header if needed."""
    if not rows:
        return
    fieldnames = ["original_url", "base_url", "name", "emails", "phones", "masked_phones", "cv_url", "pages_crawled", "crawled_urls", "all_emails", "all_phones", "all_masked_phones"]
    file_exists = os.path.exists(csv_path)
    try:
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
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
    except Exception as e:
        st.error(f"Error appending to CSV: {e}")

def _init_scrape_run_like_cli(base_query_for_name: str):
    """Mirror CLI workflow: ./scraped/scraped_run_<timestamp>/scraped_data_<date>.csv and downloaded_cvs."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    date_only = timestamp.split("_")[0]
    base_dir = scraper.BASE_EXPORTS_DIR
    os.makedirs(base_dir, exist_ok=True)
    run_dir = os.path.join(base_dir, f"scraped_run_{timestamp}")
    os.makedirs(run_dir, exist_ok=True)
    csv_path = os.path.join(run_dir, f"scraped_data_{date_only}.csv")
    download_dir = os.path.join(run_dir, "downloaded_cvs")
    os.makedirs(download_dir, exist_ok=True)
    scraper.CURRENT_RUN_DIR = run_dir
    scraper.CURRENT_DOWNLOAD_DIR = download_dir
    st.session_state["adv_scrape_run_dir"] = run_dir
    st.session_state["adv_scrape_download_dir"] = download_dir
    st.session_state["adv_scrape_csv_path"] = csv_path
    return csv_path, download_dir

def display_csv_viewer():
    st.markdown("## View Exported CSVs")
    project_dir = _safe_project_dir()
    exports_dir = os.path.join(project_dir, "exports")

    if os.path.isdir(exports_dir):
        folders = [f for f in os.listdir(exports_dir) if os.path.isdir(os.path.join(exports_dir, f))]
        if folders:
            selected_folder = st.selectbox("Select export folder", folders, key="viewer_folder")
            folder_path = os.path.join(exports_dir, selected_folder)
            csv_files = [f for f in os.listdir(folder_path) if f.endswith(".csv")]
            if csv_files:
                selected_csv = st.selectbox("Select CSV file", csv_files, key="viewer_csv")
                csv_path = os.path.join(folder_path, selected_csv)
                try:
                    df_csv = pd.read_csv(csv_path)
                    st.success(f"Showing: `{csv_path}`")
                    st.dataframe(df_csv, use_container_width=True)
                except Exception as e:
                    st.error(f"Error reading CSV: {e}")
            else:
                st.info("No CSV files found in this folder.")
        else:
            st.info("No export folders found in ./exports/.")
    else:
        st.info("No exports directory found yet. Save some results first.")


st.markdown("### Mode")
mode = st.radio(
    "Choose a tool:",
    options=["Simple", "Advanced"],
    horizontal=True,
    index=1, 
)

# st.divider()


def advanced_ui():
    st.sidebar.header("Advanced Search Controls")

    default_query = '("backend developer") AND (CV OR resume OR portfolio) AND Nepal'
    base_query = st.sidebar.text_area("Base query", value=default_query, height=200, key="adv_base_query")

    num_results_to_fetch = st.sidebar.number_input(
        "Target results", min_value=10, max_value=1000, value=10, step=10, key="adv_num_results"
    )

    col_loc1, col_loc2 = st.sidebar.columns(2)
    with col_loc1:
        gl = st.text_input("gl (country)", value=DEFAULT_GL, help="Country code (e.g., np, in, us)", key="adv_gl")
    with col_loc2:
        hl = st.text_input("hl (lang)", value=DEFAULT_HL, help="Language (e.g., en, ne)", key="adv_hl")

    location = st.sidebar.text_input("location", value=DEFAULT_LOCATION, help='E.g., "Kathmandu, Nepal"', key="adv_location")

    tbs = st.sidebar.selectbox(
        "Time filter (tbs)",
        options=[None, "qdr:d", "qdr:w", "qdr:m", "qdr:y"],
        index=0,
        help="Optional recency filter: day/week/month/year",
        key="adv_tbs"
    )

    max_pages_per_query = st.sidebar.slider("Max pages per variant", min_value=1, max_value=10, value=5, key="adv_max_pages")
    polite_delay = st.sidebar.slider("Delay between pages (s)", min_value=0.0, max_value=2.0, value=0.4, key="adv_delay")

    st.sidebar.markdown("**Variant Toggles**")
    enable_site_variants = st.sidebar.checkbox("Include site: variants", value=True, key="adv_site_variants")
    enable_filetype_variants = st.sidebar.checkbox("Include filetype: variants", value=True, key="adv_filetype_variants")
    enable_intitle_inurl_variants = st.sidebar.checkbox("Include intitle:/inurl:", value=True, key="adv_intitle_inurl")
    role_synonyms_enabled = st.sidebar.checkbox("Include role synonyms", value=True, key="adv_role_syn")

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Scraping Settings**")
    crawl_depth = st.sidebar.slider("Crawl Depth", min_value=1, max_value=15, value=10, 
                                   help="How deep to crawl websites (higher = more thorough but slower)")
    
    st.sidebar.markdown("---")
    st.sidebar.caption("Powered by Serper API • Remember to set SERPER_API_KEY in your environment.")

    run_search = st.button("Run Advanced Search", type="primary", key="adv_run_search")

    if run_search:
        if not SERPER_API_KEY:
            st.error("SERPER_API_KEY not found. Create a .env with SERPER_API_KEY=your_key and restart.")
        else:
            with st.spinner(f"Fetching up to {num_results_to_fetch} results…"):
                data = get_many_google_results(
                    base_query=base_query,
                    num_results=num_results_to_fetch,
                    gl=gl or None,
                    hl=hl or None,
                    location=location or None,
                    tbs=tbs,
                    max_pages_per_query=max_pages_per_query,
                    polite_delay=polite_delay,
                    enable_site_variants=enable_site_variants,
                    enable_filetype_variants=enable_filetype_variants,
                    enable_intitle_inurl_variants=enable_intitle_inurl_variants,
                    role_synonyms_enabled=role_synonyms_enabled,
                )
            st.session_state["advanced_search_data"] = data
            st.session_state["advanced_query_for_name"] = base_query
            # reset scraped cache for a fresh run
            st.session_state["advanced_scraped_results"] = {}
            st.session_state["advanced_scraped_accumulator"] = []

    if "advanced_search_data" in st.session_state and st.session_state["advanced_search_data"]:
        results = st.session_state["advanced_search_data"]

        df = pd.DataFrame(results)
        total_found = len(df)
        df_view = df[df["link"].notna()].copy()


        st.subheader(f"Search Results ({len(df_view)}/{total_found} usable links)")
        st.dataframe(df_view[["title", "link", "snippet", "query_variant"]], use_container_width=True, height=480)

        # Download all results
        st.markdown("### Download All Results")
        csv_all = df_view.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download CSV (ALL without Filter)",
            data=csv_all,
            file_name=f"{_safe_filename_from_query(st.session_state.get('advanced_query_for_name','advanced'))}_results.csv",
            mime="text/csv",
            key="adv_download_all"
        )

        st.markdown("---")

        st.markdown("### Item Selection & Scraping")

        # Initialize selection state
        if "advanced_selected_items" not in st.session_state:
            st.session_state["advanced_selected_items"] = {row["link"]: True for _, row in df_view.iterrows()}
        else:
            for _, row in df_view.iterrows():
                if row["link"] not in st.session_state["advanced_selected_items"]:
                    st.session_state["advanced_selected_items"][row["link"]] = True

        # Bulk controls
        c1, c2, c3 = st.columns([1,1,3])
        with c1:
            if st.button("✅ Select All", key="adv_select_all"):
                for lk in st.session_state["advanced_selected_items"].keys():
                    st.session_state["advanced_selected_items"][lk] = True
        with c2:
            if st.button("❌ Deselect All", key="adv_deselect_all"):
                for lk in st.session_state["advanced_selected_items"].keys():
                    st.session_state["advanced_selected_items"][lk] = False
        with c3:
            selected_count = sum(1 for v in st.session_state["advanced_selected_items"].values() if v)
            st.metric("Items Selected", selected_count)

        st.caption("Toggle individual items below:")
        st.divider()

        # Initialize CLI-like scrape run directory once
        if "adv_scrape_csv_path" not in st.session_state:
            _init_scrape_run_like_cli(st.session_state.get('advanced_query_for_name','advanced'))
        csv_path = st.session_state.get("adv_scrape_csv_path")
        download_dir = st.session_state.get("adv_scrape_download_dir")
        if download_dir:
            scraper.CURRENT_DOWNLOAD_DIR = download_dir

        if "advanced_scraped_results" not in st.session_state:
            st.session_state["advanced_scraped_results"] = {}

        # Batch scraping action
        st.markdown("#### Batch Scraping")
        if st.button("Scrape All Selected Items", key="adv_scrape_all", type="secondary"):
            selectable_links = [row["link"] for _, row in df_view.iterrows() if st.session_state["advanced_selected_items"].get(row["link"], False)]
            if not selectable_links:
                st.warning("No items selected to scrape.")
            else:
                prog = st.progress(0)
                done = 0
                total = len(selectable_links)
                with st.spinner("Scraping selected items…"):
                    batch_rows = []
                    for lk in selectable_links:
                        try:
                            res = scraper.process_single_url(lk, max_depth=crawl_depth)
                            st.session_state["advanced_scraped_results"][lk] = {"data": res, "error": None}
                            if res:
                                batch_rows.append(res)
                        except Exception as e:
                            st.session_state["advanced_scraped_results"][lk] = {"data": None, "error": str(e)}
                        done += 1
                        prog.progress(min(done/total, 1.0))
                if batch_rows:
                    # accumulate instead of writing immediately
                    if "advanced_scraped_accumulator" not in st.session_state:
                        st.session_state["advanced_scraped_accumulator"] = []
                    st.session_state["advanced_scraped_accumulator"].extend(batch_rows)
                    st.success(f"✅ Added {len(batch_rows)} scraped rows to your basket!")

        st.markdown("---")

      
        st.markdown("### Individual Item Review")
        st.caption("Review each item, select/deselect, and scrape individually if needed")

        selected_rows = []
        for i, row in df_view.iterrows():
            link = row["link"]
            title = row.get("title") or "No Title"
            snippet = row.get("snippet") or ""

            # Item header and selection
            checked = st.checkbox(
                f"**{i+1}. {title}**",
                value=st.session_state["advanced_selected_items"].get(link, True),
                key=f"adv_chk_{i}"
            )
            st.markdown(f"*{snippet}*")
            st.markdown(f"[{link}]({link})")
            st.markdown(f"<sub><code>{row.get('query_variant','')}</code></sub>", unsafe_allow_html=True)

            st.session_state["advanced_selected_items"][link] = checked
            if checked:
                selected_rows.append(row)

            # Scraping controls
            col_scrape, col_add, col_status = st.columns([1, 1, 3])
            with col_scrape:
                if st.button("Scrape", key=f"adv_scrape_{i}", type="primary"):
                    with st.spinner("Scraping…"):
                        try:
                            res = scraper.process_single_url(link, max_depth=crawl_depth)
                            st.session_state["advanced_scraped_results"][link] = {"data": res, "error": None}
                        except Exception as e:
                            st.session_state["advanced_scraped_results"][link] = {"data": None, "error": str(e)}
            
            with col_add:
                has_data = bool(st.session_state["advanced_scraped_results"].get(link, {}).get("data"))
                if has_data:
                    if st.button("Add to Basket", key=f"adv_addcsv_{i}", type="primary"):
                        if "advanced_scraped_accumulator" not in st.session_state:
                            st.session_state["advanced_scraped_accumulator"] = []
                        st.session_state["advanced_scraped_accumulator"].append(st.session_state["advanced_scraped_results"][link]["data"])
                        st.success("✅ Added to basket!")

            # Display scraped results
            res_state = st.session_state["advanced_scraped_results"].get(link)
            if res_state:
                data = res_state.get("data")
                err = res_state.get("error")
                if err:
                    st.error(f"❌ Scrape error: {err}")
                elif data:
                    name = data.get("name") or "-"
                    emails = data.get("emails", [])
                    phones = data.get("phones", [])
                    masked_phones = data.get("masked_phones", [])
                    cv_url = data.get("cv_url") or "-"
                    pages_crawled = data.get("pages_crawled", 0)
                    crawled_urls = data.get("crawled_urls", [])
                    
                    # Display in a nice format
                    st.markdown("**Scraped Data:**")
                    col_name, col_pages = st.columns([2, 1])
                    col_name.write(f"**Name:** {name}")
                    col_pages.write(f"**Pages Crawled:** {pages_crawled}")
                    
                    # Replace expander with a regular button for name editing
                    if "edit_name_active_{link}" not in st.session_state:
                        st.session_state[f"edit_name_active_{link}"] = False
                        
                    if st.button("✏️ Edit Name", key=f"toggle_edit_name_{link}"):
                        st.session_state[f"edit_name_active_{link}"] = not st.session_state[f"edit_name_active_{link}"]
                        
                    if st.session_state[f"edit_name_active_{link}"]:
                        manual_name = st.text_input("Enter/edit name:", value=name if name and name != "-" else "", key=f"manual_name_{link}")
                        if st.button("Update Name in Basket", key=f"update_manual_name_{link}"):
                            if manual_name and len(manual_name.strip()) > 0:
                                if "advanced_scraped_accumulator" not in st.session_state:
                                    st.session_state["advanced_scraped_accumulator"] = []
                                
                                # Check if an entry with this URL already exists in the basket
                                original_url = data.get("original_url", "")
                                existing_entry_index = None
                                for idx, entry in enumerate(st.session_state["advanced_scraped_accumulator"]):
                                    if entry.get("original_url") == original_url:
                                        existing_entry_index = idx
                                        break
                                
                                if existing_entry_index is not None:
                                    # Update existing entry with the name
                                    existing_entry = st.session_state["advanced_scraped_accumulator"][existing_entry_index]
                                    existing_entry["name"] = manual_name.strip()
                                    st.session_state["advanced_scraped_accumulator"][existing_entry_index] = existing_entry
                                else:
                                    # Create a new entry
                                    new_entry = {
                                        "original_url": original_url,
                                        "base_url": data.get("base_url", ""),
                                        "name": manual_name.strip(),
                                        "emails": [],
                                        "phones": [],
                                        "masked_phones": [],
                                        "cv_url": data.get("cv_url", ""),
                                        "pages_crawled": data.get("pages_crawled", 0),
                                        "all_emails": "",
                                        "all_phones": "",
                                        "all_masked_phones": ""
                                    }
                                    st.session_state["advanced_scraped_accumulator"].append(new_entry)
                                st.success(f"✅ Added/updated name to: {manual_name}")
                                # Close the editor after success
                                st.session_state[f"edit_name_active_{link}"] = False
                                st.rerun()
                            else:
                                st.error("Please enter a valid name")
                    
                    # Display crawled URLs (collapsed by default)
                    if crawled_urls:
                        with st.expander("📋 Crawled URLs", expanded=False):
                            for i, url in enumerate(crawled_urls, 1):
                                st.markdown(f"  {i}. [{url}]({url})")
                    
                    # Display emails with individual add buttons
                    if emails:
                        st.markdown("**Emails:**")
                        for i, email in enumerate(emails, 1):
                            col_email, col_add_email = st.columns([3, 1])
                            with col_email:
                                st.markdown(f"  {i}. {email}")
                            with col_add_email:
                                if st.button("➕", key=f"add_email_{i}_{link}", help=f"Add {email} to basket"):
                                    if "advanced_scraped_accumulator" not in st.session_state:
                                        st.session_state["advanced_scraped_accumulator"] = []
                                    
                                    # Check if an entry with this URL already exists in the basket
                                    original_url = data.get("original_url", "")
                                    existing_entry_index = None
                                    for idx, entry in enumerate(st.session_state["advanced_scraped_accumulator"]):
                                        if entry.get("original_url") == original_url:
                                            existing_entry_index = idx
                                            break
                                    
                                    if existing_entry_index is not None:
                                        # Update existing entry
                                        existing_entry = st.session_state["advanced_scraped_accumulator"][existing_entry_index]
                                        if email not in existing_entry.get("emails", []):
                                            existing_entry.setdefault("emails", []).append(email)
                                            existing_entry["all_emails"] = "; ".join(existing_entry["emails"])
                                        st.session_state["advanced_scraped_accumulator"][existing_entry_index] = existing_entry
                                    else:
                                        # Create a new entry
                                        new_entry = {
                                            "original_url": original_url,
                                            "base_url": data.get("base_url", ""),
                                            "name": data.get("name", ""),
                                            "emails": [email],
                                            "phones": [],
                                            "masked_phones": [],
                                            "cv_url": data.get("cv_url", ""),
                                            "pages_crawled": data.get("pages_crawled", 0),
                                            "all_emails": email,
                                            "all_phones": "",
                                            "all_masked_phones": ""
                                        }
                                        st.session_state["advanced_scraped_accumulator"].append(new_entry)
                                    st.success(f"✅ Added {email} to basket!")
                    else:
                        st.markdown("**Emails:** None found")
                    
                    # Add manual email input - show regardless if emails were found or not
                    # Replace expander with a regular button for manual email
                    if f"add_email_active_{link}" not in st.session_state:
                        st.session_state[f"add_email_active_{link}"] = False
                        
                    # Initialize manually added emails for display
                    if f"manual_emails_{link}" not in st.session_state:
                        st.session_state[f"manual_emails_{link}"] = []
                        
                        # Check if there are already emails for this URL in the basket
                        original_url = data.get("original_url", "")
                        for entry in st.session_state.get("advanced_scraped_accumulator", []):
                            if entry.get("original_url") == original_url and entry.get("emails"):
                                st.session_state[f"manual_emails_{link}"] = entry.get("emails", [])
                                break
                    
                    # Display any manually added emails
                    if st.session_state[f"manual_emails_{link}"]:
                        st.markdown("**Manually Added Emails:**")
                        for i, email in enumerate(st.session_state[f"manual_emails_{link}"], 1):
                            st.markdown(f"  {i}. {email}")
                    
                    if st.button("➕ Add Email Manually", key=f"toggle_add_email_{link}"):
                        st.session_state[f"add_email_active_{link}"] = not st.session_state[f"add_email_active_{link}"]
                        
                    if st.session_state[f"add_email_active_{link}"]:
                        manual_email = st.text_input("Enter email address:", key=f"manual_email_{link}")
                        if st.button("Add Email to Basket", key=f"add_manual_email_{link}"):
                            if manual_email and '@' in manual_email:
                                if "advanced_scraped_accumulator" not in st.session_state:
                                    st.session_state["advanced_scraped_accumulator"] = []
                                
                                # Check if an entry with this URL already exists in the basket
                                original_url = data.get("original_url", "")
                                existing_entry_index = None
                                for idx, entry in enumerate(st.session_state["advanced_scraped_accumulator"]):
                                    if entry.get("original_url") == original_url:
                                        existing_entry_index = idx
                                        break
                                
                                if existing_entry_index is not None:
                                    # Update existing entry
                                    existing_entry = st.session_state["advanced_scraped_accumulator"][existing_entry_index]
                                    if manual_email not in existing_entry.get("emails", []):
                                        existing_entry.setdefault("emails", []).append(manual_email)
                                        existing_entry["all_emails"] = "; ".join(existing_entry["emails"])
                                    st.session_state["advanced_scraped_accumulator"][existing_entry_index] = existing_entry
                                else:
                                    # Create a new entry
                                    new_entry = {
                                        "original_url": original_url,
                                        "base_url": data.get("base_url", ""),
                                        "name": data.get("name", ""),
                                        "emails": [manual_email],
                                        "phones": [],
                                        "masked_phones": [],
                                        "cv_url": data.get("cv_url", ""),
                                        "pages_crawled": data.get("pages_crawled", 0),
                                        "all_emails": manual_email,
                                        "all_phones": "",
                                        "all_masked_phones": ""
                                    }
                                    st.session_state["advanced_scraped_accumulator"].append(new_entry)
                                    
                                # Update the displayed emails list
                                if manual_email not in st.session_state[f"manual_emails_{link}"]:
                                    st.session_state[f"manual_emails_{link}"].append(manual_email)
                                    
                                st.success(f"✅ Added {manual_email} to basket!")
                                # Close the editor after success
                                st.session_state[f"add_email_active_{link}"] = False
                                st.rerun()
                            else:
                                st.error("Please enter a valid email address")
                    
                    # Display phones with individual add buttons
                    if phones:
                        st.markdown("**Phone Numbers:**")
                        for i, phone in enumerate(phones, 1):
                            col_phone, col_add_phone = st.columns([3, 1])
                            with col_phone:
                                st.markdown(f"  {i}. {phone}")
                            with col_add_phone:
                                if st.button("➕", key=f"add_phone_{i}_{link}", help=f"Add {phone} to basket"):
                                    if "advanced_scraped_accumulator" not in st.session_state:
                                        st.session_state["advanced_scraped_accumulator"] = []
                                    
                                    # Check if an entry with this URL already exists in the basket
                                    original_url = data.get("original_url", "")
                                    existing_entry_index = None
                                    for idx, entry in enumerate(st.session_state["advanced_scraped_accumulator"]):
                                        if entry.get("original_url") == original_url:
                                            existing_entry_index = idx
                                            break
                                    
                                    if existing_entry_index is not None:
                                        # Update existing entry
                                        existing_entry = st.session_state["advanced_scraped_accumulator"][existing_entry_index]
                                        if phone not in existing_entry.get("phones", []):
                                            existing_entry.setdefault("phones", []).append(phone)
                                            existing_entry["all_phones"] = "; ".join(existing_entry["phones"])
                                        st.session_state["advanced_scraped_accumulator"][existing_entry_index] = existing_entry
                                    else:
                                        # Create a new entry
                                        new_entry = {
                                            "original_url": original_url,
                                            "base_url": data.get("base_url", ""),
                                            "name": data.get("name", ""),
                                            "emails": [],
                                            "phones": [phone],
                                            "masked_phones": [],
                                            "cv_url": data.get("cv_url", ""),
                                            "pages_crawled": data.get("pages_crawled", 0),
                                            "all_emails": "",
                                            "all_phones": phone,
                                            "all_masked_phones": ""
                                        }
                                        st.session_state["advanced_scraped_accumulator"].append(new_entry)
                                    st.success(f"✅ Added {phone} to basket!")
                    else:
                        st.markdown("**Phone Numbers:** None found")
                    
                    # Add manual phone input - show regardless if phones were found or not
                    # Replace expander with a regular button for manual phone
                    if f"add_phone_active_{link}" not in st.session_state:
                        st.session_state[f"add_phone_active_{link}"] = False
                    
                    # Initialize manually added phones for display
                    if f"manual_phones_{link}" not in st.session_state:
                        st.session_state[f"manual_phones_{link}"] = []
                        
                        # Check if there are already phones for this URL in the basket
                        original_url = data.get("original_url", "")
                        for entry in st.session_state.get("advanced_scraped_accumulator", []):
                            if entry.get("original_url") == original_url and entry.get("phones"):
                                st.session_state[f"manual_phones_{link}"] = entry.get("phones", [])
                                break
                    
                    # Display any manually added phones
                    if st.session_state[f"manual_phones_{link}"]:
                        st.markdown("**Manually Added Phone Numbers:**")
                        for i, phone in enumerate(st.session_state[f"manual_phones_{link}"], 1):
                            st.markdown(f"  {i}. {phone}")
                        
                    if st.button("➕ Add Phone Number Manually", key=f"toggle_add_phone_{link}"):
                        st.session_state[f"add_phone_active_{link}"] = not st.session_state[f"add_phone_active_{link}"]
                        
                    if st.session_state[f"add_phone_active_{link}"]:
                        manual_phone = st.text_input("Enter phone number:", key=f"manual_phone_{link}")
                        if st.button("Add Phone to Basket", key=f"add_manual_phone_{link}"):
                            if manual_phone and len(manual_phone) >= 10:
                                if "advanced_scraped_accumulator" not in st.session_state:
                                    st.session_state["advanced_scraped_accumulator"] = []
                                
                                # Check if an entry with this URL already exists in the basket
                                original_url = data.get("original_url", "")
                                existing_entry_index = None
                                for idx, entry in enumerate(st.session_state["advanced_scraped_accumulator"]):
                                    if entry.get("original_url") == original_url:
                                        existing_entry_index = idx
                                        break
                                
                                if existing_entry_index is not None:
                                    # Update existing entry
                                    existing_entry = st.session_state["advanced_scraped_accumulator"][existing_entry_index]
                                    if manual_phone not in existing_entry.get("phones", []):
                                        existing_entry.setdefault("phones", []).append(manual_phone)
                                        existing_entry["all_phones"] = "; ".join(existing_entry["phones"])
                                    st.session_state["advanced_scraped_accumulator"][existing_entry_index] = existing_entry
                                else:
                                    # Create a new entry
                                    new_entry = {
                                        "original_url": original_url,
                                        "base_url": data.get("base_url", ""),
                                        "name": data.get("name", ""),
                                        "emails": [],
                                        "phones": [manual_phone],
                                        "masked_phones": [],
                                        "cv_url": data.get("cv_url", ""),
                                        "pages_crawled": data.get("pages_crawled", 0),
                                        "all_emails": "",
                                        "all_phones": manual_phone,
                                        "all_masked_phones": ""
                                    }
                                    st.session_state["advanced_scraped_accumulator"].append(new_entry)
                                
                                # Update the displayed phones list
                                if manual_phone not in st.session_state[f"manual_phones_{link}"]:
                                    st.session_state[f"manual_phones_{link}"].append(manual_phone)
                                    
                                st.success(f"✅ Added {manual_phone} to basket!")
                                # Close the editor after success
                                st.session_state[f"add_phone_active_{link}"] = False
                                st.rerun()
                            else:
                                st.error("Please enter a valid phone number")
                    
                    # Display masked phones with individual add buttons
                    if masked_phones:
                        st.markdown("**Masked Phone Numbers (Privacy Protected):**")
                        for i, phone in enumerate(masked_phones, 1):
                            col_masked_phone, col_add_masked_phone = st.columns([3, 1])
                            with col_masked_phone:
                                st.markdown(f"  {i}. {phone}")
                            with col_add_masked_phone:
                                if st.button("➕", key=f"add_masked_phone_{i}_{link}", help=f"Add {phone} to basket"):
                                    if "advanced_scraped_accumulator" not in st.session_state:
                                        st.session_state["advanced_scraped_accumulator"] = []
                                    
                                    # Check if an entry with this URL already exists in the basket
                                    original_url = data.get("original_url", "")
                                    existing_entry_index = None
                                    for idx, entry in enumerate(st.session_state["advanced_scraped_accumulator"]):
                                        if entry.get("original_url") == original_url:
                                            existing_entry_index = idx
                                            break
                                    
                                    if existing_entry_index is not None:
                                        # Update existing entry
                                        existing_entry = st.session_state["advanced_scraped_accumulator"][existing_entry_index]
                                        if phone not in existing_entry.get("masked_phones", []):
                                            existing_entry.setdefault("masked_phones", []).append(phone)
                                            existing_entry["all_masked_phones"] = "; ".join(existing_entry["masked_phones"])
                                        st.session_state["advanced_scraped_accumulator"][existing_entry_index] = existing_entry
                                    else:
                                        # Create a new entry
                                        new_entry = {
                                            "original_url": original_url,
                                            "base_url": data.get("base_url", ""),
                                            "name": data.get("name", ""),
                                            "emails": [],
                                            "phones": [],
                                            "masked_phones": [phone],
                                            "cv_url": data.get("cv_url", ""),
                                            "pages_crawled": data.get("pages_crawled", 0),
                                            "all_emails": "",
                                            "all_phones": "",
                                            "all_masked_phones": phone
                                        }
                                        st.session_state["advanced_scraped_accumulator"].append(new_entry)
                                    st.success(f"✅ Added {phone} to basket!")
                    else:
                        st.markdown("**Masked Phone Numbers:** None found")
                    
                    # Add "Add All to Basket" button if any contacts found
                    total_contacts = len(emails) + len(phones) + len(masked_phones)
                    # if total_contacts > 0:
                    #     st.markdown("---")
                    #     if st.button("📥 Add All Contacts to Basket", key=f"add_all_{link}", type="primary"):
                    #         if "advanced_scraped_accumulator" not in st.session_state:
                    #             st.session_state["advanced_scraped_accumulator"] = []
                            
                    #         # Create a comprehensive entry with all contacts
                    #         new_entry = {
                    #             "original_url": data.get("original_url", ""),
                    #             "base_url": data.get("base_url", ""),
                    #             "name": data.get("name", ""),
                    #             "emails": emails,
                    #             "phones": phones,
                    #             "masked_phones": masked_phones,
                    #             "cv_url": data.get("cv_url", ""),
                    #             "pages_crawled": data.get("pages_crawled", 0),
                    #             "all_emails": "; ".join(emails),
                    #             "all_phones": "; ".join(phones),
                    #             "all_masked_phones": "; ".join(masked_phones)
                    #         }
                    #         st.session_state["advanced_scraped_accumulator"].append(new_entry)
                    #         st.success(f"✅ Added all {total_contacts} contacts to basket!")
                    
                    if cv_url and cv_url != "-":
                        col_cv, col_dl = st.columns([2,1])
                        with col_cv:
                            st.markdown(f"📄 **CV:** [{cv_url}]({cv_url})")
                        with col_dl:
                            import requests
                            try:
                                response = requests.get(cv_url, timeout=15)
                                if response.status_code == 200:
                                    st.download_button(
                                        label="Download CV",
                                        data=response.content,
                                        file_name=cv_url.split("/")[-1],
                                        mime="application/pdf",
                                        key=f"download_cv_{cv_url}"
                                    )
                                else:
                                    st.caption("CV not downloadable")
                            except Exception:
                                st.caption("CV not downloadable")
                    else:
                        st.markdown("**No CV**")

            st.markdown("---")
   
        st.markdown("### Data Export & Download")

        # Scraped data basket
        basket = st.session_state.get("advanced_scraped_accumulator", [])
        st.markdown("#### Scraped Data Basket")
        st.info(f"Items in basket: **{len(basket)}** scraped profiles")
        
        if basket:
            # Show basket summary
            df_basket = pd.DataFrame(basket)
            st.markdown("**Basket Contents (Editable):**")
            
            # Prepare display columns - show all_emails and all_phones for better readability
            display_columns = ["name", "all_emails", "all_phones", "cv_url"]
            available_columns = [col for col in display_columns if col in df_basket.columns]
            
            edited_df = st.data_editor(
                df_basket[available_columns],
                use_container_width=True,
                height=500,
                num_rows="dynamic",
                key="basket_editor"
            )

            # Download button uses edited_df
            csv_bytes = edited_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Download Scraped Data as CSV",
                data=csv_bytes,
                file_name=f"{_safe_filename_from_query(st.session_state.get('advanced_query_for_name','advanced'))}_scraped_data.csv",
                mime="text/csv",
                key="adv_download_scraped",
                type="primary"
            )

            # Clear basket option
            if st.button("🗑️ Clear Basket", key="adv_clear_basket", type="secondary"):
                st.session_state["advanced_scraped_accumulator"] = []
                st.rerun()
        else:
            st.info("No scraped data in basket yet. Use individual scraping or batch scraping to add items.")

        st.markdown("---")

        with st.expander("🔧 Developer Export (Legacy)", expanded=False):
            st.info("This is for developer use only")
            folder_name = st.text_input("Folder name under ./exports/", value="my_search_exports", key="adv_folder_name")
            if st.button("Save Selected as CSV", key="adv_save_selected"):
                _export_selected(selected_rows, st.session_state.get('advanced_query_for_name','advanced'), folder_name)

def simple_ui():
    st.markdown("This is the quick extractor: paginate Serper and export or review selected items.")

    st.markdown("---")
    st.header("1. Enter Search Query")
    search_query = st.text_input("Enter your search query:", placeholder="e.g., 'best AI tools 2025'", key="simple_query")

    col1, col2 = st.columns([1, 2])
    with col1:
        num_results_input_str = st.text_input("Number of results to fetch (10-500):", value="100", key="simple_num_input")
        try:
            num_results_to_fetch = int(num_results_input_str)
            if not (10 <= num_results_to_fetch <= 500):
                st.warning("Please enter a number between 10 and 500.")
                num_results_to_fetch = 100
        except ValueError:
            st.warning("Please enter a valid integer for number of results.")
            num_results_to_fetch = 100

    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Search Google (Simple)", type="primary", key="simple_run"):
            if not SERPER_API_KEY:
                st.error("SERPER_API_KEY not found in .env file. Please set it up.")
            elif search_query:
                with st.spinner(f"Fetching up to {num_results_to_fetch} search results…"):
                    data = get_google_search_results_simple(search_query, num_results_to_fetch)
                    st.session_state['simple_search_data'] = data
                    st.session_state['simple_selected_items'] = {item['link']: True for item in data if item.get('link')}
                    st.session_state['simple_query_for_name'] = search_query
                    if data:
                        st.success(f"Successfully fetched {len(data)} results.")
                    else:
                        st.warning("No results found for your query.")
            else:
                st.warning("Please enter a search query before searching.")

    if 'simple_search_data' in st.session_state and st.session_state['simple_search_data']:
        data = st.session_state['simple_search_data']
        qname = st.session_state.get('simple_query_for_name', 'simple')

        st.markdown("---")
        st.header(f"2. Results for '{qname}' ({len(data)} found)")

    
        st.subheader("Download All Found Data")
        df_full = pd.DataFrame(data)
        col_dl_all, _ = st.columns([2, 5])
        with col_dl_all:
            csv_full_file = df_full.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download All Results as CSV",
                data=csv_full_file,
                file_name=f"{_safe_filename_from_query(qname)}_all_results.csv",
                mime="text/csv",
                help="Download a CSV containing all fetched links, titles, and snippets.",
                key="simple_download_all"
            )

        st.markdown("---")
        st.header("3. Review and Select Specific Items to Save")

        # Bulk selection form
        with st.form("simple_bulk_selection_form"):
            col_select_all, col_deselect_all, col_selected_count = st.columns([1, 1, 3])
            with col_select_all:
                if st.form_submit_button("✅ Select All", use_container_width=True):
                    st.session_state['simple_selected_items'] = {link: True for link in st.session_state['simple_selected_items']}
            with col_deselect_all:
                if st.form_submit_button("❌ Deselect All", use_container_width=True):
                    st.session_state['simple_selected_items'] = {link: False for link in st.session_state['simple_selected_items']}
            with col_selected_count:
                selected_count = sum(1 for v in st.session_state['simple_selected_items'].values() if v)
                st.metric(label="Items Selected", value=selected_count)

        st.markdown("Use the checkboxes below to select the items you wish to save.")
        st.markdown("---")

        selected_data_for_export = []
        for i, item in enumerate(data):
            link = item.get('link')
            title = item.get('title', 'No Title')
            snippet = item.get('snippet', 'No snippet available.')
            if not link:
                continue

            st.session_state['simple_selected_items'][link] = st.checkbox(
                f"**{i+1}. {title}**",
                value=st.session_state['simple_selected_items'].get(link, True),
                key=f"simple_checkbox_{i}_{link}"
            )
            st.markdown(f"*{snippet}*")
            st.markdown(f"[{link}]({link})")
            st.markdown("---")

            if st.session_state['simple_selected_items'][link]:
                selected_data_for_export.append(item)

        st.subheader("Save Selected Items to a Folder")
        folder_name = st.text_input("Enter folder name to save CSV (e.g., 'my_search_exports'):", key="simple_folder_name")
        if st.button("Save Selected Items to CSV", type="secondary", key="simple_save_selected"):
            _export_selected(selected_data_for_export, qname, folder_name or "my_search_exports")


if mode == "Advanced":
    advanced_ui()
else:
    simple_ui()


st.markdown("---")
if st.button("View Saved Data", key="viewer_toggle"):
    st.session_state["show_csv_viewer"] = not st.session_state.get("show_csv_viewer", False)

if st.session_state.get("show_csv_viewer"):
    display_csv_viewer()
else:
    st.info("Tip: Use **View Saved Data** to browse CSVs you exported earlier.")
    st.info("Tip: Use **View Saved Data** to browse CSVs you exported earlier.")
