#!/usr/bin/env python

from typing import AsyncIterable, Iterable, Any

import ansi

import sys

class ListGenerator:
	def __init__(self, gen: Iterable):
		self.gen = gen

		self.results = []

		self.next_index = 0
	
	def next(self):
		is_iterable = True

		try:
			result = next(self.gen)
		except TypeError:
			is_iterable = False

		if not is_iterable:
			raise TypeError(f"Cannot use ListGenerator using non-iterable type {self.gen.__class__}")

		self.results.append(result)

		return result

	def __next__(self):
		out_of_range = False

		try:
			result = self[self.next_index]
		except IndexError:
			out_of_range = True
		
		if out_of_range:
			raise StopIteration()

		self.next_index += 1

		return result

	def __iter__(self):
		self.next_index = 0

		return self

	def __getitem__(self, key: None | int | slice):
		if key == None or not isinstance(key, (int, slice)):
			raise TypeError(f"Cannot get item from {self.__repr__()} using with unsupported type object \"{key.__class__}\"")

		if not self.gen:
			return self.results[key]

		end = key

		is_slice = isinstance(key, slice)
		
		if is_slice:
			end = key.stop if not key.step or key.step > 0 else key.start
		
		out_of_range = False

		while end == None or end >= len(self.results):
			try:
				self.next()
			except StopIteration:
				if end:
					out_of_range = True

				break

		if out_of_range:
			raise IndexError("ListGenerator index out of range")

		return self.results[key]

	def __setitem__(self, key: None | int | slice, value):
		if key == None or not isinstance(key, (int, slice)):
			raise TypeError(f"Cannot set item to {self.__repr__()} using with unsupported type object \"{key.__class__}\"")

		index = key

		out_of_range = False
		
		try:
			if isinstance(key, slice):
				index = key.start if key.start else 0
			
				end = key.stop if not key.step or key.step > 0 else key.start

				end = end if end else -1

				try:
					while end < 0 or index < end:
						self.results[index] = value

						index += key.step
				
				except IndexError:
					pass

			elif isinstance(key, int):
				self.results[index] = value
				
		except IndexError:
			if end:
				out_of_range = True

		if out_of_range:
			raise IndexError("ListGenerator index out of range")
	
	def index(self, value, start: int = 0, _stop: int=-1) -> int:
		index = start

		while _stop < 0 or index < _stop:
			try:
				if self[index] == value:
					return index
			except IndexError:
				break
				
			index += 1
		
		return -1

	def replace(self, old_value, new_value, count: int=-1):
		index = count

		try:
			while index >= 0:
				if self[index] == old_value:
					self[index] = new_value
				
				index += 1
				
				index = self.index(old_value, index)
		except IndexError:
			pass

		return self
	
	def append(self, *args):
		for arg in args:
			self.results.append(arg)

		return self

	def remove(self, value):
		self.results.remove(value)

		return self

	def pop(self, index: int) -> Any:
		return self.results.pop(index)
	
	def __contains__(self, item):
		result = item in self.results

		try:
			while not result:
				cur_item = self.next()

				result = cur_item == item
		except StopIteration:
			pass
			
		return result

	def all(self) -> list:
		while True:
			try:
				self.next()
			except StopIteration:
				break
		
		return self.results

	def other(self) -> list:
		results = []

		while True:
			try:
				results.append(self[self.next_index])
			except IndexError:
				break

			self.next_index += 1
		
		return results

	def __len__(self):
		return len(self.all())

	def __str__(self):
		return self.__repr__()
	
	def __repr__(self) -> str:
		return f"ListGenerator(results={self.results}, gen={str(self.gen)})"
	
	#def _beatiful_str(self) -> str:
	#	return f"{ansi.default}ListGenerator({ansi.bold}{ansi.magenta_fg}results{ansi.default}={tui.parse_print_arr(self.results)}, {ansi.bold}{ansi.magenta_fg}gen{ansi.default}={ansi.yellow_fg}{str(self.gen)}{ansi.default})"

class AsyncListGenerator:
	def __init__(self, gen: AsyncIterable):
		self.gen = gen

		self.results = []

		self.next_index = 0
	
	async def next(self):
		# is_iterable = True

		result = None

		try:
			result = await anext(self.gen)
		except StopAsyncIteration:
			raise StopAsyncIteration
		# except TypeError:
		# 	is_iterable = False

		# if not is_iterable:
		# 	raise TypeError(f"Cannot use AsyncListGenerator using non-async-iterable type {self.gen.__class__}")
		
		if result:
			self.results.append(result)

		return result

	async def __anext__(self):
		out_of_range = False

		try:
			result = await self.get(self.next_index)
		except IndexError:
			out_of_range = True
		
		if out_of_range:
			raise StopAsyncIteration

		self.next_index += 1

		return result

	def __aiter__(self):
		self.next_index = 0

		return self

	async def get(self, key: None | int | slice):
		if key == None or not isinstance(key, (int, slice)):
			raise TypeError(f"Cannot get item from {self.__repr__()} using with unsupported type object \"{key.__class__}\"")

		if not self.gen:
			return self.results[key]

		end = key

		is_slice = isinstance(key, slice)
		
		if is_slice:
			end = key.stop if not key.step or key.step > 0 else key.start
		
		out_of_range = False
		
		while end == None or end >= len(self.results):
			try:
				await self.next()
			except StopAsyncIteration:
				if end:
					out_of_range = True

				break

		if out_of_range:
			raise IndexError("AsyncListGenerator index out of range")

		return self.results[key]

	async def __setitem__(self, key: None | int | slice, value):
		if key == None or not isinstance(key, (int, slice)):
			raise TypeError(f"Cannot set item to {self.__repr__()} using with unsupported type object \"{key.__class__}\"")

		index = key

		out_of_range = False
		
		try:
			if isinstance(key, slice):
				index = key.start if key.start else 0
			
				end = key.stop if not key.step or key.step > 0 else key.start

				end = end if end else -1

				try:
					while end < 0 or index < end:
						self.results[index] = value

						index += key.step
				
				except IndexError:
					pass

			elif isinstance(key, int):
				self.results[index] = value
				
		except IndexError:
			if end:
				out_of_range = True

		if out_of_range:
			raise IndexError("AsyncListGenerator index out of range")
	
	async def index(self, value, start: int = 0, _stop: int=-1) -> int:
		index = start

		while _stop < 0 or index < _stop:
			try:
				if await self.get(index) == value:
					return index
			except IndexError:
				break
				
			index += 1
		
		return -1

	async def replace(self, old_value, new_value, count: int=-1) -> None:
		index = count

		try:
			while index >= 0:
				if await self.get(index) == old_value:
					self[index] = new_value
				
					index += 1
				
				index = self.index(old_value)
		except IndexError:
			pass

		return self

	def pop(self, index: int=-1) -> Any:
		return self.results.pop(index)

	def remove(self, value):
		self.results.remove(value)

		return self
	
	async def __contains__(self, item):
		result = item in self.results

		try:
			while not result:
				cur_item = await self.next()

				result = cur_item == item
		except StopAsyncIteration:
			pass
			
		return result

	async def all(self) -> list:
		while True:
			try:
				await self.next()
			except StopAsyncIteration:
				break
		
		return self.results

	async def other(self) -> list:
		results = []

		while True:
			try:
				results.append(await self.get(self.next_index))
			except IndexError:
				break

			self.next_index += 1
		
		return results

	def __len__(self):
		return len(self.all())

	def __str__(self):
		return self.__repr__()
	
	def __repr__(self):
		return f"AsyncListGenerator(results={self.results}, gen={str(self.gen)})"
