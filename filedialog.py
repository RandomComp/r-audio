import asyncio

from pathlib import Path

from plyer import filechooser

import ansi

from menu import Menu

from translator import Translator

import tui

from random import shuffle

class FileDialog:
	def __init__(self, title: str="Choice a file", dir: Path=Path().home(), multiple: bool=False, gui: bool=True, translator: Translator=None):
		self.title = title

		if translator:
			self.title = translator.translate(self.title)

		self.gui = gui

		self.multiple = multiple

		self.translator = translator

		if isinstance(dir, str):
			dir = Path(dir)

		self.dir = dir.resolve()

		self.finished = asyncio.Event()

		self.selected_files = []

		self.find_buf = ""

		self.find = asyncio.Event()

		if not gui:
			self.objs = []

			self.info = self.__translated("""↑↓ -- navigate
f -- find objects by name (double esc to exit)
backspace -- go previous location
enter -- select
a -- multiple selection mode
q -- quit menu""")

			self.__supported_extension_str = self.__translated("Supported extensions")

			self.menu = Menu(title=self.title, info=self.info, multiple=self.multiple, translator=translator)

			self.menu.on_update_subcribe(self.menu.menu_cli_frame)

			self.menu.on_input_subcribe(self.input_handler)

	def __output(self, *values: object, sep: str=" ", end: str="\n") -> None:
		tui.print(*values, sep=sep, end=end)
	
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
	
	def select(self, option: int, allow_paths: bool=True) -> None:
		view_options = self.menu.get_view_full_options()
			
		obj: Path = view_options[option]

		if obj.is_file():
			if obj not in self.selected_files:
				self.selected_files.append(obj)
			else:
				self.selected_files.remove(obj)
				
			self.menu.select(option)

			if not self.multiple:
				self.menu.close()

				self.finished.set()

		elif (obj.is_dir() or obj.is_symlink()) and allow_paths:
			self.dir = obj.resolve()
			
			self.menu.close()
		
	async def input_handler(self, event_name: str, option: int | tuple[int, int], input_key: str) -> None:
		if input_key in "\r\n":
			if isinstance(option, int):
				self.select(option)
			elif isinstance(option, tuple):
				for i in range(option[0], option[1] + 1):
					self.select(i, allow_paths=False)

		elif input_key in "\x08\x7F":
			if not self.find.is_set():
				old_dir = self.dir

				self.dir = self.dir.parent

				if old_dir != self.dir:
					self.menu.close()
			else:
				self.find_buf = self.find_buf[:-1]

				self.menu.set_find(self.find_buf)
		
		elif self.find.is_set() and input_key == "\x1B":
			self.menu.stop_find()

			self.find.clear()

		elif self.find.is_set() and input_key.isalnum():
			self.find_buf += input_key

			self.menu.set_find(self.find_buf)

		elif input_key == "q":
			self.finished.set()

		elif input_key == "f":
			self.menu.set_find()

			self.find.set()
	
	async def choice_file_gui(self, filters: list[str] | None=None) -> list[Path | None] | None:
		try:
			return map(Path, filechooser.open_file(filers=filters, multiple=self.multiple, title=self.title))
		except TypeError:
			return None
		
		# TODO: Написать свою альтернативу plyer.filechooser используя zenity и GetOpenFileName
	
	async def choice_file_cli(self, filters: list[str] | None=None) -> list[Path | None] | None:
		while not self.finished.is_set():
			objs = []
			
			retry = True

			while retry:
				try:
					objs = list(self.dir.iterdir())
				except FileNotFoundError:
					self.dir = self.dir.parent

					continue

				retry = False

			self.menu.title = f"{self.title}: {self.dir}"

			folders = []

			files = []

			for obj in objs:
				if obj.name.startswith("."):
					continue

				if obj.is_dir() or obj.is_symlink():
					folders.append(obj)
				elif obj.is_file() and (not filters or obj.suffix.lower() in filters):
					files.append(obj)
				
			folders = sorted(folders, key=lambda x: Path.stat(x).st_mtime, reverse=True)
				
			files = sorted(files, key=lambda x: Path.stat(x).st_mtime, reverse=True)

			shuffle(folders)

			shuffle(files)

			menu_list = []

			self.objs.clear()

			for folder in folders:
				folder = Path(folder)

				self.objs.append(folder)

				menu_list.append(f"{ansi.bold}{ansi.green_fg}{folder.name}/")
				
			for file in files:
				file = Path(file)

				self.objs.append(file)

				menu_list.append(file.name)

			await self.menu.reset()

			self.menu.set_options(self.objs, menu_list)

			extension_string = "\", \"".join(filters) if filters else "All"

			self.menu.info = f"{self.info}\n{self.__supported_extension_str}: \"{extension_string}\""

			await self.menu.loop(filters=filters)

		return self.selected_files

	async def choice_file(self, filters: list[str] | None=None) -> list[Path | None] | None:
		result = []

		if self.gui:
			result = await self.choice_file_gui(filters=filters)
		else:
			result = await self.choice_file_cli(filters=filters)
		
			tui.clear_screen()
		
		return result if self.multiple else result[0] if result else None
