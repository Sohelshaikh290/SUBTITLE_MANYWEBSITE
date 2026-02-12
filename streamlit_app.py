import streamlit as st
import yt_dlp
import os
import tempfile
import re
import requests
import time
from datetime import timedelta
from typing import Tuple, Optional

# --- Page Configuration ---
st.set_page_config(
    page_title="Universal Subtitle Downloader",
    page_icon="🎬",
    layout="wide"
)

# --- Custom Styles (HTML/CSS/JS) ---
st.markdown("""
    <style>
    /* Import Google Font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

    /* Global Styles */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Modern Dark Background */
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        color: #e2e8f0;
    }

    /* Title Styling */
    h1 {
        background: linear-gradient(to right, #4facfe 0%, #00f2fe 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800 !important;
        letter-spacing: -1px;
    }
    
    h3 {
        color: #94a3b8 !important;
    }

    /* Input Fields */
    .stTextInput > div > div > input {
        background-color: #1e293b;
        color: white;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 12px;
        transition: border-color 0.3s ease;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #38bdf8;
        box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.2);
    }

    /* Styled Buttons */
    .stButton > button {
        background: linear-gradient(90deg, #3b82f6 0%, #2563eb 100%);
        color: white;
        border: none;
        padding: 0.6rem 1.2rem;
        border-radius: 10px;
        font-weight: 600;
        width: 100%;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(37, 99, 235, 0.4);
        background: linear-gradient(90deg, #2563eb 0%, #1d4ed8 100%);
    }

    /* Card/Expander Styling */
    div[data-testid="stExpander"] {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }

    /* Selectbox styling */
    div[data-baseweb="select"] > div {
        background-color: #1e293b;
        border-color: #334155;
        border-radius: 10px;
        color: white;
    }

    /* Images */
    img {
        border-radius: 16px;
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
        border: 1px solid #334155;
    }
    
    /* Custom divider */
    hr {
        margin: 2em 0;
        border-color: #334155;
    }
    
    /* Footer */
    .footer-text {
        text-align: center;
        color: #64748b;
        font-size: 0.875rem;
    }
    </style>
    """, unsafe_allow_html=True)

# --- Helper Functions ---

def sanitize_filename(name):
    """Sanitize the string to be safe for filenames."""
    return re.sub(r'[\\/*?:"<>|]', "", name)

def strip_vtt_timestamps(vtt_text: str) -> str:
    """Simple regex to remove VTT/SRT timestamps and metadata for a clean transcript."""
    text = re.sub(r'WEBVTT/n.*?\n\n', '', vtt_text, flags=re.DOTALL)
    text = re.sub(r'\d{1,2}:\d{2}:\d{2}\.\d{3} --> \d{1,2}:\d{2}:\d{2}\.\d{3}.*?\n', '', text)
    text = re.sub(r'\d{1,2}:\d{2}:\d{2},\d{3} --> \d{1,2}:\d{2}:\d{2},\d{3}.*?\n', '', text)
    text = re.sub(r'<[^>]*>', '', text)
    text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n+', '\n', text)
    return text.strip()

def get_info(url: str, cookies_path: Optional[str] = None):
    """Extracts video information using yt-dlp."""
    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'listsubtitles': True,
        'cookiefile': cookies_path if cookies_path else None
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        st.error(f"Extraction Error: {str(e)}")
        return None

# --- YouTube Specific Logic ---

def process_youtube_subtitles(url: str, sub_code: str, is_auto: bool, cookies_path: str, clean_text: bool) -> Tuple[Optional[bytes], str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            'skip_download': True,
            'writesubtitles': not is_auto,
            'writeautomaticsub': is_auto,
            'subtitleslangs': [sub_code],
            'outtmpl': os.path.join(tmpdir, 'downloaded_sub'),
            'cookiefile': cookies_path if cookies_path else None,
            'postprocessors': [{'key': 'FFmpegSubtitlesConvertor', 'format': 'srt'}] if not clean_text else [],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_title = info.get('title', 'subtitles')
                
                files = os.listdir(tmpdir)
                if not files:
                    return None, ""
                
                # Find the largest file (likely the sub)
                source_file = os.path.join(tmpdir, files[0])
                ext = os.path.splitext(files[0])[1]
                
                with open(source_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if clean_text:
                    content = strip_vtt_timestamps(content)
                    final_name = f"{sanitize_filename(video_title)}.txt"
                    return content.encode('utf-8'), final_name
                else:
                    final_name = f"{sanitize_filename(video_title)}{ext}"
                    return content.encode('utf-8'), final_name
                    
        except Exception as e:
            st.error(f"Processing failed: {e}")
            return None, ""

def render_youtube_ui(info, url, cookies_path):
    st.subheader("⚙️ Download Options")
    
    col1, col2 = st.columns(2)
    with col1:
        clean_mode = st.toggle("Clean Transcript Mode", value=True, help="Removes timestamps for easy reading.")
    
    manual = info.get('subtitles', {})
    auto = info.get('automatic_captions', {})
    
    options = []
    for k, v in manual.items():
        options.append({"label": f"✅ {v[0].get('name', k)} (Manual)", "code": k, "auto": False})
    for k, v in auto.items():
        options.append({"label": f"🤖 {v[0].get('name', k)} (Auto)", "code": k, "auto": True})
    
    if not options:
        st.warning("No subtitles detected for this video.")
    else:
        selection = st.selectbox(
            "Choose Language & Type", 
            options, 
            format_func=lambda x: x['label']
        )
        
        if st.button("🚀 Generate Download Link"):
            with st.spinner("Processing..."):
                data, name = process_youtube_subtitles(
                    url, 
                    selection['code'], 
                    selection['auto'], 
                    cookies_path, 
                    clean_mode
                )
                
                if data:
                    st.success("Ready!")
                    st.download_button(
                        label=f"💾 Download {name}",
                        data=data,
                        file_name=name,
                        mime="text/plain" if clean_mode else "text/srt"
                    )

# --- Dailymotion Specific Logic ---

def render_dailymotion_ui(info):
    video_title = info.get('title', 'Dailymotion_Video')
    safe_title = sanitize_filename(video_title)
    
    manual_subs = info.get('subtitles', {})
    auto_subs = info.get('automatic_captions', {})
    
    options = []

    # Helper to add options
    def add_options(subs_dict, type_label):
        for lang, sub_list in subs_dict.items():
            for sub in sub_list:
                ext = sub.get('ext')
                # Skip playlists, we want text formats
                if ext == 'm3u8': 
                    continue
                
                options.append({
                    "label": f"{type_label} {lang.upper()} ({ext})",
                    "url": sub.get('url'),
                    "ext": ext,
                    "lang": lang
                })

    add_options(manual_subs, "✅ Manual")
    add_options(auto_subs, "🤖 Auto")

    st.subheader("⚙️ Download Options")
    
    if options:
        selection = st.selectbox(
            "Choose Language & Format",
            options,
            format_func=lambda x: x['label']
        )

        if st.button("🚀 Generate Download Link"):
            with st.spinner("Fetching raw subtitle file..."):
                try:
                    response = requests.get(selection['url'])
                    if response.status_code == 200:
                        file_name = f"{safe_title}_{selection['lang']}.{selection['ext']}"
                        st.success("Ready!")
                        st.download_button(
                            label=f"💾 Download {selection['ext'].upper()}",
                            data=response.content,
                            file_name=file_name,
                            mime="application/octet-stream"
                        )
                    else:
                        st.error("Could not fetch file from Dailymotion.")
                except Exception as e:
                    st.error(f"Error fetching subtitle: {e}")
    else:
        st.info("No text-based subtitles found for this video.")

# --- Main App Layout ---

# Header with Logo
col1, col2 = st.columns([0.1, 0.9])
with col1:
    st.image("https://cdn-icons-png.flaticon.com/512/1169/1169608.png", width=70)
with col2:
    st.title("Universal Subtitle Downloader")

st.markdown("""
<div style='background-color: rgba(30, 41, 59, 0.5); padding: 15px; border-radius: 10px; border: 1px solid #334155; margin-bottom: 20px;'>
    <p style='margin:0; color: #94a3b8;'>Supports <b>YouTube</b> (Clean & SRT conversion) and <b>Dailymotion</b> (Raw VTT/SRT extraction).</p>
</div>
""", unsafe_allow_html=True)

# Global Settings (Cookies apply to both if needed, mainly YouTube)
with st.expander("🔐 Advanced Settings (Cookies)"):
    use_cookies = st.toggle("Enable Cookies", help="Required for age-gated YouTube videos")
    cookie_file = None
    if use_cookies:
        cookie_file = st.file_uploader("Upload cookies.txt", type=['txt'])

url = st.text_input("Paste Video Link (YouTube or Dailymotion):", placeholder="https://...")

if url:
    cookies_path = None
    if use_cookies and cookie_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
            tmp.write(cookie_file.getvalue())
            cookies_path = tmp.name

    with st.spinner("Analyzing video metadata..."):
        info = get_info(url, cookies_path)

    if info:
        # Common Info Display
        title = info.get('title', 'Unknown Title')
        thumbnail = info.get('thumbnail')
        duration = info.get('duration')
        duration_str = str(timedelta(seconds=duration)) if duration else "Unknown"
        extractor = info.get('extractor_key', 'Unknown').lower()

        st.divider()
        
        # Use a container for the video info card effect
        with st.container():
            col1, col2 = st.columns([1, 2])
            with col1:
                if thumbnail:
                    st.image(thumbnail, use_container_width=True)
            with col2:
                st.subheader(title)
                st.markdown(f"""
                <div style='display: flex; gap: 10px; flex-wrap: wrap; margin-top: 10px;'>
                    <span style='background-color: #3b82f6; padding: 4px 12px; border-radius: 20px; font-size: 0.8em; font-weight: 600;'>{extractor.capitalize()}</span>
                    <span style='background-color: #1e293b; border: 1px solid #334155; padding: 4px 12px; border-radius: 20px; font-size: 0.8em;'>⏱️ {duration_str}</span>
                    <span style='background-color: #1e293b; border: 1px solid #334155; padding: 4px 12px; border-radius: 20px; font-size: 0.8em;'>👤 {info.get('uploader', 'Unknown')}</span>
                </div>
                """, unsafe_allow_html=True)

        st.divider()

        # Branch Logic based on Platform
        if 'dailymotion' in extractor:
            render_dailymotion_ui(info)
        else:
            # Default to YouTube style logic for YouTube and others
            render_youtube_ui(info, url, cookies_path)

    # Cleanup
    if cookies_path and os.path.exists(cookies_path):
        os.remove(cookies_path)

st.markdown("---")
st.markdown("<p class='footer-text'>Developed with ❤️ using Streamlit & yt-dlp</p>", unsafe_allow_html=True)
