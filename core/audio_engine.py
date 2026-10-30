# core/audio_engine.py
import sounddevice as sd
import soundfile as sf
import numpy as np
import threading

class MultiTrackMixer:
    def __init__(self, sample_rate=44100, channels=2):
        self.sample_rate = sample_rate
        self.channels = channels
        self.stream = None
        self.tracks = {}
        self.lock = threading.Lock()
        self._playing = False
        self._position_frames = 0
        self._total_frames = 0
        self._peak_levels = [0.0, 0.0]
        
        self._play_start_frame = 0
        self._play_end_frame = 0 

    def load_stem(self, name: str, file_path: str):
        try:
            data, sr = sf.read(file_path, dtype='float32')
            if sr != self.sample_rate:
                import librosa
                data = librosa.resample(data.T, orig_sr=sr, target_sr=self.sample_rate).T
        except Exception as e:
            print(f"Не удалось загрузить {file_path}: {e}")
            return

        if data.ndim == 1:
            data = np.column_stack([data] * self.channels)
        elif data.shape[1] != self.channels:
            if data.shape[1] == 1:
                data = np.column_stack([data[:, 0]] * self.channels)
            else:
                data = data[:, :self.channels]

        with self.lock:
            self.tracks[name] = {
                'data': data, 
                'original_data': data.copy(),
                'volume': 1.0, 
                'mute': False, 
                'solo': False
            }
            self._total_frames = max(self._total_frames, len(data))
            if self._play_end_frame == 0:
                self._play_end_frame = self._total_frames

    def append_stem(self, name: str, file_path: str, start_sec: float, total_duration: float = 0.0):
        try:
            data, sr = sf.read(file_path, dtype='float32')
            if sr != self.sample_rate:
                import librosa
                data = librosa.resample(data.T, orig_sr=sr, target_sr=self.sample_rate).T
        except Exception as e:
            print(f"Не удалось загрузить {file_path}: {e}")
            return

        if data.ndim == 1:
            data = np.column_stack([data] * self.channels)
        elif data.shape[1] != self.channels:
            if data.shape[1] == 1:
                data = np.column_stack([data[:, 0]] * self.channels)
            else:
                data = data[:, :self.channels]

        with self.lock:
            if name not in self.tracks:
                self.tracks[name] = {
                    'data': np.zeros((0, self.channels), dtype=np.float32),
                    'original_data': np.zeros((0, self.channels), dtype=np.float32),
                    'volume': 1.0, 'mute': False, 'solo': False
                }
            
            track = self.tracks[name]
            start_idx = int(start_sec * self.sample_rate)
            end_idx = start_idx + len(data)
            
            # ВАЖНО: Всегда расширяем массив до полной длины трека
            required_len = end_idx
            if total_duration > 0:
                required_len = max(required_len, int(total_duration * self.sample_rate))
            
            if len(track['data']) < required_len:
                pad_len = required_len - len(track['data'])
                track['data'] = np.vstack([track['data'], np.zeros((pad_len, self.channels), dtype=np.float32)])
                track['original_data'] = np.vstack([track['original_data'], np.zeros((pad_len, self.channels), dtype=np.float32)])
            
            track['data'][start_idx:end_idx] += data
            track['original_data'][start_idx:end_idx] += data
            
            self._total_frames = max(self._total_frames, len(track['data']))
            if self._play_end_frame == 0 or self._play_end_frame < self._total_frames:
                self._play_end_frame = self._total_frames

    def set_play_range(self, start_sec: float, end_sec: float):
        with self.lock:
            self._play_start_frame = int(start_sec * self.sample_rate)
            if end_sec > start_sec:
                self._play_end_frame = int(end_sec * self.sample_rate)
            else:
                self._play_end_frame = self._total_frames
                
            if not (self._play_start_frame <= self._position_frames < self._play_end_frame):
                self._position_frames = self._play_start_frame

    def play(self):
        with self.lock:
            if self._position_frames >= self._play_end_frame or self._position_frames < self._play_start_frame:
                self._position_frames = self._play_start_frame
        self.start()

    def start(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception: pass
            self.stream = None

        self.stream = sd.OutputStream(
            samplerate=self.sample_rate, channels=self.channels,
            dtype='float32', callback=self._audio_callback, blocksize=0,
        )
        self.stream.start()
        self._playing = True

    def pause(self):
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception: pass
            self.stream = None
        self._playing = False
        self._peak_levels = [0.0, 0.0]

    def stop(self):
        self.pause()
        with self.lock:
            self._position_frames = self._play_start_frame

    def seek(self, position_sec: float):
        with self.lock:
            self._position_frames = int(position_sec * self.sample_rate)
            self._position_frames = max(self._play_start_frame, min(self._position_frames, self._play_end_frame))

    def get_position(self) -> float:
        with self.lock:
            return self._position_frames / self.sample_rate

    def get_duration(self) -> float:
        with self.lock:
            return (self._play_end_frame - self._play_start_frame) / self.sample_rate

    def get_levels(self) -> list:
        return self._peak_levels

    def set_volume(self, track_name: str, volume: float):
        with self.lock:
            if track_name in self.tracks:
                self.tracks[track_name]['volume'] = max(0.0, min(1.0, volume))

    def set_mute(self, track_name: str, mute: bool):
        with self.lock:
            if track_name in self.tracks:
                self.tracks[track_name]['mute'] = mute

    def set_solo(self, track_name: str, solo: bool):
        with self.lock:
            if track_name in self.tracks:
                self.tracks[track_name]['solo'] = solo

    def _audio_callback(self, outdata, frames, time_info, status):
        if status: print(f"Статус: {status}")
        with self.lock:
            pos = self._position_frames
            end_pos = pos + frames

            if pos >= self._play_end_frame:
                outdata.fill(0)
                self._playing = False
                raise sd.CallbackStop

            any_solo = any(t['solo'] for t in self.tracks.values())
            mixed = np.zeros((frames, self.channels), dtype=np.float32)
            
            for name, track in self.tracks.items():
                if any_solo and (not track['solo'] or track['mute']): continue
                if not any_solo and track['mute']: continue

                vol = track['volume']
                if vol == 0.0: continue

                chunk = track['data'][pos:end_pos]
                if len(chunk) < frames:
                    chunk = np.vstack([chunk, np.zeros((frames - len(chunk), self.channels), dtype=np.float32)])
                mixed += chunk * vol

            outdata[:] = mixed
            self._position_frames += frames
            
            peak = np.max(np.abs(mixed), axis=0)
            self._peak_levels[0] = max(self._peak_levels[0], float(peak[0]))
            self._peak_levels[1] = max(self._peak_levels[1], float(peak[-1]))