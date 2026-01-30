import json
import pandas as pd
import pygsheets
import os
import re
import sys
import time
import util

# --- CONFIG ---
localDrive = '/Volumes/Moana'
cb_path = 'DEVS/PERSONAL/CinemaBin'
whereAmI = os.path.join(localDrive, cb_path)
movies_path = 'Dropbox/Videos/Movies'
localMovies = os.path.join(localDrive, movies_path)
remote_access = True
raw_sheet = "raw"
pretty_sheet = "pretty"
raw_columns = [
  'Title', 'Year', 'Edition', 'Director', 
  'Format', 'Resolution', 'Codec', 'Audio', 'Bit Depth', 
  'Location', 'External Subtitles', 'Filename or ISBN', 'Duration', 'Files', 'Bonus Materials'
]

print("\n\n", 'CINEPHILES, SKIP THE TRAILERS! LET THE SYNC BEGIN!', "\n\n")
print(f"It is {time.strftime('%A, %Y-%m-%d %H:%M:%S %Z (%z)', time.localtime())}")

# --- 1. CONNECT & LOAD (READ-ONLY FROM PRETTY) ---
if remote_access:
  # Auth and Open 
  gc = pygsheets.authorize(service_file='credentials.json')
  sh = gc.open_by_key('1YM1bmps-gyKsHJk5B9iZv2WfiOCTZDuTDGS7_x2rov8')
  # sh = gc.open('Video Collection')
  wks = sh.worksheet_by_title(pretty_sheet) 

  print("\n\n", 'SWEEPING THE THEATER!', "\n\n")

  df = wks.get_as_df(has_header=True)
  # df_xIDENTs = set(df['xIDENT'].dropna().unique())

  if not df.empty and 'Title' in df.columns:
    df = df.dropna(subset=['Title'])
    dicTotals = df.iloc[0] # subheader/totals row
    rem_viddies = df.iloc[1:]
    df = df.drop(df.index[0])

    # --- SAFETY BACKUP ---
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    backup_filename = f"video_collection_{timestamp}.csv"
    backups_path = 'backups'
    backup_path = os.path.join(whereAmI, backups_path, backup_filename)
    print(f"Creating safety backup of original remote data: {backup_path}...")
    df.to_csv(backup_path, index=False)

    print("\n", dicTotals, "\n")
    remVidzCount = len(rem_viddies)
  else:
    df = pd.DataFrame(columns=raw_columns)
    remVidzCount = 0
    
  print(f"Video Collection gsheet contains {remVidzCount} videos\n")

REMOTE_MOVIES_CHANGED = {'REMOTE MOVIES ADDED': {}, 'REMOTE MOVIES UPDATED': {}}

# local_xIDENTs = []
# --- 2. AGGREGATE LOCAL FILES (Handle Multi-Part Movies) ---
# We scan everything first to group parts together.
# Key = Unique Tuple (Title, Year, Edition, Resolution)
local_inventory = {}
has_ext_subs = {}

# Regex to verify if a suffix is actually a 'part' tag
# Matches: .2_of_2, .CD1, .Part1, .pt2 (case insensitive)
pat_part_suffix = re.compile(r'^\.(?:cd|disc|disk|part|pt|\d+_of_)\d+$', re.IGNORECASE)

print(f"Scanning: {localMovies}")

for root, dirs, files in os.walk(localMovies):
  if root.count('/') == 6: 
    folder_name = '/' + util.normalize_unicode(os.path.basename(root))
    
    if str(folder_name) == '/untitled folder':
      sys.exit("Error: 'untitled folder' detected.")
      
    files = util.remove_value_from_list(files, '.DS_Store') 
    files = util.remove_value_from_list(files, 'Thumbs.db') 

    for file in files:
      filename, ext = os.path.splitext(file)
      filename = util.normalize_unicode(filename)
      
      # CAPTURE SUB EXTENSIONS
      if ext.lower() in ['.srt', '.sub', '.vtt', '.idx', '.ass']:   
        has_ext_subs[filename] = os.path.splitext(file)[1]
        
        # We need to strip the part tag from subs too so they map to the movie!
        # e.g. "Movie.Part1.srt" -> should map to "Movie"
        clean_sub_name = filename
        root_check, possible_part = os.path.splitext(filename)
        if pat_part_suffix.match(possible_part):
          clean_sub_name = root_check
          
        has_ext_subs[clean_sub_name] = ext
        
      elif ext.lower() in ['.mkv', '.mp4', '.avi', '.iso']:    # Parse
        # --- THE DOUBLE SPLIT ---
        # Check if we have a secondary extension like ".CD1" or ".2_of_2"
        clean_filename = filename
        root_check, possible_part = os.path.splitext(filename)
        
        if pat_part_suffix.match(possible_part):
          # It is a part tag! Strip it.
          # "Movie-2003...XVID.2_of_2" -> "Movie-2003...XVID"
          clean_filename = root_check

        # Reconstruct a "clean" filename for the parser to read
        # "Movie-2003...XVID" + ".mkv"
        clean_file_for_parsing = clean_filename + ext
        
        # Parse the CLEAN filename (so the parser doesn't see ".2_of_2")
        mdata = util.parse_filename(clean_file_for_parsing)
                
        # Add critical tracking data
        mdata['Location'] = folder_name
        mdata['Filename or ISBN'] = str(file)

        # Create Unique ID for this movie (Groups Part 1 & Part 2)
        unique_key = (
          str(mdata['Title']), 
          str(mdata['Year']), 
          str(mdata['Edition']), 
          str(mdata['Resolution'])
        )

        if unique_key in local_inventory:
          # FOUND ANOTHER PART OF AN EXISTING MOVIE
          local_inventory[unique_key]['Files'] += 1
          
          # Keep the alphabetically first filename (e.g. keep "Movie - Part 1.mkv")
          current_file = local_inventory[unique_key]['Filename or ISBN']
          if file < current_file:
            local_inventory[unique_key]['Filename or ISBN'] = file
        else:
          # FIRST TIME SEEING THIS MOVIE
          mdata['Files'] = 1
          local_inventory[unique_key] = mdata

print(f"Found {len(local_inventory)} unique movies locally.")

# --- 3. SYNC TO SHEET ---
new_entries = []

for mdata in local_inventory.values():
  # Strict Match Logic
  match_mask = (
    (df['Title'].astype(str) == str(mdata['Title'])) & 
    (df['Year'].astype(str) == str(mdata['Year'])) & 
    (df['Edition'].astype(str) == str(mdata['Edition'])) & 
    (df['Resolution'].astype(str) == str(mdata['Resolution']))
  )
    
  if match_mask.any():
    # --- UPDATE EXISTING ---
    idx = df.index[match_mask][0]
    
    # Added 'Files' and 'Filename or ISBN' to update list
    cols_to_update = [
      'Codec', 'Audio', 'Bit Depth', 'Director', 
      'Format', 'Location', 'Filename or ISBN', 'Files'
    ]
    
    for col in cols_to_update:
      if col in mdata:
        df.at[idx, col] = mdata[col]

    REMOTE_MOVIES_CHANGED['REMOTE MOVIES UPDATED'][mdata['Filename or ISBN']] = mdata
    
  else:
    # --- ADD NEW ---
    new_entries.append(mdata)
    REMOTE_MOVIES_CHANGED['REMOTE MOVIES ADDED'][mdata['Filename or ISBN']] = mdata

# --- 4. MERGE & WRITE ---
if new_entries:
  new_df = pd.DataFrame(new_entries)
  df = pd.concat([df, new_df], ignore_index=True)

if not df.empty:
  # Sort
  df = df.sort_values(by=['Title', 'Year'])

  # Cleanup NaNs (Critical for Filename logic)
  df = df.fillna('')
  
  # Ensure 'Files' column exists for old data
  if 'Files' not in df.columns:
    df['Files'] = 1
  else:
    # Make sure we don't have empty strings in Files column
    df['Files'] = pd.to_numeric(df['Files'], errors='coerce').fillna(1)

  # Look up the extension based on the movie filename (without extension)
  df['External Subtitles'] = df['Filename or ISBN'].apply(
    lambda x: has_ext_subs.get(util.normalize_unicode(os.path.splitext(x)[0]), "").lstrip('.')
  )

  # Reindex
  df = df.reindex(columns=raw_columns)
  
  # Remove tail if it's junk (legacy logic)
  has_tail = True
  while has_tail and len(df) > 0:
    tail = df.tail(1).iloc[0]
    # Check if Title is valid (adjust logic as needed for your data)
    if util.safe_str_to_int(tail['Title'], tail['Title']) == util.safe_str_to_int(tail['Title']):
      df = df.iloc[:-1]
    else:
      has_tail = False

  # Write to RAW Sheet (Clear & Write)
  try:
    xwks = sh.worksheet_by_title(raw_sheet)
    xwks.clear() 
    print(f"Cleared existing '{raw_sheet}' sheet.")
  except pygsheets.WorksheetNotFound:
    xwks = sh.add_worksheet(raw_sheet, rows=len(df)+50, cols=26)
    print(f"Created fresh raw data sheet: {raw_sheet}\n")

  xwks.set_dataframe(df, start='A1', copy_head=True, fit=True)
  print(f"Successfully wrote {len(df)} rows.")
  print(f"Added {len(new_entries)} new entries.")

else:
  print("No entries to process.")
  
print(json.dumps(REMOTE_MOVIES_CHANGED, indent=2, default=str))
print("\n\n", f"SYNC COMPLETE @ {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}", "\n\n")