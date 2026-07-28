#!/usr/bin/env python

from menu import Menu

from filedialog import FileDialog

import asyncio

import tui

import ansi

async def main():
	chooser = FileDialog(gui=False)

	files = await chooser.choice_file()

	tui.print(files)

	#console = utils.VirtualConsole()

	#console.set_cursor_pos(0, 0)

	#console.print("Choice a file".center(console.columns))

	#console.print("World, world!", end='')

	#console.update()

if __name__ == "__main__":
	default_settings = tui.switch_to_raw()

	print(ansi.invisible_cursor, end='')

	try:
		asyncio.run(main())
	finally:
		tui.print()

		print(ansi.visible_cursor, end='')

		tui.switch_to_default(default_settings)
