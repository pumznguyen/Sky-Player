    # Picker-level playback state (now part of state)
    
    # State-dependent helpers
    search_field = TextArea(
        prompt=[("class:prompt", "Search: ")],
        multiline=False,
        style="class:input",
    )
    
    # Wrap in prompt_toolkit conditional filter
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.layout.containers import ConditionalContainer
    is_picker_view = Condition(lambda: state.current_view == "picker")
    search_container = ConditionalContainer(search_field, filter=is_picker_view)

    header_control = FormattedTextControl(text="")
    results_control = FormattedTextControl(text="")
    detail_control = FormattedTextControl(text="")
    footer_control = FormattedTextControl(text="")

    def get_layout_heights() -> tuple[int, int]:
        term_height = shutil.get_terminal_size((80, 24)).lines
        if state.current_view == "picker":
            overhead = 9  # header(3) + search(1) + footer(5)
            available = max(0, term_height - overhead)
            if available >= 18:
                return 13, 5
            elif available >= 10:
                return available - 5, 4
            else:
                return max(3, available), 0
        elif state.current_view == "preview":
            overhead = 8  # header(3) + footer(5)
            available = max(0, term_height - overhead)
            has_warnings = False
            if state.filtered_songs:
                selected_song = state.filtered_songs[state.selected_index]
                metadata = get_cached_song_ui_metadata(selected_song)
                if metadata.risk != "low":
                    has_warnings = True
            if not has_warnings:
                return min(11, available), 0
            if available >= 16:
                return 11, 5
            elif available >= 13:
                return 10, 3
            elif available >= 8:
                return available, 0
            else:
                return max(3, available), 0
        elif state.current_view == "profile_select":
            overhead = 8
            available = max(0, term_height - overhead)
            return min(6, available), 0
        elif state.current_view == "tempo_select":
            overhead = 8
            available = max(0, term_height - overhead)
            return min(11, available), 0
        elif state.current_view == "fps_select":
            overhead = 8
            available = max(0, term_height - overhead)
            return min(7, available), 0
        elif state.current_view == "help":
            overhead = 8  # header(3) + footer(5)
            available = max(0, term_height - overhead)
            return min(14, available), 0
        return 13, 5

    def get_results_height() -> int:
        return get_layout_heights()[0]

    def get_detail_height() -> int:
        return get_layout_heights()[1]

    header_window = Window(content=header_control, height=3)
    results_window = Window(content=results_control, height=get_results_height, style="class:results")
    detail_window = Window(content=detail_control, height=get_detail_height, style="class:detail")
    footer_window = Window(content=footer_control, height=5, style="class:footer")

    layout = Layout(
        HSplit([
            header_window,
            search_container,
            results_window,
            detail_window,
            footer_window,
        ])
    )

    kb = KeyBindings()
    def build_header_text() -> list[tuple[str, str]]:
        terminal_width = max(60, min(80, shutil.get_terminal_size((80, 24)).columns))
        title = " SKY MUSIC HELPER "
        
        mode_label = "Picker"
        if state.current_view == "preview":
            mode_label = "Preview"
        elif state.current_view == "profile_select":
            mode_label = "Profile Selection"
        elif state.current_view == "tempo_select":
            mode_label = "Tempo Adjustment"
        elif state.current_view == "fps_select":
            mode_label = "FPS Sync Selection"
        elif state.current_view == "help":
            mode_label = "Help Guide"
            
        dry_str = "ON" if state.dry_run_mode else "OFF"
        hud_str = "VERBOSE" if verbose_hud_mode else "NORMAL"
        telem_str = "ON" if telemetry_mode else "OFF"
        fps_str = str(state.current_fps) if state.current_fps else "Auto"
        
        parts = [
            mode_label,
            f"profile: {state.current_profile}",
            f"tempo: {state.current_tempo:.2f}x",
            f"fps: {fps_str}",
            f"dry: {dry_str}",
            f"telem: {telem_str}",
            f"theme: {current_theme_name}",
            f"songs: {len(state.song_choices)}",
        ]
        
        info_str = format_info_str(parts, terminal_width - 4)
        
        title_bar = f"╭─ {title} "
        title_bar += "─" * (terminal_width - len(title_bar) - 1) + "╮\n"
        info_line = f"│ {info_str:<{terminal_width - 4}} │\n"
        bottom_bar = "╰" + "─" * (terminal_width - 2) + "╯\n"
        
        return [
            ("class:title", title_bar),
            ("class:subtitle", info_line),
            ("class:divider", bottom_bar),
        ]

    def build_results_text() -> list[tuple[str, str]]:
        terminal_width = max(60, min(80, shutil.get_terminal_size((80, 24)).columns))
        if state.current_view == "picker":
            header_str = f"  #   {'Song Title':<36}    Time   Notes   Risk    Suggested\n"
            divider_str = f"  ──  {'─' * 36}    ────   ─────   ─────   ───────────\n"
            
            lines = [
                ("class:divider", header_str),
                ("class:divider", divider_str)
            ]
            
            if not state.filtered_songs:
                lines.extend([
                    ("class:empty", f"  {empty_icon} No songs found for "),
                    ("class:match", search_field.text.strip() or "empty query"),
                    ("class:empty", "\n"),
                    ("class:muted", "    Try another keyword, number, or press Ctrl+R to reload songs.\n"),
                ])
                return lines
                
            r_height, _ = get_layout_heights()
            max_visible = max(1, r_height - 2)
            start_idx = max(0, state.selected_index - max_visible // 2)
            end_idx = min(len(state.filtered_songs), start_idx + max_visible)
            if end_idx - start_idx < max_visible:
                start_idx = max(0, end_idx - max_visible)
                
            for idx in range(start_idx, end_idx):
                path = state.filtered_songs[idx]
                orig_idx = song_indices[path]
                metadata = get_cached_song_ui_metadata(path)
                lines.extend(format_song_row(orig_idx, metadata, idx == state.selected_index, search_field.text.strip(), pointer, song_icon))
                
            printed_lines = end_idx - start_idx + 2
            if printed_lines < r_height:
                lines.append(("class:unselected", "\n" * (r_height - printed_lines)))
            return lines
            
        elif state.current_view == "preview":
            if not state.filtered_songs:
                return [("class:empty", "No song selected\n")]
            selected_song = state.filtered_songs[state.selected_index]
            metadata = get_cached_song_ui_metadata(selected_song)
            
            import sys
            timer_status = "PRECISE (1.0ms resolution active)" if sys.platform == "win32" else "N/A"
            
            preview_content = [
                f"{metadata.name}",
                f"Time {_format_duration(metadata.duration_seconds)} │ Notes {metadata.note_count} │ Polyphony {metadata.max_polyphony} (max {metadata.max_chord_size}-key chords)",
                f"Risk {metadata.risk.upper()} │ Timing Stress Rate: {metadata.timing_stress_rate:.1f}% ({metadata.impossible_repeats}/{metadata.note_count} conflicts)",
                f"Min same-key repeat gap: {metadata.min_same_key_gap_ms:.0f}ms │ Peak density: {metadata.peak_notes_per_second_1s:.1f} notes/s",
            ]
            preview_box = build_box("Song", preview_content, width=terminal_width)
            
            suggested_profile = metadata.recommended_profile
            suggested_tempo = metadata.recommended_tempo_scale
            
            # Fetch active timing profile details for context
            from sky_music.config import load_config
            user_cfg = load_config()
            profile_key = state.current_profile.lower().replace("-", "_")
            if profile_key in user_cfg.timing_profiles:
                p_dict = user_cfg.timing_profiles[profile_key]
                lead_ms = p_dict.get("input_lead_us", 0) // 1000
            else:
                from sky_music.config import DEFAULT_TIMING_PROFILES
                lead_ms = DEFAULT_TIMING_PROFILES.get(profile_key, {}).get("input_lead_us", 0) // 1000
            
            timing_content = [
                f"Current Policy:   {state.current_profile} @ {state.current_tempo:.2f}x (input-lead: {lead_ms}ms)",
                f"Suggested Policy: {suggested_profile} @ {suggested_tempo:.2f}x",
                f"Windows Timer:    {timer_status}"
            ]
            timing_box = build_box("Timing & System Status", timing_content, width=terminal_width)
            
            return preview_box + timing_box
            
        elif state.current_view == "profile_select":
            content = []
            for name, desc in PROFILES_INFO:
                is_active = (name == state.current_profile)
                is_hover = (name == state.temp_profile)
                
                bullet = "●" if is_active else "○"
                row_str = f"{bullet} {name:<15}   {desc}"
                
                if is_hover:
                    content.append([("class:selected", f" ➜ {row_str}")])
                else:
                    content.append([("class:unselected", f"   {row_str}")])
                    
            profile_box = build_box("Select Timing Profile", content, width=terminal_width)
            return profile_box
            
        elif state.current_view == "tempo_select":
            content = [
                f"Current: {state.temp_tempo:.2f}x",
                ""
            ]
            for val, desc in TEMPO_OPTIONS:
                is_active = (abs(val - state.current_tempo) < 0.005)
                is_hover = (abs(val - state.temp_tempo) < 0.005)
                
                bullet = "●" if is_active else "○"
                row_str = f"{bullet} {val:.2f}x   {desc}"
                
                if is_hover:
                    content.append([("class:selected", f" ➜ {row_str}")])
                else:
                    content.append([("class:unselected", f"   {row_str}")])
                    
            tempo_box = build_box("Tempo Scale", content, width=terminal_width)
            return tempo_box
            
        elif state.current_view == "fps_select":
            content = [
                f"Current: {state.temp_fps if state.temp_fps else 'Auto'}",
                ""
            ]
            for val, desc in FPS_OPTIONS:
                is_active = (val == state.current_fps)
                is_hover = (val == state.temp_fps)
                
                bullet = "●" if is_active else "○"
                val_str = str(val) if val else "Auto"
                row_str = f"{bullet} {val_str:<4}   {desc}"
                
                if is_hover:
                    content.append([("class:selected", f" ➜ {row_str}")])
                else:
                    content.append([("class:unselected", f"   {row_str}")])
                    
            fps_box = build_box("FPS Sync", content, width=terminal_width)
            return fps_box
            
        elif state.current_view == "help":
            content = [
                [("class:key", "  Key       "), ("class:detail_label", "Description")],
                [("class:divider", "  ────────  ───────────────────────────────────────────────")],
                [("class:key", "  Enter     "), ("class:detail", "Play selected song in Sky (auto-focuses game window)")],
                [("class:key", "  Space     "), ("class:detail", "Quick Play (alias for Enter)")],
                [("class:key", "  V         "), ("class:detail", "Open detailed preview & timing risk warnings")],
                [("class:key", "  P         "), ("class:detail", "Select Timing Profile (Balanced, Remote-Safe, etc.)")],
                [("class:key", "  T         "), ("class:detail", "Adjust play speed (tempo scale)")],
                [("class:key", "  F         "), ("class:detail", "Select FPS target for frame-aware timing")],
                [("class:key", "  D         "), ("class:detail", "Toggle Dry-Run simulation mode")],
                [("class:key", "  F2        "), ("class:detail", "Toggle Playback HUD verbosity")],
                [("class:key", "  F3        "), ("class:detail", "Toggle Telemetry saving (ON / OFF)")],
                [("class:key", "  Ctrl+T    "), ("class:detail", "Cycle through GUI themes")],
                [("class:key", "  Ctrl+R    "), ("class:detail", "Reload song list immediately")],
                [("class:key", "  H         "), ("class:detail", "Close/open this Help Guide")],
                [("class:key", "  Esc       "), ("class:detail", "Quit current screen or application")]
            ]
            help_box = build_box("Keyboard Shortcut Guide", content, width=terminal_width)
            return help_box
            
        return []

    def build_detail_text() -> list[tuple[str, str]]:
        terminal_width = max(60, min(80, shutil.get_terminal_size((80, 24)).columns))
        _, d_height = get_layout_heights()
        if d_height == 0:
            return []
            
        if state.current_view == "picker":
            if not state.filtered_songs:
                return build_box("Selected", ["No song selected"], width=terminal_width)
                
            selected_song = state.filtered_songs[state.selected_index]
            metadata = get_cached_song_ui_metadata(selected_song)
            
            line1 = f"{metadata.name}"
            
            if d_height >= 5:
                # 3 lines of content
                line2 = f"Polyphony: {metadata.max_polyphony} (max {metadata.max_chord_size}-key chords) │ Min repeat gap: {metadata.min_same_key_gap_ms:.0f}ms"
                line3 = f"Density: avg {metadata.average_notes_per_second:.1f}/s (peak {metadata.peak_notes_per_second_1s:.1f}/s) │ Timing Stress: {metadata.timing_stress_rate:.1f}%"
                content = [line1, line2, line3]
            else:
                # 2 lines of content
                line2 = f"Poly: {metadata.max_polyphony} │ Gap: {metadata.min_same_key_gap_ms:.0f}ms │ Density: {metadata.average_notes_per_second:.1f}/s │ Stress: {metadata.timing_stress_rate:.1f}%"
                content = [line1, line2]
                
            return build_box("Selected", content, width=terminal_width)
            
        elif state.current_view == "preview":
            if not state.filtered_songs:
                return []
            selected_song = state.filtered_songs[state.selected_index]
            metadata = get_cached_song_ui_metadata(selected_song)
            
            if metadata.risk == "low":
                return []
                
            import textwrap
            raw_warnings = []
            for w in metadata.warnings:
                raw_warnings.extend(textwrap.wrap(w, terminal_width - 4))
            max_content = max(1, d_height - 2)
            desc = raw_warnings[:max_content]
            if len(raw_warnings) > max_content:
                last_line = desc[-1]
                if len(last_line) > 3:
                    desc[-1] = last_line[:-3] + "..."
                else:
                    desc[-1] = last_line + "..."
                
            while len(desc) < max_content:
                desc.append("")
                
            return build_box("Warnings", desc, width=terminal_width)
            
        return []
    def build_footer_text() -> list[tuple[str, str]]:
        terminal_width = max(60, min(80, shutil.get_terminal_size((80, 24)).columns))
        if state.current_view == "picker":
            if not state.filtered_songs:
                return build_box("Footer", ["No songs available."], width=terminal_width)
                
            selected_song = state.filtered_songs[state.selected_index]
            metadata = get_cached_song_ui_metadata(selected_song)
            
            if metadata.risk != "low":
                risk_style = "fg:#f97316 bold" if metadata.risk == "high" else "fg:#fbbf24 bold"
                rec_profile = metadata.recommended_profile
                rec_tempo = metadata.recommended_tempo_scale
                
                reasons = []
                if metadata.max_polyphony > 8:
                    reasons.append("high polyphony")
                if metadata.min_same_key_gap_ms < 100:
                    reasons.append("close same-key repeats")
                if "dense" in "".join(metadata.warnings).lower():
                    reasons.append("dense clusters")
                if not reasons:
                    reasons.append("timing characteristics")
                    
                reason_str = " and ".join(reasons)
                box_title = "Warnings / Actions"
                
                line1 = [
                    (risk_style, f"{metadata.risk.upper()} risk: "),
                    ("class:detail", f"{reason_str} detected.")
                ]
                actions = [
                    ActionHint(key="Enter", long="play", short="play", tiny="play"),
                    ActionHint(key="V", long="view detail", short="view", tiny="view"),
                    ActionHint(key="R", long="apply suggested", short="apply", tiny="apply"),
                    ActionHint(key="P", long="profile", short="profile", tiny="prof"),
                    ActionHint(key="T", long="tempo", short="tempo", tiny="tempo"),
                    ActionHint(key="F", long="fps", short="fps", tiny="fps"),
                    ActionHint(key="D", long="dry-run", short="dry", tiny="dry"),
                    ActionHint(key="F2", long="toggle-hud", short="hud", tiny="hud"),
                    ActionHint(key="F3", long="telemetry", short="telem", tiny="tel"),
                    ActionHint(key="H", long="help", short="help", tiny="help"),
                    ActionHint(key="Esc", long="quit", short="quit", tiny="quit")
                ]
                # Split actions into two balanced rows
                actions_row1 = actions[:6]
                actions_row2 = actions[6:]
                
                suggested_prefix = [
                    ("class:key", "Suggested: "),
                    ("class:detail_label", f"{rec_profile}"),
                    ("class:footer", " │ ")
                ]
                prefix_len = len("Suggested: " + rec_profile + " │ ")
                line2 = suggested_prefix + format_actions(actions_row1, terminal_width - 4 - prefix_len)
                line3 = format_actions(actions_row2, terminal_width - 4)
                
                return build_box(box_title, [line1, line2, line3], width=terminal_width)
            else:
                box_title = "Footer"
                line1 = [("class:detail", "No timing warnings detected. Balanced profile is suitable.")]
                actions = [
                    ActionHint(key="Enter", long="play", short="play", tiny="play"),
                    ActionHint(key="V", long="view detail", short="view", tiny="view"),
                    ActionHint(key="P", long="profile", short="profile", tiny="prof"),
                    ActionHint(key="T", long="tempo", short="tempo", tiny="tempo"),
                    ActionHint(key="F", long="fps", short="fps", tiny="fps"),
                    ActionHint(key="D", long="dry-run", short="dry", tiny="dry"),
                    ActionHint(key="F2", long="toggle-hud", short="hud", tiny="hud"),
                    ActionHint(key="F3", long="telemetry", short="telem", tiny="tel"),
                    ActionHint(key="H", long="help", short="help", tiny="help"),
                    ActionHint(key="^T", long="cycle theme", short="theme", tiny="thm"),
                    ActionHint(key="^R", long="reload songs", short="reload", tiny="rel"),
                    ActionHint(key="Esc", long="quit", short="quit", tiny="quit")
                ]
                # Split actions into two balanced rows
                actions_row1 = actions[:6]
                actions_row2 = actions[6:]
                
                line2 = format_actions(actions_row1, terminal_width - 4)
                line3 = format_actions(actions_row2, terminal_width - 4)
                
                return build_box(box_title, [line1, line2, line3], width=terminal_width)
            
        elif state.current_view == "preview":
            if not state.filtered_songs:
                return []
            selected_song = state.filtered_songs[state.selected_index]
            metadata = get_cached_song_ui_metadata(selected_song)
            
            suggested_matches = (metadata.recommended_profile == state.current_profile and abs(metadata.recommended_tempo_scale - state.current_tempo) < 0.005)
            
            if suggested_matches:
                line1 = [("class:detail", "No timing conflicts detected.")]
                actions = [
                    ActionHint(key="Enter", long="play", short="play", tiny="play"),
                    ActionHint(key="P", long="profile", short="profile", tiny="prof"),
                    ActionHint(key="T", long="tempo", short="tempo", tiny="tempo"),
                    ActionHint(key="F", long="fps", short="fps", tiny="fps"),
                    ActionHint(key="D", long="dry-run", short="dry", tiny="dry"),
                    ActionHint(key="F2", long="toggle-hud", short="hud", tiny="hud"),
                    ActionHint(key="F3", long="toggle-telemetry", short="telem", tiny="telem"),
                    ActionHint(key="Esc", long="back", short="back", tiny="back")
                ]
                actions_row1 = actions[:4]
                actions_row2 = actions[4:]
                line2 = format_actions(actions_row1, terminal_width - 4)
                line3 = format_actions(actions_row2, terminal_width - 4)
                return build_box("Footer", [line1, line2, line3], width=terminal_width)
            else:
                if metadata.risk == "low":
                    line1 = [
                        ("class:detail", "No timing conflicts detected. Suggested balanced at 1.00x.")
                    ]
                else:
                    risk_style = "fg:#f97316 bold" if metadata.risk == "high" else "fg:#fbbf24 bold"
                    rec_profile = metadata.recommended_profile
                    rec_tempo = metadata.recommended_tempo_scale
                    
                    reasons = []
                    if metadata.max_polyphony > 8:
                        reasons.append("high polyphony")
                    if metadata.min_same_key_gap_ms < 100:
                        reasons.append("close repeats")
                    if "dense" in "".join(metadata.warnings).lower():
                        reasons.append("dense clusters")
                    if not reasons:
                        reasons.append("timing characteristics")
                    reason_str = " and ".join(reasons)
                    
                    line1 = [
                        (risk_style, f"{metadata.risk.upper()} risk: "),
                        ("class:detail", f"{reason_str} detected. Suggested {rec_profile} at {rec_tempo:.2f}x.")
                    ]
                actions = [
                    ActionHint(key="Enter", long="play current", short="play", tiny="play"),
                    ActionHint(key="R", long="apply suggested", short="apply", tiny="apply"),
                    ActionHint(key="P", long="profile", short="profile", tiny="prof"),
                    ActionHint(key="T", long="tempo", short="tempo", tiny="tempo"),
                    ActionHint(key="D", long="dry-run", short="dry", tiny="dry"),
                    ActionHint(key="F2", long="toggle-hud", short="hud", tiny="hud"),
                    ActionHint(key="F3", long="toggle-telemetry", short="telem", tiny="telem"),
                    ActionHint(key="Esc", long="back", short="back", tiny="back")
                ]
                actions_row1 = actions[:4]
                actions_row2 = actions[4:]
                line2 = format_actions(actions_row1, terminal_width - 4)
                line3 = format_actions(actions_row2, terminal_width - 4)
                return build_box("Footer", [line1, line2, line3], width=terminal_width)
        elif state.current_view == "profile_select":
            lines = [
                [("class:detail", "Use the keyboard to choose and apply a timing profile:")],
                [
                    ("class:key", "↑/↓"),
                    ("class:footer", " choose │ "),
                    ("class:key", "Enter"),
                    ("class:footer", " apply │ "),
                    ("class:key", "Esc"),
                    ("class:footer", " cancel")
                ],
                []
            ]
            return build_box("Navigation", lines, width=terminal_width)

        elif state.current_view == "tempo_select":
            lines = [
                [("class:detail", "Adjust play speed (tempo) preset or fine-tune:")],
                [
                    ("class:key", "↑/↓"),
                    ("class:footer", " preset │ "),
                    ("class:key", "←/→"),
                    ("class:footer", " fine-tune ±0.01x │ "),
                    ("class:key", "Enter"),
                    ("class:footer", " apply │ "),
                    ("class:key", "Esc"),
                    ("class:footer", " cancel")
                ],
                []
            ]
            return build_box("Navigation", lines, width=terminal_width)
            
        elif state.current_view == "fps_select":
            lines = [
                [("class:detail", "Select target FPS for timing synchronization:")],
                [
                    ("class:key", "↑/↓"),
                    ("class:footer", " choose │ "),
                    ("class:key", "Enter"),
                    ("class:footer", " apply │ "),
                    ("class:key", "Esc"),
                    ("class:footer", " cancel")
                ],
                []
            ]
            return build_box("Navigation", lines, width=terminal_width)
            
        elif state.current_view == "help":
            lines = [
                [("class:detail", "Welcome to the Keyboard Shortcut Guide.")],
                [
                    ("class:key", "H"),
                    ("class:footer", " or "),
                    ("class:key", "Esc"),
                    ("class:footer", " to close this guide and return to the song picker.")
                ],
                []
            ]
            return build_box("Help Navigation", lines, width=terminal_width)

        return []
            
    def filter_songs(query: str) -> list[Path]:
        is_digit_query = query.isdigit()
        target_idx = int(query) if is_digit_query else -1
        matches = []
        startswith_matches = []
        contains_matches = []

        for path in state.song_choices:
            orig_idx = song_indices[path]
            normalized_name = remove_accents(path.stem).casefold()
            if is_digit_query and orig_idx == target_idx:
                matches.append(path)
            elif normalized_name.startswith(query):
                startswith_matches.append(path)
            elif query in normalized_name:
                contains_matches.append(path)

        return matches + startswith_matches + contains_matches

    def update_ui() -> None:
        query = remove_accents(search_field.text).casefold().strip()
        previous_selected_song = state.filtered_songs[state.selected_index] if state.filtered_songs else None
        state.filtered_songs = filter_songs(query)

        if not state.filtered_songs:
            state.selected_index = 0
        elif previous_selected_song in state.filtered_songs:
            state.selected_index = state.filtered_songs.index(previous_selected_song)
        else:
            state.selected_index = min(max(0, state.selected_index), len(state.filtered_songs) - 1)

        header_control.text = build_header_text()
        results_control.text = build_results_text()
        detail_control.text = build_detail_text()
        footer_control.text = build_footer_text()

    search_field.buffer.on_text_changed += lambda _buf: update_ui()

    @kb.add("up")
    def move_up(event):
        if state.current_view == "picker":
            if state.filtered_songs:
                state.selected_index = (state.selected_index - 1) % len(state.filtered_songs)
                update_ui()
        elif state.current_view == "profile_select":
            profiles = [p[0] for p in PROFILES_INFO]
            idx = profiles.index(state.temp_profile)
            state.temp_profile = profiles[(idx - 1) % len(profiles)]
            update_ui()
        elif state.current_view == "tempo_select":
            presets = [t[0] for t in TEMPO_OPTIONS]
            idx = min(range(len(presets)), key=lambda i: abs(presets[i] - state.temp_tempo))
            state.temp_tempo = presets[(idx - 1) % len(presets)]
            update_ui()
        elif state.current_view == "fps_select":
            presets = [f[0] for f in FPS_OPTIONS]
            idx = presets.index(state.temp_fps)
            state.temp_fps = presets[(idx - 1) % len(presets)]
            update_ui()

    @kb.add("down")
    def move_down(event):
        if state.current_view == "picker":
            if state.filtered_songs:
                state.selected_index = (state.selected_index + 1) % len(state.filtered_songs)
                update_ui()
        elif state.current_view == "profile_select":
            profiles = [p[0] for p in PROFILES_INFO]
            idx = profiles.index(state.temp_profile)
            state.temp_profile = profiles[(idx + 1) % len(profiles)]
            update_ui()
        elif state.current_view == "tempo_select":
            presets = [t[0] for t in TEMPO_OPTIONS]
            idx = min(range(len(presets)), key=lambda i: abs(presets[i] - state.temp_tempo))
            state.temp_tempo = presets[(idx + 1) % len(presets)]
            update_ui()
        elif state.current_view == "fps_select":
            presets = [f[0] for f in FPS_OPTIONS]
            idx = presets.index(state.temp_fps)
            state.temp_fps = presets[(idx + 1) % len(presets)]
            update_ui()

    @kb.add("left")
    def move_left(event):
        if state.current_view == "tempo_select":
            state.temp_tempo = max(0.50, state.temp_tempo - 0.01)
            update_ui()

    @kb.add("right")
    def move_right(event):
        if state.current_view == "tempo_select":
            state.temp_tempo = min(2.00, state.temp_tempo + 0.01)
            update_ui()

    @kb.add("g")
    def move_to_start(event):
        if state.current_view == "picker" and state.filtered_songs:
            state.selected_index = 0
            update_ui()

    @kb.add("G")
    def move_to_end(event):
        if state.current_view == "picker" and state.filtered_songs:
            state.selected_index = len(state.filtered_songs) - 1
            update_ui()

    @kb.add("f")
    def open_fps_select(event):
        if state.current_view in {"picker", "preview"}:
            state.previous_view = state.current_view
            state.temp_fps = state.current_fps
            state.current_view = "fps_select"
            event.app.layout.focus(results_window)
            update_ui()

    @kb.add("enter")
    def accept_selection(event):
        if state.current_view == "picker":
            if state.filtered_songs:
                safe_exit(event.app, SongPickerResult(
                    song_path=state.filtered_songs[state.selected_index],
                    action="dry_run" if state.dry_run_mode else "play",
                    profile_name=state.current_profile,
                    tempo_scale=state.current_tempo,
                    fps=state.current_fps,
                ))
        elif state.current_view == "preview":
            if state.filtered_songs:
                safe_exit(event.app, SongPickerResult(
                    song_path=state.filtered_songs[state.selected_index],
                    action="dry_run" if state.dry_run_mode else "play",
                    profile_name=state.current_profile,
                    tempo_scale=state.current_tempo,
                    fps=state.current_fps,
                ))
        elif state.current_view == "profile_select":
            state.current_profile = state.temp_profile
            state.current_view = state.previous_view
            try:
                from sky_music.config import load_config, save_config
                cfg = load_config()
                cfg.default_timing_profile = state.current_profile
                save_config(cfg)
            except Exception:
                pass
            if state.current_view == "picker":
                event.app.layout.focus(search_field)
            else:
                event.app.layout.focus(results_window)
            update_ui()
        elif state.current_view == "tempo_select":
            state.current_tempo = state.temp_tempo
            state.current_view = state.previous_view
            try:
                from sky_music.config import load_config, save_config
                cfg = load_config()
                cfg.default_tempo_scale = state.current_tempo
                save_config(cfg)
            except Exception:
                pass
            if state.current_view == "picker":
                event.app.layout.focus(search_field)
            else:
                event.app.layout.focus(results_window)
            update_ui()
        elif state.current_view == "fps_select":
            state.current_fps = state.temp_fps
            state.current_view = state.previous_view
            try:
                from sky_music.config import load_config, save_config
                cfg = load_config()
                if state.current_fps is not None:
                    cfg.game_fps = state.current_fps
                save_config(cfg)
            except Exception:
                pass
            if state.current_view == "picker":
                event.app.layout.focus(search_field)
            else:
                event.app.layout.focus(results_window)
            update_ui()

    @kb.add("v")
    def open_preview(event):
        if state.current_view == "picker" and state.filtered_songs:
            state.current_view = "preview"
            event.app.layout.focus(results_window)
            update_ui()

    @kb.add("space")
    def quick_play(event):
        if state.current_view == "picker" and state.filtered_songs:
            safe_exit(event.app, SongPickerResult(
                song_path=state.filtered_songs[state.selected_index],
                action="dry_run" if state.dry_run_mode else "play",
                profile_name=state.current_profile,
                tempo_scale=state.current_tempo,
                fps=state.current_fps,
            ))

    @kb.add("d")
    def toggle_dry_run(event):
        state.dry_run_mode = not state.dry_run_mode
        update_ui()

    @kb.add("p")
    def open_profile_select(event):
        if state.current_view in {"picker", "preview"}:
            state.previous_view = state.current_view
            state.temp_profile = state.current_profile
            state.current_view = "profile_select"
            event.app.layout.focus(results_window)
            update_ui()

    @kb.add("t")
    def open_tempo_select(event):
        if state.current_view in {"picker", "preview"}:
            state.previous_view = state.current_view
            state.temp_tempo = state.current_tempo
            state.current_view = "tempo_select"
            event.app.layout.focus(results_window)
            update_ui()

    @kb.add("r")
    def apply_recommended(event):
        if state.filtered_songs and state.current_view in {"picker", "preview"}:
            metadata = get_cached_song_ui_metadata(state.filtered_songs[state.selected_index])
            safe_profiles = [p[0] for p in PROFILES_INFO]
            state.current_profile = metadata.recommended_profile if metadata.recommended_profile in safe_profiles else "balanced"
            state.current_tempo = metadata.recommended_tempo_scale
            state.risk_hint = f"Applied suggested: {state.current_profile} {state.current_tempo:.2f}x"
            try:
                from sky_music.config import load_config, save_config
                cfg = load_config()
                cfg.default_timing_profile = state.current_profile
                cfg.default_tempo_scale = state.current_tempo
                save_config(cfg)
            except Exception:
                pass
            update_ui()

    @kb.add("escape")
    def cancel_or_back(event):
        if state.current_view == "picker":
            safe_exit(event.app, None)
        elif state.current_view == "preview":
            state.current_view = "picker"
            event.app.layout.focus(search_field)
            update_ui()
        elif state.current_view in {"profile_select", "tempo_select", "help"}:
            state.current_view = state.previous_view
            if state.current_view == "picker":
                event.app.layout.focus(search_field)
            else:
                event.app.layout.focus(results_window)
            update_ui()

    @kb.add("h")
    def toggle_help_view(event):
        if state.current_view == "picker":
            state.previous_view = state.current_view
            state.current_view = "help"
            event.app.layout.focus(results_window)
            update_ui()
        elif state.current_view == "help":
            state.current_view = "picker"
            event.app.layout.focus(search_field)
            update_ui()

    @kb.add("c-c")
    def cancel(event):
        safe_exit(event.app, None)

    @kb.add("c-r")
    def reload_songs(event):
        clear_metadata_cache()
        state.song_choices = get_song_choices(force_refresh=True)
        song_indices = {path: idx for idx, path in enumerate(state.song_choices, start=1)}
        state.selected_index = 0
        state.filtered_songs = list(state.song_choices)
        search_field.text = ""
        update_ui()

    @kb.add("c-t")
    def cycle_theme(event):
        nonlocal current_theme_name, pointer, song_icon, empty_icon
        themes_list = list(THEME_PRESETS.keys())
        current_idx = themes_list.index(current_theme_name)
        next_idx = (current_idx + 1) % len(themes_list)
        current_theme_name = themes_list[next_idx]

        _, new_theme = get_theme(current_theme_name)
        pointer = new_theme["pointer"]
        song_icon = new_theme["song_icon"]
        empty_icon = new_theme["empty_icon"]

        event.app.style = Style.from_dict(new_theme["style"])

        global ACTIVE_THEME
        ACTIVE_THEME = current_theme_name
        save_theme(current_theme_name)

        update_ui()

    @kb.add("f2")
    def toggle_verbose_hud(event):
        nonlocal verbose_hud_mode
        verbose_hud_mode = not verbose_hud_mode
        from sky_music.config import load_config, save_config
        cfg = load_config()
        cfg.verbose_hud = verbose_hud_mode
        save_config(cfg)
        update_ui()

    @kb.add("f3")
    def toggle_telemetry(event):
        nonlocal telemetry_mode
        telemetry_mode = not telemetry_mode
        from sky_music.config import load_config, save_config
        cfg = load_config()
        cfg.telemetry_enabled_by_default = telemetry_mode
        save_config(cfg)
        update_ui()
