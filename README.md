# 🎵 Sky Children of the Light: PC Automatic Music Player

An ultra-precise, state-of-the-art automatic music player designed for **Sky: Children of the Light** on PC. This application simulates physical keyboard scan codes in real-time, reading JSON or skysheet song files downloaded from specy/skyMusic.

> [!WARNING]
> Automatically playing music sheets or using simulated keystrokes might violate Thatgamecompany's Terms of Service. Use this tool responsibly and at your own risk.

---

## 🛠️ Setup & Installation

### Requirements
* Operating System: **Windows 10 or 11**
* Environment: **Python >= 3.14** (Managing with [uv](https://github.com/astral-sh/uv) is highly recommended for optimal performance)

### 1. Launching the App
Open your Sky game first. Then open your terminal in this repository folder and run:
```bash
# Recommended: Using uv project script
uv run player

# Or using the quick script (Windows):
.\play

# Or using the quick script (Linux/macOS):
./play
```

### 2. Finding & Selecting Songs
* In the selection menu, you can enter the **song number**, its **exact name**, or a **fuzzy query** (case-insensitive keyword matching) to load songs instantly.
* Example: Type `flower` to match and play *Flower Dance.json*.
* Type `r` or `refresh` to scan and update the playlist without restarting the program.
* Type `q`, `quit`, `exit`, or `0` to quit.

### 3. Run System Diagnostics
If key strokes are not being received or the game window is not detected, run the automatic diagnostic suite:
```bash
# Using the uv project script:
uv run player --doctor

# Or using the quick script (Windows):
.\play --doctor
```

---

## ⚙️ Advanced CLI Configuration Options

Customize your playing experience using the following command-line flags:
```text
  --song SONG                Play a song immediately by number, name, partial keyword, or file path
  --list                     List all available songs in the songs folder and exit
  --countdown COUNTDOWN      Seconds to count down before playing (Default: 3)
  --repeat REPEAT            Number of times to repeat the selected song (Default: 1)
  --no-clear                 Do not clear the terminal console after a song ends
  --scan-code-mode {physical,mapped}
                             physical: Standard QWERTY layout scan codes (Recommended)
                             mapped: Automatically maps scan codes based on active OS keyboard layout
  --sky-process-names NAMES  Comma-separated list of expected Sky game executable process names
  --allow-title-fallback     Allow window title matching fallback if process checks fail
  --debug-playback           Enable time-buffered logging of precise playback latency in logs/
  --pause-key KEY            Customize global hotkey to pause/resume playback (Default: F8)
  --skip-key KEY             Customize global hotkey to skip a song (Default: F9)
  --quit-key KEY             Customize global hotkey to quit the program (Default: Esc)
  --refocus-key KEY          Customize global hotkey to focus the Sky game window (Default: F6)
  --disable-hotkeys          Disable all hotkeys completely (use Ctrl+C to terminate)
```

---

## 🎵 How to Download More Songs

1. Visit the library page on [Sky Music Nightly](https://specy.github.io/skyMusic/).
2. Search for any song of your choice and click download under the **JSON** or **skysheet** format.
3. Save the downloaded file inside the `songs/` directory.
4. Type `r` at the selection prompt to instantly reload and see your newly added songs in the list!
