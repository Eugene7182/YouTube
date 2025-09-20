import asyncio
import edge_tts

async def synth(text: str, out_path: str, voice: str = "en-US-JennyNeural"):
    tts = edge_tts.Communicate(text, voice=voice, rate="+0%")
    await tts.save(out_path)

def synth_sync(text: str, out_path: str, voice: str = "en-US-JennyNeural"):
    asyncio.run(synth(text, out_path, voice))
