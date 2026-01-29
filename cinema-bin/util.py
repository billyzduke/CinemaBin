import unicodedata

def normalize_unicode(s, form='NFC'):
  """
  Converts NFD (Mac style) to NFC (Web style) so names match.
  """
  if not isinstance(s, str):
    s = str(s)
  return unicodedata.normalize(form, s)
