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
from livekit.agents import mcp 

#collecting consent and escalating to human agents:
from livekit.agents import AgentTask

#WORKFLOWS:
from livekit.agents.beta.workflows import TaskGroup
from dataclasses import dataclass

#for human handoff
from livekit.agents import get_job_context

#defining logger to track metrics for performance eval
logger = logging.getLogger(__name__)

load_dotenv()


#__________________________________



#handles the behaviour of the agent
class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            #instructions = "You are a helpful voice agent."
            instructions = "You are a rockstar who is goofy and non-chalant voice AI for emotional support."
            "If I ask for help, keep it brief under 3 sentences."
            "You can also answer about the weather when asked."
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
            #important to use ToolError here.
            
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
    
    #handling lojng-running tasks: lets say some functions take a long time. in that case, we need to inform the user. 
    @function_tool
    async def search_repository(
        self,
        context: RunContext,
        query: str
    ) -> str:
        
        #giving the user feedback that we are doing something.
        await context.session.say("This might take a while:")
        
        #assume an expensive function: expensive_function()
        '''
        results = await expensive_function(query)
        return results
        '''
        
        pass
            
    #we can also add a tool that disallows anny interruptions from the user:
    @function_tool
    async def rewrite_text(
        self,
        context: RunContext,
        query: str
    ) -> str:
        
        #syntax to disallow any interruptions while this tool is being executed.
        context.disallow_interruptions()
        
        #results = await write_text()
        #return results
        
        pass
    
    
#entire class for collecting consent? since this is a conversational "behaviour" that it must show. therefore it must belong to the AgentTask method. it is different from the function_tool decorator method which only makes certain functions to the LLM as tools.
class ConsentApproval(AgentTask[bool]): #must return a bool value at the end of the conversation to the main agent
    
    def __init__(self, chat_ctx) -> None:
        super().__init__( #here we define the personality/qualities spefically for this behaviour.
            instructions="""
                Be very sharp-spoken yet gentle and polite. Use professional mannerisms. I personally recommend you use a Victorian-British English tone.
            """,
            chat_ctx=chat_ctx #chat context: acts as a memory bank (holds the running transcripts) between the agents. so that the manager agent knows the semantic context of the turns/conversations.
        )
        
    async def on_entry(self) -> None:
        ask = self.session.generate_reply( #task scheduled
            instructions="""
                Ask the user to state his name for suthentication. Seek permissions for recording the conversation for quality purposes. Before that, briefly introduce yourself.
            """
        )
        result = await ask #executes the task concurrently.
        
    #we can also add a behaviour-specific tools. (points to the importance of this architecture)
    #the most important is either confirming whether the consesnt is approved or not.
    @function_tool
    async def consent_yes(self) -> None: #in case of YES
        self.complete(True) 
        
    @function_tool
    async def consent_no(self) -> None: #in case of NO
        self.complete(False)
    
#creating an agent manager on this:
class ManagerAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""
            You are a customer service manager. You handle escalated issues 
            that frontline agents couldn't resolve. Be empathetic and 
            solution-focused. You have authority to offer refunds, credits,
            or other accommodations.
            """,
            chat_ctx=self.chat_ctx,
            tts="cartesia/sonic-3:6f84f4b8-58a2-430c-8c79-688dad597532" #we can use a different voice/personality
        )
    
    async def on_entry(self) -> None:
        await self.session.generate_reply(
        instructions="""
            Introduca yourself as the manager of all the agents. Try to resolve the escalated issue. Ask how you can help with their concern.
        """
        )
    
    
#creating multiple speciallized agents:
#we can implement the consent approval architecture here
class CustomerCareAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""
                You are a cusotmer-care agent.
                Use the escalation_feedback tool when you feel the conversation is escalating.
            """,
        ) 
    
    #implementing the consent approval using the local class object
    async def on_entry(self, chat_ctx) -> None:
        consent = await ConsentApproval(chat_ctx) #using our Consent AgentTask 

        if consent:
            await self.session.generate_reply(
                instructions="Thank them and let know they are approved."
             )
        else:
            await self.session.generate_reply(
                instructions="Reject them politely."
            ) 
    
    #adding an escalation tool: transfers the call to the manager agent
    @function_tool
    async def escalation_feedback(self, context: RunContext) -> ManagerAgent:
        #the session hands off the control to the ManagerAgent.
        #tool docstring:
        """Transfer the customer to a manager when requested or when you cannot resolve their issue."""
        #using the chat context for the 
        return ManagerAgent(self.chat_ctx),"Transferring you to a manager now."


######-------- Multi-step Agent WORKFLOWS using Task Groups: --------#######

#task to get the user's email address.
#we are basically saying that the email_result must be a data object/container with a str attribute which contains the address.
@dataclass
class EmailResult:
    email_address: str

#task to get the user's shipping address
@dataclass
class AddressRResults:
    address: str
    
#only job of this "task-agent" is to intake email.
#wont move further until it returns "self.complete" to finish the agent-task
class GetEmailAddress(AgentTask[EmailResult]):
    def __init__(self) -> None:
        super().__init__(
            instructions="""
                Collect the user's email address.
                Use the getting_email function to accept the email address input of the user.
            """
        )

    @function_tool
    async def getting_email(self, context: RunContext, email:str) -> None:
        #tool docstring:
        """Record the user's email address."""
        
        self.complete(EmailResult(email_address=email))

#task-agent: to accept the address/location of the user.
class GetShippingAddress(AgentTask[AddressRResults]):
    def __init__(self) -> None:
        super().__init__(
            instructions="""
                Get the shipping address from the user.
            """
        )

    @function_tool
    async def record_email(self, context: RunContext, address: str) -> None:
        #tool docstring:
        """Record the user's shipping address."""
        
        self.complete(AddressRResults(address=address))
        
#finally the main agent that handles these task groups: using a WORKFLOW
class CheckOutAgent(Agent):
    
    async def on_entry(self) -> None:
        
        #a taskgroup class object allows an agent to orchestrate a sequence(!) of  multiple-agent tasks. also allows regression to the previous tasks on request.
        task_group = TaskGroup()
        
        #initializing the task group object:
        task_group.add( #task1
            lambda: GetEmailAddress(), #wraps with lambda to allow regression
            id = "email",
            description="Collecting the user's email id/address."
        )
        task_group.add( #task2
            lambda: GetShippingAddress(),
            id="address",
            description="Collecting the user's shipping address."
        )
        #sequencially and concurrently running the tasks.
        results = await task_group
        
        email_add = results.task_results["email"].email_address
        shipping_add = results.task_results["address"].address
        
        #awaiting to execute the 
        await self.session.generate_reply(
            instructions=f"Confirm to the user that the order will be sent to {email_add} at the address {shipping_add}"
        )
        
# HUMAN HANDOFF (when in need):
@function_tool
async def human_handoff(self, context: RunContext) -> None:
    #tool docstring:
    """Transfer the call to a human agent."""
    
    context.disallow_interruptions() 
    #no interruptions while you transfer the call.
    
    await context.session.say(
        "Transfering you to a human agent. Please wait for a moment."
    )

    room = get_job_context().room
    await room.local_participant.publish_sip_participant(
        sip_trunk_id="your-trunk-id", #example
        dial_to="sip:support@your-pbx.com", #example
    )

######------#####-------######-------######-------#####-------########


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
        preemptive_generation= True, #enables the llm to think while the user is speaking.
        mcp_servers=[
            mcp.MCPServerHTTP("https://docs.livekit.io/mcp") #connecting to an MCP server (here livekit docs)
        ]
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

