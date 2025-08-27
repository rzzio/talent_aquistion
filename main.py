import os
import time
import json
import requests
import pandas as pd
import streamlit as st
from urllib.parse import urlparse
from dotenv import load_dotenv


load_dotenv()
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
SERPER_URL = "https://google.serper.dev/search"
SERPER_HEADERS = {"X-API-KEY": SERPER_API_KEY or "", "Content-Type": "application/json"}

DEFAULT_GL = "np"
DEFAULT_HL = "en"
DEFAULT_LOCATION = "Kathmandu, Nepal"


st.set_page_config(layout="wide", page_title="Google Talent Sourcing (Serper)")

st.title("🔎 Talent Sourcing via Google (Serper)")
st.caption("Fan-out query variants to discover personal resumes/portfolios at scale. De-duplicate by URL and host for diversity.")


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


@st.cache_data(ttl=3600, show_spinner=False)
def get_many_google_results(
    base_query: str,
    num_results: int = 100,
    gl: str = DEFAULT_GL,
    hl: str = DEFAULT_HL,
    location: str = DEFAULT_LOCATION,
    tbs: str = None,           # e.g., "qdr:y" (last year) or "qdr:m" (last month)
    max_pages_per_query: int = 5,
    polite_delay: float = 0.4,
    enable_site_variants: bool = True,
    enable_filetype_variants: bool = True,
    enable_intitle_inurl_variants: bool = True,
    role_synonyms_enabled: bool = True,
):
    """
    Fan-out across multiple query variants, aggregate + dedupe by URL and host.
    Returns: list of dicts: {query_variant, link, title, snippet}
    """

    if not SERPER_API_KEY:
        return [{"error": "Missing SERPER_API_KEY in environment."}]

    geo = '(nepal OR kathmandu OR lalitpur OR bhaktapur OR pokhara OR biratnagar OR butwal)'

    role_variants = [
        '"backend developer"', '"backend engineer"', '"python developer"', '"node.js developer"',
        '"django developer"', '"express developer"', '"spring boot developer"'
    ] if role_synonyms_enabled else ['"backend developer"']

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

    # Start with user’s base query to respect input
    variants = [base_query.strip()]

    # Structured combinations: role + intent + geo
    for role in role_variants:
        for intent in intent_variants:
            variants.append(f'{role} {intent} {geo}')

    # Add intitle/inurl flavors
    for role in role_variants:
        for ii in intitle_inurl_variants:
            variants.append(f'{role} {ii} {geo}')

    # Add filetype flavors
    for role in role_variants:
        for ft in filetype_variants:
            variants.append(f'{role} {ft} {geo}')

    # Add site flavors (role + geo + site)
    for role in role_variants:
        for site in site_variants:
            variants.append(f'{role} {geo} {site}')

    # Deduplicate textual variants & keep order
    seen_v = set()
    clean_variants = []
    for v in variants:
        vv = " ".join(v.split())  # normalize spaces
        if vv and vv not in seen_v:
            clean_variants.append(vv)
            seen_v.add(vv)

    # --- Fan-out search ---
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
                # If a variant fails, continue to the next
                results.append({
                    "query_variant": q,
                    "link": None,
                    "title": f"[ERROR] {str(e)}",
                    "snippet": ""
                })
                break

            organic = data.get('organic', []) or []
            if not organic:
                # No more results for this variant
                break

            page_got_new = False
            for item in organic:
                link = item.get('link')
                if not link:
                    continue
                host = _host(link)
                # Dedup by exact URL and host (host-diversity for portfolios)
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

            # If nothing new on this page (likely duplicates), or the page has <10 organic items → stop paging this variant
            if not page_got_new or len(organic) < 10:
                break

            if polite_delay:
                time.sleep(polite_delay)

    status.empty()
    return results[:num_results]

# ----------------------------
# Sidebar controls
# ----------------------------
st.sidebar.header("🔧 Search Controls")

default_query = '("backend developer") AND (CV OR resume OR portfolio) AND Nepal'
base_query = st.sidebar.text_area("Base query", value=default_query, height=80)

num_results_to_fetch = st.sidebar.number_input("Target results", min_value=10, max_value=1000, value=100, step=10)

col_loc1, col_loc2 = st.sidebar.columns(2)
with col_loc1:
    gl = st.text_input("gl (country)", value=DEFAULT_GL, help="Country code (e.g., np, in, us)")
with col_loc2:
    hl = st.text_input("hl (lang)", value=DEFAULT_HL, help="Language (e.g., en, ne)")

location = st.sidebar.text_input("location", value=DEFAULT_LOCATION, help='E.g., "Kathmandu, Nepal"')

tbs = st.sidebar.selectbox(
    "Time filter (tbs)",
    options=[None, "qdr:d", "qdr:w", "qdr:m", "qdr:y"],
    index=0,
    help="Optional recency filter: day/week/month/year"
)

max_pages_per_query = st.sidebar.slider("Max pages per variant", min_value=1, max_value=10, value=5)
polite_delay = st.sidebar.slider("Delay between pages (s)", min_value=0.0, max_value=2.0, value=0.4)

st.sidebar.markdown("**Variant Toggles**")
enable_site_variants = st.sidebar.checkbox("Include site: variants", value=True)
enable_filetype_variants = st.sidebar.checkbox("Include filetype: variants", value=True)
enable_intitle_inurl_variants = st.sidebar.checkbox("Include intitle:/inurl:", value=True)
role_synonyms_enabled = st.sidebar.checkbox("Include role synonyms", value=True)

st.sidebar.markdown("---")
st.sidebar.caption("Powered by Serper API • Remember to set SERPER_API_KEY in your environment.")


run_search = st.button("🚀 Run Search", type="primary")


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
        st.session_state["search_data"] = data


if "search_data" in st.session_state and st.session_state["search_data"]:
    results = st.session_state["search_data"]

    # Filter out errors in view but keep count
    df = pd.DataFrame(results)
    total_found = len(df)
    df_view = df[df["link"].notna()].copy()

    st.subheader(f"Results ({len(df_view)}/{total_found} usable links)")
    st.dataframe(df_view[["title", "link", "snippet", "query_variant"]], use_container_width=True, height=480)

    # Download all
    st.markdown("### Download All")
    csv_all = df_view.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Download CSV (All Usable)",
        data=csv_all,
        file_name=f"{_safe_filename_from_query(base_query)}_results.csv",
        mime="text/csv"
    )

    st.markdown("---")
    st.markdown("### Review & Save Selected")


    if "selected_items" not in st.session_state:
        st.session_state["selected_items"] = {row["link"]: True for _, row in df_view.iterrows()}
    else:

        for _, row in df_view.iterrows():
            if row["link"] not in st.session_state["selected_items"]:
                st.session_state["selected_items"][row["link"]] = True

    c1, c2, c3 = st.columns([1,1,3])
    with c1:
        if st.button("✅ Select All"):
            for lk in st.session_state["selected_items"].keys():
                st.session_state["selected_items"][lk] = True
    with c2:
        if st.button("❌ Deselect All"):
            for lk in st.session_state["selected_items"].keys():
                st.session_state["selected_items"][lk] = False
    with c3:
        selected_count = sum(1 for v in st.session_state["selected_items"].values() if v)
        st.metric("Items Selected", selected_count)

    st.caption("Toggle individual items below:")
    st.divider()

    selected_rows = []
    for i, row in df_view.iterrows():
        link = row["link"]
        title = row.get("title") or "No Title"
        snippet = row.get("snippet") or ""

        checked = st.checkbox(f"**{i+1}. {title}**", value=st.session_state["selected_items"].get(link, True), key=f"chk_{i}")
        st.markdown(f"*{snippet}*")
        st.markdown(f"🔗 [{link}]({link})")
        st.markdown(f"<sub><code>{row.get('query_variant','')}</code></sub>", unsafe_allow_html=True)
        st.markdown("---")

        st.session_state["selected_items"][link] = checked
        if checked:
            selected_rows.append(row)

    st.markdown("#### Save Selected to a Folder")
    folder_name = st.text_input("Folder name under ./exports/", value="my_search_exports")
    if st.button("💾 Save Selected as CSV"):
        if not selected_rows:
            st.warning("No items selected.")
        else:
            project_dir = _safe_project_dir()
            export_dir = os.path.join(project_dir, "exports", folder_name)
            os.makedirs(export_dir, exist_ok=True)
            out_df = pd.DataFrame(selected_rows)
            out_path = os.path.join(export_dir, f"{_safe_filename_from_query(base_query)}_selected.csv")
            try:
                out_df.to_csv(out_path, index=False)
                st.success(f"Saved {len(out_df)} selected rows to:\n`{out_path}`")
            except Exception as e:
                st.error(f"Error saving CSV: {e}")

# Moved the CSV viewer logic into its own function for clarity
def display_csv_viewer():
    st.markdown("## 📂 View Exported CSVs")

    project_dir = _safe_project_dir()
    exports_dir = os.path.join(project_dir, "exports")

    if os.path.isdir(exports_dir):
        # List folders inside exports
        folders = [f for f in os.listdir(exports_dir) if os.path.isdir(os.path.join(exports_dir, f))]
        if folders:
            selected_folder = st.selectbox("Select export folder", folders)
            folder_path = os.path.join(exports_dir, selected_folder)
            # List CSV files in selected folder
            csv_files = [f for f in os.listdir(folder_path) if f.endswith(".csv")]
            if csv_files:
                selected_csv = st.selectbox("Select CSV file", csv_files)
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

# Add a button to show the CSV viewer
if st.button("📊 View Saved Data"):
    st.session_state["show_csv_viewer"] = not st.session_state.get("show_csv_viewer", False)

if st.session_state.get("show_csv_viewer"):
    display_csv_viewer()
else:
    st.info("Enter a base query in the sidebar and click **Run Search** to begin. Click 'View Saved Data' to see your exports.")