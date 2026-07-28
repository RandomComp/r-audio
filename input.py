#!/usr/bin/env python

from listgenerator import AsyncListGenerator

from event import EventEmitter

import tui

import asyncio

from typing import AsyncGenerator

async def input_byte_gen(loop) -> AsyncGenerator[str, None]:
	while True:
		byte = await tui.get_input_byte(loop)

		yield byte

class Input:
	def __init__(self) -> None:
		self.input = EventEmitter("input")

		self.finished = asyncio.Event()

		loop = asyncio.get_running_loop()

		self.gen = AsyncListGenerator(input_byte_gen(loop))
	
	async def peek(self, pos: int=0) -> list[str]:
		return await self.gen.get(pos + self.gen.next_index)
	
	async def next(self, pos: int=0) -> str:
		return await self.gen.__anext__()
	
	def reset(self) -> None:
		loop = asyncio.get_running_loop()

		self.gen = AsyncListGenerator(input_byte_gen(loop))

		self.finished.clear()
	
	async def parse_esc(self) -> str:
		input_key = "\x1B"

		next_byte = await self.peek(0)

		if next_byte == "[":
			next_byte = await self.peek(1)

			esc_arrows = "ABCD"

			if next_byte in esc_arrows:
				input_arrows = "↑↓→←"

				input_key = input_arrows[esc_arrows.index(next_byte)]
					
			self.gen.next_index += 2
		else:
			input_key = next_byte

		return input_key
	
	async def parse_esc_win(self) -> str:
		input_key = "\xe0"

		next_byte = await self.peek(0)

		esc_arrows = "HPMK"

		if next_byte in esc_arrows:
			input_arrows = "↑↓→←"

			input_key = input_arrows[esc_arrows.index(next_byte)]
							
			self.gen.next_index += 1
		else:
			input_key = next_byte

		return input_key

	async def parse_key(self, input_key: str) -> str:
		if not input_key:
			return ""

		if input_key == "\x1B":
			input_key = await self.parse_esc()

		elif input_key in "\xe0\x00":
			input_key = await self.parse_esc_win()
		
		return input_key
	
	async def loop(self) -> None:
		while not self.finished.is_set():
			tasks = [
				asyncio.create_task(self.next()),
				asyncio.create_task(self.finished.wait())
			]

			done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

			input_key = '\0'

			for task in done:
				input_key = task.result()

			for task in pending:
				task.cancel()

			if self.finished.is_set():
				break

			input_key = await self.parse_key(input_key)

			stop = await self.input.invoke(input_key)

			if stop and stop[0]:
				self.finished.set()
	
	def close(self) -> None:
		self.finished.set()
