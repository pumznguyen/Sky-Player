class SongParseError(Exception):
    """Raised when the file format is corrupt, unparseable, or invalid JSON."""
    pass

class SongValidationError(Exception):
    """Raised when the sheet data does not conform to the required layout/schema specifications."""
    pass

def validate_song_structure(song_dict: dict, filepath_str: str) -> None:
    """Strictly validates the high-level schema structure of a song dictionary."""
    if not isinstance(song_dict, dict):
        raise SongValidationError(f"[{filepath_str}] Invalid root element: expected JSON object, got {type(song_dict).__name__}")
        
    if "songNotes" not in song_dict:
        raise SongValidationError(f"[{filepath_str}] Missing required key: 'songNotes'")
        
    song_notes = song_dict["songNotes"]
    if not isinstance(song_notes, list):
        raise SongValidationError(f"[{filepath_str}] Invalid 'songNotes': expected list, got {type(song_notes).__name__}")
