"""
A yaspin spinner with a second, live status line below the spinner.

    ⠋ Drawing singles bracket...
      S M1 main bracket - distributing byes...

yaspin redraws its frame with a carriage return and "erase line" only, so a
newline in `spinner.text` leaves a trail of half-cleared lines.  DetailSpinner
draws the `detail` line itself and, before each redraw, clears it and moves the
cursor back up to the spinner line.  The detail line is live-only: ok()/fail()
print the final line without it.

On a non-TTY stream (output piped or redirected) the detail is never drawn, so
no cursor escape codes end up in a file.
"""

from yaspin.core import Yaspin


class DetailSpinner(Yaspin):
    """Yaspin with a `detail` attribute shown on its own line below the spinner.

    `detail` may be set from the drawing thread at any time; the spin thread
    picks it up on its next frame.  None hides the line.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.detail = None
        # Whether the frame currently on screen has the detail line below it.
        self._detail_drawn = False

    def _detail_suffix(self):
        detail = self.detail
        if not detail or not self._supports_ansi_codes():
            return ""
        # Two leading spaces for the indent, one column spare so the line never
        # wraps: a wrapped line would take two rows, and only one is cleared.
        max_len = self._terminal_width - 3
        if max_len < 1:
            return ""
        if len(detail) > max_len:
            detail = detail[: max(0, max_len - len(self._ellipsis))] + self._ellipsis
        return f"\n  {detail}"

    def _compose_out(self, frame, mode=None):
        out = super()._compose_out(frame, mode)
        if mode is None:
            out += self._detail_suffix()
        return out

    def _clear_line(self):
        if self._detail_drawn and self._stream.isatty():
            # Clear the detail line, then move up and let yaspin clear the spinner line.
            self._stream.write("\r\033[K\033[1A")
        self._detail_drawn = False
        super()._clear_line()

    def _spin(self):
        # Same loop as Yaspin._spin, but it records whether the frame it wrote
        # has a detail line, so _clear_line knows how many rows to clear.
        if self._stop_spin is None:
            raise RuntimeError("stop_spin is None")

        while not self._stop_spin.is_set():
            if self._hide_spin is not None and self._hide_spin.is_set():
                self._stop_spin.wait(self._interval)
                continue

            out = self._compose_out(next(self._cycle))

            with self._stream_lock:
                if self._hide_spin is not None and self._hide_spin.is_set():
                    continue
                self._clear_line()
                self._stream.write(out)
                self._stream.flush()
                self._detail_drawn = "\n" in out
                self._cur_line_len = max(self._cur_line_len, len(out))

            self._stop_spin.wait(self._interval)


def detail_spinner(text, color="cyan"):
    """Create a DetailSpinner, used like `yaspin(text=..., color=...)`."""
    return DetailSpinner(text=text, color=color)
