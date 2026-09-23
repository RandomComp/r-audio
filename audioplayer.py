#!/usr/bin/env python

import io

import numpy as np

import asyncio

import audiostream

from audioloader import AudioMixer

from listgenerator import ListGenerator
from playlist import Playlist

import tui

from translator import Translator

import json

import base64

import traceback

import utils

from PIL import Image, UnidentifiedImageError

from pathlib import Path

def calculate_equalizer_bars(
	audio_chunk: np.ndarray,
	old_chunk: np.ndarray,
	old_chunk_id: int,
	num_bars: int = 16,
	sample_rate: int = 44100,
) -> np.ndarray | None:
	if num_bars < 0:
		return

	audio_chunk = np.ascontiguousarray(audio_chunk, dtype=np.float32).flatten()
	chunk_len = len(audio_chunk)
	window = np.hanning(chunk_len)

	# Спектр, нормированный на длину чанка
	fft_data = np.abs(np.fft.rfft(audio_chunk * window)) / chunk_len

	# Генерируем логарифмические МУЗЫКАЛЬНЫЕ частоты от 20 Гц до 20 кГц
	target_freqs = np.logspace(np.log10(20), np.log10(20000), num_bars + 1)

	# Переводим физические частоты в индексы массива FFT
	# Формула: индекс = частота * длина_чанка / частота_дискретизации
	indices = (target_freqs * chunk_len / sample_rate).astype(int)

	indices = np.clip(indices, 0, len(fft_data))

	current_bars = []
	for i in range(num_bars):
		start_idx = indices[i]
		end_idx = indices[i+1]

		if start_idx == end_idx:
			end_idx = min(start_idx + 1, len(fft_data))

		band = fft_data[start_idx:end_idx]

		if len(band) == 0:
			current_bars.append(0)
			continue

		amplitude = np.max(band)

		vol_db = 20.0 * np.log10(amplitude + 1e-5)

		normalized = np.interp(vol_db, [-80, 0], [0, 1])
		current_bars.append(normalized)

	old_chunk_id = old_chunk_id % 10

	return np.asarray(current_bars)

	# return ((np.asarray(current_bars) * old_chunk_id) + (np.asarray(old_chunk) * (10 - old_chunk_id))) / 10

class BytesEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, bytes):
            return base64.b64encode(obj).decode("utf-8")
        return super().default(obj)

class AudioPlayer:
	supported_extensions = (".mp4", ".mp3", ".wav", ".ogg", ".aac", ".flac")

	def __init__(self, config: dict, translator: Translator | None=None):
		super().__init__()

		# system members:

		self.state = "Paused"

		self.playback_ended = asyncio.Event()

		self.opened = asyncio.Event()
		self.finished = asyncio.Event()

		self.ready_to_quit = asyncio.Event()
		self.ready_to_quit.set()

		self.something_changed = asyncio.Event()
		self.something_changed.clear()
		self.what_changed: list[str] = []

		self.__lines_outputed = 0

		self.stream = None

		self.sound_cur_chunk = None

		self.playlist: ListGenerator | None = None

		self.id3_info = None

		self.old_chunk: np.ndarray = np.zeros(256)
		self.old_chunk_id: int = 0

		self.config = config

		self.addr = self.config["server"]["addr"].split(":")
		self.server = None

		# stream settings

		self.sample_rate = 44100
		self.channels = 2
		self.chunk_seconds: float = self.config["audio"]["chunk_dur_s"]
		self.mock = self.config["audio"]["mock"]

		self.volume = self.config["audio"]["default_volume"]
		self.play_speed = 1.0

		self.translator = translator

		self.verbose = self.config["server"]["logs"]

		# self.

		# TODO: генерировать ID для всех клиентов и отмасштабировать обложку перед отправкой

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

	def send_text(self, writer: asyncio.StreamWriter, text: str) -> None:
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

	async def open(self) -> None:
		# if self.verbose:
			# print("Available sound devices for playback:\n")

			# for i in range(self.audio.get_device_count()):
			# 	device = self.audio.get_device_info_by_index(i)

			# 	if (device['maxOutputChannels'] == 0): continue

			# 	show_device_info(device, translator=self.translator)

			# 	print()

		self.write_proc = None

		if self.stream:
			if self.verbose:
				self.__translated_output("Reopening stream...")

			await self.stream.close()

			self.stream = None
		elif self.verbose:
			self.__translated_output("Opening stream...")

		self.stream = audiostream.AudioStream(self.sample_rate, self.channels, dtype=audiostream.paFloat32, input=False, translator=self.translator)

		self.stream.open()

		await self.reset()

		self.opened.set()

		self.ready_to_quit.set()

		self.stream.show_device_info(dict(self.stream.port.get_default_output_device_info()), translator=self.translator)

		addr, port = self.addr

		self.server = await asyncio.start_server(self.handle_client, addr, port)

	async def next(self) -> None:
		try:
			self.audio.next()
		except StopIteration:
			await self.close()

			# self.state = "Nothing to play"

		self.something_changed.set()

	async def prev(self) -> None:
		self.audio.prev()

		self.something_changed.set()

	def play(self) -> None:
		self.state = "Playing"

		self.stream.start()

		self.something_changed.set()
		self.what_changed.append("state")
		self.what_changed.append("cur_time")

	def pause(self) -> None:
		self.state = "Paused"

		self.stream.stop()

		self.something_changed.set()
		self.what_changed.append("state")
		self.what_changed.append("cur_time")

	def _id3_to_json(self) -> tuple[str, str]:
		text = ""

		try:
			text = json.dumps(self.id3_info, ensure_ascii=False)
		except Exception as e:
			traceback.print_exc()

			return "ERROR", str(e)

		return "OK", text

	def get_info(self, what_changed: list[str] | None=None) -> str:
		data = {
			"cur_time": self.second,
			"duration": self.audio.duration,
			"volume": self.volume,
			"state": self.state,
			"playlist_track_id": self.playlist_track_id,
			"id": self.track_id,
			"id3": self.id3_info,
		}

		if not what_changed:
			return json.dumps(data, ensure_ascii=False, cls=BytesEncoder)

		result = {}

		for change in what_changed:
			if change != "text":
				result[change] = data[change]

				continue

			result["text"] = {"text": {}, "text_status": "not found"}

			db_file = utils.query(self.playlist_payback.db["files"], ["id"], self.track_id, [["text"], ["text_status"]])

			if len(db_file) <= 0:
				result["text"]["text"] = {}

				continue

			db_file = db_file[0]

			result["text"]["text_status"] = db_file["text_status"]

			if db_file["text_status"] == "not found":
				result["text"]["text"] = {}

				continue

			text = Path(db_file["text"]).read_text(encoding="UTF-8")

			if db_file["text_status"] == "synced":
				result_text = {}

				for line in text.splitlines():
					line = line[1:].strip()

					minute, line = line.split(":", maxsplit=1)
					second, line = line.split("]", maxsplit=1)

					line = line[1:].strip()

					time = float(minute) * 60.0 + float(second)

					result_text[time] = line

				result["text"]["text"] = result_text
			else:
				result["text"]["text"] = text

		return json.dumps(result, ensure_ascii=False, cls=BytesEncoder)

	async def do_next(self, argv: list[str]) -> tuple[str, str]:
		await self.next()

		return "OK", ""

	async def do_prev(self, argv: list[str]) -> tuple[str, str]:
		await self.prev()

		return "OK", ""

	async def do_pause(self, argv: list[str]) -> tuple[str, str]:
		self.pause()

		return "OK", ""

	async def do_play(self, argv: list[str]) -> tuple[str, str]:
		self.play()

		return "OK", ""

	async def do_play_pause(self, argv: list[str]) -> tuple[str, str]:
		if self.is_playing():
			self.pause()
		else:
			self.play()

		return "OK", ""

	async def do_update(self, argv: list[str]) -> tuple[str, str]:
		if self.something_changed.is_set():
			answer = self.get_info(self.what_changed)

			self.something_changed.clear()
			self.what_changed = []

			return "OK", answer

		return "OK", ""

	async def do_get_info(self, argv: list[str]) -> tuple[str, str]:
		return "OK", self.get_info(argv[1:])

	async def do_get_cover(self, argv: list[str]) -> tuple[str, str]:
		if len(argv) <= 2:
			return "ERROR", "Expected id from db and size"

		id = argv[1]
		size = int(argv[2])

		result = utils.query(self.playlist_payback.db["files"], ["id"], id, [["title"], ["lead"], ["cover"]])

		if len(result) <= 0:
			return "ERROR", f"Not known track with id {id}"

		result = result[0]

		name = f"{', '.join(result["lead"])} -- {result["title"]}"

		if "cover" not in result:
			return "ERROR", f"Not known field 'cover' for track id {id} ({name})"

		cover = Path(result["cover"])

		if not cover.is_file():
			return "ERROR", f"Cover unavailable for {id} ({name})"

		if size == 0:
			return "ERROR", "Invalid size"

		try:
			cover_img = Image.open(cover)

		except (UnidentifiedImageError, FileNotFoundError) as e:
			return "ERROR", f"An error occured while image reading: {e}"

		square_size = min(cover_img.width, cover_img.height)

		x = (cover_img.width - square_size) // 2
		y = (cover_img.height - square_size) // 2

		cover_img = cover_img.crop((x, y, x + square_size, y + square_size))

		cover_img_resized = cover_img.resize((size, size))

		cover_bytes = io.BytesIO()

		cover_img_resized.save(cover_bytes, format="JPEG")

		cover_img_resized.close()
		cover_img.close()

		cover_bytes.seek(0)

		cover_base64 = str(base64.b64encode(cover_bytes.read()), encoding="ascii")

		result = {"cover": cover_base64}

		return "OK", json.dumps(result)

	async def do_db(self, argv: list[str]) -> tuple[str, str]:
		if len(argv) <= 1:
			return "ERROR", "Expected subcommand for 'db'"

		if argv[1] == "query":
			if len(argv) <= 2:
				return "ERROR", "Expected category for 'query' subcommand of 'db'"

			category = argv[2]

			if len(argv) <= 3:
				return "ERROR", f"Expected key for 'db|query|{category}'"

			key = argv[3]
			values = argv[4:]

			result = utils.query(self.playlist_payback.db["files"], category.split("."), key, [value.split(".") for value in values])
			result = json.dumps(result, ensure_ascii=False)

			return "OK", result

		elif argv[1] == "set":
			if len(argv) <= 4:
				return "ERROR", "Expected key and value for 'set' subcommand of 'db'"

			fields = argv[2].split(".")

			pointer = self.playlist_payback.db

			end_field = fields[-1]

			for field in fields[:-1]:
				if not isinstance(pointer, dict) or field not in pointer:
					return "ERROR", f"Not known field {argv[2]}"

				pointer = pointer[field]

			pointer[end_field] = argv[3]
		else:
			return "ERROR", f"Unknown {argv[1]} subcommand of 'db'"

		return "OK", ""

	async def do_playlist(self, argv: list[str]) -> tuple[str, str]:
		if len(argv) >= 2:
			if argv[1] == "appendbegin":
				songs = argv[2:]

				self.playlist = songs + self.playlist

			elif argv[1] == "appendend":
				songs = argv[2:]

				self.playlist.extend(songs)

			elif argv[1] == "appendnext":
				songs = argv[2:]

				index = self.playlist_track_id + 1

				self.playlist[index:index] = songs
			else:
				return "ERROR", f"Unknown {argv[1]} subcommand of 'playlist'"

		self.audio.playlist = self.playlist

		self.something_changed.set()

		result = json.dumps(self.playlist, ensure_ascii=False)

		return "OK", result

	async def do_quit(self, argv: list[str]) -> tuple[str, str]:
		await self.close()

		return "OK", ""

	async def handle_message(self, command: str, argv: list[str]) -> tuple[str, str] | None:
		functions = {
			"next": self.do_next,
			"prev": self.do_prev,
			"pause": self.do_pause,
			"play": self.do_play,
			"play_pause": self.do_play_pause,
			"playlist": self.do_playlist,
			"db": self.do_db,
			"cover": self.do_get_cover,
			"info": self.do_get_info,
			"update": self.do_update,
			"quit": self.do_quit,
		}

		if command in functions:
			function = functions[command]

			status, answer = await function(argv)

			return status, answer

		return "ERROR", f"UNKNOWN COMMAND '{command}'"

	async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
		ret = False

		try:
			while not ret:
				message = await self.read_text(reader)

				if not message:
					ret = True

					break

				print(f"{message=}")

				argv = message.split("|")
				command = argv[0]

				status = answer = ""

				status_and_answer = await self.handle_message(command, argv)

				if not status_and_answer:
					continue

				status, answer = status_and_answer

				answer = f"{status}|{' '.join(argv)}|{answer}"

				print(f"answer='{answer[:300]}'")

				self.send_text(writer, answer)

				await writer.drain()
		except ConnectionRefusedError:
			ret = True

		writer.close()

		await writer.wait_closed()

	def is_opened(self) -> bool:
		return self.opened.is_set()

	def get_song_title(self) -> tuple[str, str]:
		if self.id3_info:
			return self.id3_info["title"], self.id3_info["lead"]

		return "", ""

	def _load_id3(self) -> None:
		track = self.playlist[self.playlist_track_id]

		track_db = self.playlist_payback.db["files"][track]

		keys = ["genre", "title", "lead", "album", "year"]

		self.id3_info = {key: track_db[key] for key in keys}
		self.track_id = track_db["id"]

		self.something_changed.set()

	def load(self, playlist_payback: Playlist) -> None:
		playlist = ListGenerator(playlist_payback.gen())

		self.playlist_payback = playlist_payback

		self.playlist = playlist

		result = AudioMixer(playlist_payback, playlist, self.sample_rate, self.channels, self.chunk_seconds, self.config["audio"]["crossfade"], self.config["audio"]["crossfade_time_s"])

		self.audio = result
		self.audio.on_id3_update = self._load_id3

		self._load_id3()

	@property
	def playlist_track_id(self) -> int:
		return self.audio.playlist_track_id

	async def play_loop(self) -> None:
		if not self.stream:
			raise RuntimeError(
				self.__translated("Cannot start the playing loop: self.stream is None")
			)

		self.stream.start()

		try:
			while not self.playback_ended.is_set():
				self.ready_to_quit.clear()

				if not self.stream.is_playing.is_set():
					raise RuntimeError(self.__translated(
						"Playing loop is back, but audio output stream is stopped."
					))

				try:
					time, chunk = self.audio.__next__()
				except StopIteration:
					await self.close()

					break

				chunk = chunk * (self.volume ** 3)

				chunk_frames = chunk.shape[0] // self.channels

				#coef = ((self.second % (seconds_coef * 2)) - seconds_coef) / seconds_coef

				# orig_indices = np.arange(chunk_samples_len)
				# new_indices = np.linspace(0, chunk_samples_len - 1, int(chunk_samples_len * abs(self.play_speed)))

				# chunk_samples = np.interp(new_indices, orig_indices, chunk_samples)

				# if self.play_speed < 0:
				# 	chunk_samples = chunk_samples[::-1]

				self.sound_cur_chunk = chunk[::2].copy()

				if self.mock:
					await asyncio.sleep(time)
				else:
					await self.stream.write(chunk, chunk_frames)

				self.ready_to_quit.set()

				if not self.is_playing() and not self.playback_ended.is_set():
					await self.wait_for_playing()
		finally:
			self.ready_to_quit.set()

	async def loop(self) -> None:
		await self.play_loop()

	async def wait_for_playing(self) -> None:
		while self.state != "Playing":
			await asyncio.sleep(0.1)

	def is_playing(self) -> bool:
		return self.state == "Playing"

	def is_paused(self) -> bool:
		return self.state == "Paused"

	def volume_up(self, percent: float) -> None:
		self.volume_set(self.volume_get() + percent)

	def volume_down(self, percent: float) -> None:
		self.volume_set(self.volume_get() - percent)

	def volume_set(self, percent: float) -> None:
		self.volume = min(1, max(0, percent))

		self.something_changed.set()
		self.what_changed.append("volume")

	def volume_get(self) -> float:
		return self.volume

	@property
	def second(self) -> float:
		return self.audio.second

	@second.setter
	def second(self, val: float) -> None:
		self.audio.second = val

		self.something_changed.set()
		self.what_changed.append("cur_time")

	async def reset(self) -> None:
		if self.verbose:
			self.__translated_output("Reseting AudioPlayer...")

		self.playback_ended.clear()

		self.finished.clear()

		self.ready_to_quit.clear()

		self.play()

		# self.id3_info = None

	async def close(self) -> None:
		self.playback_ended.set()

		self.opened.clear()

		self.finished.set()

		self.id3_info = None

	async def clean(self) -> None:
		if self.verbose:
			self.__translated_output("Cleaning AudioPlayer... ")

		if self.opened.is_set():
			await self.ready_to_quit.wait()

		self.pause()

		if self.stream:
			await self.stream.close()

			self.stream = None

		if self.server:
			self.server.close()

			await self.server.wait_closed()

			self.server = None

		if self.verbose:
			self.__translated_output("Cleaning AudioPlayer done.")

		self.opened.clear()

	def __repr__(self) -> str:
		return f"""self.state = {self.state}
self.playback_ended = {self.playback_ended.is_set()}
self.opened = {self.opened.is_set()}
self.ready_to_quit = {self.ready_to_quit.is_set()}
self.stream = {self.stream}
self.audio = {self.audio}
self.sound_cur_chunk = {self.sound_cur_chunk}
self.id3_info = {self.id3_info}
self.audio.duration = {self.audio.duration}
self.sample_rate = {self.sample_rate}
self.channels = {self.channels}
self.translator = {self.translator}
self.verbose = {self.verbose}
self.second = {self.second}
self.volume = {self.volume}
self.play_speed = {self.play_speed}
self.chunk_seconds = {self.chunk_seconds}
self.mock = {self.mock}
self.cover_name = {self.get_cover_name()}
self.playlist_track_id = {self.playlist_track_id}"""

	async def __aenter__(self):
		await self.open()

		return self

	async def __aexit__(self, exc_type, exc, tb):
		await self.close()

	def __del__(self):
		pass
