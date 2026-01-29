import json
import pandas as pd
import pygsheets
#import json
#import macos_tags
import os
#import re
import sys
import time
import util

localDrive = '/Volumes/Moana'
cb_path = 'DEVS/PERSONAL/CinemaBin'
whereAmI = os.path.join(localDrive, cb_path)
movies_path = 'Dropbox/Videos/Movies'
localMovies = os.path.join(localDrive, movies_path)
remote_access = True
raw_sheet = "raw"
pretty_sheet = "pretty"

print("\n\n", 'CINEPHILES, SKIP THE TRAILERS! LET THE SYNC BEGIN!', "\n\n")
print(f"It is {time.strftime("%A, %Y-%m-%d %H:%M:%S %Z (%z)", time.localtime())}")

if remote_access:
  # Auth and Open 
  gc = pygsheets.authorize(service_file='credentials.json')
  sh = gc.open_by_key('1YM1bmps-gyKsHJk5B9iZv2WfiOCTZDuTDGS7_x2rov8')
  # sh = gc.open('Video Collection')
  wks = sh.worksheet_by_title(pretty_sheet) 

  print("\n\n", 'SWEEPING THE THEATER!', "\n\n")

  # Efficient Read
  df = wks.get_as_df(has_header=True)
  # df_xIDENTs = set(df['xIDENT'].dropna().unique())

  if not df.empty:
    df = df.dropna(subset=['Title'])
    dicTotals = df.iloc[0] # subheader/totals row
    rem_viddies = df.iloc[1:]
    df = df.drop(df.index[0])

    # --- 1. SAFETY BACKUP --- / must allow some transforms so it matches raw sheet, not pretty
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    backup_filename = f"video_collection_{timestamp}.csv"
    backups_path = 'backups'
    backup_path = os.path.join(whereAmI, backups_path, backup_filename)
    print(f"Creating safety backup of original remote data: {backup_path}...")
    df.to_csv(backup_path, index=False)

    print("\n", dicTotals, "\n")
    remVidzCount = len(rem_viddies)
  else:
    remVidzCount = 0
    
  print(f"Video Collection gsheet contains {remVidzCount} videos\n")

REMOTE_MOVIES_CHANGED = {'REMOTE MOVIES ADDED': {}, 'REMOTE MOVIES UPDATED': {}}

# local_xIDENTs = []
new_entries = []
has_ext_subs = []
# gather relevant info from local drive
for root, subs, files in os.walk(localMovies):
  if root.count('/') == 6: # Folder Categorization
    folder_name = '/' + util.normalize_unicode(os.path.basename(root))
    if str(folder_name) == '/untitled folder':
      sys.exit("You've got an 'untitled folder' in your Movies directory. You need to get rid of that before we can proceed.")
      
    # annoying but apparently necessary
    files = util.remove_value_from_list(files, '.DS_Store') # have definitely had this issue
    files = util.remove_value_from_list(files, 'Thumbs.db') # just to be safe

    for file in files:
      filename = util.normalize_unicode(os.path.splitext(file)[0])
      if file.endswith('.srt'):
        has_ext_subs.append(filename)
      else:
        mdata_from_name = util.parse_filename(file)
        mdata_from_name['Location'] = folder_name
        mdata_from_name['Filename or ISBN'] = str(file)

        # --- STRICT MATCHING LOGIC ---
        # We filter for rows where ALL FOUR identifiers match the current file.
        # We use .astype(str) to prevent type clashes (e.g. integer 2022 vs string "2022")
        match_mask = (
          (df['Title'].astype(str) == str(mdata_from_name['Title'])) & 
          (df['Year'].astype(str) == str(mdata_from_name['Year'])) & 
          (df['Edition'].astype(str) == str(mdata_from_name['Edition'])) & 
          (df['Resolution'].astype(str) == str(mdata_from_name['Resolution']))
        )
          
        if match_mask.any():
          # --- FOUND EXACT MATCH: UPDATE METADATA ---
          # Since Title/Year/Edition/Res are identical, we only update the technical details
          # that might have changed (e.g., you swapped an x264 encode for x265).
          
          idx = df.index[match_mask][0]
          
          # Columns we allow to be updated on a match
          cols_to_update = ['Codec', 'Audio', 'Bit Depth', 'Director', 'Format', 'Filename or ISBN']
          
          for col in cols_to_update:
            df.at[idx, col] = mdata_from_name[col]

          REMOTE_MOVIES_CHANGED['REMOTE MOVIES UPDATED'][file] = mdata_from_name
          
        else:
          # --- NO MATCH: CREATE NEW ENTRY ---
          # This happens if it's a new movie OR a new resolution/edition of an old movie.
          
          new_entries.append(mdata_from_name)

          REMOTE_MOVIES_CHANGED['REMOTE MOVIES ADDED'][file] = mdata_from_name

# 3. Batch Append and Push
if new_entries:
  new_df = pd.DataFrame(new_entries)
  df = pd.concat([df, new_df], ignore_index=True)
  
  # Optional: Sort by Title so the new additions don't just sit at the bottom
  df = df.sort_values(by=['Title', 'Year'])

  df['Subtitles'] = df['Filename or ISBN'].isin(has_ext_subs).map({True: 'Yes', False: 'No'})
  
  # --- CLEANUP: FILL NaNs ---
  # 1. Fill missing Subtitles with "No" (safer than leaving them blank)
  df['External Subtitles'] = df['External Subtitles'].fillna('No')

  # 2. Fill missing Filenames with empty strings (so they don't look like errors)
  df['Filename or ISBN'] = df['Filename or ISBN'].fillna('')
  
  # 3. (Optional) Scrub the whole dataframe to be safe
  # This catches any random NaNs in Director, Codec, etc.
  df = df.fillna('')
  # Define your "Master" column order
  desired_order = [
    'Title', 'Year', 'Edition', 'Director', 
    'Format', 'Resolution', 'Codec', 'Audio', 'Bit Depth', 
    'Location', 'External Subtitles', 'Filename or ISBN',
    'Duration'
  ]

  # 1. Reorder the DataFrame columns to match
  # (This ensures 'Resolution' is always column F, etc.)
  df = df[desired_order]
  
  has_tail = True
  while has_tail:
    tail = df.tail(1).iloc[0]
    if util.safe_str_to_int(tail['Title'], tail['Title']) == util.safe_str_to_int(tail['Title']):
      df = df.iloc[:-1]
    else:
      has_tail = False

  try:
    xwks = sh.worksheet_by_title(raw_sheet)
    xwks.clear() 
    print(f"Cleared existing '{raw_sheet}' sheet.")
  except pygsheets.WorksheetNotFound:
    xwks = sh.add_worksheet(raw_sheet, rows=100, cols=12)
    print(f"Created fresh raw data sheet: {raw_sheet}\n")

  xwks.set_dataframe(df, start='A1', copy_head=True, fit=True)

  print(f"Added {len(new_entries)} entries.")
else:
  print("No new entries found.")
  
print(f"Successfully updated {len(df)} rows in a single batch.")
  
print(json.dumps(REMOTE_MOVIES_CHANGED, indent=2, default=str))

print("\n\n", f"MOVIES LIST SYNC COMPLETE @ {time.strftime("%Y-%m-%d %H:%M:%S %Z (%z)", time.localtime())}", "\n\n")
