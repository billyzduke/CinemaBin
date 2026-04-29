import os
import re
import unicodedata
from pymediainfo import MediaInfo

def decode_safe_filename(filename):
  if not filename:
    return ""
  
  filename = filename.replace('·', '.')
  filename = filename.replace('_', ' ')
  filename = filename.replace('+', ', ')
  filename = filename.replace('¿', '?')
  filename = filename.replace('--', '/')
  filename = filename.replace('±', '*')
  filename = filename.replace('÷', ': ')
  filename = filename.replace("''", '"')
  #filename = filename.replace('&', ' & ')
  return filename.strip()

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

def normalize_unicode(s, form='NFC'):
  """
  Converts NFD (Mac style) to NFC (Web style) so names match.
  """
  if not isinstance(s, str):
    s = str(s)
  return unicodedata.normalize(form, s)

def parse_filename(filename):
  base_name, extension = os.path.splitext(filename)
  base_name = decode_safe_filename(base_name)

  raw_parts = base_name.split('-')

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

  # --- 3. FIND TECH START (Boundary Detection) ---
  # We look for ANY technical tag to stop the Director scanner.
  tech_start_index = -1

  # REGEX FIX: Added [hx] to catch x264/x265, and added hevc
  pat_res = re.compile(r'^(\d{3,4}p|4K|8K|SD)$', re.IGNORECASE)
  pat_codec_broad = re.compile(r'^([hx][\.\-_]?26[45]|hevc|xvid|avc)$', re.IGNORECASE)
  pat_audio_broad = re.compile(r'^(AAC|AC|DD|DDP|DTS|TrueHD|FLAC|MP3|PCM|Opus)', re.IGNORECASE)
  pat_bitdepth_broad = re.compile(r'^\d+bit$', re.IGNORECASE)
  
  for i in range(dir_start, len(parts)):
    part = parts[i]
    
    if (pat_res.match(part) or 
        pat_codec_broad.match(part) or 
        pat_bitdepth_broad.match(part) or
        pat_audio_broad.match(part)):
      tech_start_index = i
      break
  
  if tech_start_index == -1:
    director_parts = parts[dir_start:]
    bag_of_tags = []
  else:
    director_parts = parts[dir_start:tech_start_index]
    bag_of_tags = parts[tech_start_index:]

  # --- 4. PROCESS THE BAG OF TAGS ---
  data = {
    "Resolution": "",
    "Codec": "",
    "Audio": "",
    "Bit Depth": ""
  }
  
  # Regex Definitions
  pat_res = re.compile(r'^(\d{3,4}p|4K|8K|SD)$', re.IGNORECASE)
  pat_codec = re.compile(r'^([hx]26[45]|hevc|xvid|avc)$', re.IGNORECASE)
  pat_audio = re.compile(r'^(AAC|AC|DD|DDP|DTS|TrueHD|FLAC|MP3|PCM|Opus)', re.IGNORECASE)
  pat_channels = re.compile(r'^(\d+)ch$', re.IGNORECASE)
  pat_bitdepth = re.compile(r'^\d+bit$', re.IGNORECASE) # Matches "10bit"

  # Temporary holders to avoid overwriting
  found_audio_codec = ""
  found_audio_channels = ""
  unknown_tags = []

  for tag in bag_of_tags:
    lower_tag = tag.lower()

    # VIDEO RESOLUTION
    if pat_res.match(lower_tag):
      data["Resolution"] = lower_tag
    
    # VIDEO CODEC
    elif pat_codec.match(lower_tag):
      if "xvid" in lower_tag:
        data["Codec"] = "XVID"
      elif "265" in lower_tag or "hevc" in lower_tag:
        data["Codec"] = "x265"
      else:
        data["Codec"] = "x264"

    # BIT DEPTH (Video)
    elif pat_bitdepth.match(lower_tag):
      data["Bit Depth"] = lower_tag.replace('bit', '').strip()

    # AUDIO CODEC (e.g. AAC, DTS)
    elif pat_audio.match(lower_tag):
      found_audio_codec = lower_tag.upper()

    # D. AUDIO CHANNELS (e.g. 6CH, 2CH)
    elif pat_channels.match(lower_tag):
      ch_num = int(pat_channels.match(lower_tag).group(1))
      if ch_num == 6:
        found_audio_channels = "5.1"
      elif ch_num == 8:
        found_audio_channels = "7.1"
      elif ch_num == 2:
        found_audio_channels = "2.0"
      elif ch_num == 1:
        found_audio_channels = "1.0"
        
    # UNKNOWN TAGS
    else:
      if len(lower_tag) > 1:
        unknown_tags.append(lower_tag)
      
  # --- MERGE AUDIO LOGIC ---
  # Combine codec and channels (e.g., "AAC" + "5.1" -> "AAC 5.1")
  # Check if codec string already has the channel info (e.g. "DD5.1") to avoid "DD5.1 5.1"
  if found_audio_channels and (found_audio_channels not in found_audio_codec):
    data["Audio"] = f"{found_audio_codec} {found_audio_channels}".strip()
  else:
    data["Audio"] = found_audio_codec
    
  # --- 5. FINALIZE DIRECTOR ---
  final_director_parts = director_parts
  
  # Rescue unknown tags if director was empty
  if not final_director_parts and unknown_tags:
      final_director_parts = unknown_tags

  director_string = "-".join(final_director_parts).replace("_", " ").replace("+", " & ")

  # --- 5. TRANSLATE EDITION CODES ---
  edition_map = {
    "CC": "Criterion Collection",
    "DC": "Director's Cut",
    "EX": "Extended",
    "FC": "Final Cut",
    "FE": "Fan Edit",
    "RM": "Remastered",
    "SE": "Special Edition",
    "UR": "Unrated",
    "UC": "Uncut",
  }
  
  clean_edition = edition_map.get(edition, edition)

  return {
    "Title": "-".join(parts[:title_end]).replace("_", " "),
    "Year": parts[year_index],
    "Edition": clean_edition,
    "Director": director_string,
    "Format": extension.lstrip('.'),
    **data
  }

def remove_value_from_list(arr, value):
  """
  Removes all occurrences of 'value' from the list 'arr'.
  Returns the updated list.
  """
  if not isinstance(arr, list):
    #raise TypeError("arr must be a list")
    return arr

  # Check if value exists
  if value not in arr:
    #print(f"Value '{value}' not found in list.")
    return arr

  # Remove all occurrences
  arr = [item for item in arr if item != value]
  #print(f"Value '{value}' removed successfully.")
  return arr

def safe_str_to_int(s, return_on_fail=None):
  """
  Convert string to integer safely in Python with error handling.
  Returns the integer if successful, or return_on_fail value if conversion fails.
  """
  try:
    # Strip whitespace and convert
    return int(str(s).strip())
  except ValueError:
    #print(f"Error: '{s}' is not a valid integer.")
    return return_on_fail
