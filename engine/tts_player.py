import logging
import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtTextToSpeech import QTextToSpeech, QVoice

logger = logging.getLogger(__name__)


class TTSPlayer(QObject):
    state_changed = Signal(str)
    position_changed = Signal(int, int)

    STATE_IDLE = 'idle'
    STATE_PLAYING = 'playing'
    STATE_PAUSED = 'paused'
    STATE_STOPPED = 'stopped'

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tts: Optional[QTextToSpeech] = None
        self._state = self.STATE_IDLE
        self._text_chunks: list[str] = []
        self._current_chunk = 0
        self._total_chunks = 0
        self._rate = 0.0
        self._pitch = 0.0
        self._volume = 1.0
        self._selected_voice: Optional[QVoice] = None
        self._init_tts()

    def _init_tts(self):
        try:
            self._tts = QTextToSpeech(self)
            if self._tts.state() == QTextToSpeech.State.Error:
                logger.error("TTS engine failed to initialize")
                return
            self._tts.stateChanged.connect(self._on_state_changed)
            self._tts.setRate(self._rate)
            self._tts.setPitch(self._pitch)
            self._tts.setVolume(self._volume)

            voices = self._tts.availableVoices()
            if voices:
                self._selected_voice = voices[0]
                self._tts.setVoice(self._selected_voice)
                for v in voices:
                    if 'Chinese' in v.name() or 'zh' in v.name().lower() or '中文' in v.name():
                        self._selected_voice = v
                        self._tts.setVoice(v)
                        break
        except Exception as e:
            logger.error(f"TTS init failed: {e}")

    def available_voices(self) -> list[QVoice]:
        if self._tts:
            return self._tts.availableVoices()
        return []

    def set_voice(self, voice: QVoice):
        self._selected_voice = voice
        if self._tts:
            self._tts.setVoice(voice)

    def set_rate(self, rate: float):
        self._rate = max(-1.0, min(1.0, rate))
        if self._tts:
            self._tts.setRate(self._rate)

    def set_pitch(self, pitch: float):
        self._pitch = max(-1.0, min(1.0, pitch))
        if self._tts:
            self._tts.setPitch(self._pitch)

    def set_volume(self, volume: float):
        self._volume = max(0.0, min(1.0, volume))
        if self._tts:
            self._tts.setVolume(self._volume)

    def rate(self) -> float:
        return self._rate

    def pitch(self) -> float:
        return self._pitch

    def volume(self) -> float:
        return self._volume

    @property
    def state(self) -> str:
        return self._state

    def _split_text(self, text: str, chunk_size: int = 800) -> list[str]:
        chunks = []
        current = ''
        for para in text.split('\n'):
            para = para.strip()
            if not para:
                continue
            if len(current) + len(para) > chunk_size and current:
                chunks.append(current.strip())
                current = para
            else:
                current += ('\n' if current else '') + para
        if current.strip():
            chunks.append(current.strip())
        return chunks

    def speak(self, text: str):
        if not self._tts or self._tts.state() == QTextToSpeech.State.Error:
            return
        self._tts.stop()
        self._text_chunks = self._split_text(text)
        if not self._text_chunks:
            return
        self._current_chunk = 0
        self._total_chunks = len(self._text_chunks)
        self._state = self.STATE_PLAYING
        self.state_changed.emit(self._state)
        self._speak_current()

    def _speak_current(self):
        if self._current_chunk < self._total_chunks:
            text = self._text_chunks[self._current_chunk]
            self._tts.say(text)
        else:
            self._state = self.STATE_STOPPED
            self.state_changed.emit(self._state)

    def _on_state_changed(self, state):
        if state == QTextToSpeech.State.Ready:
            self._current_chunk += 1
            self.position_changed.emit(self._current_chunk, self._total_chunks)
            self._speak_current()

    def pause(self):
        if self._tts:
            self._tts.pause()
            self._state = self.STATE_PAUSED
            self.state_changed.emit(self._state)

    def resume(self):
        if self._tts:
            self._tts.resume()
            self._state = self.STATE_PLAYING
            self.state_changed.emit(self._state)

    def stop(self):
        if self._tts:
            self._tts.stop()
        self._state = self.STATE_STOPPED
        self._current_chunk = 0
        self.state_changed.emit(self._state)

    def toggle_pause(self):
        if self._state == self.STATE_PLAYING:
            self.pause()
        elif self._state == self.STATE_PAUSED:
            self.resume()