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

def vtt_to_srt(vtt_text: str) -> str:
    """Natively converts WebVTT text to SubRip (SRT) format without FFmpeg."""
    # 1. Remove WEBVTT header and metadata
    text = re.sub(r'^WEBVTT.*?(\n\n|\r\n\r\n)', '', vtt_text, flags=re.DOTALL)
    
    # 2. Convert timestamps: 00:00.000 -> 00:00:00,000
    def fix_timestamp(match):
        ts = match.group(0).replace('.', ',')
        if len(ts.split(':')[0]) == 2 and ts.count(':') == 1:
            return "00:" + ts
        return ts

    text = re.sub(r'\d{1,2}:\d{2}[\.,]\d{3}', fix_timestamp, text)
    
    # 3. Process blocks into SRT segments
    lines = text.splitlines()
    srt_blocks = []
    block_id = 1
    current_block = []
    
    for line in lines:
        if ' --> ' in line:
            if current_block:
                srt_blocks.append(f"{block_id}\n" + "\n".join(current_block).strip() + "\n")
                block_id += 1
                current_block = []
            current_block.append(line)
        elif line.strip():
            current_block.append(line)
            
    if current_block:
        srt_blocks.append(f"{block_id}\n" + "\n".join(current_block).strip() + "\n")
        
    return "\n".join(srt_blocks).strip()

def strip_timestamps(text: str) -> str:
    """Removes VTT/SRT timestamps and metadata for a clean transcript."""
    # Handle the specific WEBVTT header format
    text = re.sub(r'WEBVTT[\s\S]*?\n\n', '', text, count=1)
    # Remove standard timestamps
    text = re.sub(r'\d{1,2}:\d{2}:\d{2}[\.,]\d{3} --> \d{1,2}:\d{2}:\d{2}[\.,]\d{3}.*?\n', '', text)
    # Remove HTML tags and sequence IDs
    text = re.sub(r'<[^>]*>', '', text)
    text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)
    # Clean up empty lines
    text = re.sub(r'\n+', '\n', text)
    return text.strip()

def get_info(url: str, cookies_path: Optional[str] = None):
    """Extracts video information using yt-dlp with anti-bot headers."""
    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'listsubtitles': True,
        'cookiefile': cookies_path if cookies_path else None,
        # Common headers to avoid 401/403 errors on Dailymotion/YouTube
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Fetch-Mode': 'navigate',
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg:
            st.error("Dailymotion Unauthorized (401). This often happens when the platform blocks automated requests. Try using the 'Cookies' setting with a cookies.txt file from your browser.")
        else:
            st.error(f"Extraction Error: {error_msg}")
        return None

# --- Unified Processing Logic (Works for YouTube, Dailymotion, etc.) ---

def process_subtitles(url: str, sub_code: str, is_auto: bool, cookies_path: str, format_choice: str) -> Tuple[Optional[bytes], str]:
    """Handles download and native conversion for all sources using yt-dlp."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outtmpl = os.path.join(tmpdir, 'subtitle.%(ext)s')
        
        ydl_opts = {
            'skip_download': True,
            'writesubtitles': not is_auto,
            'writeautomaticsub': is_auto,
            'subtitleslangs': [sub_code],
            'outtmpl': outtmpl,
            'cookiefile': cookies_path if cookies_path else None,
            'quiet': True,
            'no_warnings': True,
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_title = info.get('title', 'subtitles')
                
                files = os.listdir(tmpdir)
                if not files:
                    return None, ""
                
                source_file = None
                subtitle_exts = ('.vtt', '.srt', '.ttml', '.json3', '.ass', '.ssa')
                for f in files:
                    if f.endswith(subtitle_exts):
                        source_file = f
                        break
                
                if not source_file:
                    return None, ""

                source_path = os.path.join(tmpdir, source_file)
                
                with open(source_path, 'r', encoding='utf-8', errors='ignore') as f:
                    raw_content = f.read()
                
                if format_choice == "SRT":
                    # Actual conversion from VTT to SRT if needed
                    if source_file.endswith('.vtt'):
                        content = vtt_to_srt(raw_content)
                    else:
                        content = raw_content
                    final_name = f"{sanitize_filename(video_title)}.srt"
                    return content.encode('utf-8'), final_name

                elif format_choice == "Clean TXT":
                    content = strip_timestamps(raw_content)
                    final_name = f"{sanitize_filename(video_title)}.txt"
                    return content.encode('utf-8'), final_name
                
                else:
                    # Raw (usually VTT)
                    actual_ext = os.path.splitext(source_file)[1]
                    final_name = f"{sanitize_filename(video_title)}{actual_ext}"
                    return raw_content.encode('utf-8'), final_name
                    
        except Exception as e:
            st.error(f"Processing failed: {e}")
            return None, ""

# --- Universal UI Renderer ---

def render_download_options(info, url, cookies_path):
    st.subheader("⚙️ Download Options")
    
    manual = info.get('subtitles', {})
    auto = info.get('automatic_captions', {})
    
    options = []
    # Add Manual Subtitles
    for k, v in manual.items():
        options.append({"label": f"✅ {v[0].get('name', k)} (Manual)", "code": k, "auto": False})
    # Add Auto Captions
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
            ["SRT", "Raw (VTT)", "Clean TXT"],
            horizontal=True,
            help="SRT: High compatibility. Raw: Original source. Clean TXT: Text only transcript."
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
                st.success(f"Success! {format_choice} file ready.")
                mime_map = {"SRT": "text/plain", "Raw (VTT)": "text/vtt", "Clean TXT": "text/plain"}
                st.download_button(
                    label=f"💾 Download {name}",
                    data=data,
                    file_name=name,
                    mime=mime_map.get(format_choice, "text/plain")
                )
            else:
                st.error("Extraction failed. This video might not support the selected format.")

# --- Main App Layout ---

# Header with Logo
col1, col2 = st.columns([0.1, 0.9])
with col1:
    st.image("https://cdn-icons-png.flaticon.com/512/1169/1169608.png", width=70)
with col2:
    st.title("Universal Subtitle Downloader")

st.markdown("""
<div style='background-color: rgba(30, 41, 59, 0.5); padding: 15px; border-radius: 10px; border: 1px solid #334155; margin-bottom: 20px;'>
    <p style='margin:0; color: #94a3b8;'>Supports <b>YouTube</b>, <b>Dailymotion</b>, and more. Extract high-quality <b>SRT</b>, <b>Raw VTT</b>, or <b>Clean Transcripts</b> in seconds.</p>
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

        # MERGED LOGIC: yt-dlp now handles Dailymotion and YouTube with the same advanced features
        render_download_options(info, url_input, cookies_path)

    if cookies_path and os.path.exists(cookies_path):
        try:
            os.remove(cookies_path)
        except:
            pass

st.markdown("---")
st.markdown("<p class='footer-text'>Developed with ❤️ using Streamlit & yt-dlp</p>", unsafe_allow_html=True)
