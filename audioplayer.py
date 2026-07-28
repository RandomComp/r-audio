#!/usr/bin/env python

import numpy as np

from pathlib import Path

import asyncio

from mutagen import id3

from PIL import Image

import audiostream

from audioloader import AudioLoader

import ansi

import utils

import tui

import event

from translator import Translator

from input import Input

from math import floor, ceil

from io import BytesIO

import os

from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, dbus_property, PropertyAccess
from dbus_next import Variant

def fade(samples: np.ndarray, fade_samples: int, fade_step: int, out: bool=True) -> np.ndarray:
	samples_len = len(samples)

	for i in range(0, fade_samples, fade_step):
		delta = i / fade_samples

		delta = 1 - delta if out else delta

		start = samples_len - fade_samples + i if out else i

		samples[start:(start + fade_step)] *= min(1, max(0, delta))
	
	return samples

def calculate_equalizer_bars(
	audio_chunk: np.ndarray,
	num_bars: int = 16,
	sample_rate: int = 44100
) -> np.ndarray[np.float64]:
	if num_bars < 0:
		return np.zeros(1)

	if audio_chunk is None or audio_chunk.size < num_bars:
		return np.zeros(num_bars)

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
			
		# Заменяем чистый np.max на среднеквадратичное (RMS) — это сгладит «иголки»
		# Для компенсации падения уровня берем смесь макса и среднего
		amplitude = 0.7 * np.max(band) + 0.3 * np.mean(band)
		
		vol_db = 20.0 * np.log10(amplitude + 1e-5)

		normalized = np.interp(vol_db, [-80, 0], [0, 1])
		current_bars.append(normalized)

	return np.asarray(current_bars)

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

class AudioPlayer(ServiceInterface):
	supported_extensions = (".mp4", ".mp3", ".wav", ".ogg", ".aac", ".flac")

	def __init__(self, verbose: bool=False, extra_volume: bool=False, mock: bool=False, guru: bool=False, translator: Translator=None):
		super().__init__('org.mpris.MediaPlayer2.Player')
		
		# system members:

		self.state = "Paused"

		self.seek = asyncio.Event()

		self.playback_ended = asyncio.Event()

		self.playback_error = asyncio.Event()

		self.opened = asyncio.Event()

		self.ready_to_quit = asyncio.Event()

		self.ready_to_quit.set()

		self.update_processing = asyncio.Event()

		self.volume_change = event.EventEmitter("volume_change")

		self.update_display = event.EventEmitter("update_display")

		self.old_columns, self.old_rows = tui.get_terminal_size()

		self.__lines_outputed = 0
		
		self.progress_bar_c = "━"

		self.bus = None

		self.bus_name = "org.mpris.MediaPlayer2.r_audio_player"

		self.input = None

		self.stream = None

		self.write_proc = None

		self.sound = None

		self.sound_cur_chunk = None

		self.id3_info = None
		
		self.cover_name = "r_audio_track_cover" # temporary path for track cover
		self.cover_w = 1
		self.cover_h = 1

		self.track_id = 1

		self.cover_drawed = False

		# stream settings

		self.seconds = 0

		self.sample_rate = 44100

		self.channels = 2

		# sound settings

		self.sound_sample_rate = 44100

		self.sound_channels = 2

		self.sound_sample_width = 4

		# for user members:

		self.file_name = ""

		self.translator = translator

		self.verbose = verbose

		self.second = 0

		self.volume = 1.0

		self.play_speed = 1.0

		self.chunk_seconds = 0.08
		
		self.extra_volume = extra_volume

		self.mock = mock

		self.guru = guru
	
	def __output(self, *values: object, sep: str=" ", end: str="\n") -> None:
		string = f"{sep.join(map(str, values))}{end}"

		self.__lines_outputed += len(string.splitlines())

		tui.print(string, end='')
	
	def __translated_output(self, *values: object, sep: str=" ", end: str="\n") -> None:
		self.__output(self.__translated(*values, sep=sep), end=end)
	
	def __translated(self, *values: object, sep: str=" ") -> None:
		values_str = []

		for value in values:
			value_str = str(value)

			if isinstance(value, str):
				if self.translator:
					value_str = self.translator.translate(value_str)

			values_str.append(value_str)
		
		return sep.join(values_str)

	async def open_dbus(self) -> None:
		if not self.bus:
			self.__translated_output("Opening DBus...")

			self.bus = await MessageBus().connect()

			root = AudioPlayerMPrisRootInterface()

			self.bus.export("/org/mpris/MediaPlayer2", root)
			self.bus.export("/org/mpris/MediaPlayer2", self)

			await self.bus.request_name(self.bus_name)

			self.__translated_output("Opening DBus done")
		
	async def open(self) -> None:
		if self.verbose:
			pass
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

		self.stream = audiostream.AudioStream(self.sample_rate, self.channels, dtype=audiostream.paFloat32, input=False, chunked=False, translator=self.translator)

		self.stream.open()

		await self.reset()

		self.__translated_output("Opening stream done")

		if not self.input:
			self.input = Input()

			self.input.input.subscribe(self.key_handler)

		self.opened.set()

		self.ready_to_quit.set()

		self.stream.show_device_info(self.stream.port.get_default_output_device_info(), translator=self.translator)
	
	def is_opened(self) -> bool:
		return self.opened.is_set()

	async def volume_change_handler(self, event_name: str, volume: float) -> None:
		self.volume = volume

		await self.update_display.invoke()
	
	def display_volume(self, volume: float, columns: int) -> None:
		volume_mess = tui.progress(volume, 1, columns, passed_progress_style=f"{ansi.bold}{ansi.cyan_fg}")
					
		self.__output(f"\r{ansi.clear}{volume_mess}")

		volume_status_mess = f"{self.__translated('volume')} {int(volume * 100)}%"
					
		self.__output(f"\r{ansi.clear}{tui.center(volume_status_mess, columns)}")

	def display_progress(self, second: float, seconds: float, columns: int) -> None:
		progress = tui.time_progress(second, seconds, columns)

		self.__output(f"\r{ansi.clear}{progress}", end='')
	
	def get_song_title(self) -> tuple[str, str]:
		lead, title = utils.parse_music_file_name(self.file_name.name)

		if self.id3_info:
			if self.id3_info["lead"]:
				lead = self.id3_info["lead"]
			
			if self.id3_info["title"]:
				title = self.id3_info["title"]
		
		lead = str(lead).strip()
		title = str(title).strip()
		
		return (title, lead)
	
	def display_media_info_lines(self):
		title, lead = self.get_song_title()
		
		y = 3

		size = 30

		c_w, c_h = tui.get_char_size_emulator()

		y += (size * self.cover_h * c_w) / (self.cover_w * c_h)
		
		y += 1
		
		if lead:
			y += 2

		y += 2

		return ceil(y)
	
	def display_media_info(self, x: int, y: int, max_width: int) -> None:
		columns, rows = tui.get_terminal_size()

		title, lead = self.get_song_title()
		
		size = 30

		c_w, c_h = tui.get_char_size_emulator()

		if self.id3_info != None and self.id3_info["pic"] != None and \
			(not self.cover_drawed or 
			self.old_columns != columns or self.old_rows != rows):
			tui.clean_images_kitty()

			self.cover_drawed = True

			_bytes = self.id3_info["pic"]

			path = BytesIO(_bytes)

			# print({new_keys[i]: result.get(key) for i, key in enumerate(keys)})

			img = Image.open(path)

			img = img.convert("RGB")

			self.cover_w, self.cover_h = img.size
			aspect_ratio = self.cover_h / self.cover_w
			new_height = int(size * aspect_ratio * c_w)
			img = img.resize((size * c_w, new_height))

			tui.show_image_kitty(x - (size // 2), y, img)
		
		y += (size * self.cover_h * c_w) / (self.cover_w * c_h)
		
		y += 1

		title_message = f"{ansi.bold}{ansi.red_fg}{title}{ansi.default}"
		
		tui.set_cursor_pos(x - (utils.len(title) // 2), y)
		
		self.__output(title_message, end='')

		y += 1

		if lead:
			line_width = utils.align_up(len(title) + len(lead), 2)
		
			tui.set_cursor_pos(x - (line_width // 2), y)

			self.__output(line_width * '─', end='')

			y += 1

			lead_message = f"{ansi.bold}{ansi.cyan_fg}{lead}{ansi.default}"
		
			tui.set_cursor_pos(x - (utils.len(lead) // 2), y)

			self.__output(lead_message, end='')

			y += 1

		y += 1
		
		play_symbol = "▶ " if self.is_paused() else "||"
		
		tui.set_cursor_pos(x - 1, y)

		self.__output(play_symbol)

		y += 1

	def display_update(self, event_name: str) -> None:
		if self.update_processing.is_set():
			return

		self.update_processing.set()

		columns, rows = tui.get_terminal_size()

		if self.old_columns != columns or self.old_rows != rows:
			tui.clear_screen()

		tui.set_cursor_pos(1, 1)

		if not self.guru:
			self.__translated_output(f"{ansi.bold}{ansi.cyan_fg}space{ansi.default} to play/stop")

			self.__translated_output(f"{ansi.bold}{ansi.green_fg}s{ansi.default} to seek position")

			self.__translated_output(f"{ansi.bold}{ansi.green_fg}←→{ansi.default} to seek the audio")

			self.__translated_output(f"{ansi.bold}{ansi.green_fg}↑↓{ansi.default} to control the audio volume")

			self.__translated_output(f"{ansi.bold}{ansi.green_fg}r{ansi.default} to reverse audio")

			self.__translated_output(f"{ansi.bold}{ansi.green_fg}q{ansi.default} to quit")

		self.display_volume(self.volume, columns)

		media_info_line = self.display_media_info_lines()

		self.display_media_info(columns // 2, 10, columns)

		# 32:3 1050x700:150x50 = 7x14, 1050x700:131x47=8x15

		gap = 1

		c_bars = [" ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
		c_bars_cnt = len(c_bars)

		if len(self.sound_cur_chunk) > 0:
			# max_bar_height = ((columns * 16 * 3) // 32) // 8

			max_bar_height = rows - 1 - 8 - media_info_line

			max_bar_width = (max_bar_height * 8 * 32) // (16 * 3)

			if max_bar_width >= columns:
				max_bar_width = columns

				max_bar_height = (columns * 16 * 3) // (32 * 8)
			
			total_bar_width = floor(max_bar_width / (gap + 1))
			
			bars: np.ndarray[np.float64] = calculate_equalizer_bars(self.sound_cur_chunk, total_bar_width, self.sound_sample_rate) * max_bar_height * c_bars_cnt

			for j in range(max_bar_height):
				current_terminal_y = rows - max_bar_height + 4 + j

				distance_from_floor = max_bar_height - j

				row = []
				for bar in bars:
					index = int(bar % c_bars_cnt)
						
					bar = floor(bar / c_bars_cnt)

					if bar == distance_from_floor:
						row.append(c_bars[index])
						
						row.append(" " * gap)

						continue

					if bar >= distance_from_floor:
						row.append(c_bars[-1])
					else:
						row.append(" ")
					
					row.append(" " * gap)

				tui.set_cursor_pos(1, current_terminal_y)

				row = ''.join(row)

				tui.sys.stdout.write(f"{ansi.white_fg}{tui.center(row, columns)}{ansi.default}")

		tui.set_cursor_pos(1, rows)

		# print(repr(self).replace("\n", "\n\r"), end='')
		
		self.display_progress(self.second, self.seconds, columns)

		tui.sys.stdout.flush()

		self.old_columns = columns
		self.old_rows = rows

		self.update_processing.clear()
	
	def load_audio(self, file: Path | str):
		if self.verbose:
			self.__output(f"{self.__translated('Loading')} \"{file}\"...")
		
		audio_loading_error = False

		e = ""
		
		try:
			result = AudioLoader(file)
		except Exception as _e:
			e = _e

			audio_loading_error = True
		
		if audio_loading_error:
			raise RuntimeError(f"Audio loading error: \"{file}\": {e}")

		self.file_name = file

		e = ""

		try:
			result.read()
		except Exception as _e:
			e = _e

			audio_loading_error = True
		
		if audio_loading_error:
			raise RuntimeError(f"Audio loading error: \"{file}\": {e}")

		audio = result.load()

		self.seconds = result.seconds
		self.sound_channels = result.channels
		self.sound_sample_rate = result.sample_rate

		self.sound_sample_width = result.sample_width

		if self.verbose:
			self.__translated_output("Loading done")

			self.__translated_output(f"Sound duration: {ansi.cyan_fg}{utils.format_time(self.seconds)}{ansi.default}")
			#self.__translated_output(f"Sound dBFS: {ansi.cyan_fg}{self.sound.dBFS:.2} dB{ansi.default}")
			self.__translated_output(f"Sound channels: {ansi.cyan_fg}{self.sound_channels}{ansi.default}")
			self.__translated_output(f"Sound sample rate: {ansi.cyan_fg}{self.sound_sample_rate}{ansi.default}")
			#self.__translated_output(f"Sound frame width: {ansi.cyan_fg}{result.frame_width}{ansi.default}")
			#self.__translated_output(f"Sound max sample: {ansi.cyan_fg}{result.max}{ansi.default}")
			#self.__translated_output(f"Sound max dBFS: {ansi.cyan_fg}{result.max_dBFS}{ansi.default}")
			self.__translated_output(f"Sound max possible amplitude: {ansi.cyan_fg}{result.max_possible_amplitude}{ansi.default}")
			self.__translated_output(f"Sound normalized max: {ansi.cyan_fg}{result.normalized_max}{ansi.default}")
			#self.__translated_output(f"Sound volume (rms): {ansi.cyan_fg}{result.rms}{ansi.default}")
			#self.__translated_output(f"Sound sample width: {ansi.cyan_fg}{result.sample_width}{ansi.default}")

			self.__translated_output()
		
		return audio
	
	def load_id3(self, file: Path | str) -> dict:
		"""Result is tuple of Genre Name, Title, Lead, Album, Album Picture, Record time"""

		self.__translated_output("Loading id3 audio tags... ", end='')

		id = id3.Open(file)

		self.__translated_output("done")

		keys = ["TCON", "TIT2", "TPE1", "TALB", "TDRC"]

		new_keys = ["genre", "title", "lead", "album", "date"]

		ok = False
		item_index = 0

		for i, item in enumerate(id.items()):
			if "APIC" in item[0]:
				ok = True
				item_index = i
				break

		_bytes = None

		if ok:
			_bytes = id.items()[item_index][1].data

		result: dict = dict()

		for i, key in enumerate(keys):
			value = id.get(key)

			if not value:
				result[new_keys[i]] = None

			else:
				result[new_keys[i]] = str(value)
		
		result["pic"] = _bytes

		return result

	def load(self, file: Path | str) -> None:
		file = Path(file)

		is_mp3 = file.suffix == ".mp3"

		if self.verbose:
			self.__output(f"{self.__translated('Playback file')}: \"{file}\"")

		self.sound = self.load_audio(file)

		self.id3_info = None

		if is_mp3:
			self.id3_info = self.load_id3(file)
		
			cover_dir = self.get_cover_name()

			if cover_dir and self.id3_info["pic"]:
				with open(cover_dir, "wb") as f:
					f.write(self.id3_info["pic"])

				_bytes = self.id3_info["pic"]

				img = Image.open(BytesIO(_bytes))

				img = img.convert("RGB")

				self.cover_w, self.cover_h = img.size
			
		if self.bus:
			self.emit_properties_changed({"Metadata": self.get_metadata()})

	async def play_loop(self):
		if not self.stream:
			raise RuntimeError(
				self.__translated(f"Cannot start the playing loop: self.stream (aka {self.stream}) invalid")
			)
		
		if not self.file_name:
			raise RuntimeError(
				self.__translated(f"Cannot start the playing loop: no audio to play")
			)

		if self.sound_sample_rate != self.sample_rate:
			self.__translated_output(f"Sample rate mismatch between the sound ({self.sound_sample_rate}) and the speaker ({self.sample_rate}), reconfiguration...")

			self.sample_rate = self.sound_sample_rate

			self.channels = self.sound_channels

			await self.open()

		self.update_display.subscribe(self.display_update)

		self.volume_change.subscribe(self.volume_change_handler)

		self.input.input.subscribe(self.key_handler)

		self.stream.start()

		sample_second = int(self.sound_sample_rate * self.sound_channels)

		sample_chunks = int(self.chunk_seconds * sample_second)

		fade_samples = int(5 * sample_second)

		fade_step = int(sample_second * 0.1)

		samples = self.sound

		samples = fade(samples, fade_samples, fade_step, out=False) # Fade in

		samples = fade(samples, fade_samples, fade_step, out=True) # Fade out

		samples_len = len(samples)

		try:
			while not self.playback_ended.is_set() \
				and (samples_len - sample_chunks) >= 4:
				self.ready_to_quit.clear()

				if not self.stream.is_playing.is_set():
					raise RuntimeError(self.__translated(
						"Playing loop is back, but audio output stream is stopped."
					))

				pos = int(self.second * sample_second)

				chunk_samples = samples[pos:(pos + sample_chunks)]
				chunk_samples_len = len(chunk_samples)

				#coef = ((self.second % (seconds_coef * 2)) - seconds_coef) / seconds_coef

				orig_indices = np.arange(chunk_samples_len)
				new_indices = np.linspace(0, chunk_samples_len - 1, int(chunk_samples_len * abs(self.play_speed)))

				chunk_samples = np.interp(new_indices, orig_indices, chunk_samples)

				if self.play_speed < 0:
					chunk_samples = chunk_samples[::-1]

				chunk_samples = np.clip(chunk_samples * (self.volume ** 2), -1.0, 1.0)

				self.sound_cur_chunk = chunk_samples[::2].copy()

				if self.write_proc and not self.write_proc.done():
					await self.write_proc

					self.write_proc = None
						
				if self.mock:
					self.write_proc = asyncio.create_task(asyncio.sleep(self.chunk_seconds), name="AudioStream mock write")
				else:
					self.write_proc = asyncio.create_task(self.stream.write(chunk_samples, floor(sample_chunks / abs(self.play_speed)), self.sound_sample_width), name="AudioStream write")

				self.second += self.chunk_seconds * self.play_speed

				self.ready_to_quit.set()
				
				if self.second > self.seconds:
					await self.close()

					break
				
				self.second = min(self.second, self.seconds)

				if not self.is_playing() and not self.playback_ended.is_set():
					await self.wait_for_playing()
		finally:
			if self.write_proc and not self.write_proc.done():
				try:
					await asyncio.wait_for(self.write_proc, self.chunk_seconds * 2)
				except asyncio.exceptions.TimeoutError:
					pass

				self.write_proc = None
			
			self.ready_to_quit.set()
		
			self.__output()
	
	def play(self) -> None:
		self.state = "Playing"

		if self.bus:
			self.emit_properties_changed({'PlaybackStatus': self.state})
		
		self.stream.start()
	
	def pause(self) -> None:
		self.state = "Paused"

		if self.bus:
			self.emit_properties_changed({'PlaybackStatus': self.state})
		
		self.stream.stop()
	
	async def wait_for_playing(self) -> None:
		while self.state != "Playing":
			await asyncio.sleep(0.1)
	
	def is_playing(self) -> bool:
		return self.state == "Playing"
	
	def is_paused(self) -> bool:
		return self.state == "Paused"
	
	def get_state(self) -> bool:
		return self.state
	
	async def volume_up(self, percent: float) -> None:
		await self.volume_set(self.volume_get() + percent)
	
	async def volume_down(self, percent: float) -> None:
		await self.volume_set(self.volume_get() - percent)
	
	async def volume_set(self, percent: float) -> None:
		if percent < 0:
			#if self.verbose:
			#	self.__translated_output("Volume lower than 0% isn't supported. Forced using 0%.")

			percent = 0

		if percent > 100 and not self.extra_volume:
			#if self.verbose:
			#	self.__translated_output("Extra volume disabled, please enable it to set volume under 100%")

			percent = 100

		await self.volume_change.invoke(percent / 100)

		if self.bus:
			self.emit_properties_changed({'Volume': percent})

	def volume_get(self) -> float:
		return self.volume * 100

	def seek_second(self, second: float) -> None:
		self.second = second % self.seconds

	def get_second(self) -> float:
		return self.second

	async def key_handler(self, event_name: str, input_key: str) -> None:
		# TODO: Превратить tui.get_input_byte в генератор на все классы

		seek_seconds = 1

		handled = False

		if input_key == "q":
			await self.close()

		elif input_key == " ":
			if self.is_playing():
				self.pause()
			else:
				self.play()
				
			handled = True

		elif input_key == "s":
			if self.seek.is_set():
				self.seek.clear()
			else:
				self.seek.set()
				
			handled = True

		elif input_key == "↑":
			await self.volume_up(1)
				
			handled = True

		elif input_key == "↓":
			await self.volume_down(1)
				
			handled = True
			
		elif input_key == "←":
			self.seek_second(self.second - seek_seconds)
				
			handled = True
			
		elif input_key == "→":
			self.seek_second(self.second + seek_seconds)
				
			handled = True
			
		elif input_key == "r":
			self.play_speed *= -1
				
			handled = True
			
		if handled:
			await self.update_display.invoke()
	
	async def timer(self, dur: float=1.0) -> None:
		while not self.playback_ended.is_set():
			await self.update_display.invoke()

			await asyncio.sleep(dur)

			if not self.is_playing() and not self.playback_ended.is_set():
				await self.wait_for_playing()
	
	def get_cover_name(self) -> str:
		return f"/tmp/{self.cover_name}_{self.track_id}.jpg"
	
	async def loop(self) -> None:
		tui.clear_screen()

		tui.set_cursor_pos(1, 1)

		await asyncio.gather(
			self.play_loop(),
			self.input.loop(),
			self.timer(self.chunk_seconds)
		)

		if self.cover_name:
			cover_dir = self.get_cover_name()

			if os.path.isfile(cover_dir):
				os.remove(cover_dir)

		self.track_id += 1
	
	async def reset(self) -> None:
		self.__translated_output("Reseting AudioPlayer...")

		self.second = 0

		self.playback_error.clear()

		self.playback_ended.clear()

		self.ready_to_quit.clear()

		self.cover_drawed = False

		if not self.input:
			self.input = Input()

			self.input.input.subscribe(self.key_handler)
		
		self.input.reset()

		self.play()

		self.seek.clear()

		# self.id3_info = None	
	
	async def close(self) -> None:
		self.play()

		self.playback_ended.set()

		self.seek.clear()

		self.opened.clear()

		self.input.close()

		self.id3_info = None

		if self.bus:
			await self.bus.release_name(self.bus_name)

			self.bus.disconnect()

		self.bus = None
	
	async def clean(self) -> None:
		self.update_display.unsubscribe()

		self.volume_change.unsubscribe()

		if self.input:
			self.input.input.unsubscribe()

			self.input.close()
		
			self.input = None
		
		self.__translated_output("Cleaning AudioPlayer... ")

		try:
			if self.opened.is_set():
				await self.ready_to_quit.wait()
		finally:
			self.pause()

			if self.stream:
				await self.stream.close()

				self.stream = None

			self.__translated_output("Cleaning AudioPlayer done.")

			self.opened.clear()

	@dbus_property(access=PropertyAccess.READ)
	def CanControl(self) -> 'b':
		return True

	@dbus_property(access=PropertyAccess.READ)
	def PlaybackStatus(self) -> 's':
		return self.state

	def get_metadata(self) -> 'a{sv}':
		title, lead = self.get_song_title()
		
		cover_dir = self.get_cover_name()

		return {
			"mpris:trackid": Variant("o", f"/com/r_audio/track/{self.track_id}"),
			"mpris:length": Variant("x", int(self.seconds * 1000 * 1000)),
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
		self.volume_set(val)

	@dbus_property(access=PropertyAccess.READ)
	def Position(self) -> 'x':
		return int(self.second * 1000 * 1000)

	@method()
	def SetPosition(self, _track_id: 'o', val: 'x'):
		track_id = int(str(_track_id).split("/")[-1])

		if track_id != self.track_id:
			return

		self.seek_second(val / (1000 * 1000))

		self.Seeked(val)

	@method()
	def Seek(self, val: 'x'):
		self.seek_second(self.second + (val / (1000 * 1000)))

		self.Seeked(val)
	
	@method(name="Seeked")
	def Seeked(self, Position: 'x'):
		pass

	@method()
	async def Play(self):
		self.play()
		
		await self.update_display.invoke()

	@method()
	async def Pause(self):
		self.pause()
		
		await self.update_display.invoke()

	@method()
	async def Stop(self):
		self.pause()
		
		await self.update_display.invoke()

	@method()
	async def PlayPause(self):
		if self.state == 'Playing':
			self.pause()
		else:
			self.play()
		
		await self.update_display.invoke()
			
	# @method()
	# async def Previous(self):
	# 	print("[D-Bus] Команда: ПРЕДЫДУЩИЙ ТРЕК")

	@method()
	async def Previous(self):
		self.seek_second(0)

	@method()
	async def Next(self):
		await self.close() # TODO: Сделать переключение трека на следующий вместо выхода

	def __repr__(self) -> str:
		return f"""self.state = {self.state}
self.seek = {self.seek.is_set()}
self.playback_ended = {self.playback_ended.is_set()}
self.playback_error = {self.playback_error.is_set()}
self.opened = {self.opened.is_set()}
self.ready_to_quit = {self.ready_to_quit.is_set()}
self.update_processing = {self.update_processing.is_set()}
self.input = {self.input}
self.stream = {self.stream}
self.sound = {self.sound}
self.sound_cur_chunk = {self.sound_cur_chunk}
self.id3_info = {self.id3_info}
self.seconds = {self.seconds}
self.sample_rate = {self.sample_rate}
self.channels = {self.channels}
self.sound_sample_rate = {self.sound_sample_rate}
self.sound_channels = {self.sound_channels}
self.sound_sample_width = {self.sound_sample_width}
self.file_name = {self.file_name}
self.translator = {self.translator}
self.verbose = {self.verbose}
self.second = {self.second}
self.volume = {self.volume}
self.play_speed = {self.play_speed}
self.chunk_seconds = {self.chunk_seconds}
self.extra_volume = {self.extra_volume}
self.mock = {self.mock}
self.guru = {self.guru}
self.bus_name = {self.bus_name}
self.cover_name_template = {self.cover_name}
self.cover_name = {self.get_cover_name()}
self.track_id = {self.track_id}
self.cover_drawed = {self.cover_drawed}"""
	
	async def __aenter__(self):
		await self.open()

		return self
	
	async def __aexit__(self, exc_type, exc, tb):
		await self.close()

	def __del__(self):
		pass
