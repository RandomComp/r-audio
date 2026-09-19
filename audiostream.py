#!/usr/bin/env python

import numpy as np

import asyncio

from pyaudio import PyAudio, paFloat32, paInt32, paInt24, paInt16, paInt8, paUInt8

from tui import print

from translator import Translator

import ansi

class AudioStream:
	def __init__(self, sample_rate: int=44100, channels: int=2, dtype=paFloat32, input: bool=False, chunk_size: float=0.08, verbose: bool=False, translator: Translator=None):
		self.port = None

		self.stream = None

		self.translator = translator

		self.sample_rate = sample_rate
		self.channels = channels
		self.chunk_size = chunk_size * sample_rate * channels

		self.dtype = dtype

		self.input = input # False means output, and True means input

		self.verbose = verbose

		self.async_loop = asyncio.get_running_loop()

		self.ready_to_finish = asyncio.Event()

		self.ready_to_finish.set()

		self.finished = asyncio.Event()

		self.is_playing = asyncio.Event()

		self.write_proc = None

	def __output(self, *values: object, sep: str=" ", end: str="\n") -> None:
		print(*values, sep=sep, end=end)

	def __translated_output(self, *values: object, sep: str=" ", end: str="\n") -> None:
		self.__output(self.__translated(*values, sep=sep), end=end)

	def __translated(self, *values: object, sep: str=" ") -> str:
		values_str: list[str] = []

		for value in values:
			value_str = str(value)

			if isinstance(value, str) and self.translator:
				value_str = self.translator.translate(value_str)

			values_str.append(value_str)

		return sep.join(values_str)

	def show_device_info(self, device: dict, translator: Translator | None=None):
		device_name_str = self.__translated("Device name")

		device_index_str = self.__translated("Index")

		device_max_output_channels_str = self.__translated("Max output channels")

		device_default_output_latency_str = self.__translated("Default output latency")

		device_default_sample_rate_str = self.__translated("Default sample rate")

		self.__output(f"{device_name_str}: {ansi.green_fg}\"{device['name']}\"{ansi.default}")

		self.__output(f"\t{device_index_str}: {ansi.cyan_fg}{device['index']}{ansi.default}")

		self.__output(f"\t{device_max_output_channels_str}: {ansi.cyan_fg}{device['maxOutputChannels']}{ansi.default}")

		self.__output(f"\t{device_default_output_latency_str}: {ansi.cyan_fg}{device['defaultHighOutputLatency']:.4}{ansi.default} - {ansi.cyan_fg}{device['defaultLowOutputLatency']:.4}{ansi.default} ms")

		self.__output(f"\t{device_default_sample_rate_str}: {ansi.cyan_fg}{device['defaultSampleRate']}{ansi.default}")

	def open(self) -> None:
		if self.verbose:
			self.__translated_output("Opening AudioStream...")

		if self.port == None:
			self.port = PyAudio()

		self.is_playing.clear()

		self.close_stream()

		self.stream = self.port.open(self.sample_rate, self.channels, self.dtype, input=self.input, output=not self.input, frames_per_buffer=1024)

		self.is_playing.set()

		if self.verbose:
			self.__translated_output("Opening AudioStream done")

	def start(self) -> None:
		# if self.stream != None and not self.is_playing.is_set():
		# 	self.stream.start_stream()

		self.is_playing.set()

	async def write(self, frames: np.ndarray, num_frames: int|None=None) -> None:
		frames_bytes = frames.tobytes()

		self.ready_to_finish.clear()

		await self.is_playing.wait()

		await self.async_loop.run_in_executor(None, self.stream.write, frames_bytes, num_frames, False)

		self.ready_to_finish.set()

	async def read(self) -> None:
		raise NotImplementedError()

	def stop(self) -> None:
		# if self.stream != None and self.is_playing.is_set():
		# 	self.stream.stop_stream()

		self.is_playing.clear()

	def close_stream(self) -> None:
		if self.stream != None:
			self.stream.stop_stream()

			self.stream.close()

			self.stream = None

	async def close(self) -> None:
		if self.verbose:
			self.__translated_output("Cleaning AudioStream...")

		wait_task = None

		try:
			if self.is_playing.is_set():
				wait_task = asyncio.create_task(self.ready_to_finish.wait())

				await asyncio.wait_for(wait_task, timeout=5)
		except asyncio.exceptions.TimeoutError:
			if self.verbose:
				self.__translated_output("Timeouted.")

			if wait_task != None:
				wait_task.cancel()

			self.ready_to_finish.set()
		finally:
			self.is_playing.clear()

			self.close_stream()

			if self.port != None:
				self.port.terminate()

				self.stream = None

			self.finished.set()

		if self.verbose:
			self.__translated_output("Cleaning AudioStream done.")

	async def __aenter__(self):
		self.start()

		return self

	async def __aexit__(self, exc_type, exc_value, traceback) -> bool:
		await self.close()

		return False
