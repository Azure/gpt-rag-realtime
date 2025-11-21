import json
import numpy as np
import base64


def _read_prompt_from_txt(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read().strip()

def float_to_16bit_pcm(float32_array):
    """
    Converts a numpy array of float32 amplitude data to a numpy array in int16 format.

    :param float32_array: A numpy array of float32 representing amplitude data.
    :return: A numpy array of int16 representing PCM data.
    """
    int16_array = np.clip(float32_array, -1, 1) * 32767
    return int16_array.astype(np.int16) 

def array_buffer_to_base64(array_buffer: bytearray) -> str:
    if array_buffer.dtype == np.float32:
        array_buffer = float_to_16bit_pcm(array_buffer)
    elif array_buffer.dtype == np.int16:
        array_buffer = array_buffer.tobytes()
    else:
        array_buffer = array_buffer.tobytes()

    return base64.b64encode(array_buffer).decode("utf-8")


async def recieve_audio_for_outbound_call(session, wss):
    """
    Receive audio data from the real-time session and send it over the WebSocket.

    :param session: The real-time session object.
    :param wss: The WebSocket connection to send audio data to.
    """
    print("Receiving audio for outbound call...")
    data = {
        "kind": "AudioData",
        "audioData": {
            "data": session,
        },
        "stopAudio": None
    }
    # serialized_data = json.dumps(data)
    await wss.send_json(data)
    print("Sent audio data over WebSocket.")
    return True

async def stop_audio(wss):
    """
    Send a stop audio signal over the WebSocket.

    :param wss: The WebSocket connection to send the stop audio signal to.
    """
    data = {
        "kind": "StopAudio",
        "audioData": None,
        "stopAudio": {}
    }
    serialized_data = json.dumps(data)
    await wss.send_text(serialized_data)
    return True

if __name__ == "__main__":
    prompt = _read_prompt_from_txt("src/agents/prompts/main.txt")
    print(prompt)