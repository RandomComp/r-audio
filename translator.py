#!/usr/bin/env python

import tui

from listgenerator import ListGenerator

from pathlib import Path

from json import JSONDecoder, JSONDecodeError

from re import split, Pattern, sub

class Translator:
	def __init__(self, file: str | Path=None, translator_dict: dict=None, verbose: bool=False) -> None:
		if not translator_dict and not file:
			raise TypeError("Translator dict or file not provided")
		
		invalid_json_format = False
		
		invalid_json_format_msg = ""
		
		if file:
			if isinstance(file, str):
				try:
					translator_dict = JSONDecoder().decode(Path(file).read_text(encoding="utf-8"))
				except JSONDecodeError as e:
					invalid_json_format = True

					invalid_json_format_msg = f"{e.msg} at {e.colno}:{e.lineno} (column:line)"
			else:
				raise TypeError(f"Expected str or Path, got {file.__class__}")

		self.verbose = verbose

		if invalid_json_format:
			raise TypeError(f"Invalid JSON format: {invalid_json_format_msg}")

		if "languages" not in translator_dict or "from" not in translator_dict:
			raise TypeError(f"Invalid JSON translator format")

		languages = translator_dict["languages"]

		if not languages:
			raise TypeError(f"Field \"languages\" have invalid format: {languages}")
		
		src_lang = translator_dict["from"]

		if not src_lang:
			raise TypeError(f"Field \"from\" should have a source language name (string), not {src_lang}")
		
		self.translator_dict = dict()

		self.translator_dict["from"] = src_lang

		self.translator_dict["languages"] = languages
		
		for lang in languages:
			if lang not in translator_dict:
				raise TypeError(f"Translator JSON have no translation table for language \"{lang}\", but specified in \"languages\" field")

			lang = lang.lower()

			self.translator_dict[lang] = dict()

			for word in translator_dict[lang]:
				self.translator_dict[lang][word.lower()] = translator_dict[lang][word].lower()
		
		self.cache = {}

		self.default_lang = self.source_language()
	
	def __output(self, *values: object, sep: str=" ", end: str="\n") -> None:
		tui.print(*values, sep=sep, end=end)
	
	def translate_by_occurences(self, text: str, language: str) -> str:
		words_dict = self.translator_dict[language]

		occurences = ListGenerator(word.lower() for word in words_dict if word.lower() in text.lower())

		result = text

		occurences = sorted(occurences, key=len, reverse=True)

		result_index = -1

		try:
			result_index = occurences.index(text.lower())
		except ValueError:
			result_index = -1

		if result_index != -1:
			occurence = occurences[result_index]

			result = words_dict[occurence]

		else:
			if self.verbose:
				self.__output(f"Closest occurences:", occurences)

			for occurence in occurences:
				if occurence not in result: continue

				if self.verbose:
					self.__output(f"\"{occurence}\" --> \"{words_dict[occurence]}\"")
				
				result = result.replace(occurence, words_dict[occurence])
		
		result = ' '.join(match for match in result.split(" ") if match)
		
		return result

	def translate_by_match(self, text: str, language: str) -> str | None:
		words_dict = self.translator_dict[language]

		for word in words_dict:
			if text == word:
				return words_dict[word]
		
		return None

	def translate(self, _text: str, language: str | None=None) -> str:
		if self.verbose:
			self.__output(f"Input text: \"{_text}\"")

		lang = self.default_lang

		if not language and not self.default_lang:
			self.__output("Default language is not provided, setting native language as default...")
			
			source_lang = self.source_language()
				
			self.default_lang = source_lang
				
			lang = source_lang

		elif language in self.available_languages():
			lang = language
		elif language and language != lang:
			self.__output(f"Unknown language \"{language}\", native language fallback...")
		
		if lang == self.source_language():
			return _text

		is_capitalized = _text[0].isupper()

		is_caps = _text.isupper()

		text = _text.lower()
		
		is_cached = lang in self.cache and text in self.cache[lang]
		
		if is_cached:
			result = self.cache[lang][text]

			if self.verbose:
				self.__output(f"Using cached \"{result}\" for \"{text}\"")

		else:
			result = self.translate_by_match(text, lang)
			
			if not result:
				result = self.translate_by_occurences(text, lang)
		
		#punc_re = r" |\.|,|!|\?|:|-|\"|\(|\)"
		
		if lang not in self.cache:
			self.cache[lang] = dict()
		
		self.cache[lang][text] = result

		result = result.capitalize() if is_capitalized else result

		result = result.upper() if is_caps else result

		return result

	def see_available_languages(self) -> None:
		available = self.available_languages()

		languages_str = "\", \"".join(available)
				
		for lang in available:
			self.print(f"Available languages: \"{languages_str}\"", language=lang)
	
	def print(self, *_values: object, sep: str=" ", end: str="\n", language: str | None=None) -> None:
		values = ((self.translate(value, language=language) if isinstance(value, str) else str(value)) for value in _values)

		string = f"{sep.join(values)}{end}"

		self.__output(string, end='')
	
	def source_language(self) -> str:
		return self.translator_dict["from"]
	
	def list_languages(self) -> list[str]:
		return self.translator_dict["languages"]
	
	def available_languages(self) -> list[str]:
		return [self.translator_dict["from"], *self.translator_dict["languages"]]
	
	def __repr__(self):
		return f"Translator(from=\'{self.source_language()}\', to={self.list_languages()})"
