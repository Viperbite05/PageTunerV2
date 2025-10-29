import streamlit as st
import asyncio
import pandas as pd
import io
import time # We'll use this for the delay
from analyzer import analyze_url # Our core logic is imported

# --- Page Configuration ---
# Set the page to be wide
st.set_page_config(
    page_title="PageTuner AI",
    layout="wide"
)

# --- CSV Generation Function ---
# This function is unchanged
def flatten_results_for_csv(results):
    """Converts the nested result dictionaries into a flat list for pandas."""
    flat_data = []
    for result in results:
        if result.get('error'):
            row = {'URL': result.get('url'), 'Error': result.get('error')}
            flat_data.append(row)
            continue
            
        # Get the new meta analysis data
        meta_analysis = result.get('meta_analysis', {})
        tags = meta_analysis.get('tags', {})
        title_info = tags.get('title', {})
        meta_info = tags.get('meta_description', {})
        llm_sugs = meta_analysis.get('llm_suggestions', {})

        row = {
            'URL': result.get('url'),
            'Title': result.get('title'),
            'Title Text': title_info.get('text'),
            'Title Length': title_info.get('length'),
            'Title Status': title_info.get('status'),
            'Meta Description Text': meta_info.get('text'),
            'Meta Description Length': meta_info.get('length'),
            'Meta Description Status': meta_info.get('status'),
            'LLM Title Suggestions': llm_sugs.get('suggestions', ''),
            'Readability (Flesch Ease)': result.get('readability', {}).get('flesch_reading_ease'),
            'Structural Integrity - Headings': "\n".join(result.get('structural_integrity', {}).get('headings', [])),
            'Structural Integrity - Semantics': "\n".join(result.get('structural_integrity', {}).get('semantics', [])),
            'Existing Article Schema?': result.get('existing_schema', {}).get('Article'),
            'Existing FAQ Schema?': result.get('existing_schema', {}).get('FAQPage'),
            'Generated Article Schema': result.get('recommendations', {}).get('article_schema'),
            'Generated FAQ Schema': result.get('recommendations', {}).get('faq_schema'),
            'Content Structure Suggestions': result.get('content_structure', {}).get('heading_suggestions'),
            'Identified Content Gaps': result.get('topical_gaps', {}).get('raw_text')
        }
        flat_data.append(row)
    return flat_data

# --- Async Runner ---
# ▼▼▼ THIS FUNCTION IS NEW ▼▼▼
async def run_analysis_in_sequence(urls, delay_seconds=1.0):
    """
    Runs analysis for each URL one by one, with a delay between each.
    """
    results = []
    
    # Create a placeholder for the spinner text, so we can update it
    progress_bar = st.progress(0.0)
    status_text = st.empty()

    for i, url in enumerate(urls):
        # Update the status for the user
        status_text.info(f"Analyzing URL {i+1}/{len(urls)}: {url}")
        
        try:
            # Run the analysis for a single URL
            # asyncio.run() creates a new event loop for this single task
            result = await analyze_url(url)
            results.append(result)
        except Exception as e:
            # Don't let one bad URL stop the whole batch
            results.append({"url": url, "error": f"Failed to analyze: {e}"})

        # Update the progress bar
        progress_bar.progress((i + 1) / len(urls))

        # If it's not the last URL, add the delay
        if i < len(urls) - 1:
            # We must use asyncio.sleep since we are in an async function
            await asyncio.sleep(delay_seconds)
    
    # Clear the status text
    status_text.empty()
    progress_bar.empty()
    return results
# ▲▲▲ END OF NEW FUNCTION ▲▲▲

# --- PageTuner AI Dashboard ---
st.title("🤖 PageTuner AI")
st.caption("On-page optimization for technical and semantic structure.")

# --- URL Input ---
urls_text = st.text_area("Enter URLs (one per line, max 500)", height=200, placeholder="https://www.example.com/article1\nhttps://www.example.com/article2")

# --- Run Analysis Button ---
if st.button("Analyze URLs", type="primary"):
    urls = [url.strip() for url in urls_text.splitlines() if url.strip()]
    
    if not urls:
        st.error("Please enter at least one URL.")
    elif len(urls) > 500:
        st.error("Maximum of 500 URLs allowed.")
    else:
        # We no longer use st.spinner, as our new function handles status
        try:
            # Set your delay (in seconds) here
            # 1.0 = 1 second delay between each URL
            # 2.0 = 2 second delay, etc.
            DELAY_PER_URL = 1.0 
            
            # Call the new sequential runner
            analysis_results = asyncio.run(run_analysis_in_sequence(urls, DELAY_PER_URL))
            
            # Store results in Streamlit's session state
            st.session_state['results'] = analysis_results
            st.success("Analysis complete!")
        except Exception as e:
            st.exception(f"An unexpected error occurred: {e}")

# --- Display Results ---
# This entire section is unchanged
if 'results' in st.session_state:
    results = st.session_state['results']
    
    st.header("Analysis Report", divider="blue")

    # --- Download Button ---
    try:
        flat_data = flatten_results_for_csv(results)
        df = pd.DataFrame(flat_data)
        # Create an in-memory CSV
        csv_output = df.to_csv(index=False).encode('utf-8')
        
        st.download_button(
            label="Download CSV Report",
            data=csv_output,
            file_name="pagetuner_report.csv",
            mime="text/csv",
        )
    except Exception as e:
        st.error(f"Could not prepare CSV for download: {e}")
        
    # --- Individual Page Reports ---
    for result in results:
        if result.get('error'):
            with st.expander(f"❌ Error Analyzing: {result.get('url')}", expanded=True):
                st.error(result.get('error'))
            continue

        # Use an expander for each URL
        with st.expander(f"✅ {result.get('title')}"):
            st.link_button("Open URL in New Tab", result.get('url'))
            
            # Create two columns for a cleaner layout
            col1, col2 = st.columns(2)

            with col1:
                # --- Title & Meta Analysis ---
                st.subheader("Title & Meta Analysis")
                meta_data = result.get('meta_analysis', {})
                tags_data = meta_data.get('tags', {})
                llm_data = meta_data.get('llm_suggestions', {})
                
                # Title
                title_info = tags_data.get('title', {})
                st.metric(f"Title Length ({title_info.get('status')})", f"{title_info.get('length')} / 65")
                st.markdown("**Current Title**")
                st.code(title_info.get('text'), language=None)
                
                # Meta Description
                meta_info = tags_data.get('meta_description', {})
                st.metric(f"Meta Desc. Length ({meta_info.get('status')})", f"{meta_info.get('length')} / 160")
                st.markdown("**Current Meta Desc**")
                st.code(meta_info.get('text'), language=None)
                
                # LLM Suggestions
                st.markdown("**LLM Title Recommendations:**")
                if llm_data and not llm_data.get('error'):
                    st.code(llm_data.get('suggestions'), language=None)
                else:
                    st.info("No title suggestions were generated.")
                # --- END OF Title & Meta Analysis ---


                # --- Recommendations & Generated Assets ---
                st.subheader("Recommendations & Generated Assets")
                st.markdown("**Article Schema:**")
                if result.get('existing_schema', {}).get('Article'):
                    st.success("Article Schema already detected on page.")
                elif result.get('recommendations', {}).get('article_schema'):
                    st.warning("Article Schema missing. Generated schema below:")
                    st.code(result.get('recommendations').get('article_schema'), language="json")
                
                st.markdown("**FAQ Schema:**")
                if result.get('existing_schema', {}).get('FAQPage'):
                    st.success("FAQ Schema already detected on page.")
                elif result.get('recommendations', {}).get('faq_schema'):
                    st.warning("FAQ Schema missing. Generated schema below:")
                    st.code(result.get('recommendations').get('faq_schema'), language="json")
                
                # --- Content Structure ---
                st.subheader("Content Structure Recommendations")
                if result.get('content_structure') and not result.get('content_structure').get('error'):
                    st.markdown(result.get('content_structure').get('heading_suggestions'))
                else:
                    st.info("Could not generate heading suggestions.")

            with col2:
                # --- Structural Integrity ---
                st.subheader("Structural Integrity")
                for finding in result.get('structural_integrity', {}).get('headings', []):
                    st.markdown(finding) # Use markdown to render emoji/bold
                for finding in result.get('structural_integrity', {}).get('semantics', []):
                    st.markdown(finding)
                
                # --- Readability ---
                st.subheader("Readability")
                st.metric("Flesch Reading Ease", result.get('readability', {}).get('flesch_reading_ease'))
                
                # --- Topical Gaps ---
                st.subheader("Identified Content Gaps (LLM Output)")
                st.text(result.get('topical_gaps', {}).get('raw_text'))