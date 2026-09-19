import sys

from collections import deque
from typing import Any

import PySide6.QtWidgets as qtw
import PySide6.QtGui as qtgui
import PySide6.QtCore as qtcore

import asyncio
from audioplayer_client import AudioPlayerClient
import utils

import tui

from translator import Translator

import os

from pathlib import Path

import numpy as np

from qasync import QEventLoop

def bytes_to_icon(image: bytes) -> qtgui.QIcon:
	return qtgui.QIcon(qtgui.QPixmap(image))

def crop_to_square(pixmap: qtgui.QPixmap) -> qtgui.QPixmap:
	"""Обрезает картинку по центру до идеального квадрата"""
	width = pixmap.width()
	height = pixmap.height()

	square_size = min(width, height)

	x = (width - square_size) // 2
	y = (height - square_size) // 2

	return pixmap.copy(x, y, square_size, square_size)

def round_square(pixmap: qtgui.QPixmap) -> qtgui.QPixmap:
	"""Обрезает картинку для скругления"""
	width = pixmap.width()
	height = pixmap.height()

	rounded_pixmap = qtgui.QPixmap(qtcore.QSize(width, height))
	rounded_pixmap.fill(qtgui.QColor.fromRgba(0))

	painter = qtgui.QPainter(rounded_pixmap)
	painter.setRenderHint(qtgui.QPainter.RenderHint.Antialiasing, True)

	path = qtgui.QPainterPath()
	path.addRoundedRect(0, 0, width, height, 50, 50)

	painter.setClipPath(path)
	painter.drawPixmap(0, 0, pixmap)
	painter.end()

	return rounded_pixmap

class MarqueeLabel(qtw.QLabel):
	def __init__(self, text="", parent=None):
		super().__init__(parent)
		self.setText(text)

		# Настройки анимации
		self.offset = 0  # Текущее смещение текста в пикселях
		self.speed = 1  # Количество пикселей за один шаг (скорость)

		# Таймер для обновления анимации (60 FPS ~ 16 мс)
		self.timer = qtcore.QTimer(self)
		self.timer.timeout.connect(self.update_marquee)
		self.timer.start(16)

	def update_marquee(self):
		# Рассчитываем ширину текста в пикселях
		font_metrics = self.fontMetrics()
		text_width = font_metrics.horizontalAdvance(self.text())

		if self.width() >= text_width:
			self.offset = 0

			return

		# Сдвигаем текст влево
		self.offset -= self.speed

		# Если текст полностью ушел за левую границу, возвращаем его справа
		if self.offset < -text_width:
			self.offset = self.width()

		# Вызываем перерисовку виджета
		self.update()

	def paintEvent(self, event):
		font_metrics = self.fontMetrics()
		text_width = font_metrics.horizontalAdvance(self.text())

		if self.width() >= text_width:
			return super().paintEvent(event)

		# Вместо стандартной отрисовки QLabel рисуем текст вручную
		painter = qtgui.QPainter(self)

		# Настройка шрифта и цвета (берем из стилей виджета)
		painter.setFont(self.font())
		painter.setPen(self.palette().text().color())

		# Вычисляем Y-координату для центрирования текста по вертикали
		font_metrics = self.fontMetrics()
		y_pos = (self.height() + font_metrics.ascent() - font_metrics.descent()) // 2

		# Рисуем текст со смещением по оси X
		painter.drawText(self.offset, y_pos, self.text())

class ClickableProgressBar(qtw.QProgressBar):
	clicked_position = qtcore.Signal(float)

	def __init__(self, parent=None):
		super().__init__(parent)

		self.setAcceptDrops(True)

		self.normal_geometry = None

	def _process_mouse_logic(self, event):
		click_x = event.position().x()
		total_width = self.width()

		if total_width == 0:
			return

		fraction = click_x / total_width
		fraction = max(0.0, min(1.0, fraction))

		total_range = self.maximum() - self.minimum()
		new_value = int(self.minimum() + (fraction * total_range))
		self.setValue(new_value)

		self.clicked_position.emit(fraction)

	def mousePressEvent(self, a0):
		if a0.button() == qtcore.Qt.MouseButton.LeftButton:
			self._process_mouse_logic(a0)

		super().mousePressEvent(a0)

	def mouseMoveEvent(self, a0):
		if a0.buttons() & qtcore.Qt.MouseButton.LeftButton:
			self._process_mouse_logic(a0)

		super().mouseMoveEvent(a0)

	def enterEvent(self, event):
		"""Срабатывает при наведении мыши"""
		if not self.normal_geometry:
			self.normal_geometry = self.geometry()

		g = self.normal_geometry
		hover_geometry = qtcore.QRect(g.x() - 5, g.y(), g.width() + 10, g.height() + 10)

		self.anim = qtcore.QPropertyAnimation(self, b"geometry")
		self.anim.setDuration(150) # 150 миллисекунд
		self.anim.setEndValue(hover_geometry)
		self.anim.setEasingCurve(qtcore.QEasingCurve.Type.OutCubic)
		self.anim.start()

		super().enterEvent(event)

	def leaveEvent(self, a0):
		"""Срабатывает, когда мышь уходит с кнопки"""
		if self.normal_geometry:
			self.anim = qtcore.QPropertyAnimation(self, b"geometry")
			self.anim.setDuration(150)
			self.anim.setEndValue(self.normal_geometry)
			self.anim.setEasingCurve(qtcore.QEasingCurve.Type.OutCubic)
			self.anim.start()

			self.normal_geometry = None

		super().leaveEvent(a0)

class AnimatedLabel(qtw.QLabel):
	clicked=qtcore.Signal()

	def __init__(self, parent=None):
		super().__init__(parent)

		self.normal_geometry = None
		self.after_mouse_press_geometry = None

	def enterEvent(self, event):
		"""Срабатывает при наведении мыши"""

		if not self.normal_geometry:
			self.normal_geometry = self.geometry()

		g = self.normal_geometry
		hover_geometry = qtcore.QRect(g.x() - 5, g.y() - 5, g.width() + 10, g.height() + 10)

		self.anim = qtcore.QPropertyAnimation(self, b"geometry")
		self.anim.setDuration(150) # 150 миллисекунд
		self.anim.setEndValue(hover_geometry)
		self.anim.setEasingCurve(qtcore.QEasingCurve.Type.OutCubic)
		self.anim.start()

		super().enterEvent(event)

	def mousePressEvent(self, ev: qtgui.QMouseEvent) -> None:
		"""Срабатывает при нажатии мыши"""

		self.after_mouse_press_geometry = self.geometry()

		g = self.after_mouse_press_geometry
		click_geometry = qtcore.QRect(g.x() + 5, g.y() + 5, g.width() - 10, g.height() - 10)

		self.anim = qtcore.QPropertyAnimation(self, b"geometry")
		self.anim.setDuration(200)
		self.anim.setEndValue(click_geometry)
		self.anim.setEasingCurve(qtcore.QEasingCurve.Type.OutCubic)
		self.anim.start()

		self.clicked.emit()

	def mouseReleaseEvent(self, ev: qtgui.QMouseEvent) -> None:
		"""Срабатывает при отпускании мыши"""

		if not self.after_mouse_press_geometry:
			return

		g = self.after_mouse_press_geometry

		self.anim = qtcore.QPropertyAnimation(self, b"geometry")
		self.anim.setDuration(200)
		self.anim.setEndValue(g)
		self.anim.setEasingCurve(qtcore.QEasingCurve.Type.OutCubic)
		self.anim.start()

	def leaveEvent(self, a0):
		"""Срабатывает, когда мышь уходит с кнопки"""

		if self.normal_geometry:
			self.anim = qtcore.QPropertyAnimation(self, b"geometry")
			self.anim.setDuration(150)
			self.anim.setEndValue(self.normal_geometry)
			self.anim.setEasingCurve(qtcore.QEasingCurve.Type.OutCubic)
			self.anim.start()

			self.normal_geometry = None

		super().leaveEvent(a0)

class PlayerProgressBar(qtw.QWidget):
	def __init__(self) -> None:
		super().__init__()

		self.progress = ClickableProgressBar()
		self.progress.setObjectName("progress")
		self.progress.setFormat("")
		self.progress.setMinimum(0)
		self.progress.setMaximum(0)
		self.progress.setMinimumHeight(15)
		self.progress.setMaximumHeight(25)

		self.cur_time_label = qtw.QLabel()
		self.cur_time_label.setProperty("class", "time")
		self.cur_time_label.setText(utils.format_time(0, wordly=False))

		self.duration_label = qtw.QLabel()
		self.duration_label.setProperty("class", "time")
		self.duration_label.setText(utils.format_time(0, wordly=False))

		layout = qtw.QHBoxLayout()
		layout.setSpacing(15)
		layout.addWidget(self.cur_time_label)
		layout.addWidget(self.progress)
		layout.addWidget(self.duration_label)

		self.second = 0

		self.setLayout(layout)

	def set_second(self, second: int) -> None:
		self.cur_time_label.setText(utils.format_time(second, wordly=False))

		self.second = second

		self.progress.setValue(second)

	def set_duration(self, duration: int) -> None:
		self.duration_label.setText(utils.format_time(duration, wordly=False))

		self.progress.setMaximum(duration)

class PlayerID3Widget(qtw.QWidget):
	clicked_on_cover = qtcore.Signal()

	def __init__(self, title: str, lead: str) -> None:
		super().__init__()

		self.title = MarqueeLabel(title)
		self.title.setMaximumWidth(500)
		self.title.setToolTip("Test")
		self.title.setWordWrap(False)
		self.title.setObjectName("title")

		self.lead = MarqueeLabel(lead)
		self.lead.setMaximumWidth(500)
		self.lead.setWordWrap(False)
		self.lead.setToolTip("Test")
		self.lead.setObjectName("lead")

		self.cover = AnimatedLabel()
		self.cover.setObjectName("cover")
		self.cover.setScaledContents(True)

		self.cover.clicked.connect(self.clicked_on_cover.emit)

		title_and_lead = qtw.QVBoxLayout()
		title_and_lead.setSpacing(10)
		title_and_lead.addWidget(self.cover, alignment=qtcore.Qt.AlignmentFlag.AlignHCenter)
		title_and_lead.addWidget(self.title, alignment=qtcore.Qt.AlignmentFlag.AlignHCenter)
		title_and_lead.addWidget(self.lead, alignment=qtcore.Qt.AlignmentFlag.AlignHCenter)

		self.setLayout(title_and_lead)

	def update_id3(self, id3: dict) -> None:
		self.title.setText(id3["title"])
		self.lead.setText(' и '.join(id3["lead"]))

		if "cover" in id3:
			pixmap = qtgui.QPixmap()

			success = pixmap.loadFromData(id3["cover"])

			if success:
				pixmap = crop_to_square(pixmap)
				pixmap = round_square(pixmap)

				pixmap = pixmap.scaled(
					190, 190,
					qtcore.Qt.AspectRatioMode.KeepAspectRatio,
					qtcore.Qt.TransformationMode.SmoothTransformation,
				)

				self.cover.setPixmap(pixmap)

class TableEntryWidget(qtw.QWidget):
	def __init__(self, key: str, value: str, is_up: bool=False, is_down: bool=False, parent=None) -> None:
		super().__init__()

		key_widget = qtw.QLabel()
		key_widget.setProperty("class", "table_value")
		key_widget.setText(f"{key}: ")

		self.value_widget = MarqueeLabel()
		self.value_widget.setProperty("class", "table_value")
		self.value_widget.setText(value)

		layout = qtw.QHBoxLayout()
		# layout.setSpacing(20)
		layout.addWidget(key_widget)
		layout.addWidget(self.value_widget)
		layout.addStretch()

		self.setLayout(layout)

	def set_value(self, value: str) -> None:
		self.value_widget.setText(value)

class TableWidget(qtw.QWidget):
	def __init__(self, keys: list[str], parent=None) -> None:
		super().__init__()

		self.keys = keys

		self.entries = {}

		layout = qtw.QVBoxLayout()
		layout.setSpacing(0)

		max_key_len = len(max(keys, key=len))

		for i, key in enumerate(keys):
			is_up = i == 0
			is_down = i == (len(keys) - 1)

			entry = TableEntryWidget(key.rjust(max_key_len), "", is_up, is_down)

			self.entries[key] = entry

			layout.addWidget(entry)

		self.setLayout(layout)

	def set_value(self, _key: str, value: str) -> None:
		for key in self.keys:
			if key != _key:
				continue

			self.entries[key].set_value(value)

			break

class HPlayerID3Widget(qtw.QWidget):
	def __init__(self, id3: dict) -> None:
		super().__init__()

		self.title = MarqueeLabel()
		self.title.setToolTip("Test")
		self.title.setWordWrap(False)
		self.title.setObjectName("h_title")

		self.lead = MarqueeLabel()
		self.lead.setWordWrap(False)
		self.lead.setToolTip("Test")
		self.lead.setObjectName("h_lead")

		self.cover = qtw.QLabel()
		self.cover.setObjectName("h_cover")
		self.cover.setScaledContents(False)

		title_and_lead_layout = qtw.QVBoxLayout()
		title_and_lead_layout.setSpacing(10)
		title_and_lead_layout.addWidget(self.title)
		title_and_lead_layout.addWidget(self.lead)

		title_and_lead = qtw.QWidget()
		title_and_lead.setLayout(title_and_lead_layout)

		self.keys = ["title", "lead", "genre", "album", "year"]

		song_visual_info = qtw.QHBoxLayout()
		song_visual_info.addWidget(self.cover)
		song_visual_info.addWidget(title_and_lead)

		self.table = TableWidget([key.capitalize() for key in self.keys])

		for key in self.keys:
			if key not in id3:
				continue

			self.table.set_value(key.capitalize(), id3[key])

		layout = qtw.QVBoxLayout()
		layout.addLayout(song_visual_info)
		layout.addWidget(self.table)

		self.update_id3(id3)

		self.setLayout(layout)

	def update_id3(self, id3: dict) -> None:
		if "title" in id3:
			self.title.setText(id3["title"])

		if "lead" in id3:
			id3["lead"] = ' и '.join(id3["lead"])

			self.lead.setText(id3["lead"])

		if "cover" in id3 and id3["cover"] is not None:
			pixmap = qtgui.QPixmap()

			success = pixmap.loadFromData(id3["cover"])

			if success:
				pixmap = crop_to_square(pixmap)
				pixmap = round_square(pixmap)

				pixmap = pixmap.scaled(
					100, 100,
					qtcore.Qt.AspectRatioMode.KeepAspectRatio,
					qtcore.Qt.TransformationMode.SmoothTransformation,
				)

				self.cover.setPixmap(pixmap)

		for key in self.keys:
			if key not in id3:
				continue

			self.table.set_value(key.capitalize(), id3[key])

class AnimatedButton(qtw.QPushButton):
	def __init__(self, parent=None):
		super().__init__(parent)

		self.normal_geometry = None

		self._start_max_size: qtcore.QSize | None = None
		self.end_max_size: qtcore.QSize | None = None

	def setMaximumSize(self, nw: int, nh: int) -> None:
		self._start_max_size = qtcore.QSize(nw, nh)

		super().setMaximumSize(nw, nh)

	def mousePressEvent(self, event) -> None:
		"""Срабатывает при наведении мыши"""

		if self._start_max_size is None or self.end_max_size is None:
			super().mousePressEvent(event)

			return

		if not self.normal_geometry:
			self.normal_geometry = self.geometry()

		self.anim = qtcore.QPropertyAnimation(self, b"maximumSize")
		self.anim.setDuration(400) # 150 миллисекунд
		self.anim.setStartValue(self._start_max_size)
		self.anim.setEndValue(self.end_max_size)
		self.anim.setEasingCurve(qtcore.QEasingCurve.Type.InCubic)
		self.anim.start()

		super().mousePressEvent(event)

	def mouseReleaseEvent(self, event) -> None:
		"""Срабатывает, когда мышь уходит с кнопки"""

		if self.normal_geometry and self._start_max_size is not None and self.end_max_size is not None:
			self.anim = qtcore.QPropertyAnimation(self, b"maximumSize")
			self.anim.setDuration(400)
			self.anim.setStartValue(self.end_max_size)
			self.anim.setEndValue(self._start_max_size)
			self.anim.setEasingCurve(qtcore.QEasingCurve.Type.InOutCubic)
			self.anim.start()

			self.normal_geometry = None

		super().mouseReleaseEvent(event)

class PlayerControl(qtw.QWidget):
	on_prev = qtcore.Signal()
	on_play_pause = qtcore.Signal()
	on_next = qtcore.Signal()

	def __init__(self, work_dir: Path, parent=None) -> None:
		super().__init__(parent)

		self.icons = {
			"prev": qtgui.QIcon(str(work_dir / "prev.svg")),
			"play-to-pause": [],
			"next": qtgui.QIcon(str(work_dir / "next.svg")),
		}

		for i in range(8):
			icon = qtgui.QIcon(str(work_dir / "play-to-pause-anim" / f"play-to-pause-{i:02}.svg"))

			self.icons["play-to-pause"].append(icon)

		self.prev = AnimatedButton()
		self.prev.end_max_size = qtcore.QSize(60, 60)
		self.prev.setObjectName("prev")
		self.prev.setIcon(self.icons["prev"])
		self.prev.setMinimumSize(50, 50)
		self.prev.setMaximumSize(50, 50)
		self.prev.setIconSize(qtcore.QSize(16, 16))
		self.prev.clicked.connect(self.on_prev.emit)

		self.play_pause = AnimatedButton()
		self.play_pause.end_max_size = qtcore.QSize(80, 80)
		self.play_pause.setObjectName("play_pause")
		self.play_pause.setIcon(self.icons["play-to-pause"][0])
		self.play_pause.setMinimumSize(70, 70)
		self.play_pause.setMaximumSize(70, 70)
		self.play_pause.setIconSize(qtcore.QSize(24, 24))
		self.play_pause.clicked.connect(self.on_play_pause.emit)

		self.next = AnimatedButton()
		self.next.end_max_size = qtcore.QSize(60, 60)
		self.next.setObjectName("next")
		self.next.setIcon(self.icons["next"])
		self.next.setMinimumSize(50, 50)
		self.next.setMaximumSize(50, 50)
		self.next.setIconSize(qtcore.QSize(16, 16))
		self.next.clicked.connect(self.on_next.emit)

		layout = qtw.QHBoxLayout()
		layout.setObjectName("control")
		layout.addWidget(self.prev)
		layout.addWidget(self.play_pause)
		layout.addWidget(self.next)

		self.setLayout(layout)

		self.state = "Paused"
		self.cur_icon_index = 0

	def set_state(self, state: str) -> None:
		if self.state == state:
			return

		self.timer = qtcore.QTimer()

		if state == "Playing":
			self.cur_icon_index = 0

			self.timer.timeout.connect(self.anim_pause)
		else:
			self.cur_icon_index = 7

			self.timer.timeout.connect(self.anim_play)

		self.timer.start(16)

		self.state = state

	def anim_play(self) -> None:
		self.play_pause.setIcon(self.icons["play-to-pause"][self.cur_icon_index])

		if self.cur_icon_index == 0:
			self.timer.stop()

			return

		self.cur_icon_index -= 1

	def anim_pause(self) -> None:
		self.play_pause.setIcon(self.icons["play-to-pause"][self.cur_icon_index])

		if self.cur_icon_index == 7:
			self.timer.stop()

			return

		self.cur_icon_index += 1

class PlayerWidget(qtw.QWidget):
	on_prev = qtcore.Signal()
	on_play_pause = qtcore.Signal()
	on_next = qtcore.Signal()
	clicked_on_cover = qtcore.Signal()

	def __init__(self, work_dir: Path, id3: dict, parent=None) -> None:
		super().__init__(parent)

		self.control = PlayerControl(work_dir)
		self.control.on_prev.connect(self.on_prev)
		self.control.on_play_pause.connect(self.on_play_pause)
		self.control.on_next.connect(self.on_next)
		self.control.setFixedWidth(250)

		self.id3_widget = PlayerID3Widget(id3["title"], id3["lead"])
		self.id3_widget.clicked_on_cover.connect(self.clicked_on_cover.emit)

		self.progress = PlayerProgressBar()
		self.progress.setFixedWidth(300)

		vert_center = qtw.QVBoxLayout()
		vert_center.setSpacing(25)
		vert_center.addStretch()
		vert_center.addWidget(self.id3_widget, alignment=qtcore.Qt.AlignmentFlag.AlignHCenter)
		vert_center.addWidget(self.progress, alignment=qtcore.Qt.AlignmentFlag.AlignHCenter)
		vert_center.addWidget(self.control, alignment=qtcore.Qt.AlignmentFlag.AlignHCenter)
		vert_center.addStretch()

		# qtw.Q

		self.setLayout(vert_center)

	def set_second(self, second: int) -> None:
		self.progress.set_second(second)

	def set_duration(self, duration: int) -> None:
		self.progress.set_duration(duration)

	def set_state(self, state: str) -> None:
		self.control.set_state(state)

	def update_id3(self, id3: dict) -> None:
		self.id3_widget.update_id3(id3)

	def update_interface(self, second: int, duration: int, id3: dict) -> None:
		self.set_second(second)
		self.set_duration(duration)

		self.update_id3(id3)

class ClickableLabel(qtw.QLabel):
	clicked = qtcore.Signal()

	def __init__(self, text: str="") -> None:
		super().__init__(text=text)

	def mousePressEvent(self, ev: qtgui.QMouseEvent) -> None:
		self.clicked.emit()

class MenuWidget(qtw.QWidget):
	def __init__(self, content: qtw.QWidget, parent=None):
		super().__init__(parent)

		content.setParent(self)

		self.content = content
		self.menu = None

		self.anim = None

	def show_or_hide_menu(self) -> None:
		if not self.menu or not self.anim:
			return

		if self.menu.isHidden():
			self.show_menu()
		else:
			self.hide_menu()

	def show_menu(self) -> None:
		if not self.menu or not self.anim:
			return

		self.menu.show()

		self.anim.setDirection(qtcore.QAbstractAnimation.Direction.Forward)

		self.anim.start()

		self.anim.finished.connect(self.on_show_anim_end)

	def hide_menu(self) -> None:
		if not self.menu or not self.anim:
			return

		self.anim.setDirection(qtcore.QAbstractAnimation.Direction.Backward)

		self.menu.show()

		self.anim.start()

		self.anim.finished.connect(self.on_hide_anim_end)

	def on_show_anim_end(self) -> None:
		if not self.menu or not self.anim:
			return

		self.anim.finished.disconnect(self.on_show_anim_end)

	def on_hide_anim_end(self) -> None:
		if not self.menu or not self.anim:
			return

		self.anim.finished.disconnect(self.on_hide_anim_end)

		self.menu.hide()

	def setWidgetAsMenu(self, widget: qtw.QWidget) -> None:
		self.menu = widget
		self.menu.hide()

		self.anim = qtcore.QPropertyAnimation(self.menu, b"pos")
		self.anim.setEasingCurve(qtcore.QEasingCurve.Type.InOutCubic)
		self.anim.setDuration(300)

		widget.setParent(self)

		self.resizeMenu(self.size())

	def resizeMenu(self, new_size: qtcore.QSize) -> None:
		if not self.menu:
			return

		size = self.menu.sizeHint()

		max_width = int(new_size.width() * 0.4)

		hint_width = min(max_width, size.width())

		print(f"{hint_width=}")

		x, y = new_size.width() - hint_width, 0
		width, height = hint_width, new_size.height()

		self.menu.setProperty("pos", qtcore.QPoint(x, y))
		self.menu.setProperty("size", qtcore.QSize(width, height))

		if self.anim:
			self.anim.setStartValue(qtcore.QPoint(self.width(), y))
			self.anim.setEndValue(qtcore.QPoint(self.width() - width, y))

	def resizeEvent(self, event: qtgui.QResizeEvent) -> None:
		new_size = event.size()

		if self.menu:
			self.resizeMenu(new_size)

		self.content.setProperty("size", new_size)

		super().resizeEvent(event)

	def minimumSizeHint(self) -> qtcore.QSize:
		result = self.content.sizeHint()

		if self.menu:
			result += self.menu.sizeHint()

		return result

class ID3WidgetMenu(qtw.QWidget):
	def __init__(self, parent=None) -> None:
		super().__init__(parent=parent)

		self.id3_widget = HPlayerID3Widget({
			"title": "Loading..."
		})

		id3_widget_layout = qtw.QVBoxLayout()
		id3_widget_layout.addWidget(self.id3_widget)
		id3_widget_layout.addStretch()

		self.id3_widget_bg = qtw.QWidget()
		self.id3_widget_bg.setObjectName("second_half")
		self.id3_widget_bg.setLayout(id3_widget_layout)

		id3_widget_bg_layout = qtw.QVBoxLayout()
		id3_widget_bg_layout.addWidget(self.id3_widget_bg)

		self.setLayout(id3_widget_bg_layout)

	def update_id3(self, id3: dict) -> None:
		self.id3_widget.update_id3(id3)

class AudioPlayerClientGUI(qtw.QMainWindow):
	supported_extensions = (".mp4", ".mp3", ".wav", ".ogg", ".aac", ".flac")

	def __init__(self, app: qtw.QApplication, work_dir: Path, config: dict | None=None, translator: Translator | None=None):
		super().__init__()
		self.setWindowTitle("R-Audio")

		self.work_dir = work_dir

		# system members:

		self.update_processing = asyncio.Event()

		self.id3_info = None
		self.cur_time = 0
		self.duration = 0
		self.volume = 0
		self.state = "Paused"
		self.track_id = 0

		self.addr = ("127.0.0.1", 6700)
		self.reader, self.writer = None, None
		self.command_queue = deque()

		self.cover_name = "r_audio_track_cover" # temporary path for track cover

		self.cover_drawed = False

		self.config = config

		self.translator = translator

		self.protocol = AudioPlayerClient(config)

		self.setStyleSheet(Path(work_dir / "style.css").read_text(encoding="UTF-8"))

		self.player_widget = PlayerWidget(work_dir, {
			"title": "Connecting...",
			"lead": None,
			"cover": None
		})

		self.player_widget.setObjectName("player_widget")

		# self.player_widget.setFixedWidth(300)

		self.player_widget.on_prev.connect(self.protocol.prev)
		self.player_widget.on_play_pause.connect(self.protocol.play_pause)
		self.player_widget.on_next.connect(self.protocol.next)

		self.id3_widget = ID3WidgetMenu()

		central_widget = MenuWidget(self.player_widget)
		central_widget.setWidgetAsMenu(self.id3_widget)

		self.player_widget.clicked_on_cover.connect(central_widget.show_or_hide_menu)

		self.background_label = qtw.QLabel()
		self.background_label.setMinimumSize(0, 0)
		self.background_label.setScaledContents(True)

		# qtw.

		self.blur_effect = qtw.QGraphicsBlurEffect(blurRadius=70.0)
		self.background_label.setGraphicsEffect(self.blur_effect)

		stacked = qtw.QStackedLayout()
		stacked.setStackingMode(qtw.QStackedLayout.StackingMode.StackAll)
		stacked.addWidget(self.background_label)
		stacked.addWidget(central_widget)

		stacked_widget = qtw.QWidget()
		stacked_widget.setLayout(stacked)

		self.setCentralWidget(stacked_widget)

		self.setObjectName("window")

		qtcore.QTimer.singleShot(0, lambda: asyncio.create_task(self.loop()))

		self.copy_title_shortcut = qtgui.QShortcut(qtgui.QKeySequence("Ctrl+C"), self)
		self.copy_title_shortcut.setContext(qtcore.Qt.ShortcutContext.WindowShortcut)
		self.copy_title_shortcut.activated.connect(self.format_song_id3)

		self.clipboard = app.clipboard()

		self.protocol.on_id3_info_changed.subscribe(self.id3_info_changed)
		self.protocol.on_time_changed.subscribe(self.time_changed)
		self.protocol.on_duration_changed.subscribe(self.duration_changed)
		self.protocol.on_volume_changed.subscribe(self.volume_changed)
		self.protocol.on_state_changed.subscribe(self.state_changed)
		self.protocol.on_track_id_changed.subscribe(self.track_id_changed)

	def id3_info_changed(self, _: str, value: dict[str, Any]) -> None:
		if self.cover_name:
			cover_dir = self.get_cover_name()

			if os.path.isfile(cover_dir):
				os.remove(cover_dir)

		self.id3_info = value

		if self.id3_info is None:
			self.id3_info: dict[str, Any] = {
				"title": "Nothing is playing",
			}

		self.player_widget.update_id3(self.id3_info)
		self.id3_widget.update_id3(self.id3_info)

		if "cover" in self.id3_info and self.id3_info["cover"] is not None:
			pixmap = qtgui.QPixmap()

			success = pixmap.loadFromData(self.id3_info["cover"])

			painter = qtgui.QPainter(pixmap)

			painter.setCompositionMode(qtgui.QPainter.CompositionMode.CompositionMode_SourceAtop)
			painter.fillRect(pixmap.rect(), qtgui.QColor(0, 0, 0, 100))

			painter.end()

			if success:
				pixmap = crop_to_square(pixmap)

				self.background_label.setPixmap(pixmap)

	def time_changed(self, _: str, value: float) -> None:
		self.cur_time = value

		self.player_widget.set_second(int(self.cur_time))
	def duration_changed(self, _: str, value: float) -> None:
		self.duration = value

		self.player_widget.set_duration(int(self.duration))
	def volume_changed(self, _: str, value: float) -> None:
		self.volume = value
	def state_changed(self, _: str, value: str) -> None:
		self.state = value

		self.player_widget.set_state(self.state)
	def track_id_changed(self, _: str, value: int) -> None:
		self.track_id = value

	def format_song_id3(self) -> None:
		if not self.id3_info or not self.clipboard:
			return

		result = f"{self.id3_info["lead"]} -- {self.id3_info["title"]}"

		self.clipboard.setText(result)

	async def loop(self) -> None:
		await self.protocol.loop()

	def get_cover_name(self) -> str:
		return f"/tmp/{self.cover_name}_{self.track_id}"

	async def close_connection(self) -> None:
		self.id3_info = None

		await self.protocol.close_connection()

	def __repr__(self) -> str:
		return f"""{self.update_processing=}
{self.id3_info=}
{self.translator=}
{self.verbose=}
{self.cur_time=}
{self.cover_name=}
self.cover_name={self.get_cover_name()}
{self.cover_drawed=}"""

if __name__ == "__main__":
	app = qtw.QApplication(sys.argv)
	app.setDesktopFileName("com.rdev.r-audio-gui")

	loop = QEventLoop(app)
	asyncio.set_event_loop(loop)

	window = AudioPlayerClientGUI(app, Path(__file__).resolve().parent)
	window.show()

	with loop:
		loop.run_forever()
