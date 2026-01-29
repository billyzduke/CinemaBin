import os
import re
import unicodedata
from pymediainfo import MediaInfo

def normalize_unicode(s, form='NFC'):
  """
  Converts NFD (Mac style) to NFC (Web style) so names match.
  """
  if not isinstance(s, str):
    s = str(s)
  return unicodedata.normalize(form, s)

def get_video_details(filepath):
  media_info = MediaInfo.parse(filepath)
  for track in media_info.tracks:
    if track.track_type == "Video":
      return {
        "resolution": f"{track.width}x{track.height}",
        "duration_min": round(track.duration / 60000, 1), # Duration is usually in ms
        "codec": track.codec_id
      }
  return None

def parse_filename(filename):
  base_name, extension = os.path.splitext(filename)
  parts = base_name.split('-')

  # --- 0. CLEAN SPLIT TOKENS (NEW STEP) ---
  # Remove things like "1_of_2", "cd1", "part1" so they don't corrupt metadata
  parts = []
  
  # Regex for "1_of_2", "1of2"
  pat_split_xofy = re.compile(r'^\d+\s?of\s?\d+$', re.IGNORECASE)
  # Regex for "cd1", "disc1", "part1", "pt1"
  pat_split_token = re.compile(r'^(cd|disc|disk|part|pt)\s*\d+$', re.IGNORECASE)

  for part in raw_parts:
    if pat_split_xofy.match(part) or pat_split_token.match(part):
      continue # Skip this part (it's junk)
    parts.append(part)
  
  # --- 1. FIND YEAR (The Primary Anchor) ---
  year_index = -1
  for i, part in enumerate(parts):
    if re.match(r'^\d{4}$', part):
      year_index = i
      break
  
  # Safety: If no year found, return empty structure
  if year_index == -1:
    return {
      "Title": base_name, 
      "Format": extension.lstrip('.'),
      "Year": "",
      "Edition": "",
      "Director": "",
      "Resolution": "",
      "Codec": "",
      "Audio": "",
      "Bit Depth": ""
    }
  
  # --- 2. DEFINE BOUNDARIES ---
  edition = ""
  title_end = year_index
  dir_start = year_index + 1
  
  # Check for Edition (DC, RM, etc) to left or right of year
  if year_index > 0 and re.match(r'^[A-Z]{2}$', parts[year_index - 1]):
    edition = parts[year_index - 1]
    title_end = year_index - 1
  elif (year_index + 1 < len(parts)) and re.match(r'^[A-Z]{2}$', parts[year_index + 1]):
    edition = parts[year_index + 1]
    dir_start = year_index + 2

  # --- 3. FIND RESOLUTION (The Secondary Anchor) ---
  res_index = -1
  pat_res = re.compile(r'^(\d{3,4}p|4K|8K|SD)$', re.IGNORECASE)

  for i in range(dir_start, len(parts)):
    if pat_res.match(parts[i]):
      res_index = i
      break
  
  if res_index == -1:
    director_parts = parts[dir_start:]
    bag_of_tags = []
    resolution_val = ""
  else:
    director_parts = parts[dir_start:res_index]
    resolution_val = parts[res_index]
    bag_of_tags = parts[res_index+1:]

  # --- 4. PROCESS THE BAG OF TAGS ---
  data = {
    "Resolution": resolution_val,
    "Codec": "",
    "Audio": "",
    "Bit Depth": ""
  }

  # Updated Codec Pattern: Matches h264/5 AND xvid (case insensitive)
  pat_codec = re.compile(r'^(h[\.\-_]?26[45]|xvid)$', re.IGNORECASE)
  
  pat_audio = re.compile(r'^(AAC|AC|DD|DDP|DTS|TrueHD|FLAC|MP3|PCM).*', re.IGNORECASE)
  pat_bitrate = re.compile(r'.*(bit|bps)$', re.IGNORECASE)

  for tag in bag_of_tags:
    clean_tag = tag.replace('·', '.')

    if pat_codec.match(clean_tag):
      lower_tag = clean_tag.lower()
      
      # Normalize XVID to uppercase
      if "xvid" in lower_tag:
        data["Codec"] = "XVID"
      # Normalize H.265/x265 to lowercase x265
      elif "265" in lower_tag:
        data["Codec"] = "x265"
      # Default the rest to lowercase x264
      else:
        data["Codec"] = "x264"
        
    elif pat_bitrate.match(clean_tag):
      data["Bit Depth"] = clean_tag.replace('bit', '').strip()
      
    elif pat_audio.match(clean_tag):
      data["Audio"] = clean_tag

  # --- 5. TRANSLATE EDITION CODES ---
  edition_map = {
    "EX": "Extended",
    "UR": "Unrated",
    "UC": "Uncut",
    "DC": "Director's Cut",
    "RM": "Remastered",
    "SE": "Special Edition",
    "FC": "Final Cut"
  }
  
  clean_edition = edition_map.get(edition, edition)

  return {
    "Title": "-".join(parts[:title_end]).replace("_", " "),
    "Year": parts[year_index],
    "Edition": clean_edition,
    "Director": "-".join(director_parts).replace("_", " "),
    "Format": extension.lstrip('.'),
    **data
  }
# --- 5. TRANSLATE EDITION CODES ---
  edition_map = {
    "EX": "Extended",
    "UR": "Unrated",
    "UC": "Uncut",
    "DC": "Director's Cut",
    "RM": "Remastered",
    "SE": "Special Edition", # Added for good measure
    "FC": "Final Cut"        # Added for good measure
  }
  
  # Translate if found, otherwise keep original code (e.g. "DC" -> "Director's Cut")
  clean_edition = edition_map.get(edition, edition)

  return {
    "Title": "-".join(parts[:title_end]).replace("_", " "),
    "Year": parts[year_index],
    "Edition": clean_edition,  # Use the translated value here
    "Director": "-".join(director_parts).replace("_", " "),
    "Format": extension.lstrip('.'),
    **data
  }

# Convert string to integer safely in Python
def safe_str_to_int(s, return_on_fail=None):
  """
  Converts a string to an integer with error handling.
  Returns the integer if successful, or return_on_fail value if conversion fails.
  """
  try:
    # Strip whitespace and convert
    return int(str(s).strip())
  except ValueError:
    #print(f"Error: '{s}' is not a valid integer.")
    return return_on_fail
