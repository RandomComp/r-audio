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

		self.db = {}

		if self.db_dir.is_file():
			db_text = self.db_dir.read_text(encoding="UTF-8")

			self.db = json.loads(db_text)

		self.update_db(dir)

		self.db_files = list(self.db["files"].keys())
		self.recommended = []

		self._recommended_index = 0

		self.leads_rate = {}

		for file in self.db_files:
			file_db = self.get_file(file)

			print(f"{file_db=}")

			leads = tuple(file_db["lead"])

			self.leads_rate[leads] = 0

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
		"""Returns dict of Genre Name, Title, Lead, Album, Record time"""

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

	def file_in_db(self, file: str) -> bool:
		return file in self.db["files"] if "files" in self.db else False

	def get_file(self, file: str) -> dict:
		if not self.file_in_db(file):
			self.add_file_to_db(file)

		return self.db["files"][file]

	def load_cover(self, file: str) -> bytes:
		return Path(self.get_file(file)["cover"]).read_bytes()

	def add_file_to_db(self, file: str) -> None:
		if self.file_in_db(file):
			return

		if "files" not in self.db:
			self.db["files"] = {}

		self.db["files"][file] = {
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

		self.db["files"][file]["lead"] = []

		if "lead" in id3 and id3["lead"] is not None:
			leads = id3["lead"]
			leads = [lead.strip() for lead in leads.split(",")]

			self.db["files"][file]["lead"] = leads

		keys = ["genre", "title", "album", "cover", "year", "text"]

		for key in keys:
			if key not in id3:
				continue

			self.db["files"][file][key] = id3[key]

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
		file_db = self.get_file(file)

		leads = tuple(file_db["lead"])

		recommended = self.recommended[self._recommended_index:]

		if self.leads_rate[leads] > 0.0:
			self.leads_rate[leads] = (self.leads_rate[leads] * 0.7) + (time * 0.3)
		else:
			self.leads_rate[leads] = time

		recommended = self.sort(recommended)
		recommended = sorted(recommended, key=lambda x: self.leads_rate[tuple(self.get_file(x)["lead"])], reverse=True)
		self.recommended[self._recommended_index:] = recommended

		cur_time_of_day = self.get_cur_time_of_day()

		rate = file_db[cur_time_of_day]["rate"]
		listen_times = file_db[cur_time_of_day]["listen_times"]

		if listen_times == 0:
			file_db[cur_time_of_day]["rate"] = time
		else:
			file_db[cur_time_of_day]["rate"] = (rate + time) * 0.5

		file_db[cur_time_of_day]["listen_times"] += 1

	def add_pure_listen_time(self, file: str, time: float) -> None:
		if file not in self.db:
			self.add_file_to_db(file)

		cur_time_of_day = self.get_cur_time_of_day()

		rate = self.db["files"][file][cur_time_of_day]["rate"]

		self.db["files"][file][cur_time_of_day]["rate"] = rate + time

	def appendleft(self, playlist: list[str]) -> None:
		self.recommended[0:0] = playlist

	def sort(self, files: list[str]) -> list[str]:
		cur_time_of_day = self.get_cur_time_of_day()

		leads = []
		genres = []
		albums = []
		years = []

		for file in files:
			file_db = self.get_file(file)

			lead = file_db["lead"]
			if lead not in leads:
				leads.append(lead)

			genre = file_db["genre"]
			if genre not in genres:
				genres.append(genre)

			album = file_db["album"]
			if album not in albums:
				albums.append(album)

			year = file_db["year"]
			if year not in years:
				years.append(year)

		result = sorted(files, key=lambda x: albums.index(self.get_file(x)["album"]))
		result = sorted(result, key=lambda x: leads.index(self.get_file(x)["lead"]))
		result = sorted(result, key=lambda x: genres.index(self.get_file(x)["genre"]))
		result = sorted(result, key=lambda x: years.index(self.get_file(x)["year"]))

		result = sorted(result, key=lambda x: self.get_file(x)[cur_time_of_day]["rate"], reverse=True)

		result = sorted(result, key=lambda x: self.get_file(x)[cur_time_of_day]["listen_times"])

		return result

	def gen(self):
		self.recommended = (self.db_files[:200]).copy()

		shuffle(self.recommended)

		self.recommended = self.sort(self.recommended)

		self._recommended_index = 0

		while True:
			print(f"{self._recommended_index=}")

			yield self.recommended[self._recommended_index]

			self._recommended_index += 1

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
