#!/usr/bin/env python

import builtins

from typing import Iterable

import sys

import os, psutil

from re import sub, split

from listgenerator import ListGenerator

import numpy as np

def ansi_len(ansi_str: str) -> int:
	ch_len = builtins.len(ansi_str)

	index = ansi_str.find("\x1B[")

	result = 0

	while index != -1:
		temp_result = 2 # [

		c = get_ch(ansi_str, index + temp_result, ch_len)

		commands = "mhlsuHJK"

		while c not in commands and c != "\0":
			inc = 1

			if c.isdigit():
				inc = num_len(ansi_str, index + temp_result, ch_len)

			temp_result += inc

			c = get_ch(ansi_str, index + temp_result, ch_len)

		if c in commands:
			temp_result += 1

		index = ansi_str.find("\x1B[", index + temp_result)

		result += temp_result

	return result

# THIS FUNCTION ARE TAKEN FROM THE wcwidt LIBRARY AND HAVE BEEN MODIFIED FOR PERFORMANCE OPTIMIZATION.
# You need to download wcwidth to use this function. (python3 -m pip install wcwidth)
from wcwidth._wcwidth import wcwidth
from wcwidth.bisearch import bisearch
from wcwidth._constants import (_EMOJI_ZWJ_SET,
                         _ISC_VIRAMA_SET,
                         _CATEGORY_MC_TABLE,
                         _FITZPATRICK_RANGE,
                         _REGIONAL_INDICATOR_SET)
from wcwidth.table_vs15 import VS15_WIDE_TO_NARROW
from wcwidth.table_vs16 import VS16_NARROW_TO_WIDE

def wcswidth(
    pwcs: str,
    n: int = None,
    ambiguous_width: int = 1,
) -> int:
    """
    Given a unicode string, return its printable length on a terminal.

    See :ref:`Specification` for details of cell measurement.

    This implementation differs from Markus Khun's original POSIX C implementation, in that this
    ``wcswidth()`` processes graphemes strings yielded by :func:`wcwidth.iter_graphemes` defined by
    `Unicode Standard Annex #29`_. POSIX wcswidth(3) is not grapheme-aware and does not measure many
    kinds of Emojis or complex scripts correctly.

    :param pwcs: Measure width of given unicode string.
    :param n: When ``n`` is None (default), return the length of the entire
        string, otherwise only the first ``n`` characters are measured.

    :param ambiguous_width: Width to use for East Asian Ambiguous (A)
        characters. Default is ``1`` (narrow). Set to ``2`` for CJK contexts.
    :returns: The width, in cells, needed to display the first ``n`` characters
        of the unicode string ``pwcs``.  Returns ``-1`` for C0 and C1 control
        characters!

    .. _`Unicode Standard Annex #29`: https://www.unicode.org/reports/tr29/
    """
    # pylint: disable=unused-argument,too-many-locals,too-many-statements,redefined-variable-type
    # pylint: disable=too-complex,too-many-branches,duplicate-code,too-many-nested-blocks

    # Fast path: pure ASCII printable strings are always width == length
    if n is None and pwcs.isascii() and pwcs.isprintable():
        return builtins.len(pwcs)

    _wcwidth = wcwidth if ambiguous_width == 1 else lambda c: wcwidth(c, 'auto', ambiguous_width)

    end = builtins.len(pwcs) if n is None else n
    total_width = 0
    idx = 0

    last_measured_idx = -2  # -2 sentinel blocks VS16/VS15 (no base available)
    last_measured_ucs = -1
    last_measured_w = 0
    prev_was_virama = False
    cluster_width = 0
    vs16_nw_table = VS16_NARROW_TO_WIDE['9.0.0']
    vs15_wn_table = VS15_WIDE_TO_NARROW['9.0.0']
    _bisearch = bisearch

    while idx < end:
        char = pwcs[idx]
        ucs = ord(char)

        # 5. ZWJ (U+200D): consumed without contributing width.
        # Virama codepoints are treated as zero-width combining marks (Mn). When a
        # virama+consonant sequence forms a conjunct, its width is capped at 2 cells.

        # ZWJ (U+200D)
        if ucs == 0x200D:
            if prev_was_virama:
                idx += 1
            elif idx + 1 < end:
                last_measured_w = 0
                prev_was_virama = False
                idx += 2
            else:
                prev_was_virama = False
                idx += 1
            continue

        # 6. VS16 (U+FE0F): converts preceding narrow character to wide.
        if ucs == 0xFE0F and last_measured_idx >= 0:
            if _bisearch(last_measured_ucs, vs16_nw_table):
                cluster_width = 2
            last_measured_idx = -2
            idx += 1
            continue

        # VS15 (U+FE0E): text variation selector, requests narrow presentation.
        if ucs == 0xFE0E and last_measured_idx >= 0:
            if bisearch(last_measured_ucs, vs15_wn_table) and last_measured_w == 2:
                total_width -= 1
            idx += 1
            continue

        # 7. Regional Indicator & Fitzpatrick (both above BMP)
        if ucs > 0xFFFF:
            if ucs in _REGIONAL_INDICATOR_SET:
                ri_before = 0
                j = idx - 1
                while j >= 0 and ord(pwcs[j]) in _REGIONAL_INDICATOR_SET:
                    ri_before += 1
                    j -= 1
                if ri_before % 2 == 1:
                    last_measured_ucs = ucs
                    idx += 1
                    continue
            elif (_FITZPATRICK_RANGE[0] <= ucs <= _FITZPATRICK_RANGE[1]
                  and last_measured_ucs in _EMOJI_ZWJ_SET):
                idx += 1
                continue

        # 8. Normal character: measure with wcwidth
        w = _wcwidth(char)
        if w < 0:
            if cluster_width:
                total_width += cluster_width
                cluster_width = 1
            else:
                cluster_width = 1

            last_measured_idx = idx
            last_measured_ucs = ucs
            last_measured_w = w
            prev_was_virama = False
        if w > 0:
            if prev_was_virama:
                cluster_width = 2
            elif cluster_width:
                total_width += cluster_width
                cluster_width = w
            else:
                cluster_width = w

            last_measured_idx = idx
            last_measured_ucs = ucs
            last_measured_w = w
            prev_was_virama = False
        elif ucs in _ISC_VIRAMA_SET:
            prev_was_virama = True
        elif last_measured_idx >= 0 and _bisearch(ucs, _CATEGORY_MC_TABLE):
            cluster_width = 2
            last_measured_idx = -2
            prev_was_virama = False
        else:
            prev_was_virama = False
        idx += 1

    if cluster_width:
        total_width += cluster_width
    return total_width

def len(text: Iterable) -> int:
	if not isinstance(text, str):
		return builtins.len(text)

	return wcswidth(text) - ansi_len(text)

def text_start(text: str) -> int | tuple[int]:
	result = 0

	i = text.find("\x1B[")

	while i != -1 and text[i] == "\x1B":
		i += 2

		i = text.find("\x1B[")

	return result

def get_ch(txt: str, i: int, c_len: int) -> str:
	return "\0" if i >= c_len else txt[i]

def num_len(txt: str, i: int, c_len: int) -> int:
	result = 0

	while get_ch(txt, i + result, c_len).isdigit():
		result += 1

	return result

def parse_music_file_name(_file_name: str) -> tuple[str, str]:
	"""Function for parse file names like "MORGENSHTERN_-_Selyavi_74039193.mp3" to ("MORGENSHTERN", "Selyavi")"""

	file_name = _file_name

	file_name_and_ext = _file_name.split(".mp")

	file_name_and_ext_len = len(file_name_and_ext)

	if not file_name_and_ext:
		return ("Unknown", _file_name)

	if file_name_and_ext_len >= 1:
		file_name = file_name_and_ext[0]

	file_name = sub(r"_-?\d+$", "", file_name)

	lead_and_name = [match.replace("_", " ").strip() for match in split(r"-+(?!.*-)", file_name, 1) if match.strip()]

	if len(lead_and_name) == 1:
		lead_and_name = ["Unknown", lead_and_name[0]]

	return lead_and_name if lead_and_name else ["Unknown", _file_name]

def split_by_punctuation(text: str, punc_re=r" |\.|,|!|\?|:|-|\"|\(|\)|/|\||\n|\r") -> tuple[ListGenerator, ListGenerator]:
	result = ListGenerator(word for word in split(rf"({punc_re})", text) if word)

	words = ListGenerator(word for word in split(punc_re, text) if word)

	return (result, words)

def format_time(time: float, wordly: bool=True) -> str:
	if time == np.inf:
		return "inf"

	hours = int((time / (60 * 60)) % 24)
	minutes = int((time / 60) % 60)
	seconds = int(time % 60)

	result = ""

	if wordly:
		if hours != 0:
			result += f"{hours:02} h "

		if minutes != 0:
			result += f"{minutes:02} m "

		result += f"{seconds:02} s"

	elif hours > 0:
		result = f"{hours:02}:{minutes:02}:{seconds:02}"
	else:
		result = f"{minutes:02}:{seconds:02}"

	return result

def format_size(size: int, base: int=1024,
				unit_names: list[str]=["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB", "RB", "QB"]) -> str:
	if base <= 1:
		raise RuntimeError(f"Base ({base}) cannot be <= 1")

	index = 0

	result = []

	while size > 1 and index < len(unit_names) - 1:
		number = size % base

		if number >= 1:
			result.append(f"{number} {unit_names[index]}")

		size //= base

		index += 1

	if size >= 1:
		result.append(f"{size} {unit_names[index]}")

	return ' '.join(result[::-1]) if result else f"0 {unit_names[0]}"

def avg(x: list[int]) -> int:
	return sum(x) / len(x)

def align_up(x: int, align: int) -> int:
	x = int(x)

	align = int(align)

	if x % align == 0: return x

	return int((x // align) * align)

def align_down(x: int, align: int) -> int:
	x = int(x)

	align = int(align)

	if x % align == 0: return x

	return (x // align + 1) * align

def parse_args(argv: list[str]) -> tuple[list, dict]:
	args = []

	kwargs = {}

	kwarg_key = ""

	kwarg_value = False

	for arg in argv:
		if arg.startswith("-") and not arg.startswith("--"):
			kwarg_key = arg[1:]

			kwarg_value = True

			kwargs[kwarg_key] = ""

		elif kwarg_value:
			kwargs[kwarg_key] = arg

			kwarg_value = False

		else:
			args.append(arg)

	return (args, kwargs)

def is_input_bytes() -> bool:
	if sys.platform == "win32":
		from msvcrt import kbhit

		return kbhit()
	else:
		raise NotImplementedError()

def get_parent_process_name():
	current_process = psutil.Process(os.getppid())
	parent_process = current_process.parent()

	if parent_process:
		return parent_process.name()

	return "not found"
