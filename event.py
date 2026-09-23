#!/usr/bin/env python

from types import FunctionType, CoroutineType, MethodType

from typing import Any

import builtins

import tui

class EventEmitter:
	def __init__(self, name: str='', max_handlers: int = -1, silent: bool=True):
		if max_handlers == 0:
			raise RuntimeError("Maximum handlers cannot be 0.")

		self.name = name

		self.handlers: list[MethodType | FunctionType] = []

		self.max_handlers = max_handlers

		self.silent = silent

	def on(self, handler: MethodType | FunctionType) -> None:
		handler_cnt = builtins.len(self.handlers)

		if handler_cnt >= self.max_handlers and not self.max_handlers < 0:
			if not self.silent:
				tui.print(f"Maximum handlers count exceeded ({handler_cnt} >= {self.max_handlers})")

			return

		if handler not in self.handlers:
			self.handlers.append(handler)

	def dison(self, handler: MethodType | FunctionType | None=None) -> None:
		handler_cnt = builtins.len(self.handlers)

		if handler == None or handler_cnt == 1:
			if self.handlers: self.handlers.pop()

		elif handler in self.handlers:
			self.handlers.remove(handler)

	async def aemit(self, *args, **kwargs) -> list[Any]:
		corous_or_results: list[CoroutineType | Any] = \
			[handler(self.name, *args, **kwargs) for handler in self.handlers]

		results = []

		for cor_or_result in corous_or_results:
			result = None

			if isinstance(cor_or_result, CoroutineType):
				result = await cor_or_result
			else:
				result = cor_or_result

			results.append(result)

		return results

	def emit(self, *args, **kwargs) -> list[Any] | CoroutineType:
		if not self.handlers:
			if not self.silent:
				tui.print(f"No any handler subscribed for event \"{self.name}\".")

			return []

		return [handler(self.name, *args, **kwargs) for handler in self.handlers]
