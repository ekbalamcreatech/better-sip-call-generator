"""
G.729 codec using libbcg729 via ctypes.
Encodes PCM16 audio to G.729 bitstream and decodes back.
G.729: 8kbps, 10ms frames, 80 samples per frame at 8kHz
"""
import ctypes
import ctypes.util
import os
import wave

# G.729 constants
SAMPLE_RATE = 8000
FRAME_SAMPLES = 80      # 10ms at 8kHz
FRAME_BYTES_G729 = 10   # G.729 produces 10 bytes per 10ms frame
FRAME_BYTES_PCM = 160   # 80 samples * 2 bytes (int16)

# load libbcg729
_lib = None

def _load_lib():
    global _lib
    if _lib is not None:
        return _lib
    paths = [
        "/usr/lib/x86_64-linux-gnu/libbcg729.so.0",
        "/usr/lib/x86_64-linux-gnu/libbcg729.so",
        "libbcg729.so.0"
    ]
    for path in paths:
        try:
            _lib = ctypes.CDLL(path)
            # encoder functions
            _lib.initBcg729EncoderChannel.restype = ctypes.c_void_p
            _lib.initBcg729EncoderChannel.argtypes = []
            _lib.bcg729Encoder.restype = None
            _lib.bcg729Encoder.argtypes = [
                ctypes.c_void_p,          # encoder state
                ctypes.POINTER(ctypes.c_int16),  # input PCM
                ctypes.POINTER(ctypes.c_uint8),  # output bitstream
                ctypes.POINTER(ctypes.c_uint8),  # output length
            ]
            # decoder functions
            _lib.initBcg729DecoderChannel.restype = ctypes.c_void_p
            _lib.initBcg729DecoderChannel.argtypes = []
            _lib.bcg729Decoder.restype = None
            _lib.bcg729Decoder.argtypes = [
                ctypes.c_void_p,          # decoder state
                ctypes.POINTER(ctypes.c_uint8),  # input bitstream
                ctypes.c_uint8,           # input length
                ctypes.c_uint8,           # frame erased flag
                ctypes.c_uint8,           # SID flag
                ctypes.c_uint8,           # voice activity
                ctypes.POINTER(ctypes.c_int16),  # output PCM
            ]
            print(f"G.729 codec loaded: {path}")
            return _lib
        except Exception:
            continue
    raise RuntimeError("Could not load libbcg729")

class G729Encoder:
    def __init__(self):
        lib = _load_lib()
        self._state = lib.initBcg729EncoderChannel()
        self._lib = lib

    def encode_frame(self, pcm_samples: bytes) -> bytes:
        """Encode one 10ms PCM16 frame (160 bytes) to G.729 (10 bytes)."""
        samples = (ctypes.c_int16 * FRAME_SAMPLES).from_buffer_copy(pcm_samples)
        output = (ctypes.c_uint8 * FRAME_BYTES_G729)()
        out_len = ctypes.c_uint8(0)
        self._lib.bcg729Encoder(self._state, samples, output, ctypes.byref(out_len))
        return bytes(output[:out_len.value])

    def encode_pcm(self, pcm_data: bytes) -> bytes:
        """Encode full PCM16 audio to G.729 bitstream."""
        result = bytearray()
        offset = 0
        while offset + FRAME_BYTES_PCM <= len(pcm_data):
            frame = pcm_data[offset:offset + FRAME_BYTES_PCM]
            encoded = self.encode_frame(frame)
            result.extend(encoded)
            offset += FRAME_BYTES_PCM
        return bytes(result)

class G729Decoder:
    def __init__(self):
        lib = _load_lib()
        self._state = lib.initBcg729DecoderChannel()
        self._lib = lib

    def decode_frame(self, g729_frame: bytes) -> bytes:
        """Decode one G.729 frame (10 bytes) to PCM16 (160 bytes)."""
        input_buf = (ctypes.c_uint8 * len(g729_frame)).from_buffer_copy(g729_frame)
        output = (ctypes.c_int16 * FRAME_SAMPLES)()
        self._lib.bcg729Decoder(
            self._state,
            input_buf,
            ctypes.c_uint8(len(g729_frame)),
            ctypes.c_uint8(0),  # not erased
            ctypes.c_uint8(0),  # not SID
            ctypes.c_uint8(1),  # voice activity
            output
        )
        return bytes(output)

    def decode_bitstream(self, g729_data: bytes) -> bytes:
        """Decode full G.729 bitstream to PCM16."""
        result = bytearray()
        offset = 0
        while offset + FRAME_BYTES_G729 <= len(g729_data):
            frame = g729_data[offset:offset + FRAME_BYTES_G729]
            decoded = self.decode_frame(frame)
            result.extend(decoded)
            offset += FRAME_BYTES_G729
        return bytes(result)

def wav_to_g729(wav_path: str, g729_path: str) -> bool:
    """Convert WAV file to raw G.729 bitstream."""
    try:
        with wave.open(wav_path, 'rb') as wf:
            if wf.getsampwidth() != 2:
                raise ValueError("WAV must be 16-bit PCM")
            if wf.getframerate() != SAMPLE_RATE:
                raise ValueError(f"WAV must be {SAMPLE_RATE}Hz")
            pcm_data = wf.readframes(wf.getnframes())

        encoder = G729Encoder()
        g729_data = encoder.encode_pcm(pcm_data)

        with open(g729_path, 'wb') as f:
            f.write(g729_data)

        print(f"G.729 encoded: {len(pcm_data)} PCM bytes -> {len(g729_data)} G.729 bytes")
        return True
    except Exception as e:
        print(f"G.729 encode error: {e}")
        return False

def g729_to_wav(g729_path: str, wav_path: str) -> bool:
    """Convert raw G.729 bitstream to WAV file."""
    try:
        with open(g729_path, 'rb') as f:
            g729_data = f.read()

        decoder = G729Decoder()
        pcm_data = decoder.decode_bitstream(g729_data)

        with wave.open(wav_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm_data)

        print(f"G.729 decoded: {len(g729_data)} G.729 bytes -> {len(pcm_data)} PCM bytes")
        return True
    except Exception as e:
        print(f"G.729 decode error: {e}")
        return False

def prepare_g729_reference(wav_path: str) -> str:
    """
    Prepare G.729 reference file from WAV.
    Returns path to G.729 file.
    """
    g729_path = wav_path.replace('.wav', '.g729')
    if not os.path.exists(g729_path):
        wav_to_g729(wav_path, g729_path)
    return g729_path

if __name__ == "__main__":
    # test
    print("Testing G.729 codec...")
    try:
        enc = G729Encoder()
        dec = G729Decoder()
        # create test PCM frame (silence)
        pcm = bytes(FRAME_BYTES_PCM)
        encoded = enc.encode_frame(pcm)
        decoded = dec.decode_frame(encoded)
        print(f"✓ Encode: {len(pcm)} bytes -> {len(encoded)} bytes")
        print(f"✓ Decode: {len(encoded)} bytes -> {len(decoded)} bytes")
        print("G.729 codec working!")
    except Exception as e:
        print(f"G.729 test failed: {e}")
