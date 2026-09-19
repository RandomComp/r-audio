import base64
import time
import json

from collections import deque

from io import BytesIO
from typing import Any

from PIL import Image

import asyncio

import ansi

from event import EventEmitter
import utils

import tui

from translator import Translator

from math import ceil

import os

from dbus_next.aio.message_bus import MessageBus
from dbus_next.service import ServiceInterface, method, dbus_property
from dbus_next.constants import PropertyAccess
from dbus_next.signature import Variant

class AudioPlayerMPrisRootInterface(ServiceInterface):
	def __init__(self):
		super().__init__('org.mpris.MediaPlayer2')

	@dbus_property(access=PropertyAccess.READ)
	def CanQuit(self) -> 'b':
		return False

	@dbus_property(access=PropertyAccess.READ)
	def CanRaise(self) -> 'b':
		return False

	@dbus_property(access=PropertyAccess.READ)
	def HasTrackList(self) -> 'b':
		return False

	@dbus_property(access=PropertyAccess.READ)
	def Identity(self) -> 's':
		return "r-audio"

	@dbus_property(access=PropertyAccess.READ)
	def SupportedUriSchemes(self) -> 'as':
		return ["file"]

	@dbus_property(access=PropertyAccess.READ)
	def SupportedMimeTypes(self) -> 'as':
		return ["audio/mpeg", "audio/wav", "audio/ogg", "audio/aac", "audio/flac"]

	@dbus_property(access=PropertyAccess.READ)
	def DesktopEntry(self) -> 's':
		return ""

class AudioPlayerClient:
	def __init__(self, config: dict | None=None):
		self.finished = asyncio.Event()

		self.__id3_info = {}
		self.__playlist = []
		self.audio_start_time = time.time()
		self.__duration = 0
		self.__volume = 0
		self.__state = "Paused"
		self.__track_id = 0

		self.on_id3_info_changed = EventEmitter(name="on_id3_info_changed")
		self.on_time_changed = EventEmitter(name="on_time_changed")
		self.on_duration_changed = EventEmitter(name="on_duration_changed")
		self.on_volume_changed = EventEmitter(name="on_volume_changed")
		self.on_state_changed = EventEmitter(name="on_state_changed")
		self.on_track_id_changed = EventEmitter(name="on_track_id_changed")

		self.addr = ("127.0.0.1", 6700)
		self.reader, self.writer = None, None
		self.command_queue = deque()

		self.config = config

	@property
	def id3_info(self) -> dict[str, Any]:
		return self._id3_info
	@property
	def cur_time(self) -> float:
		return time.time() - self.audio_start_time
	@property
	def duration(self) -> float:
		return self.__duration
	@property
	def volume(self) -> float:
		return self.__volume
	@property
	def state(self) -> str:
		return self.__state
	@property
	def track_id(self) -> int:
		return self.__track_id

	@id3_info.setter
	def id3_info(self, value: dict[str, Any]) -> None:
		self.__id3_info = value

		self.on_id3_info_changed.invoke(value)

	@cur_time.setter
	def cur_time(self, value: float) -> None:
		# self.audio.second = val
		return
	@duration.setter
	def duration(self, value: float) -> None:
		self.__duration = value

		self.on_duration_changed.invoke(value)
	@volume.setter
	def volume(self, value: float) -> None:
		self.__volume = value

		self.on_volume_changed.invoke(value)
	@state.setter
	def state(self, value: str) -> None:
		self.__state = value

		self.on_state_changed.invoke(value)
	@track_id.setter
	def track_id(self, value: int) -> None:
		self.__track_id = value

		self.on_track_id_changed.invoke(value)

	def send_text(self, writer: asyncio.StreamWriter, text: str) -> None:
		# print(f"{text=}")

		msg = text + "\n"

		writer.write(msg.encode("UTF-8"))

	async def read_text(self, reader: asyncio.StreamReader) -> str:
		result = []

		c = await reader.read(1)

		while c and c != b"\n":
			result.append(c)

			c = await reader.read(1)

		result = b''.join(result)

		return result.decode("UTF-8")

	async def _read_answer(self, reader: asyncio.StreamReader) -> tuple[str, str, str]:
		response = await self.read_text(reader)

		state, command, msg = response.split("|", maxsplit=2)

		return state, command, msg

	async def send_command(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, _expected_command: str, argv: list[str] | None=None) -> tuple[str, str]:
		expected_command = f"{_expected_command}{'|'.join(argv) if argv else ""}"

		self.send_text(writer, expected_command)

		await writer.drain()

		state, command, msg = await self._read_answer(reader)

		state_command = ["play", "pause", "play_pause"]
		info_command = ["prev", "next", "info"]

		if command in state_command:
			self.state = msg

		if command in info_command:
			self.read_info(json.loads(msg))

		if command == "update" and msg:
			self.read_info(json.loads(msg))

		return state, msg

	async def init(self) -> None:
		try:
			addr, port = self.addr

			self.reader, self.writer = await asyncio.open_connection(addr, port)
		except ConnectionRefusedError:
			pass

		if self.reader and self.writer:
			await self.update_info()

	def _load_id3(self, id3_info: dict) -> None:
		self.id3_info = id3_info

	async def wait_for_playing(self) -> None:
		while self.state != "Playing":
			await asyncio.sleep(0.1)

	def is_playing(self) -> bool:
		return self.state == "Playing"

	def is_paused(self) -> bool:
		return self.state == "Paused"

	def volume_up(self, percent: float) -> None:
		self.volume_set(self.volume + percent)

	def volume_down(self, percent: float) -> None:
		self.volume_set(self.volume - percent)

	def volume_set(self, percent: float) -> None:
		self.volume = min(1, max(0, percent))

	def volume_get(self) -> float:
		return self.volume

	def read_info(self, info: dict) -> None:
		if "cur_time" in info:
			self.audio_start_time = time.time() - info["cur_time"]

		if "duration" in info:
			self.duration = info["duration"]

		if "volume" in info:
			self.volume = info["volume"]

		if "state" in info:
			self.state = info["state"]

		if "track_id" in info:
			self.track_id = info["track_id"]

		if "id3" in info:
			id3 = info["id3"]

			if id3 and "cover" in id3 and id3["cover"]:
				id3["cover"] = base64.b64decode(id3["cover"])

			self._load_id3(id3)

	async def update_info(self) -> None:
		if not self.reader or not self.writer:
			return

		await self.send_command(self.reader, self.writer, "info")

	async def update_info_timer(self) -> None:
		i = 0

		while not self.finished.is_set():
			if not self.reader or not self.writer:
				if i % 100 == 0:
					await self.init()

					# print("Waiting for the server...")

				i += 1

				await asyncio.sleep(0.01)

				continue

			while len(self.command_queue) > 0:
				command, args = self.command_queue.popleft()

				await self.send_command(self.reader, self.writer, command, args)

			if i % 10 == 0:
				await self.send_command(self.reader, self.writer, "update")

				if self.is_playing():
					self.on_time_changed.invoke(self.cur_time)

			await asyncio.sleep(0.01)

			i += 1

	async def loop(self) -> None:
		await self.init()

		await self.update_info_timer()

	async def reset(self) -> None:
		self.finished.clear()

	async def close_connection(self) -> None:
		self.finished.set()

		self.id3_info = {}

		if self.writer:
			self.writer.close()

			await self.writer.wait_closed()

	def next(self) -> None:
		self.command_queue.append(("next", []))

	def prev(self) -> None:
		self.command_queue.append(("prev", []))

	def play(self) -> None:
		self.command_queue.append(("play", []))

	def pause(self) -> None:
		self.command_queue.append(("pause", []))

	def play_pause(self) -> None:
		self.command_queue.append(("play_pause", []))

	def __repr__(self) -> str:
		return f"""
self.id3_info = {self.id3_info}
self.cur_time = {self.cur_time}"""

class AudioPlayerClientTUI(ServiceInterface):
	supported_extensions = (".mp4", ".mp3", ".wav", ".ogg", ".aac", ".flac")

	def __init__(self, input: asyncio.Queue, config: dict, translator: Translator | None=None):
		super().__init__('org.mpris.MediaPlayer2.Player')

		# system members:

		self.finished = asyncio.Event()
		self.update_processing = asyncio.Event()

		self.old_columns, self.old_rows = tui.get_terminal_size()

		self.__lines_outputed = 0

		self.progress_bar_c = "━"

		self.bus = None
		self.bus_name = "org.mpris.MediaPlayer2.r_audio_player"

		self.input = input

		self.id3_info = None
		self.cur_time = 0
		self.duration = 0
		self.volume = 0
		self.state = "Paused"
		self.track_id = 0

		self.addr = ("127.0.0.1", 6700)
		self.reader, self.writer = None, None
		self.command_queue = deque()

		self.cover_name = "r_audio_track_cover" # temporary path for track cover
		self.cover_w = 1
		self.cover_h = 1

		self.cover_drawed = False

		self.config = config

		self.translator = translator

		self.verbose = self.config["interface"]["logs"]

		self.protocol = AudioPlayerClient()

		self.protocol.on_id3_info_changed.subscribe(self.id3_info_changed)
		self.protocol.on_time_changed.subscribe(self.time_changed)
		self.protocol.on_duration_changed.subscribe(self.duration_changed)
		self.protocol.on_volume_changed.subscribe(self.volume_changed)
		self.protocol.on_state_changed.subscribe(self.state_changed)
		self.protocol.on_track_id_changed.subscribe(self.track_id_changed)

	def __output(self, *values: object, sep: str=" ", end: str="\n") -> None:
		string = f"{sep.join(map(str, values))}{end}"

		self.__lines_outputed += len(string.splitlines())

		tui.print(string, end='')

	def __translated_output(self, *values: object, sep: str=" ", end: str="\n") -> None:
		self.__output(self.__translated(*values, sep=sep), end=end)

	def __translated(self, *values: object, sep: str=" ") -> str:
		values_str = []

		for value in values:
			value_str = str(value)

			if isinstance(value, str) and self.translator:
				value_str = self.translator.translate(value_str)

			values_str.append(value_str)

		return sep.join(values_str)

	async def open_dbus(self) -> None:
		if self.bus is not None:
			return

		if self.verbose:
			self.__translated_output("Opening DBus...")

		self.bus = await MessageBus().connect()

		root = AudioPlayerMPrisRootInterface()

		self.bus.export("/org/mpris/MediaPlayer2", root)
		self.bus.export("/org/mpris/MediaPlayer2", self)

		await self.bus.request_name(self.bus_name)

		if self.verbose:
			self.__translated_output("Opening DBus done")

	def display_volume(self, volume: float, columns: int) -> None:
		volume_mess = tui.progress(
			volume, 1, columns,
			passed_progress_style=self.config["color-scheme"]["volume_passed_progress_color"],
			remaining_progress_style=self.config["color-scheme"]["volume_remaining_progress_color"]
		)

		self.__output(f"\r{ansi.clear}{volume_mess}")

		volume_status_mess = f"{self.__translated('volume')} {int(volume * 100)}%"

		self.__output(f"\r{ansi.clear}{tui.center(volume_status_mess, columns)}")

	def display_progress(self, second: float, seconds: float, columns: int) -> None:
		progress = tui.time_progress(
			second, seconds, columns,
			passed_progress_style=self.config["color-scheme"]["timeline_passed_progress_color"],
			remaining_progress_style=self.config["color-scheme"]["timeline_remaining_progress_color"]
		)

		self.__output(f"\r{ansi.clear}{progress}", end='')

	def get_song_title(self) -> tuple[str, str]:
		if self.id3_info:
			return self.id3_info["title"], self.id3_info["lead"]

		return "", ""

	def display_media_info_lines(self):
		title, lead = self.get_song_title()

		y = 3

		# size = 30

		# c_w, c_h = tui.get_char_size_emulator()

		# y += (size * self.cover_h * c_w) / (self.cover_w * c_h)

		y += 1

		if lead:
			y += 2

		y += 2

		return ceil(y)

	def display_media_info(self, y: int, max_width: int) -> None:
		columns, rows = tui.get_terminal_size()

		title, lead = self.get_song_title()

		size = 30

		# c_w, c_h = tui.get_char_size_emulator()

		# if self.id3_info != None and self.id3_info["cover"] != None and not self.cover_drawed:
		# 	tui.clean_images_kitty()

		# 	self.cover_drawed = True

		# 	_bytes = self.id3_info["cover"]

		# 	path = BytesIO(_bytes)

		# 	# print({new_keys[i]: result.get(key) for i, key in enumerate(keys)})

		# 	img = Image.open(path)

		# 	img = img.convert("RGB")

		# 	self.cover_w, self.cover_h = img.size
		# 	aspect_ratio = self.cover_h / self.cover_w
		# 	new_height = int(size * aspect_ratio * c_w)
		# 	img = img.resize((size * c_w, new_height))

		# 	tui.show_image_kitty((columns // 2) - (size // 2), y, img)

		# y += (size * self.cover_h * c_w) // (self.cover_w * c_h)

		y = (rows // 2) - 3

		y += 1

		title_message = f"{self.config["color-scheme"]["title_color"]}{title}{ansi.default}"

		tui.set_cursor_pos(1, y)

		self.__output(tui.center(title_message, columns), end='')

		y += 1

		lead_len = len(lead) if lead else 0

		line_width = utils.align_up(len(title) + lead_len, 2)

		tui.set_cursor_pos(1, y)

		self.__output(tui.center(line_width * '─', columns), end='')

		y += 1

		if lead:
			lead_message = f"{self.config["color-scheme"]["lead_color"]}{lead}{ansi.default}"

			tui.set_cursor_pos(1, y)

			self.__output(tui.center(lead_message, columns), end='')

			y += 1

		y += 1

		play_symbol = "▶ " if self.is_paused() else "||"

		tui.set_cursor_pos(1, y)

		self.__output(tui.center(play_symbol, columns))

		y += 1

	def display_update(self) -> None:
		columns, rows = tui.get_terminal_size()

		if self.old_columns != columns or self.old_rows != rows:
			tui.clear_screen()

			self.cover_drawed = False

		tui.set_cursor_pos(1, 1)

		if self.config["interface"]["show_help"]:
			self.__translated_output(f"{ansi.bold}{ansi.cyan_fg}space{ansi.default} to play/stop")
			self.__translated_output(f"{ansi.bold}{ansi.green_fg}←→{ansi.default} to seek the audio")
			self.__translated_output(f"{ansi.bold}{ansi.green_fg}↑↓{ansi.default} to control the audio volume")
			self.__translated_output(f"{ansi.bold}{ansi.green_fg}z{ansi.default} and {ansi.green_fg}c{ansi.default} to go previous and next track")
			self.__translated_output(f"{ansi.bold}{ansi.green_fg}q{ansi.default} to quit")

		self.display_volume(self.volume, columns)

		media_info_line = self.display_media_info_lines()
		self.display_media_info(10, columns)

		# 32:3 1050x700:150x50 = 7x14, 1050x700:131x47=8x15

		gap = 1

		# c_bars = [" ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
		# c_bars_cnt = len(c_bars)

		# if self.config["interface"]["show_equalizer"] and self.sound_cur_chunk is not None and self.sound_cur_chunk.shape[0] > 0:
		# 	# max_bar_height = ((columns * 16 * 3) // 32) // 8

		# 	max_bar_height = rows - 1 - 8 - media_info_line

		# 	max_bar_width = (max_bar_height * 8 * 32) // (16 * 3)

		# 	if max_bar_width >= columns:
		# 		max_bar_width = columns

		# 		max_bar_height = (columns * 16 * 3) // (32 * 8)

		# 	total_bar_width = floor(max_bar_width / (gap + 1))

		# 	bars: np.ndarray = calculate_equalizer_bars(self.sound_cur_chunk, self.old_chunk, self.old_chunk_id, total_bar_width, self.sample_rate) * max_bar_height * c_bars_cnt

		# 	self.old_chunk = bars

		# 	self.old_chunk_id += 1

		# 	for j in range(max_bar_height):
		# 		current_terminal_y = rows - max_bar_height + 4 + j

		# 		distance_from_floor = max_bar_height - j

		# 		row = []
		# 		for bar in bars:
		# 			index = int(bar % c_bars_cnt)

		# 			bar = floor(bar / c_bars_cnt)

		# 			if bar == distance_from_floor:
		# 				row.append(c_bars[index])

		# 				row.append(" " * gap)

		# 				continue

		# 			if bar >= distance_from_floor:
		# 				row.append(c_bars[-1])
		# 			else:
		# 				row.append(" ")

		# 			row.append(" " * gap)

		# 		tui.set_cursor_pos(1, current_terminal_y)

		# 		row = ''.join(row)

		# 		tui.sys.stdout.write(f"{ansi.white_fg}{tui.center(row, columns)}{ansi.default}")

		tui.set_cursor_pos(1, rows)

		# print(repr(self).replace("\n", "\n\r"), end='')

		self.display_progress(self.cur_time, self.duration, columns)

		tui.sys.stdout.flush()

		self.old_columns = columns
		self.old_rows = rows

	def id3_info_changed(self, _: str, value: dict[str, Any]) -> None:
		self.id3_info = value

		cover_dir = self.get_cover_name()

		if cover_dir and "cover" in self.id3_info and self.id3_info["cover"] is not None:
			with open(cover_dir, "wb") as f:
				f.write(self.id3_info["cover"])

		if self.bus:
			self.emit_properties_changed({'Metadata': self.get_metadata()})

		self.display_update()
	def time_changed(self, _: str, value: float) -> None:
		self.cur_time = value

		self.display_update()
	def duration_changed(self, _: str, value: float) -> None:
		self.duration = value

		self.display_update()
	def volume_changed(self, _: str, value: float) -> None:
		self.volume = value

		self.display_update()
	def state_changed(self, _: str, value: str) -> None:
		self.state = value

		self.display_update()
	def track_id_changed(self, _: str, value: int) -> None:
		self.track_id = value

	def play(self) -> None:
		self.protocol.play()
	def pause(self) -> None:
		self.protocol.pause()
	def play_pause(self) -> None:
		self.protocol.play_pause()
	def prev(self) -> None:
		self.protocol.prev()
	def next(self) -> None:
		self.protocol.next()
	def volume_set(self, value: float) -> None:
		self.protocol.volume_set(value)
	def volume_up(self, value: float) -> None:
		self.protocol.volume_up(value)
	def volume_down(self, value: float) -> None:
		self.protocol.volume_down(value)

	async def wait_for_playing(self) -> None:
		while self.state != "Playing":
			await asyncio.sleep(0.1)

	def is_playing(self) -> bool:
		return self.state == "Playing"

	def is_paused(self) -> bool:
		return self.state == "Paused"

	async def key_handler(self) -> None:
		while not self.finished.is_set():
			seek_seconds = 1

			get_task = asyncio.create_task(self.input.get())
			wait_event = asyncio.create_task(self.finished.wait())

			done, pending = await asyncio.wait(
				[get_task, wait_event],
				return_when=asyncio.FIRST_COMPLETED
			)

			for task in pending:
				task.cancel()

				try:
					await task
				except asyncio.CancelledError:
					pass

			input_key = ""

			if get_task in done:
				input_key = get_task.result()

			if self.finished.is_set():
				break

			if input_key == "q":
				await self.close()

				break

			elif input_key == " ":
				self.play_pause()

			elif input_key == "↑":
				self.volume_up(0.01)

			elif input_key == "↓":
				self.volume_down(0.01)

			elif input_key == "←":
				self.second = self.second - seek_seconds

			elif input_key == "→":
				self.second = self.second + seek_seconds

			elif input_key == "z":
				self.prev()

			elif input_key == "c":
				self.next()

	def get_cover_name(self) -> str:
		return f"/tmp/{self.cover_name}_{self.track_id}.jpg"

	async def loop(self) -> None:
		tui.clear_screen()

		await asyncio.gather(
			self.key_handler(),
			self.protocol.loop()
		)

		if self.cover_name:
			cover_dir = self.get_cover_name()

			if os.path.isfile(cover_dir):
				os.remove(cover_dir)

	async def reset(self) -> None:
		self.finished.clear()

		self.cover_drawed = False

		# self.id3_info = None

	async def close(self) -> None:
		self.finished.set()

		self.id3_info = None

		await self.protocol.close_connection()

		if self.bus:
			await self.bus.release_name(self.bus_name)

			self.bus.disconnect()

		self.bus = None

	@dbus_property(access=PropertyAccess.READ)
	def CanControl(self) -> 'b':
		return True

	@dbus_property(access=PropertyAccess.READ)
	async def PlaybackStatus(self) -> 's':
		return self.state

	def get_metadata(self) -> 'a{sv}':
		title, lead = self.get_song_title()

		cover_dir = self.get_cover_name()

		return {
			"mpris:trackid": Variant("o", f"/com/r_audio/track/{self.track_id}"),
			"mpris:length": Variant("x", int(self.duration * 1000 * 1000)),
			"mpris:artUrl": Variant("s", f"file://{cover_dir}"),
			"xesam:title": Variant("s", title),
			"xesam:artist": Variant("as", [lead]),
		}

	@dbus_property(access=PropertyAccess.READ)
	def Metadata(self) -> 'a{sv}':
		return self.get_metadata()

	@dbus_property(access=PropertyAccess.READ)
	def CanPause(self) -> 'b':
		return True

	@dbus_property(access=PropertyAccess.READ)
	def CanPlay(self) -> 'b':
		return True

	@dbus_property(access=PropertyAccess.READ)
	def CanGoNext(self) -> 'b':
		return True

	@dbus_property(access=PropertyAccess.READ)
	def CanGoPrevious(self) -> 'b':
		return True

	@dbus_property(access=PropertyAccess.READ)
	def CanSeek(self) -> 'b':
		return True

	@dbus_property(access=PropertyAccess.READ)
	def CanSetPosition(self) -> 'b':
		return True

	@dbus_property(access=PropertyAccess.READ)
	def LoopStatus(self) -> 's':
		return "None"

	@dbus_property(access=PropertyAccess.READ)
	def Shuffle(self) -> 'b':
		return False

	@dbus_property(access=PropertyAccess.READWRITE)
	def Volume(self) -> 'd':
		return self.volume

	@Volume.setter
	def Volume(self, val: 'd'):
		self.protocol.volume_set(val)

	@dbus_property(access=PropertyAccess.READ)
	def Position(self) -> 'x':
		return int(self.protocol.cur_time * 1000 * 1000)

	@method()
	def SetPosition(self, _track_id: 'o', val: 'x'):
		track_id = int(str(_track_id).split("/")[-1])

		if track_id != self.track_id:
			return

		self.protocol.cur_time = val / (1000 * 1000)

		self.Seeked(val)

	@method()
	def Seek(self, val: 'x'):
		self.protocol.cur_time = self.protocol.cur_time + (val / (1000 * 1000))

		self.Seeked(val)

	@method(name="Seeked")
	def Seeked(self, Position: 'x'):
		pass

	@method()
	async def Play(self):
		self.play()

	@method()
	async def Pause(self):
		self.pause()

	@method()
	async def Stop(self):
		self.pause()

	@method()
	async def PlayPause(self):
		self.play_pause()

	@method()
	async def Previous(self):
		if self.second >= 5:
			self.second = 0
		else:
			self.prev()

	@method()
	async def Next(self):
		try:
			self.next()
		except StopIteration:
			await self.close()

	def __repr__(self) -> str:
		return f"""self.update_processing = {self.update_processing.is_set()}
self.input = {self.input}
self.id3_info = {self.id3_info}
self.translator = {self.translator}
self.verbose = {self.verbose}
self.second = {self.second}
self.bus_name = {self.bus_name}
self.cover_name_template = {self.cover_name}
self.cover_name = {self.get_cover_name()}
self.cover_drawed = {self.cover_drawed}"""

	async def __aenter__(self):
		await self.open()

		return self

	async def __aexit__(self, exc_type, exc, tb):
		await self.close()

	def __del__(self):
		pass
