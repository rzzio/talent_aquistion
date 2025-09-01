# Resume Scraper: Enhanced Web Crawling & Contact Extraction

A powerful tool for recruiters to efficiently extract candidate information from websites, resumes, and CVs.

## Table of Contents
- [Overview](#overview)
- [Key Improvements](#key-improvements)
- [Technical Details](#technical-details)
- [Usage Guide](#usage-guide)
- [Performance Considerations](#performance-considerations)
- [Data Structure](#data-structure)

## Overview
The `scrape_resume_details.py` script has been significantly improved to provide more comprehensive and efficient scraping capabilities for talent acquisition.

## Key Improvements

### 1. Comprehensive Website Crawling
- **Before**: Only checked predefined `LIKELY_PATHS` (e.g., `/resume`, `/cv`, `/about`)
- **After**: Crawls ALL links on the website with configurable depth (default: 10 levels)
- **Benefit**: Finds contact information and resumes that might be on any page of the website

### 2. Multiple Contact Extraction
- **Before**: Only extracted the first email and phone number found
- **After**: Extracts ALL emails and phone numbers found across the entire website
- **Benefit**: More complete contact information for each candidate

### 3. Smart URL Handling
- **Before**: Document URLs (like `example.com/resume.pdf`) were processed as-is and only the file was downloaded
- **After**: Document URLs are automatically converted to homepage (`example.com`) and the entire website is crawled for contact information
- **Benefit**: Ensures comprehensive crawling even when starting from a direct document link, finding all available contact details

### 4. Configurable Crawling Depth
- **Before**: Fixed crawling strategy
- **After**: Configurable depth parameter (1-15 levels) in the Streamlit UI
- **Benefit**: Users can balance thoroughness vs. speed based on their needs

### 5. Enhanced Error Handling & Safety Limits
- **Before**: Basic error handling
- **After**: 
  - Maximum page limit (50 pages) to prevent infinite crawling
  - Maximum links per page (20) to prevent explosion
  - Queue size limits (100) to prevent memory issues
  - Better URL filtering (excludes images, CSS, JS files)
- **Benefit**: More stable and predictable scraping behavior

### 6. Improved Contact Validation & Extraction
- **Before**: Basic regex extraction
- **After**: 
  - Email validation (checks for @ and domain structure)
  - Phone number cleaning and validation (minimum length check)
  - Duplicate removal
  - HTML attribute extraction (mailto links, data attributes)
  - Structured data extraction (JSON-LD)
  - Cloudflare email protection handling
  - Domain-based email generation for protected emails
  - Masked phone number detection and reporting
- **Benefit**: Higher quality contact data and better coverage, including privacy-protected information

### 7. Enhanced UI Display & Individual Selection
- **Before**: Single email/phone display, no individual selection
- **After**: 
  - Lists all emails found with individual ➕ buttons
  - Lists all phone numbers found with individual ➕ buttons
  - Lists masked phone numbers (privacy protected) with individual ➕ buttons
  - Shows pages crawled count
  - Shows all crawled URLs in collapsible expander (collapsed by default)
  - Manual input expanders for name, email, and phone when none found
  - "Add All Contacts to Basket" button for convenience
  - Better organized data display
- **Benefit**: Users can selectively choose which contacts to add and manually input missing information

### 8. Better CSV Export
- **Before**: Single email/phone columns
- **After**: 
  - `emails` column (semicolon-separated list)
  - `phones` column (semicolon-separated list)
  - `all_emails` and `all_phones` columns for compatibility
  - `pages_crawled` column for transparency
- **Benefit**: More comprehensive data export

## Technical Details

### New Functions Added
- `crawl_website()`: Main crawling engine with depth control
- `extract_all_links()`: Extracts all valid links from a page
- `extract_contacts_from_soup()`: Extracts contacts from HTML structure and attributes
- `extract_emails_from_json()`: Extracts emails from JSON structured data
- `extract_phones_from_json()`: Extracts phone numbers from JSON structured data
- `extract_masked_phones_from_soup()`: Extracts masked phone numbers from structured data
- `extract_masked_phones_from_json()`: Extracts masked phone numbers from JSON data
- Enhanced `extract_contacts()`: Better validation, multiple extraction, and Cloudflare protection handling

### Modified Functions
- `process_single_url()`: Now uses comprehensive crawling instead of likely paths, and crawls websites even when starting from document URLs
- `get_base_url()`: Handles document URLs by converting to homepage
- `write_results()`: Handles new data structure with multiple contacts
- `download_file()`: Added fallback directory handling for standalone usage

### Safety Features
- Rate limiting between requests
- Maximum page limits
- URL filtering to avoid non-HTML resources
- Queue size management
- Comprehensive error handling

## Usage Guide

### In Streamlit UI
1. Set the "Crawl Depth" slider in the sidebar (1-15, default 10)
2. Higher depth = more thorough but slower scraping
3. Results will show all emails and phones found

### Standalone Script
```bash
python scrape_resume_details.py
```
The script will use depth=10 by default and process all URLs in `urls.csv`.

### Example: PDF URL Handling
When processing a URL like `https://jeevenlamichhane.com.np/cv.pdf`:

**Before (Old Logic):**
- Downloads the PDF file
- Pages Crawled: 0
- No contact information extracted

**After (New Logic):**
- Downloads the PDF file
- Crawls the entire website (5 pages)
- Extracts all contact information:
  - Emails: `info@jeevenlamichhane.com.np`
  - Phones: `+977 9860463471`, `9711514328`
- Pages Crawled: 5

### Example: Contact Page Crawling
When processing a URL like `https://aashishtimsina.com.np`:

**Before (Old Logic):**
- Pages Crawled: 1 (homepage only)
- Emails: `contact@aashishtimsina.com.np`
- Phones: None found
- No individual selection options

**After (New Logic):**
- Pages Crawled: 13 (including contact page)
- Emails: `contact@aashishtimsina.com.np` ➕ (individual add button)
- Masked Phones: `+977-XXXXXXXXXX` ➕ (individual add button)
- Crawled URLs: Collapsible expander with all 13 pages
- Manual input options for missing data
- "Add All Contacts to Basket" button

## Performance Considerations
| Crawl Depth | Speed | Coverage | Recommended For |
|-------------|-------|----------|-----------------|
| 1-3         | Fast  | Basic    | Quick scanning  |
| 4-7         | Medium| Good     | Most use cases  |
| 8-10        | Slow  | Thorough | Important candidates |
| 11-15       | Very slow | Comprehensive | Special cases only |

## Data Structure
The scraped data now includes:
- `emails`: List of all emails found
- `phones`: List of all phone numbers found
- `all_emails`: Semicolon-separated string of emails
- `all_phones`: Semicolon-separated string of phones

This ensures both backward compatibility and enhanced data access.
