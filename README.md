# R-Audio
This is my audio player written from scratch in Python using PyAudio and audioread libraries, using TUI without curses-like libraries

# How to use

## Install the requirements
**Install the system requirements:**
**For Debian-based OS:**
><br/><code>sudo apt update</code>

><code>sudo apt intall python3-dev portaudio19-dev</code>
**For Arch-based OS:**
><br/><code>sudo pacman -Sy portaudio</code>

**Install the pip requirements (may broke your system, it is better to use a virtual environment (see below)):**

><br/><code>python -m pip install -r requirements.txt</code>

**or follow steps to create virtual environment:**

## Create your virtual environment
><br/><code>python -m venv venv</code>

## Activate your virtual environment
**For Windows:**

><br/><code>venv\bin\activate</code>

**For Unix-like OS (MacOS, Linux):**

><br/><code>source venv/bin/activate</code>

## Then install the pip requirements

><code>python -m pip install -r requirements.txt</code>

# Using:

## Run main file using this command in your shell (zsh/bash/cmd/powershell):

<code>python main.py</code>

## Use your arrows on keyboard to control your audio player:
**Use "←" and "→" to seek the audio**

**Use "↑" and "↓" to control the audio volume**

**Press space to play/stop playback**

**Press 's' to input time and seek**

**Press 'q' to quit the program**

## Screenshots

# IMPORTANT:
## This is a work-in-progress. If you encounter any bugs, visual glitches, or unexpected behavior, please report them in the Issues section. Your feedback helps make r-audio better.
