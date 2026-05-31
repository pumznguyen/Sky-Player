from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sky_music.domain.session_context import PlaybackSessionContext
from sky_music.domain.song_repository import get_shared_song_repository

@dataclass(frozen=True, slots=True)
class SongUiMetadata:
    path: Path
    name: str
    duration_seconds: float
    note_count: int
    max_polyphony: int
    min_note_gap_ms: float
    min_same_key_gap_ms: float
    risk: Literal["low", "medium", "high", "error"]
    recommended_profile: str
    recommended_tempo_scale: float
    warnings: tuple[str, ...]
    average_notes_per_second: float = 0.0
    peak_notes_per_second_1s: float = 0.0
    impossible_repeats: int = 0
    max_chord_size: int = 0
    chords_count: int = 0
    timing_stress_rate: float = 0.0

_metadata_cache: dict[tuple, SongUiMetadata] = {}
_song_repository = get_shared_song_repository()

def get_song_ui_metadata(
    song_path: Path,
    session: PlaybackSessionContext | None = None,
) -> SongUiMetadata:
    session = session or PlaybackSessionContext.balanced()
    try:
        from sky_music.domain.scheduler import build_key_actions
        from sky_music.domain.analyzer import analyze_schedule

        import sys
        resolver = None
        if sys.platform == "win32":
            from sky_music.platform.win32.keycodes import Win32NoteResolver
            from sky_music.layouts import SKY_15_KEY_PROFILE
            resolver = Win32NoteResolver(SKY_15_KEY_PROFILE)

        song = _song_repository.load(song_path)
        policy = session.resolve_effective_policy()
        sched = build_key_actions(
            song,
            policy=policy,
            scan_code_mode=session.scan_code_mode,
            resolver=resolver,
            tempo_scale=session.tempo_scale,
        )
        report = analyze_schedule(sched, raw_notes=song.notes)

        rec_profile = report.suggested_profile
        rec_tempo = report.suggested_tempo_scale

        min_note_gap = (report.min_any_note_gap_us / 1000.0) if report.min_any_note_gap_us is not None else 0.0
        min_repeat_gap = (report.min_same_key_gap_us / 1000.0) if report.min_same_key_gap_us is not None else 0.0

        return SongUiMetadata(
            path=song_path,
            name=song.name or song_path.stem,
            duration_seconds=sched.source_duration_us / 1_000_000,
            note_count=sched.note_count,
            max_polyphony=report.max_polyphony,
            min_note_gap_ms=min_note_gap,
            min_same_key_gap_ms=min_repeat_gap,
            risk=report.severity,
            recommended_profile=rec_profile,
            recommended_tempo_scale=rec_tempo,
            warnings=report.recommendations,
            average_notes_per_second=report.average_notes_per_second,
            peak_notes_per_second_1s=report.peak_notes_per_second_1s,
            impossible_repeats=report.impossible_repeats,
            max_chord_size=report.max_chord_size,
            chords_count=report.chords_count,
            timing_stress_rate=report.timing_stress_rate
        )
    except Exception as e:
        return SongUiMetadata(
            path=song_path,
            name=song_path.stem,
            duration_seconds=0.0,
            note_count=0,
            max_polyphony=0,
            min_note_gap_ms=0.0,
            min_same_key_gap_ms=0.0,
            risk="error",
            recommended_profile="unplayable",
            recommended_tempo_scale=1.0,
            warnings=(f"Failed to analyze song: {e}",),
            average_notes_per_second=0.0,
            peak_notes_per_second_1s=0.0,
            impossible_repeats=0,
            max_chord_size=0,
            chords_count=0,
            timing_stress_rate=0.0
        )

def get_cached_song_ui_metadata(
    song_path: Path,
    session: PlaybackSessionContext | None = None,
) -> SongUiMetadata:
    session = session or PlaybackSessionContext.balanced()
    try:
        song_file_key = _song_repository.cache_key(song_path)
    except Exception:
        return get_song_ui_metadata(song_path, session)

    cache_key = session.metadata_cache_key(song_file_key)
    if cache_key not in _metadata_cache:
        _metadata_cache[cache_key] = get_song_ui_metadata(song_path, session)
    return _metadata_cache[cache_key]

def clear_metadata_cache() -> None:
    _metadata_cache.clear()
    _song_repository.clear()

def _get_song_recommendation(
    song_path: Path,
    session: PlaybackSessionContext | None = None,
) -> tuple[str, float]:
    meta = get_cached_song_ui_metadata(song_path, session)
    return meta.recommended_profile, meta.recommended_tempo_scale
