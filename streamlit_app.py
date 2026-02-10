import streamlit as st
import yt_dlp
import requests
import re
import time

# Set page config
st.set_page_config(page_title="Dailymotion Raw Subtitle Extractor", page_icon="🎬")

def sanitize_filename(name):
    """
    Sanitize the string to be safe for filenames.
    Removes characters that aren't allowed in filenames.
    """
    return re.sub(r'[\\/*?:"<>|]', "", name)

def get_video_info(url):
    """
    Extracts video information using yt-dlp.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'listsubtitles': True,
        'skip_download': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except Exception as e:
        st.error(f"Error extracting info: {e}")
        return None

def format_duration(seconds):
    """Converts seconds to HH:MM:SS format."""
    if not seconds:
        return "Unknown"
    return time.strftime('%H:%M:%S', time.gmtime(seconds))

# --- UI Layout ---
st.title("🎬 Dailymotion Raw Subtitle Downloader")
st.markdown("Enter a Dailymotion link to extract **raw** subtitles in their original format (VTT, SRT, etc.).")

# Input
url = st.text_input("Paste Dailymotion Link Here:", placeholder="https://www.dailymotion.com/video/x...")

if url:
    if st.button("Extract Raw Subtitles"):
        with st.spinner("Fetching video details and subtitle maps..."):
            info = get_video_info(url)

            if info:
                # 1. Video Title & Metadata
                video_title = info.get('title', 'Dailymotion_Video')
                safe_title = sanitize_filename(video_title)
                duration = info.get('duration')
                thumbnail_url = info.get('thumbnail')
                
                # Combine manual subtitles and automatic captions
                manual_subs = info.get('subtitles', {})
                auto_subs = info.get('automatic_captions', {})
                
                # Merge dictionaries for processing
                # We flag them to know if they are auto-generated or not
                all_subs = {}
                
                for lang, sub_list in manual_subs.items():
                    all_subs[lang] = {'type': 'Manual', 'formats': sub_list}
                
                for lang, sub_list in auto_subs.items():
                    if lang not in all_subs:
                        all_subs[lang] = {'type': 'Auto-Generated', 'formats': sub_list}
                    else:
                        # If language exists in both, append formats
                        all_subs[lang]['formats'].extend(sub_list)

                total_langs = len(all_subs)

                # --- Display Info ---
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    if thumbnail_url:
                        st.image(thumbnail_url, caption="Video Thumbnail", use_container_width=True)
                
                with col2:
                    st.subheader(video_title)
                    st.write(f"**⏱️ Runtime:** {format_duration(duration)}")
                    st.write(f"**🌍 Languages Found:** {total_langs}")

                st.divider()

                # --- Subtitle Section ---
                st.subheader("⬇️ Download Raw Files")
                
                if total_langs > 0:
                    for lang, data in all_subs.items():
                        sub_type = data['type']
                        formats = data['formats']
                        
                        # Create an expander for each language to keep UI clean
                        with st.expander(f"{lang.upper()} ({sub_type})"):
                            
                            # Iterate through every format provided by Dailymotion
                            for fmt in formats:
                                ext = fmt.get('ext')
                                download_url = fmt.get('url')
                                
                                # Skip m3u8 playlists, we want the text files
                                if ext == 'm3u8':
                                    continue
                                
                                # Define the exact filename based on video title + language + raw extension
                                file_name = f"{safe_title}_{lang}.{ext}"
                                button_label = f"Download .{ext.upper()} File"
                                
                                # Fetch content immediately to serve the file
                                try:
                                    response = requests.get(download_url)
                                    if response.status_code == 200:
                                        st.download_button(
                                            label=button_label,
                                            data=response.content,
                                            file_name=file_name,
                                            mime="application/octet-stream",
                                            key=f"{lang}_{ext}_{download_url}"
                                        )
                                    else:
                                        st.warning(f"Could not retrieve .{ext} file from server.")
                                except Exception as e:
                                    st.error(f"Error downloading {ext}: {e}")
                else:
                    st.info("No subtitles found for this video.")

            else:
                st.error("Could not fetch video info. Please check the URL and try again.")
