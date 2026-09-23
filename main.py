#!/usr/bin/env python

from asyncio.exceptions import CancelledError

from filedialog import FileDialog
from audioplayer import AudioPlayer
from translator import Translator

import ansi

import utils

import tui

from input import Input

import asyncio

from sys import argv, platform

from pathlib import Path

from random import shuffle

import tomllib

from playlist import Playlist

class AudioPlayerApp:
	def __init__(self, gui: bool=True) -> None:
		self.gui = gui

		self.translator = None

		self.need_quit = False

		self.script_name = ""

		self.input_queue = None
		self.input = None

	def __translated_output(self, *values: object, sep: str=" ", end: str="\n", language: str | None=None) -> None:
		tui.print(self.__translated(*values, sep=sep, language=language), end=end)

	def __output(self, *values: object, sep: str=" ", end: str="\n") -> None:
		tui.print(*values, sep=sep, end=end)

	def __translated(self, *values: object, sep: str=" ", language: str | None=None) -> str:
		values_str: list[str] = []

		for value in values:
			value_str: str = str(value)

			if isinstance(value, str) and self.translator:
				value_str = self.translator.translate(value_str, language)

			values_str.append(value_str)

		return sep.join(values_str)

	def see_on_all_langs(self, msg_def, *args) -> None:
		if self.translator:
			for lang in self.translator.available_languages():
				msg_def(*args, language=lang)
		else:
			msg_def(*args)

	def set_lang_as_default(self, language: str) -> None:
		if not self.translator:
			return

		if language in self.translator.available_languages():
			self.translator.default_lang = language

	def default_language(self) -> str:
		return self.translator.default_lang if self.translator else "en"

	def source_language(self) -> str:
		return self.source_language() if self.translator else "en"

	def available_languages(self) -> list[str]:
		return self.translator.available_languages() if self.translator else ["en"]

	def see_help(self, language: str | None=None) -> None:
		self.__translated_output("Usage:", language=language)

		options_str = self.__translated("options", language=language)

		attributes_str = self.__translated("attributes", language=language)

		changes_app_lang_str = self.__translated("changes the app language (now defaults to", language=language)

		see_help_str = self.__translated("to see help (this output) and exit", language=language)

		self.__output(f"\tpython {self.script_name} [{options_str}] [{attributes_str}]")

		self.__translated_output("Available options: ", language=language)

		self.__output(f"\t-h -help -- {see_help_str}")

		default_lang = self.default_language()

		self.__output(f"\t-lang -- {changes_app_lang_str} \"{default_lang}\")")

	def see_warning_about_platform(self, platform: str) -> None:
		self.__translated_output(f"Platform {platform} is not fully supported")

	def see_unrecognized_lang_msg(self, requested_lang: str, language: str | None=None) -> None:
		unrecognized_lang_str = self.__translated("Unrecognized language", language=language)

		use_str = self.__translated("Use", language=language)

		available_languages_str = self.__translated("to see available languages", language=language)

		self.__output(f"{unrecognized_lang_str} \"{requested_lang}\"")

		self.__output(f"{use_str} \"-lang list\" {available_languages_str}")

	def see_unrecognized_option_msg(self, language: str | None=None) -> None:
		options_str = "\", \"".join([*args, *kwargs.keys()])

		use_str = self.__translated("Use", language=language)

		or_str = self.__translated("or", language=language)

		or_str = self.__translated("or", language=language)

		see_available = self.__translated("to see available options and attributes", language=language)

		unrecognized_option_msg = self.__translated("Unrecognized option", language=language)

		self.__output(f"{unrecognized_option_msg} \"{options_str}\"")

		self.__output(f"{use_str} \"-help\" {or_str} \"-h\" {see_available}")

	def parse_arg(self, arg_name, arg) -> tuple[str, bool]:
		self.need_quit = False

		if arg_name == "lang":
			if arg == "off":
				self.translator = None
			else:
				self.translator = Translator("localization.json", verbose=False)

			if arg in self.available_languages():
				self.set_lang_as_default(arg)
			elif arg == "list":
				self.translator.see_available_languages()

				self.need_quit = True
			elif self.translator and arg:
				self.see_on_all_langs(self.see_unrecognized_lang_msg, arg)

				self.need_quit = True

		elif arg_name == "h" or arg_name == "help":
			self.see_on_all_langs(self.see_help)

			self.need_quit = True

		else:
			self.see_on_all_langs(self.see_unrecognized_option_msg)

			self.need_quit = True

	async def main(self, script_name: str, platform: str, *args, **kwargs):
		self.script_name = script_name

		if platform == "win32":
			self.see_warning_about_platform(platform)

		for arg in args:
			self.parse_arg(arg, "")

		for kwarg, value in kwargs.items():
			self.parse_arg(kwarg, value)

		if self.need_quit: return

		config = tomllib.loads(Path("r-audio-server.toml").read_text())

		# files = ["https://music.youtube.com/watch?v=8etHSLhHT4o&si=rLT7aeo6Am9Nwtiz"]

		player = None

		work_dir = Path().home() / "Music"

		try:
			playlist = Playlist(work_dir)

			player = AudioPlayer(config=config, translator=self.translator)

			await player.open()

			player.load(playlist)

			player.play()

			await player.loop()

		except KeyboardInterrupt, CancelledError:
			pass

		finally:
			if player:
				await player.close()
				await player.clean()

	def run(self, script_name: str, platform: str, *args, **kwargs) -> None:
		asyncio.run(self.main(script_name, platform, *args, **kwargs))

if __name__ == "__main__":
	app = AudioPlayerApp(gui=False)

	args, kwargs = utils.parse_args(argv[1:])

	app.run(argv[0], platform, *args, **kwargs)
