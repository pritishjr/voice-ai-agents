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

#tools and MCP integration
import httpx
from livekit.agents import (
    function_tool,
    ToolError,
    RunContext
)

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
        
    @function_tool #below function becomes a tool that the llm can call
    async def weather_lookup( #coroutine that can be awaited via scheduling task
        self,
        context: RunContext, #gives access to the user data, speech handle .etc
        location: str #hints that help the llm to understand what is being asked (eg: city name/place)
    ) -> dict:
        
        #getting coordinates
        #asynchronous httpx client to get data concurrently
        async with httpx.AsyncClient() as client:
            geo_response = await client.get(
                "https://www.geocoding-api.open-meteo.com/v1/search", #url
                params = {'name': location, 'count': 1} #storage variables
            ) 
            geo_data = geo_response.json() #storing data in a json file.
            
            #error handling: in case we dont get the location right:
            if not geo_data.get("results"):
                raise ToolError("COULD NOT FIND LOCATION.")
            
            lat = geo_data["results"][0]["latitude"]
            lon = geo_data["results"][0]["longitude"]
            place_name = geo_data["results"][0]["name"]
            
            #now getting the weather conditions from the location.
            weather_response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,weather_code",
                    "temperature_unit": "celsius"
                }
            )
            weather = weather_response.json() #storing data
            
            #returning a dict for the LLM: (best practice)
            return {
                "location": place_name,
                "temperature_f": weather["current"]["temperature_2m"],
                "conditions": weather["current"]["weather_code"]
            }
            
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
        record=False #if we need to not store transcropts and logs for a particular session.
    )

def main():
    logging.basicConfig(level=logging.INFO)
    agents.cli.run_app(server)
    
if __name__ == "__main__":
    main()
    
#working voice agent: avg e2e latency ~3000ms

