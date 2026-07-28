#!/usr/bin/env python

import asyncio

from time import time

from types import FunctionType

import tui

import ansi

import event

from translator import Translator

from input import Input

from listgenerator import ListGenerator

class Menu:
	def __init__(self, options: list[str]=[], full_options: list[str]=None, title: str="Menu", info: str=None, multiple: bool=False, translator: Translator=None) -> None:
		self.options = options

		if not full_options:
			full_options = options

		self.full_options = full_options

		self.options = options

		self.option_cnt = len(options)

		self.title = title

		self.translator = translator

		if not info:
			info = self.__translated("""↑↓→← -- navigate
f -- find objects by name (double esc to exit)
backspace -- go previous location
enter -- select
a -- multiple selection mode
q -- quit menu""")

		self.info = info
		
		self.multiple = multiple

		self.input_event = event.EventEmitter("input")

		self.__menu_update = event.EventEmitter("menu_update")

		self.input = Input()

		self.on_update_subcribe(self.menu_cli_frame)

		self.input.input.subscribe(self.menu_default_input_handler)

		self.finished = asyncio.Event()

		self.find_buf = ""

		self.state_string = ""

		self.find = asyncio.Event()

		self.shift_select = False

		self.commands = False

		self.screen2 = False

		self.command_buf = ""

		self.shift_option_start = 0

		self.highlighted_option = 0

		self.highlighted_options = []

		self.old_sel_item = 0

		self.options_display_start = 0

		self.selected_options: list[str] = []

		self.filters: list[str] | None = []

		self.__lines_outputed = 0

		self.__selected_str = self.__translated("selected")

		self.__selected_item_str = self.__translated("selected item")

		#self.console = utils.VirtualConsole()
	
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

			if isinstance(value, str) and self.translator:
				value_str = self.translator.translate(value_str)

			values_str.append(value_str)
		
		return sep.join(values_str)
	
	def __output_update(self) -> None:
		columns, rows = tui.get_terminal_size()

		for _ in range(self.__lines_outputed, rows - 1):
			tui.print("\r".ljust(columns))

		self.__lines_outputed = 0

		tui.set_cursor_pos(0, 0)
	
	def use_default_handlers(self) -> None:
		self.on_input_subcribe(self.menu_default)
	
	def handle_command(self, command: str) -> None:
		self.__output(command)
	
	def handle_command_keys(self, input_key: str) -> None:
		if input_key == "\x1B":
			self.commands = False
		elif input_key in "\x08\x7F":
			self.command_buf = self.command_buf[:-1]
		elif input_key in "\n\r":
			self.handle_command(self.command_buf)

			self.command_buf = ""
		else:
			self.command_buf += input_key
	
	async def menu_default_input_handler(self, event_name: str, input_key: str) -> None:
		if input_key == "↑":
			self.highlighted_option -= 1
		elif input_key == "↓":
			self.highlighted_option += 1
			
		elif self.commands:
			self.handle_command_keys(input_key)
	
		# TODO: Нормализовать байтовую строку input_key и обычную строку к единому виду в Windows
		
		self.highlighted_options = self.highlighted_option
		
		if self.shift_select:
			if self.highlighted_option >= self.shift_option_start:
				self.highlighted_options = (self.shift_option_start, self.highlighted_option)
			else:
				self.highlighted_options = (self.highlighted_option, self.shift_option_start)
		
		push_key = True

		if not self.find.is_set() and not self.commands:
			push_key = False

			if input_key == "q":
				self.input.close()

				self.finished.set()

				push_key = True
			
			elif input_key == "a":
				self.shift_select = not self.shift_select

				self.shift_option_start = self.highlighted_option
			
			elif input_key == ":":
				self.commands = True
			else:
				push_key = True

		if push_key and not self.commands:
			await self.input_event.invoke(self.highlighted_options, input_key)
				
		await self.update()
	
	def get_view_full_options(self) -> list:
		return ListGenerator(option for option in self.full_options \
		  		if self.find_buf.lower() in str(option).lower())
	
	def get_view_options(self) -> list:
		return ListGenerator((i, option) for i, option in enumerate(self.full_options) \
		  		if self.find_buf.lower() in str(option).lower())
	
	def select(self, option: int) -> None:
		view_options = self.get_view_full_options()
			
		option_name = view_options[option]

		if option_name not in self.selected_options:
			self.selected_options.append(option_name)
		else:
			self.selected_options.remove(option_name)

	def set_options(self, full_options: list[str]=None, options: list[str]=[]) -> None:
		if not full_options:
			full_options = options

		self.full_options = full_options

		self.options = options

		self.option_cnt = len(options)
	
	def display_option(self, option: str, max_width: int, is_selected: bool, full_option: str=None) -> None:
		selected_marker = "[ ]" if self.multiple else ""

		option_width = max_width - 3

		if self.multiple:
			option_width -= 3

			if full_option:
				selected_marker = "[X]" if full_option in self.selected_options else "[ ]"
		
		dur = time()

		if is_selected:
			option = tui.text_scroll(option, option_width, dur)

			option = tui.ljust(option, option_width)
				
			self.__output(f"│{selected_marker} {ansi.inverse}{option}{ansi.default}│")
		else:
			option_len = len(option)

			option = option[:option_width - 3]

			if option_len > option_width:
				option += f"{ansi.bold}{ansi.red_fg}...{ansi.default}"

			option = tui.ljust(option, option_width)

			self.__output(f"│{selected_marker} {ansi.default}{option}{ansi.default}│")
	
	async def menu_cli_frame(self, event_name: str, filters: list[str]) -> None:
		columns, rows = tui.get_terminal_size()

		dur = time()
			
		view_options = [i for i, _ in self.get_view_options()]
			
		view_options_cnt = len(view_options)

		self.highlighted_option = 0 if view_options_cnt <= 0 else self.highlighted_option % view_options_cnt

		options_string = '\", \"'.join(map(str, self.selected_options))

		selected_mess = f"{len(self.selected_options)} {self.__selected_str}: "

		selected_string = tui.text_scroll(f"\"{options_string}\"", columns - len(selected_mess) - 1, dur)

		shift_option_end = self.highlighted_option

		self.state_string = f"{self.__selected_item_str}: "

		if self.shift_select:
			self.state_string += f"[{self.shift_option_start + 1}...{shift_option_end + 1}]/{view_options_cnt}"
		else:
			self.state_string += f"{self.highlighted_option + 1}/{view_options_cnt}"

		self.state_string = tui.center(self.state_string, columns)

		self.state_string += "\n"

		self.state_string += tui.center(f"{selected_mess}{selected_string}", columns)

		if self.find.is_set():
			mess = "Type: "

			mess_len = len(mess)

			inputed = tui.ljust(tui.text_scroll(self.find_buf, columns - mess_len, dur), columns - mess_len)

			self.state_string += "\n"

			self.state_string += tui.ljust(f"{mess}{inputed}", columns)
		
		info_msg = tui.center(tui.clamp_text(self.__translated("Type \":h\" and press enter to see more information (double esc to exit)")), columns)

		head = 2 + len(self.title.splitlines())

		tail = 1 + len(info_msg.splitlines()) + len(self.state_string.splitlines())

		if self.commands:
			tail += 1

		options_display_cnt = min(view_options_cnt, rows - head - tail)

		options_display_end = self.options_display_start + options_display_cnt

		if self.highlighted_option >= options_display_end:
			self.options_display_start = self.highlighted_option - options_display_cnt + 1

		elif self.highlighted_option < self.options_display_start:
			self.options_display_start = self.highlighted_option

		self.__output(tui.center(tui.text_scroll(self.title, columns, time=dur), columns))
				
		screen_width = columns - 2

		options_display_end = self.options_display_start + options_display_cnt

		self.__output(f"┌{'─' * screen_width}┐")

		for i in range(options_display_cnt):
			i += self.options_display_start

			if i >= view_options_cnt:
				break

			option_index = view_options[i]

			option = self.options[option_index]

			is_selected = self.highlighted_option == i

			if self.shift_select:
				if i >= self.shift_option_start and i < shift_option_end:
					is_selected = True
				elif shift_option_end < i and i <= self.shift_option_start:
					is_selected = True

			self.display_option(option, columns, is_selected, full_option=self.full_options[option_index])
		
		if not view_options:
			self.display_option(self.__translated("(NO OPTIONS)"), columns, True)

		self.__output(f"└{'─' * screen_width}┘")

		self.__output(self.state_string)

		self.__output(info_msg)

		#self.__output(tui.center(tui.text_scroller(self.info, columns, dur), columns))

		if self.commands:
			self.__output(tui.ljust(f":{tui.text_scroll(self.command_buf, columns - 1, dur)}", columns))

		self.__output_update()
	
	async def timer(self) -> None:
		while not self.finished.is_set():
			await asyncio.sleep(0.1)

			await self.update()
	
	async def menu_gui(self) -> list[str | None]:
		raise NotImplementedError()
		
		return self.selected_options

	async def loop(self, filters: list[str] | None=None) -> list[str]:
		self.filters = filters

		await self.update()

		await asyncio.gather(self.timer(), self.input.loop())

		return self.selected_options

	def set_find(self, find: str="") -> None:
		self.find_buf = find

		self.find.set()

	def stop_find(self) -> None:
		self.find.clear()

	async def reset(self) -> None:
		self.finished.clear()
		self.input.reset()
		self.highlighted_option = 0
		self.options.clear()
		self.option_cnt = 0

	def on_update_subcribe(self, update_handler: FunctionType) -> None:
		self.__menu_update.subscribe(update_handler)

	def on_update_unsubcribe(self, update_handler: FunctionType) -> None:
		self.__menu_update.unsubscribe(update_handler)

	def on_input_subcribe(self, update_handler: FunctionType) -> None:
		self.input_event.subscribe(update_handler)

	def on_input_unsubcribe(self, update_handler: FunctionType) -> None:
		self.input_event.unsubscribe(update_handler)

	async def update(self) -> None:
		await self.__menu_update.invoke(self.filters)

	def close(self) -> None:
		self.finished.set()

		self.input.close()
