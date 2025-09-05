"""
Create and present sounds.
"""

import sys
import os
import sounddevice as sd
import random
import numpy as np
#import scipy.io.wavfile

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
    def __init__(self):
        self.device = sd.default.device[1]  # Use default device
        self.sounds = {}

    def set_sound(self, name, sound):
        self.sounds[name] = sound

    def play(self, name):
        sound = self.sounds[name]
        sd.play(sound.wave, sound.srate, device=self.device)

    def play_noise(self, max_channels=2):
        tvec = np.linspace(0, SOUND_DURATION, int(SAMPLERATE * SOUND_DURATION), False)
        noise_wave = SOUND_AMPLITUDE * np.random.rand(len(tvec))
        multichan_output = np.tile(noise_wave[:,np.newaxis], (1, max_channels)).astype(np.float32)
        try:
            sd.play(multichan_output, SAMPLERATE, device=self.device)
        except Exception as e:
            print(f"Sound playback error: {e}")
        
        
    def play_tone(self, channel=0, max_channels=2):
        """
        Channels:
          0: left
          1: right
        """
        # Generate a sine wave
        tvec = np.linspace(0, SOUND_DURATION, int(SAMPLERATE * SOUND_DURATION), False)
        sine_wave = SOUND_AMPLITUDE * np.sin(2 * np.pi * SOUND_FREQUENCY * tvec)

        # Create multichan output
        multichan_output = np.zeros((len(sine_wave), max_channels), dtype=np.float32)
        multichan_output[:, channel] = sine_wave

        try:
            sd.play(multichan_output, SAMPLERATE, device=self.device)
            #sd.wait()  # Commented out as per user request to avoid slowing down video
        except Exception as e:
            #QMessageBox.warning(self, "Sound Error", f"Could not play sound: {e}\n"
            #                    "Please ensure your audio output device is correctly configured.")
            print(f"Sound playback error: {e}")
            ##self.reset_to_monitoring() # Reset state if sound fails

    
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
        freqEachComp = np.logspace(np.log10(midfreq/factor),
                                   np.log10(midfreq*factor),
                                   ntones)
        phase = randomGen.uniform(-np.pi, np.pi, ntones)
        chordAmp = amp/np.sqrt(ntones)
        for indcomp, freqThisComp in enumerate(freqEachComp):
            self.wave += chordAmp*np.sin(2*np.pi * freqThisComp * self.tvec + phase[indcomp])
        self.components += [{'type':'chord', 'midfreq':midfreq, 'factor':factor,
                             'ntones':ntones, 'amp':amp}]
        return self.tvec, self.wave
    
    def add_from_file(self, soundfile, amp=1, channel='all', loop=False):
        """
        Add a sound from a file to sound waveform
        """
        pass


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
        self.wave[:nSamplesRise] *= riseVec
        self.wave[-nSamplesFall:] *= fallVec
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
    splayer.set_sound('mix3', sound)
    splayer.play('mix3')
    


