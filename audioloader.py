#!/usr/bin/env python

import audioread

from pydub import AudioSegment

from pathlib import Path

import numpy as np

class AudioLoader:
	def __init__(self, file: Path | str, segment_dur: int=30):
		file = Path(file).resolve()

		if not file.is_file():
			raise FileNotFoundError(f"No file specified \"{str(file)}\"")

		self.file = file

		self.seconds = 0

		self.sample_rate = 0

		self.channels = 0

		self.sample_width = 0

		self.max_possible_amplitude = 0

		self.normalized_max = 0

		self.segment_dur = segment_dur

		self.next_seconds = 0

		self.next_sample_rate = 0

		self.next_channels = 0
	
	def load(self):
		if not self.file:
			raise RuntimeError("No any file to load")
		
		audio = AudioSegment.from_file(self.file)

		self.sample_width = audio.sample_width

		dtype = np.int32

		if self.sample_width == 1:
			dtype = np.int8

		elif self.sample_width == 2:
			dtype = np.int16

		elif self.sample_width == 4:
			dtype = np.int32
		
		self.max_possible_amplitude = (2 ** ((self.sample_width * 8) - 1)) - 1
		
		audio = np.asarray(np.frombuffer(audio.raw_data, dtype=dtype), dtype=np.float32)

		mask = np.isnan(audio) | np.isinf(audio)

		if np.any(mask):
			x = np.arange(len(audio))

			audio[mask] = np.interp(x[mask], x[~mask], audio[~mask])

		self.normalized_max = self.max_possible_amplitude

		audio = audio / self.normalized_max

		return audio
	
	def read(self) -> None:
		backend_error = False

		try:
			with audioread.audio_open(self.file) as audio:
				self.sample_rate = audio.samplerate

				self.seconds = audio.duration

				self.channels = audio.channels

				print(audio)
		except audioread.exceptions.NoBackendError:
			backend_error = True
		
		if backend_error:
			raise RuntimeError(f"No available backend")
	
	def close(self) -> None:
		pass
