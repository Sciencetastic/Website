original_as_received/   your two audit scripts, unmodified
linux_font_patched/     same logic; only the Windows font paths replaced by a DejaVu/default fallback so they run on Linux.
                        Scripts write to <parent-of-scripts-folder>/outputs/Art_Reviews/.
Usage: python audit_filter_draft2.py image.png [--origin X Y] [--backdrop 000000]
