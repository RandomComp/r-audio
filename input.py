#!/usr/bin/env python

from listgenerator import AsyncListGenerator

from event import EventEmitter

import tui

import asyncio

from collections.abc import AsyncGenerator

async def input_byte_gen(loop) -> AsyncGenerator[str, None]:
	while True:
		byte = await tui.get_input_byte(loop)

		yield byte

class Input:
	def __init__(self, queue: asyncio.Queue) -> None:
		loop = asyncio.get_running_loop()

		self._gen = AsyncListGenerator(input_byte_gen(loop))
		self._queue = queue

	async def peek(self, pos: int=0) -> list[str]:
		return await self._gen.get(pos + self._gen.next_index)

	async def next(self) -> str:
		return await anext(self._gen)

	async def parse_esc(self) -> str:
		input_key = "\x1B"

		next_byte = await self.peek(0)

		if next_byte == "[":
			next_byte = await self.peek(1)

			esc_arrows = ["A", "B", "C", "D"]

			if next_byte in esc_arrows:
				input_arrows = "↑↓→←"

				input_key = input_arrows[esc_arrows.index(next_byte)]

			self._gen.next_index += 2
		else:
			input_key = next_byte

		return input_key

	async def parse_esc_win(self) -> str:
		input_key = "\xe0"

		next_byte = await self.peek(0)

		esc_arrows = ["H", "P", "M", "K"]

		if next_byte in esc_arrows:
			input_arrows = "↑↓→←"

			input_key = input_arrows[esc_arrows.index(next_byte)]

			self._gen.next_index += 1
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
		while True:
			input_key = await self.next()

			input_key = await self.parse_key(input_key)

			await self._queue.put(input_key)
