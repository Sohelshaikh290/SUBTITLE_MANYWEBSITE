import streamlit as st
import yt_dlp
import os
import tempfile
import re
import requests
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
        color: white !important;
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

    /* Radio button labels */
    .stRadio label {
        color: #e2e8f0 !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- Helper Functions ---

def sanitize_filename(name):
    """Sanitize the string to be safe for filenames."""
    return re.sub(r'[\\/*?:"<>|]', "", name)

def strip_vtt_timestamps(vtt_text: str) -> str:
    """Simple regex to remove VTT/SRT timestamps and metadata for a clean transcript."""
    # Remove WEBVTT header
    text = re.sub(r'WEBVTT\n.*?\n\n', '', vtt_text, flags=re.DOTALL)
    # Remove timestamps (VTT: 00:00:00.000 --> 00:00:00.000, SRT: 00:00:00,000 --> 00:00:00,000)
    text = re.sub(r'\d{1,2}:\d{2}:\d{2}[\.,]\d{3} --> \d{1,2}:\d{2}:\d{2}[\.,]\d{3}.*?\n', '', text)
    # Remove HTML-like tags
    text = re.sub(r'<[^>]*>', '', text)
    # Remove leading sequence numbers from SRT
    text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)
    # Collapse multiple newlines
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

# --- Unified Processing Logic ---

def process_subtitles(url: str, sub_code: str, is_auto: bool, cookies_path: str, format_choice: str) -> Tuple[Optional[bytes], str]:
    """Handles download and conversion for both YouTube and general sources via yt-dlp."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            'skip_download': True,
            'writesubtitles': not is_auto,
            'writeautomaticsub': is_auto,
            'subtitleslangs': [sub_code],
            'outtmpl': os.path.join(tmpdir, 'sub_file.%(ext)s'),
            'cookiefile': cookies_path if cookies_path else None,
        }

        # Force conversion to srt if SRT or Clean TXT is requested (SRT is easier to parse for cleaning)
        if format_choice in ["SRT", "Clean TXT"]:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegSubtitlesConvertor',
                'format': 'srt'
            }]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_title = info.get('title', 'subtitles')
                
                files = os.listdir(tmpdir)
                if not files:
                    return None, ""
                
                # Logic to find the right file: 
                # If we asked for SRT, look for .srt first. Otherwise look for .vtt.
                sub_file = None
                target_ext = '.srt' if format_choice in ["SRT", "Clean TXT"] else '.vtt'
                
                # Try to find the specific converted file first
                for f in files:
                    if f.endswith(target_ext):
                        sub_file = f
                        break
                
                # Fallback to any subtitle file if target extension wasn't found
                if not sub_file:
                    for f in files:
                        if f.endswith(('.srt', '.vtt', '.ttml', '.json3')):
                            sub_file = f
                            break
                
                if not sub_file:
                    return None, ""

                source_path = os.path.join(tmpdir, sub_file)
                
                with open(source_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                if format_choice == "Clean TXT":
                    content = strip_vtt_timestamps(content)
                    final_name = f"{sanitize_filename(video_title)}.txt"
                    return content.encode('utf-8'), final_name
                else:
                    actual_ext = os.path.splitext(sub_file)[1]
                    final_name = f"{sanitize_filename(video_title)}{actual_ext}"
                    return content.encode('utf-8'), final_name
                    
        except Exception as e:
            st.error(f"Processing failed: {e}")
            return None, ""

# --- UI Renderers ---

def render_download_options(info, url, cookies_path):
    st.subheader("⚙️ Download Options")
    
    manual = info.get('subtitles', {})
    auto = info.get('automatic_captions', {})
    
    options = []
    for k, v in manual.items():
        options.append({"label": f"✅ {v[0].get('name', k)} (Manual)", "code": k, "auto": False})
    for k, v in auto.items():
        options.append({"label": f"🤖 {v[0].get('name', k)} (Auto)", "code": k, "auto": True})
    
    if not options:
        st.warning("No subtitles detected for this video.")
        return

    col_lang, col_fmt = st.columns(2)
    
    with col_lang:
        selection = st.selectbox(
            "1. Choose Language", 
            options, 
            format_func=lambda x: x['label']
        )
    
    with col_fmt:
        format_choice = st.radio(
            "2. Select Output Format",
            ["SRT", "VTT", "Clean TXT"],
            horizontal=True,
            help="SRT is standard for players. VTT is web-standard. Clean TXT removes all timestamps."
        )
        
    if st.button("🚀 Generate Download Link"):
        with st.spinner("Processing subtitles..."):
            data, name = process_subtitles(
                url, 
                selection['code'], 
                selection['auto'], 
                cookies_path, 
                format_choice
            )
            
            if data:
                st.success(f"Success! '{format_choice}' file generated.")
                mime_map = {"SRT": "text/srt", "VTT": "text/vtt", "Clean TXT": "text/plain"}
                st.download_button(
                    label=f"💾 Download {name}",
                    data=data,
                    file_name=name,
                    mime=mime_map.get(format_choice, "text/plain")
                )
            else:
                st.error("Failed to extract subtitles in that specific format. Try 'VTT' (Raw) instead.")

# --- Main App Layout ---

# Header with Logo
col_logo, col_title = st.columns([0.1, 0.9])
with col_logo:
    st.image("https://cdn-icons-png.flaticon.com/512/1169/1169608.png", width=70)
with col_title:
    st.title("Universal Subtitle Downloader")

st.markdown("""
<div style='background-color: rgba(30, 41, 59, 0.5); padding: 15px; border-radius: 10px; border: 1px solid #334155; margin-bottom: 20px;'>
    <p style='margin:0; color: #94a3b8;'>Supports <b>YouTube</b> and <b>Dailymotion</b>. Extract high-quality <b>SRT</b>, <b>VTT</b>, or <b>Clean Transcripts</b> in seconds.</p>
</div>
""", unsafe_allow_html=True)

# Global Settings
with st.expander("🔐 Advanced Settings (Cookies)"):
    use_cookies = st.toggle("Enable Cookies", help="Recommended for age-gated or region-locked content.")
    cookie_file = None
    if use_cookies:
        cookie_file = st.file_uploader("Upload cookies.txt", type=['txt'])

url_input = st.text_input("Paste Video Link:", placeholder="https://www.youtube.com/watch?v=... or https://www.dailymotion.com/video/...")

if url_input:
    cookies_path = None
    if use_cookies and cookie_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
            tmp.write(cookie_file.getvalue())
            cookies_path = tmp.name

    with st.spinner("Analyzing video metadata..."):
        info = get_info(url_input, cookies_path)

    if info:
        # Common Info Display
        title = info.get('title', 'Unknown Title')
        thumbnail = info.get('thumbnail')
        duration = info.get('duration')
        duration_str = str(timedelta(seconds=duration)) if duration else "Unknown"
        extractor = info.get('extractor_key', 'Video').lower()

        st.divider()
        
        # Metadata Card
        with st.container():
            col_img, col_txt = st.columns([1, 2])
            with col_img:
                if thumbnail:
                    st.image(thumbnail, use_container_width=True)
            with col_txt:
                st.subheader(title)
                st.markdown(f"""
                <div style='display: flex; gap: 10px; flex-wrap: wrap; margin-top: 10px;'>
                    <span style='background-color: #3b82f6; padding: 4px 12px; border-radius: 20px; font-size: 0.8em; font-weight: 600;'>{extractor.capitalize()}</span>
                    <span style='background-color: #1e293b; border: 1px solid #334155; padding: 4px 12px; border-radius: 20px; font-size: 0.8em;'>⏱️ {duration_str}</span>
                    <span style='background-color: #1e293b; border: 1px solid #334155; padding: 4px 12px; border-radius: 20px; font-size: 0.8em;'>👤 {info.get('uploader', 'Unknown Author')}</span>
                </div>
                """, unsafe_allow_html=True)

        st.divider()

        # Download UI (Same logic for both now, as yt-dlp handles both)
        render_download_options(info, url_input, cookies_path)

    # Cleanup Cookies
    if cookies_path and os.path.exists(cookies_path):
        try:
            os.remove(cookies_path)
        except:
            pass

st.markdown("---")
st.markdown("<p class='footer-text'>Developed with ❤️ using Streamlit & yt-dlp</p>", unsafe_allow_html=True)
