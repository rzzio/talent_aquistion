import streamlit as st
import requests
import os
from dotenv import load_dotenv
import pandas as pd
import time  # For introducing a small delay between API calls if needed

# Load environment variables
load_dotenv()
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

# --- Serper API Function ---
@st.cache_data(ttl=3600)  # Cache results for 1 hour to avoid redundant API calls for same query
def get_google_search_results(query, num_results_to_fetch=100):
    if not SERPER_API_KEY:
        st.error("SERPER_API_KEY not found in .env file. Please set it up.")
        return []

    url = "https://google.serper.dev/search"
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }

    all_results = []
    max_results_per_page = 10  # Serper API returns up to 10 results per request

    num_pages = (num_results_to_fetch + max_results_per_page - 1) // max_results_per_page
    
    status_message = st.empty() # Placeholder for status updates

    for page in range(num_pages):
        # Stop if we've already collected enough results
        if len(all_results) >= num_results_to_fetch:
            break

        payload = {
            "q": query,
            "page": page + 1  # Serper uses 'page' for pagination, starting from 1
        }

        try:
            status_message.info(f"Fetching page {page + 1}/{num_pages} (collected {len(all_results)}/{num_results_to_fetch} results so far)...")
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()  # Corrected: It's 'raise_for_status()'
            data = response.json()

            if 'organic' in data:
                for result in data['organic']:
                    all_results.append({
                        'link': result.get('link'),
                        'title': result.get('title'),
                        'snippet': result.get('snippet')
                    })

            # If Serper indicates no more results, or we've reached the end of available results
            if 'organic' not in data or len(data['organic']) < max_results_per_page:
                status_message.warning(f"Serper API returned fewer than requested results for page {page + 1} or no more results available. Stopping pagination.")
                break

            # Introduce a small delay between API calls to be polite and avoid rate limits
            if page < num_pages - 1 and len(all_results) < num_results_to_fetch:  # Don't delay after the last call or if we have enough
                time.sleep(0.5)  # Half-second delay

        except requests.exceptions.RequestException as e:
            status_message.error(f"Error calling Serper API on page {page + 1}: {e}")
            break  # Stop trying to fetch more if an error occurs
    
    status_message.empty() # Clear the status message once done
    return all_results[:num_results_to_fetch]  # Ensure we return exactly what was requested (or less if not available)

# --- Streamlit UI ---
st.set_page_config(layout="wide", page_title="Google Search Extractor")
st.title("🔗 Google Search Link Extractor & Reviewer")

st.markdown("""
This application allows you to search Google and extract result links, titles, and snippets.
You can specify the number of results, then save all found data or review and select them individually before saving to a CSV file in a specified folder.
""")

st.markdown("---")
st.header("1. Enter Search Query")
search_query = st.text_input("Enter your search query:", placeholder="e.g., 'best AI tools 2023'", key="search_query_input")

col1, col2 = st.columns([1, 2])
with col1:
    num_results_input_str = st.text_input("Number of results to fetch (10-500):", value="100", key="num_results_input")
    num_results_to_fetch = 100 # Default value
    try:
        num_results_to_fetch = int(num_results_input_str)
        if not (10 <= num_results_to_fetch <= 500):
            st.warning("Please enter a number between 10 and 500.")
            num_results_to_fetch = 100 # Revert to default if out of range
    except ValueError:
        st.warning("Please enter a valid integer for number of results.")
        num_results_to_fetch = 100 # Revert to default if invalid

with col2:
    st.markdown("<br>", unsafe_allow_html=True) # Add some space
    if st.button("🚀 Search Google", type="primary"):
        if search_query:
            with st.spinner(f"Fetching up to {num_results_to_fetch} search results... This might take a moment."):
                search_data = get_google_search_results(search_query, num_results_to_fetch)
                st.session_state['search_data'] = search_data
                # Initialize selected state for each item, default to True
                st.session_state['selected_items'] = {item['link']: True for item in search_data if item['link']}
                if search_data:
                    st.success(f"Successfully fetched {len(search_data)} results.")
                else:
                    st.warning("No results found for your query.")
        else:
            st.warning("Please enter a search query before searching.")

# --- Display Results and Export Options ---
if 'search_data' in st.session_state and st.session_state['search_data']:
    st.markdown("---")
    st.header(f"2. Results for '{search_query}' ({len(st.session_state['search_data'])} found)")

    # Option to save all at once
    st.subheader("Download All Found Data")
    df_full = pd.DataFrame(st.session_state['search_data'])
    
    col_dl_all, col_dl_all_spacer = st.columns([2, 5])
    with col_dl_all:
        csv_full_file = df_full.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download All Results as CSV",
            data=csv_full_file,
            file_name=f"{search_query.replace(' ', '_').lower()}_all_results.csv",
            mime="text/csv",
            help="Download a CSV containing all fetched links, titles, and snippets."
        )

    st.markdown("---")
    st.header("3. Review and Select Specific Items to Save")

    # Bulk Selection/Deselection Buttons within a form for proper state management
    with st.form("bulk_selection_form"):
        col_select_all, col_deselect_all, col_selected_count = st.columns([1, 1, 3])
        
        with col_select_all:
            if st.form_submit_button("✅ Select All"):
                st.session_state['selected_items'] = {link: True for link in st.session_state['selected_items']}
                # No rerun needed here, the changes will be reflected in the next render cycle
        with col_deselect_all:
            if st.form_submit_button("❌ Deselect All"):
                st.session_state['selected_items'] = {link: False for link in st.session_state['selected_items']}
                # No rerun needed here either
        with col_selected_count:
            selected_count = sum(1 for v in st.session_state['selected_items'].values() if v)
            st.metric(label="Items Selected", value=selected_count)
        
        # This submit button is just for the bulk actions, not the individual items.
        # Streamlit forms simplify state management for groups of inputs.

    st.markdown("Use the checkboxes below to select the items you wish to save.")
    st.markdown("---")
    
    selected_data_for_export = []

    # Display results directly without expanders
    for i, item in enumerate(st.session_state['search_data']):
        link = item.get('link')
        title = item.get('title', 'No Title')
        snippet = item.get('snippet', 'No snippet available.')

        if link:
            # Checkbox for each item
            st.session_state['selected_items'][link] = st.checkbox(
                f"**{i+1}. {title}**",
                value=st.session_state['selected_items'].get(link, True), # Get current state or default to True
                key=f"checkbox_{i}_{link}" # Unique key for each checkbox
            )

            # Display snippet and link
            st.markdown(f"*{snippet}*")
            st.markdown(f"🔗 [{link}]({link})")
            st.markdown("---") # Separator between items

            if st.session_state['selected_items'][link]:
                selected_data_for_export.append(item)
    
    # After the loop, the selected_data_for_export list is fully populated based on current checkbox states.

    st.subheader("Save Selected Items to a Folder")
    folder_name = st.text_input("Enter folder name to save CSV (e.g., 'my_search_exports'):", key="folder_name_input_selected")
    
    if st.button("Save Selected Items to CSV", type="secondary"):
        if folder_name:
            if selected_data_for_export:
                project_dir = os.path.dirname(os.path.abspath(__file__))
                export_dir = os.path.join(project_dir, "exports", folder_name)
                os.makedirs(export_dir, exist_ok=True) 

                df_to_save_individual = pd.DataFrame(selected_data_for_export)
                filename_query = "".join([c if c.isalnum() or c in [' ', '_'] else '' for c in search_query]).replace(' ', '_').lower()
                csv_path = os.path.join(export_dir, f"{filename_query}_selected_results.csv")
                
                try:
                    df_to_save_individual.to_csv(csv_path, index=False)
                    st.success(f"CSV with {len(selected_data_for_export)} selected items saved to: `{csv_path}`")
                except Exception as e:
                    st.error(f"Error saving CSV: {e}")
            else:
                st.warning("No items selected to save. Please check the checkboxes above.")
        else:
            st.error("Please enter a folder name before saving selected items.")

st.markdown("---")
st.markdown("Powered by [Serper API](https://serper.dev/) and Streamlit.")