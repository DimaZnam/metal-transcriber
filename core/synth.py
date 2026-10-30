# core/synth.py
import numpy as np
import sounddevice as sd
import threading
import time

# Глобальные настройки
SR = 44100
_synth_cache = {}
_active_voices = []  # Список играющих нот [data, current_position]
_lock = threading.Lock()

# Кэшируем звук при первом обращении
def _get_wave(midi_note: int, duration: float = 1.5):
    if midi_note in _synth_cache:
        return _synth_cache[midi_note]
    
    freq = 440.0 * (2.0 ** ((midi_note - 69) / 12.0))
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)
    wave = np.sin(2 * np.pi * freq * t)
    wave += 0.4 * np.sin(4 * np.pi * freq * t)
    wave += 0.2 * np.sin(6 * np.pi * freq * t)
    envelope = np.exp(-3 * t)
    audio = (wave * envelope * 0.2).astype(np.float32) # 0.2 чтобы не клипповало при аккордах
    
    _synth_cache[midi_note] = audio
    return audio

# Непрерывный аудио-коллбэк (работает постоянно)
def _audio_callback(outdata, frames, time_info, status):
    if status:
        print(f"Аудио статус: {status}")
    
    outdata.fill(0) # Очищаем буфер
    
    with _lock:
        for voice in _active_voices[:]:
            data, pos = voice
            chunk = data[pos:pos+frames]
            
            if len(chunk) > 0:
                # Микшируем в оба канала (стерео)
                if outdata.ndim > 1:
                    outdata[:len(chunk), 0] += chunk
                    outdata[:len(chunk), 1] += chunk
                else:
                    outdata[:len(chunk)] += chunk
                
            voice[1] += frames
            
            # Если нота закончилась, удаляем её из списка
            if voice[1] >= len(data):
                _active_voices.remove(voice)
    
    # Мягкое ограничение (Soft clip), чтобы не было хрипа при многих нотах
    np.clip(outdata, -1.0, 1.0, out=outdata)

# Запускаем поток один раз при импорте модуля
_stream = None
def _start_stream():
    global _stream
    if _stream is not None:
        return
    try:
        _stream = sd.OutputStream(
            samplerate=SR,
            channels=2, # Принудительно стерео
            dtype='float32',
            callback=_audio_callback,
            blocksize=512, # Небольшой буфер для низкой задержки
        )
        _stream.start()
    except Exception as e:
        print(f"[Synth] Ошибка запуска аудио-потока: {e}")

# Вызываем при импорте
_start_stream()

def play_midi_note(midi_note: int, duration: float = 1.5):
    t_start = time.perf_counter()
    
    audio = _get_wave(midi_note, duration)
    
    with _lock:
        _active_voices.append([audio, 0])
    
    t_end = time.perf_counter()
    # Этот лог теперь будет показывать микросекунды
    print(f"[SYNTH] Нота {midi_note} | Добавлена в очередь: {(t_end-t_start)*1000:.2f} мс")

# Функция для корректного закрытия при выходе из приложения
def cleanup():
    global _stream
    if _stream is not None:
        _stream.stop()
        _stream.close()
        _stream = None