import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from sky_music.layouts import SKY_15_KEY_PROFILE, SKY_15_KEY_MAP

def test_layout_completeness():
    """Test that default 15-key profile maps exactly 15 unique key indexes correctly."""
    key_map = SKY_15_KEY_PROFILE.key_map
    
    # Extract unique base keys (Key0 to Key14)
    base_keys = {f"Key{i}" for i in range(15)}
    
    # Assert all base keys exist in key_map
    for bk in base_keys:
        assert bk in key_map
        
    # Assert all base keys map to unique character bindings
    mapped_chars = {key_map[bk] for bk in base_keys}
    assert len(mapped_chars) == 15
    
    # Ensure they map to exactly the classic layout characters
    expected_layout = {'y', 'u', 'i', 'o', 'p', 'h', 'j', 'k', 'l', ';', 'n', 'm', ',', '.', '/'}
    assert mapped_chars == expected_layout

def test_legacy_compatibility_keys():
    """Verify prefix fallback mappings (1Key and 2Key) are preserved in layout map."""
    assert SKY_15_KEY_MAP["1Key0"] == "y"
    assert SKY_15_KEY_MAP["2Key14"] == "/"
