import math
from importlib import import_module

import numpy as np


class AudioOutputError(RuntimeError):
    pass


class AudioOutput:
    @staticmethod
    def generate_signal(
        frequency: float = 1000.0,
        amplitude: float = 0.5,
        duration: float = 1.0,
        sample_rate: int = 44100,
    ) -> np.ndarray:
        if not math.isfinite(frequency) or not 0 < frequency < sample_rate / 2:
            raise ValueError("La frecuencia debe estar entre 0 y Nyquist.")
        if not math.isfinite(amplitude) or not 0 <= amplitude <= 1:
            raise ValueError("La amplitud normalizada debe estar entre 0 y 1.")
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("La duración debe ser mayor que cero.")
        samples = int(round(duration * sample_rate))
        time = np.arange(samples, dtype=np.float64) / sample_rate
        signal = amplitude * np.sin(2 * np.pi * frequency * time)
        return np.rint(signal * 32767).astype(np.int16)

    def play(
        self,
        frequency: float = 1000.0,
        amplitude: float = 0.5,
        duration: float = 1.0,
        sample_rate: int = 44100,
    ) -> None:
        signal = self.generate_signal(frequency, amplitude, duration, sample_rate)
        sd = import_module("sounddevice")
        try:
            sd.play(signal, samplerate=sample_rate, blocking=False)
        except sd.PortAudioError as error:
            raise AudioOutputError(str(error)) from error

    def stop(self) -> None:
        sd = import_module("sounddevice")
        try:
            sd.stop()
        except sd.PortAudioError as error:
            raise AudioOutputError(str(error)) from error
