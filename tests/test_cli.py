import sys
from pathlib import Path
import pytest

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

import main

def test_cli_basic_arguments():
    """Verify legacy arguments parse correctly with expected default structures."""
    parser = main.build_arg_parser()
    
    # Check default parses
    args = parser.parse_args([])
    assert args.song is None
    assert args.list is False
    assert args.countdown == 3
    assert args.repeat == 1
    assert args.no_clear is False
    assert args.doctor is False
    
    # Check custom parses
    args = parser.parse_args([
        "--song", "My Song",
        "--countdown", "5",
        "--repeat", "3",
        "--no-clear",
        "--list"
    ])
    assert args.song == "My Song"
    assert args.countdown == 5
    assert args.repeat == 3
    assert args.no_clear is True
    assert args.list is True

def test_cli_hotkeys_defaults():
    """Verify default hotkey binds parse securely without overlapping constraints."""
    parser = main.build_arg_parser()
    args = parser.parse_args([])
    
    assert args.pause_key == "f8"
    assert args.skip_key == "f9"
    assert args.quit_key == "esc"
    assert args.refocus_key == "f6"
    assert args.disable_hotkeys is False
    assert args.allow_note_hotkeys is False

def test_cli_playback_controls_parsing():
    """Verify PlaybackControls constructs bindings securely from CLI argument string tokens."""
    parser = main.build_arg_parser()
    
    # 1. Standard allowed defaults
    args = parser.parse_args([])
    controls = main.build_playback_controls(args)
    assert controls.pause.display == "F8"
    assert controls.skip.display == "F9"
    assert controls.quit.display == "Esc"
    assert controls.refocus.display == "F6"
    assert controls.enabled is True
    
    # 2. Disabled hotkeys
    args = parser.parse_args(["--disable-hotkeys"])
    controls = main.build_playback_controls(args)
    assert controls.enabled is False
    
    # 3. Conflict trigger (Note key 'p' overlap)
    args = parser.parse_args(["--pause-key", "p"])
    with pytest.raises(ValueError, match="Hotkey overlaps with note keys"):
        main.build_playback_controls(args)
        
    # 4. Conflict allowed explicitly
    args = parser.parse_args(["--pause-key", "p", "--allow-note-hotkeys"])
    controls = main.build_playback_controls(args)
    assert controls.pause.display == "P"
