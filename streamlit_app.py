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
            result = await analyze_url(url)
            results.append(result)
        except Exception as e:
            # Don't let one bad URL stop the whole batch
            results.append({"url": url, "error": f"Failed to analyze: {e}"})

        # Update the progress bar
        progress_bar.progress((i + 1) / len(urls))

        # If it's not the last URL, add the delay
        if i < len(urls) - 1:
            await asyncio.sleep(delay_seconds)
    
    # Clear the status text
    status_text.empty()
    progress_bar.empty()
    return results

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
        try:
            # Set your delay (in seconds) here
            DELAY_PER_URL = 1.0 
            
            # Call the new sequential runner
            analysis_results = asyncio.run(run_analysis_in_sequence(urls, DELAY_PER_URL))
            
            # Store results in Streamlit's session state
            st.session_state['results'] = analysis_results
            st.success("Analysis complete!")
        except Exception as e:
            st.exception(f"An unexpected error occurred: {e}")

# --- Display Results ---
if 'results' in st.session_state:
    results = st.session_state['results']
    
    st.header("Analysis Report", divider="blue")

    # --- Download Button ---
    try:
        flat_data = flatten_results_for_csv(results)
        df = pd.DataFrame(flat_data)
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

        with st.expander(f"✅ {result.get('title')}"):
            st.link_button("Open URL in New Tab", result.get('url'))
            
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
                
                # ▼▼▼ THIS SECTION IS UPDATED ▼▼▼
                st.markdown("**LLM Title Recommendations:**")
                suggestions = llm_data.get('suggestions')
                error_message = llm_data.get('error')

                if suggestions:
                    st.code(suggestions, language=None)
                elif error_message:
                    st.error(f"Could not generate suggestions: {error_message}")
                else:
                    st.info("No title suggestions were generated.")
                # ▲▲▲ END OF UPDATE ▲▲▲


                # --- Recommendations & Generated Assets ---
                st.subheader("Recommendations & Generated Assets")
                st.markdown("**Article Schema:**")
                # ... (this part is unchanged) ...
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
                
                # ▼▼▼ THIS SECTION IS UPDATED ▼▼▼
                st.subheader("Content Structure Recommendations")
                content_data = result.get('content_structure', {})
                suggestions = content_data.get('heading_suggestions')
                error_message = content_data.get('error')

                if suggestions:
                    st.markdown(suggestions)
                elif error_message:
                    st.error(f"Could not generate structure recommendations: {error_message}")
                else:
                    st.info("Could not generate heading suggestions.")
                # ▲▲▲ END OF UPDATE ▲▲▲

            with col2:
                # --- Structural Integrity ---
                st.subheader("Structural Integrity")
                # ... (this part is unchanged) ...
                for finding in result.get('structural_integrity', {}).get('headings', []):
                    st.markdown(finding) # Use markdown to render emoji/bold
                for finding in result.get('structural_integrity', {}).get('semantics', []):
                    st.markdown(finding)
                
                # --- Readability ---
                st.subheader("Readability")
                st.metric("Flesch Reading Ease", result.get('readability', {}).get('flesch_reading_ease'))
                
                # ▼▼▼ THIS SECTION IS UPDATED ▼▼▼
                st.subheader("Identified Content Gaps (LLM Output)")
                gaps_data = result.get('topical_gaps', {})
                raw_text = gaps_data.get('raw_text')
                error_message = gaps_data.get('error')

                if raw_text:
                    st.text(raw_text)
                elif error_message:
                    st.error(f"Could not generate content gaps: {error_message}")
                else:
                    st.info("No content gaps were generated.")
                # ▲▲▲ END OF UPDATE ▲▲▲