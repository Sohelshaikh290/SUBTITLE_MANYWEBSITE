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

# --- Custom Styles ---
st.markdown("""
    <style>
    .main { max-width: 1000px; margin: 0 auto; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; }
    .video-info-container { display: flex; gap: 20px; margin-bottom: 20px; align-items: flex-start; }
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
    st.subheader("Settings")
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
        
        if st.button("Generate Download"):
            with st.spinner("Processing..."):
                data, name = process_youtube_subtitles(
                    url, 
                    selection['code'], 
                    selection['auto'], 
                    cookies_path, 
                    clean_mode
                )
                
                if data:
                    st.balloons()
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

    st.subheader("Download Settings")
    
    if options:
        selection = st.selectbox(
            "Choose Language & Format",
            options,
            format_func=lambda x: x['label']
        )

        if st.button("Generate Download"):
            with st.spinner("Fetching raw subtitle file..."):
                try:
                    response = requests.get(selection['url'])
                    if response.status_code == 200:
                        file_name = f"{safe_title}_{selection['lang']}.{selection['ext']}"
                        st.balloons()
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

st.title("🎬 Universal Subtitle Downloader")
st.caption("Supports **YouTube** (Clean & SRT conversion) and **Dailymotion** (Raw VTT/SRT extraction).")

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
        col1, col2 = st.columns([1, 2])
        with col1:
            if thumbnail:
                st.image(thumbnail, use_container_width=True)
        with col2:
            st.subheader(title)
            st.write(f"**Source:** {extractor.capitalize()}")
            st.write(f"**Duration:** {duration_str}")
            st.write(f"**Channel:** {info.get('uploader', 'Unknown')}")

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
st.markdown("Developed with ❤️ using Streamlit & yt-dlp")
