#!/usr/bin/env python

import utils

import ansi

import sys

import asyncio

import sys

from re import finditer

from os import get_terminal_size

from utils import split_by_punctuation

if sys.platform == "win32":
	from msvcrt import getch
else:
	from termios import tcsetattr, tcgetattr, TCSADRAIN, TIOCGWINSZ

	from tty import setraw

	import fcntl

def __print(*values: object, sep: str=" ", end: str="\n", file=sys.stdout) -> None:
	string = f"{sep.join(map(str, values))}{end}".replace("\n", "\n\r").expandtabs(4)

	file.write(string)

	file.flush()

old_print = __print

def parse_print_dict(value: dict, sep: str=" ", end: str="\n", level: int=0) -> str:
	if not value:
		return "{}" + end

	result = "{\n"

	dict_values = list(value.values())

	max_len = max(dict_values, key=len)

	min_len = min(dict_values, key=len)

	mid_len = (len(max_len) - len(min_len)) / 2

	for i, key in enumerate(value):
		sep = ", " if i != len(value) - 1 else ""

		dict_value = value[key]

		if len(dict_value) > mid_len:
			result += "\n"

		key_str = parse_print_str(key, end='') if isinstance(key, str) else parse_print(key, end='', level=level + 1)

		value_str = parse_print_str(dict_value, end='') if isinstance(dict_value, str) else parse_print(dict_value, end='', level=level + 1)

		tab_str = "\t" * level

		result += (f"{tab_str}{key_str}{ansi.default}: {value_str}{ansi.default}{sep}")

		if len(dict_value) > mid_len:
			result += "\n"

	result += "}"

	return f"{result}{end}"

def parse_print_arr(value: list, sep: str=" ", end: str="\n", level: int=0) -> str:
	_end = end

	if not value: return f"{ansi.default}[]"

	result = f"{ansi.default}["

	columns, rows = get_terminal_size()

	quarter_columns = columns / 4

	items = []

	for item in value:
		items.append(f"{parse_print(item)}")

	avg_width = utils.len(', '.join(map(str, items))) / len(value)

	if avg_width > quarter_columns:
		result += "\n"

	width = 0

	for i, item in enumerate(value):
		sep = ", " if i != len(value) - 1 else ""

		end = "\n" if i != len(value) - 1 else ""

		item_str = parse_print_str(item, end='') if isinstance(item, str) else parse_print(item, end='', level=level + 1)

		item_str = f"{item_str}{sep}"

		result += item_str

		width += utils.len(item_str)

		if width > avg_width and width >= quarter_columns:
			result += end

			width = 0

	result += f"]{_end}"

	return result

def parse_print_tuple(value: tuple, sep: str=" ", end: str="\n", level: int=0) -> str:
	result = f"{ansi.default}("

	items = []

	for item in value:
		if isinstance(item, (int, float)):
			items.append(f"{ansi.yellow_fg}{item}{ansi.default}")
		elif isinstance(item, str):
			items.append(parse_print_str(item, end=''))
		else:
			items.append(parse_print(item, end=''))

	result += ", ".join(items)

	result += f"){end}"

	return result

def parse_print_str(value: str, sep: str=" ", end: str="\n") -> str:
	return f"{ansi.green_fg}\"{value}\"{ansi.default}{end}"

def parse_print_int(value: str, sep: str=" ", end: str="") -> str:
	return f"{ansi.yellow_fg}{value}{ansi.default}{end}"

def parse_print(*_values: object, sep: str=" ", end: str="\n", level: int=0) -> str:
	values = []

	for i, value in enumerate(_values):
		_sep = sep if i != len(_values) - 1 else ""

		if isinstance(value, dict):
			values.append(parse_print_dict(value, end=sep, level=level))

		elif isinstance(value, list):
			values.append(parse_print_arr(value, end=sep, level=level))

		elif isinstance(value, tuple):
			values.append(parse_print_tuple(value, end=sep, level=level))

		elif isinstance(value, (int, float)):
			values.append(parse_print_int(value, end=sep))
		else:
			result: str = ""

			try:
				result = value._beatiful_str()
			except AttributeError:
				result = str(value)

			values.append(f"{result}{_sep}")

	values.append(end)

	result = ''.join(values) if values else ""

	return result

def print(*_values: object, sep: str=" ", end: str="\n", file=sys.stdout) -> None:
	if not _values:
		__print(file=file)

		return

	__print(parse_print(*_values, sep=sep, end=end), end='', file=file)

async def get_input_byte(loop: asyncio.AbstractEventLoop, bytes: int=1):
	if sys.platform == "win32":
		result = await loop.run_in_executor(None, getch)

		if result in b"\xe0\x00":
			return "\xe0"

		return str(result, encoding="utf-8")

	byte = await loop.run_in_executor(None, sys.stdin.read, bytes)

	return byte

def set_cursor_pos(x: int, y: int):
	sys.stdout.write(f"\x1B[{int(y)};{int(x)}H")

# unstable
def get_cursor_pos() -> tuple[int, int]:
	sys.stdout.write("\x1B[6n")

	sys.stdout.flush()

	sys.stdin.read(2)

	buffer = c = ""

	while c != "R":
		buffer += c

		c = sys.stdin.read(1)

	row, column = buffer.split(";")

	row = ''.join(c for c in row if c.isdigit())

	column = ''.join(c for c in column if c.isdigit())

	return (int(column), int(row))

import base64
import numpy as np

from PIL import Image

import struct

ASCII_CHARS = "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXVItfjrcxvun[]{}()|~<>~!;:,^\\. "[::-1]
NUM_CHARS = len(ASCII_CHARS)

def show_image_ascii(_x: int, _y: int, img: np.ndarray) -> None:
	for y, row in enumerate(img):
		ascii_row = []

		for x in range(len(row)):
			avg = int(np.mean(img[y, x]))

			pix = (avg * (NUM_CHARS - 1)) // 256

			c = ASCII_CHARS[min(pix, NUM_CHARS - 1)]

			ascii_row.append(c)

		ascii_row = ''.join(ascii_row)

		set_cursor_pos(_x, _y + y)

		sys.stdout.write(f"{ascii_row}\x1B[0m\n")

	sys.stdout.flush()

def show_image_ansi_16_colors(_x: int, _y: int, img: np.ndarray) -> None:
	set_cursor_pos(_x, _y)

	# ansi_16_pallete: np.ndarray = np.array([
	# 	[0, 	0, 		0],
	# 	[0xAA, 	0, 		0],
	# 	[0, 	0xAA, 	0],
	# 	[0xAA, 	0x55, 	0],
	# 	[0, 	0, 		0xAA],
	# 	[0xAA, 	0, 		0xAA],
	# 	[0, 	0xAA, 	0xAA],
	# 	[0xAA, 	0xAA, 	0xAA],

	# 	[0x55, 	0x55, 	0x55],
	# 	[0xFF, 	0x55, 	0x55],
	# 	[0x55, 	0xFF, 	0x55],
	# 	[0xFF, 	0xFF, 	0x55],
	# 	[0x55, 	0x55, 	0xFF],
	# 	[0xFF, 	0x55, 	0xFF],
	# 	[0x55, 	0xFF, 	0xFF],
	# 	[0xFF, 	0xFF, 	0xFF],
	# ])

	ansi_16_pallete: np.ndarray = np.array([
		[0, 	0, 		0],
		[0xFF, 	0, 		0],
		[0, 	0xFF, 	0],
		[0xFF, 	0, 		0],
		[0, 	0, 		0xFF],
		[0xFF, 	0, 		0xFF],
		[0, 	0xFF, 	0xFF],
		[0xFF, 	0xFF, 	0xFF],
	])

	for y, row in enumerate(img):
		ascii_row = []

		for x in range(len(row)):
			pix = img[y, x]

			dists = np.linalg.norm(ansi_16_pallete - pix, axis=1)

			index = np.argmin(dists)

			avg = int(np.mean(img[y, x]))

			pix = (avg * (NUM_CHARS - 1)) // 256

			c = ASCII_CHARS[min(pix, NUM_CHARS - 1)]

			if index == 0:
				ascii_row.append(f"\x1B[38;5;16m{c}")
			elif index < 8:
				ascii_row.append(f"\x1B[{30 + index}m{c}")
			elif index <= 16:
				ascii_row.append(f"\x1B[{90 + index - 8}m{c}")

		ascii_row = ''.join(ascii_row)

		set_cursor_pos(_x, _y + y)

		sys.stdout.write(f"{ascii_row}\x1B[0m\n")

	sys.stdout.flush()

def show_image_ansi(_x: int, _y: int, img: np.ndarray) -> None:
	set_cursor_pos(_x, _y)

	for y, row in enumerate(img):
		ascii_row = []

		for x in range(len(row)):
			pix = img[y, x]

			ascii_row.append(f"\x1B[48;2;{pix[0]};{pix[1]};{pix[2]}m ")

		ascii_row = ''.join(ascii_row)

		set_cursor_pos(_x, _y + y)

		sys.stdout.write(f"{ascii_row}\x1B[0m\n")

	sys.stdout.flush()

def show_image_kitty(x: int, y: int, img: Image.Image) -> None:
	width, height = img.size
	raw_bytes = img.tobytes()

	# 2. Кодируем сырые пиксели в base64
	b64_data = base64.b64encode(raw_bytes).decode('ascii')

	# 3. Формируем управляющую команду Kitty Graphics Protocol
	# a=T (передача и вывод), f=24 (формат RGB 24-bit), s=ширина, v=высота
	control_fragment = f"\x1B_Ga=T,f=24,s={width},v={height},m=1;"

	set_cursor_pos(x, y)

	# Выводим управляющую команду
	sys.stdout.write(control_fragment)

	chunk_size = 4096

	for i in range(0, len(b64_data), chunk_size):
		chunk = b64_data[i:(i + chunk_size)]

		if (i + chunk_size) >= len(b64_data):
			sys.stdout.write(f"\x1B_Gm=0;{chunk}\x1B\\")
		else:
			sys.stdout.write(f"\x1B_Gm=1;{chunk}\x1B\\")

	sys.stdout.write("\n")

	sys.stdout.flush()

def clean_images_kitty() -> None:
	sys.stdout.write("\x1B_Ga=d,d=S\x1B\\")

	sys.stdout.flush()

def get_char_size_emulator() -> tuple[int, int]:
	if sys.platform == "win32":
		return 8, 16

	# Структура winsize: 2 байта (строки), 2 байта (колонки), 2 байта (x пиксели), 2 байта (y пиксели)
	fmt = "HHHH"
	buf = struct.pack(fmt, 0, 0, 0, 0)

	result = fcntl.ioctl(sys.stdout.fileno(), TIOCGWINSZ, buf)

	rows, cols, x_pixels, y_pixels = struct.unpack(fmt, result)

	if x_pixels == 0 or y_pixels == 0:
		return 8, 16

	char_width = x_pixels // cols
	char_height = y_pixels // rows

	return char_width, char_height

def load_and_show_img(path: str, x: int, y: int, size: int) -> None:
	c_w, c_h = get_char_size_emulator()

	img = Image.open(path)

	img = img.convert("RGB")

	w, h = img.size
	aspect_ratio = h / w
	new_height = int(size * c_w * aspect_ratio)
	img = img.resize((size * c_w, new_height))

	clear_screen()

	show_image_kitty(x, y, img)

def clamp_text(text: str, max_width: int=None) -> str:
	if not max_width:
		columns, rows = get_terminal_size()

		max_width = columns // 3

	result = ""

	words, _ = split_by_punctuation(text)

	line_width = 0

	for word in words:
		if line_width >= max_width:
			line_width = 0

			word = word.strip()

			result += f"{word}\n"
		else:
			result += word

		line_width += len(word)

	return result

def switch_to_raw() -> list:
	if sys.platform == "win32":
		print(f"Terminal mode switching default/raw is unsupported on your OS ({sys.platform}).")

		return

	fileno = sys.stdin.fileno()

	default_settings = tcgetattr(fileno)

	setraw(fileno)

	return default_settings

def switch_to_default(default_settings) -> None:
	if sys.platform == "win32":
		print(f"Terminal mode switching default/raw is unsupported on your OS ({sys.platform}).")

		return

	fileno = sys.stdin.fileno()

	tcsetattr(fileno, TCSADRAIN, default_settings)

def clear_screen() -> None:
	columns, rows = get_terminal_size()

	print(" " * columns * rows, end='')

	set_cursor_pos(1, 1)

def line_scroll(text: str, max_length: int, time: float, speed: float=10) -> str:
	text_len = len(text)

	if text_len <= max_length:
		return text

	result = text

	pos = int(((time * speed) % (text_len + max_length + 1)) - max_length)

	end = pos + max_length

	result = result[max(0, pos):end]

	if pos >= 0:
		result = ljust(result, max_length)
	else:
		result = rjust(result, max_length)

	return result

def text_scroll(block: str, length: int, time: float, speed: float=10) -> str:
	result = ""

	strings = block.splitlines()

	strings_cnt = len(strings)

	for i, string in enumerate(strings):
		end = "\n" if i != (strings_cnt - 1) else ""

		result += f"{line_scroll(string, length, time, speed)}{end}"

	return result

def __ljust(string: str, length: int, fill_char: str=" ") -> str:
	str_len = utils.len(string)

	if str_len >= length:
		return string

	spaces = length - str_len

	return f"{string}{fill_char * spaces}"

def ljust(block: str, length: int, fill_char: str=" ") -> str:
	result = ""

	strings = block.splitlines() if block else [""]

	strings_cnt = len(strings)

	for i, string in enumerate(strings):
		end = "\n" if i != (strings_cnt - 1) else ""

		result += f"{__ljust(string, length, fill_char=fill_char)}{end}"

	return result

def __rjust(string: str, length: int, fill_char: str=" ") -> str:
	str_len = utils.len(string)

	if str_len >= length:
		return string

	spaces = length - str_len

	return f"{fill_char * spaces}{string}"

def rjust(block: str, length: int, fill_char: str=" ") -> str:
	result = ""

	strings = block.splitlines() if block else [""]

	strings_cnt = len(strings)

	for i, string in enumerate(strings):
		end = "\n" if i != (strings_cnt - 1) else ""

		result += f"{__rjust(string, length, fill_char=fill_char)}{end}"

	return result

def __center(string: str, length: int, fill_char: str=" ") -> str:
	str_len = utils.len(string)

	if str_len == 0 or str_len >= length:
		return string

	spaces = (length - str_len) // 2

	return f"{fill_char * spaces}{string}{fill_char * spaces}"

def center(block: str, length: int, fill_char: str=" ") -> str:
	result = ""

	strings = block.splitlines() if block else [""]

	strings_cnt = len(strings)

	for i, string in enumerate(strings):
		end = "\n" if i != (strings_cnt - 1) else ""

		result += f"{__center(string, length, fill_char=fill_char)}{end}"

	return result

def text_over(orig: str, _text: str, over_ch: str=r" ") -> str:
	if not orig or not _text:
		return orig

	_text = ljust(_text, len(orig))

	text = list(_text)

	for match in finditer(rf"{over_ch}+", _text):
		space = match.span()

		index = slice(space[0], space[1])

		text[index] = orig[index]

	return ''.join(text)

from math import floor, ceil

def progress(progress: float, dest: float, max_width: int, c: str="━", marker_style: str=ansi.default, marker: str="|", passed_progress_style: str=f"{ansi.bold}{ansi.green_fg}", remaining_progress_style: str=f"{ansi.default}", text_over_bar: str=None) -> None:
	norm_progress = max(0, min(1, progress / dest if dest > 0 else 1))

	marker_len = len(marker)

	width = norm_progress * max_width

	remaining_progress_len = ceil(max_width - width)

	if width > 0:
		width -= marker_len
	else:
		remaining_progress_len -= marker_len

	passed_progress = c * floor(width)

	remaining_progress = c * remaining_progress_len

	if text_over_bar:
		text_over_bar = ljust(text_over_bar, max_width)

		start = floor(width)

		passed_progress = text_over(passed_progress, text_over_bar[:start])

		marker = text_over(marker, text_over_bar[start:start + marker_len])

		start = start + marker_len

		remaining_progress = text_over(remaining_progress, text_over_bar[start:(start + remaining_progress_len)])

	bar = f"{passed_progress_style}{passed_progress}{marker_style}{marker}{remaining_progress_style}{remaining_progress}"

	return f"{ansi.default}{bar}{ansi.default}"

def time_progress(second: float, seconds: float, max_width: int, c: str="━", marker_style: str=ansi.default, passed_progress_style: str=f"{ansi.bold}{ansi.green_fg}", remaining_progress_style: str=ansi.default, text_over_bar: str="", text_center_over_bar: str="") -> None:
	seconds_str = utils.format_time(seconds)

	seconds_str_len = len(seconds_str)

	second_str = utils.format_time(second)

	width = max_width - len(second_str) - len(seconds_str) - 3

	start = seconds_str_len - 1

	if text_center_over_bar:
		text_center_over_bar = center(text_center_over_bar, max_width)

		if text_over_bar:
			text_over_bar = text_over(text_over_bar, text_center_over_bar)
		else:
			text_over_bar = text_center_over_bar

	text_over_bar = ljust(text_over_bar, max_width)

	bar = progress(
		second, seconds, width, c=c,
		marker_style=marker_style,
		passed_progress_style=passed_progress_style,
		remaining_progress_style=remaining_progress_style,
		text_over_bar=text_over_bar[start:]
	)

	second_str = text_over(second_str, text_over_bar[:start])

	start = max_width - seconds_str_len

	seconds_str = text_over(seconds_str, text_over_bar[start:])

	result = f"{second_str} {bar} {seconds_str}"

	return f"{ansi.default}{result}"
