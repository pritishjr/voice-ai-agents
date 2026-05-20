'''
This is from the LiveKit tutorials on the basics of building voice ai agents.
'''

import logging
import time 
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import JobContext, room_io, Agent, AgentServer, AgentSession
from livekit.plugins import silero, noise_cancellation

#semantic turn detection (multilingual): to reduce unwanted interruptions
from livekit.plugins.turn_detector.multilingual import MultilingualModel

#adding fallback adapters: secondary providers that prevent performance during model outages.
from livekit.agents import tts, llm, stt, inference

#calculating metrics:
from livekit.agents import AgentStateChangedEvent, MetricsCollectedEvent, metrics

#defining logger to track metrics for performance eval
logger = logging.getLogger(__name__)

load_dotenv()

#handles the behaviour of the agent
class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            #instructions = "You are a helpful voice agent."
            instructions = "You are a rockstar who is goofy and non-chalant voice AI for emotional support."
            "If I ask for help, keep it brief under 3 sentences."
        )
        
#handles dispatching the sessions
server = AgentServer()

#extracting VAD (to reuse)
vad = silero.VAD.load()

#configuring the voice pipeline:
#this runs when there is an active connection (participant) into the server.#creates an rtc session object and passes onto the entrypoint.
@server.rtc_session() 
async def entrypoint(ctx: JobContext):
    
    #defining the session pipeline:
    '''
    session = AgentSession(
        stt = "assemblyai/universal-streaming:en",
        llm = "openai/gpt-4.1-mini",
        tts = "cartesia/sonic-3:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc" #different voice ID
        vad=vad,
        turn_detection= MultilingualModel() #turn detection (multilingual)
    )
    '''
    
    #wrapping the session pipeline with inference fallback adapters:
    session = AgentSession(
            # LLM with fallback: OpenAI primary, Gemini backup
        llm=llm.FallbackAdapter(
            [
                inference.LLM(model="openai/gpt-4.1-mini"), #primary llm
                inference.LLM(model="google/gemini-2.5-flash"), #backup llm
            ]
        ),
        # STT with fallback: AssemblyAI primary, Deepgram backup
        stt=stt.FallbackAdapter(
            [
                inference.STT.from_model_string("assemblyai/universal-streaming:en"),
                inference.STT.from_model_string("deepgram/nova-3"),
            ]
        ),
        # TTS with fallback: Cartesia primary, Inworld backup
        tts=tts.FallbackAdapter(
            [
                inference.TTS.from_model_string("cartesia/sonic-3:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"),
                inference.TTS.from_model_string("inworld/inworld-tts-1"),
            ]
        ),
        vad = vad,
        turn_detection = MultilingualModel(),
        preemptive_generation= True #enables the llm to think while the user is speaking.
    )
    
    '''
    Collecting metrics before the session start: EVENT HANDLER
    - usage collector: aggregates data across all conversation turns (token counts: LLM, audio durations: STT and TTS, cost estimates)
    - 
    '''
    #aggregating data across all turns(over all responses):
    usage_collector = metrics.UsageCollector()
    #calculate metrics at end of utterance timing: whenever the turn-detection gets activated - called EOU
    last_eou_metric = metrics.EOUMetrics() | None = None
    
    #fires after each component finishes processing:
    @session.on("metrics_collected") #collecting the aggregated metrics
    def _on_metrics_collected(event: MetricsCollectedEvent):
        
        nonlocal last_eou_metric
        if event.metrics == "eou_metrics":
            last_eou_metric = event.metrics
        
        #logging each metric:
        metrics.log_metrics(event.metrics)
        usage_collector.collect(event.metrics) #aggregating
    
    async def log_usage(): #logging the per-session summary of metrics
        
        summary = usage_collector.get_summary()
        logger.info("Usage summary: %s", summary)
        
    # Fire log_usage when worker shuts down
    ctx.add_shutdown_callback(log_usage)
    
    
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

