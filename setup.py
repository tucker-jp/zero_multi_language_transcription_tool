"""py2app configuration for building macOS .app bundle."""

from setuptools import setup

setup(
    name="French Transcription Helper",
    app=["main.py"],
    options={"py2app": {
        "argv_emulation": False,
        "packages": [
            "config", "audio", "transcription", "translation",
            "workers", "ui", "storage",
            "PyQt6", "numpy", "torch", "mlx_whisper", "mlx",
            "transformers", "sentencepiece", "sounddevice", "silero_vad",
            "websocket", "requests", "urllib3",
        ],
        "includes": ["PyQt6.QtWidgets", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.sip"],
        "plist": {
            "CFBundleName": "French Transcription Helper",
            "CFBundleIdentifier": "com.transcriptionhelper.french",
            "CFBundleVersion": "1.0.0",
            "NSMicrophoneUsageDescription":
                "Captures system audio via BlackHole to transcribe French speech.",
            "NSHighResolutionCapable": True,
        },
    }},
    setup_requires=["py2app"],
)
