import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import io
import zipfile
import requests
import textwrap
import os
import re

# --- CONSTANTS ---
MAX_WIDTH = 1700
POS_TITLE = (2100, 300)
POS_PRONUNCIATION = (2100, 1000)
POS_DEFINITION = (2100, 1300)
SPACING = 100

# --- FONT LOADING ---
# We need to ensure fonts are available. 
# In Streamlit Cloud, we'll deploy the font files with the app.
FONT_FILES = {
    'normal': 'Cabin-Variable.ttf',
    'italic': 'Cabin-Italic-Variable.ttf'
}

STYLES = {
    'Title': {'size': 255, 'font_file': 'normal', 'variation': 'Bold', 'pos': POS_TITLE},
    'Pronunciation': {'size': 116, 'font_file': 'italic', 'variation': 'Italic', 'pos': POS_PRONUNCIATION},
    'Definition': {'size': 157, 'font_file': 'normal', 'variation': 'Medium', 'pos': POS_DEFINITION}
}

def load_font(font_file, size, variation=None):
    try:
        font = ImageFont.truetype(font_file, size)
        if variation and hasattr(font, 'set_variation_by_name'):
            try:
                font.set_variation_by_name(variation)
            except:
                if variation == 'Bold':
                    try: font.set_variation_by_axes([700])
                    except: pass
                elif variation == 'Medium':
                    try: font.set_variation_by_axes([500])
                    except: pass
        return font
    except Exception as e:
        return ImageFont.load_default()

def draw_text_wrapped(draw, text, pos, max_width, font_file, max_size, variation, fill="black", line_spacing=1.2):
    font = load_font(font_file, max_size, variation)
    
    words = text.split()
    if not words: return
    
    longest_word = max(words, key=len)
    bbox = draw.textbbox((0, 0), longest_word, font=font)
    while (bbox[2] - bbox[0]) > max_width and max_size > 10:
        max_size = int(max_size * 0.9)
        font = load_font(font_file, max_size, variation)
        bbox = draw.textbbox((0, 0), longest_word, font=font)
        
    avg_char_width = draw.textlength("x", font=font)
    width_in_chars = int(max_width / (avg_char_width * 0.8))
    lines = textwrap.wrap(text, width=width_in_chars)
    
    # Refined wrapping
    current_font = font
    final_lines = []
    current_line = []
    for word in words:
        test_line = ' '.join(current_line + [word])
        w = draw.textlength(test_line, font=current_font)
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line: final_lines.append(' '.join(current_line))
            current_line = [word]
    if current_line: final_lines.append(' '.join(current_line))
        
    x, y = pos
    line_height = getattr(current_font, 'size', max_size) * line_spacing
    for line in final_lines:
        draw.text((x, y), line, font=current_font, fill=fill)
        y += line_height

def calculate_text_height(draw, text, font_file, max_size, variation, max_width, wrapped=False, line_spacing=1.2):
    font = load_font(font_file, max_size, variation)
    if wrapped:
        words = text.split()
        if not words: return 0, font, 0
        
        longest_word = max(words, key=len)
        bbox = draw.textbbox((0, 0), longest_word, font=font)
        while (bbox[2] - bbox[0]) > max_width and max_size > 10:
            max_size = int(max_size * 0.9)
            font = load_font(font_file, max_size, variation)
            bbox = draw.textbbox((0, 0), longest_word, font=font)
            
        current_font = font
        lines = []
        current_line = []
        for word in words:
            test_line = ' '.join(current_line + [word])
            w = draw.textlength(test_line, font=current_font)
            if w <= max_width:
                current_line.append(word)
            else:
                if current_line: lines.append(' '.join(current_line))
                current_line = [word]
        if current_line: lines.append(' '.join(current_line))
        
        line_count = len(lines)
        line_height = getattr(current_font, 'size', max_size) * line_spacing
        return line_count * line_height, current_font, line_count
    else:
        return getattr(font, 'size', max_size) * 1.2, font, 1

# --- STREAMLIT APP ---
st.set_page_config(page_title="Bulk Image Generator", layout="wide")
st.title("🖼️ Bulk Image Generator")
st.markdown("Generate images from a Google Sheet and a Template.")

# 1. INPUTS
col1, col2 = st.columns(2)

with col1:
    sheet_url = st.text_input("Google Sheet URL (Must be 'Anyone with link can view')")
    
with col2:
    uploaded_template = st.file_uploader("Upload Template Image (PNG)", type="png")

if st.button("Generate Images") and sheet_url and uploaded_template:
    with st.spinner("Processing..."):
        try:
            # 1. Load Sheet Data
            # Robust URL conversion using Regex to find the Sheet ID
            sheet_id_match = re.search(r'/d/([a-zA-Z0-9-_]+)', sheet_url)
            if sheet_id_match:
                sheet_id = sheet_id_match.group(1)
                export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
            else:
                st.error("Invalid Google Sheet URL. Could not find Sheet ID.")
                st.stop()
                
            st.write(f"Debug: Fetching CSV from: `{export_url}`") # Optional: Show user what URL is being used
                
            df = pd.read_csv(export_url)
            st.success(f"Loaded {len(df)} rows from Google Sheet!")
            
            # 2. Load Template
            template_image = Image.open(uploaded_template).convert("RGBA")
            
            # 3. Prepare ZIP buffer
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                
                progress_bar = st.progress(0)
                
                for index, row in df.iterrows():
                    # Create layer
                    txt_layer = Image.new("RGBA", template_image.size, (255, 255, 255, 0))
                    draw = ImageDraw.Draw(txt_layer)
                    image_height = template_image.size[1]
                    
                    title_text = str(row['Title'])
                    pron_text = str(row['Pronunciation'])
                    def_text = str(row['Definition'])
                    
                    # --- SMART LOGIC ---
                    title_size = STYLES['Title']['size']
                    h_title, f_title, title_lines = calculate_text_height(
                        draw, title_text, FONT_FILES['normal'], title_size, 'Bold', MAX_WIDTH, wrapped=True, line_spacing=1.0
                    )
                    if title_lines > 3:
                        title_size -= 20
                        h_title, f_title, title_lines = calculate_text_height(
                            draw, title_text, FONT_FILES['normal'], title_size, 'Bold', MAX_WIDTH, wrapped=True, line_spacing=1.0
                        )

                    def_size = STYLES['Definition']['size']
                    h_def, f_def, line_count = calculate_text_height(
                        draw, def_text, FONT_FILES['normal'], def_size, 'Medium', MAX_WIDTH, wrapped=True, line_spacing=1.2
                    )
                    if line_count > 5:
                        def_size = 130
                        h_def, f_def, line_count = calculate_text_height(
                            draw, def_text, FONT_FILES['normal'], def_size, 'Medium', MAX_WIDTH, wrapped=True, line_spacing=1.2
                        )
                        
                    h_pron, f_pron, _ = calculate_text_height(draw, pron_text, FONT_FILES['italic'], STYLES['Pronunciation']['size'], 'Italic', MAX_WIDTH, wrapped=True, line_spacing=1.2)

                    # Layout
                    total_height = h_title + SPACING + h_pron + SPACING + h_def
                    start_y = (image_height - total_height) / 2
                    
                    # Draw
                    draw_text_wrapped(draw, title_text, (POS_TITLE[0], start_y), MAX_WIDTH, FONT_FILES['normal'], getattr(f_title, 'size', title_size), 'Bold', line_spacing=1.0)
                    
                    current_y = start_y + h_title + SPACING
                    draw_text_wrapped(draw, pron_text, (POS_PRONUNCIATION[0], current_y), MAX_WIDTH, FONT_FILES['italic'], getattr(f_pron, 'size', STYLES['Pronunciation']['size']), 'Italic', line_spacing=1.2)
                    
                    current_y = current_y + h_pron + SPACING
                    draw_text_wrapped(draw, def_text, (POS_DEFINITION[0], current_y), MAX_WIDTH, FONT_FILES['normal'], getattr(f_def, 'size', def_size), 'Medium', line_spacing=1.2)

                    # Composite
                    out = Image.alpha_composite(template_image, txt_layer)
                    
                    # Save to buffer
                    img_buffer = io.BytesIO()
                    out.save(img_buffer, format="PNG")
                    
                    safe_name = "".join([c for c in title_text if c.isalnum() or c in (' ', '-', '_')]).strip()
                    zip_file.writestr(f"{safe_name}.png", img_buffer.getvalue())
                    
                    progress_bar.progress((index + 1) / len(df))
            
            st.success("Processing Complete!")
            
            # Download Button
            st.download_button(
                label="Download ZIP",
                data=zip_buffer.getvalue(),
                file_name="generated_images.zip",
                mime="application/zip"
            )
            
        except Exception as e:
            st.error(f"An error occurred: {e}")
