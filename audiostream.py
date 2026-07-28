#!/usr/bin/env python

import numpy as np

import asyncio

from pyaudio import PyAudio, paFloat32, paInt32, paInt24, paInt16, paInt8, paUInt8

import os

from tui import print

from translator import Translator

import ansi

class AudioStream:
	def __init__(self, sample_rate: int=44100, channels: int=2, dtype=paFloat32, input: bool=False, chunked: bool=True, chunk_seconds: float=0.5, verbose: bool=False, translator: Translator=None):
		self.port = None

		self.stream = None

		self.translator = translator

		self.sample_rate = sample_rate

		self.channels = channels

		self.dtype = dtype

		self.input = input # False means output, and True means input

		self.chunk_size = int(chunk_seconds * self.sample_rate * self.channels)

		self.chunked = chunked

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
	
	def __translated(self, *values: object, sep: str=" ") -> None:
		values_str = []

		for value in values:
			value_str = str(value)

			if isinstance(value, str):
				if self.translator:
					value_str = self.translator.translate(value_str)

			values_str.append(value_str)
		
		return sep.join(values_str)

	def show_device_info(self, device: dict, translator: Translator=None):
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
			devnull = os.open(os.devnull, os.O_WRONLY)

			original_stderr = os.dup(2)

			os.dup2(devnull, 2)

			self.port = PyAudio()

			os.dup2(original_stderr, 2)

			os.close(original_stderr)

			os.close(devnull)

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

	async def __write_wrapper(self, frames: np.ndarray, frames_size: int, bytes_per_frame: int=4) -> None:
		frames = bytes(frames.astype(np.float32))

		frames_len = len(frames)

		if frames_len == 0 or frames_size <= 0 or self.finished.is_set():
			#print(frames_size, self.finished.is_set())

			return

		self.ready_to_finish.clear()

		frames_size = min(frames_len, frames_size) // bytes_per_frame

		await self.async_loop.run_in_executor(None, self.stream.write, frames, frames_size)

		self.ready_to_finish.set()
	
	async def __write_chunk(self, frames: np.ndarray, bytes_per_frame: int=4) -> None:
		if not self.stream:
			raise IOError(self.__translated("Invalid stream."))
		
		frames_len = len(frames)

		frames_size = self.chunk_size

		if frames_size == -1:
			frames_size = frames_len

		await self.__write_wrapper(frames, frames_size, bytes_per_frame)
	
	def next_chunk(self, _frames: np.ndarray, frames_size: int=-1):
		frames = _frames.copy()

		frames_len = len(frames)
		
		if frames_size == 0: return

		if frames_size == -1: frames_size = frames_len

		st_i = 0

		while st_i <= frames_size:
			chunk = frames[st_i:(st_i + self.chunk_size)]

			frames_size = min(frames_len, frames_size)

			yield chunk

			st_i += self.chunk_size

	async def write(self, frames: np.ndarray, frames_size: int=-1, bytes_per_frame: int=4) -> None:
		if not self.stream:
			raise IOError(self.__translated("Invalid stream."))
		
		await self.is_playing.wait()
		
		if frames_size == 0: return
		
		frames_len = len(frames)

		if frames_size == -1: frames_size = frames_len

		frames = np.clip(frames, -1.0, 1.0)

		if self.chunked:
			for chunk in self.next_chunk(frames, frames_size):
				await self.__write_chunk(chunk, bytes_per_frame)
		else:
			frames_size = min(frames_len, frames_size)
			
			await self.__write_wrapper(frames, frames_size, bytes_per_frame)
	
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
