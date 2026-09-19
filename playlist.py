from pathlib import Path

import json
from random import shuffle

from mutagen import id3, MutagenError

from datetime import datetime

import utils

# from audioloader import AudioFileStream

# import numpy as np

# def make_loudness_equalization(filename: str) -> float:
# 	result = 0.0
# 	chunks = 0

# 	file = AudioFileStream(filename, sample_rate=44100, channels=2, chunk_seconds=0.025)

# 	for chunk in file:
# 		result += np.max(np.abs(chunk))

# 		chunks += 1

# 	result = np.sqrt(result / chunks)

# 	file.close()

# 	return result

class Playlist:
	def __init__(self, dir: Path | None=None):
		if not dir:
			dir = Path().home() / "Music"

		self.db_name = "r-audio-db.json"
		self.db_dir = (dir / self.db_name)

		self.files = []

		self.db = {}

		if self.db_dir.is_file():
			db_text = self.db_dir.read_text(encoding="UTF-8")

			self.db = json.loads(db_text)

		self.update_db(dir)

		self.recommended = list(self.db.keys())

	def update_db(self, dir: Path) -> None:
		for file in dir.rglob("*.mp3"):
			file = str(file)

			if file in self.db:
				continue

			self.add_file_to_db(file)

		self.save_db()

	def save_db(self) -> None:
		json_str = json.dumps(self.db, ensure_ascii=False, indent="\t")

		self.db_dir.write_text(json_str, encoding="UTF-8")

	def load_id3(self, file: str) -> dict:
		"""Returns dict of Genre Name, Title, Lead, Album, Album Cover, Record time"""

		result: dict = {}

		try:
			id = id3.Open(file)
		except MutagenError:
			result["lead"], result["title"] = utils.parse_music_file_name(file)

			return result

		keys = ["TCON", "TIT2", "TPE1", "TALB", "TDRC"]

		new_keys = ["genre", "title", "lead", "album", "year"]

		for key, new_key in zip(keys, new_keys):
			value = id.get(key)

			if not value:
				result[new_key] = None
			else:
				result[new_key] = str(value)

		cover = (Path().home() / ".cache" / f"{Path(file).stem}.png").resolve()

		for item in id.items():
			if "APIC" not in item[0]:
				continue

			_bytes = item[1].data

			cover.write_bytes(_bytes)

			break

		result["cover"] = str(cover)
		result["text"] = str((self.db_dir / f"{Path(file).stem}.lrc").resolve())

		return result

	def load_cover(self, file: str) -> bytes:
		if file not in self.db:
			self.add_file_to_db(file)

		return Path(self.db[file]["cover"]).read_bytes()

	def add_file_to_db(self, file: str) -> None:
		if file in self.db:
			return

		self.db[file] = {
			"morning": {
				"rate": 0.0,
				"listen_times": 0,
			},
			"day": {
				"rate": 0.0,
				"listen_times": 0,
			},
			"evening": {
				"rate": 0.0,
				"listen_times": 0,
			},
			"night": {
				"rate": 0.0,
				"listen_times": 0,
			},
		}

		id3 = self.load_id3(file)

		if "lead" in id3 and id3["lead"] is not None:
			self.db[file]["lead"] = [lead.strip() for lead in id3["lead"].split(",")]

		keys = ["genre", "title", "album", "cover", "year", "text"]

		for key in keys:
			if key not in id3:
				continue

			self.db[file][key] = id3[key]

	def get_cur_time_of_day(self) -> str:
		hour = datetime.now().hour

		if hour >= 0 and hour <= 5:
			return "night"

		if hour >= 6 and hour <= 9:
			return "morning"

		if hour >= 17 and hour <= 23:
			return "evening"

		return "day"

	def add_avg_listen_time(self, file: str, time: float) -> None:
		if file not in self.db:
			self.add_file_to_db(file)

		cur_time_of_day = self.get_cur_time_of_day()

		rate = self.db[file][cur_time_of_day]["rate"]
		listen_times = self.db[file][cur_time_of_day]["listen_times"]

		if listen_times == 0:
			self.db[file][cur_time_of_day]["rate"] = time
		else:
			self.db[file][cur_time_of_day]["rate"] = (rate + time) * 0.5

		self.db[file][cur_time_of_day]["listen_times"] += 1

	def add_pure_listen_time(self, file: str, time: float) -> None:
		if file not in self.db:
			self.add_file_to_db(file)

		cur_time_of_day = self.get_cur_time_of_day()

		rate = self.db[file][cur_time_of_day]["rate"]

		self.db[file][cur_time_of_day]["rate"] = rate + time

	def appendleft(self, playlist: list[str]) -> None:
		self.files.extend(playlist)

	def gen(self) -> list[str]:
		shuffle(self.recommended)

		result = self.files

		for file in self.recommended[:200]:
			if file not in result:
				result.append(file)

		cur_time_of_day = self.get_cur_time_of_day()

		leads = [self.db[file]["lead"] for file in result]
		genres = [self.db[file]["genre"] for file in result]
		albums = [self.db[file]["album"] for file in result]
		years = [self.db[file]["year"] for file in result]

		result = sorted(result, key=lambda x: albums.index(self.db[x]["album"]))
		result = sorted(result, key=lambda x: leads.index(self.db[x]["lead"]))
		result = sorted(result, key=lambda x: genres.index(self.db[x]["genre"]))
		result = sorted(result, key=lambda x: years.index(self.db[x]["year"]))

		result = sorted(result, key=lambda x: self.db[x][cur_time_of_day]["listen_times"])

		result = sorted(result, key=lambda x: self.db[x][cur_time_of_day]["rate"], reverse=True)

		return result

	def __del__(self) -> None:
		self.save_db()

# if __name__ == "__main__":
# 	playlist = Playlist()

# 	for file in playlist.gen():
# 		data = playlist.db[file]

# 		song_name = f"{data["lead"]} -- {data["title"]}".ljust(80)

# 		print(f"{song_name} | genre {data["genre"]}")

# import curses
# import curses.textpad
# import time

# def main(stdscr: curses.window) -> None:
# 	stdscr.no

# 	while True:
# 		stdscr.clear()

# 		key = stdscr.getch()

# 		if key == ord("q"):
# 			break

# 		curses.textpad.rectangle(stdscr, 20, 20, 30, 30)

# 		time.sleep(0.01)

# 		stdscr.refresh()

# curses.wrapper(main)
