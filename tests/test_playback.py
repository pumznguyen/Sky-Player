import sys
from pathlib import Path
import pytest

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from sky_music.domain import Song, Note, NoteKey, Millis
from sky_music.scheduler import build_key_actions
from sky_music.backend import DryRunBackend
from sky_music.playback import PlaybackEngine, PLAYBACK_FINISHED

def test_dry_run_playback_execution():
    """Verify PlaybackEngine interacts correctly with the InputBackend and dispatches correct batches."""
    song = Song(
        name="Mock Playback Song",
        notes=(
            Note(time_ms=Millis(0), key=NoteKey("Key0")),
            Note(time_ms=Millis(50), key=NoteKey("Key1")),
        )
    )
    
    # Generate microsecond Actions
    sched_meta = build_key_actions(song)
    actions = sched_meta["actions"]
    
    backend = DryRunBackend()
    
    # Initialize Engine without UI rendering constraints
    engine = PlaybackEngine(
        song=song,
        actions=actions,
        backend=backend,
        telemetry_enabled=False,
        require_focus=False
    )
    
    res = engine.play()
    
    assert res == PLAYBACK_FINISHED
    
    # Assert physical key execution history
    history = backend.history
    
    # Expected chronological key actions:
    # 1. Down 'y' (0x15) at 0ms
    # 2. Up 'y' (0x15) at 20ms
    # 3. Down 'u' (0x16) at 50ms
    # 4. Up 'u' (0x16) at 70ms
    assert len(history) >= 4
    
    assert history[0] == ("down", (0x15,))
    assert history[1] == ("up", (0x15,))
    assert history[2] == ("down", (0x16,))
    assert history[3] == ("up", (0x16,))

def test_dry_run_playback_without_focus():
    """Verify that dry-run playback executes successfully without requiring active Sky window focus."""
    song = Song(
        name="Focusless Song",
        notes=(
            Note(time_ms=Millis(0), key=NoteKey("Key0")),
        )
    )
    sched_meta = build_key_actions(song)
    actions = sched_meta["actions"]
    
    backend = DryRunBackend()
    # Explicitly set require_focus = False
    engine = PlaybackEngine(
        song=song,
        actions=actions,
        backend=backend,
        telemetry_enabled=False,
        require_focus=False
    )
    
    # This must complete successfully and return PLAYBACK_FINISHED without blocking or focus-waiting
    res = engine.play()
    assert res == PLAYBACK_FINISHED
    assert len(backend.history) == 2

def test_backend_does_not_mark_keys_active_on_send_failure():
    """Verify that WinSendInputBackend does not mark keys as active if SendInput fails."""
    from sky_music.backend import WinSendInputBackend
    import types
    
    # 1. Create a dummy inputs module to mock send_scan_code_batch with error
    dummy_inputs = types.SimpleNamespace()
    def fail_send(scan_codes, key_up=False):
        raise OSError("UIPI Mismatch or injection error")
    dummy_inputs.send_scan_code_batch = fail_send
    
    backend = WinSendInputBackend()
    backend.inputs_module = dummy_inputs
    
    # Send should raise Exception
    with pytest.raises(OSError, match="UIPI Mismatch"):
        backend.key_down((0x15, 0x16))
        
    # Active keys must remain empty since the send failed
    assert len(backend.active_keys) == 0

def test_telemetry_includes_send_duration_us(tmp_path):
    """Verify that high-precision telemetry logger records and saves the send_duration_us metric."""
    import csv
    song = Song(
        name="Telemetry Song",
        notes=(
            Note(time_ms=Millis(0), key=NoteKey("Key0")),
        )
    )
    sched_meta = build_key_actions(song)
    actions = sched_meta["actions"]
    
    backend = DryRunBackend()
    engine = PlaybackEngine(
        song=song,
        actions=actions,
        backend=backend,
        telemetry_enabled=True,
        require_focus=False
    )
    # Set mock telemetry path
    engine.telemetry.log_filepath = tmp_path / "test_telemetry.csv"
    
    res = engine.play()
    assert res == PLAYBACK_FINISHED
    
    # Verify CSV content
    assert engine.telemetry.log_filepath.exists()
    with engine.telemetry.log_filepath.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        records = list(reader)
        
    assert len(records) == 2
    # Ensure send_duration_us header and record exists
    for rec in records:
        assert "send_duration_us" in rec
        assert int(rec["send_duration_us"]) >= 0

