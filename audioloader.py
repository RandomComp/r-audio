#!/usr/bin/env python

import subprocess

import numpy as np

from mutagen import id3, MutagenError

from listgenerator import ListGenerator
from playlist import Playlist
import utils

import asyncio

class AudioFileStream:
	def __init__(self, file: str, sample_rate: int=44100, channels: int=2, chunk_seconds: float=0.1, chunk_size: int | None=None):
		self.sample_rate = sample_rate
		self.channels = channels

		self.file = file

		if not chunk_size:
			chunk_size = int(chunk_seconds * sample_rate * channels * 2)

		self.chunk_size = chunk_size

		self.process = None

		self.read_command = [
			"ffmpeg",
			"-i", file,
			"-vn",
			"-acodec", "pcm_s16le",
			"-ar", f"{sample_rate}",
			"-ac", f"{channels}",
			"-f", "s16le",
			"-loglevel", "quiet",
			"pipe:1"
		]

		self.get_duration_command = [
			"ffprobe",
			"-v", "error",
			"-show_entries", "format=duration",
			"-of", "default=noprint_wrappers=1:nokey=1",
			file
		]

		if file.startswith(("https://youtube.com", "https://music.youtube.com")):
			self.read_command = [ # ffplay -f s16le -sample_rate 48000 -ch_layout stereo -i -
				"yt-dlp",
				"--cookies-from-browser", "firefox",
				"-f", "bestaudio",
				"-o", "-",
				file,
				"--downloader", "ffmpeg",
				"--downloader-args", "ffmpeg:-f s16le -ar 44100 -ac 2 -acodec pcm_s16le"
			]

			self.get_duration_command = [
				"yt-dlp",
				"--print", "duration",
				file
			]

		get_duration_process = subprocess.run(self.get_duration_command, capture_output=True, text=True, check=True)
		duration = get_duration_process.stdout.strip()
		self.duration = float(duration) if duration != "N/A" else np.inf

	def __iter__(self):
		return self

	def __next__(self) -> np.ndarray:
		if not self.process:
			self.process = subprocess.Popen(self.read_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

		result = self.process.stdout.read(self.chunk_size)

		if not result:
			raise StopIteration

		return np.frombuffer(result, dtype=np.int16).astype(np.float32) / 32768

	def close(self) -> None:
		if not self.process:
			return

		self.process.kill()
		self.process.wait()

		if self.process.stdout:
			self.process.stdout.close()

	def __del__(self) -> None:
		self.close()

class AudioMixer:
	def __init__(self, playlist_payback: Playlist, playlist: ListGenerator, sample_rate: int=44100, channels: int=2, chunk_seconds: float=0.1, crossfade_enabled: bool=False, crossfade_dur: float=5):
		self.playlist_payback = playlist_payback
		self.playlist = playlist

		self._cur_second = 0

		self.sample_rate = sample_rate
		self.channels = channels

		self._track_switching = 0

		self.track_id = 0

		self.old_track_id = 0
		self.previoused = False

		self._stream: AudioFileStream = AudioFileStream(self.playlist[self.track_id], sample_rate, channels, chunk_seconds)
		self._old_stream: AudioFileStream | None = None

		self._stream_volume = 1.0
		# self._pausing = False
		# self._previous_state =

		self.chunk_seconds = chunk_seconds

		# self.max_s = 30
		# self.max_s = self.max_s / chunk_seconds
		self._chunk: np.ndarray | None = None
		# self._chunk_s = 0

		self.on_id3_update = None

		self.crossfade = crossfade_enabled
		self.crossfade_dur = crossfade_dur

	@property
	def track_switching(self) -> int:
		return self._track_switching

	@track_switching.setter
	def track_switching(self, id: int) -> None:
		self._track_switching = id

		if id % 10 == 0:
			self.playlist_payback.save_db()

	@property
	def duration(self) -> float:
		return self._stream.duration

	@property
	def second(self) -> float:
		return self._cur_second

	@second.setter
	def second(self, val: float) -> None:
		if val < 0:
			self.prev()

			val = self._stream.duration - 1

		if self._cur_second < val:
			try:
				while self._cur_second < val:
					binary_stream_len = len(next(self._stream)) / 2

					self._cur_second += binary_stream_len / (self.channels * self.sample_rate)
			except StopIteration:
				self.next()

		elif val == 0:
			self._stream.close()
			self._stream = AudioFileStream(self.playlist[self.track_id], self.sample_rate, self.channels, self.chunk_seconds)
			self._cur_second = 0

		elif self._cur_second > val:
			pass
			# if (second - self._cur_second) < (self._chunk_s * self.chunk_seconds):
			# 	self._chunk_s =

	async def skip_silence(self, stream: AudioFileStream, threshold: float=-80) -> float:
		seconds = 0

		while True:
			chunk = next(stream)

			rms = np.sqrt(np.mean(chunk ** 2))

			dbfs = 20 * np.log10(rms) if rms > 0 else -100

			if dbfs >= threshold:
				break

			seconds += chunk.shape[0] / (self.channels * self.sample_rate)

			await asyncio.sleep(0.0)

		return seconds

	def next(self) -> None:
		duration = self.duration - (self.crossfade_dur / 2) if self.crossfade else self.duration

		self.playlist_payback.add_avg_listen_time(self.playlist[self.track_id], self._cur_second / duration)

		self.track_id += 1

		self.track_switching += 1

		# if self.track_id >= len(self.playlist):
		# 	raise StopIteration

		self._cur_second = 0

		if self.crossfade:
			self._old_stream = self._stream
		else:
			self._stream.close()

		self._stream = AudioFileStream(self.playlist[self.track_id], self.sample_rate, self.channels, self.chunk_seconds)

		if self.on_id3_update:
			self.on_id3_update()

	def prev(self) -> None:
		self.old_track_id = self.track_id
		self.track_id = max(0, self.track_id - 1)
		self.previoused = self.track_id != self.old_track_id

		self.track_switching += 1

		self._cur_second = 0

		if self.crossfade:
			self._old_stream = self._stream
		else:
			self._stream.close()

		self._stream = AudioFileStream(self.playlist[self.track_id], self.sample_rate, self.channels, self.chunk_seconds)

		if self.on_id3_update:
			self.on_id3_update()

	def play_pause(self) -> None:
		self.pausing = not self.pausing

	def read_chunk(self) -> None:
		# if self._chunk_s >= self.max_s:
		# 	self._chunk_s = 0

		offset = 0 # int(self._chunk_s * self.chunk_seconds * self.channels * self.sample_rate)

		try:
			arr = next(self._stream)
		except StopIteration:
			self.next()

			arr = next(self._stream)

		stream_volume = 1.0 - min(1.0, self._stream_volume)

		if self._chunk is None:
			self._chunk = np.zeros(arr.shape[0], dtype=np.float32)

		self._chunk[offset:(offset + arr.shape[0])] = arr

		if self._old_stream:
			self._chunk[offset:(offset + arr.shape[0])] = arr * np.cos(stream_volume * np.pi / 2)

			try:
				arr_old = next(self._old_stream)

				arr_old = arr_old * np.sin(stream_volume * np.pi / 2)

				self._chunk[offset:(offset + arr_old.shape[0])] += arr_old
			except StopIteration:
				self._old_stream.close()

				self._old_stream = None

		# ===========================================================================

		# diff = arr[::2] - arr[1::2]

		# arr[::2] = arr[::2] - diff
		# arr[1::2] = arr[1::2] - diff

		# ===========================================================================

	def _is_last(self) -> bool:
		return self.track_id == (len(self.playlist) - 1)

	def __next__(self) -> tuple[float, np.ndarray]:
		if self._stream is None:
			raise RuntimeError("Not AudioLoader stream")

		half_crossfade_dur = self.crossfade_dur / 2

		if self.crossfade:
			if self._cur_second <= half_crossfade_dur:
				self._stream_volume = self._cur_second / half_crossfade_dur

			if self._cur_second >= half_crossfade_dur and self._old_stream:
				self._old_stream.close()

				self._old_stream = None

			if self._cur_second >= (self.duration - half_crossfade_dur):
				self.next()

		if self.previoused and self._cur_second >= (self.duration * 0.5):
			self.playlist_payback.add_pure_listen_time(self.playlist[self.old_track_id], 0.1)

		self.read_chunk()

		# self._chunk_s += 1

		view_chunk = self._chunk.view()

		view_chunk.flags.writeable = False

		# fade_samples = int(5 * sample_second)

		# fade_step = int(sample_second * 0.1)

		# samples = fade(samples, fade_samples, fade_step, out=False) # Fade in

		# samples = fade(samples, fade_samples, fade_step, out=True) # Fade out

		time = view_chunk.shape[0] / (self.channels * self.sample_rate)

		self._cur_second += time

		return time, view_chunk

	def close(self) -> None:
		self._stream.close()
