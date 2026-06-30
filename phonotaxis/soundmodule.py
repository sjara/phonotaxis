"""
Create and present sounds.
"""

import sys
import os
import threading
import random
import numpy as np
import scipy.io.wavfile

# Temporary parameters
SOUND_DURATION = 0.5  # seconds
SOUND_FREQUENCY = 440  # Hz (A4 note)
SOUND_AMPLITUDE = 0.5 # Global amplitude for the sound wave

# Default parameters
SAMPLERATE = 44100  # samples per second
RISETIME = 0.002
FALLTIME = 0.002

randomGen = np.random.default_rng()

def list_devices():
    import sounddevice as sd
    return sd.query_devices()

def find_5_1_device():
    pass

def apply_rise_fall(waveform, samplingRate, riseTime, fallTime):
    nSamplesRise = round(samplingRate * riseTime)
    nSamplesFall = round(samplingRate * fallTime)
    riseVec = np.linspace(0, 1, nSamplesRise)
    fallVec = np.linspace(1, 0, nSamplesFall)
    newWaveform = waveform.copy()
    if (len(newWaveform)>nSamplesRise) and (len(waveform)>nSamplesFall):
        newWaveform[:nSamplesRise] *= riseVec
        newWaveform[-nSamplesFall:] *= fallVec
    return newWaveform


class SoundPlayer():
    """
    Sound player for managing and playing multiple sounds.
    
    This class manages a library of Sound objects indexed by integer IDs and
    provides playback control. It can be connected to a state machine's
    integerOutput signal for automated sound playback during behavioral tasks.
    
    Integer ID Convention:
        0: No action (reserved, no sound plays)
        Positive (1, 2, 3, ...): Play sound with this ID
        -1: Stop all currently playing sounds
        Other negative values: Reserved for future use
    
    Example:
        >>> player = SoundPlayer()
        >>> player.set_sound(1, sound1)
        >>> player.set_sound(2, sound2)
        >>> player.play(1)  # Play sound 1
        >>> player.play(-1)  # Stop all sounds
        >>> # Connect to state machine:
        >>> state_machine.integerOutput.connect(player.play)
    """
    def __init__(self):
        try:
            import sounddevice as sd
        except Exception as e:
            raise ImportError(f"sounddevice could not be initialized (is PortAudio available?): {e}")
        self._sd = sd
        self.device = sd.default.device[1]  # Use default device
        self.sounds = {}  # Maps integer IDs to Sound objects
        self.active_streams = {}  # Maps sound_id to active OutputStream objects

    def set_sound(self, sound_id, sound):
        """
        Set a sound with an integer ID.
        
        Args:
            sound_id (int): Integer ID for the sound (use 0 for no sound)
            sound: Sound object to store
        """
        self.sounds[sound_id] = sound

    def play(self, sound_id):
        """
        Play a sound by its integer ID (non-blocking, simple method).
        
        Integer ID values:
            0: No action
            Positive (1, 2, 3, ...): Play sound with this ID
            -1: Stop all sounds
            Other negative values: Reserved for future use
        
        Note: This method doesn't allow stopping individual sounds.
        Use play_stream() if you need that capability.
        
        Args:
            sound_id (int): Integer ID of the sound to play
        """
        if sound_id == 0:
            return  # 0 means no action
        
        if sound_id == -1:
            self.stop()  # Stop all sounds
            return
        
        if sound_id > 0:
            if sound_id in self.sounds:
                sound = self.sounds[sound_id]
                self._sd.play(sound.wave, sound.srate, device=self.device)
            else:
                print(f"Warning: Sound ID {sound_id} not found")
        else:
            # Other negative values are reserved for future use
            print(f"Warning: Unrecognized control signal {sound_id} (reserved for future use)")

    def play_stream(self, sound_id):
        """
        Play a sound by its integer ID using a stream (allows stopping individual sounds).
        
        Integer ID values:
            0: No action
            Positive (1, 2, 3, ...): Play sound with this ID
            -1: Stop all sounds
            Other negative values: Reserved for future use
        
        IMPLELEMENTATION IN PROGRESS

        This method uses a callback-based stream approach that allows for
        individual control of each playing sound via the stop() method.
        
        Args:
            sound_id (int): Integer ID of the sound to play
        """
        if sound_id == 0:
            return  # 0 means no action
        
        if sound_id == -1:
            self.stop_stream()  # Stop all streams
            return
        
        if sound_id > 0:
            if sound_id in self.sounds:
                sound = self.sounds[sound_id]
                
                # Prepare the waveform data
                wave_data = sound.wave.astype(np.float32)
                
                # Create a closure to keep track of playback position
                position = [0]  # Use list to allow modification in nested function
                
                def callback(outdata, frames, time_info, status):
                    """Callback function to feed audio data to the stream."""
                    if status:
                        print(f"Stream status: {status}")
                    
                    chunksize = min(len(wave_data) - position[0], frames)
                    outdata[:chunksize] = wave_data[position[0]:position[0] + chunksize]
                    
                    if chunksize < frames:
                        outdata[chunksize:] = 0  # Fill remaining with silence
                        raise self._sd.CallbackStop()  # Stop the stream when done
                    
                    position[0] += chunksize
                
                # Create an OutputStream with callback for non-blocking playback
                stream = self._sd.OutputStream(
                    samplerate=sound.srate,
                    channels=sound.nchannels,
                    device=self.device,
                    callback=callback,
                    finished_callback=lambda: self._cleanup_stream(sound_id)
                )
                
                # Store the stream for later control (stopping, etc.)
                self.active_streams[sound_id] = stream
                
                # Start the stream (non-blocking)
                stream.start()
            else:
                print(f"Warning: Sound ID {sound_id} not found")
        else:
            # Other negative values are reserved for future use
            print(f"Warning: Unrecognized control signal {sound_id} (reserved for future use)")

    def _cleanup_stream(self, sound_id):
        """Internal method to clean up a stream after it finishes playing."""
        if sound_id in self.active_streams:
            try:
                stream = self.active_streams[sound_id]
                stream.close()
                del self.active_streams[sound_id]
            except:
                pass  # Stream might already be closed

    def stop(self):
        """
        Stop sounds started with play() method.
        
        Note: Since sd.play() doesn't provide individual sound control, this stops ALL
        sounds started with play().
        """
        self._sd.stop()

    def stop_stream(self, sound_id=None):
        """
        Stop stream-based sounds started with play_stream() by their integer ID,
        or stop all streams if no ID is given.
        
        Args:
            sound_id (int, optional): Integer ID of the stream to stop. If None, stops all streams.
        """
        if sound_id is None:
            # Stop all streams
            sound_ids = list(self.active_streams.keys())  # Copy keys to avoid modification during iteration
            for sid in sound_ids:
                stream = self.active_streams[sid]
                stream.stop()
                stream.close()
                del self.active_streams[sid]
        elif sound_id in self.active_streams:
            stream = self.active_streams[sound_id]
            stream.stop()
            stream.close()
            del self.active_streams[sound_id]
        else:
            print(f"Warning: No active stream with ID {sound_id} to stop")

    def wait_until_done(self):
        """Wait until the current sound is done playing."""
        self._sd.wait()

    def connect_state_machine(self, state_machine):
        """
        Connect to a state machine's integerOutput signal.
        
        When the state machine emits an integerOutput signal, the corresponding
        sound will be played automatically.
        
        Args:
            state_machine: StateMachine instance with integerOutput signal
        """
        state_machine.integerOutput.connect(self.play)

    def close(self):
        """
        Close the sound player and clean up all resources.
        
        Stops all currently playing sounds (both play() and play_stream()) and clears the sound library.
        Call this when you're done using the SoundPlayer to ensure proper cleanup.
        """
        # Stop all sounds started with play()
        self.stop()
        
        # Stop all active streams started with play_stream()
        self.stop_stream()
        
        # Clear the sounds dictionary
        self.sounds.clear()

    
def create_player():
    """
    Instantiate and return the appropriate sound player based on config.SOUND_BACKEND.

    Returns an AlsaPlayer if SOUND_BACKEND is 'alsa', otherwise a SoundPlayer.
    Config keys used: SOUND_BACKEND, SOUND_DEVICE, ALSA_DEVICE, ALSA_SAMPLERATE,
    ALSA_PERIOD_SIZE.
    """
    try:
        from phonotaxis import config
    except ImportError:
        config = None

    backend = getattr(config, 'SOUND_BACKEND', 'portaudio')

    if backend == 'alsa':
        device = getattr(config, 'ALSA_DEVICE', 'hw:1,0')
        samplerate = getattr(config, 'ALSA_SAMPLERATE', 384000)
        period_size = getattr(config, 'ALSA_PERIOD_SIZE', 1024)
        return AlsaPlayer(device=device, samplerate=samplerate, period_size=period_size)
    else:
        player = SoundPlayer()
        device = getattr(config, 'SOUND_DEVICE', None)
        if device is not None:
            player.device = device
        return player


class AlsaPlayer():
    """
    Low-latency sound player for Linux using direct ALSA hardware access.

    Bypasses PulseAudio/PipeWire and the PortAudio layer to write directly to
    an ALSA hw device, enabling 192/384 kHz operation and minimal latency.
    Shares the same public interface as SoundPlayer so paradigm scripts can
    swap backends via config.SOUND_BACKEND without any other changes.

    Requires the 'pyalsaaudio' package (Linux only).

    Args:
        device (str): ALSA hw device string, e.g. 'hw:1,0'.
        samplerate (int): Sampling rate in Hz (e.g. 384000).
        period_size (int): Frames per ALSA period; smaller = lower latency.
        nchannels (int): Number of output channels.

    Example:
        >>> player = AlsaPlayer(device='hw:1,0', samplerate=384000)
        >>> player.set_sound(1, sound)
        >>> player.play(1)
        >>> state_machine.integerOutput.connect(player.play)
    """

    FORMAT = None  # set in __init__ after importing alsaaudio

    def __init__(self, device='hw:1,0', samplerate=384000, period_size=1024, nchannels=2):
        try:
            import alsaaudio
        except ImportError:
            raise ImportError("pyalsaaudio is required for AlsaPlayer. "
                              "Install it with: pip install pyalsaaudio")
        self._alsaaudio = alsaaudio
        self.device = device
        self.samplerate = samplerate
        self.period_size = period_size
        self.nchannels = nchannels
        self.sounds = {}
        self._lock = threading.Lock()
        self._playback_thread = None
        self._stop_event = threading.Event()

    def _open_pcm(self):
        """Open and configure the ALSA PCM device for playback."""
        pcm = self._alsaaudio.PCM(
            self._alsaaudio.PCM_PLAYBACK,
            device=self.device,
        )
        pcm.setchannels(self.nchannels)
        actual_rate = pcm.setrate(self.samplerate)
        if actual_rate != self.samplerate:
            print(f"Warning: requested sample rate {self.samplerate} Hz but "
                  f"ALSA is using {actual_rate} Hz. Sound duration will be wrong.")
        pcm.setformat(self._alsaaudio.PCM_FORMAT_S32_LE)
        pcm.setperiodsize(self.period_size)
        return pcm

    def set_sound(self, sound_id, sound):
        """Store a Sound object under an integer ID."""
        self.sounds[sound_id] = sound

    def play(self, sound_id):
        """
        Play a sound by its integer ID (non-blocking).

        Integer ID convention (same as SoundPlayer):
            0:          No action
            Positive:   Play that sound
            -1:         Stop all sounds
        """
        if sound_id == 0:
            return
        if sound_id == -1:
            self.stop()
            return
        if sound_id > 0:
            if sound_id not in self.sounds:
                print(f"Warning: Sound ID {sound_id} not found")
                return
            sound = self.sounds[sound_id]
            # Convert float64 [-1, 1] waveform to signed 32-bit PCM.
            wave_int32 = (sound.wave * 2147483647).astype(np.int32)
            # ALSA expects interleaved bytes.
            raw = wave_int32.tobytes()
            self._stop_event.clear()
            with self._lock:
                self._playback_thread = threading.Thread(
                    target=self._write_pcm,
                    args=(raw,),
                    daemon=True,
                )
                self._playback_thread.start()
        else:
            print(f"Warning: Unrecognized control signal {sound_id} (reserved for future use)")

    def _write_pcm(self, raw):
        """Write raw PCM bytes to the ALSA device in period-sized chunks."""
        bytes_per_period = self.period_size * self.nchannels * 4  # 4 bytes per S32_LE sample
        pcm = self._open_pcm()
        offset = 0
        try:
            while offset < len(raw) and not self._stop_event.is_set():
                chunk = raw[offset:offset + bytes_per_period]
                if len(chunk) < bytes_per_period:
                    chunk = chunk + b'\x00' * (bytes_per_period - len(chunk))
                pcm.write(chunk)
                offset += bytes_per_period
        finally:
            pcm.close()

    def stop(self):
        """Stop any currently playing sound."""
        self._stop_event.set()
        with self._lock:
            if self._playback_thread is not None:
                self._playback_thread.join(timeout=0.5)
                self._playback_thread = None

    def wait_until_done(self):
        """Block until the current sound finishes playing."""
        with self._lock:
            t = self._playback_thread
        if t is not None:
            t.join()

    def connect_state_machine(self, state_machine):
        """Connect to a state machine's integerOutput signal."""
        state_machine.integerOutput.connect(self.play)

    def close(self):
        """Stop playback and release all resources."""
        self.stop()
        self.sounds.clear()


class Sound():
    """
    Sound waveform generator.

    Attributes:
        duration (float): Duration of the sound in seconds.
        srate (int): Sampling rate of the sound.
        tvec (numpy.ndarray): Time vector for the sound.
        wave (numpy.ndarray): The generated sound waveform.
        components (list): List to store information about added components.
    """
    def __init__(self, duration, srate, nchannels=2):
        """
        Initializes a Sound object.

        Args:
            duration (float): Duration of the sound in seconds.
            srate (int): Sampling rate of the sound.
        """
        self.duration = duration
        self.srate = srate
        self.nchannels = nchannels        
        self.tvec = np.arange(0, self.duration, 1/self.srate)
        self.wave = np.zeros((len(self.tvec), self.nchannels))
        self.components = []

    def add_wave(self, wave, channel):
        if channel=='all':
            self.wave += np.tile(wave[:, np.newaxis], [1, self.nchannels])
        else:
            self.wave[:, channel] += wave

    def add_tone(self, freq, amp=1, channel='all'):
        """
        Adds a sine wave tone to the sound waveform.

        Args:
            freq (float): Frequency of the tone in Hertz.
            amp (float): Amplitude of the tone (default is 1).
            channel (int/str): Either a channel index or 'all'

        Returns:
            tuple: Time vector and the updated sound waveform.
        """
        wave = amp * np.sin(2*np.pi*freq*self.tvec)
        self.add_wave(wave, channel)
        self.components += [{'type':'tone', 'freq':freq, 'amp':amp,
                              'channel':channel}]
        return self.tvec, self.wave
    
    def add_noise(self, amp=1, channel='all'):
        """
        Adds random noise to the sound waveform.

        Args:
            amp (float): Amplitude of the noise (default is 1).

        Returns:
            tuple: Time vector and the updated sound waveform.
        """
        wave = amp * randomGen.uniform(-1, 1, len(self.tvec))
        self.add_wave(wave, channel)
        self.components += [{'type':'noise', 'amp':amp,
                             'channel':channel}]
        return self.tvec, self.wave
    
    def add_chord(self, midfreq, factor, ntones, amp=1, channel='all'):
        """
        Adds a chord (multiple tones) to the sound waveform.

        Args:
            midfreq (float): Mid-frequency of the chord in Hertz.
            factor (float): Factor determining how far the highest tone is from the midfreq.
            ntones (int): Number of tones in the chord.
            amp (float): Amplitude of the chord (default is 1).

        Returns:
            tuple: Time vector and the updated sound waveform.

        Notes:
        - Waveform amplitude is amp/sqrt(ntones) to match the RMS power of one tone at the same amp.
        - A chord with ntones=1 will create a tone at midfreq/factor, not at midfreq.

        """
        pass
        # freqEachComp = np.logspace(np.log10(midfreq/factor),
        #                            np.log10(midfreq*factor),
        #                            ntones)
        # phase = randomGen.uniform(-np.pi, np.pi, ntones)
        # chordAmp = amp/np.sqrt(ntones)
        # for indcomp, freqThisComp in enumerate(freqEachComp):
        #     self.wave += chordAmp*np.sin(2*np.pi * freqThisComp * self.tvec + phase[indcomp])
        # self.components += [{'type':'chord', 'midfreq':midfreq, 'factor':factor,
        #                      'ntones':ntones, 'amp':amp}]
        # return self.tvec, self.wave
    
    def add_from_file(self, soundfile, amp=1, channel='all', loop=False):
        """
        Add a sound from a file to sound waveform.
        
        Args:
            soundfile (str): Path to the WAV file to load.
            amp (float): Amplitude scaling factor (default is 1).
            channel (int/str): Either a channel index or 'all'.
            loop (bool): If True, loop the sound to fill the duration (default is False).
            
        Raises:
            ValueError: If the sampling rate of the file doesn't match the object's sampling rate.
            FileNotFoundError: If the soundfile doesn't exist.
            
        Returns:
            tuple: Time vector and the updated sound waveform.
        """
        # Load the WAV file
        if not os.path.exists(soundfile):
            raise FileNotFoundError(f"Sound file not found: {soundfile}")
        
        file_srate, file_wave = scipy.io.wavfile.read(soundfile)
        
        # Check if sampling rate matches
        if file_srate != self.srate:
            raise ValueError(f"Sampling rate mismatch: file has {file_srate} Hz, "
                           f"but Sound object is set to {self.srate} Hz. "
                           f"Resampling is not yet implemented.")
        
        # Convert to float and normalize if necessary
        if file_wave.dtype == np.int16:
            file_wave = file_wave.astype(np.float64) / 32767.0
        elif file_wave.dtype == np.int32:
            file_wave = file_wave.astype(np.float64) / 2147483647.0
        elif file_wave.dtype != np.float32 and file_wave.dtype != np.float64:
            file_wave = file_wave.astype(np.float64)
        
        # Handle mono vs stereo files
        if file_wave.ndim == 1:
            # Mono file
            file_wave = file_wave[:, np.newaxis]
        
        # Handle looping if requested
        if loop:
            n_samples_needed = len(self.tvec)
            n_samples_file = len(file_wave)
            if n_samples_file < n_samples_needed:
                n_repeats = int(np.ceil(n_samples_needed / n_samples_file))
                file_wave = np.tile(file_wave, (n_repeats, 1))
        
        # Trim or pad to match the duration
        n_samples = min(len(file_wave), len(self.tvec))
        wave = np.zeros(len(self.tvec))
        
        # Use the first channel of the file if it's multichannel
        wave[:n_samples] = amp * file_wave[:n_samples, 0]
        
        self.add_wave(wave, channel)
        self.components += [{'type': 'file', 'soundfile': soundfile, 'amp': amp,
                            'channel': channel, 'loop': loop}]
        return self.tvec, self.wave


    def apply_rise_fall(self, riseTime=0.002, fallTime=0.002):
        """
        Applies rise and fall envelope to the sound waveform.

        Args:
            riseTime (float): Rise time of the envelope in seconds (default is 2ms).
            fallTime (float): Fall time of the envelope in seconds (default is 2ms).

        Returns:
            tuple: Time vector and the updated sound waveform.
        """
        nSamplesRise = round(self.srate * riseTime)
        nSamplesFall = round(self.srate * fallTime)
        riseVec = np.linspace(0, 1, nSamplesRise)
        fallVec = np.linspace(1, 0, nSamplesFall)
        self.wave[:nSamplesRise] *= riseVec[:, np.newaxis]
        self.wave[-nSamplesFall:] *= fallVec[:, np.newaxis]
        return self.tvec, self.wave

    def suggest_filename(self, suffix=''):
        """
        Generates a suggested filename based on added components.

        Args:
            suffix (str): Optional suffix to append to the filename (default is '').

        Returns:
            str: Suggested filename.
        """
        filename = ''
        for comp in self.components:
            compStr = comp['type']
            if comp['type'] == 'tone':
                compStr += f'{comp["freq"]}Hz'
            if comp['type'] == 'chord':
                compStr += f'{comp["midfreq"]}Hz'
            filename += compStr
            filename += '_'
        return filename.strip('_') + suffix + '.wav'
    
    def save(self, wavefile, infofile=None, outdir='./'):
        """
        Saves the sound waveform as a WAV file along with a text file containing sound information.

        Args:
            wavefile (str): Filename for the WAV file.
            infofile (str): Filename for the text file containing component information
                            (default is the same as wavefile but with .txt extension).
            outdir (str): Directory to save the files (default is './').
        """
        if wavefile[-4:] != '.wav':
            print('Nothing saved. Your filename needs to end the extension ".wav"')
            return
        if np.any(self.wave>1) or np.any(self.wave<-1):
            print('WARNING! Your waveform extends beyond the (-1, 1) amplitude range, so it will contain spurious noise created by saturation.\n         Try reducing the amplitude when generating the sound.')
        wave16bit = (32767*self.wave).astype('int16')
        wavefileFull = os.path.join(outdir, wavefile)
        scipy.io.wavfile.write(wavefileFull, self.srate, wave16bit)
        if infofile is None:
            infofile = wavefile.replace('.wav','.txt')
        infofileFull = os.path.join(outdir, infofile)
        with open(infofileFull, 'w') as file:
            objStr = ''.join([str(cstr)+'\n' for cstr in self.components])
            file.write(objStr)
        print(f'Saved: {wavefileFull}\n       {infofileFull}')

if __name__ == '__main__':
    from matplotlib import pyplot as plt
    sound = Sound(0.01, 44100, nchannels=3)
    sound.add_tone(500, amp=0.5, channel=0)
    sound.add_tone(250, amp=0.2)
    sound.add_noise(0.1, channel=1)
    plt.clf()
    plt.plot(sound.tvec, sound.wave)
    plt.legend([str(ch) for ch in range(sound.nchannels)])
    plt.show()
    print(sound.components)

    splayer = SoundPlayer()
    splayer.set_sound(1, sound)
    splayer.play(1)
    


