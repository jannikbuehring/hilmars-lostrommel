"""Tests for app/progress_spinner.py."""

import io

from app.progress_spinner import DetailSpinner


class _TtyStream(io.StringIO):
    def isatty(self):
        return True


def _spinner(stream):
    spinner = DetailSpinner(text="Drawing singles groups...")
    spinner._stream = stream
    spinner._terminal_width = 40
    return spinner


def test_detail_is_drawn_on_its_own_line_on_a_tty():
    spinner = _spinner(_TtyStream())
    spinner.detail = "S M1 - distributing byes..."

    out = spinner._compose_out("*")

    assert out.endswith("\n  S M1 - distributing byes...")


def test_long_detail_is_truncated_so_it_never_wraps():
    spinner = _spinner(_TtyStream())
    spinner.detail = "x" * 100

    detail_line = spinner._compose_out("*").split("\n")[1]

    assert len(detail_line) < spinner._terminal_width


def test_no_detail_on_the_final_line_or_without_a_tty():
    spinner = _spinner(_TtyStream())
    spinner.detail = "S M1 - distributing byes..."
    assert "\n" not in spinner._compose_out("*", mode="last").rstrip("\n")

    piped = _spinner(io.StringIO())
    piped.detail = "S M1 - distributing byes..."
    assert "\n" not in piped._compose_out("*")


def test_clear_moves_back_up_only_after_a_two_line_frame():
    stream = _TtyStream()
    spinner = _spinner(stream)

    spinner._detail_drawn = True
    spinner._clear_line()
    assert stream.getvalue() == "\r\033[K\033[1A\r\033[K"

    stream.seek(0)
    stream.truncate()
    spinner._clear_line()
    assert stream.getvalue() == "\r\033[K"
