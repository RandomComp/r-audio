#!/usr/bin/env python

from input import Input

import asyncio

import tui

async def input_handler(_: str, input_key: str) -> bool:
	tui.print(f"inputed key: {input_key}")
	
	if input_key == "q":
		return True
	
	return False

async def main() -> None:
	input_obj = Input()

	input_obj.input.subscribe(input_handler)

	await input_obj.loop()

if __name__ == "__main__":
	default_settings = tui.switch_to_raw()

	try:
		asyncio.run(main())
	finally:
		tui.switch_to_default(default_settings)
