import os
import httpx
import json
import asyncio
import traceback
from bs4 import BeautifulSoup
import textstat
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- NEW: Google Gemini Configuration ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_API_URL_BASE = "https://generativelanguage.googleapis.com/v1beta/models/"
MODEL_NAME = "gemini-2.5-flash-lite" # The model you specified

async def fetch_page(client, url):
    """Asynchronously fetches the content of a URL."""
    try:
        response = await client.get(url, follow_redirects=True, timeout=15.0)
        response.raise_for_status()
        return response.text
    except httpx.RequestError as exc:
        return f"An error occurred while requesting {exc.request.url!r}: {exc}"

# ... (All your non-LLM functions like analyze_heading_structure, audit_semantic_html, etc. are unchanged) ...
def analyze_heading_structure(soup):
    findings = []
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    h1_tags = soup.find_all('h1')
    if len(h1_tags) == 0:
        findings.append("❌ **Error:** No `<h1>` tag found.")
    elif len(h1_tags) > 1:
        findings.append(f"⚠️ **Warning:** Found {len(h1_tags)} `<h1>` tags. There should only be one.")
    if len(headings) > 1:
        last_level = int(headings[0].name[1])
        for i in range(1, len(headings)):
            current_level = int(headings[i].name[1])
            if current_level > last_level + 1:
                findings.append(f"❌ **Hierarchy Error:** Skipped from `<h{last_level}>` to `<h{current_level}>`. Text: \"{headings[i].get_text(strip=True)[:50]}...\"")
            last_level = current_level
    if not findings:
        findings.append("✅ **Success:** Heading structure is logical.")
    return findings

def audit_semantic_html(soup):
    findings = []
    for tag in soup.find_all(['strong', 'b']):
        if not tag.get_text(strip=True):
            findings.append("⚠️ **Warning:** Found an empty `<strong>` or `<b>` tag.")
    for list_tag in soup.find_all(['ul', 'ol']):
        invalid_children = [child.name for child in list_tag.children if child.name and child.name != 'li']
        if invalid_children:
            findings.append(f"❌ **Structure Error:** Found a `<{list_tag.name}>` tag with invalid direct children: {invalid_children}. Only `<li>` tags are allowed.")
    if not findings:
        findings.append("✅ **Success:** Basic semantic HTML looks good.")
    return findings

def analyze_readability(text):
    score = textstat.flesch_reading_ease(text)
    return {"flesch_reading_ease": score}

def analyze_meta_tags(soup):
    findings = {
        'title': {'text': '', 'length': 0, 'status': 'Missing'},
        'meta_description': {'text': '', 'length': 0, 'status': 'Missing'}
    }
    title_tag = soup.find('title')
    if title_tag:
        text = title_tag.get_text(strip=True)
        length = len(text)
        status = 'Good'
        if length == 0:
            status = 'Empty'
        elif length > 65:
            status = '❌ Too long'
        findings['title'] = {'text': text, 'length': length, 'status': status}
    meta_desc_tag = soup.find('meta', attrs={'name': 'description'})
    if meta_desc_tag:
        text = meta_desc_tag.get('content', '').strip()
        length = len(text)
        status = 'Good'
        if length == 0:
            status = 'Empty'
        elif length > 160:
            status = '❌ Too long'
        findings['meta_description'] = {'text': text, 'length': length, 'status': status}
    return findings

# --- UPDATED LLM FUNCTIONS FOR GEMINI ---

async def get_title_recommendations(client, current_title, h1_text, text_content):
    """Uses the Gemini API to generate SEO-friendly title recommendations."""
    if not GOOGLE_API_KEY:
        print("DEBUG: GOOGLE_API_KEY not found!")
        return {"error": "GOOGLE_API_KEY not found."}

    prompt = f"""
    You are an expert SEO copywriter.
    The current title tag is: "{current_title}"
    The main H1 heading is: "{h1_text}"
    Your task is to generate 3 improved, SEO-friendly title tags.
    GUIDELINES:
    1. CRITICAL: All 3 titles MUST be 60 characters or less.
    2. They must be compelling for human readers.
    3. They must be machine-readable, incorporating key entities.
    4. Do not just add keywords. Capture the user's intent.
    List only the 3 new title suggestions, each on a new line.
    Verify each one is 60 characters or less. Do not add any other text.
    ARTICLE TEXT SNIPPET FOR CONTEXT:
    {text_content[:2000]}
    """
    
    # Gemini API URL and payload format
    api_url = f"{GEMINI_API_URL_BASE}{MODEL_NAME}:generateContent?key={GOOGLE_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 256
        }
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = await client.post(
            api_url, 
            content=json.dumps(payload),
            headers=headers, 
            timeout=30.0
        )
        response.raise_for_status() 
        # Parse the Gemini-specific response
        data = response.json()
        suggestions = data['candidates'][0]['content']['parts'][0]['text']
        return {"suggestions": suggestions, "error": None}
    except Exception as e:
        print("\n" + "--- ERROR IN get_title_recommendations ---")
        traceback.print_exc()
        print("------------------------------------------" + "\n")
        return {"error": f"An error occurred with the LLM API: {e}", "suggestions": ""}

async def get_topical_gaps(client, title, text_content):
    """Uses Gemini API to find topical gaps and generate Q&A pairs."""
    if not GOOGLE_API_KEY:
        print("DEBUG: GOOGLE_API_KEY not found!")
        return {"error": "GOOGLE_API_KEY not found."}
    
    prompt = f"""
    An article's main topic is "{title}".
    1. Identify key sub-topics or common questions related to this topic that are missing from the article text provided below.
    2. Based ONLY on the missing topics, generate 3-5 relevant question and answer pairs suitable for an FAQ section.
    3. VERY IMPORTANT: Format the output as a clean list, with each question starting with "Q:" and each answer starting with "A:". Do not add any other conversational text or introduction.
    ARTICLE TEXT TO ANALYZE:
    {text_content[:4000]}
    """
    # Gemini API URL and payload format
    api_url = f"{GEMINI_API_URL_BASE}{MODEL_NAME}:generateContent?key={GOOGLE_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1024
        }
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = await client.post(
            api_url, 
            content=json.dumps(payload),
            headers=headers, 
            timeout=30.0
        )
        response.raise_for_status()
        # Parse the Gemini-specific response
        data = response.json()
        qna_text = data['candidates'][0]['content']['parts'][0]['text']
        
        # Parse the Q&A text (this logic is unchanged)
        qna_pairs = []
        for line in qna_text.strip().split('\n'):
            if line.startswith('Q:'):
                qna_pairs.append({'question': line[2:].strip(), 'answer': ''})
            elif line.startswith('A:') and qna_pairs:
                qna_pairs[-1]['answer'] = line[2:].strip()
        
        return {"raw_text": qna_text, "structured_qna": qna_pairs}
    except Exception as e:
        print("\n" + "--- ERROR IN get_topical_gaps ---")
        traceback.print_exc()
        print("-----------------------------------" + "\n")
        return {"error": f"An error occurred with the LLM API: {e}", "raw_text": "", "structured_qna": []}

# ... (audit_for_schema, generate_article_schema, generate_faq_schema are unchanged) ...
def audit_for_schema(soup):
    found_schema = {'Article': False, 'FAQPage': False}
    script_tags = soup.find_all('script', type='application/ld+json')
    for tag in script_tags:
        try:
            data = json.loads(tag.string)
            graph = data.get('@graph', [data])
            for item in graph:
                schema_type = item.get('@type')
                if schema_type == 'Article':
                    found_schema['Article'] = True
                elif schema_type == 'FAQPage':
                    found_schema['FAQPage'] = True
        except (json.JSONDecodeError, AttributeError):
            continue
    return found_schema

def generate_article_schema(soup, url):
    title = soup.find('h1').get_text(strip=True) if soup.find('h1') else "No H1 Title Found"
    schema = {"@context": "https://schema.org", "@type": "Article", "headline": title, "mainEntityOfPage": {"@type": "WebPage", "@id": url}}
    return json.dumps(schema, indent=4)

def generate_faq_schema(qna_pairs):
    if not qna_pairs:
        return None
    main_entity = []
    for pair in qna_pairs:
        if pair['question'] and pair['answer']:
            main_entity.append({"@type": "Question", "name": pair['question'], "acceptedAnswer": {"@type": "Answer", "text": pair['answer']}})
    if not main_entity:
        return None
    schema = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": main_entity}
    return json.dumps(schema, indent=4)


async def get_content_structure_recommendations(client, text_content):
    """Uses the Gemini API to suggest headings for long-form text."""
    if not GOOGLE_API_KEY:
        print("DEBUG: GOOGLE_API_KEY not found!")
        return {"error": "GOOGLE_API_KEY not found."}

    cleaned_text = ' '.join(text_content.split())
    
    # --- PROMPT HAS BEEN MODIFIED ---
    prompt = f"""
    Analyze the following article text, which is long and lacks sufficient headings. Your task is to improve its scannability and structure by suggesting headings.

    1. Read through the text and identify **major** logical breaks where a new, **substantial** sub-topic begins.
    2. Suggest a concise and descriptive heading for these breaks (e.g., as an ## H2 or ### H3).
    3. **CRITICAL RULE:** For each suggested heading, you MUST include a context snippet. This snippet should be the **first 10-15 words** of the paragraph that will immediately follow the new heading. This is essential for knowing where to place it.
    4. Ensure there are at least 1-2 paragraphs of substantial content *between* each suggested heading.

    Your output must follow this exact format:

    ## New Suggested H2
    **Context:** "The first few words of the paragraph that starts here..."

    ### New Suggested H3
    **Context:** "Following the main topic, this section discusses..."

    ## Another New Suggested H2
    **Context:** "Finally, the article discusses the impact of..."

    ARTICLE TEXT TO ANALYZE:
    {cleaned_text[:6000]}
    """
    
    api_url = f"{GEMINI_API_URL_BASE}{MODEL_NAME}:generateContent?key={GOOGLE_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.5,
            "maxOutputTokens": 1024
        }
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = await client.post(
            api_url, 
            content=json.dumps(payload),
            headers=headers, 
            timeout=45.0
        )
        response.raise_for_status()
        data = response.json()
        suggestions = data['candidates'][0]['content']['parts'][0]['text']
        return {"heading_suggestions": suggestions, "error": None}
    except Exception as e:
        print("\n" + "--- ERROR IN get_content_structure_recommendations ---")
        traceback.print_exc()
        print("------------------------------------------------------" + "\n")
        return {"error": f"An error occurred with the LLM API: {e}", "heading_suggestions": ""}

# --- UPDATED: analyze_url now uses asyncio.gather again ---
# We removed the artificial delays (asyncio.sleep)
# Gemini's API is generally more robust for concurrent requests
# This makes the app much faster.

async def analyze_url(url):
    """Main analysis orchestrator for a single URL."""
    async with httpx.AsyncClient() as client:
        html_content = await fetch_page(client, url)

        if html_content.startswith("An error occurred"):
            return {"url": url, "error": html_content}

        soup = BeautifulSoup(html_content, 'html.parser')
        main_content = soup.find('main') or soup.find('article') or soup.body
        text_content = main_content.get_text()
        
        title = soup.find('title').string if soup.find('title') else "No Title Found"
        h1_tag = soup.find('h1')
        h1_text = h1_tag.get_text(strip=True) if h1_tag else title

        # --- RE-ENABLED asyncio.gather for speed ---
        (topical_findings, 
         structure_recommendations,
         title_recommendations) = await asyncio.gather(
            get_topical_gaps(client, title, text_content),
            get_content_structure_recommendations(client, text_content),
            get_title_recommendations(client, title, h1_text, text_content)
        )
        # --- END OF CHANGE ---

        # Run all synchronous analyses
        meta_tag_findings = analyze_meta_tags(soup)
        heading_findings = analyze_heading_structure(soup)
        semantic_findings = audit_semantic_html(soup)
        readability_findings = analyze_readability(text_content)
        existing_schema = audit_for_schema(soup)

        # Generate recommendations
        recommendations = {"article_schema": None, "faq_schema": None}
        if not existing_schema['Article']:
            recommendations['article_schema'] = generate_article_schema(soup, url)
        
        if not existing_schema['FAQPage'] and topical_findings.get("structured_qna"):
            recommendations['faq_schema'] = generate_faq_schema(topical_findings["structured_qna"])

        # Compile all results
        return {
            "url": url,
            "title": title,
            "meta_analysis": {
                "tags": meta_tag_findings,
                "llm_suggestions": title_recommendations
            },
            "structural_integrity": {"headings": heading_findings, "semantics": semantic_findings},
            "readability": readability_findings,
            "topical_gaps": {"raw_text": topical_findings.get("raw_text")},
            "existing_schema": existing_schema,
            "recommendations": recommendations,
            "content_structure": structure_recommendations
        }