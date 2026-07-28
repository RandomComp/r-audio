# R-Audio
This is my audio player written from scratch in Python using PyAudio and audioread libraries, using TUI without curses-like libraries

# How to use

## Install the requirements
**Install the system requirements:**
**For Debian-based OS:**
```bash
sudo apt update && sudo apt intall python3-dev portaudio19-dev
```

**For Arch-based OS:**
pyaudio in pip will install portaudio automatically

**Install the pip requirements (may broke your system (PEP 668), it is better to use a virtual environment (see below)):**

```bash
python -m pip install -r requirements.txt
```

**or follow steps to create virtual environment:**

## Create your virtual environment

```bash
python -m venv venv
```

## Activate your virtual environment
**For Windows:**

```cmd
venv\bin\activate
```

**For Unix-like OS (MacOS, Linux):**

```bash
source venv/bin/activate
```

## Then install the pip requirements

```bash
python -m pip install -r requirements.txt
```

# Using:

## Run main file using this command in your shell (zsh/bash/cmd/powershell):

```bash
python main.py
```

## Use your arrows on keyboard to control your audio player:
**Use "←" and "→" to seek the audio**

**Use "↑" and "↓" to control the audio volume**

**Press space to play/stop playback**

**Press 's' to input time and seek**

**Press 'q' to quit the program**

## Screenshots

# IMPORTANT:
## This is a work-in-progress. If you encounter any bugs, visual glitches, or unexpected behavior, please report them in the Issues section. Your feedback helps make r-audio better.
