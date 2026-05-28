# 🎵 Sky Children of the Light: PC Automatic Music Player

An ultra-precise, automatic music player designed for **Sky: Children of the Light** on PC. It reads JSON or skysheet song files downloaded from specy/skyMusic and simulates keyboard keypresses in real-time.

> [!WARNING]
> Automatically playing music sheets or using simulated keystrokes might violate Thatgamecompany's Terms of Service. Use this tool responsibly and at your own risk.

---

## 🛠️ Setup & Installation

### Requirements
* Operating System: **Windows 10 or 11**
* Environment: **Python >= 3.10**

---

### Option 1: Using Standard Python (Without `uv`)

If you already have Python installed on your system:

1. **Install Dependencies:**
   Open your terminal in this repository folder and run:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the App:**
   ```bash
   python src/main.py
   # Or using the quick script:
   .\play.bat
   ```

---

### Option 2: Using `uv` (Recommended)

If you use [uv](https://github.com/astral-sh/uv) for fast, isolated Python virtual environments:

1. **Run directly:**
   ```bash
   uv run play
   # Or using the quick script:
   .\play.bat
   ```

> [!TIP]
> **Quick Start Scripts:** Both `.\play.bat` (Windows) and `./play` (Linux/macOS) are smart! They will automatically detect if `uv` is installed to run the app, and seamlessly fall back to standard `python` if it isn't.

---

## 🎵 How to Use

1. **Open your Sky game** first.
2. **Launch the player** using one of the run commands above.
3. **Select a song**: 
   * Type the song number, name, or a search keyword.
   * Type `r` or `refresh` to reload the `songs/` folder without restarting.
   * Type `q` or `Esc` to quit.

### ➕ Adding More Songs
1. Go to [Sky Music Nightly](https://specy.github.io/skyMusic/).
2. Download any song in **JSON** or **skysheet** format.
3. Save the downloaded file inside the `songs/` directory.
4. Type `r` in the player selection screen to instantly load the new songs!

---

## ⚙️ CLI Configuration Options

Customize your experience by passing arguments:
```bash
python src/main.py [OPTIONS]
# or: uv run play [OPTIONS]
```

<details>
<summary><b>Click to expand CLI arguments</b></summary>

```text
  --song SONG                Play a song immediately by number, name, keyword, or path
  --list                     List all available songs and exit
  --countdown COUNTDOWN      Seconds to count down before playing (Default: 3)
  --repeat REPEAT            Number of times to repeat the song (Default: 1)
  --no-clear                 Do not clear the console after a song ends
  --scan-code-mode {physical,mapped}
                             physical: Standard QWERTY layout scan codes (Recommended)
                             mapped: Maps based on active OS keyboard layout
  --sky-process-names NAMES  Comma-separated list of expected Sky game process names
  --allow-title-fallback     Allow window title matching fallback if process checks fail
  --debug-playback           Enable latency logging in logs/
  --pause-key KEY            Pause/resume hotkey (Default: F8)
  --skip-key KEY             Skip song hotkey (Default: F9)
  --quit-key KEY             Quit program hotkey (Default: Esc)
  --refocus-key KEY          Focus Sky game window hotkey (Default: F6)
  --disable-hotkeys          Disable all hotkeys completely
```
</details>
