import sys
from pathlib import Path
import pytest
from sky_music.config import AppConfig, clear_config_cache

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

import main

@pytest.fixture(autouse=True)
def _reset_config_cache():
    clear_config_cache()
    yield
    clear_config_cache()

def test_cli_song_argument_parsing():
    parser = main.build_arg_parser()
    args = parser.parse_args(["--song", "Diamonds"])
    assert args.song == "Diamonds"

def test_cli_list_argument():
    parser = main.build_arg_parser()
    args = parser.parse_args(["--list"])
    assert args.list is True

def test_txt_song_extension_is_supported():
    from sky_music.ui.picker_helpers import SUPPORTED_EXTENSIONS

    assert ".txt" in SUPPORTED_EXTENSIONS

def test_cli_fps_argument_applies_timing_policy():
    parser = main.build_arg_parser()
    args = parser.parse_args(["--fps", "60"])
    main.configure_from_args(args, AppConfig())
    from sky_music.domain.scheduler_types import FrameTimingPolicy
    assert isinstance(main.TIMING_POLICY, FrameTimingPolicy)
    assert main.TIMING_POLICY.fps == 60

def test_cli_theme_argument():
    parser = main.build_arg_parser()
    args = parser.parse_args(["--theme", "cyberpunk"])
    assert args.theme == "cyberpunk"

def test_cli_repeat_argument():
    parser = main.build_arg_parser()
    args = parser.parse_args(["--repeat", "5"])
    assert args.repeat == 5

def test_cli_countdown_argument():
    parser = main.build_arg_parser()
    args = parser.parse_args(["--countdown", "10"])
    assert args.countdown == 10

def test_cli_doctor_flags():
    parser = main.build_arg_parser()
    args = parser.parse_args(["--doctor"])
    assert args.doctor is True
    args = parser.parse_args(["--doctor-timing"])
    assert args.doctor_timing is True
    args = parser.parse_args(["--doctor-input"])
    assert args.doctor_input is True

def test_cli_save_calibration_argument():
    parser = main.build_arg_parser()
    args = parser.parse_args(["--save-calibration"])
    assert args.save_calibration is True

def test_cli_calibration_summary_argument():
    parser = main.build_arg_parser()
    args = parser.parse_args(["--calibration-summary", "logs/run.summary.json"])
    assert args.calibration_summary == Path("logs/run.summary.json")
