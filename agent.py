'''
This is from the LiveKit tutorials on the basics of building voice ai agents.
'''

import logging
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import JobContext, room_io, Agent, AgentServer, AgentSession
from livekit.plugins import silero, noise_cancellation

#semantic turn detection (multilingual): to reduce unwanted interruptions
from livekit.plugins.turn_detector.multilingual import MultilingualModel

#loading the apis
load_dotenv()

#handles the behaviour of the agent
class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions = "You are a helpful voice agent."
        )
        
#handles dispatching the sessions
server = AgentServer()

#configuring the voice pipeline:

#this runs when there is an active connection (participant) into the server.#creates an rtc session object and passes onto the entrypoint.
@server.rtc_session() 
async def entrypoint(ctx: JobContext):
    
    #defining the session pipeline:
    session = AgentSession(
        stt = "assemblyai/universal-streaming:en",
        llm = "openai/gpt-4.1-mini",
        tts = "cartesia/sonic-3",
        vad = silero.VAD.load(),
        turn_detection= MultilingualModel() #turn detection (multilingual)
    )
    
    #starting the session with noise_cancellation enabled.
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=noise_cancellation.BVC(),  # Background voice cancellation
            ),
        ),
    )

def main():
    logging.basicConfig(level=logging.INFO)
    agents.cli.run_app(server)
    
if __name__ == "__main__":
    main()
    
#working voice agent: avg e2e latency ~3000ms

